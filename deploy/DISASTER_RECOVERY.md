# E-Invoice & Reconciliation System — Backup, Recovery & Disaster Recovery (Phase 9)

Operations runbook for backup, verification, restore, and disaster-recovery of
the MySQL database. Everything below was **proven end-to-end** against an
isolated recovery database (`invoice_system_recovery`) in this development
environment; the live database was never modified.

---

## 1. Durable state and recovery scope

| Artifact | Durable? | Recoverability |
|---|---|---|
| MySQL database (`invoice_system`) | Yes — **only** durable application state | Logical backup + restore (this runbook) |
| Source code + migrations + `.env` | Yes | Re-clone + apply migrations |
| Uploaded import files | No — processed in-memory (`content: bytes`), never persisted outside MySQL | Documented limitation; rows live in `import_batches` / `invoices` after import |
| Frontend build | No build step (vanilla SPA) | Served from the repo copy |

> **Limitation:** importing the *files* themselves cannot be recovered from a
> DB backup — only the imported rows. Re-import requires the original files.

## 2. Tools

| Script | Purpose |
|---|---|
| `deploy/backup.sh` | Full logical gzip dump + `.sha256` completion marker + retention |
| `deploy/verify_backup.sh` | Integrity verification: `--backup <file>` or `--restored-db <db>` |
| `deploy/restore.sh` | Guarded restore into a target database (live-DB double-gate) |
| `deploy/restore_test.sh` | Isolated end-to-end restore drill against `invoice_system_recovery` |
| `deploy/restore_check.py` | App-level parity + authentication + RBAC verification on a restored DB |
| `deploy/migrate.sh` | Migration runner; runs `backup.sh` before any pending migration |
| `deploy/DISASTER_RECOVERY.md` | This runbook |

## 3. Backup procedure

```bash
# Defaults: BACKUP_DIR=/var/backups/e-invoice, daily retention 14 days.
BACKUP_DIR=/var/backups/e-invoice deploy/backup.sh

# Verify the archive (also doubles as the scheduled cron step):
deploy/verify_backup.sh --backup /var/backups/e-invoice/e-invoice-*.sql.gz
```

- `--single-transaction`: consistent snapshot, no table locking.
- Retention prunes only **verified** archives older than `RETENTION_DAYS` and
  never deletes the newest archive or any unverified file.
- An archive is trustworthy only when its `.sha256` sidecar exists; the sidecar
  doubles as the "dump finished successfully" completion marker.
- Credentials never appear on the command line (temp `[client]` defaults-file,
  mode 0600); logs contain no secrets.

## 4. Restore procedure

```bash
# Into an isolated database (safe, no confirmation prompts when using --yes):
deploy/restore.sh --backup /var/backups/e-invoice/e-invoice-....sql.gz \
                  --target invoice_system_recovery --recreate --yes

# Emergency restore over the live DB (requires a human: --confirm-live + typed yes):
deploy/restore.sh --backup /var/backups/e-invoice/e-invoice-....sql.gz \
                  --target invoice_system --recreate --confirm-live
```

Restore steps: verify archive exists → `.sha256` marker present → checksum
match → recreate/create target → load dump → structural checks (tables +
migration tracker). `--dry-run` validates everything but changes nothing.

**Two distinct restore modes — never conflate them:**

| Mode | Command shape | Safeguards | When |
|---|---|---|---|
| **Isolated recovery drill** | `--target invoice_system_recovery --recreate --yes` | target is never the live DB; `--yes` is only honoured for non-live targets; the live DB is used read-only as parity source | routine verification (cron, after any backup change, before upgrades) |
| **Actual live restoration** | `--target <live DB> --recreate --confirm-live` | equal target + live DB requires `--confirm-live` **and** a human typing `yes`; `--yes` alone is never enough, so a script can't silently hit production | real disaster recovery only, with an operator present |

A scripted (`--yes`) restore **cannot** target the live database by design;
the interactive human gate is deliberate and must not be weakened.

## 5. Disaster recovery run

`deploy/restore_test.sh` is the full drill and the acceptance test:

1. restore the newest backup into an isolated DB,
2. `verify_backup.sh --restored-db` (tables, migration tracker, data),
3. `restore_check.py`: row-count + monetary-fingerprint parity vs source,
   real Flask app pointed at the restored DB (health/readiness), real login
   (correct + wrong password), `/api/auth/me`, RBAC company isolation
   (company-999 invisible to the other tenant), and read paths
   (invoices by period, reconciliation runs, settings, audit trail, user roles).

Expected result: `RESULT: PASS` with `CHECK SUMMARY: 36 passed, 0 failed`.

## 6. Forward migration after restore

A restored DB is at the backup's schema version. Upgrade it with the same
tooling used for live deploys (it pre-backs-up the restored target, and now
audits checksums first — verifying each *applied* file's digest matches what
was recorded before it applies anything):

```bash
DB_NAME=invoice_system_recovery BACKUP_DIR=/var/backups/e-invoice/drill deploy/migrate.sh
```

Verified: the isolated DB restored at migration 009 then adopted
`010_performance_indexes.sql` (verify hint `tax_invoices` row count passed).
The format now covers the full `000…012` catalog, including the
`000_foundation_schema.sql` bootstrap for brand-new empty targets (an empty
database skips the pre-backup step and is migrated from scratch). `--check`
reports the same status/drift audit used on live. As of Phase 17 the live
database sits at migration `011` with `012_reconcile_discrepancy_range.sql`
pending; a restored backup is at the schema version of the backup and is
forward-migrated exactly like a live deploy.

## 7. RPO / RTO framing

| Metric | Current | Notes |
|---|---|---|
| RPO (point-in-time) | Interval between **verified** backups (default daily); binlog PITR **not** enabled | `binlog_format=ROW` and `log_bin=1` support recovery, but `gtid_mode=OFF` and no binlog retention policy exist → RPO is bounded by the last verified backup, not by binlogs |
| RTO (recovery time) | Restore of the full logical dump (~7 s drill on this dev dataset), then forward migrations if behind | Grows with data volume; scale = `mysqldump --single-transaction` size |

**Server-loss bucket:** recover to a fresh MySQL 8 host by re-running
`deploy/migrate.sh` (schema), then restoring the newest verified backup into
the live DB (`--recreate --confirm-live`), then `deploy/restore_test.sh` to
prove correctness.

## 8. Retention and scheduling

- Cron: run `backup.sh` then `verify_backup.sh --backup <newest>` daily.
- Old backups beyond `RETENTION_DAYS` (14) are pruned automatically, newest kept.
- Keep `.sha256` sidecars next to archives; never restore a file without one.

## 9. Verified evidence (this environment)

| Check | Result |
|---|---|
| `deploy/backup.sh` real dump | PASS (12K, sha256 `017325ed7463…`) |
| `verify_backup.sh --backup` | PASS — 30/30 (DDL for all 18 tables, flat migration tracker, baseline + files) |
| `restore_test.sh` end-to-end | PASS — restore ~7 s, 26/26 structural, 36/36 app checks |
| Parity: invoices / tax_invoices / reconciliation_results | Counts + `SUM` fingerprints equal source |
| Migration forward-drill on restored DB | PASS — 010 applied, `tax_invoices` verify passed |
| Destroyed/scrubbed artifacts untouched | Generated under `/tmp/opencode/*`, outside the repo |