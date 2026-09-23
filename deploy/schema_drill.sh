#!/usr/bin/env bash
#
# E-Invoice — fresh forward-migration drill (Phase 12).
#
# Proves that the migration catalog reproduces the canonical schema from
# scratch: it creates an isolated scratch database, applies every migration
# file in lexicographic (deployment) order, then runs the schema verifier
# against it. A PASS means migrations 000..012 are ordered, self-consistent,
# and end in exactly the state described by the expected schema manifest.
#
# The scratch database is created and destroyed by this script; only
# information_schema writes on the *scratch* DB are involved. The live
# database is never touched.
#
# Usage:
#   deploy/schema_drill.sh
#   MIGRATIONS_DIR=... BACKUP_DIR=... deploy/schema_drill.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
MIGRATIONS_DIR="${MIGRATIONS_DIR:-$ROOT_DIR/backend/database/migrations}"
PYTHON="${PYTHON:-$ROOT_DIR/.venv/bin/python}"
[ -x "$PYTHON" ] || PYTHON="${PYTHON:-python3}"

# Load DB_* values from the environment, falling back per-variable to the app
# .env file. Explicitly-exported values always win.
_load_db_config() {
  local env_file="${ENV_FILE:-$ROOT_DIR/.env}"
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
  : "${DB_USER:=invoice_app}"
  : "${DB_PASSWORD:=}"
}
_load_db_config

MYSQLARGS=(-h"$DB_HOST" -P"$DB_PORT" -u"$DB_USER")
[ -n "$DB_PASSWORD" ] && MYSQLARGS+=(-p"$DB_PASSWORD")

if ! command -v mysql >/dev/null 2>&1; then
  echo "ERROR: mysql client is not installed." >&2
  exit 1
fi

if [ ! -d "$MIGRATIONS_DIR" ]; then
  echo "ERROR: migrations directory not found: $MIGRATIONS_DIR" >&2
  exit 1
fi

DRILL_DB="invoice_system_drill_$(date +%s)"
FILES=("$MIGRATIONS_DIR"/*.sql)

cleanup() {
  mysql "${MYSQLARGS[@]}" -e "DROP DATABASE IF EXISTS \`$DRILL_DB\`;" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "Scratch database: $DRILL_DB @ $DB_HOST:$DB_PORT"
mysql "${MYSQLARGS[@]}" --force -e \
  "CREATE DATABASE \`$DRILL_DB\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

n=0
for f in "${FILES[@]}"; do
  name="$(basename "$f")"
  printf '  applying %s ... ' "$name"
  if ! mysql "${MYSQLARGS[@]}" "$DRILL_DB" < "$f"; then
    mysql "${MYSQLARGS[@]}" -e "DROP DATABASE IF EXISTS \`$DRILL_DB\`;" >/dev/null 2>&1 || true
    echo "FAILED"
    echo "ERROR: '$name' failed on the scratch database." >&2
    exit 1
  fi
  echo "ok"
  n=$((n + 1))
done

echo ""
echo "Applied $n migration(s) to the scratch database."
echo "Verifying schema against the expected manifest ..."
PYTHONPATH="$ROOT_DIR" "$PYTHON" -m backend.database.schema_verify --db "$DRILL_DB"
echo ""
echo "RESULT: PASS — migrations 000..012 reproduce the canonical schema."