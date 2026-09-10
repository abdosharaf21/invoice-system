/**
 * Shared report panels — enterprise tables, filter toolbars, summary strip
 * and export controls used by both the run-detail view and the Reports page.
 *
 * Tables are fed directly by the backend's pagination envelope
 * ({items, page, page_size, total, total_pages}). No client-side pagination
 * or business calculations happen here.
 */

import { el, clear } from "../utils/dom.js";
import {
  escapeHtml,
} from "../utils/escape.js";
import {
  formatMoney,
  formatDate,
  formatDateTime,
  matchStatusLabel,
  errorTypeLabel,
  sourceTypeLabel,
} from "../utils/format.js";
import { renderPagination } from "./pagination.js";
import { showModal } from "./modal.js";

/* ---------------------------------------------------------------------------
   Summary strip (Finexa-style report summary for a run)
--------------------------------------------------------------------------- */

export function renderSummaryStrip(container, summary) {
  clear(container);
  if (!summary) return;

  const s = summary.summary || {};
  const counts = [
    ["Matched", s.matched, "kpi is-accent", "kpi__value"],
    ["Mismatched", s.mismatched, "kpi is-warning", "kpi__value"],
    ["Missing in Tax Authority", s["missing_in_tax_authority"], "kpi is-warning", "kpi__value"],
    ["Extra in Tax Authority", s["extra_in_tax_authority"], "kpi is-info", "kpi__value"],
    ["Invalid", s.invalid, "kpi is-danger", "kpi__value"],
    ["Total results", s.total_results, "kpi is-primary", "kpi__value"],
    ["Unmatched", s.unmatched, "kpi is-warning", "kpi__value"],
    ["Errors", s.errors, "kpi is-danger", "kpi__value"],
  ];

  const grid = el("div", { className: "kpi-grid" });
  for (const [label, value, kpiClass] of counts) {
    grid.appendChild(
      el("div", { className: kpiClass },
        el("div", { className: "kpi__label" }, label),
        el("div", { className: "kpi__value" }, String(value ?? 0)),
      ),
    );
  }
  container.appendChild(grid);
}

export function renderStatusDistribution(container, summary) {
  clear(container);
  if (!summary || !summary.summary) return;

  const s = summary.summary;
  const total = s.total_results || 0;
  const bars = [
    ["matched", "Matched"],
    ["mismatched", "Mismatched"],
    ["missing_in_tax_authority", "Missing in Tax Authority"],
    ["extra_in_tax_authority", "Extra in Tax Authority"],
    ["invalid", "Invalid"],
  ];

  container.appendChild(
    el("div", { className: "bar-list" },
      ...bars.map(([key, label]) => {
        const value = s[key] || 0;
        const pct = total ? Math.round((value / total) * 100) : 0;
        return el("div", { className: "bar-row", style: "margin-block-end:0.6rem" },
          el("div", { className: "text-sm" }, label),
          el("div", { className: "bar-track" },
            el("div", {
              className: `bar-fill bar-fill--${key}`,
              style: `width:${pct}%`,
              role: "img",
              "aria-label": `${label}: ${value} (${pct}%)`,
            }),
          ),
          el("div", { className: "bar-value" }, String(value)),
        );
      }),
    ),
  );
}

/* ---------------------------------------------------------------------------
   Results table
--------------------------------------------------------------------------- */

/**
 * Render the results table from a pagination envelope.
 * @param {HTMLElement} container
 * @param {object} envelope — {items, page, page_size, total, total_pages}
 * @param {object} opts — { emptyMessage, onRowAction, onNavigate, onPageSize }
 */
export function renderResultsTable(container, envelope, opts = {}) {
  clear(container);
  const items = (envelope && envelope.items) || [];

  const wrap = el("div", { className: "table-wrap" });
  const table = el("table", { className: "etable" });

  table.appendChild(
    el("thead",
      el("tr",
        el("th", null, "Status"),
        el("th", null, "Invoice #"),
        el("th", null, "UUID"),
        el("th", null, "Tax Ref"),
        el("th", null, "Invoice Date"),
        el("th", null, "Cur"),
        el("th", { className: "num" }, "Accounting"),
        el("th", { className: "num" }, "Tax Authority"),
        el("th", { className: "num" }, "Discrepancy"),
        opts.onRowAction ? el("th", { className: "text-xs text-muted" }, "Action") : null,
      ),
    ),
  );

  const tbody = el("tbody");
  for (const row of items) {
    const discrepancy = Number(row["discrepancy_amount"]);
    const discrepancyCls =
      Number.isNaN(discrepancy) ? "" : discrepancy === 0 ? "" : discrepancy < 0 ? "neg" : "pos";

    const tr = el("tr", opts.onRowAction
      ? { className: "is-row-click", dataset: { id: row.id } }
      : {},
      el("td", null, el("span", { className: `badge badge--${row.match_status}` }, matchStatusLabel(row.match_status))),
      el("td", null, el("span", { className: "mono" }, escapeHtml(row["account_invoice_number"] || "—"))),
      el("td", null, el("code", { className: "text-xs text-muted" }, escapeHtml(truncate(row.account_uuid || row.tax_uuid || "")) || "—")),
      el("td", null, el("span", { className: "mono" }, escapeHtml(row.tax_internal_id || "—"))),
      el("td", null, formatDate(row["account_invoice_date"])),
      el("td", null, escapeHtml(row.account_currency || "—")),
      el("td", { className: "num" }, formatMoney(row.accounting_total)),
      el("td", { className: "num" }, formatMoney(row.tax_total_amount)),
      el("td", { className: "num " + discrepancyCls }, formatMoney(row["discrepancy_amount"])),
      opts.onRowAction
        ? el("td", null,
            el("button", { className: "btn btn-secondary btn-sm", onClick: () => opts.onRowAction(row) }, "Details"))
        : null,
    );
    tbody.appendChild(tr);
  }

  if (items.length === 0) {
    tbody.appendChild(
      el("tr", null, el("td", { colSpan: opts.onRowAction ? 10 : 9, className: "etable-empty" },
        opts.emptyMessage || "No results for the selected filters.", " ", opts.hint || "")),
    );
  }

  table.appendChild(tbody);
  wrap.appendChild(table);
  container.appendChild(wrap);

  if (envelope && opts.onNavigate && !opts.hidePagination) {
    const pageBox = el("div");
    container.appendChild(pageBox);
    renderPagination(pageBox, envelope, opts.onNavigate, opts.onPageSize);
  }
}

/* ---------------------------------------------------------------------------
   Errors table
--------------------------------------------------------------------------- */

export function renderErrorsTable(container, envelope, opts = {}) {
  clear(container);
  const items = (envelope && envelope.items) || [];

  const wrap = el("div", { className: "table-wrap" });
  const table = el("table", { className: "etable" });

  table.appendChild(
    el("thead",
      el("tr",
        el("th", null, "Source"),
        el("th", { className: "num" }, "Entity"),
        el("th", null, "Error"),
        el("th", null, "Field"),
        el("th", { className: "num" }, "Accounting"),
        el("th", { className: "num" }, "Tax Authority"),
        el("th", { className: "num" }, "Difference"),
        el("th", null, "Message"),
      ),
    ),
  );

  const tbody = el("tbody");
  for (const row of items) {
    const diff = Number(row.difference);
    const diffCls = Number.isNaN(diff) ? "" : diff < 0 ? "neg" : "pos";
    const msg =
      typeof row.message === "string" && row.message.length > 90
        ? row.message.slice(0, 90) + "…"
        : row.message;

    tbody.appendChild(
      el("tr",
        el("td",
          el("span", { className: `badge badge--${row.source_type === "tax" ? "tax" : "account"}` },
            sourceTypeLabel(row.source_type))),
        el("td", { className: "num" }, String(row.entity_id ?? "—")),
        el("td",
          el("span", { className: "text-sm", title: String(row.error_type || "") },
            escapeHtml(errorTypeLabel(row.error_type)))),
        el("td", null, el("code", { className: "text-xs" }, escapeHtml(row.field || "—"))),
        el("td", { className: "num" }, String(row.accounting_value ?? "—")),
        el("td", { className: "num" }, String(row.tax_authority_value ?? "—")),
        el("td", { className: "num " + diffCls }, String(row.difference ?? "—")),
        el("td", { className: "text-sm text-secondary", style: "white-space:normal;min-width:220px" },
          escapeHtml(msg || "—")),
      ),
    );
  }

  if (items.length === 0) {
    tbody.appendChild(
      el("tr", null, el("td", { colSpan: 8, className: "etable-empty" },
        opts.emptyMessage || "No errors for the selected filters.")),
    );
  }

  table.appendChild(tbody);
  wrap.appendChild(table);
  container.appendChild(wrap);

  if (envelope && opts.onNavigate && !opts.hidePagination) {
    const pageBox = el("div");
    container.appendChild(pageBox);
    renderPagination(pageBox, envelope, opts.onNavigate, opts.onPageSize);
  }
}

/* ---------------------------------------------------------------------------
   Result detail modal — a side-by-side comparison of the two sides.
   Uses ONLY fields the backend provides on the enriched result row.
--------------------------------------------------------------------------- */

const FIELD_PAIRS = [
  { label: "Invoice date", acct: "account_invoice_date", tax: "tax_issue_datetime", type: "date" },
  { label: "Currency", acct: "account_currency", tax: "tax_currency", type: "string" },
  { label: "Subtotal", acct: "accounting_subtotal", tax: "tax_total_sales", type: "money" },
  { label: "VAT", acct: "accounting_vat", tax: "tax_vat_amount", type: "money" },
  { label: "Total", acct: "accounting_total", tax: "tax_total_amount", type: "money" },
];

function fmtField(value, type) {
  if (value === null || value === undefined) return "—";
  if (type === "money") return formatMoney(value);
  if (type === "date") return formatDate(value);
  return escapeHtml(String(value));
}

function valuesDiffer(a, b, type) {
  if (a === null || a === undefined || b === null || b === undefined) return false;
  if (type === "money" || type === "string") return Number(a) !== Number(b);
  return String(a).slice(0, 10) !== String(b).slice(0, 10);
}

export function openResultDetail(row) {
  const discrepancy = Number(row["discrepancy_amount"]);
  const discrepancyRow =
    discrepancy === 0 || Number.isNaN(discrepancy)
      ? el("tr", null,
          el("td", null, el("strong", null, "Discrepancy")),
          el("td", null, "—"),
          el("td", null, "—"),
          el("td", { className: "differ" }, discrepancy === 0 ? "Driven by errors or matches" : String(row["discrepancy_amount"])))
      : el("tr", null,
          el("td", null, el("strong", null, "Discrepancy")),
          el("td", null, "—"),
          el("td", null, "—"),
          el("td", { className: "differ" }, formatMoney(row["discrepancy_amount"])));

  const body = el("div", null,
    el("div", { className: "dl", style: "margin-block-end:1.25rem" },
      el("div", null, el("dt", null, "Invoice number"), el("dd", { className: "mono" }, escapeHtml(row["account_invoice_number"] || "—"))),
      el("div", null, el("dt", null, "Accounting UUID"), el("dd", { className: "mono text-xs" }, escapeHtml(row.account_uuid || "—"))),
      el("div", null, el("dt", null, "Tax Authority Ref"), el("dd", { className: "mono" }, escapeHtml(row.tax_internal_id || "—"))),
      el("div", null, el("dt", null, "Tax UUID"), el("dd", { className: "mono text-xs" }, escapeHtml(row.tax_uuid || "—"))),
      el("div", null, el("dt", null, "Counterparty"), el("dd", escapeHtml(row.counterparty_name || "—"))),
      el("div", null, el("dt", null, "Counterparty Tax ID"), el("dd", { className: "mono" }, escapeHtml(row.counterparty_tax_id || "—"))),
    ),
    el("table", { className: "cmp-table" },
      el("thead",
        el("tr",
          el("th", { className: "text-xs text-muted" }, "Field"),
          el("th", { className: "text-xs text-muted" }, "Accounting"),
          el("th", { className: "text-xs text-muted" }, "Tax Authority"),
          el("th", { className: "text-xs text-muted" }, "Difference"),
        ),
      ),
      el("tbody",
        ...FIELD_PAIRS.map((pair) => {
          const acct = row[pair.acct];
          const tax = row[pair.tax];
          const differ = valuesDiffer(acct, tax, pair.type);
          return el("tr", { className: differ ? "differ" : "" },
            el("td", null, el("strong", null, pair.label)),
            el("td", null, fmtField(acct, pair.type)),
            el("td", null, fmtField(tax, pair.type)),
            el("td", null, differ ? "Differs" : "Equal"),
          );
        }),
        discrepancyRow,
      ),
    ),
  );

  const close = showModal("Result details", body, null);
  void close;
}

/* ---------------------------------------------------------------------------
   Toolbars
--------------------------------------------------------------------------- */

export const RESULT_STATUS_OPTIONS = [
  "matched",
  "mismatched",
  "missing_in_tax_authority",
  "extra_in_tax_authority",
  "invalid",
];

export const ERROR_TYPE_CODES = [
  "INVALID_UUID", "INVALID_DATE", "INVALID_FINANCIAL_VALUE",
  "INVOICE_DATE_MISMATCH", "CURRENCY_MISMATCH",
  "COUNTERPARTY_TAX_ID_MISMATCH", "COUNTERPARTY_NAME_MISMATCH",
  "SUBTOTAL_AMOUNT_MISMATCH", "DISCOUNT_AMOUNT_MISMATCH", "NET_AMOUNT_MISMATCH",
  "VAT_AMOUNT_MISMATCH", "TOTAL_AMOUNT_MISMATCH",
  "ITEM_COUNT_MISMATCH", "ITEM_QUANTITY_SUM_MISMATCH",
  "ITEM_VAT_SUM_MISMATCH", "ITEM_TOTAL_SUM_MISMATCH",
];

export function buildResultsToolbar(toolbar, currentFilters, onApply, onReset) {
  clear(toolbar);

  const f = currentFilters || {};
  const makeField = (label, control) =>
    el("div", { className: "toolbar__field" },
      el("label", { className: "toolbar__label" }, label),
      control,
    );

  const statusSel = el("select", { className: "select", "aria-label": "Match status" },
    el("option", { value: "" }, "Any status"),
    ...RESULT_STATUS_OPTIONS.map((s) => el("option", { value: s }, matchStatusLabel(s))),
  );
  if (f.match_status) statusSel.value = f.match_status;

  const uuidInput = el("input", { className: "input", type: "text", value: f.uuid || "", placeholder: "e.g. d3c6e4f7-…", "aria-label": "UUID" });
  const numInput = el("input", { className: "input", type: "text", value: f.invoice_number || "", placeholder: "e.g. INV-100", "aria-label": "Invoice number" });
  const fromInput = el("input", { className: "input", type: "date", value: f.date_from || "", "aria-label": "Date from" });
  const toInput = el("input", { className: "input", type: "date", value: f.date_to || "", "aria-label": "Date to" });
  const sizeSel = el("select", { className: "select", "aria-label": "Page size", value: String(f.page_size || 50) },
    ...["10", "25", "50", "100", "200"].map((n) => el("option", { value: n }, `${n} / page`)));
  if (f.page_size && !["10", "25", "50", "100", "200"].includes(String(f.page_size))) {
    sizeSel.appendChild(el("option", { value: String(f.page_size) }, `${f.page_size} / page`));
    sizeSel.value = String(f.page_size);
  }

  toolbar.appendChild(
    el("form", { className: "toolbar", onsubmit: (e) => { e.preventDefault(); onApply(readFilters()); } },
      makeField("Status", statusSel),
      makeField("UUID", uuidInput),
      makeField("Invoice #", numInput),
      makeField("From", fromInput),
      makeField("To", toInput),
      makeField("Page size", sizeSel),
      el("div", { className: "form-actions", style: "margin:0 0 0 auto;" },
        el("button", { className: "btn btn-secondary", type: "button", onClick: () => { onReset(); } }, "Reset"),
        el("button", { className: "btn btn-primary", type: "submit" }, "Apply"),
      ),
    ),
  );

  function readFilters() {
    const filters = {};
    if (statusSel.value) filters.match_status = statusSel.value;
    if (uuidInput.value.trim()) filters.uuid = uuidInput.value.trim();
    if (numInput.value.trim()) filters.invoice_number = numInput.value.trim();
    if (fromInput.value) filters.date_from = fromInput.value;
    if (toInput.value) filters.date_to = toInput.value;
    if (sizeSel.value && Number(sizeSel.value) !== 50) filters.page_size = Number(sizeSel.value);
    return filters;
  }
}

export function buildErrorsToolbar(toolbar, currentFilters, onApply, onReset) {
  clear(toolbar);

  const f = currentFilters || {};
  const makeField = (label, control) =>
    el("div", { className: "toolbar__field" },
      el("label", { className: "toolbar__label" }, label),
      control,
    );

  const typeInput = el("input", { className: "input", type: "text", value: f.error_type || "", list: "error-type-options", placeholder: "e.g. TOTAL_AMOUNT_MISMATCH", "aria-label": "Error type" });
  const typeList = el("datalist", { id: "error-type-options" },
    ...ERROR_TYPE_CODES.map((c) => el("option", { value: c }, errorTypeLabel(c))),
  );
  toolbar.appendChild(typeList);

  const sourceSel = el("select", { className: "select", "aria-label": "Source type" },
    el("option", { value: "" }, "Any source"),
    el("option", { value: "account" }, "Accounting"),
    el("option", { value: "tax" }, "Tax Authority"),
  );
  if (f.source_type) sourceSel.value = f.source_type;

  const sizeSel = el("select", { className: "select", "aria-label": "Page size", value: String(f.page_size || 50) },
    ...["10", "25", "50", "100", "200"].map((n) => el("option", { value: n }, `${n} / page`)));
  if (f.page_size && !["10", "25", "50", "100", "200"].includes(String(f.page_size))) {
    sizeSel.appendChild(el("option", { value: String(f.page_size) }, `${f.page_size} / page`));
    sizeSel.value = String(f.page_size);
  }

  toolbar.appendChild(
    el("form", { className: "toolbar", onsubmit: (e) => { e.preventDefault(); onApply(readFilters()); } },
      makeField("Error type", typeInput),
      makeField("Source", sourceSel),
      makeField("Page size", sizeSel),
      el("div", { className: "form-actions", style: "margin:0 0 0 auto;" },
        el("button", { className: "btn btn-secondary", type: "button", onClick: () => { onReset(); } }, "Reset"),
        el("button", { className: "btn btn-primary", type: "submit" }, "Apply"),
      ),
    ),
  );

  function readFilters() {
    const filters = {};
    if (typeInput.value.trim()) filters.error_type = typeInput.value.trim();
    if (sourceSel.value) filters.source_type = sourceSel.value;
    if (sizeSel.value && Number(sizeSel.value) !== 50) filters.page_size = Number(sizeSel.value);
    return filters;
  }
}

/* ---------------------------------------------------------------------------
   Export controls
--------------------------------------------------------------------------- */

export function renderExportControls(container, onExport, opts = {}) {
  clear(container);
  container.appendChild(
    el("div", { className: "dropdown" },
      el("button", { className: "btn btn-secondary", type: "button", "aria-haspopup": "menu", onClick: (e) => {
          const menu = e.currentTarget.parentNode.querySelector(".dropdown__menu");
          menu.classList.toggle("is-open");
        } }, "Export"),
      el("div", { className: "dropdown__menu", role: "menu" },
        el("button", { className: "dropdown-item", role: "menuitem", onClick: () => onExport("csv") }, "CSV (.csv)"),
        el("button", { className: "dropdown-item", role: "menuitem", onClick: () => onExport("xlsx") }, "Excel (.xlsx)"),
      ),
    ),
  );
}

function truncate(value, max = 30) {
  const s = String(value || "");
  return s.length > max ? s.slice(0, max) + "…" : s;
}