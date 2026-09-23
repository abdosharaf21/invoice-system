# E-Invoice & Reconciliation System — Operations Runbook (Phase 17)

Day-to-day operational procedures for operators and developers. This is the
**operational reference**; installation details live in `deploy/DEPLOYMENT.md`
and backup/restore/disaster-recovery in `deploy/DISASTER_RECOVERY.md`.

> **Boundary:** this phase *prepares and documents* operating procedures. The
> system is **not yet deployed to production**; Phase 18 is responsible for the
> actual deployment, upgrade, rollback, live migration and deployment smoke
> tests. Nothing here claims a production deployment has happened.

All commands below are verified against this repository (Phase 17). Replace
placeholders (`<...>`) with your values; **never** put real secrets on a
command line (the shipped scripts already keep them out of the process list).

---

## 1. Stack at a glance

| Layer | Implementation | Bind / port (dev) | Production |
|---|---|---|---|
| Backend | Python 3.12 + Flask, `backend/app.py` factory, Gunicorn `backend.wsgi:application` | dev server `0.0.0.0:5001` (`python backend/app.py`) | Gunicorn `127.0.0.1:8000` behind Nginx |
| Frontend | Vanilla JS SPA in `frontend/` (no build step) | `python3 -m http.server 8080 --directory .` | same origin via Nginx `/api` proxy |
| Database | MySQL 8, `invoice_system` by default | `127.0.0.1:3306` | dedicated least-privilege user (§ DEPLOYMENT.md) |

Config comes entirely from environment variables (`.env` / `EnvironmentFile`);
see `backend/config.py` and the table in `DEPLOYMENT.md` §3. **Never** commit
real secrets — only `.env.example` with placeholders is tracked.

---

## 2. Health vs readiness

Two distinct signals (both unauthenticated, not rate-limited):

| Endpoint | Meaning | Success | Failure |
|---|---|---|---|
| `GET /api/health` | **Liveness** — the process is up and serving | `200 {"success":true,"status":"ok",...}` | — (no DB contact) |
| `GET /api/health/ready` | **Readiness** — can serve real traffic (DB pool operational) | `200 {"success":true,...,"data":{"database":"ok"}}` | `503 {"success":false,"status":"error","message":"Database unavailable"}` |

- Use `/api/health` for "is the worker alive?" (uptime probes, `after` steps).
- Use `/api/health/ready` for "should traffic be routed here?" (orchestration,
  post-start gating, bootstrap scripts).
- Readiness never exposes infrastructure details.

Quick checks:

```bash
curl -si http://127.0.0.1:8000/api/health
curl -si http://127.0.0.1:8000/api/health/ready
```

Both responses carry an `X-Request-Id` header (§4).

---

## 3. Verified day-to-day procedure references

| # | Task | Command (verified) |
|---|---|---|
| 1 | Start application (dev API) | `cd ~/e-invoice-system/invoice-system && .venv/bin/python backend/app.py` |
| 1b | Start application (prod, Gunicorn) | `systemctl enable --now e-invoice` (unit binds `127.0.0.1:8000`) |
| 2 | Stop application (prod unit) | `systemctl stop e-invoice` |
| 3 | Verify health | `curl -si http://127.0.0.1:8000/api/health` |
| 4 | Verify readiness | `curl -si http://127.0.0.1:8000/api/health/ready` |
| 5 | Check logs | `journalctl -u e-invoice -e -n 200` (Gunicorn logs to journal) |
| 6 | Run migrations — status/drift (read-only) | `deploy/migrate.sh --check` |
| 6b | Run migrations — apply pending | `deploy/migrate.sh` (pre-backs-up the DB) |
| 6c | Run migrations — seed tracker for a hand-migrated DB | `deploy/migrate.sh --record-existing` |
| 7 | Verify schema (target vs golden manifest) | `PYTHONPATH=. .venv/bin/python -m backend.database.schema_verify --db <database>` |
| 7b | Prove catalog bootstrappable (isolated scratch) | `deploy/schema_drill.sh` |
| 8 | Create backup | `BACKUP_DIR=/var/backups/e-invoice deploy/backup.sh` |
| 9 | Verify backup (file) | `deploy/verify_backup.sh --backup /var/backups/e-invoice/e-invoice-*.sql.gz` |
| 10 | Restore into isolated DB (drill) | `deploy/restore_test.sh` (or `deploy/restore.sh --backup … --target <isolated> --recreate --yes`) |
| 11 | Recover from failure | Follow `deploy/DISASTER_RECOVERY.md` (isolated drills only in this phase) |
| 12 | Verify authentication | See §5.2 (curl login + `/api/auth/me`) |
| 13 | Verify representative business workflow | See §5.3 |
| 14 | Check dependencies (local) | `deploy/check_dependencies.sh` |
| 14b | Check dependencies (online audits) | `deploy/check_dependencies.sh --online` |

Paths assume the repo root (`~/e-invoice-system/invoice-system`). Behind Nginx
the API is reached through `/api/*`; directly it is `127.0.0.1:8000/api/*`.

---

## 4. Logging & observability runbook

### Where logs are emitted

- **Application logs** go to the Python root logger → `StreamHandler` (stdout).
  Under systemd they land in the journal (`journalctl -u e-invoice`);
  under the dev server they go to the terminal.
- **Gunicorn** access + error logs go to stdout/stderr (`--access-logfile -`,
  `--error-logfile -`), i.e. the same journal.
- **Backups** write `backup.log` next to the archive directory (`BACKUP_DIR`);
  MySQL errors during dump are appended to the same log.
- Log level is `LOG_LEVEL` (default `INFO`; `backend/config.py`).

### Request correlation IDs

- Every request gets `X-Request-Id`. A client-supplied value is honoured only
  when it is a safe token (alphanumeric/dot/dash, ≤64 chars); anything else is
  replaced with a generated UUID.
- Every response echoes it back (header), and the appends it (with `user_id`
  and `role` when a token is present) to every log line:

  ```
  INFO backend.middleware.logger Response: GET /api/reconciliation/runs/3 status=200 duration=0.0123s [request_id=… user_id=1 role=admin]
  ```

- Use the header value to correlate a client failure with server logs:
  `journalctl -u e-invoice | grep <request_id>`.

### Important events to look for

| Event | Log signature |
|---|---|
| Startup | `Invoice System API started (env=… debug=… log_level=…)` |
| Readiness failures | `Readiness check failed: database unavailable` |
| Authentication failures | `401` responses on `/api/auth/login` (wrong credentials) |
| Authorization failures | `403` responses (role-gated endpoints) |
| Rate limiting | `Rate limit exceeded category=<login|refresh|password|email|upload> client=… path=…` |
| Import failures | `ERROR: Failed to process import batch …` + trace in the error handler |
| Reconciliation failures | `ERROR … reconciliation …` + trace |
| Startup recovery | `Recovered <import batches|reconciliation runs> to failed on startup` |

### What is NEVER logged

- Passwords / password hashes, any `*_SECRET` value (JWT, Flask secrets),
  SMTP credentials (`EMAIL_USERNAME`/`EMAIL_PASSWORD`),
- sensitive personal/business data beyond the minimum business identifiers the
  application writes to emails/audit — request logs record method, path
  (**no query string**), client IP, status, duration, user id and role only.
- Query strings are intentionally omitted by `log_request`/`log_response`.

### Limits of this phase's observability

There is **no** centralized log shipping, metrics, or tracing backend. What
exists is structured, request-correlated stdout logging, per-request duration
in the log line, plus the `X-Request-Id` response header (exposed via CORS for
frontend debugging). Do not claim agent-based APM or SIEM integration — those
remain operational recommendations (§8).

---

## 5. Verification walkthroughs

### 5.1 Health / readiness / startup

```bash
curl -si http://127.0.0.1:8000/api/health        # expect 200 + X-Request-Id
curl -si http://127.0.0.1:8000/api/health/ready  # expect 200 + data.database=ok
```

### 5.2 Authentication

```bash
# Login (rate limited: 5/min per client) — use a real account, no secrets here
curl -si -X POST http://127.0.0.1:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"<email>","password":"<password>"}'
# expect 200 {success:true, data:{access_token, refresh_token}}

# Use the returned token:
curl -si http://127.0.0.1:8000/api/auth/me \
  -H "Authorization: Bearer <access_token>"
# expect 200 {success:true, data:{…}} — also proves RBAC claims load
```

### 5.3 Representative business workflow

1. Create a backup first (`deploy/backup.sh`) as a restore point.
2. **Import**: `POST /api/imports` (multipart `file`) — needs `admin`/
   `accountant`/`manager`; check the returned batch state.
3. **Reconcile**: `POST /api/reconciliation/runs` with `{"period":"YYYY-MM"}`;
   expect `status: completed` and per-status counts.
4. **Report**: `GET /api/reconciliation/runs/<id>/summary`, filter results,
   and export `…/results/export?format=csv|xlsx`.
5. **Tenant isolation**: an account in company A must get `404` for a run of
   company B and must never see company B's users via `GET /api/users/`.

### 5.4 Dependency checks

```bash
deploy/check_dependencies.sh            # local: manifests, pins, venv parity, npm zero-deps
deploy/check_dependencies.sh --online   # adds pip-audit + npm audit (needs network)
```

Exit 0 = clean; a non-zero exit or a `[FAIL]` line means an operator
intervention before any deploy.

---

## 6. Troubleshooting runbook

| Symptom | Checks (in order) |
|---|---|
| **Backend does not start** | `SECRET_KEY`/`JWT_SECRET_KEY` set (startup aborts without them outside development); `FLASK_ENV=production` refuses the dev server (`python backend/app.py`) → use Gunicorn; `.venv` deps installed from the lockfile (`deploy/check_dependencies.sh`); MySQL reachable at `DB_HOST:DB_PORT`; port free (`ss -ltnp`), config via `backend/config.py`; logs for the exact abort reason. |
| **Frontend cannot reach backend** | API base resolution in `frontend/assets/js/config.js` (`?api=…`, `window.__EIS_API_BASE__`, same-origin `/api` when non-localhost, else `http://localhost:5001`); backend up (`/api/health`); CORS: `CORS_ORIGINS` must equal the **exact** `scheme://host:port` the browser is on (`*` is never used with credentials); behind Nginx check the `/api/` proxy block. |
| **Login fails** | Backend healthy; credentials correct and account active; remember login is rate limited (5/min per client IP — check for `Rate limit exceeded category=login`); confirm the request id: capture `X-Request-Id` from the response and `grep` the journal; check `401` vs `429` vs `500` distinction in logs. |
| **Migration fails** | `deploy/migrate.sh --check` first (pending/drift/orphans are reported read-only); a `DRIFT`/`ORPHAN` result means restore the pre-migration backup before proceeding (`--accept-drift` is a conscious override, not the default path); DB credentials and `MIGRATIONS_DIR`; verify the target DB is the intended one (`Target database:` line); migration ordering is lexicographic (`000…012`). |
| **Backup fails** | `mysql` client installed; DB user has `SELECT`+`LOCK TABLES`/`RELOAD` (or run as a privileged user); disk space in `BACKUP_DIR`; inspect `BACKUP_DIR/backup.log`; a missing `.sha256` sidecar means the dump was rejected (never restore such a file). |
| **Readiness fails (503)** | Is the app process running? (a live `/api/health` but failing `/api/health/ready` isolates the DB layer); is MySQL up and credentials valid in the env file; any startup/readiness warnings in the journal. |

Never “fix” these by deleting data, disabling security headers, rate limiting,
CSP, or the auth gates.

---

## 7. Production configuration checklist

Phase 17 documents the requirements; **nothing below is claimed to be
configured on a production host** (Phase 18 validates the deployment).

Secrets & configuration:
- [ ] `SECRET_KEY`, `JWT_SECRET_KEY` **set to strong random values**; env file
      owned `root:e-invoice`, mode `0640`, outside the repo
- [ ] `FLASK_ENV=production`; `DEBUG` off; dev server refused
- [ ] `DB_USER`/`DB_PASSWORD` for a dedicated least-privilege MySQL user
      (SELECT/INSERT/UPDATE/DELETE; DDL only when the app runs its own migrations)
- [ ] `CORS_ORIGINS` = exact public origin(s); `CORS_EXPAND_LAN=false`
- [ ] `SECURITY_HEADERS_ENABLED=true`; `CSP_ENABLED=true`; `HSTS_ENABLED=true`
      only behind HTTPS
- [ ] `RATE_LIMIT_ENABLED=true`; `RATE_LIMIT_EXEMPT_IPS` **empty** behind Nginx
- [ ] `EMAIL_*` configured **only if** outbound notifications are wanted
Connectivity & topology:
- [ ] Nginx serves the SPA and proxies `/api/*` → `127.0.0.1:8000`;
      TLS certificate + `listen 443 ssl` enabled; `return 301 https://…`
- [ ] Firewall: only `22/80/443` inbound; 8000 and 3306 never public
- [ ] `server_name` matches the real domain
Data & integrity:
- [ ] Nightly `deploy/backup.sh` + `deploy/verify_backup.sh` (cron), retention
      per `RETENTION_DAYS`, archives + `.sha256` sidecars off-box
- [ ] Restore drill (`deploy/restore_test.sh`) run at least once per release
- [ ] Migrations applied via `deploy/migrate.sh`; `--check` shows no drift/orphans
- [ ] `deploy/check_dependencies.sh --online` clean
Operations:
- [ ] `GET /api/health` liveness probe + `GET /api/health/ready` readiness probe
      wired to the orchestrator
- [ ] Logs collected from the journal; `LOG_LEVEL` chosen for the environment
- [ ] Admin account created; operator roles assigned via the users module
- [ ] Human gate (`--confirm-live` + typed `yes`) understood for live restore

---

## 8. Security operations summary

**Implemented controls** (verify, don’t dismantle):
- JWT access + refresh; **revocation** on logout and **blocklist** it is
  persisted in `refresh_token_blocklist` and consulted per request
- RBAC (`admin`/`accountant`/`manager`/`viewer`) enforced per module; company
  (tenant) isolation resolved from the authenticated user, never the body
- User management is tenant-scoped end to end: reads, creation, updates,
  password, activate/deactivate and delete are bound to the authenticated
  user's company (`g.user_company_id` from the signed JWT); client-supplied
  company identifiers cannot move or create users across companies.
  Platform-admins (no company claim) retain cross-company scope.
- Password hashing via bcrypt; minimum-length and complexity validators
- Full **audit trail** (`audit_logs`, kill-switch `AUDIT_LOG_ENABLED`) —
  see `backend/modules/audit_trail/`
- Secrets only from env; startup fail-fast when required secrets are missing
- Dependency verification (`deploy/check_dependencies.sh`) + supply-chain tests
- CORS exact-origin allow-list with credentials; security headers + CSP + HSTS
- Request correlation (`X-Request-Id`) and rate limiting on sensitive endpoints

**Operational recommendations** (operator actions):
- Least-privilege MySQL user and strict firewall (§7)
- Backup credentials protected (env file `0640`, no secrets in process list,
  `.sha256` sidecars guarded with the archives)
- Periodic restore drills and dependency audits
- Rotate `JWT_SECRET_KEY`/`DB_PASSWORD` on a schedule and on personnel changes

**Future enhancements** (not yet implemented, do not document as present):
- Binlog point-in-time recovery (RPO < backup interval), centralized SIEM/APM
  log shipping, metrics/tracing agents, a managed secrets vault
- No external certification/compliance status is claimed.

---

## 9. Upgrade procedure (to be validated in Phase 18)

An operational sequence only — Phase 18 executes and validates it on the real
deployment. Never skip a step:

```
1. Back up             deploy/backup.sh  (BACKUP_DIR=<target>)
2. Verify backup       deploy/verify_backup.sh --backup <newest>
3. Record version      note current schema state via deploy/migrate.sh --check
                       and `git rev-parse HEAD` / app version
4. Deploy code         stage the new release (never run as root)
5. Run migrations      deploy/migrate.sh   (pre-backs-up automatically)
6. Verify schema       PYTHONPATH=. .venv/bin/python -m backend.database.schema_verify --db <db>  (expect exit 0)
7. Health/readiness    curl /api/health and /api/health/ready
8. Smoke test          §5.3 representative business workflow
9. Monitor             watch readiness, rate-limit rejects, 5xx in the journal
```

If any step fails, **restore the pre-change backup** (§10) before continuing.

---

## 10. Rollback considerations

- **Application rollback** — reverting the code may be viable only if it stays
  compatible with the (possibly migrated) schema. Check the migration patch
  scope before assuming code-only rollback.
- **Database rollback** — schema changes are **not automatically reversible**;
  in-application rollback SQL is not fabricated. Roll the DB back by restoring
  the pre-change **verified** backup (`deploy/backup.sh` output + `.sha256`)
  and, if needed, forward-migrating a restored database again (see
  `DISASTER_RECOVERY.md` §6).
- **Restore-point requirements** — every upgrade must start from a verified
  backup, and the operator must know the backup’s schema version (tracker) so
  a rollback restores the right point and is then upgraded cleanly.
- Live restores require the human double-gate (`--confirm-live` + typed `yes`).

---

## 11. Current database & migration state (Phase 17)

As of this phase:

- Catalog: `backend/database/migrations/000…012.sql` (13 files).
- Live `invoice_system`: migrations `000`–`011` recorded in the tracker
  (`000`, `010`, `011` checksum-protected; `001`–`009` legacy pre-checksum),
  **`012_reconcile_discrepancy_range.sql` pending**; 0 drift, 0 orphans.
- Consequently `schema_verify` reports the expected CHECK-constraint drift on
  the live DB until `012` is applied — this is the accurate current state, not
  a hidden failure. `deploy/schema_drill.sh` proves `000…012` reproduce the
  manifest on a scratch DB (PASS, 13 files).
- Backup/restore drill and `restore_test.sh` were re-run this phase: 30/30
  backup verification, 36/36 application checks, ~7 s restore on dev data.

Do **not** apply migrations to the live DB as part of this phase — that is a
Phase 18 deployment/migration validation task.