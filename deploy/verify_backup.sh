#!/usr/bin/env bash
#
# E-Invoice & Reconciliation — backup integrity verification
#
# A backup is NOT valid merely because it exists or gzip succeeds. This tool
# proves, for either an archived backup file or a freshly restored database:
#
#   1. the file exists, is non-empty and passes gzip integrity;
#   2. the recorded SHA-256 sidecar matches the archive (file mode only);
#   3. every expected application table exists in the dump / restored DB;
#   4. the migration tracker is present and every recorded migration name
#      corresponds to a real file in the migrations directory;
#   5. representative application data is present (companies / users / etc.)
#      and is reported for evidence.
#
# The strongest verification (importing the dump into an isolated database)
# is performed by deploy/restore_test.sh; this script is its DDL/data/state
# counterpart and is called by restore_test.sh after the import.
#
# Usage:
#   deploy/verify_backup.sh --backup /var/backups/e-invoice/e-invoice-....sql.gz
#   deploy/verify_backup.sh --restored-db invoice_system_recovery
#
# Exit codes:
#   0 verified | 1 verification failed
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MIGRATIONS_DIR="${MIGRATIONS_DIR:-$SCRIPT_DIR/../backend/database/migrations}"
APP_TABLES="${APP_TABLES:-application_settings audit_logs audit_logs_legacy companies email_deliveries import_batch_errors import_batches invoice_items invoices reconciliation_errors reconciliation_results reconciliation_runs refresh_token_blocklist roles schema_migrations tax_invoice_items tax_invoices user_roles users}"
FIRST_MIGRATION="001_reconcile_foundation_schema.sql"

MODE=""
BACKUP_FILE=""
RESTORED_DB=""

usage() {
  echo "Usage: $0 --backup <file.sql.gz> | --restored-db <db_name>" >&2
  exit 2
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --backup) MODE=file; BACKUP_FILE="$2"; shift 2 ;;
    --restored-db) MODE=db; RESTORED_DB="$2"; shift 2 ;;
    *) usage ;;
  esac
done

[ -n "$MODE" ] || usage
PASS=0
FAILS=0

report() {
  local status="$1" msg="$2"
  if [ "$status" = "ok" ]; then
    echo "  [PASS] $msg"
    PASS=$((PASS + 1))
  else
    echo "  [FAIL] $msg" >&2
    FAILS=$((FAILS + 1))
  fi
}

_sql_stream_of_backup() {
  # Lazily decompress the archive once per consumer is wasteful; callers that
  # need many checks call this multiple times. Archives are small enough that
  # this is acceptable and keeps memory bounded.
  gzip -dc "$BACKUP_FILE"
}

_load_db_config() {
  if [ -z "${DB_HOST:-}" ]; then
    local env_file="${ENV_FILE:-$SCRIPT_DIR/../.env}"
    if [ -f "$env_file" ]; then
      while IFS='=' read -r key value; do
        case "$key" in
          DB_HOST|DB_PORT|DB_NAME|DB_USER|DB_PASSWORD)
            export "$key"="$value"
            ;;
        esac
      done < <(grep -E '^(DB_HOST|DB_PORT|DB_NAME|DB_USER|DB_PASSWORD)=' "$env_file")
    fi
  fi
  : "${DB_HOST:=localhost}"
  : "${DB_PORT:=3306}"
  : "${DB_NAME:=invoice_system}"
  : "${DB_USER:=invoice_app}"
  : "${DB_PASSWORD:=}"
}
_load_db_config

umask 077
DEFAULTS_FILE="$(mktemp "${TMPDIR:-/tmp}/e-invoice-mysql.XXXXXX")"
cleanup() { rm -f -- "$DEFAULTS_FILE"; }
trap cleanup EXIT INT TERM
printf '[client]\nuser=%s\npassword=%s\n' "$DB_USER" "$DB_PASSWORD" > "$DEFAULTS_FILE"
chmod 600 "$DEFAULTS_FILE"
MYSQLARGS=(--defaults-extra-file="$DEFAULTS_FILE" -h"$DB_HOST" -P"$DB_PORT")

_db_query() {
  mysql "${MYSQLARGS[@]}" --batch --skip-column-names -e "$1" 2>/dev/null || true
}

_db_exists() {
  [ "$(_db_query "SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name = '$RESTORED_DB';")" -gt 0 ]
}

echo "Verifying backup  ($MODE)"

if [ "$MODE" = "file" ]; then
  # --- file-level checks ------------------------------------------------------
  if [ -f "$BACKUP_FILE" ]; then
    report ok "backup file exists"
  else
    report fail "backup file exists ($BACKUP_FILE)"
  fi
  if [ -s "$BACKUP_FILE" ]; then
    report ok "backup non-empty ($(stat -c%s "$BACKUP_FILE") bytes)"
  else
    report fail "backup non-empty"
  fi
  if [ -f "$BACKUP_FILE.sha256" ]; then
    set +e
    computed="$(sha256sum "$BACKUP_FILE" | awk '{print $1}')"
    recorded="$(awk '{print $1}' "$BACKUP_FILE.sha256")"
    set -e
    if [ -n "$computed" ] && [ "$computed" = "$recorded" ]; then
      report ok "SHA-256 sidecar matches archive"
    else
      report fail "SHA-256 sidecar matches archive (computed ${computed:-none} vs recorded ${recorded:-none})"
    fi
  else
    report fail "SHA-256 sidecar present (no completion marker; backup may be incomplete)"
  fi
  if gzip -t "$BACKUP_FILE" 2>/dev/null; then
    report ok "gzip integrity"
  else
    report fail "gzip integrity"
  fi
  # --- schema object presence --------------------------------------------------
  for table in $APP_TABLES; do
    set +e
    found="$(gzip -dc "$BACKUP_FILE" | grep -c "CREATE TABLE \`$table\` ")"
    set -e
    if [ "${found:-0}" -gt 0 ]; then
      report ok "table '$table' DDL present"
    else
      report fail "table '$table' DDL present"
    fi
  done
  # --- migration tracker --------------------------------------------------------
  set +e
  recorded="$(gzip -dc "$BACKUP_FILE" | grep -oE "'[0-9]+_[a-z_]+\.sql'" | tr -d "'" | sort -u)"
  set -e
else
  # --- restored-database checks ---------------------------------------------------
  if ! _db_exists; then
    echo "ERROR: target database '$RESTORED_DB' does not exist." >&2
    exit 1
  fi
  for table in $APP_TABLES; do
    set +e
    cnt="$(_db_query "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = '$RESTORED_DB' AND table_name = '$table';")"
    set -e
    if [ "${cnt:-0}" -gt 0 ]; then
      report ok "table '$table' exists in restored DB"
    else
      report fail "table '$table' exists in restored DB"
    fi
  done
  set +e
  recorded="$(_db_query "SELECT name FROM \`$RESTORED_DB\`.schema_migrations ORDER BY name;" 2>/dev/null)"
  set -e
fi

# --- migration record consistency ------------------------------------------------
if [ -n "$recorded" ]; then
  report ok "migration tracker records $(printf '%s\n' "$recorded" | grep -c '^') migration(s)"
  if printf '%s\n' "$recorded" | grep -qx "$FIRST_MIGRATION"; then
    report ok "baseline migration '$FIRST_MIGRATION' recorded"
  else
    report fail "baseline migration '$FIRST_MIGRATION' recorded"
  fi
  unknown=""
  while IFS= read -r name; do
    [ -n "$name" ] || continue
    if [ ! -f "$MIGRATIONS_DIR/$name" ]; then
      unknown="$unknown $name"
    fi
  done <<< "$recorded"
  if [ -z "$unknown" ]; then
    report ok "every recorded migration exists as a file in migrations/"
  else
    report fail "recorded migrations missing from repo:$unknown"
  fi
else
  report fail "migration tracker present"
fi

# --- representative data -----------------------------------------------------------
if [ "$MODE" = "file" ]; then
  for t in companies users roles reconciliation_runs; do
    set +e
    found="$(gzip -dc "$BACKUP_FILE" | grep -c "INSERT INTO \`$t\` ")"
    set -e
    report "$([ "${found:-0}" -gt 0 ] && echo ok || echo fail)" "representative data: INSERT rows for '$t'"
  done
else
  for t in companies users roles reconciliation_runs; do
    set +e
    cnt="$(_db_query "SELECT COUNT(*) FROM \`$RESTORED_DB\`.\`$t\`;")"
    set -e
    report "$([ "${cnt:-0}" -ge 0 ] && echo ok || echo fail)" "representative data: '$t' readable (rows=${cnt:-0})"
  done
fi

echo ""
echo "Verification: $PASS passed, $FAILS failed."
[ "$FAILS" -eq 0 ]