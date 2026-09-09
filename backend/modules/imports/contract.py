"""Canonical contract for accounting file imports.

Defines the single, canonical schema that every imported source file
(CSV or XLSX) is translated into. Files may name their columns whatever
they like; header aliases map source headers onto canonical fields.
Unknown headers are ignored and never fail the import. Required headers
that are missing fail the import before any data is processed.

Canonical field kinds decide how values are normalized:

* ``uuid``     - UUID v4-v5 style, stored lower-case dashed
* ``string``   - trimmed text
* ``enum``     - one of ``allowed`` values (case-insensitive)
* ``date``     - calendar date
* ``money``    - exact decimal, rounded to 2 places
* ``quantity`` - exact decimal, rounded to 4 places
"""

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, Optional, Set

INVOICE_TYPES = {"sales", "purchase", "credit_note", "debit_note"}
DEFAULT_CURRENCY = "EGP"
DEFAULT_INVOICE_STATUS = "draft"
DEFAULT_INVOICE_TYPE = "sales"
DEFAULT_QUANTITY = Decimal("1")
DEFAULT_MONEY_ZERO = Decimal("0")

IMPORT_SOURCE_FILE = "file"
IMPORT_SOURCE_MANUAL = "manual"

BATCH_STATUSES = {"uploaded", "processing", "completed", "failed"}

UPLOAD_EXTENSIONS = {".csv", ".xlsx"}
UPLOAD_MIME_TYPES = {
    "text/csv",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "application/octet-stream",
}

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB, matches MAX_CONTENT_LENGTH


@dataclass(frozen=True)
class FieldSpec:
    """Describes how a single canonical field is normalized."""

    kind: str
    required: bool = False
    default: Any = None
    allowed: Optional[Set[str]] = None


CONTRACT: Dict[str, FieldSpec] = {
    "uuid": FieldSpec(kind="uuid"),
    "invoice_number": FieldSpec(kind="string", required=True),
    "invoice_type": FieldSpec(
        kind="enum", allowed=INVOICE_TYPES, default=DEFAULT_INVOICE_TYPE
    ),
    "invoice_date": FieldSpec(kind="date", required=True),
    "due_date": FieldSpec(kind="date"),
    "currency": FieldSpec(kind="string", default=DEFAULT_CURRENCY),
    "counterparty_name": FieldSpec(kind="string", required=True),
    "counterparty_tax_id": FieldSpec(kind="string"),
    "item_description": FieldSpec(kind="string", required=True),
    "quantity": FieldSpec(kind="quantity", default=DEFAULT_QUANTITY),
    "unit_price": FieldSpec(kind="money", default=DEFAULT_MONEY_ZERO),
    "item_discount_amount": FieldSpec(kind="money", default=DEFAULT_MONEY_ZERO),
    "vat_rate": FieldSpec(kind="money", default=DEFAULT_MONEY_ZERO),
    "vat_amount": FieldSpec(kind="money"),
    "line_total": FieldSpec(kind="money"),
}

REQUIRED_FIELDS = (
    "invoice_number",
    "invoice_date",
    "counterparty_name",
    "item_description",
)

INVOICE_LEVEL_FIELDS = (
    "uuid",
    "invoice_number",
    "invoice_type",
    "invoice_date",
    "due_date",
    "currency",
    "counterparty_name",
    "counterparty_tax_id",
)

ITEM_LEVEL_FIELDS = (
    "item_description",
    "quantity",
    "unit_price",
    "item_discount_amount",
    "vat_rate",
    "vat_amount",
    "line_total",
)

_RAW_ALIASES: Dict[str, list] = {
    "uuid": ["uuid", "invoice_uuid", "document_uuid"],
    "invoice_number": [
        "invoice_number",
        "invoice_no",
        "invoice#",
        "no.",
        "number",
        "doc_number",
        "document_number",
    ],
    "invoice_type": ["invoice_type", "type", "document_type", "invoice_kind"],
    "invoice_date": ["invoice_date", "date", "issue_date", "document_date"],
    "due_date": ["due_date", "payment_due_date", "payment_date"],
    "currency": ["currency", "currency_code"],
    "counterparty_name": [
        "counterparty_name",
        "counterparty",
        "customer_name",
        "customer",
        "client_name",
        "client",
        "supplier_name",
        "supplier",
        "vendor_name",
        "vendor",
        "buyer_name",
        "partner_name",
    ],
    "counterparty_tax_id": [
        "counterparty_tax_id",
        "customer_tax_id",
        "supplier_tax_id",
        "vendor_tax_id",
        "tax_id",
    ],
    "item_description": [
        "item_description",
        "description",
        "item_name",
        "product_name",
        "service_name",
        "goods_description",
    ],
    "quantity": ["quantity", "qty", "quantity_"],
    "unit_price": [
        "unit_price",
        "price",
        "unit_cost",
        "unit_price_excl_vat",
        "unitprice",
    ],
    "item_discount_amount": [
        "item_discount_amount",
        "discount_amount",
        "discount",
        "line_discount_amount",
    ],
    "vat_rate": ["vat_rate", "tax_rate", "vat_percent"],
    "vat_amount": ["vat_amount", "tax_amount"],
    "line_total": ["line_total", "total", "gross_amount", "line_total_amount", "amount"],
}

HEADER_ALIASES: Dict[str, str] = {}


def normalize_header(value: Any) -> str:
    """Normalize a header/cell label for alias matching.

    Lower-cases, treats ``#`` as the word ``no`` and collapses every run
    of non-alphanumeric characters into a single underscore, e.g.
    ``"Invoice  #"`` becomes ``invoice_no``.
    """
    text = str(value or "").strip().lower()
    text = text.replace("#", " no ")
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text


def _build_header_aliases() -> None:
    for canonical, aliases in _RAW_ALIASES.items():
        for alias in aliases:
            key = normalize_header(alias)
            HEADER_ALIASES[key] = canonical


_build_header_aliases()


def resolve_header(header: Any) -> Optional[str]:
    """Map a raw header value to its canonical field name, if known."""
    return HEADER_ALIASES.get(normalize_header(header))