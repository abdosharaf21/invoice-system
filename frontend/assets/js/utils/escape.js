/**
 * HTML escaping. Every dynamic string rendered into the DOM goes through
 * this helper (or is assigned via textContent). Never inject untrusted
 * backend content with raw innerHTML.
 */

export function escapeHtml(value) {
  if (value === null || value === undefined) return "";
  return String(value).replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[ch]);
}

/** Shortcut: escape only when a value is a string to keep none escaped. */
export function safe(value) {
  return escapeHtml(value);
}