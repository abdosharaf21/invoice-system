"""SECURITY-1 regression: tenant isolation for the user-management surface.

The users module previously scoped only the *listing* endpoint to the
actor's company; every single-user operation (GET/PUT/DELETE ``/<id>``,
password, activate, deactivate) and user creation trusted role checks alone,
letting a company-admin read and provision users belonging to another
company.

The fix binds user management to the authenticated actor's company derived
from trusted server context (the signed JWT ``company_id`` claim surfaced as
``g.user_company_id``). Platform-level admins (``company_id`` claim absent →
``None``) retain their existing cross-company scope.

These tests cover service- and HTTP-level behaviour, both tenants, payload
forgery attempts, and the platform-admin exemption.
"""

import bcrypt
import pytest
from unittest.mock import MagicMock

from backend.modules.users.model import User
from backend.modules.users.service import UserService

_PASSWORD = "Password123!"

COMPANY_A = 10
COMPANY_B = 20

_GOOD_CREATE = {
    "username": "newuser",
    "email": "newuser@example.com",
    "password": _PASSWORD,
    "first_name": "New",
    "last_name": "User",
    "company_id": None,
    "roles": ["viewer"],
    "status": "active",
}


def _make_user(user_id=1, company_id=COMPANY_A, role="viewer", is_active=True, name="User") -> User:
    return User(
        id=user_id,
        company_id=company_id,
        username=f"user{user_id}",
        email=f"{name.lower()}@example.com",
        password_hash=bcrypt.hashpw(b"old-password", bcrypt.gensalt()).decode(),
        first_name=name,
        last_name="Name",
        roles=[role],
        is_active=is_active,
    )


def _service(repo=None, company_repo=None):
    if company_repo is None:
        company_repo = MagicMock()
        company_repo.get_by_id.return_value = MagicMock()
    return UserService(repo or MagicMock(), company_repository=company_repo)


def _scoped_headers(app, company_id, role="admin", identity="1"):
    """Build auth headers whose token carries a company claim."""
    from flask_jwt_extended import create_access_token
    with app.app_context():
        token = create_access_token(
            identity=identity,
            additional_claims={
                "email": "admin@test.com",
                "role": role,
                "company_id": company_id,
            },
        )
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Service level
# ---------------------------------------------------------------------------

class TestTenantScopeServiceRead:
    def test_get_user_by_id_scopes_lookup_to_actor_company(self):
        repo = MagicMock()
        repo.get_by_id_for_company.return_value = _make_user(1, COMPANY_A)
        service = _service(repo)
        service.get_user_by_id(1, actor_company_id=COMPANY_A)
        repo.get_by_id_for_company.assert_called_once_with(1, COMPANY_A)
        repo.get_by_id.assert_not_called()

    def test_get_user_by_id_platform_admin_uses_unscoped_lookup(self):
        repo = MagicMock()
        repo.get_by_id.return_value = _make_user(1, COMPANY_B)
        service = _service(repo)
        assert service.get_user_by_id(1, actor_company_id=None).email == "user@example.com"
        repo.get_by_id.assert_called_once_with(1)
        repo.get_by_id_for_company.assert_not_called()

    def test_get_user_by_id_cross_tenant_not_found(self):
        repo = MagicMock()
        repo.get_by_id_for_company.return_value = None
        service = _service(repo)
        with pytest.raises(ValueError, match="User not found"):
            service.get_user_by_id(42, actor_company_id=COMPANY_A)


class TestTenantScopeServiceCreate:
    def _payload(self, company_id=None):
        payload = dict(_GOOD_CREATE)
        payload["company_id"] = company_id
        return payload

    def test_scoped_create_forces_actor_company(self):
        repo = MagicMock()
        repo.exists_by_username.return_value = False
        repo.exists_by_email.return_value = False
        repo.create.return_value = _make_user(7, COMPANY_A)
        service = _service(repo)
        result = service.create_user(self._payload(company_id=COMPANY_B), actor_company_id=COMPANY_A)
        assert result.company_id == COMPANY_A
        created = repo.create.call_args[0][0]
        assert created.company_id == COMPANY_A

    def test_scoped_create_forces_company_even_when_none(self):
        repo = MagicMock()
        repo.exists_by_username.return_value = False
        repo.exists_by_email.return_value = False
        repo.create.return_value = _make_user(7, COMPANY_A)
        service = _service(repo)
        service.create_user(self._payload(company_id=None), actor_company_id=COMPANY_A)
        created = repo.create.call_args[0][0]
        assert created.company_id == COMPANY_A

    def test_scoped_create_ignores_company_key(self):
        repo = MagicMock()
        repo.exists_by_username.return_value = False
        repo.exists_by_email.return_value = False
        repo.create.return_value = _make_user(7, COMPANY_A)
        service = _service(repo)
        payload = self._payload(company_id=None)
        payload["company"] = COMPANY_B
        service.create_user(payload, actor_company_id=COMPANY_A)
        created = repo.create.call_args[0][0]
        assert created.company_id == COMPANY_A

    def test_platform_admin_create_keeps_client_company(self):
        repo = MagicMock()
        repo.exists_by_username.return_value = False
        repo.exists_by_email.return_value = False
        repo.create.return_value = _make_user(7, COMPANY_B)
        service = _service(repo)
        result = service.create_user(self._payload(company_id=COMPANY_B), actor_company_id=None)
        assert result.company_id == COMPANY_B


class TestTenantScopeServiceUpdate:
    def test_scoped_update_binds_target_and_drops_company_reassignment(self):
        repo = MagicMock()
        target = _make_user(9, COMPANY_A)
        repo.get_by_id_for_company.return_value = target
        repo.update.side_effect = lambda user: user
        service = _service(repo)
        updated = service.update_user(
            9, {"first_name": "New", "company_id": COMPANY_B}, actor_company_id=COMPANY_A
        )
        assert updated.company_id == COMPANY_A
        assert updated.first_name == "New"

    def test_scoped_update_company_only_payload_rejected(self):
        repo = MagicMock()
        repo.get_by_id_for_company.return_value = _make_user(9, COMPANY_A)
        service = _service(repo)
        with pytest.raises(ValueError, match="No valid fields to update"):
            service.update_user(9, {"company_id": COMPANY_B}, actor_company_id=COMPANY_A)

    def test_scoped_update_cross_tenant_not_found(self):
        repo = MagicMock()
        repo.get_by_id_for_company.return_value = None
        service = _service(repo)
        with pytest.raises(ValueError, match="User not found"):
            service.update_user(42, {"first_name": "X"}, actor_company_id=COMPANY_A)


class TestTenantScopeServiceMutations:
    @pytest.mark.parametrize("call", [
        ("change_password", dict(new_password=_PASSWORD)),
        ("activate_user", {}),
        ("deactivate_user", {}),
    ])
    def test_scoped_mutation_cross_tenant_not_found(self, call):
        repo = MagicMock()
        repo.get_by_id_for_company.return_value = None
        service = _service(repo)
        with pytest.raises(ValueError, match="User not found"):
            getattr(service, call[0])(42, **call[1], actor_company_id=COMPANY_A)

    def test_scoped_delete_cross_tenant_not_found(self):
        repo = MagicMock()
        repo.get_by_id_for_company.return_value = None
        service = _service(repo)
        with pytest.raises(ValueError, match="User not found"):
            service.delete_user(42, actor_company_id=COMPANY_A)

    def test_scoped_mutation_uses_company_scoped_lookup(self):
        repo = MagicMock()
        repo.get_by_id_for_company.return_value = _make_user(5, COMPANY_A, role="viewer")
        repo.update.return_value = _make_user(5, COMPANY_A, role="viewer")
        service = _service(repo)
        service.deactivate_user(5, actor_company_id=COMPANY_A)
        repo.get_by_id_for_company.assert_called_once_with(5, COMPANY_A)
        repo.get_by_id.assert_not_called()

    def test_scoped_delete_uses_company_scoped_lookup(self):
        repo = MagicMock()
        repo.get_by_id_for_company.return_value = _make_user(5, COMPANY_A, role="viewer")
        repo.delete.return_value = True
        service = _service(repo)
        assert service.delete_user(5, actor_company_id=COMPANY_A) is True
        repo.get_by_id_for_company.assert_called_once_with(5, COMPANY_A)


# ---------------------------------------------------------------------------
# HTTP level
# ---------------------------------------------------------------------------

def _neutralize_company_repo(monkeypatch):
    """Prevent the real (DB-bound) company repository from running under mocks."""
    from backend.modules.users import routes as users_routes
    company_repo = MagicMock()
    company_repo.get_by_id.return_value = MagicMock()
    monkeypatch.setattr(users_routes._user_service, "_company_repository", company_repo)


class TestTenantIsolationHTTP:
    def test_cross_tenant_read_returns_not_found(self, client, mock_repos, monkeypatch):
        mock_repos.user_repo.get_by_id_for_company.return_value = None
        headers = _scoped_headers(client.application, COMPANY_A)
        response = client.get("/api/users/42", headers=headers)
        assert response.status_code == 404
        assert response.get_json()["message"] == "User not found"
        mock_repos.user_repo.get_by_id_for_company.assert_called_once_with(42, COMPANY_A)

    def test_platform_admin_can_read_any_company_user(self, client, mock_repos, admin_headers):
        mock_repos.user_repo.get_by_id.return_value = _make_user(42, COMPANY_B)
        response = client.get("/api/users/42", headers=admin_headers)
        assert response.status_code == 200
        assert response.get_json()["data"]["company_id"] == COMPANY_B

    def test_cross_tenant_create_cannot_provision_other_company(self, client, mock_repos, monkeypatch):
        _neutralize_company_repo(monkeypatch)
        mock_repos.user_repo.exists_by_username.return_value = False
        mock_repos.user_repo.exists_by_email.return_value = False
        mock_repos.user_repo.create.return_value = _make_user(77, COMPANY_A)
        headers = _scoped_headers(client.application, COMPANY_A)

        payload = dict(_GOOD_CREATE)
        payload["company_id"] = COMPANY_B
        payload["roles"] = ["admin"]
        response = client.post("/api/users/", json=payload, headers=headers)

        assert response.status_code == 201
        assert response.get_json()["data"]["company_id"] == COMPANY_A
        created = mock_repos.user_repo.create.call_args[0][0]
        assert created.company_id == COMPANY_A

    def test_cross_tenant_create_with_company_key_ignored(self, client, mock_repos, monkeypatch):
        _neutralize_company_repo(monkeypatch)
        mock_repos.user_repo.exists_by_username.return_value = False
        mock_repos.user_repo.exists_by_email.return_value = False
        mock_repos.user_repo.create.return_value = _make_user(77, COMPANY_A)
        payload = dict(_GOOD_CREATE)
        payload.pop("company_id", None)
        payload["company"] = COMPANY_B
        response = client.post(
            "/api/users/", json=payload, headers=_scoped_headers(client.application, COMPANY_A)
        )
        assert response.status_code == 201
        created = mock_repos.user_repo.create.call_args[0][0]
        assert created.company_id == COMPANY_A

    def test_scoped_create_omitted_and_null_company_bound_to_actor(self, client, mock_repos, monkeypatch):
        _neutralize_company_repo(monkeypatch)
        mock_repos.user_repo.exists_by_username.return_value = False
        mock_repos.user_repo.exists_by_email.return_value = False
        mock_repos.user_repo.create.side_effect = lambda user: user
        headers = _scoped_headers(client.application, COMPANY_A)

        for payload in [dict(_GOOD_CREATE, company_id=None), dict(_GOOD_CREATE, company_id=COMPANY_B)]:
            response = client.post("/api/users/", json=payload, headers=headers)
            assert response.status_code == 201
            assert response.get_json()["data"]["company_id"] == COMPANY_A

    def test_platform_admin_can_create_user_in_company(self, client, mock_repos, monkeypatch, admin_headers):
        _neutralize_company_repo(monkeypatch)
        mock_repos.user_repo.exists_by_username.return_value = False
        mock_repos.user_repo.exists_by_email.return_value = False
        mock_repos.user_repo.create.return_value = _make_user(78, COMPANY_B)
        payload = dict(_GOOD_CREATE, company_id=COMPANY_B)
        response = client.post("/api/users/", json=payload, headers=admin_headers)
        assert response.status_code == 201
        assert response.get_json()["data"]["company_id"] == COMPANY_B

    @pytest.mark.parametrize("method,path,payload", [
        ("put", "/api/users/42", {"first_name": "Nope"}),
        ("put", "/api/users/42/password", {"new_password": _PASSWORD}),
        ("put", "/api/users/42/activate", None),
        ("put", "/api/users/42/deactivate", None),
        ("delete", "/api/users/42", None),
    ])
    def test_cross_tenant_mutations_denied(self, client, mock_repos, monkeypatch, method, path, payload):
        mock_repos.user_repo.get_by_id_for_company.return_value = None
        headers = _scoped_headers(client.application, COMPANY_A)
        response = getattr(client, method)(path, json=payload, headers=headers)
        assert response.status_code in (400, 404)
        assert response.get_json()["message"] == "User not found"
        mock_repos.user_repo.get_by_id_for_company.assert_called_once_with(42, COMPANY_A)

    def test_same_tenant_operations_still_work(self, client, mock_repos, monkeypatch):
        _neutralize_company_repo(monkeypatch)
        target = _make_user(5, COMPANY_A, role="viewer")
        mock_repos.user_repo.get_by_id_for_company.return_value = target
        mock_repos.user_repo.update.return_value = target
        mock_repos.user_repo.delete.return_value = True
        headers = _scoped_headers(client.application, COMPANY_A)

        assert client.get("/api/users/5", headers=headers).status_code == 200
        updated = client.put("/api/users/5", json={"first_name": "Renamed"}, headers=headers)
        assert updated.status_code == 200
        assert updated.get_json()["data"]["first_name"] == "Renamed"
        pw = client.put(
            "/api/users/5/password", json={"new_password": _PASSWORD}, headers=headers
        )
        assert pw.status_code == 200
        assert client.put("/api/users/5/activate", headers=headers).status_code == 200
        assert client.put("/api/users/5/deactivate", headers=headers).status_code == 200
        assert client.delete("/api/users/5", headers=headers).status_code == 200


class TestTenantIsolationList:
    def test_list_scoped_to_actor_company_ignores_client_params(self, client, mock_repos):
        admin = _make_user(1, COMPANY_A, role="admin")
        mock_repos.user_repo.get_by_id.return_value = admin
        mock_repos.user_repo.get_all_by_company.return_value = [
            _make_user(1, COMPANY_A, role="admin"),
            _make_user(2, COMPANY_A, role="viewer"),
        ]
        response = client.get(
            "/api/users/?company_id=%d&company=%d" % (COMPANY_B, COMPANY_B),
            headers=_scoped_headers(client.application, COMPANY_A),
        )
        assert response.status_code == 200
        payload = response.get_json()["data"]
        assert len(payload) == 2
        assert all(u["company_id"] == COMPANY_A for u in payload)
        mock_repos.user_repo.get_all_by_company.assert_called_once_with(COMPANY_A)

    def test_platform_admin_list_returns_empty_system_scope(self, client, mock_repos, admin_headers):
        mock_repos.user_repo.get_by_id.return_value = _make_user(1, None, role="admin")
        response = client.get("/api/users/?company_id=20", headers=admin_headers)
        assert response.status_code == 200
        assert response.get_json()["data"] == []


class TestTenantIsolationBypass:
    def test_non_integer_user_id_rejected(self, client, mock_repos):
        response = client.get(
            "/api/users/not-an-int", headers=_scoped_headers(client.application, COMPANY_A)
        )
        assert response.status_code == 404

    def test_malformed_company_id_in_update_rejected(self, client, mock_repos):
        mock_repos.user_repo.get_by_id_for_company.return_value = _make_user(5, COMPANY_A)
        response = client.put(
            "/api/users/5",
            json={"company_id": "abc"},
            headers=_scoped_headers(client.application, COMPANY_A),
        )
        assert response.status_code == 400
        assert "integer" in response.get_json()["message"]

    def test_scoped_actor_cannot_downgrade_to_platform_by_null_company(self, client, mock_repos, monkeypatch):
        _neutralize_company_repo(monkeypatch)
        mock_repos.user_repo.exists_by_username.return_value = False
        mock_repos.user_repo.exists_by_email.return_value = False
        mock_repos.user_repo.create.return_value = _make_user(99, COMPANY_A)
        response = client.post(
            "/api/users/",
            json=dict(_GOOD_CREATE, company_id=None, username="nulco", email="nulco@example.com"),
            headers=_scoped_headers(client.application, COMPANY_A),
        )
        assert response.status_code == 201
        assert response.get_json()["data"]["company_id"] == COMPANY_A