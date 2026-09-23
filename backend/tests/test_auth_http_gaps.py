"""HTTP tests for auth surfaces that lacked regression protection (Phase 14).

Gaps closed:
* G1  PUT /api/auth/change-password — missing fields, wrong current password,
      weak new password, success, and the no-secret-in-response invariant.
* G2  POST /api/auth/logout-refresh — missing refresh_token -> 400, success,
      and access-token misuse -> 401.
* G4  JWT token-lifetime error paths — expired token -> TOKEN_EXPIRED and
      malformed token -> INVALID_TOKEN through the real JWT callbacks.
"""

from datetime import timedelta

import bcrypt

from backend.modules.users.model import User


def _user_with_password(password: str, role: str = "admin") -> User:
    return User(
        id=1,
        username="admin",
        email="admin@test.com",
        password_hash=bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
        first_name="Admin",
        last_name="User",
        roles=[role],
        is_active=True,
    )


# ---------------------------------------------------------------------------
# G1 - change password
# ---------------------------------------------------------------------------

class TestChangePassword:
    def test_change_password_missing_fields(self, client, admin_headers):
        for body in ({}, {"current_password": "x"}, {"new_password": "y"}, None):
            response = client.put(
                "/api/auth/change-password", json=body, headers=admin_headers
            )
            assert response.status_code == 400
            assert response.get_json()["message"] == (
                "current_password and new_password are required"
            )

    def test_change_password_wrong_current_password(self, client, admin_headers, mock_repos):
        mock_repos.user_repo.get_by_id.return_value = _user_with_password("correct-password")
        response = client.put(
            "/api/auth/change-password",
            json={"current_password": "wrong", "new_password": "newpassword"},
            headers=admin_headers,
        )
        assert response.status_code == 401
        body = response.get_json()
        assert body["code"] == "UNAUTHORIZED"
        assert body["message"] == "Current password is incorrect"

    def test_change_password_weak_new_password(self, client, admin_headers, mock_repos):
        mock_repos.user_repo.get_by_id.return_value = _user_with_password("correct-password")
        response = client.put(
            "/api/auth/change-password",
            json={"current_password": "correct-password", "new_password": "short"},
            headers=admin_headers,
        )
        assert response.status_code == 400
        assert "at least" in response.get_json()["message"]

    def test_change_password_ok(self, client, admin_headers, mock_repos):
        mock_repos.user_repo.get_by_id.return_value = _user_with_password("correct-password")
        response = client.put(
            "/api/auth/change-password",
            json={"current_password": "correct-password", "new_password": "newpassword"},
            headers=admin_headers,
        )
        assert response.status_code == 200
        body = response.get_json()
        assert body["success"] is True
        serialized = str(body)
        assert "current-password" not in serialized
        assert "newpassword" not in serialized
        mock_repos.user_repo.update_password.assert_called_once()
        user_id_arg, new_hash_arg = mock_repos.user_repo.update_password.call_args.args
        assert user_id_arg == 1
        assert bcrypt.checkpw(b"newpassword", new_hash_arg.encode())


# ---------------------------------------------------------------------------
# G2 - logout-refresh
# ---------------------------------------------------------------------------

class TestLogoutRefresh:
    def test_logout_refresh_requires_refresh_token(self, client, admin_headers):
        response = client.post("/api/auth/logout-refresh", headers=admin_headers)
        assert response.status_code == 400
        assert response.get_json()["message"] == "refresh_token is required"

    def test_logout_refresh_ok(self, client, admin_headers, admin_refresh_token, mock_repos):
        response = client.post(
            "/api/auth/logout-refresh",
            json={"refresh_token": admin_refresh_token},
            headers=admin_headers,
        )
        assert response.status_code == 200
        assert response.get_json()["data"]["message"] == "Refresh token revoked"
        mock_repos.auth_repo.add_to_blocklist.assert_called_once()

    def test_logout_refresh_rejects_access_token(self, client, admin_headers, admin_token):
        response = client.post(
            "/api/auth/logout-refresh",
            json={"refresh_token": admin_token},
            headers=admin_headers,
        )
        assert response.status_code == 401
        assert response.get_json()["message"] == "Token is not a refresh token"


# ---------------------------------------------------------------------------
# G4 - token lifetime error paths
# ---------------------------------------------------------------------------

class TestTokenLifetime:
    def test_expired_access_token_yields_token_expired(self, app, client):
        with app.app_context():
            from flask_jwt_extended import create_access_token
            expired = create_access_token(
                identity="1",
                expires_delta=timedelta(hours=-1),
            )
        response = client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {expired}"}
        )
        assert response.status_code == 401
        assert response.get_json()["code"] == "TOKEN_EXPIRED"

    def test_malformed_token_yields_invalid_token(self, app, client):
        response = client.get(
            "/api/auth/me", headers={"Authorization": "Bearer not.a.token"}
        )
        assert response.status_code == 401
        assert response.get_json()["code"] == "INVALID_TOKEN"

    def test_expired_token_rejected_on_protected_reconciliation(self, app, client, mock_repos):
        with app.app_context():
            from flask_jwt_extended import create_access_token
            expired = create_access_token(
                identity="1",
                additional_claims={"role": "admin"},
                expires_delta=timedelta(hours=-1),
            )
        response = client.get(
            "/api/reconciliation/runs/1/summary",
            headers={"Authorization": f"Bearer {expired}"},
        )
        assert response.status_code == 401
        assert response.get_json()["code"] == "TOKEN_EXPIRED"