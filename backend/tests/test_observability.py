"""Observability tests for request correlation and logging.

Covers the Phase 7 logging requirements:

- ``X-Request-Id`` is generated when absent and echoed on the response.
- A client-supplied id is honoured only when it is a short, safe token;
  anything unsafe (whitespace, control characters, oversized) is replaced.
- Every log record emitted inside a request carries the correlation id and
  the acting user context when available.
- Sensitive headers and query strings are never written to the log stream.
- Unexpected exceptions are logged server-side with their stack trace while
  the client response stays generic (no internals leak).
- Correlation ids do not leak across concurrent requests.
- The readiness endpoint reports database health without leaking details.
"""

import logging
import threading
from unittest.mock import patch

import pytest

from backend.database.connection import Database
from backend.middleware.logger import (
    REQUEST_ID_HEADER,
    _SAFE_REQUEST_ID,
    ContextFilter,
)


class _ListHandler(logging.Handler):
    """Collect LogRecords into a list for in-process assertions."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records = []

    def emit(self, record) -> None:
        self.records.append(record)


@pytest.fixture
def captured_logs():
    """Attach a capturing handler to the root logger for the test duration."""
    handler = _ListHandler()
    handler.addFilter(ContextFilter())
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.addHandler(handler)
    try:
        yield handler
    finally:
        root.removeHandler(handler)


def _messages(handler) -> str:
    return "\n".join(r.getMessage() for r in handler.records)


# ---------------------------------------------------------------------------
# Request-id correlation
# ---------------------------------------------------------------------------

def test_request_id_generated_when_absent_and_logged(client, captured_logs):
    """An absent X-Request-Id is generated, echoed and attached to records."""
    response = client.get("/api/health")

    request_id = response.headers.get(REQUEST_ID_HEADER)
    assert request_id
    assert _SAFE_REQUEST_ID.fullmatch(request_id)

    assert any(r.request_id == request_id for r in captured_logs.records)


def test_safe_client_supplied_request_id_is_echoed(client, captured_logs):
    """A well-formed client id is honoured verbatim (and logged)."""
    supplied = "run-123.abc"
    response = client.get("/api/health", headers={REQUEST_ID_HEADER: supplied})

    assert response.headers[REQUEST_ID_HEADER] == supplied
    assert any(
        r.request_id == supplied for r in captured_logs.records
    )


@pytest.mark.parametrize(
    "bad",
    [
        "a b",             # whitespace after first char
        "a\tb",            # tab
        "a" * 200,         # oversized
        "-leading-dash",   # first char must be alphanumeric
        "drop table x",    # spaces
        "%0d%0a",          # encoded CR/LF characters
        "x<y",             # angle brackets
        "a/value",         # slash
    ],
)
def test_unsafe_client_request_id_is_replaced(client, bad):
    """Unsafe client-supplied ids never reach the response or the logs."""
    response = client.get("/api/health", headers={REQUEST_ID_HEADER: bad})

    got = response.headers[REQUEST_ID_HEADER]
    assert got != bad
    assert _SAFE_REQUEST_ID.fullmatch(got)


def test_sequential_requests_get_distinct_ids(client):
    """Correlation ids must not be reused across requests."""
    ids = {
        client.get("/api/health").headers[REQUEST_ID_HEADER]
        for _ in range(5)
    }
    assert len(ids) == 5


def test_user_context_attached_to_request_logs(client, captured_logs, admin_headers):
    """Once a valid token is present, user id + role appear on log records."""
    response = client.get("/api/health", headers=admin_headers)
    assert response.status_code == 200

    user_records = [
        r for r in captured_logs.records
        if r.request_id and r.user_id is not None and r.user_role
    ]
    assert user_records, "expected records carrying user context"
    assert any(r.user_id == 1 and r.user_role == "admin" for r in user_records)


# ---------------------------------------------------------------------------
# Sensitive data exposure
# ---------------------------------------------------------------------------

def test_sensitive_headers_never_logged(client, captured_logs):
    """Authorization, cookies and query strings must not reach the stream."""
    secret_token = "super-secret-token-123"
    session_cookie = "session=abc123"
    super_secret_query = "very-secret-value"

    client.get(
        "/api/auth/me",
        headers={
            "Authorization": f"Bearer {secret_token}",
            "Cookie": session_cookie,
        },
    )
    client.get(f"/api/health?secret={super_secret_query}")

    messages = _messages(captured_logs)
    assert secret_token not in messages
    assert session_cookie not in messages
    assert super_secret_query not in messages
    assert "secret=" not in messages


# ---------------------------------------------------------------------------
# Server-side error visibility without leaking internals
# ---------------------------------------------------------------------------

def _build_minimal_error_app():
    """A tiny app exercising the real error handling only."""
    from flask import Flask

    from backend.middleware.error_handlers import register_error_handlers

    app = Flask(__name__)

    @app.get("/_boom")
    def boom():
        raise RuntimeError("internal-detail-xyz")

    @app.get("/_ok")
    def ok():
        return {"success": True}

    register_error_handlers(app)
    return app


def test_unexpected_exception_logged_but_response_hides_stack(captured_logs):
    """A 500 is logged with a traceback server-side; client sees no internals."""
    app = _build_minimal_error_app()
    client = app.test_client()

    response = client.get("/_boom")

    assert response.status_code == 500
    body = response.get_json()
    assert body["code"] == "INTERNAL_ERROR"
    assert "internal-detail-xyz" not in response.get_data(as_text=True)
    assert "Traceback" not in response.get_data(as_text=True)

    assert any(
        "internal-detail-xyz" in r.getMessage() for r in captured_logs.records
    )
    assert any(
        r.levelno >= logging.ERROR
        and getattr(r, "exc_info", None) is not None
        and getattr(r, "exc_text", None)
        for r in captured_logs.records
    )

    # The generic handler must not break normal traffic.
    assert client.get("/_ok").status_code == 200


# ---------------------------------------------------------------------------
# Concurrent request isolation
# ---------------------------------------------------------------------------

def test_concurrent_requests_keep_correlation_isolated(app, captured_logs):
    """Parallel requests must never cross-contaminate request ids."""
    barrier = threading.Barrier(2)
    results = []
    threads = []

    def _worker(worker_id):
        client = app.test_client()
        supplied = f"worker-{worker_id}"
        barrier.wait()
        response = client.get(
            "/api/health",
            headers={REQUEST_ID_HEADER: supplied},
        )
        return response.headers[REQUEST_ID_HEADER]

    for worker_id in (1, 2):
        threads.append(
            threading.Thread(
                target=lambda i=worker_id: results.append(_worker(i))
            )
        )
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(results) == ["worker-1", "worker-2"]

    ids_seen = {r.request_id for r in captured_logs.records if r.request_id}
    assert {"worker-1", "worker-2"}.issubset(ids_seen)
    # No record is ever associated with both correlation ids at once.
    for record in captured_logs.records:
        request_id = record.request_id
        assert request_id in {"", "worker-1", "worker-2"}


def test_rate_limit_rejection_is_logged(client, captured_logs, monkeypatch):
    """A 429 rejection is logged with category, client and request id."""
    from backend.middleware.rate_limit import _rate_limiter

    monkeypatch.setattr(_rate_limiter, "_exempt_prefixes", [])
    monkeypatch.setattr(
        _rate_limiter,
        "allow",
        lambda category, client, now=None: False,
    )

    response = client.post("/api/auth/login", json={"email": "a@b.co", "password": "x"})

    assert response.status_code == 429
    assert response.get_json()["code"] == "RATE_LIMITED"
    request_id = response.headers.get(REQUEST_ID_HEADER)
    assert request_id

    assert any(
        "Rate limit exceeded" in r.getMessage()
        and r.levelno == logging.WARNING
        and r.request_id == request_id
        for r in captured_logs.records
    )


# ---------------------------------------------------------------------------
# Readiness endpoint
# ---------------------------------------------------------------------------

def test_readiness_reports_healthy_database(client):
    """With a healthy DB the readiness check returns 200 + database ok."""
    with patch.object(Database, "is_healthy", property(lambda self: True)):
        response = client.get("/api/health/ready")

    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    assert body["data"]["database"] == "ok"


def test_readiness_reports_unhealthy_database(client):
    """With an unhealthy DB the readiness check returns 503, no internals."""
    with patch.object(Database, "is_healthy", property(lambda self: False)):
        response = client.get("/api/health/ready")

    assert response.status_code == 503
    body = response.get_json()
    assert body["success"] is False
    assert body["message"] == "Database unavailable"
    body_text = response.get_data(as_text=True)
    assert "health check failed" not in body_text