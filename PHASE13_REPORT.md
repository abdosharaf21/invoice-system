# Phase 13 — Dependency & Supply-Chain Security — Completion Report

Generated: Phase 13, E-Invoice System, `/home/abdo-sharaf21/e-invoice-system/invoice-system/`

---

## 1. Executive Summary

Phase 13 inventories, scans, pins, separates, documents, and continuously
guards every runtime and development dependency the system installs. The
repo arrives with **zero known vulnerabilities** across Python and npm, and
with a reproducible, auditable supply chain enforced by two new offline
contract-test suites and an automated integrity-check script.

Key outcomes:

| Outcome | Status |
|---|---|
| Vulnerability scan (pip-audit) | ✅ No known advisories in any lockfile |
| npm audit | ✅ 0 vulnerabilities |
| Runtime lockfile pins | ✅ 16 exact `==` pins (7 direct + 9 transitive) |
| Dev lockfile pins | ✅ 20 exact `==` pins (+ pytest, pluggy, iniconfig, Pygments) |
| Production/dev separation | ✅ pytest removed from production manifests |
| Forbidden sources (VCS/path/index) | ✅ All manifests clean |
| `deploy/check_dependencies.sh --online` | ✅ 0 failures, 1 documented warning (pyflakes stray) |
| Backend pytest | ✅ 547 passed (527 baseline + 20 manifest + old Phase 12 suite) |
| Frontend `node --test` | ✅ 197 passed (194 baseline + 3 supply-chain) |

## 2. Phase Scope & Objectives

Per the Phase 13 task specification:

| # | Objective | Delivered |
|---|---|---|
| 1 | Inventory all Python/npm/lockfile surfaces | ✅ §4–6 |
| 2 | Audit known vulnerabilities | ✅ §8 |
| 3 | Verify reproducible installation | ✅ §9 |
| 4 | Establish dependency change policy | ✅ §11, §18 |
| 5 | Add focused integrity checks | ✅ §15–17 |
| 6 | Generate 21-section report | ✅ this file |

Out-of-scope (by design): no runtime upgrades beyond security fixes; no
new dependencies added; no CDN introduction; no Node build toolchain.

## 3. Baseline (Phase 13 start)

| Metric | Value |
|---|---|
| requirements.txt direct deps | 8 (Flask, Flask-JWT-Extended, bcrypt, mysql-connector-python, python-dotenv, openpyxl, gunicorn, pytest) |
| Locked transitive packages | 11 |
| mysql-connector-python | 9.7.0 (already security-fixed in prior work) |
| pytest | 8.4.2 with PYSEC-2026-1845 advisory |
| npm `package.json` dependencies | 0 (pure static SPA) |
| npm lockfile | did not exist |
| `frontend/test/supply-chain.test.js` | did not exist |
| `requirements-dev.txt` / `requirements-dev.lock.txt` | did not exist |
| `deploy/check_dependencies.sh` | did not exist |
| Production lockfile | pytest leaked into production install set |

## 4. Dependency Inventory — Python Runtime

`requirements.txt` (final): **7 direct** bounded-range entries.

| Package | Declared range | Resolved (lock) | Role |
|---|---|---|---|
| Flask | `>=3.0,<4.0` | 3.1.3 | Web framework |
| Flask-JWT-Extended | `>=4.6,<5.0` | 4.7.4 | JWT auth |
| bcrypt | `>=4.0,<5.0` | 4.3.0 | Password hashing |
| mysql-connector-python | `>=9.1.0,<10.0` | 9.7.0 | MySQL driver |
| python-dotenv | `>=1.0,<2.0` | 1.2.3 | .env loader |
| openpyxl | `>=3.1,<4.0` | 3.1.5 | XLSX export |
| gunicorn | `>=23.0,<24.0` | 23.0.0 | WSGI server |

**9 transitive** runtime packages: blinker, click, et\_xmlfile, itsdangerous,
Jinja2, MarkupSafe, packaging, PyJWT, Werkzeug. All resolved from PyPI
via standard pip resolution; no custom indexes, no VCS deps.

## 5. Dependency Inventory — Python Dev/Test

`requirements-dev.txt` includes `-r requirements.txt` and adds one test-only
dependency:

| Package | Declared range | Resolved (lock) | Purpose |
|---|---|---|---|
| pytest | `>=9.0.3,<10.0` | 9.1.1 | Test runner |

**3 additional transitive** dev packages: iniconfig, pluggy, Pygments
(Pygments is also an optional Werkzeug debugger dependency; confirmed safe,
no active vulnerability).

Total dev lockfile inventory: **20 packages** (16 runtime + 4 dev-only).

## 6. Dependency Inventory — Frontend / npm

`frontend/package.json` declares **zero** runtime and **zero** dev
dependencies. The application is a plain-vanilla static SPA with no
framework, no CDN links, and no build step. `package-lock.json`
(lockfileVersion 3) pins only the root package (zero transitive entries).

No npm lifecycle scripts that could execute arbitrary commands during install.

## 7. Transitive Resolution

Lockfile generation used a clean scratch venv (`python3 -m venv /tmp/opencode/lockgen`, confirmed deleted and recreated between runtime and dev passes). Each
lockfile is a direct `pip freeze` of that clean venv, with the leading
auto-bootstrapped `pip` and `setuptools` lines filtered out.

Dependency graph (runtime):

```
Flask (3.1.3)
  └─ blinker, click, itsdangerous, Jinja2, MarkupSafe, Werkzeug
Flask-JWT-Extended (4.7.4)
  └─ PyJWT
bcrypt (4.3.0)
  (no transitive; bcrypt bundles its C extension)
mysql-connector-python (9.7.0)
  └─ packaging (for X DevAPI metadata)
openpyxl (3.1.5)
  └─ et_xmlfile
gunicorn (23.0.0)
  (no runtime transitive deps)
python-dotenv (1.2.3)
  (no transitive)
```

Dev-only tree: pytest → pluggy, iniconfig, Pygments. All pinned and known.

## 8. Vulnerability Scan & Remediation

**Prior remediation (already completed before Phase 13):**
- `mysql-connector-python` pinned `>=9.1.0` (fixes PYSEC-2026-1685 / CVE-2024-21272, CVSS 7.5 HIGH).
- `pytest` updated to `>=9.0.3` (fixes PYSEC-2026-1845, `/tmp` race, dev-only).

**Phase 13 scan (pip-audit, both lockfiles):**

```
No known vulnerabilities found
```

**npm audit:**

```
found 0 vulnerabilities
```

**Rationale for not upgrading beyond security fixes:** both `bcrypt` 4.3→5.0
(major) and `gunicorn` 23→26 (major) show as outdated by `pip list --outdated`,
but neither carries a known advisory. Major bumps carry interface risk; upgrading
for freshness alone would violate the "no unnecessary churn" principle. `PyJWT`
was also updated transitively from an unpinned state to 2.14.0 via lockfile
resolution — this is not an intentional upgrade but a resolution artifact that
pip-audit confirmed clean.

## 9. Reproducible Install Strategy

**Production path** (`deploy/DEPLOYMENT.md` §3):

```bash
pip install -r requirements.lock.txt   # byte-identical across installs
```

**Development path:**

```bash
pip install -r requirements.txt -r requirements-dev.txt
```

**Lockfile regeneration protocol:**

```bash
python3 -m venv /tmp/lockgen
/tmp/lockgen/bin/pip install -r requirements.txt         # or -r requirements-dev.txt
/tmp/lockgen/bin/pip freeze | grep -v -E '^(pip|setuptools)'
# paste output into the corresponding .lock.txt file
```

Regeneration is documented in the lockfile header, `requirements.txt` header,
`requirements-dev.txt` header, `deploy/DEPLOYMENT.md`, and `README.md`.

## 10. Runtime vs Dev Separation

The pre-existing `requirements.txt` mixed runtime and test tooling. Phase 13
splits cleanly:

| File | Purpose | Installed in production? |
|---|---|---|
| `requirements.txt` | Runtime manifest | ❌ production uses lockfile instead |
| `requirements.lock.txt` | Runtime lock (16 pins) | ✅ yes, by `DEPLOYMENT.md` §3 |
| `requirements-dev.txt` | Dev manifest (includes runtime) | ❌ dev only |
| `requirements-dev.lock.txt` | Dev lock (20 pins) | ❌ dev only |

`pytest`, `pluggy`, `iniconfig`, and `Pygments` are explicitly excluded from
the production lockfile. Production installs are now smaller and have a
narrower attack surface.

## 11. Manifest Policy

Enforced at creation time and continuously verified by
`deploy/check_dependencies.sh` and `test_dependency_manifest.py`:

| Policy | runtime | runtime lock | dev lock |
|---|---|---|---|
| Every line is `name>=a,<b` | ✅ | n/a | n/a |
| Every line is `name==version` | n/a | ✅ | ✅ |
| No `*` floating versions | ✅ | n/a | n/a |
| No `-e` editable installs | ✅ | ✅ | ✅ |
| No `git+`/`http(s)://` VCS deps | ✅ | ✅ | ✅ |
| No `--index-url`/`--extra-index-url` | ✅ | n/a | n/a |
| No `[extras]` syntax | ✅ | ✅ | ✅ |

## 12. Lockfile Integrity

`requirements.lock.txt` and `requirements-dev.lock.txt` are both:

- auto-generated from a clean venv (never hand-edited after creation)
- comment-prefixed with regeneration instructions
- excluded from `.gitignore` (committed as tracked reproducibility artifacts)
- validated at creation time by `pip check` (no broken requirements)
- post-validated by `deploy/check_dependencies.sh`: every pin in the lockfile
  is installed at the exact pinned version in the active project venv

**Reproducibility confirmation (runtime):** all 16 runtime pins match the
project venv. `pip check` reports no broken requirements.

## 13. Forbidden Dependency Sources

All manifests are scanned by `deploy/check_dependencies.sh` for forbidden
patterns:

- **VCS dependencies** (`git+`, `hg+`, `svn+`, `bzr+`): none found.
- **Path/editable installs** (`-e .`, `-e file://`): none found.
- **Custom indexes** (`--index-url`, `--extra-index-url`): none found.
- **Pre-release pins** (`>=1.0.0rc1`): none found.
- **Local file references** (`./path`): none found.

Both Python and npm resolve exclusively from their default TLS-protected
registries (`PyPI`, `registry.npmjs.org`).

## 14. NPM Zero-Dependency Policy

`frontend/package.json` has an empty `dependencies` object (or omits the
key entirely) and no `devDependencies`. The following structural guards
are enforced:

| Guard | Enforced by |
|---|---|
| No `dependencies` or `devDependencies` entries | `test/supply-chain.test.js`, `test_dependency_manifest.py` |
| No `install`/`preinstall`/`postinstall` scripts | `test/supply-chain.test.js` |
| No `husky` or hook system | `test/supply-chain.test.js` |
| `package-lock.json` lockfileVersion 3 | `test/supply-chain.test.js`, `test_dependency_manifest.py` |
| Lockfile packages map contains only root entry | `test/supply-chain.test.js`, `test_dependency_manifest.py` |
| No legacy `dependencies` map in lockfile | both test suites |
| `npm audit`: 0 vulnerabilities | `deploy/check_dependencies.sh --online` |
| `npm ci --dry-run --ignore-scripts` validates lockfile | `deploy/check_dependencies.sh --online` |

Any future addition of an npm dependency must deliberately update
`package.json`, regenerate `package-lock.json`, and update the test
suites' assertions — making it a deliberate, auditable supply-chain event.

## 15. Automated Integrity Check (`deploy/check_dependencies.sh`)

A single script provides two modes:

**Default (offline, no network):**

| Check | Exit condition |
|---|---|
| Manifest presence | All five manifest files exist |
| Python pinning policy | Bounded ranges in requirements.txt; plain pins in lockfiles |
| Venv ↔ runtime lock reproducibility | Every runtime pin installed at exact version |
| `pip check` | No broken installed requirements |
| Frontend supply-chain node test | `node --test test/supply-chain.test.js` passes |

**`--online` additionally:**

| Check | Exit condition |
|---|---|
| `pip-audit` on both lockfiles | Zero known vulnerabilities |
| `npm audit` | Zero advisory findings |
| `npm ci --dry-run --ignore-scripts` | Lockfile consistent with manifest |

The script returns exit 1 if any hard check fails; warnings (documented
stray packages, missing optional tools) produce exit 0 with a summary.

## 16. Offline Contract Tests (`test_dependency_manifest.py`)

20 new pytest tests across 5 test classes, fully offline:

| Class | Tests | What it checks |
|---|---|---|
| `TestManifestSyntax` | 4 | Bounded ranges, `-r` includes, lockfile plain pins, no VCS/extras |
| `TestRangePinningConsistency` | 2 | Each requirement range has a satisfying lock pin; dev lock extends runtime |
| `TestProductionDevSeparation` | 8 | pytest/pluggy/iniconfig/Pygments absent from runtime manifest and lockfile |
| `TestInventoryConsistency` | 4 | Lockfile contents match documented direct + transitive sets exactly (16 runtime, 20 dev) |
| `TestFrontendLockIntegrity` | 2 | package-lock.json lockfileVersion 3, root-only; package.json no deps/scripts |

If a future dependency introduces new transitive children, the inventory
tests will deliberately fail — requiring the operator to add the new package
to the documented `RUNTIME_TRANSITIVE` or `DEV_ONLY_TRANSITIVE` set. This
is intentional friction guarding against silent supply-chain drift or
typosquatting.

## 17. Frontend Supply-Chain Guard (`test/supply-chain.test.js`)

3 new `node:test` assertions (part of the 197-pass frontend suite):

1. **Zero-dep manifest:** `package.json` must have no `dependencies` or
   `devDependencies` keys; `test` script must use `node --test` only.
2. **Lockfile version + root-only:** `package-lock.json` lockfileVersion 3,
   `packages` contains only the `""` root entry, `dependencies` map empty.
3. **No install hooks:** no `install`/`preinstall`/`postinstall` scripts in
   package.json; root lockfile entry must not declare `hasInstallScript`.

Run via `cd frontend && node --test test/supply-chain.test.js`, or as part
of the full `npm test` suite.

## 18. Documentation Updates

| File | Section | Change |
|---|---|---|
| `deploy/DEPLOYMENT.md` | §3 Install | Updated command to install from `requirements.lock.txt`; added regeneration procedure |
| `README.md` | New §"Dependency management" | Documents the 5-file manifest model, change policy, and regeneration protocol |
| `requirements.txt` | Header | Bounded-range policy statement; security-fix notes on mysql-connector + pytest |
| `requirements-dev.txt` | New file | `-r requirements.txt` + pytest; documents intentional exclusion from production |
| `requirements.lock.txt` | Header | Regeneration instructions |
| `requirements-dev.lock.txt` | New file | Dev lockfile; notes production uses runtime lockfile instead |

## 19. Live Verification Evidence

| What | Where | Result |
|---|---|---|
| Runtime venv ↔ lock | Project `.venv` | All 16 pins match exactly |
| `pip check` | Project `.venv` | No broken requirements |
| `deploy/check_dependencies.sh` | Full offline suite | 0 failures, 1 warning (pyflakes stray) |
| `deploy/check_dependencies.sh --online` | Full online suite | 0 failures, 1 warning |
| `pip-audit` (both lockfiles) | PyPI advisory scan | No known vulnerabilities |
| `npm audit` | advisory scan | 0 vulnerabilities |
| `npm ci --dry-run` | lockfile consistency | Pass |
| `frontend/test/supply-chain.test.js` | node:test | 3/3 pass |
| `backend/tests/test_dependency_manifest.py` | pytest | 20/20 pass |
| Full backend regression | `pytest backend/tests` | 547 passed |
| Full frontend regression | `node --test test/*.test.js` | 197 passed |

## 20. Risks, Limitations & Non-Changes

| Item | Status | Notes |
|---|---|---|
| `pyflakes` 3.4.0 in project `.venv` | ⚠️ documented stray | Manually installed; not in any manifest. Does not affect production (`pip install -r requirements.lock.txt` will not pull it). `check_dependencies.sh` emits a warning. |
| `Pygments` 2.21.0 (Werkzeug debugger optional) | ℹ️ dev-only | Pulled in by `pytest` dependency chain. Absent from runtime lockfile. In dev lockfile only; used optionally by Werkzeug if debugger is active. |
| `bcrypt` 4.3.0 vs latest 5.0 | ℹ️ no advisory | Major bump available; no known vulnerability. Intentionally not upgraded — no security reason to carry interface risk. |
| `gunicorn` 23.0.0 vs latest 26.x | ℹ️ no advisory | Major bump available; no known vulnerability. Intentionally not upgraded — no security reason to carry interface risk. |
| `packaging` in runtime lock | ℹ️ required by mysql-connector-python | Used for X DevAPI metadata parsing; not optional, correctly resolved by pip. |
| Full lockfile regeneration verification | ⚠️ not tested against a fresh database | Regen is a file-level operation; database impact is zero. Schema drill from Phase 12 is the appropriate database regression gate. |
| `npm audit --production` (audit without dev deps) | n/a | No dev dependencies; not needed. |

## 21. Verdict

**Phase 13 is complete.** The system's dependency and supply-chain posture
has been hardened from an unsplit, unscoped manifest into a fully auditable,
reproducible, vulnerability-free, production-separated dependency tree with
continuous offline guards.

| Criterion | Met |
|---|---|
| All known vulnerabilities remediated or confirmed absent | ✅ |
| Reproducible installs via lockfiles | ✅ |
| Runtime / dev separation reviewed and clean | ✅ |
| Forbidden dependency sources absent | ✅ |
| npm integrity verified | ✅ |
| Automated checks deployable without network | ✅ |
| Contract tests lock the inventory | ✅ |
| Documentation complete | ✅ |
| Full regression passing (547 backend + 197 frontend) | ✅ |
| PHASE13\_REPORT.md with 21 sections delivered | ✅ |

Ready to proceed to Phase 14 (or next).
