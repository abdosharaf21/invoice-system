/**
 * Tiny payload unwrappers shared across pages.
 */

/**
 * POST /api/imports returns data = {batch, errors}. Older/direct responses
 * could return the batch alone, so accept both shapes.
 * @param {object|undefined} result - response data payload.
 * @returns {object} the import batch.
 */
export function unwrapImportResult(result) {
  return (result && result.batch) || result || {};
}