"""Expected schema manifest (Phase 12) — the gold reference for drift detection.

``EXPECTED_TABLES`` encodes the *target* schema of a fully-migrated database:
the Phase 1 foundation (``companies``, ``users``, ``roles``, ``user_roles``)
plus the cumulative effect of migrations 001–011. ``schema_verify.py``
compares the live ``information_schema`` against this manifest and reports
every difference (missing/unexpected tables, columns, indexes, foreign keys,
checks, types, nullability, defaults, engine and collation).

The manifest is deliberately derived from the migration files, not from any
specific database: a fresh database produced by migrating 001→011 matches it
exactly (proven by ``deploy/schema_drill.sh``), and any live drift shows up as
differences.

Conventions:
  * Column ``default`` mirrors the value returned by
    ``information_schema.COLUMNS.COLUMN_DEFAULT``: ``"CURRENT_TIMESTAMP"`` for
    timestamps, the bare literal for strings (``"uploaded"``, ``""``,
    ``"0.00"``), and ``None`` for *no default / explicit DEFAULT NULL*.
  * ``TableRule.columns`` is an ordered list; positional layout is a supported
    contract of the codebase (repository ``SELECT *`` mapping relies on it).
  * Indexes include ``PRIMARY`` plus every explicit index; ``unique`` carries
    the UNIQUE flag. Foreign keys carry the referenced columns and the
    ON DELETE / ON UPDATE rules exactly as declared in the migrations.
  * ``audit_logs_legacy`` is intentionally NOT part of the target schema (it is
    only ever written by migration 008's guarded rename on pre-tracker
    databases) and is listed in ``ALLOWED_EXTRA_TABLES``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

ENGINE = "InnoDB"
COLLATION = "utf8mb4_unicode_ci"

# Tables that legitimately exist on some databases but are not part of the
# canonical target schema. The verifier ignores these when they appear.
ALLOWED_EXTRA_TABLES = frozenset({"audit_logs_legacy", "schema_migrations"})


@dataclass(frozen=True)
class Column:
    """One column of the expected schema."""

    type: str
    nullable: bool = False
    default: Optional[str] = None


@dataclass(frozen=True)
class Index:
    """One expected index (or unique constraint)."""

    unique: bool
    columns: Tuple[str, ...]


@dataclass(frozen=True)
class ForeignKey:
    """One expected foreign key constraint."""

    table: str
    columns: Tuple[str, ...]
    referenced_columns: Tuple[str, ...]
    delete_rule: str
    update_rule: str = "CASCADE"


@dataclass(frozen=True)
class TableRule:
    """Full expected definition of one table."""

    columns: Tuple[Tuple[str, Column], ...]
    indexes: Dict[str, Index] = field(default_factory=dict)
    foreign_keys: Dict[str, ForeignKey] = field(default_factory=dict)
    checks: Tuple[str, ...] = ()
    engine: str = ENGINE
    collation: str = COLLATION

    def column_names(self) -> Tuple[str, ...]:
        return tuple(name for name, _ in self.columns)

    def primary_key(self) -> Tuple[str, ...]:
        index = self.indexes.get("PRIMARY")
        return index.columns if index else ()


def _col(t: str, *, nullable: bool = False, default: Optional[str] = None) -> Column:
    return Column(type=t, nullable=nullable, default=default)


def _tbl(*cols: tuple, **opts) -> TableRule:
    """Build a TableRule from ``(name, Column)`` pairs plus keyword options."""
    columns: list = []
    for item in cols:
        name, column = item
        columns.append((name, column))
    return TableRule(columns=tuple(columns), **opts)


def _idx(unique: bool, *cols: str) -> Index:
    return Index(unique=unique, columns=tuple(cols))


def _fk(table: str, cols: Tuple[str, ...], delete: str,
        ref: Tuple[str, ...] = ("id",), update: str = "CASCADE") -> ForeignKey:
    return ForeignKey(
        table=table,
        columns=cols,
        referenced_columns=ref,
        delete_rule=delete,
        update_rule=update,
    )


TS = "CURRENT_TIMESTAMP"  # information_schema spelling of DEFAULT CURRENT_TIMESTAMP


# ---------------------------------------------------------------------------
# Phase 1 foundation (defined by hand before migrations were tracked).
# ---------------------------------------------------------------------------

COMPANIES = _tbl(
    ("id", _col("bigint unsigned")),
    ("name", _col("varchar(255)")),
    ("tax_registration_number", _col("varchar(50)", nullable=True)),
    ("email", _col("varchar(255)", nullable=True)),
    ("phone", _col("varchar(50)", nullable=True)),
    ("address", _col("text", nullable=True)),
    ("is_active", _col("tinyint(1)", default="1")),
    ("created_at", _col("datetime", default=TS)),
    ("updated_at", _col("datetime", default=TS)),
    ("logo_path", _col("varchar(500)", nullable=True)),
    ("website", _col("varchar(255)", nullable=True)),
    ("default_currency", _col("varchar(3)", nullable=True, default="EGP")),
    ("default_tax_rate", _col("decimal(5,2)", nullable=True, default="0.00")),
    ("fiscal_year_start", _col("varchar(10)", nullable=True, default="01-01")),
    indexes={
        "PRIMARY": _idx(True, "id"),
        "uq_companies_tax_registration_number": _idx(True, "tax_registration_number"),
        "idx_companies_name": _idx(False, "name"),
        "idx_companies_active": _idx(False, "is_active"),
    },
    foreign_keys={},
)

USERS = _tbl(
    ("id", _col("bigint unsigned")),
    ("company_id", _col("bigint unsigned", nullable=True)),
    ("username", _col("varchar(100)")),
    ("email", _col("varchar(255)")),
    ("password_hash", _col("varchar(255)")),
    ("first_name", _col("varchar(100)", nullable=True)),
    ("last_name", _col("varchar(100)", nullable=True)),
    ("is_active", _col("tinyint(1)", default="1")),
    ("last_login_at", _col("datetime", nullable=True)),
    ("created_at", _col("datetime", default=TS)),
    ("updated_at", _col("datetime", default=TS)),
    ("language", _col("varchar(10)", nullable=True, default="en")),
    ("theme", _col("varchar(20)", nullable=True, default="light")),
    ("date_format", _col("varchar(20)", nullable=True, default="YYYY-MM-DD")),
    ("number_format", _col("varchar(20)", nullable=True, default="#,##0.00")),
    ("timezone", _col("varchar(50)", nullable=True, default="UTC")),
    ("avatar_path", _col("varchar(500)", nullable=True)),
    ("pagination_size", _col("int unsigned", nullable=True, default="25")),
    indexes={
        "PRIMARY": _idx(True, "id"),
        "uq_users_username": _idx(True, "username"),
        "uq_users_email": _idx(True, "email"),
        "idx_users_company": _idx(False, "company_id"),
    },
    foreign_keys={
        "fk_users_company": _fk("companies", ("company_id",), "SET NULL"),
    },
)

ROLES = _tbl(
    ("id", _col("bigint unsigned")),
    ("name", _col("varchar(100)")),
    ("description", _col("varchar(255)", nullable=True)),
    ("created_at", _col("datetime", default=TS)),
    indexes={
        "PRIMARY": _idx(True, "id"),
        "uq_roles_name": _idx(True, "name"),
    },
)

USER_ROLES = _tbl(
    ("user_id", _col("bigint unsigned")),
    ("role_id", _col("bigint unsigned")),
    ("assigned_at", _col("datetime", default=TS)),
    indexes={
        "PRIMARY": _idx(True, "user_id", "role_id"),
        "fk_user_roles_role": _idx(False, "role_id"),
    },
    foreign_keys={
        "fk_user_roles_user": _fk("users", ("user_id",), "CASCADE"),
        "fk_user_roles_role": _fk("roles", ("role_id",), "CASCADE"),
    },
)

# ---------------------------------------------------------------------------
# Migration 001 — refresh_token_blocklist
# ---------------------------------------------------------------------------

REFRESH_TOKEN_BLOCKLIST = _tbl(
    ("id", _col("bigint unsigned")),
    ("jti", _col("varchar(64)")),
    ("token_type", _col("varchar(16)", default="access")),
    ("expires_at", _col("datetime")),
    ("created_at", _col("datetime", default=TS)),
    indexes={
        "PRIMARY": _idx(True, "id"),
        "uq_refresh_token_blocklist_jti": _idx(True, "jti"),
        "idx_refresh_token_blocklist_expires": _idx(False, "expires_at"),
    },
)

# ---------------------------------------------------------------------------
# Migration 002 — e-invoice domain tables
# ---------------------------------------------------------------------------

IMPORT_BATCHES = _tbl(
    ("id", _col("bigint unsigned")),
    ("company_id", _col("bigint unsigned")),
    ("filename", _col("varchar(255)")),
    ("file_type", _col("varchar(20)", default="csv")),
    ("source_type", _col("varchar(20)", default="manual")),  # 003
    ("status", _col("varchar(20)", default="uploaded")),
    ("total_rows", _col("int unsigned", default="0")),
    ("processed_rows", _col("int unsigned", default="0")),
    ("error_rows", _col("int unsigned", default="0")),
    ("uploaded_by", _col("bigint unsigned", nullable=True)),
    ("started_at", _col("datetime", nullable=True)),
    ("finished_at", _col("datetime", nullable=True)),
    ("created_at", _col("datetime", default=TS)),
    ("updated_at", _col("datetime", default=TS)),
    indexes={
        "PRIMARY": _idx(True, "id"),
        "idx_import_batches_company": _idx(False, "company_id"),
        "idx_import_batches_status": _idx(False, "status"),
        "idx_import_batches_uploaded_by": _idx(False, "uploaded_by"),
        # 010
        "idx_import_batches_company_created": _idx(False, "company_id", "created_at", "id"),
    },
    foreign_keys={
        "fk_import_batches_company": _fk("companies", ("company_id",), "CASCADE"),
        "fk_import_batches_uploaded_by": _fk("users", ("uploaded_by",), "SET NULL"),
    },
    checks=("chk_import_batches_status",),  # 009
)

IMPORT_BATCH_ERRORS = _tbl(
    ("id", _col("bigint unsigned")),
    ("batch_id", _col("bigint unsigned")),
    ("row_number", _col("int unsigned")),
    ("field", _col("varchar(100)", nullable=True)),  # 003
    ("error_code", _col("varchar(50)", nullable=True)),  # 003
    ("error_message", _col("text")),
    ("raw_data", _col("text", nullable=True)),
    ("created_at", _col("datetime", default=TS)),
    indexes={
        "PRIMARY": _idx(True, "id"),
        "idx_import_batch_errors_batch": _idx(False, "batch_id"),
    },
    foreign_keys={
        "fk_import_batch_errors_batch": _fk("import_batches", ("batch_id",), "CASCADE"),
    },
)

INVOICES = _tbl(
    ("id", _col("bigint unsigned")),
    ("uuid", _col("char(36)", nullable=True)),  # 003
    ("company_id", _col("bigint unsigned")),
    ("import_batch_id", _col("bigint unsigned", nullable=True)),
    ("invoice_number", _col("varchar(50)")),
    ("invoice_type", _col("varchar(20)", default="sales")),
    ("invoice_date", _col("date")),
    ("due_date", _col("date", nullable=True)),
    ("currency", _col("varchar(3)", default="EGP")),
    ("counterparty_name", _col("varchar(255)")),
    ("counterparty_tax_id", _col("varchar(50)", nullable=True)),
    ("subtotal_amount", _col("decimal(15,2)", default="0.00")),
    ("discount_amount", _col("decimal(15,2)", default="0.00")),
    ("vat_amount", _col("decimal(15,2)", default="0.00")),
    ("total_amount", _col("decimal(15,2)", default="0.00")),
    ("status", _col("varchar(20)", default="draft")),
    ("created_at", _col("datetime", default=TS)),
    ("updated_at", _col("datetime", default=TS)),
    ("counterparty_email", _col("varchar(255)", nullable=True)),  # 007
    indexes={
        "PRIMARY": _idx(True, "id"),
        "uq_invoices_uuid": _idx(True, "uuid"),
        "uq_invoices_company_number": _idx(True, "company_id", "invoice_number"),
        "idx_invoices_company_date": _idx(False, "company_id", "invoice_date"),
        "idx_invoices_status": _idx(False, "status"),
        "idx_invoices_import_batch": _idx(False, "import_batch_id"),
    },
    foreign_keys={
        "fk_invoices_company": _fk("companies", ("company_id",), "CASCADE"),
        "fk_invoices_import_batch": _fk("import_batches", ("import_batch_id",), "SET NULL"),
    },
    checks=(  # 009
        "chk_invoices_money_nonneg",
        "chk_invoices_discount_le_subtotal",
        "chk_invoices_total_formula",
        "chk_invoices_currency",
    ),
)

INVOICE_ITEMS = _tbl(
    ("id", _col("bigint unsigned")),
    ("invoice_id", _col("bigint unsigned")),
    ("description", _col("varchar(255)")),
    ("quantity", _col("decimal(15,4)", default="1.0000")),
    ("unit_price", _col("decimal(15,2)", default="0.00")),
    ("discount_amount", _col("decimal(15,2)", default="0.00")),
    ("vat_rate", _col("decimal(5,2)", default="0.00")),
    ("vat_amount", _col("decimal(15,2)", default="0.00")),
    ("line_total", _col("decimal(15,2)", default="0.00")),
    ("created_at", _col("datetime", default=TS)),
    indexes={
        "PRIMARY": _idx(True, "id"),
        "idx_invoice_items_invoice": _idx(False, "invoice_id"),
    },
    foreign_keys={
        "fk_invoice_items_invoice": _fk("invoices", ("invoice_id",), "CASCADE"),
    },
    checks=(  # 009
        "chk_invoice_items_quantity_pos",
        "chk_invoice_items_money_nonneg",
        "chk_invoice_items_vat_range",
        "chk_invoice_items_formula",
        "chk_invoice_items_discount_le_gross",
    ),
)

TAX_INVOICES = _tbl(
    ("id", _col("bigint unsigned")),
    ("company_id", _col("bigint unsigned")),
    ("account_invoice_id", _col("bigint unsigned", nullable=True)),
    ("import_batch_id", _col("bigint unsigned", nullable=True)),
    ("uuid", _col("char(36)", nullable=True)),
    ("internal_id", _col("varchar(50)", nullable=True)),
    ("document_type", _col("varchar(20)", default="invoice")),
    ("issue_datetime", _col("datetime")),
    ("currency", _col("varchar(3)", default="EGP")),
    ("exchange_rate", _col("decimal(12,6)", default="1.000000")),
    ("seller_name", _col("varchar(255)")),
    ("seller_tax_id", _col("varchar(50)", nullable=True)),
    ("buyer_name", _col("varchar(255)", nullable=True)),
    ("buyer_tax_id", _col("varchar(50)", nullable=True)),
    ("total_sales", _col("decimal(15,2)", default="0.00")),
    ("total_discount", _col("decimal(15,2)", default="0.00")),
    ("net_amount", _col("decimal(15,2)", default="0.00")),
    ("vat_amount", _col("decimal(15,2)", default="0.00")),
    ("other_charges", _col("decimal(15,2)", default="0.00")),
    ("total_amount", _col("decimal(15,2)", default="0.00")),
    ("submission_status", _col("varchar(20)", default="draft")),
    ("submission_errors", _col("text", nullable=True)),
    ("created_at", _col("datetime", default=TS)),
    ("updated_at", _col("datetime", default=TS)),
    indexes={
        "PRIMARY": _idx(True, "id"),
        "uq_tax_invoices_uuid": _idx(True, "uuid"),
        "uq_tax_invoices_company_internal": _idx(True, "company_id", "internal_id"),
        # idx_tax_invoices_company was dropped by 010
        "idx_tax_invoices_account_invoice": _idx(False, "account_invoice_id"),
        "idx_tax_invoices_submission_status": _idx(False, "submission_status"),
        "idx_tax_invoices_import_batch": _idx(False, "import_batch_id"),
        "idx_tax_invoices_company_issue_datetime": _idx(False, "company_id", "issue_datetime"),  # 010
    },
    foreign_keys={
        "fk_tax_invoices_company": _fk("companies", ("company_id",), "CASCADE"),
        "fk_tax_invoices_account_invoice": _fk("invoices", ("account_invoice_id",), "SET NULL"),
        "fk_tax_invoices_import_batch": _fk("import_batches", ("import_batch_id",), "SET NULL"),
    },
    checks=(  # 009
        "chk_tax_invoices_money_nonneg",
        "chk_tax_invoices_discount_le_sales",
        "chk_tax_invoices_net_formula",
        "chk_tax_invoices_total_formula",
        "chk_tax_invoices_currency",
    ),
)

TAX_INVOICE_ITEMS = _tbl(
    ("id", _col("bigint unsigned")),
    ("tax_invoice_id", _col("bigint unsigned")),
    ("description", _col("varchar(255)")),
    ("item_type", _col("varchar(20)", default="composite")),
    ("quantity", _col("decimal(15,4)", default="1.0000")),
    ("unit_value", _col("decimal(15,2)", default="0.00")),
    ("vat_rate", _col("decimal(5,2)", default="0.00")),
    ("vat_amount", _col("decimal(15,2)", default="0.00")),
    ("discount_amount", _col("decimal(15,2)", default="0.00")),
    ("total_amount", _col("decimal(15,2)", default="0.00")),
    ("created_at", _col("datetime", default=TS)),
    indexes={
        "PRIMARY": _idx(True, "id"),
        "idx_tax_invoice_items_invoice": _idx(False, "tax_invoice_id"),
    },
    foreign_keys={
        "fk_tax_invoice_items_invoice": _fk("tax_invoices", ("tax_invoice_id",), "CASCADE"),
    },
    checks=(  # 009
        "chk_tax_invoice_items_quantity_pos",
        "chk_tax_invoice_items_money_nonneg",
        "chk_tax_invoice_items_vat_range",
        "chk_tax_invoice_items_formula",
        "chk_tax_invoice_items_discount_le_gross",
    ),
)

RECONCILIATION_RUNS = _tbl(
    ("id", _col("bigint unsigned")),
    ("company_id", _col("bigint unsigned")),
    ("period", _col("varchar(20)")),
    ("status", _col("varchar(20)", default="pending")),
    ("invoice_count", _col("int unsigned", default="0")),
    ("tax_invoice_count", _col("int unsigned", default="0")),
    ("matched_count", _col("int unsigned", default="0")),
    ("unmatched_count", _col("int unsigned", default="0")),
    ("error_count", _col("int unsigned", default="0")),
    ("started_at", _col("datetime", nullable=True)),
    ("finished_at", _col("datetime", nullable=True)),
    ("created_at", _col("datetime", default=TS)),
    ("updated_at", _col("datetime", default=TS)),
    indexes={
        "PRIMARY": _idx(True, "id"),
        "idx_reconciliation_runs_company": _idx(False, "company_id"),
        "idx_reconciliation_runs_period": _idx(False, "period"),
        "idx_reconciliation_runs_status": _idx(False, "status"),
        # 010
        "idx_reconciliation_runs_company_created": _idx(False, "company_id", "created_at", "id"),
    },
    foreign_keys={
        "fk_reconciliation_runs_company": _fk("companies", ("company_id",), "CASCADE"),
    },
    checks=("chk_reconciliation_runs_status",),  # 009
)

RECONCILIATION_RESULTS = _tbl(
    ("id", _col("bigint unsigned")),
    ("run_id", _col("bigint unsigned")),
    ("account_invoice_id", _col("bigint unsigned", nullable=True)),
    ("tax_invoice_id", _col("bigint unsigned", nullable=True)),
    ("match_status", _col("varchar(32)")),  # 005 widened from varchar(20)
    ("discrepancy_amount", _col("decimal(15,2)", default="0.00")),
    ("notes", _col("text", nullable=True)),
    ("created_at", _col("datetime", default=TS)),
    indexes={
        "PRIMARY": _idx(True, "id"),
        "uq_reconciliation_results_run_account": _idx(True, "run_id", "account_invoice_id"),
        "uq_reconciliation_results_run_tax": _idx(True, "run_id", "tax_invoice_id"),
        "idx_reconciliation_results_match_status": _idx(False, "match_status"),
        # MySQL auto-creates a supporting index for every FK whose leading
        # column is not already indexed; 002 declared no index on
        # account_invoice_id / tax_invoice_id, so these appear in every
        # database (their names match the constraint names).
        "fk_reconciliation_results_account_invoice": _idx(False, "account_invoice_id"),
        "fk_reconciliation_results_tax_invoice": _idx(False, "tax_invoice_id"),
    },
    foreign_keys={
        "fk_reconciliation_results_run": _fk("reconciliation_runs", ("run_id",), "CASCADE"),
        "fk_reconciliation_results_account_invoice": _fk("invoices", ("account_invoice_id",), "SET NULL"),
        "fk_reconciliation_results_tax_invoice": _fk("tax_invoices", ("tax_invoice_id",), "SET NULL"),
    },
    checks=(  # 009 (match_status), 012 (discrepancy_range replaces discrepancy_nonneg)
        "chk_reconciliation_results_match_status",
        "chk_reconciliation_results_discrepancy_range",
    ),
)

RECONCILIATION_ERRORS = _tbl(
    ("id", _col("bigint unsigned")),
    ("run_id", _col("bigint unsigned")),
    ("source_type", _col("varchar(20)")),
    ("entity_id", _col("bigint unsigned", nullable=True)),
    ("field", _col("varchar(100)", nullable=True)),  # 004
    ("accounting_value", _col("varchar(255)", nullable=True)),  # 004
    ("tax_authority_value", _col("varchar(255)", nullable=True)),  # 004
    ("difference", _col("decimal(15,2)", nullable=True)),  # 004
    ("error_type", _col("varchar(50)")),
    ("message", _col("text")),
    ("created_at", _col("datetime", default=TS)),
    indexes={
        "PRIMARY": _idx(True, "id"),
        "idx_reconciliation_errors_run": _idx(False, "run_id"),
    },
    foreign_keys={
        "fk_reconciliation_errors_run": _fk("reconciliation_runs", ("run_id",), "CASCADE"),
    },
)

# ---------------------------------------------------------------------------
# Migration 006 — application settings
# ---------------------------------------------------------------------------

APPLICATION_SETTINGS = _tbl(
    ("id", _col("bigint unsigned")),
    ("setting_key", _col("varchar(100)")),
    ("setting_value", _col("text", nullable=True)),
    ("value_type", _col("varchar(20)", default="string")),
    ("description", _col("varchar(255)", nullable=True)),
    ("created_at", _col("datetime", default=TS)),
    ("updated_at", _col("datetime", default=TS)),
    indexes={
        "PRIMARY": _idx(True, "id"),
        "uq_application_settings_key": _idx(True, "setting_key"),
    },
)

# ---------------------------------------------------------------------------
# Migration 007 — email deliveries
# ---------------------------------------------------------------------------

EMAIL_DELIVERIES = _tbl(
    ("id", _col("bigint unsigned")),
    ("company_id", _col("bigint unsigned")),
    ("run_id", _col("bigint unsigned")),
    ("recipient_email", _col("varchar(255)", nullable=True)),
    ("taxpayer_name", _col("varchar(255)", nullable=True)),
    ("taxpayer_tax_id", _col("varchar(50)", nullable=True)),
    ("invoice_count", _col("int unsigned", default="0")),
    ("subject", _col("varchar(255)", default="")),
    ("status", _col("varchar(20)", default="pending")),
    ("failure_reason", _col("varchar(255)", nullable=True)),
    ("request_id", _col("varchar(128)", nullable=True)),
    ("attempted_at", _col("datetime", nullable=True)),
    ("sent_at", _col("datetime", nullable=True)),
    ("created_at", _col("datetime", default=TS)),
    ("updated_at", _col("datetime", default=TS)),
    indexes={
        "PRIMARY": _idx(True, "id"),
        "uq_email_deliveries_run_recipient": _idx(True, "run_id", "recipient_email"),
        "idx_email_deliveries_company": _idx(False, "company_id"),
        "idx_email_deliveries_status": _idx(False, "status"),
        "idx_email_deliveries_recipient": _idx(False, "recipient_email"),
        # idx_email_deliveries_run was dropped by 010
    },
    foreign_keys={
        "fk_email_deliveries_company": _fk("companies", ("company_id",), "CASCADE"),
        "fk_email_deliveries_run": _fk("reconciliation_runs", ("run_id",), "CASCADE"),
    },
    checks=("chk_email_deliveries_status",),  # 009
)

# ---------------------------------------------------------------------------
# Migrations 008 + 011 — audit trail (traceability columns from 011)
# ---------------------------------------------------------------------------

AUDIT_LOGS = _tbl(
    ("id", _col("bigint unsigned")),
    ("actor_id", _col("bigint unsigned", nullable=True)),
    ("company_id", _col("bigint unsigned", nullable=True)),  # 011
    ("actor_email", _col("varchar(255)", nullable=True)),
    ("role", _col("varchar(50)", nullable=True)),
    ("actor_type", _col("varchar(20)", default="user")),  # 011
    ("action", _col("varchar(50)")),
    ("resource_type", _col("varchar(100)")),
    ("resource_id", _col("varchar(255)", nullable=True)),
    ("result", _col("varchar(20)", default="success")),
    ("metadata", _col("json", nullable=True)),
    ("before_state", _col("json", nullable=True)),  # 011
    ("after_state", _col("json", nullable=True)),  # 011
    ("request_id", _col("varchar(128)", nullable=True)),
    ("ip_address", _col("varchar(45)", nullable=True)),
    ("user_agent", _col("varchar(500)", nullable=True)),
    ("created_at", _col("datetime", default=TS)),
    indexes={
        "PRIMARY": _idx(True, "id"),
        "idx_audit_logs_created_at": _idx(False, "created_at"),
        "idx_audit_logs_actor": _idx(False, "actor_id"),
        "idx_audit_logs_action": _idx(False, "action"),
        "idx_audit_logs_resource": _idx(False, "resource_type", "resource_id"),
        "idx_audit_logs_result": _idx(False, "result"),
        "idx_audit_logs_request_id": _idx(False, "request_id"),
        "idx_audit_logs_company": _idx(False, "company_id"),  # 011
    },
    foreign_keys={
        "fk_audit_logs_actor": _fk("users", ("actor_id",), "SET NULL"),
        "fk_audit_logs_company": _fk("companies", ("company_id",), "SET NULL"),  # 011
    },
    checks=(  # 009
        "chk_audit_logs_action",
        "chk_audit_logs_result",
    ),
)

EXPECTED_TABLES: Dict[str, TableRule] = {
    "application_settings": APPLICATION_SETTINGS,
    "audit_logs": AUDIT_LOGS,
    "companies": COMPANIES,
    "email_deliveries": EMAIL_DELIVERIES,
    "import_batch_errors": IMPORT_BATCH_ERRORS,
    "import_batches": IMPORT_BATCHES,
    "invoice_items": INVOICE_ITEMS,
    "invoices": INVOICES,
    "reconciliation_errors": RECONCILIATION_ERRORS,
    "reconciliation_results": RECONCILIATION_RESULTS,
    "reconciliation_runs": RECONCILIATION_RUNS,
    "refresh_token_blocklist": REFRESH_TOKEN_BLOCKLIST,
    "roles": ROLES,
    "tax_invoice_items": TAX_INVOICE_ITEMS,
    "tax_invoices": TAX_INVOICES,
    "user_roles": USER_ROLES,
    "users": USERS,
}