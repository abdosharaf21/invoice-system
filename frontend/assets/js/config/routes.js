/**
 * Centralized route definitions and role permissions.
 *
 * Every hash route the application recognises is listed here. The router
 * compares the URL fragment against the `match` regex to determine which
 * page handler to call. Each entry declares which roles may access it.
 */

import {
  renderLogin,
  renderDashboard,
  renderImports,
  renderImportDetail,
  renderReconciliation,
  renderRunDetail,
  renderReports,
  renderUsers,
  renderAuditLog,
  renderAccount,
  renderSettings,
  renderNotFound,
  renderForbidden,
} from "../pages/index.js";

import { getCurrentRole } from "../auth/store.js";

export const ALL = null; // accessible by any authenticated user

export const routeTable = [
  {
    path: "login",
    match: /^login$/i,
    roles: ALL,
    section: null,
    breadcrumb: "nav.login",
    render: renderLogin,
  },
  {
    path: "dashboard",
    match: /^dashboard$/i,
    section: "nav.overview",
    breadcrumb: "nav.dashboard",
    render: renderDashboard,
  },
  {
    path: "imports",
    match: /^imports$/i,
    section: "nav.operations",
    roles: ["admin", "accountant", "manager"],
    breadcrumb: "nav.imports",
    render: renderImports,
  },
  {
    path: "imports/:id",
    match: /^imports\/(\d+)$/i,
    section: "nav.operations",
    roles: ["admin", "accountant", "manager"],
    breadcrumb: "nav.importDetail",
    render: renderImportDetail,
  },
  {
    path: "reconciliation",
    match: /^reconciliation$/i,
    section: "nav.operations",
    roles: ["admin", "accountant", "manager"],
    breadcrumb: "nav.reconciliation",
    render: renderReconciliation,
  },
  {
    path: "reconciliation/:id",
    match: /^reconciliation\/(\d+)$/i,
    section: "nav.operations",
    roles: ["admin", "accountant", "manager"],
    breadcrumb: "nav.runDetail",
    render: renderRunDetail,
  },
  {
    path: "reports",
    match: /^reports$/i,
    section: "nav.operations",
    roles: ["admin", "accountant", "manager"],
    breadcrumb: "nav.reports",
    render: renderReports,
  },
  {
    path: "users",
    match: /^users$/i,
    section: "nav.administration",
    roles: ["admin"],
    breadcrumb: "nav.users",
    render: renderUsers,
  },
  {
    path: "audit-log",
    match: /^audit-log$/i,
    section: "nav.monitoring",
    roles: ["admin", "manager"],
    breadcrumb: "nav.auditLog",
    render: renderAuditLog,
  },
  {
    path: "settings",
    match: /^settings$/i,
    section: "nav.administration",
    roles: ALL,
    breadcrumb: "nav.settings",
    render: renderSettings,
  },
  {
    path: "settings/:section",
    match: /^settings\/([a-z-]+)$/i,
    section: "nav.administration",
    roles: ALL,
    breadcrumb: "nav.settings",
    render: renderSettings,
  },
  {
    path: "account",
    match: /^account$/i,
    section: "account.nav",
    breadcrumb: "nav.account",
    render: renderAccount,
  },
];

export function resolveRoute(hash) {
  const slug = (hash || "").replace(/^#\/?/, "").toLowerCase();

  if (slug === "") return { route: routeTable.find((r) => r.path === "login"), params: [] };

  for (const route of routeTable) {
    const m = slug.match(route.match);
    if (m) {
      return { route, params: Array.from(m).slice(1) };
    }
  }
  return null;
}

export function canEnter(route) {
  if (!route.roles || route.roles === ALL) return true;
  const role = getCurrentRole();
  return role !== null && route.roles.includes(role);
}

/** True when the current role is allowed for a nav section's minRoles. */
export function canSeeSection(section) {
  if (!section || !section.minRoles) return true;
  const role = getCurrentRole();
  return role !== null && section.minRoles.includes(role);
}

/** Generate the top-level nav items for the sidebar (ordered). Labels are
 * i18n keys resolved at render time by the shell. */
export const navSections = [
  {
    title: "nav.overview",
    items: [
      { label: "nav.dashboard", hash: "#/dashboard", icon: "dashboard" },
    ],
  },
  {
    title: "nav.operations",
    minRoles: ["admin", "accountant", "manager"],
    items: [
      { label: "nav.imports", hash: "#/imports", icon: "import" },
      { label: "nav.reconciliation", hash: "#/reconciliation", icon: "reconciliation" },
      { label: "nav.reports", hash: "#/reports", icon: "reports" },
    ],
  },
  {
    title: "nav.administration",
    minRoles: ["admin"],
    items: [
      { label: "nav.users", hash: "#/users", icon: "users" },
      { label: "nav.settings", hash: "#/settings", icon: "settings" },
    ],
  },
  {
    title: "nav.monitoring",
    minRoles: ["admin", "manager"],
    items: [
      { label: "nav.auditLog", hash: "#/audit-log", icon: "search" },
    ],
  },
];

export const accountNav = {
  items: [
    { label: "nav.account", hash: "#/account", icon: "account" },
    { label: "nav.settings", hash: "#/settings", icon: "settings" },
  ],
};