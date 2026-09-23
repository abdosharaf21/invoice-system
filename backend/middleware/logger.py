"""Request correlation and application logging middleware.

Provides a per-request correlation ID (``X-Request-Id``) that is attached
to the current request and echoed back on every response header so server
logs and client responses can be correlated.

A client-supplied id is honoured only when it is a short, safe token
(alphanumeric/dot/dash, max 64 chars); anything else is replaced by a
freshly generated UUID so user-controlled values can never inject log
content or bloat the log stream.

The logging root is configured with a context-aware formatter plus filter
that append the correlation id, the acting user id and role to every record
emitted inside a request. The values come from Flask's request-scoped ``g``
object, so concurrent requests never share correlation context and records
produced outside a request context degrade to an empty context instead of
crashing.
"""

import logging
import re
import uuid

from flask import Request, Response, g, request

DEFAULT_LOG_LEVEL = logging.INFO
REQUEST_ID_HEADER = "X-Request-Id"
_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"

_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-]{0,63}$")

logger = logging.getLogger(__name__)


class ContextFilter(logging.Filter):
    """Attach request/user context to every log record when available.

    Reads the correlation id, acting user id and role from Flask's ``g``
    request context. Outside a request context every field degrades to
    ``None``; the filter never raises, so background and startup logging
    keeps working unchanged.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _gattr("request_id")
        record.user_id = _gattr("user_id")
        record.user_role = _gattr("user_role")
        return True


class ObservabilityFormatter(logging.Formatter):
    """Human-readable formatter that appends correlation context fields.

    A record emitted inside a request is rendered as::

        <asctime> <LEVEL> <logger> <message> [request_id=.. user_id=.. role=..]

    The bracketed suffix only lists fields that are actually present, so the
    output stays stable across background jobs and library loggers.
    """

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        context = []
        request_id = getattr(record, "request_id", None)
        user_id = getattr(record, "user_id", None)
        user_role = getattr(record, "user_role", None)
        if request_id:
            context.append(f"request_id={request_id}")
        if user_id is not None:
            context.append(f"user_id={user_id}")
        if user_role:
            context.append(f"role={user_role}")
        if not context:
            return base
        return f"{base} [{', '.join(context)}]"


def configure_logging(level: int = DEFAULT_LOG_LEVEL) -> None:
    """Configure the root logger with a context-enriched handler.

    Idempotent: existing handlers (e.g. from ``logging.basicConfig``) get
    their formatter refreshed and the context filter attached; no duplicate
    handler is created.

    Args:
        level: Root log level (defaults to INFO).
    """
    root = logging.getLogger()
    root.setLevel(level)

    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(ObservabilityFormatter(_LOG_FORMAT))
        handler.addFilter(ContextFilter())
        root.addHandler(handler)
        return

    for handler in root.handlers:
        if getattr(handler, "_eia_observability_formatter", False):
            continue
        handler.setFormatter(ObservabilityFormatter(_LOG_FORMAT))
        if not any(isinstance(f, ContextFilter) for f in handler.filters):
            handler.addFilter(ContextFilter())


def new_request_id(request: Request) -> str:
    """Resolve the correlation ID for the current request.

    Accepts a client-supplied ``X-Request-Id`` only when it matches the
    strict safe-token pattern; otherwise a fresh UUID is generated. The
    chosen value is stored on ``g`` for the lifetime of the request.

    Args:
        request: The incoming Flask request.

    Returns:
        The correlation id bound to the request.
    """
    supplied = (request.headers.get(REQUEST_ID_HEADER) or "").strip()
    if supplied and _SAFE_REQUEST_ID.fullmatch(supplied):
        request_id = supplied
    else:
        request_id = uuid.uuid4().hex
    g.request_id = request_id
    return request_id


def get_request_id() -> str:
    """Return the current request correlation ID, if any."""
    try:
        return getattr(g, "request_id", "")
    except RuntimeError:
        return ""


def log_request(request: Request) -> None:
    """Log incoming request details.

    Records method, path (no query string), and a client identifier. The
    correlation id and user context are appended by the formatter.
    """
    logger.info(
        "Incoming request: %s %s client=%s",
        request.method,
        request.path,
        _client_ip(),
    )


def log_response(response: Response, duration: float) -> None:
    """Log outgoing response details.

    Args:
        response: The response being returned to the client.
        duration: Request duration in seconds.
    """
    logger.info(
        "Response: %s %s status=%s duration=%.4fs",
        request.method,
        request.path,
        response.status_code,
        duration,
    )


def log_error(error: Exception) -> None:
    """Log error details with the full stack trace."""
    logger.error(
        "Error: %s - %s",
        type(error).__name__,
        str(error),
        exc_info=True,
    )


def _client_ip() -> str:
    """Return the client identifier, preferring the proxy-declared IP."""
    try:
        return request.headers.get("X-Real-IP") or request.remote_addr or "unknown"
    except RuntimeError:
        return "unknown"


def _gattr(name: str):
    """Read an attribute from Flask's ``g`` without raising outside a
    request context."""
    try:
        return getattr(g, name, None)
    except RuntimeError:
        return None