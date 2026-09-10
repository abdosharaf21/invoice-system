"""Reconciliation API routes.

Endpoints:

* ``POST /api/reconciliation/runs``                       - start a run for a period.
* ``GET  /api/reconciliation/runs``                       - list a company's runs.
* ``GET  /api/reconciliation/runs/<run_id>``              - run detail + result counts.
* ``GET  /api/reconciliation/runs/<run_id>/summary``      - structured run summary.
* ``GET  /api/reconciliation/runs/<run_id>/results``      - per-invoice results
  (paginated + filterable when report query params are present).
* ``GET  /api/reconciliation/runs/<run_id>/errors``       - field/rule-level errors
  (paginated + filterable when report query params are present).
* ``GET  /api/reconciliation/runs/<run_id>/results/export`` - results as csv/xlsx.
* ``GET  /api/reconciliation/runs/<run_id>/errors/export``  - errors as csv/xlsx.

All endpoints require authentication and the admin, accountant or manager
role, and enforce company ownership of the requested run.
"""

import io
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request, send_file
from flask_jwt_extended import get_jwt_identity

from backend.middleware.exceptions import BadRequestException, NotFoundException
from backend.middleware.rbac import require_roles
from backend.modules.reconciliation import contract as c
from backend.modules.reconciliation.service import ReconciliationService

from backend.modules.reconciliation.engine import is_valid_period, normalize_period

logger = logging.getLogger(__name__)

reconciliation_bp = Blueprint(
    "reconciliation", __name__, url_prefix="/api/reconciliation"
)

_reconciliation_service: ReconciliationService = None

_RECONCILIATION_ROLES = ("admin", "accountant", "manager")

_PERIOD_HELP = "Expected a 'YYYY-MM' period."
_TAX = Decimal("0.00")

_DEFAULT_PAGE_SIZE = 50
_MAX_PAGE_SIZE = 200

_RESULT_REPORT_PARAMS = (
    "page", "page_size", "match_status", "uuid",
    "invoice_number", "date_from", "date_to",
)
_ERROR_REPORT_PARAMS = ("page", "page_size", "error_type", "source_type")


def init_reconciliation_service(service: ReconciliationService) -> None:
    """Initialize the reconciliation service dependency."""
    global _reconciliation_service
    _reconciliation_service = service


@reconciliation_bp.route("/runs", methods=["POST"])
@require_roles(*_RECONCILIATION_ROLES)
def start_reconciliation_run():
    """Start a reconciliation run for a company and period."""
    _ensure_configured()

    company_id = _company_id()
    if company_id is None:
        raise BadRequestException("User does not belong to a company")

    body = request.get_json(silent=True) or {}
    period = body.get("period")
    if not isinstance(period, str) or not is_valid_period(normalize_period(period)):
        raise BadRequestException(f"Invalid period: {_PERIOD_HELP}")

    money_tolerance = _parse_tolerance(body.get("money_tolerance"))

    run, counts = _reconciliation_service.start_run(
        company_id=company_id,
        period=normalize_period(period),
        money_tolerance=money_tolerance,
    )
    return jsonify({
        "success": True,
        "data": {"run": run.to_dict(), "counts": counts},
    }), 201


@reconciliation_bp.route("/runs", methods=["GET"])
@require_roles(*_RECONCILIATION_ROLES)
def list_reconciliation_runs():
    """List reconciliation runs for the authenticated user's company."""
    _ensure_configured()

    company_id = _company_id()
    if company_id is None:
        raise BadRequestException("User does not belong to a company")

    limit = _clamp_int(request.args.get("limit"), default=50, low=1, high=200)
    offset = _clamp_int(request.args.get("offset"), default=0, low=0, high=None)

    runs = _reconciliation_service.list_runs(company_id, limit=limit, offset=offset)
    return jsonify({
        "success": True,
        "data": {
            "runs": [run.to_dict() for run in runs],
            "count": len(runs),
            "limit": limit,
            "offset": offset,
        },
    }), 200


@reconciliation_bp.route("/runs/<int:run_id>", methods=["GET"])
@require_roles(*_RECONCILIATION_ROLES)
def get_reconciliation_run(run_id: int):
    """Fetch a run and its per-status result counts."""
    _ensure_configured()

    company_id = _company_id()
    run = _reconciliation_service.get_run(run_id, company_id)
    if run is None:
        raise NotFoundException("Reconciliation run not found")

    counts = _reconciliation_service.get_summary(run_id)
    return jsonify({
        "success": True,
        "data": {"run": run.to_dict(), "counts": counts},
    }), 200


@reconciliation_bp.route("/runs/<int:run_id>/summary", methods=["GET"])
@require_roles(*_RECONCILIATION_ROLES)
def get_reconciliation_summary(run_id: int):
    """Fetch a run's structured report summary."""
    _ensure_configured()

    summary = _reconciliation_service.get_report_summary(run_id, _company_id())
    if summary is None:
        raise NotFoundException("Reconciliation run not found")

    return jsonify({"success": True, "data": summary}), 200


@reconciliation_bp.route("/runs/<int:run_id>/results", methods=["GET"])
@require_roles(*_RECONCILIATION_ROLES)
def get_reconciliation_results(run_id: int):
    """Fetch a run's invoice-level results.

    With no report query params this keeps the original shape
    ``{results: [...]}``. With pagination and/or filter params it returns a
    paginated envelope ``{items, page, page_size, total, total_pages}``.
    """
    _ensure_configured()

    company_id = _company_id()
    if _has_report_params(_RESULT_REPORT_PARAMS):
        page, page_size = _page_query()
        filters = _result_filters()
        payload = _reconciliation_service.paginate_results(
            run_id, company_id, page, page_size, filters
        )
        if payload is None:
            raise NotFoundException("Reconciliation run not found")
        return jsonify({"success": True, "data": payload}), 200

    results = _reconciliation_service.get_results(run_id, company_id)
    if results is None:
        raise NotFoundException("Reconciliation run not found")
    return jsonify({
        "success": True,
        "data": {"results": results},
    }), 200


@reconciliation_bp.route("/runs/<int:run_id>/errors", methods=["GET"])
@require_roles(*_RECONCILIATION_ROLES)
def get_reconciliation_errors(run_id: int):
    """Fetch a run's field/rule-level errors.

    With no report query params this keeps the original shape
    ``{errors: [...]}``. With pagination and/or filter params it returns a
    paginated envelope ``{items, page, page_size, total, total_pages}``.
    """
    _ensure_configured()

    company_id = _company_id()
    if _has_report_params(_ERROR_REPORT_PARAMS):
        page, page_size = _page_query()
        filters = _error_filters()
        payload = _reconciliation_service.paginate_errors(
            run_id, company_id, page, page_size, filters
        )
        if payload is None:
            raise NotFoundException("Reconciliation run not found")
        return jsonify({"success": True, "data": payload}), 200

    errors = _reconciliation_service.get_errors(run_id, company_id)
    if errors is None:
        raise NotFoundException("Reconciliation run not found")
    return jsonify({
        "success": True,
        "data": {"errors": [error.to_dict() for error in errors]},
    }), 200


@reconciliation_bp.route("/runs/<int:run_id>/results/export", methods=["GET"])
@require_roles(*_RECONCILIATION_ROLES)
def export_reconciliation_results(run_id: int):
    """Export a run's results as CSV or XLSX."""
    _ensure_configured()

    fmt = _export_format()
    filters = _result_filters()
    outcome = _reconciliation_service.export_results(
        run_id, _company_id(), fmt, filters
    )
    if outcome is None:
        raise NotFoundException("Reconciliation run not found")
    return _export_response(*outcome)


@reconciliation_bp.route("/runs/<int:run_id>/errors/export", methods=["GET"])
@require_roles(*_RECONCILIATION_ROLES)
def export_reconciliation_errors(run_id: int):
    """Export a run's errors as CSV or XLSX."""
    _ensure_configured()

    fmt = _export_format()
    filters = _error_filters()
    outcome = _reconciliation_service.export_errors(
        run_id, _company_id(), fmt, filters
    )
    if outcome is None:
        raise NotFoundException("Reconciliation run not found")
    return _export_response(*outcome)


def _ensure_configured() -> None:
    if _reconciliation_service is None:
        raise BadRequestException("Reconciliation service is not configured")


def _company_id():
    user_id = _user_id()
    return _reconciliation_service.company_for_user(user_id)


def _user_id() -> int:
    try:
        return int(get_jwt_identity())
    except (TypeError, ValueError):
        raise BadRequestException("Invalid user identity in token")


def _parse_tolerance(value):
    if value is None or value == "":
        return None
    try:
        tolerance = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise BadRequestException("money_tolerance must be a decimal number")
    if tolerance < _TAX:
        raise BadRequestException("money_tolerance must be zero or positive")
    return tolerance


def _clamp_int(raw, default: int, low: int, high=None) -> int:
    if raw is None:
        return default
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        raise BadRequestException("Query parameters must be integers")
    if parsed < low or (high is not None and parsed > high):
        raise BadRequestException(
            f"Query parameter out of range ({low}..{high or 'unbounded'})"
        )
    return parsed


# ---------------------------------------------------------------------------
# Report query helpers
# ---------------------------------------------------------------------------


def _has_report_params(param_names) -> bool:
    return any(name in request.args for name in param_names)


def _page_query() -> tuple:
    page = _clamp_int(request.args.get("page"), default=1, low=1, high=None)
    page_size = _clamp_int(
        request.args.get("page_size"),
        default=_DEFAULT_PAGE_SIZE,
        low=1,
        high=_MAX_PAGE_SIZE,
    )
    return page, page_size


def _result_filters() -> dict:
    filters = {}
    status = request.args.get("match_status")
    if status:
        if status not in c.RESULT_STATUSES:
            raise BadRequestException(
                f"match_status must be one of: {', '.join(c.RESULT_STATUSES)}"
            )
        filters["match_status"] = status
    uuid = request.args.get("uuid")
    if uuid:
        filters["uuid"] = uuid.strip()
    invoice_number = request.args.get("invoice_number")
    if invoice_number:
        filters["invoice_number"] = invoice_number.strip()
    date_from = _date_param("date_from")
    date_to = _date_param("date_to")
    if date_from and date_to and date_from > date_to:
        raise BadRequestException("date_from must not be after date_to")
    if date_from:
        filters["date_from"] = date_from
    if date_to:
        filters["date_to"] = date_to
    return filters


def _error_filters() -> dict:
    filters = {}
    error_type = request.args.get("error_type")
    if error_type:
        filters["error_type"] = error_type.strip()
    source_type = request.args.get("source_type")
    if source_type:
        if source_type not in ("account", "tax"):
            raise BadRequestException("source_type must be 'account' or 'tax'")
        filters["source_type"] = source_type
    return filters


def _date_param(name: str):
    raw = request.args.get(name)
    if not raw:
        return None
    try:
        return datetime.strptime(raw.strip(), "%Y-%m-%d").date()
    except ValueError:
        raise BadRequestException(f"{name} must be a 'YYYY-MM-DD' date")


def _export_format() -> str:
    fmt = (request.args.get("format") or "csv").strip().lower()
    if fmt not in ("csv", "xlsx"):
        raise BadRequestException("format must be 'csv' or 'xlsx'")
    return fmt


def _export_response(filename: str, mimetype: str, payload):
    return send_file(
        io.BytesIO(payload),
        mimetype=mimetype,
        as_attachment=True,
        download_name=filename,
    )