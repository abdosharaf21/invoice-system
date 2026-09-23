/**
 * Report tabs — a reusable panel hosting the results and errors sub-reports
 * of a reconciliation report, with their filter toolbars, enterprise tables,
 * pagination and export controls. Used by both the run-detail view and the
 * Reports page; the caller supplies the data-access functions so it stays a
 * pure presentation component.
 */

import { el, clear, showLoading, showError } from "../utils/dom.js";
import { renderTabs, tabPanelId, tabTriggerId } from "./tabs.js";
import {
  renderResultsTable,
  renderErrorsTable,
  buildResultsToolbar,
  buildErrorsToolbar,
  renderExportControls,
  openResultDetail,
} from "./reportPanels.js";
import { toast } from "./toast.js";
import { t } from "../i18n/index.js";

const DEFAULT_PAGE_SIZE = 50;

/**
 * @param {HTMLElement} container
 * @param {object} api
 *  - loadResults(params) -> pagination envelope
 *  - loadErrors(params)  -> pagination envelope
 *  - onExport(kind, format, filters) -> filename (kind: "results"|"errors")
 * @param {object} [opts] — { activeTab: "results"|"errors" }
 */
export function reportTabs(container, api, opts = {}) {
  clear(container);

  const state = {
    tab: opts.activeTab || "results",
    results: { page: 1, page_size: DEFAULT_PAGE_SIZE, filters: {} },
    errors: { page: 1, page_size: DEFAULT_PAGE_SIZE, filters: {} },
  };

  const tabsBox = el("div");
  container.appendChild(tabsBox);

  renderTabs(tabsBox, [
    { id: "results", label: t("report.tabResults") },
    { id: "errors", label: t("report.tabErrors") },
  ], onTab, state.tab, { label: t("report.tabsLabel") });

  onTab(state.tab);

  function onTab(id) {
    state.tab = id;
    const panel = el("div", {
      className: "report-panel",
      role: "tabpanel",
      id: tabPanelId(id),
      "aria-labelledby": tabTriggerId(id),
    });
    tabsBox.appendChild(panel);
    tabsBox.querySelectorAll(".report-panel").forEach((n) => { if (n !== panel) n.remove(); });
    if (id === "results") renderResults(panel);
    if (id === "errors") renderErrors(panel);
  }

  function renderResults(panel) {
    clear(panel);
    const exportBox = el("div", { style: "display:flex;justify-content:flex-end;margin-block-end:var(--space-3);" });
    const filterCard = el("div", { className: "card filter-card" },
      el("div", { className: "card__header" },
        el("div", { className: "section-title" }, t("report.filtersTitle"))),
      el("div", { className: "card__body" },
        (() => { const toolbar = el("div"); buildResultsToolbar(toolbar,
          { ...state.results.filters, page_size: state.results.page_size },
          (filters) => { state.results.filters = filters; state.results.page = 1; loadResults(tableBox); },
          () => { state.results.filters = {}; state.results.page = 1; loadResults(tableBox); },
        ); return toolbar; })(),
      ),
    );
    const tableBox = el("div");

    panel.appendChild(exportBox);
    panel.appendChild(filterCard);
    panel.appendChild(tableBox);

    renderExportControls(exportBox, (fmt) => runExport("results", fmt));

    loadResults(tableBox);

    async function loadResults(box) {
      showLoading(box, t("report.loadingResults"));
      try {
        const params = { page: state.results.page, page_size: state.results.page_size, ...state.results.filters };
        const env = await api.loadResults(params);
        renderResultsTable(box, env, {
          emptyMessage: t("report.noResults"),
          onRowAction: (row) => openResultDetail(row),
          onNavigate: (page) => { state.results.page = page; loadResults(box); },
          onPageSize: (size) => { state.results.page_size = size; state.results.page = 1; loadResults(box); },
        });
      } catch (err) {
        showError(box, err.message || t("report.failedResults"), { onRetry: () => loadResults(box) });
      }
    }
  }

  function renderErrors(panel) {
    clear(panel);
    const exportBox = el("div", { style: "display:flex;justify-content:flex-end;margin-block-end:var(--space-3);" });
    const filterCard = el("div", { className: "card filter-card" },
      el("div", { className: "card__header" },
        el("div", { className: "section-title" }, t("report.filtersTitle"))),
      el("div", { className: "card__body" },
        (() => { const toolbar = el("div"); buildErrorsToolbar(toolbar,
          { ...state.errors.filters, page_size: state.errors.page_size },
          (filters) => { state.errors.filters = filters; state.errors.page = 1; loadErrors(tableBox); },
          () => { state.errors.filters = {}; state.errors.page = 1; loadErrors(tableBox); },
        ); return toolbar; })(),
      ),
    );
    const tableBox = el("div");

    panel.appendChild(exportBox);
    panel.appendChild(filterCard);
    panel.appendChild(tableBox);

    renderExportControls(exportBox, (fmt) => runExport("errors", fmt));

    loadErrors(tableBox);

    async function loadErrors(box) {
      showLoading(box, t("report.loadingErrors"));
      try {
        const params = { page: state.errors.page, page_size: state.errors.page_size, ...state.errors.filters };
        const env = await api.loadErrors(params);
        renderErrorsTable(box, env, {
          emptyMessage: t("report.noErrors"),
          onNavigate: (page) => { state.errors.page = page; loadErrors(box); },
          onPageSize: (size) => { state.errors.page_size = size; state.errors.page = 1; loadErrors(box); },
        });
      } catch (err) {
        showError(box, err.message || t("report.failedErrors"), { onRetry: () => loadErrors(box) });
      }
    }
  }

  async function runExport(kind, format) {
    try {
      const filters =
        kind === "results" ? state.results.filters : state.errors.filters;
      const filename = await api.onExport(kind, format, { ...filters });
      toast(t("report.downloaded", { file: filename }), { type: "success" });
    } catch (err) {
      toast(err.message || t("report.exportFailed"), { type: "error" });
    }
  }
}