"""Role-Based Access Control (RBAC) middleware for Flask routes."""

import logging
from functools import wraps
from typing import Callable

from flask import g, jsonify, request
from flask_jwt_extended import verify_jwt_in_request, get_jwt

logger = logging.getLogger(__name__)


def _deny(message: str):
    """Build and audit a 403 access-denied response.

    Records a security event on the audit trail so denied attempts are
    traceable, then returns the same response contract used before the
    audit trail existed.

    Args:
        message: The permission-denied message to expose to the client.

    Returns:
        A Flask JSON response tuple with status 403 and a stable code.
    """
    from backend.modules.audit_trail.model import AuditLog
    from backend.modules.audit_trail.service import record_security_event

    record_security_event(
        action=AuditLog.ACTION_OTHER,
        resource_type="authorization",
        result=AuditLog.RESULT_FAILURE,
        metadata={"reason": "insufficient_permissions", "message": message},
    )
    logger.warning(
        "Authorization denied user_id=%s role=%s method=%s path=%s message=%s",
        getattr(g, "user_id", None),
        getattr(g, "user_role", None),
        request.method,
        request.path,
        message,
    )
    return jsonify({
        "success": False,
        "message": message,
        "status": 403,
        "code": "FORBIDDEN",
    }), 403


def require_roles(*allowed_roles: str) -> Callable:
    """Decorator to restrict route access by user role.

    Usage:
        @require_roles("admin")
        def admin_only_route():
            pass

        @require_roles("admin", "manager")
        def admin_or_manager_route():
            pass
    """
    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            jwt_data = get_jwt()
            user_role = jwt_data.get("role")

            if user_role not in allowed_roles:
                return _deny("Access denied. Insufficient permissions.")

            return fn(*args, **kwargs)
        return wrapper
    return decorator


def require_admin(fn: Callable) -> Callable:
    """Decorator to restrict route access to admin only."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        verify_jwt_in_request()
        jwt_data = get_jwt()
        user_role = jwt_data.get("role")

        if user_role != "admin":
            return _deny("Access denied. Admin privileges required.")

        return fn(*args, **kwargs)
    return wrapper


def require_admin_or_manager(fn: Callable) -> Callable:
    """Decorator to restrict route access to admin or manager."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        verify_jwt_in_request()
        jwt_data = get_jwt()
        user_role = jwt_data.get("role")

        if user_role not in ("admin", "manager"):
            return _deny("Access denied. Admin or manager privileges required.")

        return fn(*args, **kwargs)
    return wrapper


def require_authenticated(fn: Callable) -> Callable:
    """Decorator to require valid JWT authentication."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        verify_jwt_in_request()
        return fn(*args, **kwargs)
    return wrapper