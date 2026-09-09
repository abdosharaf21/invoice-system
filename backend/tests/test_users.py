"""Tests for the reconciled users domain.

Verifies the User model matches the reconciled schema and that the
UserService behaves correctly against a mocked repository.
"""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from backend.modules.users.model import User
from backend.modules.users.service import UserService
from backend.modules.users.validator import UserValidator


_PASSWORD_HASH = "$2b$12$S6K77KBp40oAgCdh0gaThefjHeH3F8Z.lOUIHzYD5yo.3OemNOFeC"


def _make_user(role: str = None, is_active: bool = True) -> User:
    return User(
        id=1,
        company_id=1,
        username="admin1",
        email="admin@example.com",
        password_hash=_PASSWORD_HASH,
        first_name="Admin",
        last_name="User",
        is_active=is_active,
        roles=[role] if role else ["viewer"],
    )


def _make_service(repo=None):
    return UserService(repo or MagicMock())


# ---------------------------------------------------------------------------
# User model
# ---------------------------------------------------------------------------

class TestUserModel:
    def test_full_name_combines_first_and_last(self):
        user = _make_user()
        assert user.full_name == "Admin User"

    def test_full_name_falls_back_to_first_name(self):
        user = User(first_name="Solo")
        assert user.full_name == "Solo"

    def test_role_returns_primary_role(self):
        user = User(first_name="A", roles=["admin", "viewer"])
        assert user.role == "admin"

    def test_role_none_when_no_roles(self):
        user = User(first_name="A")
        assert user.role is None

    def test_status_derived_from_is_active(self):
        assert _make_user(is_active=True).status == "active"
        assert _make_user(is_active=False).status == "inactive"

    def test_to_dict_contains_reconciled_fields(self):
        data = _make_user(role="accountant").to_dict()
        assert data["username"] == "admin1"
        assert data["company_id"] == 1
        assert data["first_name"] == "Admin"
        assert data["last_name"] == "User"
        assert data["full_name"] == "Admin User"
        assert data["roles"] == ["accountant"]
        assert data["is_active"] is True
        assert data["status"] == "active"
        assert "phone" not in data

    def test_from_dict_round_trip(self):
        iso = datetime(2025, 1, 15, 10, 30, 0).isoformat()
        data = {
            "id": 3,
            "company_id": 2,
            "username": "jdoe",
            "email": "jdoe@example.com",
            "first_name": "Jane",
            "last_name": "Doe",
            "roles": ["manager"],
            "status": "inactive",
            "created_at": iso,
            "updated_at": iso,
        }
        user = User.from_dict(data)
        assert user.username == "jdoe"
        assert user.roles == ["manager"]
        assert user.is_active is False
        assert user.status == "inactive"
        assert user.created_at == datetime(2025, 1, 15, 10, 30, 0)
        restored = user.to_dict()
        assert restored["first_name"] == "Jane"
        assert restored["roles"] == ["manager"]


# ---------------------------------------------------------------------------
# User validator
# ---------------------------------------------------------------------------

class TestUserValidator:
    def test_valid_roles_are_seeded_role_names(self):
        assert UserValidator.VALID_ROLES == ["admin", "accountant", "manager", "viewer"]

    def test_validate_roles_rejects_unknown_role(self):
        with pytest.raises(ValueError):
            UserValidator.validate_roles(["employee"])

    def test_validate_roles_returns_list(self):
        assert UserValidator.validate_roles(["ADMIN"]) == ["admin"]

    def test_validate_create_user_requires_username(self):
        with pytest.raises(ValueError):
            UserValidator.validate_create_user({"email": "a@b.com", "password": "password123", "username": None})


# ---------------------------------------------------------------------------
# User service
# ---------------------------------------------------------------------------

class TestUserService:
    def test_create_user_assigns_default_viewer_role(self):
        repo = MagicMock()
        repo.exists_by_username.return_value = False
        repo.exists_by_email.return_value = False
        repo.create.return_value = _make_user()
        service = _make_service(repo)

        service.create_user({
            "username": "viewer1",
            "email": "viewer1@example.com",
            "password": "password123",
            "first_name": "Test",
            "last_name": "One",
            "company_id": 1,
            "roles": [],
            "status": "active",
        })

        created = repo.create.call_args[0][0]
        assert created.roles == ["viewer"]

    def test_create_user_requires_roles(self):
        repo = MagicMock()
        repo.exists_by_username.return_value = False
        repo.exists_by_email.return_value = False
        service = _make_service(repo)

        service.create_user({
            "username": "acct1",
            "email": "acct1@example.com",
            "password": "password123",
            "first_name": "Test",
            "roles": ["accountant"],
        })

        created = repo.create.call_args[0][0]
        assert created.roles == ["accountant"]

    def test_create_user_rejects_duplicate_username(self):
        repo = MagicMock()
        repo.exists_by_username.return_value = True
        service = _make_service(repo)

        with pytest.raises(ValueError, match="Username already exists"):
            service.create_user({
                "username": "dup",
                "email": "dup@example.com",
                "password": "password123",
            })

    def test_create_user_rejects_duplicate_email(self):
        repo = MagicMock()
        repo.exists_by_username.return_value = False
        repo.exists_by_email.return_value = True
        service = _make_service(repo)

        with pytest.raises(ValueError, match="Email already exists"):
            service.create_user({
                "username": "dup",
                "email": "dup@example.com",
                "password": "password123",
            })

    def test_login_rejects_inactive_user(self):
        repo = MagicMock()
        repo.get_by_email.return_value = _make_user(is_active=False)
        service = _make_service(repo)

        with pytest.raises(ValueError, match="Account is inactive"):
            service.login("admin@example.com", "password123")

    def test_deactivate_last_active_admin_rejected(self):
        repo = MagicMock()
        repo.get_by_id.return_value = _make_user(role="admin")
        repo.count_active_admins.return_value = 1
        service = _make_service(repo)

        with pytest.raises(ValueError, match="last active admin"):
            service.deactivate_user(1)

    def test_deactivate_admin_ok_when_other_admin_exists(self):
        repo = MagicMock()
        repo.get_by_id.return_value = _make_user(role="admin")
        repo.count_active_admins.return_value = 2
        repo.update.return_value = _make_user(role="admin", is_active=False)
        service = _make_service(repo)

        user = service.deactivate_user(1)
        assert user.status == "inactive"

    def test_delete_last_active_admin_rejected(self):
        repo = MagicMock()
        repo.get_by_id.return_value = _make_user(role="admin")
        repo.count_active_admins.return_value = 1
        service = _make_service(repo)

        with pytest.raises(ValueError, match="last active admin"):
            service.delete_user(1)