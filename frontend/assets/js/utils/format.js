/**
 * Display formatting for money, numbers and dates.
 *
 * Money values arrive from the backend as JSON numbers that came from SQL
 * DECIMAL columns. Formatting here is display-only: the frontend never
 * performs arithmetic on financial values — the backend remains the source
 * of truth for totals, differences and reconciliation outcomes.
 *
 * Human labels (statuses, roles, error codes) are resolved through the i18n
 * dictionary for the active locale; en remains the default so the app works
 * before any locale is loaded.
 */

import { t, getLocale } from "../i18n/index.js";

const moneyFmts = new Map();
const numFmts = new Map();

function loc() {
  return getLocale() || "en";
}

function moneyFmt(locale) {
  if (!moneyFmts.has(locale)) {
    moneyFmts.set(locale, new Intl.NumberFormat(locale, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }));
  }
  return moneyFmts.get(locale);
}

function numFmt(locale) {
  if (!numFmts.has(locale)) {
    numFmts.set(locale, new Intl.NumberFormat(locale, { maximumFractionDigits: 4 }));
  }
  return numFmts.get(locale);
}

/**
 * Format a monetary value. Accepts numbers and numeric strings.
 * Returns "—" for null/undefined/blank.
 */
export function formatMoney(value) {
  if (value === null || value === undefined || value === "") return "—";
  const n = Number(value);
  if (Number.isNaN(n)) return String(value);
  return moneyFmt(loc()).format(n);
}

/** Format a generic number without forcing decimals. */
export function formatNumber(value) {
  if (value === null || value === undefined || value === "") return "—";
  const n = Number(value);
  if (Number.isNaN(n)) return String(value);
  return numFmt(loc()).format(n);
}

function renderDate(y, m, d) {
  const dt = new Date(y, m - 1, d);
  if (Number.isNaN(dt.getTime())) return null;
  // en keeps the original "DD Mon YYYY" order so existing behaviour/tests are
  // preserved; other locales fall back to Intl (e.g. Arabic for `ar`).
  if (loc() === "en") {
    return dt.toLocaleDateString("en-GB", {
      day: "2-digit",
      month: "short",
      year: "numeric",
    });
  }
  return dt.toLocaleDateString(loc(), {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

const MONTHS = {
  Jan: 1, Feb: 2, Mar: 3, Apr: 4, May: 5, Jun: 6,
  Jul: 7, Aug: 8, Sep: 9, Oct: 10, Nov: 11, Dec: 12,
};

/** Human "DD Mon YYYY" date from ISO or RFC822 date strings. */
export function formatDate(value) {
  if (!value) return "—";
  const s = String(value).trim();

  // ISO: "YYYY-MM-DD" or "YYYY-MM-DDTHH:MM:SS…"
  let m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s);
  if (m) {
    const out = renderDate(Number(m[1]), Number(m[2]), Number(m[3]));
    if (out) return out;
  }

  // RFC822 (report rows serialize MySQL DATE as "Wed, 06 Mar 2024 00:00:00 GMT").
  m = /^[A-Za-z]{3},\s*(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})/.exec(s);
  if (m) {
    const out = renderDate(Number(m[3]), MONTHS[m[2]], Number(m[1]));
    if (out) return out;
  }

  return s;
}

/** "DD Mon YYYY, HH:MM" datetime display. */
export function formatDateTime(value) {
  if (!value) return "—";
  const parsed = new Date(String(value));
  if (Number.isNaN(parsed.getTime())) return String(value);

  if (loc() === "en") {
    return (
      parsed.toLocaleDateString("en-GB", {
        day: "2-digit",
        month: "short",
        year: "numeric",
      }) +
      ", " +
      parsed.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })
    );
  }
  return (
    parsed.toLocaleDateString(loc(), {
      day: "numeric",
      month: "short",
      year: "numeric",
    }) +
    ", " +
    parsed.toLocaleTimeString(loc(), { hour: "2-digit", minute: "2-digit" })
  );
}

/** Parse a form "YYYY-MM" period into the exact value the backend accepts. */
export function normalizePeriod(raw) {
  return String(raw || "").trim();
}

/** Shared, allow-listed business statuses (reconciliation, runs, batches,
 * email deliveries, users). Single source of truth for class tokens/labels. */
const STATUS_LABELS = {
  matched: true,
  mismatched: true,
  missing_in_tax_authority: true,
  extra_in_tax_authority: true,
  invalid: true,
  pending: true,
  running: true,
  completed: true,
  failed: true,
  uploaded: true,
  processing: true,
  sent: true,
  skipped: true,
  no_email: true,
  active: true,
  inactive: true,
};

/**
 * Return a safe CSS class token for a business status. null / undefined /
 * empty / unknown values fall back to `fallback` (default "neutral") so a
 * backend value can never be interpolated raw into a class name.
 */
export function statusClassToken(status, fallback = "neutral") {
  if (status === null || status === undefined) return fallback;
  const s = String(status).trim();
  if (s === "" || !Object.prototype.hasOwnProperty.call(STATUS_LABELS, s)) return fallback;
  return s;
}

/**
 * Human label for a status. Missing values produce "Unknown"; unknown values
 * are returned verbatim (they are still rendered as safe text, never markup).
 */
export function statusLabel(status) {
  if (status === null || status === undefined) return t("common.unknown");
  const s = String(status).trim();
  if (s === "") return t("common.unknown");
  const key = `status.${s}`;
  const out = t(key);
  return out === key ? s : out;
}

/** Human label for a reconciliation match status. */
export function matchStatusLabel(status) {
  return statusLabel(status);
}

/** Human label for a run status. */
export function runStatusLabel(status) {
  return statusLabel(status);
}

/** Human label for a batch status. */
export function batchStatusLabel(status) {
  return statusLabel(status);
}

/** Human label for an import error code. */
export function importErrorLabel(code) {
  const key = `error.import.${code}`;
  const out = t(key);
  return out === key ? code : out;
}

/** Human label for a reconciliation error type code. */
export function errorTypeLabel(code) {
  const key = `error.recon.${code}`;
  const out = t(key);
  return out === key ? code : out;
}

/** Human label for a role. */
export function roleLabel(role) {
  const key = `role.${role}`;
  const out = t(key);
  return out === key ? role : out;
}

/** Safe CSS class token for a role badge; unknown roles fall back to "viewer". */
export function roleClassToken(role) {
  const tokens = {
    admin: "role-admin",
    accountant: "role-accountant",
    manager: "role-manager",
    viewer: "role-viewer",
  };
  return tokens[role] === undefined ? "role-viewer" : tokens[role];
}

/** Human label for an error source type. */
export function sourceTypeLabel(sourceType) {
  if (sourceType === "account") return t("report.sourceAccounting");
  if (sourceType === "tax") return t("report.sourceTax");
  return sourceType || "—";
}