"""Authentication routes.

Handles all /api/auth/* endpoints for login, logout, refresh, and profile.
Uses JWT access tokens and refresh tokens with blocklist support.
"""

from flask import Blueprint, request
from flask_jwt_extended import (
    get_jwt,
    get_jwt_identity,
    jwt_required,
    decode_token,
)

from backend.middleware.contract import error_response
from backend.middleware.exceptions import (
    AppException,
)
from backend.modules.auth.service import AuthService


auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")

_auth_service: AuthService = None


def init_auth_service(auth_service: AuthService) -> None:
    """Initialize the auth service dependency."""
    global _auth_service
    _auth_service = auth_service


def _success(data, status: int = 200):
    """Standard success response."""
    return {"success": True, "data": data}, status


def _error(message: str, status: int = 400):
    """Standard error response using the canonical error envelope."""
    return error_response(message, status)


@auth_bp.route("/login", methods=["POST"])
def login():
    """Authenticate user and return access + refresh tokens."""
    data = request.get_json(silent=True) or {}
    email = data.get("email")
    password = data.get("password")

    result = _auth_service.login(email, password)
    return _success(result, 200)


@auth_bp.route("/logout", methods=["POST"])
@jwt_required()
def logout():
    """Revoke current access token and optionally a refresh token."""
    claims = get_jwt()
    access_jti = claims.get("jti")

    data = request.get_json(silent=True) or {}
    refresh_token = data.get("refresh_token")

    refresh_jti = None
    if refresh_token:
        try:
            decoded = decode_token(refresh_token)
            refresh_jti = decoded.get("jti")
        except Exception:
            pass

    _auth_service.logout(
        access_jti=access_jti,
        refresh_jti=refresh_jti or access_jti,
    )

    return _success({"message": "Logged out successfully"}, 200)


@auth_bp.route("/refresh", methods=["POST"])
def refresh():
    """Exchange a valid refresh token for a new access token."""
    data = request.get_json(silent=True) or {}
    refresh_token = data.get("refresh_token")

    result = _auth_service.refresh_tokens(refresh_token)
    return _success(result, 200)


@auth_bp.route("/logout-refresh", methods=["POST"])
@jwt_required()
def logout_refresh():
    """Revoke a specific refresh token."""
    data = request.get_json(silent=True) or {}
    refresh_token = data.get("refresh_token")

    if not refresh_token:
        return _error("refresh_token is required", 400)

    _auth_service.logout_refresh(refresh_token)
    return _success({"message": "Refresh token revoked"}, 200)


@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def me():
    """Get current authenticated user profile."""
    user_id = get_jwt_identity()
    result = _auth_service.get_current_user(user_id)
    return _success(result, 200)


@auth_bp.route("/change-password", methods=["PUT"])
@jwt_required()
def change_password():
    """Change the authenticated user's password."""
    data = request.get_json(silent=True) or {}
    current_password = data.get("current_password")
    new_password = data.get("new_password")

    if not current_password or not new_password:
        return _error("current_password and new_password are required", 400)

    user_id = get_jwt_identity()
    _auth_service.change_password(user_id, current_password, new_password)

    return _success({"message": "Password changed successfully"}, 200)


@auth_bp.errorhandler(AppException)
def handle_app_exception(e):
    """Handle known application exceptions."""
    return e.to_dict(), e.status_code


@auth_bp.errorhandler(422)
def handle_422(e):
    """Handle JWT missing/invalid errors."""
    return {
        "success": False,
        "message": "Missing or invalid token",
        "status": 401,
        "code": "TOKEN_REQUIRED",
    }, 401


@auth_bp.errorhandler(401)
def handle_401(e):
    """Handle unauthorized errors."""
    return {
        "success": False,
        "message": str(e.description),
        "status": 401,
        "code": "UNAUTHORIZED",
    }, 401
