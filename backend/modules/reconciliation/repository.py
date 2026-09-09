"""Reconciliation repository for database operations on runs, results and errors."""

from datetime import datetime
from typing import List, Optional

import mysql.connector

from backend.database import Database
from backend.modules.reconciliation.model import (
    ReconciliationError,
    ReconciliationResult,
    ReconciliationRun,
)
from backend.shared.database import db_cursor


class ReconciliationRepository:
    """Repository for reconciliation runs, results and errors.

    Handles CRUD for the reconciliation_runs, reconciliation_results and
    reconciliation_errors tables using parameterized queries and a shared
    connection pool.
    """

    def __init__(self, database: Database) -> None:
        self._database = database

    def _row_to_run(self, row: tuple) -> ReconciliationRun:
        return ReconciliationRun(
            id=row[0],
            company_id=row[1],
            period=row[2],
            status=row[3],
            invoice_count=row[4],
            tax_invoice_count=row[5],
            matched_count=row[6],
            unmatched_count=row[7],
            error_count=row[8],
            started_at=row[9],
            finished_at=row[10],
            created_at=row[11],
            updated_at=row[12]
        )

    def _row_to_result(self, row: tuple) -> ReconciliationResult:
        return ReconciliationResult(
            id=row[0],
            run_id=row[1],
            account_invoice_id=row[2],
            tax_invoice_id=row[3],
            match_status=row[4],
            discrepancy_amount=row[5],
            notes=row[6],
            created_at=row[7]
        )

    def _row_to_error(self, row: tuple) -> ReconciliationError:
        return ReconciliationError(
            id=row[0],
            run_id=row[1],
            source_type=row[2],
            entity_id=row[3],
            error_type=row[4],
            field=row[5],
            accounting_value=row[6],
            tax_authority_value=row[7],
            difference=row[8],
            message=row[9],
            created_at=row[10]
        )

    def create_run(self, run: ReconciliationRun) -> ReconciliationRun:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                query = """
                    INSERT INTO reconciliation_runs
                        (company_id, period, status, invoice_count,
                         tax_invoice_count, matched_count, unmatched_count,
                         error_count)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """
                cursor.execute(query, (
                    run.company_id,
                    run.period,
                    run.status,
                    run.invoice_count,
                    run.tax_invoice_count,
                    run.matched_count,
                    run.unmatched_count,
                    run.error_count
                ))
                run.id = cursor.lastrowid
                conn.commit()
                run.created_at = datetime.now()
                run.updated_at = datetime.now()
                return run
            except mysql.connector.Error:
                conn.rollback()
                raise

    def get_run_by_id(self, run_id: int) -> Optional[ReconciliationRun]:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                cursor.execute("SELECT * FROM reconciliation_runs WHERE id = %s", (run_id,))
                row = cursor.fetchone()
                return self._row_to_run(row) if row else None
            except mysql.connector.Error:
                raise

    def list_runs_by_company(
        self,
        company_id: int,
        limit: int = 50,
        offset: int = 0
    ) -> List[ReconciliationRun]:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                query = """
                    SELECT * FROM reconciliation_runs
                    WHERE company_id = %s
                    ORDER BY created_at DESC, id DESC
                    LIMIT %s OFFSET %s
                """
                cursor.execute(query, (company_id, limit, offset))
                rows = cursor.fetchall()
                return [self._row_to_run(row) for row in rows]
            except mysql.connector.Error:
                raise

    def start_run(self, run_id: int) -> bool:
        """Mark a run as running and record the start time."""
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                query = """
                    UPDATE reconciliation_runs
                    SET status = 'running', started_at = NOW(),
                        updated_at = NOW()
                    WHERE id = %s
                """
                cursor.execute(query, (run_id,))
                conn.commit()
                return cursor.rowcount > 0
            except mysql.connector.Error:
                conn.rollback()
                raise

    def set_run_counts(self, run_id: int, invoice_count: int, tax_invoice_count: int) -> bool:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                query = """
                    UPDATE reconciliation_runs
                    SET invoice_count = %s, tax_invoice_count = %s,
                        updated_at = NOW()
                    WHERE id = %s
                """
                cursor.execute(query, (invoice_count, tax_invoice_count, run_id))
                conn.commit()
                return cursor.rowcount > 0
            except mysql.connector.Error:
                conn.rollback()
                raise

    def complete_run(
        self,
        run_id: int,
        matched_count: int,
        unmatched_count: int,
        error_count: int
    ) -> bool:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                query = """
                    UPDATE reconciliation_runs
                    SET status = 'completed',
                        matched_count = %s, unmatched_count = %s,
                        error_count = %s, finished_at = NOW(),
                        updated_at = NOW()
                    WHERE id = %s
                """
                cursor.execute(query, (
                    matched_count, unmatched_count, error_count, run_id
                ))
                conn.commit()
                return cursor.rowcount > 0
            except mysql.connector.Error:
                conn.rollback()
                raise

    def fail_run(self, run_id: int) -> bool:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                query = """
                    UPDATE reconciliation_runs
                    SET status = 'failed', finished_at = NOW(),
                        updated_at = NOW()
                    WHERE id = %s
                """
                cursor.execute(query, (run_id,))
                conn.commit()
                return cursor.rowcount > 0
            except mysql.connector.Error:
                conn.rollback()
                raise

    def add_result(self, result: ReconciliationResult) -> ReconciliationResult:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                query = """
                    INSERT INTO reconciliation_results
                        (run_id, account_invoice_id, tax_invoice_id,
                         match_status, discrepancy_amount, notes)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """
                cursor.execute(query, (
                    result.run_id,
                    result.account_invoice_id,
                    result.tax_invoice_id,
                    result.match_status,
                    result.discrepancy_amount,
                    result.notes
                ))
                result.id = cursor.lastrowid
                conn.commit()
                result.created_at = datetime.now()
                return result
            except mysql.connector.Error:
                conn.rollback()
                raise

    def list_results(self, run_id: int) -> List[ReconciliationResult]:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                cursor.execute(
                    "SELECT * FROM reconciliation_results WHERE run_id = %s ORDER BY id",
                    (run_id,)
                )
                rows = cursor.fetchall()
                return [self._row_to_result(row) for row in rows]
            except mysql.connector.Error:
                raise

    def count_results_by_status(self, run_id: int, status: str) -> int:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                query = """
                    SELECT COUNT(*) FROM reconciliation_results
                    WHERE run_id = %s AND match_status = %s
                """
                cursor.execute(query, (run_id, status))
                result = cursor.fetchone()
                return int(result[0]) if result else 0
            except mysql.connector.Error:
                raise

    def finish_run_transaction(
        self,
        run_id: int,
        results,
        errors,
        invoice_count: int,
        tax_invoice_count: int,
        matched_count: int,
        unmatched_count: int,
        error_count: int,
    ) -> bool:
        """Persist a completed run atomically.

        Inserts the run's reconciliation results and errors and flips the run
        status to ``completed`` in a single transaction, so a run is never
        half-persisted or marked completed while its outcomes are incomplete.
        """
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                insert_result = """
                    INSERT INTO reconciliation_results
                        (run_id, account_invoice_id, tax_invoice_id,
                         match_status, discrepancy_amount, notes)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """
                for result in results:
                    cursor.execute(insert_result, (
                        run_id,
                        result.account_invoice_id,
                        result.tax_invoice_id,
                        result.match_status,
                        result.discrepancy_amount,
                        result.notes
                    ))

                insert_error = """
                    INSERT INTO reconciliation_errors
                        (run_id, source_type, entity_id, field,
                         accounting_value, tax_authority_value, difference,
                         error_type, message)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                for error in errors:
                    cursor.execute(insert_error, (
                        run_id,
                        error.source_type,
                        error.entity_id,
                        error.field,
                        error.accounting_value,
                        error.tax_authority_value,
                        error.difference,
                        error.error_type,
                        error.message
                    ))

                update_query = """
                    UPDATE reconciliation_runs
                    SET status = 'completed',
                        invoice_count = %s, tax_invoice_count = %s,
                        matched_count = %s, unmatched_count = %s,
                        error_count = %s, finished_at = NOW(),
                        updated_at = NOW()
                    WHERE id = %s AND status IN ('running', 'pending')
                """
                cursor.execute(update_query, (
                    invoice_count, tax_invoice_count,
                    matched_count, unmatched_count, error_count, run_id
                ))
                conn.commit()
                return cursor.rowcount > 0
            except mysql.connector.Error:
                conn.rollback()
                raise

    def get_results_with_details(self, run_id: int) -> List[dict]:
        """List results for a run, enriched with invoice references."""
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                query = """
                    SELECT r.*,
                           i.invoice_number,
                           i.uuid AS account_uuid,
                           t.uuid AS tax_uuid,
                           t.internal_id AS tax_internal_id
                    FROM reconciliation_results r
                    LEFT JOIN invoices i ON i.id = r.account_invoice_id
                    LEFT JOIN tax_invoices t ON t.id = r.tax_invoice_id
                    WHERE r.run_id = %s
                    ORDER BY r.id
                """
                cursor.execute(query, (run_id,))
                rows = cursor.fetchall()
                n = cursor.column_names.index("invoice_number")
                return [
                    {
                        "id": row[0],
                        "run_id": row[1],
                        "account_invoice_id": row[2],
                        "tax_invoice_id": row[3],
                        "match_status": row[4],
                        "discrepancy_amount": row[5],
                        "notes": row[6],
                        "created_at": row[7].isoformat() if row[7] else None,
                        "account_invoice_number": row[n],
                        "account_uuid": row[n + 1],
                        "tax_uuid": row[n + 2],
                        "tax_internal_id": row[n + 3],
                    }
                    for row in rows
                ]
            except mysql.connector.Error:
                raise

    def get_results_summary(self, run_id: int) -> dict:
        """Count results per match_status for a run in one query."""
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                cursor.execute(
                    """
                    SELECT match_status, COUNT(*)
                    FROM reconciliation_results
                    WHERE run_id = %s
                    GROUP BY match_status
                    """,
                    (run_id,)
                )
                return {row[0]: int(row[1]) for row in cursor.fetchall()}
            except mysql.connector.Error:
                raise

    def add_error(self, error: ReconciliationError) -> ReconciliationError:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                query = """
                    INSERT INTO reconciliation_errors
                        (run_id, source_type, entity_id, field,
                         accounting_value, tax_authority_value, difference,
                         error_type, message)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                cursor.execute(query, (
                    error.run_id,
                    error.source_type,
                    error.entity_id,
                    error.field,
                    error.accounting_value,
                    error.tax_authority_value,
                    error.difference,
                    error.error_type,
                    error.message
                ))
                error.id = cursor.lastrowid
                conn.commit()
                error.created_at = datetime.now()
                return error
            except mysql.connector.Error:
                conn.rollback()
                raise

    def list_errors(self, run_id: int) -> List[ReconciliationError]:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                cursor.execute(
                    "SELECT * FROM reconciliation_errors WHERE run_id = %s ORDER BY id",
                    (run_id,)
                )
                rows = cursor.fetchall()
                return [self._row_to_error(row) for row in rows]
            except mysql.connector.Error:
                raise

    def delete_run(self, run_id: int) -> bool:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                cursor.execute("DELETE FROM reconciliation_runs WHERE id = %s", (run_id,))
                conn.commit()
                return cursor.rowcount > 0
            except mysql.connector.Error:
                conn.rollback()
                raise