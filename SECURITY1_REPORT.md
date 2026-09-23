# SECURITY-1 Report — User Tenant Isolation Remediation

**Status: COMPLETE · repository:** `~/e-invoice-system/invoice-system`
**Date:** 2026-09-18
**Baseline:** Phase 18 (PRODUCTION-EQUIVALENT VALIDATION) confirmed the defect; this phase remediates it.

| Verdict | Meaning |
|---|---|
| **PASS** | Executed and machine-verified. |
| **FAIL** | A check did not pass. |
| **N/A** | Not applicable / not verifiable in this environment. |
| **DEFERRED** | Recorded but intentionally not done in this phase. |

---

## 1. Executive Summary — **PASS**

Phase 18 confirmed that user-management endpoints were not tenant-scoped:
a company-A admin could read a company-B user (`GET /api/users/<id>` → 200)
and provision a company-B admin (`POST /api/users/` with `company_id=2` → 201),
while only the *listing* endpoint was company-scoped. This phase closed that
gap across **every** user-management operation:

- company scope is now derived from **trusted server context** (the signed JWT
  `company_id` claim surfaced as `g.user_company_id`);
- single-user reads, updates, password resets, activate/deactivate and deletion
  are scoped to the actor's company **in SQL** (`WHERE id = %s AND company_id = %s`);
- creation binds `company_id` to the actor's company — a client-supplied
  `company_id`, `company`, or null value cannot override it;
- platform-admins (no company claim) retain their existing cross-company scope;
- the API contract (status codes, error envelope, messages) is unchanged.

Final state: **exception-free**, no 5xx, exact Phase-18 exploit re-tested at the
API level → both vectors now rejected; full backend **706 passed / 11 skipped**;
frontend **207 passed / 0 failed**; live database untouched.

## 2. Confirmed Vulnerability — **PASS (confirmed)**

Two reproducible cross-tenant vectors on `/api/users`:

1. **Cross-tenant read** — company-A admin `GET /api/users/<company-B-id>`
   returned `200` with full company-B user data (email, username, roles).
2. **Cross-tenant provisioning** — company-A admin `POST /api/users/` with
   `company_id` of company B and `roles: ["admin"]` returned `201` and created
   an admin account inside company B (account-provisioning escalation).

The listing endpoint (`GET /api/users/`) was already scoped to the actor's
company; the remaining operations were role-only guarded.

## 3. Original Evidence — **PASS**

Captured during Phase 18 against the isolated `invoice_system_pe` database:

- `/tmp/opencode/p18/xread.json` — `GET /api/users/42` (company-B admin) → `200`,
  body includes `"company_id": 2`, `"email": "admin.b@uat.test"`, `roles:["admin"]`.
- `/tmp/opencode/p18/xcreate.json` — `POST /api/users/` with `company_id:2` +
  admin role → `201`, user id 44 created in company B.
- The Phase 18 test artifact (user 44) was deleted; the audit-log row recording
  the creation (id 22, company 2) remains as historical evidence.
- Recorded in `PHASE18_REPORT.md` §23 as DEFECT D1/D2 (SECURITY-1).

## 4. Root Cause — **PASS**

- `backend/modules/users/routes.py` guarded every user-management route with
  `require_admin` (role-only) and passed **no company scope** into the service.
- `backend/modules/users/service.py` looked users up by `id` alone
  (`UserRepository.get_by_id`), so a targeted user's company was never compared
  with the actor's.
- `create_user`/`update_user` accepted the client-supplied `company_id` from the
  request body and trusted it without binding to the authenticated actor.
- The repository's single-user lookups had no company dimension
  (`SELECT * FROM users WHERE id = %s`).

## 5. Affected Endpoints — **PASS (inventoried)**

All under `/api/users` (admin-only):

| Operation | Before fix | After fix (company-scoped actor) |
|---|---|---|
| `GET /users/` (list) | scoped (unchanged) | scoped (unchanged) |
| `GET /users/<id>` | cross-tenant 200 | 404 `User not found` |
| `POST /users/` | cross-tenant 201 | 201, but bound to actor's company |
| `PUT /users/<id>` | cross-tenant update | 400 `User not found` |
| `PUT /users/<id>/password` | cross-tenant reset | 400 `User not found` |
| `PUT /users/<id>/activate` | cross-tenant activate | 400 `User not found` |
| `PUT /users/<id>/deactivate` | cross-tenant deactivate | 400 `User not found` |
| `DELETE /users/<id>` | cross-tenant delete | 404 `User not found` |

Indirect user paths were audited: `/api/auth/me`, `/api/users/me`,
`/api/settings/user`, `/api/auth/change-password`, `/api/companies/company`
(settings) all operate on the **authenticated actor's own** identity and are not
tenant-management surfaces — no change required (verified; see §17/§21).

## 6. Authorization Model — **PASS**

Applying the application's existing convention (the same one already used by
imports, reconciliation and audit-trail):

```text
actor_company_id = g.user_company_id        # from the signed JWT (trusted)
target_user.company_id == actor_company_id  # required for read/modify/delete
new_user.company_id    = actor_company_id   # for creation; client value ignored
```

- `g.user_company_id is None` ⇒ **platform-admin**: keeps its established
  cross-company scope and the ability to choose the target company on creation.
- The JWT claim is issued by the server from the user record at login; a client
  cannot inject or downgrade it via body/query parameters.
- Not-found behaviour is shared with the existing tenant convention: a
  cross-company user is indistinguishable from a missing user (`User not found`,
  no existence disclosure).

## 7. Remediation — **PASS** (files: see §20)

- `backend/modules/users/repository.py`: new `get_by_id_for_company(user_id,
  company_id)` enforcing `WHERE id = %s AND company_id = %s` — SQL-level scope.
- `backend/modules/users/service.py`: private `_lookup_user(user_id,
  actor_company_id)` used by get/update/password/activate/deactivate/delete;
  `create_user(..., actor_company_id)` forces `company_id = actor_company_id`;
  `update_user(..., actor_company_id)` drops any client `company_id` for
  company-scoped actors (and rejects a company-only payload with the existing
  `No valid fields to update` error).
- `backend/modules/users/routes.py`: every single-user route now passes the
  trusted `g.user_company_id` into the service.
- No existing surface behaviour, envelope, or status code changed.

## 8. Cross-Tenant Read Tests — **PASS**

- HTTP: company-A admin `GET /api/users/42` (company-B user) → **404**
  `User not found`, and `get_by_id_for_company` asserted called with `(42, A)`.
- HTTP: second company-B id → 404; platform-admin read of a company-B user →
  200 (exemption preserved).
- Enumeration: `GET /users/` returns only company-A users; client
  `?company_id=2&company=2` cannot redirect the scope
  (`get_all_by_company` asserted called with company-A only).
- Service: `get_user_by_id(…, actor_company_id=A)` uses the scoped lookup and
  raises `User not found` when the repo returns None.

## 9. Cross-Tenant Create Tests — **PASS**

- `POST /users/` with `company_id=B` by company-A admin → **201** but the created
  user's `company_id == A`; the repo received a `User` with `company_id A`.
- Same with a `company` key instead of `company_id` → ignored, created in A.
- Same with `company_id: null` / omitted -> still bound to A (no platform
  downgrade).
- `roles: ["admin"]` forgery stays inside the actor's company.
- Platform-admin `POST /users/` with `company_id=B` → 201 in B (unchanged).

## 10. Cross-Tenant Update Tests — **PASS**

- `PUT /users/<B-id>` by company-A admin → **400** `User not found`.
- `PUT` with `company_id: B` against an in-company target → company change
  dropped, target stays in A; a company-only update payload → 400
  `No valid fields to update`.
- Role/status/name updates still work for same-company targets and still enforce
  the last-active-admin guard.

## 11. Cross-Tenant Delete/Deactivate Tests — **PASS**

- `DELETE /users/<B-id>` → **404** `User not found`.
- `PUT /users/<B-id>/deactivate` and `/activate` → **400** `User not found`.
- `PUT /users/<B-id>/password` → **400** `User not found`.
- Same-company delete/deactivate keep working; last-active-admin and
  self-protection invariants unchanged (existing `test_users_repository_guard`
  suite still passes).

## 12. Same-Tenant Tests — **PASS**

- HTTP: company-A admin can GET/PUT/activate/deactivate/delete and reset the
  password of company-A users (all 200; delete 200).
- Service: scoped lookups return in-company users for all operations.
- Listing still returns company-A users only.

## 13. Platform-Admin Tests — **PASS**

- Platform token (no `company_id` claim) still reads any company's user (200)
  and creates a user in a company of its choosing (201 in B).
- `company_id: None` invariant preserved (platform scope, system-only listing);
  client params cannot downgrade/override platform scope (token is signed).
- A company-scoped actor cannot obtain platform behaviour via null/omitted
  company, query params, or body fields.

## 14. Bypass Variant Tests — **PASS**

Realistic variants supported by the API (per Step 13, no speculative
complexity):

| Variant | Result |
|---|---|
| `company_id` in body (int) | ignored → bound to actor company |
| `company` in body | ignored → bound to actor company |
| `company_id: null` / omitted | bound to actor company (no downgrade) |
| `company_id: "abc"` (malformed) | 400 validator error, no DB touch |
| Query params on list (`company_id`, `company`) | ignored; scope stays actor company |
| Alternate endpoints (`/auth/me`, `/users/me`, settings) | own-identity only |
| User-ID manipulation / non-int id | Flask int converter → 404 |
| Cross-tenant activate/deactivate/password/delete | 404/400 `User not found` |
| Role manipulation on create/update | roles validated; scope still enforced |

## 15. Audit Logging Verification — **PASS**

Against isolated `invoice_system_pe`, the post-fix API battery produced audit
rows with actor (`actor_id`/`actor_email`), target (`resource_id`), action,
company scope, and result — e.g. `create user 45 {actor_id 38, company_id 1}`
and `update user 39 {company_id 1}`, all `success`. **0** audit rows contain
`password`/secret strings in metadata or before/after snapshots. The single
historical `create user … company 2` audit row (id 22) is the pre-fix Phase-18
record, retained as evidence.

## 16. API Contract Verification — **PASS**

- No endpoint, response status, error envelope, `code`, or message changed.
- Cross-tenant access reuses the exact existing not-found/invalid-input
  responses (`404/400` + `User not found`, `400` + validator messages).
- Request-ID correlation, success envelope (`success/message/data`), i18n
  strings and `X-Request-Id` echo all unchanged (verified in logs and the
  observability tests). OpenAPI `openapi.yaml` remains accurate: no new or
  removed paths.

## 17. Frontend Impact — **PASS (no frontend changes required)**

The SPA performs user management from the authenticated user's context; it does
not pass a cross-tenant `company_id` (the UI has no company switcher for user
administration). The backend now ignores any such value for company-scoped
actors, so the frontend's existing same-company flows are unaffected. Frontend
suite: **207 passed / 0 failed**; no frontend files changed.

## 18. Regression Results — **PASS**

| Suite | Before | After |
|---|---|---|
| Backend `pytest backend/tests` | 673 passed / 11 skipped | **706 passed / 11 skipped** (+33 new security tests) |
| Frontend `npm test` | 207 pass / 0 fail | **207 pass / 0 fail** |
| Targeted user/RBAC/security modules | — | 183 passed (see §18 module list) |

Targeted modules run independently (Step 16): `test_users_tenant_isolation`
(33 new), `test_users` (30), `test_users_http` (45), `test_users_repository_guard`
(7), `test_audit_security_events` (5), `test_audit_traceability` (27),
`test_api_contract` (36) → **183 passed, 0 failed**. Cross-tenant and
platform-admin cases exercise two distinct companies (company A = 10, company B
= 20; live API companies 1 and 2).

## 19. Database Safety Verification — **PASS**

- All integration-style verification ran against the isolated `invoice_system_pe`
  database (Phase 18 sandbox; UAT companies 1 and 2).
- After the API battery and cleanup: company-1 users = 4, company-2 users = 2
  (exact original UAT state); the two post-fix exploit-attempt artifacts were
  created in company 1 and deleted via the scoped API
  (`DELETE` → 200, audited). **No cross-tenant records were created** by the
  fixed code.
- The live dev `invoice_system` database was verified untouched
  (companies=1, users=2 — identical to baseline; migration `012` still pending).
- No migrations, truncations, drops, or destructive operations occurred.

## 20. Files Changed — **PASS**

| File | Change |
|---|---|
| `backend/modules/users/repository.py` | Added `get_by_id_for_company` (SQL tenant scope) |
| `backend/modules/users/service.py` | `_lookup_user` scope helper; scope params on get/create/update/password/activate/deactivate/delete; create binds actor company; update drops client `company_id` |
| `backend/modules/users/routes.py` | Pass trusted `g.user_company_id` into every single-user service call |
| `backend/tests/test_users_tenant_isolation.py` | **New** — 33 regression tests (service + HTTP, both tenants, bypass variants, platform-admin) |
| `deploy/DEPLOYMENT.md` | Added tenant-scoped user-administration note (§security) |
| `deploy/OPERATIONS.md` | Added tenant-scoped user-management invariant (§8) |

No migrations modified. No frontend changes. No auth/RBAC/rate-limiting changes.

## 21. Remaining Risks / Limitations — **DEFERRED / N/A**

- **DEFERRED — broader tenant surface audit beyond `/api/users`:** this phase
  scoped the confirmed users module; imports/reconciliation were already
  verified scoped in Phase 18. A full cross-module tenant audit (settings,
  reports, exports) remains a future security review item.
- **DEFERRED — JWT claim freshness:** company scope comes from the signed JWT
  claim at login; a user moved between companies after login keeps the old claim
  until re-auth. Recommended as a hardening follow-up (custom claim refresh on
  each request) if needed.
- **N/A — live deployment:** no production host exists; remediation is verified
  in the production-equivalent isolated environment (same code, same MySQL 8).
- **N/A — offensive tooling:** no security scanners (SAST has no runtime test
  gap here; the change is covered by unit + HTTP + live-API tests).
- Residual accepted: no change to platform-admin semantics (intended).

## 22. Acceptance Decision — **COMPLETE**

SECURITY-1 is **COMPLETE**. The confirmed cross-tenant read and creation
vulnerabilities are fixed and API-level re-tested (both now rejected/confined);
every user-management operation is tenant-scoped; company scope comes from
trusted authenticated context and client-supplied company identifiers cannot
override it; platform-admin semantics are preserved; 33 new cross-tenant
regression tests were added; full backend (706/11) and frontend (207/0)
regressions pass; audit logging is verified correct with no secrets logged; the
API contract is unchanged; the live database was not modified; and no unrelated
architectural work was introduced. **DEFERRED items in §21 do not block this
decision.**

**Next official phase (to be started separately — not begun here): Phase 19 —
Frontend Completion Audit.**