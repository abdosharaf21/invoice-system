/**
 * Simple reusable modal.
 *
 * Two APIs:
 *  * showModal(title, bodyNode, footerNode) — low-level.
 *  * openModal({ title, body, actions }) — actions = [{ label, variant,
 *    onClick(modal) }]; the modal handle exposes close().
 *
 * Accessibility:
 *  * the dialog is labelled by its title ("aria-labelledby"),
 *  * focus moves into the dialog on open and is trapped with Tab / Shift+Tab,
 *  * Escape closes the dialog,
 *  * focus is restored to the element that opened it on close,
 *  * background interaction is prevented while open (focus is trapped and the
 *    page scroll is locked on document.body).
 */

import { el } from "../utils/dom.js";
import { t } from "../i18n/index.js";

let active = null;
let opener = null;
let modalSeq = 0;

const FOCUSABLE_TAGS = new Set(["button", "input", "select", "textarea", "a"]);

/** Collect focusable, enabled elements reachable under `root`. */
function focusable(root, list = []) {
  const walk = (node) => {
    if (!node || node.nodeType === 3) return;
    const tag = String(node.tagName || "").toLowerCase();
    if (FOCUSABLE_TAGS.has(tag) && !node.disabled) list.push(node);
    if (node.childNodes) {
      for (const child of node.childNodes) walk(child);
    }
  };
  walk(root);
  return list;
}

function focusInDialog(dialog) {
  const target = focusable(dialog)[0] || dialog;
  if (target && typeof target.focus === "function") target.focus();
}

/** Attach the overlay wiring. Returns a cleanup callback. */
function mount(overlay, dialog) {
  const prevOverflow = document.body.style.overflow;
  document.body.style.overflow = "hidden";
  document.body.appendChild(overlay);
  active = overlay;

  const onOverlayClick = (e) => {
    if (e.target === overlay) closeModal();
  };
  const onKeydown = (e) => {
    if (e.key === "Escape") {
      e.preventDefault();
      closeModal();
      return;
    }
    if (e.key !== "Tab") return;

    const focusables = focusable(dialog);
    if (focusables.length === 0) {
      e.preventDefault();
      if (typeof dialog.focus === "function") dialog.focus();
      return;
    }
    const first = focusables[0];
    const last = focusables[focusables.length - 1];
    const cur = document.activeElement;
    const inside = Boolean(cur && dialog.contains(cur));
    if (e.shiftKey) {
      if (!inside || cur === first) {
        e.preventDefault();
        last.focus();
      }
    } else if (!inside || cur === last) {
      e.preventDefault();
      first.focus();
    }
  };

  overlay.addEventListener("click", onOverlayClick);
  document.addEventListener("keydown", onKeydown);

  focusInDialog(dialog);

  overlay._einvCleanup = () => {
    overlay.removeEventListener("click", onOverlayClick);
    document.removeEventListener("keydown", onKeydown);
    document.body.style.overflow = prevOverflow;
    if (opener && typeof opener.focus === "function") {
      opener.focus();
    }
    opener = null;
  };
  return overlay._einvCleanup;
}

function keepOpener() {
  return document.activeElement && document.activeElement.nodeType === 1
    ? document.activeElement
    : null;
}

/** Show a modal. Returns a close() function. */
export function showModal(title, bodyNode, footerNode) {
  closeModal(); // dismiss any existing
  opener = keepOpener();
  const titleId = `modal-title-${++modalSeq}`;
  const dialog = el("div", {
    className: "modal",
    role: "dialog",
    "aria-modal": "true",
    "aria-labelledby": titleId,
    tabIndex: -1,
  },
    el("div", { className: "modal__header" },
      el("div", { className: "modal__title", id: titleId }, title),
      el("button", { className: "modal__close", onClick: () => closeModal(), "aria-label": t("common.close"), type: "button" }, "×"),
    ),
    el("div", { className: "modal__body" }, bodyNode),
    footerNode ? el("div", { className: "modal__footer" }, footerNode) : null,
  );
  const overlay = el("div", { className: "modal-overlay" });
  overlay.appendChild(dialog);
  mount(overlay, dialog);

  const close = () => closeModal();
  return close;
}

/**
 * Show a modal from an options object.
 * actions: [{ label, variant?: "primary"|"secondary"|"danger", onClick(modal) }]
 * The modal handle exposes close() and is passed to each action's onClick.
 */
export function openModal({ title, body, actions = [], footer = null }) {
  closeModal();
  opener = keepOpener();
  const titleId = `modal-title-${++modalSeq}`;
  const handle = {
    close: () => closeModal(),
    body,
  };

  const builtActions = el("div", { className: "modal__actions" });
  for (const action of actions) {
    const btn = el("button", {
      className: `btn btn-${action.variant || "primary"}`,
      type: "button",
      onClick: () => action.onClick(handle),
    }, action.label || t("common.ok"));
    builtActions.appendChild(btn);
  }
  if (footer) builtActions.appendChild(footer);

  const dialog = el("div", {
    className: "modal",
    role: "dialog",
    "aria-modal": "true",
    "aria-labelledby": titleId,
    tabIndex: -1,
  },
    el("div", { className: "modal__header" },
      el("div", { className: "modal__title", id: titleId }, title),
      el("button", { className: "modal__close", onClick: () => closeModal(), "aria-label": t("common.close"), type: "button" }, "×"),
    ),
    el("div", { className: "modal__body" }, body),
    el("div", { className: "modal__footer" }, builtActions),
  );

  const overlay = el("div", { className: "modal-overlay" });
  overlay.appendChild(dialog);
  mount(overlay, dialog);

  return handle;
}

export function closeModal() {
  if (!active) return;
  if (typeof active._einvCleanup === "function") {
    active._einvCleanup();
  }
  if (active.parentNode) active.remove();
  active = null;
}

export function closeActiveModal() {
  closeModal();
}