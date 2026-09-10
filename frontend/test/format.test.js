import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  formatMoney,
  formatNumber,
  formatDate,
  formatDateTime,
  normalizePeriod,
  matchStatusLabel,
  runStatusLabel,
  batchStatusLabel,
  importErrorLabel,
  errorTypeLabel,
  roleLabel,
  sourceTypeLabel,
} from "../assets/js/utils/format.js";

describe("formatMoney", () => {
  it("formats numbers with two decimals", () => {
    assert.equal(formatMoney(1234.5), "1,234.50");
    assert.equal(formatMoney(0), "0.00");
  });
  it("keeps a dash for missing values", () => {
    assert.equal(formatMoney(null), "—");
    assert.equal(formatMoney(undefined), "—");
    assert.equal(formatMoney(""), "—");
  });
  it("falls back to the raw string for non-numeric input", () => {
    assert.equal(formatMoney("abc"), "abc");
  });
});

describe("formatNumber", () => {
  it("formats integers without decimals", () => {
    assert.equal(formatNumber(12), "12");
  });
  it("keeps a dash for missing values", () => {
    assert.equal(formatNumber(null), "—");
  });
});

describe("formatDate / formatDateTime", () => {
  it("renders a readable date", () => {
    assert.equal(formatDate("2024-03-05"), "05 Mar 2024");
  });
  it("renders a readable datetime", () => {
    const out = formatDateTime("2024-03-05T10:15:00");
    assert.equal(out, "05 Mar 2024, 10:15");
  });
  it("keeps invalid values verbatim", () => {
    assert.equal(formatDate("nope"), "nope");
    assert.equal(formatDateTime(null), "—");
  });
  it("parses RFC822 dates from report rows", () => {
    assert.equal(formatDate("Wed, 06 Mar 2024 00:00:00 GMT"), "06 Mar 2024");
    assert.equal(formatDate("Mon, 09 Jan 2026 00:00:00 GMT"), "09 Jan 2026");
  });
  it("parses ISO datetime strings as dates", () => {
    assert.equal(formatDate("2024-03-05T00:00:00"), "05 Mar 2024");
  });
});

describe("normalizePeriod", () => {
  it("trims surrounding whitespace", () => {
    assert.equal(normalizePeriod("  2024-03  "), "2024-03");
  });
});

describe("status / role labels", () => {
  it("maps match statuses", () => {
    assert.equal(matchStatusLabel("matched"), "Matched");
    assert.equal(matchStatusLabel("missing_in_tax_authority"), "Missing in Tax Authority");
    assert.equal(matchStatusLabel("bogus"), "bogus");
  });
  it("maps run statuses", () => {
    assert.equal(runStatusLabel("completed"), "Completed");
    assert.equal(runStatusLabel("pending"), "Pending");
  });
  it("maps batch statuses", () => {
    assert.equal(batchStatusLabel("processing"), "Processing");
    assert.equal(batchStatusLabel("failed"), "Failed");
  });
  it("maps import error codes", () => {
    assert.equal(importErrorLabel("DUPLICATE_IN_DB"), "Invoice already exists");
    assert.equal(importErrorLabel("UNKNOWN"), "UNKNOWN");
  });
  it("maps reconciliation error types", () => {
    assert.equal(errorTypeLabel("TOTAL_AMOUNT_MISMATCH"), "Total amount differs");
    assert.equal(errorTypeLabel("TOTAL_AMOUNT_MISMATCH"), "Total amount differs");
    assert.equal(errorTypeLabel("NOPE"), "NOPE");
  });
  it("maps roles", () => {
    assert.equal(roleLabel("admin"), "Admin");
    assert.equal(roleLabel("viewer"), "Viewer");
    assert.equal(roleLabel("x"), "x");
  });
  it("maps source types", () => {
    assert.equal(sourceTypeLabel("account"), "Accounting");
    assert.equal(sourceTypeLabel("tax"), "Tax Authority");
    assert.equal(sourceTypeLabel(null), "—");
  });
});