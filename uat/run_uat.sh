#!/usr/bin/env bash
# Phase 15 UAT orchestration.
#
# Starts two live application instances against the isolated scratch
# database (DB_NAME=einv_uat_p15):
#   * 127.0.0.1:5001  email DISABLED (development posture)
#   * 127.0.0.1:5061  email ENABLED  -> local mock SMTP sink on 2525
# then runs the full UAT battery and tears everything down.
#
# The mock SMTP sink is started inside the harness process during the email
# section; the email-enabled instance only ever connects on send, so it is
# safe for it to be up before the sink exists.
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export DB_NAME="${EINVOICE_UAT_DB:-einv_uat_p15}"
export UAT_PRIMARY_BASE="http://127.0.0.1:5001"
export UAT_EMAIL_BASE="http://127.0.0.1:5061"

declare -a PIDS=()
STICKY=""
cleanup() {
  printf '\n-- teardown --\n'
  for pid in "${PIDS[@]:-}"; do
    kill "$pid" 2>/dev/null || true
  done
  # gunicorn processes may need a moment to die; drop ownership of the sockets
  exit 0
}
trap cleanup EXIT INT TERM

"$ROOT/.venv/bin/gunicorn" \
  --workers 2 --timeout 120 --graceful-timeout 10 \
  --bind 127.0.0.1:5001 backend.wsgi:application \
  > /tmp/opencode/uat_primary.log 2>&1 &
PIDS+=($!)

EMAIL_ENABLED=true EMAIL_HOST=127.0.0.1 EMAIL_PORT=2525 \
EMAIL_FROM=uat@invoice.test EMAIL_USE_TLS=false EMAIL_USE_SSL=false \
EMAIL_USERNAME="" EMAIL_PASSWORD="" \
"$ROOT/.venv/bin/gunicorn" \
  --workers 2 --timeout 120 --graceful-timeout 10 \
  --bind 127.0.0.1:5061 backend.wsgi:application \
  > /tmp/opencode/uat_email.log 2>&1 &
PIDS+=($!)

for i in $(seq 1 30); do
  ok=0
  for port in 5001 5061; do
    if curl -fsS "http://127.0.0.1:${port}/api/health" > /dev/null 2>&1; then
      ok=$((ok + 1))
    fi
  done
  [ "$ok" -eq 2 ] && break
  sleep 1
done

if [ "$ok" -ne 2 ]; then
  echo "instances failed to become healthy"
  tail -40 /tmp/opencode/uat_primary.log 2>/dev/null || true
  tail -40 /tmp/opencode/uat_email.log 2>/dev/null || true
  exit 2
fi

echo "instances healthy; running UAT battery"
"$ROOT/.venv/bin/python" uat/run_uat.py
RC=$?
echo "UAT battery exit code: $RC"
exit "$RC"