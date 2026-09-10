/**
 * Error pages — 404 (not found) and 403 (forbidden).
 */

import { el, clear } from "../utils/dom.js";

export function renderNotFound(container) {
  clear(container);
  container.appendChild(
    el("div", { className: "state-block state-block--page" },
      el("div", { className: "state-block__icon" }, "404"),
      el("div", { className: "state-block__title" }, "Page not found"),
      el("div", null, "The address you requested does not exist."),
      el("button", { className: "btn btn-primary", onClick: () => { window.location.hash = "#/dashboard"; } }, "Go to dashboard"),
    ),
  );
}

export function renderForbidden(container) {
  clear(container);
  container.appendChild(
    el("div", { className: "state-block state-block--page" },
      el("div", { className: "state-block__icon" }, "403"),
      el("div", { className: "state-block__title" }, "Access denied"),
      el("div", null, "Your role does not allow this action."),
      el("button", { className: "btn btn-primary", onClick: () => { window.location.hash = "#/dashboard"; } }, "Go to dashboard"),
    ),
  );
}