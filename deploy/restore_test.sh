#!/usr/bin/env bash
#
# E-Invoice & Reconciliation — isolated end-to-end restore test
#
# Proves that a real backup can be restored into a completely isolated
# database and that the application can operate against the restored state:
#
#   1. creates/recreates the isolated recovery database,
#   2. restores the newest verified backup into it (deploy/restore.sh),
#   3. structurally verifies the restored database (deploy/verify_backup.sh),
#   4. runs application-level checks against the restored database
#      (deploy/restore_check.py: health, readiness, login, RBAC isolation,
#      invoice/reconciliation/audit/settings reads, source-vs-restore counts),
#   5. reports durations (RTO evidence) and a PASS/FAIL summary.
#
# The isolated database is the ONLY thing this script ever touches. The live
# database is used read-only as the count/fingerprint source of truth.
#
# Usage:
#   deploy/restore_test.sh
#   RESTORE_DB=invoice_system_recovery BACKUP_FILE=/path/to/backup.sql.gz deploy/restore_test.sh
#
# Exit codes:
#   0 all checks passed | 1 any step failed
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESTORE_DB="${RESTORE_DB:-invoice_system_recovery}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/e-invoice}"
BACKUP_FILE="${BACKUP_FILE:-$(ls -1t "$BACKUP_DIR"/e-invoice-*.sql.gz 2>/dev/null | head -1 || true)}"
SOURCE_DB="${SOURCE_DB:-}"

if [ -z "$BACKUP_FILE" ] || [ ! -f "$BACKUP_FILE" ]; then
  echo "ERROR: no backup found. Run deploy/backup.sh first or set BACKUP_FILE." >&2
  exit 1
fi

# Load config so we can print/harden against the live DB name.
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

LIVE_DB="${DB_NAME}"
SOURCE_DB="${SOURCE_DB:-$LIVE_DB}"

if [ "$RESTORE_DB" = "$LIVE_DB" ]; then
  echo "ERROR: RESTORE_DB '$RESTORE_DB' is the live database. Refusing to run." >&2
  exit 1
fi

echo "=============================================================="
echo " ISOLATED RESTORE TEST"
echo "=============================================================="
echo "  backup   : $BACKUP_FILE"
echo "  target   : $RESTORE_DB (isolated)"
echo "  source   : $SOURCE_DB (read-only reference)"
echo "  live db  : $LIVE_DB (never touched)"
echo ""

START="$(date +%s)"
STEP=0
step() { STEP=$((STEP + 1)); echo ""; echo "[$STEP] $1"; }

# --- 1. Restore into the isolated database -------------------------------------
step "Restoring backup into '$RESTORE_DB' (isolated)"
if ! "$SCRIPT_DIR/restore.sh" \
    --backup "$BACKUP_FILE" \
    --target "$RESTORE_DB" \
    --recreate --yes; then
  echo "ERROR: restore step failed." >&2
  exit 1
fi

# --- 2. Structural verification of the restored database -----------------------
step "Verifying restored database structure, migration state and data"
if ! "$SCRIPT_DIR/verify_backup.sh" --restored-db "$RESTORE_DB"; then
  echo "ERROR: restored database verification failed." >&2
  exit 1
fi

# --- 3. Application-level verification against the restored DB ------------------
step "Running application checks against '$RESTORE_DB'"
PYTHON_BIN="${PYTHON_BIN:-/home/abdo-sharaf21/e-invoice-system/invoice-system/.venv/bin/python}"
if ! DB_NAME="$RESTORE_DB" "$PYTHON_BIN" \
    "$SCRIPT_DIR/restore_check.py" --target "$RESTORE_DB" --source "$SOURCE_DB" \
      --host "$DB_HOST" --port "$DB_PORT" --user "$DB_USER" --password "$DB_PASSWORD"; then
  echo "ERROR: application checks failed." >&2
  exit 1
fi

END="$(date +%s)"
echo ""
echo "=============================================================="
echo " RESULT: PASS"
echo "  total elapsed        : $((END - START))s"
echo "  targets modified     : only $RESTORE_DB (isolated)"
echo "=============================================================="