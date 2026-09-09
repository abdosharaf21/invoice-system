"""Request and response logging middleware.

Provides a per-request correlation ID (``X-Request-Id``) that is attached
to `g` at the start of every request and echoed back on the response header
so logs and client responses can be correlated.
"""

import logging
import time
import uuid
from typing import Callable

from flask import Request, Response, g, request


logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-Id"


def new_request_id(request: Request) -> str:
    """Generate a correlation ID for the current request."""
    request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
    g.request_id = request_id
    return request_id


def get_request_id() -> str:
    """Return the current request correlation ID, if any."""
    return getattr(g, "request_id", "")


def log_request(request: Request) -> None:
    """Log incoming request details."""
    request_id = new_request_id(request)
    logger.info(
        "Incoming request: %s %s from %s (request_id=%s)",
        request.method,
        request.url,
        request.remote_addr,
        request_id,
    )


def log_response(response: Response, start_time: float) -> None:
    """Log outgoing response details."""
    duration = time.time() - start_time
    logger.info(
        "Response: %s %s - Status: %s - Duration: %.4fs (request_id=%s)",
        request.method,
        request.url,
        response.status_code,
        duration,
        get_request_id(),
    )


def log_error(error: Exception) -> None:
    """Log error details."""
    logger.error(
        "Error: %s - %s (request_id=%s)",
        type(error).__name__,
        str(error),
        get_request_id(),
        exc_info=True,
    )
