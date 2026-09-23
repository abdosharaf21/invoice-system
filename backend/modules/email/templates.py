"""Email templates for taxpayer reconciliation notifications.

Notifications go to the run's *taxpayers/counterparties* whose invoices
were affected by a reconciliation run (mismatched, missing from the tax
authority records, or invalid). Each template keeps a plain-text version
and an HTML version.

Safety rules enforced here:

* every dynamic value is HTML-escaped for the HTML body,
* only business identifiers are included (invoice number, date, amounts),
  never internal database ids, JWTs, request ids, SMTP credentials or
  stack traces,
* the recipient's own contact details (name / tax id) are echoed back so
  the email is clearly scoped to them.
"""

import html
from decimal import Decimal
from typing import Tuple

APP_NAME = "E-Invoice & Reconciliation"

_STATUS_LABELS = {
    "mismatched": "Mismatch",
    "missing_in_tax_authority": "Not found in tax records",
    "invalid": "Invalid - review needed",
}

_STATUS_ACTIONS = {
    "mismatched": "Please verify the details of this invoice.",
    "missing_in_tax_authority": (
        "This invoice could not be matched against the tax authority "
        "records; please confirm its details."
    ),
    "invalid": "This invoice could not be validated; please review its details.",
}


def _esc(value) -> str:
    return html.escape("" if value is None else str(value))


def _money(value) -> str:
    try:
        amount = Decimal(str(value))
    except (TypeError, ValueError, ArithmeticError):
        return "-"
    if not amount.is_finite():
        return "-"
    return f"{amount:,.2f}"


def _date(value) -> str:
    if value is None:
        return "-"
    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    return str(value)


def _status_label(status: str) -> str:
    return _STATUS_LABELS.get(status or "", status or "-").replace("_", " ")


def _status_action(status: str) -> str:
    return _STATUS_ACTIONS.get(status or "", "Please review this invoice.")


def render_reconciliation_discrepancy(context: dict) -> Tuple[str, str, str]:
    """Template for a run's per-taxpayer discrepancy summary.

    Args:
        context: Dictionary with keys:
            company_name, period,
            taxpayer: {"name": ..., "tax_id": ...},
            invoices: list of
                {"invoice_number", "invoice_date", "match_status",
                 "total_amount", "discrepancy_amount"}.
    """
    company = context.get("company_name") or f"Company #{context.get('company_id')}"
    period = context.get("period")
    taxpayer = context.get("taxpayer") or {}
    taxpayer_name = taxpayer.get("name") or "customer"
    tax_id = taxpayer.get("tax_id")
    invoices = context.get("invoices") or []

    subject = (
        f"[{APP_NAME}] Reconciliation notice - {company} ({period})"
        if company and period
        else f"[{APP_NAME}] Reconciliation notice"
    )

    greet = taxpayer_name
    tax_line = f"Tax identification: {tax_id}" if tax_id else None

    text_lines = [
        f"Dear {greet},",
        "",
        f"We reconciled the invoices involving {company} for the period "
        f"{period}. The following invoice(s) need your attention:",
        "",
    ]
    if tax_line:
        text_lines.append(tax_line)
        text_lines.append("")

    text_lines.append(
        "Invoice number | Date       | Status                  | "
        "Total ({cur}) | Difference".format(cur="EGP")
    )
    text_lines.append("-" * 76)
    for invoice in invoices:
        text_lines.append(
            "{num:<15} {date:<12} {status:<23} {total:>12}  {diff:>8}".format(
                num=str(invoice.get("invoice_number") or "-")[:15],
                date=str(_date(invoice.get("invoice_date"))) or "-",
                status=str(_status_label(invoice.get("match_status")))[:23],
                total=_money(invoice.get("total_amount")),
                diff=_money(invoice.get("discrepancy_amount")),
            )
        )
    text_lines.append("")

    for invoice in invoices:
        text_lines.append(f"- {invoice.get('invoice_number') or '-'}: "
                          f"{_status_action(invoice.get('match_status'))}")

    text_lines.append("")
    text_lines.append("Please review the affected invoice(s) above and contact us "
                      "if anything is incorrect.")
    text_lines.append("")
    text_lines.append("This is an automated message from the E-Invoice & "
                      "Reconciliation system.")
    text_body = "\n".join(text_lines)

    c_company = _esc(company)
    c_period = _esc(period)
    c_greet = _esc(greet)
    c_tax_id = _esc(tax_id) if tax_id else None

    rows = []
    for invoice in invoices:
        rows.append(
            "<tr>"
            f"<td>{_esc(invoice.get('invoice_number') or '-')}</td>"
            f"<td>{_esc(_date(invoice.get('invoice_date')))}</td>"
            f"<td>{_esc(_status_label(invoice.get('match_status')))}</td>"
            f"<td align=\"right\">{_esc(_money(invoice.get('total_amount')))}</td>"
            f"<td align=\"right\">{_esc(_money(invoice.get('discrepancy_amount')))}</td>"
            "</tr>"
        )
    table_rows = "".join(rows)

    html_body = (
        "<html><body style=\"font-family: Arial, sans-serif;\">"
        f"<h2>Reconciliation notice</h2>"
        f"<p>Dear {c_greet},</p>"
        f"<p>We reconciled the invoices involving <strong>{c_company}</strong> "
        f"for the period <strong>{c_period}</strong>. The following "
        f"invoice(s) need your attention:</p>"
        + (f"<p><strong>Tax identification:</strong> {c_tax_id}</p>"
           if c_tax_id else "")
        + "<table cellpadding=\"4\" cellspacing=\"0\" "
          "style=\"border-collapse: collapse;\">"
          "<tr>"
          "<th align=\"left\">Invoice</th><th align=\"left\">Date</th>"
          "<th align=\"left\">Status</th>"
          "<th align=\"right\">Total (EGP)</th>"
          "<th align=\"right\">Difference</th>"
          "</tr>"
        + table_rows
        + "</table>"
        + "".join(
            f"<p style=\"color: #666;\">- {_esc(invoice.get('invoice_number') or '-')}: "
            f"{_esc(_status_action(invoice.get('match_status')))}</p>"
            for invoice in invoices
        )
        + "<p>Please review the affected invoice(s) above and contact us if "
          "anything is incorrect.</p>"
        "<p style=\"color: #666;\">This is an automated message from the "
        "E-Invoice &amp; Reconciliation system.</p>"
        "</body></html>"
    )
    return subject, text_body, html_body