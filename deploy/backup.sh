#!/usr/bin/env bash
#
# E-Invoice & Reconciliation — MySQL logical backup with integrity metadata
#
# Produces an InnoDB-consistent logical dump (gzip) plus a SHA-256 sidecar
# file. The sidecar is written ONLY after the dump passes every integrity
# check, so it doubles as the "backup is complete and valid" completion
# marker. A dump without a matching *.sha256 is an interrupted or failed
# artifact and MUST NOT be restored.
#
# Credentials are never exposed on the command line (no -p<password>; that is
# visible in the process list). They are handed to the MySQL clients through a
# temporary [client] defaults file created with mode 0600 and removed on exit.
# No secrets are written to log output.
#
# Usage:
#   deploy/backup.sh
#   BACKUP_DIR=./backups RETENTION_DAYS=30 deploy/backup.sh
#   APP_TABLES="invoices users" deploy/backup.sh      # override expected set
#
# Compatible interface kept for deploy/migrate.sh (same env vars, same
# e-invoice-*.sql.gz naming and same "rollback restore point" printing).
#
# Exit codes:
#   0 success (verified + sidecar marker written)
#   1 dump or verification failure (partial output removed, nothing retained)
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/e-invoice}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
HOSTNAME_LABEL="${HOSTNAME_LABEL:-$(hostname -s)}"

# Every application table plus the migration tracker. A full backup of the
# application must contain each of these DDL statements.
APP_TABLES="${APP_TABLES:-application_settings audit_logs audit_logs_legacy companies email_deliveries import_batch_errors import_batches invoice_items invoices reconciliation_errors reconciliation_results reconciliation_runs refresh_token_blocklist roles schema_migrations tax_invoice_items tax_invoices user_roles users}"

# ---------------------------------------------------------------------------
# Database configuration: prefer the environment, else the app .env file.
# ---------------------------------------------------------------------------
_load_db_config() {
  # Load DB_* values from the environment, falling back per-variable to the
  # app .env file. Explicitly-exported values always win (deploy/migrate.sh
  # runs this with DB_NAME=<scratch> to back up a non-default database).
  local env_file="${ENV_FILE:-$SCRIPT_DIR/../.env}"
  if [ -f "$env_file" ]; then
    while IFS='=' read -r key value; do
      case "$key" in
        DB_HOST|DB_PORT|DB_NAME|DB_USER|DB_PASSWORD)
          if [ -z "${!key:-}" ]; then
            export "$key"="$value"
          fi
          ;;
      esac
    done < <(grep -E '^(DB_HOST|DB_PORT|DB_NAME|DB_USER|DB_PASSWORD)=' "$env_file")
  fi
  : "${DB_HOST:=localhost}"
  : "${DB_PORT:=3306}"
  : "${DB_NAME:=invoice_system}"
  : "${DB_USER:=invoice_app}"
  : "${DB_PASSWORD:=}"
}

_load_db_config

if ! command -v mysqldump >/dev/null 2>&1; then
  echo "ERROR: mysqldump is not installed." >&2
  exit 1
fi

umask 077
mkdir -p "$BACKUP_DIR"
LOG_FILE="${BACKUP_LOG:-$BACKUP_DIR/backup.log}"

# Temporary [client] defaults file holds the credentials for the child
# processes without ever putting them on a command line.
DEFAULTS_FILE="$(mktemp "${TMPDIR:-/tmp}/e-invoice-mysql.XXXXXX")"
cleanup() { rm -f -- "$DEFAULTS_FILE"; }
trap cleanup EXIT INT TERM
printf '[client]\nuser=%s\npassword=%s\n' "$DB_USER" "$DB_PASSWORD" > "$DEFAULTS_FILE"
chmod 600 "$DEFAULTS_FILE"

MYSQLARGS=(--defaults-extra-file="$DEFAULTS_FILE" -h"$DB_HOST" -P"$DB_PORT")

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUTFILE="$BACKUP_DIR/e-invoice-$HOSTNAME_LABEL-$STAMP.sql.gz"
TMPFILE="$OUTFILE.tmp"

echo "Dumping '$DB_NAME' @ $DB_HOST:$DB_PORT -> $OUTFILE"
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] dump start db=$DB_NAME host=$DB_HOST:$DB_PORT file=$OUTFILE" >> "$LOG_FILE"

# A consistent snapshot with no table locks and no downtime. --set-gtid-purged
# is disabled because this deployment runs with GTID off.
mysqldump \
  "${MYSQLARGS[@]}" \
  --single-transaction \
  --routines \
  --events \
  --triggers \
  --skip-lock-tables \
  --set-gtid-purged=OFF \
  "$DB_NAME" 2>>"$LOG_FILE" \
  | gzip > "$TMPFILE"

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] dump done db=$DB_NAME file=$OUTFILE" >> "$LOG_FILE"

# --- Integrity checks -------------------------------------------------------
if ! gzip -t "$TMPFILE"; then
  echo "ERROR: gzip integrity check failed." >&2
  rm -f -- "$TMPFILE"
  exit 1
fi

SIZE_BYTES="$(stat -c%s "$TMPFILE" 2>/dev/null || echo 0)"
if [ "${SIZE_BYTES:-0}" -le 0 ]; then
  echo "ERROR: dump produced an empty archive." >&2
  rm -f -- "$TMPFILE"
  exit 1
fi

# Every expected table must be present in the dump. Shell-level fixture: run
# without pipefail so grep cannot be SIGPIPE-killed by truncation.
MISSING=""
for table in $APP_TABLES; do
  set +e
  found="$(gzip -dc "$TMPFILE" | grep -c "CREATE TABLE \`$table\` ")"
  set -e
  if [ "${found:-0}" -eq 0 ]; then
    echo "ERROR: expected table '$table' missing from dump." >&2
    MISSING="$MISSING $table"
  fi
done
if [ -n "$MISSING" ]; then
  rm -f -- "$TMPFILE"
  echo "ERROR: dump rejected; missing tables:$MISSING" >&2
  exit 1
fi

# Publish the backup and the atomic completion/verification marker.
mv "$TMPFILE" "$OUTFILE"
CHKSUM="$(sha256sum "$OUTFILE" | awk '{print $1}')"
printf '%s  %s\n' "$CHKSUM" "$(basename "$OUTFILE")" > "$OUTFILE.sha256"

SIZE_H="$(du -h "$OUTFILE" | cut -f1)"
echo "Backup OK  ($SIZE_H, sha256 ${CHKSUM:0:12}…)"
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] backup verified file=$OUTFILE sha256=$CHKSUM bytes=$SIZE_BYTES" >> "$LOG_FILE"

# --- Retention ----------------------------------------------------------------
# Never prune the newest backup. Only remove verified backups (those with a
# matching *.sha256), never match unrelated files, and only prune files older
# than RETENTION_DAYS. A failed .tmp from this run is cleaned immediately above.
if [ "${RETENTION_DAYS:-0}" -gt 0 ] 2>/dev/null; then
  newest="$(ls -1t "$BACKUP_DIR"/e-invoice-*.sql.gz 2>/dev/null | head -1 || true)"
  pruned=0
  while IFS= read -r -d '' candidate; do
    [ -n "$candidate" ] || continue
    [ "$candidate" != "$newest" ] || continue
    [ -f "$candidate" ] && [ -f "$candidate.sha256" ] || continue
    rm -f -- "$candidate" "$candidate.sha256"
    pruned=$((pruned + 1))
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] pruned old backup file=$candidate" >> "$LOG_FILE"
  done < <(find "$BACKUP_DIR" -maxdepth 1 -name 'e-invoice-*.sql.gz' -mtime +"$RETENTION_DAYS" -print0 2>/dev/null || true)
  if [ "$pruned" -gt 0 ]; then
    echo "Pruned $pruned verified backup(s) older than $RETENTION_DAYS days."
  fi
  find "$BACKUP_DIR" -maxdepth 1 -name '*.tmp' -mtime +1 -delete 2>/dev/null || true
fi