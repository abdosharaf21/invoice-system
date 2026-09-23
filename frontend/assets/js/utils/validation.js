/**
 * Client-side validation helpers for forms. These mirror the backend's
 * accepted value formats exactly. Validation here is for UX only — the
 * backend always re-validates and remains authoritative.
 */

import { t } from "../i18n/index.js";

const PERIOD_RE = /^\d{4}-(0[1-9]|1[0-2])$/;
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** Validate a "YYYY-MM" reconciliation period. */
export function isValidPeriod(value) {
  return PERIOD_RE.test(String(value || "").trim());
}

/** Validate a naive ISO date string "YYYY-MM-DD". */
export function isValidDate(value) {
  const raw = String(value || "").trim();
  if (!DATE_RE.test(raw)) return false;
  const [year, month, day] = raw.split("-").map(Number);
  const d = new Date(year, month - 1, day);
  return d.getFullYear() === year && d.getMonth() === month - 1 && d.getDate() === day;
}

/** Validate an email address shape. */
export function isValidEmail(value) {
  return EMAIL_RE.test(String(value || "").trim());
}

/**
 * Parse the optional money tolerance input into an exact decimal string the
 * backend accepts, or null when the field is left blank.
 * Returns { ok, message, value }.
 */
export function parseTolerance(raw) {
  const value = String(raw || "").trim();
  if (value === "") return { ok: true, value: null, message: "" };
  if (!/^\d+(\.\d{1,4})?$/.test(value)) {
    return {
      ok: false,
      value: null,
      message: t("validation.toleranceInvalid"),
    };
  }
  return { ok: true, value, message: "" };
}

/** Clamp an integer into [min, max]; returns null when unparseable. */
export function clampInt(raw, min, max, fallback) {
  const n = Number.parseInt(String(raw), 10);
  if (Number.isNaN(n)) return fallback;
  if (n < min) return min;
  if (max !== null && n > max) return max;
  return n;
}

/** Ensure a page number is >= 1. */
export function pageNumber(raw) {
  return clampInt(raw, 1, null, 1);
}