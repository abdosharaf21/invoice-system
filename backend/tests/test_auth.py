"""Tests for the authentication foundation.

Verifies that auth routes return proper responses and middleware
works with the mocked app.
"""

import json

from backend.modules.users.model import User


def test_health_check(client):
    """Health check endpoint should return 200."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True


def test_login_missing_credentials(client):
    """Login with missing credentials should return 400."""
    response = client.post(
        "/api/auth/login",
        data=json.dumps({}),
        content_type="application/json",
    )
    assert response.status_code == 400


def test_me_requires_auth(client):
    """GET /api/auth/me without token should return 401."""
    response = client.get("/api/auth/me")
    assert response.status_code in (401, 422)


def test_me_with_valid_token(client, admin_token, mock_repos):
    """GET /api/auth/me with valid token returns user data."""
    mock_user = User(
        id=1,
        full_name="Admin User",
        email="admin@test.com",
        role="admin",
        status="active",
    )
    mock_repos.user_repo.get_by_id.return_value = mock_user
    response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["data"]["email"] == "admin@test.com"


def test_users_list_requires_admin(client, employee_token):
    """Non-admin users should not access user list."""
    response = client.get(
        "/api/users/",
        headers={"Authorization": f"Bearer {employee_token}"},
    )
    assert response.status_code == 403


def test_users_list_requires_auth(client):
    """Unauthenticated users should not access user list."""
    response = client.get("/api/users/")
    assert response.status_code in (401, 422)


def test_admin_can_access_users_list(client, admin_token):
    """Admin users should access user list."""
    response = client.get(
        "/api/users/",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200


def test_refresh_missing_token(client):
    """Refresh without token should return 400."""
    response = client.post(
        "/api/auth/refresh",
        data=json.dumps({}),
        content_type="application/json",
    )
    assert response.status_code == 400


def test_security_headers_present(client):
    """Security headers should be present on responses."""
    response = client.get("/api/health")
    assert "X-Content-Type-Options" in response.headers
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "X-Frame-Options" in response.headers
    assert response.headers["X-Frame-Options"] == "DENY"


def test_request_id_header(client):
    """X-Request-Id header should be present on responses."""
    response = client.get("/api/health")
    assert "X-Request-Id" in response.headers


def test_request_duration_header(client):
    """X-Request-Duration header should be present on responses."""
    response = client.get("/api/health")
    assert "X-Request-Duration" in response.headers
