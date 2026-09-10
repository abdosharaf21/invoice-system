/**
 * Pagination bar. Renders "Page 3 of 7 · 150 results" plus prev/next and
 * a page-size selector, driven entirely by the backend's pagination envelope
 * ({items, page, page_size, total, total_pages}).
 */

import { el, clear } from "../utils/dom.js";
import { LIMITS } from "../config.js";

/**
 * @param {object} envelope — {page, page_size, total, total_pages}
 * @param {function} onNavigate  — (page) => void
 * @param {function} [onPageSize] — (pageSize) => void
 */
export function renderPagination(container, envelope, onNavigate, onPageSize = null) {
  clear(container);
  const { page = 1, page_size = LIMITS.defaultPageSize, total = 0, total_pages = 1 } = envelope;

  const first = total === 0 ? 0 : (page - 1) * page_size + 1;
  const last = Math.min(page * page_size, total);

  const node = el("div", { className: "pagination" },
    el("div", { className: "pagination__info", "aria-live": "polite" },
      `${first}–${last} of ${total} results`,
    ),
    el("div", { className: "pagination__controls" },
      onPageSize &&
        el("select", {
          className: "select",
          style: "width:auto;min-width:0;padding:0.25rem 0.5rem;margin-inline-end:1rem;",
          "aria-label": "Results per page",
          value: String(page_size),
          onChange: (e) => onPageSize(Number(e.target.value)),
        },
          ...["10", "25", "50", "100", "200"].map((n) =>
            el("option", { value: n, selected: String(page_size) === n ? "" : null }, `${n} / page`),
          ),
        ),
      el("button", {
        className: "btn btn-secondary btn-sm",
        disabled: page <= 1 ? "disabled" : null,
        onClick: () => onNavigate(page - 1),
      }, "← Prev"),
      el("span", { className: "text-sm text-secondary" }, `Page ${page} of ${total_pages}`),
      el("button", {
        className: "btn btn-secondary btn-sm",
        disabled: page >= total_pages ? "disabled" : null,
        onClick: () => onNavigate(page + 1),
      }, "Next →"),
    ),
  );

  container.appendChild(node);
}