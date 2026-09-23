"""Invoice models representing the accounting invoices and invoice_items tables."""

from datetime import date, datetime
from typing import List, Optional


def _parse_datetime(value):
    if value and isinstance(value, str):
        return datetime.fromisoformat(value)
    return value


def _parse_date(value):
    if value and isinstance(value, str):
        return date.fromisoformat(value)
    return value


class InvoiceItem:
    """Represents a single line item on an accounting invoice."""

    def __init__(
        self,
        id: Optional[int] = None,
        invoice_id: Optional[int] = None,
        description: Optional[str] = None,
        quantity: float = 1.0,
        unit_price: float = 0.0,
        discount_amount: float = 0.0,
        vat_rate: float = 0.0,
        vat_amount: float = 0.0,
        line_total: float = 0.0,
        created_at: Optional[datetime] = None
    ) -> None:
        self.id = id
        self.invoice_id = invoice_id
        self.description = description
        self.quantity = quantity
        self.unit_price = unit_price
        self.discount_amount = discount_amount
        self.vat_rate = vat_rate
        self.vat_amount = vat_amount
        self.line_total = line_total
        self.created_at = created_at or datetime.now()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "invoice_id": self.invoice_id,
            "description": self.description,
            "quantity": float(self.quantity),
            "unit_price": float(self.unit_price),
            "discount_amount": float(self.discount_amount),
            "vat_rate": float(self.vat_rate),
            "vat_amount": float(self.vat_amount),
            "line_total": float(self.line_total),
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

    @classmethod
    def from_dict(cls, data: dict) -> "InvoiceItem":
        return cls(
            id=data.get("id"),
            invoice_id=data.get("invoice_id"),
            description=data.get("description"),
            quantity=data.get("quantity", 1.0),
            unit_price=data.get("unit_price", 0.0),
            discount_amount=data.get("discount_amount", 0.0),
            vat_rate=data.get("vat_rate", 0.0),
            vat_amount=data.get("vat_amount", 0.0),
            line_total=data.get("line_total", 0.0),
            created_at=_parse_datetime(data.get("created_at"))
        )

    def __repr__(self) -> str:
        return f"InvoiceItem(id={self.id}, description={self.description!r})"


class Invoice:
    """Represents an accounting invoice in the invoices table.

    The accounting side is the source of truth for invoices issued and
    received on the books. It is kept separate from the tax authority
    representation (TaxInvoice) by design.
    """

    def __init__(
        self,
        id: Optional[int] = None,
        uuid: Optional[str] = None,
        company_id: Optional[int] = None,
        import_batch_id: Optional[int] = None,
        invoice_number: Optional[str] = None,
        invoice_type: str = "sales",
        invoice_date: Optional[date] = None,
        due_date: Optional[date] = None,
        currency: str = "EGP",
        counterparty_name: Optional[str] = None,
        counterparty_tax_id: Optional[str] = None,
        counterparty_email: Optional[str] = None,
        subtotal_amount: float = 0.0,
        discount_amount: float = 0.0,
        vat_amount: float = 0.0,
        total_amount: float = 0.0,
        status: str = "draft",
        items: Optional[List[InvoiceItem]] = None,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None
    ) -> None:
        self.id = id
        self.uuid = uuid
        self.company_id = company_id
        self.import_batch_id = import_batch_id
        self.invoice_number = invoice_number
        self.invoice_type = invoice_type
        self.invoice_date = invoice_date
        self.due_date = due_date
        self.currency = currency
        self.counterparty_name = counterparty_name
        self.counterparty_tax_id = counterparty_tax_id
        self.counterparty_email = counterparty_email
        self.subtotal_amount = subtotal_amount
        self.discount_amount = discount_amount
        self.vat_amount = vat_amount
        self.total_amount = total_amount
        self.status = status
        self.items = items if items is not None else []
        self.created_at = created_at or datetime.now()
        self.updated_at = updated_at or datetime.now()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "uuid": self.uuid,
            "company_id": self.company_id,
            "import_batch_id": self.import_batch_id,
            "invoice_number": self.invoice_number,
            "invoice_type": self.invoice_type,
            "invoice_date": self.invoice_date.isoformat() if self.invoice_date else None,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "currency": self.currency,
            "counterparty_name": self.counterparty_name,
            "counterparty_tax_id": self.counterparty_tax_id,
            "counterparty_email": self.counterparty_email,
            "subtotal_amount": float(self.subtotal_amount),
            "discount_amount": float(self.discount_amount),
            "vat_amount": float(self.vat_amount),
            "total_amount": float(self.total_amount),
            "status": self.status,
            "items": [item.to_dict() for item in self.items],
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Invoice":
        return cls(
            id=data.get("id"),
            uuid=data.get("uuid"),
            company_id=data.get("company_id"),
            import_batch_id=data.get("import_batch_id"),
            invoice_number=data.get("invoice_number"),
            invoice_type=data.get("invoice_type", "sales"),
            invoice_date=_parse_date(data.get("invoice_date")),
            due_date=_parse_date(data.get("due_date")),
            currency=data.get("currency", "EGP"),
            counterparty_name=data.get("counterparty_name"),
            counterparty_tax_id=data.get("counterparty_tax_id"),
            counterparty_email=data.get("counterparty_email"),
            subtotal_amount=data.get("subtotal_amount", 0.0),
            discount_amount=data.get("discount_amount", 0.0),
            vat_amount=data.get("vat_amount", 0.0),
            total_amount=data.get("total_amount", 0.0),
            status=data.get("status", "draft"),
            items=[InvoiceItem.from_dict(item) for item in (data.get("items") or [])],
            created_at=_parse_datetime(data.get("created_at")),
            updated_at=_parse_datetime(data.get("updated_at"))
        )

    def __str__(self) -> str:
        return f"Invoice(id={self.id}, number={self.invoice_number}, company={self.company_id})"

    def __repr__(self) -> str:
        return self.__str__()