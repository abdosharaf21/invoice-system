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
  renderAccount,
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
    breadcrumb: "Login",
    render: renderLogin,
  },
  {
    path: "dashboard",
    match: /^dashboard$/i,
    section: "Overview",
    breadcrumb: "Dashboard",
    render: renderDashboard,
  },
  {
    path: "imports",
    match: /^imports$/i,
    section: "Operations",
    roles: ["admin", "accountant", "manager"],
    breadcrumb: "Imports",
    render: renderImports,
  },
  {
    path: "imports/:id",
    match: /^imports\/(\d+)$/i,
    section: "Operations",
    roles: ["admin", "accountant", "manager"],
    breadcrumb: "Import Detail",
    render: renderImportDetail,
  },
  {
    path: "reconciliation",
    match: /^reconciliation$/i,
    section: "Operations",
    roles: ["admin", "accountant", "manager"],
    breadcrumb: "Reconciliation",
    render: renderReconciliation,
  },
  {
    path: "reconciliation/:id",
    match: /^reconciliation\/(\d+)$/i,
    section: "Operations",
    roles: ["admin", "accountant", "manager"],
    breadcrumb: "Run Detail",
    render: renderRunDetail,
  },
  {
    path: "reports",
    match: /^reports$/i,
    section: "Operations",
    roles: ["admin", "accountant", "manager"],
    breadcrumb: "Reports",
    render: renderReports,
  },
  {
    path: "users",
    match: /^users$/i,
    section: "Administration",
    roles: ["admin"],
    breadcrumb: "Users",
    render: renderUsers,
  },
  {
    path: "account",
    match: /^account$/i,
    section: "Account",
    breadcrumb: "My Account",
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

/** Generate the top-level nav items for the sidebar (ordered). */
export const navSections = [
  {
    title: "Overview",
    items: [
      { label: "Dashboard", hash: "#/dashboard", icon: "dashboard" },
    ],
  },
  {
    title: "Operations",
    minRoles: ["admin", "accountant", "manager"],
    items: [
      { label: "Imports", hash: "#/imports", icon: "import" },
      { label: "Reconciliation", hash: "#/reconciliation", icon: "reconciliation" },
      { label: "Reports", hash: "#/reports", icon: "reports" },
    ],
  },
  {
    title: "Administration",
    minRoles: ["admin"],
    items: [
      { label: "Users", hash: "#/users", icon: "users" },
    ],
  },
];

export const accountNav = {
  items: [
    { label: "My Account", hash: "#/account", icon: "account" },
  ],
};