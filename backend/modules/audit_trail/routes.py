"""Audit trail routes for the platform audit log API."""

from flask import Blueprint, jsonify, request

from backend.middleware.auth_context import get_current_user_company_id
from backend.middleware.contract import error_response
from backend.middleware.exceptions import BadRequestException
from backend.middleware.rbac import require_admin_or_manager
from backend.modules.audit_trail.service import (
    AuditTrailService,
    set_audit_trail_service,
)

audit_trail_bp = Blueprint(
    "audit_trail", __name__, url_prefix="/api/audit-trail"
)

_audit_service: AuditTrailService = None


def init_audit_trail_service(audit_service: AuditTrailService) -> None:
    """Initialize the audit trail service dependency.

    Args:
        audit_service: Instance of AuditTrailService for dependency injection.
    """
    global _audit_service
    _audit_service = audit_service
    set_audit_trail_service(audit_service)


@audit_trail_bp.route("/logs", methods=["GET"])
@require_admin_or_manager
def list_audit_logs():
    """List audit trail entries with optional filters.

    Query params:
        actor_id: Optional filter by acting user id.
        action: Optional filter by action verb (login, create, ...).
        resource_type: Optional filter by resource type.
        result: Optional filter by outcome (success, failure).
        start_date: Optional inclusive created_at lower bound (YYYY-MM-DD).
        end_date: Optional inclusive created_at upper bound (YYYY-MM-DD).
        page: Page number, starting at 1.
        page_size: Entries per page (max 200).
        sort_by: Optional allowed sort column.

    Company scoping is always derived from the authenticated user's JWT,
    never from client-supplied input, so records from other tenants can
    never be read or filtered by the requester.

    Returns:
        JSON response with the paginated audit log list.
    """
    if _audit_service is None:
        raise BadRequestException("Audit trail service is not configured")

    try:
        result = _audit_service.list_logs(
            actor_id=request.args.get("actor_id", type=int),
            action=request.args.get("action") or None,
            resource_type=request.args.get("resource_type") or None,
            result=request.args.get("result") or None,
            start_date=request.args.get("start_date") or None,
            end_date=request.args.get("end_date") or None,
            page=request.args.get("page", default=1, type=int),
            page_size=request.args.get("page_size", default=50, type=int),
            sort_by=request.args.get("sort_by") or None,
            company_id=get_current_user_company_id(),
        )
    except ValueError as e:
        return error_response(str(e), 400)

    return jsonify({"success": True, "data": result}), 200