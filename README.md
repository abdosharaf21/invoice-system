# Invoice System (E-Invoice)

Backend for an electronic-invoicing platform that reconciles its accounting
records against invoices submitted to the tax authority.

## Tech stack

- Python 3.12 + Flask
- MySQL 8 (raw SQL via a shared connection pool, no ORM)
- JWT auth (access + refresh tokens) with bcrypt password hashing

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

Migrations are plain, numbered SQL files under `backend/database/migrations/`.
Apply them in order against the configured database:

```bash
mysql -h $DB_HOST -u $DB_USER -p $DB_NAME \
  < backend/database/migrations/001_reconcile_foundation_schema.sql
mysql -h $DB_HOST -u $DB_USER -p $DB_NAME \
  < backend/database/migrations/002_einvoice_domain.sql
mysql -h $DB_HOST -u $DB_USER -p $DB_NAME \
  < backend/database/migrations/003_import_columns.sql
mysql -h $DB_HOST -u $DB_USER -p $DB_NAME \
  < backend/database/migrations/004_reconciliation_error_columns.sql
mysql -h $DB_HOST -u $DB_USER -p $DB_NAME \
  < backend/database/migrations/005_widen_reconciliation_match_status.sql
```

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

## Running tests

```bash
.venv/bin/python -m pytest backend/tests
```

The suite runs against fully mocked repositories — no database required.