"""Security-header middleware tests (Phase 14 gap G9).

Covers the full configuration matrix of ``build_security_headers`` (base
headers, CSP on/off, HSTS on/off, disabled) plus an HTTP-level assertion
that the production-style app emits CSP when enabled — the toggles that
previous tests only partially exercised.
"""

from types import SimpleNamespace

from backend.middleware.security import (
    BASE_SECURITY_HEADERS,
    HSTS_HEADER,
    add_security_headers,
    build_security_headers,
)


class TestBuildSecurityHeadersMatrix:
    def test_disabled_returns_no_headers(self):
        assert build_security_headers(False, True, "x", True) == {}

    def test_base_headers_without_csp_or_hsts(self):
        headers = build_security_headers(True, False, "csp", False)
        assert headers == BASE_SECURITY_HEADERS
        assert "Content-Security-Policy" not in headers
        assert "Strict-Transport-Security" not in headers

    def test_csp_header_added_when_enabled(self):
        policy = "default-src 'self'"
        headers = build_security_headers(True, True, policy, False)
        assert headers["Content-Security-Policy"] == policy
        assert "Strict-Transport-Security" not in headers

    def test_hsts_header_added_when_enabled(self):
        headers = build_security_headers(True, False, "csp", True)
        assert headers["Strict-Transport-Security"] == HSTS_HEADER
        assert "Content-Security-Policy" not in headers

    def test_csp_and_hsts_together(self):
        headers = build_security_headers(True, True, "default-src 'self'", True)
        assert headers["Content-Security-Policy"] == "default-src 'self'"
        assert headers["Strict-Transport-Security"] == HSTS_HEADER


class TestAddSecurityHeaders:
    def _apply(self, config):
        from flask import Response
        response = add_security_headers(Response(), app=SimpleNamespace(config=config))
        return dict(response.headers)

    def test_app_config_csp_and_hsts_flow_through(self):
        headers = self._apply({
            "SECURITY_HEADERS_ENABLED": True,
            "CSP_ENABLED": True,
            "CSP_POLICY": "default-src 'self'",
            "HSTS_ENABLED": True,
        })
        assert headers["Content-Security-Policy"] == "default-src 'self'"
        assert headers["Strict-Transport-Security"] == HSTS_HEADER
        assert headers["X-Content-Type-Options"] == "nosniff"

    def test_disabled_kill_switch_removes_all(self):
        options = {
            "SECURITY_HEADERS_ENABLED": False,
            "CSP_ENABLED": True,
            "CSP_POLICY": "default-src 'self'",
            "HSTS_ENABLED": True,
        }
        # First pass with the flags ON so the headers are present…
        headers = self._apply({**options, "SECURITY_HEADERS_ENABLED": True})
        assert headers["Content-Security-Policy"] == "default-src 'self'"
        assert headers["Strict-Transport-Security"] == HSTS_HEADER
        # …then OFF; the kill switch must strip them again.
        headers = self._apply(options)
        assert "Content-Security-Policy" not in headers
        assert "Strict-Transport-Security" not in headers
        assert "X-Content-Type-Options" not in headers


class TestHttpSecurityHeaders:
    def test_base_headers_present_on_api_response(self, client):
        response = client.get("/api/health")
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
        assert response.headers["Permissions-Policy"].startswith("camera=()")

    def test_no_store_cache_headers(self, client):
        response = client.get("/api/health")
        assert "no-store" in response.headers["Cache-Control"]
        assert response.headers["Pragma"] == "no-cache"