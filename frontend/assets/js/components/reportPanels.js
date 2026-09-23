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
  formatMoney,
  formatDate,
  formatDateTime,
  matchStatusLabel,
  statusClassToken,
  errorTypeLabel,
  sourceTypeLabel,
} from "../utils/format.js";
import { renderPagination } from "./pagination.js";
import { showModal } from "./modal.js";
import { t } from "../i18n/index.js";

/* ---------------------------------------------------------------------------
   Summary strip (Finexa-style report summary for a run)
--------------------------------------------------------------------------- */

export function renderSummaryStrip(container, summary) {
  clear(container);
  if (!summary) return;

  const s = summary.summary || {};
  const counts = [
    ["strip.matched", s.matched, "kpi is-accent"],
    ["strip.mismatched", s.mismatched, "kpi is-warning"],
    ["strip.missing", s["missing_in_tax_authority"], "kpi is-warning"],
    ["strip.extra", s["extra_in_tax_authority"], "kpi is-info"],
    ["strip.invalid", s.invalid, "kpi is-danger"],
    ["strip.total", s.total_results, "kpi is-primary"],
    ["strip.unmatched", s.unmatched, "kpi is-warning"],
    ["strip.errors", s.errors, "kpi is-danger"],
  ];

  const grid = el("div", { className: "kpi-grid" });
  for (const [labelKey, value, kpiClass] of counts) {
    grid.appendChild(
      el("div", { className: kpiClass },
        el("div", { className: "kpi__label" }, t(labelKey)),
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
    ["matched", "status.matched"],
    ["mismatched", "status.mismatched"],
    ["missing_in_tax_authority", "status.missing_in_tax_authority"],
    ["extra_in_tax_authority", "status.extra_in_tax_authority"],
    ["invalid", "status.invalid"],
  ];

  container.appendChild(
    el("div", { className: "bar-list" },
      ...bars.map(([key, labelKey]) => {
        const value = s[key] || 0;
        const pct = total ? Math.round((value / total) * 100) : 0;
        const label = t(labelKey);
        const tip = `${label}: ${value} (${pct}%)`;
        return el("div", { className: "bar-row", style: "margin-block-end:var(--space-2)", title: tip },
          el("div", { className: "text-sm" }, label),
          el("div", { className: "bar-track" },
            el("div", {
              className: `bar-fill bar-fill--${key}`,
              style: `width:${pct}%`,
              role: "img",
              "aria-label": tip,
            }),
          ),
          el("div", { className: "bar-value", "aria-label": tip },
            String(value),
            el("span", { className: "bar-value__pct" }, ` (${pct}%)`),
          ),
        );
      }),
      el("div", { className: "text-xs text-muted bar-scale", style: "margin-block-start:var(--space-2);" }, t("strip.scaleCaption")),
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
        el("th", null, t("report.resultsThStatus")),
        el("th", null, t("report.resultsThInvoice")),
        el("th", null, t("report.resultsThUuid")),
        el("th", null, t("report.resultsThTaxRef")),
        el("th", null, t("report.resultsThDate")),
        el("th", null, t("report.resultsThCur")),
        el("th", { className: "num" }, t("report.resultsThAccounting")),
        el("th", { className: "num" }, t("report.resultsThTax")),
        el("th", { className: "num" }, t("report.resultsThDiscrepancy")),
        opts.onRowAction ? el("th", { className: "text-xs text-muted" }, t("common.action")) : null,
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
      el("td", null, el("span", { className: `badge badge--${statusClassToken(row.match_status)}` }, matchStatusLabel(row.match_status))),
      el("td", null, el("span", { className: "mono" }, row["account_invoice_number"] || "—")),
      el("td", null, el("code", { className: "text-xs text-muted" }, truncate(row.account_uuid || row.tax_uuid || "") || "—")),
      el("td", null, el("span", { className: "mono" }, row.tax_internal_id || "—")),
      el("td", null, formatDate(row["account_invoice_date"])),
      el("td", null, row.account_currency || "—"),
      el("td", { className: "num" }, formatMoney(row.accounting_total)),
      el("td", { className: "num" }, formatMoney(row.tax_total_amount)),
      el("td", { className: "num " + discrepancyCls }, formatMoney(row["discrepancy_amount"])),
      opts.onRowAction
        ? el("td", null,
            el("button", { className: "btn btn-secondary btn-sm", onClick: () => opts.onRowAction(row) }, t("report.details")))
        : null,
    );
    tbody.appendChild(tr);
  }

  if (items.length === 0) {
    tbody.appendChild(
      el("tr", null, el("td", { colSpan: opts.onRowAction ? 10 : 9, className: "etable-empty" },
        opts.emptyMessage || t("report.noResults"), " ", opts.hint || "")),
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
        el("th", null, t("report.errorsThSource")),
        el("th", { className: "num" }, t("report.errorsThEntity")),
        el("th", null, t("report.errorsThError")),
        el("th", null, t("report.errorsThField")),
        el("th", { className: "num" }, t("report.errorsThAccounting")),
        el("th", { className: "num" }, t("report.errorsThTax")),
        el("th", { className: "num" }, t("report.errorsThDifference")),
        el("th", null, t("report.errorsThMessage")),
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
            errorTypeLabel(row.error_type))),
        el("td", null, el("code", { className: "text-xs" }, row.field || "—")),
        el("td", { className: "num" }, String(row.accounting_value ?? "—")),
        el("td", { className: "num" }, String(row.tax_authority_value ?? "—")),
        el("td", { className: "num " + diffCls }, String(row.difference ?? "—")),
        el("td", { className: "text-sm text-secondary", style: "white-space:normal;min-width:220px" },
          msg || "—"),
      ),
    );
  }

  if (items.length === 0) {
    tbody.appendChild(
      el("tr", null, el("td", { colSpan: 8, className: "etable-empty" },
        opts.emptyMessage || t("report.noErrors"))),
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
  { labelKey: "report.fieldInvoiceDate", acct: "account_invoice_date", tax: "tax_issue_datetime", type: "date" },
  { labelKey: "report.fieldCurrency", acct: "account_currency", tax: "tax_currency", type: "string" },
  { labelKey: "report.fieldSubtotal", acct: "accounting_subtotal", tax: "tax_total_sales", type: "money" },
  { labelKey: "report.fieldVat", acct: "accounting_vat", tax: "tax_vat_amount", type: "money" },
  { labelKey: "report.fieldTotal", acct: "accounting_total", tax: "tax_total_amount", type: "money" },
];

function fmtField(value, type) {
  if (value === null || value === undefined) return "—";
  if (type === "money") return formatMoney(value);
  if (type === "date") return formatDate(value);
  return String(value);
}

function valuesDiffer(a, b, type) {
  if (a === null || a === undefined || b === null || b === undefined) return false;
  if (type === "money" || type === "string") return Number(a) !== Number(b);
  return String(a).slice(0, 10) !== String(b).slice(0, 10);
}

export function openResultDetail(row) {
  const discrepancy = Number(row["discrepancy_amount"]);
  const accordance = discrepancy === 0 ? t("report.detailDrivenByErrors") : formatMoney(row["discrepancy_amount"]);
  const discrepancyRow =
    discrepancy === 0 || Number.isNaN(discrepancy)
      ? el("tr", null,
          el("td", null, el("strong", null, t("report.detailDiscrepancy"))),
          el("td", null, "—"),
          el("td", null, "—"),
          el("td", { className: "differ" }, accordance))
      : el("tr", null,
          el("td", null, el("strong", null, t("report.detailDiscrepancy"))),
          el("td", null, "—"),
          el("td", null, "—"),
          el("td", { className: "differ" }, formatMoney(row["discrepancy_amount"])));

  const body = el("div", null,
    el("div", { className: "dl", style: "margin-block-end:var(--space-5)" },
      el("div", null, el("dt", null, t("report.detailInvoice")), el("dd", { className: "mono" }, row["account_invoice_number"] || "—")),
      el("div", null, el("dt", null, t("report.detailAcctUuid")), el("dd", { className: "mono text-xs" }, row.account_uuid || "—")),
      el("div", null, el("dt", null, t("report.detailTaxRef")), el("dd", { className: "mono" }, row.tax_internal_id || "—")),
      el("div", null, el("dt", null, t("report.detailTaxUuid")), el("dd", { className: "mono text-xs" }, row.tax_uuid || "—")),
      el("div", null, el("dt", null, t("report.detailCounterparty")), el("dd", row.counterparty_name || "—")),
      el("div", null, el("dt", null, t("report.detailCounterpartyTaxId")), el("dd", { className: "mono" }, row.counterparty_tax_id || "—")),
    ),
    el("table", { className: "cmp-table" },
      el("thead",
        el("tr",
          el("th", { className: "text-xs text-muted" }, t("report.detailField")),
          el("th", { className: "text-xs text-muted" }, t("report.detailAccounting")),
          el("th", { className: "text-xs text-muted" }, t("report.detailTax")),
          el("th", { className: "text-xs text-muted" }, t("report.detailDifference")),
        ),
      ),
      el("tbody",
        ...FIELD_PAIRS.map((pair) => {
          const acct = row[pair.acct];
          const tax = row[pair.tax];
          const differ = valuesDiffer(acct, tax, pair.type);
          return el("tr", { className: differ ? "differ" : "" },
            el("td", null, el("strong", null, t(pair.labelKey))),
            el("td", null, fmtField(acct, pair.type)),
            el("td", null, fmtField(tax, pair.type)),
            el("td", null, differ ? t("report.detailDiffers") : t("report.detailEqual")),
          );
        }),
        discrepancyRow,
      ),
    ),
  );

  const close = showModal(t("report.detailTitle"), body, null);
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

  const statusSel = el("select", { className: "select", "aria-label": t("report.labelStatus") },
    el("option", { value: "" }, t("report.statusAny")),
    ...RESULT_STATUS_OPTIONS.map((s) => el("option", { value: s }, matchStatusLabel(s))),
  );
  if (f.match_status) statusSel.value = f.match_status;

  const uuidInput = el("input", { className: "input", type: "text", value: f.uuid || "", placeholder: t("report.uuidPlaceholder"), "aria-label": t("report.ariaUuid") });
  const numInput = el("input", { className: "input", type: "text", value: f.invoice_number || "", placeholder: t("report.invoicePlaceholder"), "aria-label": t("report.ariaInvoice") });
  const fromInput = el("input", { className: "input", type: "date", value: f.date_from || "", "aria-label": t("report.ariaDateFrom") });
  const toInput = el("input", { className: "input", type: "date", value: f.date_to || "", "aria-label": t("report.ariaDateTo") });
  const sizeSel = el("select", { className: "select", "aria-label": t("report.labelPageSize"), value: String(f.page_size || 50) },
    ...["10", "25", "50", "100", "200"].map((n) => el("option", { value: n }, `${n} ${t("common.perPage")}`)));
  if (f.page_size && !["10", "25", "50", "100", "200"].includes(String(f.page_size))) {
    sizeSel.appendChild(el("option", { value: String(f.page_size) }, `${f.page_size} ${t("common.perPage")}`));
    sizeSel.value = String(f.page_size);
  }

  toolbar.appendChild(
    el("form", { className: "toolbar", onsubmit: (e) => { e.preventDefault(); onApply(readFilters()); } },
      makeField(t("report.labelStatus"), statusSel),
      makeField(t("report.labelUuid"), uuidInput),
      makeField(t("report.labelInvoice"), numInput),
      makeField(t("report.labelFrom"), fromInput),
      makeField(t("report.labelTo"), toInput),
      makeField(t("report.labelPageSize"), sizeSel),
      el("div", { className: "form-actions", style: "margin:0;margin-inline-start:auto;" },
        el("button", { className: "btn btn-secondary", type: "button", onClick: () => { onReset(); } }, t("common.reset")),
        el("button", { className: "btn btn-primary", type: "submit" }, t("common.apply")),
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

  const typeInput = el("input", { className: "input", type: "text", value: f.error_type || "", list: "error-type-options", placeholder: t("report.errorTypePlaceholder"), "aria-label": t("report.ariaErrorType") });
  const typeList = el("datalist", { id: "error-type-options" },
    ...ERROR_TYPE_CODES.map((c) => el("option", { value: c }, errorTypeLabel(c))),
  );
  toolbar.appendChild(typeList);

  const sourceSel = el("select", { className: "select", "aria-label": t("report.ariaSourceType") },
    el("option", { value: "" }, t("report.sourceAny")),
    el("option", { value: "account" }, t("report.sourceAccounting")),
    el("option", { value: "tax" }, t("report.sourceTax")),
  );
  if (f.source_type) sourceSel.value = f.source_type;

  const sizeSel = el("select", { className: "select", "aria-label": t("report.labelPageSize"), value: String(f.page_size || 50) },
    ...["10", "25", "50", "100", "200"].map((n) => el("option", { value: n }, `${n} ${t("common.perPage")}`)));
  if (f.page_size && !["10", "25", "50", "100", "200"].includes(String(f.page_size))) {
    sizeSel.appendChild(el("option", { value: String(f.page_size) }, `${f.page_size} ${t("common.perPage")}`));
    sizeSel.value = String(f.page_size);
  }

  toolbar.appendChild(
    el("form", { className: "toolbar", onsubmit: (e) => { e.preventDefault(); onApply(readFilters()); } },
      makeField(t("report.labelErrorType"), typeInput),
      makeField(t("report.labelSource"), sourceSel),
      makeField(t("report.labelPageSize"), sizeSel),
      el("div", { className: "form-actions", style: "margin:0;margin-inline-start:auto;" },
        el("button", { className: "btn btn-secondary", type: "button", onClick: () => { onReset(); } }, t("common.reset")),
        el("button", { className: "btn btn-primary", type: "submit" }, t("common.apply")),
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

  const menu = el("div", { className: "dropdown__menu", role: "menu" },
    el("button", { className: "dropdown-item", role: "menuitem", type: "button", onClick: () => { setOpen(false); onExport("csv"); } }, t("report.exportCsv")),
    el("button", { className: "dropdown-item", role: "menuitem", type: "button", onClick: () => { setOpen(false); onExport("xlsx"); } }, t("report.exportXlsx")),
  );
  const button = el("button", {
    className: "btn btn-secondary",
    type: "button",
    "aria-haspopup": "menu",
    "aria-expanded": "false",
    onClick: (e) => {
      e.stopPropagation();
      setOpen(!menu.classList.contains("is-open"));
    },
  }, t("common.export"));

  container.appendChild(el("div", { className: "dropdown" }, button, menu));

  const items = () => Array.from(menu.querySelectorAll('[role="menuitem"]'));
  const setOpen = (open, { focusFirst = false, restoreFocus = false } = {}) => {
    menu.classList.toggle("is-open", open);
    button.setAttribute("aria-expanded", String(open));
    if (open && focusFirst && items()[0]) items()[0].focus();
    if (!open && restoreFocus) button.focus();
  };
  const moveFocus = (dir) => {
    const list = items();
    if (!list.length) return;
    const cur = list.findIndex((node) => node === document.activeElement);
    const next = cur === -1 ? (dir > 0 ? 0 : list.length - 1) : (cur + dir + list.length) % list.length;
    list[next].focus();
  };

  button.addEventListener("keydown", (e) => {
    const open = menu.classList.contains("is-open");
    if (e.key === "Escape") {
      if (open) {
        e.preventDefault();
        e.stopPropagation();
        setOpen(false, { restoreFocus: true });
      }
      return;
    }
    if (open) return;
    if (e.key === "ArrowDown" || e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      setOpen(true, { focusFirst: true });
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setOpen(true);
      const list = items();
      if (list.length) list[list.length - 1].focus();
    }
  });

  menu.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      setOpen(false, { restoreFocus: true });
    } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      moveFocus(e.key === "ArrowDown" ? 1 : -1);
    } else if (e.key === "Home" || e.key === "End") {
      e.preventDefault();
      const list = items();
      if (!list.length) return;
      (e.key === "Home" ? list[0] : list[list.length - 1]).focus();
    } else if (e.key === "Tab") {
      setOpen(false);
    }
  });

  document.addEventListener("click", (e) => {
    if (menu.classList.contains("is-open") && !menu.contains(e.target) && e.target !== button && !button.contains(e.target)) {
      setOpen(false);
    }
  });
}

function truncate(value, max = 30) {
  const s = String(value || "");
  return s.length > max ? s.slice(0, max) + "…" : s;
}