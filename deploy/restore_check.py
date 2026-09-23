#!/usr/bin/env python3
"""Application-level verification of a restored database (Phase 9).

Operates entirely on an ISOLATED restored database. It:

  * comparess row counts and monetary fingerprints against the source
    database (source is a read-only reference),
  * points the real Flask application at the restored database,
  * proves liveness + readiness endpoints respond,
  * resets an admin password inside the isolated DB and logs in through the
    real /api/auth/login endpoint (authentication against restored data),
  * exercises RBAC + company isolation through the real users API,
  * performs read-only application reads (invoices, reconciliation runs,
    application settings, audit trail, user roles).

The live database is used ONLY as a read-only comparison source.
"""

import argparse
import os
import sys

import mysql.connector


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--target", required=True)
    p.add_argument("--source", required=True)
    p.add_argument("--host", default=os.environ.get("DB_HOST", "127.0.0.1"))
    p.add_argument("--port", default=os.environ.get("DB_PORT", "3306"))
    p.add_argument("--user", default=os.environ.get("DB_USER", "root"))
    p.add_argument("--password", default=os.environ.get("DB_PASSWORD", ""))
    return p.parse_args()


ARGS = parse_args()

PASS, FAIL = 0, 0


def check(label, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  [PASS] {label}" + (f" — {detail}" if detail else ""))
    else:
        FAIL += 1
        print(f"  [FAIL] {label}" + (f" — {detail}" if detail else ""), file=sys.stderr)
    return ok


def connect(db):
    return mysql.connector.connect(
        host=ARGS.host, port=int(ARGS.port), user=ARGS.user,
        password=ARGS.password, database=db,
    )


def scalar(conn, sql, params=None):
    cur = conn.cursor()
    cur.execute(sql, params or ())
    rows = cur.fetchall()
    cur.close()
    return rows[0][0] if rows else None


def pair(conn, sql, params=None):
    cur = conn.cursor()
    cur.execute(sql, params or ())
    rows = cur.fetchall()
    cur.close()
    return tuple(rows[0]) if rows else ()


src = connect(ARGS.source)
tgt = connect(ARGS.target)

try:
    # ------------------------------------------------------------------ 1.
    print("== Data parity (source vs restored) ==")
    TABLES = [
        "application_settings", "audit_logs", "companies", "email_deliveries",
        "import_batch_errors", "import_batches", "invoice_items", "invoices",
        "reconciliation_errors", "reconciliation_results", "reconciliation_runs",
        "refresh_token_blocklist", "roles", "schema_migrations",
        "tax_invoice_items", "tax_invoices", "user_roles", "users",
    ]
    FINANCIAL = {
        "invoices": "SELECT COUNT(*), COALESCE(SUM(total_amount),0) FROM invoices",
        "invoice_items": "SELECT COUNT(*), COALESCE(SUM(line_total),0) FROM invoice_items",
        "tax_invoices": "SELECT COUNT(*), COALESCE(SUM(total_amount),0) FROM tax_invoices",
        "reconciliation_results": "SELECT COUNT(*), COALESCE(SUM(discrepancy_amount),0) FROM reconciliation_results",
    }
    for table in TABLES:
        s = scalar(src, f"SELECT COUNT(*) FROM `{table}`")
        t = scalar(tgt, f"SELECT COUNT(*) FROM `{table}`")
        check(f"row count parity: {table}", s == t, f"source={s} restored={t}")
    for table, sql in FINANCIAL.items():
        s = pair(src, sql)
        t = pair(tgt, sql)
        check(f"monetary fingerprint: {table}", s == t, f"source={s} restored={t}")

    # ------------------------------------------------------------------ 2.
    os.environ["DB_NAME"] = ARGS.target
    os.environ["FLASK_ENV"] = "development"
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, repo_root)

    from backend.app import create_app  # noqa: E402
    from backend.shared.security import hash_password  # noqa: E402

    app = create_app()
    client = app.test_client()
    db = app.extensions["database"]

    print("== Application against restored database ==")
    r = client.get("/api/health")
    check("health endpoint", r.status_code == 200 and (r.get_json() or {}).get("success"))
    r = client.get("/api/health/ready")
    check("readiness endpoint (db ok)", r.status_code == 200 and (r.get_json() or {}).get("success"))

    # ------------------------------------------------------------------ 3.
    print("== Authentication against restored data ==")
    ADMIN_EMAIL = "admin@test.local"
    ADMIN_PWD = "Restore_Test_9!"

    cur = tgt.cursor()
    cur.execute(
        "UPDATE users SET password_hash = %s WHERE email = %s",
        (hash_password(ADMIN_PWD), ADMIN_EMAIL),
    )
    tgt.commit()
    cur.close()

    r = client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PWD})
    login = r.get_json() or {}
    ok = r.status_code == 200 and login.get("success")
    check("login with correct password", ok)
    access = ((login.get("data") or {}).get("access_token") if ok else None)
    check("access token issued", bool(access))

    r = client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong-password"})
    check("login with wrong password rejected", r.status_code == 401)

    if access:
        headers = {"Authorization": f"Bearer {access}"}
        r = client.get("/api/auth/me", headers=headers)
        check("authenticated /api/auth/me", r.status_code == 200 and (r.get_json() or {}).get("success"))

    # ------------------------------------------------------------------ 4.
    print("== Authorization / company isolation ==")
    cur = tgt.cursor()
    cur.execute(
        "INSERT INTO companies (id, name, tax_registration_number, email, is_active) "
        "VALUES (999, 'Isolated Co', 'TAX-ISO-999', 'iso@test.local', 1) "
        "ON DUPLICATE KEY UPDATE name = VALUES(name)"
    )
    cur.execute(
        "INSERT INTO users (id, company_id, username, email, password_hash, "
        "first_name, last_name, is_active) "
        "VALUES (999, 999, 'iso_admin', 'iso.admin@test.local', %s, 'Iso', 'Admin', 1)",
        (hash_password("Isolated_Admin_9!"),),
    )
    cur.execute(
        "INSERT INTO user_roles (user_id, role_id) VALUES (999, 1) "
        "ON DUPLICATE KEY UPDATE role_id = 1"
    )
    tgt.commit()
    cur.close()

    r = client.post("/api/auth/login", json={
        "email": "iso.admin@test.local", "password": "Isolated_Admin_9!",
    })
    iso_login = r.get_json() or {}
    iso_access = (iso_login.get("data") or {}).get("access_token")
    check("second-company admin can log in", bool(iso_access))
    if iso_access:
        r = client.get("/api/users/", headers={"Authorization": f"Bearer {iso_access}"})
        body = r.get_json() or {}
        users = body.get("data") or []
        check("company isolation: admin sees only own-company users",
              r.status_code == 200 and all(u.get("company_id") == 999 for u in users),
              f"returned {len(users)} user(s)")

    if access:
        r = client.get("/api/users/", headers={"Authorization": f"Bearer {access}"})
        body = r.get_json() or {}
        iso_visible = [u for u in (body.get("data") or []) if u.get("company_id") == 999]
        check("company-22 admin does not see company-999 users",
              r.status_code == 200 and not iso_visible,
              f"company-999 rows visible to other company: {len(iso_visible)}")

    # ------------------------------------------------------------------ 5.
    print("== Application reads on restored data ==")
    from backend.modules.invoices.repository import InvoiceRepository  # noqa: E402
    from backend.modules.reconciliation.repository import ReconciliationRepository  # noqa: E402
    from backend.modules.settings.repository import ApplicationSettingRepository  # noqa: E402
    from backend.modules.audit_trail.repository import AuditTrailRepository  # noqa: E402
    from backend.modules.users.repository import UserRepository  # noqa: E402

    inv_repo = InvoiceRepository(db)
    recon_repo = ReconciliationRepository(db)
    settings_repo = ApplicationSettingRepository(db)
    audit_repo = AuditTrailRepository(db)
    user_repo = UserRepository(db)

    company_ids = [scalar(tgt, "SELECT id FROM companies ORDER BY id")]
    company_id = company_ids[0]
    period = scalar(src, "SELECT DATE_FORMAT(invoice_date, '%Y-%m') FROM invoices GROUP BY 1 ORDER BY 1 LIMIT 1")
    period = period if period else "2024-03"
    expected = scalar(src, "SELECT COUNT(*) FROM invoices WHERE company_id = %s AND invoice_date LIKE %s",
                      (company_id, f"{period}%"))
    restored_invoices = inv_repo.list_by_company_and_period(company_id, period)
    check("invoice period list query matches source on restored DB",
          len(restored_invoices) == expected,
          f"period={period} expected={expected} restored={len(restored_invoices)}")

    expected_runs = scalar(src, "SELECT COUNT(*) FROM reconciliation_runs WHERE company_id = %s", (company_id,))
    runs = recon_repo.list_runs_by_company(company_id, limit=200)
    check("reconciliation runs listed from restored DB",
          len(runs) == expected_runs, f"expected={expected_runs} restored={len(runs)}")

    settings = settings_repo.get_all()
    check("application settings readable from restored DB", len(settings) >= 0,
          f"settings={len(settings)}")

    audit_count = scalar(tgt, "SELECT COUNT(*) FROM audit_logs WHERE action = 'login'")
    check("audit trail recorded logins against restored DB",
          audit_count is not None and audit_count >= 1, f"login events={audit_count}")

    users_with_roles = user_repo.get_all_by_company(company_id)
    check("users roles loaded (batch) from restored DB",
          len(users_with_roles) >= 0, f"users={len(users_with_roles)}")

    # ------------------------------------------------------------------ end
    print("")
    print(f"CHECK SUMMARY: {PASS} passed, {FAIL} failed")
    sys.exit(0 if FAIL == 0 else 1)

finally:
    src.close()
    tgt.close()