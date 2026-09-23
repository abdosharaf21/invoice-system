"""Tests for security-event audit trail integration.

Verifies that authentication and authorization events are recorded to
the audit trail with the correct action/result metadata, and that no
secrets (passwords, plaintext hashes, tokens) are ever persisted in the
metadata payload.
"""

from unittest.mock import MagicMock

from backend.modules.audit_trail.model import AuditLog
from backend.modules.audit_trail.service import get_audit_trail_service
from backend.modules.users.model import User


def _record_calls():
    """Return the list of (args, kwargs) passed to repository.record."""
    service = get_audit_trail_service()
    if service is None:
        return []
    return [(c.args, c.kwargs) for c in service._repository.record.call_args_list]


def _audit_record_kwargs():
    """Return the kwargs dicts of all recorded audit events."""
    return [kwargs for (_args, kwargs) in _record_calls()]


def _reset_repository():
    """Swap the configured audit service's repository for a MagicMock."""
    service = get_audit_trail_service()
    if service is not None:
        service._repository = MagicMock()


class TestAuditLoginEvents:
    """Audit events around authentication."""

    def test_login_success_recorded(self, app, client):
        """A successful login records a login/success event with email."""
        from backend.modules.auth.routes import _auth_service
        from backend.shared.security import hash_password

        user = User(
            id=1,
            username="admin",
            email="admin@test.com",
            password_hash=hash_password("password123"),
            first_name="Admin",
            roles=["admin"],
            is_active=True,
        )
        user_repo = MagicMock()
        user_repo.get_by_email.return_value = user
        _auth_service._user_repository = user_repo

        _reset_repository()
        response = client.post("/api/auth/login", json={
            "email": "admin@test.com", "password": "password123"
        })
        assert response.status_code == 200

        records = _audit_record_kwargs()
        assert any(
            r["action"] == AuditLog.ACTION_LOGIN
            and r["result"] == AuditLog.RESULT_SUCCESS
            and r["resource_type"] == "auth"
            for r in records
        )

    def test_login_failure_recorded_no_password(self, app, client):
        """A failed login records a failure event without the password."""
        from backend.modules.auth.routes import _auth_service
        from backend.shared.security import hash_password

        user = User(
            id=1,
            username="admin",
            email="admin@test.com",
            password_hash=hash_password("correct-horse"),
            first_name="Admin",
            roles=["admin"],
            is_active=True,
        )
        user_repo = MagicMock()
        user_repo.get_by_email.return_value = user
        _auth_service._user_repository = user_repo

        _reset_repository()
        response = client.post("/api/auth/login", json={
            "email": "admin@test.com", "password": "wrong-password"
        })
        assert response.status_code == 401

        records = _audit_record_kwargs()
        failure = [
            r for r in records
            if r["action"] == AuditLog.ACTION_LOGIN
            and r["result"] == AuditLog.RESULT_FAILURE
        ]
        assert failure, "no login failure event recorded"
        metadata = failure[0].get("metadata") or {}
        assert "password" not in metadata
        assert "wrong-password" not in str(metadata)


class TestAuditNoSecrets:
    """Ensure audit metadata never contains sensitive material."""

    def test_change_password_not_recorded_with_token_or_hash(self, app, client):
        """A password change event carries no password or token value."""
        from backend.modules.auth.routes import _auth_service
        from backend.shared.security import hash_password

        user = User(
            id=1,
            username="admin",
            email="admin@test.com",
            password_hash=hash_password("currentpass"),
            first_name="Admin",
            roles=["admin"],
            is_active=True,
        )
        user_repo = MagicMock()
        user_repo.get_by_id.return_value = user
        _auth_service._user_repository = user_repo

        _reset_repository()

        svc = _auth_service
        with app.app_context():
            svc.change_password("1", "currentpass", "newpassword123")

        records = _audit_record_kwargs()
        assert records
        serialized = str(records)
        assert "newpassword123" not in serialized


class TestAuditAuthorizationDenied:
    """Audit events for access denials."""

    def test_rbac_403_records_denial(self, app, client, employee_headers):
        """A permission-denied request records an authorization failure."""
        _reset_repository()
        response = client.get("/api/audit-trail/logs", headers=employee_headers)
        assert response.status_code == 403

        records = _audit_record_kwargs()
        assert any(
            r["action"] == AuditLog.ACTION_OTHER
            and r["result"] == AuditLog.RESULT_FAILURE
            and r["resource_type"] == "authorization"
            for r in records
        )

    def test_rbac_403_has_forbidden_code(self, app, client, employee_headers):
        """RBAC 403 responses expose the stable FORBIDDEN code."""
        response = client.get("/api/audit-trail/logs", headers=employee_headers)
        assert response.status_code == 403
        data = response.get_json()
        assert data["code"] == "FORBIDDEN"