#!/usr/bin/env bash
#
# E-Invoice & Reconciliation — guarded database restore
#
# Restores a verified logical backup (deploy/backup.sh output) into a target
# database. This script is deliberately conservative: restoring over the live
# application database requires an explicit --confirm-live flag AND an
# interactive yes/no confirmation. A scripted run (--yes) is only honoured
# for targets that are NOT the live database configured in the environment.
#
# The target database is never modified without the operator's explicit
# intent:
#   - no --recreate  -> the target must already exist; the dump is loaded
#                       into it (objects are replaced by DDL/DML, data is
#                       only added on top of whatever is there)
#   - --recreate     -> DROP + CREATE the target, only after confirmation
#
# Usage:
#   deploy/restore.sh --backup /var/backups/e-invoice/e-invoice-....sql.gz \
#                     --target invoice_system_recovery
#   deploy/restore.sh --backup F --target DB --recreate --yes        # isolated
#   deploy/restore.sh --backup F --target <live> --recreate --confirm-live
#   deploy/restore.sh --backup F --target DB --dry-run              # no changes
#
# Exit codes:
#   0 restored and post-restore verification passed
#   1 refused / failed
#   2 usage error
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_FILE=""
TARGET_DB=""
RECREATE=0
ASSUME_YES=0
CONFIRM_LIVE=0
DRY_RUN=0

usage() {
  echo "Usage: $0 --backup <file.sql.gz> --target <db> [--recreate] [--yes] [--confirm-live] [--dry-run]" >&2
  exit 2
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --backup) BACKUP_FILE="$2"; shift 2 ;;
    --target) TARGET_DB="$2"; shift 2 ;;
    --recreate) RECREATE=1; shift ;;
    --yes) ASSUME_YES=1; shift ;;
    --confirm-live) CONFIRM_LIVE=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    *) usage ;;
  esac
done

[ -n "$TARGET_DB" ] || usage
[ -n "$BACKUP_FILE" ] || usage

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

LIVE_DB="${DB_NAME:-invoice_system}"

echo "Restore request:
  backup : $BACKUP_FILE
  target : $TARGET_DB @ $DB_HOST:$DB_PORT
  live db: $LIVE_DB (configured in env/.env)
  flags  : $([ "$RECREATE" -eq 1 ] && echo -n '--recreate ') $([ "$ASSUME_YES" -eq 1 ] && echo -n '--yes ') $([ "$CONFIRM_LIVE" -eq 1 ] && echo -n '--confirm-live ') $([ "$DRY_RUN" -eq 1 ] && echo '--dry-run')"

# --- Safety guards -------------------------------------------------------------
if [ "$TARGET_DB" = "$LIVE_DB" ]; then
  # Restoring over the live database is an emergency procedure: it always
  # requires --confirm-live and an interactive confirmation. --yes is NOT
  # enough, so a script can never silently hit production.
  if [ "$CONFIRM_LIVE" -ne 1 ]; then
    echo "ERROR: target '$TARGET_DB' is the live database. Refusing to restore" >&2
    echo "over it without --confirm-live." >&2
    exit 1
  fi
  if [ "$DRY_RUN" -eq 0 ]; then
    read -r -p "DESTRUCTIVE restore of the LIVE database '$TARGET_DB'. Type 'yes' to continue: " confirm
    if [ "$confirm" != "yes" ]; then
      echo "Aborted." >&2
      exit 1
    fi
  fi
else
  if [ "$DRY_RUN" -eq 0 ] && [ "$RECREATE" -eq 1 ] && [ "$ASSUME_YES" -ne 1 ]; then
    read -r -p "DROP and recreate database '$TARGET_DB'? Type 'yes' to continue: " confirm
    if [ "$confirm" != "yes" ]; then
      echo "Aborted." >&2
      exit 1
    fi
  fi
fi

if [ ! -f "$BACKUP_FILE" ]; then
  echo "ERROR: backup file not found: $BACKUP_FILE" >&2
  exit 1
fi
if [ ! -f "$BACKUP_FILE.sha256" ]; then
  echo "ERROR: verification marker missing ($BACKUP_FILE.sha256). Refusing to" >&2
  echo "restore an unverified backup. Re-run deploy/backup.sh to obtain a" >&2
  echo "verified artifact." >&2
  exit 1
fi
set +e
computed="$(sha256sum "$BACKUP_FILE" | awk '{print $1}')"
recorded="$(awk '{print $1}' "$BACKUP_FILE.sha256")"
set -e
if [ -z "$computed" ] || [ "$computed" != "$recorded" ]; then
  echo "ERROR: SHA-256 mismatch computed=${computed:-none} recorded=${recorded:-none}." >&2
  exit 1
fi
echo "Backup checksum verified."

if [ "$DRY_RUN" -eq 1 ]; then
  echo "DRY-RUN: no changes made. Target '$TARGET_DB' would be restored from $BACKUP_FILE."
  exit 0
fi

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

# --- Recreate or bail ----------------------------------------------------------
existing="$(_db_query "SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name = '$TARGET_DB';")"
if [ "$RECREATE" -eq 1 ]; then
  echo "Recreating target database '$TARGET_DB'..."
  mysql "${MYSQLARGS[@]}" -e "DROP DATABASE IF EXISTS \`$TARGET_DB\`; CREATE DATABASE \`$TARGET_DB\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
elif [ "${existing:-0}" -gt 0 ]; then
  echo "Target '$TARGET_DB' exists; loading backup on top (no --recreate given)."
else
  echo "Target '$TARGET_DB' does not exist; creating it."
  mysql "${MYSQLARGS[@]}" -e "CREATE DATABASE \`$TARGET_DB\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
fi

# --- Restore --------------------------------------------------------------------
START_SEC="$(date +%s)"
echo "Restoring $BACKUP_FILE into '$TARGET_DB' ..."
gzip -dc "$BACKUP_FILE" | mysql "${MYSQLARGS[@]}" "$TARGET_DB"
END_SEC="$(date +%s)"
DURATION="$((END_SEC - START_SEC))"
echo "Restore completed in ${DURATION}s."

# --- Post-restore verification --------------------------------------------------
FAILS=0
for table in companies invoices reconciliation_runs schema_migrations roles users; do
  cnt="$(_db_query "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = '$TARGET_DB' AND table_name = '$table';")"
  if [ "${cnt:-0}" -gt 0 ]; then
    echo "  [PASS] table '$table' present in restored DB"
  else
    echo "  [FAIL] table '$table' missing in restored DB" >&2
    FAILS=$((FAILS + 1))
  fi
done
migrations="$(_db_query "SELECT COUNT(*) FROM \`$TARGET_DB\`.schema_migrations;")"
echo "  migration records in restored DB: ${migrations:-0}"
if [ "${migrations:-0}" -gt 0 ]; then
  echo "  [PASS] migration tracker populated"
else
  echo "  [FAIL] migration tracker empty" >&2
  FAILS=$((FAILS + 1))
fi
if [ "$FAILS" -eq 0 ]; then
  echo "Restore OK: $TARGET_DB is populated and structurally verified in ${DURATION}s."
else
  echo "Restore verification FAILED with $FAILS problem(s)." >&2
  exit 1
fi

echo "Rollback/recovery note: full restore performed; live database untouched."