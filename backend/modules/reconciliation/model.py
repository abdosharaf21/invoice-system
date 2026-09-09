"""Reconciliation models representing the reconciliation_runs, results and errors tables."""

from datetime import datetime
from typing import Optional


def _parse_datetime(value):
    if value and isinstance(value, str):
        return datetime.fromisoformat(value)
    return value


class ReconciliationError:
    """Represents an error encountered during a reconciliation run."""

    def __init__(
        self,
        id: Optional[int] = None,
        run_id: Optional[int] = None,
        source_type: str = "account",
        entity_id: Optional[int] = None,
        error_type: Optional[str] = None,
        message: Optional[str] = None,
        created_at: Optional[datetime] = None
    ) -> None:
        self.id = id
        self.run_id = run_id
        self.source_type = source_type
        self.entity_id = entity_id
        self.error_type = error_type
        self.message = message
        self.created_at = created_at or datetime.now()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "run_id": self.run_id,
            "source_type": self.source_type,
            "entity_id": self.entity_id,
            "error_type": self.error_type,
            "message": self.message,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ReconciliationError":
        return cls(
            id=data.get("id"),
            run_id=data.get("run_id"),
            source_type=data.get("source_type", "account"),
            entity_id=data.get("entity_id"),
            error_type=data.get("error_type"),
            message=data.get("message"),
            created_at=_parse_datetime(data.get("created_at"))
        )

    def __repr__(self) -> str:
        return f"ReconciliationError(id={self.id}, type={self.error_type})"


class ReconciliationResult:
    """Represents the outcome of matching one invoice in a reconciliation run."""

    def __init__(
        self,
        id: Optional[int] = None,
        run_id: Optional[int] = None,
        account_invoice_id: Optional[int] = None,
        tax_invoice_id: Optional[int] = None,
        match_status: Optional[str] = None,
        discrepancy_amount: float = 0.0,
        notes: Optional[str] = None,
        created_at: Optional[datetime] = None
    ) -> None:
        self.id = id
        self.run_id = run_id
        self.account_invoice_id = account_invoice_id
        self.tax_invoice_id = tax_invoice_id
        self.match_status = match_status
        self.discrepancy_amount = discrepancy_amount
        self.notes = notes
        self.created_at = created_at or datetime.now()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "run_id": self.run_id,
            "account_invoice_id": self.account_invoice_id,
            "tax_invoice_id": self.tax_invoice_id,
            "match_status": self.match_status,
            "discrepancy_amount": float(self.discrepancy_amount),
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ReconciliationResult":
        return cls(
            id=data.get("id"),
            run_id=data.get("run_id"),
            account_invoice_id=data.get("account_invoice_id"),
            tax_invoice_id=data.get("tax_invoice_id"),
            match_status=data.get("match_status"),
            discrepancy_amount=data.get("discrepancy_amount", 0.0),
            notes=data.get("notes"),
            created_at=_parse_datetime(data.get("created_at"))
        )

    def __repr__(self) -> str:
        return (
            f"ReconciliationResult(id={self.id}, run={self.run_id}, "
            f"status={self.match_status})"
        )


class ReconciliationRun:
    """Represents a reconciliation run for a company and accounting period.

    Tracks a single pass over the accounting invoices and tax authority
    invoices for a period, with aggregated match/unmatched/error counts.
    Individual outcomes are stored as ReconciliationResult rows.
    """

    def __init__(
        self,
        id: Optional[int] = None,
        company_id: Optional[int] = None,
        period: Optional[str] = None,
        status: str = "pending",
        invoice_count: int = 0,
        tax_invoice_count: int = 0,
        matched_count: int = 0,
        unmatched_count: int = 0,
        error_count: int = 0,
        started_at: Optional[datetime] = None,
        finished_at: Optional[datetime] = None,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None
    ) -> None:
        self.id = id
        self.company_id = company_id
        self.period = period
        self.status = status
        self.invoice_count = invoice_count
        self.tax_invoice_count = tax_invoice_count
        self.matched_count = matched_count
        self.unmatched_count = unmatched_count
        self.error_count = error_count
        self.started_at = started_at
        self.finished_at = finished_at
        self.created_at = created_at or datetime.now()
        self.updated_at = updated_at or datetime.now()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "company_id": self.company_id,
            "period": self.period,
            "status": self.status,
            "invoice_count": self.invoice_count,
            "tax_invoice_count": self.tax_invoice_count,
            "matched_count": self.matched_count,
            "unmatched_count": self.unmatched_count,
            "error_count": self.error_count,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ReconciliationRun":
        return cls(
            id=data.get("id"),
            company_id=data.get("company_id"),
            period=data.get("period"),
            status=data.get("status", "pending"),
            invoice_count=data.get("invoice_count", 0),
            tax_invoice_count=data.get("tax_invoice_count", 0),
            matched_count=data.get("matched_count", 0),
            unmatched_count=data.get("unmatched_count", 0),
            error_count=data.get("error_count", 0),
            started_at=_parse_datetime(data.get("started_at")),
            finished_at=_parse_datetime(data.get("finished_at")),
            created_at=_parse_datetime(data.get("created_at")),
            updated_at=_parse_datetime(data.get("updated_at"))
        )

    def __str__(self) -> str:
        return f"ReconciliationRun(id={self.id}, company={self.company_id}, period={self.period})"

    def __repr__(self) -> str:
        return self.__str__()