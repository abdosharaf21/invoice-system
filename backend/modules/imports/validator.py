"""Semantic validation for imported rows and invoice groups.

Field-level normalization (required values, types, formats) happens in
the normalizer. This layer adds the *semantic* checks that only make
sense once values are typed, and the invoice-level checks that apply to
a whole group of line items:

* line totals must not be negative,
* a discount cannot exceed the line subtotal,
* VAT rates must be between 0% and 100%,
* currency must be a three-letter code.

Rows and groups that fail are reported with structured
:class:`ImportErrorInfo` objects and skipped during persistence.
"""

from typing import Any, Dict, List

from decimal import Decimal

from backend.modules.imports.grouping import InvoiceGroup
from backend.modules.imports.normalizer import parse_money
from backend.modules.imports.errors import (
    E_INVALID_MONEY,
    E_INVALID_ENUM,
    E_INVALID_QUANTITY,
    ImportErrorInfo,
)

HUNDRED = Decimal("100")


def validate_row(row_number: int, normalized: Dict[str, Any]) -> List[ImportErrorInfo]:
    """Validate the semantic invariants of one normalized line item."""
    errors: List[ImportErrorInfo] = []

    quantity = normalized.get("quantity")
    if quantity is not None and quantity <= 0:
        errors.append(ImportErrorInfo(
            row_number=row_number,
            field="quantity",
            error_code=E_INVALID_QUANTITY,
            message="Quantity must be greater than zero.",
        ))

    unit_price = normalized.get("unit_price")
    if unit_price is not None and unit_price < 0:
        errors.append(ImportErrorInfo(
            row_number=row_number,
            field="unit_price",
            error_code=E_INVALID_MONEY,
            message="Unit price cannot be negative.",
        ))

    discount = normalized.get("item_discount_amount")
    subtotal = _item_subtotal(normalized)
    if discount is None:
        discount = 0
    if discount < 0:
        errors.append(ImportErrorInfo(
            row_number=row_number,
            field="item_discount_amount",
            error_code=E_INVALID_MONEY,
            message="Discount cannot be negative.",
        ))
    elif subtotal is not None and discount > subtotal:
        errors.append(ImportErrorInfo(
            row_number=row_number,
            field="item_discount_amount",
            error_code=E_INVALID_MONEY,
            message="Line discount cannot exceed the line subtotal.",
        ))

    vat_rate = normalized.get("vat_rate")
    if vat_rate is not None and (vat_rate < 0 or vat_rate > HUNDRED):
        errors.append(ImportErrorInfo(
            row_number=row_number,
            field="vat_rate",
            error_code=E_INVALID_ENUM,
            message="VAT rate must be between 0 and 100 percent.",
        ))

    return errors


def validate_group(group: InvoiceGroup) -> List[ImportErrorInfo]:
    """Validate invoice-level invariants for a group."""
    errors: List[ImportErrorInfo] = list(group.errors)
    invoice_values = group.invoice_values

    currency = invoice_values.get("currency")
    if currency is not None and not _is_valid_currency(currency):
        errors.append(ImportErrorInfo(
            row_number=group.first_row,
            field="currency",
            error_code=E_INVALID_ENUM,
            message=f"'{currency}' is not a valid three-letter currency code.",
        ))

    if not group.item_values:
        errors.append(ImportErrorInfo(
            row_number=group.first_row,
            field="item_description",
            error_code=E_INVALID_QUANTITY,
            message="Invoice group has no line items.",
        ))

    return errors


def _item_subtotal(normalized: Dict[str, Any]) -> Decimal:
    unit_price = normalized.get("unit_price")
    if unit_price is None:
        return Decimal("0")
    return unit_price * normalized.get("quantity", Decimal("1"))


def _is_valid_currency(value: Any) -> bool:
    text = str(value or "").strip()
    return len(text) == 3 and text.isalpha() and text.isupper()