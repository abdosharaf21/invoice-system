import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { escapeHtml } from "../assets/js/utils/escape.js";

describe("escapeHtml", () => {
  it("escapes markup-breaking characters", () => {
    assert.equal(escapeHtml('<script>"x"&\'y\''),
      "&lt;script&gt;&quot;x&quot;&amp;&#39;y&#39;");
  });
  it("preserves safe text", () => {
    assert.equal(escapeHtml("Invoice INV-100 · 12.50"), "Invoice INV-100 · 12.50");
  });
  it("handles edge inputs", () => {
    assert.equal(escapeHtml(""), "");
    assert.equal(escapeHtml(null), "");
    assert.equal(escapeHtml(undefined), "");
    assert.equal(escapeHtml(42), "42");
  });
});