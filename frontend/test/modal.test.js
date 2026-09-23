import { describe, it, beforeEach } from "node:test";
import assert from "node:assert/strict";
import "./helpers/dom.js";
import { showModal, openModal } from "../assets/js/components/modal.js";
import { el } from "../assets/js/utils/dom.js";

function findModal() {
  const overlay = document.querySelector(".modal-overlay");
  return overlay ? overlay.querySelector(".modal") : null;
}

describe("modal accessibility (P0.5)", () => {
  beforeEach(() => {
    document.body.childNodes = [];
    document.body.style.overflow = "";
    document._docListeners = {};
    document.activeElement = null;
  });

  it("opens and removes the dialog", () => {
    const close = showModal("Title", el("p", null, "Body"));
    assert.ok(document.querySelector(".modal-overlay"), "overlay mounted");
    close();
    assert.equal(document.querySelector(".modal"), null, "dialog removed");
  });

  it("exposes dialog semantics and a labelled title", () => {
    showModal("Run summary", el("p", null, "x"));
    const modal = findModal();
    assert.equal(modal.getAttribute("role"), "dialog");
    assert.equal(modal.getAttribute("aria-modal"), "true");
    const labelledby = modal.getAttribute("aria-labelledby");
    assert.ok(labelledby, "aria-labelledby present");
    const title = modal.querySelector(".modal__title");
    assert.equal(title.getAttribute("id"), labelledby);
  });

  it("moves focus into the dialog on open", () => {
    showModal("Title", el("input", { type: "text" }));
    const closeBtn = findModal().querySelector(".modal__close");
    assert.equal(document.activeElement, closeBtn, "close button is the first focusable");
  });

  it("traps Tab forward at the last focusable", () => {
    openModal({ title: "T", body: el("p", null, "b"), actions: [{ label: "Save", onClick: () => {} }] });
    const buttons = findModal().querySelectorAll("button");
    assert.ok(buttons.length >= 2, "has close + action buttons");
    document.activeElement = buttons[buttons.length - 1];
    let prevented = false;
    document.dispatchEvent({ type: "keydown", key: "Tab", preventDefault: () => { prevented = true; } });
    assert.ok(prevented, "Tab at the end is intercepted");
    assert.equal(document.activeElement, buttons[0], "focus wraps to the first control");
  });

  it("traps Shift+Tab backward at the first focusable", () => {
    openModal({ title: "T", body: el("p", null, "b"), actions: [{ label: "Save", onClick: () => {} }] });
    const buttons = findModal().querySelectorAll("button");
    document.activeElement = buttons[0];
    document.dispatchEvent({ type: "keydown", key: "Tab", shiftKey: true, preventDefault: () => {} });
    assert.equal(document.activeElement, buttons[buttons.length - 1], "focus wraps to the last control");
  });

  it("does not intercept Tab on a middle control", () => {
    const input = el("input", { type: "text" });
    openModal({ title: "T", body: input, actions: [{ label: "Save", onClick: () => {} }] });
    document.activeElement = input;
    let prevented = false;
    document.dispatchEvent({ type: "keydown", key: "Tab", preventDefault: () => { prevented = true; } });
    assert.equal(prevented, false, "middle Tab flows through");
  });

  it("closes on Escape", () => {
    showModal("T", el("p", null, "b"));
    assert.ok(document.querySelector(".modal"), "open before escape");
    document.dispatchEvent({ type: "keydown", key: "Escape", preventDefault: () => {} });
    assert.equal(document.querySelector(".modal"), null, "closed by Escape");
  });

  it("restores focus to the opener on close", () => {
    const opener = document.createElement("button");
    document.activeElement = opener;
    const close = showModal("T", el("p", null, "b"));
    document.activeElement = findModal().querySelector(".modal__close");
    close();
    assert.equal(document.activeElement, opener, "opener refocused");
  });

  it("locks page scroll while open and restores it after close", () => {
    document.body.style.overflow = "auto";
    const close = showModal("T", el("p", null, "b"));
    assert.equal(document.body.style.overflow, "hidden");
    close();
    assert.equal(document.body.style.overflow, "auto");
  });

  it("closes when clicking the overlay, not the dialog", () => {
    showModal("T", el("p", null, "b"));
    const overlay = document.querySelector(".modal-overlay");
    const modal = overlay.querySelector(".modal");
    overlay.dispatchEvent({ type: "click", target: modal });
    assert.ok(document.querySelector(".modal"), "dialog click keeps it open");
    overlay.dispatchEvent({ type: "click", target: overlay });
    assert.equal(document.querySelector(".modal"), null, "overlay click closes it");
  });

  it("closes via the openModal handle", () => {
    const handle = openModal({ title: "T", body: el("p", null, "b") });
    assert.equal(typeof handle.close, "function");
    handle.close();
    assert.equal(document.querySelector(".modal"), null, "handle.close removes the modal");
  });
});