/**
 * Page registry — re-exports every page renderer as the router's single import
 * point (the route table imports from here).
 */

export { renderLogin } from "./login.js";
export { renderDashboard } from "./dashboard.js";
export { renderImports } from "./imports.js";
export { renderImportDetail } from "./importDetail.js";
export { renderReconciliation } from "./reconciliation.js";
export { renderRunDetail } from "./runDetail.js";
export { renderReports } from "./reports.js";
export { renderUsers } from "./users.js";
export { renderAuditLog } from "./auditLog.js";
export { renderAccount } from "./account.js";
export { renderSettings } from "./settings.js";
export { renderNotFound, renderForbidden } from "./errors.js";