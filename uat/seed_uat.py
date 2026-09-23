"""Seed the Phase 15 UAT scratch database with realistic test data.

Everything here targets ONLY the isolated UAT database (``einv_uat_p15``),
never the live ``invoice_system``. It creates two isolated companies,
their users/roles and the application-settings surface, so the UAT harness
can drive the real application over HTTP and verify tenant isolation,
RBAC, imports, reconciliation, emails, audits and settings.

This is UAT tooling, not part of the shipped application.
"""

import os
import sys
from pathlib import Path

import bcrypt
import mysql.connector

DB_NAME = os.environ.get("EINVOICE_UAT_DB", "einv_uat_p15")
DB_HOST = os.environ.get("DB_HOST", "127.0.0.1")
DB_PORT = int(os.environ.get("DB_PORT", "3306"))
DB_USER = os.environ.get("DB_USER", "root")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "abdo2146")

PASSWORD = "UAT-Pass-2026!"

ROLES = [("admin", "Administrator"), ("accountant", "Accountant"),
         ("manager", "Manager"), ("viewer", "Read-only viewer")]

# (username, email, role, first, last, company)
USERS = [
    ("a_admin", "admin.a@uat.test", "admin", "A", "Admin", 1),
    ("a_acc", "acc.a@uat.test", "accountant", "A", "Accountant", 1),
    ("a_mgr", "mgr.a@uat.test", "manager", "A", "Manager", 1),
    ("a_viewer", "viewer.a@uat.test", "viewer", "A", "Viewer", 1),
    ("b_admin", "admin.b@uat.test", "admin", "B", "Admin", 2),
    ("b_mgr", "mgr.b@uat.test", "manager", "B", "Manager", 2),
]

COMPANIES = [
    ("UAT Company A", "UATA" + "1" * 10, "company.a@uat.test",
     "Phone-A", "Address A", "https://a.uat.test"),
    ("UAT Company B", "UATB" + "2" * 10, "company.b@uat.test",
     "Phone-B", "Address B", "https://b.uat.test"),
]


def _hash(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def main() -> None:
    conn = mysql.connector.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD,
        database=DB_NAME, autocommit=False,
    )
    cursor = conn.cursor()

    for name, desc in ROLES:
        cursor.execute(
            "INSERT IGNORE INTO roles (name, description) VALUES (%s, %s)",
            (name, desc),
        )

    for i, (name, trn, email, phone, addr, website) in enumerate(COMPANIES, start=1):
        cursor.execute(
            "INSERT INTO companies (id, name, tax_registration_number, email, "
            "phone, address, website, default_currency, default_tax_rate, "
            "fiscal_year_start) VALUES (%s, %s, %s, %s, %s, %s, %s, 'EGP', 14.00, '01-01') "
            "ON DUPLICATE KEY UPDATE name = VALUES(name)",
            (i, name, trn, email, phone, addr, website),
        )
    conn.commit()

    for username, email, role, first, last, company in USERS:
        cursor.execute(
            "SELECT id FROM users WHERE email = %s", (email,),
        )
        row = cursor.fetchone()
        if row:
            user_id = row[0]
        else:
            cursor.execute(
                "INSERT INTO users (company_id, username, email, password_hash, "
                "first_name, last_name, is_active) VALUES (%s, %s, %s, %s, %s, %s, 1)",
                (company, username, email, _hash(PASSWORD), first, last),
            )
            user_id = cursor.lastrowid
            cursor.execute(
                "INSERT INTO user_roles (user_id, role_id) "
                "SELECT %s, id FROM roles WHERE name = %s",
                (user_id, role),
            )
        conn.commit()

    cursor.execute(
        "SELECT id, name FROM roles ORDER BY id"
    )
    role_ids = dict(cursor.fetchall())
    cursor.execute(
        "SELECT u.id, u.username FROM users u JOIN companies c ON c.id = u.company_id "
        "WHERE u.username IN ('a_admin','a_acc','a_mgr','a_viewer','b_admin','b_mgr') "
        "ORDER BY u.id"
    )
    print("roles:", role_ids)
    print("seeded users:")
    for uid, uname in cursor.fetchall():
        print(f"  {uname}: id={uid}, password={PASSWORD!r}")
    cursor.close()
    conn.close()
    print(f"Seeded {DB_NAME} OK")


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    main()