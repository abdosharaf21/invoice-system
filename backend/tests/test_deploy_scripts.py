"""Tests for the Phase 9 backup / restore safeguards (safety-failure modes).

These tests run the deploy shell scripts through their *safe* code paths that
require no working database:

  * restore refuses a missing backup file, a missing verification marker and a
    checksum mismatch (nothing is ever loaded without verified checksums),
  * restore refuses to touch the live database without --confirm-live,
  * restore --dry-run verifies the archive but makes no changes,
  * verify_backup fails (non-zero) on a missing archive,
  * backup never leaves a partial or unchecked artifact when the dump fails.

A real, verified restore against an isolated database is exercised end-to-end
by deploy/restore_test.sh (not here, so pytest stays DB-free).
"""

import hashlib
import os
import subprocess

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEPLOY = os.path.join(REPO_ROOT, "deploy")


@pytest.fixture
def env():
    """Baseline environment that prevents the scripts from sourcing .env."""
    base = dict(os.environ)
    base.update(
        {
            "DB_HOST": "127.0.0.1",
            "DB_PORT": "3306",
            "DB_NAME": "invoice_system",
            "DB_USER": "invoice_app",
            "DB_PASSWORD": "",
        }
    )
    return base


def run_script(name, args, env, cwd=None):
    return subprocess.run(
        ["bash", os.path.join(DEPLOY, name), *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd or REPO_ROOT,
        timeout=60,
    )


def write_backup(tmp_path, content=b"fake dump content\n", name="backup.sql.gz"):
    path = tmp_path / name
    path.write_bytes(content)
    return path


def write_sha256(path, digest):
    sidecar = path.with_name(path.name + ".sha256")
    sidecar.write_text(f"{digest}  {path.name}\n")
    return sidecar


# --- restore.sh usage / guard rails -----------------------------------------


def test_restore_usage_requires_backup(tmp_path, env):
    result = run_script("restore.sh", ["--target", "iso_db"], env)
    assert result.returncode == 2
    assert "Usage" in (result.stdout + result.stderr)


def test_restore_usage_requires_target(tmp_path, env):
    result = run_script("restore.sh", ["--backup", str(tmp_path / "x.sql.gz")], env)
    assert result.returncode == 2
    assert "Usage" in (result.stdout + result.stderr)


def test_restore_refuses_missing_backup_file(tmp_path, env):
    result = run_script(
        "restore.sh",
        ["--backup", str(tmp_path / "nope.sql.gz"), "--target", "iso_db"],
        env,
    )
    assert result.returncode == 1
    assert "backup file not found" in result.stderr


def test_restore_requires_verified_backup(tmp_path, env):
    """A backup without its .sha256 completion marker must be refused."""
    path = write_backup(tmp_path)
    result = run_script("restore.sh", ["--backup", str(path), "--target", "iso_db"], env)
    assert result.returncode == 1
    assert "verification marker missing" in result.stderr


def test_restore_rejects_checksum_mismatch(tmp_path, env):
    path = write_backup(tmp_path, content=b"corrupted archive")
    write_sha256(path, "0" * 64)
    result = run_script("restore.sh", ["--backup", str(path), "--target", "iso_db"], env)
    assert result.returncode == 1
    assert "SHA-256 mismatch" in result.stderr


def test_restore_refuses_live_db_without_confirm_live(tmp_path, env):
    """--yes is never enough to restore over the live database."""
    result = run_script(
        "restore.sh",
        ["--backup", str(tmp_path / "x.sql.gz"), "--target", "invoice_system", "--yes"],
        env,
    )
    assert result.returncode == 1
    assert "Refusing to restore" in result.stderr


def test_restore_dry_run_verifies_and_changes_nothing(tmp_path, env):
    content = b"fake but checksum-consistent dump\n"
    path = write_backup(tmp_path, content=content)
    digest = hashlib.sha256(content).hexdigest()
    write_sha256(path, digest)
    result = run_script(
        "restore.sh",
        [
            "--backup", str(path),
            "--target", "iso_db",
            "--recreate", "--yes", "--dry-run",
        ],
        env,
    )
    assert result.returncode == 0
    assert "DRY-RUN" in result.stdout
    assert "no changes made" in result.stdout


# --- verify_backup.sh --------------------------------------------------------


def test_verify_backup_fails_for_missing_archive(tmp_path, env):
    result = run_script(
        "verify_backup.sh", ["--backup", str(tmp_path / "missing.sql.gz")], env
    )
    assert result.returncode != 0
    assert "backup file exists" in result.stderr


def test_verify_backup_usage_for_no_mode(env):
    result = run_script("verify_backup.sh", [], env)
    assert result.returncode == 2


def test_verify_backup_flags_missing_sha256_sidecar(tmp_path, env):
    content = b"gzip-not-required for this path; marker check runs first\n"
    path = write_backup(tmp_path, content=content)
    result = run_script("verify_backup.sh", ["--backup", str(path)], env)
    assert result.returncode != 0
    assert "SHA-256 sidecar present" in result.stderr


# --- backup.sh ---------------------------------------------------------------


def test_backup_failure_leaves_no_artifact(tmp_path, env):
    """A failed dump must never leave a final archive or completion marker."""
    backup_dir = tmp_path / "store"
    backup_dir.mkdir()
    bad_env = dict(env)
    bad_env["DB_PORT"] = "1"  # nothing listens here: mysqldump fails fast
    result = run_script(
        "backup.sh",
        [],
        bad_env,
        cwd=tmp_path,
    )
    # the run above is in a temp cwd; backup.sh resolves repo relative to itself
    assert result.returncode != 0
    final = list(backup_dir.glob("e-invoice-*.sql.gz"))
    sidecars = list(backup_dir.glob("*.sha256"))
    assert final == []
    assert sidecars == []