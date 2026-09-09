"""Invoice repository for database operations on the invoices and invoice_items tables."""

from datetime import datetime
from typing import List, Optional

import mysql.connector

from backend.database import Database
from backend.modules.invoices.model import Invoice, InvoiceItem
from backend.shared.database import db_cursor


class InvoiceRepository:
    """Repository for accounting invoice operations.

    Handles CRUD for the invoices and invoice_items tables using
    parameterized queries and a shared connection pool. Item rows are
    created and loaded together with their parent invoice.
    """

    def __init__(self, database: Database) -> None:
        self._database = database

    def _row_to_invoice(self, row: tuple) -> Invoice:
        return Invoice(
            id=row[0],
            uuid=row[1],
            company_id=row[2],
            import_batch_id=row[3],
            invoice_number=row[4],
            invoice_type=row[5],
            invoice_date=row[6],
            due_date=row[7],
            currency=row[8],
            counterparty_name=row[9],
            counterparty_tax_id=row[10],
            subtotal_amount=row[11],
            discount_amount=row[12],
            vat_amount=row[13],
            total_amount=row[14],
            status=row[15],
            created_at=row[16],
            updated_at=row[17]
        )

    def _row_to_item(self, row: tuple) -> InvoiceItem:
        return InvoiceItem(
            id=row[0],
            invoice_id=row[1],
            description=row[2],
            quantity=row[3],
            unit_price=row[4],
            discount_amount=row[5],
            vat_rate=row[6],
            vat_amount=row[7],
            line_total=row[8],
            created_at=row[9]
        )

    def _load_items(self, cursor, invoice_id: int) -> List[InvoiceItem]:
        query = "SELECT * FROM invoice_items WHERE invoice_id = %s ORDER BY id"
        cursor.execute(query, (invoice_id,))
        return [self._row_to_item(row) for row in cursor.fetchall()]

    def create(self, invoice: Invoice) -> Invoice:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                query = """
                    INSERT INTO invoices
                        (uuid, company_id, import_batch_id, invoice_number,
                         invoice_type, invoice_date, due_date, currency,
                         counterparty_name, counterparty_tax_id,
                         subtotal_amount, discount_amount, vat_amount,
                         total_amount, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                cursor.execute(query, (
                    invoice.uuid,
                    invoice.company_id,
                    invoice.import_batch_id,
                    invoice.invoice_number,
                    invoice.invoice_type,
                    invoice.invoice_date,
                    invoice.due_date,
                    invoice.currency,
                    invoice.counterparty_name,
                    invoice.counterparty_tax_id,
                    invoice.subtotal_amount,
                    invoice.discount_amount,
                    invoice.vat_amount,
                    invoice.total_amount,
                    invoice.status
                ))
                invoice.id = cursor.lastrowid

                if invoice.items:
                    item_query = """
                        INSERT INTO invoice_items
                            (invoice_id, description, quantity, unit_price,
                             discount_amount, vat_rate, vat_amount, line_total)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """
                    for item in invoice.items:
                        cursor.execute(item_query, (
                            invoice.id,
                            item.description,
                            item.quantity,
                            item.unit_price,
                            item.discount_amount,
                            item.vat_rate,
                            item.vat_amount,
                            item.line_total
                        ))

                conn.commit()
                invoice.created_at = datetime.now()
                invoice.updated_at = datetime.now()
                return invoice
            except mysql.connector.Error:
                conn.rollback()
                raise

    def get_by_id(self, invoice_id: int) -> Optional[Invoice]:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                cursor.execute("SELECT * FROM invoices WHERE id = %s", (invoice_id,))
                row = cursor.fetchone()
                if not row:
                    return None
                invoice = self._row_to_invoice(row)
                invoice.items = self._load_items(cursor, invoice.id)
                return invoice
            except mysql.connector.Error:
                raise

    def get_by_uuid(self, company_id: int, uuid: str) -> Optional[Invoice]:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                query = """
                    SELECT * FROM invoices
                    WHERE company_id = %s AND uuid = %s
                """
                cursor.execute(query, (company_id, uuid))
                row = cursor.fetchone()
                if not row:
                    return None
                invoice = self._row_to_invoice(row)
                invoice.items = self._load_items(cursor, invoice.id)
                return invoice
            except mysql.connector.Error:
                raise

    def get_by_company_and_number(self, company_id: int, invoice_number: str) -> Optional[Invoice]:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                query = """
                    SELECT * FROM invoices
                    WHERE company_id = %s AND invoice_number = %s
                """
                cursor.execute(query, (company_id, invoice_number))
                row = cursor.fetchone()
                if not row:
                    return None
                invoice = self._row_to_invoice(row)
                invoice.items = self._load_items(cursor, invoice.id)
                return invoice
            except mysql.connector.Error:
                raise

    def list_by_company(
        self,
        company_id: int,
        limit: int = 100,
        offset: int = 0
    ) -> List[Invoice]:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                query = """
                    SELECT * FROM invoices
                    WHERE company_id = %s
                    ORDER BY invoice_date DESC, id DESC
                    LIMIT %s OFFSET %s
                """
                cursor.execute(query, (company_id, limit, offset))
                invoices = [self._row_to_invoice(row) for row in cursor.fetchall()]
                for invoice in invoices:
                    invoice.items = self._load_items(cursor, invoice.id)
                return invoices
            except mysql.connector.Error:
                raise

    def list_by_company_and_period(self, company_id: int, period: str) -> List[Invoice]:
        """List accounting invoices in a 'YYYY-MM' period with items."""
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                query = """
                    SELECT * FROM invoices
                    WHERE company_id = %s AND invoice_date LIKE %s
                    ORDER BY invoice_date ASC, id ASC
                """
                cursor.execute(query, (company_id, f"{period}%"))
                invoices = [self._row_to_invoice(row) for row in cursor.fetchall()]
                for invoice in invoices:
                    invoice.items = self._load_items(cursor, invoice.id)
                return invoices
            except mysql.connector.Error:
                raise

    def count_by_company_and_period(self, company_id: int, period: str) -> int:
        """Count invoices in a 'YYYY-MM' accounting period.

        The period string is used as a LIKE prefix against invoice_date.
        """
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                query = """
                    SELECT COUNT(*) FROM invoices
                    WHERE company_id = %s AND invoice_date LIKE %s
                """
                cursor.execute(query, (company_id, f"{period}%"))
                result = cursor.fetchone()
                return int(result[0]) if result else 0
            except mysql.connector.Error:
                raise

    def update_status(self, invoice_id: int, status: str) -> bool:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                query = """
                    UPDATE invoices
                    SET status = %s, updated_at = NOW()
                    WHERE id = %s
                """
                cursor.execute(query, (status, invoice_id))
                conn.commit()
                return cursor.rowcount > 0
            except mysql.connector.Error:
                conn.rollback()
                raise

    def delete(self, invoice_id: int) -> bool:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                cursor.execute("DELETE FROM invoices WHERE id = %s", (invoice_id,))
                conn.commit()
                return cursor.rowcount > 0
            except mysql.connector.Error:
                conn.rollback()
                raise