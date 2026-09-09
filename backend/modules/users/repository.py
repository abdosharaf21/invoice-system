"""User repository for database operations on the users table."""

from datetime import datetime
from typing import List, Optional

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
            updated_at=row[10]
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

    def _assign_roles(self, cursor, user_id: int, roles: List[str]) -> None:
        placeholders = ", ".join(["%s"] * len(roles))
        query = f"""
            INSERT INTO user_roles (user_id, role_id)
            SELECT %s, r.id
            FROM roles r
            WHERE r.name IN ({placeholders})
        """
        cursor.execute(query, (user_id, *roles))

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

    def get_by_id(self, user_id: int) -> Optional[User]:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
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
                for user in users:
                    user.roles = self._load_roles(cursor, user.id)
                return users
            except mysql.connector.Error:
                raise

    def count_active_admins(self) -> int:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                query = (
                    "SELECT COUNT(*) FROM users u "
                    "INNER JOIN user_roles ur ON ur.user_id = u.id "
                    "INNER JOIN roles r ON r.id = ur.role_id "
                    "WHERE r.name = %s AND u.is_active = 1"
                )
                cursor.execute(query, ("admin",))
                row = cursor.fetchone()
                return int(row[0]) if row else 0
            except mysql.connector.Error:
                raise

    def update(self, user: User) -> Optional[User]:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
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
                if cursor.rowcount > 0:
                    return self.get_by_id(user.id)
                return None
            except mysql.connector.Error:
                conn.rollback()
                raise

    def set_roles(self, user_id: int, roles: List[str]) -> List[str]:
        """Replace the roles assigned to a user."""
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                cursor.execute("DELETE FROM user_roles WHERE user_id = %s", (user_id,))
                self._assign_roles(cursor, user_id, roles)
                conn.commit()
                return self._load_roles(cursor, user_id)
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
                query = "DELETE FROM users WHERE id = %s"
                cursor.execute(query, (user_id,))
                conn.commit()
                return cursor.rowcount > 0
            except mysql.connector.Error:
                conn.rollback()
                raise