# Email Configuration Audit — Diagnostic Report

Status: **investigation only — no implementation changes made**
Date: 2026-09-19

---

## Summary / verdict

Case **E applies — the current runtime genuinely has no SMTP configuration.**
(Closely allied with Case A: the backend *requires* `EMAIL_*` environment
variables and none are supplied.)

- The backend email module, provider, API and frontend UI are all wired and
  behaving correctly for the input they receive.
- Every layer is reporting `enabled: false` because **no `EMAIL_*` variable is
  set anywhere** — not in `.env`, not in the running backend process's
  environment, not in the current shell.
- The Settings → Email & Notifications page is **not** broken; it is faithfully
  rendering the backend's truthful "disabled" status.
- Real SMTP sending capability exists and would work immediately once the
  `EMAIL_*` variables are provided. **Gmail SMTP + App Password is supported by
  the existing implementation** (see Gmail section below).

No secrets are printed in this report; variables are only described as
present / absent / empty / set.

---

## 1. Configuration source

- No `.env` file exists at the repository parent; the app loads
  `invoice-system/.env` (present, 316 bytes).
- `invoice-system/.env.example` documents the intended schema, including the
  full `EMAIL_*` block (defaults: `EMAIL_ENABLED=false`, `EMAIL_PROVIDER=smtp`,
  `EMAIL_HOST=` empty, `EMAIL_PORT=587`, `EMAIL_USE_TLS=true`,
  `EMAIL_USE_SSL=false`).
- Config loading: `backend/config.py::_load_env_file()` loads `.env` with
  `override=False`, then `BaseConfig` reads values straight from
  `os.environ`. Process/environment variables thus take precedence over `.env`.

## 2. Required environment variables

| Variable | Purpose |
| --- | --- |
| `EMAIL_ENABLED` | Master switch (`1/true/yes/on`). Off by default. |
| `EMAIL_PROVIDER` | `smtp` (default) or `gmail`. |
| `EMAIL_HOST` | SMTP server hostname. Required when enabled. |
| `EMAIL_PORT` | SMTP port (default 587). |
| `EMAIL_USERNAME` | SMTP AUTH username. Must pair with password. |
| `EMAIL_PASSWORD` | SMTP AUTH password (e.g. a Gmail App Password). |
| `EMAIL_FROM` | Sender/From address. Required when enabled. |
| `EMAIL_USE_TLS` | STARTTLS on the plain connection (default true). |
| `EMAIL_USE_SSL` | Implicit-TLS/SSL connection (mutually exclusive with TLS). |

When `EMAIL_ENABLED=true` the config is validated at startup
(`EmailConfig.validate()` in `backend/modules/email/provider.py`):
`EMAIL_HOST` and `EMAIL_FROM` required; port in 1–65535; TLS and SSL not both
set; `EMAIL_USERNAME` and `EMAIL_PASSWORD` set together; provider in
`smtp`/`gmail`. An invalid combination **refuses to boot**. When `EMAIL_ENABLED`
is false the validator is skipped, so a machine without SMTP settings starts
normally (the current situation).

## 3. Variable status (values redacted)

| Variable | `.env` | Running process env | Shell env | Verdict |
| --- | --- | --- | --- | --- |
| `EMAIL_ENABLED` | absent | absent | absent | → default `false` |
| `EMAIL_PROVIDER` | absent | absent | absent | → default `smtp` |
| `EMAIL_HOST` | absent | absent | absent | empty |
| `EMAIL_PORT` | absent | absent | absent | → default `587` |
| `EMAIL_USERNAME` | absent | absent | absent | empty |
| `EMAIL_PASSWORD` | absent | absent | absent | empty |
| `EMAIL_FROM` | absent | absent | absent | empty |
| `EMAIL_USE_TLS` | absent | absent | absent | → default `true` |
| `EMAIL_USE_SSL` | absent | absent | absent | → default `false` |

Running backend process verified via `/proc/<pid>/environ`: `DB_*`,
`SECRET_KEY`, `JWT_SECRET_KEY`, `FLASK_ENV`, `LOG_LEVEL` are present (loaded
from `.env`); **no `EMAIL_*` variable is present**.

## 4. Email service enabled? SMTP configured?

- **Email service enabled: NO.** `EMAIL_ENABLED` unset ⇒ `BaseConfig` default
  `False` (also the `.env.example` default, so nothing silently enables it).
- **SMTP configured: NO.** `EMAIL_HOST` / `EMAIL_USERNAME` / `EMAIL_FROM` are
  empty (both password fields unset).
- Runtime also confirmed by reads of the live process environment, not just the
  file on disk.

## 5. End-to-end trace through the exact code path

1. **Config loading** — `backend/config.py` (`BaseConfig.EMAIL_ENABLED =
   _env_bool("EMAIL_ENABLED", False)`, `EMAIL_HOST = os.environ.get("EMAIL_HOST", "")`,
   etc.).
2. **Into Flask** — `backend/app.py` copies every `EMAIL_*` into
   `app.config` (lines 155–163), then builds the service:
   `EmailService(config_mapping=app.config, ...)` (app.py:284–290).
3. **Service/provider** — `EmailService.__init__` → `EmailConfig.from_mapping(app.config)`
   → `EmailConfig(enabled=False, provider="smtp", host="", port=587, ..., use_tls=True)`.
   `SMTPEmailProvider` is constructed with that frozen config; nothing is sent.
4. **API endpoint — exact backend endpoint:**
   `GET /api/email/status`
   (blueprint `backend/modules/email/routes.py:46-51`, `@require_admin`,
   `_email_service.get_status()`).
5. **Backend response shape** (redacted; credentials never appear — the
   backend deliberately does not expose them):

```json
{
  "success": true,
  "data": {
    "enabled": false,
    "provider": null,
    "host": "",
    "port": 587,
    "from_addr": null,
    "use_tls": true,
    "use_ssl": false,
    "workflows": [
      {
        "name": "reconciliation.discrepancies",
        "description": "After a reconciliation run, email a grouped summary …"
      }
    ]
  }
}
```

   Note: `provider` and `from_addr` are nulled by `get_status()` when disabled;
   `host` is the (empty) value; `use_tls`/`use_ssl` always reflect the config.
6. **Frontend API call** — `frontend/assets/js/services/email.js`:
   `getEmailStatus()` ⇒ `api.get("/api/email/status")`; the shared client
   unwraps `data`.
7. **Frontend enable check** — `frontend/assets/js/pages/settings.js`
   `mountEmailSection()`:
   `const enabled = Boolean(data && data.enabled);`
8. **Frontend mapping** — same function renders the `<dl>` from
   `data.provider` / `data.host:data.port` / `data.from_addr` /
   `connectionLabel(data.use_tls, data.use_ssl)`; `valueOrDash()` turns
   `null`/empty into `—`; the test form is disabled when `!enabled`.

### The exact point the Settings page gets "disabled"

The disabled state is decided by the backend: `EmailConfig.enabled` is `false`
(`provider.py`) → `get_status()["enabled"] === false` (`service.py:103-117`)
→ returned by `GET /api/email/status` → the frontend's
`Boolean(data.enabled)` is `false` → warning banner
("Email sending is currently disabled…"), `—` for Provider / SMTP server /
From address, and the test form disabled with the hint
"Enable email in the server configuration to send test messages."

Minor UI nuance: the **Connection security** row is *not* `—`; with no config
it renders label text "STARTTLS" because `use_tls` defaults to `true` and the
frontend maps it via `connectionLabel(true, false)`.

## 6. Would a real test email currently be sent?

**No.** `POST /api/email/test` would return
`400 "Email is not enabled"` (`EmailDisabledError` at `service.send_test`,
mapped at `routes.py:67-68`). No message leaves the process. Not sent during
this audit.

## 7. Gmail SMTP + App Password support

**Supported by the existing implementation** — no new Gmail integration or SMTP
subsystem needed:

- Host/port: any SMTP server string is passed through unchanged; Gmail works with
  `EMAIL_HOST=smtp.gmail.com`.
- Modes: `EMAIL_USE_TLS=true` + `EMAIL_PORT=587` ⇒ STARTTLS
  (`provider._connect` → `smtplib.SMTP(host, 587)` then `starttls`), and
  `EMAIL_USE_SSL=true` + `EMAIL_PORT=465` ⇒ implicit TLS
  (`smtplib.SMTP_SSL`). Both are implemented.
- Account: `EMAIL_USERNAME` is submitted verbatim to `server.login()`, so a full
  Gmail address works.
- App Password: `EMAIL_PASSWORD` is passed to `server.login()`; a Google App
  Password is a standard SMTP AUTH password, so it works — no special code path
  is required.
- `EMAIL_PROVIDER` accepts `"gmail"` (validation) but has **no dedicated code
  path**; `gmail` behaves identically to `smtp`, which is sufficient because
  Gmail is reached via plain SMTP + App Password.
- Sender: `EMAIL_FROM` is used as the message `From`; for Gmail it should be the
  Gmail address matching `EMAIL_USERNAME`.

## 8. Test-send & notification implementation (verified, not modified)

- **Test send** — `EmailService.send_test` → `SMTPEmailProvider.send` →
  connect (TLS/SSL per config) → `login(username, password)` when both set →
  `send_message`; clean `EmailAuthError`/`EmailTransportError` mapping in
  `routes.py` (502 on auth/transport failure).
- **Reconciliation notifications** — `ReconciliationService._notify_discrepancies`
  (`reconciliation/service.py:447-461`) calls `EmailService.notify_run_summary`
  best-effort after a run commits; failures are logged and never affect the run.
  When disabled, deliveries are recorded as `skipped` (see
  `_create_delivery_record`, `service.py:345-356`).

## 9. Root cause

**The `EMAIL_*` environment variables are simply not set.** The backend loads
them correctly, the service reads them correctly, `GET /api/email/status`
reports them correctly, and the frontend renders correctly. Every layer says
"disabled" because `EMAIL_ENABLED` defaults to `false` (and SMTP fields are
empty) in the absence of configuration. The code is production-ready; it has
simply never been pointed at an SMTP server.

## 10. Minimal fix required (not applied)

1. Add the `EMAIL_*` block from `.env.example` to `invoice-system/.env`
   (or export it in the deployment environment / process manager):
   - `EMAIL_ENABLED=true`
   - `EMAIL_PROVIDER=smtp` (or `gmail`)
   - `EMAIL_HOST=smtp.gmail.com` (Gmail) or the appropriate SMTP relay
   - `EMAIL_PORT=587`, `EMAIL_USE_TLS=true` (STARTTLS) — or `EMAIL_PORT=465`,
     `EMAIL_USE_SSL=true` (implicit TLS)
   - `EMAIL_USERNAME=<full Gmail address>`
   - `EMAIL_PASSWORD=<Gmail App Password>`
   - `EMAIL_FROM=<the same Gmail address>`
2. Restart the backend process (config is read at boot; `.env` changes require a
   restart).
3. Sanity checks afterwards: `GET /api/email/status` returns `enabled: true`,
   `provider`, `host`, `from_addr`; Settings → Email & Notifications shows the
   enabled banner and an active test form; optionally `POST /api/email/test`
   with a single recipient (only if explicitly requested).

No database, migration, backend, or frontend code change is required to enable
email. (If `EMAIL_ENABLED=true` is ever set with incomplete values, the backend
refuses to boot rather than half-configure — see §3 validation notes.)