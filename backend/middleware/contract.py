"""Canonical API response contract.

Single source of truth for the stable HTTP envelope used by every module:

* Success::

    { "success": true, "message"?: "optional text", "data"?: <payload> }

* Error::

    { "success": false, "message": "reason", "status": <int>, "code": "CODE" }

The error ``code`` is machine-readable and stable. ``APP_ERROR`` is a
reserved fallback that must only be reachable for an undocumented status; for
every documented status the mapping in ``error_response()`` produces a
specific code (see ``STANDARD_ERROR_CODES``).

Also provides the deprecation-header helpers used by legacy, superseded
endpoints so clients can migrate deterministically instead of guessing.
"""

from flask import jsonify

DEPRECATION_HEADER = "Deprecation"
"""Standard header marking an endpoint as superseded (value ``"true"``)."""

STANDARD_ERROR_CODES = {
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

_MISSING = object()


def success_response(data=_MISSING, message=None, status: int = 200):
    """Build a canonical success response tuple.

    ``data`` is the contract payload field; ``message`` is optional
    human-readable text. Returns ``(Response, status)`` exactly like the
    route modules' existing JSON helpers so no view behavior changes.
    """
    payload = {"success": True}
    if data is not _MISSING:
        payload["data"] = data
    if message is not None:
        payload["message"] = message
    return jsonify(payload), status


def error_response(message: str, status: int = 400, code: str = None):
    """Build a canonical error response tuple.

    Args:
        message: Human-readable error message.
        status: HTTP status code.
        code: Optional explicit machine-readable code. When omitted, the
            standard mapping for ``status`` is used; an undocumented status
            falls back to ``APP_ERROR``.

    Returns:
        A ``(Response, status)`` pair with the stable error envelope.
    """
    resolved = code or STANDARD_ERROR_CODES.get(status, "APP_ERROR")
    return jsonify({
        "success": False,
        "message": message,
        "status": status,
        "code": resolved,
    }), status


def deprecated_response(payload: dict, status: int = 200, successor: str = None):
    """Build a success response that advertises its deprecation.

    Attaches ``Deprecation: true`` (and, when a successor path is supplied,
    a ``Link`` header with ``rel="successor-version"``) so clients can
    migrate from legacy endpoints without guessing.

    Args:
        payload: Body dict for the (still working) response.
        status: HTTP status code.
        successor: Optional absolute-or-API path of the replacement endpoint.

    Returns:
        A ``(Response, status)`` pair carrying the deprecation headers.
    """
    response = jsonify(payload)
    response.headers[DEPRECATION_HEADER] = "true"
    if successor:
        response.headers["Link"] = f'<{successor}>; rel="successor-version"'
    return response, status