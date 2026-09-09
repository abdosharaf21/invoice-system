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
    imports/             File upload/import tracking + row errors
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
| `import_batches`           | File uploads (CSV/Excel) and their progress             |
| `import_batch_errors`      | Per-row import failures                                 |
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
```

Copy `.env.example` to `.env` and set real credentials before running.

## Running tests

```bash
.venv/bin/python -m pytest backend/tests
```

The suite runs against fully mocked repositories — no database required.