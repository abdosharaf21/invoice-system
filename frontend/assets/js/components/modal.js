/**
 * Simple reusable modal.
 *
 * Two APIs:
 *  * showModal(title, bodyNode, footerNode) — low-level.
 *  * openModal({ title, body, actions }) — actions = [{ label, variant,
 *    onClick(modal) }]; the modal handle exposes close().
 */

import { el, clear } from "../utils/dom.js";

let active = null;

/** Show a modal. Returns a close() function. */
export function showModal(title, bodyNode, footerNode) {
  closeModal(); // dismiss any existing
  const overlay = el("div", { className: "modal-overlay" },
    el("div", { className: "modal", role: "dialog", "aria-modal": "true" },
      el("div", { className: "modal__header" },
        el("div", { className: "modal__title" }, title),
        el("button", { className: "modal__close", onClick: () => closeModal(), "aria-label": "Close" }, "×"),
      ),
      el("div", { className: "modal__body" }, bodyNode),
      footerNode ? el("div", { className: "modal__footer" }, footerNode) : null,
    ),
  );
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) closeModal();
  });
  document.body.appendChild(overlay);
  active = overlay;

  const close = () => closeModal();
  return close;
}

/**
 * Show a modal from an options object.
 * actions: [{ label, variant?: "primary"|"secondary"|"danger", onClick(modal) }]
 * The modal handle exposes close() and is passed to each action's onClick.
 */
export function openModal({ title, body, actions = [], footer = null }) {
  const footerNode = el("div", { className: "modal__actions" });
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
    }, action.label || "OK");
    builtActions.appendChild(btn);
  }
  if (footer) builtActions.appendChild(footer);

  const overlay = el("div", { className: "modal-overlay" },
    el("div", { className: "modal", role: "dialog", "aria-modal": "true" },
      el("div", { className: "modal__header" },
        el("div", { className: "modal__title" }, title),
        el("button", { className: "modal__close", onClick: () => closeModal(), "aria-label": "Close" }, "×"),
      ),
      el("div", { className: "modal__body" }, body),
      el("div", { className: "modal__footer" }, builtActions),
    ),
  );
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) closeModal();
  });
  document.body.appendChild(overlay);
  active = overlay;

  return handle;
}

export function closeModal() {
  if (active && active.parentNode) {
    active.remove();
    active = null;
  }
}

export function closeActiveModal() {
  closeModal();
}