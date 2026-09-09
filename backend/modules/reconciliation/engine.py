"""Reconciliation engine: deterministic matching and field comparison.

The engine is a pure module: it holds no database or HTTP dependencies. It
receives accounting invoices and tax authority invoices (each with their
line items) and returns a ReconcileOutcome with per-invoice
ReconciliationResult rows and machine-readable ReconciliationError rows.

Matching strategy
-----------------

Identity matching is strict and hierarchical (see ``contract.py``):

1. When an accounting invoice has a valid UUID, it matches only the tax
   authority invoice carrying that same normalized UUID.
2. When an accounting invoice has no UUID, its ``invoice_number`` is matched
   against the tax authority ``internal_id`` (scoped to the same company).
3. An accounting invoice whose UUID is present but malformed cannot be
   trusted, so it is classified INVALID instead of being guessed.

An invoice with no counterpart on the other side is classified
MISSING_IN_TAX_AUTHORITY or EXTRA_IN_TAX_AUTHORITY accordingly, so the engine
is two-sided. All lookups are O(1) dictionary lookups (UUID and internal_id
indexes), never an O(n²) scan.

Money policy
------------

All money is Decimal. Values are compared with exact equality unless an
explicit ``money_tolerance`` is supplied. The difference is always stored on
the error row and the result's discrepancy_amount.

Date policy
-----------

Invoice dates are compared at date granularity. The tax authority store is a
DATETIME (issue_datetime); its time component and a hypothetical timezone do
not participate in comparison — the schema persists neither a timezone nor
timed issue times for the accounting side.
"""

import re
from dataclasses import dataclass, field as dataclass_field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, List, Optional

from backend.modules.reconciliation import contract as c
from backend.modules.reconciliation.model import (
    ReconciliationError,
    ReconciliationResult,
)

_TWO = Decimal("0.01")

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


@dataclass
class ReconcileOutcome:
    """Deterministic outcomes of one reconciliation over two datasets."""

    results: List[ReconciliationResult] = dataclass_field(default_factory=list)
    errors: List[ReconciliationError] = dataclass_field(default_factory=list)


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------


def normalize_uuid(value: Optional[str]) -> Optional[str]:
    """Normalize a UUID to lowercase canonical form (or None)."""
    if value is None:
        return None
    text = str(value).strip().strip("{}").lower()
    return text or None


def is_valid_uuid(value: Optional[str]) -> bool:
    return bool(value) and _UUID_RE.match(str(value)) is not None


def normalize_period(period: str) -> str:
    """Normalize a 'YYYY-MM' period string, stripping whitespace."""
    return str(period or "").strip()


def is_valid_period(period: str) -> bool:
    """Return whether the string is a valid 'YYYY-MM' accounting period."""
    value = normalize_period(period)
    if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", value):
        return False
    year = int(value[:4])
    return 1900 <= year <= 2200


def _q2(value: Decimal) -> Decimal:
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(_TWO, rounding=ROUND_HALF_UP)


def _to_decimal(value) -> Optional[Decimal]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value).strip())
    except Exception:
        return None


def _to_date(value) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError:
        return None


def _fmt_date(value: Optional[date]) -> Optional[str]:
    result = _to_date(value)
    return result.isoformat() if result else None


def _fmt_money(value) -> str:
    dec = _to_decimal(value)
    return f"{_q2(dec):.2f}" if dec is not None else ""


def _norm_text(value: Optional[str]) -> str:
    if value is None:
        return ""
    return str(value).strip().upper()


# ---------------------------------------------------------------------------
# Error builders
# ---------------------------------------------------------------------------


def _error(
    entity_id: Optional[int],
    source_type: str,
    error_type: str,
    field: Optional[str],
    accounting_value,
    tax_authority_value,
    difference,
    message: str,
) -> ReconciliationError:
    return ReconciliationError(
        source_type=source_type,
        entity_id=entity_id,
        error_type=error_type,
        field=field,
        accounting_value=accounting_value,
        tax_authority_value=tax_authority_value,
        difference=difference,
        message=message,
    )


def _money_error(
    entity_id: int,
    source_type: str,
    error_type: str,
    field: str,
    acc_value,
    tax_value,
    tolerance: Decimal,
) -> Optional[ReconciliationError]:
    acc = _to_decimal(acc_value)
    tax = _to_decimal(tax_value)
    if acc is None or tax is None:
        return _error(
            entity_id, source_type, c.E_INVALID_FINANCIAL_VALUE, field,
            str(acc_value) if acc_value is not None else None,
            str(tax_value) if tax_value is not None else None,
            None,
            f"{field}: a financial value could not be interpreted.",
        )
    if abs(acc - tax) <= tolerance:
        return None
    return _error(
        entity_id, source_type, error_type, field,
        _fmt_money(acc), _fmt_money(tax), _q2(acc - tax),
        f"{field} differs: accounting {_fmt_money(acc)}, "
        f"tax authority {_fmt_money(tax)}.",
    )


def _text_error(
    entity_id: int,
    source_type: str,
    error_type: str,
    field: str,
    acc_value,
    tax_value,
    message: str,
) -> ReconciliationError:
    return _error(
        entity_id, source_type, error_type, field,
        str(acc_value) if acc_value is not None else None,
        str(tax_value) if tax_value is not None else None,
        None,
        message,
    )


# ---------------------------------------------------------------------------
# Matching machinery
# ---------------------------------------------------------------------------


def _index_tax_invoices(tax_invoices) -> tuple:
    """Build O(1) lookup indexes: normalized UUID and company+internal_id."""
    by_uuid: Dict[str, object] = {}
    by_internal: Dict[tuple, object] = {}
    ordered = sorted(
        tax_invoices,
        key=lambda t: (str(t.issue_datetime or ""), t.id or 0),
    )
    for tax in ordered:
        uuid = normalize_uuid(getattr(tax, "uuid", None))
        if uuid is not None and is_valid_uuid(uuid):
            by_uuid.setdefault(uuid, tax)
        internal_id = getattr(tax, "internal_id", None)
        if internal_id:
            key = (tax.company_id, str(internal_id).strip().lower())
            by_internal.setdefault(key, tax)
    return by_uuid, by_internal


def _match_account(
    invoice,
    by_uuid: Dict[str, object],
    by_internal: Dict[tuple, object],
    tolerance: Decimal,
) -> tuple:
    """Produce (result, errors, claimed_tax_id) for one accounting invoice."""
    uuid = normalize_uuid(getattr(invoice, "uuid", None))

    if uuid is not None and not is_valid_uuid(uuid):
        error = _error(
            invoice.id, "account", c.E_INVALID_UUID, "uuid",
            invoice.uuid, None, None,
            f"Invoice '{invoice.invoice_number}' has an invalid UUID "
            f"'{invoice.uuid}'; identity cannot be trusted.",
        )
        return _result(account=invoice.id, status=c.INVALID), [error], None

    tax = None
    if uuid is not None:
        tax = by_uuid.get(uuid)
    else:
        number = str(invoice.invoice_number or "").strip().lower()
        if number:
            tax = by_internal.get((invoice.company_id, number))

    if tax is None:
        return _result(account=invoice.id, status=c.MISSING_IN_TAX_AUTHORITY), [], None

    errors = _compare(invoice, tax, tolerance)
    status = c.MATCHED if not errors else c.MISMATCHED
    discrepancy = _q2(
        (_to_decimal(invoice.total_amount) or Decimal("0.00"))
        - (_to_decimal(tax.total_amount) or Decimal("0.00"))
    )
    notes = None
    if errors:
        notes = "Mismatched fields: " + ", ".join(
            e.field for e in errors if e.field
        )
    return (
        _result(
            account=invoice.id,
            tax=tax.id,
            status=status,
            discrepancy=discrepancy,
            notes=notes,
        ),
        errors,
        tax.id,
    )


def _classify_unclaimed_tax(tax_invoice) -> tuple:
    """Produce (result, errors) for a tax invoice no accounting invoice matched."""
    uuid = normalize_uuid(getattr(tax_invoice, "uuid", None))
    if uuid is not None and not is_valid_uuid(uuid):
        error = _error(
            tax_invoice.id, "tax", c.E_INVALID_UUID, "uuid",
            None, tax_invoice.uuid, None,
            f"Tax invoice (id={tax_invoice.id}) has an invalid UUID "
            f"'{tax_invoice.uuid}'; identity cannot be trusted.",
        )
        return _result(tax=tax_invoice.id, status=c.INVALID), [error]
    return _result(tax=tax_invoice.id, status=c.EXTRA_IN_TAX_AUTHORITY), []


def _result(
    account: Optional[int] = None,
    tax: Optional[int] = None,
    status: str = None,
    discrepancy: Decimal = Decimal("0.00"),
    notes: Optional[str] = None,
) -> ReconciliationResult:
    return ReconciliationResult(
        account_invoice_id=account,
        tax_invoice_id=tax,
        match_status=status,
        discrepancy_amount=discrepancy,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Field-level comparison
# ---------------------------------------------------------------------------


def _compare(invoice, tax_invoice, tolerance: Decimal) -> List[ReconciliationError]:
    """Compare a matched pair field by field. Returns the mismatch errors."""
    errors: List[ReconciliationError] = []

    _compare_date(errors, invoice, tax_invoice)
    _compare_currency(errors, invoice, tax_invoice)
    _compare_amounts(errors, invoice, tax_invoice, tolerance)
    _compare_party(errors, invoice, tax_invoice)
    _compare_items(errors, invoice, tax_invoice, tolerance)

    return errors


def _compare_date(errors, invoice, tax_invoice) -> None:
    acc_date = _to_date(getattr(invoice, "invoice_date", None))
    tax_date = _to_date(getattr(tax_invoice, "issue_datetime", None))

    if tax_date is None:
        errors.append(_error(
            invoice.id, "account", c.E_INVALID_DATE, "invoice_date",
            _fmt_date(acc_date), None, None,
            "invoice_date: the tax authority issue date could not be read.",
        ))
        return
    if acc_date is None:
        errors.append(_error(
            invoice.id, "account", c.E_INVALID_DATE, "invoice_date",
            None, tax_date.isoformat(), None,
            "invoice_date: the accounting invoice date could not be read.",
        ))
        return
    if acc_date != tax_date:
        errors.append(_text_error(
            invoice.id, "account", c.E_INVOICE_DATE_MISMATCH, "invoice_date",
            acc_date.isoformat(), tax_date.isoformat(),
            "invoice_date differs: accounting "
            f"{acc_date.isoformat()}, tax authority {tax_date.isoformat()}.",
        ))


def _compare_currency(errors, invoice, tax_invoice) -> None:
    acc = _norm_text(getattr(invoice, "currency", ""))
    tax = _norm_text(getattr(tax_invoice, "currency", ""))
    if acc != tax:
        errors.append(_text_error(
            invoice.id, "account", c.E_CURRENCY_MISMATCH, "currency",
            acc or None, tax or None,
            "currency differs: accounting "
            f"{acc or '<empty>'}, tax authority {tax or '<empty>'}.",
        ))


def _compare_amounts(errors, invoice, tax_invoice, tolerance) -> None:
    money_checks = (
        (c.E_SUBTOTAL_AMOUNT_MISMATCH, "subtotal_amount",
         getattr(invoice, "subtotal_amount", None),
         getattr(tax_invoice, "total_sales", None)),
        (c.E_DISCOUNT_AMOUNT_MISMATCH, "discount_amount",
         getattr(invoice, "discount_amount", None),
         getattr(tax_invoice, "total_discount", None)),
        (c.E_VAT_AMOUNT_MISMATCH, "vat_amount",
         getattr(invoice, "vat_amount", None),
         getattr(tax_invoice, "vat_amount", None)),
        (c.E_TOTAL_AMOUNT_MISMATCH, "total_amount",
         getattr(invoice, "total_amount", None),
         getattr(tax_invoice, "total_amount", None)),
    )
    for code, field, acc_value, tax_value in money_checks:
        error = _money_error(
            invoice.id, "account", code, field, acc_value, tax_value, tolerance
        )
        if error is not None:
            errors.append(error)

    net_error = _money_error(
        invoice.id, "account", c.E_NET_AMOUNT_MISMATCH, "net_amount",
        _net_amount(invoice), getattr(tax_invoice, "net_amount", None),
        tolerance,
    )
    if net_error is not None:
        errors.append(net_error)


def _net_amount(invoice) -> Decimal:
    subtotal = _to_decimal(getattr(invoice, "subtotal_amount", None))
    discount = _to_decimal(getattr(invoice, "discount_amount", None))
    if subtotal is None or discount is None:
        return None
    return _q2(subtotal - discount)


def _compare_party(errors, invoice, tax_invoice) -> None:
    acc_tin = _norm_text(getattr(invoice, "counterparty_tax_id", None))
    buyer_tin = _norm_text(getattr(tax_invoice, "buyer_tax_id", None))
    seller_tin = _norm_text(getattr(tax_invoice, "seller_tax_id", None))

    if acc_tin:
        if buyer_tin and buyer_tin == acc_tin:
            _compare_party_name(errors, invoice.id,
                                getattr(invoice, "counterparty_name", None),
                                getattr(tax_invoice, "buyer_name", None))
            return
        if seller_tin and seller_tin == acc_tin:
            _compare_party_name(errors, invoice.id,
                                getattr(invoice, "counterparty_name", None),
                                getattr(tax_invoice, "seller_name", None))
            return
        buyer = getattr(tax_invoice, "buyer_tax_id", None) or ""
        seller = getattr(tax_invoice, "seller_tax_id", None) or ""
        errors.append(_text_error(
            invoice.id, "account", c.E_COUNTERPARTY_TAX_ID_MISMATCH,
            "counterparty_tax_id",
            getattr(invoice, "counterparty_tax_id", None),
            (buyer or seller) or None,
            "counterparty_tax_id matches neither the buyer nor the seller "
            "tax identification on the tax authority document.",
        ))
        return

    acc_name = _norm_text(getattr(invoice, "counterparty_name", None))
    buyer_name = _norm_text(getattr(tax_invoice, "buyer_name", None))
    seller_name = _norm_text(getattr(tax_invoice, "seller_name", None))
    if acc_name and acc_name not in (buyer_name, seller_name):
        errors.append(_text_error(
            invoice.id, "account", c.E_COUNTERPARTY_NAME_MISMATCH,
            "counterparty_name",
            getattr(invoice, "counterparty_name", None),
            "buyer=" + (getattr(tax_invoice, "buyer_name", None) or "-")
            + " / seller=" + (getattr(tax_invoice, "seller_name", None) or "-"),
            "counterparty_name does not match the buyer or seller name "
            "on the tax authority document, and no counterparty tax "
            "identification was provided to disambiguate the direction.",
        ))


def _compare_party_name(errors, entity_id, acc_name, tax_name) -> None:
    acc = _norm_text(acc_name)
    tax = _norm_text(tax_name)
    if acc != tax:
        errors.append(_text_error(
            entity_id, "account", c.E_COUNTERPARTY_NAME_MISMATCH,
            "counterparty_name", acc_name, tax_name,
            "counterparty_name differs: accounting "
            f"{acc_name or '<empty>'}, tax authority {tax_name or '<empty>'}.",
        ))


def _compare_items(errors, invoice, tax_invoice, tolerance) -> None:
    items = invoice.items or []
    tax_items = tax_invoice.items or []

    if len(items) != len(tax_items):
        errors.append(_text_error(
            invoice.id, "account", c.E_ITEM_COUNT_MISMATCH, "items",
            len(items), len(tax_items),
            f"items count differs: accounting {len(items)}, "
            f"tax authority {len(tax_items)}.",
        ))

    acc_qty = sum((_to_decimal(getattr(it, "quantity", None)) or Decimal("0"))
                  for it in items)
    tax_qty = sum((_to_decimal(getattr(it, "quantity", None)) or Decimal("0"))
                  for it in tax_items)
    if acc_qty != tax_qty:
        errors.append(_mass_error(
            invoice.id, c.E_ITEM_QUANTITY_SUM_MISMATCH, "items",
            f"{acc_qty:.4f}", f"{tax_qty:.4f}",
            f"items quantity sum differs: accounting {acc_qty:.4f}, "
            f"tax authority {tax_qty:.4f}.",
        ))

    acc_vat = sum((_to_decimal(getattr(it, "vat_amount", None)) or Decimal("0"))
                  for it in items)
    tax_vat = sum((_to_decimal(getattr(it, "vat_amount", None)) or Decimal("0"))
                  for it in tax_items)
    if abs(acc_vat - tax_vat) > tolerance:
        errors.append(_money_error(
            invoice.id, "account", c.E_ITEM_VAT_SUM_MISMATCH, "items",
            _q2(acc_vat), _q2(tax_vat), tolerance,
        ))

    acc_total = sum((_to_decimal(getattr(it, "line_total", None)) or Decimal("0"))
                    for it in items)
    tax_total = sum((_to_decimal(getattr(it, "total_amount", None)) or Decimal("0"))
                    for it in tax_items)
    if abs(acc_total - tax_total) > tolerance:
        errors.append(_money_error(
            invoice.id, "account", c.E_ITEM_TOTAL_SUM_MISMATCH, "items",
            _q2(acc_total), _q2(tax_total), tolerance,
        ))


def _mass_error(entity_id, error_type, field, acc_value, tax_value, message):
    return _error(
        entity_id, "account", error_type, field,
        acc_value, tax_value, None, message,
    )


# ---------------------------------------------------------------------------
# Public engine entry point
# ---------------------------------------------------------------------------


def reconcile(
    account_invoices=None,
    tax_invoices=None,
    money_tolerance: Optional[Decimal] = None,
) -> ReconcileOutcome:
    """Reconcile accounting invoices against tax authority invoices.

    Args:
        account_invoices: Accounting Invoice objects (without items is fine;
            item aggregates are computed from whatever items are attached).
        tax_invoices: TaxInvoice objects.
        money_tolerance: Optional tolerance for money comparisons. Defaults to
            exact equality (Decimal("0.00")).

    Returns:
        A ReconcileOutcome with results and errors. The engine never raises
        for malformed input rows; it classifies or reports them instead.
    """
    tolerance = money_tolerance if money_tolerance is not None else c.DEFAULT_MONEY_TOLERANCE

    accounts = sorted(
        account_invoices or [],
        key=lambda inv: (str(getattr(inv, "invoice_date", None) or ""), inv.id or 0),
    )
    by_uuid, by_internal = _index_tax_invoices(tax_invoices or [])

    claimed_tax_ids = set()
    outcome = ReconcileOutcome()

    for invoice in accounts:
        result, errors, claimed = _match_account(
            invoice, by_uuid, by_internal, tolerance
        )
        outcome.results.append(result)
        outcome.errors.extend(errors)
        if claimed is not None:
            claimed_tax_ids.add(claimed)

    for tax in sorted(
        tax_invoices or [],
        key=lambda t: (str(getattr(t, "issue_datetime", None) or ""), t.id or 0),
    ):
        if tax.id in claimed_tax_ids:
            continue
        result, errors = _classify_unclaimed_tax(tax)
        outcome.results.append(result)
        outcome.errors.extend(errors)

    return outcome