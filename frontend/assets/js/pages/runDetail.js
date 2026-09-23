/**
 * Run detail — summary, status distribution, and the results/errors sub
 * reports (shared report panels with filters, pagination and exports).
 */

import { el, clear, showLoading, showError } from "../utils/dom.js";
import { getReportSummary, getRun, getResults, getErrors, exportResults, exportErrors } from "../services/reconciliation.js";
import { listRunEmailDeliveries, resendEmailDelivery } from "../services/email.js";
import { reportTabs } from "../components/reportTabs.js";
import { openModal } from "../components/modal.js";
import { renderSummaryStrip, renderStatusDistribution } from "../components/reportPanels.js";
import { runStatusLabel, statusClassToken, formatDateTime } from "../utils/format.js";
import { toast } from "../components/toast.js";
import { t } from "../i18n/index.js";

export async function renderRunDetail(container, params) {
  clear(container);
  document.body.classList.remove("login-body");

  const runId = Number(params[0]);

  container.appendChild(
    el("div", { className: "page-head" },
      el("div", null,
        el("h1", { className: "page-title" }, t("run.title", { id: runId })),
        el("div", { className: "page-head__meta", id: "run-meta" }, t("run.loadingMeta")),
      ),
      el("div", { className: "page-head__actions" },
        el("button", { className: "btn btn-secondary", onClick: () => { window.location.hash = "#/reconciliation"; } }, t("run.allRuns")),
        el("button", { className: "btn btn-primary", onClick: () => { window.location.hash = "#/reports"; } }, t("run.reports")),
      ),
    ),
  );

  const stripBox = el("div");
  container.appendChild(stripBox);
  showLoading(stripBox, t("run.loadingSummary"));

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
    showError(stripBox, err.message || t("run.notAvailable"), {
      onRetry: () => renderRunDetail(container, params),
    });
    return;
  }

  const meta = document.getElementById("run-meta");
  if (meta) meta.textContent = t("run.meta", {
    period: run.period || "—",
    invoices: run.invoice_count ?? 0,
    tax: run.tax_invoice_count ?? 0,
  });

  clear(stripBox);
  stripBox.appendChild(
    el("div", { className: "card" },
      el("div", { className: "card__body" },
        el("dl", { className: "dl" },
          el("div", null, el("dt", null, t("run.labelPeriod")), el("dd", { className: "mono" }, run.period || "—")),
          el("div", null, el("dt", null, t("run.labelStatus")), el("dd", el("span", { className: `badge badge--${statusClassToken(run.status)}` }, runStatusLabel(run.status)))),
          el("div", null, el("dt", null, t("run.labelStarted")), el("dd", formatDateTime(run.started_at))),
          el("div", null, el("dt", null, t("run.labelFinished")), el("dd", formatDateTime(run.finished_at))),
        ),
      ),
    ),
  );

  const reportBox = el("div", { className: "card" },
    el("div", { className: "card__header" }, el("div", { className: "section-title" }, t("run.summary"))),
    el("div", { className: "card__body" }, (() => { const b = el("div"); renderSummaryStrip(b, summary); return b; })()),
  );
  container.appendChild(reportBox);

  const distBox = el("div", { className: "card" },
    el("div", { className: "card__header" }, el("div", { className: "section-title" }, t("run.statusDist"))),
    el("div", { className: "card__body" }, el("div", { style: "max-width:640px;" }, (() => {
      const b = el("div"); renderStatusDistribution(b, summary); return b;
    })())),
  );
  container.appendChild(distBox);

  renderEmailDeliveriesCard(container, runId);

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

/* ------------------------- Email deliveries ------------------------- */

const DELIVERY_LABELS = {
  pending: "run.deliveryPending",
  sent: "run.deliverySent",
  failed: "run.deliveryFailed",
  skipped: "run.deliverySkipped",
  no_email: "run.deliveryNoEmail",
  invalid: "run.deliveryInvalid",
};

const DELIVERY_BADGES = {
  pending: "pending",
  sent: "completed",
  failed: "failed",
  skipped: "warn",
  no_email: "warn",
  invalid: "invalid",
};

export function deliveryCounts(deliveries) {
  const counts = { pending: 0, sent: 0, failed: 0, skipped: 0, no_email: 0, invalid: 0 };
  for (const d of deliveries || []) {
    const status = String((d && d.status) || "pending");
    if (Object.prototype.hasOwnProperty.call(counts, status)) counts[status] += 1;
  }
  return counts;
}

const DELIVERY_KPIS = [
  ["sent", "run.deliverySent", "kpi is-accent"],
  ["failed", "run.deliveryFailed", "kpi is-danger"],
  ["skipped", "run.deliverySkipped", "kpi is-warning"],
  ["no_email", "run.deliveryNoEmail", "kpi is-info"],
  ["invalid", "run.deliveryInvalid", "kpi is-danger"],
  ["pending", "run.deliveryPending", "kpi is-warning"],
];

function renderDeliveryStrip(container, deliveries) {
  const counts = deliveryCounts(deliveries);
  const grid = el("div", { className: "kpi-grid", style: "margin-block-end:var(--space-4);" });
  for (const [key, labelKey, kpiClass] of DELIVERY_KPIS) {
    grid.appendChild(
      el("div", { className: kpiClass },
        el("div", { className: "kpi__label" }, t(labelKey)),
        el("div", { className: "kpi__value" }, String(counts[key])),
      ),
    );
  }
  container.appendChild(grid);
}

function renderEmailDeliveriesCard(container, runId) {
  const card = el("div", { className: "card" },
    el("div", { className: "card__header" }, el("div", { className: "section-title" }, t("run.emailDeliveries"))),
    el("div", { className: "card__body", id: "email-deliveries-body" }),
  );
  container.appendChild(card);
  loadDeliveries(card, runId);
}

function loadDeliveries(card, runId) {
  const body = card.querySelector("#email-deliveries-body");
  clear(body);
  showLoading(body, t("run.loadingDeliveries"));

  listRunEmailDeliveries(runId)
    .then((data) => {
      clear(body);
      const deliveries = (data && data.deliveries) || [];
      if (deliveries.length === 0) {
        body.appendChild(el("p", { className: "text-sm text-secondary" },
          t("run.noDeliveries")));
        return;
      }
      renderDeliveryStrip(body, deliveries);
      const table = el("table", { className: "etable" },
        el("thead", null, el("tr", null,
          el("th", null, t("run.thRecipient")),
          el("th", null, t("run.thTaxpayer")),
          el("th", null, t("run.thInvoices")),
          el("th", null, t("run.thStatus")),
          el("th", null, t("run.thSubject")),
          el("th", null, t("run.thAttempted")),
          el("th", null, ""),
        )),
      );
      const tbody = el("tbody");
      for (const d of deliveries) {
        tbody.appendChild(deliveryRow(card, runId, d));
      }
      table.appendChild(tbody);
      body.appendChild(el("div", { className: "table-wrap" }, table));
    })
    .catch((err) => {
      clear(body);
      showError(body, err.message || t("run.loadedDeliveriesError"), {
        onRetry: () => loadDeliveries(card, runId),
      });
    });
}

function deliveryRow(card, runId, d) {
  const status = String(d.status || "pending");
  const tr = el("tr", null,
    el("td", null, d.recipient_email
      ? el("span", { className: "mono" }, d.recipient_email)
      : el("span", { className: "text-muted" }, "—")),
    el("td", null, d.taxpayer_name || "—"),
    el("td", null, String(d.invoice_count ?? 0)),
    el("td", null, el("span", { className: `badge badge--${DELIVERY_BADGES[status] || "neutral"}` },
      t(DELIVERY_LABELS[status] || "run.deliveryPending"))),
    el("td", null, d.subject || "—"),
    el("td", null, formatDateTime(d.attempted_at || d.sent_at)),
  );

  const actions = el("td");
  if (d.recipient_email) {
    actions.appendChild(
      el("button",
        { className: "btn btn-sm btn-secondary", onClick: () => resendDelivery(card, runId, d.id, d.recipient_email) },
        t("run.resend")),
    );
  }
  tr.appendChild(actions);
  return tr;
}

function resendDelivery(card, runId, deliveryId, recipient) {
  // Accessible confirm (Req 15) — the native window.confirm cannot be styled,
  // translated, focus-trapped, or surfaced reliably to assistive technology.
  openModal({
    title: t("run.resendTitle"),
    body: el("p", null, t("run.resendConfirm", { recipient })),
    actions: [
      { label: t("common.cancel"), variant: "secondary", onClick: (m) => m.close() },
      {
        label: t("run.resend"),
        variant: "primary",
        onClick: async (m) => {
          m.close();
          try {
            await resendEmailDelivery(runId, deliveryId);
            toast(t("run.emailResent"), { type: "success" });
          } catch (err) {
            toast(err.message || t("run.resendFailed"), { type: "error" });
          }
          loadDeliveries(card, runId);
        },
      },
    ],
  });
}