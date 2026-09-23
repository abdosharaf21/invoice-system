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


def test_login_post_route_reaches_handler(client, monkeypatch):
    """POST /api/auth/login must dispatch to the route handler, not 405.

    Method checking stays on: only the POST path must invoke the service.
    The service is stubbed so the assertion is purely about routing.
    """
    from backend.modules.auth import routes as auth_routes
    from backend.middleware.exceptions import UnauthorizedException

    class StubAuthService:
        def login(self, email, password):
            raise UnauthorizedException("Bad credentials")

    monkeypatch.setattr(auth_routes, "_auth_service", StubAuthService())
    response = client.post(
        "/api/auth/login",
        data=json.dumps({"email": "any@test.com", "password": "password123"}),
        content_type="application/json",
    )
    assert response.status_code == 401
    data = response.get_json()
    assert data["success"] is False
    assert data["message"] == "Bad credentials"


def test_login_get_is_method_not_allowed(client):
    """A GET to /api/auth/login must keep yielding the 405 METHOD_NOT_ALLOWED envelope."""
    response = client.get("/api/auth/login")
    assert response.status_code == 405
    data = response.get_json()
    assert data == {
        "success": False,
        "message": "Method not allowed",
        "status": 405,
        "code": "METHOD_NOT_ALLOWED",
    }


def test_login_options_preflight_ok(client):
    """CORS preflight (OPTIONS) to /api/auth/login must pass, not 405."""
    response = client.options(
        "/api/auth/login",
        headers={
            "Origin": "http://localhost:8899",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert "OPTIONS" in (response.headers.get("Allow") or "")


def test_me_requires_auth(client):
    """GET /api/auth/me without token should return 401."""
    response = client.get("/api/auth/me")
    assert response.status_code in (401, 422)


def test_me_with_valid_token(client, admin_token, mock_repos):
    """GET /api/auth/me with valid token returns user data."""
    mock_user = User(
        id=1,
        username="admin",
        email="admin@test.com",
        first_name="Admin",
        last_name="User",
        roles=["admin"],
        is_active=True,
    )
    mock_repos.user_repo.get_by_id.return_value = mock_user
    response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["data"]["email"] == "admin@test.com"


def test_login_rejects_inactive_user(client, mock_repos):
    """API login must reject a deactivated account with a generic 401."""
    import bcrypt

    inactive = User(
        id=1,
        username="inactive",
        email="inactive@test.com",
        password_hash=bcrypt.hashpw(b"password123", bcrypt.gensalt()).decode(),
        first_name="Inactive",
        last_name="User",
        roles=["admin"],
        is_active=False,
    )
    mock_repos.user_repo.get_by_email.return_value = inactive
    response = client.post(
        "/api/auth/login",
        data=json.dumps({"email": "inactive@test.com", "password": "password123"}),
        content_type="application/json",
    )
    assert response.status_code == 401


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


def test_refresh_rejects_inactive_user(client, admin_refresh_token, mock_repos):
    """Deactivated accounts must not be able to exchange a refresh token."""
    import bcrypt

    inactive = User(
        id=1,
        username="inactive",
        email="inactive@test.com",
        password_hash=bcrypt.hashpw(b"password123", bcrypt.gensalt()).decode(),
        first_name="Inactive",
        last_name="User",
        roles=["admin"],
        is_active=False,
    )
    mock_repos.user_repo.get_by_id.return_value = inactive
    mock_repos.auth_repo.is_blocklisted.return_value = False

    response = client.post(
        "/api/auth/refresh",
        data=json.dumps({"refresh_token": admin_refresh_token}),
        content_type="application/json",
    )
    assert response.status_code == 401


def test_refresh_with_active_user(client, admin_refresh_token, mock_repos):
    """Active accounts can still exchange a refresh token."""
    active = User(
        id=1,
        username="admin",
        email="admin@test.com",
        first_name="Admin",
        last_name="User",
        roles=["admin"],
        is_active=True,
    )
    mock_repos.user_repo.get_by_id.return_value = active
    mock_repos.auth_repo.is_blocklisted.return_value = False

    response = client.post(
        "/api/auth/refresh",
        data=json.dumps({"refresh_token": admin_refresh_token}),
        content_type="application/json",
    )
    assert response.status_code == 200
    assert "access_token" in response.get_json()["data"]


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


def test_revoked_access_token_rejected_via_db_after_restart(
    client, admin_token, mock_repos
):
    """A revoked access token stays revoked after an app restart.

    The token is never added to the in-process blocklist (as happens after a
    restart, when the in-memory set is empty). Rejection can only come from
    the persistent DB blocklist check, which is exactly what the loader must
    consult for revocation to survive a restart.
    """
    from flask_jwt_extended import decode_token

    with client.application.app_context():
        jti = decode_token(admin_token)["jti"]

    mock_repos.auth_repo.is_blocklisted.side_effect = lambda value: value == jti

    response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 401
    assert response.get_json()["code"] == "TOKEN_REVOKED"


def test_logout_revokes_token_immediately_in_process(client, admin_token):
    """Logout must revoke the access token for the current process."""
    response = client.post(
        "/api/auth/logout",
        headers={"Authorization": f"Bearer {admin_token}"},
        content_type="application/json",
    )
    assert response.status_code == 200

    response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 401
    assert response.get_json()["code"] == "TOKEN_REVOKED"


def test_logout_persists_access_and_refresh_to_db(
    client, admin_token, admin_refresh_token, mock_repos
):
    """Logout must persist both the access and refresh JTIs to the DB."""
    mock_repos.auth_repo.reset_mock()

    response = client.post(
        "/api/auth/logout",
        data=json.dumps({"refresh_token": admin_refresh_token}),
        headers={"Authorization": f"Bearer {admin_token}"},
        content_type="application/json",
    )
    assert response.status_code == 200

    calls = mock_repos.auth_repo.add_to_blocklist.call_args_list
    assert len(calls) == 2
    assert {call.args[1] for call in calls} == {"access", "refresh"}


def test_users_logout_persists_access_jti_to_db(client, admin_token, mock_repos):
    """Legacy /api/users/logout must persist the access JTI to the DB."""
    from flask_jwt_extended import decode_token

    mock_repos.auth_repo.reset_mock()

    with client.application.app_context():
        jti = decode_token(admin_token)["jti"]

    response = client.post(
        "/api/users/logout",
        headers={"Authorization": f"Bearer {admin_token}"},
        content_type="application/json",
    )
    assert response.status_code == 200

    call = mock_repos.auth_repo.add_to_blocklist.call_args
    assert call is not None
    assert call.args[0] == jti
    assert call.args[1] == "access"
