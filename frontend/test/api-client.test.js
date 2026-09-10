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
});