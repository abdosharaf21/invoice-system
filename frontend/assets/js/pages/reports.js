/**
 * Reports — pick a reconciliation period/run, then explore the results and
 * errors sub-reports with filters, pagination and CSV/XLSX exports.
 */

import { el, clear, showLoading, showError } from "../utils/dom.js";
import { listRuns, getReportSummary, getResults, getErrors, exportResults, exportErrors } from "../services/reconciliation.js";
import { reportTabs } from "../components/reportTabs.js";
import { renderSummaryStrip } from "../components/reportPanels.js";
import { runStatusLabel, formatDateTime } from "../utils/format.js";

export async function renderReports(container) {
  clear(container);
  document.body.classList.remove("login-body");

  container.appendChild(
    el("div", { className: "page-head" },
      el("div", null,
        el("h1", { className: "page-title" }, "Reports"),
        el("div", { className: "page-head__meta" }, "Reconciliation reports · results and errors, filterable and exportable"),
      ),
    ),
  );

  const pickerCard = el("div", { className: "card", style: "margin-block-end:1.25rem;" },
    el("div", { className: "card__header" }, el("div", { className: "section-title" }, "Select run")),
    el("div", { className: "card__body" }, (() => {
      const row = el("div", { className: "field-row" });
      row.appendChild(el("label", {}, "Run / period", "for-run-picker"));
      row.appendChild(el("select", { id: "run-picker", className: "select" }));
      row.appendChild(el("button", { id: "run-refresh", className: "btn btn-secondary", type: "button" }, "Refresh"));
      const hint = el("div", { className: "form-hint" }, "Runs appear once a reconciliation period has been submitted.");
      row.appendChild(el("div", { style: "flex-basis:100%;" }, hint));
      return row;
    })()),
  );
  container.appendChild(pickerCard);

  const select = pickerCard.querySelector("#run-picker");
  const runsCard = el("div", { className: "card" });
  container.appendChild(runsCard);

  try {
    const env = await listRuns({ limit: 200, offset: 0 });
    const runs = (env && env.runs) || [];
    if (!runs.length) {
      clear(runsCard);
      runsCard.appendChild(el("div", { className: "card__body" },
        el("div", { className: "empty" },
          el("p", null, "No reconciliation runs yet."),
          el("button", { className: "btn btn-primary", onClick: () => { window.location.hash = "#/reconciliation"; } }, "Run reconciliation"),
        ),
      ));
      return;
    }

    const ranked = runs.map((r) => ({ ...r, score: r.status === "completed" ? 2 : r.status === "failed" ? 1 : 0 }));
    ranked.sort((a, b) => (b.score - a.score) || (new Date(b.started_at) - new Date(a.started_at)));
    fillSelect(select, ranked);
    select.value = String(ranked[0].id);
    select.addEventListener("change", () => {
      if (select.value) renderRun(Number(select.value));
    });
    pickerCard.querySelector("#run-refresh").addEventListener("click", () => renderReports(container));
    renderRun(Number(ranked[0].id));
  } catch (err) {
    showError(runsCard, err.message || "Failed to load runs.", { onRetry: () => renderReports(container) });
  }

  function fillSelect(node, runs) {
    clear(node);
    for (const r of runs) {
      const opt = document.createElement("option");
      opt.value = String(r.id);
      opt.textContent = `${r.period} · #${r.id} · ${runStatusLabel(r.status)} (${r.matched_count ?? 0} matched) · ${formatDateTime(r.finished_at)}`;
      node.appendChild(opt);
    }
  }

  async function renderRun(runId) {
    clear(runsCard);
    showLoading(runsCard, "Loading report…");
    try {
      const summary = await getReportSummary(runId);
      clear(runsCard);

      const summaryBox = el("div", { className: "card__body" });
      const runStatus = summary.run ? summary.run.status : "";
      runsCard.appendChild(el("div", { className: "card__header" },
        el("div", { className: "section-title" }, `Run #${runId} summary`),
        runStatus ? el("span", { className: `badge badge--${runStatus}` }, runStatusLabel(runStatus)) : null,
      ));
      runsCard.appendChild(summaryBox);
      renderSummaryStrip(summaryBox, summary);

      const tabsBox = el("div", { className: "card__body" });
      runsCard.appendChild(tabsBox);
      reportTabs(tabsBox, {
        loadResults: (params) => getResults(runId, params),
        loadErrors: (params) => getErrors(runId, params),
        onExport: (kind, format, filters) =>
          kind === "results"
            ? exportResults(runId, format, filters)
            : exportErrors(runId, format, filters),
      }, { activeTab: "results" });
    } catch (err) {
      showError(runsCard, err.message || "Failed to load this report.", { onRetry: () => renderRun(runId) });
    }
  }
}