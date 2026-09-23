"""Email package — outbound (send-only) email notifications.

The module owns SMTP transport configuration (``provider``), the
per-taxpayer reconciliation notification templates (``templates``), the
``email_deliveries`` tracking model/repository, and the ``EmailService``
that plans, sends and records every delivery (including "no email",
"invalid" and "disabled/skipped" outcomes).
"""

from backend.modules.email.provider import (
    EmailAuthError,
    EmailConfig,
    EmailConfigError,
    EmailDisabledError,
    EmailError,
    EmailTransportError,
    EmailValidationError,
    SMTPEmailProvider,
)
from backend.modules.email.model import (
    DELIVERY_FAILED,
    DELIVERY_INVALID,
    DELIVERY_NO_EMAIL,
    DELIVERY_PENDING,
    DELIVERY_SENT,
    DELIVERY_SKIPPED,
    EmailDelivery,
)
from backend.modules.email.repository import EmailDeliveryRepository
from backend.modules.email.service import EMAIL_WORKFLOWS, EmailService

__all__ = [
    "EmailAuthError",
    "EmailConfig",
    "EmailConfigError",
    "EmailDisabledError",
    "EmailError",
    "EmailTransportError",
    "EmailValidationError",
    "SMTPEmailProvider",
    "DELIVERY_FAILED",
    "DELIVERY_INVALID",
    "DELIVERY_NO_EMAIL",
    "DELIVERY_PENDING",
    "DELIVERY_SENT",
    "DELIVERY_SKIPPED",
    "EmailDelivery",
    "EmailDeliveryRepository",
    "EMAIL_WORKFLOWS",
    "EmailService",
]