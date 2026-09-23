"""Focused Phase 10 tests: audit & compliance traceability.

Covers the confirmed transparency gaps (user management, company/app
settings, email operations) and the cross-cutting Phase 10 properties:
whitelisted redaction, tenant isolation, date-range filtering, actor-type
classification, audit immutability, pagination/ordering, and the display of
before/after state. All repositories are mocked; no real database is used.
"""

from unittest.mock import MagicMock, patch

import pytest

from backend.modules.audit_trail.model import AuditLog
from backend.modules.audit_trail.service import (
    AuditTrailService,
    build_snapshot,
    get_audit_trail_service,
)
from backend.modules.companies.model import Company
from backend.modules.companies.service import CompanyService
from backend.modules.settings.model import ApplicationSetting
from backend.modules.settings.service import ApplicationSettingService
from backend.modules.users.model import User
from backend.modules.users.service import UserService
from backend.shared.security import hash_password


def _record_calls():
    """Return the (args, kwargs) list of repository.record invocations."""
    service = get_audit_trail_service()
    if service is None:
        return []
    return [(c.args, c.kwargs) for c in service._repository.record.call_args_list]


def _audit_record_kwargs():
    """Return the kwargs dicts of every recorded audit event."""
    return [kwargs for (_args, kwargs) in _record_calls()]


def _reset_repository():
    """Swap the configured audit repository for a fresh MagicMock."""
    service = get_audit_trail_service()
    if service is not None:
        service._repository = MagicMock()


def _viewer(**overrides) -> User:
    """Return a non-admin user for management flows (avoids the last-admin
    guard while still exercising the audited transitions)."""
    kwargs = dict(
        id=5,
        company_id=10,
        username="viewer1",
        email="viewer@test.com",
        password_hash=hash_password("secret-password-value"),
        first_name="View",
        last_name="Er",
        roles=["viewer"],
        is_active=True,
    )
    kwargs.update(overrides)
    return User(**kwargs)


class TestUserManagementAudit:
    """User management operations must each produce an audit event."""

    def _service(self, user_repo, company_repo=None):
        return UserService(
            user_repository=user_repo,
            company_repository=company_repo or MagicMock(),
        )

    def test_create_user_records_create(self, app):
        _reset_repository()
        created = _viewer(id=99)
        repo = MagicMock()
        repo.exists_by_username.return_value = False
        repo.exists_by_email.return_value = False
        repo.create.return_value = created
        svc = UserService(user_repository=repo, company_repository=MagicMock())

        svc.create_user({
            "company_id": 10,
            "username": "viewer1",
            "email": "viewer@test.com",
            "password": "newpass123",
            "first_name": "View",
            "last_name": "Er",
            "roles": ["viewer"],
            "status": "active",
        })

        event = _audit_record_kwargs()[-1]
        assert event["action"] == AuditLog.ACTION_CREATE
        assert event["resource_type"] == "user"
        assert event["resource_id"] == "99"
        assert event["company_id"] == 10
        assert event["after_state"]["email"] == "viewer@test.com"
        assert "password" not in str(event)

    def test_update_user_records_before_and_after(self, app):
        _reset_repository()
        repo = MagicMock()
        repo.get_by_id.return_value = _viewer(email="before@test.com", company_id=10)
        repo.exists_by_email.return_value = False
        after = _viewer(email="after@test.com", company_id=10)
        repo.update.return_value = after
        svc = UserService(user_repository=repo, company_repository=MagicMock())

        svc.update_user(5, {"email": "after@test.com"})

        event = _audit_record_kwargs()[-1]
        assert event["action"] == AuditLog.ACTION_UPDATE
        assert event["resource_type"] == "user"
        assert event["company_id"] == 10
        assert event["before_state"]["email"] == "before@test.com"
        assert event["after_state"]["email"] == "after@test.com"

    def test_deactivation_records_before_and_after(self, app):
        _reset_repository()
        repo = MagicMock()
        repo.get_by_id.return_value = _viewer(is_active=True)
        repo.update.return_value = _viewer(is_active=False)
        svc = UserService(user_repository=repo, company_repository=MagicMock())

        svc.deactivate_user(5)

        event = _audit_record_kwargs()[-1]
        assert event["action"] == AuditLog.ACTION_UPDATE
        assert event["metadata"]["event"] == "deactivate"
        assert event["before_state"]["is_active"] is True
        assert event["after_state"]["is_active"] is False

    def test_delete_user_records_before_state(self, app):
        _reset_repository()
        repo = MagicMock()
        repo.get_by_id.return_value = _viewer()
        repo.delete.return_value = True
        svc = UserService(user_repository=repo, company_repository=MagicMock())

        assert svc.delete_user(5) is True

        event = _audit_record_kwargs()[-1]
        assert event["action"] == AuditLog.ACTION_DELETE
        assert event["resource_type"] == "user"
        assert event["company_id"] == 10
        assert event["before_state"]["username"] == "viewer1"

    def test_logout_records_event(self, app):
        _reset_repository()
        repo = MagicMock()
        svc = UserService(user_repository=repo)

        svc.logout("jti-1")

        event = _audit_record_kwargs()[-1]
        assert event["action"] == AuditLog.ACTION_LOGOUT
        assert event["resource_type"] == "auth"


class TestCompanySettingsAudit:
    """Company settings updates are audited with a before/after snapshot."""

    def _company(self, name="ACME", **overrides):
        kwargs = dict(
            id=7,
            name=name,
            tax_registration_number="TR-123",
            email="acme@test.com",
            phone="+20 100",
            address="Cairo",
            is_active=True,
            default_currency="EGP",
            default_tax_rate=0.14,
            fiscal_year_start="01-01",
        )
        kwargs.update(overrides)
        return Company(**kwargs)

    def test_update_company_records_before_and_after(self, app):
        _reset_repository()
        repo = MagicMock()
        before = self._company(name="Old Co")
        after = self._company(name="New Co")
        repo.get_by_id.return_value = before
        repo.update.return_value = after
        svc = CompanyService(repo)

        svc.update_company(7, {"name": "New Co"})

        event = _audit_record_kwargs()[-1]
        assert event["action"] == AuditLog.ACTION_UPDATE
        assert event["resource_type"] == "company"
        assert event["resource_id"] == "7"
        assert event["company_id"] == 7
        assert event["before_state"]["name"] == "Old Co"
        assert event["after_state"]["name"] == "New Co"
        assert "tax_registration_number" in event["after_state"]


class TestApplicationSettingsAudit:
    """Application settings updates are audited with secret redaction."""

    def _service(self, repo):
        return ApplicationSettingService(repo)

    def test_update_settings_records_changes(self, app):
        _reset_repository()
        repo = MagicMock()
        repo.get_all_as_dict.side_effect = [
            {"application_name": "Old"},
            {"application_name": "New"},
        ]
        svc = self._service(repo)

        result = svc.update_settings({"application_name": "New"})

        assert result == {"application_name": "New"}
        event = _audit_record_kwargs()[-1]
        assert event["action"] == AuditLog.ACTION_UPDATE
        assert event["resource_type"] == "setting"
        assert event["before_state"]["application_name"] == "Old"
        assert event["after_state"]["application_name"] == "New"

    def test_sensitive_settings_are_redacted(self, app):
        _reset_repository()
        repo = MagicMock()
        repo.get_all_as_dict.side_effect = [
            {"smtp_password": "plain-secret", "application_name": "X"},
            {"smtp_password": "new-secret", "application_name": "X"},
        ]
        svc = self._service(repo)

        svc.update_settings({"smtp_password": "new-secret"})

        event = _audit_record_kwargs()[-1]
        assert event["after_state"]["smtp_password"] == "[redacted]"
        assert "plain-secret" not in str(event)
        assert "new-secret" not in str(event)


class TestSnapshotRedaction:
    """build_snapshot only mirrors whitelisted, non-sensitive fields."""

    def test_user_snapshot_drops_password_and_unlisted_fields(self):
        user = _viewer()
        snapshot = build_snapshot("user", user.to_dict())

        assert snapshot is not None
        assert "password_hash" not in snapshot
        assert "password" not in str(snapshot)
        assert "full_name" not in snapshot
        assert "language" not in snapshot
        assert "created_at" not in snapshot
        assert snapshot["email"] == "viewer@test.com"
        assert snapshot["company_id"] == 10
        assert snapshot["roles"] == ["viewer"]

    def test_unknown_resource_type_returns_none(self):
        assert build_snapshot("invoice", {"id": 1}) is None

    def test_empty_data_returns_none(self):
        assert build_snapshot("user", None) is None
        assert build_snapshot("user", {}) is None

    def test_company_snapshot_whitelist(self):
        company = Company(id=7, name="ACME", tax_registration_number="TR-1", logo_path="x")
        snapshot = build_snapshot("company", company.to_dict())

        assert snapshot is not None
        assert "logo_path" not in snapshot
        assert snapshot["name"] == "ACME"

    def test_sensitive_field_names_never_mirrored(self):
        snapshot = build_snapshot(
            "user", {"id": 1, "email": "a@b.c", "password_reset_token": "abc"}
        )
        assert "password_reset_token" not in snapshot


class TestTenantIsolation:
    """Audit reads are scoped to the authenticated user's company."""

    def test_service_forwards_company_scope(self):
        repo = MagicMock()
        repo.list_logs.return_value = ([{"id": 1}], 1)
        svc = AuditTrailService(repo)

        svc.list_logs(company_id=42)

        filters = repo.list_logs.call_args.args[0]
        assert filters["company_id"] == 42

    def test_route_scopes_to_jwt_company_and_ignores_client(self, app, client, mock_repos):
        mock_repos.audit_repo.list_logs.return_value = ([{"id": 1}], 1)
        with app.app_context():
            from flask_jwt_extended import create_access_token
            token = create_access_token(
                identity="9",
                additional_claims={
                    "email": "manager@test.com",
                    "role": "manager",
                    "company_id": 42,
                },
            )
        response = client.get(
            "/api/audit-trail/logs?company_id=999&company=evil",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        filters = mock_repos.audit_repo.list_logs.call_args.args[0]
        assert filters["company_id"] == 42
        assert "999" not in str(filters)

    def test_platform_admin_without_company_sees_system_only_scope(
        self, app, client, mock_repos
    ):
        mock_repos.audit_repo.list_logs.return_value = ([], 0)
        response = client.get(
            "/api/audit-trail/logs?company_id=999&company=evil",
            headers=_admin_headers(app),
        )
        # A platform-level token has no company claim, so the scope is
        # system-only; the client-supplied company params must be ignored.
        assert response.status_code == 200
        filters = mock_repos.audit_repo.list_logs.call_args.args[0]
        assert filters["company_id"] is None
        assert "999" not in str(filters)


def _jwtish(app):
    """Create a platform-level admin token with no company claim."""
    with app.app_context():
        from flask_jwt_extended import create_access_token
        return create_access_token(
            identity="1",
            additional_claims={"email": "admin@test.com", "role": "admin"},
        )


class TestDateRangeFiltering:
    """Audit list supports an optional inclusive date window."""

    def test_service_forwards_dates(self):
        repo = MagicMock()
        repo.list_logs.return_value = ([], 0)
        svc = AuditTrailService(repo)

        svc.list_logs(start_date="2026-09-01", end_date="2026-09-30")

        filters = repo.list_logs.call_args.args[0]
        assert filters["start_date"] == "2026-09-01"
        assert filters["end_date"] == "2026-09-30"

    def test_invalid_dates_rejected_before_repo(self):
        repo = MagicMock()
        svc = AuditTrailService(repo)

        with pytest.raises(ValueError):
            svc.list_logs(start_date="01/02/2026")
        repo.list_logs.assert_not_called()

    def test_route_accepts_dates_and_rejects_bad(self, app, client, mock_repos):
        mock_repos.audit_repo.list_logs.return_value = ([], 0)
        ok = client.get(
            "/api/audit-trail/logs?start_date=2026-09-01&end_date=2026-09-30",
            headers=_admin_headers(app),
        )
        assert ok.status_code == 200

        bad = client.get(
            "/api/audit-trail/logs?start_date=not-a-date",
            headers=_admin_headers(app),
        )
        assert bad.status_code == 400


def _admin_headers(app):
    """Authorization header for a platform-level admin token."""
    return {"Authorization": f"Bearer {_jwtish(app)}"}


class TestActorType:
    """Audit records classify the actor as 'user' or 'system'."""

    def test_default_actor_type_is_user(self):
        repo = MagicMock()
        repo.record.return_value = 1
        svc = AuditTrailService(repo)

        svc.record_from_context(
            action=AuditLog.ACTION_VIEW, resource_type="report"
        )

        assert repo.record.call_args.kwargs["actor_type"] == AuditLog.ACTOR_USER

    def test_system_actor_is_accepted(self):
        repo = MagicMock()
        repo.record.return_value = 1
        svc = AuditTrailService(repo)

        svc.record_from_context(
            action=AuditLog.ACTION_VIEW,
            resource_type="report",
            actor_type=AuditLog.ACTOR_SYSTEM,
        )

        assert repo.record.call_args.kwargs["actor_type"] == AuditLog.ACTOR_SYSTEM

    def test_invalid_actor_type_rejected(self):
        svc = AuditTrailService(MagicMock())
        with pytest.raises(ValueError):
            svc.record(
                actor_id=1, actor_email="a@b.c", role="admin",
                action=AuditLog.ACTION_OTHER, resource_type="auth",
                actor_type="robot",
            )


class TestAuditImmutability:
    """Audit logs are append-only: no update/delete surface exists."""

    def test_blueprint_has_no_mutation_routes(self, app):
        from backend.modules.audit_trail.routes import audit_trail_bp

        rules = [
            r for r in app.url_map.iter_rules()
            if r.endpoint.startswith("audit_trail.")
        ]
        assert rules, "audit_trail routes not registered"
        for rule in rules:
            assert not (rule.methods & {"POST", "PUT", "PATCH", "DELETE"}), (
                f"audit route {rule} must not mutate"
            )

    def test_repository_is_append_only(self):
        from backend.modules.audit_trail.repository import AuditTrailRepository

        public = [name for name in dir(AuditTrailRepository) if not name.startswith("_")]
        assert "delete" not in public
        assert "update" not in public
        assert {"record", "list_logs"}.issubset(set(public))


class TestPaginationAndOrdering:
    """Audit list returns a paginated envelope and passes sort through."""

    def test_sort_by_forwarded(self):
        repo = MagicMock()
        repo.list_logs.return_value = ([], 0)
        svc = AuditTrailService(repo)

        svc.list_logs(sort_by="created_at", page=2, page_size=10)

        filters = repo.list_logs.call_args.args[0]
        assert filters["sort_by"] == "created_at"
        assert filters["page"] == 2
        assert filters["page_size"] == 10

    def test_pagination_envelope(self):
        repo = MagicMock()
        repo.list_logs.return_value = ([{"id": 1}, {"id": 2}], 21)
        svc = AuditTrailService(repo)

        result = svc.list_logs(page=3, page_size=10)

        assert result["total"] == 21
        assert result["pages"] == 3
        assert result["page"] == 3


class TestEmailOperationAudit:
    """Email resend/test operations are traced with tenant attribution."""

    def _service(self, delivery_repo):
        from backend.modules.email.service import EmailService

        service = EmailService(
            config_mapping={
                "EMAIL_ENABLED": True,
                "EMAIL_PROVIDER": "smtp",
                "EMAIL_HOST": "smtp.test",
                "EMAIL_PORT": 587,
                "EMAIL_USERNAME": "u",
                "EMAIL_PASSWORD": "smtp-secret",
                "EMAIL_FROM": "no-reply@test.com",
                "EMAIL_USE_TLS": True,
                "EMAIL_USE_SSL": False,
            },
            company_repo=MagicMock(),
            delivery_repo=delivery_repo,
            recon_repo=MagicMock(),
            provider=MagicMock(),
        )
        return service

    def test_resend_records_success_with_company(self, app):
        _reset_repository()
        from backend.modules.email.model import EmailDelivery
        from backend.modules.email.service import EmailService

        delivery = EmailDelivery(
            id=3, company_id=10, run_id=1, recipient_email="payer@test.com",
            status="failed",
        )
        delivery_repo = MagicMock()
        delivery_repo.get_by_id.return_value = delivery
        svc = self._service(delivery_repo)
        svc._recon_repo.list_affected_results_with_party.return_value = [
            {
                "counterparty_email": "payer@test.com",
                "counterparty_name": "Payer",
                "counterparty_tax_id": "TR-1",
            }
        ]

        with patch.object(EmailService, "_render_messages", return_value=("s", "t", "h")):
            result = svc.resend_delivery(1, 3, company_id=10)

        event = _audit_record_kwargs()[-1]
        assert result is not None
        assert event["action"] == AuditLog.ACTION_UPDATE
        assert event["resource_type"] == "email_delivery"
        assert event["resource_id"] == "3"
        assert event["company_id"] == 10
        assert event["metadata"]["event"] == "resend"
        assert "smtp-secret" not in str(event)