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
  roleClassToken,
  statusLabel,
  statusClassToken,
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

describe("safe status class tokens (P0.1)", () => {
  it("maps every known status to its own token", () => {
    for (const s of [
      "matched", "mismatched", "missing_in_tax_authority", "extra_in_tax_authority",
      "invalid", "pending", "running", "completed", "failed",
      "uploaded", "processing", "sent", "skipped", "no_email", "active", "inactive",
    ]) {
      assert.equal(statusClassToken(s), s);
    }
  });
  it("falls back to neutral for missing, empty and unknown values", () => {
    assert.equal(statusClassToken(null), "neutral");
    assert.equal(statusClassToken(undefined), "neutral");
    assert.equal(statusClassToken(""), "neutral");
    assert.equal(statusClassToken("   "), "neutral");
    assert.equal(statusClassToken("bogus"), "neutral");
  });
  it("never returns a raw attacker-controlled class token", () => {
    assert.equal(statusClassToken('<img src=x onerror=bad>'), "neutral");
    assert.equal(statusClassToken("matched onerror=x"), "neutral");
    assert.equal(statusClassToken('x" style="x'), "neutral");
  });
  it("renders human labels, Unknown for missing and verbatim for unknown", () => {
    assert.equal(statusLabel("completed"), "Completed");
    assert.equal(statusLabel("sent"), "Sent");
    assert.equal(statusLabel("no_email"), "No email");
    assert.equal(statusLabel("active"), "Active");
    assert.equal(statusLabel(null), "Unknown");
    assert.equal(statusLabel(undefined), "Unknown");
    assert.equal(statusLabel(""), "Unknown");
    assert.equal(statusLabel("weird"), "weird");
  });
  it("keeps the domain label helpers consistent with the shared map", () => {
    assert.equal(matchStatusLabel("matched"), statusLabel("matched"));
    assert.equal(matchStatusLabel("bogus"), "bogus");
    assert.equal(runStatusLabel("running"), statusLabel("running"));
    assert.equal(batchStatusLabel("uploaded"), statusLabel("uploaded"));
  });
  it("guards role badge tokens", () => {
    assert.equal(roleClassToken("admin"), "role-admin");
    assert.equal(roleClassToken("accountant"), "role-accountant");
    assert.equal(roleClassToken("manager"), "role-manager");
    assert.equal(roleClassToken("viewer"), "role-viewer");
    assert.equal(roleClassToken("<script>"), "role-viewer");
    assert.equal(roleClassToken(undefined), "role-viewer");
    assert.equal(roleClassToken(null), "role-viewer");
  });
});