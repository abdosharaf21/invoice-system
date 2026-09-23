/**
 * Import result detail — batch summary plus a professional, filterable
 * errors table. Consumes GET /api/imports/<id>?include=errors.
 */

import { el, clear, showLoading, showError } from "../utils/dom.js";
import { getBatch } from "../services/imports.js";
import {
  batchStatusLabel,
  importErrorLabel,
  statusClassToken,
  formatDateTime,
  formatNumber,
} from "../utils/format.js";
import { t } from "../i18n/index.js";

export async function renderImportDetail(container, params) {
  clear(container);
  document.body.classList.remove("login-body");

  const batchId = Number(params[0]);

  container.appendChild(
    el("div", { className: "page-head" },
      el("div", null,
        el("h1", { className: "page-title" }, t("imports.batchNo", { id: batchId })),
        el("div", { className: "page-head__meta" }, t("imports.metaDetail")),
      ),
      el("div", { className: "page-head__actions" },
        el("button", { className: "btn btn-secondary", onClick: () => { window.location.hash = "#/imports"; } }, t("imports.back")),
      ),
    ),
  );

  const summaryBox = el("div");
  container.appendChild(summaryBox);
  showLoading(summaryBox, t("imports.loading"));

  try {
    const data = await getBatch(batchId, true);
    const batch = data.batch || {};
    const errors = data.errors || [];

    clear(summaryBox);
    summaryBox.appendChild(renderBatchSummary(batch));

    const errorsBox = el("div", { className: "card" });
    errorsBox.appendChild(
      el("div", { className: "card__header" },
        el("div", { className: "section-title" }, t("imports.validationErrors")),
        el("span", { className: "text-xs text-muted" },
          errors.length ? t("imports.rejectedCount", { count: errors.length }) : t("imports.noRejected")),
      ),
    );
    errorsBox.appendChild(renderErrorsTable(errors));
    container.appendChild(errorsBox);
  } catch (err) {
    showError(summaryBox, err.message || t("imports.failedLoad"), {
      onRetry: () => renderImportDetail(container, params),
    });
  }
}

function renderBatchSummary(batch) {
  const rows = [
    [t("imports.file"), batch.filename || "—"],
    [t("imports.fileType"), String(batch.file_type || "—").toUpperCase()],
    [t("imports.status"), batchStatusLabel(batch.status)],
    [t("imports.totalRows"), formatNumber(batch.total_rows)],
    [t("imports.processedRows"), formatNumber(batch.processed_rows)],
    [t("imports.rejectedRows"), formatNumber(batch.error_rows)],
    [t("imports.started"), formatDateTime(batch.started_at)],
    [t("imports.finished"), formatDateTime(batch.finished_at)],
  ];

  return el("div", { className: "card" },
    el("div", { className: "card__header" },
      el("div", { className: "section-title" }, t("imports.batchSummary")),
      el("span", { className: `badge badge--${statusClassToken(batch.status)}` }, batchStatusLabel(batch.status)),
    ),
    el("div", { className: "card__body" },
      el("dl", { className: "dl" }, ...rows.map(([k, v]) => el("div", null, el("dt", null, k), el("dd", null, v)))),
    ),
  );
}

function renderErrorsTable(errors) {
  const body = el("div", { className: "table-wrap table-wrap--flush" });
  const table = el("table", { className: "etable" });
  table.appendChild(
    el("thead",
      el("tr",
        el("th", { className: "num" }, t("imports.thRow")),
        el("th", null, t("imports.thField")),
        el("th", null, t("imports.thError")),
        el("th", null, t("imports.thMessage")),
      ),
    ),
  );
  const tbody = el("tbody");
  for (const err of errors || []) {
    tbody.appendChild(
      el("tr",
        el("td", { className: "num" }, String(err.row_number ?? "—")),
        el("td", null, el("code", { className: "text-xs" }, err.field || "—")),
        el("td",
          el("span", { className: "badge badge--neutral", style: "font-family:var(--font-mono);" },
            err.error_code || "—"),
        ),
        el("td", { className: "text-sm text-secondary", style: "white-space:normal;min-width:240px;" },
          err.message || importErrorLabel(err.error_code)),
      ),
    );
  }
  if (!errors || errors.length === 0) {
    tbody.appendChild(el("tr", null, el("td", { colSpan: 4, className: "etable-empty" },
      t("imports.allImported"))));
  }
  table.appendChild(tbody);
  body.appendChild(table);
  return body;
}