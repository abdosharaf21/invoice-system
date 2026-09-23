#!/usr/bin/env bash
#
# E-Invoice — deterministic schema migration runner (000..012, ordered).
#
# Strategy (backup -> migrate -> verify -> record):
#   1. Tracks applied files in a `schema_migrations` table (created on demand).
#      Each recorded row stores the file's SHA-256 checksum (Phase 12).
#   2. Audits the tracker *before* touching anything: an applied migration
#      whose recorded checksum no longer matches its file is a DRIFT and
#      aborts the run (rollback first), so silently-edited or corrupted
#      migrations can never be masked by a re-run.
#   3. Runs a full pre-migration backup (deploy/backup.sh) before ANY pending
#      migration, so every change is rollback-ready.
#   4. Applies pending .sql files in lexicographic order (000 first).
#   5. Verifies each application (exit status + presence of the expected
#      table/view when the file declares a `-- verify:` hint).
#   6. Records the file in schema_migrations only after success.
#
# Bootstrap: migration 000_foundation_schema.sql creates the Phase 1
# foundation tables (companies/users/roles/user_roles) so a completely empty
# database can be migrated end-to-end. The file is idempotent, so databases
# provisioned by hand keep working (see --record-existing below).
#
# Rollback: restore the newest backup taken by this script (it prints the
# path on each run). Schema changes are not reversible in-application.
#
# Usage:
#   deploy/migrate.sh                         # apply everything pending
#   deploy/migrate.sh --record-existing       # seed tracker, apply nothing
#   deploy/migrate.sh --check                 # read-only status + drift audit
#   deploy/migrate.sh --accept-drift          # apply even if checksums differ
#   MIGRATIONS_DIR=... BACKUP_DIR=... deploy/migrate.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
MIGRATIONS_DIR="${MIGRATIONS_DIR:-$ROOT_DIR/backend/database/migrations}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/e-invoice}"

# Load DB_* values from the environment, falling back per-variable to the app
# .env file. Explicitly-exported values always win, so
# `DB_NAME=scratch BACKUP_DIR=... deploy/migrate.sh` targets `scratch` even
# when .env sets DB_NAME (this kept silently breaking deployment drills).
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
  : "${DB_NAME:=invoice_system}"
  : "${DB_USER:=invoice_app}"
  : "${DB_PASSWORD:=}"
}

_load_db_config

MYSQLARGS=(-h"$DB_HOST" -P"$DB_PORT" -u"$DB_USER")
[ -n "$DB_PASSWORD" ] && MYSQLARGS+=(-p"$DB_PASSWORD")

# Fail-soft (|| true) so legacy trackers lacking the checksum column and
# missing tables yield empty output instead of killing the script under `set -e`.
_db_query() {
  mysql "${MYSQLARGS[@]}" --batch --skip-column-names "$DB_NAME" -e "$1" 2>/dev/null || true
}

is_applied() {
  local name="$1"
  [ "$(_db_query "SELECT COUNT(*) FROM schema_migrations WHERE name = '$name';")" = "1" ]
}

# Recorded SHA-256 for an applied migration, or empty when it has none
# (pre-checksum tracker) or is not recorded at all.
_applied_checksum() {
  local name="$1"
  _db_query "SELECT IFNULL(MAX(checksum), '') FROM schema_migrations WHERE name = '$name';"
}

_file_checksum() {
  sha256sum "$1" | awk '{print $1}'
}

_checksum_column_exists() {
  [ "$(_db_query "SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = '$DB_NAME' AND TABLE_NAME = 'schema_migrations' AND COLUMN_NAME = 'checksum';")" = "1" ]
}

_tracker_exists() {
  [ "$(_db_query "SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA = '$DB_NAME' AND TABLE_NAME = 'schema_migrations';")" = "1" ]
}

if ! command -v mysql >/dev/null 2>&1; then
  echo "ERROR: mysql client is not installed." >&2
  exit 1
fi

if ! command -v sha256sum >/dev/null 2>&1; then
  echo "ERROR: sha256sum is not installed." >&2
  exit 1
fi

if [ ! -d "$MIGRATIONS_DIR" ]; then
  echo "ERROR: migrations directory not found: $MIGRATIONS_DIR" >&2
  exit 1
fi

echo "Target database: $DB_NAME @ $DB_HOST:$DB_PORT"

ALL_SQL=("$MIGRATIONS_DIR"/*.sql)
[ -e "${ALL_SQL[0]}" ] || ALL_SQL=()

# --check: read-only status and drift audit. Nothing is created or changed.
if [ "${1:-}" = "--check" ]; then
  if ! _tracker_exists; then
    echo "Tracker table 'schema_migrations' does not exist yet."
    echo "PENDING: ${#ALL_SQL[@]} migration(s) would be applied on the first run."
    exit 0
  fi

  pending=0
  applied=0
  legacy=0
  drifted=0
  orphans=0
  for f in "${ALL_SQL[@]}"; do
    name="$(basename "$f")"
    if ! is_applied "$name"; then
      printf '  PENDING   %s\n' "$name"
      pending=$((pending + 1))
      continue
    fi
    recorded="$(_applied_checksum "$name")"
    if [ -z "$recorded" ]; then
      printf '  LEGACY    %s  (applied before checksum tracking; digest unknown)\n' "$name"
      legacy=$((legacy + 1))
      continue
    fi
    digest="$(_file_checksum "$f")"
    if [ "$recorded" = "$digest" ]; then
      printf '  APPLIED   %s  sha256 %s\n' "$name" "${digest:0:12}"
      applied=$((applied + 1))
    else
      printf '  DRIFT     %s  recorded %s != file %s\n' "$name" "${recorded:0:12}" "${digest:0:12}"
      drifted=$((drifted + 1))
    fi
  done
  while IFS=$'\t' read -r name applied_at; do
    [ -z "$name" ] && continue
    if [ ! -f "$MIGRATIONS_DIR/$name" ]; then
      printf '  ORPHAN    %s  (recorded %s but no matching file)\n' "$name" "$applied_at"
      orphans=$((orphans + 1))
    fi
  done < <(_db_query "SELECT name, applied_at FROM schema_migrations ORDER BY name;")

  echo ""
  echo "Summary: $applied applied, $legacy legacy, $drifted drifted, $pending pending, $orphans orphan(s)."
  if [ "$drifted" -gt 0 ] || [ "$orphans" -gt 0 ]; then
    echo "DRIFT DETECTED — restore the pre-migration backup before running migrate.sh."
    exit 1
  fi
  exit 0
fi

# Create the tracking table if this is the first run (idempotent).
mysql "${MYSQLARGS[@]}" "$DB_NAME" <<'SQL'
CREATE TABLE IF NOT EXISTS schema_migrations (
  name       VARCHAR(255) NOT NULL PRIMARY KEY,
  applied_at TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  checksum   VARCHAR(64)  DEFAULT NULL
);
SQL

# Phase 12 upgrade: trackers created before checksums existed get the column
# added in place (MySQL 8 has no ADD COLUMN IF NOT EXISTS, hence the guard).
if ! _checksum_column_exists; then
  mysql "${MYSQLARGS[@]}" "$DB_NAME" \
    -e "ALTER TABLE schema_migrations ADD COLUMN checksum VARCHAR(64) DEFAULT NULL;"
  echo "Upgraded schema_migrations: added 'checksum' column."
fi

# --record-existing: seed the tracking table with every migration file without
# re-running anything. Use when the schema was already migrated by hand
# (e.g. this repo's live database where 000..007 were applied without a
# tracker). Existing legacy rows have their checksum backfilled in place.
if [ "${1:-}" = "--record-existing" ]; then
  seeded=0
  backfilled=0
  for f in "${ALL_SQL[@]}"; do
    name="$(basename "$f")"
    digest="$(_file_checksum "$f")"
    if is_applied "$name"; then
      recorded="$(_applied_checksum "$name")"
      if [ -z "$recorded" ]; then
        mysql "${MYSQLARGS[@]}" "$DB_NAME" \
          -e "UPDATE schema_migrations SET checksum = '$digest' WHERE name = '$name' AND checksum IS NULL;"
        backfilled=$((backfilled + 1))
      fi
      continue
    fi
    mysql "${MYSQLARGS[@]}" "$DB_NAME" \
      -e "INSERT INTO schema_migrations (name, checksum) VALUES ('$name', '$digest');"
    seeded=$((seeded + 1))
  done
  echo "Recorded $seeded migration(s) and backfilled $backfilled checksum(s) without applying anything."
  echo "Summary:"
  _db_query "SELECT name, applied_at, IFNULL(checksum,'') FROM schema_migrations ORDER BY applied_at;" | \
    while IFS=$'\t' read -r n at c; do
      [ -n "$n" ] || continue
      printf '  %s  (applied %s, sha256 %s)\n' "$n" "$at" "${c:0:12}"
    done
  exit 0
fi

# Audit already-applied migrations before any backup/apply: a checksum that
# no longer matches its file means the migration (or the tracker) changed
# after it ran — never mask that with a re-run.
echo "Auditing applied migrations ..."
AUDIT_DIRTY=0
for f in "${ALL_SQL[@]}"; do
  name="$(basename "$f")"
  if is_applied "$name"; then
    recorded="$(_applied_checksum "$name")"
    if [ -n "$recorded" ] && [ "$recorded" != "$(_file_checksum "$f")" ]; then
      echo "  DRIFT: $name — recorded sha256 ${recorded:0:12} differs from the file ${(_file_checksum "$f"):0:12}."
      AUDIT_DIRTY=1
    fi
  fi
done

# Orphan/unknown tracker rows (e.g. files deleted after being applied).
_ORPHAN_COUNT=0
while IFS=$'\t' read -r name applied_at; do
  [ -z "$name" ] && continue
  if [ ! -f "$MIGRATIONS_DIR/$name" ]; then
    echo "  ORPHAN: $name is recorded but its file is missing."
    _ORPHAN_COUNT=$((_ORPHAN_COUNT + 1))
  fi
done < <(_db_query "SELECT name, applied_at FROM schema_migrations ORDER BY name;")

if [ "$AUDIT_DIRTY" -eq 1 ] || [ "$_ORPHAN_COUNT" -gt 0 ]; then
  if [ "${1:-}" = "--accept-drift" ]; then
    echo "WARNING: drift/orphans found but --accept-drift was given; continuing."
  else
    echo "ERROR: schema_migrations disagrees with the migration files." >&2
    echo "Restore the pre-migration backup, then run deploy/migrate.sh --record-existing to repair." >&2
    exit 1
  fi
fi

PENDING=()
for f in "${ALL_SQL[@]}"; do
  if ! is_applied "$(basename "$f")"; then
    PENDING+=("$f")
  fi
done

if [ "${#PENDING[@]}" -eq 0 ]; then
  if [ "$AUDIT_DIRTY" -eq 0 ]; then
    echo "No pending migrations. All files in $MIGRATIONS_DIR are applied."
  fi
  exit 0
fi

echo "Pending migrations: ${#PENDING[@]}"
printf '  %s\n' "${PENDING[@]##*/}"

# A brand-new database has no application tables yet, so there is nothing to
# back up (and backup.sh's structural gate correctly rejects an empty dump).
LAST_BACKUP=""
if [ "$(_db_query "SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA = '$DB_NAME' AND TABLE_TYPE = 'BASE TABLE' AND TABLE_NAME <> 'schema_migrations';")" = "0" ]; then
  echo "Target database is empty; skipping pre-migration backup."
else
  echo "Pre-migration backup ..."
  BACKUP_DIR="$BACKUP_DIR" "$SCRIPT_DIR/backup.sh"

  LAST_BACKUP="$(ls -1t "$BACKUP_DIR"/e-invoice-*.sql.gz 2>/dev/null | head -1 || true)"
  if [ -n "$LAST_BACKUP" ]; then
    echo "Rollback restore point: $LAST_BACKUP"
  else
    echo "WARNING: no backup produced; continuing anyway." >&2
  fi
fi

for f in "${PENDING[@]}"; do
  name="$(basename "$f")"
  digest="$(_file_checksum "$f")"
  echo ""
  echo ">> Applying $name"
  # Safety: refuse to apply a file whose content changed since it was already
  # recorded (belt-and-braces with the pre-flight audit above).
  recorded="$(_applied_checksum "$name")"
  if [ -n "$recorded" ] && [ "$recorded" != "$digest" ]; then
    echo "ERROR: '$name' is recorded with a different checksum than the file." >&2
    echo "Restore the last backup first: $LAST_BACKUP" >&2
    exit 1
  fi
  if ! mysql "${MYSQLARGS[@]}" "$DB_NAME" < "$f"; then
    echo "ERROR: '$name' failed. Restore the last backup first: $LAST_BACKUP" >&2
    exit 1
  fi
  # Extract the verify block from the migration file's header comments.
  # A block opens with "-- verify: <table, ...>" and continues over the next
  # comment lines while they contain only table tokens and commas; a blank
  # "--" line or prose line terminates the block.
  verify_hint="$(awk '
    /^[[:space:]]*--[[:space:]]*verify:[[:space:]]*[[:alnum:]_`]+/ {
      line = $0
      sub(/^[[:space:]]*--[[:space:]]*verify:[[:space:]]*/, "", line)
      gsub(/[`]/, "", line); gsub(/,[[:space:]]*/, " ", line)
      if (line != "") print line
      inblock = 1; next
    }
    inblock {
      line = $0
      sub(/^[[:space:]]*--[[:space:]]*/, "", line)
      if (line ~ /^[[:alnum:]_`]+([[:space:]]*,[[:space:]]*[[:alnum:]_`]+)*[[:space:]]*,?[[:space:]]*$/) {
        gsub(/[`]/, "", line); gsub(/,[[:space:]]*/, " ", line)
        if (line != "") print line
        next
      }
      inblock = 0
    }
  ' "$f" | tr '\n' ' ')" || true
  if [ -n "$verify_hint" ]; then
    for table in $verify_hint; do
      [ -n "$table" ] || continue
      count="$(_db_query "SELECT COUNT(*) FROM \`$table\`;")"
      echo "   verify table '$table': row count = ${count:-VERIFY_FAILED}"
    done
  fi
  mysql "${MYSQLARGS[@]}" "$DB_NAME" \
    -e "INSERT INTO schema_migrations (name, checksum) VALUES ('$name', '$digest')
        ON DUPLICATE KEY UPDATE checksum = VALUES(checksum);"
  echo "   recorded in schema_migrations (sha256 ${digest:0:12})."
done

echo ""
echo "All migrations applied. Summary:"
_db_query "SELECT name, applied_at, IFNULL(checksum,'') FROM schema_migrations ORDER BY applied_at;" | \
  while IFS=$'\t' read -r n at c; do
    [ -n "$n" ] || continue
    printf '  %s  (applied %s, sha256 %s)\n' "$n" "$at" "${c:0:12}"
  done