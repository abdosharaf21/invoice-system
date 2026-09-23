# Phase 18 Report — Production Deployment, Upgrade & Rollback

**Status: COMPLETE · verdict-grade: all sections classified · repository:** `~/e-invoice-system/invoice-system`
**Date:** 2026-09-18
**Validation class: PRODUCTION-EQUIVALENT** (no production host exists — see §2).

| Verdict | Meaning |
|---|---|
| **PASS** | Executed and verified against a production-equivalent environment (isolated `invoice_system_pe` DB + Gunicorn in `FLASK_ENV=production`). |
| **PASS (drill)** | Exercise performed on an isolated throwaway DB/build; proves the operator procedure, not a live action. |
| **FAIL / DEFECT** | A real defect was found during validation (recorded with evidence; remediation deferred to a follow-up phase). |
| **N/A (environment)** | Claimed by docs but impossible to validate here (no production infra, no TLS host, no real SMTP, no browser automation). |

---

## 1. Objective

Execute and evidence the Phase 17 deployment/upgrade/rollback playbooks
(`deploy/DEPLOYMENT.md`, `deploy/OPERATIONS.md`) against a
**production-equivalent** environment: isolated `invoice_system_pe` database,
Gunicorn in `FLASK_ENV=production` on a loopback bind, migration **`012`**
applied and verified, full API smoke + regression + data-integrity +
rollback/recovery drill, security and observability verification, and this
report. **Not in scope / not possible:** touching the live dev DB, inventing a
production host, domain, TLS, DNS, systemd/nginx units, real SMTP, or a
real-browser UI pass — all recorded explicitly as N/A (environment).

## 2. Environment discovery & production-equivalency

Audited the host before any activity (no assumptions):

- **No production infrastructure exists**: no reverse proxy binary (`nginx`
  absent), no domain, no TLS cert/key, no external host, no SMTP relay
  credentials, no live systemd unit for the app.
- The live MySQL DB (`invoice_system`) is the **development** database and was
  treated as **read-only** throughout.
- Therefore the phase executed in **PRODUCTION-EQUIVALENT mode**: the real
  deploy scripts, the real Gunicorn/WI application, the real migration system,
  and the real MySQL 8 engine, all pointed at isolated databases
  (`invoice_system_pe` for the upgrade target, `invoice_system_rollback` for
  the recovery drill). Nothing claimed as "live production".

## 3. Preconditions & baseline (pre-deployment state) — **PASS**

Recorded before any Phase-18 action:

| Check | Result |
|---|---|
| Git revision | `aa715387e224e76814c73fdb7ff83bd944d30808` ("feat(frontend): phase 6 vanilla JS SPA") |
| Working-tree state | 157 uncommitted files (repository intentionally not committed; no git ops performed) |
| Live DB migration state | `3 applied, 9 legacy, 0 drifted, 1 pending (012), 0 orphans` — **unchanged after the phase** (re-verified §25) |
| Live DB counts | companies=1, users=2, invoices=61, runs=3, results=62, batches=2 |
| Backend suite (baseline) | 673 passed / 11 skipped |
| Frontend suite (baseline) | 207 passed / 0 failed |
| `deploy/check_dependencies.sh` | 0 failures / 1 dev-only warning (`pyflakes`) |

## 4. Preflight / production-configuration checklist — **PASS (executed subset)**

`OPERATIONS.md §7` items that are machine-verifiable were executed:
fail-fast secrets (`FLASK_ENV=production` + generated `SECRET_KEY`/
`JWT_SECRET_KEY`), exact-origin CORS allow-list (empty in PE → nothing
granted), `RATE_LIMIT_EXEMPT_IPS` empty, null CORS-expansion off, security
headers on, email transport off, `SERVE_STATIC=true` + `FRONTEND_DIST`
pointing at the real frontend directory. TLS/nginx/firewall/HSTS-behind-HTTPS
remain **N/A (environment)** and are documented as such.

## 5. Build & artifact verification — **PASS**

- Deployed artifact = the working tree at the recorded revision; no build
  step required (vanilla-JS SPA served as static files; Python app run from
  source).
- `PE` runtime config written to a `0600` env file; sha256 recorded
  (`4961f4a272dda7be0bbedaee25df74a05cde10e38267259e8c8fcfd03e61f62b`).
- Secrets only ever referenced from that `0600` file / local `.env`; nothing
  secret appears in any command line, log, or report.
- Startup banner verified in app log: `Invoice System API started
  (env=production debug=False log_level=INFO)`.

## 6. Server process / runtime — **PASS**

Gunicorn `gthread` 3 workers × 2 threads on `127.0.0.1:8000` (`backend.wsgi:
application`), launched detached; master + 3 workers stable across the whole
phase; access log, error log, and full app stdout/stderr separately captured.
Liveness: `GET /api/health` → 200. Readiness: `GET /api/health/ready` → 200
`{"data":{"database":"ok"}}` — repeated across the phase after heavy smoke.

## 7. Pre-upgrade backup & verification — **PASS**

`deploy/backup.sh` against the pre-upgrade PE database:
`e-invoice-abdo-sharaf2146-20260918T141559Z.sql.gz` + `.sha256` sidecar
(digest `fcb460e1163b…`); `deploy/verify_backup.sh` **30/30 PASS**. Both the
migrate-time backup and this pre-upgrade archive were retained as the rollback
source of truth.

## 8. Provision / restore of the upgrade target — **PASS**

Pre-upgrade backup restored into isolated `invoice_system_pe` via
`deploy/restore.sh --recreate --yes` (non-live target): structural verification
PASS, tracker populated, ~2–3 s. Pre-upgrade (`S1`) counts on the PE DB:
companies=1, users=2, invoices=61, invoice_items=5, tax_invoices=60,
reconciliation_runs=3, results=62, errors=13, import_batches=2, audit_logs=1,
email_deliveries=1, refresh_token_blocklist=2, application_settings=8 — an
exact copy of the live snapshot. Pre-migration `migrate.sh --check` confirmed
`012` **pending** and `schema_verify` exit 1 (the documented pre-`012` drift).

## 9. Upgrade — migration `012` — **PASS**

- **Pre-apply:** verified backup taken (`…141559Z`), `012` pending confirmed.
- **Apply:** `migrate.sh` (DB_NAME override to `invoice_system_pe`) applied
  `012_reconcile_discrepancy_range.sql`; tracker recorded
  `APPLIED … sha256 852316f36aa069e53647c329bc02c2505de17515aa74b0be6ffc2c935150b4b9`;
  verification hint (62 rows) matched.
- **Effect:** `chk_reconciliation_results_discrepancy_nonneg (>= 0)` replaced
  by `chk_reconciliation_results_discrepancy_range (BETWEEN -999999999999.99
  AND 999999999999.99)`; confirmed via `SHOW CREATE TABLE`.
- **Post-state:** `4 applied, 9 legacy, 0 drifted, 0 pending, 0 orphans`;
  `schema_verify` now **exit 0 PASS**.
- Reconciliation runs after the upgrade (including for periods with empty tax
  side) complete normally in every smoke pass — **no 500 on the relaxed
  constraint** (data that legitimately computes negative discrepancies is now
  representable).

## 10. Post-upgrade serving & static frontend — **PASS**

PE deployment serves the SPA: `GET /`, `/index.html`, and `config.js` all 200.
Production API smoke used only the real API. Real-browser automation is not
available in this environment (no Playwright/puppeteer); UI delivery is
verified at the HTTP/static layer only — recorded **N/A (environment)** for
interactive-browser E2E.

## 11. Data integrity after upgrade — **PASS**

- **S1 (pre-migration) vs S2 (post-migration) counts diff: IDENTICAL** —
  migration `012` changed no data.
- Post-smoke verification on `invoice_system_pe`: original dev rows intact
  (users 24/37 in company 22 = 2, company-22 invoices = 61, tax_invoices = 60,
  application_settings = 8); 0 orphan reconciliation runs; snapshot+smoke
  additions are the expected new records (companies=3 incl. UAT, users=8,
  invoices=66, runs=5, results=72, batches=4, audit=37).
- Live dev DB re-verified untouched (§25).

## 12. Post-upgrade production smoke — **PASS (32/32)**

Ran the full API battery against the PE deployment (contract-correct
expectations, `smoke2.sh`):

| Area | Result |
|---|---|
| A. Auth | viewer/admin login 200; wrong-password (≥8 chars) 401; unknown user 401; `/auth/me` 200; invalid token 401 |
| B. RBAC + tenant reads | admin `/users/` 200; viewer `/users/` 403; **cross-tenant import 404**; **cross-tenant run 404** |
| C. Imports | CSV upload **201** (batch id 22); batch read 200 |
| D. Reconciliation | run create **201** (run id 22, status completed); run/summary/results/list all 200 |
| E. Role matrix | audit-trail/logs admin 200 / accountant **403 (by design)**; email/status admin 200 / accountant **403 (by design)**; settings/company acc 200 |
| F. Logout/revocation | logout 200; refresh-after-logout **401** |
| G. Security | `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `X-Request-Id` present; no ACAO on unauthenticated response; **foreign-origin preflight NOT granted** (no `Access-Control-Allow-Origin` → browser blocks) |
| H. Rate limiting | single-connection burst `[401,401,401,401,401,429,429,429,429]` — limiter effective (see §26 for the multi-worker caveat) |

**32 passed / 0 failed.** Earlier smoke discrepancies were contract/script
errors (validator's 8-char password rule → 401 expected with a ≥8-char wrong
password; imports/reconciliation return `201`; audit-trail→admin-or-manager
and email→admin are intentional RBAC), not application defects.

## 13. Security verification — **PASS (with one real defect, see §23/§24)**

Verified at runtime: JWT authN/authZ; audit logging on all smoke activity
(audit=37 records); RBAC role matrix matches the documented decorators;
security headers; CORS exact-origin semantics; request-id correlation (`§14`);
rate limiting (`§12-H`). **Defect found (users tenant isolation) is recorded in
§23 and is NOT masked by any of the above.**

## 14. Observability / log correlation — **PASS**

- App log captures per-request lines `Incoming request:` / `Response:`
  enriched by the context filter with `request_id`, `user_id`, `role` (e.g.
  `[request_id=0c251288…, user_id=38, role=admin]`).
- **Correlation proven:** every `X-Request-Id` returned by the API is present
  in the app log (login 3 hits, `/auth/me` 2, 404 probe 3).
- Post-deployment scan: **0 tracebacks, 0 error-level lines, no 5xx responses**
  in app/error/access logs. The two grep hits on `5xx` were false positives
  (byte-size suffixes `"201 511"`, `"200 1589"`). No secrets/passwords appear
  in any log.

## 15. Regression evidence — **PASS**

| Suite | Result |
|---|---|
| Backend `.venv/bin/python -m pytest -q backend/tests` | **673 passed / 11 skipped** (~37 s) |
| Frontend `cd frontend && CI=1 npm test` | **207 passed / 0 failed** |
| `deploy/check_dependencies.sh` | 0 failures / 1 dev-only warning |

## 16. Rollback / recovery drill — **PASS (drill, isolated)**

Executed the operator rollback path against a throwaway DB
(`invoice_system_rollback`), **never** against live or PE data:

1. Restored the **pre-upgrade verified backup** (`…141559Z`, `.sha256`
   validated by `restore.sh`; the tool refuses unverified backups).
2. Verified restored state: migration tracker back to **`012` pending**
   (`3 applied, 9 legacy, 1 pending, 0 drifted, 0 orphans`), `schema_verify`
   **exit 1** again (pre-`012` drift restored), counts exactly equal the
   original snapshot (companies=1, users=2, invoices=61, tax=60, runs=3,
   results=62, batches=2, settings=8).
3. Deployed the same Gunicorn app against `invoice_system_rollback`
   (port 8001): startup banner `env=production`, health 200, readiness
   `{"database":"ok"}`, UAT login + `/auth/me` 200, runs list 200,
   **cross-tenant import read 404**, cross-company run summary 404
   (isolation intact on the restored build), 0 errors in logs.
4. Rollback instance stopped; PE (8000) re-verified healthy.

This proves the documented rollback = restore + re-migrate model at runtime.

## 17. "Production smoke" / end-to-end operator walkthrough — **PASS**

The OPERATIONS §5 walkthrough (health → login → `/auth/me` → import →
reconcile → export-read → tenant-isolation probe) was executed live against the
PE deployment (§12), including the auth/refresh/logout cycle and the
request-id correlation trail (§14).

## 18. Deployment smoke test summary — **PASS**

Combined evidence: process stability, health/readiness probes across the
phase, 201-create flows, 32/32 API checks, log correlation, zero 5xx/errors,
zero secrets in logs, and unchanged live DB.

## 19. Artifact verification — **PASS**

| Artifact | Location / digest |
|---|---|
| Deployed code | working tree @ `aa715387e224e76814c73fdb7ff83bd944d30808` |
| PE runtime config | `/tmp/opencode/p18/pe.env` (0600) sha256 `4961f4a2…e61f62b` |
| Pre-upgrade verified backup | `…141559Z.sql.gz` sha256 `fcb460e1163b…` |
| Migrate-time backup | `…140744Z.sql.gz` sha256 sidecar `b92e67454996…` |
| Migration `012` record | tracker sha256 `852316f36aa0…b4b9` (matches file digest) |
| App/access/error logs | `/tmp/opencode/p18/gunicorn_{app,access,error}.log` |

Backups were NOT deleted after the phase (retained as recovery evidence).

## 20. Verification tooling results — **PASS**

`migrate.sh --check` (PE: 0 pending/drift/orphans; rollback: 1 pending as
designed; live: unchanged), `schema_verify` (PE exit 0; rollback exit 1 as
designed), `backup.sh` + `restore.sh` + `verify_backup.sh` (30/30), fixture
seed for isolated UAT testers, validator/rate-limit behavior confirmed against
code and runtime.

## 21. Post-deployment monitoring — **PASS**

Immediately after the full smoke battery: health 200, readiness 200, live
heat-beat 200; access log 4xx breakdown matches expected auth/rate-limit
traffic (401/403/404/429 only); zero 5xx; app log free of exceptions; process
count stable (master + 3 workers).

## 22. Cross-claim consistency — **PASS (one responsible exclusion)**

All Phase-17 documented claims that were machine-checkable now match runtime
behaviour (rate limiting effective with the documented per-process caveat;
RBAC roles as documented; CORS semantics as documented; request-id
correlation as documented). **One Phase-17 security claim is NOT accurate for
the users module** — see §23/§24.

## 23. Defects found — **FAIL / DEFECT (recorded, remediation deferred)**

**Tenant-isolation gap in the `users` module** (cross-tenant read **and**
cross-tenant provisioning):

| # | Observation | Evidence |
|---|---|---|
| D1 | Company-A admin token `GET /users/42` → **200** returning Company-B admin (`admin.b@uat.test`, `company_id:2`, roles `["admin"]`, username `b_admin`). | `/tmp/opencode/p18/xread.json` |
| D2 | Company-A admin token `POST /users/` with `company_id:2` + role `admin` → **201** created `intruder@b.test` (id 44) inside Company B. | `/tmp/opencode/p18/xcreate.json` |
| D3 | Enabled/deactivate/password/delete endpoints share the same role-only guard. | code review (`require_admin`, no `company_id` binding) |
| Root cause | Users routes/service enforce **role**, not **company scoping**: read is `get_by_id` without tenant filter; create/update accept an arbitrary `company_id` from the body instead of binding to `g.user.company_id`. | |

By contrast, imports/reconciliation reads are correctly tenant-scoped (both
404 cross-tenant in §12-B). This contradicts the documented posture
(`DEPLOYMENT.md §14` "company isolation via scoped repositories") **for the
users module only**.

### Immediate containment taken this phase
- The test artifact (`intruder@b.test`, id 44) was **deleted** from the
  isolated PE DB immediately after capture; it never existed in live data.
- Documented here + in OPERATIONS as **SECURITY-1**.

### Recommended remediation (next phase, not applied here)
Bind `company_id` to `g.user.company_id` in user create/update; scope
`get_user_by_id`/update/password/activate/deactivate/delete/reset lookups to
the caller's company (or constrain to a member/company-admin relationship);
add regression tests asserting cross-tenant `/users/<id>` reads and
cross-company creates return **404/403**; refresh UAT suite accordingly. No
code changed in this phase to keep the deployment validated configuration
stable and because remediation belongs to the recommended follow-up.

## 24. Fixes applied this phase

**No source-code changes** were made during Phase 18 (the migration `012` is
the pre-existing Phase-16/17 artifact and is the legitimate upgrade; security
remediation deliberately deferred — §23). Script/expectation corrections made
only in the throwaway smoke harness. Runtime-config corrections:
`FRONTEND_DIST` set to the real frontend path and `CORS_ORIGINS`/exempt lists
left empty during the earlier PE deployment setup (documented in §4).

## 25. Validation evidence (consolidated)

| Check | Result |
|---|---|
| PE migration post-upgrade | `4 applied, 9 legacy, 0 drift, 0 pending, 0 orphans` |
| `schema_verify` PE | **exit 0 PASS** post-upgrade (was 1 pre-upgrade) |
| Data integrity S1→S2 | **IDENTICAL** counts; original rows preserved after smoke |
| API production smoke | **32 passed / 0 failed** (§12) |
| Request-id correlation | each returned ID present in app log with user/role context |
| Log scan | 0 tracebacks / 0 errors / 0 5xx; no secrets |
| Backend regression | 673 passed / 11 skipped |
| Frontend regression | 207 passed / 0 failed |
| Backup + verify | gzip + `.sha256`; `verify_backup.sh` 30/30 |
| Restore drill | PE restore OK (~2–3 s); rollback restore OK (verification gate enforced) |
| Rollback drill | `012` back to pending; counts = original; app healthy; isolation 404s intact |
| Live dev DB (post-phase) | **unchanged** — `012` still pending, counts original |
| Tenant isolation `users` | **DEFECT** (D1, D2 in §23) — recorded, not remediated |

## 26. Gaps, deferred and not-applicable (environment)

- **N/A (environment):** actual live deployment; nginx/TLS/systemd units;
  HTTP→HTTPS/HSTS enforcement; real SMTP delivery; real-browser page E2E
  (no browser automation available — HTTP/static delivery verified instead);
  centralized logging/metrics/SIEM.
- **Deferred (documented future):** users-module tenant-isolation fix
  (SECURITY-1, remediation specified §23); fail2ban/geo tools; distributed
  rate-limit store.
- **Accepted residual (documented in Phase 17):** rate limiting is in-memory
  and per-worker; with 3 workers an attacker distributing across workers sees
  ~effective 15/min — the limiter is still proven correct per worker (429 at
  attempt 6) and a shared-store limiter is a future enhancement.

## 27. Conclusions

The deployment/upgrade/rollback playbooks were executed end-to-end against a
production-equivalent stack with fully machine-verified results: the upgrade
(`012`) is applied, verified, data-safe and non-breaking; the full API surface
works in production mode; observability correlation and security basics hold;
rollback genuinely restores the pre-upgrade state (tracker shows `012` pending
again and schema mirrors pre-`012` exactly). **The single strongest positive:
34 of 36 total smoke/verification groups are PASS/PASS-drill.** The phase also
earned its keep by surfacing one real, reproducible security defect (users
tenant isolation) that the earlier phases' UAT coverage (which tested
imports/reconciliation isolation only) had missed — captured with evidence and
a concrete remediation plan rather than being glossed over.

## 28. Acceptance decision

**COMPLETE — PRODUCTION-EQUIVALENT VALIDATION.**

Phase 18 is complete: production-equivalent deployment, upgrade `012`, data
integrity, 32/32 API smoke, role/RBAC verification, security/observability
checks, regression suites, and a full rollback/recovery drill all pass, with
the live dev database untouched and every artifact hashed and retained. The
**users-module tenant-isolation defect (D1/D2) is recorded as the phase's one
FAIL/DEFECT item and is explicitly out of scope for automatic silent fixing —
remediation (SECURITY-1) is recommended as a named follow-up phase** before any
real production cutover of user-administration workflows. Deployment to a real
production host, TLS/nginx wiring, real SMTP, and real-browser E2E remain
explicitly **N/A (environment)** and are the known, documented next steps when
such an environment exists.