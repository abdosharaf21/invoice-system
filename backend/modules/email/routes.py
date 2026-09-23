"""Admin-only email diagnostics routes.

Two endpoints exist, both strictly admin-gated. Neither endpoint accepts
arbitrary recipients for bulk relaying:

* ``GET  /api/email/status`` - read-only status and supported events
  (credentials are never returned).
* ``POST /api/email/test``   - send one test message to a single address
  that the calling admin explicitly provides.
"""

import logging

from flask import Blueprint, jsonify, request

from backend.middleware.contract import error_response
from backend.middleware.exceptions import ServiceUnavailableException
from backend.middleware.rbac import require_admin
from backend.modules.email.provider import (
    EmailAuthError,
    EmailConfigError,
    EmailDisabledError,
    EmailTransportError,
    EmailValidationError,
)
from backend.modules.email.service import EmailService

logger = logging.getLogger(__name__)

email_bp = Blueprint("email", __name__, url_prefix="/api/email")

_email_service: EmailService = None


def init_email_service(service: EmailService) -> None:
    """Initialize the email service dependency."""
    global _email_service
    _email_service = service


def _error(message: str, status: int) -> tuple:
    """Build an error response using the canonical error envelope."""
    return error_response(message, status)


@email_bp.route("/status", methods=["GET"])
@require_admin
def get_email_status():
    """Return the email configuration status (no credentials)."""
    _ensure_configured()
    return jsonify({"success": True, "data": _email_service.get_status()}), 200


@email_bp.route("/test", methods=["POST"])
@require_admin
def send_test_email():
    """Send a diagnostic test email to one address."""
    _ensure_configured()
    body = request.get_json(silent=True) or {}
    to = body.get("to")
    if not to or not isinstance(to, str):
        return _error("A recipient email address ('to') is required", 400)
    try:
        outcome = _email_service.send_test(to)
    except EmailValidationError as exc:
        return _error(str(exc), 400)
    except EmailDisabledError as exc:
        return _error(str(exc), 400)
    except EmailConfigError as exc:
        return _error(str(exc), 400)
    except (EmailAuthError, EmailTransportError) as exc:
        logger.error("Email test failed: %s", exc)
        return _error("Email test failed; check the server logs", 502)
    return jsonify({
        "success": True,
        "message": "Test email sent",
        "data": outcome,
    }), 200


def _ensure_configured() -> None:
    if _email_service is None:
        raise ServiceUnavailableException("Email service is not configured")