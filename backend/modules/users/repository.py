"""User repository for database operations on the users table."""

from datetime import datetime
from typing import Optional, List

import mysql.connector

from backend.database import Database
from backend.modules.users.model import User
from backend.shared.database import db_cursor


class UserRepository:
    """Repository for user database operations.

    Handles all CRUD operations for the users table using
    parameterized queries and a shared connection pool.
    """

    def __init__(self, database: Database) -> None:
        self._database = database

    def _row_to_user(self, row: tuple) -> User:
        return User(
            id=row[0],
            full_name=row[1],
            email=row[2],
            password_hash=row[3],
            phone=row[4],
            role=row[5],
            status=row[6],
            created_at=row[7],
            updated_at=row[8]
        )

    def create(self, user: User) -> User:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                query = """
                    INSERT INTO users (full_name, email, password_hash, phone, role, status)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """
                cursor.execute(query, (
                    user.full_name,
                    user.email,
                    user.password_hash,
                    user.phone,
                    user.role,
                    user.status
                ))
                conn.commit()
                user.id = cursor.lastrowid
                user.created_at = datetime.now()
                user.updated_at = datetime.now()
                return user
            except mysql.connector.Error:
                conn.rollback()
                raise

    def get_by_id(self, user_id: int) -> Optional[User]:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                query = "SELECT * FROM users WHERE id = %s"
                cursor.execute(query, (user_id,))
                row = cursor.fetchone()
                if row:
                    return self._row_to_user(row)
                return None
            except mysql.connector.Error:
                raise

    def get_by_email(self, email: str) -> Optional[User]:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                query = "SELECT * FROM users WHERE email = %s"
                cursor.execute(query, (email,))
                row = cursor.fetchone()
                if row:
                    return self._row_to_user(row)
                return None
            except mysql.connector.Error:
                raise

    def exists_by_email(self, email: str) -> bool:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                query = "SELECT COUNT(*) FROM users WHERE email = %s"
                cursor.execute(query, (email,))
                result = cursor.fetchone()
                return result[0] > 0
            except mysql.connector.Error:
                raise

    def get_all(self) -> List[User]:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                query = "SELECT * FROM users ORDER BY created_at DESC"
                cursor.execute(query)
                rows = cursor.fetchall()
                return [self._row_to_user(row) for row in rows]
            except mysql.connector.Error:
                raise

    def count_active_admins(self) -> int:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                query = (
                    "SELECT COUNT(*) FROM users "
                    "WHERE role = %s AND status = %s"
                )
                cursor.execute(query, ("admin", "active"))
                row = cursor.fetchone()
                return int(row[0]) if row else 0
            except mysql.connector.Error:
                raise

    def update(self, user: User) -> Optional[User]:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                query = """
                    UPDATE users
                    SET full_name = %s, email = %s, password_hash = %s,
                        phone = %s, role = %s, status = %s, updated_at = NOW()
                    WHERE id = %s
                """
                cursor.execute(query, (
                    user.full_name,
                    user.email,
                    user.password_hash,
                    user.phone,
                    user.role,
                    user.status,
                    user.id
                ))
                conn.commit()
                if cursor.rowcount > 0:
                    cursor.execute("SELECT * FROM users WHERE id = %s", (user.id,))
                    row = cursor.fetchone()
                    if row:
                        return self._row_to_user(row)
                return None
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
