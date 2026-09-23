/**
 * Tests for the API base URL resolution (frontend production serving).
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import "./helpers/dom.js";

/**
 * config.js computes CONFIG at import time, and Node caches modules, so each
 * scenario is tested against a fresh module instance loaded with a cache
 * busting query param.
 */
async function loadConfig() {
  return import(`../assets/js/config.js?t=${Date.now()}-${Math.random()}`);
}

describe("config apiBase resolution", () => {
  it("defaults to http://localhost:5001 on localhost (dev)", async () => {
    window.location = { search: "", hostname: "localhost" };
    const { CONFIG } = await loadConfig();
    assert.equal(CONFIG.apiBase, "http://localhost:5001");
  });

  it("defaults to same-origin /api on a production host", async () => {
    window.location = { search: "", hostname: "invoice.example.com" };
    const { CONFIG } = await loadConfig();
    assert.equal(CONFIG.apiBase, "/api");
  });

  it("treats 127.0.0.1 as localhost", async () => {
    window.location = { search: "", hostname: "127.0.0.1" };
    const { CONFIG } = await loadConfig();
    assert.equal(CONFIG.apiBase, "http://localhost:5001");
  });

  it("treats 0.0.0.0 as localhost (static server on all interfaces)", async () => {
    window.location = { search: "", hostname: "0.0.0.0" };
    const { CONFIG } = await loadConfig();
    assert.equal(CONFIG.apiBase, "http://localhost:5001");
  });

  it("honours window.__EIS_API_BASE__ regardless of host", async () => {
    window.location = { search: "", hostname: "invoice.example.com" };
    globalThis.__EIS_API_BASE__ = "https://api.invoice.example.com/";
    try {
      const { CONFIG } = await loadConfig();
      assert.equal(CONFIG.apiBase, "https://api.invoice.example.com");
    } finally {
      delete globalThis.__EIS_API_BASE__;
    }
  });

  it("honours the ?api= query override over every other source", async () => {
    window.location = {
      search: "?api=http://10.0.0.5:5001",
      hostname: "invoice.example.com",
    };
    const { CONFIG } = await loadConfig();
    assert.equal(CONFIG.apiBase, "http://10.0.0.5:5001");
  });

  it("strips trailing slashes from overrides", async () => {
    window.location = { search: "?api=/api/", hostname: "localhost" };
    const { CONFIG } = await loadConfig();
    assert.equal(CONFIG.apiBase, "/api");
  });
});