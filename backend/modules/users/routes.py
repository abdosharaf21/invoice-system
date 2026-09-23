"""User routes for user-related API endpoints."""

from flask import Blueprint, g, request, jsonify
from flask_jwt_extended import (
    get_jwt_identity,
    get_jwt
)

from backend.modules.users.service import UserService
from backend.middleware.contract import deprecated_response, error_response
from backend.middleware.rbac import require_admin, require_authenticated

users_bp = Blueprint("users", __name__, url_prefix="/api/users")

_user_service: UserService = None
_blocklist = None


def init_user_service(user_service: UserService, blocklist: set = None) -> None:
    """Initialize the user service dependency."""
    global _user_service, _blocklist
    _user_service = user_service
    _blocklist = blocklist


def _error(message: str, status: int) -> tuple:
    """Build an error response using the canonical error envelope.

    Args:
        message: Human-readable error message.
        status: HTTP status code.

    Returns:
        JSON payload with success, message, status and machine-readable code.
    """
    code = "INVALID_CREDENTIALS" if status == 401 else None
    return error_response(message, status, code=code)


@users_bp.route("/login", methods=["POST"])
def login():
    """Authenticate a user (legacy alias superseded by ``POST /api/auth/login``)."""
    data = request.get_json()
    try:
        validated_email = data.get("email")
        validated_password = data.get("password")

        if not validated_email:
            return _error("Email is required", 400)

        if not validated_password:
            return _error("Password is required", 400)

        result = _user_service.login(validated_email, validated_password)
        return deprecated_response(
            {
                "success": True,
                "message": "Login successful",
                "data": result,
            },
            200,
            successor="/api/auth/login",
        )
    except ValueError as e:
        return _error(str(e), 401)


@users_bp.route("/logout", methods=["POST"])
@require_authenticated
def logout():
    """Logout current user by revoking the JWT token (legacy alias of ``/api/auth/logout``)."""
    try:
        jwt_data = get_jwt()
        jti = jwt_data["jti"]
        _user_service.logout(jti)
        return deprecated_response(
            {"success": True, "message": "Logout successful"},
            200,
            successor="/api/auth/logout",
        )
    except Exception:
        return _error("Failed to logout", 500)


@users_bp.route("/me", methods=["GET"])
@require_authenticated
def get_current_user():
    """Get the current authenticated user (legacy alias of ``/api/auth/me``)."""
    try:
        user_id = get_jwt_identity()
        user = _user_service.get_user_by_id(int(user_id))
        return deprecated_response(
            {
                "success": True,
                "message": "User retrieved successfully",
                "data": user.to_dict(),
            },
            200,
            successor="/api/auth/me",
        )
    except ValueError as e:
        return _error(str(e), 404)


@users_bp.route("/", methods=["GET"])
@require_admin
def get_all_users():
    """Get all users for the admin's company."""
    admin = _user_service.get_user_by_id(g.user_id)
    if not admin.company_id:
        return jsonify({
            "success": True,
            "message": "Users retrieved successfully",
            "data": []
        }), 200
    users = _user_service.get_all_users_for_company(admin.company_id)
    return jsonify({
        "success": True,
        "message": "Users retrieved successfully",
        "data": [user.to_dict() for user in users]
    }), 200


@users_bp.route("/<int:user_id>", methods=["GET"])
@require_admin
def get_user(user_id):
    """Get a user by ID."""
    try:
        user = _user_service.get_user_by_id(user_id, g.user_company_id)
        return jsonify({
            "success": True,
            "message": "User retrieved successfully",
            "data": user.to_dict()
        }), 200
    except ValueError as e:
        return _error(str(e), 404)


@users_bp.route("/", methods=["POST"])
@require_admin
def create_user():
    """Create a new user."""
    data = request.get_json()
    try:
        validated_data = {
            "username": data.get("username"),
            "email": data.get("email"),
            "password": data.get("password"),
            "first_name": data.get("first_name"),
            "last_name": data.get("last_name"),
            "company_id": data.get("company_id"),
            "roles": data.get("roles"),
            "status": data.get("status")
        }

        if not validated_data["username"]:
            return _error("Username is required", 400)

        if not validated_data["email"]:
            return _error("Email is required", 400)

        if not validated_data["password"]:
            return _error("Password is required", 400)

        user = _user_service.create_user(validated_data, g.user_company_id)
        return jsonify({
            "success": True,
            "message": "User created successfully",
            "data": user.to_dict()
        }), 201
    except ValueError as e:
        return _error(str(e), 400)


@users_bp.route("/<int:user_id>", methods=["PUT"])
@require_admin
def update_user(user_id):
    """Update an existing user."""
    data = request.get_json()
    try:
        user = _user_service.update_user(user_id, data, g.user_company_id)
        return jsonify({
            "success": True,
            "message": "User updated successfully",
            "data": user.to_dict()
        }), 200
    except ValueError as e:
        return _error(str(e), 400)


@users_bp.route("/<int:user_id>/password", methods=["PUT"])
@require_admin
def change_password(user_id):
    """Change a user's password."""
    data = request.get_json()
    try:
        new_password = data.get("new_password")
        if not new_password:
            return _error("New password is required", 400)

        _user_service.change_password(user_id, new_password, g.user_company_id)
        return jsonify({"success": True, "message": "Password changed successfully"}), 200
    except ValueError as e:
        return _error(str(e), 400)


@users_bp.route("/<int:user_id>/activate", methods=["PUT"])
@require_admin
def activate_user(user_id):
    """Activate a user account."""
    try:
        user = _user_service.activate_user(user_id, g.user_company_id)
        return jsonify({
            "success": True,
            "message": "User activated successfully",
            "data": user.to_dict()
        }), 200
    except ValueError as e:
        return _error(str(e), 400)


@users_bp.route("/<int:user_id>/deactivate", methods=["PUT"])
@require_admin
def deactivate_user(user_id):
    """Deactivate a user account."""
    try:
        user = _user_service.deactivate_user(user_id, g.user_company_id)
        return jsonify({
            "success": True,
            "message": "User deactivated successfully",
            "data": user.to_dict()
        }), 200
    except ValueError as e:
        return _error(str(e), 400)


@users_bp.route("/<int:user_id>", methods=["DELETE"])
@require_admin
def delete_user(user_id):
    """Delete a user."""
    try:
        _user_service.delete_user(user_id, g.user_company_id)
        return jsonify({"success": True, "message": "User deleted successfully"}), 200
    except ValueError as e:
        return _error(str(e), 404)
