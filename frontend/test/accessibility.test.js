import { describe, it, beforeEach } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import "./helpers/dom.js";

// toast() caches its stack element via getElementById; point it at the stub
// body so notifications can be observed and asserted.
globalThis.document.getElementById = () => globalThis.document.body;

import { toast } from "../assets/js/components/toast.js";
import { showError, showLoading } from "../assets/js/utils/dom.js";
import { renderTabs, tabPanelId, tabTriggerId } from "../assets/js/components/tabs.js";
import { renderExportControls } from "../assets/js/components/reportPanels.js";
import { renderUsers } from "../assets/js/pages/users.js";
import { renderLogin, resetLoginState } from "../assets/js/pages/login.js";
import { parseTolerance } from "../assets/js/utils/validation.js";
import { t, applyAppLocale } from "../assets/js/i18n/index.js";

function jsonResponse(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Map([["content-type", "application/json"]]),
    async json() { return body; },
    async blob() { return new Blob(["x"]); },
  };
}

const tick = () => new Promise((resolve) => setTimeout(resolve, 5));

describe("accessibility & UX (P16)", () => {
  beforeEach(() => {
    document.body.childNodes = [];
    document.body.style.overflow = "";
    document._docListeners = {};
    document.activeElement = null;
    resetLoginState();
    globalThis.fetch = async () =>
      jsonResponse(401, { success: false, message: "Bad credentials" });
  });

  it("announces error toasts with role=alert and others with role=status", () => {
    toast("Boom", { type: "error" });
    toast("Saved", { type: "success" });
    toast("Heads up", { type: "info" });

    const errors = document.body.childNodes.filter(
      (n) => n.getAttribute("class")?.includes("toast--error"),
    );
    assert.equal(errors.length, 1, "error toast rendered");
    assert.equal(errors[0].getAttribute("role"), "alert", "errors use the assertive live region");

    const neutral = document.body.childNodes.filter(
      (n) => (n.getAttribute("class")?.includes("toast--success") || n.getAttribute("class")?.includes("toast--info")),
    );
    assert.equal(neutral.length, 2);
    for (const node of neutral) {
      assert.equal(node.getAttribute("role"), "status", "non-errors stay polite");
    }
  });

  it("marks page-level load errors as role=alert", () => {
    const box = document.createElement("div");
    showError(box, "Failed to load data", { onRetry: () => {} });
    const block = box.querySelector(".state-block");
    assert.ok(block, "error state rendered");
    assert.equal(block.getAttribute("role"), "alert", "load failures are announced");
    assert.ok(box.querySelector(".btn"), "retry action is keyboard reachable");
  });

  it("keeps loading state as role=status", () => {
    const box = document.createElement("div");
    showLoading(box, "Loading…");
    assert.equal(box.querySelector(".spinner").getAttribute("role"), "status");
    assert.notEqual(box.querySelector(".state-block").getAttribute("role"), "alert", "loading is polite, not assertive");
  });

  it("exposes the ARIA tabs pattern on the report tab switcher", () => {
    const selected = [];
    const container = document.createElement("div");
    renderTabs(container, [
      { id: "results", label: "Results" },
      { id: "errors", label: "Errors" },
    ], (id) => selected.push(id), "results", { label: "Report views" });

    const bar = container.querySelector("[role='tablist']");
    assert.ok(bar, "tablist present");
    assert.equal(bar.getAttribute("aria-label"), "Report views");

    const tabs = container.querySelectorAll("[role='tab']");
    assert.equal(tabs.length, 2);
    assert.equal(tabs[0].getAttribute("aria-selected"), "true", "active tab selected");
    assert.equal(tabs[1].getAttribute("aria-selected"), "false");
    assert.equal(tabs[0].getAttribute("tabindex"), "0", "active tab in the roving tabindex");
    assert.equal(tabs[1].getAttribute("tabindex"), "-1");
    assert.equal(tabs[0].getAttribute("aria-controls"), tabPanelId("results"));
    assert.equal(tabTriggerId("errors"), tabs[1].getAttribute("id"), "trigger id exposed for labelledby");
  });

  it("lets arrow keys switch report tabs with roving focus", () => {
    const selected = [];
    const container = document.createElement("div");
    renderTabs(container, [
      { id: "results", label: "Results" },
      { id: "errors", label: "Errors" },
    ], (id) => selected.push(id), "results");

    const tabs = container.querySelectorAll("[role='tab']");
    tabs[0].dispatchEvent({ type: "keydown", key: "ArrowRight", preventDefault: () => {} });
    assert.equal(selected[selected.length - 1], "errors", "ArrowRight activates the next tab");
    assert.equal(tabs[1].getAttribute("aria-selected"), "true");
    assert.equal(document.activeElement, tabs[1], "focus follows to the active tab");

    tabs[1].dispatchEvent({ type: "keydown", key: "Home", preventDefault: () => {} });
    assert.equal(selected[selected.length - 1], "results", "Home jumps to the first tab");
    assert.equal(document.activeElement, tabs[0]);
  });

  it("exposes the export menu button pattern and arrow-key navigation", () => {
    const container = document.createElement("div");
    let exported = null;
    renderExportControls(container, (fmt) => { exported = fmt; });

    const button = container.querySelector("[aria-haspopup='menu']");
    assert.ok(button, "export toggle present");
    assert.equal(button.getAttribute("aria-expanded"), "false");

    button.dispatchEvent({ type: "keydown", key: "ArrowDown", preventDefault: () => {} });
    const menuEl = container.querySelector(".dropdown__menu");
    const items = container.querySelectorAll("[role='menuitem']");
    assert.ok(menuEl.classList.contains("is-open"), "menu opens via ArrowDown");
    assert.equal(button.getAttribute("aria-expanded"), "true");
    assert.equal(document.activeElement, items[0], "focus moves into the first item");

    menuEl.dispatchEvent({ type: "keydown", key: "ArrowDown", preventDefault: () => {} });
    assert.equal(document.activeElement, items[1], "ArrowDown moves to the next item");

    menuEl.dispatchEvent({ type: "keydown", key: "Escape", preventDefault: () => {}, stopPropagation: () => {} });
    assert.ok(!menuEl.classList.contains("is-open"), "Escape closes the menu");
    assert.equal(document.activeElement, button, "focus returns to the toggle");

    button.dispatchEvent({ type: "click", stopPropagation: () => {} });
    items[0].dispatchEvent({ type: "click", stopPropagation: () => {} });
    assert.equal(exported, "csv", "item click exports and closes");
    assert.ok(!menuEl.classList.contains("is-open"), "menu closed after choice");
  });

  it("associates every user-modal label with its control", async () => {
    globalThis.fetch = async (url) => {
      if (String(url).includes("/api/users/")) {
        return jsonResponse(200, { success: true, data: [
          { id: 1, username: "alice", full_name: "Alice", email: "alice@corp.test", roles: ["admin"], company_id: 3, is_active: true, last_login_at: null },
        ] });
      }
      return jsonResponse(404, { success: false, message: "Not found" });
    };
    const container = document.createElement("div");
    await renderUsers(container);

    const addBtn = container.querySelector(".btn");
    assert.ok(addBtn, "add-user button exists");
    addBtn.click();

    const dialog = document.querySelector("[role='dialog']");
    assert.ok(dialog, "dialog mounted for the add-user form");

    const controls = [
      ...dialog.querySelectorAll("input"),
      ...dialog.querySelectorAll("select"),
    ];
    assert.ok(controls.length >= 6, `expected form controls, got ${controls.length}`);
    const seenFors = new Set();
    for (const control of controls) {
      const id = control.getAttribute("id");
      assert.ok(id, `control <${control.tagName}> has a matching id`);
      seenFors.add(id);
    }
    const labels = dialog.querySelectorAll("label");
    assert.equal(labels.length, controls.length, "one label per control");
    for (const label of labels) {
      assert.ok(label.getAttribute("for"), "every label carries `for`");
      assert.ok(seenFors.has(label.getAttribute("for")), `label for="${label.getAttribute("for")}" resolves to a control`);
    }
  });

  it("keeps the typed email across a failed login re-render", async () => {
    const container = document.createElement("div");
    renderLogin(container);

    const email = container.querySelector("#login-email");
    email.value = "ops@corp.test";
    container.querySelector("#login-password").value = "wrong-password";
    container.querySelector("#login-form").dispatchEvent({ type: "submit", preventDefault: () => {} });
    await tick();
    await tick();

    const after = container.querySelector("#login-email");
    assert.ok(after, "login form re-rendered");
    assert.equal(after.value, "ops@corp.test", "email is preserved while the error is shown");
    assert.ok(container.querySelector("[role='alert']"), "sign-in failure is announced");
  });

  it("localizes the tolerance validation message", async () => {
    assert.equal(parseTolerance("abc").message, t("validation.toleranceInvalid"));
    await applyAppLocale("ar");
    assert.equal(parseTolerance("abc").message, t("validation.toleranceInvalid"), "translated in Arabic");
    assert.ok(document.documentElement.dir === "rtl" || document.documentElement.lang === "ar",
      "document flips direction/language for Arabic");
    await applyAppLocale("en");
  });
});

describe("mobile drawer CSS (P16)", () => {
  it("hides the closed off-canvas sidebar from focus and the a11y tree", () => {
    const cssPath = join(fileURLToPath(new URL(".", import.meta.url)), "../assets/css/layout.css");
    const css = readFileSync(cssPath, "utf8");
    const mobile = css.slice(css.indexOf("@media (max-width: 860px)"));

    assert.ok(mobile.includes("visibility: hidden"), "closed drawer uses visibility:hidden (removes from tab order + AT)");
    assert.ok(mobile.includes(".sidebar.is-open"), "open state is defined");
    assert.ok(mobile.includes("visibility: visible"), "open drawer becomes visible/announced");
  });
});