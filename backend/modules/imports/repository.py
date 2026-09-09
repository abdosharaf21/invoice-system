"""Import repository for database operations on import_batches and import_batch_errors."""

from datetime import datetime
from typing import List, Optional

import mysql.connector

from backend.database import Database
from backend.modules.imports.model import ImportBatch, ImportBatchError
from backend.shared.database import db_cursor


class ImportBatchRepository:
    """Repository for import batch tracking operations."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def _row_to_batch(self, row: tuple) -> ImportBatch:
        return ImportBatch(
            id=row[0],
            company_id=row[1],
            filename=row[2],
            file_type=row[3],
            status=row[4],
            total_rows=row[5],
            processed_rows=row[6],
            error_rows=row[7],
            uploaded_by=row[8],
            started_at=row[9],
            finished_at=row[10],
            created_at=row[11],
            updated_at=row[12]
        )

    def _row_to_error(self, row: tuple) -> ImportBatchError:
        return ImportBatchError(
            id=row[0],
            batch_id=row[1],
            row_number=row[2],
            error_message=row[3],
            raw_data=row[4],
            created_at=row[5]
        )

    def create(self, batch: ImportBatch) -> ImportBatch:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                query = """
                    INSERT INTO import_batches
                        (company_id, filename, file_type, status,
                         total_rows, processed_rows, error_rows, uploaded_by)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """
                cursor.execute(query, (
                    batch.company_id,
                    batch.filename,
                    batch.file_type,
                    batch.status,
                    batch.total_rows,
                    batch.processed_rows,
                    batch.error_rows,
                    batch.uploaded_by
                ))
                batch.id = cursor.lastrowid
                conn.commit()
                batch.created_at = datetime.now()
                batch.updated_at = datetime.now()
                return batch
            except mysql.connector.Error:
                conn.rollback()
                raise

    def get_by_id(self, batch_id: int) -> Optional[ImportBatch]:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                cursor.execute("SELECT * FROM import_batches WHERE id = %s", (batch_id,))
                row = cursor.fetchone()
                return self._row_to_batch(row) if row else None
            except mysql.connector.Error:
                raise

    def list_by_company(
        self,
        company_id: int,
        limit: int = 100,
        offset: int = 0
    ) -> List[ImportBatch]:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                query = """
                    SELECT * FROM import_batches
                    WHERE company_id = %s
                    ORDER BY created_at DESC, id DESC
                    LIMIT %s OFFSET %s
                """
                cursor.execute(query, (company_id, limit, offset))
                rows = cursor.fetchall()
                return [self._row_to_batch(row) for row in rows]
            except mysql.connector.Error:
                raise

    def start(self, batch_id: int) -> bool:
        """Mark a batch as processing and record the start time."""
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                query = """
                    UPDATE import_batches
                    SET status = 'processing', started_at = NOW(),
                        updated_at = NOW()
                    WHERE id = %s
                """
                cursor.execute(query, (batch_id,))
                conn.commit()
                return cursor.rowcount > 0
            except mysql.connector.Error:
                conn.rollback()
                raise

    def update_counts(
        self,
        batch_id: int,
        processed_rows: Optional[int] = None,
        error_rows: Optional[int] = None,
        status: Optional[str] = None
    ) -> bool:
        """Update processing counters and optionally the batch status."""
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                set_clauses = ["updated_at = NOW()"]
                params = []
                if processed_rows is not None:
                    set_clauses.append("processed_rows = %s")
                    params.append(processed_rows)
                if error_rows is not None:
                    set_clauses.append("error_rows = %s")
                    params.append(error_rows)
                if status is not None:
                    set_clauses.append("status = %s")
                    params.append(status)
                    if status in ("completed", "failed"):
                        set_clauses.append("finished_at = NOW()")

                query = f"UPDATE import_batches SET {', '.join(set_clauses)} WHERE id = %s"
                params.append(batch_id)
                cursor.execute(query, tuple(params))
                conn.commit()
                return cursor.rowcount > 0
            except mysql.connector.Error:
                conn.rollback()
                raise

    def add_error(self, error: ImportBatchError) -> ImportBatchError:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                query = """
                    INSERT INTO import_batch_errors
                        (batch_id, `row_number`, error_message, raw_data)
                    VALUES (%s, %s, %s, %s)
                """
                cursor.execute(query, (
                    error.batch_id,
                    error.row_number,
                    error.error_message,
                    error.raw_data
                ))
                error.id = cursor.lastrowid
                conn.commit()
                error.created_at = datetime.now()
                return error
            except mysql.connector.Error:
                conn.rollback()
                raise

    def list_errors(self, batch_id: int) -> List[ImportBatchError]:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                query = """
                    SELECT * FROM import_batch_errors
                    WHERE batch_id = %s
                    ORDER BY `row_number`, id
                """
                cursor.execute(query, (batch_id,))
                rows = cursor.fetchall()
                return [self._row_to_error(row) for row in rows]
            except mysql.connector.Error:
                raise

    def get_error_count(self, batch_id: int) -> int:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                cursor.execute(
                    "SELECT COUNT(*) FROM import_batch_errors WHERE batch_id = %s",
                    (batch_id,)
                )
                result = cursor.fetchone()
                return int(result[0]) if result else 0
            except mysql.connector.Error:
                raise

    def delete(self, batch_id: int) -> bool:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                cursor.execute("DELETE FROM import_batches WHERE id = %s", (batch_id,))
                conn.commit()
                return cursor.rowcount > 0
            except mysql.connector.Error:
                conn.rollback()
                raise