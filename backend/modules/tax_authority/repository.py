"""Tax authority repository for operations on tax_invoices and tax_invoice_items."""

from datetime import datetime
from typing import List, Optional

import mysql.connector

from backend.database import Database
from backend.modules.tax_authority.model import TaxInvoice, TaxInvoiceItem
from backend.shared.database import db_cursor


class TaxInvoiceRepository:
    """Repository for tax authority E-Invoice operations.

    Handles CRUD for the tax_invoices and tax_invoice_items tables using
    parameterized queries and a shared connection pool.
    """

    def __init__(self, database: Database) -> None:
        self._database = database

    def _row_to_tax_invoice(self, row: tuple) -> TaxInvoice:
        return TaxInvoice(
            id=row[0],
            company_id=row[1],
            account_invoice_id=row[2],
            import_batch_id=row[3],
            uuid=row[4],
            internal_id=row[5],
            document_type=row[6],
            issue_datetime=row[7],
            currency=row[8],
            exchange_rate=row[9],
            seller_name=row[10],
            seller_tax_id=row[11],
            buyer_name=row[12],
            buyer_tax_id=row[13],
            total_sales=row[14],
            total_discount=row[15],
            net_amount=row[16],
            vat_amount=row[17],
            other_charges=row[18],
            total_amount=row[19],
            submission_status=row[20],
            submission_errors=row[21],
            created_at=row[22],
            updated_at=row[23]
        )

    def _row_to_item(self, row: tuple) -> TaxInvoiceItem:
        return TaxInvoiceItem(
            id=row[0],
            tax_invoice_id=row[1],
            description=row[2],
            item_type=row[3],
            quantity=row[4],
            unit_value=row[5],
            vat_rate=row[6],
            vat_amount=row[7],
            discount_amount=row[8],
            total_amount=row[9],
            created_at=row[10]
        )

    def _load_items(self, cursor, tax_invoice_id: int) -> List[TaxInvoiceItem]:
        query = "SELECT * FROM tax_invoice_items WHERE tax_invoice_id = %s ORDER BY id"
        cursor.execute(query, (tax_invoice_id,))
        return [self._row_to_item(row) for row in cursor.fetchall()]

    def create(self, tax_invoice: TaxInvoice) -> TaxInvoice:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                query = """
                    INSERT INTO tax_invoices
                        (company_id, account_invoice_id, import_batch_id,
                         uuid, internal_id, document_type, issue_datetime,
                         currency, exchange_rate, seller_name, seller_tax_id,
                         buyer_name, buyer_tax_id, total_sales,
                         total_discount, net_amount, vat_amount,
                         other_charges, total_amount, submission_status,
                         submission_errors)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                cursor.execute(query, (
                    tax_invoice.company_id,
                    tax_invoice.account_invoice_id,
                    tax_invoice.import_batch_id,
                    tax_invoice.uuid,
                    tax_invoice.internal_id,
                    tax_invoice.document_type,
                    tax_invoice.issue_datetime,
                    tax_invoice.currency,
                    tax_invoice.exchange_rate,
                    tax_invoice.seller_name,
                    tax_invoice.seller_tax_id,
                    tax_invoice.buyer_name,
                    tax_invoice.buyer_tax_id,
                    tax_invoice.total_sales,
                    tax_invoice.total_discount,
                    tax_invoice.net_amount,
                    tax_invoice.vat_amount,
                    tax_invoice.other_charges,
                    tax_invoice.total_amount,
                    tax_invoice.submission_status,
                    tax_invoice.submission_errors
                ))
                tax_invoice.id = cursor.lastrowid

                if tax_invoice.items:
                    item_query = """
                        INSERT INTO tax_invoice_items
                            (tax_invoice_id, description, item_type,
                             quantity, unit_value, vat_rate, vat_amount,
                             discount_amount, total_amount)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """
                    for item in tax_invoice.items:
                        cursor.execute(item_query, (
                            tax_invoice.id,
                            item.description,
                            item.item_type,
                            item.quantity,
                            item.unit_value,
                            item.vat_rate,
                            item.vat_amount,
                            item.discount_amount,
                            item.total_amount
                        ))

                conn.commit()
                tax_invoice.created_at = datetime.now()
                tax_invoice.updated_at = datetime.now()
                return tax_invoice
            except mysql.connector.Error:
                conn.rollback()
                raise

    def get_by_id(self, tax_invoice_id: int) -> Optional[TaxInvoice]:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                cursor.execute("SELECT * FROM tax_invoices WHERE id = %s", (tax_invoice_id,))
                row = cursor.fetchone()
                if not row:
                    return None
                tax_invoice = self._row_to_tax_invoice(row)
                tax_invoice.items = self._load_items(cursor, tax_invoice.id)
                return tax_invoice
            except mysql.connector.Error:
                raise

    def get_by_uuid(self, uuid: str) -> Optional[TaxInvoice]:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                cursor.execute("SELECT * FROM tax_invoices WHERE uuid = %s", (uuid,))
                row = cursor.fetchone()
                if not row:
                    return None
                tax_invoice = self._row_to_tax_invoice(row)
                tax_invoice.items = self._load_items(cursor, tax_invoice.id)
                return tax_invoice
            except mysql.connector.Error:
                raise

    def get_by_company_and_internal_id(self, company_id: int, internal_id: str) -> Optional[TaxInvoice]:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                query = """
                    SELECT * FROM tax_invoices
                    WHERE company_id = %s AND internal_id = %s
                """
                cursor.execute(query, (company_id, internal_id))
                row = cursor.fetchone()
                if not row:
                    return None
                tax_invoice = self._row_to_tax_invoice(row)
                tax_invoice.items = self._load_items(cursor, tax_invoice.id)
                return tax_invoice
            except mysql.connector.Error:
                raise

    def list_by_company(
        self,
        company_id: int,
        limit: int = 100,
        offset: int = 0
    ) -> List[TaxInvoice]:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                query = """
                    SELECT * FROM tax_invoices
                    WHERE company_id = %s
                    ORDER BY issue_datetime DESC, id DESC
                    LIMIT %s OFFSET %s
                """
                cursor.execute(query, (company_id, limit, offset))
                tax_invoices = [self._row_to_tax_invoice(row) for row in cursor.fetchall()]
                for tax_invoice in tax_invoices:
                    tax_invoice.items = self._load_items(cursor, tax_invoice.id)
                return tax_invoices
            except mysql.connector.Error:
                raise

    def list_by_company_and_period(self, company_id: int, period: str) -> List[TaxInvoice]:
        """List tax invoices issued in a 'YYYY-MM' period with items."""
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                query = """
                    SELECT * FROM tax_invoices
                    WHERE company_id = %s AND issue_datetime LIKE %s
                    ORDER BY issue_datetime ASC, id ASC
                """
                cursor.execute(query, (company_id, f"{period}%"))
                tax_invoices = [self._row_to_tax_invoice(row) for row in cursor.fetchall()]
                for tax_invoice in tax_invoices:
                    tax_invoice.items = self._load_items(cursor, tax_invoice.id)
                return tax_invoices
            except mysql.connector.Error:
                raise

    def count_by_company_and_period(self, company_id: int, period: str) -> int:
        """Count tax invoices issued in a 'YYYY-MM' period."""
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                query = """
                    SELECT COUNT(*) FROM tax_invoices
                    WHERE company_id = %s AND issue_datetime LIKE %s
                """
                cursor.execute(query, (company_id, f"{period}%"))
                result = cursor.fetchone()
                return int(result[0]) if result else 0
            except mysql.connector.Error:
                raise

    def update_submission_status(
        self,
        tax_invoice_id: int,
        status: str,
        errors: Optional[str] = None,
        uuid: Optional[str] = None
    ) -> bool:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                query = """
                    UPDATE tax_invoices
                    SET submission_status = %s,
                        submission_errors = %s,
                        uuid = COALESCE(%s, uuid),
                        updated_at = NOW()
                    WHERE id = %s
                """
                cursor.execute(query, (status, errors, uuid, tax_invoice_id))
                conn.commit()
                return cursor.rowcount > 0
            except mysql.connector.Error:
                conn.rollback()
                raise

    def delete(self, tax_invoice_id: int) -> bool:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                cursor.execute("DELETE FROM tax_invoices WHERE id = %s", (tax_invoice_id,))
                conn.commit()
                return cursor.rowcount > 0
            except mysql.connector.Error:
                conn.rollback()
                raise