"""Outbound email service for taxpayer reconciliation notifications.

Coordinates SMTP configuration, per-taxpayer recipient planning (resolved
from the run's imported accounting data), template rendering and delivery
tracking, then hands the finished message to the transport provider.

The only workflow today is ``reconciliation.discrepancies`` - when a
reconciliation run finishes, every taxpayer/counterparty with at least one
affected invoice (mismatched, missing from the tax authority records or
invalid) receives a single grouped summary email. Internal users are never
recipients, and the organisation's billing email is never a fallback.

All notifications are best-effort: ``notify_run_summary`` never raises for a
disabled module or empty results, and the reconciliation service swallows
transport failures so an email problem can never corrupt application data.
Every planned delivery is recorded in ``email_deliveries`` - including the
"no email", "invalid" and "disabled/skipped" outcomes - so administrators
can audit and explicitly resend. Transport exceptions from ``send_test`` and
``resend_delivery`` are propagated so API callers can surface them.
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional

from backend.middleware import get_request_id
from backend.modules.audit_trail.model import AuditLog
from backend.modules.audit_trail.service import record_event
from backend.modules.email import templates
from backend.modules.email.model import (
    DELIVERY_FAILED,
    DELIVERY_INVALID,
    DELIVERY_NO_EMAIL,
    DELIVERY_PENDING,
    DELIVERY_SENT,
    DELIVERY_SKIPPED,
    EmailDelivery,
)
from backend.modules.email.provider import (
    EmailAuthError,
    EmailConfig,
    EmailConfigError,
    EmailDisabledError,
    EmailTransportError,
    EmailValidationError,
    SMTPEmailProvider,
)
from backend.modules.email.validator import is_valid_email, validate_email

logger = logging.getLogger(__name__)


EMAIL_WORKFLOWS = {
    "reconciliation.discrepancies": {
        "description": (
            "After a reconciliation run, email a grouped summary to every "
            "taxpayer/counterparty whose invoices were affected by a "
            "discrepancy."
        ),
    },
}

# Provider exceptions that should be surfaced to admins as send failures.
_PROVIDER_FAILURE_EXC = (EmailAuthError, EmailTransportError, EmailConfigError)


def _failure_reason(exc: Exception) -> str:
    if isinstance(exc, EmailAuthError):
        return "SMTP authentication failed"
    if isinstance(exc, EmailTransportError):
        return "SMTP delivery failed"
    if isinstance(exc, EmailConfigError):
        return "Invalid email configuration"
    return "Unexpected sending error"


class EmailService:
    """Builds and sends per-taxpayer notifications under the SMTP settings."""

    def __init__(
        self,
        config_mapping,
        company_repo=None,
        delivery_repo=None,
        recon_repo=None,
        provider=None,
    ):
        self._config = EmailConfig.from_mapping(config_mapping)
        self._config.validate()
        self._provider = provider or SMTPEmailProvider(self._config)
        self._company_repo = company_repo
        self._delivery_repo = delivery_repo
        self._recon_repo = recon_repo

    @property
    def enabled(self) -> bool:
        return self._config.enabled

    @property
    def config(self) -> EmailConfig:
        return self._config

    def get_status(self) -> dict:
        """Public status, safe to expose over the API (no credentials)."""
        return {
            "enabled": self._config.enabled,
            "provider": self._config.provider if self._config.enabled else None,
            "host": self._config.host,
            "port": self._config.port,
            "from_addr": self._config.from_addr if self._config.enabled else None,
            "use_tls": self._config.use_tls,
            "use_ssl": self._config.use_ssl,
            "workflows": [
                {"name": name, "description": spec["description"]}
                for name, spec in EMAIL_WORKFLOWS.items()
            ],
        }

    # ------------------------------------------------------------------
    # Reconciliation summary deliveries
    # ------------------------------------------------------------------

    def notify_run_summary(self, run, rows: List[dict]) -> dict:
        """Plan, record and send one summary email per affected taxpayer.

        Args:
            run: The persisted ReconciliationRun.
            rows: Affected result rows (see the reconciliation repository's
                ``list_affected_results_with_party``) with counterparty
                contact data.

        Returns:
            A summary dictionary of planned/attempted deliveries.
        """
        if not rows:
            return {"planned": 0, "sent": 0, "failed": 0, "skipped": 0,
                    "no_email": 0, "invalid": 0}

        request_id = get_request_id() or ""
        enabled = self._config.enabled
        taxpayer_plan = self._plan_recipients(rows)

        planned = 0
        sent = 0
        failed = 0
        skipped = 0
        no_email = 0
        invalid = 0

        for group in taxpayer_plan:
            delivery = self._create_delivery_record(run, group, enabled)
            planned += 1
            if delivery.status == DELIVERY_SENT:
                sent += 1
            elif delivery.status == DELIVERY_FAILED:
                failed += 1
            elif delivery.status == DELIVERY_SKIPPED:
                skipped += 1
            elif delivery.status == DELIVERY_NO_EMAIL:
                no_email += 1
            elif delivery.status == DELIVERY_INVALID:
                invalid += 1
            else:
                outcome = self._attempt_delivery(run, group, delivery, request_id)
                if outcome == DELIVERY_SENT:
                    sent += 1
                else:
                    failed += 1

        logger.info(
            "Reconciliation summary email planned=%d sent=%d failed=%d "
            "skipped=%d no_email=%d invalid=%d (run=%s request_id=%s)",
            planned, sent, failed, skipped, no_email, invalid,
            run.id, request_id,
        )
        return {
            "planned": planned,
            "sent": sent,
            "failed": failed,
            "skipped": skipped,
            "no_email": no_email,
            "invalid": invalid,
        }

    def list_deliveries(self, run_id: int, company_id: int) -> List[dict]:
        """Delivery rows for a run, scoped to a company, newest first."""
        if self._delivery_repo is None:
            return []
        deliveries = self._delivery_repo.list_by_run(run_id)
        scoped = [
            delivery for delivery in deliveries
            if delivery.company_id == company_id
        ]
        return [delivery.to_dict() for delivery in scoped]

    def resend_delivery(
        self, run_id: int, delivery_id: int, company_id: int
    ) -> Optional[dict]:
        """Explicitly resend one delivery for a run.

        The delivery must belong to the run and to the calling company, and
        must carry a valid recipient address. Content is rebuilt from the
        run's affected results so nothing sensitive is stored or replayed.

        Raises:
            EmailDisabledError: If email is not enabled.
            EmailValidationError: If the stored recipient is unusable.
        """
        if not self._config.enabled:
            raise EmailDisabledError("Email is not enabled")

        if self._delivery_repo is None:
            return None
        delivery = self._delivery_repo.get_by_id(delivery_id)
        if delivery is None:
            return None
        if delivery.run_id != run_id or delivery.company_id != company_id:
            return None

        recipient = (delivery.recipient_email or "").strip()
        if not is_valid_email(recipient):
            raise EmailValidationError(
                f"Cannot resend to invalid address: {recipient!r}"
            )

        rows = []
        if self._recon_repo is not None:
            rows = self._recon_repo.list_affected_results_with_party(run_id)
        group = self._find_plan_group(rows, recipient)
        if group is None:
            return None

        run = self._resend_run(run_id, delivery.company_id)
        request_id = get_request_id() or ""
        subject, text_body, html_body = self._render_messages(run, group)
        try:
            self._provider.send(
                to=[recipient],
                subject=subject,
                text_body=text_body,
                html_body=html_body,
                request_id=request_id,
            )
            self._delivery_repo.mark_sent(delivery.id, request_id, subject)
            record_event(
                action=AuditLog.ACTION_UPDATE,
                resource_type="email_delivery",
                resource_id=str(delivery.id),
                result=AuditLog.RESULT_SUCCESS,
                company_id=delivery.company_id,
                metadata={"event": "resend", "run_id": run_id},
            )
        except EmailDisabledError:
            raise
        except _PROVIDER_FAILURE_EXC as exc:
            logger.error(
                "Email resend failed delivery=%s request_id=%s: %s",
                delivery.id, request_id, exc,
            )
            reason = _failure_reason(exc)
            self._delivery_repo.mark_failed(delivery.id, reason)
            record_event(
                action=AuditLog.ACTION_UPDATE,
                resource_type="email_delivery",
                resource_id=str(delivery.id),
                result=AuditLog.RESULT_FAILURE,
                company_id=delivery.company_id,
                metadata={"event": "resend", "run_id": run_id, "reason": reason},
            )
            raise

        refreshed = self._delivery_repo.get_by_id(delivery.id)
        return refreshed.to_dict() if refreshed else None

    def send_test(self, to: str, request_id: str = "") -> dict:
        """Send a diagnostic test message to a single address.

        Raises:
            EmailDisabledError: If email is not enabled.
            EmailValidationError: If the address is malformed.
            EmailAuthError / EmailTransportError: On SMTP failure.
        """
        if not self._config.enabled:
            raise EmailDisabledError("Email is not enabled")
        to = validate_email(to)
        request_id = request_id or get_request_id() or ""
        subject = "E-Invoice email test"
        text_body = (
            "This is a test message from the E-Invoice system.\n"
            f"Smtp config: host={self._config.host}, port={self._config.port}\n"
            f"Request id: {request_id}"
        )
        html_body = (
            "<html><body style=\"font-family: Arial, sans-serif;\">"
            "<h2>E-Invoice email test</h2>"
            "<p>This is a test message from the E-Invoice system.</p>"
            f"<p>Sent {datetime.now(timezone.utc).isoformat()}Z</p>"
            "</body></html>"
        )
        self._provider.send(
            to=[to],
            subject=subject,
            text_body=text_body,
            html_body=html_body,
            request_id=request_id,
        )
        record_event(
            action=AuditLog.ACTION_OTHER,
            resource_type="email",
            result=AuditLog.RESULT_SUCCESS,
            metadata={"event": "send_test", "to": to},
        )
        return {"delivered": True, "to": to, "request_id": request_id}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _create_delivery_record(self, run, group: dict, enabled: bool) -> EmailDelivery:
        email = group.get("recipient_email")
        if not group.get("has_email"):
            delivery = EmailDelivery(
                company_id=run.company_id,
                run_id=run.id,
                recipient_email=None,
                taxpayer_name=group.get("taxpayer_name"),
                taxpayer_tax_id=group.get("taxpayer_tax_id"),
                invoice_count=len(group.get("invoices") or []),
                status=DELIVERY_NO_EMAIL,
                failure_reason="The counterparty has no email address on record.",
                subject=self._subject_for(run),
            )
        elif not group.get("email_valid"):
            delivery = EmailDelivery(
                company_id=run.company_id,
                run_id=run.id,
                recipient_email=email,
                taxpayer_name=group.get("taxpayer_name"),
                taxpayer_tax_id=group.get("taxpayer_tax_id"),
                invoice_count=len(group.get("invoices") or []),
                status=DELIVERY_INVALID,
                failure_reason="The counterparty email address is invalid.",
                subject=self._subject_for(run),
            )
        elif not enabled:
            delivery = EmailDelivery(
                company_id=run.company_id,
                run_id=run.id,
                recipient_email=email,
                taxpayer_name=group.get("taxpayer_name"),
                taxpayer_tax_id=group.get("taxpayer_tax_id"),
                invoice_count=len(group.get("invoices") or []),
                status=DELIVERY_SKIPPED,
                failure_reason="Email sending is disabled in the server configuration.",
                subject=self._subject_for(run),
            )
        else:
            delivery = EmailDelivery(
                company_id=run.company_id,
                run_id=run.id,
                recipient_email=email,
                taxpayer_name=group.get("taxpayer_name"),
                taxpayer_tax_id=group.get("taxpayer_tax_id"),
                invoice_count=len(group.get("invoices") or []),
                status=DELIVERY_PENDING,
                subject="",
            )
        if self._delivery_repo is not None:
            delivery = self._delivery_repo.create(delivery)
        return delivery

    def _attempt_delivery(self, run, group: dict, delivery, request_id: str) -> str:
        recipient = group.get("recipient_email")
        subject, text_body, html_body = self._render_messages(run, group)
        try:
            self._provider.send(
                to=[recipient],
                subject=subject,
                text_body=text_body,
                html_body=html_body,
                request_id=request_id,
            )
            if self._delivery_repo is not None:
                self._delivery_repo.mark_sent(delivery.id, request_id, subject)
            logger.info(
                "Email sent recipient=%s run=%s request_id=%s",
                recipient, run.id, request_id,
            )
            return DELIVERY_SENT
        except Exception as exc:
            logger.error(
                "Email send failed recipient=%s run=%s request_id=%s: %s",
                recipient, run.id, request_id, exc,
            )
            reason = _failure_reason(exc)
            if self._delivery_repo is not None:
                self._delivery_repo.mark_failed(delivery.id, reason)
            return DELIVERY_FAILED

    def _render_messages(self, run, group: dict):
        context = {
            "company_id": run.company_id,
            "company_name": self._company_name(run.company_id),
            "period": run.period,
            "taxpayer": {
                "name": group.get("taxpayer_name"),
                "tax_id": group.get("taxpayer_tax_id"),
            },
            "invoices": group.get("invoices") or [],
        }
        return templates.render_reconciliation_discrepancy(context)

    def _subject_for(self, run) -> str:
        company = self._company_name(run.company_id) or f"Company #{run.company_id}"
        return (
            f"[{templates.APP_NAME}] Reconciliation notice - {company} "
            f"({run.period})"
        )

    @staticmethod
    def _plan_recipients(rows: List[dict]) -> List[dict]:
        """Group affected rows into one plan entry per recipient.

        Recipients are grouped by normalized email; taxpayers without a
        usable email are grouped by their party identity (name + tax id) so
        a single "no email" delivery is recorded for all their invoices.
        """
        groups: dict = {}
        for row in rows:
            email = (row.get("counterparty_email") or "").strip()
            email_valid = is_valid_email(email)
            has_email = bool(email)
            name = (row.get("counterparty_name") or "").strip() or None
            tax_id = (row.get("counterparty_tax_id") or "").strip() or None

            if email_valid:
                key = ("email", email.lower())
            elif has_email:
                key = ("bad-email", email.lower())
            else:
                key = ("party", name, tax_id)

            group = groups.get(key)
            if group is None:
                group = {
                    "recipient_email": email.lower() if email else None,
                    "email_valid": email_valid,
                    "has_email": has_email,
                    "taxpayer_name": name,
                    "taxpayer_tax_id": tax_id,
                    "invoices": [],
                }
                groups[key] = group

            if name and not group["taxpayer_name"]:
                group["taxpayer_name"] = name
            if tax_id and not group["taxpayer_tax_id"]:
                group["taxpayer_tax_id"] = tax_id

            group["invoices"].append({
                "invoice_number": row.get("invoice_number"),
                "invoice_date": row.get("invoice_date"),
                "match_status": row.get("match_status"),
                "total_amount": row.get("total_amount"),
                "discrepancy_amount": row.get("discrepancy_amount"),
            })

        return list(groups.values())

    def _find_plan_group(self, rows: List[dict], recipient: str):
        for group in self._plan_recipients(rows):
            if group.get("recipient_email") == (recipient or "").lower():
                return group
        return None

    def _resend_run(self, run_id: int, company_id: Optional[int]):
        """The run a resend belongs to, or a minimal safe fallback context."""
        run = None
        if self._recon_repo is not None:
            loader = getattr(self._recon_repo, "get_run_by_id", None)
            if callable(loader):
                try:
                    run = loader(run_id)
                except Exception:
                    logger.exception("Failed to load run %s for a resend", run_id)
                    run = None
        if run is not None:
            return run
        from types import SimpleNamespace
        return SimpleNamespace(id=run_id, company_id=company_id, period="")

    def _company_name(self, company_id):
        company = None
        if self._company_repo is not None and company_id is not None:
            company = self._company_repo.get_by_id(company_id)
        if company and getattr(company, "name", None):
            return company.name
        return f"Company #{company_id}" if company_id else None