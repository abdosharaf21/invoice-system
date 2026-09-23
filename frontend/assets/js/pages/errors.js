/**
 * Error pages — 404 (not found) and 403 (forbidden).
 */

import { el, clear } from "../utils/dom.js";
import { t } from "../i18n/index.js";

export function renderNotFound(container) {
  clear(container);
  container.appendChild(
    el("div", { className: "state-block state-block--page" },
      el("div", { className: "state-block__icon" }, "404"),
      el("div", { className: "state-block__title" }, t("errors.notFound")),
      el("div", null, t("errors.notFoundBody")),
      el("button", { className: "btn btn-primary", onClick: () => { window.location.hash = "#/dashboard"; } }, t("errors.goDashboard")),
    ),
  );
}

export function renderForbidden(container) {
  clear(container);
  container.appendChild(
    el("div", { className: "state-block state-block--page" },
      el("div", { className: "state-block__icon" }, "403"),
      el("div", { className: "state-block__title" }, t("errors.forbidden")),
      el("div", null, t("errors.forbiddenBody")),
      el("button", { className: "btn btn-primary", onClick: () => { window.location.hash = "#/dashboard"; } }, t("errors.goDashboard")),
    ),
  );
}