"""CORS regression tests.

Verifies that the frontend origins served outside the old Vite defaults
are allowed by the backend CORS middleware, and that responses always
carry the CORS headers — including error responses and preflight.
"""

def _cors_headers(response):
    return {
        key.lower(): value
        for key, value in response.headers.items()
        if key.lower().startswith("access-control-")
    }


def test_preflight_allowed_origin_gets_cors_headers(client):
    for origin in ("http://localhost:8899", "http://127.0.0.1:8899", "http://0.0.0.0:8899"):
        response = client.options(
            "/api/auth/login",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        assert response.status_code == 200
        headers = _cors_headers(response)
        assert headers["access-control-allow-origin"] == origin
        assert "Origin" in response.headers.get("Vary", "")
        assert headers["access-control-allow-credentials"] == "true"
        assert "POST" in headers["access-control-allow-methods"]
        assert "authorization" in headers["access-control-allow-headers"].lower()


def test_login_error_response_includes_cors_for_allowed_origin(client, mock_repos):
    mock_repos.user_repo.get_by_email.return_value = None
    response = client.post(
        "/api/auth/login",
        headers={"Origin": "http://localhost:8899"},
        json={"email": "admin@test.local", "password": "wrong-password"},
    )
    assert response.status_code in (400, 401)
    headers = _cors_headers(response)
    assert headers["access-control-allow-origin"] == "http://localhost:8899"
    assert headers["access-control-allow-credentials"] == "true"


def test_health_response_includes_cors_headers(client):
    response = client.get("/api/health", headers={"Origin": "http://localhost:8899"})
    assert response.status_code == 200
    headers = _cors_headers(response)
    assert headers["access-control-allow-origin"] == "http://localhost:8899"


def test_preflight_for_origin_not_in_allowlist_has_no_allow_origin(client):
    response = client.options(
        "/api/auth/login",
        headers={
            "Origin": "http://evil.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert "access-control-allow-origin" not in _cors_headers(response)


def test_actual_response_for_disallowed_origin_has_no_allow_origin(client, mock_repos):
    mock_repos.user_repo.get_by_email.return_value = None
    response = client.post(
        "/api/auth/login",
        headers={"Origin": "http://evil.example"},
        json={"email": "admin@test.local", "password": "wrong-password"},
    )
    assert response.status_code in (400, 401)
    assert "access-control-allow-origin" not in _cors_headers(response)