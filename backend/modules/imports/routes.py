"""Import API routes for accounting file imports.

Endpoints:

* ``POST /api/imports``       - upload an accounting file and import it.
* ``GET  /api/imports/<id>``  - fetch a batch (or list one batch's errors
  when ``?include=errors`` is passed).

Both endpoints are restricted to admin, accountant and manager roles.
"""

from flask import Blueprint, jsonify, request

from flask_jwt_extended import get_jwt_identity

from backend.middleware.exceptions import BadRequestException, NotFoundException
from backend.middleware.rbac import require_roles
from backend.modules.imports.service import ImportService

imports_bp = Blueprint("imports", __name__, url_prefix="/api/imports")

_import_service: ImportService = None

_IMPORT_ROLES = ("admin", "accountant", "manager")


def init_import_service(service: ImportService) -> None:
    """Initialize the import service dependency."""
    global _import_service
    _import_service = service


@imports_bp.route("", methods=["POST"])
@require_roles(*_IMPORT_ROLES)
def create_import():
    """Upload and import a CSV/XLSX accounting file."""
    if _import_service is None:
        raise BadRequestException("Import service is not configured")

    company_id = _company_id_for_authenticated_user()
    if company_id is None:
        raise BadRequestException("User does not belong to a company")

    file = request.files.get("file")
    if file is None:
        raise BadRequestException("A 'file' form field is required")

    filename = file.filename or ""
    content = file.read()
    content_type = file.mimetype or ""

    result = _import_service.import_file(
        company_id=company_id,
        uploaded_by=_user_id(),
        filename=filename,
        content_type=content_type,
        content=content,
    )
    return jsonify({"success": True, "data": result.to_dict()}), 201


@imports_bp.route("/<int:batch_id>", methods=["GET"])
@require_roles(*_IMPORT_ROLES)
def get_import(batch_id: int):
    """Fetch an import batch by id."""
    if _import_service is None:
        raise BadRequestException("Import service is not configured")

    company_id = _company_id_for_authenticated_user()
    if company_id is None:
        raise NotFoundException("Import batch not found")

    batch = _import_service.get_batch(batch_id, company_id)
    if batch is None:
        raise NotFoundException("Import batch not found")

    include_errors = request.args.get("include", "").lower() == "errors"
    data = {
        "batch": batch.to_dict(),
    }
    if include_errors:
        data["errors"] = [
            error.to_dict() for error in _import_service.list_errors(batch_id)
        ]
    return jsonify({"success": True, "data": data}), 200


def _company_id_for_authenticated_user():
    user_id = _user_id()
    return _import_service.company_for_user(user_id)


def _user_id() -> int:
    try:
        return int(get_jwt_identity())
    except (TypeError, ValueError):
        raise BadRequestException("Invalid user identity in token")