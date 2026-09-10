/**
 * Display formatting for money, numbers and dates.
 *
 * Money values arrive from the backend as JSON numbers that came from SQL
 * DECIMAL columns. Formatting here is display-only: the frontend never
 * performs arithmetic on financial values — the backend remains the source
 * of truth for totals, differences and reconciliation outcomes.
 */

const moneyFmt = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const numFmt = new Intl.NumberFormat("en-US", { maximumFractionDigits: 4 });

/**
 * Format a monetary value. Accepts numbers and numeric strings.
 * Returns "—" for null/undefined/blank.
 */
export function formatMoney(value) {
  if (value === null || value === undefined || value === "") return "—";
  const n = Number(value);
  if (Number.isNaN(n)) return String(value);
  return moneyFmt.format(n);
}

/** Format a generic number without forcing decimals. */
export function formatNumber(value) {
  if (value === null || value === undefined || value === "") return "—";
  const n = Number(value);
  if (Number.isNaN(n)) return String(value);
  return numFmt.format(n);
}

function renderDate(y, m, d) {
  const dt = new Date(y, m - 1, d);
  if (Number.isNaN(dt.getTime())) return null;
  return dt.toLocaleDateString("en-GB", {
    day: "2-digit",
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

/** Parse a form "YYYY-MM" period into the exact value the backend accepts. */
export function normalizePeriod(raw) {
  return String(raw || "").trim();
}

/** Human label for a reconciliation match status. */
export function matchStatusLabel(status) {
  const labels = {
    matched: "Matched",
    mismatched: "Mismatched",
    missing_in_tax_authority: "Missing in Tax Authority",
    extra_in_tax_authority: "Extra in Tax Authority",
    invalid: "Invalid",
  };
  return labels[status] || status;
}

/** Human label for a run status. */
export function runStatusLabel(status) {
  const labels = {
    pending: "Pending",
    running: "Running",
    completed: "Completed",
    failed: "Failed",
  };
  return labels[status] || status;
}

/** Human label for a batch status. */
export function batchStatusLabel(status) {
  const labels = {
    uploaded: "Uploaded",
    processing: "Processing",
    completed: "Completed",
    failed: "Failed",
  };
  return labels[status] || status;
}

/** Human label for an import error code. */
export function importErrorLabel(code) {
  const labels = {
    MISSING_FIELD: "Missing required field",
    INVALID_UUID: "Invalid UUID",
    INVALID_DATE: "Invalid date",
    INVALID_MONEY: "Invalid monetary value",
    INVALID_QUANTITY: "Invalid quantity",
    INVALID_ENUM: "Invalid value",
    MISSING_HEADER: "Missing column header",
    DUPLICATE_HEADER: "Duplicate column header",
    UNKNOWN_HEADER: "Unrecognised column header",
    INCONSISTENT_GROUP: "Conflicting values within invoice group",
    DUPLICATE_IN_FILE: "Duplicate invoice in file",
    DUPLICATE_IN_DB: "Invoice already exists",
    FILE_ERROR: "File error",
  };
  return labels[code] || code;
}

/** Human label for a reconciliation error type code. */
export function errorTypeLabel(code) {
  const labels = {
    INVALID_UUID: "Invalid UUID",
    INVALID_DATE: "Invalid date",
    INVALID_FINANCIAL_VALUE: "Invalid financial value",
    INVOICE_DATE_MISMATCH: "Invoice date differs",
    CURRENCY_MISMATCH: "Currency differs",
    COUNTERPARTY_TAX_ID_MISMATCH: "Counterparty tax ID differs",
    COUNTERPARTY_NAME_MISMATCH: "Counterparty name differs",
    SUBTOTAL_AMOUNT_MISMATCH: "Subtotal amount differs",
    DISCOUNT_AMOUNT_MISMATCH: "Discount amount differs",
    NET_AMOUNT_MISMATCH: "Net amount differs",
    VAT_AMOUNT_MISMATCH: "VAT amount differs",
    TOTAL_AMOUNT_MISMATCH: "Total amount differs",
    ITEM_COUNT_MISMATCH: "Item count differs",
    ITEM_QUANTITY_SUM_MISMATCH: "Item quantity sum differs",
    ITEM_VAT_SUM_MISMATCH: "Item VAT sum differs",
    ITEM_TOTAL_SUM_MISMATCH: "Item line-total sum differs",
  };
  return labels[code] || code;
}

/** Human label for a role. */
export function roleLabel(role) {
  const labels = {
    admin: "Admin",
    accountant: "Accountant",
    manager: "Manager",
    viewer: "Viewer",
  };
  return labels[role] || role;
}

/** Human label for an error source type. */
export function sourceTypeLabel(sourceType) {
  if (sourceType === "account") return "Accounting";
  if (sourceType === "tax") return "Tax Authority";
  return sourceType || "—";
}