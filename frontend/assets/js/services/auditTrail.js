/**
 * Audit trail API client — consuming the /api/audit-trail blueprint.
 *
 * The endpoint is scoped to the authenticated company by the backend and is
 * available to admins and managers only. Responses are wrapped as
 * { success, data } and the shared api client unwraps `data`, so this returns
 * the pagination envelope { items, total, page, page_size, total_pages }.
 */

import { api } from "../api/client.js";

/** Params forwarded verbatim; empty/undefined values are omitted. */
const FILTER_PARAMS = [
  "page",
  "page_size",
  "action",
  "resource_type",
  "result",
  "actor_id",
  "start_date",
  "end_date",
  "sort_by",
];

/**
 * List audit trail entries with optional filters.
 * @param {object} filters — {page, page_size, action, resource_type, result,
 *   actor_id, start_date, end_date, sort_by}
 */
export function listAuditLogs(filters = {}) {
  const params = {};
  for (const key of FILTER_PARAMS) {
    const value = filters[key];
    if (value !== undefined && value !== null && value !== "") {
      params[key] = value;
    }
  }
  return api.get("/api/audit-trail/logs", params);
}