/**
 * Reconciliation hub — start a run for a period and browse the company's
 * runs. Consumes POST /api/reconciliation/runs and GET /api/reconciliation/runs.
 */

import { el, clear, showLoading, showError, showEmpty } from "../utils/dom.js";
import { startRun, listRuns } from "../services/reconciliation.js";
import { isValidPeriod, parseTolerance } from "../utils/validation.js";
import { runStatusLabel, statusClassToken, formatDateTime, formatNumber } from "../utils/format.js";
import { toast } from "../components/toast.js";
import { t } from "../i18n/index.js";

export async function renderReconciliation(container) {
  clear(container);
  document.body.classList.remove("login-body");

  container.appendChild(
    el("div", { className: "page-head" },
      el("div", null,
        el("h1", { className: "page-title" }, t("recon.title")),
        el("div", { className: "page-head__meta" }, t("recon.meta")),
      ),
    ),
  );

  container.appendChild(buildStartCard());

  const runsBox = el("div", { className: "card" });
  container.appendChild(runsBox);
  renderRuns(runsBox);
}

function buildStartCard() {
  const card = el("div", { className: "card" });
  card.appendChild(
    el("div", { className: "card__header" },
      el("div", { className: "section-title" }, t("recon.startNew")),
    ),
  );

  const body = el("div", { className: "card__body" });
  const periodInput = el("input", {
    className: "input",
    type: "month",
    required: "required",
    id: "run-period",
    value: "",
    placeholder: "2024-03",
    "aria-label": t("recon.period"),
  });
  const periodError = el("div", { className: "field-error", role: "alert" });
  periodError.style.display = "none";

  const toleranceInput = el("input", {
    className: "input",
    type: "text",
    inputmode: "decimal",
    id: "run-tolerance",
    placeholder: "0.00",
    "aria-label": t("recon.tolerance"),
  });
  const toleranceError = el("div", { className: "field-error", role: "alert" });
  toleranceError.style.display = "none";

  const startBtn = el("button", { className: "btn btn-primary", type: "submit" }, t("recon.start"));

  body.appendChild(
    el("form", { className: "form-row form-row--start", onsubmit: onStart },
      el("div", { className: "form-field" },
        el("label", { className: "form-label", for: "run-period" }, t("recon.period"), el("span", { className: "req" }, "*")),
        periodInput,
        periodError,
        el("div", { className: "form-hint" }, t("recon.periodHint")),
      ),
      el("div", { className: "form-field" },
        el("label", { className: "form-label", for: "run-tolerance" }, t("recon.tolerance")),
        toleranceInput,
        toleranceError,
        el("div", { className: "form-hint" }, t("recon.toleranceHint")),
      ),
      el("div", { className: "form-field", style: "align-self:end;margin-block-end:0;" }, startBtn),
    ),
  );

  card.appendChild(body);

  async function onStart(e) {
    e.preventDefault();

    periodError.style.display = "none";
    toleranceError.style.display = "none";
    const period = periodInput.value.trim();
    if (!isValidPeriod(period)) {
      periodError.textContent = t("recon.invalidPeriod");
      periodError.style.display = "block";
      return;
    }
    const tolerance = parseTolerance(toleranceInput.value);
    if (!tolerance.ok) {
      toleranceError.textContent = tolerance.message;
      toleranceError.style.display = "block";
      return;
    }

    startBtn.disabled = true;
    startBtn.textContent = t("recon.starting");
    try {
      const result = await startRun(period, tolerance.value);
      toast(t("recon.completeFor", { period }), { type: "success" });
      const runId = result && result.run && result.run.id;
      if (runId) {
        window.location.hash = `#/reconciliation/${runId}`;
      } else {
        renderRuns(boxOf(startBtn));
      }
    } catch (err) {
      startBtn.disabled = false;
      startBtn.textContent = t("recon.start");
      toast(err.message || t("recon.failedStart"), { type: "error" });
    }
  }

  return card;
}

function boxOf(node) {
  return node.closest(".card");
}

async function renderRuns(container) {
  clear(container);
  container.appendChild(
    el("div", { className: "card__header" },
      el("div", { className: "section-title" }, t("recon.history")),
    ),
  );

  const body = el("div");
  container.appendChild(body);
  showLoading(body, t("recon.loading"));

  try {
    const data = await listRuns(100, 0);
    const runs = (data && data.runs) || [];
    clear(body);

    if (runs.length === 0) {
      body.appendChild(el("div", { className: "state-block" },
        el("div", { className: "state-block__icon" }, "📋"),
        el("div", { className: "state-block__title" }, t("recon.noRuns")),
      ));
      return;
    }

    const table = el("table", { className: "etable" });
    table.appendChild(
      el("thead",
        el("tr",
          el("th", { className: "num" }, t("recon.thId")),
          el("th", null, t("recon.thPeriod")),
          el("th", null, t("recon.thStatus")),
          el("th", { className: "num" }, t("recon.thInvoices")),
          el("th", { className: "num" }, t("recon.thTaxDocs")),
          el("th", { className: "num" }, t("recon.thMatched")),
          el("th", { className: "num" }, t("recon.thUnmatched")),
          el("th", { className: "num" }, t("recon.thErrors")),
          el("th", null, t("recon.thStarted")),
          el("th", null, t("common.action")),
        ),
      ),
    );
    const tbody = el("tbody");
    for (const run of runs.sort((a, b) => b.id - a.id)) {
      tbody.appendChild(
        el("tr", { className: "is-row-click", dataset: { id: run.id }, onClick: () => { window.location.hash = `#/reconciliation/${run.id}`; } },
          el("td", { className: "num" }, String(run.id)),
          el("td", { className: "mono" }, run.period),
          el("td", el("span", { className: `badge badge--${statusClassToken(run.status)}` }, runStatusLabel(run.status))),
          el("td", { className: "num" }, formatNumber(run.invoice_count)),
          el("td", { className: "num" }, formatNumber(run.tax_invoice_count)),
          el("td", { className: "num" }, formatNumber(run.matched_count)),
          el("td", { className: "num" }, formatNumber(run.unmatched_count)),
          el("td", { className: "num" }, formatNumber(run.error_count)),
          el("td", { className: "text-sm text-secondary" }, formatDateTime(run.started_at)),
          el("td",
            el("button", { className: "btn btn-secondary btn-sm", onClick: () => { window.location.hash = `#/reconciliation/${run.id}`; } }, t("recon.open")),
          ),
        ),
      );
    }
    table.appendChild(tbody);
    body.appendChild(el("div", { className: "table-wrap" }, table));
  } catch (err) {
    showError(body, err.message || t("recon.failedLoad"), {
      onRetry: () => renderRuns(container),
    });
  }
}