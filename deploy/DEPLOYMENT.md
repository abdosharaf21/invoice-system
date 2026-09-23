# E-Invoice & Reconciliation System — Production Deployment Guide (Phase 8)

This guide deploys the system for production. It intentionally records what
has been **verified in this development environment** separately from what
**requires a real production server, domain, certificate, and SMTP service**.

> **Day-to-day operator procedures** (start/stop, health & readiness, logs,
> migrations, backups, troubleshooting, upgrade/rollback preparation, the
> production checklist and security-operations summary) live in
> `deploy/OPERATIONS.md`. **Backup/restore and disaster recovery** live in
> `deploy/DISASTER_RECOVERY.md`.

---

## 1. Architecture

```
Internet
   │   :80 / :443
   ▼
Nginx (public) ── serves the SPA statics + proxies /api/*
   │                       │
   ▼                       ▼
/opt/e-invoice/frontend    Gunicorn (127.0.0.1:8000, backend.wsgi:application)
                                   │
                                   ▼
                            MySQL 8 (127.0.0.1:3306, dedicated user)
```

- **Frontend** — vanilla JS SPA, no build step. Hash router, so no server-side
  route fallback is needed. Served by Nginx from a staging copy of `frontend/`.
- **Backend** — Flask behind Gunicorn (3 workers × 2 threads). Binds only to
  the loopback interface; Nginx fronts it.
- **Database** — MySQL 8 on the same host (or internal network). The app pools
  connections (`DB_POOL_SIZE`, default 5) and keeps them scoped via
  `pool_reset_session=["ROLLBACK"]`.

---

## 2. Verified vs Requires a real environment

| Item | Status in this repo |
|---|---|
| Gunicorn boots the real WSGI app, serves `/api/health` | ✅ Verified (workers on 127.0.0.1:8000) |
| `deploy/migrate.sh` + `deploy/backup.sh` run against MySQL | ✅ Verified (live dev DB, backup + record-existing) |
| Rate limiting for login/refresh/password/email/upload | ✅ Verified by unit tests |
| Refresh tokens rejected for deactivated accounts | ✅ Verified by unit tests |
| Production config: no dev server, DEBUG off, CORS LAN expansion off by default | ✅ Verified by unit tests |
| Nginx reverse proxy + static serving | ✅ Syntax-reviewed; **requires a real server** to run `nginx -t` and serve traffic |
| HTTPS/TLS + HSTS | ⛔ **Requires real domain + certificate** (config commented in `nginx.conf`) |
| Production MySQL user with least privilege | ⛔ Operator must run the `GRANT` step (§5) on the DB server |
| Real SMTP delivery | ⛔ **Requires real SMTP credentials**; config only (`EMAIL_*`) |

---

## 3. Install from the repository

```bash
sudo mkdir -p /opt/e-invoice
sudo rsync -a --exclude='.git' --exclude='node_modules' \
  --exclude='__pycache__' /path/to/repo/ /opt/e-invoice/
cd /opt/e-invoice

# Create the service user (never run as root)
sudo useradd --system --home /opt/e-invoice --shell /usr/sbin/nologin e-invoice
sudo chown -R e-invoice:e-invoice /opt/e-invoice

# Python virtualenv + dependencies
# Production installs from the lockfile so every install is byte-identical:
# exact pins for all direct AND transitive packages (supply-chain pinning).
sudo -u e-invoice python3 -m venv .venv
sudo -u e-invoice .venv/bin/pip install -r requirements.lock.txt   # includes gunicorn
```

`requirements.txt` is the human-authored range manifest (used for *new* /
development environments and as the policy statement: `>=X,<Y` bounds, no
floating top versions). `requirements.lock.txt` is the generated, exact-pinned
resolution of that manifest (direct + transitive) and is what production and
restore drills install from. After any deliberate dependency change: regenerate
the lockfile in a clean venv (`python3 -m venv /tmp/lockgen && /tmp/lockgen/bin/pip
install -r requirements.txt && /tmp/lockgen/bin/pip freeze`) and re-run
`deploy/check_dependencies.sh` to confirm venv ↔ lock ↔ manifest agreement.

**Environment file.** Copy `.env.example` to `/etc/e-invoice/e-invoice.env`
(owned by `root:e-invoice`, mode `0640`) and set real values:

```bash
sudo mkdir -p /etc/e-invoice
sudo cp /opt/e-invoice/.env.example /etc/e-invoice/e-invoice.env
sudo chown root:e-invoice /etc/e-invoice/e-invoice.env
sudo chmod 0640 /etc/e-invoice/e-invoice.env
```

> Secrets **never live in version control**. Only `.env.example` (placeholders)
> is tracked; `.env`, `*.pem`, `*.key` are git-ignored.

### Environment variables (table)

| Variable | Default | Notes |
|---|---|---|
| `FLASK_ENV` | `development` | **`production`** selects `ProductionConfig` |
| `SECRET_KEY`, `JWT_SECRET_KEY` | — | **Required**; startup aborts if missing in production |
| `JWT_ACCESS_TOKEN_EXPIRES` | `3600` | seconds |
| `JWT_REFRESH_TOKEN_EXPIRES` | `2592000` | seconds (30 days) |
| `DB_HOST` / `DB_PORT` / `DB_NAME` | `localhost` / `3306` / `invoice_system` | MySQL location |
| `DB_USER` / `DB_PASSWORD` | `invoice_app` / `` | dedicated user (§5), never root |
| `DB_POOL_NAME` / `DB_POOL_SIZE` | `invoice_pool` / `5` | connection pool |
| `SERVER_HOST` / `SERVER_PORT` | `0.0.0.0` / `5001` | only used by the (dev) Flask server |
| `CORS_ORIGINS` | dev localhost list | comma-separated exact public origins, **no `*`** |
| `CORS_EXPAND_LAN` | `true` (dev) / **`false`** (prod) | LAN-IP auto-expansion is off in production |
| `SECURITY_HEADERS_ENABLED` | `true` | on by default |
| `CSP_ENABLED` | `false` (dev) / **`true`** (prod) | on by default in `ProductionConfig` |
| `CSP_POLICY` | default | keep in sync with the app if overridden |
| `HSTS_ENABLED` | `false` | enable **only** behind HTTPS |
| `RATE_LIMIT_ENABLED` | `true` | login 5/min · refresh 30/min · password 5/min · email 10/min · upload 5/min |
| `EMAIL_ENABLED` | `false` | set `true` to send taxpayer notifications |
| `EMAIL_PROVIDER` | `smtp` | `smtp` or `gmail` |
| `EMAIL_HOST` / `EMAIL_PORT` | `` / `587` | required when email is enabled |
| `EMAIL_USERNAME` / `EMAIL_PASSWORD` | `` | credentials, never logged or exposed |
| `EMAIL_FROM` / `EMAIL_USE_TLS` / `EMAIL_USE_SSL` | `` / `true` / `false` | SMTP sender settings |
| `FRONTEND_DIST` | `frontend/dist` | only when Flask static serving (`SERVE_STATIC`) is used |
| `LOG_LEVEL` | `INFO` | Python logging level |

---

## 4. Frontend staging (no build step)

The SPA is plain static files. Stage them into the Nginx root:

```bash
sudo mkdir -p /opt/e-invoice/frontend
sudo cp -r frontend/index.html frontend/assets /opt/e-invoice/frontend/
```

**API base URL without editing source.** `frontend/assets/js/config.js`
resolves the API base in this order:

1. `?api=...` query parameter,
2. `window.__EIS_API_BASE__` global,
3. **same-origin `/api` when served from a non-localhost host** (production), or
4. `http://localhost:5001` on localhost (development).

So on `https://invoice.example.com`, the SPA calls the same origin at
`/api/*`, which Nginx proxies to Gunicorn. No source edit per environment.

---

## 5. MySQL production setup

Run on the DB server as `root`:

```sql
CREATE DATABASE invoice_system
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE USER 'invoice_app'@'%' IDENTIFIED BY '<strong-password>';
GRANT SELECT, INSERT, UPDATE, DELETE ON invoice_system.* TO 'invoice_app'@'%';
-- DDL is only needed if the app user runs migrations/backups itself;
-- prefer running migrate.sh with a privileged account instead.
GRANT CREATE, ALTER, DROP, INDEX, REFERENCES ON invoice_system.* TO 'invoice_app'@'%';
FLUSH PRIVILEGES;
```

Match the password in `/etc/e-invoice/e-invoice.env` (`DB_USER`/`DB_PASSWORD`).
The app refuses nothing at the DB level; least-privilege is enforced here.

---

## 6. Schema migrations — ordered, with backup/verify/rollback

Migrations live in `backend/database/migrations/000…012.sql` and run in
lexicographic order. Migration `000` makes the catalog self-contained: it
bootstraps the foundation tables (`companies`, `users`, `roles`, `user_roles`)
that the later files reference, so a fresh database migrates cleanly with no
hand-provisioned schema. `deploy/migrate.sh`:

1. **audits** the tracker: every *applied* file must carry a SHA-256 checksum
   that matches the file on disk, otherwise it refuses to run (drift/orphan
   abort) — unless `--accept-drift` is given,
2. **backs up** the whole DB (`deploy/backup.sh`) before the first pending
   file (skipped automatically when the target database is empty),
3. applies pending files in order,
4. **verifies** each file (exit status + `-- verify: <table>` row-count
   hints, including wrapped multi-table hint blocks),
5. records it (name + checksum) only after success.

```bash
# Read-only status + drift audit
sudo -u e-invoice deploy/migrate.sh --check

# Fresh database: apply everything
sudo -u e-invoice BACKUP_DIR=/var/backups/e-invoice deploy/migrate.sh

# Database already migrated by hand (like this repo's live DB):
# seed the tracker without re-running anything
sudo -u e-invoice deploy/migrate.sh --record-existing

# Apply even when recorded checksums disagree with the files on disk
sudo -u e-invoice deploy/migrate.sh --accept-drift
```

The golden target schema is maintained in
`backend/database/schema_manifest.py` and diffed against any live database
with `schema_verify` (exit 0 = in sync, 1 = drift, 2 = error):

```bash
PYTHONPATH=. .venv/bin/python -m backend.database.schema_verify --db <database>
```

`deploy/schema_drill.sh` proves the catalog is bootstrappable: it creates a
throwaway database, applies every migration in `backend/database/migrations/`
(currently `000…012`) in order, runs `schema_verify` against
it (PASS), and drops the scratch database.

**Rollback.** Schema changes are not automatically reversible. Restore the
backup printed by the run:

```bash
zcat /var/backups/e-invoice/e-invoice-<latest>.sql.gz \
  | mysql -h $DB_HOST -u $DB_USER -p$DB_PASSWORD $DB_NAME
```

---

## 7. Backup & restore

`deploy/backup.sh` produces a consistent logical dump:

```bash
# cron: nightly at 02:17
17 2 * * *  e-invoice  BACKUP_DIR=/var/backups/e-invoice deploy/backup.sh
```

- `--single-transaction --skip-lock-tables` → no downtime, InnoDB-consistent.
- `--routines --events --triggers` → every schema object is captured.
- `gzip -t` integrity check before success; old dumps pruned after
  `RETENTION_DAYS` (default 14).

Restore (documented, verified against a scratch DB):

```bash
zcat /var/backups/e-invoice/e-invoice-<latest>.sql.gz \
  | mysql -h $DB_HOST -u $DB_USER -p$DB_PASSWORD $DB_NAME
mysql -h $DB_HOST -u $DB_USER -p$DB_PASSWORD $DB_NAME \
  -e "SELECT COUNT(*) FROM email_deliveries;"   # spot check
```

---

## 8. Gunicorn — systemd service

Install `deploy/systemd/e-invoice.service`:

```bash
sudo install -m 0644 deploy/systemd/e-invoice.service /etc/systemd/system/e-invoice.service
sudo systemctl daemon-reload
sudo systemctl enable --now e-invoice
sudo systemctl status e-invoice
```

- `Type=notify` — Gunicorn signals readiness to systemd on boot.
- `EnvironmentFile=/etc/e-invoice/e-invoice.env` — secrets stay out of the repo.
- `Restart=always`, hardened (NoNewPrivileges, PrivateTmp, ProtectSystem, …).
- Logs via `journalctl -u e-invoice`.
- Binds `127.0.0.1:8000`. Gunicorn's `--access-logfile -` prints the access
  log to the journal for the operator.

> **Never start production with the Flask dev server.** `FLASK_ENV=production`
> makes the app refuse to boot via `python -m backend.app` (it aborts with
> instructions to use Gunicorn).

---

## 9. Nginx — reverse proxy + static serving

Install `deploy/nginx/e-invoice.conf`:

```bash
sudo install -m 0644 deploy/nginx/e-invoice.conf /etc/nginx/conf.d/e-invoice.conf
sudo nginx -t && sudo systemctl reload nginx
```

The server block:
- serves the SPA root (`/opt/e-invoice/frontend`) and `/assets/*` with caching,
- proxies `/api/*` to `http://127.0.0.1:8000` with `X-Forwarded-*` headers,
  `client_max_body_size 12m` (backend cap is 10 MB),
- has a dedicated `location = /api/health` for probes,
- adds security headers and gzip.

**HTTPS/TLS** — commented block included. Enable after you have a real domain
and certificate (e.g. Let's Encrypt):
- uncomment `listen 443 ssl; server_name; ssl_certificate[_key]` and the
  `return 301 https://…` redirect,
- then set `HSTS_ENABLED=true` in the env file (both the app header and the
  Nginx `Strict-Transport-Security` line).

---

## 10. Firewall

Two sensible profiles:

| Deployment | Allowed inbound |
|---|---|
| Internet-facing (with TLS) | `22/tcp` (SSH), `80/tcp`, `443/tcp` |
| Internal/trusted network | `22/tcp`, `80/tcp`, plus Gunicorn `8000/tcp` scoped to trusted Nginx hosts if Nginx is elsewhere |

Example (ufw):

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp   # when TLS is live
sudo ufw enable
```

Never expose 8000 (Gunicorn) or 3306 (MySQL) to the public internet.

---

## 11. Health checks

`GET /api/health` returns `200 {"success": true, ...}`. Use it for:

- Nginx/uptime probes on the public endpoint,
- systemd or external monitors against `http://127.0.0.1:8000/api/health`,
- the `after` condition in scripts.

It is unauthenticated and excluded from rate limiting.

**Readiness** is a separate signal: `GET /api/health/ready` probes the database
connection pool and returns `200 {"success": true, "data": {"database":"ok"}}`
when operational, or `503 {"success": false, "status": "error", ...}` when the
database is unavailable. Use `/api/health` for "is the process alive?" and
`/api/health/ready` for "can it serve real traffic?" (see
`deploy/OPERATIONS.md` for the full health/readiness runbook).

---

## 12. Email (production readiness)

Phase 7 sends taxpayer notifications for reconciliation runs whose
counterparties lack a tax-authority match. Delivery records persist in
`email_deliveries`; resends are explicit, RBAC-guarded, company-scoped, and
rate-limited (10/min). Outbound email is **off until enabled**:

```bash
EMAIL_ENABLED=true
EMAIL_PROVIDER=smtp              # or gmail
EMAIL_HOST=smtp.provider.com
EMAIL_PORT=587
EMAIL_USERNAME=...
EMAIL_PASSWORD=...               # never committed
EMAIL_FROM=sender@example.com
EMAIL_USE_TLS=true
```

Boot-time validation refuses to start with an invalid mail configuration.
Credentials are never returned by any endpoint (`/api/email/status` exposes
only host/port/enabled/from).

Live-send smoke test from the UI: **Settings → Email → Send test email**.

---

## 13. Troubleshooting

| Symptom | Check |
|---|---|
| `Missing required environment variables` on boot | `SECRET_KEY` / `JWT_SECRET_KEY` set in `/etc/e-invoice/e-invoice.env`; `FLASK_ENV=production` |
| `Refusing to start the Flask development server in production` | run via Gunicorn/systemd, not `python -m backend.app` |
| 502 from Nginx | Gunicorn up? `systemctl status e-invoice`, `journalctl -u e-invoice -e` |
| CORS errors in the browser | `CORS_ORIGINS` includes the **exact** public origin (scheme+host+port); `*` won't work with credentials |
| Uploads > 10 MB rejected | expected; `client_max_body_size 12m` allows Nginx to forward, Flask enforces 10 MB |
| Slow first requests | Gunicorn worker boot + connection pool warm-up; normal |
| "Too many requests" after a bulk operation | rate limits are per client IP/minute; local probes on `127.0.0.1` are exempt |
| Email enabled but not sending | validate `EMAIL_HOST/PORT/TLS`, check `journalctl -u e-invoice` for SMTP errors |

---

## 14. Security checklist (Phase 8)

- ✅ Secrets only from env; `.env`/`.env.*`/certificates git-ignored; only `.env.example` tracked.
- ✅ Startup fail-fast when required secrets are missing in production.
- ✅ No debug mode in production; dev server refused under `FLASK_ENV=production`.
- ✅ CORS: exact-origin allow-list, credentials only, **LAN auto-expansion off** in production.
- ✅ Rate limiting: login 5/min, refresh 30/min, password 5/min, email 10/min, upload 5/min.
- ✅ RBAC on every module; company isolation via scoped repositories; refresh rejected for deactivated users.
- ✅ User administration is tenant-scoped: a company-scoped admin can read/create/modify/delete users only in their own company (company scope from the authenticated token, never the request body); platform admins keep cross-company scope.
- ✅ Uploads: extension + size + content + path-traversal checks (`file_safety.py`), 10 MB cap.
- ✅ Standard security headers on; CSP on by default in production; HSTS opt-in behind HTTPS.
- ✅ Global error handlers return generic bodies, never stack traces or secrets.
- ✅ Request-ID correlation (`X-Request-Id`) across logs and responses.
- ⛔ Operator task: least-privilege MySQL user, strict firewall, TLS cert, real SMTP credentials.