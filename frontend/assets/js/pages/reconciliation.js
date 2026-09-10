/**
 * Reconciliation hub — start a run for a period and browse the company's
 * runs. Consumes POST /api/reconciliation/runs and GET /api/reconciliation/runs.
 */

import { el, clear, showLoading, showError, showEmpty } from "../utils/dom.js";
import { startRun, listRuns } from "../services/reconciliation.js";
import { isValidPeriod, parseTolerance } from "../utils/validation.js";
import { runStatusLabel, formatDateTime, formatNumber } from "../utils/format.js";
import { toast } from "../components/toast.js";

export async function renderReconciliation(container) {
  clear(container);
  document.body.classList.remove("login-body");

  container.appendChild(
    el("div", { className: "page-head" },
      el("div", null,
        el("h1", { className: "page-title" }, "Reconciliation"),
        el("div", { className: "page-head__meta" }, "Compare accounting invoices against tax-authority e-invoices for a period."),
      ),
    ),
  );

  container.appendChild(buildStartCard());

  const runsBox = el("div", { className: "card", style: "margin-block-start:1.25rem;" });
  container.appendChild(runsBox);
  renderRuns(runsBox);
}

function buildStartCard() {
  const card = el("div", { className: "card" });
  card.appendChild(
    el("div", { className: "card__header" },
      el("div", { className: "section-title" }, "Start a new run"),
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
    "aria-label": "Period",
  });
  const periodError = el("div", { className: "field-error" });
  periodError.style.display = "none";

  const toleranceInput = el("input", {
    className: "input",
    type: "text",
    inputmode: "decimal",
    id: "run-tolerance",
    placeholder: "0.00",
    "aria-label": "Money tolerance",
  });
  const toleranceError = el("div", { className: "field-error" });
  toleranceError.style.display = "none";

  const startBtn = el("button", { className: "btn btn-primary", type: "submit" }, "Start reconciliation");

  body.appendChild(
    el("form", { className: "form-row", onsubmit: onStart },
      el("div", { className: "form-field" },
        el("label", { className: "form-label", for: "run-period" }, "Period", el("span", { className: "req" }, "*")),
        periodInput,
        periodError,
        el("div", { className: "form-hint" }, "Calendar month, e.g. 2024-03."),
      ),
      el("div", { className: "form-field" },
        el("label", { className: "form-label", for: "run-tolerance" }, "Money tolerance"),
        toleranceInput,
        toleranceError,
        el("div", { className: "form-hint" }, "Optional. Amounts within this difference still reconcile (e.g. 0.01)."),
      ),
      el("div", { className: "form-field", style: "align-self:flex-end;" }, startBtn),
    ),
  );

  card.appendChild(body);

  async function onStart(e) {
    e.preventDefault();

    periodError.style.display = "none";
    toleranceError.style.display = "none";
    const period = periodInput.value.trim();
    if (!isValidPeriod(period)) {
      periodError.textContent = "Enter a valid period in YYYY-MM format.";
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
    startBtn.textContent = "Running…";
    try {
      const result = await startRun(period, tolerance.value);
      toast(`Reconciliation complete for ${period}`, { type: "success" });
      const runId = result && result.run && result.run.id;
      if (runId) {
        window.location.hash = `#/reconciliation/${runId}`;
      } else {
        renderRuns(boxOf(startBtn));
      }
    } catch (err) {
      startBtn.disabled = false;
      startBtn.textContent = "Start reconciliation";
      toast(err.message || "Failed to start reconciliation", { type: "error" });
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
      el("div", { className: "section-title" }, "Run history"),
    ),
  );

  const body = el("div");
  container.appendChild(body);
  showLoading(body, "Loading reconciliation runs…");

  try {
    const data = await listRuns(100, 0);
    const runs = (data && data.runs) || [];
    clear(body);

    if (runs.length === 0) {
      body.appendChild(el("div", { className: "etable-empty" },
        "No reconciliation runs yet — start one for a period above."));
      return;
    }

    const table = el("table", { className: "etable" });
    table.appendChild(
      el("thead",
        el("tr",
          el("th", { className: "num" }, "ID"),
          el("th", null, "Period"),
          el("th", null, "Status"),
          el("th", { className: "num" }, "Invoices"),
          el("th", { className: "num" }, "Tax docs"),
          el("th", { className: "num" }, "Matched"),
          el("th", { className: "num" }, "Unmatched"),
          el("th", { className: "num" }, "Errors"),
          el("th", null, "Started"),
          el("th", null, "Action"),
        ),
      ),
    );
    const tbody = el("tbody");
    for (const run of runs.sort((a, b) => b.id - a.id)) {
      tbody.appendChild(
        el("tr", { className: "is-row-click", dataset: { id: run.id }, onClick: () => { window.location.hash = `#/reconciliation/${run.id}`; } },
          el("td", { className: "num" }, String(run.id)),
          el("td", { className: "mono" }, run.period),
          el("td", el("span", { className: `badge badge--${run.status}` }, runStatusLabel(run.status))),
          el("td", { className: "num" }, formatNumber(run.invoice_count)),
          el("td", { className: "num" }, formatNumber(run.tax_invoice_count)),
          el("td", { className: "num" }, formatNumber(run.matched_count)),
          el("td", { className: "num" }, formatNumber(run.unmatched_count)),
          el("td", { className: "num" }, formatNumber(run.error_count)),
          el("td", { className: "text-sm text-secondary" }, formatDateTime(run.started_at)),
          el("td",
            el("button", { className: "btn btn-secondary btn-sm", onClick: () => { window.location.hash = `#/reconciliation/${run.id}`; } }, "Open"),
          ),
        ),
      );
    }
    table.appendChild(tbody);
    body.appendChild(el("div", { className: "table-wrap" }, table));
  } catch (err) {
    showError(body, err.message || "Failed to load reconciliation runs.", {
      onRetry: () => renderRuns(container),
    });
  }
}