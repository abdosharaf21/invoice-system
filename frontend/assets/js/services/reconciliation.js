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

/** List runs for the authenticated company. */
export function listRuns(limit = 50, offset = 0) {
  return api.get("/api/reconciliation/runs", { limit, offset });
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