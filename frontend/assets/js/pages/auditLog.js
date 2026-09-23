/**
 * Audit Log (admin + manager) — immutable trail of user and system actions,
 * backed by GET /api/audit-trail/logs. Filterable by action, resource type,
 * result and date range, sortable and paginated. All values from the backend
 * are rendered as safe text — never interpolated into markup.
 */

import { el, clear, showLoading, showError, showEmpty } from "../utils/dom.js";
import { LIMITS } from "../config.js";
import { listAuditLogs } from "../services/auditTrail.js";
import { openModal } from "../components/modal.js";
import { renderPagination } from "../components/pagination.js";
import { formatDateTime, roleLabel, roleClassToken } from "../utils/format.js";
import { t } from "../i18n/index.js";

const ACTIONS = ["login", "logout", "create", "update", "delete", "view", "import", "reconcile", "other"];
const RESOURCE_TYPES = ["auth", "user", "company", "setting", "import", "reconciliation", "email_delivery", "email"];
const RESULTS = ["success", "failure"];
const SORTS = ["created_at", "actor_email", "action", "role"];

const EMPTY_FILTERS = { action: "", resource_type: "", result: "", start_date: "", end_date: "" };

export async function renderAuditLog(container) {
  clear(container);
  document.body.classList.remove("login-body");

  const state = {
    filters: { ...EMPTY_FILTERS },
    sort_by: "created_at",
    page: 1,
    page_size: LIMITS.defaultPageSize,
  };

  const box = el("div");

  container.appendChild(
    el("div", { className: "page-head" },
      el("div", null,
        el("h1", { className: "page-title" }, t("auditLog.title")),
        el("div", { className: "page-head__meta" }, t("auditLog.meta")),
      ),
      el("div", { className: "page-head__actions" },
        el("button", { className: "btn btn-secondary", onClick: () => load(box) }, t("common.refresh")),
      ),
    ),
  );

  const toolbarWrap = el("div");
  container.appendChild(toolbarWrap);
  container.appendChild(box);

  buildToolbar(toolbarWrap, state, onFiltersApplied, () => {
    state.filters = { ...EMPTY_FILTERS };
    state.sort_by = "created_at";
    state.page = 1;
    rebuildToolbar();
    load(box);
  });

  await load(box);

  function onFiltersApplied() {
    state.page = 1;
    load(box);
  }

  function rebuildToolbar() {
    buildToolbar(toolbarWrap, state, onFiltersApplied, () => {
      state.filters = { ...EMPTY_FILTERS };
      state.sort_by = "created_at";
      state.page = 1;
      rebuildToolbar();
      load(box);
    });
  }

  async function load(target) {
    showLoading(target, t("auditLog.loading"));
    try {
      const params = {
        page: state.page,
        page_size: state.page_size,
        sort_by: state.sort_by,
        ...state.filters,
      };
      const env = await listAuditLogs(params);
      clear(target);
      if (!env || !Array.isArray(env.items) || env.items.length === 0) {
        showEmpty(target, t("auditLog.noEntries"), {
          action: stateHasFilters(state) ? t("common.reset") : null,
          onAction: () => {
            state.filters = { ...EMPTY_FILTERS };
            state.page = 1;
            rebuildToolbar();
            load(box);
          },
        });
        return;
      }
      target.appendChild(renderTable(env.items));
      const pager = el("div");
      target.appendChild(pager);
      renderPagination(pager, env, (page) => { state.page = page; load(box); }, (size) => {
        state.page_size = size;
        state.page = 1;
        load(box);
      });
    } catch (err) {
      showError(target, err.message || t("auditLog.failedLoad"), { onRetry: () => load(target) });
    }
  }
}

/**
 * Mount (or rebuild in place) the filter toolbar. Reads/writes the page state
 * through the populated DOM controls so a rebuild always shows current values.
 */
function buildToolbar(wrap, state, onChange, onReset) {
  clear(wrap);

  const actionSel = selectControl(ACTIONS, state.filters.action, t("auditLog.anyAction"), "action", actionLabel);
  const resourceSel = selectControl(RESOURCE_TYPES, state.filters.resource_type, t("auditLog.anyResource"), "resource_type", resourceTypeLabel);
  const resultSel = selectControl(RESULTS, state.filters.result, t("auditLog.anyResult"), "result", resultLabel);
  const sortSel = selectControl(SORTS, state.sort_by, null, "sort_by", sortLabel);

  const start = el("input", { className: "input", type: "date", value: state.filters.start_date || "", "data-field": "start_date", "aria-label": t("auditLog.fromDate") });
  const end = el("input", { className: "input", type: "date", value: state.filters.end_date || "", "data-field": "end_date", "aria-label": t("auditLog.toDate") });

  const apply = el("button", { className: "btn btn-primary", type: "button", "data-field": "apply" }, t("common.apply"));
  const reset = el("button", { className: "btn btn-ghost", type: "button", "data-field": "reset" }, t("common.reset"));

  apply.addEventListener("click", () => {
    state.filters = {
      action: actionSel.value || "",
      resource_type: resourceSel.value || "",
      result: resultSel.value || "",
      start_date: start.value || "",
      end_date: end.value || "",
    };
    state.sort_by = sortSel.value || "created_at";
    onChange();
  });

  reset.addEventListener("click", () => {
    state.filters = { ...EMPTY_FILTERS };
    state.sort_by = "created_at";
    onReset();
  });

  const card = el("div", { className: "card filter-card" },
    el("div", { className: "card__header" },
      el("div", { className: "section-title" }, t("auditLog.filtersTitle"))),
    el("div", { className: "card__body" },
      el("div", { className: "audit-filters" },
        el("div", { className: "field-row" },
          el("div", { className: "field" },
            el("label", null, t("auditLog.filterAction")),
            actionSel,
          ),
          el("div", { className: "field" },
            el("label", null, t("auditLog.filterResourceType")),
            resourceSel,
          ),
          el("div", { className: "field" },
            el("label", null, t("auditLog.filterResult")),
            resultSel,
          ),
          el("div", { className: "field" },
            el("label", null, t("auditLog.sortBy")),
            sortSel,
          ),
        ),
        el("div", { className: "field-row" },
          el("div", { className: "field" },
            el("label", null, t("auditLog.fromDate")),
            start,
          ),
          el("div", { className: "field" },
            el("label", null, t("auditLog.toDate")),
            end,
          ),
        ),
        el("div", { className: "form-actions" }, apply, reset),
      ),
    ),
  );

  wrap.appendChild(card);
}

/** Generic select with an optional "all" placeholder and per-value labels. */
function selectControl(values, current, placeholder, field, labelFn) {
  const opts = [];
  if (placeholder) opts.push(el("option", { value: "", selected: "" === String(current || "") ? "" : null }, placeholder));
  for (const v of values) {
    opts.push(el("option", { value: v, selected: String(v) === String(current || "") ? "" : null }, labelFn ? labelFn(v) : v));
  }
  return el("select", { className: "select", "data-field": field }, ...opts);
}

function stateHasFilters(state) {
  return Object.values(state.filters).some((v) => v !== "");
}

function renderTable(items) {
  const table = el("table", { className: "etable" },
    el("thead", null, el("tr", null,
      el("th", null, t("auditLog.thTime")),
      el("th", null, t("auditLog.thActor")),
      el("th", null, t("auditLog.thAction")),
      el("th", null, t("auditLog.thResource")),
      el("th", null, t("auditLog.thResult")),
      el("th", null, t("auditLog.thRequestId")),
      el("th", null, t("auditLog.thIp")),
      el("th", null, t("common.actions")),
    )),
  );
  const tbody = el("tbody");
  for (const entry of items) {
    tbody.appendChild(
      el("tr", null,
        el("td", { className: "text-sm text-secondary" }, formatDateTime(entry.created_at)),
        el("td", null,
          el("div", { className: "user-cell" },
            el("span", null, entry.actor_email || "—"),
            entry.role ? el("span", { className: `badge badge--${roleClassToken(entry.role)}` }, roleLabel(entry.role)) : null,
          ),
        ),
        el("td", null, el("span", { className: "badge badge--plain" }, actionLabel(entry.action))),
        el("td", null,
          el("div", null, resourceTypeLabel(entry.resource_type)),
          entry.resource_id != null ? el("span", { className: "mono text-sm text-secondary" }, `#${entry.resource_id}`) : null,
        ),
        el("td", null, el("span", { className: `badge badge--${resultToken(entry.result)}` }, resultLabel(entry.result))),
        el("td", { className: "mono text-sm" }, entry.request_id || "—"),
        el("td", { className: "mono text-sm" }, entry.ip_address || "—"),
        el("td", null,
          el("button", { className: "btn btn-ghost btn-sm", type: "button", onClick: () => openDetail(entry) }, t("auditLog.view")),
        ),
      ),
    );
  }
  table.appendChild(tbody);
  return el("div", { className: "card card--table" },
    el("div", { className: "table-wrap" }, table),
  );
}

function openDetail(entry) {
  const rows = [
    ["audit.createdAt", formatDateTime(entry.created_at)],
    ["audit.actorEmail", entry.actor_email || "—"],
    ["audit.role", entry.role ? roleLabel(entry.role) : "—"],
    ["audit.actorId", entry.actor_id != null ? String(entry.actor_id) : "—"],
    ["audit.actorType", actorTypeLabel(entry.actor_type)],
    ["audit.action", actionLabel(entry.action)],
    ["audit.resourceType", resourceTypeLabel(entry.resource_type)],
    ["audit.resourceId", entry.resource_id != null ? String(entry.resource_id) : "—"],
    ["audit.result", resultLabel(entry.result)],
    ["audit.companyId", entry.company_id != null ? String(entry.company_id) : "—"],
    ["audit.requestId", entry.request_id || "—"],
    ["audit.ipAddress", entry.ip_address || "—"],
  ];

  const body = el("div", null,
    el("dl", { className: "dl" }, ...rows.map(([k, v]) =>
      el("div", null, el("dt", null, t(k)), el("dd", null, v)))),
    el("div", { className: "section-title" }, t("audit.metadata")),
    el("div", null, prettyJson(entry.metadata)),
    el("div", { className: "section-title" }, t("audit.beforeState")),
    el("div", null, prettyJson(entry.before_state)),
    el("div", { className: "section-title" }, t("audit.afterState")),
    el("div", null, prettyJson(entry.after_state)),
  );

  openModal({
    title: t("audit.detailTitle", { id: entry.id }),
    body,
    actions: [
      { label: t("common.close"), variant: "secondary", onClick: (m) => m.close() },
    ],
  });
}

function prettyJson(value) {
  if (value === undefined || value === null) return el("span", { className: "text-muted" }, t("audit.noValue"));
  return el("pre", { className: "audit-json" }, JSON.stringify(value, null, 2));
}

/** Human label for an audit action; unknown values render verbatim as text. */
function actionLabel(action) {
  if (action === null || action === undefined) return "—";
  const key = `audit.action.${action}`;
  const out = t(key);
  return out === key ? String(action) : out;
}

/** Human label for an audit result; unknown values render verbatim. */
function resultLabel(result) {
  if (result === null || result === undefined) return "—";
  const key = `audit.result.${result}`;
  const out = t(key);
  return out === key ? String(result) : out;
}

/** Human label for a resource type; unknown values render verbatim. */
function resourceTypeLabel(type) {
  if (type === null || type === undefined) return "—";
  const key = `audit.resource.${type}`;
  const out = t(key);
  return out === key ? String(type) : out;
}

/** Human label for an actor type (user / system). */
function actorTypeLabel(type) {
  if (type === null || type === undefined) return "—";
  const key = `audit.actorType.${type}`;
  const out = t(key);
  return out === key ? String(type) : out;
}

/** Safe CSS token for a result badge; unknown values fall back to neutral. */
function resultToken(result) {
  if (result === "success") return "ok";
  if (result === "failure") return "failed";
  return "neutral";
}

/** Human label for a sort column. */
function sortLabel(sort) {
  const key = `auditLog.sort.${sort}`;
  const out = t(key);
  return out === key ? sort : out;
}