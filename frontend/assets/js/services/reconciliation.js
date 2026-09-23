/**
 * Reconciliation API client — consuming the /api/reconciliation blueprint.
 */

import { api } from "../api/client.js";

/** Start a run for a period (and optional money tolerance). Returns {run, counts}. */
export function startRun(period, moneyTolerance = null) {
  const body = { period };
  if (moneyTolerance !== null && moneyTolerance !== "") body["money_tolerance"] = moneyTolerance;
  return api.post("/api/reconciliation/runs", body);
}

/**
 * List runs for the authenticated company.
 *
 * Accepts either positional args ``listRuns(limit, offset)`` or an options
 * object ``listRuns({ limit, offset })``. Pagination values are coerced to
 * integers and defaulted when missing/empty so the backend always receives
 * valid integer query parameters.
 */
export function listRuns(limit = 50, offset = 0) {
  const opts =
    limit && typeof limit === "object" ? limit : { limit, offset };
  return api.get("/api/reconciliation/runs", {
    limit: normalizePage(opts.limit, 50),
    offset: normalizePage(opts.offset, 0),
  });
}

function normalizePage(value, fallback) {
  const n = Number(value);
  return Number.isInteger(n) && n >= 0 ? n : fallback;
}

/** Get a single run + per-status counts. */
export function getRun(runId) {
  return api.get(`/api/reconciliation/runs/${runId}`);
}

/** Get the structured report summary for a run. */
export function getReportSummary(runId) {
  return api.get(`/api/reconciliation/runs/${runId}/summary`);
}

/**
 * Get paginated, filtered results.
 * @param {object} filters — {page, page_size, match_status, uuid, invoice_number, date_from, date_to}
 */
export function getResults(runId, filters = {}) {
  return api.get(`/api/reconciliation/runs/${runId}/results`, filters);
}

/**
 * Get paginated, filtered errors.
 * @param {object} filters — {page, page_size, error_type, source_type}
 */
export function getErrors(runId, filters = {}) {
  return api.get(`/api/reconciliation/runs/${runId}/errors`, filters);
}

/** Export results (format: "csv" | "xlsx", plus result filters). */
export function exportResults(runId, format, filters = {}) {
  return api.download(`/api/reconciliation/runs/${runId}/results/export`, {
    ...filters,
    format,
  });
}

/** Export errors (format: "csv" | "xlsx", plus error filters). */
export function exportErrors(runId, format, filters = {}) {
  return api.download(`/api/reconciliation/runs/${runId}/errors/export`, {
    ...filters,
    format,
  });
}