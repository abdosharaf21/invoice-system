"""Reconciliation contract: statuses, error codes and comparison policy.

The contract defines the deterministic rules the reconciliation engine
follows when comparing accounting invoices against tax authority invoices.
It is the single source of truth for the machine-readable vocabulary used
by the engine, the ``reconciliation_results``/``reconciliation_errors``
tables and the public API.
"""

from decimal import Decimal

# ---------------------------------------------------------------------------
# Run lifecycle (reconciliation_runs.status)
# ---------------------------------------------------------------------------

RUN_PENDING = "pending"
RUN_RUNNING = "running"
RUN_COMPLETED = "completed"
RUN_FAILED = "failed"

RUN_STATUSES = (RUN_PENDING, RUN_RUNNING, RUN_COMPLETED, RUN_FAILED)

# ---------------------------------------------------------------------------
# Result statuses (reconciliation_results.match_status)
# ---------------------------------------------------------------------------

MATCHED = "matched"
MISMATCHED = "mismatched"
MISSING_IN_TAX_AUTHORITY = "missing_in_tax_authority"
EXTRA_IN_TAX_AUTHORITY = "extra_in_tax_authority"
INVALID = "invalid"

RESULT_STATUSES = (
    MATCHED,
    MISMATCHED,
    MISSING_IN_TAX_AUTHORITY,
    EXTRA_IN_TAX_AUTHORITY,
    INVALID,
)

# Statuses that count towards reconciliation_runs.unmatched_count.
UNMATCHED_STATUSES = (
    MISMATCHED,
    MISSING_IN_TAX_AUTHORITY,
    EXTRA_IN_TAX_AUTHORITY,
    INVALID,
)

# ---------------------------------------------------------------------------
# Error type codes (reconciliation_errors.error_type)
# ---------------------------------------------------------------------------

E_INVALID_UUID = "INVALID_UUID"
E_INVALID_DATE = "INVALID_DATE"
E_INVALID_FINANCIAL_VALUE = "INVALID_FINANCIAL_VALUE"

E_INVOICE_DATE_MISMATCH = "INVOICE_DATE_MISMATCH"
E_CURRENCY_MISMATCH = "CURRENCY_MISMATCH"
E_COUNTERPARTY_TAX_ID_MISMATCH = "COUNTERPARTY_TAX_ID_MISMATCH"
E_COUNTERPARTY_NAME_MISMATCH = "COUNTERPARTY_NAME_MISMATCH"
E_SUBTOTAL_AMOUNT_MISMATCH = "SUBTOTAL_AMOUNT_MISMATCH"
E_DISCOUNT_AMOUNT_MISMATCH = "DISCOUNT_AMOUNT_MISMATCH"
E_NET_AMOUNT_MISMATCH = "NET_AMOUNT_MISMATCH"
E_VAT_AMOUNT_MISMATCH = "VAT_AMOUNT_MISMATCH"
E_TOTAL_AMOUNT_MISMATCH = "TOTAL_AMOUNT_MISMATCH"
E_ITEM_COUNT_MISMATCH = "ITEM_COUNT_MISMATCH"
E_ITEM_QUANTITY_SUM_MISMATCH = "ITEM_QUANTITY_SUM_MISMATCH"
E_ITEM_VAT_SUM_MISMATCH = "ITEM_VAT_SUM_MISMATCH"
E_ITEM_TOTAL_SUM_MISMATCH = "ITEM_TOTAL_SUM_MISMATCH"

# ---------------------------------------------------------------------------
# Comparison policy
# ---------------------------------------------------------------------------

# Money is compared with exact Decimal equality by default. A caller may pass
# an explicit tolerance (for example Decimal("0.01")) to the engine; the
# policy is never hidden — the tolerance used for a run is documented and the
# difference is always surfaced on each mismatch error and by the result's
# discrepancy_amount.
DEFAULT_MONEY_TOLERANCE = Decimal("0.00")

# Column mapping between the two representations. Net amount on the tax side
# is stored directly; on the accounting side it is derived from the stored
# subtotal minus the stored discount.
COMPARED_FIELDS = (
    ("invoice_date", "invoice_date", "issue_datetime"),
    ("currency", "currency", "currency"),
    ("subtotal_amount", "subtotal_amount", "total_sales"),
    ("discount_amount", "discount_amount", "total_discount"),
    ("net_amount", "subtotal_amount - discount_amount", "net_amount"),
    ("vat_amount", "vat_amount", "vat_amount"),
    ("total_amount", "total_amount", "total_amount"),
    ("counterparty_tax_id", "counterparty_tax_id", "buyer_tax_id/seller_tax_id"),
    ("counterparty_name", "counterparty_name", "buyer_name/seller_name"),
    ("items", "item count and aggregates", "item count and aggregates"),
)

# ---------------------------------------------------------------------------
# Identity normalization
# ---------------------------------------------------------------------------

# UUID hierarchy: an accounting invoice with a valid UUID only matches a tax
# invoice carrying the same UUID. When an accounting invoice has no UUID, it
# falls back to its invoice_number matched against the tax authority's
# internal_id (scoped to the company). Fuzzy matching is intentionally absent.
UUID_HIERARCHY = "uuid -> invoice_number/internal_id (no fuzzy matching)"