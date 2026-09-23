"""Regression tests for the repository-level last-active-admin guard (Phase 6).

Phase 14 found that the ``SELECT ... FOR UPDATE`` helpers
``_lock_active_admin_ids`` / ``_guard_not_last_active_admin`` were dead code:
the last-active-admin invariant was only enforced by the service layer's
unlocked ``count_active_admins()`` check, leaving a check-then-act race where
two concurrent deactivations of two different active admins could end with
zero active admins.

These offline tests lock in that the FOR UPDATE guard is now wired into the
admin-reducing mutation paths (``update``, ``delete``, ``set_roles``) so the
invariant holds even when the service-layer fast-fail is bypassed by
concurrency. They use a fake connector (like the reconciliation repository
tests) and therefore run without a database.
"""

import pytest

from backend.modules.users.model import User
from backend.modules.users.repository import UserRepository


class FakeCursor:
    """Cursor that returns scripted fetch results and records queries."""

    def __init__(self, fetch_results=None):
        self.fetch_results = list(fetch_results or [])
        self.queries = []
        self.rowcount = 1

    def execute(self, query, params=None):
        self.queries.append(query)
        return None

    def fetchone(self):
        if self.fetch_results:
            return self.fetch_results.pop(0)
        return None

    def fetchall(self):
        if self.fetch_results:
            return self.fetch_results.pop(0)
        return []

    def close(self):
        return None


class FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor
        self.committed = False
        self.rolled_back = False

    def cursor(self, **kwargs):
        return self._cursor

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


class FakeDatabase:
    def __init__(self, fetch_results=None):
        self.conn = FakeConn(FakeCursor(fetch_results))

    def connection(self):
        return _ConnContext(self.conn)


class _ConnContext:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, *exc):
        return False


def _make_user(user_id=1, is_active=True, roles=None):
    return User(
        id=user_id,
        company_id=1,
        username=f"admin{user_id}",
        email=f"admin{user_id}@example.com",
        password_hash="$2b$12$S6K77KBp40oAgCdh0gaThefjHeH3F8Z.lOUIHzYD5yo.3OemNOFeC",
        first_name="Admin",
        last_name=str(user_id),
        is_active=is_active,
        roles=roles or ["admin"],
    )


# ---------------------------------------------------------------------------
# update() — deactivation path
# ---------------------------------------------------------------------------

class TestUpdateGuard:
    def test_deactivate_last_active_admin_raises_without_mutating(self):
        # _lock_active_admin_ids returns exactly this user -> last active admin
        database = FakeDatabase(fetch_results=[[(1,)]])
        repo = UserRepository(database)

        with pytest.raises(ValueError, match="last active admin"):
            repo.update(_make_user(user_id=1, is_active=False))

        assert database.conn.rolled_back is True
        assert database.conn.committed is False
        # Only the lock SELECT ran; the UPDATE must never be issued.
        lock_query = database.conn._cursor.queries[0]
        assert "FOR UPDATE" in lock_query
        assert "UPDATE users" not in " ".join(database.conn._cursor.queries[1:])

    def test_deactivate_admin_allowed_when_another_active_admin_exists(self):
        # Two active admins -> deactivating one is fine.
        database = FakeDatabase(fetch_results=[
            [(1,), (2,)],                                   # lock result
            (1, 1, "admin1", "admin1@example.com",          # refreshed user row
             "hash", "Admin", "1", 0, None, None, None,
             "en", "light", "YYYY-MM-DD", "#,##0.00", "UTC", None, 25),
            [("admin",)],                                   # roles
        ])
        repo = UserRepository(database)

        updated = repo.update(_make_user(user_id=1, is_active=False))
        assert updated is not None
        assert database.conn.committed is True
        assert database.conn.rolled_back is False

    def test_updating_non_admin_does_not_lock_guard_path(self):
        # A viewer update must still go through the normal update path.
        database = FakeDatabase(fetch_results=[
            [],                                             # no active admins
            (2, 1, "viewer1", "viewer1@example.com", "hash",
             "V", "1", 1, None, None, None,
             "en", "light", "YYYY-MM-DD", "#,##0.00", "UTC", None, 25),
            [("viewer",)],
        ])
        repo = UserRepository(database)

        user = _make_user(user_id=2, roles=["viewer"])
        updated = repo.update(user)
        assert updated is not None
        assert database.conn.committed is True


# ---------------------------------------------------------------------------
# delete() path
# ---------------------------------------------------------------------------

class TestDeleteGuard:
    def test_delete_last_active_admin_raises_without_mutating(self):
        database = FakeDatabase(fetch_results=[[(1,)]])
        repo = UserRepository(database)

        with pytest.raises(ValueError, match="last active admin"):
            repo.delete(1)

        assert database.conn.rolled_back is True
        assert database.conn.committed is False
        assert "DELETE FROM users" not in " ".join(database.conn._cursor.queries[1:])

    def test_delete_admin_allowed_when_another_active_admin_exists(self):
        database = FakeDatabase(fetch_results=[[(1,), (2,)]])
        repo = UserRepository(database)

        assert repo.delete(2) is True
        assert database.conn.committed is True


# ---------------------------------------------------------------------------
# set_roles() — demotion path
# ---------------------------------------------------------------------------

class TestSetRolesGuard:
    def test_demote_last_active_admin_raises_without_mutating(self):
        database = FakeDatabase(fetch_results=[[(1,)]])
        repo = UserRepository(database)

        with pytest.raises(ValueError, match="last active admin"):
            repo.set_roles(1, ["viewer"])

        assert database.conn.rolled_back is True
        assert database.conn.committed is False
        # The role DELETE must never have been issued.
        assert "DELETE FROM user_roles" not in " ".join(database.conn._cursor.queries[1:])

    def test_keep_admin_role_does_not_guard(self):
        database = FakeDatabase(fetch_results=[
            [(1,), (2,)],                                   # lock result
            [],                                             # roles loader (deleted)
        ])
        repo = UserRepository(database)

        repo.set_roles(1, ["admin"])  # must not raise
        assert database.conn.committed is True