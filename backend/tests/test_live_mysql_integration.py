"""Opt-in live MySQL integration tests (Phase 14 gap G10).

These tests exercise the real ``Database``/``MySQLConnectionPool`` stack
against a throwaway database and are **opt-in**: they skip unless the
``EINVOICE_E2E`` environment variable names a scratch database. They never
run against the production ``invoice_system`` database (or anything
reserved); the named database is created, migrated, used and then dropped,
and the test fails loudly if the name looks dangerous.

The concurrency classes verify the Phase 6 race protections against the
real InnoDB engine with real threads:

* ``TestRunExclusive``           - reconciliation start race
* ``TestFinishRunRace``          - reconciliation finish race + rollback
* ``TestLastActiveAdminRace``    - last-active-admin deactivate/delete race
"""

import os
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from backend.database.config import DatabaseConfig
from backend.database.connection import Database, DatabaseError
from backend.modules.reconciliation.model import ReconciliationRun
from backend.modules.reconciliation.repository import ReconciliationRepository
from backend.modules.users.repository import UserRepository
from backend.modules.users.service import UserService

from backend.database.migration_audit import MIGRATIONS, MIGRATIONS_DIR

_RESERVED_NAMES = {"invoice_system", "mysql", "information_schema", "performance_schema", "sys"}
_CONNECTION_ERROR_MARKER = "Connection refused"
_WORKER_POOL_SIZE = 2


def _scratch_db_name() -> str:
    """Return the E2E database name, or pytest-skip when unset."""
    name = os.environ.get("EINVOICE_E2E", "").strip()
    if not name:
        pytest.skip("EINVOICE_E2E not set; skipping live-MySQL integration tests")
    return name


def _guard_db_name(name: str) -> None:
    """Refuse to create/drop dangerous or production-like databases."""
    lowered = name.lower()
    if lowered in _RESERVED_NAMES or lowered.startswith("invoice_system"):
        raise AssertionError(f"Refusing to run E2E against reserved database '{name}'")


def _split_statements(sql: str) -> list[str]:
    """Split a migration file into statements, respecting quotes/identifiers.

    Semicolons inside string literals (e.g. a CSP default value) and quoted
    identifiers must not terminate the statement, and comment markers inside
    string literals (``'#,##0.00'``) must not be stripped.
    """
    statements = []
    start = 0
    quote = None
    i = 0
    n = len(sql)
    while i < n:
        ch = sql[i]
        if quote is not None:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                if i + 1 < n and sql[i + 1] == quote:
                    i += 2
                    continue
                quote = None
        else:
            if ch in "'\"`":
                quote = ch
            elif ch == "-" and sql[i:i + 2] == "--":
                line_end = sql.find("\n", i)
                i = n if line_end == -1 else line_end + 1
                continue
            elif ch == "#":
                line_end = sql.find("\n", i)
                i = n if line_end == -1 else line_end + 1
                continue
            elif ch == "/" and sql[i:i + 2] == "/*":
                end = sql.find("*/", i + 2)
                i = n if end == -1 else end + 2
                continue
            elif ch == ";":
                statement = sql[start:i].strip()
                if statement:
                    statements.append(statement)
                start = i + 1
        i += 1
    tail = sql[start:].strip()
    if tail:
        statements.append(tail)
    return statements


def _apply_migrations(conn, db_name: str) -> None:
    """Apply the canonical migration catalog to the scratch database."""
    connector = conn.cursor()
    for filename, _digest in MIGRATIONS:
        path = MIGRATIONS_DIR / filename
        sql = path.read_text(encoding="utf-8")
        for statement in _split_statements(sql):
            connector.execute(statement)
            try:
                connector.fetchall()
            except Exception:
                pass
            while connector.nextset():
                try:
                    connector.fetchall()
                except Exception:
                    pass
    connector.close()


@pytest.fixture(scope="module")
def e2e_db():
    """Provision, migrate and (at module end) drop a scratch database."""
    db_name = _scratch_db_name()
    _guard_db_name(db_name)
    base = DatabaseConfig(
        name=db_name,
        pool_name="e2e_admin_pool",
    )
    admin = DatabaseConfig(name="", pool_name="e2e_setup_pool")
    admin_pool = Database(admin)
    with admin_pool.connection() as conn:
        conn.autocommit = True
        connector = conn.cursor()
        connector.execute(f"DROP DATABASE IF EXISTS `{db_name}`")
        connector.execute(f"CREATE DATABASE `{db_name}` "
                          "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        connector.close()
    with admin_pool.connection() as conn:
        conn.autocommit = True
        connector = conn.cursor()
        connector.execute(f"USE `{db_name}`")
        _apply_migrations(conn, db_name)
    admin_pool.close_all()

    yield base

    try:
        teardown_config = DatabaseConfig(
            name="",
            pool_name="e2e_teardown_pool",
        )
        teardown_pool = Database(teardown_config)
        with teardown_pool.connection() as conn:
            conn.autocommit = True
            connector = conn.cursor()
            connector.execute(f"DROP DATABASE IF EXISTS `{db_name}`")
            connector.close()
        teardown_pool.close_all()
        print(f"\n[teardown] dropped `{db_name}`", flush=True)
    except Exception as exc:  # pragma: no cover - diagnostics
        print(f"\n[teardown] FAILED to drop `{db_name}`: {exc!r}", flush=True)
        raise


@pytest.fixture(scope="module")
def repository(e2e_db):
    database = Database(DatabaseConfig(name=e2e_db.name, pool_name="e2e_repo_pool"))
    yield ReconciliationRepository(database)
    database.close_all()


@pytest.fixture(scope="module")
def user_repository(e2e_db):
    database = Database(DatabaseConfig(name=e2e_db.name, pool_name="e2e_user_pool"))
    yield UserRepository(database)
    database.close_all()


class TestConnectivity:
    def test_pool_health_check(self, e2e_db):
        database = Database(DatabaseConfig(name=e2e_db.name, pool_name="e2e_health_pool"))
        try:
            assert database.is_healthy is True
        finally:
            database.close_all()

    def test_schema_is_reconciliation_complete(self, repository):
        with repository._database.connection() as conn:
            connector = conn.cursor()
            connector.execute("SHOW TABLES")
            tables = {row[0] for row in connector.fetchall()}
            connector.close()
        assert "companies" in tables
        assert "users" in tables
        assert "reconciliation_runs" in tables
        assert "reconciliation_results" in tables
        assert "reconciliation_errors" in tables


class TestCompanyCrud:
    def test_insert_and_read_company(self, repository):
        with repository._database.connection() as conn, conn.cursor() as connector:
            connector.execute(
                "INSERT INTO companies (name, tax_registration_number, email) "
                "VALUES (%s, %s, %s)",
                ("E2E Co", "E2E_" + "9" * 10, "e2e@example.test"),
            )
            company_id = connector.lastrowid
            conn.commit()
            connector.execute("SELECT id, name FROM companies WHERE id = %s", (company_id,))
            row = connector.fetchone()
            assert row[1] == "E2E Co"
            connector.execute("DELETE FROM companies WHERE id = %s", (company_id,))
            conn.commit()
            connector.execute("SELECT COUNT(*) FROM companies WHERE id = %s", (company_id,))
            assert connector.fetchone()[0] == 0


class TestRunExclusive:
    @pytest.fixture(autouse=True)
    def _company(self, repository):
        with repository._database.connection() as conn, conn.cursor() as connector:
            connector.execute(
                "INSERT INTO companies (name, tax_registration_number, email) "
                "VALUES (%s, %s, %s)",
                ("E2E Runs Co", "E2E_" + "8" * 10, "e2e-runs@example.test"),
            )
            company_id = connector.lastrowid
            conn.commit()
        try:
            yield company_id
        finally:
            with repository._database.connection() as conn, conn.cursor() as connector:
                connector.execute("DELETE FROM reconciliation_runs WHERE company_id = %s", (company_id,))
                connector.execute("DELETE FROM companies WHERE id = %s", (company_id,))
                conn.commit()

    def test_create_run_exclusive_inserts_once(self, repository, _company):
        run, is_new = repository.create_run_exclusive(_company, "2025-04")
        assert is_new is True
        assert run.company_id == _company
        assert run.status == "pending"

        again, is_new_again = repository.create_run_exclusive(_company, "2025-04")
        assert is_new_again is False
        assert again.id == run.id

    def test_concurrent_create_produces_single_run(self, repository, _company):
        results = []

        def worker():
            _, is_new = repository.create_run_exclusive(_company, "2025-04")
            results.append(is_new)

        with ThreadPoolExecutor(max_workers=_WORKER_POOL_SIZE) as pool:
            list(pool.map(lambda _: worker(), range(_WORKER_POOL_SIZE)))

        assert results.count(True) == 1
        assert results.count(False) == 1

        with repository._database.connection() as conn, conn.cursor() as connector:
            connector.execute(
                "SELECT COUNT(*) FROM reconciliation_runs WHERE company_id = %s AND period = %s",
                (_company, "2025-04"),
            )
            assert connector.fetchone()[0] == 1

    def test_start_and_complete_run(self, repository, _company):
        run, _ = repository.create_run_exclusive(_company, "2025-05")
        assert repository.start_run(run.id) is True
        assert repository.complete_run(run.id, 2, 1, 0) is True
        fetched = repository.get_run_by_id(run.id)
        assert fetched.status == "completed"
        assert fetched.matched_count == 2
        assert fetched.unmatched_count == 1

    def test_unknown_company_raises(self, repository):
        with pytest.raises(ValueError, match="not found"):
            repository.create_run_exclusive(999999, "2025-04")


# ---------------------------------------------------------------------------
# Reconciliation finish race + real rollback (Phase 6)
# ---------------------------------------------------------------------------

def _seed_company(database, name, tax_registration, email):
    with database.connection() as conn, conn.cursor() as connector:
        connector.execute(
            "INSERT INTO companies (name, tax_registration_number, email) "
            "VALUES (%s, %s, %s)",
            (name, tax_registration, email),
        )
        company_id = connector.lastrowid
        conn.commit()
    return company_id


def _drop_company(database, company_id):
    with database.connection() as conn, conn.cursor() as connector:
        connector.execute(
            "DELETE FROM reconciliation_runs WHERE company_id = %s", (company_id,)
        )
        connector.execute(
            "DELETE FROM users WHERE company_id = %s", (company_id,)
        )
        connector.execute("DELETE FROM companies WHERE id = %s", (company_id,))
        conn.commit()


def _seed_running_run(repository, company_id, period="2026-01"):
    run, _ = repository.create_run_exclusive(company_id, period)
    repository.start_run(run.id)
    return run.id


def _seed_active_admin(database, company_id, username, role="admin"):
    with database.connection() as conn, conn.cursor() as connector:
        connector.execute(
            "INSERT IGNORE INTO roles (name) VALUES ('admin'), ('accountant'), "
            "('manager'), ('viewer')"
        )
        connector.execute(
            "INSERT INTO users (company_id, username, email, password_hash, "
            "first_name, last_name, is_active) VALUES (%s, %s, %s, %s, %s, %s, 1)",
            (company_id, username, f"{username}@example.test",
             "$2b$12$S6K77KBp40oAgCdh0gaThefjHeH3F8Z.lOUIHzYD5yo.3OemNOFeC",
             "First", "Last"),
        )
        user_id = connector.lastrowid
        connector.execute(
            "INSERT INTO user_roles (user_id, role_id) "
            "SELECT %s, id FROM roles WHERE name = %s",
            (user_id, role),
        )
        conn.commit()
    return user_id


def _count_results(repository, run_id):
    with repository._database.connection() as conn, conn.cursor() as connector:
        connector.execute(
            "SELECT COUNT(*) FROM reconciliation_results WHERE run_id = %s", (run_id,)
        )
        return connector.fetchone()[0]


def _results_for(batch_tag):
    """A small distinct result set (NULL invoice ids avoid unique-key clashes)."""
    from backend.modules.reconciliation.model import ReconciliationResult

    return [
        ReconciliationResult(
            account_invoice_id=None,
            tax_invoice_id=None,
            match_status="matched",
            discrepancy_amount=0.0,
            notes=f"{batch_tag}-matched",
        ),
        ReconciliationResult(
            account_invoice_id=None,
            tax_invoice_id=None,
            match_status="mismatched",
            discrepancy_amount=10.00,
            notes=f"{batch_tag}-mismatched",
        ),
    ]


class TestFinishRunRace:
    @pytest.fixture(autouse=True)
    def _company_run(self, repository):
        company_id = _seed_company(
            repository._database, "Finish Race Co", "P14_" + "1" * 10,
            "finish-race@example.test",
        )
        try:
            yield company_id, _seed_running_run(repository, company_id)
        finally:
            _drop_company(repository._database, company_id)

    def test_concurrent_finish_persists_single_result_set(self, repository, _company_run):
        company_id, run_id = _company_run
        outcomes = []

        def worker(tag):
            try:
                ok = repository.finish_run_transaction(
                    run_id,
                    _results_for(tag),
                    [],
                    invoice_count=2, tax_invoice_count=2,
                    matched_count=1, unmatched_count=1, error_count=0,
                )
                outcomes.append((tag, ok))
            except Exception as exc:  # pragma: no cover - fail loudly below
                outcomes.append((tag, f"error: {exc!r}"))

        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda tag: worker(tag), ("A", "B")))

        # The loser must observe the completed state and return False cleanly;
        # a deadlock error here would be a regression (Phase 14 fixed it).
        for tag, outcome in outcomes:
            assert isinstance(outcome, bool), f"{tag} failed with {outcome}"

        # Exactly one finish transaction may win the state transition.
        winners = [tag for tag, ok in outcomes if ok]
        losers = [tag for tag, ok in outcomes if not ok]
        assert len(winners) == 1
        assert len(losers) == 1

        # The final database state must match the winning transaction exactly.
        fetched = repository.get_run_by_id(run_id)
        assert fetched.status == "completed"
        assert fetched.matched_count == 1
        assert fetched.unmatched_count == 1
        assert fetched.error_count == 0
        assert _count_results(repository, run_id) == 2

        winner_tag, = winners
        with repository._database.connection() as conn, conn.cursor() as connector:
            connector.execute(
                "SELECT notes FROM reconciliation_results WHERE run_id = %s ORDER BY id",
                (run_id,),
            )
            notes = [row[0] for row in connector.fetchall()]
        assert set(notes) == {f"{winner_tag}-matched", f"{winner_tag}-mismatched"}

    def test_finish_after_completed_rolls_back_leaving_no_partial_state(
        self, repository, _company_run
    ):
        """Real rollback: a second finish on an already-completed run returns
        False and none of its result rows are persisted (partial state)."""
        company_id, run_id = _company_run
        assert repository.finish_run_transaction(
            run_id, _results_for("FIRST"), [],
            invoice_count=2, tax_invoice_count=2,
            matched_count=1, unmatched_count=1, error_count=0,
        ) is True

        assert repository.finish_run_transaction(
            run_id, _results_for("SECOND"), [],
            invoice_count=2, tax_invoice_count=2,
            matched_count=1, unmatched_count=1, error_count=0,
        ) is False

        fetched = repository.get_run_by_id(run_id)
        assert fetched.status == "completed"
        assert fetched.matched_count == 1
        # Only the first (winning) result set is present; the second was rolled back.
        assert _count_results(repository, run_id) == 2
        with repository._database.connection() as conn, conn.cursor() as connector:
            connector.execute(
                "SELECT notes FROM reconciliation_results WHERE run_id = %s ORDER BY id",
                (run_id,),
            )
            notes = [row[0] for row in connector.fetchall()]
        assert all(note.startswith("FIRST-") for note in notes)


class TestLastActiveAdminRace:
    """Concurrent admin-reducing mutations must never end with zero active admins."""

    @pytest.fixture(autouse=True)
    def _company_admins(self, user_repository):
        company_id = _seed_company(
            user_repository._database, "Admin Race Co", "P14_" + "2" * 10,
            "admin-race@example.test",
        )
        try:
            admin_a = _seed_active_admin(user_repository._database, company_id, "admin_race_a")
            admin_b = _seed_active_admin(user_repository._database, company_id, "admin_race_b")
            yield company_id, (admin_a, admin_b)
        finally:
            _drop_company(user_repository._database, company_id)

    def test_concurrent_deactivations_keep_one_active_admin(self, user_repository, _company_admins):
        company_id, (admin_a, admin_b) = _company_admins
        service = UserService(user_repository)
        outcomes = []

        def deactivate(user_id):
            try:
                service.deactivate_user(user_id)
                outcomes.append("ok")
            except ValueError as exc:
                outcomes.append(f"rejected: {exc}")

        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(deactivate, (admin_a, admin_b)))

        # Invariant: at least one active admin must remain.
        assert user_repository.count_active_admins(company_id) == 1
        # And exactly one deactivation actually committed.
        assert outcomes.count("ok") == 1
        assert any(outcome.startswith("rejected") for outcome in outcomes)

    def test_concurrent_delete_and_deactivate_keep_one_active_admin(
        self, user_repository, _company_admins
    ):
        company_id, (admin_a, admin_b) = _company_admins
        service = UserService(user_repository)
        outcomes = []

        def remove_a():
            try:
                service.delete_user(admin_a)
                outcomes.append("ok")
            except ValueError as exc:
                outcomes.append(f"rejected: {exc}")

        def deactivate_b():
            try:
                service.deactivate_user(admin_b)
                outcomes.append("ok")
            except ValueError as exc:
                outcomes.append(f"rejected: {exc}")

        with ThreadPoolExecutor(max_workers=2) as pool:
            futs = [pool.submit(remove_a), pool.submit(deactivate_b)]
            for fut in futs:
                fut.result()

        assert user_repository.count_active_admins(company_id) == 1
        assert outcomes.count("ok") == 1
        assert any(outcome.startswith("rejected") for outcome in outcomes)


def test_scratch_name_guard():
    for name in ("invoice_system", "invoice_system_e2e", "MYSQL", "information_schema"):
        with pytest.raises(AssertionError):
            _guard_db_name(name)