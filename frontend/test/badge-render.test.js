import { describe, it } from "node:test";
import assert from "node:assert/strict";
import "./helpers/dom.js";
import { renderBadge } from "../assets/js/utils/dom.js";

function walk(node, visit) {
  visit(node);
  for (const child of node.childNodes || []) walk(child, visit);
}

function textOf(node) {
  const parts = [];
  walk(node, (el) => { if (typeof el.textContent === "string") parts.push(el.textContent); });
  return parts.join("");
}

describe("renderBadge (P0.1)", () => {
  it("applies the allow-listed class token to known statuses", () => {
    const badge = renderBadge("completed");
    assert.ok(badge.className.includes("badge--completed"));
  });

  it("falls back to neutral instead of interpolating null/undefined/unknown", () => {
    assert.ok(renderBadge(null).className.includes("badge--neutral"));
    assert.ok(renderBadge(undefined).className.includes("badge--neutral"));
    assert.ok(renderBadge("").className.includes("badge--neutral"));
    assert.ok(renderBadge("totally-bogus").className.includes("badge--neutral"));
  });

  it("never turns attacker input into a CSS class", () => {
    assert.ok(renderBadge('<img src=x onerror=evil()>').className.includes("badge--neutral"));
  });

  it("keeps the label as display text, not markup", () => {
    const badge = renderBadge("matched");
    assert.ok(badge.className.includes("badge--matched"));
    assert.equal(textOf(badge), "matched");
    const raw = renderBadge("<b>x</b>");
    assert.equal(textOf(raw), "<b>x</b>");
  });
});