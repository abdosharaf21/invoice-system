"""Email delivery model representing the email_deliveries table.

One row exists per (reconciliation run, recipient). Notifications are sent
to the run's *taxpayers/counterparties* — resolved from the imported
accounting data — never to internal users. The row records the outcome of
that single grouped message so administrators can audit and resend.
"""

from datetime import datetime
from typing import Optional

DELIVERY_PENDING = "pending"
DELIVERY_SENT = "sent"
DELIVERY_FAILED = "failed"
DELIVERY_SKIPPED = "skipped"
DELIVERY_NO_EMAIL = "no_email"
DELIVERY_INVALID = "invalid"

DELIVERY_STATUSES = (
    DELIVERY_PENDING,
    DELIVERY_SENT,
    DELIVERY_FAILED,
    DELIVERY_SKIPPED,
    DELIVERY_NO_EMAIL,
    DELIVERY_INVALID,
)

# Statuses that represent an actually-sent message.
DELIVERED_STATUSES = (DELIVERY_SENT,)

# Statuses that never touch the SMTP transport.
NON_SEND_STATUSES = (
    DELIVERY_SKIPPED,
    DELIVERY_NO_EMAIL,
    DELIVERY_INVALID,
)


class EmailDelivery:
    """Represents one per-taxpayer notification attempt for a run."""

    def __init__(
        self,
        id: Optional[int] = None,
        company_id: Optional[int] = None,
        run_id: Optional[int] = None,
        recipient_email: Optional[str] = None,
        taxpayer_name: Optional[str] = None,
        taxpayer_tax_id: Optional[str] = None,
        invoice_count: int = 0,
        subject: str = "",
        status: str = DELIVERY_PENDING,
        failure_reason: Optional[str] = None,
        request_id: Optional[str] = None,
        attempted_at: Optional[datetime] = None,
        sent_at: Optional[datetime] = None,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
    ) -> None:
        self.id = id
        self.company_id = company_id
        self.run_id = run_id
        self.recipient_email = recipient_email
        self.taxpayer_name = taxpayer_name
        self.taxpayer_tax_id = taxpayer_tax_id
        self.invoice_count = invoice_count
        self.subject = subject
        self.status = status
        self.failure_reason = failure_reason
        self.request_id = request_id
        self.attempted_at = attempted_at
        self.sent_at = sent_at
        self.created_at = created_at or datetime.now()
        self.updated_at = updated_at or datetime.now()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "company_id": self.company_id,
            "run_id": self.run_id,
            "recipient_email": self.recipient_email,
            "taxpayer_name": self.taxpayer_name,
            "taxpayer_tax_id": self.taxpayer_tax_id,
            "invoice_count": self.invoice_count,
            "subject": self.subject,
            "status": self.status,
            "failure_reason": self.failure_reason,
            "request_id": self.request_id,
            "attempted_at": self.attempted_at.isoformat() if self.attempted_at else None,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EmailDelivery":
        return cls(
            id=data.get("id"),
            company_id=data.get("company_id"),
            run_id=data.get("run_id"),
            recipient_email=data.get("recipient_email"),
            taxpayer_name=data.get("taxpayer_name"),
            taxpayer_tax_id=data.get("taxpayer_tax_id"),
            invoice_count=data.get("invoice_count", 0),
            subject=data.get("subject") or "",
            status=data.get("status", DELIVERY_PENDING),
            failure_reason=data.get("failure_reason"),
            request_id=data.get("request_id"),
            attempted_at=_parse_datetime(data.get("attempted_at")),
            sent_at=_parse_datetime(data.get("sent_at")),
            created_at=_parse_datetime(data.get("created_at")),
            updated_at=_parse_datetime(data.get("updated_at")),
        )

    def __repr__(self) -> str:
        return (
            f"EmailDelivery(id={self.id}, run={self.run_id}, "
            f"status={self.status})"
        )


def _parse_datetime(value):
    if value and isinstance(value, str):
        return datetime.fromisoformat(value)
    return value