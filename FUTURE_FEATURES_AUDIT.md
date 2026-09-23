# Future Features Audit

Audit of what the E-Invoice & Reconciliation platform currently ships, what
the frontend can and cannot do, and which future product features the system
should (and should **not**) build next.

**Status:** AUDIT ONLY. No product features were implemented in this phase,
no code was changed, and the regression baseline is unchanged.

- Audit date: 2026-09-20
- Repository: `~/e-invoice-system/invoice-system` (GitHub `abdosharaf21/invoice-system`)
- Backend: Flask + MySQL 8, raw SQL connectors; tests `pytest`
- Frontend: Vanilla JS SPA (no build step, no framework); tests `node:test`
- Production deliverables complete through **Phase 20** (`PHASE20_REPORT.md`)

---

## 1. Executive Summary

The platform is a **single-tenant-per-company, role-scoped** VAT invoice
reconciliation and tax-reporting tool. It imports accounting files
(CSV/XLSX), imports tax-authority invoices, runs deterministic
reconciliation, emails per-taxpayer discrepancy summaries, exposes reports
and exports, keeps a full user/company audit trail, and ships a fully
localised (EN/AR) SPA.

The backend is deliberately **read/export focused** for its operational
surface and **writes restricted to admins**; the SPA exposes everything the
backend currently offers. The notable product gaps are not UI polish — they
are **missing backend capabilities**: scheduling/automation, user-facing
notifications, role & permission administration, invoice/tax-document
submission workflows, and administrative monitoring beyond what the audit
log offers.

Because Settings and the Audit Log were completed and are now FINAL, this
audit treats them as closed. Future work must not redesign either.

**Bottom line:** the most valuable next features are (1) scheduled /
automated reconciliation, (2) an in-app notifications centre, and (3) role
& permission administration. All three are gated on new backend work first.

---

## 2. Current Product Capability Inventory

### Backend modules & their route surface (all under `/api/v1` + `/api` alias)

| Module | Routes (methods) | Roles | Notes |
|---|---|---|---|
| `auth` | `/auth/login`, `/auth/logout`, `/auth/refresh`, `/auth/logout-refresh`, `/auth/me`, `/auth/change-password` | all authenticated; change-password all | JWT access+refresh, refresh-token blocklist, deactivated-account rejection |
| `users` | `/users/` (GET,POST), `/users/<id>` (GET,PUT), `/users/<id>/password`, `/activate`, `/deactivate`, `/users/<id>` (DELETE) | admin for management; viewer can read own | Roles are static (`admin|accountant|manager|viewer`) |
| `audit_trail` | `GET /audit-trail/logs` | admin, manager | filters, sorting whitelist, pagination ≤200, export-ready contract |
| `imports` | `POST /imports`, `GET /imports/<batch_id>` | admin, accountant, manager | CSV/XLSX, batch + row errors, recovery of interrupted runs |
| `reconciliation` | POST/GET `/runs`, GET `/runs/<id>`, `/summary`, `/results`, `/errors`, `/results/export`, `/errors/export`, `/email-deliveries`, `/email-deliveries/<id>/resend` | admin, accountant, manager | deterministic engine, no fuzzy matching, tolerance per run |
| `companies` | `GET/PUT /settings/company` (via settings) | admin (write), all (read own company) | company profile: name, VAT/TRN, currency, tax rate, fiscal year start |
| `settings` | `GET/PUT /application`, `GET /application/all`, `GET/PUT /user` | admin (application writes); per-user prefs | app settings (currency, language, theme, date/number format, pagination) + per-user prefs |
| `email` | `GET /email/status`, `POST /email/test` | admin only | status + test blast; all other email features are triggered by runs |
| `imports`/`invoices`/`tax_authority` | **model/repository only, no public routes** | — | internal `TaxInvoice`, `Invoice`, `TaxInvoiceItem` models — used only by import + reconcile engine |
| `static` | `GET /`, `/index.html`, `/assets/<path>` | all | serves the built SPA |

### Frontend routes & role gating (`frontend/assets/js/config/routes.js`)

| Route | Roles | Nav section |
|---|---|---|
| `#/login` | all | — |
| `#/dashboard` | admin, accountant, manager, viewer | Overview |
| `#/imports`, `#/imports/:id` | admin, accountant, manager | Operations |
| `#/reconciliation`, `#/reconciliation/:id` | admin, accountant, manager | Operations |
| `#/reports` | admin, accountant, manager | Operations |
| `#/users` | admin | Administration |
| `#/settings`, `#/settings/:section` | all | Administration |
| `#/audit-log` | admin, manager | Monitoring |
| `#/account`, `#/account/settings` | all | Account |

Role matrix is enforced both in the SPA (route gating + nav hiding) and in
the backend (RBAC decorators).

### Cross-cutting infrastructure (not product features, audit documented only)

- JWT auth with access+refresh tokens, token blocklist, request-ID
  correlation, rate limiting, audit trail on every authz event.
- Idempotency and safety: deterministic matching contract, exact Decimal
  money compare, per-run tolerance, no fuzzy matching (intentional).
- DB: migration catalog with SHA-256 checksums, integrity constraints,
  performance indexes, backup/restore, schema verification.
- Password hashing, request validation, XSS-safe rendering, CSP enabled.

---

## 3. Existing Frontend Gaps

These are UI capabilities the backend can already serve but the SPA does
not expose — **the cheapest wins** because they need no backend work:

| Gap | Backend support? | Effort |
|---|---|---|
| Audit Log **enrichment** (metadata JSON viewer is done; pre/post diffs, actor email linking is done; no deeper search/export download button in the UI) | partial | Low |
| **Export download buttons** wired in the browser for the already-exposed CSV/XLSX endpoints (imports, reports, audit log) | yes | Low |
| **Per-user session list / "log out everywhere"** — refresh-token blocklist exists server-side, but there is no "sessions" page | backend partial | Medium |
| **Company flag in reconciliation UI** for multi-company-conscious display | backend returns company data | Low |
| Accounting-file **corrected-format display** after re-import (UI shows batch; per-row diff preview not present) | backend has row errors | Medium |

**Frontend hard limits (documented, already accepted):** interactive browser
E2E automation (drag/drop, real canvas) is not covered by an installed
Playwright harness in this environment; the functional unit suite + live
HTTP checks stand in. `viewer` accounts are blocked from operations by the
backend; the UI correctly hides those sections.

---

## 4. Backend Capabilities Not Yet Exposed

These exist as **repository/model/services** but have **no public API
surface** and therefore no frontend:

| Capability | Where it lives | Why unexposed |
|---|---|---|
| `TaxInvoice` / `TaxInvoiceItem` full data model (submission status, tax IDs, item-level VAT) | `backend/modules/tax_authority/` | Internal to import + reconcile; no invoice viewer API exists |
| Accounting `Invoice` model incl. per-item data | `backend/modules/invoices/` | Used only by import + engine |
| **Submission-status lifecycle** (`draft → submitted`) on tax invoices | `model.py` | No endpoint lets a user mark an invoice submitted to the tax authority |
| Per-taxpayer delivery records (`email_deliveries`) | `reconciliation` repository | Only exposed via `/email-deliveries` list + resend; no "notification centre" mailbox |

**Design note:** there is intentionally no invoice CRUD API. Invoices are
rendered as internal records produced by imports — not user-editable
documents. Any "invoice management" future feature must decide whether the
system should *own* invoices (new scope) or keep them read-only artefacts.

---

## 5. Future Product Features (candidate list with evaluation)

| # | Feature | Current state | Backend needed? | Frontend needed? | Business purpose | Complexity | Recommendation |
|---|---|---|---|---|---|---|---|
| F1 | **Scheduled reconciliation** (cron at month-end / daily) | None — runs are manual, synchronous | Yes (scheduler, background worker, run-queue table) | Yes (schedule config + "next run" indicator) | Automate month-end close; remove manual step | **High** | **Build (priority)** — highest value |
| F2 | **In-app notifications centre** (unread badge, read/unread) | Emails only to taxpayers; no per-user inbox | Yes (notifications tables + API + unread state) | Yes (bell + list page) | Keep operators informed without depending on SMTP | **Medium** | **Build (priority)** — gated on backend first |
| F3 | **Role & permission administration** (create roles, assign permissions, manage role→feature map) | Roles static in validator; RBAC hard-coded per route | Yes (roles/permissions tables + management APIs) | Yes (admin role manager screen) | Let organisations match their own operating model | **High** | **Build** — but scoped carefully; RBAC today is proven and safe |
| F4 | **Invoice / tax-document submission workflow** (draft → submitted → acknowledged w/ submission-ref) | `submission_status` field exists, unexposed | Yes (submit/ack endpoints + status transitions + validation) | Yes (invoice workspace page) | Demonstrate control over tax-authority submissions | **High** | **Build later** — new product scope, requires domain design |
| F5 | **User invitations & self-registration on-boarding** (invite link, reset-password flow) | No invite flow; admin creates users; JWT blocklist exists | Yes (invite tokens, reset flow) | Yes (invite UI, reset UI) | Reduce admin burden, enable growth | **Medium** | **Build later** |
| F6 | **Multi-company / tenancy management** (create org, switch company, per-company grants) | Single company per environment; company settings exist but single-row | Yes (company CRUD, membership table, scope re-wiring) | Yes (company switcher) | Serve agencies/group structures | **High** | **Long-term** — touches every query's tenant scoping |
| F7 | **Audit-log retention & archival** (purge/export old logs, retention policy setting) | Full log only; no expiry | Yes (retention config + archival job) | Yes (retention settings UI) | Compliance + data-size control | Low/Med | **Build** — pairs with F1 scheduler |
| F8 | **Email configuration UI** (edit SMTP/from/preferences in-app) | Email is env/SMTP config; admin status+test only | Yes (config persistence + validator) | Yes (Email section) | Operations self-service | Medium | **Deferred** — is a dedicated, separate task (see `EMAIL_CONFIGURATION_AUDIT.md`) |
| F9 | **Reports scheduler** (email a report monthly) | Reports are run-finished snapshots; no scheduling | Yes (same scheduler as F1) | Yes (schedule config) | Recurring compliance reporting | High | **Build after F1** (shares scheduler infra) |
| F10 | **Bulk re-import/diff workflow** (correct file, re-run, show delta) | Single batch import exists; no "replace" semantics | Partial (batch import exists) | Medium | Support iterative correction | Medium | Build later |
| F11 | **Dark-mode / appearance** | Theme setting exists (light/dark) in Settings | Yes (exposed) | Mostly done | Preference | Low | **Already largely present** — verify |
| F12 | **Currency conversion / multi-currency reconciliation** | `default_currency` setting only; engine compares in one currency | Yes (FX tables) | Yes (FX UI) | Trading across currencies | High | **Long-term** — money compare is exact, mixing currencies is complex |
| F13 | **API tokens / service accounts** (machine-to-machine) | JWT only for humans | Yes (token issuance scope, role) | No | Integrations | Medium | Long-term |
| F14 | **Tax rate versioning / rule explorer** | `default_tax_rate` single value; contract is deterministic | Yes (rate table, effective dates) | Yes | Handle rate changes across fiscal years | Medium | Long-term |

---

## 6. Backend Prerequisites (before the chosen builds)

Every high-value feature has a backend dependency. Order of implementation:

1. **Scheduler infra** (F1/7/9): a `scheduled_jobs` table, a lightweight
   background loop (no heavy framework needed; repo has no scheduler today),
   locking against overlapping runs, and job-state audit entries.
2. **Notifications infra** (F2): `notifications` table (user_id, type,
   payload, read_at, created_at) + upsert API + unread badge contract;
   reuse the existing delivery/audit patterns.
3. **Roles & permissions infra** (F3): `roles` and `role_permissions`
   tables + management API; migrate the RBAC decorator to read from DB with
   a validated default (current hard-coded set as baseline); run an
   idempotent seed so existing behaviour is unchanged.
4. **Retention config** (F7): key in `application_settings` + archival job.

Each of these must preserve today's 706-passing backend suite and 234
passing frontend tests; the RBAC migration in particular must be proven
behaviourally identical before rollout.

---

## 7. Future Features — Should NOT Build (and why)

| Candidate | Why not |
|---|---|
| **General invoice CRUD / free-form invoice editing** | Invoices are reconciliated artefacts with exact matching against the tax authority; letting users edit them breaks the determinism guarantee and the audit story. Out of product scope unless the product pivots to "invoice authoring". |
| **Fuzzy / "smart guess" matching** | Explicitly rejected in the reconciliation contract; introduces non-reproducible results and audit ambiguity. |
| **Anonymous / unauthenticated access to any operational page** | AuthZ is the backbone; this would be a security regression. All routes require auth. |
| **Bypassing email for notification (silent, unlogged)** | Every email is recorded in `email_deliveries`. Features must never add silent side channels. |
| **Self-service password reset without control** | No reset flow exists on purpose; adding public reset requires an invite/email-verification control first (see F5). |
| **`viewer` reaching reconciliation reports** | Backend enforces admin/accountant/manager; viewer stays read-only. |
| **Email-configuration merged into this audit's Settings** | Already declared a dedicated separate task; merging would violate the "Settings is FINAL" boundary. |

---

## 8. Internal Infrastructure vs Product Features

Do not confuse engineering foundations with shippable features. The following
exist and are **infrastructure, not user-facing product capabilities**:
idempotency, rate limiting, JWT revocation/blocklist, request IDs,
transactions, integrity constraints, migrations + checksums, backup/restore,
schema verification, password hashing, exact-Deci`Money` compare policy,
per-run tolerance, and the audit trail itself)Skip counting any of these as
"future features" — they are either done or maintenance.

---

## 9. Proposed Roadmap

### Near term (no backend work; UI/ops wins)
1. Wire CSV/XLSX export download buttons into the existing Audit Log and
   Reports/Imports pages (backend endpoints already exist).
2. Add a small "next run scheduled" + run-history summary card on the
   dashboard from existing run data.

### Medium term (new backend + frontend; the recommended build sequence)
3. **Notifications centre** (F2) — backend first, then unread badge + page.
4. **Scheduled reconciliation + retention** (F1, F7) — shared scheduler infra,
   then wiring both.
5. **Role & permission administration** (F3) — best-effort on top of the
   RBAC-safe refactor (defaults preserved).

### Long term
6. Invoice submission workflow (F4), user invitations/reset (F5),
   reports scheduler (F9), API tokens (F13).

### Optional / niche
7. Multi-company tenancy (F6), multi-currency (F12), tax-rate versioning
   (F14), bulk re-import delta (F10).

---

## 10. Dependencies

- Python 3 (backend) + MySQL 8; no new runtime deps required for the audit.
- Frontend has zero npm runtime deps (Vanilla JS SPA) — keep it that way;
  new features build on existing `services/` + `pages/` + `i18n` patterns.
- Any scheduler (F1) must avoid adding a heavyweight dependency; the repo
  currently has no background scheduler and prefers minimal, auditable code.
- Email/notifications require SMTP (already wired); user-facing
  notifications (F2) are intentionally NOT SMTP-dependent.

---

## 11. Risks / Complexity

| Risk | Mitigation |
|---|---|
| New scheduler adds background concurrency to a transactional codebase | Use run-locking + audit entries; keep jobs idempotent; same pattern as `recover_interrupted` |
| RBAC refactor (F3) could regress authorisation | Ship as a drop-in behavioural pass; full backend suite must stay 706/11; keep hard-coded defaults as seed |
| Invoice submission workflow expands product scope | Treat as separately-designed new domain; do not bolt onto reconciliation |
| Multi-currency / rounding drift | Keep exact Decimal policy; only adopt with explicit FX rules per run |
| Frontend `viewer` limitations documented | Accept as a product decision; don't weaken backend checks |

---

## 12. Final Recommendations

1. **Do not** expand Settings or the Audit Log — both are FINAL; future work
   goes to new surfaces.
2. Build **scheduling + notifications** first; they unlock the most recurring
   business value with the least risk to the deterministic core.
3. Keep the **no-fuzzy, exact-money, fully-audited** core as the product's
   non-negotiable backbone.
4. Everything must keep frontend **234 passed / 0 failed** and backend
   **706 passed / 11 skipped**.

---

## 13. Explicit Non-Goals of This Phase

- No code changes (frontend or backend), no migrations, no DB data changes.
- No new dependencies, no new routes/APIs/UI/page/nav, no Settings or
  Audit Log redesign.
- No auth/authorisation changes, no email/SMTP changes, no messages sent.
- No bug fixes (open issues are logged separately, not fixed inline).
- No git commit/push/branch/reset/stash/clean/revert/discard.
- Tests were run only to confirm the baseline; they were not modified to
  match expected numbers.

---

## 14. Current Regression Baseline

Run to prove nothing changed in this audit phase:

```
frontend:  npm test            → 234 passed / 0 failed
backend:   pytest -q           → 706 passed / 11 skipped
```

Both suites were executed during this phase with identical results to the
previous phase. No source files were touched; the only artifact produced is
this audit document.

---

## Evaluation table (consolidated)

| Feature | Current state | Backend needed? | Frontend needed? | Business purpose | Complexity | Recommendation |
|---|---|---|---|---|---|---|
| Scheduled reconciliation | none — manual runs | yes (scheduler+queue) | yes | automate month-end | High | **Build (priority)** |
| Notifications centre | email-only, no inbox | yes | yes | operator awareness | Medium | **Build (priority)** |
| Role & permission admin | static roles, hard-coded RBAC | yes | yes | organisation fit | High | Build (safe refactor first) |
| Invoice submission workflow | status field exists, unexposed | yes | yes | tax submissions | High | Build later |
| User invites + reset flow | none | yes | yes | growth/onboarding | Medium | Build later |
| Multi-company tenancy | single-company | yes | yes | groups/agencies | High | Long-term |
| Audit-log retention | full log, no expiry | yes | yes | compliance/size | Low/Med | Build (with scheduler) |
| Email configuration UI | env/SMTP, admin status+test | yes | yes | ops self-service | Medium | **Deferred — separate task** |
| Reports scheduler | run-snapshot only | yes | yes | recurring reports | High | After F1 |
| Multi-currency | single default currency | yes | yes | FX trading | High | Long-term |
| API tokens / service accounts | JWT only | yes | no | integrations | Medium | Long-term |
| Tax-rate versioning | single default rate | yes | yes | fiscal-year changes | Medium | Long-term |
| Bulk re-import delta | batch import only | partial | yes | iterative correction | Medium | Build later |
| Dark-mode / appearance | theme setting exists | exposed | mostly done | preference | Low | **Verify existing (near-done)** |

---

**This phase is an audit only. No product features were implemented.**
