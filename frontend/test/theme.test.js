import { describe, it, beforeEach } from "node:test";
import assert from "node:assert/strict";
import "./helpers/dom.js";
import { CONFIG } from "../assets/js/config.js";
import { authStore } from "../assets/js/auth/store.js";
import { loadAppSettings, loadUserPrefs, invalidateSettings } from "../assets/js/settings/store.js";
import {
  LIGHT,
  DARK,
  SYSTEM,
  normalizeTheme,
  effectiveThemeFor,
  getThemePreference,
  getEffectiveTheme,
  applyTheme,
  setThemePreference,
  syncThemeFromSettings,
  initializeTheme,
  destroyTheme,
} from "../assets/js/theme.js";

const BASE = CONFIG.apiBase;

function jsonResponse(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Map([["content-type", "application/json"]]),
    async json() { return body; },
    async blob() { return new Blob(["data"]); },
  };
}

function installFetch(handler) {
  const original = globalThis.fetch;
  globalThis.fetch = async (url, init = {}) => handler(String(url), init);
  return () => { globalThis.fetch = original; };
}

/** Mock matchMedia exposing its change listeners for manual dispatch. */
function installMatchMedia(matches) {
  const listeners = [];
  let current = matches;
  const mql = {
    get matches() { return current; },
    media: "(prefers-color-scheme: dark)",
    addEventListener(type, fn) { if (type === "change") listeners.push(fn); },
    removeEventListener(type, fn) {
      const i = listeners.indexOf(fn);
      if (i >= 0) listeners.splice(i, 1);
    },
    setMatches(v) { current = v; },
    listeners,
  };
  window.matchMedia = () => mql;
  return mql;
}

beforeEach(() => {
  authStore.clear();
  localStorage.clear();
  destroyTheme();
  delete window.matchMedia;
  globalThis.fetch = undefined;
});

describe("theme preference normalization", () => {
  it("accepts the three canonical modes", () => {
    assert.equal(normalizeTheme(LIGHT), LIGHT);
    assert.equal(normalizeTheme(DARK), DARK);
    assert.equal(normalizeTheme(SYSTEM), SYSTEM);
  });

  it("collapses unknown values to the system fallback", () => {
    assert.equal(normalizeTheme("neon"), SYSTEM);
    assert.equal(normalizeTheme("LIGHT"), SYSTEM);
    assert.equal(normalizeTheme(""), SYSTEM);
  });

  it("collapses null and undefined to the fallback", () => {
    assert.equal(normalizeTheme(null), SYSTEM);
    assert.equal(normalizeTheme(undefined), SYSTEM);
    assert.equal(normalizeTheme(42), SYSTEM);
  });
});

describe("theme effective resolution", () => {
  it("explicit light is light regardless of OS", () => {
    assert.equal(effectiveThemeFor(LIGHT, true), LIGHT);
    assert.equal(effectiveThemeFor(LIGHT, false), LIGHT);
  });

  it("explicit dark is dark regardless of OS", () => {
    assert.equal(effectiveThemeFor(DARK, true), DARK);
    assert.equal(effectiveThemeFor(DARK, false), DARK);
  });

  it("system follows the operating system", () => {
    assert.equal(effectiveThemeFor(SYSTEM, false), LIGHT);
    assert.equal(effectiveThemeFor(SYSTEM, true), DARK);
    // getSystemTheme() supplies the literal "dark"/"light" strings.
    assert.equal(effectiveThemeFor(SYSTEM, DARK), DARK);
    assert.equal(effectiveThemeFor(SYSTEM, LIGHT), LIGHT);
  });

  it("invalid preferences resolve through the system fallback", () => {
    assert.equal(effectiveThemeFor("bogus", true), DARK);
    assert.equal(effectiveThemeFor(null, false), LIGHT);
  });
});

describe("theme application (DOM contract)", () => {
  it("writes the effective theme to <html data-theme>", () => {
    setThemePreference(LIGHT);
    assert.equal(document.documentElement.dataset.theme, LIGHT);
    setThemePreference(DARK);
    assert.equal(document.documentElement.dataset.theme, DARK);
  });

  it("never leaves data-theme=system; system resolves to light/dark", () => {
    const mql = installMatchMedia(true);
    setThemePreference(SYSTEM);
    assert.equal(document.documentElement.dataset.theme, DARK);

    mql.setMatches(false);
    applyTheme();
    assert.equal(document.documentElement.dataset.theme, LIGHT);
    assert.notEqual(document.documentElement.dataset.theme, SYSTEM);
  });

  it("getEffectiveTheme reflects the OS for system mode", () => {
    const mql = installMatchMedia(true);
    setThemePreference(SYSTEM);
    assert.equal(getEffectiveTheme(), DARK);
    mql.setMatches(false);
    assert.equal(getEffectiveTheme(), LIGHT);
    mql.setMatches(true);
    assert.equal(getEffectiveTheme(), DARK);
  });
});

describe("theme persistence", () => {
  it("persists explicit choices to localStorage", () => {
    setThemePreference(DARK);
    assert.equal(localStorage.getItem("eis:theme"), DARK);
    setThemePreference(SYSTEM);
    assert.equal(localStorage.getItem("eis:theme"), SYSTEM);
  });

  it("survives the module lifecycle (reads from storage, not memory)", () => {
    setThemePreference(DARK);
    installMatchMedia(false); // OS light must NOT win over the explicit choice
    assert.equal(getThemePreference(), DARK);
    assert.equal(getEffectiveTheme(), DARK);
    assert.equal(document.documentElement.dataset.theme, DARK);
  });

  it("ignores an invalid stored preference (falls back, never crashes)", () => {
    localStorage.setItem("eis:theme", "not-a-theme");
    assert.equal(getThemePreference(), SYSTEM);
    applyTheme();
    assert.equal(document.documentElement.dataset.theme, LIGHT);
    assert.equal(SYSTEM, "system", "fallback is system");
  });
});

describe("theme OS listener", () => {
  it("reacts to OS changes in system mode", () => {
    const mql = installMatchMedia(false);
    setThemePreference(SYSTEM);
    initializeTheme();
    assert.equal(document.documentElement.dataset.theme, LIGHT);

    mql.setMatches(true);
    mql.listeners.forEach((fn) => fn());
    assert.equal(document.documentElement.dataset.theme, DARK);
  });

  it("does not react to OS changes while explicit light is selected", () => {
    const mql = installMatchMedia(false);
    setThemePreference(LIGHT);
    initializeTheme();
    assert.equal(document.documentElement.dataset.theme, LIGHT);

    mql.setMatches(true);
    mql.listeners.forEach((fn) => fn());
    assert.equal(document.documentElement.dataset.theme, LIGHT);
  });

  it("does not react to OS changes while explicit dark is selected", () => {
    const mql = installMatchMedia(true);
    setThemePreference(DARK);
    initializeTheme();
    assert.equal(document.documentElement.dataset.theme, DARK);

    mql.setMatches(false);
    mql.listeners.forEach((fn) => fn());
    assert.equal(document.documentElement.dataset.theme, DARK);
  });

  it("does not register duplicate OS listeners across initializations", () => {
    const mql = installMatchMedia(false);
    initializeTheme();
    initializeTheme();
    initializeTheme();
    assert.equal(mql.listeners.length, 1, "listener must be attached exactly once");
  });

  it("removes the listener on destroyTheme and can re-bind", () => {
    const mql = installMatchMedia(false);
    initializeTheme();
    assert.equal(mql.listeners.length, 1);
    destroyTheme();
    assert.equal(mql.listeners.length, 0);
    initializeTheme();
    assert.equal(mql.listeners.length, 1);
  });
});

describe("theme settings integration", () => {
  it("app default theme drives the effective theme when no explicit choice exists", async () => {
    installMatchMedia(false);
    const stop = installFetch((url) => {
      if (url.endsWith("/settings/application")) {
        return jsonResponse(200, { success: true, data: { default_theme: DARK } });
      }
      if (url.endsWith("/settings/user")) return jsonResponse(200, { success: true, data: {} });
      return jsonResponse(404, { success: false, message: "unexpected " + url });
    });
    try {
      await loadAppSettings();
      await loadUserPrefs();
      syncThemeFromSettings();
      assert.equal(document.documentElement.dataset.theme, DARK);
    } finally {
      stop();
    }
  });

  it("changing the canonical app setting updates the theme without a reload", async () => {
    installMatchMedia(false);
    let appTheme = DARK;
    const stop = installFetch((url) => {
      if (url.endsWith("/settings/application")) {
        return jsonResponse(200, { success: true, data: { default_theme: appTheme } });
      }
      if (url.endsWith("/settings/user")) return jsonResponse(200, { success: true, data: {} });
      return jsonResponse(404, { success: false, message: "unexpected " + url });
    });
    try {
      await loadAppSettings();
      syncThemeFromSettings();
      assert.equal(document.documentElement.dataset.theme, DARK);

      appTheme = LIGHT;
      invalidateSettings();
      await loadAppSettings(true);
      syncThemeFromSettings();
      assert.equal(document.documentElement.dataset.theme, LIGHT);
    } finally {
      stop();
    }
  });

  it("a backend user preference overrides the application default", async () => {
    installMatchMedia(false);
    const stop = installFetch((url) => {
      if (url.endsWith("/settings/application")) {
        return jsonResponse(200, { success: true, data: { default_theme: DARK } });
      }
      if (url.endsWith("/settings/user")) {
        return jsonResponse(200, { success: true, data: { theme: LIGHT } });
      }
      return jsonResponse(404, { success: false, message: "unexpected " + url });
    });
    try {
      await loadAppSettings();
      await loadUserPrefs();
      syncThemeFromSettings();
      assert.equal(document.documentElement.dataset.theme, LIGHT);
    } finally {
      stop();
    }
  });

  it("an explicit local choice outranks both backend sources", async () => {
    installMatchMedia(false);
    setThemePreference(DARK);
    const stop = installFetch((url) => {
      if (url.endsWith("/settings/application")) {
        return jsonResponse(200, { success: true, data: { default_theme: LIGHT } });
      }
      if (url.endsWith("/settings/user")) {
        return jsonResponse(200, { success: true, data: { theme: LIGHT } });
      }
      return jsonResponse(404, { success: false, message: "unexpected " + url });
    });
    try {
      await loadAppSettings();
      await loadUserPrefs();
      syncThemeFromSettings();
      assert.equal(document.documentElement.dataset.theme, DARK);
    } finally {
      stop();
    }
  });
});