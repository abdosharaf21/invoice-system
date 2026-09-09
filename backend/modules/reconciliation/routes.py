"""Reconciliation API routes.

Endpoints:

* ``POST /api/reconciliation/runs``                      - start a run for a period.
* ``GET  /api/reconciliation/runs``                      - list a company's runs.
* ``GET  /api/reconciliation/runs/<run_id>``             - run detail + result counts.
* ``GET  /api/reconciliation/runs/<run_id>/results``     - per-invoice results.
* ``GET  /api/reconciliation/runs/<run_id>/errors``      - field/rule-level errors.

All endpoints require authentication and the admin, accountant or manager
role, and enforce company ownership of the requested run.
"""

import logging
from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity

from backend.middleware.exceptions import BadRequestException, NotFoundException
from backend.middleware.rbac import require_roles
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


@reconciliation_bp.route("/runs/<int:run_id>/results", methods=["GET"])
@require_roles(*_RECONCILIATION_ROLES)
def get_reconciliation_results(run_id: int):
    """Fetch a run's invoice-level results."""
    _ensure_configured()

    company_id = _company_id()
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
    """Fetch a run's field/rule-level errors."""
    _ensure_configured()

    company_id = _company_id()
    errors = _reconciliation_service.get_errors(run_id, company_id)
    if errors is None:
        raise NotFoundException("Reconciliation run not found")

    return jsonify({
        "success": True,
        "data": {"errors": [error.to_dict() for error in errors]},
    }), 200


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