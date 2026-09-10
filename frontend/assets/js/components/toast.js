/**
 * Toast notifications.
 */

import { el, clear } from "../utils/dom.js";
import { escapeHtml } from "../utils/escape.js";

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

  const node = el("div", { className: `toast toast--${type}`, role: "status" },
    el("span", { className: "toast__msg" }, message),
    el("button", {
      className: "menu-item",
      "aria-label": "Close",
      style: "padding:0 0 0 8px;flex:0 0 auto;color:inherit;font-size:inherit;",
      onClick: () => remove(node),
    }, "×"),
  );
  s.appendChild(node);

  if (duration > 0) {
    setTimeout(() => remove(node), duration);
  }
}