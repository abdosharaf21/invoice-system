import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  isValidPeriod,
  isValidDate,
  isValidEmail,
  parseTolerance,
  clampInt,
  pageNumber,
} from "../assets/js/utils/validation.js";

describe("isValidPeriod", () => {
  it("accepts YYYY-MM", () => {
    assert.equal(isValidPeriod("2024-03"), true);
    assert.equal(isValidPeriod("2024-12"), true);
    assert.equal(isValidPeriod("2024-01"), true);
  });
  it("rejects malformed periods", () => {
    assert.equal(isValidPeriod("2024-13"), false);
    assert.equal(isValidPeriod("2024-0"), false);
    assert.equal(isValidPeriod("mar-2024"), false);
    assert.equal(isValidPeriod(""), false);
  });
});

describe("isValidDate", () => {
  it("accepts real ISO dates", () => {
    assert.equal(isValidDate("2024-02-29"), true);
  });
  it("rejects impossible dates", () => {
    assert.equal(isValidDate("2024-02-30"), false);
    assert.equal(isValidDate("2024/03/01"), false);
  });
});

describe("isValidEmail", () => {
  it("accepts basic emails", () => {
    assert.equal(isValidEmail("a@b.co"), true);
    assert.equal(isValidEmail("first.last@example.com"), true);
  });
  it("rejects bad emails", () => {
    assert.equal(isValidEmail("nope"), false);
    assert.equal(isValidEmail("a@b"), false);
    assert.equal(isValidEmail(""), false);
  });
});

describe("parseTolerance", () => {
  it("returns null for blank input", () => {
    assert.deepEqual(parseTolerance(""), { ok: true, value: null, message: "" });
  });
  it("accepts non-negative decimals", () => {
    assert.deepEqual(parseTolerance("0.01"), { ok: true, value: "0.01", message: "" });
    assert.deepEqual(parseTolerance("5"), { ok: true, value: "5", message: "" });
  });
  it("rejects negatives and junk", () => {
    assert.equal(parseTolerance("-1").ok, false);
    assert.equal(parseTolerance("abc").ok, false);
    assert.equal(parseTolerance("0.00123").ok, false); // >4dp rejected client-side
  });
});

describe("clampInt / pageNumber", () => {
  it("clamps into range", () => {
    assert.equal(clampInt("5", 1, 10, 1), 5);
    assert.equal(clampInt("0", 1, 10, 1), 1);
    assert.equal(clampInt("99", 1, 10, 1), 10);
    assert.equal(clampInt("x", 1, 10, 1), 1);
  });
  it("keeps page numbers >= 1", () => {
    assert.equal(pageNumber("1"), 1);
    assert.equal(pageNumber("0"), 1);
    assert.equal(pageNumber(undefined), 1);
  });
});