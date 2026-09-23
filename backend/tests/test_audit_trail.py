"""Tests for the Audit Trail module (service + model)."""

from unittest.mock import MagicMock

import pytest

from backend.modules.audit_trail.model import AuditLog
from backend.modules.audit_trail.service import AuditTrailService


class TestAuditLogModel:
    """Tests for the AuditLog model."""

    def test_to_dict_roundtrip(self):
        """to_dict must expose all fields and from_dict must rebuild them."""
        entry = AuditLog(
            id=1,
            actor_id=5,
            actor_email="a@b.com",
            role="manager",
            action=AuditLog.ACTION_UPDATE,
            resource_type="invoice",
            resource_id="42",
            result=AuditLog.RESULT_SUCCESS,
            metadata={"qty": 3},
            request_id="req-1",
            created_at="2026-08-01T10:00:00",
        )
        data = entry.to_dict()
        assert data["action"] == "update"
        assert data["metadata"] == {"qty": 3}
        rebuilt = AuditLog.from_dict(data)
        assert rebuilt.actor_id == 5
        assert rebuilt.resource_type == "invoice"

    def test_defaults(self):
        """Defaults should be empty/optional-safe."""
        entry = AuditLog()
        data = entry.to_dict()
        assert data["actor_id"] is None
        assert data["metadata"] is None


class TestAuditTrailService:
    """Tests for audit trail service validation and orchestration."""

    def test_record_success(self):
        """record must delegate to the repository and return the id."""
        repo = MagicMock()
        repo.record.return_value = 99
        service = AuditTrailService(repo)

        entry_id = service.record(
            actor_id=1,
            actor_email="admin@test.com",
            role="admin",
            action=AuditLog.ACTION_CREATE,
            resource_type="invoice",
            resource_id="10",
            result=AuditLog.RESULT_SUCCESS,
            metadata={"name": "Widget"},
            request_id="req-abc",
        )

        assert entry_id == 99
        repo.record.assert_called_once_with(
            actor_id=1,
            actor_email="admin@test.com",
            role="admin",
            action="create",
            resource_type="invoice",
            resource_id="10",
            result="success",
            metadata={"name": "Widget"},
            request_id="req-abc",
            ip_address=None,
            user_agent=None,
            company_id=None,
            actor_type="user",
            before_state=None,
            after_state=None,
        )

    def test_record_rejects_invalid_action(self):
        """An unknown action should raise ValueError."""
        service = AuditTrailService(MagicMock())
        with pytest.raises(ValueError):
            service.record(
                actor_id=1,
                actor_email="a@b.com",
                role="admin",
                action="explode",
                resource_type="invoice",
            )

    def test_record_rejects_invalid_result(self):
        """An unknown result should raise ValueError."""
        service = AuditTrailService(MagicMock())
        with pytest.raises(ValueError):
            service.record(
                actor_id=1,
                actor_email="a@b.com",
                role="admin",
                action=AuditLog.ACTION_CREATE,
                resource_type="invoice",
                result="maybe",
            )

    def test_list_logs_pagination_shape(self):
        """list_logs must return a paginated envelope."""
        repo = MagicMock()
        repo.list_logs.return_value = ([{"id": 1}], 1)
        service = AuditTrailService(repo)

        result = service.list_logs(page=1, page_size=50)

        assert result["items"] == [{"id": 1}]
        assert result["total"] == 1
        assert result["page"] == 1
        assert result["page_size"] == 50
        assert result["pages"] == 1

    def test_list_logs_invalid_action_filter(self):
        """A bad action filter should raise ValueError before hitting repo."""
        service = AuditTrailService(MagicMock())
        with pytest.raises(ValueError):
            service.list_logs(action="nonsense")

    def test_record_from_context_uses_context_helpers(self, app):
        """record_from_context must source actor + request id from g."""
        repo = MagicMock()
        repo.record.return_value = 7
        service = AuditTrailService(repo)

        with app.test_request_context():
            from flask import g
            g.user_id = 3
            g.user_email = "emp@test.com"
            g.user_role = "employee"
            g.request_id = "req-ctx"

            service.record_from_context(
                action=AuditLog.ACTION_VIEW,
                resource_type="report",
            )

        kwargs = repo.record.call_args.kwargs
        assert kwargs["actor_id"] == 3
        assert kwargs["actor_email"] == "emp@test.com"
        assert kwargs["role"] == "employee"
        assert kwargs["request_id"] == "req-ctx"