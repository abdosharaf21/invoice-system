"""User repository for database operations on the users table."""

from datetime import datetime
from typing import Dict, List, Optional

import mysql.connector

from backend.database import Database
from backend.modules.users.model import User
from backend.shared.database import db_cursor


class UserRepository:
    """Repository for user database operations.

    Handles all CRUD operations for the users table using
    parameterized queries and a shared connection pool. Roles are
    stored in the normalized user_roles/roles tables and are loaded
    alongside the user record.
    """

    def __init__(self, database: Database) -> None:
        self._database = database

    def _row_to_user(self, row: tuple) -> User:
        return User(
            id=row[0],
            company_id=row[1],
            username=row[2],
            email=row[3],
            password_hash=row[4],
            first_name=row[5],
            last_name=row[6],
            is_active=bool(row[7]),
            last_login_at=row[8],
            created_at=row[9],
            updated_at=row[10],
            language=row[11] if len(row) > 11 else "en",
            theme=row[12] if len(row) > 12 else "light",
            date_format=row[13] if len(row) > 13 else "YYYY-MM-DD",
            number_format=row[14] if len(row) > 14 else "#,##0.00",
            timezone=row[15] if len(row) > 15 else "UTC",
            avatar_path=row[16] if len(row) > 16 else None,
            pagination_size=int(row[17]) if len(row) > 17 and row[17] is not None else 25,
        )

    def _load_roles(self, cursor, user_id: int) -> List[str]:
        query = """
            SELECT r.name
            FROM roles r
            INNER JOIN user_roles ur ON ur.role_id = r.id
            WHERE ur.user_id = %s
            ORDER BY r.id
        """
        cursor.execute(query, (user_id,))
        return [row[0].lower() for row in cursor.fetchall()]

    def _load_roles_batch(self, cursor, user_ids) -> Dict[int, List[str]]:
        """Load roles for many users in one query, keyed by user id."""
        ids = [user_id for user_id in user_ids if user_id is not None]
        if not ids:
            return {}
        placeholders = ", ".join(["%s"] * len(ids))
        query = (
            f"SELECT ur.user_id, r.name "
            f"FROM roles r INNER JOIN user_roles ur ON ur.role_id = r.id "
            f"WHERE ur.user_id IN ({placeholders}) "
            "ORDER BY ur.user_id, r.id"
        )
        cursor.execute(query, ids)
        grouped: Dict[int, List[str]] = {}
        for user_id, name in cursor.fetchall():
            grouped.setdefault(user_id, []).append(name.lower())
        return grouped

    def _assign_roles(self, cursor, user_id: int, roles: List[str]) -> None:
        placeholders = ", ".join(["%s"] * len(roles))
        query = f"""
            INSERT INTO user_roles (user_id, role_id)
            SELECT %s, r.id
            FROM roles r
            WHERE r.name IN ({placeholders})
        """
        cursor.execute(query, (user_id, *roles))

    def _lock_active_admin_ids(self, cursor) -> set:
        """Return the ids of currently active admin users, locking their rows.

        The lock (``SELECT ... FOR UPDATE``) serializes concurrent
        admin-reducing mutations: a second transaction that would remove,
        demote, or deactivate an active admin is forced to wait until the
        first commits, then re-counts against the post-commit state. This
        closes the check-then-act window in the last-active-admin guard.
        """
        cursor.execute(
            """
            SELECT u.id FROM users u
            WHERE u.is_active = 1
              AND u.id IN (
                SELECT ur.user_id FROM user_roles ur
                INNER JOIN roles r ON r.id = ur.role_id
                WHERE r.name = %s
              )
            FOR UPDATE
            """,
            ("admin",),
        )
        return {row[0] for row in cursor.fetchall()}

    def _guard_not_last_active_admin(
        self, cursor, user_id: int, admin_ids: set
    ) -> None:
        """Raise ValueError when ``user_id`` is the last active admin.

        Args:
            cursor: Cursor on an active transaction.
            user_id: The user about to be removed/demoted/deactivated.
            admin_ids: Ids of currently active admins, already locked.

        Raises:
            ValueError: If the user is the last active admin, to preserve the
                "at least one active admin" invariant.
        """
        if user_id in admin_ids and len(admin_ids) <= 1:
            raise ValueError(
                "Cannot remove, demote, or deactivate the last active admin"
            )

    def create(self, user: User) -> User:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                query = """
                    INSERT INTO users
                        (company_id, username, email, password_hash,
                         first_name, last_name, is_active)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """
                cursor.execute(query, (
                    user.company_id,
                    user.username,
                    user.email,
                    user.password_hash,
                    user.first_name,
                    user.last_name,
                    user.is_active
                ))
                user.id = cursor.lastrowid
                roles = user.roles or ["viewer"]
                self._assign_roles(cursor, user.id, roles)
                user.roles = self._load_roles(cursor, user.id)
                conn.commit()
                user.created_at = datetime.now()
                user.updated_at = datetime.now()
                return user
            except mysql.connector.Error:
                conn.rollback()
                raise

    def get_by_id(
        self, user_id: int, company_id: Optional[int] = None
    ) -> Optional[User]:
        """Fetch a user by id, optionally scoped to a company.

        When ``company_id`` is provided the lookup is restricted to that
        tenant at the SQL level (``WHERE id = %s AND company_id = %s``), so a
        user belonging to another company is indistinguishable from a missing
        user. This is the same scoped-repository pattern used by the imports
        and reconciliation domains.

        Args:
            user_id: The user id to fetch.
            company_id: Optional owning company to scope the lookup to.

        Returns:
            The matching user, or None when absent (or outside the scope).
        """
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                query = "SELECT * FROM users WHERE id = %s"
                params: list = [user_id]
                if company_id is not None:
                    query += " AND company_id = %s"
                    params.append(company_id)
                cursor.execute(query, params)
                row = cursor.fetchone()
                if not row:
                    return None
                user = self._row_to_user(row)
                user.roles = self._load_roles(cursor, user.id)
                return user
            except mysql.connector.Error:
                raise

    def get_by_id_for_company(self, user_id: int, company_id: int) -> Optional[User]:
        """Fetch a user only when it belongs to ``company_id``.

        The tenant scope is enforced in SQL (``id`` and ``company_id`` must
        match) so a caller cannot read or operate on a user from another
        company by guessing an id alone.
        """
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                cursor.execute(
                    "SELECT * FROM users WHERE id = %s AND company_id = %s",
                    (user_id, company_id),
                )
                row = cursor.fetchone()
                if not row:
                    return None
                user = self._row_to_user(row)
                user.roles = self._load_roles(cursor, user.id)
                return user
            except mysql.connector.Error:
                raise

    def get_by_email(self, email: str) -> Optional[User]:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
                row = cursor.fetchone()
                if not row:
                    return None
                user = self._row_to_user(row)
                user.roles = self._load_roles(cursor, user.id)
                return user
            except mysql.connector.Error:
                raise

    def get_by_username(self, username: str) -> Optional[User]:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
                row = cursor.fetchone()
                if not row:
                    return None
                user = self._row_to_user(row)
                user.roles = self._load_roles(cursor, user.id)
                return user
            except mysql.connector.Error:
                raise

    def exists_by_email(self, email: str) -> bool:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                cursor.execute("SELECT COUNT(*) FROM users WHERE email = %s", (email,))
                result = cursor.fetchone()
                return result[0] > 0
            except mysql.connector.Error:
                raise

    def exists_by_username(self, username: str) -> bool:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                cursor.execute("SELECT COUNT(*) FROM users WHERE username = %s", (username,))
                result = cursor.fetchone()
                return result[0] > 0
            except mysql.connector.Error:
                raise

    def get_all(self) -> List[User]:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                cursor.execute("SELECT * FROM users ORDER BY created_at DESC")
                users = [self._row_to_user(row) for row in cursor.fetchall()]
                roles_by_id = self._load_roles_batch(
                    cursor, [user.id for user in users]
                )
                for user in users:
                    user.roles = roles_by_id.get(user.id, [])
                return users
            except mysql.connector.Error:
                raise

    def get_all_by_company(self, company_id: int) -> List[User]:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                cursor.execute(
                    "SELECT * FROM users WHERE company_id = %s ORDER BY created_at DESC",
                    (company_id,),
                )
                users = [self._row_to_user(row) for row in cursor.fetchall()]
                roles_by_id = self._load_roles_batch(
                    cursor, [user.id for user in users]
                )
                for user in users:
                    user.roles = roles_by_id.get(user.id, [])
                return users
            except mysql.connector.Error:
                raise

    def count_active_admins(self, company_id: Optional[int] = None) -> int:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                query = (
                    "SELECT COUNT(*) FROM users u "
                    "INNER JOIN user_roles ur ON ur.user_id = u.id "
                    "INNER JOIN roles r ON r.id = ur.role_id "
                    "WHERE r.name = %s AND u.is_active = 1 AND u.company_id = %s"
                )
                cursor.execute(query, ("admin", company_id))
                row = cursor.fetchone()
                return int(row[0]) if row else 0
            except mysql.connector.Error:
                raise

    def update_preferences(self, user_id: int, prefs: dict) -> Optional[User]:
        """Update only the current user's preference/settings columns."""
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                query = """
                    UPDATE users
                    SET language = %s, theme = %s, date_format = %s,
                        number_format = %s, timezone = %s, avatar_path = %s,
                        pagination_size = %s, updated_at = NOW()
                    WHERE id = %s
                """
                cursor.execute(query, (
                    prefs.get("language", "en"),
                    prefs.get("theme", "light"),
                    prefs.get("date_format", "YYYY-MM-DD"),
                    prefs.get("number_format", "#,##0.00"),
                    prefs.get("timezone", "UTC"),
                    prefs.get("avatar_path"),
                    prefs.get("pagination_size", 25),
                    user_id
                ))
                conn.commit()
                return self.get_by_id(user_id)
            except mysql.connector.Error:
                conn.rollback()
                raise

    def update(self, user: User) -> Optional[User]:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                active_admin_ids = self._lock_active_admin_ids(cursor)
                if user.id in active_admin_ids and not user.is_active:
                    self._guard_not_last_active_admin(cursor, user.id, active_admin_ids)
                query = """
                    UPDATE users
                    SET company_id = %s, username = %s, email = %s,
                        password_hash = %s, first_name = %s,
                        last_name = %s, is_active = %s, updated_at = NOW()
                    WHERE id = %s
                """
                cursor.execute(query, (
                    user.company_id,
                    user.username,
                    user.email,
                    user.password_hash,
                    user.first_name,
                    user.last_name,
                    user.is_active,
                    user.id
                ))
                conn.commit()
                return self.get_by_id(user.id)
            except ValueError:
                conn.rollback()
                raise
            except mysql.connector.Error:
                conn.rollback()
                raise

    def set_roles(self, user_id: int, roles: List[str]) -> List[str]:
        """Replace the roles assigned to a user.

        When the change removes the ``admin`` role from a currently active
        admin, the active-admin rows are locked (``SELECT ... FOR UPDATE``)
        and the last-active-admin invariant is enforced inside this
        transaction, serializing concurrent admin-reducing mutations.
        """
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                active_admin_ids = self._lock_active_admin_ids(cursor)
                if user_id in active_admin_ids and "admin" not in roles:
                    self._guard_not_last_active_admin(cursor, user_id, active_admin_ids)
                cursor.execute("DELETE FROM user_roles WHERE user_id = %s", (user_id,))
                self._assign_roles(cursor, user_id, roles)
                conn.commit()
                return self._load_roles(cursor, user_id)
            except ValueError:
                conn.rollback()
                raise
            except mysql.connector.Error:
                conn.rollback()
                raise

    def update_last_login(self, user_id: int) -> bool:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                query = """
                    UPDATE users
                    SET last_login_at = NOW()
                    WHERE id = %s
                """
                cursor.execute(query, (user_id,))
                conn.commit()
                return cursor.rowcount > 0
            except mysql.connector.Error:
                conn.rollback()
                raise

    def update_password(self, user_id: int, new_hash: str) -> bool:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                query = """
                    UPDATE users
                    SET password_hash = %s, updated_at = NOW()
                    WHERE id = %s
                """
                cursor.execute(query, (new_hash, user_id))
                conn.commit()
                return cursor.rowcount > 0
            except mysql.connector.Error:
                conn.rollback()
                raise

    def delete(self, user_id: int) -> bool:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                active_admin_ids = self._lock_active_admin_ids(cursor)
                if user_id in active_admin_ids:
                    self._guard_not_last_active_admin(cursor, user_id, active_admin_ids)
                query = "DELETE FROM users WHERE id = %s"
                cursor.execute(query, (user_id,))
                conn.commit()
                return cursor.rowcount > 0
            except ValueError:
                conn.rollback()
                raise
            except mysql.connector.Error:
                conn.rollback()
                raise