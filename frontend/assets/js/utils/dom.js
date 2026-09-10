/**
 * DOM helpers — a thin wrapper over native DOM APIs. Keeps all components
 * free from repeated boilerplate while retaining explicit element ownership.
 *
 *  * `el()` — create an element.
 *  * `clear()` — remove all children from a node.
 *  * `qs()`, `qsa()` — scoped query helpers.
 *  * `icon()`, `emptyCell()` — small, reusable DOM snippets.
 *  * `listen()` — add an event listener that returns a dispose function.
 */

import { escapeHtml } from "./escape.js";

/**
 * Create an element with attributes and children.
 *  * @param {string} tag
 *  * @param {Object} [attrs]
 *  * @param  {...(Node|string|null)} children
 *  * @returns {HTMLElement}
 */
export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);

  // Tolerate calling el("tbody", el("tr", …)) — treat a leading Node as the
  // first child rather than as an attribute map.
  if (attrs instanceof Node || (attrs && typeof attrs === "object" && attrs.nodeType)) {
    children = [attrs, ...children];
    attrs = {};
  }

  if (attrs) {
    for (const [key, val] of Object.entries(attrs)) {
      if (val === undefined || val === null) continue;
      if (key === "className") {
        node.className = String(val);
      } else if (key.startsWith("on") && typeof val === "function") {
        node.addEventListener(key.slice(2).toLowerCase(), val);
      } else if (key === "dataset" && typeof val === "object") {
        Object.assign(node.dataset, val);
      } else {
        node.setAttribute(key, String(val));
      }
    }
  }

  for (const child of children.flat(Infinity)) {
    if (child === undefined || child === null) continue;
    node.appendChild(
      typeof child === "string"
        ? document.createTextNode(child)
        : child instanceof Node
          ? child
          : document.createTextNode(String(child)),
    );
  }

  return node;
}

/** Remove all children from a node. */
export function clear(node) {
  node.replaceChildren();
}

export function qs(selector, context = document) {
  return context.querySelector(selector);
}

export function qsa(selector, context = document) {
  return Array.from(context.querySelectorAll(selector));
}

export function icon(svgPath) {
  const svg = el("svg", {
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    "stroke-width": 2,
    "stroke-linecap": "round",
    "stroke-linejoin": "round",
  });
  const p = el("path", { d: svgPath });
  svg.appendChild(p);
  return svg;
}

export const icons = {
  dashboard: el("svg", { viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "stroke-width": 2 },
    el("rect", { x: "3", y: "3", width: "7", height: "7", rx: "1" }),
    el("rect", { x: "14", y: "3", width: "7", height: "7", rx: "1" }),
    el("rect", { x: "3", y: "14", width: "7", height: "7", rx: "1" }),
    el("rect", { x: "14", y: "14", width: "7", height: "7", rx: "1" }),
  ),
  import: el("svg", { viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "stroke-width": 2 },
    el("path", { d: "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" }),
    el("polyline", { points: "17 8 12 3 7 8" }),
    el("line", { x1: "12", y1: "3", x2: "12", y2: "15" }),
  ),
  reconciliation: el("svg", { viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "stroke-width": 2 },
    el("path", { d: "M12 20V10" }),
    el("path", { d: "M18 20V4" }),
    el("path", { d: "M6 20v-4" }),
  ),
  reports: el("svg", { viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "stroke-width": 2 },
    el("path", { d: "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" }),
    el("polyline", { points: "14 2 14 8 20 8" }),
    el("line", { x1: "16", y1: "13", x2: "8", y2: "13" }),
    el("line", { x1: "16", y1: "17", x2: "8", y2: "17" }),
    el("polyline", { points: "10 9 9 9 8 9" }),
  ),
  users: el("svg", { viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "stroke-width": 2 },
    el("path", { d: "M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" }),
    el("circle", { cx: "9", cy: "7", r: "4" }),
    el("path", { d: "M23 21v-2a4 4 0 0 0-3-3.87" }),
    el("path", { d: "M16 3.13a4 4 0 0 1 0 7.75" }),
  ),
  account: el("svg", { viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "stroke-width": 2 },
    el("path", { d: "M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" }),
    el("circle", { cx: "12", cy: "7", r: "4" }),
  ),
  search: el("svg", { viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "stroke-width": 2 },
    el("circle", { cx: "11", cy: "11", r: "8" }),
    el("line", { x1: "21", y1: "21", x2: "16.65", y2: "16.65" }),
  ),
  download: el("svg", { viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "stroke-width": 2 },
    el("path", { d: "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" }),
    el("polyline", { points: "7 10 12 15 17 10" }),
    el("line", { x1: "12", y1: "15", x2: "12", y2: "3" }),
  ),
  close: el("svg", { viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "stroke-width": 2 },
    el("line", { x1: "18", y1: "6", x2: "6", y2: "18" }),
    el("line", { x1: "6", y1: "6", x2: "18", y2: "18" }),
  ),
  menu: el("svg", { viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "stroke-width": 2 },
    el("line", { x1: "3", y1: "12", x2: "21", y2: "12" }),
    el("line", { x1: "3", y1: "6", x2: "21", y2: "6" }),
    el("line", { x1: "3", y1: "18", x2: "21", y2: "18" }),
  ),
};

/** Render a simple neutral-dash "—" for missing values. */
export function emptyCell() {
  return el("span", { className: "text-muted" }, "—");
}

/** Create an HTML banner alert. */
export function banner({ type = "info", title = "", message = "" }) {
  const node = el("div", { className: `alert alert--${type}`, role: "alert" }, title && el("strong", null, title), " ", message || null);
  return node;
}

/** Create a skeleton row block for a loading state. */
export function skeletonRows(cols = 5, rows = 5) {
  const frag = document.createDocumentFragment();
  for (let r = 0; r < rows; r++) {
    frag.appendChild(
      el(
        "div",
        { className: "sk-row" },
        ...Array.from({ length: cols }, (_, i) =>
          el("div", {
            className: "skeleton",
            style: `width: ${60 + (i % 3) * 25}px; height: 14px`,
          }),
        ),
      ),
    );
  }
  return frag;
}

/** Central render helpers. */
export function renderBadge(status) {
  const cls = `badge badge--${status || "neutral"}`;
  return el("span", { className: cls }, (status || "—").replace(/_/g, " "));
}

/** Create a section heading. */
export function sectionHeading(text) {
  return el("h2", { className: "section-title" }, text);
}

/**
 * Central show/hide helpers for loading/empty/error states inside a container.
 * Each returns a function that can remove the state later.
 */
export function showLoading(container, message = "Loading…") {
  clear(container);
  container.appendChild(
    el("div", { className: "state-block" },
      el("div", { className: "spinner", role: "status", "aria-label": "Loading" }),
      el("div", null, message),
    ),
  );
}

export function showError(container, message, { onRetry = null } = {}) {
  clear(container);
  container.appendChild(
    el("div", { className: "state-block" },
      el("div", { className: "state-block__icon" }, "⚠"),
      el("div", { className: "state-block__title" }, "Unable to load data"),
      el("div", null, message),
      onRetry ? el("button", { className: "btn btn-secondary", onClick: onRetry }, "Retry") : null,
    ),
  );
}

export function showEmpty(container, message, { action = null, onAction = null } = {}) {
  clear(container);
  container.appendChild(
    el("div", { className: "state-block" },
      el("div", { className: "state-block__icon" }, "📋"),
      el("div", { className: "state-block__title" }, message || "Nothing here"),
      action ? el("button", { className: "btn btn-primary", onClick: onAction }, action) : null,
    ),
  );
}