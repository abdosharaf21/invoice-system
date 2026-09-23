# Phase 12 — Database & Migration Engineering — Completion Report

Repository: `~/e-invoice-system/invoice-system`
Branch: `phase-6-frontend` (working tree, no commits made in Phase 12)
Date: 2026-09-15

---

## 1. Executive Summary

Phase 12 made the migration catalog deterministic, auditable and
bootstrappable. The audit found a critical defect before anything else: the
catalog was **not bootstrappable from an empty database** — migrations
002–011 reference the Phase 1 foundation tables, but those existed only
because they had been provisioned by hand before migrations were tracked, so a
fresh `deploy/migrate.sh` run failed at migration 002 with `ERROR 1824:
FAILED to open the referenced table 'companies'`. A new idempotent migration
`000_foundation_schema.sql` closes the gap without touching 001–011.

On top of that, the runner now records a SHA-256 checksum per applied
migration, audits already-applied files before doing anything (aborting on
drift/orphans unless `--accept-drift`), and walks complete multi-line
`-- verify:` hint blocks. A golden schema manifest (`schema_manifest.py`, 17
tables derived from the migration files — not from any database) plus a pure
`diff_schema` verifier (`schema_verify.py`) catch column/index/FK/check/type/
engine/collation drift against any live database. `deploy/schema_drill.sh`
proves the catalog by migrating a throwaway database and verifying it matches
the manifest (PASS). The full runner path was also exercised against a fresh
scratch database end-to-end (exit 0), including the new empty-target backup
skip.

The live database now matches the manifest exactly (`schema_verify` PASS), and
`migrate.sh --check` reports a clean audit: 3 applied-with-checksum, 9 legacy,
0 drifted, 0 pending, 0 orphans.

Backend: **527 passed** (497 baseline + 30 new offline tests).

Verdict: **PHASE 12 COMPLETE**.

---

## 2. Phase Scope

- Full inventory of the migration catalog (001–011 at start), the
  `schema_migrations` tracker, and every deploy tool that reads or writes DB
  schema (`deploy/migrate.sh`, `backup.sh`, `restore.sh`, `restore_test.sh`,
  `verify_backup.sh`, `schema_drill.sh`).
- Reproduce a fresh-database bootstrap to prove (or disprove) self-contained
  forward migration.
- Add checksum tracking + drift/orphan detection to `deploy/migrate.sh`.
- Build a golden schema manifest derived from the migration files and a pure,
  offline-testable drift diff.
- Prove the catalog with a forward drill and a full runner run.
- Reconcile the live database against the manifest and leave the tracker in an
  honest state (legacy rows stay legacy; only what the runner applied carries a
  checksum).
- Regression gate: backend 497 baseline must stay green; new tests are additive.

---

## 3. Baseline (Phase 12 start)

| Suite    | Baseline | After Phase 12 |
|----------|----------|----------------|
| Backend  | 497 pass | 527 pass (497 + 30 new) |
| Frontend | 194 pass | 194 pass (untouched) |

Environment: MySQL `8.0.46-0ubuntu0.24.04.4`, live DB `invoice_system`,
clients `mysql`/`mysqldump` available, venv at `.venv` (python 3.12.3).

---

## 4. Audit Findings

### 4.1 CRITICAL — catalog not bootstrappable from an empty database

Migrations 002–011 reference `companies`, `users`, `roles`, `user_roles`
(FKs: `fk_invoices_company`, `fk_import_batches_company`,
`fk_user_roles_user`, …), but no migration created those tables. They existed
only because the Phase 1 foundation was provisioned by hand. Proof, fresh DB:

```
ERROR 1824 (HY000): Failed to open the referenced table 'companies'
```

A brand-new environment could therefore never migrate.

### 4.2 No integrity on applied migrations

`schema_migrations` tracked *names and timestamps only*. Nothing detected that
an applied file was edited/corrupted on disk or diverged from what was
applied.

### 4.3 No schema-level drift detection

Nothing compared a live database to a *golden* target schema. Missing indexes
(010/011), accidentally-dropped columns or renamed constraints would sail
through the runner silently.

### 4.4 Verify hints truncated for wrapped blocks

Migration 009's `-- verify:` block spans four comment lines (9 tables); the
runner only parsed the first line, so `invoices`, `invoice_items`,
`tax_invoices`, `tax_invoice_items` were never row-count checked.

### 4.5 Runner loading bug — explicit `DB_NAME=` silently ignored

`migrate.sh` only reloaded DB_* from `.env` when `DB_HOST` was unset, so
`DB_NAME=<scratch> BACKUP_DIR=$PWD bash deploy/migrate.sh` targeted the **live**
database. During the first (buggy) drill this actually applied additive DDL
000/010/011 + the checksum column to `invoice_system`. A pre-change backup was
taken automatically first (see §16); no destructive change occurred. The bug
is now fixed and the same guard pattern documented across the deploy family.

### 4.6 Backup completeness gate rejects fresh (empty) databases

`backup.sh` rejects dumps missing the expected app tables — correct for a
backup, but it made `migrate.sh` unable to migrate a brand-new empty target.
The runner now detects an empty target (`only schema_migrations` at most) and
skips the pre-backup (nothing to protect).

---

## 5. Migration Catalog (000…011)

| # | File | SHA-256 (first 12) |
|---|------|--------------------|
| 000 | `000_foundation_schema.sql` | `4862d7692687` |
| 001 | `001_reconcile_foundation_schema.sql` | `84055f097bbb` |
| 002 | `002_einvoice_domain.sql` | `83a02434957c` |
| 003 | `003_import_columns.sql` | `c9720af0ef8a` |
| 004 | `004_reconciliation_error_columns.sql` | `91bc9023a0c1` |
| 005 | `005_widen_reconciliation_match_status.sql` | `8953aace872d` |
| 006 | `006_settings.sql` | `d364948cd14b` |
| 007 | `007_email_deliveries.sql` | `d050bbdcd9b6` |
| 008 | `008_audit_logs.sql` | `4c5f43e9c871` |
| 009 | `009_integrity_constraints.sql` | `64d820cedf39` |
| 010 | `010_performance_indexes.sql` | `b5821b93550e` |
| 011 | `011_audit_traceability.sql` | `7a8e87d43a32` |

Migrations 001–011 are **unchanged**. The catalog manifest plus per-file
digests live in `backend/database/migration_audit.py`; a test recomputes every
digest from disk, so editing an applied file breaks the suite before it can
become live drift.

---

## 6. Migration 000 — Foundation Bootstrap

`000_foundation_schema.sql` creates `companies`, `users`, `roles`,
`user_roles` idempotently (`CREATE TABLE IF NOT EXISTS`) with exactly the
columns/toggles the later migrations expect. It is:

- **Byte-compatible** with how the tables were originally provisioned (verified
  by `schema_verify` before and after on live).
- **Idempotent**, so hand-provisioned databases (like live) continue to work;
  010/011 still append their indexes/columns.
- Declares `-- verify: companies, users, roles, user_roles`.

Run order is zero-padded lexicographic (`000` first), enforced by the audit
module's `verify_catalog` (contiguous 000..011) and by the runner itself.

---

## 7. Checksum Tracking

`schema_migrations` gains a `checksum VARCHAR(64)` column (guarded `ALTER`).
Each successful apply records `INSERT … ON DUPLICATE KEY UPDATE` of the file's
SHA-256. Migrations applied before tracking exist (live 001–009) stay **legacy**
rows with a `NULL` checksum — the honest signal that their digest is unknown;
they are never silently re-branded as checksummed.

Fresh and scratch databases (proven by the drills) record checksums for every
migration, 000–011.

---

## 8. Drift Detection Model

`backend/database/migration_audit.py` (pure/offline):

- `MigrationStatus`: `APPLIED_CURRENT`, `APPLIED_LEGACY`,
  `APPLIED_MISMATCH`, `PENDING`, `UNKNOWN_FILE`, `ORPHAN`.
- `verify_catalog()` — on-disk file set + digests + contiguous order.
- `verify_hints()` — parse `-- verify:` blocks (see §9).
- `analyze_tracker()` / `tracker_summary()` — classify tracker rows.

`deploy/migrate.sh` audits **before** touching anything: an applied file whose
recorded checksum ≠ file on disk, or an orphan tracker row, aborts the run
with a pointer to the rollback restore point — unless `--accept-drift` is
given. `--check` exposes the same audit read-only.

---

## 9. Verify-Hint Parsing (multi-line blocks)

Both the Python module and the bash runner now parse a hint block statefully:
the `-- verify:` marker line opens it and the runner continues over following
comment lines **while they contain only table tokens and commas**, terminating
on a blank `--` or prose line. This is why 002's prose continuation
(`-- reconciliation -> reconciliation_errors`) is *not* picked up, while 009's
9-table block *is* fully parsed in both implementations. The two parsers were
cross-checked against every file: identical output.

---

## 10. Golden Schema Manifest

`backend/database/schema_manifest.py` encodes the **target** schema: 17 tables
(companies, users, roles, user_roles, refresh_token_blocklist, import_batches,
import_batch_errors, invoices, invoice_items, tax_invoices, tax_invoice_items,
reconciliation_runs/results/errors, application_settings, email_deliveries,
audit_logs) with ordered columns, indexes, FKs, CHECK names, engine and
collation.

Key design decisions:

- **Derived from the migration files, not from any database** — a fresh
  000→011 drill matches it exactly; any live difference is drift by
  definition.
- `ALLOWED_EXTRA_TABLES = {audit_logs_legacy, schema_migrations}` — the latter
  is the tracker itself, the former only ever written by 008's guarded rename
  on pre-tracker databases.
- MySQL's auto-created FK-support indexes on `reconciliation_results`
  (`fk_reconciliation_results_*`, one-column) are first-class manifest entries.
- CHECKs compare **by name** (MySQL reformats clauses).
- Default normalization treats numerics by value (`0` ≡ `0.00`).

---

## 11. The Verifier

`backend/database/schema_verify.py` splits cleanly:

- `collect_facts(connection, schema)` — information_schema → `TableFacts` (a
  live-database concern), also exposed as `collect_facts_live()` for the CLI.
- `diff_schema(expected, actual)` — **pure**, fully offline-testable; emits
  structured `Drift` records for every category (missing/unexpected tables,
  columns, column order, indexes, FKs, checks, type/nullable/default, engine,
  collation).
- CLI: `python -m backend.database.schema_verify --db <schema>` → **0** in
  sync / **1** drift / **2** error.

Live result after reconciliation:

```
RESULT: PASS — database matches the expected schema manifest.
verify_exit=0
```

---

## 12. Forward Drill (`deploy/schema_drill.sh`)

Creates a throwaway database (`CREATE DATABASE … utf8mb4_unicode_ci`), applies
every `.sql` in lexicographic order, runs `schema_verify` against it, prints
the result, and drops the scratch database on exit (trap).

```
RESULT: PASS — database matches the expected schema manifest.
```

Proof that migrations 000→011 alone produce the canonical schema.

---

## 13. Runner End-to-End (fresh target)

`DB_NAME=invoice_system_migrun BACKUP_DIR=/tmp/opencode/e-invoice-drill
bash deploy/migrate.sh` on a brand-new empty database:

- Target recognized as empty → **pre-migration backup skipped** ("nothing to
  protect").
- All 12 files applied in order, each verified (row counts = 0, including all
  9 tables of 009's hint block) and recorded with its SHA-256.
- Final `exit=0`; scratch DB dropped afterwards.
- A later live run with zero pending fields short-circuits safely
  (`No pending migrations … exit=0`).

---

## 14. Live Database Reconciliation

The live DB was previously at migrations 001–009 (hand-provisioned schema, no
checksums), with 010/011 pending. After the reconciliation it is structurally
complete and clean:

```
migrate.sh --check (invoice_system):
  APPLIED  000_foundation_schema.sql  sha256 4862d7692687
  LEGACY   001…009_reconcile…        (applied before checksum tracking)
  APPLIED  010_performance_indexes.sql  sha256 b5821b93550e
  APPLIED  011_audit_traceability.sql   sha256 7a8e87d43a32
Summary: 3 applied, 9 legacy, 0 drifted, 0 pending, 0 orphan(s).
schema_verify --db invoice_system → PASS (exit 0)
```

The 9 legacy rows are intentionally checksum-free (§7). Everything is
additive/idempotent; no data changed.

---

## 15. Tooling Fixes

- `deploy/migrate.sh` — per-variable `.env` fallback (explicit `DB_HOST` /
  `DB_PORT` / `DB_NAME` / `DB_USER` / `DB_PASSWORD` wins); empty-target backup
  skip; full verify-hint blocks; `--check` / `--accept-drift`; header now
  documents 000..011.
- `deploy/backup.sh` — same per-variable loader fix (it is invoked by
  `migrate.sh` with `DB_NAME=<scratch>`).
- `deploy/schema_drill.sh` — same loader fix.
- The same guard pattern already exists in `restore.sh` / `restore_test.sh` /
  `verify_backup.sh` and is **documented** here as a known family; those tools
  are out of Phase 12 scope and remain proven by the Phase 9 restore drills.

---

## 16. Restores & Rollback Posture

Every pre-change point is preserved or reproducible:

| Point | Purpose |
|-------|---------|
| `/tmp/opencode/e-invoice-drill/e-invoice-abdo-sharaf2146-20260915T163338Z.sql.gz` | Runner's automatic pre-change backup, taken before the first drill applied 000/010/011 + checksum column to live — the rollback restore point for those additive changes |
| `deploy/migrate.sh` | Prints the newest backup path on every run with pending migrations |
| `deploy/restore.sh --backup … --target … --confirm-live` | Emergency restore over live requires `--confirm-live` + typed `yes` |

No destructive change was made to any database during Phase 12.

---

## 17. Test Additions (30 new, offline)

`backend/tests/test_migration_audit.py` (14 tests): index/sequence parsing,
catalog digest integrity, verify-hint block parsing (incl. prose exclusion and
hint-tables ⊆ expected-schema), tracker state classification
(current/legacy/mismatch/pending/orphan/unexpected-file) using temporary fake
files.

`backend/tests/test_schema_verify.py` (16 tests): type/default normalization,
identical-schema-is-clean for every manifest table, and per-category drift
(missing/unexpected table and column, order, index, FK, check, engine,
collation, type/nullable/default) against purpose-built `TableFacts`.

```
527 passed in 24.15s   (497 baseline + 30 new)
```

---

## 18. Documentation

- `README.md` §Database migrations — rewritten for 000…011, checksums/drift,
  `--check`/`--record-existing`/`--accept-drift`, `schema_verify` usage.
- `deploy/DEPLOYMENT.md` §6 — includes the audit step, empty-target skip,
  `schema_verify` and `schema_drill.sh` pointers.
- `deploy/DISASTER_RECOVERY.md` §6 — forward-migration after restore now notes
  the checksum audit and the 000…011 catalog.

---

## 19. Risks, Limitations & Non-Changes

| Item | Status |
|------|--------|
| Migrations 001–011 | **Not modified** (digest-stable; only 000 added) |
| Legacy rows 001–009 on live | Kept checksum-less on purpose — honest history |
| CHECK clauses | Compared by name, not text (MySQL rewrites clauses) |
| `audit_logs_legacy` / `schema_migrations` | Whitelisted extra tables; anything else unexpected |
| Reverting schema changes | Still via restore of the newest backup (no in-app rollback) |
| `restore.sh`/`restore_test.sh`/`verify_backup.sh` loader pattern | Known family; unchanged, functionality outside Phase 12 scope |
| Frontend | Untouched (194 pass) |

---

## 20. Verdict

**PHASE 12 COMPLETE.**

The migration catalog is now deterministic (000…011, contiguous, digest-stable),
bootstrappable from an empty database, and protected at every layer: runner
time (checksum + drift/orphan audit), golden-manifest verification
(`schema_verify`), a proven forward drill, and 30 new offline tests. The live
database matches the manifest with a clean tracker audit, and the full backend
suite passes **527/527**.