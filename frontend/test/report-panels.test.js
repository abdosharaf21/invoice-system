import { describe, it } from "node:test";
import assert from "node:assert/strict";
import "./helpers/dom.js";
import { renderResultsTable, renderStatusDistribution, renderSummaryStrip } from "../assets/js/components/reportPanels.js";
import { renderPagination } from "../assets/js/components/pagination.js";

function walk(node, visit) {
  visit(node);
  for (const child of node.childNodes || []) walk(child, visit);
}

function count(node, tag) {
  let n = 0;
  walk(node, (el) => { if (el.tagName === tag.toUpperCase()) n += 1; });
  return n;
}

function textOf(node) {
  const parts = [];
  walk(node, (el) => { if (el.nodeType === 3 || el.tagName === "#text" || typeof el.textContent === "string") parts.push(el.textContent); });
  return parts.join("");
}

describe("report panels", () => {
  it("renders a results table row per item with a details button", () => {
    const container = document.createElement("div");
    const envelope = {
      items: [
        { id: 1, match_status: "matched", account_invoice_number: "INV-1", account_currency: "EUR", accounting_total: "10.00", tax_total_amount: "10.00", discrepancy_amount: "0.00" },
        { id: 2, match_status: "mismatched", account_invoice_number: "INV-2", account_currency: "EUR", accounting_total: "11.00", tax_total_amount: "12.00", discrepancy_amount: "1.00" },
      ],
      page: 1, page_size: 10, total: 2, total_pages: 1,
    };
    renderResultsTable(container, envelope, { onRowAction: () => {} });
    assert.equal(count(container, "tr"), 3); // header + 2 rows
    assert.equal(count(container, "table"), 1);
  });

  it("shows an empty-state row when there are no results", () => {
    const container = document.createElement("div");
    renderResultsTable(container, { items: [], page: 1, page_size: 10, total: 0, total_pages: 0 }, { emptyMessage: "Nothing here." });
    assert.ok(textOf(container).includes("Nothing here."));
  });

  it("renders the status distribution bars from the summary envelope", () => {
    const container = document.createElement("div");
    renderStatusDistribution(container, {
      summary: { total_results: 10, matched: 5, mismatched: 2, missing_in_tax_authority: 1, extra_in_tax_authority: 1, invalid: 1 },
    });
    assert.ok(count(container, "div") > 0, "renders bar rows");
    const seen = textOf(container);
    assert.ok(/Matched/.test(seen));
  });

  it("renders the summary strip KPIs", () => {
    const container = document.createElement("div");
    renderSummaryStrip(container, {
      summary: { matched: 5, mismatched: 1, missing_in_tax_authority: 1, extra_in_tax_authority: 0, invalid: 0, total_results: 8, unmatched: 2, errors: 3 },
    });
    const seen = textOf(container);
    assert.ok(/Total results/.test(seen));
    assert.ok(/8/.test(seen));
  });
});

describe("pagination", () => {
  it("drives navigation from the backend envelope", () => {
    const container = document.createElement("div");
    const pages = [];
    renderPagination(container, { page: 3, page_size: 50, total: 130, total_pages: 3 }, (p) => pages.push(p));
    const seen = textOf(container);
    assert.ok(/of 3/.test(seen), seen);
    assert.ok(/130 results/.test(seen), seen);
  });
});