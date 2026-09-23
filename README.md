# Invoice System (E-Invoice)

Backend for an electronic-invoicing platform that reconciles its accounting
records against invoices submitted to the tax authority.

## Tech stack

- Python 3.12 + Flask
- MySQL 8 (raw SQL via a shared connection pool, no ORM)
- JWT auth (access + refresh tokens) with bcrypt password hashing

## API reference

The **authoritative** HTTP API contract is `docs/api/openapi.yaml` (OpenAPI 3).
Every endpoint is exposed under the stable, documented **`/api/v1`** namespace
and, as a compatibility alias, under the unversioned **`/api`** prefix —
both resolve to the same handlers (see `backend/app.py::register_api_v1_aliases`).
Routes, methods, request/response schemas, error codes, rate limits,
`X-Request-Id` correlation and deprecation behavior are described there; do
not hand-duplicate routes elsewhere. Health (`/api/health`) and readiness
(`/api/health/ready`) plus the day-to-day operator procedures live in
`deploy/OPERATIONS.md`.

## Project layout

```
backend/
  app.py                 Flask application factory
  config.py              Environment configuration
  wsgi.py                WSGI entry point
  database/              Connection pool + SQL migrations
  middleware/            Errors, CORS, security headers, rate limit, RBAC
  modules/               Feature modules (Routes → Services → Repos → Models)
    auth/                Login, logout, refresh, blocklist
    users/               Users tied to a company, with roles
    companies/           Company records (legal name, tax registration number)
    invoices/            Accounting invoices + line items
    tax_authority/       E-Invoice documents exchanged with the tax authority
    imports/             Accounting file import pipeline + batch tracking
    reconciliation/      Reconciliation runs, results and errors
  shared/                Shared helpers (security, database cursor)
  tests/                 Pytest suite (mock repositories, no DB required)
```

## Domain & database design

The schema models two sides of the invoice lifecycle and a reconciliation
layer that joins them:

| Table                      | Purpose                                                |
| -------------------------- | ------------------------------------------------------ |
| `companies`                | Tenants; legal name, tax registration number           |
| `users`                    | Users belonging to a company                            |
| `roles`, `user_roles`      | RBAC (Admin, Accountant, Manager, Viewer)              |
| `audit_logs`               | Audit trail of actions                                  |
| `refresh_token_blocklist`  | Revoked JWT ids for logout/refresh                     |
| `import_batches`           | File uploads (CSV/Excel), progress and outcome            |
| `import_batch_errors`      | Structured per-row import failures                        |
| `invoices`                 | Accounting invoices (source of truth on the books)     |
| `invoice_items`            | Line items of accounting invoices                       |
| `tax_invoices`             | E-Invoice documents, kept separate from accounting      |
| `tax_invoice_items`        | Line items of tax authority invoices                    |
| `reconciliation_runs`      | One reconciliation pass per company + period            |
| `reconciliation_results`   | Per-invoice match outcomes                              |
| `reconciliation_errors`    | Errors encountered during a run                         |

Key design decisions:

- Accounting (`invoices`) and tax authority (`tax_invoices`) data are stored
  separately; `tax_invoices.account_invoice_id` links them for reconciliation.
- Users belong to a company and get roles via the normalized `user_roles`
  join table (no denormalized role column).
- Money is `DECIMAL(15,2)`; quantities `DECIMAL(15,4)`.

## Database migrations

Migrations are plain, numbered SQL files under `backend/database/migrations/`
(000…012). `000_foundation_schema.sql` bootstraps the base tables
(`companies`/`users`/`roles`/`user_roles`) so the catalog is self-contained —
a fresh database can be fully migrated without any hand-provisioned schema
(see the Phase 12 report). Applying them by hand against the configured
database:

```bash
for f in backend/database/migrations/*.sql; do
  mysql -h $DB_HOST -u $DB_USER -p$DB_PASSWORD $DB_NAME < "$f"
done
```

For production, use the deterministic runner `deploy/migrate.sh` instead. It:

- records every applied file in a `schema_migrations` table with a SHA-256
  checksum of the file content,
- **audits** already-applied checksums and refuses to run when recorded and
  on-disk digests disagree (drift), unless `--accept-drift` is given,
- takes a pre-migration backup (`deploy/backup.sh`) before the first pending
  file — skipped automatically for a brand-new empty database,
- applies pending files in order, verifies each one (exit status +
  `-- verify: <table>` row-count hints), and records a file only after success.

The current live database is migrated through `011`; migration
`012_reconcile_discrepancy_range.sql` (Phase 15) exists in the catalog and is
**pending** until the next upgrade run. `deploy/migrate.sh --check` reports the
live status, drift and orphans read-only, and `schema_verify` reflects the
target state (a live DB at `011` reports drift until `012`-equivalent state is
reached, as expected).

Other modes: `--check` (read-only status + drift audit), `--record-existing`
(seed the tracker for databases already migrated by hand). Drift against the
golden target schema can also be inspected with
`schema_verify`:

```bash
PYTHONPATH=. .venv/bin/python -m backend.database.schema_verify --db <database>
```

That command compares the live `information_schema` against the expected
manifest (`backend/database/schema_manifest.py`) and exits 0 when in sync,
1 when drift is found, 2 on error. Combined with `deploy/backup.sh` the
workflow is backup → migrate → verify → rollback. See `deploy/DEPLOYMENT.md`
for the full production playbook (Gunicorn, Nginx, HTTPS, systemd, firewall,
backups), and `deploy/DISASTER_RECOVERY.md` for the restore drill.

Copy `.env.example` to `.env` and set real credentials before running.

## Accounting file imports

CSV and XLSX files of accounting invoices can be uploaded and imported.
The file has **one row per invoice line item**; rows belonging to the same
invoice are folded back into one invoice automatically.

### File contract

| Canonical field       | Required | Aliases accepted                                        |
| --------------------- | -------- | ------------------------------------------------------- |
| `uuid`                | no       | invoice_uuid, document_uuid                              |
| `invoice_number`      | yes      | invoice_no, invoice #, number, doc_number               |
| `invoice_type`        | no       | type, document_type; values: sales, purchase, credit_note, debit_note |
| `invoice_date`        | yes      | date, issue_date, document_date                         |
| `due_date`            | no       | payment_due_date, payment_date                          |
| `currency`            | no       | currency_code (default EGP)                             |
| `counterparty_name`   | yes      | customer/customer_name, client/client_name, supplier, vendor, buyer |
| `counterparty_tax_id` | no       | customer_tax_id, supplier_tax_id, vendor_tax_id, tax_id |
| `item_description`    | yes      | description, item_name, product_name, service_name      |
| `quantity`            | no       | qty (default 1.0000)                                    |
| `unit_price`          | no       | price, unit_cost (default 0.00)                         |
| `item_discount_amount`| no       | discount_amount, discount, line_discount_amount         |
| `vat_rate`            | no       | tax_rate (percentage, default 0)                        |
| `vat_amount`          | no       | tax_amount; computed when absent                        |
| `line_total`          | no       | total, gross_amount; computed when absent               |

Headers are matched case-insensitively and tolerate spaces/punctuation
(`"Invoice #"`, `"due date"`). Unknown columns are ignored. Money accepts
thousand separators, `1.234,56` European style, currency symbols and
parenthesised negatives; dates accept `YYYY-MM-DD`, `DD/MM/YYYY`,
`MM/DD/YYYY` and Excel serial numbers. Unknown or ambiguous rows are
reported as errors and skipped — they never block valid rows.

### Endpoints

- `POST /api/imports` — upload a file (`file` multipart field). Creates an
  import batch, processes it, and returns the batch + structured errors.
- `GET /api/imports/<id>?include=errors` — fetch a batch and its per-row
  errors. Scoped to the caller's company.

Requires the `admin`, `accountant` or `manager` role.

### Import rules

- **Grouping**: rows sharing a `uuid` are one invoice; otherwise rows sharing
  `invoice_number`. Invoice-level values must match across the group.
- **Duplicates**: checked in-file first, then against the database. Lookup is
  by `uuid` when present, otherwise by `(company_id, invoice_number)`.
- **Totals**: `line_total = (unit_price × quantity − discount) + vat`, with
  VAT `rate%` of the discounted subtotal. Provided `vat_amount`/`line_total`
  are trusted verbatim.
- **Statuses**: `uploaded` → `processing` → `completed` or `failed`. A batch
  is `completed` when at least one invoice imported (even with row errors),
  `failed` when nothing could be imported.

### Error structure

Every error carries `row_number`, `field`, `error_code` and `message`
(e.g. `MISSING_FIELD`, `INVALID_MONEY`, `INVALID_DATE`, `INVALID_UUID`,
`DUPLICATE_IN_FILE`, `DUPLICATE_IN_DB`, `INCONSISTENT_GROUP`,
`MISSING_HEADER`) and is persisted to `import_batch_errors`.

### Sample CSV

```csv
uuid,invoice_number,invoice_date,currency,counterparty_name,item_description,quantity,unit_price,vat_rate
d3c6e4f7-1a2b-4c3d-8e5f-6a7b8c9d0e1f,INV-100,2024-03-01,EGP,Acme Corp,Widget A,2,100.00,14
d3c6e4f7-1a2b-4c3d-8e5f-6a7b8c9d0e1f,INV-100,2024-03-01,EGP,Acme Corp,Widget B,1,50.00,14
,INV-101,2024-03-02,EGP,Globex Ltd,Gadget,5,20.00,0
```

## Reconciliation

The reconciliation engine compares a company's accounting invoices
(`invoices`) against the e-invoice documents received from the tax authority
(`tax_invoices`) for a given calendar period (`YYYY-MM`). It produces a
deterministic per-invoice match outcome plus field-level errors explaining any
discrepancies, and records everything in a reconciliation run.

### Matching hierarchy

Identities are resolved strictly, in order — no fuzzy matching:

1. Valid UUID on both sides → match by UUID (normalized to lowercase,
   `{}` stripped). This drives the tax authority's `EINVOICE_HASHTEXT` /
   `uuid` linkage.
2. No valid UUID at all → match accounting `invoice_number` against the tax
   invoice's `internal_id`, scoped to the company and case-insensitive.
3. A malformed/unparseable UUID on either side → the invoice is `invalid`
   and never matched: a broken identity must not be guessed.

Matching uses O(1) dictionary lookups over both collections (by UUID, and by
`company_id + internal_id`), so runs are linear and stable.

### Normalization

- **Money**: parsed to `Decimal`, compared with exact equality by default. An
  optional `money_tolerance` (a `Decimal`, non-negative) may be passed per
  run; any difference within tolerance still passes but the absolute
  difference is preserved on the error row.
- **Dates**: compared at date granularity only — time-of-day and timezone are
  ignored (the schema stores no timezone).
- Any unparseable value is treated as absent and flagged `invalid`.

### Compared fields

| Accounting invoice | Tax authority invoice          | Error code on mismatch        |
| ------------------ | ------------------------------ | ----------------------------- |
| `invoice_date`     | `issue_datetime`               | `INVOICE_DATE_MISMATCH`       |
| `currency`         | `currency`                     | `CURRENCY_MISMATCH`           |
| `counterparty_tax_id` | buyer/seller TIN            | `COUNTERPARTY_TAX_ID_MISMATCH`|
| `counterparty_name` | buyer/seller name             | `COUNTERPARTY_NAME_MISMATCH`  |
| `subtotal_amount`  | `total_sales`                  | `SUBTOTAL_AMOUNT_MISMATCH`    |
| `discount_amount`  | `total_discount`               | `DISCOUNT_AMOUNT_MISMATCH`    |
| `subtotal − discount` (derived) | `net_amount`      | `NET_AMOUNT_MISMATCH`         |
| `vat_amount`       | `vat_amount`                   | `VAT_AMOUNT_MISMATCH`         |
| `total_amount`     | `total_amount`                 | `TOTAL_AMOUNT_MISMATCH`       |
| item count         | item count                     | `ITEM_COUNT_MISMATCH`         |
| item quantity sum  | item quantity sum              | `ITEM_QUANTITY_SUM_MISMATCH`  |
| item VAT sum       | item VAT sum                   | `ITEM_VAT_SUM_MISMATCH`       |
| item line-total sum| item line-total sum            | `ITEM_TOTAL_SUM_MISMATCH`     |

The counterparty check accepts a match against either the buyer **or** seller
TIN of the tax invoice (the accounting side carries a single tax id), and the
name is verified against both buyer and seller names.

### Result statuses

- `matched` — identity + all compared fields agree.
- `mismatched` — identity is certain but one or more fields differ (or both
  sides share an invalid value that still allows a confident on-invoice match;
  identification only).
- `missing_in_tax_authority` — accounting invoice has no tax-side counterpart.
- `extra_in_tax_authority` — tax invoice has no accounting-side counterpart.
- `invalid` — identity could not be trusted (malformed UUID in scope), so no
  comparison happened.

Run statuses: `pending` → `running` → `completed` or `failed`. A run is
`completed` once all results/errors are persisted atomically in a single
transaction. `unmatched_count` = mismatched + missing + extra + invalid.
`error_count` is recomputed from persisted error rows.

### Errors

Each error row carries `source_type` (`account`/`tax`), `entity_id`,
`error_type`, `field`, `accounting_value`, `tax_authority_value`,
`difference` and a human-readable `message`. Error type codes include
`INVALID_UUID`, `INVALID_DATE`, `INVALID_FINANCIAL_VALUE` and the field codes
in the table above.

### Endpoints

All require a valid token and the `admin`, `accountant` or `manager` role,
and are scoped to the authenticated user's company:

- `POST /api/reconciliation/runs` — body `{"period": "YYYY-MM"}` plus
  optional `money_tolerance`. Starts and waits for the run, then returns the
  run summary with per-status counts.
- `GET /api/reconciliation/runs` — list runs (`limit`/`offset`).
- `GET /api/reconciliation/runs/<id>` — run + per-status counts.
- `GET /api/reconciliation/runs/<id>/results` — match outcomes enriched with
  invoice number and both UUids / `internal_id`.
- `GET /api/reconciliation/runs/<id>/errors` — field-level discrepancies.

### Limitations

- Reconciliation can only see invoices that exist in both stores; there is no
  pull from an external tax-authority API in this phase.
- Line items are compared as aggregates (count, quantity/VAT/total sums); a
  line-by-line description fingerprint is not implemented.
- Period filters match the leading `YYYY-MM` of the date; invoices are
  assigned to the period of their accounting `invoice_date`.

## Reconciliation reports

Reports are read-only views over a **completed, persisted run** — they never
re-trigger reconciliation, so a run can be reported on and exported as many
times as needed without side effects.

Endpoints require a valid token and the `admin`, `accountant` or `manager`
role. Every endpoint is scoped to the authenticated user's company: a run
belonging to another company returns `404 Not Found`, requests without a
token return `401`, and non-allowed roles return `403`.

### Run summary

- `GET /api/reconciliation/runs/<id>/summary` — run metadata plus per-status
  counts computed from the persisted result rows (SQL aggregation) and the
  error table:

```json
{
  "run": { "id": 1, "company_id": 1, "period": "2024-03",
           "status": "completed", "invoice_count": 4, "tax_invoice_count": 3,
           "matched_count": 1, "unmatched_count": 4, "error_count": 3,
           "started_at": "...", "finished_at": "..." },
  "summary": { "matched": 1, "mismatched": 1,
               "missing_in_tax_authority": 1, "extra_in_tax_authority": 1,
               "invalid": 1, "total_results": 5,
               "unmatched": 4, "errors": 3 }
}
```

`unmatched` = total results minus matched. `errors` = persisted error rows.

### Results & errors reports

- `GET /api/reconciliation/runs/<id>/results`
- `GET /api/reconciliation/runs/<id>/errors`

Both are **dual-mode**: passing any report parameter (pagination or a filter)
returns a paginated envelope, while a bare request keeps the original list
shape.

Paginated envelope (default `page=1`, `page_size=50`, max 200):

```json
{
  "items": [ /* result / error rows */ ],
  "page": 1, "page_size": 50,
  "total": 5, "total_pages": 1
}
```

Results filters: `match_status` (one of the five statuses above), `uuid`
(accounting side), `invoice_number`, `date_from`/`date_to`
(`YYYY-MM-DD`, `date_from` must not be after `date_to`).

Errors filters: `error_type`, `source_type` (`account`/`tax`).

Results rows are enriched with the accounting invoice number, UUID and date,
counterparty details, amounts, and the matched tax invoice's `internal_id` /
UUID / amounts so a report is usable without extra lookups. Row ordering is
deterministic by record id; invalid pagination or filter values return
`400 Bad Request`.

### Exports

- `GET /api/reconciliation/runs/<id>/results/export?format=csv` (default) or `xlsx`
- `GET /api/reconciliation/runs/<id>/errors/export?format=csv` or `xlsx`

Exports stream the full (optionally filtered) dataset in batches, never
loading it into memory. Files are downloaded with server-generated names
(`reconciliation_results_<run_id>.csv`, `reconciliation_errors_<run_id>.xlsx`).
In CSV, money is emitted as its exact decimal string and dates as ISO; in
XLSX, money and dates are native numeric/date cells (no rounding).

### Limitations

- Reports reflect the state of the run at the time it finished; later
  corrections to invoices or tax documents are not re-reflected.
- Date filters apply to the accounting invoice date. Results with no
  accounting side (`extra_in_tax_authority`) have null enrichment fields.

## Frontend (Phase 6)

A framework-free single-page application (`frontend/`) that consumes the Flask
APIs above. It is plain HTML/CSS/ES modules — no build step, no bundler. The
backend remains the single source of truth: the frontend performs no business
calculations and matches the API envelopes exactly as implemented.

### Tech stack & structure

- Vanilla ES modules (`<script type="module">`), CSS custom properties,
  logical properties (RTL-ready), responsive enterprise shell.
- No frameworks, no charting library (status distribution is CSS bars).

```
frontend/
  index.html              SPA root (#app, toast stack, noscript)
  package.json            "npm test" → node --test
  assets/css/             reset, variables (design tokens), base, layout, components
  assets/js/
    app.js                Bootstrap: hash router, auth guard, shell
    config.js             API base resolution, limits, accepted uploads
    config/routes.js      Route table, RBAC gating, sidebar sections
    api/client.js         fetch client: token attach, refresh+retry, downloads
    auth/                 Login endpoints + token/user store
    services/             imports, reconciliation, users API clients
    utils/                escape, format, validation, DOM helpers
    components/           toast, modal, tabs, pagination, report panels/tabs
    pages/                login, dashboard, imports, import detail,
                          reconciliation, run detail, reports, users, account, errors
  test/                   node:test suite (pure-logic, DOM-stubbed)
```

### Running the frontend

The app is static — serve the directory and open it:

```bash
cd frontend
python3 -m http.server 8080 --directory .
```

By default on localhost the JS targets `http://localhost:5001` (the Flask
backend). Override at runtime without rebuilding: open
`http://localhost:8080/?api=http://host:port`, or set `window.__EIS_API_BASE__`
for the whole deployment. When the SPA is served from a **non-localhost**
host in production, the API defaults to the same origin via `/api` (e.g. an
Nginx server block proxying `/api` to Gunicorn) — no source edit per
environment. See `frontend/assets/js/config.js`.

**Production**: serve the SPA from Nginx and run the API on Gunicorn behind it
(Nginx → Gunicorn → Flask → MySQL). Do **not** launch the Flask dev server in
production — `FLASK_ENV=production` refuses to. Full playbook:
`deploy/DEPLOYMENT.md`.

Authentication gates the UI on the same claims as the backend: the sidebar
only shows sections the current role is allowed to use, anonymous users are
routed to the login page, and a forbidden route renders a 403 screen.
`viewer` accounts get a read-only dashboard; operators (`admin`, `accountant`,
`manager`) get imports, reconciliation and reports; `admin` alone manages
users.

### Pages

- `#/login` — sign in (email + password), stores access/refresh tokens.
- `#/dashboard` — KPIs aggregated from the real reconciliation runs plus the
  latest completed run's status distribution; read-only notice for `viewer`.
- `#/imports` — drop-zone upload of CSV/XLSX accounting files, progress, and
  the batch outcome (`POST /api/imports` returns `{batch, errors}`).
- `#/imports/:id` — batch detail with per-row errors.
- `#/reconciliation` — start a run for a `YYYY-MM` period (synchronous;
  redirects to the run detail).
- `#/reconciliation/:id` — run metadata, summary counts, CSS status bars and
  the shared Results/Errors panels with filters, pagination and export.
- `#/reports` — run picker over the same shared Results/Errors panels.
- `#/users` — admin-only user CRUD (create, edit, activate/deactivate, reset
  password, delete) with destructive-action confirmation.
- `#/account` — profile and change-password form.
- 403/404 screens for forbidden/unknown routes.

### Reports, filters, pagination & exports

Results and Errors are one shared component (`components/reportTabs.js`)
used by both the run detail and the reports page — no duplicated tables.
Both panels stay server-side: filters (`match_status`, `uuid`,
`invoice_number`, `date_from`/`date_to` for results; `error_type`,
`source_type` for errors) and pagination (`page`, `page_size`) are sent to
the API, never applied in JavaScript. CSV and XLSX exports of the fully
filtered dataset are streamed as downloads with server-generated filenames.

### Frontend tests

```bash
cd frontend && npm test        # node:test, no external dependencies
```

Covers validation, formatting/labels, HTML escaping, the auth store and role
helpers, the API client (error envelopes, refresh-and-retry, query building),
route resolution plus RBAC gating, and report table/pagination rendering.

### Run a frontend + backend integration

```bash
cp .env.example .env           # set DB creds; DB schema via migrations (below)
.venv/bin/python backend/app.py   # API on 0.0.0.0:5001
cd frontend && python3 -m http.server 8080 --directory .
# open http://localhost:8080/ and sign in with an admin/operator account
```

### Known limitations

- The SPA is verified against the API contract and unit-tested; interactive
  browser automation (drag/drop, canvas-free CSS bars) is covered by the
  functional unit suite, not by a browser E2E harness.
- Reports reflect the state of the run at the time it finished; later
  corrections to invoices or tax documents are not re-reflected in the UI.
- `viewer` accounts cannot reach reconciliation/report endpoints because the
  backend requires the `admin`/`accountant`/`manager` roles; the UI hides
  those sections and the backend enforces them.

## Settings (Phase 6.5)

Application-wide, organisation, and per-user settings that persist in the
database and are consumed by both the API and the SPA shell (application and
company names are rendered from settings, never hard-coded).

### Data model

`006_settings.sql` adds:

- `application_settings` — a generic key/value table. Keys are unique; values
  carry a `value_type` (`string`, `integer`, `boolean`, `json`) so reads return
  typed values. Eight defaults are seeded (`application_name`,
  `application_subtitle`, `default_language`, `default_theme`, `date_format`,
  `number_format`, `timezone`, `pagination_size`).
- `companies` gain `logo_path`, `website`, `default_currency`,
  `default_tax_rate`, `fiscal_year_start`.
- `users` gain `language`, `theme`, `date_format`, `number_format`,
  `timezone`, `avatar_path`, `pagination_size`.

### API

| Method | Path | Access | Purpose |
| ------ | ---- | ------ | ------- |
| GET | `/api/settings/application` | any authenticated user | safe frontend subset (8 keys) |
| PUT | `/api/settings/application` | admin | update one or more application settings |
| GET | `/api/settings/application/all` | admin | every setting including non-frontend ones |
| GET | `/api/settings/company` | any authenticated user | the caller's own company profile |
| PUT | `/api/settings/company` | admin | update the caller's company settings |
| GET | `/api/settings/user` | any authenticated user | the caller's own preferences |
| PUT | `/api/settings/user` | any authenticated user | update *only* the caller's preferences |

Validation (`backend/modules/settings/validator.py`): languages `en/ar/fr/de/es`,
themes `light/dark`, date formats `YYYY-MM-DD | DD/MM/YYYY | MM/DD/YYYY |
DD-MM-YYYY`, number formats `#,##0.00 | #,##0 | 0,00 | 0.00`, pagination
5–200, plus email/currency/tax-rate/fiscal-year checks for company settings.
Invalid values are rejected with a `400` and an explanatory message. Password
changes remain on the existing `/api/auth/change-password` endpoint.

The API validator accepts all five languages, but the Settings UI currently
offers only the two with shipped dictionaries (`en`, `ar`) — the other values
are reserved for future dictionaries.

Company writes require an admin but are always scoped to the admin's own
company (resolved from the authenticated user, never from the request body).

### Frontend

The SPA gains a `#/settings` route (reachable from the account menu) with three
sections: **Application** and **Company** (admin only) and **My profile** (all
roles). The shell reads application/company settings via
`frontend/assets/js/settings/store.js` so the sidebar brand, document title,
and company label reflect the stored values.

## Email notifications (Phase 7)

Outbound, send-only email notifications. The backend submits fully-formed
messages to an SMTP server with `smtplib`; it never opens, reads, imports,
synchronizes or deletes mailbox items (no Gmail read/inbox APIs, no OAuth).

Notifications are sent to the **taxpayers/counterparties** of a run — the
companies and individuals your invoices involve — never to internal users
and never to the organisation's billing address. After a reconciliation run
finishes, every taxpayer with at least one affected invoice (mismatched,
missing from the tax authority records, or invalid) receives a single grouped
summary email naming only their affected invoices and the differences to
review.

### Configuration

All email settings come from environment variables (`.env`). When
`EMAIL_ENABLED=true` the application validates the configuration at startup
and refuses to boot if it is unusable. Credentials are never exposed through
the API or logged.

| Variable | Default | Purpose |
| -------- | ------- | ------- |
| `EMAIL_ENABLED` | `false` | master switch; `false` = sending disabled (and deliveries are recorded as `skipped`) |
| `EMAIL_PROVIDER` | `smtp` | `smtp` (generic) or `gmail` |
| `EMAIL_HOST` | (empty) | SMTP server host; `smtp.gmail.com` for Gmail |
| `EMAIL_PORT` | `587` | SMTP port (465 with implicit TLS + `EMAIL_USE_SSL=true`) |
| `EMAIL_USERNAME` | (empty) | optional SMTP login user (requires `EMAIL_PASSWORD`) |
| `EMAIL_PASSWORD` | (empty) | optional SMTP login password (never logged/returned) |
| `EMAIL_FROM` | (empty) | envelope `From` address (required when enabled) |
| `EMAIL_USE_TLS` | `true` | STARTTLS after connect |
| `EMAIL_USE_SSL` | `false` | implicit TLS (mutually exclusive with `EMAIL_USE_TLS`) |

There is no recipient-role configuration: recipients come from the accounting
data, not from application settings.

### Recipients

Recipient email addresses are captured during invoice import and stored on the
accounting invoice as `counterparty_email` (migration 007, an optional column
added `AFTER updated_at` so the existing positional row mapping is untouched).
During planning the run's affected invoices are grouped by taxpayer:

1. invoices whose invoice has a valid `counterparty_email` are grouped per
   email address — one delivery per taxpayer per run;
2. counterparties with no email on record produce a single `no_email` delivery
   (with a recorded reason, never a send attempt);
3. counterparties with an unparsable address produce a single `invalid`
   delivery.

### Delivery tracking

Every planned delivery is recorded in the `email_deliveries` table (one row
per run + recipient), so every run has an auditable list:

| Status | Meaning |
| ------ | ------- |
| `pending` | recorded, send not yet attempted |
| `sent` | SMTP accepted the message |
| `failed` | SMTP rejected/timed out; `failure_reason` is recorded |
| `skipped` | email sending disabled in the configuration |
| `no_email` | taxpayer has no email address on record |
| `invalid` | taxpayer email address is invalid |

`sent` and `failed` carry the originating `X-Request-Id` correlation id and
attempt timestamps (`attempted_at`, `sent_at`). Non-send rows keep the reason
the send did not happen.

### Delivery behavior

- Notifications are planned and attempted **after** the reconciliation
  transaction has committed; an email failure can never roll back or corrupt
  a run.
- `notify_run_summary` is best-effort: empty result sets, a disabled module
  and SMTP failures are all recorded and never raise into the reconciliation
  service.
- No retry loop is used. A `failed`/`pending`/`skipped` delivery can be
  resent explicitly from the run's delivery list; the message is rebuilt from
  the persisted affected results (nothing sensitive is stored or replayed).
- Every outbound message is HTML-escaped and contains only business
  identifiers (invoice number, date, status, amounts); internal database ids,
  request ids, JWTs, SMTP credentials and stack traces are never included.

Templates (`backend/modules/email/templates.py`) render plain-text + HTML
versions of the reconciliation discrepancy summary via
`render_reconciliation_discrepancy(context)`.

### API

| Method | Path | Access | Purpose |
| ------ | ---- | ------ | ------- |
| GET | `/api/email/status` | admin | enabled flag, provider, host/port, from address, workflows (no credentials) |
| POST | `/api/email/test` | admin | send one test message to the single address in the body |
| GET | `/api/reconciliation/runs/:id/email-deliveries` | admin, accountant, manager | tracked deliveries for a run (company-scoped) |
| POST | `/api/reconciliation/runs/:id/email-deliveries/:delivery_id/resend` | admin, accountant, manager | explicitly resend one delivery |

`POST /api/email/test` is the only diagnostic send-forced endpoint. It is
admin-only, takes exactly one recipient that the admin explicitly provides,
and returns `400` when email is disabled or the address is invalid and `502`
on SMTP failure. It is never an open relay. Resend is company-scoped to the
run and returns `400` when email is disabled or the stored recipient is
invalid and `502` on SMTP failure.

### Files

`backend/modules/email/` — `provider.py` (smtplib transport + config
validation), `validator.py` (recipient checks), `templates.py`,
`model.py` + `repository.py` (`email_deliveries` tracking), `service.py`
(recipient planning, delivery and audit), `routes.py` (admin status/test
endpoints). The reconciliation service (`service.py`,
`routes.py`) invokes the summary notification after a completed run and
exposes the delivery list + resend endpoints. Migration
`backend/database/migrations/007_email_deliveries.sql` adds
`invoices.counterparty_email` and creates `email_deliveries`.

## Running tests

```bash
.venv/bin/python -m pytest backend/tests
```

The suite runs against fully mocked repositories — no database required.

## Dependency management (Phase 13)

Python 3.12 + Flask runtime, MySQL 8, JWT + bcrypt.

- `requirements.txt` — **runtime/production** manifest: every entry is a bounded
  range (`name>=a,<b`), no floating versions.
- `requirements.lock.txt` — **autogenerated, exact-pinned** resolution of the
  runtime manifest (direct *and* transitive). Production and restore drills
  install from this file for byte-identical environments.
- `requirements-dev.txt` / `requirements-dev.lock.txt` — development manifest
  (`-r requirements.txt` + pytest). `pytest` is intentionally **not** in the
  production set. Use `pip install -r requirements.txt -r requirements-dev.txt`.
- `frontend/package-lock.json` — npm lockfile (lockfileVersion 3) verifying the
  frontend pins **zero** dependencies; there is no build step and no CDN use.

Change policy: never edit a lockfile by hand. After a deliberate dependency
change, regenerate in a clean venv (`python3 -m venv /tmp/lockgen && /tmp/lockgen
/bin/pip install -r requirements.txt`), update the affected `RUNTIME_*` /
`DEV_ONLY_*` inventory sets in `backend/tests/test_dependency_manifest.py`, and
re-run `deploy/check_dependencies.sh` (add `--online` for pip-audit + npm audit).