#!/usr/bin/env bash
#
# E-Invoice — dependency & supply-chain integrity checks (Phase 13).
#
# Local-only mode (default, no network):
#   1. Manifest presence (requirements*.txt, frontend package files).
#   2. Python pinning policy: requirements.txt entries must be bounded ranges
#      (`name>=x,<y`, no `*`, no VCS/path/extra-index); lockfiles must be plain
#      `name==version` pins.
#   3. Reproducibility: every pin in requirements.lock.txt must be installed at
#      exactly that version in the active venv (the reproducible set). Extra
#      installed packages (e.g. development strays) are reported as warnings.
#   4. NPM integrity: package.json declares zero dependencies and
#      package-lock.json (lockfileVersion 3) contains only the root package.
#      `node --test test/supply-chain.test.js` guards this from the JS side.
#   5. `pip check` — no broken installed requirements.
#
# --online additionally (requires network):
#   A. pip-audit on both lockfiles (known-vulnerability scan).
#   B. `npm audit` and `npm ci --dry-run` (advisory + lockfile-consistency).
#
# Usage:
#   deploy/check_dependencies.sh                # local-only
#   deploy/check_dependencies.sh --online       # + vulnerability audits
#
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ONLINE="${1:-}"
if [ "$ONLINE" = "--online" ]; then
  ONLINE=1
else
  ONLINE=0
fi

FAILS=0
WARNS=0

say()  { printf '%s\n' "$@"; }
pass() { say "  [PASS] $*"; }
warn() { say "  [WARN] $*"; WARNS=$((WARNS + 1)); }
fail() { say "  [FAIL] $*"; FAILS=$((FAILS + 1)); }

say "Checking dependency & supply-chain integrity in $ROOT_DIR"

# ---------------------------------------------------------------- manifests
REQ=("requirements.txt" "requirements.lock.txt"
     "requirements-dev.txt" "requirements-dev.lock.txt")
MISSING=0
for f in "${REQ[@]}"; do
  if [ ! -f "$ROOT_DIR/$f" ]; then
    fail "missing python manifest: $f"
    MISSING=1
  fi
done
for f in "package.json" "package-lock.json"; do
  if [ ! -f "$ROOT_DIR/frontend/$f" ]; then
    fail "missing frontend manifest: frontend/$f"
    MISSING=1
  fi
done
if [ "$MISSING" -eq 1 ]; then
  say "Aborting: manifests missing."
  exit 1
fi

# ------------------------------------------------- python pinning policy
python_req_bad=0
while IFS= read -r line || [ -n "$line" ]; do
  line="${line%%#*}"                       # strip trailing comment
  line="$(printf '%s' "$line" | tr -s ' ' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
  [ -z "$line" ] && continue
  if echo "$line" | grep -qE '(^|[-[:space:]])(-e |git\+|http://|https://|::|@ )'; then
    fail "requirements.txt forbids VCS/path/index entry: $line"
    python_req_bad=1; continue
  fi
  if ! echo "$line" | grep -qE '^[A-Za-z0-9_.-]+>=[0-9][^,]*,[^ ]*<[0-9]'; then
    fail "requirements.txt entry not bounded 'name>=a,<b': $line"
    python_req_bad=1
  fi
done < "$ROOT_DIR/requirements.txt"
for f in requirements.lock.txt requirements-dev.lock.txt; do
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line%%#*}"
    line="$(printf '%s' "$line" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    [ -z "$line" ] && continue
    if ! echo "$line" | grep -qE '^[A-Za-z0-9_.-]+==[0-9][^,\s]*$'; then
      fail "$f must contain only 'name==version' pins: $line"
    fi
  done < "$ROOT_DIR/$f"
done
[ "$python_req_bad" -eq 0 ] && pass "python pinning policy (bounded ranges + plain == pins)"

# ------------------------------------------------ venv <-> runtime lock
VENV_BIN="$ROOT_DIR/.venv/bin"
if [ ! -x "$VENV_BIN/pip" ]; then
  warn "no .venv found in $ROOT_DIR — skipping reproducibility check"
else
  drift=0
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line%%#*}"
    line="$(printf '%s' "$line" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    [ -z "$line" ] && continue
    name="${line%%==*}"
    ver="${line#*==}"
    inst=$("$VENV_BIN/pip" show "$name" 2>/dev/null | sed -n 's/^Version: //p')
    if [ -z "$inst" ]; then
      fail "runtime lock pin NOT installed: $name==$ver"
      drift=1
    elif [ "$inst" != "$ver" ]; then
      fail "runtime lock pin MISMATCH: $name expected $ver, installed $inst"
      drift=1
    fi
  done < "$ROOT_DIR/requirements.lock.txt"
  if [ "$drift" -eq 0 ]; then
    pass "runtime lock pins all installed at exact versions"
    # Informational: report anything installed that is NOT pinned in the dev
    # lockfile (potential reproducibility drift beyond the known strays,
    # e.g. a manually-installed pyflakes).
    while IFS= read -r stray; do
      [ -z "$stray" ] && continue
      case "$stray" in pip==*|setuptools==*) continue;; esac
      warn "installed but not in requirements-dev.lock.txt: $stray"
    done < <("$VENV_BIN/pip" list --format=freeze 2>/dev/null | grep -E '==' | \
             grep -vFf <(grep -E '==' "$ROOT_DIR/requirements-dev.lock.txt"))
  fi
fi

# --------------------------------------------- pip check (broken installs)
"$VENV_BIN/pip" check >/dev/null 2>&1 \
  && pass "pip check: no broken requirements" \
  || { "$VENV_BIN/pip" check; fail "pip check reports broken requirements"; }

# ------------------------------------------------------------ frontend
FRONTEND_SRC_OK=""
if command -v node >/dev/null 2>&1; then
  ( cd "$ROOT_DIR/frontend" && node --test test/supply-chain.test.js >/dev/null 2>&1 ) \
    && pass "frontend supply-chain node test" \
    || FRONTEND_SRC_OK=fail
  [ "$FRONTEND_SRC_OK" = fail ] && fail "frontend supply-chain node test failed"
else
  warn "node not found — skipping frontend supply-chain guard"
fi

# --------------------------------------------------------- summary + exit
say ""
say "Dependency integrity: $FAILS failure(s), $WARNS warning(s)"
[ "$FAILS" -eq 0 ] || exit 1

# ------------------------------------------------------- --online audits
if [ "$ONLINE" -eq 0 ]; then
  say "(pass --online for pip-audit + npm audit)"
  exit 0
fi

say ""
say "Online vulnerability audits:"
audit_bin="${PIP_AUDIT_BIN:-}"
if [ -z "$audit_bin" ]; then
  for c in "/tmp/opencode/pipaudit-venv/bin/pip-audit" "$VENV_BIN/pip-audit"; do
    [ -x "$c" ] && audit_bin="$c" && break
  done
fi
if command -v pip-audit >/dev/null 2>&1; then audit_bin="$(command -v pip-audit)"; fi
if [ -n "$audit_bin" ]; then
  if "$audit_bin" -r "$ROOT_DIR/requirements.lock.txt" \
                -r "$ROOT_DIR/requirements-dev.lock.txt" >/dev/null 2>&1; then
    pass "pip-audit: no known vulnerabilities in either lockfile"
  else
    "$audit_bin" -r "$ROOT_DIR/requirements.lock.txt" \
                 -r "$ROOT_DIR/requirements-dev.lock.txt"
    fail "pip-audit found vulnerabilities"
  fi
else
  warn "pip-audit not installed — skipping Python vulnerability scan"
fi

if command -v npm >/dev/null 2>&1; then
  ( cd "$ROOT_DIR/frontend" && npm audit >/dev/null 2>&1 ) \
    && pass "npm audit: 0 vulnerabilities" \
    || fail "npm audit reported findings"
  ( cd "$ROOT_DIR/frontend" && npm ci --dry-run --ignore-scripts >/dev/null 2>&1 ) \
    && pass "npm ci --dry-run: lockfile consistent" \
    || fail "npm ci --dry-run could not validate frontend lockfile"
else
  warn "npm not found — skipping frontend vulnerability audit"
fi

say "Online dependency integrity: $FAILS failure(s), $WARNS warning(s)"
[ "$FAILS" -eq 0 ] || exit 1
exit 0