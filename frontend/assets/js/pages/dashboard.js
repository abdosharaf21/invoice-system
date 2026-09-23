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

import { el, clear, showError, showLoading, showEmpty, icons } from "../utils/dom.js";
import { listRuns, getReportSummary } from "../services/reconciliation.js";
import { formatDateTime, runStatusLabel, statusClassToken } from "../utils/format.js";
import { canReconcile, authStore } from "../auth/store.js";
import { renderStatusDistribution } from "../components/reportPanels.js";
import { t } from "../i18n/index.js";

export async function renderDashboard(container) {
  clear(container);
  const user = authStore.getUser();

  document.body.classList.remove("login-body");

  container.appendChild(
    el("div", { className: "page-head" },
      el("div", null,
        el("h1", { className: "page-title" }, t("dash.welcome", { name: user ? (user.full_name || user.username || "") : "" })),
        el("div", { className: "page-head__meta" }, t("dash.meta")),
      ),
      canReconcile()
        ? el("div", { className: "page-head__actions" },
            el("button", { className: "btn btn-secondary", onClick: () => { window.location.hash = "#/imports"; } }, t("dash.uploadFile")),
            el("button", { className: "btn btn-primary", onClick: () => { window.location.hash = "#/reconciliation"; } }, t("dash.newRun")),
          )
        : null,
    ),
  );

  if (!canReconcile()) {
    container.appendChild(
      el("div", { className: "card" },
        el("div", { className: "notice" },
          el("strong", null, t("dash.readOnlyTitle")),
          t("dash.readOnlyBody"),
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
    el("div", { style: "display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:var(--space-4);margin-block-end:var(--space-4);" },
      recentBox,
      statusBox,
    ),
  );
  container.appendChild(layout);

  showLoading(kpiBox, t("dash.loading"));

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
        kpiCard(t("dash.kpiRuns"), String(runs.length), t("dash.kpiRunsSub", { count: runs.length }), "is-primary", iconCopy(icons.reconciliation)),
        kpiCard(t("dash.kpiMatched"), String(matched), t("dash.kpiMatchedSub"), "is-accent", iconCopy(icons.checkCircle)),
        kpiCard(t("dash.kpiUnmatched"), String(unmatched), t("dash.kpiUnmatchedSub"), "is-warning", iconCopy(icons.alertTriangle)),
        kpiCard(t("dash.kpiErrors"), String(errors), t("dash.kpiErrorsSub"), "is-danger", iconCopy(icons.xCircle)),
        kpiCard(t("dash.kpiInvoices"), String(invoices), t("dash.kpiInvoicesSub"), "is-info", iconCopy(icons.reports)),
        kpiCard(t("dash.kpiTaxDocs"), String(taxDocs), t("dash.kpiTaxDocsSub"), "is-info", iconCopy(icons.shield)),
      ),
    );

    renderRecentRuns(recentBox, runs);

    // Status distribution from the most recent completed run's summary.
    const latest = runs.find((r) => r.status === "completed");
    if (latest) {
      showLoading(statusBox, t("dash.loadingSummary"));
      try {
        const summary = await getReportSummary(latest.id);
        clear(statusBox);
        statusBox.appendChild(
          el("div", { className: "card__header" },
            el("div", null,
              el("div", { className: "section-title" }, t("dash.statusDist", { period: latest.period })),
              el("div", { className: "text-xs text-muted" }, t("dash.runRef", { id: latest.id, date: formatDateTime(latest.started_at) })),
            ),
          ),
        );
        statusBox.appendChild(el("div", { className: "card__body" }));
        renderStatusDistribution(statusBox.querySelector(".card__body"), summary);
      } catch {
        clear(statusBox);
        statusBox.appendChild(el("div", { className: "state-block text-muted" }, t("dash.couldNotLoadSummary")));
      }
    } else {
      showEmpty(statusBox, t("dash.noCompleted"), {
        action: canReconcile() ? t("dash.startRun") : null,
        onAction: () => { window.location.hash = "#/reconciliation"; },
      });
    }
  } catch (err) {
    showError(kpiBox, err.message || t("dash.failed"), {
      onRetry: () => renderDashboard(container),
    });
  }
}

function iconCopy(node) {
  const copy = node.cloneNode(true);
  copy.setAttribute("aria-hidden", "true");
  return copy;
}

function kpiCard(label, value, sub, tone, kpiIcon) {
  const labelEl = el("div", { className: "kpi__label" });
  if (kpiIcon) {
    kpiIcon.classList.add("kpi__icon");
    labelEl.appendChild(kpiIcon);
  }
  labelEl.appendChild(document.createTextNode(label));
  return el("div", { className: `kpi ${tone || ""}` },
    labelEl,
    el("div", { className: "kpi__value" }, value),
    el("div", { className: "kpi__sub" }, sub),
  );
}

function renderRecentRuns(container, runs) {
  clear(container);
  container.appendChild(
    el("div", { className: "card__header" },
      el("div", { className: "section-title" }, t("dash.recent")),
      el("button", { className: "btn btn-ghost btn-sm", onClick: () => { window.location.hash = "#/reconciliation"; } }, t("dash.viewAll")),
    ),
  );

  if (runs.length === 0) {
    container.appendChild(el("div", { className: "state-block" },
      el("div", { className: "state-block__icon" }, "📋"),
      el("div", { className: "state-block__title" }, t("dash.noRuns")),
    ));
    return;
  }

  const table = el("table", { className: "etable" });
  table.appendChild(
    el("thead",
      el("tr",
        el("th", null, t("dash.thPeriod")),
        el("th", null, t("dash.thStatus")),
        el("th", { className: "num" }, t("dash.thMatched")),
        el("th", { className: "num" }, t("dash.thUnmatched")),
        el("th", { className: "num" }, t("dash.thErrors")),
        el("th", null, t("dash.thStarted")),
      ),
    ),
  );
  const tbody = el("tbody");
  for (const run of runs.slice(0, 8)) {
    tbody.appendChild(
      el("tr", { className: "is-row-click", dataset: { id: run.id }, onClick: () => { window.location.hash = `#/reconciliation/${run.id}`; } },
        el("td", { className: "mono" }, run.period),
        el("td", el("span", { className: `badge badge--${statusClassToken(run.status)}` }, runStatusLabel(run.status))),
        el("td", { className: "num" }, String(run.matched_count ?? 0)),
        el("td", { className: "num" }, String(run.unmatched_count ?? 0)),
        el("td", { className: "num" }, String(run.error_count ?? 0)),
        el("td", { className: "text-sm text-secondary" }, formatDateTime(run.started_at)),
      ),
    );
  }
  table.appendChild(tbody);
  const wrap = el("div", { className: "table-wrap table-wrap--flush" });
  wrap.appendChild(table);
  container.appendChild(wrap);
}