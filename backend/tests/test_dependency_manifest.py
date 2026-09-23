"""Offline tests for dependency manifests and lockfile consistency (Phase 13).

Ensures:
- requirements.txt entries are bounded ranges; no VCS/path/index/`*`.
- Lockfile entries are plain ``name==version`` pins.
- Every direct requirement has a lockfile pin satisfying its declared range.
- Runtime vs dev separation: test-only packages do NOT leak into the
  production lockfile or requirements.txt.
- Lockfile contents are an exact known inventory (direct + declared
  transitive); no unknown/typosquatting packages.
- frontend/package-lock.json is lockfileVersion 3 with only the root package.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

# --- paths (work for repo root) ------------------------------------------------
ROOT = Path(__file__).resolve().parents[2]
REQ_RUNTIME = ROOT / "requirements.txt"
REQ_LOCK = ROOT / "requirements.lock.txt"
REQ_DEV = ROOT / "requirements-dev.txt"
REQ_DEV_LOCK = ROOT / "requirements-dev.lock.txt"
PKG_LOCK = ROOT / "frontend" / "package-lock.json"

_RANGE_RE = re.compile(
    r"^[A-Za-z0-9_.-]+>=([0-9][0-9a-zA-Z.]*),<([0-9][0-9a-zA-Z.]*)$"
)
_PIN_RE = re.compile(r"^[A-Za-z0-9_.-]+==([0-9][0-9a-zA-Z.*]*)$")
_COMMENT_RE = re.compile(r"(#.*)|(\s+)")


# --- helpers -------------------------------------------------------------------
def _read_manifest(path: Path) -> list[str]:
    lines: list[str] = []
    for raw in path.read_text().splitlines():
        raw = raw.split("#")[0].strip()  # strip comment + whitespace
        if raw:
            lines.append(raw)
    return lines


def _parse_ranges(lines: list[str]) -> dict[str, tuple[str, str]]:
    out: dict[str, tuple[str, str]] = {}
    for line in lines:
        m = _RANGE_RE.match(line)
        if m is None:
            continue  # -r includes handled separately
        out[m.group(0).split(">=")[0]] = (m.group(1), m.group(2))
    return out


def _parse_pins(lines: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in lines:
        m = _PIN_RE.match(line)
        if m:
            out[line.split("==")[0]] = m.group(1)
    return out


def _version_tuple(v: str) -> tuple[int, ...]:
    return tuple(int(p) for p in v.split(".") if p.isdigit())


# --- inventory (Phase 13 documented sets) ---------------------------------------
# If you add a new *direct* dependency, add it to RUNTIME_DIRECT or
# DEV_ONLY_DIRECT.  If its transitive children change, update the matching
# TRANSITIVE set and regenerate the lockfiles.  This is intentional friction:
# new transitive packages are a supply-chain event and must be deliberate.
RUNTIME_DIRECT = {
    "Flask",
    "Flask-JWT-Extended",
    "bcrypt",
    "mysql-connector-python",
    "python-dotenv",
    "openpyxl",
    "gunicorn",
}
RUNTIME_TRANSITIVE = {
    "blinker",
    "click",
    "et_xmlfile",
    "itsdangerous",
    "Jinja2",
    "MarkupSafe",
    "packaging",
    "PyJWT",
    "Werkzeug",
}
DEV_ONLY_DIRECT = {"pytest"}
DEV_ONLY_TRANSITIVE = {"iniconfig", "pluggy", "Pygments"}

ALL_RUNTIME = RUNTIME_DIRECT | RUNTIME_TRANSITIVE      # 16 packages
ALL_DEV = ALL_RUNTIME | DEV_ONLY_DIRECT | DEV_ONLY_TRANSITIVE  # 20 packages


# === tests ======================================================================

class TestManifestSyntax:
    def test_requirements_txt_bounded_ranges(self):
        lines = _read_manifest(REQ_RUNTIME)
        assert lines, f"{REQ_RUNTIME} is empty"
        for line in lines:
            assert not line.startswith("-"), f"no flags/includes allowed in runtime manifest: {line}"
            assert "*" not in line, f"floating version * forbidden: {line}"
            assert "git+" not in line, f"VCS dependency forbidden: {line}"
            assert "http://" not in line and "https://" not in line, \
                f"URL dependency forbidden: {line}"
            assert _RANGE_RE.match(line), f"not a bounded 'name>=a,<b' line: {line}"

    def test_requirements_dev_txt_includes_runtime(self):
        lines = _read_manifest(REQ_DEV)
        includes_runtime = any("-r requirements.txt" in l for l in lines)
        assert includes_runtime, "requirements-dev.txt must include -r requirements.txt"
        dev_deps = [l for l in lines if _RANGE_RE.match(l)]
        assert len(dev_deps) == 1, f"expected exactly one dev dep (pytest), got {dev_deps}"

    def test_lockfiles_are_plain_pins(self):
        for path in (REQ_LOCK, REQ_DEV_LOCK):
            lines = _read_manifest(path)
            assert lines, f"{path} is empty"
            for line in lines:
                assert _PIN_RE.match(line), f"{path}: not a plain pin: {line}"

    def test_lockfiles_no_vcs_or_extras(self):
        for path in (REQ_LOCK, REQ_DEV_LOCK):
            for line in _read_manifest(path):
                assert "-e " not in line.lower(), f"editable install in lockfile: {line}"
                assert "::" not in line, f"extras syntax in lockfile: {line}"
                assert "[" not in line, f"extras syntax in lockfile: {line}"


class TestRangePinningConsistency:
    def test_runtime_ranges_have_matching_lock_pins(self):
        ranges = _parse_ranges(_read_manifest(REQ_RUNTIME))
        pins = _parse_pins(_read_manifest(REQ_LOCK))
        pin_lower = {k.lower(): k for k in pins}
        for name, (lo, hi) in ranges.items():
            assert name.lower() in pin_lower, \
                f"runtime requirement {name} missing from runtime lockfile"
            pin_name = pin_lower[name.lower()]
            lo_tuple, hi_tuple = _version_tuple(lo), _version_tuple(hi)
            pin_tuple = _version_tuple(pins[pin_name])
            assert pin_tuple >= lo_tuple, \
                f"{name}: pin {pins[pin_name]} < lower bound {lo}"
            assert pin_tuple < hi_tuple, \
                f"{name}: pin {pins[pin_name]} >= upper bound {hi}"

    def test_dev_lock_extends_runtime_lock(self):
        runtime_pins = _parse_pins(_read_manifest(REQ_LOCK))
        dev_pins = _parse_pins(_read_manifest(REQ_DEV_LOCK))
        assert runtime_pins, "runtime lock empty"
        for name, ver in runtime_pins.items():
            assert name in dev_pins, f"dev lock missing runtime package: {name}=={ver}"
            assert dev_pins[name] == ver, \
                f"version divergence: runtime {name}=={ver}, dev {name}=={dev_pins[name]}"
        assert len(dev_pins) > len(runtime_pins), "dev lock must extend runtime lock"


class TestProductionDevSeparation:
    """Ensure test-only packages do NOT leak into the production set."""

    @pytest.mark.parametrize("pkg", sorted(DEV_ONLY_DIRECT | DEV_ONLY_TRANSITIVE))
    def test_dev_package_not_in_runtime_requirements(self, pkg: str):
        lines = _read_manifest(REQ_RUNTIME)
        joined = " ".join(lines)
        assert pkg.lower() not in joined.lower(), \
            f"dev-only package '{pkg}' must not appear in requirements.txt"

    @pytest.mark.parametrize("pkg", sorted(DEV_ONLY_DIRECT | DEV_ONLY_TRANSITIVE))
    def test_dev_package_not_in_runtime_lockfile(self, pkg: str):
        pins = _parse_pins(_read_manifest(REQ_LOCK))
        # Compare case-insensitively: pip freeze uses canonical casing
        lower_map = {k.lower(): k for k in pins}
        assert pkg.lower() not in lower_map, \
            f"dev-only package '{pkg}' leaked into requirements.lock.txt"


class TestInventoryConsistency:
    """Lockfile must equal exactly the declared direct + transitive set."""

    def test_runtime_lock_inventory(self):
        pins = _parse_pins(_read_manifest(REQ_LOCK))
        pin_set = set(pins.keys())
        assert pin_set == ALL_RUNTIME, (
            f"runtime lockfile inventory mismatch.\n"
            f"  Missing from lock:  {ALL_RUNTIME - pin_set}\n"
            f"  Unexpected in lock: {pin_set - ALL_RUNTIME}"
        )

    def test_dev_lock_inventory(self):
        pins = _parse_pins(_read_manifest(REQ_DEV_LOCK))
        pin_set = set(pins.keys())
        assert pin_set == ALL_DEV, (
            f"dev lockfile inventory mismatch.\n"
            f"  Missing from lock:  {ALL_DEV - pin_set}\n"
            f"  Unexpected in lock: {pin_set - ALL_DEV}"
        )

    def test_runtime_lock_has_exactly_16_packages(self):
        lines = _read_manifest(REQ_LOCK)
        assert len(lines) == 16, f"expected 16 runtime lock entries, got {len(lines)}"

    def test_dev_lock_has_exactly_20_packages(self):
        lines = _read_manifest(REQ_DEV_LOCK)
        assert len(lines) == 20, f"expected 20 dev lock entries, got {len(lines)}"


class TestFrontendLockIntegrity:
    def test_package_lock_is_v3_root_only(self):
        data = json.loads(PKG_LOCK.read_text())
        assert data.get("lockfileVersion") == 3, "lockfileVersion must be 3"
        packages = data.get("packages", {})
        assert "" in packages, "root package entry missing"
        non_root = [k for k in packages if k != ""]
        assert non_root == [], f"unexpected non-root entries: {non_root}"
        assert not data.get("dependencies"), "legacy dependencies map must be empty"
        assert not packages.get("") or not packages[""].get("hasInstallScript"), \
            "root package must not declare an install script"

    def test_package_json_no_deps(self):
        pkg_json = json.loads((ROOT / "frontend" / "package.json").read_text())
        assert not pkg_json.get("dependencies"), "no runtime dependencies allowed"
        assert not pkg_json.get("devDependencies"), "no dev dependencies allowed"
        scripts = pkg_json.get("scripts", {})
        assert not scripts.get("install"), "no install lifecycle script"
        assert not scripts.get("postinstall"), "no postinstall lifecycle script"
        assert not scripts.get("preinstall"), "no preinstall lifecycle script"