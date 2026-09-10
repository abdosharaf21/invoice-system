/**
 * Dashboard — Sigma6/Rep-style business overview built strictly from the
 * reconciliation API. Financially relevant values are displayed exactly as
 * the backend returns them; no fabrications, no client-side recalculation.
 *
 * KPI data sources (all present in the backend runs list):
 *   runs            → GET /api/reconciliation/runs
 *   matched/unmatched/errors → summed across the returned runs
 *   latest summary  → GET /api/reconciliation/runs/<id>/summary
 */

import { el, clear, showError, showLoading, showEmpty } from "../utils/dom.js";
import { listRuns, getReportSummary } from "../services/reconciliation.js";
import { formatDateTime } from "../utils/format.js";
import { canReconcile, authStore } from "../auth/store.js";
import { renderStatusDistribution } from "../components/reportPanels.js";

export async function renderDashboard(container) {
  clear(container);
  const user = authStore.getUser();

  document.body.classList.remove("login-body");

  container.appendChild(
    el("div", { className: "page-head" },
      el("div", null,
        el("h1", { className: "page-title" }, `Welcome, ${user ? user.full_name || user.username : ""}`),
        el("div", { className: "page-head__meta" }, "Company e-invoice reconciliation overview."),
      ),
      canReconcile()
        ? el("div", { className: "page-head__actions" },
            el("button", { className: "btn btn-secondary", onClick: () => { window.location.hash = "#/imports"; } }, "Upload file"),
            el("button", { className: "btn btn-primary", onClick: () => { window.location.hash = "#/reconciliation"; } }, "New reconciliation run"),
          )
        : null,
    ),
  );

  if (!canReconcile()) {
    container.appendChild(
      el("div", { className: "card" },
        el("div", { className: "notice" },
          el("strong", null, "Read-only access"),
          " Your account has view-only permissions in this system. Talk to your company administrator if you need to upload files or run reconciliations.",
        ),
      ),
    );
    return;
  }

  const kpiBox = el("div");
  const recentBox = el("div", { className: "card" });
  const statusBox = el("div", { className: "card" });

  const layout = el("div", null,
    kpiBox,
    el("div", { style: "display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:1rem;margin-block-end:1rem;" },
      recentBox,
      statusBox,
    ),
  );
  container.appendChild(layout);

  showLoading(kpiBox, "Loading reconciliation overview…");

  try {
    const data = await listRuns(50, 0);
    const runs = (data && data.runs) || [];

    // Aggregate KPIs from backend-summed counters on each run.
    let matched = 0, unmatched = 0, errors = 0, invoices = 0, taxDocs = 0;
    for (const run of runs) {
      matched += run.matched_count || 0;
      unmatched += run.unmatched_count || 0;
      errors += run.error_count || 0;
      invoices += run.invoice_count || 0;
      taxDocs += run.tax_invoice_count || 0;
    }

    clear(kpiBox);
    kpiBox.appendChild(
      el("div", { className: "kpi-grid" },
        kpiCard("Reconciliation runs", String(runs.length), `${runs.length} run${runs.length === 1 ? "" : "s"}`, "is-primary"),
        kpiCard("Matched", String(matched), "across all runs", "is-accent"),
        kpiCard("Unmatched", String(unmatched), "mismatched + missing + extra + invalid", "is-warning"),
        kpiCard("Errors", String(errors), "field-level discrepancies", "is-danger"),
        kpiCard("Accounting invoices", String(invoices), "seen by reconciliation", "is-info"),
        kpiCard("Tax documents", String(taxDocs), "from the tax authority side", "is-info"),
      ),
    );

    renderRecentRuns(recentBox, runs);

    // Status distribution from the most recent completed run's summary.
    const latest = runs.find((r) => r.status === "completed");
    if (latest) {
      showLoading(statusBox, "Loading latest run summary…");
      try {
        const summary = await getReportSummary(latest.id);
        clear(statusBox);
        statusBox.appendChild(
          el("div", { className: "card__header" },
            el("div", null,
              el("div", { className: "section-title" }, `Status distribution — period ${latest.period}`),
              el("div", { className: "text-xs text-muted" }, `Run #${latest.id} · ${formatDateTime(latest.started_at)}`),
            ),
          ),
        );
        statusBox.appendChild(el("div", { className: "card__body" }));
        renderStatusDistribution(statusBox.querySelector(".card__body"), summary);
      } catch {
        clear(statusBox);
        statusBox.appendChild(el("div", { className: "state-block text-muted" }, "Could not load the latest run summary."));
      }
    } else {
      showEmpty(statusBox, "No completed reconciliation runs yet.", {
        action: canReconcile() ? "Start a run" : null,
        onAction: () => { window.location.hash = "#/reconciliation"; },
      });
    }
  } catch (err) {
    showError(kpiBox, err.message || "Failed to load the reconciliation overview.", {
      onRetry: () => renderDashboard(container),
    });
  }
}

function kpiCard(label, value, sub, tone) {
  return el("div", { className: `kpi ${tone || ""}` },
    el("div", { className: "kpi__label" }, label),
    el("div", { className: "kpi__value" }, value),
    el("div", { className: "kpi__sub" }, sub),
  );
}

function renderRecentRuns(container, runs) {
  clear(container);
  container.appendChild(
    el("div", { className: "card__header" },
      el("div", { className: "section-title" }, "Recent reconciliation activity"),
      el("button", { className: "btn btn-ghost btn-sm", onClick: () => { window.location.hash = "#/reconciliation"; } }, "View all"),
    ),
  );

  if (runs.length === 0) {
    container.appendChild(el("div", { className: "etable-empty" }, "No runs yet — start your first reconciliation."));
    return;
  }

  const table = el("table", { className: "etable" });
  table.appendChild(
    el("thead",
      el("tr",
        el("th", null, "Period"),
        el("th", null, "Status"),
        el("th", { className: "num" }, "Matched"),
        el("th", { className: "num" }, "Unmatched"),
        el("th", { className: "num" }, "Errors"),
        el("th", null, "Started"),
      ),
    ),
  );
  const tbody = el("tbody");
  for (const run of runs.slice(0, 8)) {
    tbody.appendChild(
      el("tr", { className: "is-row-click", dataset: { id: run.id }, onClick: () => { window.location.hash = `#/reconciliation/${run.id}`; } },
        el("td", { className: "mono" }, run.period),
        el("td", el("span", { className: `badge badge--${run.status}` }, run.status)),
        el("td", { className: "num" }, String(run.matched_count ?? 0)),
        el("td", { className: "num" }, String(run.unmatched_count ?? 0)),
        el("td", { className: "num" }, String(run.error_count ?? 0)),
        el("td", { className: "text-sm text-secondary" }, formatDateTime(run.started_at)),
      ),
    );
  }
  table.appendChild(tbody);
  const wrap = el("div", { className: "table-wrap", style: "border:none;border-radius:0;" });
  wrap.appendChild(table);
  container.appendChild(wrap);
}