"""Engine tests: matching, field comparison, error generation and determinism.

The engine is pure — these tests build Invoice/TaxInvoice model instances
directly and assert on the resulting results/errors without any HTTP or DB.
"""

import uuid as _uuid
from datetime import date, datetime
from decimal import Decimal

from backend.modules.invoices.model import Invoice, InvoiceItem
from backend.modules.reconciliation import contract as c
from backend.modules.reconciliation.engine import reconcile
from backend.modules.tax_authority.model import TaxInvoice, TaxInvoiceItem


def _fresh_uuid(seed):
    """Deterministic valid UUID derived from a seed string."""
    return str(_uuid.uuid5(_uuid.NAMESPACE_URL, seed))


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _invoice(
    id=None,
    uuid=None,
    number="INV-1",
    company=1,
    invoice_date=date(2024, 3, 1),
    currency="EGP",
    subtotal=Decimal("100.00"),
    discount=Decimal("0.00"),
    vat=Decimal("14.00"),
    total=Decimal("114.00"),
    counterparty="Acme Corp",
    tin=None,
    items=None,
):
    return Invoice(
        id=id,
        uuid=uuid,
        company_id=company,
        invoice_number=number,
        invoice_date=invoice_date,
        currency=currency,
        counterparty_name=counterparty,
        counterparty_tax_id=tin,
        subtotal_amount=subtotal,
        discount_amount=discount,
        vat_amount=vat,
        total_amount=total,
        items=items or [],
    )


def _tax(
    id=None,
    uuid=None,
    internal_id=None,
    company=1,
    issue_datetime=datetime(2024, 3, 1, 12, 0, 0),
    currency="EGP",
    total_sales=Decimal("100.00"),
    total_discount=Decimal("0.00"),
    net_amount=Decimal("100.00"),
    vat=Decimal("14.00"),
    total=Decimal("114.00"),
    buyer="Acme Corp",
    buyer_tin=None,
    seller="Mega Retail",
    seller_tin=None,
    items=None,
):
    return TaxInvoice(
        id=id,
        uuid=uuid,
        internal_id=internal_id,
        company_id=company,
        issue_datetime=issue_datetime,
        currency=currency,
        total_sales=total_sales,
        total_discount=total_discount,
        net_amount=net_amount,
        vat_amount=vat,
        total_amount=total,
        buyer_name=buyer,
        buyer_tax_id=buyer_tin,
        seller_name=seller,
        seller_tax_id=seller_tin,
        items=items or [],
    )


def _statuses(outcome):
    return [result.match_status for result in outcome.results]


def _result_status(outcome, account_id):
    for result in outcome.results:
        if result.account_invoice_id == account_id:
            return result.match_status
    return None


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------


def test_exact_uuid_match():
    uuid = _fresh_uuid("exact")
    outcome = reconcile(
        [_invoice(id=1, uuid=uuid)],
        [_tax(id=10, uuid=uuid)],
    )
    assert _statuses(outcome) == [c.MATCHED]
    assert outcome.errors == []


def test_normalized_uuid_match():
    lower = _fresh_uuid("norm")
    upper = "{" + lower.upper() + "}"
    outcome = reconcile(
        [_invoice(id=1, uuid=upper)],
        [_tax(id=10, uuid=lower)],
    )
    assert _statuses(outcome) == [c.MATCHED]


def test_invoice_number_to_internal_id_match():
    outcome = reconcile(
        [_invoice(id=1, uuid=None, number="INV-42")],
        [_tax(id=10, uuid=None, internal_id="INV-42")],
    )
    assert _statuses(outcome) == [c.MATCHED]


def test_uuid_has_priority_over_number():
    uuid = _fresh_uuid("priority")
    outcome = reconcile(
        [_invoice(id=1, uuid=uuid, number="NUM-X")],
        [
            _tax(id=10, uuid=None, internal_id="NUM-X"),
            _tax(id=11, uuid=uuid),
        ],
    )
    assert [r.match_status for r in outcome.results] == [
        c.MATCHED, c.EXTRA_IN_TAX_AUTHORITY,
    ]
    assert outcome.results[0].tax_invoice_id == 11


def test_matching_invoice_compares_amounts():
    uuid = _fresh_uuid("amounts")
    outcome = reconcile(
        [_invoice(id=1, uuid=uuid, subtotal=Decimal("200.00"), vat=Decimal("28.00"),
                  total=Decimal("228.00"))],
        [_tax(id=10, uuid=uuid, total_sales=Decimal("200.00"), net_amount=Decimal("200.00"),
              vat=Decimal("28.00"), total=Decimal("228.00"))],
    )
    assert _statuses(outcome) == [c.MATCHED]
    assert outcome.results[0].discrepancy_amount == Decimal("0.00")


# ---------------------------------------------------------------------------
# Field-level mismatches
# ---------------------------------------------------------------------------


def test_invoice_date_mismatch():
    uuid = _fresh_uuid("date")
    outcome = reconcile(
        [_invoice(id=1, uuid=uuid, invoice_date=date(2024, 3, 1))],
        [_tax(id=10, uuid=uuid, issue_datetime=datetime(2024, 3, 2, 9, 0))],
    )
    result = outcome.results[0]
    assert result.match_status == c.MISMATCHED
    error = outcome.errors[0]
    assert error.error_type == c.E_INVOICE_DATE_MISMATCH
    assert error.field == "invoice_date"
    assert error.accounting_value == "2024-03-01"
    assert error.tax_authority_value == "2024-03-02"


def test_time_component_is_ignored_for_dates():
    uuid = _fresh_uuid("time")
    outcome = reconcile(
        [_invoice(id=1, uuid=uuid, invoice_date=date(2024, 3, 1))],
        [_tax(id=10, uuid=uuid, issue_datetime=datetime(2024, 3, 1, 23, 59))],
    )
    assert _statuses(outcome) == [c.MATCHED]


def test_subtotal_mismatch():
    uuid = _fresh_uuid("subtotal")
    outcome = reconcile(
        [_invoice(id=1, uuid=uuid, subtotal=Decimal("100.00"))],
        [_tax(id=10, uuid=uuid, total_sales=Decimal("120.00"),
              net_amount=Decimal("120.00"), total=Decimal("134.00"),
              vat=Decimal("14.00"))],
    )
    errors = {e.field: e for e in outcome.errors}
    assert _result_status(outcome, 1) == c.MISMATCHED
    assert errors["subtotal_amount"].error_type == c.E_SUBTOTAL_AMOUNT_MISMATCH
    assert errors["subtotal_amount"].difference == Decimal("-20.00")


def test_tax_mismatch():
    uuid = _fresh_uuid("vat")
    outcome = reconcile(
        [_invoice(id=1, uuid=uuid, vat=Decimal("14.00"))],
        [_tax(id=10, uuid=uuid, vat=Decimal("20.00"), total=Decimal("120.00"))],
    )
    errors = {e.field: e for e in outcome.errors}
    assert _result_status(outcome, 1) == c.MISMATCHED
    assert errors["vat_amount"].accounting_value == "14.00"
    assert errors["vat_amount"].tax_authority_value == "20.00"
    assert errors["vat_amount"].difference == Decimal("-6.00")


def test_total_mismatch_records_discrepancy():
    uuid = _fresh_uuid("total")
    outcome = reconcile(
        [_invoice(id=1, uuid=uuid, total=Decimal("1150.00"))],
        [_tax(id=10, uuid=uuid, total=Decimal("1200.00"))],
    )
    result = outcome.results[0]
    assert result.match_status == c.MISMATCHED
    assert result.discrepancy_amount == Decimal("-50.00")
    error = {e.field: e for e in outcome.errors}["total_amount"]
    assert error.error_type == c.E_TOTAL_AMOUNT_MISMATCH
    assert error.difference == Decimal("-50.00")


def test_counterparty_tax_id_mismatch():
    uuid = _fresh_uuid("tin")
    outcome = reconcile(
        [_invoice(id=1, uuid=uuid, counterparty="Acme", tin="TIN-123")],
        [_tax(id=10, uuid=uuid, buyer="Acme", buyer_tin="TIN-999",
              seller="Mega Retail", seller_tin="TIN-S")],
    )
    error = {e.field: e for e in outcome.errors}["counterparty_tax_id"]
    assert error.error_type == c.E_COUNTERPARTY_TAX_ID_MISMATCH


def test_counterparty_name_mismatch_via_tin_direction():
    uuid = _fresh_uuid("party")
    outcome = reconcile(
        [_invoice(id=1, uuid=uuid, counterparty="Acme Corp", tin="TIN-123")],
        [_tax(id=10, uuid=uuid, buyer="Acme Inc", buyer_tin="TIN-123")],
    )
    error = {e.field: e for e in outcome.errors}["counterparty_name"]
    assert error.error_type == c.E_COUNTERPARTY_NAME_MISMATCH
    assert error.accounting_value == "Acme Corp"
    assert error.tax_authority_value == "Acme Inc"


def test_counterparty_name_mismatch_without_tin():
    uuid = _fresh_uuid("party2")
    outcome = reconcile(
        [_invoice(id=1, uuid=uuid, counterparty="Totally Different")],
        [_tax(id=10, uuid=uuid, buyer="Acme", seller="Mega")],
    )
    error = {e.field: e for e in outcome.errors}["counterparty_name"]
    assert "buyer=Acme / seller=Mega" in error.tax_authority_value


def test_counterparty_name_matches_either_side_without_tin():
    uuid = _fresh_uuid("party3")
    outcome = reconcile(
        [_invoice(id=1, uuid=uuid, counterparty="Mega")],
        [_tax(id=10, uuid=uuid, buyer="Acme", seller="Mega")],
    )
    assert _result_status(outcome, 1) == c.MATCHED


def test_item_count_mismatch():
    uuid = _fresh_uuid("items1")
    outcome = reconcile(
        [
            _invoice(id=1, uuid=uuid, items=[
                InvoiceItem(description="A", quantity=1, line_total=Decimal("10.00"),
                            vat_amount=Decimal("1.00")),
                InvoiceItem(description="B", quantity=1, line_total=Decimal("20.00"),
                            vat_amount=Decimal("2.00")),
            ]),
        ],
        [
            _tax(id=10, uuid=uuid, items=[
                TaxInvoiceItem(description="A", quantity=1, total_amount=Decimal("30.00"),
                               vat_amount=Decimal("3.00")),
            ]),
        ],
    )
    errors = {e.error_type: e for e in outcome.errors}
    assert c.E_ITEM_COUNT_MISMATCH in errors
    assert _result_status(outcome, 1) == c.MISMATCHED


def test_item_quantity_and_total_mismatch():
    uuid = _fresh_uuid("items2")
    outcome = reconcile(
        [
            _invoice(id=1, uuid=uuid, items=[
                InvoiceItem(description="A", quantity=Decimal("2.0000"),
                            unit_price=Decimal("10.00"),
                            line_total=Decimal("20.00"), vat_amount=Decimal("0.00")),
                InvoiceItem(description="B", quantity=Decimal("1.0000"),
                            unit_price=Decimal("10.00"),
                            line_total=Decimal("10.00"), vat_amount=Decimal("0.00")),
            ]),
        ],
        [
            _tax(id=10, uuid=uuid, items=[
                TaxInvoiceItem(description="A", quantity=Decimal("5.0000"),
                               total_amount=Decimal("30.00"), vat_amount=Decimal("0.00")),
            ]),
        ],
    )
    errors = {e.error_type: e for e in outcome.errors}
    assert c.E_ITEM_COUNT_MISMATCH in errors
    assert c.E_ITEM_QUANTITY_SUM_MISMATCH in errors
    assert c.E_ITEM_TOTAL_SUM_MISMATCH not in errors


# ---------------------------------------------------------------------------
# Missing / Extra
# ---------------------------------------------------------------------------


def test_accounting_invoice_missing_in_tax_authority():
    outcome = reconcile(
        [_invoice(id=1, uuid=_fresh_uuid("m1"))],
        [],
    )
    assert _statuses(outcome) == [c.MISSING_IN_TAX_AUTHORITY]
    assert outcome.errors == []


def test_tax_invoice_extra_in_accounting():
    outcome = reconcile(
        [],
        [_tax(id=10, uuid=_fresh_uuid("e1"))],
    )
    assert _statuses(outcome) == [c.EXTRA_IN_TAX_AUTHORITY]
    assert outcome.errors == []


def test_both_sides_contain_unique_invoices():
    outcome = reconcile(
        [_invoice(id=1, uuid=_fresh_uuid("b1")), _invoice(id=2, uuid=_fresh_uuid("b2"))],
        [_tax(id=10, uuid=_fresh_uuid("t1")), _tax(id=11, uuid=_fresh_uuid("t2"))],
    )
    assert _statuses(outcome) == [
        c.MISSING_IN_TAX_AUTHORITY,
        c.MISSING_IN_TAX_AUTHORITY,
        c.EXTRA_IN_TAX_AUTHORITY,
        c.EXTRA_IN_TAX_AUTHORITY,
    ]


# ---------------------------------------------------------------------------
# Invalid
# ---------------------------------------------------------------------------


def test_invalid_accounting_uuid():
    outcome = reconcile(
        [_invoice(id=1, uuid="not-a-uuid", number="INV-BAD")],
        [_tax(id=10, internal_id="INV-BAD")],
    )
    result = outcome.results[0]
    assert result.match_status == c.INVALID
    error = outcome.errors[0]
    assert error.error_type == c.E_INVALID_UUID
    assert error.entity_id == 1
    assert error.source_type == "account"


def test_invalid_tax_uuid_is_invalid_not_extra():
    outcome = reconcile(
        [],
        [_tax(id=10, uuid="garbage")],
    )
    result = outcome.results[0]
    assert result.match_status == c.INVALID
    assert outcome.errors[0].source_type == "tax"


def test_invalid_financial_value_does_not_crash():
    uuid = _fresh_uuid("finance")
    outcome = reconcile(
        [_invoice(id=1, uuid=uuid)],
        [_tax(id=10, uuid=uuid, total="not-a-number")],
    )
    result = outcome.results[0]
    assert result.match_status == c.MISMATCHED
    codes = {error.error_type for error in outcome.errors}
    assert c.E_INVALID_FINANCIAL_VALUE in codes


# ---------------------------------------------------------------------------
# Tolerance + combined runs
# ---------------------------------------------------------------------------


def test_money_tolerance_allows_small_difference():
    tolerance = Decimal("0.01")
    uuid = _fresh_uuid("tol")
    outcome = reconcile(
        [_invoice(id=1, uuid=uuid, total=Decimal("114.00"))],
        [_tax(id=10, uuid=uuid, total=Decimal("114.01"))],
        money_tolerance=tolerance,
    )
    assert _statuses(outcome) == [c.MATCHED]
    assert outcome.results[0].discrepancy_amount == Decimal("-0.01")


def test_money_tolerance_is_exact_by_default():
    uuid = _fresh_uuid("tol2")
    outcome = reconcile(
        [_invoice(id=1, uuid=uuid, total=Decimal("114.00"))],
        [_tax(id=10, uuid=uuid, total=Decimal("114.01"))],
    )
    assert _statuses(outcome) == [c.MISMATCHED]


def test_combined_run_with_all_five_statuses():
    matched_uuid = _fresh_uuid("combined-match")
    mismatch_uuid = _fresh_uuid("combined-mismatch")
    missing_uuid = _fresh_uuid("combined-missing")
    extra_uuid = _fresh_uuid("combined-extra")
    outcome = reconcile(
        [
            _invoice(id=1, uuid=matched_uuid, number="A"),
            _invoice(id=2, uuid=mismatch_uuid, total=Decimal("500.00")),
            _invoice(id=3, uuid=missing_uuid, number="C"),
            _invoice(id=4, uuid="bad-uuid!", number="D"),
        ],
        [
            _tax(id=10, uuid=matched_uuid),
            _tax(id=11, uuid=mismatch_uuid, total=Decimal("600.00")),
            _tax(id=12, uuid=extra_uuid),
        ],
    )
    assert _statuses(outcome) == [
        c.MATCHED,
        c.MISMATCHED,
        c.MISSING_IN_TAX_AUTHORITY,
        c.INVALID,
        c.EXTRA_IN_TAX_AUTHORITY,
    ]
    assert any(e.error_type == c.E_TOTAL_AMOUNT_MISMATCH for e in outcome.errors)
    assert any(e.error_type == c.E_INVALID_UUID for e in outcome.errors)


def test_result_notes_list_mismatched_fields():
    uuid = _fresh_uuid("notes")
    outcome = reconcile(
        [_invoice(id=1, uuid=uuid, vat=Decimal("10.00"), total=Decimal("100.00"))],
        [_tax(id=10, uuid=uuid, vat=Decimal("20.00"), total=Decimal("200.00"))],
    )
    notes = outcome.results[0].notes
    assert "vat_amount" in notes
    assert "total_amount" in notes


def test_results_are_deterministically_ordered():
    a = _fresh_uuid("ord-a")
    b = _fresh_uuid("ord-b")
    d = _fresh_uuid("ord-d")
    outcome_a = reconcile(
        [_invoice(id=10, uuid=d), _invoice(id=1, uuid=a), _invoice(id=5, uuid=b)],
        [_tax(id=1, uuid=a), _tax(id=2, uuid=b), _tax(id=3, uuid=d)],
    )
    outcome_b = reconcile(
        [_invoice(id=5, uuid=b), _invoice(id=1, uuid=a), _invoice(id=10, uuid=d)],
        [_tax(id=3, uuid=d), _tax(id=1, uuid=a), _tax(id=2, uuid=b)],
    )
    assert _statuses(outcome_a) == [c.MATCHED, c.MATCHED, c.MATCHED]
    assert [r.account_invoice_id for r in outcome_a.results] == [1, 5, 10]
    assert [r.account_invoice_id for r in outcome_b.results] == [1, 5, 10]