"""HTTP tests for the user-management admin surface (Phase 14 gap G3).

Covers the seven admin endpoints under /api/users that previously had no
HTTP-level regression protection:

* GET    /api/users/                 - company-scoped listing
* GET    /api/users/<id>             - single user
* POST   /api/users/                 - create
* PUT    /api/users/<id>             - update
* PUT    /api/users/<id>/password    - admin password reset
* PUT    /api/users/<id>/activate    - activate
* PUT    /api/users/<id>/deactivate  - deactivate
* DELETE /api/users/<id>             - delete

RBAC (admin-only), validation branches, 404 handling, company scoping and
last-admin protection are exercised at the HTTP layer against the mocked
repository fixture (no database required).
"""

import bcrypt
import pytest

from backend.modules.users.model import User

_PASSWORD = "Password123!"


def _make_user(user_id=1, role="admin", company_id=1, is_active=True, name="Admin") -> User:
    return User(
        id=user_id,
        username=f"user{user_id}",
        email=f"{name.lower()}@example.com",
        password_hash=bcrypt.hashpw(b"old-password", bcrypt.gensalt()).decode(),
        first_name=name,
        last_name="User",
        roles=[role],
        company_id=company_id,
        is_active=is_active,
    )


def _create_payload(**overrides):
    payload = {
        "username": "newuser",
        "email": "newuser@example.com",
        "password": _PASSWORD,
        "first_name": "New",
        "last_name": "User",
        "company_id": None,
        "roles": ["viewer"],
        "status": "active",
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# RBAC: every admin endpoint must reject non-admin roles with 403
# ---------------------------------------------------------------------------

_ADMIN_ENDPOINTS = [
    ("get", "/api/users/"),
    ("get", "/api/users/1"),
    ("post", "/api/users/"),
    ("put", "/api/users/1"),
    ("put", "/api/users/1/password"),
    ("put", "/api/users/1/activate"),
    ("put", "/api/users/1/deactivate"),
    ("delete", "/api/users/1"),
]


class TestUserHttpRBAC:
    @pytest.mark.parametrize("method,path", _ADMIN_ENDPOINTS)
    @pytest.mark.parametrize("headers", ["manager_headers", "employee_headers", "viewer_headers"])
    def test_admin_endpoints_forbidden_for_non_admin(self, client, method, path, headers, request):
        response = getattr(client, method)(path, headers=request.getfixturevalue(headers))
        assert response.status_code == 403
        assert response.get_json()["code"] == "FORBIDDEN"

    def test_admin_endpoints_require_authentication(self, client):
        assert client.get("/api/users/").status_code == 401
        assert client.post("/api/users/").status_code == 401


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------

class TestUserHttpList:
    def test_list_empty_when_admin_has_no_company(self, client, admin_headers, mock_repos):
        mock_repos.user_repo.get_by_id.return_value = _make_user(company_id=None)
        response = client.get("/api/users/", headers=admin_headers)
        assert response.status_code == 200
        assert response.get_json()["data"] == []

    def test_list_scoped_to_admin_company(self, client, admin_headers, mock_repos):
        mock_repos.user_repo.get_by_id.return_value = _make_user(company_id=7)
        mock_repos.user_repo.get_all_by_company.return_value = [
            _make_user(1, "admin", company_id=7), _make_user(2, "viewer", company_id=7),
        ]
        response = client.get("/api/users/", headers=admin_headers)
        assert response.status_code == 200
        payload = response.get_json()["data"]
        assert len(payload) == 2
        assert [u["company_id"] for u in payload] == [7, 7]
        mock_repos.user_repo.get_all_by_company.assert_called_once_with(7)


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

class TestUserHttpCreate:
    def test_create_user_ok(self, client, admin_headers, mock_repos):
        mock_repos.user_repo.exists_by_username.return_value = False
        mock_repos.user_repo.exists_by_email.return_value = False
        mock_repos.user_repo.create.return_value = _make_user(role="viewer", name="New")
        response = client.post(
            "/api/users/",
            json=_create_payload(),
            headers=admin_headers,
        )
        assert response.status_code == 201
        data = response.get_json()["data"]
        assert data["username"] == "user1"
        mock_repos.user_repo.create.assert_called_once()

    @pytest.mark.parametrize("missing", ["username", "email", "password"])
    def test_create_user_requires_all_required_fields(self, client, admin_headers, mock_repos, missing):
        payload = _create_payload()
        payload[missing] = None
        response = client.post("/api/users/", json=payload, headers=admin_headers)
        assert response.status_code == 400
        assert response.get_json()["message"] == f"{missing.capitalize()} is required"

    def test_create_user_rejects_duplicate_username(self, client, admin_headers, mock_repos):
        mock_repos.user_repo.exists_by_username.return_value = True
        response = client.post("/api/users/", json=_create_payload(), headers=admin_headers)
        assert response.status_code == 400
        assert response.get_json()["message"] == "Username already exists"

    def test_create_user_rejects_duplicate_email(self, client, admin_headers, mock_repos):
        mock_repos.user_repo.exists_by_username.return_value = False
        mock_repos.user_repo.exists_by_email.return_value = True
        response = client.post("/api/users/", json=_create_payload(), headers=admin_headers)
        assert response.status_code == 400
        assert response.get_json()["message"] == "Email already exists"


# ---------------------------------------------------------------------------
# Single-user retrieve / update / password / activate / deactivate / delete
# ---------------------------------------------------------------------------

class TestUserHttpSingle:
    def test_get_user_ok(self, client, admin_headers, mock_repos):
        mock_repos.user_repo.get_by_id.return_value = _make_user()
        response = client.get("/api/users/1", headers=admin_headers)
        assert response.status_code == 200
        assert response.get_json()["data"]["email"] == "admin@example.com"

    def test_get_user_not_found(self, client, admin_headers, mock_repos):
        mock_repos.user_repo.get_by_id.return_value = None
        response = client.get("/api/users/999", headers=admin_headers)
        assert response.status_code == 404
        assert response.get_json()["message"] == "User not found"

    def test_update_user_ok(self, client, admin_headers, mock_repos):
        user = _make_user()
        mock_repos.user_repo.get_by_id.return_value = user
        mock_repos.user_repo.update.return_value = user
        response = client.put(
            "/api/users/1", json={"first_name": "Renamed"}, headers=admin_headers
        )
        assert response.status_code == 200
        assert response.get_json()["data"]["username"] == "user1"

    def test_update_user_not_found(self, client, admin_headers, mock_repos):
        mock_repos.user_repo.get_by_id.return_value = None
        response = client.put("/api/users/999", json={"first_name": "X"}, headers=admin_headers)
        assert response.status_code == 400
        assert response.get_json()["message"] == "User not found"

    def test_change_user_password_ok(self, client, admin_headers, mock_repos):
        mock_repos.user_repo.get_by_id.return_value = _make_user()
        mock_repos.user_repo.update.return_value = _make_user()
        response = client.put(
            "/api/users/1/password", json={"new_password": _PASSWORD}, headers=admin_headers
        )
        assert response.status_code == 200
        assert response.get_json()["success"] is True

    def test_change_user_password_requires_new_password(self, client, admin_headers):
        response = client.put("/api/users/1/password", json={}, headers=admin_headers)
        assert response.status_code == 400
        assert response.get_json()["message"] == "New password is required"

    def test_activate_user_ok(self, client, admin_headers, mock_repos):
        mock_repos.user_repo.get_by_id.return_value = _make_user(is_active=False)
        mock_repos.user_repo.update.return_value = _make_user(is_active=True)
        response = client.put("/api/users/1/activate", headers=admin_headers)
        assert response.status_code == 200
        assert response.get_json()["data"]["is_active"] is True

    def test_deactivate_user_ok(self, client, admin_headers, mock_repos):
        mock_repos.user_repo.get_by_id.return_value = _make_user(role="viewer")
        mock_repos.user_repo.update.return_value = _make_user(role="viewer", is_active=False)
        response = client.put("/api/users/1/deactivate", headers=admin_headers)
        assert response.status_code == 200
        assert response.get_json()["data"]["is_active"] is False

    def test_deactivate_last_active_admin_rejected_at_http(self, client, admin_headers, mock_repos):
        mock_repos.user_repo.get_by_id.return_value = _make_user(role="admin")
        mock_repos.user_repo.count_active_admins.return_value = 1
        response = client.put("/api/users/1/deactivate", headers=admin_headers)
        assert response.status_code == 400
        assert "last active admin" in response.get_json()["message"]

    def test_delete_user_ok(self, client, admin_headers, mock_repos):
        mock_repos.user_repo.get_by_id.return_value = _make_user(role="viewer")
        mock_repos.user_repo.delete.return_value = True
        response = client.delete("/api/users/1", headers=admin_headers)
        assert response.status_code == 200
        assert response.get_json()["message"] == "User deleted successfully"

    def test_delete_user_not_found(self, client, admin_headers, mock_repos):
        mock_repos.user_repo.get_by_id.return_value = _make_user(role="viewer")
        mock_repos.user_repo.delete.return_value = False
        response = client.delete("/api/users/999", headers=admin_headers)
        assert response.status_code == 404
        assert response.get_json()["message"] == "User not found"

    def test_delete_last_active_admin_rejected_at_http(self, client, admin_headers, mock_repos):
        mock_repos.user_repo.get_by_id.return_value = _make_user(role="admin")
        mock_repos.user_repo.count_active_admins.return_value = 1
        response = client.delete("/api/users/1", headers=admin_headers)
        assert response.status_code == 404  # ValueError routed through the delete 404 branch
        assert "last active admin" in response.get_json()["message"]