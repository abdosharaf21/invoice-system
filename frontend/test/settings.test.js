import { describe, it, beforeEach } from "node:test";
import assert from "node:assert/strict";
import "./helpers/dom.js";
import { authStore } from "../assets/js/auth/store.js";
import { CONFIG } from "../assets/js/config.js";
import { renderSettings, resetSettingsView } from "../assets/js/pages/settings.js";
import {
  getApplicationSettings,
  updateApplicationSettings,
  getCompanySettings,
  updateCompanySettings,
  getUserSettings,
  updateUserSettings,
} from "../assets/js/services/settings.js";
import {
  loadAppSettings,
  loadCompanySettings,
  getAppName,
  getAppSubtitle,
  getCompanyName,
  invalidateSettings,
} from "../assets/js/settings/store.js";
import { applyAppLocale } from "../assets/js/i18n/index.js";

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

const APP_DATA = {
  application_name: "E-Invoice & Reconciliation",
  application_subtitle: "Tax authority compliance",
  default_language: "en",
  default_theme: "light",
  date_format: "YYYY-MM-DD",
  number_format: "#,##0.00",
  timezone: "UTC",
  pagination_size: 25,
};

const COMPANY_DATA = {
  id: 22,
  name: "Frontend Test Company",
  tax_registration_number: "FRT-TEMP-001",
  email: "admin@test.local",
  phone: "+201000000000",
  address: "Cairo",
  website: null,
  default_currency: "EGP",
  default_tax_rate: 0,
  fiscal_year_start: "01-01",
};

const USER_DATA = {
  language: "en",
  theme: "light",
  date_format: "YYYY-MM-DD",
  number_format: "#,##0.00",
  timezone: "UTC",
  avatar_path: null,
  pagination_size: 25,
};

const EMAIL_STATUS_DATA = {
  enabled: false,
  provider: null,
  host: "",
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

/** Flatten the stub DOM tree into its visible text. */
function treeText(node) {
  let out = "";
  const walk = (n) => {
    if (!n) return;
    if (n.nodeType === 3) {
      out += n.textContent || "";
      return;
    }
    for (const c of n.childNodes || []) walk(c);
  };
  walk(node);
  return out;
}

describe("settings service", () => {
  beforeEach(() => {
    authStore.clear();
    authStore.setTokens({ access: "tok" });
  });

  it("GETs application settings and returns the unwrapped payload", async () => {
    const stop = installFetch((url) => {
      assert.equal(url, `${BASE}/api/settings/application`);
      return jsonResponse(200, { success: true, data: APP_DATA });
    });
    try {
      const data = await getApplicationSettings();
      assert.equal(data.application_name, "E-Invoice & Reconciliation");
    } finally {
      stop();
    }
  });

  it("PUTs application settings with a JSON body", async () => {
    const stop = installFetch((url, init) => {
      assert.equal(url, `${BASE}/api/settings/application`);
      assert.equal(init.method, "PUT");
      assert.equal(init.headers.Authorization, "Bearer tok");
      return jsonResponse(200, { success: true, data: { ...APP_DATA, default_theme: "dark" } });
    });
    try {
      const data = await updateApplicationSettings({ default_theme: "dark" });
      assert.equal(data.default_theme, "dark");
    } finally {
      stop();
    }
  });

  it("GETs company settings", async () => {
    const stop = installFetch((url) => {
      assert.equal(url, `${BASE}/api/settings/company`);
      return jsonResponse(200, { success: true, data: COMPANY_DATA });
    });
    try {
      const data = await getCompanySettings();
      assert.equal(data.name, "Frontend Test Company");
    } finally {
      stop();
    }
  });

  it("PUTs company settings", async () => {
    const stop = installFetch((url, init) => {
      assert.equal(url, `${BASE}/api/settings/company`);
      assert.equal(init.method, "PUT");
      const body = JSON.parse(init.body);
      assert.equal(body.website, "https://acme.com");
      return jsonResponse(200, { success: true, data: { ...COMPANY_DATA, website: "https://acme.com" } });
    });
    try {
      const data = await updateCompanySettings({ website: "https://acme.com" });
      assert.equal(data.website, "https://acme.com");
    } finally {
      stop();
    }
  });

  it("GETs current user settings", async () => {
    const stop = installFetch((url) => {
      assert.equal(url, `${BASE}/api/settings/user`);
      return jsonResponse(200, { success: true, data: USER_DATA });
    });
    try {
      const data = await getUserSettings();
      assert.equal(data.pagination_size, 25);
    } finally {
      stop();
    }
  });

  it("PUTs current user settings to /api/settings/user", async () => {
    const stop = installFetch((url, init) => {
      assert.equal(url, `${BASE}/api/settings/user`);
      assert.equal(init.method, "PUT");
      return jsonResponse(200, { success: true, data: { ...USER_DATA, theme: "dark" } });
    });
    try {
      const data = await updateUserSettings({ theme: "dark" });
      assert.equal(data.theme, "dark");
    } finally {
      stop();
    }
  });

  it("propagates backend validation errors as ApiError", async () => {
    const stop = installFetch(() =>
      jsonResponse(400, { success: false, message: "Unsupported theme. Must be one of: light, dark" }));
    try {
      await assert.rejects(
        () => updateUserSettings({ theme: "neon" }),
        (err) => err.message.includes("Unsupported theme"),
      );
    } finally {
      stop();
    }
  });
});

describe("settings store caching", () => {
  beforeEach(() => invalidateSettings());

  it("falls back to defaults before settings load", () => {
    assert.equal(getAppName(), "E-Invoice & Reconciliation");
    assert.equal(getAppSubtitle(), "Tax authority compliance");
    assert.equal(getCompanyName(), null);
  });

  it("caches application settings after a single fetch", async () => {
    let hits = 0;
    const stop = installFetch((url) => {
      hits += 1;
      assert.equal(url, `${BASE}/api/settings/application`);
      return jsonResponse(200, { success: true, data: APP_DATA });
    });
    try {
      await loadAppSettings();
      await loadAppSettings();
      assert.equal(hits, 1, "second load must be served from cache");
      assert.equal(getAppName(), "E-Invoice & Reconciliation");
    } finally {
      stop();
    }
  });

  it("renders the fetched application and company names", async () => {
    const stop = installFetch((url) => {
      if (url.endsWith("/application")) {
        return jsonResponse(200, { success: true, data: { ...APP_DATA, application_name: "Acme Suite" } });
      }
      if (url.endsWith("/company")) {
        return jsonResponse(200, { success: true, data: { ...COMPANY_DATA, name: "Acme Ltd" } });
      }
      return jsonResponse(404, { success: false, message: "Not found" });
    });
    try {
      await loadAppSettings();
      await loadCompanySettings();
      assert.equal(getAppName(), "Acme Suite");
      assert.equal(getCompanyName(), "Acme Ltd");
    } finally {
      stop();
    }
  });

  it("keeps cached values when a force refresh fails", async () => {
    let hits = 0;
    const stop = installFetch((url) => {
      hits += 1;
      if (hits === 1) return jsonResponse(200, { success: true, data: APP_DATA });
      return jsonResponse(500, { success: false, message: "boom" });
    });
    try {
      await loadAppSettings();
      await loadAppSettings(true);
      assert.equal(getAppName(), "E-Invoice & Reconciliation");
      assert.ok(hits >= 2);
    } finally {
      stop();
    }
  });
});

describe("settings page rendering (regression)", () => {
  beforeEach(async () => {
    authStore.clear();
    authStore.setTokens({ access: "tok" });
    resetSettingsView();
    invalidateSettings();
    globalThis.localStorage.clear();
    // The locale persists across tests (an earlier per-test run may save
    // Arabic); reset the dictionary, <html lang/dir> and the device-persisted
    // choice so every test renders from a fresh English/LTR baseline.
    await applyAppLocale("en");
    document.body.childNodes = [];
    // toast() caches its stack element via getElementById; point it at the
    // stub body so the save toast can be observed and asserted.
    document.getElementById = () => document.body;
  });

  const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

  /**
   * Navigate to a settings sub-route the way the hash router does: assert the
   * nav anchor points at #/settings/<id>, then re-render the page with the
   * route id as params (mirrors app.js handleRoute calling renderSettings).
   * Returns the anchor element so tests can inspect its a11y attributes.
   */
  async function clickNav(container, label) {
    const items = container.querySelectorAll(".settings-nav__item");
    const link = items.find((b) => treeText(b).trim() === label);
    assert.ok(link, `nav item "${label}" is present`);
    const id = link.dataset && link.dataset.section;
    assert.ok(id, `nav item "${label}" carries a route id (data-section)`);
    assert.equal(link.getAttribute("href"), `#/settings/${id}`,
      `nav item "${label}" links to its sub-route`);
    await renderSettings(container, [id]);
    await flush();
    await flush();
    const active = container.querySelectorAll(".settings-nav__item")
      .find((b) => b.classList.contains("is-active"));
    assert.ok(active && active.dataset && active.dataset.section === id,
      `"${label}" is the active section after navigating`);
    assert.equal(active.getAttribute("aria-current"), "page",
      "the active nav item declares aria-current=page");
    return active;
  }

  function navLabels(container) {
    return container
      .querySelectorAll(".settings-nav__item")
      .map((b) => treeText(b).trim());
  }

  /**
   * Stand in for app.js's shell wiring: register an `eis:localechange`
   * listener on `window` (the same target applyAppLocale dispatches to) that
   * re-renders the settings sub-route, exactly like the app-shell rebuild.
   * Returns a counter the tests use to prove the event fires once and only
   * once (no silent-swallow, no duplicate, no loop).
   */
  function installLocaleRebuild(container) {
    const listeners = {};
    const originals = {
      add: globalThis.addEventListener,
      remove: globalThis.removeEventListener,
      dispatch: globalThis.dispatchEvent,
    };
    let rebuilds = 0;
    globalThis.addEventListener = (type, fn) => { (listeners[type] ||= []).push(fn); };
    globalThis.removeEventListener = (type, fn) => {
      const list = listeners[type] || [];
      listeners[type] = list.filter((x) => x !== fn);
    };
    globalThis.dispatchEvent = (ev) => { (listeners[ev.type] || []).forEach((fn) => fn(ev)); };
    globalThis.addEventListener("eis:localechange", () => {
      rebuilds += 1;
      renderSettings(container, ["regional"]).catch(() => {});
    });
    return {
      count: () => rebuilds,
      restore() {
        if (originals.add) globalThis.addEventListener = originals.add; else delete globalThis.addEventListener;
        if (originals.remove) globalThis.removeEventListener = originals.remove; else delete globalThis.removeEventListener;
        if (originals.dispatch) globalThis.dispatchEvent = originals.dispatch; else delete globalThis.dispatchEvent;
      },
    };
  }

  function adminFetch(urls) {
    return (url) => {
      urls.push(String(url));
      if (url.endsWith("/settings/application")) return jsonResponse(200, { success: true, data: APP_DATA });
      if (url.endsWith("/settings/company")) return jsonResponse(200, { success: true, data: COMPANY_DATA });
      if (url.endsWith("/email/status")) return jsonResponse(200, { success: true, data: EMAIL_STATUS_DATA });
      if (url.endsWith("/settings/user")) return jsonResponse(200, { success: true, data: USER_DATA });
      return jsonResponse(500, { success: false, message: "unexpected " + url });
    };
  }

  it("renders the full section nav for an admin and opens General (application settings) by default", async () => {
    authStore.setUser({ id: 24, username: "admin_test", email: "admin@test.local", roles: ["admin"] });
    const container = document.createElement("div");
    const stop = installFetch(adminFetch([]));
    try {
      await renderSettings(container);
      const text = treeText(container);
      assert.deepEqual(navLabels(container), [
        "General",
        "Organization",
        "Email & Notifications",
        "Appearance",
        "Language & Regional",
      ]);
      assert.ok(text.includes("Application name"), "General section renders application fields");
      assert.ok(text.includes("Save application settings"), "the section-scoped save action is present");
      const active = container.querySelectorAll(".settings-nav__item").find((b) => b.classList.contains("is-active"));
      assert.ok(active && treeText(active).trim() === "General", "General starts active");
      assert.equal(active.getAttribute("aria-current"), "page", "the active anchor declares aria-current=page");
      assert.equal(active.getAttribute("href"), "#/settings/general", "the default anchor targets its sub-route");
    } finally {
      stop();
    }
  });

  it("switches sections through the internal nav and only fetches what the active section needs", async () => {
    authStore.setUser({ id: 24, username: "admin_test", email: "admin@test.local", roles: ["admin"] });
    const urls = [];
    const container = document.createElement("div");
    const stop = installFetch(adminFetch(urls));
    try {
      await renderSettings(container);
      assert.deepEqual(urls, [`${BASE}/api/settings/application`], "only the active section is fetched on mount");

      await clickNav(container, "Organization");
      assert.ok(treeText(container).includes("Company name"), "Organization section renders company fields");
      assert.ok(urls.includes(`${BASE}/api/settings/company`), "company settings fetched after navigating to Organization");
      assert.ok(!urls.includes(`${BASE}/api/email/status`), "email status not fetched before its section opens");

      await clickNav(container, "Appearance");
      assert.ok(container.querySelector('[name="theme"]'), "Appearance renders the personal theme control");
      assert.ok(!urls.includes(`${BASE}/api/email/status`), "email status still not fetched for Appearance");
    } finally {
      stop();
    }
  });

  it("loads the Email section on demand, including the workflow description and test form", async () => {
    authStore.setUser({ id: 24, username: "admin_test", email: "admin@test.local", roles: ["admin"] });
    const urls = [];
    const container = document.createElement("div");
    const stop = installFetch(adminFetch(urls));
    try {
      await renderSettings(container);
      await clickNav(container, "Email & Notifications");
      const text = treeText(container);
      assert.ok(text.includes("reconciliation.discrepancies"), "email workflow id is described");
      assert.ok(text.includes("Send test email"), "test email form renders");
      assert.ok(urls.includes(`${BASE}/api/email/status`), "email status API was called once its section opened");
      const active = container.querySelectorAll(".settings-nav__item").find((b) => b.classList.contains("is-active"));
      assert.ok(active && treeText(active).trim() === "Email & Notifications", "the opened section is marked active");
    } finally {
      stop();
    }
  });

  it("loads a section directly when arriving on a settings sub-route", async () => {
    authStore.setUser({ id: 24, username: "admin_test", email: "admin@test.local", roles: ["admin"] });
    const urls = [];
    const container = document.createElement("div");
    const stop = installFetch(adminFetch(urls));
    try {
      await renderSettings(container, ["email"]);
      assert.ok(treeText(container).includes("reconciliation.discrepancies"), "the Email section rendered from the sub-route");
      assert.ok(urls.includes(`${BASE}/api/email/status`), "email status fetched on direct sub-route mount");
      const active = container.querySelectorAll(".settings-nav__item").find((b) => b.classList.contains("is-active"));
      assert.ok(active && treeText(active).trim() === "Email & Notifications", "the direct sub-route marks its section active");
    } finally {
      stop();
    }
  });

  it("redirects a non-admin away from an admin-gated sub-route to Appearance", async () => {
    authStore.setUser({ id: 37, username: "abdo21", email: "abdo213@gmail.com", roles: ["viewer"] });
    const urls = [];
    const stop = installFetch((url) => {
      urls.push(String(url));
      if (url.endsWith("/settings/user")) return jsonResponse(200, { success: true, data: USER_DATA });
      return jsonResponse(500, { success: false, message: "unexpected " + url });
    });
    try {
      const container = document.createElement("div");
      await renderSettings(container, ["general"]);
      assert.equal(window.location.hash, "#/settings/appearance", "the forbidden section redirected to the first section the role may see");
      const labels = navLabels(container);
      assert.ok(!labels.includes("General") && !labels.includes("Organization") && !labels.includes("Email & Notifications"),
        "admin-only sections never render for a non-admin");
      assert.ok(container.querySelector('[name="theme"]'), "the personal theme content rendered after the redirect");
      assert.ok(!urls.includes(`${BASE}/api/settings/application`), "application settings were not fetched for a non-admin");
    } finally {
      stop();
      window.location.hash = "";
    }
  });

  it("falls back to the first allowed section on an unknown sub-route", async () => {
    authStore.setUser({ id: 24, username: "admin_test", email: "admin@test.local", roles: ["admin"] });
    const urls = [];
    const container = document.createElement("div");
    const stop = installFetch(adminFetch(urls));
    try {
      await renderSettings(container, ["nonsense"]);
      assert.equal(window.location.hash, "#/settings/general", "unknown ids redirect to the role's first section");
      assert.ok(treeText(container).includes("Application name"), "General rendered for the fallback");
    } finally {
      stop();
      window.location.hash = "";
    }
  });

  it("keeps the Email card visible with an inline error when GET /api/email/status fails", async () => {
    authStore.setUser({ id: 24, username: "admin_test", email: "admin@test.local", roles: ["admin"] });
    const stop = installFetch((url) => {
      if (url.endsWith("/settings/application")) return jsonResponse(200, { success: true, data: APP_DATA });
      if (url.endsWith("/email/status")) return jsonResponse(500, { success: false, message: "Email service is not configured" });
      return jsonResponse(500, { success: false, message: "unexpected" });
    });
    try {
      const container = document.createElement("div");
      await renderSettings(container);
      await clickNav(container, "Email & Notifications");
      const text = treeText(container);
      assert.ok(text.includes("Unable to load data"), "an error state renders inside the Email section");
      assert.ok(text.includes("Email service is not configured"), "the backend message is surfaced");
    } finally {
      stop();
    }
  });

  it("does not render admin-only sections (General, Organization, Email) for a non-admin and opens Appearance", async () => {
    authStore.setUser({ id: 37, username: "abdo21", email: "abdo213@gmail.com", roles: ["viewer"] });
    const stop = installFetch((url) => {
      if (url.endsWith("/settings/user")) return jsonResponse(200, { success: true, data: USER_DATA });
      return jsonResponse(500, { success: false, message: "unexpected " + url });
    });
    try {
      const container = document.createElement("div");
      await renderSettings(container);
      const labels = navLabels(container);
      assert.ok(!labels.includes("General"), "non-admin must not see the General admin section");
      assert.ok(!labels.includes("Organization"), "non-admin must not see the Organization admin section");
      assert.ok(!labels.includes("Email & Notifications"), "non-admin must not see the Email admin section");
      assert.deepEqual(labels, ["Appearance", "Language & Regional"]);
      assert.ok(container.querySelector('[name="theme"]'), "Appearance is the default section for a non-admin");
      const active = container.querySelectorAll(".settings-nav__item").find((b) => b.classList.contains("is-active"));
      assert.ok(active && treeText(active).trim() === "Appearance", "Appearance starts active");
    } finally {
      stop();
    }
  });

  it("saving Arabic in Language & Regional PUTs the profile, persists locally and re-renders in Arabic", async () => {
    authStore.setUser({ id: 24, username: "admin_test", email: "admin@test.local", roles: ["admin"] });
    let putBody = null;
    let userGets = 0;
    const stop = installFetch((url, init) => {
      if (url.endsWith("/settings/user") && init.method === "PUT") {
        putBody = JSON.parse(init.body);
        return jsonResponse(200, { success: true, data: { ...USER_DATA, language: putBody.language } });
      }
      if (url.endsWith("/settings/user")) {
        userGets += 1;
        const language = putBody && putBody.language === "ar" ? "ar" : USER_DATA.language;
        return jsonResponse(200, { success: true, data: { ...USER_DATA, language } });
      }
      if (url.endsWith("/settings/application")) return jsonResponse(200, { success: true, data: APP_DATA });
      return jsonResponse(500, { success: false, message: "unexpected " + url });
    });
    try {
      const container = document.createElement("div");
      await renderSettings(container);
      await clickNav(container, "Language & Regional");
      assert.ok(treeText(container).includes("Language"), "regional form renders");

      const form = container.querySelector("form");
      const select = form.querySelector('[name="language"]');
      assert.ok(select, "language select is present");
      select.value = "ar";
      form.dispatchEvent({ type: "submit", preventDefault() {} });
      for (let i = 0; i < 8; i++) await flush();

      assert.equal(putBody.language, "ar", "the PUT payload carries the profile language");
      assert.equal(globalThis.localStorage.getItem("eis:lang"), "ar", "the choice is persisted for later boots");
      assert.equal(document.documentElement.lang, "ar", "the active locale switched immediately");
      assert.equal(document.documentElement.dir, "rtl", "the document switched to RTL");
      assert.ok(userGets >= 1, "preferences were reloaded after saving");
      assert.ok(select.value === "ar", "the language select reflects the saved value");

      // The localechange listener rebuilds the app shell; tests stand in for
      // it by re-rendering the settings route in the new locale.
      await renderSettings(container, ["regional"]);
      await flush();
      await flush();
      const labels = navLabels(container);
      assert.ok(labels.includes("اللغة والإقليم"), "the section nav re-rendered in Arabic");
      const arSelect = container.querySelector('[name="language"]');
      assert.ok(arSelect, "regional form re-rendered");
      assert.equal(arSelect.value, "ar", "the language select keeps the saved value after re-render");
      assert.ok(treeText(document.body).includes("تم حفظ التفضيلات الشخصية"),
        "the Arabic profile-save toast was announced");
    } finally {
      stop();
    }
  });

  it("no longer surfaces application-default theme/language controls in any section", async () => {
    authStore.setUser({ id: 24, username: "admin_test", email: "admin@test.local", roles: ["admin"] });
    const container = document.createElement("div");
    const stop = installFetch(adminFetch([]));
    try {
      await renderSettings(container);
      assert.equal(container.querySelector('[name="default_language"]'), null,
        "no default-language control renders in General");
      assert.equal(container.querySelector('[name="default_theme"]'), null,
        "no default-theme control renders in General");

      await clickNav(container, "Language & Regional");
      assert.equal(container.querySelector('[name="default_language"]'), null,
        "no application-default language control exists in Language & Regional");
      assert.equal(container.querySelectorAll('[name="language"]').length, 1,
        "the personal language control is the only language control");
      assert.equal(container.querySelector("#default-language-hint"), null,
        "no application-default language hint exists");

      await clickNav(container, "Appearance");
      assert.equal(container.querySelector('[name="default_theme"]'), null,
        "no application-default theme control exists in Appearance");
      assert.equal(container.querySelectorAll('[name="theme"]').length, 1,
        "the personal theme control is the only theme control");
      assert.equal(container.querySelector("#default-theme-hint"), null,
        "no application-default theme hint exists");
    } finally {
      stop();
    }
  });

  it("keeps the Application-defaults blocks hidden for non-admins", async () => {
    authStore.setUser({ id: 37, username: "abdo21", email: "abdo213@gmail.com", roles: ["viewer"] });
    const stop = installFetch((url) => {
      if (url.endsWith("/settings/user")) return jsonResponse(200, { success: true, data: USER_DATA });
      return jsonResponse(500, { success: false, message: "unexpected " + url });
    });
    try {
      const container = document.createElement("div");
      await renderSettings(container, ["regional"]);
      assert.equal(container.querySelector('[name="default_language"]'), null,
        "non-admin never sees the application default language");
      assert.ok(container.querySelector('[name="language"]'),
        "the personal language select still renders");

      await renderSettings(container, ["appearance"]);
      assert.equal(container.querySelector('[name="default_theme"]'), null,
        "non-admin never sees the application default theme");
      assert.ok(container.querySelector('[name="theme"]'),
        "the personal theme select still renders");
    } finally {
      stop();
    }
  });

  it("Settings no longer contains Security or My Profile, and exposes no page-size control", async () => {
    authStore.setUser({ id: 24, username: "admin_test", email: "admin@test.local", roles: ["admin"] });
    const container = document.createElement("div");
    const stop = installFetch(adminFetch([]));
    try {
      await renderSettings(container);
      const labels = navLabels(container);
      assert.ok(!labels.includes("Security"), "the Security section is gone (password management lives on Account)");
      assert.ok(!labels.includes("My profile"), "the My Profile section is gone (it lives on the Account page)");
      assert.equal(container.querySelector('[name="pagination_size"]'), null,
        "General exposes no page-size control");

      await clickNav(container, "Appearance");
      assert.equal(container.querySelector('[name="pagination_size"]'), null,
        "Appearance exposes no page-size control");

      await clickNav(container, "Language & Regional");
      assert.equal(container.querySelector('[name="pagination_size"]'), null,
        "Language & Regional exposes no page-size control");
    } finally {
      stop();
    }
  });

  it("requesting the removed Security/My Profile sub-routes falls back to the role's first section", async () => {
    window.location.hash = "";
    authStore.setUser({ id: 24, username: "admin_test", email: "admin@test.local", roles: ["admin"] });
    let container = document.createElement("div");
    let stop = installFetch(adminFetch([]));
    try {
      await renderSettings(container, ["security"]);
      assert.equal(window.location.hash, "#/settings/general",
        "the removed Security sub-route redirects an admin to General");
    } finally {
      stop();
      window.location.hash = "";
    }

    authStore.setUser({ id: 37, username: "abdo21", email: "abdo213@gmail.com", roles: ["viewer"] });
    container = document.createElement("div");
    stop = installFetch((url) => {
      if (url.endsWith("/settings/user")) return jsonResponse(200, { success: true, data: USER_DATA });
      return jsonResponse(500, { success: false, message: "unexpected " + url });
    });
    try {
      await renderSettings(container, ["profile"]);
      assert.equal(window.location.hash, "#/settings/appearance",
        "the removed My Profile sub-route redirects a non-admin to Appearance");
    } finally {
      stop();
      window.location.hash = "";
    }
  });

  it("Appearance shows exactly one theme-changing control (personal theme only)", async () => {
    authStore.setUser({ id: 24, username: "admin_test", email: "admin@test.local", roles: ["admin"] });
    const container = document.createElement("div");
    const stop = installFetch(adminFetch([]));
    try {
      await renderSettings(container, ["appearance"]);
      assert.equal(container.querySelectorAll('[name="theme"]').length, 1,
        "exactly one personal theme control");
      assert.equal(container.querySelector('[name="default_theme"]'), null,
        "no duplicate application-default theme control");
      const text = treeText(container);
      assert.ok(text.includes("Personal theme"), "the single control is labelled for the account scope");
      assert.ok(text.includes("Applies to this account only."), "the control carries a scope hint");
      assert.ok(!text.includes("Default theme"), "no second theme control is offered");
      assert.equal(container.querySelector("#default-theme-hint"), null,
        "no application-default theme hint renders");
    } finally {
      stop();
    }
  });

  it("Language & Regional shows exactly one language-changing control (personal language only)", async () => {
    authStore.setUser({ id: 24, username: "admin_test", email: "admin@test.local", roles: ["admin"] });
    const container = document.createElement("div");
    const stop = installFetch(adminFetch([]));
    try {
      await renderSettings(container, ["regional"]);
      assert.equal(container.querySelectorAll('[name="language"]').length, 1,
        "exactly one personal language control");
      assert.equal(container.querySelector('[name="default_language"]'), null,
        "no duplicate application-default language control");
      const text = treeText(container);
      assert.ok(text.includes("Personal language"), "the single control is labelled with its scope");
      assert.ok(text.includes("Interface language for this account."), "the control carries a scope hint");
      assert.ok(!text.includes("Default language"), "no second language control is offered");
    } finally {
      stop();
    }
  });

  it("selects pre-fill the saved non-default values instead of the first option", async () => {
    authStore.setUser({ id: 24, username: "admin_test", email: "admin@test.local", roles: ["admin"] });
    const nonDefault = { ...USER_DATA, language: "ar", theme: "dark", timezone: "Africa/Cairo" };
    const container = document.createElement("div");
    const stop = installFetch((url) => {
      if (url.endsWith("/settings/company")) return jsonResponse(200, { success: true, data: COMPANY_DATA });
      if (url.endsWith("/email/status")) return jsonResponse(200, { success: true, data: EMAIL_STATUS_DATA });
      if (url.endsWith("/settings/user")) return jsonResponse(200, { success: true, data: nonDefault });
      return jsonResponse(500, { success: false, message: "unexpected " + url });
    });
    try {
      await renderSettings(container, ["appearance"]);
      assert.equal(container.querySelector('[name="theme"]').value, "dark",
        "a saved dark personal theme pre-selects instead of falling back to the first option");
      await renderSettings(container, ["regional"]);
      assert.equal(container.querySelector('[name="language"]').value, "ar",
        "a saved Arabic personal language pre-selects instead of the first option");
      assert.equal(container.querySelector('[name="timezone"]').value, "Africa/Cairo",
        "a saved non-default timezone pre-selects instead of the first option");
    } finally {
      stop();
    }
  });

  it("removes the System section entirely: no nav item, no page, and the old route redirects", async () => {
    authStore.setUser({ id: 24, username: "admin_test", email: "admin@test.local", roles: ["admin"] });
    let container = document.createElement("div");
    let stop = installFetch(adminFetch([]));
    try {
      await renderSettings(container);
      assert.ok(!navLabels(container).includes("System"),
        "the System nav item is gone from an admin's Settings nav");
      assert.ok(!treeText(container).includes("System settings are not currently available."),
        "no reserved-state System content is rendered");

      // The old route follows the existing invalid/unknown-section fallback.
      window.location.hash = "";
      await renderSettings(container, ["system"]);
      assert.equal(window.location.hash, "#/settings/general",
        "the removed System sub-route redirects an admin to the role's first section");
    } finally {
      stop();
      window.location.hash = "";
    }

    authStore.setUser({ id: 37, username: "abdo21", email: "abdo213@gmail.com", roles: ["viewer"] });
    container = document.createElement("div");
    stop = installFetch((url) => {
      if (url.endsWith("/settings/user")) return jsonResponse(200, { success: true, data: USER_DATA });
      return jsonResponse(500, { success: false, message: "unexpected " + url });
    });
    try {
      window.location.hash = "";
      await renderSettings(container, ["system"]);
      assert.equal(window.location.hash, "#/settings/appearance",
        "the removed System sub-route redirects a non-admin to Appearance");
      assert.ok(!navLabels(container).includes("System"),
        "the System nav item is gone from a non-admin's Settings nav");
    } finally {
      stop();
      window.location.hash = "";
    }
  });

  it("switching the language to Arabic re-renders immediately via the locale event without changing the route", async () => {
    authStore.setUser({ id: 24, username: "admin_test", email: "admin@test.local", roles: ["admin"] });
    let putBody = null;
    const stop = installFetch((url, init) => {
      if (url.endsWith("/settings/user") && init.method === "PUT") {
        putBody = JSON.parse(init.body);
        return jsonResponse(200, { success: true, data: { ...USER_DATA, language: putBody.language } });
      }
      if (url.endsWith("/settings/user")) {
        const language = putBody && putBody.language === "ar" ? "ar" : USER_DATA.language;
        return jsonResponse(200, { success: true, data: { ...USER_DATA, language } });
      }
      if (url.endsWith("/settings/application")) return jsonResponse(200, { success: true, data: APP_DATA });
      return jsonResponse(500, { success: false, message: "unexpected " + url });
    });
    const container = document.createElement("div");
    const hashBefore = window.location.hash;
    const events = installLocaleRebuild(container);
    try {
      await renderSettings(container, ["regional"]);
      const select = container.querySelector('[name="language"]');
      assert.ok(select, "personal language select is present");
      select.value = "ar";
      container.querySelector("form").dispatchEvent({ type: "submit", preventDefault() {} });
      for (let i = 0; i < 8; i++) await flush();

      assert.equal(putBody.language, "ar", "the PUT payload carries the profile language");
      assert.equal(document.documentElement.lang, "ar", "<html lang> updated immediately");
      assert.equal(document.documentElement.dir, "rtl", "<html dir> switched to RTL immediately");
      assert.ok(navLabels(container).includes("اللغة والإقليم"),
        "the section nav re-rendered in Arabic via the locale event — no manual refresh");
      assert.equal(window.location.hash, hashBefore, "the hash route is unchanged by the language switch");
      assert.equal(events.count(), 1, "exactly one locale event fired — no silent swallow, duplicates or loop");
      assert.equal(globalThis.localStorage.getItem("eis:lang"), "ar", "the choice persists for later boots");
    } finally {
      events.restore();
      stop();
    }
  });

  it("switching the language back to English re-renders immediately and returns the document to LTR", async () => {
    authStore.setUser({ id: 24, username: "admin_test", email: "admin@test.local", roles: ["admin"] });
    await applyAppLocale("ar");
    let putBody = { language: "ar" };
    const stop = installFetch((url, init) => {
      if (url.endsWith("/settings/user") && init.method === "PUT") {
        putBody = JSON.parse(init.body);
        return jsonResponse(200, { success: true, data: { ...USER_DATA, language: putBody.language } });
      }
      if (url.endsWith("/settings/user")) {
        return jsonResponse(200, { success: true, data: { ...USER_DATA, language: putBody.language } });
      }
      if (url.endsWith("/settings/application")) return jsonResponse(200, { success: true, data: APP_DATA });
      return jsonResponse(500, { success: false, message: "unexpected " + url });
    });
    const container = document.createElement("div");
    const hashBefore = window.location.hash;
    const events = installLocaleRebuild(container);
    try {
      await renderSettings(container, ["regional"]);
      assert.ok(navLabels(container).includes("اللغة والإقليم"), "the section starts in Arabic");
      const select = container.querySelector('[name="language"]');
      assert.ok(select, "personal language select is present");
      select.value = "en";
      container.querySelector("form").dispatchEvent({ type: "submit", preventDefault() {} });
      for (let i = 0; i < 8; i++) await flush();

      assert.equal(document.documentElement.lang, "en", "<html lang> updated back to English immediately");
      assert.equal(document.documentElement.dir, "ltr", "<html dir> returned to LTR immediately");
      assert.ok(navLabels(container).includes("Language & Regional"),
        "the section nav re-rendered in English via the locale event — no manual refresh");
      assert.equal(window.location.hash, hashBefore, "the hash route is unchanged by the language switch");
      assert.equal(events.count(), 1, "exactly one locale event fired — no duplicates or loop");
    } finally {
      events.restore();
      stop();
    }
  });
});