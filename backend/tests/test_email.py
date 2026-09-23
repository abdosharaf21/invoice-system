"""Tests for the outbound (send-only) email module.

Covers configuration validation, the SMTP provider (against patched
smtplib), templates, the taxpayer-recipient planning/sending service, the
email_deliveries tracking path, the admin-gated API routes and the
reconciliation integration hooks. Notifications target the run's
taxpayers/counterparties — never internal users.
"""

import smtplib
from datetime import date, datetime
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

import pytest

from backend.modules.email.model import (
    DELIVERY_FAILED,
    DELIVERY_INVALID,
    DELIVERY_NO_EMAIL,
    DELIVERY_SENT,
    DELIVERY_SKIPPED,
    DELIVERED_STATUSES,
    DELIVERY_STATUSES,
    NON_SEND_STATUSES,
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
from backend.modules.email import templates as email_templates
from backend.modules.email.validator import (
    is_valid_email,
    normalize_recipients,
    validate_email,
)
from backend.modules.email.service import EMAIL_WORKFLOWS, EmailService
from backend.modules.invoices.model import Invoice
from backend.modules.reconciliation import contract as c
from backend.modules.reconciliation.model import ReconciliationRun
from backend.modules.reconciliation.service import ReconciliationService
from backend.modules.tax_authority.model import TaxInvoice


def _email_config(**overrides):
    base = {
        "EMAIL_ENABLED": True,
        "EMAIL_PROVIDER": "smtp",
        "EMAIL_HOST": "smtp.example.com",
        "EMAIL_PORT": 587,
        "EMAIL_USERNAME": "",
        "EMAIL_PASSWORD": "",
        "EMAIL_FROM": "noreply@example.com",
        "EMAIL_USE_TLS": True,
        "EMAIL_USE_SSL": False,
    }
    base.update(overrides)
    return EmailConfig.from_mapping(base)


class FakeProvider:
    """Records outbound messages without touching the network."""

    def __init__(self, raise_on_send=None):
        self.sent = []
        self.raise_on_send = raise_on_send

    def send(self, to, subject, text_body, html_body=None, request_id=""):
        if self.raise_on_send is not None:
            raise self.raise_on_send
        self.sent.append({
            "to": to,
            "subject": subject,
            "text": text_body,
            "html": html_body,
            "request_id": request_id,
        })


class _FakeCompanyRepo:
    def __init__(self, companies):
        self._companies = {co.id: co for co in companies}

    def get_by_id(self, company_id):
        return self._companies.get(company_id)


class _FakeDeliveryRepo:
    """In-memory stand-in for EmailDeliveryRepository."""

    def __init__(self):
        self.rows = []
        self._next_id = 1

    def create(self, delivery: EmailDelivery) -> EmailDelivery:
        delivery.id = self._next_id
        self._next_id += 1
        self.rows.append(delivery)
        return delivery

    def get_by_id(self, delivery_id):
        for row in self.rows:
            if row.id == delivery_id:
                return row
        return None

    def list_by_run(self, run_id):
        return [row for row in self.rows if row.run_id == run_id]

    def mark_sent(self, delivery_id, request_id, subject):
        row = self.get_by_id(delivery_id)
        if row:
            row.status = DELIVERY_SENT
            row.request_id = request_id
            row.subject = subject
        return row is not None

    def mark_failed(self, delivery_id, reason):
        row = self.get_by_id(delivery_id)
        if row:
            row.status = DELIVERY_FAILED
            row.failure_reason = reason
        return row is not None


class _AffectedRowsRepo:
    def __init__(self, runs, affected_rows=None):
        self._runs = runs
        self._affected_rows = affected_rows or {}

    def get_run_by_id(self, run_id):
        return self._runs.get(run_id)

    def list_affected_results_with_party(self, run_id):
        return self._affected_rows.get(run_id, [])


def _affected_row(**overrides):
    row = {
        "result_id": 1,
        "run_id": 7,
        "match_status": "mismatched",
        "discrepancy_amount": "5.00",
        "notes": None,
        "invoice_id": 1,
        "invoice_number": "INV-1",
        "invoice_date": date(2024, 3, 1),
        "total_amount": "114.00",
        "counterparty_name": "Acme Co",
        "counterparty_tax_id": "TA-1",
        "counterparty_email": "acme@example.com",
    }
    row.update(overrides)
    return row


def _run(run_id=7, company_id=5, period="2024-03"):
    return ReconciliationRun(
        id=run_id, company_id=company_id, period=period, status=c.RUN_COMPLETED
    )


def _service(config, **kwargs):
    return EmailService(config, **kwargs)


# ---------------------------------------------------------------------------
# EmailConfig validation
# ---------------------------------------------------------------------------


def test_config_valid_when_email_disabled_even_without_settings():
    cfg = EmailConfig.from_mapping({"EMAIL_ENABLED": False})
    cfg.validate()
    assert cfg.host == ""


def test_config_requires_host_and_from_when_enabled():
    cfg = _email_config(EMAIL_HOST="", EMAIL_FROM="")
    with pytest.raises(EmailConfigError):
        cfg.validate()


def test_config_rejects_tls_and_ssl_together():
    cfg = _email_config(EMAIL_USE_TLS=True, EMAIL_USE_SSL=True)
    with pytest.raises(EmailConfigError):
        cfg.validate()


def test_config_rejects_partial_credentials():
    cfg = _email_config(EMAIL_USERNAME="user", EMAIL_PASSWORD="")
    with pytest.raises(EmailConfigError):
        cfg.validate()


def test_config_rejects_unknown_provider():
    cfg = _email_config(EMAIL_PROVIDER="sendmail")
    with pytest.raises(EmailConfigError):
        cfg.validate()


def test_config_accepts_gmail_provider():
    cfg = _email_config(
        EMAIL_PROVIDER="gmail", EMAIL_FROM="a@b.com", EMAIL_HOST="smtp.gmail.com"
    )
    cfg.validate()
    assert cfg.provider == "gmail"


def test_config_defaults_to_standard_smtp_port():
    cfg = _email_config(EMAIL_PORT="")
    assert cfg.port == 587


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


def test_provider_sends_with_tls_and_login(monkeypatch):
    server = _FakeSMTP()
    monkeypatch.setattr(smtplib, "SMTP", lambda *a, **k: server(*a, **k))

    provider = SMTPEmailProvider(_email_config(EMAIL_USERNAME="u", EMAIL_PASSWORD="p"))
    provider.send(
        to=["acme@example.com"],
        subject="Hi",
        text_body="Body",
        html_body="<p>Body</p>",
        request_id="req-1",
    )

    assert server.called_with == ("smtp.example.com", 587)
    assert server.tls_started is True
    assert server.logged_in == ("u", "p")
    assert server.last_to == "acme@example.com"
    assert server.last_subject == "Hi"
    assert "X-Request-Id" in server.last_headers
    assert server.last_headers["X-Request-Id"] == "req-1"


def test_provider_uses_implicit_ssl_when_configured(monkeypatch):
    ssl_server = _FakeSMTP()
    monkeypatch.setattr(smtplib, "SMTP_SSL", lambda *a, **k: ssl_server(*a, **k))

    provider = SMTPEmailProvider(_email_config(EMAIL_USE_TLS=False, EMAIL_USE_SSL=True))
    provider.send(["a@example.com"], "S", "T")

    assert ssl_server.called_with == ("smtp.example.com", 587)
    assert ssl_server.tls_started is False
    assert ssl_server.logged_in is None


def test_provider_skips_login_without_credentials(monkeypatch):
    server = _FakeSMTP()
    monkeypatch.setattr(smtplib, "SMTP", lambda *a, **k: server(*a, **k))

    provider = SMTPEmailProvider(_email_config())
    provider.send(["a@example.com"], "S", "T")

    assert server.logged_in is None


def test_provider_maps_auth_failure(monkeypatch):
    server = _FakeSMTP()
    server.login_error = smtplib.SMTPAuthenticationError(535, b"auth failed")
    monkeypatch.setattr(smtplib, "SMTP", lambda *a, **k: server)

    provider = SMTPEmailProvider(_email_config(EMAIL_USERNAME="u", EMAIL_PASSWORD="bad"))
    with pytest.raises(EmailAuthError):
        provider.send(["a@example.com"], "S", "T")
    assert "PAYLOAD" not in str(EmailAuthError("x"))


def test_provider_maps_connection_failure(monkeypatch):
    def _refuse(*a, **k):
        raise OSError("connection refused")

    monkeypatch.setattr(smtplib, "SMTP", _refuse)
    provider = SMTPEmailProvider(_email_config())
    with pytest.raises(EmailTransportError):
        provider.send(["a@example.com"], "S", "T")


def test_provider_maps_recipient_refusal(monkeypatch):
    server = _FakeSMTP()
    server.send_error = smtplib.SMTPRecipientsRefused({"a@example.com": (550, b"no")})
    monkeypatch.setattr(smtplib, "SMTP", lambda *a, **k: server(*a, **k))

    provider = SMTPEmailProvider(_email_config())
    with pytest.raises(EmailTransportError):
        provider.send(["a@example.com"], "S", "T")


class _FakeSMTP:
    def __init__(self):
        self.called_with = None
        self.tls_started = False
        self.logged_in = None
        self.last_message = None
        self.last_headers = {}
        self.login_error = None
        self.send_error = None

    def __call__(self, *args, **kwargs):
        self.called_with = args
        return self

    def starttls(self, context=None):
        self.tls_started = True
        return (220, b"go")

    def login(self, username, password):
        if self.login_error:
            raise self.login_error
        self.logged_in = (username, password)
        return (235, b"ok")

    def send_message(self, msg):
        if self.send_error:
            raise self.send_error
        self.last_message = msg
        self.last_headers = dict(msg)
        self.last_to = msg["To"]
        self.last_subject = msg["Subject"]

    def quit(self):
        return (221, b"bye")

    def close(self):
        return None


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


def test_is_valid_email():
    assert is_valid_email("acme@example.com")
    assert is_valid_email("a.b+c@sub.example.co")
    assert not is_valid_email("")
    assert not is_valid_email("not-an-email")
    assert not is_valid_email("a@b")


def test_validate_email_raises_on_invalid():
    with pytest.raises(EmailValidationError):
        validate_email("oops")
    assert validate_email("  Acme@Example.COM ") == "acme@example.com"


def test_normalize_recipients_dedupes_and_drops_invalid():
    result = normalize_recipients(["A@Example.com", "a@example.com", "bad", "b@example.com"])
    assert result == ("a@example.com", "b@example.com")


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


def _discrepancy_context():
    return {
        "company_id": 5,
        "company_name": "Acme <Co>",
        "period": "2024-03",
        "taxpayer": {"name": "Blue Corp & Sons", "tax_id": "T-123"},
        "invoices": [
            {
                "invoice_number": "INV-1",
                "invoice_date": date(2024, 3, 1),
                "match_status": "mismatched",
                "total_amount": "114.00",
                "discrepancy_amount": "5.00",
            },
            {
                "invoice_number": "INV-2",
                "invoice_date": date(2024, 3, 2),
                "match_status": "missing_in_tax_authority",
                "total_amount": "50.00",
                "discrepancy_amount": "0.00",
            },
        ],
    }


def test_discrepancy_template_contains_rows_and_escapes_html():
    subject, text, html = email_templates.render_reconciliation_discrepancy(
        _discrepancy_context()
    )
    assert "2024-03" in subject
    assert "INV-1" in text
    assert "INV-2" in text
    assert "Blue Corp & Sons" in text
    assert "&lt;Co&gt;" in html
    assert "<Co>" not in html
    assert "&amp;" in html
    assert "T-123" in text
    assert "114.00" in text


def test_discrepancy_template_does_not_leak_internal_details():
    context = dict(_discrepancy_context())
    context["invoices"] = [dict(_discrepancy_context()["invoices"][0])]
    subject, text, html = email_templates.render_reconciliation_discrepancy(context)

    lowered = (subject + text + html).lower()
    assert "request" not in lowered
    assert "secret" not in lowered
    assert "password" not in lowered
    assert "bearer" not in lowered


def test_discrepancy_template_escapes_invoice_fields():
    context = dict(_discrepancy_context())
    context["invoices"] = [{
        "invoice_number": "<img src=x onerror=alert(1)>",
        "invoice_date": "2024-03-01",
        "match_status": "mismatched",
        "total_amount": "1.00",
        "discrepancy_amount": "2.00",
    }]
    _, _, html = email_templates.render_reconciliation_discrepancy(context)
    assert "<img" not in html
    assert "&lt;img" in html
    assert "alert(1)" in html  # inert text only; the tag is escaped away


def test_discrepancy_template_handles_empty_invoice_list():
    context = {
        "company_id": 5,
        "company_name": "Acme",
        "period": "2024-03",
        "taxpayer": {"name": "Blue", "tax_id": None},
        "invoices": [],
    }
    subject, text, html = email_templates.render_reconciliation_discrepancy(context)
    assert "Acme" in subject


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


def test_plan_recipients_groups_by_email_and_splits_missing_invalid():
    service = _service({"EMAIL_ENABLED": True, "EMAIL_HOST": "h", "EMAIL_FROM": "a@b.com"})
    rows = [
        _affected_row(counterparty_name="Alpha", counterparty_tax_id="TA1",
                      counterparty_email="a@example.com", invoice_number="I1"),
        _affected_row(counterparty_name="Alpha", counterparty_tax_id="TA1",
                      counterparty_email="A@Example.com", invoice_number="I2",
                      invoice_date=date(2024, 3, 2)),
        _affected_row(counterparty_name="Beta", counterparty_tax_id="TB1",
                      counterparty_email="", invoice_number="I3"),
        _affected_row(counterparty_name="Gamma", counterparty_tax_id="TG1",
                      counterparty_email="not-an-email", invoice_number="I4"),
    ]
    plans = EmailService._plan_recipients(rows)

    grouped = {(p["recipient_email"], p["has_email"], p["email_valid"]): len(p["invoices"])
               for p in plans}
    assert grouped[("a@example.com", True, True)] == 2
    assert grouped[(None, False, False)] == 1
    assert grouped[("not-an-email", True, False)] == 1
    assert len(plans) == 3


def test_notify_run_summary_sends_one_grouped_email_per_taxpayer(monkeypatch):
    provider = FakeProvider()
    delivery_repo = _FakeDeliveryRepo()
    company_repo = _FakeCompanyRepo([type("C", (), {"id": 5, "name": "Acme <Co>"})()])
    run = _run()
    service = _service(
        {"EMAIL_ENABLED": True, "EMAIL_HOST": "h", "EMAIL_FROM": "noreply@example.com"},
        company_repo=company_repo,
        delivery_repo=delivery_repo,
        provider=provider,
    )
    monkeypatch.setattr(
        "backend.modules.email.service.get_request_id", lambda: "req-123"
    )

    rows = [
        _affected_row(run_id=7, counterparty_email="acme@example.com", invoice_number="INV-1"),
        _affected_row(run_id=7, counterparty_email="acme@example.com", invoice_number="INV-2"),
    ]
    outcome = service.notify_run_summary(run, rows)

    assert outcome == {"planned": 1, "sent": 1, "failed": 0, "skipped": 0,
                       "no_email": 0, "invalid": 0}
    assert len(provider.sent) == 1
    sent = provider.sent[0]
    assert sent["to"] == ["acme@example.com"]
    assert sent["request_id"] == "req-123"
    assert "Acme <Co>" in sent["subject"]
    assert "INV-2" in sent["text"]

    assert len(delivery_repo.rows) == 1
    delivery = delivery_repo.rows[0]
    assert delivery.run_id == 7
    assert delivery.company_id == 5
    assert delivery.recipient_email == "acme@example.com"
    assert delivery.taxpayer_name == "Acme Co"
    assert delivery.invoice_count == 2
    assert delivery.status == DELIVERY_SENT
    assert delivery.request_id == "req-123"


def test_notify_run_summary_records_non_send_outcomes():
    delivery_repo = _FakeDeliveryRepo()
    service = _service(
        {"EMAIL_ENABLED": False, "EMAIL_HOST": "h", "EMAIL_FROM": "a@b.com"},
        delivery_repo=delivery_repo,
        provider=FakeProvider(),
    )
    rows = [
        _affected_row(counterparty_email="ok@example.com"),
        _affected_row(counterparty_email="", invoice_number="I-noemail"),
        _affected_row(counterparty_email="bad-address", invoice_number="I-invalid"),
    ]

    outcome = service.notify_run_summary(_run(), rows)

    assert outcome == {"planned": 3, "sent": 0, "failed": 0, "skipped": 1,
                       "no_email": 1, "invalid": 1}
    by_status = {row.status for row in delivery_repo.rows}
    assert by_status == {DELIVERY_SKIPPED, DELIVERY_NO_EMAIL, DELIVERY_INVALID}
    sent_el = [r for r in delivery_repo.rows if r.status == DELIVERY_SKIPPED][0]
    assert sent_el.recipient_email == "ok@example.com"
    assert sent_el.failure_reason


def test_notify_run_summary_marks_failed_without_raising():
    provider = FakeProvider(raise_on_send=EmailTransportError("smtp down"))
    delivery_repo = _FakeDeliveryRepo()
    service = _service(
        {"EMAIL_ENABLED": True, "EMAIL_HOST": "h", "EMAIL_FROM": "a@b.com"},
        delivery_repo=delivery_repo,
        provider=provider,
    )

    outcome = service.notify_run_summary(_run(), [_affected_row()])

    assert outcome["planned"] == 1
    assert outcome["failed"] == 1
    assert provider.sent == []
    delivery = delivery_repo.rows[0]
    assert delivery.status == DELIVERY_FAILED
    assert delivery.failure_reason == "SMTP delivery failed"


def test_notify_run_summary_empty_rows_no_ops():
    service = _service(
        {"EMAIL_ENABLED": True, "EMAIL_HOST": "h", "EMAIL_FROM": "a@b.com"},
        delivery_repo=_FakeDeliveryRepo(),
        provider=FakeProvider(),
    )
    outcome = service.notify_run_summary(_run(), [])
    assert outcome["planned"] == 0


def test_delivery_rows_record_invalid_email_reason():
    delivery_repo = _FakeDeliveryRepo()
    service = _service(
        {"EMAIL_ENABLED": True, "EMAIL_HOST": "h", "EMAIL_FROM": "a@b.com"},
        delivery_repo=delivery_repo,
        provider=FakeProvider(),
    )
    service.notify_run_summary(_run(), [_affected_row(counterparty_email="broken")])
    delivery = delivery_repo.rows[0]
    assert delivery.status == DELIVERY_INVALID
    assert "invalid" in (delivery.failure_reason or "").lower()


def test_list_deliveries_scopes_to_company():
    run = _run()
    delivery_repo = _FakeDeliveryRepo()
    service = _service(
        {"EMAIL_ENABLED": True, "EMAIL_HOST": "h", "EMAIL_FROM": "a@b.com"},
        delivery_repo=delivery_repo,
        provider=FakeProvider(),
    )
    mine = EmailDelivery(company_id=5, run_id=7, recipient_email="a@example.com",
                         status=DELIVERY_SENT)
    other = EmailDelivery(company_id=9, run_id=7, recipient_email="b@example.com",
                          status=DELIVERY_SENT)
    delivery_repo.rows = [mine, other]

    rows = service.list_deliveries(run.id, 5)

    assert [r["id"] for r in rows] == [mine.id]


def test_resend_delivery_sends_and_marks_sent(monkeypatch):
    provider = FakeProvider()
    delivery_repo = _FakeDeliveryRepo()
    company_repo = _FakeCompanyRepo([type("C", (), {"id": 5, "name": "Acme"})()])
    run = _run()
    delivery = EmailDelivery(
        id=1, company_id=5, run_id=7, recipient_email="acme@example.com",
        taxpayer_name="Acme Co", status=DELIVERY_FAILED,
    )
    delivery_repo.rows = [delivery]
    recon_repo = _AffectedRowsRepo({7: run}, {7: [_affected_row()]})
    service = _service(
        {"EMAIL_ENABLED": True, "EMAIL_HOST": "h", "EMAIL_FROM": "a@b.com"},
        company_repo=company_repo,
        delivery_repo=delivery_repo,
        recon_repo=recon_repo,
        provider=provider,
    )
    monkeypatch.setattr(
        "backend.modules.email.service.get_request_id", lambda: "req-9"
    )

    refreshed = service.resend_delivery(run.id, delivery.id, 5)

    assert provider.sent[0]["to"] == ["acme@example.com"]
    assert "Acme" in provider.sent[0]["subject"]
    assert refreshed["status"] == DELIVERY_SENT
    assert refreshed["request_id"] == "req-9"


def test_resend_delivery_requires_enabled():
    service = _service({"EMAIL_ENABLED": False})
    with pytest.raises(EmailDisabledError):
        service.resend_delivery(7, 1, 5)


def test_resend_delivery_rejects_invalid_recipient():
    delivery = EmailDelivery(id=1, company_id=5, run_id=7, recipient_email="broken",
                             status=DELIVERY_FAILED)
    delivery_repo = _FakeDeliveryRepo()
    delivery_repo.rows = [delivery]
    provider = FakeProvider()
    service = _service(
        {"EMAIL_ENABLED": True, "EMAIL_HOST": "h", "EMAIL_FROM": "a@b.com"},
        delivery_repo=delivery_repo,
        provider=provider,
    )
    with pytest.raises(EmailValidationError):
        service.resend_delivery(7, 1, 5)
    assert provider.sent == []


def test_resend_delivery_cross_company_or_missing_returns_none():
    provider = FakeProvider()
    service = _service(
        {"EMAIL_ENABLED": True, "EMAIL_HOST": "h", "EMAIL_FROM": "a@b.com"},
        delivery_repo=_FakeDeliveryRepo(),
        recon_repo=_AffectedRowsRepo({7: _run()}, {}),
        provider=provider,
    )
    assert service.resend_delivery(7, 404, 5) is None
    assert provider.sent == []


def test_resend_propagates_transport_failure_and_marks_failed(monkeypatch):
    provider = FakeProvider(raise_on_send=EmailTransportError("smtp down"))
    delivery_repo = _FakeDeliveryRepo()
    delivery = EmailDelivery(id=1, company_id=5, run_id=7,
                             recipient_email="acme@example.com", status=DELIVERY_SENT)
    delivery_repo.rows = [delivery]
    service = _service(
        {"EMAIL_ENABLED": True, "EMAIL_HOST": "h", "EMAIL_FROM": "a@b.com"},
        delivery_repo=delivery_repo,
        recon_repo=_AffectedRowsRepo({7: _run()}, {7: [_affected_row()]}),
        provider=provider,
    )
    with pytest.raises(EmailTransportError):
        service.resend_delivery(7, 1, 5)
    assert delivery_repo.rows[0].status == DELIVERY_FAILED


def test_send_test_requires_enabled_and_valid_address():
    service = _service({"EMAIL_ENABLED": False}, provider=FakeProvider())
    with pytest.raises(EmailDisabledError):
        service.send_test("a@example.com")

    service = _service(
        {"EMAIL_ENABLED": True, "EMAIL_HOST": "h", "EMAIL_FROM": "a@b.com"},
        provider=FakeProvider(),
    )
    with pytest.raises(EmailValidationError):
        service.send_test("broken")


def test_send_test_propagates_transport_failure():
    provider = FakeProvider(raise_on_send=EmailTransportError("down"))
    service = _service(
        {"EMAIL_ENABLED": True, "EMAIL_HOST": "h", "EMAIL_FROM": "a@b.com"},
        provider=provider,
    )
    with pytest.raises(EmailTransportError):
        service.send_test("a@example.com")


def test_get_status_hides_credentials_and_lists_workflows():
    service = _service({
        "EMAIL_ENABLED": True,
        "EMAIL_HOST": "h",
        "EMAIL_PORT": 25,
        "EMAIL_USERNAME": "secret-user",
        "EMAIL_PASSWORD": "secret-password",
        "EMAIL_FROM": "a@b.com",
    }, provider=FakeProvider())

    status = service.get_status()

    assert status["enabled"] is True
    assert status["host"] == "h"
    assert "password" not in jsonify_lower(status)
    assert "secret-password" not in jsonify_lower(status)
    assert "secret-user" not in jsonify_lower(status)
    assert any(w["name"] == "reconciliation.discrepancies" for w in status["workflows"])
    assert EMAIL_WORKFLOWS["reconciliation.discrepancies"]["description"]


def jsonify_lower(data):
    import json
    return json.dumps(data).lower()


# ---------------------------------------------------------------------------
# EmailDelivery model
# ---------------------------------------------------------------------------


def test_delivery_model_roundtrip_and_status_constants():
    delivery = EmailDelivery(
        id=3,
        company_id=5,
        run_id=7,
        recipient_email="acme@example.com",
        taxpayer_name="Acme Co",
        taxpayer_tax_id="TA-1",
        invoice_count=2,
        subject="Notice",
        status=DELIVERY_SENT,
        failure_reason=None,
        request_id="req-1",
    )
    data = delivery.to_dict()
    assert data["id"] == 3
    assert data["status"] == DELIVERY_SENT
    restored = EmailDelivery.from_dict(data)
    assert restored.recipient_email == "acme@example.com"
    assert restored.status == DELIVERY_SENT
    assert restored.subject == "Notice"
    assert DELIVERY_SENT in DELIVERED_STATUSES
    assert DELIVERY_SENT in DELIVERY_STATUSES
    assert DELIVERY_INVALID in NON_SEND_STATUSES
    assert DELIVERY_SKIPPED in NON_SEND_STATUSES
    assert DELIVERY_NO_EMAIL in NON_SEND_STATUSES
    assert DELIVERY_FAILED not in NON_SEND_STATUSES


# ---------------------------------------------------------------------------
# API routes (RBAC)
# ---------------------------------------------------------------------------


def test_email_status_admin_only(client, admin_headers, viewer_headers, employee_headers):
    resp = client.get("/api/email/status", headers=viewer_headers)
    assert resp.status_code == 403
    resp = client.get("/api/email/status", headers=employee_headers)
    assert resp.status_code == 403
    resp = client.get("/api/email/status", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert body["data"]["enabled"] is False


def test_email_test_admin_only_and_disabled(client, admin_headers, viewer_headers):
    resp = client.post(
        "/api/email/test", headers=viewer_headers, json={"to": "a@example.com"}
    )
    assert resp.status_code == 403

    resp = client.post(
        "/api/email/test", headers=admin_headers, json={"to": "a@example.com"}
    )
    assert resp.status_code == 400


def test_email_test_missing_recipient(client, admin_headers):
    resp = client.post("/api/email/test", headers=admin_headers, json={})
    assert resp.status_code == 400


def test_email_test_success_when_enabled(client, admin_headers, monkeypatch):
    provider = FakeProvider()
    service = EmailService(
        {"EMAIL_ENABLED": True, "EMAIL_HOST": "h", "EMAIL_PORT": 25, "EMAIL_FROM": "a@b.com"},
        provider=provider,
    )
    import backend.modules.email.routes as email_routes
    monkeypatch.setattr(email_routes, "_email_service", service)

    resp = client.post(
        "/api/email/test", headers=admin_headers, json={"to": "ok@example.com"}
    )
    assert resp.status_code == 200
    assert provider.sent[0]["to"] == ["ok@example.com"]


def test_email_test_transport_error_maps_to_502(client, admin_headers, monkeypatch):
    service = EmailService(
        {"EMAIL_ENABLED": True, "EMAIL_HOST": "h", "EMAIL_PORT": 25, "EMAIL_FROM": "a@b.com"},
        provider=FakeProvider(raise_on_send=EmailTransportError("down")),
    )
    import backend.modules.email.routes as email_routes
    monkeypatch.setattr(email_routes, "_email_service", service)

    resp = client.post(
        "/api/email/test", headers=admin_headers, json={"to": "ok@example.com"}
    )
    assert resp.status_code == 502


# ---------------------------------------------------------------------------
# Reconciliation integration
# ---------------------------------------------------------------------------


class _RecorderEmailService:
    def __init__(self, raise_on_run=None):
        self.calls = []
        self.raise_on_run = raise_on_run

    def notify_run_summary(self, run, rows):
        if self.raise_on_run == run.id:
            raise RuntimeError("email down")
        self.calls.append((run.id, len(rows)))


class _FakeReconRepo:
    def __init__(self):
        self.finished = {}
        self.failed = 0
        self.affected = {}

    def set_affected(self, run_id, rows):
        self.affected[run_id] = rows
        return self

    def create_run(self, run):
        run.id = 100
        return run

    def create_run_exclusive(self, company_id, period):
        run = ReconciliationRun(
            company_id=company_id, period=period, status=c.RUN_PENDING
        )
        run.id = 100
        return run, True

    def find_active_run(self, company_id, period):
        return None

    def start_run(self, run_id):
        return True

    def finish_run_transaction(self, run_id, results, errors, **counts):
        self.finished[run_id] = counts
        return True

    def fail_run(self, run_id):
        self.failed += 1
        return True

    def get_run_by_id(self, run_id):
        return ReconciliationRun(
            id=run_id, company_id=1, period="2024-03", status=c.RUN_COMPLETED
        )

    def list_affected_results_with_party(self, run_id):
        return self.affected.get(run_id, [])


class _FakeInvoiceRepo:
    def __init__(self, invoices):
        self.invoices = invoices
        self.raise_on_list = False

    def list_by_company_and_period(self, company_id, period):
        if self.raise_on_list:
            raise RuntimeError("boom")
        return self.invoices


class _FakeTaxRepo:
    def __init__(self, tax_invoices):
        self.tax_invoices = tax_invoices

    def list_by_company_and_period(self, company_id, period):
        return self.tax_invoices


def _uuid(seed):
    return str(uuid5(NAMESPACE_URL, f"email-{seed}"))


def _invoice(uuid_value, subtotal="100.00"):
    return Invoice(
        id=1, uuid=uuid_value, company_id=1, invoice_number="INV",
        invoice_date=date(2024, 3, 1), currency="EGP",
        counterparty_name="Acme", subtotal_amount=Decimal(subtotal),
        discount_amount=Decimal("0.00"), vat_amount=Decimal("14.00"),
        total_amount=Decimal("114.00"),
    )


def _tax(uuid_value, id=10):
    return TaxInvoice(
        id=id, uuid=uuid_value, company_id=1,
        issue_datetime=datetime(2024, 3, 1), currency="EGP",
        seller_name="Mega", total_sales=Decimal("100.00"),
        total_discount=Decimal("0.00"), net_amount=Decimal("100.00"),
        vat_amount=Decimal("14.00"), total_amount=Decimal("114.00"),
        buyer_name="Acme", buyer_tax_id=None, seller_tax_id=None,
    )


def _recon_service(recon, invoice_repo, tax_repo, email_service):
    return ReconciliationService(
        recon, invoice_repo, tax_repo, user_repo=None, email_service=email_service
    )


def test_reconciliation_completion_triggers_summary_email_after_persist():
    recon = _FakeReconRepo().set_affected(100, [
        _affected_row(run_id=100, counterparty_email="acme@example.com")
    ])
    email = _RecorderEmailService()
    service = _recon_service(
        recon,
        _FakeInvoiceRepo([_invoice(_uuid("m"))]),
        _FakeTaxRepo([_tax(_uuid("m"))]),
        email,
    )

    run, counts, _ = service.start_run(1, "2024-03")

    assert run.status == c.RUN_COMPLETED
    assert email.calls == [(100, 1)]
    assert counts[c.MATCHED] == 1


def test_reconciliation_failure_marks_failed_without_email():
    recon = _FakeReconRepo()
    email = _RecorderEmailService()
    invoices = _FakeInvoiceRepo([_invoice(_uuid("x"))])
    invoices.raise_on_list = True
    service = _recon_service(recon, invoices, _FakeTaxRepo([]), email)

    with pytest.raises(RuntimeError):
        service.start_run(1, "2024-03")

    assert recon.failed == 1
    assert email.calls == []


def test_email_failure_does_not_fail_completed_run():
    recon = _FakeReconRepo().set_affected(100, [
        _affected_row(run_id=100, counterparty_email="acme@example.com")
    ])
    email = _RecorderEmailService(raise_on_run=100)
    service = _recon_service(
        recon,
        _FakeInvoiceRepo([_invoice(_uuid("m"))]),
        _FakeTaxRepo([_tax(_uuid("m"))]),
        email,
    )

    run, counts, _ = service.start_run(1, "2024-03")

    assert run.status == c.RUN_COMPLETED
    assert counts[c.MATCHED] == 1


def test_no_email_service_does_not_crash():
    service = _recon_service(
        _FakeReconRepo().set_affected(100, []),
        _FakeInvoiceRepo([_invoice(_uuid("m"))]),
        _FakeTaxRepo([_tax(_uuid("m"))]),
        None,
    )

    run, counts, _ = service.start_run(1, "2024-03")

    assert run.status == c.RUN_COMPLETED


# ---------------------------------------------------------------------------
# Reconciliation delivery API routes
# ---------------------------------------------------------------------------


def test_list_deliveries_route_requires_reconcile_role(
    client, admin_headers, employee_headers, mock_repos
):
    resp = client.get(
        "/api/reconciliation/runs/5/email-deliveries", headers=employee_headers
    )
    assert resp.status_code == 403

    mock_repos.reconciliation_service.list_email_deliveries.return_value = [
        {"id": 1, "status": "sent"}
    ]
    resp = client.get(
        "/api/reconciliation/runs/5/email-deliveries", headers=admin_headers
    )
    assert resp.status_code == 200
    assert resp.get_json()["data"]["count"] == 1


def test_resend_delivery_route_not_found(client, admin_headers, mock_repos):
    mock_repos.reconciliation_service.resend_email_delivery.return_value = None
    resp = client.post(
        "/api/reconciliation/runs/5/email-deliveries/9/resend",
        headers=admin_headers,
    )
    assert resp.status_code == 404


def test_resend_delivery_route_transport_error(client, admin_headers, mock_repos):
    mock_repos.reconciliation_service.resend_email_delivery.side_effect = (
        EmailTransportError("down")
    )
    resp = client.post(
        "/api/reconciliation/runs/5/email-deliveries/9/resend",
        headers=admin_headers,
    )
    assert resp.status_code == 502