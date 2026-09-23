"""Reconciliation service: orchestrates reconciliation runs end to end.

The service owns the run lifecycle:

1. create the run row as ``pending``,
2. mark it ``running`` with a start time,
3. load the company's accounting invoices and tax authority invoices for the
   target period,
4. run the pure reconciliation engine,
5. persist results, errors and the ``completed`` status in a single
   transaction,
6. on a fatal database/system error, mark the run ``failed`` and re-raise,
7. best-effort email notifications for the completed run, after the
   transaction is committed.

Individual invoice mismatches are expected outcomes, not errors. The run is
never reported successful unless every result row was persisted atomically.
Email notification failures are logged and never change the run outcome.
"""

import logging
import math
from decimal import Decimal
from typing import List, Optional

from backend.modules.reconciliation import contract as c
from backend.modules.reconciliation import export as report_export
from backend.modules.reconciliation.engine import (
    ReconcileOutcome,
    is_valid_period,
    normalize_period,
    reconcile,
)
from backend.modules.reconciliation.model import (
    ReconciliationRun,
)
from backend.modules.audit_trail.model import AuditLog
from backend.modules.audit_trail.service import record_event

logger = logging.getLogger(__name__)


class ReconciliationService:
    """Coordinates reconciliation runs for a company and period."""

    def __init__(
        self,
        recon_repo,
        invoice_repo,
        tax_repo,
        user_repo=None,
        email_service=None,
    ) -> None:
        self._recon_repo = recon_repo
        self._invoice_repo = invoice_repo
        self._tax_repo = tax_repo
        self._user_repo = user_repo
        self._email_service = email_service

    def company_for_user(self, user_id: int) -> Optional[int]:
        """Resolve the company id a user belongs to, if any."""
        if self._user_repo is None:
            return None
        user = self._user_repo.get_by_id(user_id)
        if user is None:
            return None
        return user.company_id

    def recover_interrupted(self) -> int:
        """Mark any run left in a temporary state as failed.

        Called once at application startup so runs interrupted by a crash are
        surfaced as ``failed`` instead of staying ``pending``/``running``
        forever. A run in a temporary state at startup has no persisted
        results (those commit atomically with the ``completed`` status), so
        marking it ``failed`` never discards real outcomes.

        Returns:
            The number of runs transitioned to ``failed``.
        """
        return self._recon_repo.recover_interrupted_runs()

    def start_run(
        self,
        company_id: int,
        period: str,
        money_tolerance: Optional[Decimal] = None,
    ) -> tuple:
        """Run a full reconciliation for a company and 'YYYY-MM' period.

        Starts are idempotent per (company_id, period): when an in-flight run
        already exists for the same period it is returned instead of creating
        a duplicate run.  Completed or failed runs do not block a new attempt.

        Args:
            company_id: Owning company id.
            period: Billing period as 'YYYY-MM'.
            money_tolerance: Optional tolerance for money comparisons.

        Returns:
            ``(run, summary_counts, is_new)``.  ``is_new`` is ``True`` when a
            new run was created and ``False`` when an in-flight run already
            existed for the period and was returned instead.  ``run`` is the
            completed run on a fresh start or the existing in-flight run on a
            duplicate request; ``summary_counts`` is the per-status breakdown.

        Raises:
            ValueError: if the period is malformed.
        """
        normalized = normalize_period(period)
        if not is_valid_period(normalized):
            raise ValueError(
                f"Invalid period '{period}'. Expected a 'YYYY-MM' period."
            )

        run, is_new = self._recon_repo.create_run_exclusive(
            company_id, normalized
        )
        if not is_new:
            return run, self.get_summary(run.id), False

        logger.info(
            "Reconciliation started run=%s company=%s period=%s",
            run.id, company_id, normalized,
        )
        self._recon_repo.start_run(run.id)

        try:
            account_invoices = self._invoice_repo.list_by_company_and_period(
                company_id, normalized
            )
            tax_invoices = self._tax_repo.list_by_company_and_period(
                company_id, normalized
            )
            outcome = reconcile(
                account_invoices,
                tax_invoices,
                money_tolerance=money_tolerance,
            )
        except Exception as exc:
            logger.exception("Reconciliation run %s failed", run.id)
            self._fail_run(run.id)
            record_event(
                action=AuditLog.ACTION_RECONCILE,
                resource_type="reconciliation",
                resource_id=str(run.id),
                result=AuditLog.RESULT_FAILURE,
                company_id=company_id,
                metadata={
                    "period": normalized,
                    "phase": "reconcile",
                },
            )
            raise

        counts = self._counts(outcome)
        try:
            completed = self._recon_repo.finish_run_transaction(
                run.id,
                outcome.results,
                outcome.errors,
                invoice_count=len(account_invoices),
                tax_invoice_count=len(tax_invoices),
                matched_count=counts[c.MATCHED],
                unmatched_count=counts[c.MISMATCHED]
                + counts[c.MISSING_IN_TAX_AUTHORITY]
                + counts[c.EXTRA_IN_TAX_AUTHORITY]
                + counts[c.INVALID],
                error_count=len(outcome.errors),
            )
        except Exception as exc:
            logger.exception(
                "Failed to persist outcomes for reconciliation run %s", run.id
            )
            self._fail_run(run.id)
            record_event(
                action=AuditLog.ACTION_RECONCILE,
                resource_type="reconciliation",
                resource_id=str(run.id),
                result=AuditLog.RESULT_FAILURE,
                company_id=company_id,
                metadata={
                    "period": normalized,
                    "phase": "persist",
                },
            )
            raise

        if not completed:
            logger.error(
                "Reconciliation run %s could not be completed (status no "
                "longer eligible; likely recovered as interrupted)",
                run.id,
            )
            self._fail_run(run.id)
            record_event(
                action=AuditLog.ACTION_RECONCILE,
                resource_type="reconciliation",
                resource_id=str(run.id),
                result=AuditLog.RESULT_FAILURE,
                company_id=company_id,
                metadata={
                    "period": normalized,
                    "phase": "persist",
                    "reason": "run_no_longer_in_flight",
                },
            )
            raise RuntimeError(
                "Reconciliation run could not be completed because it was "
                "no longer in a running state"
            )

        persisted = self._recon_repo.get_run_by_id(run.id)
        record_event(
            action=AuditLog.ACTION_RECONCILE,
            resource_type="reconciliation",
            resource_id=str(run.id),
            result=AuditLog.RESULT_SUCCESS,
            company_id=company_id,
            metadata={
                "period": normalized,
                "invoice_count": counts[c.MATCHED]
                + counts[c.MISMATCHED]
                + counts[c.MISSING_IN_TAX_AUTHORITY]
                + counts[c.EXTRA_IN_TAX_AUTHORITY]
                + counts[c.INVALID],
                "matched": counts[c.MATCHED],
                "unmatched": counts[c.MISMATCHED]
                + counts[c.MISSING_IN_TAX_AUTHORITY]
                + counts[c.EXTRA_IN_TAX_AUTHORITY]
                + counts[c.INVALID],
                "errors": len(outcome.errors),
            },
        )
        logger.info(
            "Reconciliation completed run=%s company=%s period=%s matched=%d "
            "unmatched=%d errors=%d",
            run.id,
            company_id,
            normalized,
            counts[c.MATCHED],
            counts[c.MISMATCHED]
            + counts[c.MISSING_IN_TAX_AUTHORITY]
            + counts[c.EXTRA_IN_TAX_AUTHORITY]
            + counts[c.INVALID],
            len(outcome.errors),
        )
        self._notify_discrepancies(persisted)
        return persisted, counts, True

    def get_run(self, run_id: int, company_id: int) -> Optional[ReconciliationRun]:
        """Fetch a run by id, scoped to a company."""
        run = self._recon_repo.get_run_by_id(run_id)
        if run is None or run.company_id != company_id:
            return None
        return run

    def list_runs(
        self, company_id: int, limit: int = 50, offset: int = 0
    ) -> List[ReconciliationRun]:
        """List a company's runs, newest first."""
        return self._recon_repo.list_runs_by_company(
            company_id, limit=limit, offset=offset
        )

    def get_summary(self, run_id: int) -> dict:
        """Per-status result counts for a run, zero-filled."""
        raw = self._recon_repo.get_results_summary(run_id)
        return {status: int(raw.get(status, 0)) for status in c.RESULT_STATUSES}

    def get_results(self, run_id: int, company_id: int) -> Optional[List[dict]]:
        """Fetch a run's results (enriched), scoped to a company."""
        if self.get_run(run_id, company_id) is None:
            return None
        return self._recon_repo.get_results_with_details(run_id)

    def get_errors(self, run_id: int, company_id: int):
        """Fetch a run's errors, scoped to a company."""
        if self.get_run(run_id, company_id) is None:
            return None
        return self._recon_repo.list_errors(run_id)

    # ------------------------------------------------------------------
    # Reports
    # ------------------------------------------------------------------

    def resend_email_delivery(
        self, run_id: int, delivery_id: int, company_id: int
    ):
        """Explicitly resend one email delivery for a run, scoped to a company.

        Returns the refreshed delivery dict on success, or ``None`` when the
        run is not accessible, email is not wired up, or the delivery does
        not belong to the run/company. Transport and validation failures are
        propagated to the route so they can be surfaced to the caller.
        """
        if self.get_run(run_id, company_id) is None or self._email_service is None:
            return None
        return self._email_service.resend_delivery(run_id, delivery_id, company_id)

    def list_email_deliveries(
        self, run_id: int, company_id: int
    ) -> Optional[List[dict]]:
        """Delivery rows for a run, scoped to a company (newest first)."""
        if self.get_run(run_id, company_id) is None or self._email_service is None:
            return None
        return self._email_service.list_deliveries(run_id, company_id)

    # ------------------------------------------------------------------
    # Report summary
    # ------------------------------------------------------------------

    def get_report_summary(self, run_id: int, company_id: int) -> Optional[dict]:
        """Structured summary of a run, scoped to a company.

        Counts come from the persisted run's result rows (SQL aggregation)
        and the persisted error table — reconciliation is never re-run to
        produce the summary.
        """
        run = self.get_run(run_id, company_id)
        if run is None:
            return None
        statuses = self._recon_repo.get_results_summary(run_id)
        counts = {status: int(statuses.get(status, 0)) for status in c.RESULT_STATUSES}
        total = sum(counts.values())
        return {
            "run": run.to_dict(),
            "summary": {
                **counts,
                "total_results": total,
                "unmatched": total - counts[c.MATCHED],
                "errors": self._recon_repo.count_errors(run_id),
            },
        }

    def paginate_results(
        self,
        run_id: int,
        company_id: int,
        page: int,
        page_size: int,
        filters: Optional[dict] = None,
    ) -> Optional[dict]:
        """Paginated, filtered results for a run, scoped to a company."""
        if self.get_run(run_id, company_id) is None:
            return None
        query_filters = filters or {}
        total = self._recon_repo.count_results(run_id, query_filters)
        offset = (page - 1) * page_size
        items = self._recon_repo.list_results_report(
            run_id, limit=page_size, offset=offset, filters=query_filters
        )
        return self._envelope(items, total, page, page_size)

    def paginate_errors(
        self,
        run_id: int,
        company_id: int,
        page: int,
        page_size: int,
        filters: Optional[dict] = None,
    ) -> Optional[dict]:
        """Paginated, filtered errors for a run, scoped to a company."""
        if self.get_run(run_id, company_id) is None:
            return None
        query_filters = filters or {}
        total = self._recon_repo.count_errors(run_id, query_filters)
        offset = (page - 1) * page_size
        items = self._recon_repo.list_errors_report(
            run_id, limit=page_size, offset=offset, filters=query_filters
        )
        return self._envelope(items, total, page, page_size)

    def export_results(
        self,
        run_id: int,
        company_id: int,
        fmt: str,
        filters: Optional[dict] = None,
    ) -> Optional[tuple]:
        """Export a run's results (filtered) as csv/xlsx, scoped to a company.

        Returns ``(filename, mimetype, payload)`` or None when the run is not
        accessible. The full filtered dataset is streamed from the repository
        in batches.
        """
        if self.get_run(run_id, company_id) is None:
            return None
        rows = self._recon_repo.iter_results_report(run_id, filters or {})
        payload, mimetype, extension = report_export.build_file("results", rows, fmt)
        return f"reconciliation_results_{run_id}.{extension}", mimetype, payload

    def export_errors(
        self,
        run_id: int,
        company_id: int,
        fmt: str,
        filters: Optional[dict] = None,
    ) -> Optional[tuple]:
        """Export a run's errors (filtered) as csv/xlsx, scoped to a company."""
        if self.get_run(run_id, company_id) is None:
            return None
        rows = self._recon_repo.iter_errors_report(run_id, filters or {})
        payload, mimetype, extension = report_export.build_file("errors", rows, fmt)
        return f"reconciliation_errors_{run_id}.{extension}", mimetype, payload

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _envelope(items: list, total: int, page: int, page_size: int) -> dict:
        total_pages = math.ceil(total / page_size) if total > 0 else 0
        return {
            "items": items,
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _counts(outcome: ReconcileOutcome) -> dict:
        counts = {status: 0 for status in c.RESULT_STATUSES}
        for result in outcome.results:
            if result.match_status in counts:
                counts[result.match_status] += 1
        return counts

    def _mark_failed(self, run_id: int) -> None:
        try:
            self._recon_repo.fail_run(run_id)
        except Exception:
            logger.exception("Failed to mark run %s as failed", run_id)

    # ------------------------------------------------------------------
    # Email notifications (best-effort, never affect the run outcome)
    # ------------------------------------------------------------------

    def _fail_run(self, run_id: int) -> None:
        self._mark_failed(run_id)

    def _notify_discrepancies(self, run: ReconciliationRun) -> None:
        """Best-effort per-taxpayer summary email for a completed run.

        Called after the run's transaction is committed. Failures are logged
        and never affect the run outcome.
        """
        if self._email_service is None:
            return
        try:
            rows = self._recon_repo.list_affected_results_with_party(run.id)
            self._email_service.notify_run_summary(run, rows)
        except Exception:
            logger.exception(
                "Email notification failed for reconciliation run %s", run.id
            )