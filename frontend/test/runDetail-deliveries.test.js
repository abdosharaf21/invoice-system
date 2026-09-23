import { describe, it, beforeEach } from "node:test";
import assert from "node:assert/strict";
import "./helpers/dom.js";
import { renderRunDetail } from "../assets/js/pages/runDetail.js";

function jsonResponse(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Map([["content-type", "application/json"]]),
    async json() { return body; },
    async blob() { return new Blob(["x"]); },
  };
}

function walk(node, visit) {
  visit(node);
  for (const child of node.childNodes || []) walk(child, visit);
}

function textOf(node) {
  const parts = [];
  walk(node, (el) => { if (typeof el.textContent === "string") parts.push(el.textContent); });
  return parts.join("");
}

const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

describe("run detail email-deliveries table (P0.3)", () => {
  beforeEach(() => {
    globalThis.fetch = async (url) => {
      const u = String(url);
      if (u.includes("/email-deliveries")) {
        return jsonResponse(200, { success: true, data: { deliveries: [
          { id: 11, recipient_email: "a@b.co", taxpayer_name: "ACME <img src=x>", invoice_count: 3, status: "sent", subject: "Invoice available", attempted_at: "2024-03-05T10:15:00" },
          { id: 12, recipient_email: null, taxpayer_name: "No-email Co", invoice_count: 0, status: "no_email", subject: "Invoice available", attempted_at: null },
          { id: 13, recipient_email: "c@d.co", taxpayer_name: "Beta", invoice_count: 1, status: "weird-status", subject: "Invoice available", attempted_at: null },
        ] } });
      }
      if (u.includes("/summary")) {
        return jsonResponse(200, { success: true, data: { summary: { total_results: 3, matched: 3, unmatched: 0, errors: 0 } } });
      }
      if (u.includes("/results")) {
        return jsonResponse(200, { success: true, data: { items: [], page: 1, page_size: 50, total: 0, total_pages: 0 } });
      }
      if (u.includes("/runs/")) {
        return jsonResponse(200, { success: true, data: { run: { id: 5, period: "2024-03", status: "completed", invoice_count: 3, tax_invoice_count: 3 } } });
      }
      return jsonResponse(404, { success: false, message: "Not found" });
    };
  });

  it("renders the deliveries table with the etable/table-wrap pattern", async () => {
    const container = document.createElement("div");
    await renderRunDetail(container, [5]);
    await settle();
    const body = container.querySelector("#email-deliveries-body");
    assert.ok(body, "deliveries card body present");
    const table = body.querySelector("table");
    assert.ok(table, "deliveries table rendered");
    assert.ok(table.className.includes("etable"), `expected etable, got "${table.className}"`);
    assert.ok(body.querySelector(".table-wrap"), "deliveries table wrapped in .table-wrap");
    const headers = table.querySelector("thead").querySelectorAll("th");
    assert.equal(headers.length, 7);
    const seen = textOf(table.querySelector("thead"));
    assert.ok(seen.includes("Recipient") && seen.includes("Status"));
  });

  it("renders one row per delivery with a controlled badge class", async () => {
    const container = document.createElement("div");
    await renderRunDetail(container, [5]);
    await settle();
    const table = container.querySelector("#email-deliveries-body").querySelector("table");
    const rows = table.querySelector("tbody").querySelectorAll("tr");
    assert.equal(rows.length, 3);
    const statusCells = table.querySelector("tbody").querySelectorAll(".badge");
    assert.equal(statusCells.length, 3);
    for (const cell of statusCells) {
      assert.ok(/badge--(completed|neutral|pending|failed|warn|invalid)/.test(cell.className), `unbounded badge class: ${cell.className}`);
    }
    assert.ok(textOf(table).includes("Sent"), "known delivery status rendered with human label");
  });

  it("renders all tables in the view with the etable pattern", async () => {
    const container = document.createElement("div");
    await renderRunDetail(container, [5]);
    await settle();
    const tables = container.querySelectorAll("table");
    assert.ok(tables.length >= 2, "results + deliveries tables rendered");
    for (const table of tables) {
      assert.ok(table.className.includes("etable"), `expected etable everywhere, got "${table.className}"`);
    }
  });
});