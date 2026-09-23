/**
 * Pagination bar. Renders "Page 3 of 7 · 150 results" plus prev/next and
 * a page-size selector, driven entirely by the backend's pagination envelope
 * ({items, page, page_size, total, total_pages}).
 */

import { el, clear } from "../utils/dom.js";
import { LIMITS } from "../config.js";
import { t } from "../i18n/index.js";

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
      t("pagination.range", { first, last, total }),
    ),
    el("div", { className: "pagination__controls" },
      onPageSize &&
        el("select", {
          className: "select",
          style: "width:auto;min-width:0;padding:var(--space-1) var(--space-2);margin-inline-end:var(--space-4);",
          "aria-label": t("common.ariaResultsPerPage"),
          value: String(page_size),
          onChange: (e) => onPageSize(Number(e.target.value)),
        },
          ...["10", "25", "50", "100", "200"].map((n) =>
            el("option", { value: n, selected: String(page_size) === n ? "" : null }, `${n} ${t("common.perPage")}`),
          ),
        ),
      el("button", {
        className: "btn btn-secondary btn-sm",
        disabled: page <= 1 ? "disabled" : null,
        onClick: () => onNavigate(page - 1),
      }, t("common.prev")),
      el("span", { className: "text-sm text-secondary" }, t("pagination.pageOf", { page, total: total_pages })),
      el("button", {
        className: "btn btn-secondary btn-sm",
        disabled: page >= total_pages ? "disabled" : null,
        onClick: () => onNavigate(page + 1),
      }, t("common.next")),
    ),
  );

  container.appendChild(node);
}