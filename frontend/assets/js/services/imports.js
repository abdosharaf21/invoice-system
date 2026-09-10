/**
 * Import API client — consuming the /api/imports blueprint.
 */

import { api } from "../api/client.js";

/** Upload a CSV/XLSX accounting file. Accepts a FormData with a "file" field. */
export function uploadImport(formData) {
  return api.upload("/api/imports", formData);
}

/** Fetch an import batch (optionally including its per-row errors). */
export function getBatch(batchId, includeErrors = false) {
  const params = includeErrors ? { include: "errors" } : undefined;
  return api.get(`/api/imports/${batchId}`, params);
}