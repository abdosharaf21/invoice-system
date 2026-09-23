import { describe, it, beforeEach } from "node:test";
import assert from "node:assert/strict";
import "./helpers/dom.js";
import { authStore } from "../assets/js/auth/store.js";
import { CONFIG } from "../assets/js/config.js";
import {
  listRuns,
  getResults,
  getErrors,
  getReportSummary,
  exportResults,
  exportErrors,
} from "../assets/js/services/reconciliation.js";

// The client builds URLs as joinApiBase(CONFIG.apiBase, path) and dedupes the
// same-origin /api mount, so the origin portion is "" when apiBase is "/api".
const BASE = CONFIG.apiBase === "/api" ? "" : CONFIG.apiBase;

function envelope(data) {
  return {
    ok: true,
    status: 200,
    headers: new Map([["content-type", "application/json"]]),
    async json() { return { success: true, data }; },
    async blob() { return new Blob(["data"]); },
  };
}

function blobResponse() {
  return {
    ok: true,
    status: 200,
    headers: new Map([["content-type", "application/octet-stream"]]),
    async blob() { return new Blob(["data"]); },
  };
}

/** Install a scripted fetch that records request URLs. Returns restore. */
function recordFetch(urls) {
  const original = globalThis.fetch;
  globalThis.fetch = async (url) => {
    urls.push(String(url));
    return envelope({ runs: [], count: 0 });
  };
  return () => { globalThis.fetch = original; };
}

describe("reconciliation service query construction", () => {
  beforeEach(() => authStore.clear());

  it("sends integer pagination params when listRuns receives an options object", async () => {
    const urls = [];
    const restore = recordFetch(urls);
    try {
      await listRuns({ limit: 200, offset: 0 });
    } finally {
      restore();
    }
    assert.deepEqual(urls, [`${BASE}/api/reconciliation/runs?limit=200&offset=0`]);
  });

  it("still supports the positional listRuns(limit, offset) signature", async () => {
    const urls = [];
    const restore = recordFetch(urls);
    try {
      await listRuns(100, 0);
    } finally {
      restore();
    }
    assert.deepEqual(urls, [`${BASE}/api/reconciliation/runs?limit=100&offset=0`]);
  });

  it("defaults limit/offset when pagination values are missing or empty", async () => {
    const urls = [];
    const restore = recordFetch(urls);
    try {
      await listRuns();
      await listRuns({});
      await listRuns({ limit: undefined, offset: "" });
    } finally {
      restore();
    }
    assert.deepEqual(urls, [
      `${BASE}/api/reconciliation/runs?limit=50&offset=0`,
      `${BASE}/api/reconciliation/runs?limit=50&offset=0`,
      `${BASE}/api/reconciliation/runs?limit=50&offset=0`,
    ]);
  });

  it("defaults non-integer pagination values instead of emitting them verbatim", async () => {
    const urls = [];
    const restore = recordFetch(urls);
    try {
      await listRuns({ limit: "abc", offset: "xyz" });
    } finally {
      restore();
    }
    assert.deepEqual(urls, [`${BASE}/api/reconciliation/runs?limit=50&offset=0`]);
    assert.ok(!urls[0].includes("[object"), "never serializes objects into the query string");
  });

  it("keeps filter params separate from integer pagination on results/errors", async () => {
    const urls = [];
    const original = globalThis.fetch;
    globalThis.fetch = async (url) => {
      urls.push(String(url));
      return envelope({ items: [], page: 1, page_size: 50, total: 0, total_pages: 1 });
    };
    try {
      await getResults(9, { page: 2, page_size: 25, match_status: "mismatched", date_from: "2024-03-01" });
      await getErrors(9, { page: 1, page_size: 50, error_type: "TOTAL_AMOUNT_MISMATCH", source_type: "account" });
    } finally {
      globalThis.fetch = original;
    }
    assert.deepEqual(urls, [
      `${BASE}/api/reconciliation/runs/9/results?page=2&page_size=25&match_status=mismatched&date_from=2024-03-01`,
      `${BASE}/api/reconciliation/runs/9/errors?page=1&page_size=50&error_type=TOTAL_AMOUNT_MISMATCH&source_type=account`,
    ]);
  });

  it("keeps filter params separate from the export format", async () => {
    const urls = [];
    const original = globalThis.fetch;
    globalThis.fetch = async (url) => {
      urls.push(String(url));
      return blobResponse();
    };
    try {
      await exportResults(9, "csv", { match_status: "invalid", date_to: "2024-03-31" });
      await exportErrors(9, "xlsx", { source_type: "tax" });
    } finally {
      globalThis.fetch = original;
    }
    assert.deepEqual(urls, [
      `${BASE}/api/reconciliation/runs/9/results/export?match_status=invalid&date_to=2024-03-31&format=csv`,
      `${BASE}/api/reconciliation/runs/9/errors/export?source_type=tax&format=xlsx`,
    ]);
  });

  it("getReportSummary sends no pagination query params", async () => {
    const urls = [];
    const restore = recordFetch(urls);
    try {
      await getReportSummary(9);
    } finally {
      restore();
    }
    assert.deepEqual(urls, [`${BASE}/api/reconciliation/runs/9/summary`]);
  });
});