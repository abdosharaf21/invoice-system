"""Tax authority models representing the tax_invoices and tax_invoice_items tables."""

from datetime import datetime
from typing import List, Optional


def _parse_datetime(value):
    if value and isinstance(value, str):
        return datetime.fromisoformat(value)
    return value


class TaxInvoiceItem:
    """Represents a single line item on a tax authority invoice."""

    def __init__(
        self,
        id: Optional[int] = None,
        tax_invoice_id: Optional[int] = None,
        description: Optional[str] = None,
        item_type: str = "composite",
        quantity: float = 1.0,
        unit_value: float = 0.0,
        vat_rate: float = 0.0,
        vat_amount: float = 0.0,
        discount_amount: float = 0.0,
        total_amount: float = 0.0,
        created_at: Optional[datetime] = None
    ) -> None:
        self.id = id
        self.tax_invoice_id = tax_invoice_id
        self.description = description
        self.item_type = item_type
        self.quantity = quantity
        self.unit_value = unit_value
        self.vat_rate = vat_rate
        self.vat_amount = vat_amount
        self.discount_amount = discount_amount
        self.total_amount = total_amount
        self.created_at = created_at or datetime.now()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tax_invoice_id": self.tax_invoice_id,
            "description": self.description,
            "item_type": self.item_type,
            "quantity": float(self.quantity),
            "unit_value": float(self.unit_value),
            "vat_rate": float(self.vat_rate),
            "vat_amount": float(self.vat_amount),
            "discount_amount": float(self.discount_amount),
            "total_amount": float(self.total_amount),
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TaxInvoiceItem":
        return cls(
            id=data.get("id"),
            tax_invoice_id=data.get("tax_invoice_id"),
            description=data.get("description"),
            item_type=data.get("item_type", "composite"),
            quantity=data.get("quantity", 1.0),
            unit_value=data.get("unit_value", 0.0),
            vat_rate=data.get("vat_rate", 0.0),
            vat_amount=data.get("vat_amount", 0.0),
            discount_amount=data.get("discount_amount", 0.0),
            total_amount=data.get("total_amount", 0.0),
            created_at=_parse_datetime(data.get("created_at"))
        )

    def __repr__(self) -> str:
        return f"TaxInvoiceItem(id={self.id}, description={self.description!r})"


class TaxInvoice:
    """Represents an E-Invoice document in the tax_invoices table.

    Mirrors the documents exchanged with the tax authority and is kept
    separate from the accounting side (Invoice). Account invoices are
    linked via account_invoice_id so the two representations can be
    reconciled.
    """

    def __init__(
        self,
        id: Optional[int] = None,
        company_id: Optional[int] = None,
        account_invoice_id: Optional[int] = None,
        import_batch_id: Optional[int] = None,
        uuid: Optional[str] = None,
        internal_id: Optional[str] = None,
        document_type: str = "invoice",
        issue_datetime: Optional[datetime] = None,
        currency: str = "EGP",
        exchange_rate: float = 1.0,
        seller_name: Optional[str] = None,
        seller_tax_id: Optional[str] = None,
        buyer_name: Optional[str] = None,
        buyer_tax_id: Optional[str] = None,
        total_sales: float = 0.0,
        total_discount: float = 0.0,
        net_amount: float = 0.0,
        vat_amount: float = 0.0,
        other_charges: float = 0.0,
        total_amount: float = 0.0,
        submission_status: str = "draft",
        submission_errors: Optional[str] = None,
        items: Optional[List[TaxInvoiceItem]] = None,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None
    ) -> None:
        self.id = id
        self.company_id = company_id
        self.account_invoice_id = account_invoice_id
        self.import_batch_id = import_batch_id
        self.uuid = uuid
        self.internal_id = internal_id
        self.document_type = document_type
        self.issue_datetime = issue_datetime
        self.currency = currency
        self.exchange_rate = exchange_rate
        self.seller_name = seller_name
        self.seller_tax_id = seller_tax_id
        self.buyer_name = buyer_name
        self.buyer_tax_id = buyer_tax_id
        self.total_sales = total_sales
        self.total_discount = total_discount
        self.net_amount = net_amount
        self.vat_amount = vat_amount
        self.other_charges = other_charges
        self.total_amount = total_amount
        self.submission_status = submission_status
        self.submission_errors = submission_errors
        self.items = items if items is not None else []
        self.created_at = created_at or datetime.now()
        self.updated_at = updated_at or datetime.now()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "company_id": self.company_id,
            "account_invoice_id": self.account_invoice_id,
            "import_batch_id": self.import_batch_id,
            "uuid": self.uuid,
            "internal_id": self.internal_id,
            "document_type": self.document_type,
            "issue_datetime": self.issue_datetime.isoformat() if self.issue_datetime else None,
            "currency": self.currency,
            "exchange_rate": float(self.exchange_rate),
            "seller_name": self.seller_name,
            "seller_tax_id": self.seller_tax_id,
            "buyer_name": self.buyer_name,
            "buyer_tax_id": self.buyer_tax_id,
            "total_sales": float(self.total_sales),
            "total_discount": float(self.total_discount),
            "net_amount": float(self.net_amount),
            "vat_amount": float(self.vat_amount),
            "other_charges": float(self.other_charges),
            "total_amount": float(self.total_amount),
            "submission_status": self.submission_status,
            "submission_errors": self.submission_errors,
            "items": [item.to_dict() for item in self.items],
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TaxInvoice":
        return cls(
            id=data.get("id"),
            company_id=data.get("company_id"),
            account_invoice_id=data.get("account_invoice_id"),
            import_batch_id=data.get("import_batch_id"),
            uuid=data.get("uuid"),
            internal_id=data.get("internal_id"),
            document_type=data.get("document_type", "invoice"),
            issue_datetime=_parse_datetime(data.get("issue_datetime")),
            currency=data.get("currency", "EGP"),
            exchange_rate=data.get("exchange_rate", 1.0),
            seller_name=data.get("seller_name"),
            seller_tax_id=data.get("seller_tax_id"),
            buyer_name=data.get("buyer_name"),
            buyer_tax_id=data.get("buyer_tax_id"),
            total_sales=data.get("total_sales", 0.0),
            total_discount=data.get("total_discount", 0.0),
            net_amount=data.get("net_amount", 0.0),
            vat_amount=data.get("vat_amount", 0.0),
            other_charges=data.get("other_charges", 0.0),
            total_amount=data.get("total_amount", 0.0),
            submission_status=data.get("submission_status", "draft"),
            submission_errors=data.get("submission_errors"),
            items=[TaxInvoiceItem.from_dict(item) for item in (data.get("items") or [])],
            created_at=_parse_datetime(data.get("created_at")),
            updated_at=_parse_datetime(data.get("updated_at"))
        )

    def __str__(self) -> str:
        return f"TaxInvoice(id={self.id}, uuid={self.uuid}, company={self.company_id})"

    def __repr__(self) -> str:
        return self.__str__()