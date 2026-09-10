/**
 * Import result detail — batch summary plus a professional, filterable
 * errors table. Consumes GET /api/imports/<id>?include=errors.
 */

import { el, clear, showLoading, showError } from "../utils/dom.js";
import { getBatch } from "../services/imports.js";
import {
  batchStatusLabel,
  importErrorLabel,
  formatDateTime,
  formatNumber,
} from "../utils/format.js";
import { escapeHtml } from "../utils/escape.js";

export async function renderImportDetail(container, params) {
  clear(container);
  document.body.classList.remove("login-body");

  const batchId = Number(params[0]);

  container.appendChild(
    el("div", { className: "page-head" },
      el("div", null,
        el("h1", { className: "page-title" }, `Import batch #${batchId}`),
        el("div", { className: "page-head__meta" }, "Uploaded accounting file, processing outcome."),
      ),
      el("div", { className: "page-head__actions" },
        el("button", { className: "btn btn-secondary", onClick: () => { window.location.hash = "#/imports"; } }, "Back to imports"),
      ),
    ),
  );

  const summaryBox = el("div");
  container.appendChild(summaryBox);
  showLoading(summaryBox, "Loading import result…");

  try {
    const data = await getBatch(batchId, true);
    const batch = data.batch || {};
    const errors = data.errors || [];

    clear(summaryBox);
    summaryBox.appendChild(renderBatchSummary(batch));

    const errorsBox = el("div", { className: "card", style: "margin-block-start:1.25rem;" });
    errorsBox.appendChild(
      el("div", { className: "card__header" },
        el("div", { className: "section-title" }, "Validation errors"),
        el("span", { className: "text-xs text-muted" },
          errors.length ? `${errors.length} row${errors.length === 1 ? "" : "s"} rejected` : "No rejected rows"),
      ),
    );
    errorsBox.appendChild(renderErrorsTable(errors));
    container.appendChild(errorsBox);
  } catch (err) {
    showError(summaryBox, err.message || "Failed to load the import batch.", {
      onRetry: () => renderImportDetail(container, params),
    });
  }
}

function renderBatchSummary(batch) {
  const rows = [
    ["File", escapeHtml(batch.filename || "—")],
    ["File type", String(batch.file_type || "—").toUpperCase()],
    ["Status", batchStatusLabel(batch.status)],
    ["Total rows", formatNumber(batch.total_rows)],
    ["Processed rows", formatNumber(batch.processed_rows)],
    ["Rejected rows", formatNumber(batch.error_rows)],
    ["Started", formatDateTime(batch.started_at)],
    ["Finished", formatDateTime(batch.finished_at)],
  ];

  return el("div", { className: "card" },
    el("div", { className: "card__header" },
      el("div", { className: "section-title" }, "Batch summary"),
      el("span", { className: `badge badge--${batch.status}` }, batchStatusLabel(batch.status)),
    ),
    el("div", { className: "card__body" },
      el("dl", { className: "dl" }, ...rows.map(([k, v]) => el("div", null, el("dt", null, k), el("dd", null, v)))),
    ),
  );
}

function renderErrorsTable(errors) {
  const body = el("div", { className: "table-wrap", style: "border:none;border-radius:0;" });
  const table = el("table", { className: "etable" });
  table.appendChild(
    el("thead",
      el("tr",
        el("th", { className: "num" }, "Row"),
        el("th", null, "Field"),
        el("th", null, "Error"),
        el("th", null, "Message"),
      ),
    ),
  );
  const tbody = el("tbody");
  for (const err of errors || []) {
    tbody.appendChild(
      el("tr",
        el("td", { className: "num" }, String(err.row_number ?? "—")),
        el("td", null, el("code", { className: "text-xs" }, escapeHtml(err.field || "—"))),
        el("td",
          el("span", { className: "badge badge--neutral", style: "font-family:var(--font-mono);" },
            escapeHtml(err.error_code || "—")),
        ),
        el("td", { className: "text-sm text-secondary", style: "white-space:normal;min-width:240px;" },
          escapeHtml(err.message || importErrorLabel(err.error_code))),
      ),
    );
  }
  if (!errors || errors.length === 0) {
    tbody.appendChild(el("tr", null, el("td", { colSpan: 4, className: "etable-empty" },
      "All rows were imported successfully.")));
  }
  table.appendChild(tbody);
  body.appendChild(table);
  return body;
}