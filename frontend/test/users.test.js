import { describe, it, beforeEach } from "node:test";
import assert from "node:assert/strict";
import "./helpers/dom.js";
import { renderUsers } from "../assets/js/pages/users.js";

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

describe("users table (P0.2)", () => {
  beforeEach(() => {
    globalThis.fetch = async (url) => {
      if (String(url).includes("/api/users/")) {
        return jsonResponse(200, { success: true, data: [
          { id: 1, username: "alice", full_name: "Alice <img src=x onerror=evil()>", email: "alice@corp.test", roles: ["admin"], company_id: 3, is_active: true, last_login_at: "2024-03-05T10:15:00" },
          { id: 2, username: "bob", full_name: "Bob", email: "bob@corp.test", roles: ["x"], company_id: null, is_active: false, last_login_at: null },
        ] });
      }
      return jsonResponse(404, { success: false, message: "Not found" });
    };
  });

  it("renders an enterprise table inside a scroll wrapper", async () => {
    const container = document.createElement("div");
    await renderUsers(container);
    const table = container.querySelector("table");
    assert.ok(table, "a table is rendered");
    assert.ok(table.className.includes("etable"), `expected etable, got "${table.className}"`);
    assert.ok(container.querySelector(".table-wrap"), "table is wrapped in .table-wrap");
  });

  it("renders a header row for every user column", async () => {
    const container = document.createElement("div");
    await renderUsers(container);
    const table = container.querySelector("table");
    const headers = table.querySelector("thead").querySelectorAll("th");
    assert.equal(headers.length, 8);
    const seen = textOf(table.querySelector("thead"));
    assert.ok(seen.includes("Full name") && seen.includes("Actions"));
  });

  it("keeps backend-provided names as text nodes (XSS-literal)", async () => {
    const container = document.createElement("div");
    await renderUsers(container);
    assert.equal(container.querySelectorAll("img").length, 0, "no <img> element parsed from user input");
    const strongs = container.querySelectorAll("strong");
    const name = strongs[0];
    const firstChild = name.childNodes[0];
    assert.ok(firstChild && firstChild.nodeType === 3, "name is a text node, not markup");
    const shown = textOf(name);
    assert.ok(shown.includes("Alice"), "raw user name is preserved as display text");
  });

  it("guards role and status badge classes", async () => {
    const container = document.createElement("div");
    await renderUsers(container);
    const badges = container.querySelectorAll(".badge");
    const classes = badges.map((b) => b.className);
    assert.ok(classes.some((c) => c.includes("badge--active")), "active user badge class is allow-listed");
    assert.ok(classes.some((c) => c.includes("badge--inactive")), "inactive user badge class is allow-listed");
    assert.ok(classes.some((c) => c.includes("badge--admin") || c.includes("badge--role-admin")), "admin role badge present");
    assert.ok(classes.every((c) => /badge--(active|inactive|role-(admin|accountant|manager|viewer))/.test(c)),
      `no unbounded badge class interpolation: ${classes.join(", ")}`);
  });

  it("renders per-user rows with action buttons", async () => {
    const container = document.createElement("div");
    await renderUsers(container);
    const rows = container.querySelector("tbody").querySelectorAll("tr");
    assert.equal(rows.length, 2);
    const rowText = textOf(container.querySelector("tbody"));
    assert.ok(rowText.includes("Edit") && rowText.includes("Password") && rowText.includes("Delete"));
  });
});