"""Flask routes for application and user settings (admin-only for writes).

Application settings: any authenticated user may read the safe subset;
writes require admin. User settings: a user may only read/update their own.
"""

from flask import Blueprint, g, request, jsonify
from backend.middleware.contract import error_response
from backend.middleware.rbac import require_admin, require_authenticated
from backend.modules.settings.service import ApplicationSettingService
from backend.modules.users.service import UserService

settings_bp = Blueprint("settings", __name__, url_prefix="/api/settings")

_service: ApplicationSettingService = None
_user_service: UserService = None


def init_settings_service(
    service: ApplicationSettingService,
    user_service: UserService = None,
) -> None:
    global _service, _user_service
    _service = service
    _user_service = user_service


def _error(message: str, status: int) -> tuple:
    """Build an error response using the canonical error envelope."""
    return error_response(message, status)


@settings_bp.route("/application", methods=["GET"])
@require_authenticated
def get_application_settings():
    """Return application settings (safe subset for any authenticated user)."""
    data = _service.get_settings_for_frontend()
    return jsonify({
        "success": True,
        "message": "Application settings retrieved",
        "data": data,
    }), 200


@settings_bp.route("/application", methods=["PUT"])
@require_admin
def update_application_settings():
    """Update application settings (admin only)."""
    payload = request.get_json(silent=True)
    if not payload:
        return _error("Request body is required", 400)
    try:
        data = _service.update_settings(payload)
        return jsonify({
            "success": True,
            "message": "Application settings updated",
            "data": data,
        }), 200
    except ValueError as e:
        return _error(str(e), 400)


@settings_bp.route("/application/all", methods=["GET"])
@require_admin
def get_all_application_settings():
    """Return every application setting including internal ones (admin only)."""
    data = _service.get_all_settings()
    return jsonify({
        "success": True,
        "message": "Application settings retrieved",
        "data": data,
    }), 200


@settings_bp.route("/user", methods=["GET"])
@require_authenticated
def get_current_user_settings():
    """Return the authenticated user's own preferences."""
    if _user_service is None:
        return _error("User service not initialized", 500)
    try:
        data = _user_service.get_user_settings(g.user_id)
        return jsonify({
            "success": True,
            "message": "User settings retrieved",
            "data": data,
        }), 200
    except ValueError as e:
        return _error(str(e), 400)


@settings_bp.route("/user", methods=["PUT"])
@require_authenticated
def update_current_user_settings():
    """Update the authenticated user's own preferences only."""
    if _user_service is None:
        return _error("User service not initialized", 500)
    payload = request.get_json(silent=True)
    if not payload:
        return _error("Request body is required", 400)
    try:
        data = _user_service.update_user_settings(g.user_id, payload)
        return jsonify({
            "success": True,
            "message": "User settings updated",
            "data": data,
        }), 200
    except ValueError as e:
        return _error(str(e), 400)
