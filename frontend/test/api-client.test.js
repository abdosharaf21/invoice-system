import { describe, it, beforeEach } from "node:test";
import assert from "node:assert/strict";
import "./helpers/dom.js";
import { authStore } from "../assets/js/auth/store.js";
import { api, ApiError, _internal, setAuthFailureHandler } from "../assets/js/api/client.js";

function jsonResponse(status, body, headers = {}) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Map(Object.entries({ "content-type": "application/json", ...headers })),
    async json() { return body; },
    async blob() { return new Blob(["data"]); },
  };
}

/** Install a scripted fetch. */
function installFetch(handler) {
  const calls = [];
  const original = globalThis.fetch;
  globalThis.fetch = async (url, init = {}) => {
    calls.push({ url: String(url), init, body: init.body });
    return handler(String(url), init, calls.length - 1);
  };
  return () => { globalThis.fetch = original; return calls; };
}

describe("api client", () => {
  beforeEach(() => {
    authStore.clear();
    setAuthFailureHandler(null);
  });

  it("normalizes backend error envelopes into ApiError", async () => {
    const stop = installFetch(() =>
      jsonResponse(401, { success: false, message: "Bad credentials", code: "INVALID_CREDENTIALS" }));
    try {
      await assert.rejects(
        () => api.post("/api/auth/login", { email: "a@b.co", password: "x" }),
        (err) => err instanceof ApiError && err.status === 401 && err.message === "Bad credentials",
      );
    } finally {
      const calls = stop();
      assert.equal(calls.length, 1); // no refresh attempted without a token
    }
  });

  it("surfaces the X-Request-Id correlation header on API errors", async () => {
    const stop = installFetch(() =>
      jsonResponse(422, {
        success: false,
        message: "Invalid file",
        status: 422,
        code: "BAD_REQUEST",
        errors: ["row 1: missing invoice number"],
      }, { "x-request-id": "req-abc123" }));
    try {
      await assert.rejects(
        () => api.upload("/api/imports", new FormData()),
        (err) => err instanceof ApiError
          && err.status === 422
          && err.details && err.details.request_id === "req-abc123",
      );
    } finally {
      const calls = stop();
      assert.equal(calls.length, 1);
    }
  });

  it("omits request_id from ApiError details when the header is absent", async () => {
    const stop = installFetch(() =>
      jsonResponse(400, { success: false, message: "Bad request", status: 400, code: "BAD_REQUEST" }));
    try {
      await assert.rejects(
        () => api.post("/api/auth/login", { email: "a@b.co", password: "x" }),
        (err) => err instanceof ApiError && JSON.stringify(err.details) === "null",
      );
    } finally {
      const calls = stop();
      assert.equal(calls.length, 1);
    }
  });

  it("sends login as POST to exactly /api/auth/login (no /api double prefix)", async () => {
    const stop = installFetch(() =>
      jsonResponse(400, { success: false, message: "Bad creds", status: 400, code: "BAD_REQUEST" }));
    try {
      await assert.rejects(() => api.post("/api/auth/login", { email: "a@b.co", password: "x" }));
    } finally {
      const calls = stop();
      assert.equal(calls.length, 1);
      assert.equal(calls[0].url, "/api/auth/login", "same-origin base must not be prefixed twice");
      assert.equal(calls[0].init.method, "POST");
      assert.deepEqual(JSON.parse(calls[0].body), { email: "a@b.co", password: "x" });
    }
  });

  it("preserves the real 405 METHOD_NOT_ALLOWED envelope", async () => {
    const stop = installFetch(() =>
      jsonResponse(405, { success: false, message: "Method not allowed", status: 405, code: "METHOD_NOT_ALLOWED" }));
    try {
      await assert.rejects(
        () => api.post("/api/auth/login", { email: "a@b.co", password: "x" }),
        (err) => err instanceof ApiError
          && err.status === 405
          && err.code === "METHOD_NOT_ALLOWED"
          && err.message === "Method not allowed",
      );
    } finally {
      const calls = stop();
      assert.equal(calls.length, 1);
    }
  });

  it("joinApiBase dedupes the same-origin /api mount", () => {
    const { joinApiBase } = _internal();
    assert.equal(joinApiBase("/api", "/api/auth/login"), "/api/auth/login");
    assert.equal(joinApiBase("/api", "/api"), "/api");
    assert.equal(joinApiBase("/api", "/auth/login"), "/api/auth/login");
    assert.equal(joinApiBase("http://localhost:5001", "/api/auth/login"), "http://localhost:5001/api/auth/login");
    assert.equal(joinApiBase("http://localhost:5001", "/auth/login"), "http://localhost:5001/auth/login");
    assert.equal(joinApiBase("http://localhost:5001/", "/api/health"), "http://localhost:5001/api/health");
    assert.equal(joinApiBase("", "/api/auth/login"), "/api/auth/login");
    assert.equal(joinApiBase(null, "/api/auth/login"), "/api/auth/login");
  });

  it("builds query strings deterministically and skips blanks", () => {
    const { buildPath } = _internal();
    assert.equal(buildPath("/runs", { limit: 50, offset: 0 }), "/runs?limit=50&offset=0");
    assert.equal(buildPath("/runs", { q: undefined, page: null, skip: "" }), "/runs");
    assert.equal(buildPath("/runs", { q: "a b&c" }), "/runs?q=a+b%26c");
  });

  it("refreshes an expired access token and retries once", async () => {
    authStore.setTokens({ access: "old", refresh: "refresh-t" });
    let fooCalls = 0;
    const stop = installFetch((url, init) => {
      if (url.endsWith("/api/auth/refresh")) {
        return jsonResponse(200, { success: true, data: { access_token: "new-access" } });
      }
      if (url.endsWith("/api/foo")) {
        fooCalls += 1;
        if (fooCalls === 1) return jsonResponse(401, { success: false, message: "Token expired" });
        const auth = init.headers && init.headers.Authorization;
        return jsonResponse(200, { success: true, data: { token: auth, tasks: [1, 2] } });
      }
      return jsonResponse(404, { success: false, message: "Not found" });
    });
    try {
      const data = await api.get("/api/foo");
      assert.deepEqual(data.tasks, [1, 2]);
      assert.equal(data.token, "Bearer new-access");
      assert.ok(authStore.getTokens().access === "new-access", "access token swapped");
    } finally {
      const calls = stop();
      assert.equal(fooCalls, 2, "retried the original request");
      assert.equal(calls.filter((c) => c.url.endsWith("/api/auth/refresh")).length, 1);
    }
  });

  it("invokes the auth-failure hook when refresh fails", async () => {
    authStore.setTokens({ access: "old", refresh: "dead" });
    let failed = 0;
    setAuthFailureHandler(() => { failed += 1; });
    const stop = installFetch((url) => {
      if (url.endsWith("/api/auth/refresh")) {
        return jsonResponse(401, { success: false, message: "Refresh token expired" });
      }
      return jsonResponse(401, { success: false, message: "Token expired" });
    });
    try {
      await assert.rejects(() => api.get("/api/data"), (err) => err instanceof ApiError && err.status === 401);
    } finally {
      stop();
      assert.ok(failed >= 1, "auth failure handler ran");
    }
  });

  it("returns empty data for empty success envelopes", async () => {
    const stop = installFetch(() => jsonResponse(204, { success: true }));
    try {
      const out = await api.post("/api/users", {});
      assert.deepEqual(out, {});
    } finally {
      stop();
    }
  });

  it("fires the auth-failure hook when a JSON 401 survives a successful refresh", async () => {
    authStore.setTokens({ access: "old", refresh: "alive" });
    let failed = 0;
    let dataCalls = 0;
    setAuthFailureHandler(() => { failed += 1; });
    const stop = installFetch((url) => {
      if (url.endsWith("/api/auth/refresh")) {
        return jsonResponse(200, { success: true, data: { access_token: "fresh" } });
      }
      if (url.endsWith("/api/data")) {
        dataCalls += 1;
        return jsonResponse(401, { success: false, message: "Session revoked" });
      }
      return jsonResponse(404, { success: false, message: "Not found" });
    });
    try {
      await assert.rejects(() => api.get("/api/data"), (err) => err instanceof ApiError && err.status === 401);
    } finally {
      stop();
      assert.equal(dataCalls, 2, "the request was retried after a successful refresh");
      assert.equal(failed, 1, "auth-failure handler fired exactly once");
    }
  });

  it("does not fire the auth-failure hook for a JSON 401 on a brand-new session", async () => {
    let failed = 0;
    setAuthFailureHandler(() => { failed += 1; });
    const stop = installFetch(() =>
      jsonResponse(401, { success: false, message: "Bad credentials", code: "INVALID_CREDENTIALS" }));
    try {
      await assert.rejects(() => api.post("/api/auth/login", { email: "a@b.co", password: "x" }));
    } finally {
      stop();
      assert.equal(failed, 0, "login failures are not session-expiry events");
    }
  });

  it("download() retries once with a refreshed token", async () => {
    authStore.setTokens({ access: "old", refresh: "rt" });
    let exportCalls = 0;
    const stop = installFetch((url, init) => {
      if (url.endsWith("/api/auth/refresh")) {
        return jsonResponse(200, { success: true, data: { access_token: "new-access" } });
      }
      if (url.includes("/results/export")) {
        exportCalls += 1;
        if (exportCalls === 1) return jsonResponse(401, { success: false, message: "Token expired" });
        return {
          ok: true,
          status: 200,
          headers: new Map([["content-disposition", 'attachment; filename="report.csv"']]),
          async json() { return {}; },
          async blob() { return new Blob(["x"]); },
        };
      }
      return jsonResponse(404, { success: false, message: "Not found" });
    });
    try {
      const name = await api.download("/api/report/results/export?format=csv", {});
      assert.equal(name, "report.csv");
      assert.equal(exportCalls, 2, "the export was retried after refresh");
      assert.equal(authStore.getTokens().access, "new-access");
    } finally {
      stop();
    }
  });

  it("download() fires the auth-failure hook when a JSON 401 survives refresh", async () => {
    authStore.setTokens({ access: "old", refresh: "rt" });
    let failed = 0;
    let exportCalls = 0;
    setAuthFailureHandler(() => { failed += 1; });
    const stop = installFetch((url) => {
      if (url.endsWith("/api/auth/refresh")) {
        return jsonResponse(200, { success: true, data: { access_token: "new-access" } });
      }
      if (url.includes("/results/export")) {
        exportCalls += 1;
        return jsonResponse(401, { success: false, message: "Session revoked" });
      }
      return jsonResponse(404, { success: false, message: "Not found" });
    });
    try {
      await assert.rejects(
        () => api.download("/api/report/results/export?format=csv", {}),
        (err) => err instanceof ApiError && err.status === 401,
      );
    } finally {
      stop();
      assert.equal(exportCalls, 2);
      assert.equal(failed, 1, "auth-failure handler fired exactly once");
    }
  });

  it("download() does not fire the auth-failure hook for a plain export error", async () => {
    authStore.setTokens({ access: "a", refresh: "rt" });
    let failed = 0;
    setAuthFailureHandler(() => { failed += 1; });
    const stop = installFetch((url) => {
      if (url.includes("/results/export")) {
        return jsonResponse(500, { success: false, message: "Backend exploded" });
      }
      return jsonResponse(404, { success: false, message: "Not found" });
    });
    try {
      await assert.rejects(() => api.download("/api/report/results/export?format=csv", {}), (err) => err.status === 500);
    } finally {
      stop();
      assert.equal(failed, 0);
    }
  });

  it("unwraps data array directly from list endpoints", async () => {
    const users = [
      { id: 1, username: "admin1", company_id: 22 },
      { id: 2, username: "viewer1", company_id: 22 },
    ];
    const stop = installFetch(() =>
      jsonResponse(200, { success: true, data: users, message: "ok" }));
    try {
      const res = await api.get("/api/users/");
      assert.ok(Array.isArray(res), "api.get must return the unwrapped array");
      assert.equal(res.length, 2);
      assert.equal(res[0].username, "admin1");
    } finally {
      stop();
    }
  });

  it("returns empty array when list endpoint has empty data", async () => {
    const stop = installFetch(() =>
      jsonResponse(200, { success: true, data: [], message: "ok" }));
    try {
      const res = await api.get("/api/users/");
      assert.ok(Array.isArray(res), "returns an array even when empty");
      assert.equal(res.length, 0);
    } finally {
      stop();
    }
  });
});