"""Flask routes for company settings (company-scoped, admin-only for writes)."""

from flask import Blueprint, g, request, jsonify
from backend.middleware.contract import error_response
from backend.middleware.rbac import require_admin, require_authenticated
from backend.modules.companies.service import CompanyService
from backend.modules.users.service import UserService

company_settings_bp = Blueprint("company_settings", __name__, url_prefix="/api/settings")

_company_service: CompanyService = None
_user_service: UserService = None


def init_company_settings_service(
    company_service: CompanyService,
    user_service: UserService = None,
) -> None:
    global _company_service, _user_service
    _company_service = company_service
    _user_service = user_service


def _get_admin_company_id() -> int:
    """Look up the current admin user's company_id."""
    if _user_service is None:
        raise ValueError("User service not initialized")
    admin = _user_service.get_user_by_id(g.user_id)
    if not admin.company_id:
        raise ValueError("No company associated with this account")
    return admin.company_id


def _error(message: str, status: int) -> tuple:
    """Build an error response using the canonical error envelope."""
    return error_response(message, status)


@company_settings_bp.route("/company", methods=["GET"])
@require_authenticated
def get_company_settings():
    """Return the current user's company settings."""
    try:
        company_id = _get_admin_company_id()
        company = _company_service.get_company(company_id)
        return jsonify({
            "success": True,
            "message": "Company settings retrieved",
            "data": company.to_dict(),
        }), 200
    except ValueError as e:
        return _error(str(e), 400)


@company_settings_bp.route("/company", methods=["PUT"])
@require_admin
def update_company_settings():
    """Update the current user's company settings (admin only)."""
    payload = request.get_json(silent=True)
    if not payload:
        return _error("Request body is required", 400)
    try:
        company_id = _get_admin_company_id()
        company = _company_service.update_company(company_id, payload)
        return jsonify({
            "success": True,
            "message": "Company settings updated",
            "data": company.to_dict(),
        }), 200
    except ValueError as e:
        return _error(str(e), 400)
