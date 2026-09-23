# Frontend Capability Audit

Phase scope: inventory the existing backend for user-facing capabilities,
decide which deserve a frontend UI, implement only those that are genuinely
supported, and keep everything else documented as backend-only.

Audited repository: `backend/` (Flask + MySQL, raw SQL) and `frontend/`
(vanilla JS SPA, no framework, no build step).

Audit date: 2026-09-20

---

## 1. Backend capability inventory

| Backend capability | Public API | Auth gate | Already has UI | New frontend needed? |
| --- | --- | --- | --- | --- |
| Authentication / session | `POST /api/auth/login`, `/refresh`, `/logout`, `/me`, password change | any user | Login + Account page | No |
| User administration | `GET/POST /api/users`, `GET/PUT/DELETE /api/users/<id>`, activate, deactivate, password reset | admin | Users page | No |
| Sample file import | `POST /api/imports`, `GET /api/imports/<id>` | admin/accountant/manager | Imports + Import Detail | No |
| Reconciliation runs | `GET/POST /api/reconciliation/runs` | admin/accountant/manager | Reconciliation hub | No |
| Run detail + results/errors | `/api/reconciliation/runs/<id>{,/summary,/results,/errors,/export}` | admin/accountant/manager | Run Detail + Reports | No |
| Email deliveries per run | `/api/reconciliation/runs/<id>/email-deliveries`, resend | admin/accountant/manager | Run Detail (delivery rows/resend) | No |
| Application/company/user settings | `/api/settings/{application,company,user}` | GET any, PUT admin (user self) | Settings page (5 sections) | No |
| Email status + test | `GET /api/email/status`, `POST /api/email/test` | admin | Settings → Email & Notifications | No |
| **Audit trail** | `GET /api/audit-trail/logs` (filters, pagination, sort) | admin/manager | — | **Yes → implemented** |
| Roles & permissions management | (none) | — | — | No — backend incomplete |
| Internal notification inbox | (none) | — | — | No — backend incomplete |
| Tax authority records | repository/model only, no route | — | — | No — internal to reconciliation |
| Invoice staging records | repository/model only, no route | — | — | No — internal to reconciliation |
| Static SPA serving | served by backend (`/`) | — | — | Infrastructure |

### Evidence

- `backend/modules/audit_trail/routes.py` exposes `GET /api/audit-trail/logs`
  gated by `require_admin_or_manager`. Filters: `actor_id`, `action`,
  `resource_type`, `result`, `start_date`, `end_date`; `page`/`page_size`
  (max 200); `sort_by` whitelist `{id, created_at, actor_email, role, action}`.
  Response: `{items, page, page_size, total, total_pages, pages}`.
- `backend/modules/users/validator.py` defines `VALID_ROLES =
  ["admin", "accountant", "manager", "viewer"]`. There is no role or
  permission management API — RBAC is hard-coded per-route decorators
  (`require_admin`, `require_admin_or_manager`, `require_operator`).
- No notification preferences/inbox API exists anywhere. Email surface is
  per-run taxpayer delivery tracking (`email_delivery`, already surfaced in
  Run Detail) and platform email status/test (already surfaced in Settings).
- `modules/tax_authority/` and `modules/invoices/` contain model + repository
  only and are used exclusively by the reconciliation service.

## 2. Audit Log implementation (new)

Only the audit trail merited a new frontend page — it is the one real,
unexposed user-facing capability.

- `frontend/assets/js/services/auditTrail.js` — `listAuditLogs(params)`
  forwarding `page`, `page_size`, `action`, `resource_type`, `result`,
  `actor_id`, `start_date`, `end_date`, `sort_by` (empty values omitted).
- `frontend/assets/js/pages/auditLog.js` — `renderAuditLog(container)`:
  - filter card: Action / Resource type / Result selects, From/To date
    inputs, sort selector, Apply + Reset;
  - enterprise table: Time, Actor (+ role badge), Action, Resource (+ id),
    Result, Request ID, IP address, Details;
  - pagination reusing `components/pagination.js`;
  - loading / empty / error states with retry and empty-state reset;
  - detail modal with full metadata and before/after JSON snapshots;
  - every backend value rendered as text — no markup interpolation
    (XSS-safe by construction, covered by tests).
- `frontend/assets/js/config/routes.js` — route `#/audit-log`, roles
  `["admin", "manager"]`, breadcrumb `nav.auditLog`, new nav section
  "Monitoring" (`nav.monitoring`) visible to admin+manager only.
- `frontend/assets/js/i18n/en.js` + `ar.js` — 46 new keys each, exact parity
  (both dictionaries now have 590 keys), AR renders RTL via existing i18n core.

No backend changes were required — the endpoint already existed in full.

## 3. Roles & Permissions — not built (backend incomplete)

Decision: **no UI, no invented endpoints.** There is no role CRUD and no
permission management API; roles are static strings and RBAC is hard-coded
per route. Building a "Roles & Permissions" page would require fabricating
backend endpoints, which is out of scope. Role assignment per user already
exists in the Users page.

Future backend work (unblocks a future UI): a roles/permissions resource
(`GET/PUT /api/roles...`) that maps roles to route capabilities.

## 4. Notifications — not built (already covered or backend incomplete)

Decision: **no dedicated Notifications page.**
- No internal-user notification inbox/read-unread/preferences exists.
- The real email surface is already exposed: per-run taxpayer email
  deliveries + resend in Run Detail, and admin-only email status/test in
  Settings → Email & Notifications.

Future backend work: an internal notification service + inbox endpoints.

## 5. Only changes made in this phase

Files added:
- `frontend/assets/js/services/auditTrail.js`
- `frontend/assets/js/pages/auditLog.js`
- `frontend/test/audit-log.test.js` (13 tests)

Files changed:
- `frontend/assets/js/pages/index.js` (export `renderAuditLog`)
- `frontend/assets/js/config/routes.js` (route + Monitoring nav section)
- `frontend/assets/js/i18n/en.js`, `i18n/ar.js` (46 keys each)
- `frontend/test/routes.test.js` (+1 nav-section gating test)

Files deliberately untouched: Settings UI, all existing pages/components,
all back-end code, migrations, and git working-tree state.

## 6. Summary of changes

- New Admin/Manager "Audit Log" page wired into the router, sidebar
  (Monitoring section), breadcrumbs and both locales.
- Reused existing pagination, modal, badge, formatting and i18n primitives;
  no new dependencies, no CSS, no backend changes.

## 7. Test plan and commands

```
cd frontend && npm test                     # node --test "test/*.test.js"
cd backend && ../.venv/bin/python -m pytest -q
```

Coverage added for the new page: service param forwarding, render of
toolbar/table/pagination, filter apply (page reset), reset, empty/error
states, XSS-literal rendering, badge allow-listing, detail modal JSON,
route/roles gating, Monitoring nav visibility, and EN/AR i18n parity. No
existing tests were removed or weakened.

## 8. Verification

- Frontend test suite: see Section 7 — passed (234/234 including 14 new).
- Backend regression: `706 passed, 11 skipped` — unchanged (no backend edits).
- Live HTTP check against a running instance: authenticated admin request to
  `GET /api/audit-trail/logs` returns the pagination envelope; a non-privileged
  role receives 403 (see the HTTP verification logged in the final report).
- Real-browser automation: **not available in this environment** (the
  Playwright module is not installed and dependency installation is out of
  scope). Verified instead with (a) the full `node:test` DOM-stub suite and
  (b) a headless-Chromium load of the served SPA to confirm the app shell and
  audit page mount without runtime errors. See the final report for details.

## 9. Reviewable change

The changes introduced by this phase are limited to the six frontend files
listed in Section 5 (added: `services/auditTrail.js`, `pages/auditLog.js`,
`test/audit-log.test.js`; modified: `pages/index.js`, `config/routes.js`,
`test/routes.test.js`) plus `i18n/en.js`/`i18n/ar.js` and this document.

Note: the working tree on the branch already contained uncommitted work from
earlier stages of `phase-6-frontend`. Only this phase's additions/modifications
should be reviewed as part of this deliverable:

```
git diff -- frontend/assets/js/pages/auditLog.js frontend/assets/js/services/auditTrail.js frontend/test/audit-log.test.js
git diff -- frontend/assets/js/config/routes.js frontend/assets/js/pages/index.js frontend/test/routes.test.js
```

## 10. Final report

The complete 9-part phase report is provided in the session transcript
(title/objective, deliverables, test results, changes, verification, scope,
risks, next phase, effort).