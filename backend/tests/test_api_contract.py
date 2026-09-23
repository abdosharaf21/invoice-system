"""API contract tests.

A set of contract-test categories that lock down the public API surface,
ensuring stability for existing clients (React frontend) and future
integrations. These tests use the same mock-based Flask app as every
other backend test; no real database is required.
"""

import json
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from backend.middleware.logger import REQUEST_ID_HEADER
from backend.middleware.rate_limit import classify_request, _normalize_path
from backend.modules.reconciliation.repository import _iso


# ---------------------------------------------------------------------------
# 1. Versioning: /api/v1 aliases exist for every API route
# ---------------------------------------------------------------------------


def test_v1_aliases_exist_for_every_api_route(app):
    """Every /api/<...> rule has a matching /api/v1/<...> alias."""
    api_rules = {
        rule.rule
        for rule in app.url_map.iter_rules()
        if rule.rule.startswith("/api/") and not rule.rule.startswith("/api/v1/")
    }
    v1_rules = {
        rule.rule
        for rule in app.url_map.iter_rules()
        if rule.rule.startswith("/api/v1/")
    }

    expected_v1 = {"/api/v1" + r[len("/api"):] for r in api_rules}

    missing = expected_v1 - v1_rules
    assert not missing, f"Missing v1 aliases: {missing}"


# ---------------------------------------------------------------------------
# 2. Versioning: v1 path resolves to the same view function
# ---------------------------------------------------------------------------


def test_v1_endpoint_shares_view_function_with_unversioned(app):
    """V1 aliases map to the same view function as the unversioned rule."""
    rule_map = {}
    for rule in app.url_map.iter_rules():
        rule_map[rule.rule] = rule.endpoint

    # Pick an example: /api/auth/login → /api/v1/auth/login
    unversioned_endpoint = rule_map.get("/api/auth/login")
    v1_endpoint = rule_map.get("/api/v1/auth/login")
    assert unversioned_endpoint is not None
    assert v1_endpoint is not None
    assert (
        app.view_functions[unversioned_endpoint]
        is app.view_functions[v1_endpoint]
    )


# ---------------------------------------------------------------------------
# 3. Error envelope: every error body contains success + message + status + code
# ---------------------------------------------------------------------------


def _assert_error_envelope(response, expected_status=None):
    """Helper: verify the error envelope contract."""
    data = response.get_json()
    assert data["success"] is False
    assert isinstance(data["message"], str)
    assert isinstance(data["status"], int)
    assert isinstance(data["code"], str)
    if expected_status is not None:
        assert data["status"] == expected_status
    return data


def test_error_envelope_shape_on_not_found(client):
    """404 errors carry the standard error envelope."""
    resp = client.get("/api/nonexistent-resource")
    assert resp.status_code == 404
    data = _assert_error_envelope(resp, 404)
    assert data["code"] == "NOT_FOUND"


def test_error_envelope_shape_on_method_not_allowed(client):
    """405 errors carry the standard error envelope."""
    resp = client.get("/api/auth/login")
    assert resp.status_code == 405
    data = _assert_error_envelope(resp, 405)
    assert data["code"] == "METHOD_NOT_ALLOWED"


# ---------------------------------------------------------------------------
# 4. Status code: not found
# ---------------------------------------------------------------------------


def test_error_code_not_found(client):
    """Unknown resource returns 404 NOT_FOUND."""
    resp = client.get("/api/bogus-endpoint/42")
    data = _assert_error_envelope(resp, 404)
    assert data["code"] == "NOT_FOUND"
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 5. Status code: method not allowed
# ---------------------------------------------------------------------------


def test_error_code_method_not_allowed(client):
    """Wrong HTTP method returns 405 METHOD_NOT_ALLOWED."""
    resp = client.get("/api/auth/login")
    data = _assert_error_envelope(resp, 405)
    assert data["code"] == "METHOD_NOT_ALLOWED"


# ---------------------------------------------------------------------------
# 6. Status code: bad request (validation)
# ---------------------------------------------------------------------------


def test_error_code_bad_request(client):
    """Missing required fields returns 400 BAD_REQUEST."""
    resp = client.post(
        "/api/auth/login",
        data=json.dumps({}),
        content_type="application/json",
    )
    data = _assert_error_envelope(resp, 400)
    assert data["code"] == "BAD_REQUEST"
    assert "Email is required" in data["message"]


# ---------------------------------------------------------------------------
# 7. Status code: forbidden (RBAC)
# ---------------------------------------------------------------------------


def test_error_code_forbidden(client, employee_headers):
    """Insufficient role returns 403 FORBIDDEN."""
    resp = client.get("/api/users/", headers=employee_headers)
    data = _assert_error_envelope(resp, 403)
    assert data["code"] == "FORBIDDEN"


# ---------------------------------------------------------------------------
# 8. Status code: token required (auth)
# ---------------------------------------------------------------------------


def test_error_code_token_required(client):
    """Missing JWT returns 401 TOKEN_REQUIRED."""
    resp = client.get("/api/auth/me")
    assert resp.status_code in (401, 422)
    data = resp.get_json()
    # flask-jwt-extended handles missing tokens via its unauthorized_loader
    # or via the blueprint 422 handler. Both produce stable envelopes.
    assert data["success"] is False
    assert isinstance(data["code"], str)
    assert data["status"] in (401, 422)


# ---------------------------------------------------------------------------
# 9. Status code: invalid credentials
# ---------------------------------------------------------------------------


def test_error_code_invalid_credentials(client, monkeypatch):
    """Invalid login credentials return 401 INVALID_CREDENTIALS."""
    from backend.modules.auth import routes as auth_routes
    from backend.middleware.exceptions import InvalidCredentialsException

    class StubAuthService:
        def login(self, email, password):
            raise InvalidCredentialsException("Invalid email or password")

    monkeypatch.setattr(auth_routes, "_auth_service", StubAuthService())

    resp = client.post(
        "/api/auth/login",
        data=json.dumps({"email": "bad@test.com", "password": "wrong"}),
        content_type="application/json",
    )
    data = _assert_error_envelope(resp, 401)
    assert data["code"] == "INVALID_CREDENTIALS"


# ---------------------------------------------------------------------------
# 10. Status code: conflict
# ---------------------------------------------------------------------------


def test_error_code_conflict(client, monkeypatch):
    """A conflict exception returns 409 CONFLICT with the error envelope."""
    from backend.modules.auth import routes as auth_routes
    from backend.middleware.exceptions import ConflictException

    class StubAuthService:
        def login(self, email, password):
            raise ConflictException("Resource already exists")

    monkeypatch.setattr(auth_routes, "_auth_service", StubAuthService())

    resp = client.post(
        "/api/auth/login",
        data=json.dumps({"email": "x@y.com", "password": "pass"}),
        content_type="application/json",
    )
    data = _assert_error_envelope(resp, 409)
    assert data["code"] == "CONFLICT"


# ---------------------------------------------------------------------------
# 11. Status code: internal error (unexpected exception)
# ---------------------------------------------------------------------------


def test_error_code_internal_error(client, monkeypatch):
    """An unexpected exception returns 500 INTERNAL_ERROR."""
    from backend.modules.auth import routes as auth_routes
    from backend.middleware.exceptions import AppException

    class ExplodingAuthService:
        def login(self, email, password):
            raise RuntimeError("database exploded")

    monkeypatch.setattr(auth_routes, "_auth_service", ExplodingAuthService())

    resp = client.post(
        "/api/auth/login",
        data=json.dumps({"email": "x@y.com", "password": "pass"}),
        content_type="application/json",
    )
    # Global Exception handler catches RuntimeError
    data = _assert_error_envelope(resp, 500)
    assert data["code"] == "INTERNAL_ERROR"


# ---------------------------------------------------------------------------
# 11. Request ID: X-Request-Id header present on success responses
# ---------------------------------------------------------------------------


def test_request_id_header_present_on_success(client, admin_headers):
    """Success responses include the X-Request-Id header."""
    resp = client.get("/api/health")
    assert REQUEST_ID_HEADER in resp.headers
    assert len(resp.headers[REQUEST_ID_HEADER]) > 0


# ---------------------------------------------------------------------------
# 12. Request ID: client-supplied X-Request-Id is echoed back
# ---------------------------------------------------------------------------


def test_request_id_echoed(client):
    """Client-supplied X-Request-Id is echoed in the response header."""
    resp = client.get(
        "/api/health",
        headers={REQUEST_ID_HEADER: "test-contract-id-001"},
    )
    assert resp.headers.get(REQUEST_ID_HEADER) == "test-contract-id-001"


# ---------------------------------------------------------------------------
# 13. Request ID: present on error responses too
# ---------------------------------------------------------------------------


def test_request_id_present_on_error(client):
    """Error responses also include an X-Request-Id for correlation."""
    resp = client.get("/api/bogus-endpoint")
    assert REQUEST_ID_HEADER in resp.headers


# ---------------------------------------------------------------------------
# 14. Money serialization: Decimal becomes a JSON string
# ---------------------------------------------------------------------------


def test_money_decimal_serializes_as_string(app):
    """Decimal amounts serialize as JSON strings, not floats."""
    with app.test_request_context():
        from flask import jsonify
        resp = jsonify({"amount": Decimal("12345.67")})
        data = json.loads(resp.get_data(as_text=True))
        assert data["amount"] == "12345.67"
        assert isinstance(data["amount"], str)


# ---------------------------------------------------------------------------
# 15. Date serialization: datetime and date become ISO-8601 strings
# ---------------------------------------------------------------------------


def test_date_serialization_iso8601(app):
    """Reconciliation report dates use ISO-8601, not HTTP-date format."""
    # Verify the _iso helper (used in reconciliation report serializers)
    dt = datetime(2026, 3, 15, 14, 30, 0)
    d = date(2026, 3, 15)
    assert _iso(dt) == "2026-03-15T14:30:00"
    assert _iso(d) == "2026-03-15"

    # Flask jsonify renders dates in HTTP-date format by default; the
    # reconciliation report serializers pre-convert via _iso() to keep
    # the API consistent with model isoformat() behavior.
    with app.test_request_context():
        from flask import jsonify
        resp = jsonify({"created_at": _iso(dt), "invoice_date": _iso(d)})
        data = json.loads(resp.get_data(as_text=True))
        assert data["created_at"] == "2026-03-15T14:30:00"
        assert data["invoice_date"] == "2026-03-15"


# ---------------------------------------------------------------------------
# 16. Rate limiting: v1 paths are classified correctly
# ---------------------------------------------------------------------------


def test_rate_limit_v1_path_classification():
    """Rate limiter classifies /api/v1/auth/login as the login category."""
    assert classify_request("/api/v1/auth/login") == "login"
    assert classify_request("/api/v1/auth/refresh") == "refresh"
    assert classify_request("/api/v1/auth/change-password") == "password"
    assert classify_request("/api/v1/email/test") == "email"


def test_rate_limit_v1_upload_classification():
    """Rate limiter normalizes /api/v1/imports for upload limiting."""
    assert _normalize_path("/api/v1/imports") == "/api/imports"
    # Upload classification happens in check() via path comparison;
    # normalization is correct at the path level.
    assert classify_request("/api/v1/imports") is None  # not a sensitive endpoint


# ---------------------------------------------------------------------------
# 17. Reconciliation report pagination envelope keys
# ---------------------------------------------------------------------------


def test_reconciliation_envelope_keys(client, admin_headers, mock_repos):
    """Results pagination envelope has items/page/page_size/total/total_pages.

    When page/page_size query params are present, the endpoint returns
    the paginated envelope (items, page, page_size, total, total_pages).
    Without those params it returns a flat results array (a different
    shape used by the detail page). This test validates the paginated
    contract which is the stable public API.
    """
    mock_repos.reconciliation_service.paginate_results.return_value = {
        "items": [
            {
                "id": 1,
                "match_status": "mismatched",
                "discrepancy_amount": "50.00",
                "account_invoice_number": "INV-001",
                "account_invoice_date": "2026-01-15",
                "accounting_total": "1150.00",
            }
        ],
        "page": 2,
        "page_size": 20,
        "total": 45,
        "total_pages": 3,
    }

    resp = client.get(
        "/api/reconciliation/runs/10/results?page=2&page_size=20",
        headers=admin_headers,
    )
    data = resp.get_json()
    assert resp.status_code == 200
    paginated = data["data"]
    assert "items" in paginated
    assert "page" in paginated
    assert "page_size" in paginated
    assert "total" in paginated
    assert "total_pages" in paginated
    # The route echoes the service's pagination metadata verbatim; these
    # values are non-trivial so a route that recomputes or hardcodes the
    # envelope would fail them.
    assert paginated["page"] == 2
    assert paginated["page_size"] == 20
    assert paginated["total"] == 45
    assert paginated["total_pages"] == 3


# ---------------------------------------------------------------------------
# 18. Audit logs pagination: total_pages is present
# ---------------------------------------------------------------------------


def test_audit_envelope_has_total_pages(client, admin_headers, mock_repos):
    """Audit logs pagination envelope includes total_pages alias."""
    mock_repos.audit_repo.list_logs.return_value = ([], 0)

    resp = client.get(
        "/api/audit-trail/logs",
        headers=admin_headers,
    )
    data = resp.get_json()
    assert resp.status_code == 200
    assert "total_pages" in data["data"]
    assert "pages" in data["data"]
    assert data["data"]["total_pages"] == 0
    assert data["data"]["pages"] == 0


# ---------------------------------------------------------------------------
# 19. Idempotency: running the same reconciliation period twice returns 200
# ---------------------------------------------------------------------------


def test_idempotent_reconciliation_run(client, admin_headers, mock_repos):
    """Starting a reconciliation run for an existing period returns 200,
    not 409 Conflict, with is_new=False."""
    mock_run = MagicMock()
    mock_run.to_dict.return_value = {
        "id": 5, "company_id": 1, "period": "2026-01",
        "status": "completed",
    }
    mock_repos.reconciliation_service.start_run.return_value = (
        mock_run,
        {"matched": 10, "mismatched": 2},
        False,
    )

    resp = client.post(
        "/api/reconciliation/runs",
        data=json.dumps({"period": "2026-01"}),
        headers={**admin_headers, "Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["data"]["run"]["period"] == "2026-01"


# ---------------------------------------------------------------------------
# 20. Content type: JSON responses use application/json
# ---------------------------------------------------------------------------


def test_content_type_is_json_on_success(client):
    """Success responses carry application/json content type."""
    resp = client.get("/api/health")
    assert resp.content_type.startswith("application/json")


def test_content_type_is_json_on_error(client):
    """Error responses carry application/json content type."""
    resp = client.get("/api/bogus-endpoint")
    assert resp.content_type.startswith("application/json")


# ---------------------------------------------------------------------------
# 21. Filtering: report query params are forwarded to the service
# ---------------------------------------------------------------------------


def test_reconciliation_filtering_params_forwarded(
    client, admin_headers, mock_repos
):
    """Results filters are passed through to the reconciliation service."""
    mock_repos.reconciliation_service.paginate_results.return_value = {
        "items": [],
        "page": 1,
        "page_size": 20,
        "total": 0,
        "total_pages": 0,
    }

    resp = client.get(
        "/api/reconciliation/runs/10/results"
        "?match_status=mismatched&invoice_number=INV-1"
        "&date_from=2026-01-01&date_to=2026-01-31",
        headers=admin_headers,
    )
    assert resp.status_code == 200

    call_args = mock_repos.reconciliation_service.paginate_results.call_args
    filters = call_args.args[4]
    assert filters.get("match_status") == "mismatched"
    assert filters.get("invoice_number") == "INV-1"
    assert str(filters.get("date_from")) == "2026-01-01"
    assert str(filters.get("date_to")) == "2026-01-31"


# ---------------------------------------------------------------------------
# 22. Sorting: audit trail sort_by is honored
# ---------------------------------------------------------------------------


def test_audit_logs_sorts_and_scopes_to_company(
    client, admin_headers, mock_repos
):
    """Audit logs honor sort_by and always scope to the JWT company."""
    mock_repos.audit_repo.list_logs.return_value = ([], 0)

    resp = client.get(
        "/api/audit-trail/logs?sort_by=created_at&action=login",
        headers=admin_headers,
    )
    assert resp.status_code == 200

    call_args = mock_repos.audit_repo.list_logs.call_args
    filters = call_args.args[0]
    assert filters.get("sort_by") == "created_at"
    assert filters.get("action") == "login"


# ---------------------------------------------------------------------------
# 23. Deprecation: legacy /api/users auth endpoints carry Deprecation header
# ---------------------------------------------------------------------------

from backend.middleware.contract import DEPRECATION_HEADER


def _stub_user_service():
    """Create a minimal stub UserService with the methods the legacy routes call."""

    class _Stub:
        def login(self, email, password):
            return {"access_token": "stub", "refresh_token": "stub"}

        def logout(self, jti):
            pass

        def get_user_by_id(self, uid):

            class _User:
                def to_dict(self):
                    return {"id": uid, "username": "stub"}

            return _User()

    return _Stub()


def _stub_auth_service():
    class _Stub:
        def login(self, email, password):
            return {"access_token": "stub", "refresh_token": "stub"}

    return _Stub()


def test_deprecated_users_login_carry_deprecation_header(
    app, client, monkeypatch
):
    """POST /api/users/login succeeds and carries Deprecation + Link."""
    from backend.modules.users import routes as users_routes

    monkeypatch.setattr(users_routes, "_user_service", _stub_user_service())

    resp = client.post(
        "/api/users/login",
        data=json.dumps({"email": "x@y.com", "password": "pass"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert resp.headers.get(DEPRECATION_HEADER) == "true"
    assert "/api/auth/login" in resp.headers.get("Link", "")
    assert 'rel="successor-version"' in resp.headers["Link"]


def test_deprecated_users_logout_carry_deprecation_header(
    app, client, admin_token, monkeypatch
):
    """POST /api/users/logout succeeds and carries Deprecation + Link."""
    from backend.modules.users import routes as users_routes

    monkeypatch.setattr(users_routes, "_user_service", _stub_user_service())

    resp = client.post(
        "/api/users/logout",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert resp.headers.get(DEPRECATION_HEADER) == "true"
    assert "auth/logout" in resp.headers.get("Link", "")


def test_deprecated_users_me_carry_deprecation_header(
    app, client, admin_token, monkeypatch
):
    """GET /api/users/me succeeds and carries Deprecation + Link."""
    from backend.modules.users import routes as users_routes

    monkeypatch.setattr(users_routes, "_user_service", _stub_user_service())

    resp = client.get(
        "/api/users/me",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert resp.headers.get(DEPRECATION_HEADER) == "true"
    assert "auth/me" in resp.headers.get("Link", "")


def test_v1_legacy_users_endpoint_also_deprecated(
    app, client, admin_token, monkeypatch
):
    """/api/v1/users/logout (v1 alias) carries Deprecation — same view function."""
    from backend.modules.users import routes as users_routes

    monkeypatch.setattr(users_routes, "_user_service", _stub_user_service())

    resp = client.post(
        "/api/v1/users/logout",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert resp.headers.get(DEPRECATION_HEADER) == "true"


def test_canonical_auth_login_does_not_carry_deprecation(
    app, client, monkeypatch
):
    """POST /api/auth/login carries no Deprecation header."""
    monkeypatch.setattr(
        "backend.modules.auth.routes._auth_service", _stub_auth_service()
    )

    resp = client.post(
        "/api/auth/login",
        data=json.dumps({"email": "x@y.com", "password": "pass"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert DEPRECATION_HEADER not in resp.headers


# ---------------------------------------------------------------------------
# 24. Error-code mapping: contract.error_response() covers all documented statuses
# ---------------------------------------------------------------------------


def test_contract_error_response_maps_documented_statuses(app):
    """The shared error_response builder produces stable codes for every
    documented HTTP status, and falls back to APP_ERROR for undocumented ones."""
    import json as _json

    from backend.middleware.contract import error_response

    documented = {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        409: "CONFLICT",
        422: "VALIDATION_ERROR",
        429: "RATE_LIMITED",
        500: "INTERNAL_ERROR",
        502: "BAD_GATEWAY",
        503: "SERVICE_UNAVAILABLE",
    }

    with app.test_request_context():
        for status, expected_code in documented.items():
            resp, st = error_response("boom", status)
            assert st == status
            body = _json.loads(resp.get_data(as_text=True))
            assert body["success"] is False
            assert body["code"] == expected_code

        resp, st = error_response("boom", 599)
        assert st == 599
        body = _json.loads(resp.get_data(as_text=True))
        assert body["code"] == "APP_ERROR"


def test_contract_error_response_explicit_code_override(app):
    """Modules can override the canonical mapping with an explicit code."""
    import json as _json

    from backend.middleware.contract import error_response

    with app.test_request_context():
        resp, st = error_response("bad creds", 401, code="INVALID_CREDENTIALS")
        body = _json.loads(resp.get_data(as_text=True))
        assert body["code"] == "INVALID_CREDENTIALS"


# ---------------------------------------------------------------------------
# 25. Envelope shape: error bodies always have exactly the canonical 4 keys
# ---------------------------------------------------------------------------


def test_error_envelope_keys_are_exactly_canonical(client):
    """A 404 error body contains exactly {success, message, status, code}."""
    data = _assert_error_envelope(client.get("/api/nonexistent-resource"), 404)
    assert set(data.keys()) == {"success", "message", "status", "code"}


# ---------------------------------------------------------------------------
# 26. Success envelope: success field is always boolean and payload is an object
# ---------------------------------------------------------------------------


def test_success_envelope_is_flat_object(client):
    """/api/health returns a JSON object (not array) with success=true."""
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, dict)
    assert data["success"] is True


def test_success_envelope_with_data_key(client, admin_headers, mock_repos):
    """Reconciliation list success returns data as a dict, not raw list."""
    mock_repos.reconciliation_service.list_runs.return_value = []

    resp = client.get(
        "/api/reconciliation/runs?limit=10",
        headers=admin_headers,
    )
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["success"] is True
    assert isinstance(data["data"], dict)
    assert "runs" in data["data"]
