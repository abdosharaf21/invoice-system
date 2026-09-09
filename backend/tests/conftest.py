"""Pytest configuration and fixtures for API tests.

Provides mock-based Flask app, test client, and JWT token fixtures
for all three roles (admin, manager, employee). All repositories
and DB connections are mocked so no real database is needed.
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import timedelta, datetime, timezone

from backend.modules.users.model import User

_JWT_SECRET = "test-secret-key-xxxxxxxxxxxxxxxxxxx"


def _make_user(user_id: int, email: str, role: str, name: str) -> User:
    """Factory helper that returns a realistic User model instance."""
    return User(
        id=user_id,
        username=f"user{user_id}",
        email=email,
        password_hash="$2b$12$xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        first_name=name,
        roles=[role],
        is_active=True,
        created_at=datetime.now(timezone.utc).isoformat(),
        updated_at=datetime.now(timezone.utc).isoformat(),
    )


class _MockRepos:
    """Container for mock repository instances created during app setup."""

    def __init__(self):
        self.user_repo = None
        self.auth_repo = None
        self.batch_repo = None
        self.invoice_repo = None
        self.import_service = None


@pytest.fixture
def mock_repos():
    """Shared mock repository container for test-level configuration."""
    return _MockRepos()


@pytest.fixture
def app(mock_repos):
    """Create a fully mocked Flask application for testing.

    Patches every repository + Database internals so the app
    starts without a real database.
    """
    user_repo_mock = MagicMock()
    auth_repo_mock = MagicMock()
    batch_repo_mock = MagicMock()
    invoice_repo_mock = MagicMock()
    import_service_mock = MagicMock()

    import_service_mock.company_for_user.return_value = 1

    patches = [
        patch("backend.app.AuthRepository", return_value=auth_repo_mock),
        patch("backend.app.UserRepository", return_value=user_repo_mock),
        patch("backend.app.ImportBatchRepository", return_value=batch_repo_mock),
        patch("backend.app.InvoiceRepository", return_value=invoice_repo_mock),
        patch("backend.app.ImportService", return_value=import_service_mock),
        patch("backend.database.connection.Database._initialize_pool"),
    ]

    for p in patches:
        p.start()

    mock_repos.user_repo = user_repo_mock
    mock_repos.auth_repo = auth_repo_mock
    mock_repos.batch_repo = batch_repo_mock
    mock_repos.invoice_repo = invoice_repo_mock
    mock_repos.import_service = import_service_mock

    from backend.app import create_app

    test_config = {
        "TESTING": True,
        "SECRET_KEY": _JWT_SECRET,
        "JWT_SECRET_KEY": _JWT_SECRET,
        "JWT_ACCESS_TOKEN_EXPIRES": timedelta(hours=1),
        "JWT_REFRESH_TOKEN_EXPIRES": timedelta(days=30),
    }

    application = create_app(config=test_config)
    yield application

    for p in patches:
        p.stop()


@pytest.fixture
def client(app):
    """Flask test client bound to the mocked app."""
    return app.test_client()


# ---------------------------------------------------------------------------
# JWT token fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def admin_token(app):
    """Valid JWT access token for an admin user."""
    with app.app_context():
        from flask_jwt_extended import create_access_token
        return create_access_token(
            identity="1",
            additional_claims={"email": "admin@test.com", "role": "admin", "full_name": "Admin User"},
        )


@pytest.fixture
def manager_token(app):
    """Valid JWT access token for a manager user."""
    with app.app_context():
        from flask_jwt_extended import create_access_token
        return create_access_token(
            identity="2",
            additional_claims={"email": "manager@test.com", "role": "manager", "full_name": "Manager User"},
        )


@pytest.fixture
def employee_token(app):
    """Valid JWT access token for an employee user."""
    with app.app_context():
        from flask_jwt_extended import create_access_token
        return create_access_token(
            identity="3",
            additional_claims={"email": "employee@test.com", "role": "employee", "full_name": "Employee User"},
        )


@pytest.fixture
def viewer_token(app):
    """Valid JWT access token for a viewer user."""
    with app.app_context():
        from flask_jwt_extended import create_access_token
        return create_access_token(
            identity="4",
            additional_claims={"email": "viewer@test.com", "role": "viewer", "full_name": "Viewer User"},
        )


@pytest.fixture
def admin_refresh_token(app):
    """Valid JWT refresh token for an admin user."""
    with app.app_context():
        from flask_jwt_extended import create_refresh_token
        return create_refresh_token(identity="1")


@pytest.fixture
def admin_headers(admin_token):
    """HTTP Authorization header dict for admin."""
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def manager_headers(manager_token):
    """HTTP Authorization header dict for manager."""
    return {"Authorization": f"Bearer {manager_token}"}


@pytest.fixture
def employee_headers(employee_token):
    """HTTP Authorization header dict for employee."""
    return {"Authorization": f"Bearer {employee_token}"}


@pytest.fixture
def viewer_headers(viewer_token):
    """HTTP Authorization header dict for viewer."""
    return {"Authorization": f"Bearer {viewer_token}"}


# ---------------------------------------------------------------------------
# Sample data fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_user():
    """Sample user data dict."""
    return {
        "id": 1,
        "username": "testuser",
        "email": "test@example.com",
        "first_name": "Test",
        "last_name": "User",
        "roles": ["viewer"],
        "status": "active",
    }
