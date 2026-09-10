"""Reconciliation report export helpers (CSV and XLSX).

Pure serialization of report rows into CSV text or an XLSX workbook. The
repository streams report rows as dictionaries; these helpers only decide how
to render them. Money arrives as Decimal and is written as a plain number in
XLSX (no rounding) and as its exact string form in CSV. Dates are serialized
as ISO strings in CSV and kept as native date/datetime cells in XLSX.
"""

import csv
import io
from datetime import date, datetime
from decimal import Decimal

CSV_MIMETYPE = "text/csv"
XLSX_MIMETYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

FORMATS = ("csv", "xlsx")

RESULTS_COLUMNS = (
    ("result_id", "id"),
    ("run_id", "run_id"),
    ("match_status", "match_status"),
    ("account_invoice_id", "account_invoice_id"),
    ("account_invoice_number", "account_invoice_number"),
    ("account_uuid", "account_uuid"),
    ("account_invoice_date", "account_invoice_date"),
    ("account_currency", "account_currency"),
    ("counterparty_name", "counterparty_name"),
    ("counterparty_tax_id", "counterparty_tax_id"),
    ("accounting_subtotal", "accounting_subtotal"),
    ("accounting_vat", "accounting_vat"),
    ("accounting_total", "accounting_total"),
    ("tax_invoice_id", "tax_invoice_id"),
    ("tax_internal_id", "tax_internal_id"),
    ("tax_uuid", "tax_uuid"),
    ("tax_issue_datetime", "tax_issue_datetime"),
    ("tax_currency", "tax_currency"),
    ("tax_total_sales", "tax_total_sales"),
    ("tax_net_amount", "tax_net_amount"),
    ("tax_vat_amount", "tax_vat_amount"),
    ("tax_total_amount", "tax_total_amount"),
    ("discrepancy_amount", "discrepancy_amount"),
    ("notes", "notes"),
    ("created_at", "created_at"),
)

ERRORS_COLUMNS = (
    ("error_id", "id"),
    ("run_id", "run_id"),
    ("source_type", "source_type"),
    ("entity_id", "entity_id"),
    ("error_type", "error_type"),
    ("field", "field"),
    ("accounting_value", "accounting_value"),
    ("tax_authority_value", "tax_authority_value"),
    ("difference", "difference"),
    ("message", "message"),
    ("created_at", "created_at"),
)

_SHEET_TITLES = {"results": "Results", "errors": "Errors"}


def _csv_cell(value):
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def render_csv(columns, rows) -> str:
    """Render report rows as CSV text with an exact header row."""
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow([header for header, _ in columns])
    for row in rows:
        writer.writerow([_csv_cell(row.get(key)) for _, key in columns])
    return buffer.getvalue()


def render_xlsx(sheet_title: str, columns, rows) -> bytes:
    """Render report rows into a valid XLSX workbook (bytes)."""
    from openpyxl import Workbook

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = sheet_title
    worksheet.append([header for header, _ in columns])
    for row in rows:
        worksheet.append([row.get(key) for _, key in columns])
    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()


def build_file(kind: str, rows, fmt: str) -> tuple:
    """Build export bytes for a report kind and format.

    Args:
        kind: 'results' or 'errors'.
        rows: iterable of report row dicts.
        fmt: 'csv' or 'xlsx'.

    Returns:
        ``(payload, mimetype, extension)``.

    Raises:
        ValueError: for an unknown kind or format.
    """
    fmt = (fmt or "").strip().lower()
    if fmt not in FORMATS:
        raise ValueError("format must be 'csv' or 'xlsx'")
    columns = RESULTS_COLUMNS if kind == "results" else ERRORS_COLUMNS
    sheet_title = _SHEET_TITLES.get(kind)
    if sheet_title is None:
        raise ValueError(f"unknown export kind '{kind}'")
    if fmt == "csv":
        return render_csv(columns, rows).encode("utf-8"), CSV_MIMETYPE, "csv"
    return render_xlsx(sheet_title, columns, rows), XLSX_MIMETYPE, "xlsx"