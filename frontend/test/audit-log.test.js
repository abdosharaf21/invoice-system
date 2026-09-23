import { describe, it, beforeEach } from "node:test";
import assert from "node:assert/strict";
import "./helpers/dom.js";
import { authStore } from "../assets/js/auth/store.js";
import { resolveRoute, canEnter } from "../assets/js/config/routes.js";
import en from "../assets/js/i18n/en.js";
import ar from "../assets/js/i18n/ar.js";
import { renderAuditLog } from "../assets/js/pages/auditLog.js";
import { listAuditLogs } from "../assets/js/services/auditTrail.js";

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

const envelope = {
  items: [
    {
      id: 1,
      actor_id: 42,
      actor_email: "alice@corp.test",
      role: "admin",
      action: "update",
      resource_type: "user",
      resource_id: 7,
      result: "success",
      metadata: { "field": "email" },
      request_id: "req-abc123",
      ip_address: "10.0.0.5",
      user_agent: "Mozilla/5.0",
      created_at: "2024-03-05T10:15:00",
      company_id: 3,
      actor_type: "user",
      before_state: { "is_active": true },
      after_state: { "is_active": false },
    },
    {
      id: 2,
      actor_id: null,
      actor_email: null,
      role: null,
      action: "import",
      resource_type: "import",
      resource_id: 99,
      result: "failure",
      metadata: null,
      request_id: null,
      ip_address: null,
      user_agent: null,
      created_at: null,
      company_id: null,
      actor_type: "system",
      before_state: null,
      after_state: null,
    },
    {
      id: 3,
      actor_id: 7,
      actor_email: "<script>alert('x')</script>@corp.test",
      role: "viewer",
      action: "surprise",
      resource_type: "unknown_resource",
      resource_id: null,
      result: "meh",
      metadata: { "note": "</pre><img src=x onerror=evil()>" },
      request_id: "req-xyz",
      ip_address: "10.0.0.6",
      user_agent: "curl/8",
      created_at: "2024-03-04T09:00:00",
      company_id: 0,
      actor_type: "system",
      before_state: null,
      after_state: null,
    },
  ],
  total: 3,
  page: 1,
  page_size: 50,
  total_pages: 1,
  pages: 1,
};

describe("audit log service", () => {
  beforeEach(() => {
    authStore.setTokens({ access: "tok" });
  });

  it("forwards only non-empty filter params to the endpoint", async () => {
    let calledWith = null;
    globalThis.fetch = async (url) => {
      calledWith = String(url);
      return jsonResponse(200, { success: true, data: envelope });
    };
    await listAuditLogs({ page: 2, page_size: 25, action: "", result: "success" });
    assert.ok(calledWith.includes("/api/audit-trail/logs"));
    assert.ok(calledWith.includes("page=2") && calledWith.includes("page_size=25"));
    assert.ok(calledWith.includes("result=success"));
    assert.ok(!calledWith.includes("action="), "empty action omitted");
    assert.ok(!calledWith.includes("actor_id"), "absent actor_id omitted");
  });

  it("returns the unwrapped pagination envelope", async () => {
    globalThis.fetch = async () => jsonResponse(200, { success: true, data: envelope });
    const data = await listAuditLogs({});
    assert.equal(data.total, 3);
    assert.equal(data.total_pages, 1);
    assert.equal(data.items.length, 3);
  });
});

describe("audit log page", () => {
  beforeEach(() => {
    authStore.clear();
    authStore.setTokens({ access: "tok" });
  });

  it("renders the toolbar, table and pagination from the envelope", async () => {
    globalThis.fetch = async (url) => {
      assert.ok(String(url).includes("/api/audit-trail/logs"));
      return jsonResponse(200, { success: true, data: envelope });
    };
    const container = document.createElement("div");
    await renderAuditLog(container);

    const head = textOf(container.querySelector(".page-head"));
    assert.ok(head.includes("Audit Log"));

    for (const field of ["action", "resource_type", "result", "sort_by"]) {
      assert.ok(container.querySelector(`[data-field="${field}"]`), `filter control ${field} rendered`);
    }
    assert.ok(container.querySelector('[data-field="start_date"]'));
    assert.ok(container.querySelector('[data-field="end_date"]'));
    assert.ok(container.querySelector('[data-field="apply"]'));
    assert.ok(container.querySelector('[data-field="reset"]'));

    const table = container.querySelector("table");
    assert.ok(table, "a table is rendered");
    const headers = textOf(table.querySelector("thead"));
    assert.ok(headers.includes("Time") && headers.includes("Actor") && headers.includes("Action"));
    assert.ok(headers.includes("Request ID") && headers.includes("IP address"));

    const rows = container.querySelector("tbody").querySelectorAll("tr");
    assert.equal(rows.length, 3);
    const bodyText = textOf(container.querySelector("tbody"));
    assert.ok(bodyText.includes("alice@corp.test"));
    assert.ok(bodyText.includes("Reconcile") === false);

    assert.ok(textOf(container).includes("Page 1 of 1"));
  });

  it("applies filters and reloads with page 1", async () => {
    const urls = [];
    globalThis.fetch = async (url) => {
      urls.push(String(url));
      return jsonResponse(200, { success: true, data: envelope });
    };
    const container = document.createElement("div");
    await renderAuditLog(container);

    const action = container.querySelector('[data-field="action"]');
    action.value = "login";
    container.querySelector('[data-field="start_date"]').value = "2024-03-01";
    container.querySelector('[data-field="apply"]').click();

    const last = urls[urls.length - 1];
    assert.ok(last.includes("action=login"), `action filter forwarded: ${last}`);
    assert.ok(last.includes("start_date=2024-03-01"), `start date forwarded: ${last}`);
    assert.ok(last.includes("page=1"), `resets to page 1 after filter: ${last}`);
  });

  it("reset clears the filters and reloads", async () => {
    const urls = [];
    globalThis.fetch = async (url) => {
      urls.push(String(url));
      return jsonResponse(200, { success: true, data: { ...envelope, items: envelope.items.slice(0, 1) } });
    };
    const container = document.createElement("div");
    await renderAuditLog(container);

    const action = container.querySelector('[data-field="action"]');
    action.value = "delete";
    container.querySelector('[data-field="apply"]').click();
    container.querySelector('[data-field="reset"]').click();

    const last = urls[urls.length - 1];
    assert.ok(!last.includes("action="), `reset drops action filter: ${last}`);
    assert.ok(!last.includes("start_date="));
  });

  it("shows an empty state when no entries match", async () => {
    globalThis.fetch = async () => jsonResponse(200, { success: true, data: { items: [], total: 0, page: 1, page_size: 50, total_pages: 0 } });
    const container = document.createElement("div");
    await renderAuditLog(container);
    assert.ok(container.querySelector(".state-block"));
    assert.ok(textOf(container).includes("No audit entries match the current filters."));
  });

  it("shows an error state when the request fails", async () => {
    globalThis.fetch = async () => jsonResponse(500, { success: false, message: "boom" });
    const container = document.createElement("div");
    await renderAuditLog(container);
    assert.ok(container.querySelector('[role="alert"]'));
    assert.ok(textOf(container).includes("boom"));
  });

  it("keeps backend strings as text nodes (XSS-literal)", async () => {
    globalThis.fetch = async () => jsonResponse(200, { success: true, data: envelope });
    const container = document.createElement("div");
    await renderAuditLog(container);

    assert.equal(container.querySelectorAll("img").length, 0, "no <img> parsed from payload");
    assert.equal(container.querySelectorAll("script").length, 0, "no <script> parsed from payload");
    const bodyText = textOf(container.querySelector("tbody"));
    assert.ok(bodyText.includes("<script>alert('x')</script>@corp.test"), "email preserved as display text");
    assert.ok(bodyText.includes("surprise"), "unknown action rendered verbatim");
    assert.ok(bodyText.includes("unknown_resource"), "unknown resource type rendered verbatim");
  });

  it("badge classes are allow-listed", async () => {
    globalThis.fetch = async () => jsonResponse(200, { success: true, data: envelope });
    const container = document.createElement("div");
    await renderAuditLog(container);
    const badges = container.querySelectorAll(".badge");
    const classes = badges.map((b) => b.className);
    for (const c of classes) {
      assert.match(c, /badge--(ok|failed|neutral|plain|role-(admin|accountant|manager|viewer))/,
        `unbounded badge class interpolation: ${c}`);
    }
  });

  it("opens a details modal with metadata and state snapshots", async () => {
    globalThis.fetch = async () => jsonResponse(200, { success: true, data: envelope });
    const container = document.createElement("div");
    await renderAuditLog(container);

    const details = container.querySelector("tbody").querySelectorAll("button");
    assert.equal(details.length, 3);
    details[0].click();

    const modal = document.body.querySelector(".modal");
    assert.ok(modal, "details modal is opened");
    const modalText = textOf(modal);
    assert.ok(modalText.includes("Audit entry #1"));
    assert.ok(modalText.includes("alice@corp.test"));
    const pres = modal.querySelectorAll("pre");
    assert.ok(pres.length === 3, "metadata + before + after rendered as JSON text");
    assert.ok(textOf(pres[0]).includes('"field": "email"'));
  });

  it("renders JSON snapshots as text, never as markup", async () => {
    globalThis.fetch = async () => jsonResponse(200, { success: true, data: envelope });
    const container = document.createElement("div");
    await renderAuditLog(container);
    container.querySelector("tbody").querySelectorAll("button")[2].click();
    const modal = document.body.querySelector(".modal");
    assert.equal(modal.querySelectorAll("img").length, 0, "no <img> parsed from metadata");
    assert.ok(textOf(modal).includes("<img src=x onerror=evil()>"), "metadata preserved as display text");
  });
});

describe("audit log route gating", () => {
  beforeEach(() => authStore.clear());

  it("allows admin and manager, denies accountant and viewer", () => {
    const route = resolveRoute("#/audit-log").route;
    assert.equal(route.path, "audit-log");
    for (const role of ["admin", "manager"]) {
      authStore.setUser({ roles: [role] });
      assert.equal(canEnter(route), true, role);
    }
    for (const role of ["accountant", "viewer"]) {
      authStore.setUser({ roles: [role] });
      assert.equal(canEnter(route), false, role);
    }
  });
});

describe("audit log i18n", () => {
  it("provides every audit string in both locales", () => {
    const auditKeys = Object.keys(en).filter((k) => k.startsWith("audit") || k === "nav.monitoring" || k === "nav.auditLog");
    for (const key of auditKeys) {
      const enVal = en[key];
      const arVal = ar[key];
      assert.ok(typeof enVal === "string" && enVal.length > 0, `en missing ${key}`);
      assert.ok(typeof arVal === "string" && arVal.length > 0, `ar missing ${key}`);
      assert.notEqual(enVal, arVal, `ar collides with en for ${key}`);
    }
  });
});