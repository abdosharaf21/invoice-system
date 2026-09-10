/**
 * Run detail — summary, status distribution, and the results/errors sub
 * reports (shared report panels with filters, pagination and exports).
 */

import { el, clear, showLoading, showError } from "../utils/dom.js";
import { getReportSummary, getRun, getResults, getErrors, exportResults, exportErrors } from "../services/reconciliation.js";
import { reportTabs } from "../components/reportTabs.js";
import { renderSummaryStrip, renderStatusDistribution } from "../components/reportPanels.js";
import { runStatusLabel, formatDateTime } from "../utils/format.js";
import { escapeHtml } from "../utils/escape.js";

export async function renderRunDetail(container, params) {
  clear(container);
  document.body.classList.remove("login-body");

  const runId = Number(params[0]);

  container.appendChild(
    el("div", { className: "page-head" },
      el("div", null,
        el("h1", { className: "page-title" }, `Reconciliation run #${runId}`),
        el("div", { className: "page-head__meta", id: "run-meta" }, "Loading…"),
      ),
      el("div", { className: "page-head__actions" },
        el("button", { className: "btn btn-secondary", onClick: () => { window.location.hash = "#/reconciliation"; } }, "All runs"),
        el("button", { className: "btn btn-primary", onClick: () => { window.location.hash = "#/reports"; } }, "Reports"),
      ),
    ),
  );

  const stripBox = el("div");
  container.appendChild(stripBox);
  showLoading(stripBox, "Loading run summary…");

  let run = null;
  let summary = null;
  try {
    const [runData, summaryData] = await Promise.all([
      getRun(runId),
      getReportSummary(runId),
    ]);
    run = (runData && runData.run) || {};
    summary = summaryData || {};
  } catch (err) {
    showError(stripBox, err.message || "This run is not available for your company.", {
      onRetry: () => renderRunDetail(container, params),
    });
    return;
  }

  const meta = document.getElementById("run-meta");
  if (meta) meta.textContent = `Period ${run.period} · ${run.invoice_count ?? 0} invoices vs ${run.tax_invoice_count ?? 0} tax documents`;

  clear(stripBox);
  stripBox.appendChild(
    el("div", { className: "card", style: "margin-block-end:1.25rem;" },
      el("div", { className: "card__body" },
        el("dl", { className: "dl" },
          el("div", null, el("dt", null, "Period"), el("dd", { className: "mono" }, escapeHtml(run.period || "—"))),
          el("div", null, el("dt", null, "Status"), el("dd", el("span", { className: `badge badge--${run.status}` }, runStatusLabel(run.status)))),
          el("div", null, el("dt", null, "Started"), el("dd", formatDateTime(run.started_at))),
          el("div", null, el("dt", null, "Finished"), el("dd", formatDateTime(run.finished_at))),
        ),
      ),
    ),
  );

  const reportBox = el("div", { className: "card", style: "margin-block-end:1.25rem;" },
    el("div", { className: "card__header" }, el("div", { className: "section-title" }, "Summary")),
    el("div", { className: "card__body" }, (() => { const b = el("div"); renderSummaryStrip(b, summary); return b; })()),
  );
  container.appendChild(reportBox);

  const distBox = el("div", { className: "card", style: "margin-block-end:1.25rem;" },
    el("div", { className: "card__header" }, el("div", { className: "section-title" }, "Status distribution")),
    el("div", { className: "card__body" }, el("div", { style: "max-width:640px;" }, (() => {
      const b = el("div"); renderStatusDistribution(b, summary); return b;
    })())),
  );
  container.appendChild(distBox);

  const tabs = el("div");
  container.appendChild(tabs);

  reportTabs(tabs, {
    loadResults: (params) => getResults(runId, params),
    loadErrors: (params) => getErrors(runId, params),
    onExport: (kind, format, filters) =>
      kind === "results"
        ? exportResults(runId, format, filters)
        : exportErrors(runId, format, filters),
  }, { activeTab: "results" });
}