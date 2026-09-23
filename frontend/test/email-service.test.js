import { describe, it, beforeEach } from "node:test";
import assert from "node:assert/strict";
import "./helpers/dom.js";
import { authStore } from "../assets/js/auth/store.js";
import { CONFIG } from "../assets/js/config.js";
import {
  getEmailStatus,
  sendTestEmail,
  listRunEmailDeliveries,
  resendEmailDelivery,
} from "../assets/js/services/email.js";

// The client builds URLs as joinApiBase(CONFIG.apiBase, path) and dedupes the
// same-origin /api mount, so the origin portion is "" when apiBase is "/api".
const BASE = CONFIG.apiBase === "/api" ? "" : CONFIG.apiBase;

function jsonResponse(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Map([["content-type", "application/json"]]),
    async json() { return body; },
    async blob() { return new Blob(["data"]); },
  };
}

/** Install a scripted fetch that records { url, method, body } calls. */
function installFetch(handler) {
  const calls = [];
  const original = globalThis.fetch;
  globalThis.fetch = async (url, init = {}) => {
    calls.push({ url: String(url), method: init.method || "GET", body: init.body });
    return handler(String(url), init);
  };
  return () => { globalThis.fetch = original; return calls; };
}

const STATUS_DATA = {
  enabled: false,
  provider: null,
  host: "smtp.example.com",
  port: 587,
  from_addr: null,
  use_tls: true,
  use_ssl: false,
  workflows: [
    {
      name: "reconciliation.discrepancies",
      description: "After a reconciliation run, email a grouped summary to every taxpayer/counterparty whose invoices were affected by a discrepancy.",
    },
  ],
};

describe("email service", () => {
  beforeEach(() => {
    authStore.clear();
    authStore.setTokens({ access: "tok" });
  });

  it("GETs email status and returns the unwrapped payload", async () => {
    const stop = installFetch((url, init) => {
      assert.equal(url, `${BASE}/api/email/status`);
      assert.equal(init.method, "GET");
      assert.equal(init.headers.Authorization, "Bearer tok");
      return jsonResponse(200, { success: true, data: STATUS_DATA });
    });
    try {
      const data = await getEmailStatus();
      assert.equal(data.enabled, false);
      assert.deepEqual(
        data.workflows.map((e) => e.name),
        ["reconciliation.discrepancies"],
      );
    } finally {
      stop();
    }
  });

  it("POSTs the test recipient to /api/email/test", async () => {
    const stop = installFetch((url, init) => {
      assert.equal(url, `${BASE}/api/email/test`);
      assert.equal(init.method, "POST");
      assert.deepEqual(JSON.parse(init.body), { to: "admin@example.com" });
      return jsonResponse(200, {
        success: true,
        message: "Test email sent",
        data: { delivered: true, to: "admin@example.com", request_id: "req-123" },
      });
    });
    try {
      const outcome = await sendTestEmail("admin@example.com");
      assert.equal(outcome.delivered, true);
      assert.equal(outcome.request_id, "req-123");
    } finally {
      stop();
    }
  });

  it("GETs the deliveries for a run", async () => {
    const stop = installFetch((url, init) => {
      assert.equal(url, `${BASE}/api/reconciliation/runs/42/email-deliveries`);
      assert.equal(init.method, "GET");
      assert.equal(init.headers.Authorization, "Bearer tok");
      return jsonResponse(200, {
        success: true,
        data: { deliveries: [{ id: 7, status: "sent" }], count: 1 },
      });
    });
    try {
      const data = await listRunEmailDeliveries(42);
      assert.equal(data.count, 1);
      assert.equal(data.deliveries[0].id, 7);
    } finally {
      stop();
    }
  });

  it("POSTs a resend for a run delivery", async () => {
    const stop = installFetch((url, init) => {
      assert.equal(url, `${BASE}/api/reconciliation/runs/42/email-deliveries/7/resend`);
      assert.equal(init.method, "POST");
      return jsonResponse(200, {
        success: true,
        message: "Email resent",
        data: { delivery: { id: 7, status: "sent" } },
      });
    });
    try {
      const data = await resendEmailDelivery(42, 7);
      assert.equal(data.delivery.status, "sent");
    } finally {
      stop();
    }
  });

  it("propagates the disabled-email error from the backend", async () => {
    const stop = installFetch(() =>
      jsonResponse(400, { success: false, message: "Email is not enabled" }));
    try {
      await assert.rejects(
        () => sendTestEmail("admin@example.com"),
        (err) => err.message.includes("Email is not enabled"),
      );
    } finally {
      stop();
    }
  });

  it("propagates invalid-recipient validation errors", async () => {
    const stop = installFetch(() =>
      jsonResponse(400, { success: false, message: "Invalid email address: not-an-email" }));
    try {
      await assert.rejects(
        () => sendTestEmail("not-an-email"),
        (err) => err.message.includes("Invalid email address"),
      );
    } finally {
      stop();
    }
  });

  it("propagates SMTP delivery failures as an ApiError", async () => {
    const stop = installFetch(() =>
      jsonResponse(502, { success: false, message: "Email test failed; check the server logs" }));
    try {
      await assert.rejects(
        () => sendTestEmail("admin@example.com"),
        (err) => err.message.includes("Email test failed") && err.status === 502,
      );
    } finally {
      stop();
    }
  });

  it("reflects the admin-only gate as a 403 ApiError on status", async () => {
    const stop = installFetch(() =>
      jsonResponse(403, { success: false, message: "Access denied. Admin privileges required." }));
    try {
      await assert.rejects(
        () => getEmailStatus(),
        (err) => err.message.includes("Admin privileges required") && err.status === 403,
      );
    } finally {
      stop();
    }
  });
});