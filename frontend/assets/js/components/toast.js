/**
 * Toast notifications.
 */

import { el, clear } from "../utils/dom.js";
import { t } from "../i18n/index.js";

let stack = null;

function getStack() {
  if (!stack) stack = document.getElementById("toast-stack");
  return stack;
}

function remove(node) {
  node.remove();
}

export function toast(message, { type = "info", duration = 4500 } = {}) {
  const s = getStack();
  if (!s) return;

  // Errors must be announced with the assertive "alert" live region so
  // screen-reader users hear the failure immediately; polite "status" is
  // reserved for neutral/success updates.
  const role = type === "error" ? "alert" : "status";

  const node = el("div", { className: `toast toast--${type}`, role },
    el("span", { className: "toast__msg" }, message),
    el("button", {
      className: "toast__close",
      "aria-label": t("common.close"),
      onClick: () => remove(node),
    }, "×"),
  );
  s.appendChild(node);

  if (duration > 0) {
    setTimeout(() => remove(node), duration);
  }
}