"""Company repository for database operations on the companies table."""

from datetime import datetime
from typing import List, Optional

import mysql.connector

from backend.database import Database
from backend.modules.companies.model import Company
from backend.shared.database import db_cursor


class CompanyRepository:
    """Repository for company database operations.

    Handles all CRUD operations for the companies table using
    parameterized queries and a shared connection pool.
    """

    def __init__(self, database: Database) -> None:
        self._database = database

    def _row_to_company(self, row: tuple) -> Company:
        return Company(
            id=row[0],
            name=row[1],
            tax_registration_number=row[2],
            email=row[3],
            phone=row[4],
            address=row[5],
            is_active=bool(row[6]),
            created_at=row[7],
            updated_at=row[8],
            logo_path=row[9] if len(row) > 9 else None,
            website=row[10] if len(row) > 10 else None,
            default_currency=row[11] if len(row) > 11 else "EGP",
            default_tax_rate=float(row[12]) if len(row) > 12 and row[12] is not None else 0.0,
            fiscal_year_start=row[13] if len(row) > 13 else "01-01",
        )

    def create(self, company: Company) -> Company:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                query = """
                    INSERT INTO companies
                        (name, tax_registration_number, email, phone,
                         address, is_active)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """
                cursor.execute(query, (
                    company.name,
                    company.tax_registration_number,
                    company.email,
                    company.phone,
                    company.address,
                    company.is_active
                ))
                company.id = cursor.lastrowid
                conn.commit()
                company.created_at = datetime.now()
                company.updated_at = datetime.now()
                return company
            except mysql.connector.Error:
                conn.rollback()
                raise

    def get_by_id(self, company_id: int) -> Optional[Company]:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                cursor.execute("SELECT * FROM companies WHERE id = %s", (company_id,))
                row = cursor.fetchone()
                return self._row_to_company(row) if row else None
            except mysql.connector.Error:
                raise

    def get_by_tax_registration_number(self, tax_registration_number: str) -> Optional[Company]:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                query = "SELECT * FROM companies WHERE tax_registration_number = %s"
                cursor.execute(query, (tax_registration_number,))
                row = cursor.fetchone()
                return self._row_to_company(row) if row else None
            except mysql.connector.Error:
                raise

    def exists_by_tax_registration_number(self, tax_registration_number: str) -> bool:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                query = "SELECT COUNT(*) FROM companies WHERE tax_registration_number = %s"
                cursor.execute(query, (tax_registration_number,))
                result = cursor.fetchone()
                return result[0] > 0
            except mysql.connector.Error:
                raise

    def get_all(self, active_only: bool = False) -> List[Company]:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                query = "SELECT * FROM companies"
                if active_only:
                    query += " WHERE is_active = 1"
                query += " ORDER BY name"
                cursor.execute(query)
                rows = cursor.fetchall()
                return [self._row_to_company(row) for row in rows]
            except mysql.connector.Error:
                raise

    def update(self, company: Company) -> Optional[Company]:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                query = """
                    UPDATE companies
                    SET name = %s, tax_registration_number = %s,
                        email = %s, phone = %s, address = %s,
                        is_active = %s, logo_path = %s, website = %s,
                        default_currency = %s, default_tax_rate = %s,
                        fiscal_year_start = %s, updated_at = NOW()
                    WHERE id = %s
                """
                cursor.execute(query, (
                    company.name,
                    company.tax_registration_number,
                    company.email,
                    company.phone,
                    company.address,
                    company.is_active,
                    company.logo_path,
                    company.website,
                    company.default_currency,
                    company.default_tax_rate,
                    company.fiscal_year_start,
                    company.id
                ))
                conn.commit()
                if cursor.rowcount > 0:
                    cursor.execute("SELECT * FROM companies WHERE id = %s", (company.id,))
                    row = cursor.fetchone()
                    if row:
                        return self._row_to_company(row)
                return None
            except mysql.connector.Error:
                conn.rollback()
                raise

    def delete(self, company_id: int) -> bool:
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                cursor.execute("DELETE FROM companies WHERE id = %s", (company_id,))
                conn.commit()
                return cursor.rowcount > 0
            except mysql.connector.Error:
                conn.rollback()
                raise