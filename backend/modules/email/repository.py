"""Email delivery repository for operations on the email_deliveries table."""

from datetime import datetime
from typing import List, Optional

import mysql.connector

from backend.database import Database
from backend.modules.email.model import (
    DELIVERY_FAILED,
    DELIVERY_SENT,
    EmailDelivery,
)
from backend.shared.database import db_cursor


class EmailDeliveryRepository:
    """Repository for one per-taxpayer notification per reconciliation run.

    Only the primary key is used for single-row operations so every method
    stays safe against SQL injection while the company scoping is enforced
    by the service layer before any read or write is attempted.
    """

    def __init__(self, database: Database) -> None:
        self._database = database

    def _row_to_delivery(self, row: tuple) -> EmailDelivery:
        return EmailDelivery(
            id=row[0],
            company_id=row[1],
            run_id=row[2],
            recipient_email=row[3],
            taxpayer_name=row[4],
            taxpayer_tax_id=row[5],
            invoice_count=row[6],
            subject=row[7],
            status=row[8],
            failure_reason=row[9],
            request_id=row[10],
            attempted_at=row[11],
            sent_at=row[12],
            created_at=row[13],
            updated_at=row[14],
        )

    def create(self, delivery: EmailDelivery) -> EmailDelivery:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                query = """
                    INSERT INTO email_deliveries
                        (company_id, run_id, recipient_email, taxpayer_name,
                         taxpayer_tax_id, invoice_count, subject, status,
                         failure_reason, request_id, attempted_at, sent_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                cursor.execute(query, (
                    delivery.company_id,
                    delivery.run_id,
                    delivery.recipient_email,
                    delivery.taxpayer_name,
                    delivery.taxpayer_tax_id,
                    delivery.invoice_count,
                    delivery.subject,
                    delivery.status,
                    delivery.failure_reason,
                    delivery.request_id,
                    delivery.attempted_at,
                    delivery.sent_at,
                ))
                delivery.id = cursor.lastrowid
                conn.commit()
                delivery.created_at = datetime.now()
                delivery.updated_at = datetime.now()
                return delivery
            except mysql.connector.Error:
                conn.rollback()
                raise

    def get_by_id(self, delivery_id: int) -> Optional[EmailDelivery]:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                cursor.execute(
                    "SELECT * FROM email_deliveries WHERE id = %s",
                    (delivery_id,),
                )
                row = cursor.fetchone()
                return self._row_to_delivery(row) if row else None
            except mysql.connector.Error:
                raise

    def list_by_run(self, run_id: int) -> List[EmailDelivery]:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                cursor.execute(
                    """
                    SELECT * FROM email_deliveries
                    WHERE run_id = %s
                    ORDER BY id
                    """,
                    (run_id,),
                )
                return [self._row_to_delivery(row) for row in cursor.fetchall()]
            except mysql.connector.Error:
                raise

    def mark_sent(
        self, delivery_id: int, request_id: Optional[str], subject: str
    ) -> bool:
        """Record a successful send (also used by an explicit resend)."""
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                query = """
                    UPDATE email_deliveries
                    SET status = %s, attempted_at = NOW(), sent_at = NOW(),
                        failure_reason = NULL, request_id = %s,
                        subject = %s, updated_at = NOW()
                    WHERE id = %s
                """
                cursor.execute(query, (
                    DELIVERY_SENT, request_id, subject, delivery_id
                ))
                conn.commit()
                return cursor.rowcount > 0
            except mysql.connector.Error:
                conn.rollback()
                raise

    def mark_failed(self, delivery_id: int, reason: Optional[str]) -> bool:
        """Record a failed send attempt (also used by an explicit resend)."""
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                query = """
                    UPDATE email_deliveries
                    SET status = %s, attempted_at = NOW(), sent_at = NULL,
                        failure_reason = %s, updated_at = NOW()
                    WHERE id = %s
                """
                cursor.execute(query, (DELIVERY_FAILED, reason, delivery_id))
                conn.commit()
                return cursor.rowcount > 0
            except mysql.connector.Error:
                conn.rollback()
                raise


__all__ = ["EmailDeliveryRepository"]