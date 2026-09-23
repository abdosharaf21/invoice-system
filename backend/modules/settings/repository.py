"""Repository for the application_settings table."""

from typing import Dict, List, Optional

import mysql.connector

from backend.database import Database
from backend.modules.settings.model import ApplicationSetting
from backend.shared.database import db_cursor


class ApplicationSettingRepository:
    """CRUD + bulk operations for the application_settings key/value table."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def _row_to_setting(self, row: tuple) -> ApplicationSetting:
        return ApplicationSetting(
            id=row[0],
            setting_key=row[1],
            setting_value=row[2],
            value_type=row[3],
            description=row[4],
            created_at=row[5],
            updated_at=row[6],
        )

    def get_by_key(self, key: str) -> Optional[ApplicationSetting]:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                cursor.execute(
                    "SELECT * FROM application_settings WHERE setting_key = %s",
                    (key,),
                )
                row = cursor.fetchone()
                return self._row_to_setting(row) if row else None
            except mysql.connector.Error:
                raise

    def get_all(self) -> List[ApplicationSetting]:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                cursor.execute(
                    "SELECT * FROM application_settings ORDER BY setting_key"
                )
                return [self._row_to_setting(row) for row in cursor.fetchall()]
            except mysql.connector.Error:
                raise

    def get_all_as_dict(self) -> Dict[str, object]:
        """Return all settings as a flat {key: typed_value} dict."""
        settings = self.get_all()
        return {s.setting_key: s.typed_value() for s in settings}

    def upsert(self, setting: ApplicationSetting) -> ApplicationSetting:
        """Insert or update a setting by its unique key."""
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                query = """
                    INSERT INTO application_settings
                        (setting_key, setting_value, value_type, description)
                    VALUES (%s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        setting_value = VALUES(setting_value),
                        value_type = VALUES(value_type),
                        description = VALUES(description),
                        updated_at = NOW()
                """
                cursor.execute(query, (
                    setting.setting_key,
                    setting.setting_value,
                    setting.value_type,
                    setting.description,
                ))
                conn.commit()
                return self.get_by_key(setting.setting_key)
            except mysql.connector.Error:
                conn.rollback()
                raise

    def upsert_many(self, settings: List[ApplicationSetting]) -> None:
        """Batch upsert multiple settings in a single transaction."""
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                for s in settings:
                    cursor.execute(
                        """
                        INSERT INTO application_settings
                            (setting_key, setting_value, value_type, description)
                        VALUES (%s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                            setting_value = VALUES(setting_value),
                            value_type = VALUES(value_type),
                            description = VALUES(description),
                            updated_at = NOW()
                        """,
                        (s.setting_key, s.setting_value, s.value_type, s.description),
                    )
                conn.commit()
            except mysql.connector.Error:
                conn.rollback()
                raise

    def delete(self, key: str) -> bool:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                cursor.execute(
                    "DELETE FROM application_settings WHERE setting_key = %s",
                    (key,),
                )
                conn.commit()
                return cursor.rowcount > 0
            except mysql.connector.Error:
                conn.rollback()
                raise
