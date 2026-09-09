"""Authentication repository.

Handles refresh token blocklist persistence in MySQL.
Tokens are stored as JWT IDs (jti) with expiration timestamps.
"""

from datetime import datetime, timezone
from typing import Optional

import mysql.connector

from backend.database import Database
from backend.shared.database import db_cursor


class AuthRepository:
    """Repository for refresh token blocklist operations."""

    _TABLE = "refresh_token_blocklist"

    def __init__(self, database: Database) -> None:
        self._database = database

    def add_to_blocklist(self, jti: str, token_type: str, expires_at: datetime) -> bool:
        """Add a token JTI to the blocklist."""
        sql = f"""
            INSERT IGNORE INTO `{self._TABLE}` (jti, token_type, expires_at)
            VALUES (%s, %s, %s)
        """
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                cursor.execute(sql, (jti, token_type, expires_at))
                conn.commit()
                return True
            except mysql.connector.Error:
                conn.rollback()
                raise

    def is_blocklisted(self, jti: str) -> bool:
        """Check if a token JTI is in the blocklist."""
        sql = f"""
            SELECT COUNT(*) AS cnt
            FROM `{self._TABLE}`
            WHERE jti = %s
        """
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            cursor.execute(sql, (jti,))
            row = cursor.fetchone()
            return row[0] > 0 if row else False

    def purge_expired(self) -> int:
        """Remove expired tokens from the blocklist."""
        sql = f"""
            DELETE FROM `{self._TABLE}`
            WHERE expires_at < %s
        """
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                now = datetime.now(timezone.utc)
                cursor.execute(sql, (now,))
                deleted = cursor.rowcount
                conn.commit()
                return deleted
            except mysql.connector.Error:
                conn.rollback()
                raise

    def delete_by_jti(self, jti: str) -> bool:
        """Remove a specific JTI from the blocklist."""
        sql = f"""
            DELETE FROM `{self._TABLE}`
            WHERE jti = %s
        """
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                cursor.execute(sql, (jti,))
                deleted = cursor.rowcount
                conn.commit()
                return deleted > 0
            except mysql.connector.Error:
                conn.rollback()
                raise


def init_auth_repository(database: Database) -> AuthRepository:
    """Create and return an AuthRepository instance."""
    return AuthRepository(database)
