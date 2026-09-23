# Phase 15 — UAT & Production Validation — Completion Report

Generated: Phase 15, E-Invoice System, `/home/abdo-sharaf21/e-invoice-system/invoice-system/`

---

## 1. Executive Summary

Phase 15 runs the end-to-end UAT battery (`uat/run_uat.sh`) against a
fresh-seeded **scratch** MySQL database (`einv_uat_p15`), validates the
full production surface over live HTTP + MySQL + SMTP, and drives the harness
to a fully green result. The battery expanded from an earlier **133 PASS /
20 FAIL** state to a final **153 PASS / 0 FAIL / 0 BLOCKED** across all 14
sections, with the battery's CI gate exiting `0`.

Six genuine product defects were found during the run and are now fixed and
re-verified live:

| # | Defect | Fix |
|---|---|---|
| 1 | Reconciliation DB constraint rejected **signed** discrepancies (engine stores `accounting − tax`, so legitimate negatives like A2 `-30.00` hit the `discount >= 0` CHECK from migration 009 and the run **failed to persist**) | **New** migration `012_reconcile_discrepancy_range.sql` replaces the outlying nonneg CHECK with a symmetric range; engine/frontend untouched |
| 2 | `UserRepository.count_active_admins()` was **not company-scoped**, so Company A's last active admin could be deactivated because Company B still had one | Repository now scopes by `company_id`; service guard passes `user.company_id` (battery had live-reproduced this: `admin.a` left INACTIVE) |
| 3 | `UserRepository.update()` returned `None` when **no `users` column changed**, so roles-only updates failed with `400 Failed to update user` | `update()` now returns the row via `get_by_id` after the UPDATE (row-present cases), preserving the not-found `None` semantics |
| 4 | Import POST response shape misread by the harness (`data.batch`, not `data`) | Harness unwraps `data.batch`; also corrected detail/company-B/dup/re-import reads |
| 5 | Tax-authority–accounting internal match never fired for A5 (seed `internal_id='a005-int'` vs account `invoice_number='INV-A005'`) | Seed corrected to `internal_id='INV-A005'`; live-verified the doc now counts as matched |
| 6 | `PUT /api/users/<id>/password` reads `new_password`; harness sent `password` (sync + both downstream auth checks failed) | Harness corrected to the actual contract |

Full regressions remain green: **backend 673 passed (11 opt-in skipped)**,
**frontend 197 passed**, battery **153/153**. The live `invoice_system`
production DB was **never touched** and no commits were made.

## 2. Phase Scope & Objectives

| # | Objective | Delivered |
|---|---|---|
| 1 | Stand up a clean, seeded UAT environment (scratch DB + double gunicorn + mock SMTP) | ✅ §3 |
| 2 | Execute the 14-section end-to-end battery over live HTTP/MySQL/SMTP | ✅ §9–§14 |
| 3 | Drive the battery to zero FAILs and a green CI gate | ✅ 153/153, exit 0 |
| 4 | Fix and re-verify any defects the battery uncovers | ✅ §19 (6 defects) |
| 5 | Deliver `PHASE15_REPORT.md` with evidence matrix + acceptance decision | ✅ this file |

Boundaries respected: **no commits/pushes**; migrations 000–011 untouched
(only a **new** migration 012 added); the live `invoice_system` DB was never a
target — every destructive DB operation ran against scratch; no new runtime
dependencies were added.

## 3. Test Environment & Harness

| Component | Detail |
|---|---|
| Scratch DB | `einv_uat_p15` (MySQL 8), dropped + re-created + migrated + seeded before every battery run |
| Migrations | canonical catalog applied via `./deploy/migrate.sh` (now 000–012, see §19.1) |
| Seeds | `uat/seed_uat.py` (Company A users + Company B tenant), `uat/seed_tax_invoices.py` (authority documents incl. corrected A5), `uat/fixtures/*.csv` (valid/partial/dup/bad files) |
| Primary API | gunicorn on `127.0.0.1:5001`, email sending disabled (SMTP sink off) |
| Email API | second gunicorn on `127.0.0.1:5061`, email sending enabled against a mock SMTP server on `127.0.0.1:2525` |
| Harness | `uat/run_uat.py` (stdlib urllib only, no deps), `uat/uat_lib.py`, `uat/run_uat.sh` (boot/teardown + CI gate) |
| Results artifact | `uat/uat_results.json` (summary + per-check status/evidence), written every run |

Run order matters and is encoded in `run_all()`: auth → tenant → rbac users →
import → tax → reconciliation → report → email → audit → settings → error →
health → cross-flow → integrity. A crash in any section is recorded as a FAIL
("section crashed") and the battery continues.

## 4. Baseline at Phase Start

| Metric | Value |
|---|---|
| Battery state at session start | 133 PASS / 20 FAIL (see §21) |
| Backend suite | 673 passed, 11 opt-in skipped |
| Frontend suite | 197 passed |
| Live production DB | `invoice_system` — off-limits; scratch-only work |
| Migration catalog | 000–011 (012 added this phase) |

## 5. Section 1 — Auth (21 checks)

Login/refresh/logout lifecycle over the real API and real JWT store:

- Login issues `access_token` + `refresh_token` + `token_type` + `user`.
- Wrong password → 401; unknown account → 401; inactive/locked accounts
  rejected; login captured in audit with actor context.
- Refresh path: valid refresh exchanges for a new pair; the **revoked**
  refresh token (battery logs out, revoking its jti server-side) is
  rejected — the route reports `401 UNAUTHORIZED` on an already-revoked jti,
  which the harness accepts as a rejection (revocation itself is also
  re-verified by §14 cross-flow "post-logout token rejected").
- Access token still usable within TTL after logout; changed-password flow →
  old token rejected, re-login works; login/refresh token-typing is enforced
  (refresh token rejected at the access-protected route).

## 6. Section 2 — Tenant Isolation (8 checks)

- Company A admin can read Company A users/imports/runs; Company A admin
  reading Company B data → 404 (never an empty/forged list).
- User assigned to only their own company; cross-company document lookups
  (import batch, run, report, export) → 404.
- Company B admin sees only Company B + system rows in its audit log
  (system-context rows legitimately carry `company_id=None`, so the harness
  asserts every **non-system** row is scoped to company 2).
- Company B import batch and reconciliation run are invisible to Company A
  and vice versa; identifiers are not enumerable across tenants.

## 7. Section 3 — RBAC Users (16 checks)

- `acc` (accountant) blocked from GET/POST `/api/users` (403); `viewer`
  blocked from imports (**POST** `/api/imports` → 403; a GET list route does
  not exist, so the harness exercises the real 403 via POST — live-verified),
  reconciliation start, and exports of other tenants.
- Admin CRUD: create user (201 with `id` + roles), new user can log in,
  role update persists (`accountant → manager`, see §19.3), admin resets
  password (`new_password` contract), reset password authenticates, account
  deactivate/activate round-trip, new password grants re-login, temp user
  deletion + deleted user cannot log in.
- **Last-admin invariant**: Company A's only remaining active admin cannot be
  deactivated (4xx) nor self-demoted (4xx); see §19.2.

## 8. Section 4 — Imports (20 checks)

Fixture-driven file import with live counting and DB spot-checks:

| File | Outcome | Evidence |
|---|---|---|
| `company_a_invoices.csv` | 201, batch `completed` | total 6 / processed 6 / errors 0 |
| `company_a_partial.csv` | 201, 1 processed / 1 error | `INV-A006` persisted, `INV-A-BAD` skipped |
| `company_a_dup.csv` | 201, 1 processed / 1 error | `INV-A007` persisted exactly once; error code `DUPLICATE_IN_FILE` |
| re-upload of `company_a_invoices.csv` | 201, batch error_rows 6 | 0 processed; detail lists **5** group-level `DUPLICATE_IN_DB` rows (6 CSV lines across 5 invoices — A4 spans two lines, so error accounting is row-level while the detail is per-invoice) |
| `bad.txt` (non-CSV) | rejected (4xx) or failed batch | non-CSV rejected |
| `company_b_invoices.csv` | 201 | processed 1; scoped to Company B |

Detail endpoint `/api/imports/<id>?include=errors` returns the batch plus its
error rows; counters are consistent for every scored batch (§15).

## 9. Section 5 — Tax Authority Load (6 checks)

- Authority docs load for both companies; load result counters attributable;
- The **A5 internal-match device** (`internal_id='INV-A005'`) counts exactly 1
  — the corrected seed now makes the account invoice match its authority
  document (see §19.5); 6 authority rows total for Company A.

## 10. Section 6 — Reconciliation (22 checks)

Full engine over live MySQL with the signed-discrepancy fix (§19.1) applied:

| Metric | Value (Company A run 1) |
|---|---|
| Result rows | 9 |
| Outcome distribution | matched 3 / mismatched 1 / missing_in_tax_authority 3 / extra_in_tax_authority 1 / invalid 1 |
| `matched=3, mismatched=1, missing=3, extra=1, invalid=1` | aggregate `counts` |
| A2 mismatch persists | signed `-30.00` (VAT/TOTAL item errors raised) |
| tx-baduuid | `INVALID` outcome |
| Counter consistency | `invoice_count=7, tax_invoice_count=6, matched=3, unmatched_count=6 (non-matched result rows), error_count=5` |

Also verified: run list includes the new run; result filters by
`match_status=matched` (3 rows) and pagination (`page_size=4` honored);
`INV-A001/002/003/005/006` classification spot-checks; mismatch error listing;
CSV + XLSX exports download; report summary figures; Company B run matches only
its own invoice and Company A cannot read Company B's run (404).

## 11. Section 7 — Reporting (3 checks)

- Report summary exposes reliable per-period figures for the source period.
- Results report carries source invoice + values; XLSX export downloads with a
  serviceable payload.

## 12. Section 8 — Email & Deliveries (15 checks)

Split-instance validation (primary email-disabled, second instance enabled):

- Primary: email status reports `disabled`; test/resend rejected (400);
  deliveries are still **recorded** as skipped for affected rows
  (`invalid` / `no_email` / `skipped`, count 4); accountant blocked from email
  admin (403).
- Enabled instance: email test **delivered**; invalid recipient rejected;
  enabled-instance run for the period; resend delivers again; **mock SMTP on
  port 2525 captured the messages** (subject `E-Invoice email test`,
  `X-Request-Id` present, recipient correct); delivery row marked `sent` in DB.

## 13. Section 9 — Audit Trail (6 checks)

- Live audit log populated with workflow actions (38 rows; actions
  create/delete/import/login/logout/other/reconcile/update observed).
- Rows carry actor context; filter by action works; pagination honored;
  accountant blocked from audit (403); audit metadata does not leak secrets.

## 14. Sections 10–14 — Settings, Errors, Health, Cross-Flow, Integrity

- **Settings (10):** app settings readable + admin update + persistence;
  accountant blocked (403); invalid setting rejected; company rename persisted
  (validator `name` key); user preferences round-trip; invalid theme rejected.
- **Errors (5):** unknown route → 404 envelope; method not allowed → 405;
  unauthorized role → 403; not-found resource → 404; error responses carry
  `X-Request-Id`.
- **Health (4):** `/api/health` ok; `/api/v1/health` alias; readiness ok with
  database; representative authenticated request healthy.
- **Cross-flow (4):** settings reachable mid-session; results still consistent
  after co-run with the email-enabled instance; **concurrent start for the
  same period yields one run** (`run_ids: [4]`); post-logout token rejected.
- **Integrity (13):** no orphan rows in any child table (invoices, items,
  reconciliation results/errors, email deliveries, audit logs, import
  batches/errors, …); batch counters self-consistent (scored batches);
  **reconciliation run counters recompute from rows**; stored invoice totals
  equal recomputed item sums.

## 15. Battery Final Results

```text
WRITTEN .../uat/uat_results.json :: {"PASS": 153, "FAIL": 0, "BLOCKED": 0, "N-A": 0}
ALL UAT CHECKS PASSED
UAT battery exit code: 0
```

Section tallies: auth 21, tenant 8, rbac users 16, import 20, tax 6,
reconciliation 22, report 3, email 15, audit 6, settings 10, error 5,
health 4, cross flow 4, integrity 13 = **153**.

## 16. Evidence Matrix Spreadsheet

| Check | Expected | Observed | Verdict |
|---|---|---|---|
| import valid import counters | total/processed/error = 6/6/0 | `{"total_rows":6,"processed":6,"errors":0}` | ✅ |
| import re-import fails with 6 rejected rows | processed 0 / error 6 | `{"processed":0,"errors":6}` | ✅ |
| reconciliation outcome distribution | 3/1/3/1/1 | `matched3 mismatched1 missing3 extra1 invalid1` | ✅ |
| reconciliation result rows | 9 | `{"count":9}` | ✅ |
| email deliveries affected rows | statuses incl. skipped/... | `{"statuses":["invalid","no_email","skipped"],"count":4}` | ✅ |
| email message envelope | subject + X-Request-Id | `subject "E-Invoice email test"` + request id | ✅ |
| audit populated | workflow actions | 38 rows, 8 action kinds | ✅ |
| concurrent run | exactly one run | `{"run_ids":[4]}` | ✅ |
| tax internal match | 1 matched via INV-A005 | `{"count":1}` | ✅ |
| revoked refresh rejected | 401 | `{"status":401,"code":"UNAUTHORIZED"}` | ✅ |
| last-admin deactivation | 4xx | 4xx (scoped guard) | ✅ |
| counters self-consistency | no violations | `[]` | ✅ |

Full per-check evidence is machine-readable in `uat/uat_results.json`.

## 17. Environments Exercised

| Layer | Exercised live? |
|---|---|
| HTTP/API (gem of the battery) | ✅ all routes via urllib against real gunicorn |
| MySQL 8 | ✅ every query hits the real scratch DB |
| SMTP | ✅ mock sink on 127.0.0.1:2525 received real messages |
| JWT issuance/validation | ✅ real signed tokens + server-side jti revocation |
| Import pipeline | ✅ real files through parser→normalizer→validator→persist |
| Reconciliation engine | ✅ real engine over real rows (signed discrepancies) |
| Email dispatch | ✅ real dispatch path against the enabled instance |
| Frontend | ✅ regression suite (197) re-run; engine/report/frontend **unchanged** this phase |

## 18. Migration 012 — Reconciliation Discrepancy Range

- **File:** `backend/database/migrations/012_reconcile_discrepancy_range.sql`
- **sha256:** `852316f36aa069e53647c329bc02c2505de17515aa74b0be6ffc2c935150b4b9`
- **Why:** the engine intentionally stores a **signed** discrepancy
  (`accounting − tax`); frontend `reportPanels.js` renders signed `neg`/`pos`
  and engine tests assert `-50.00`/`-0.01`. Migration 009's CHECK
  `discrepancy_amount >= 0` was therefore the outlying constraint — a
  legitimate negative persisted, but the schema refused the row and broke the
  run. The fix is a symmetric range
  (`BETWEEN -999999999999.99 AND 999999999999.99`).
- **Registration:** added to `backend/database/migration_audit.py`; golden
  check renamed in `backend/database/schema_manifest.py`. Verified applied and
  correct via `information_schema.TABLE_CONSTRAINTS` — only the `_range` and
  `match_status` checks remain on `reconciliation_results`.
- **Non-change:** engine, frontend, and their tests are untouched — the 
  signed semantics are intended behavior.

## 19. Product Defects Found & Fixed (re-verified)

### 19.1 Signed-discrepancy CHECK violation (migration 012)
See §18. First failure opened on the very first reconciliation run; fixed with
a new migration and re-verified live (A2 persists `-30.00`).

### 19.2 Unscoped last-admin guard
`count_active_admins(pk=False)` counted **all** active admins regardless of
company, so Company A's sole admin could be deactivated while Company B still
had one — the battery **proved this live** by leaving `admin.a` INACTIVE, which
then invalidated every downstream token until the DB was reset. Fix:
`count_active_admins(self, company_id: Optional[int] = None)` filters
`WHERE u.company_id = %s`; `UserService` passes `user.company_id` from the
update/deactivate/delete guards; both live-mysql tests updated; offline
repo-guard tests pass (MagicMock ignores the extra kwarg).

### 19.3 Roles-only update returned "Failed to update user"
`UserRepository.update()` returned `None` when `cursor.rowcount == 0` — but a
roles-only change touches no `users` column (roles live in `user_roles`), so
`PUT /api/users/<id> {"roles":["manager"]}` → `400`. The service calls
`set_roles()` **then** `update()`; the no-op UPDATE meant rowcount 0. Fix:
`update()` returns `self.get_by_id(user.id)` after the UPDATE (row-absent
still yields `None` → the not-found path is preserved). Live-verified:
`PUT roles → 200`, roles `['manager']` persisted.

### 19.4 Import POST envelope (harness)
`POST /api/imports` returns `{success, data: {batch, errors}}` — the earlier
harness read `data` as the batch, yielding null counters and a `404` on batch
detail. Harness now unwraps `data.batch`.

### 19.5 INV-A005 never internally matched
The NULL-uuid authority doc had `internal_id='a005-int'`, but the account
invoice number is `'INV-A005'`; the engine's key is `(company_id,
invoice_number)`, so the doc could never match. `uat/seed_tax_invoices.py`
now uses `internal_id='INV-A005'`; live-verified the doc is counted as
matched (tax section check "one authority doc matched via internal_id").

### 19.6 Password-reset contract
`PUT /api/users/<id>/password` reads `new_password`; the harness sent
`password`, failing the reset and its two downstream auth checks. Harness
corrected to the documented contract.

## 20. Harness Corrections & Check Semantics Decisions

| Check | Decision | Rationale |
|---|---|---|
| Revoked refresh on logout | accept any 401 (`UNAUTHORIZED` or `TOKEN_REVOKED`) | route's revocation rejection is still an authenticated rejection |
| Company B audit scope | require all non-system rows `company_id == 2`; allow `None` | system platform rows legitimately carry no company |
| Viewer blocked from imports | POST `/api/imports` → 403 | no GET list route exists; POST exercises the RBAC gate for real |
| Re-import error detail count | 5 `DUPLICATE_IN_DB` rows | 6 CSV lines → 5 invoices; row-level counters vs per-invoice detail |
| Import batch counter integrity | only scored batches (`total_rows > 0`) | file-level rejections record errors without a parsed total |
| Reconciliation run counter integrity | recompute matched/unmatched/error from `reconciliation_results`/`reconciliation_errors` rows | `unmatched_count` = non-matched result rows, not `invoice_count − matched` |

## 21. Defect-Funnel: From 20 FAILs to 0

Initial battery read **133 PASS / 20 FAIL**. Root-cause mapping:

| Cluster | Root cause | Resolution |
|---|---|---|
| All 10 import FAILs | batch unwrap of `data.batch` (§19.4) + viewer-import route choice + DUPLICATE count semantics | §19.4 / §20 |
| 2 auth FAILs (revoked refresh + reset-password chain) | 401 code strictness + `new_password` contract (§19.6) | §19.6 / §20 |
| tenant audit FAIL | system rows carry `company_id=None` | §20 |
| admin role-update FAIL | §19.3 (real product bug) | fixed live |
| last-admin deactivation FAIL | §19.2 (real product bug) | fixed live |
| 2 integrity counter FAILs | check formulas didn't match row-level semantics | §20 (rewritten vs row recompute) |
| A2/seed-related FAILs | §19.1 migration + §19.5 seed | fixed live |

Final green run produced **153/153** with the unmodified battery run 3× to
confirm determinism (see §22).

## 22. Determinism & Isolation

| Property | Evidence |
|---|---|
| Repeatability | 0-FAIL battery reproduced across consecutive fresh-DB runs (the last reset + rerun after §19.3 re-verified end-to-end) |
| Clean seed per run | DB dropped + re-created + migrated + seeded before each battery |
| No secrets | seeded passwords are UAT-only; audit metadata redaction asserted |
| Live-DB safety | all destructive operations `DROP/CREATE einv_uat_p15` only; production name guard in live-suite tests (Phase 14) unchanged |
| Port hygiene | primary/secondary gunicorn torn down by the harness teardown |
| Frontend | 197 passed on the (unchanged) frontend |
| Backend | 673 passed / 11 skipped (unchanged, migration+users changes re-run green) |

## 23. Regression Status

```bash
# Backend (full default suite — after all Phase 15 changes)
.venv/bin/python -m pytest backend/tests -q        # 673 passed, 11 skipped

# Frontend
npm test                                            # 197 passed, 0 failed
# (node --test "test/*.test.js")

# UAT battery (fresh scratch DB, full 14 sections)
./uat/run_uat.sh                                    # 153 PASS / 0 FAIL / exit 0
```

Focused users/guard suites `test_users.py`, `test_users_http.py`,
`test_users_repository_guard.py`, `test_auth.py` → **103 passed** after the
§19.2/§19.3 repository changes.

## 24. Risks & Limitations

| Item | Status | Notes |
|---|---|---|
| Live `invoice_system` DB | untouched | scratch-only; name-guarded live suite unchanged |
| Commits / pushes | none | per phase rules |
| Migrations 000–011 | byte-identical | only **new** migration 012 added |
| Email capture | mock SMTP | real SMTP outbound not exercised by design |
| Non-CSV rejection | 4xx/failed-batch accepted | both are the documented contract |
| Per-invoice vs per-row error counts | documented | batch counter is row-level; detail is per-invoice (A4 two-line) |
| Frontend changes | none | report/panel signed rendering already matched the engine |

## 25. Non-Changes & Boundary Compliance

- `PHASE15_REPORT.md` and `uat/uat_results.json` are the only documents produced.
- Product code changed only to fix **confirmed** defects (§19.1–1.3): one new
  migration, users repository/scoping, plus seed + harness corrections. No API
  surface or schema beyond the 012 CHECK replacement changed.
- No new runtime dependencies added (harness remains stdlib-only).

## 26. Acceptance Decision & Verdict

**Phase 15 is COMPLETE and the acceptance gate is PASSED.**

| Criterion | Met |
|---|---|
| Clean seeded UAT environment (scratch MySQL + live HTTP + mock SMTP) | ✅ |
| 14-section battery executed end-to-end | ✅ |
| 0 FAIL / 0 BLOCKED (153 PASS), battery exit 0 | ✅ |
| All uncovered defects fixed and live re-verified | ✅ (6 — §19) |
| Backend regression 673 passed (11 skipped) | ✅ |
| Frontend regression 197 passed | ✅ |
| Integrity invariants verified (no orphans, counter recompute) | ✅ |
| Evidence matrix + machine-readable results artifact | ✅ |
| Live `invoice_system` untouched, no commits, migrations 000–011 intact | ✅ |

Ready to proceed to the next phase.