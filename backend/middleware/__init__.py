"""Middleware package for Flask application."""

from backend.middleware.exceptions import (
    AppException,
    BadRequestException,
    UnauthorizedException,
    ForbiddenException,
    NotFoundException,
    ConflictException,
    ValidationException,
    DatabaseException,
    ServiceUnavailableException
)
from backend.middleware.error_handlers import register_error_handlers
from backend.middleware.logger import (
    log_request,
    log_response,
    log_error,
    get_request_id,
    new_request_id,
    REQUEST_ID_HEADER,
)
from backend.middleware.timing import start_timer, get_request_duration
from backend.middleware.security import register_security_headers, add_security_headers
from backend.middleware.cors import register_cors
from backend.middleware.auth_context import load_user_context, clear_user_context
from backend.middleware.rate_limit import (
    RateLimiter,
    register_rate_limits,
    before_request_rate_limit,
    classify_request,
)

__all__ = [
    "AppException",
    "BadRequestException",
    "UnauthorizedException",
    "ForbiddenException",
    "NotFoundException",
    "ConflictException",
    "ValidationException",
    "DatabaseException",
    "ServiceUnavailableException",
    "register_error_handlers",
    "log_request",
    "log_response",
    "log_error",
    "get_request_id",
    "new_request_id",
    "REQUEST_ID_HEADER",
    "start_timer",
    "get_request_duration",
    "register_security_headers",
    "add_security_headers",
    "register_cors",
    "load_user_context",
    "clear_user_context",
    "RateLimiter",
    "register_rate_limits",
    "before_request_rate_limit",
    "classify_request",
]
