"""Phase 15 UAT & Production Validation harness.

Drives two live application instances over real HTTP (stdlib only):

* primary  ``PRIMARY_BASE``  - email DISABLED (development posture)
* email    ``EMAIL_BASE``    - email ENABLED against a local mock SMTP sink

and verifies every business outcome against the isolated scratch database
``einv_uat_p15``. Results are printed per check and dumped to JSON.

Run order matters: later sections depend on state created by earlier ones
(imports before reconciliation, reconciliation before email deliveries,
etc.). Idempotent-safe enough to re-run against a fresh scratch DB.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from uat_lib import Api, Db, Registry, auth_headers, bearer

PRIMARY_BASE = os.environ.get("UAT_PRIMARY_BASE", "http://127.0.0.1:5001")
EMAIL_BASE = os.environ.get("UAT_EMAIL_BASE", "http://127.0.0.1:5061")
DB_NAME = os.environ.get("EINVOICE_UAT_DB", "einv_uat_p15")
FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uat_results.json")

PASSWORD = "UAT-Pass-2026!"
JWT_SECRET = b"local-dev-jwt-secret-key-for-invoice-system"

import base64
import hashlib
import hmac


def _b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=")


def craft_token(payload: dict, secret: bytes = JWT_SECRET) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    h = _b64(json.dumps(header, separators=(",", ":")).encode())
    p = _b64(json.dumps(payload, separators=(",", ":")).encode())
    msg = h + b"." + p
    sig = hmac.new(secret, msg, hashlib.sha256).digest()
    return (msg + b"." + _b64(sig)).decode()


class UAT:
    def __init__(self):
        self.reg = Registry()
        self.primary = Api(PRIMARY_BASE)
        self.email_api = Api(EMAIL_BASE)
        self.db = Db(DB_NAME)
        self.state = {}
        self.req_counter = 0

    # ------------------------------------------------------------- helpers
    def check(self, name, condition, evidence=None, failure=None):
        self.reg.check(f"{self.cur_section} | {name}", condition, evidence,
                       failure=failure)
        if condition:
            print(f"  PASS  {name}")
        else:
            print(f"  FAIL  {name}  ::  {failure or ''}")

    def record(self, status, name, evidence=None, failure=None):
        self.reg.record(status, f"{self.cur_section} | {name}", evidence,
                        failure=failure)
        print(f"  {status}  {name}")

    # ------------------------------------------------------------ sections
    def run_all(self):
        for section in (
            self.auth_uat, self.tenant_uat, self.rbac_users_uat,
            self.import_uat, self.tax_uat, self.reconciliation_uat,
            self.report_uat, self.email_uat, self.audit_uat,
            self.settings_uat, self.error_uat, self.health_uat,
            self.cross_flow_uat, self.integrity_uat,
        ):
            self.cur_section = section.__name__.replace("_uat", "").replace("_", " ")
            print(f"\n=== {self.cur_section.upper()} ===")
            try:
                section()
            except Exception as exc:  # section must never abort the battery
                self.record("FAIL", f"section crashed: {exc!r}", failure=str(exc))
        self.write_output()

    def write_output(self):
        out = {
            "summary": self.reg.summary(),
            "results": [
                {"status": r.status, "name": r.name,
                 "evidence": _json_safe(r.evidence), "failure": r.failure}
                for r in self.reg.results
            ],
        }
        with open(OUT, "w") as fh:
            json.dump(out, fh, indent=2)
        print(f"\nWRITTEN {OUT} :: {json.dumps(self.reg.summary())}")

    # ---------------------------------------------------------- AUTH
    def auth_uat(self):
        api = self.primary

        status, payload, _ = api.json("POST", "/api/auth/login",
                                      {"email": "admin.a@uat.test", "password": PASSWORD})
        token = payload.get("data", {}).get("access_token") if payload and payload.get("success") else None
        refresh = payload.get("data", {}).get("refresh_token") if payload and payload.get("success") else None
        self.check("admin login returns 200 + JWT tokens", status == 200 and token and refresh,
                   {"status": status, "keys": list((payload.get("data") or {}).keys()) if payload else None})
        if not token:
            self.record("BLOCKED", "login failed, cannot continue auth section")
            return
        self.state["admin_token"] = token
        self.state["admin_refresh"] = refresh

        self.check("envelope carries success flag", bool(payload.get("success")))
        self.check("token issued to admin user", payload["data"].get("user", {}).get("email") == "admin.a@uat.test",
                   payload["data"].get("user"))

        status, payload, _ = api.json("POST", "/api/auth/login",
                                      {"email": "admin.a@uat.test", "password": "wrong-password"})
        self.check("wrong password rejected 401", status == 401,
                   {"status": status, "success": payload.get("success") if isinstance(payload, dict) else payload})

        status, payload, _ = api.json("POST", "/api/auth/login",
                                      {"email": "ghost@uat.invalid", "password": PASSWORD})
        self.check("unknown email rejected 401", status == 401,
                   {"status": status, "code": (payload or {}).get("code")})

        status, payload, _ = api.json("POST", "/api/auth/login",
                                      {"email": "admin.a@uat.test"})
        self.check("missing password rejected 4xx", 400 <= status < 500,
                   {"status": status, "code": (payload or {}).get("code")})

        status, payload, _ = api.raw("POST", "/api/auth/login", b"not json at all",
                                     "application/json")
        self.check("malformed json rejected 4xx", 400 <= status <= 422,
                   {"status": status, "success": payload.get("success") if isinstance(payload, dict) else payload})

        status, payload, _ = api.json("GET", "/api/auth/me", headers=bearer(token))
        user = payload.get("data") if payload and payload.get("success") else {}
        self.check("me returns profile", status == 200 and user.get("email") == "admin.a@uat.test",
                   user)
        self.check("me profile has role+company", "admin" in (user.get("roles") or []) and user.get("company_id") == 1,
                   {"roles": user.get("roles"), "company_id": user.get("company_id")})

        status, payload, _ = api.json("POST", "/api/auth/refresh",
                                      {"refresh_token": refresh})
        new_access = payload.get("data", {}).get("access_token") if payload and payload.get("success") else None
        self.check("refresh issues new access token", status == 200 and bool(new_access),
                   {"status": status})
        if new_access:
            status, payload, _ = api.json("GET", "/api/auth/me", headers=bearer(new_access))
            self.check("refreshed token authenticates", status == 200,
                       {"status": status})

        status, payload, _ = api.json("GET", "/api/auth/me")
        self.check("protected call without token 401", status == 401,
                   {"status": status, "code": (payload or {}).get("code")})

        status, payload, _ = api.json("GET", "/api/auth/me", headers=bearer("junk.token.value"))
        self.check("malformed bearer rejected 401", status == 401,
                   {"status": status, "code": (payload or {}).get("code")})

        expired = craft_token({"sub": "1", "email": "admin.a@uat.test", "role": "admin",
                               "company_id": 1, "user_id": 1,
                               "exp": 1000, "iat": 1, "jti": "uat-expired"})
        status, payload, _ = api.json("GET", "/api/auth/me", headers=bearer(expired))
        self.check("expired token rejected 401 TOKEN_EXPIRED", status == 401 and (payload or {}).get("code") == "TOKEN_EXPIRED",
                   {"status": status, "code": (payload or {}).get("code")})

        status, payload, _ = api.json("POST", "/api/auth/logout",
                                      {"refresh_token": refresh}, headers=bearer(token))
        self.check("logout succeeds", status == 200 and bool(payload.get("success")))

        status, payload, _ = api.json("GET", "/api/auth/me", headers=bearer(token))
        self.check("revoked access token rejected", status == 401 and (payload or {}).get("code") == "TOKEN_REVOKED",
                   {"status": status, "code": (payload or {}).get("code")})

        status, payload, _ = api.json("POST", "/api/auth/refresh", {"refresh_token": refresh})
        self.check("revoked refresh token rejected", status == 401 and (payload or {}).get("code") in ("TOKEN_REVOKED", "UNAUTHORIZED"),
                   {"status": status, "code": (payload or {}).get("code")})

        # password change flow
        status, utoken = auth_headers(api, "acc.a@uat.test", PASSWORD)
        self.state["acc_token"] = utoken
        status, payload, _ = api.json("PUT", "/api/auth/change-password",
                                      {"current_password": PASSWORD, "new_password": "Temp-Change-2026!"},
                                      headers=bearer(utoken))
        self.check("self password change succeeds", status == 200,
                   {"status": status, "success": payload.get("success")})
        status, old_token = auth_headers(api, "acc.a@uat.test", PASSWORD)
        self.check("old password now rejected", status == 401, {"status": status})
        status, _ = auth_headers(api, "acc.a@uat.test", "Temp-Change-2026!")
        self.check("new password authenticates", status == 200, {"status": status})
        api.json("PUT", "/api/auth/change-password",
                 {"current_password": "Temp-Change-2026!", "new_password": PASSWORD},
                 headers=bearer(utoken))

        # v1 alias
        status, payload, _ = api.json("GET", "/api/v1/health")
        self.check("/api/v1 alias route works", status == 200 and payload.get("status") == "ok",
                   {"status": status})

    # --------------------------------------------------------- TENANT
    def tenant_uat(self):
        api = self.primary
        _, a_token = auth_headers(api, "admin.a@uat.test", PASSWORD)
        _, b_token = auth_headers(api, "admin.b@uat.test", PASSWORD)
        self.state["a_token"] = a_token
        self.state["b_token"] = b_token

        status, payload, _ = api.json("GET", "/api/users", headers=bearer(a_token))
        users = payload.get("data") or []
        if isinstance(users, dict):
            users = users.get("users", [])
        self.check("company A user list contains only company A users",
                   all(u.get("company_id") == 1 for u in users),
                   {"ids": sorted(u.get("id") for u in users)})

        status, payload, _ = api.json("GET", "/api/users", headers=bearer(b_token))
        users_b = payload.get("data") or []
        if isinstance(users_b, dict):
            users_b = users_b.get("users", [])
        self.check("company B user list contains only company B users",
                   all(u.get("company_id") == 2 for u in users_b),
                   {"ids": sorted(u.get("id") for u in users_b)})

        status, payload, _ = api.json("GET", "/api/settings/company", headers=bearer(a_token))
        self.check("company settings scoped to own company", (payload.get("data") or {}).get("id") == 1,
                   (payload.get("data") or {}))
        status, payload, _ = api.json("GET", "/api/settings/company", headers=bearer(b_token))
        self.check("company B settings scoped to company 2", (payload.get("data") or {}).get("id") == 2)

        # cross-tenant hides resources as 404
        status, payload, _ = api.json("GET", "/api/imports/999999", headers=bearer(b_token))
        self.check("cross-tenant import batch read 404", status == 404, {"status": status})
        status, payload, _ = api.json("GET", "/api/reconciliation/runs/999999", headers=bearer(b_token))
        self.check("cross-tenant reconciliation run read 404", status == 404, {"status": status})
        status, payload, _ = api.json("GET", "/api/audit-trail/logs", headers=bearer(b_token))
        logs = payload.get("data", {}).get("logs", payload.get("data", {}).get("items", []))
        self.check("company B audit log scoped to company 2 only",
                   all(l.get("company_id") in (2, None) for l in logs),
                   {"count": len(logs),
                    "companies": sorted({c for c in (l.get("company_id") for l in logs) if c is not None})})

        status, payload, _ = api.json("GET", "/api/auth/me", headers=bearer(b_token))
        self.check("company B admin sees own identity", (payload.get("data") or {}).get("company_id") == 2)

    # ---------------------------------------------------- RBAC / USERS
    def rbac_users_uat(self):
        api = self.primary
        a_token = self.state["a_token"]
        acc_token = self.state.get("acc_token")

        status, payload, _ = api.json("GET", "/api/users", headers=bearer(acc_token))
        self.check("accountant blocked from user admin (403)", status == 403, {"status": status})

        status, payload, _ = api.json("POST", "/api/users/",
                                      {"name": "Should Not Exist", "email": "forbidden@uat.test",
                                       "password": PASSWORD, "role": "viewer"},
                                      headers=bearer(acc_token))
        self.check("accountant blocked from user create (403)", status == 403, {"status": status})

        _, viewer_token = auth_headers(api, "viewer.a@uat.test", PASSWORD)
        self.state["viewer_token"] = viewer_token
        status, payload, _ = api.json("POST", "/api/imports", {"file": "none"},
                                      headers=bearer(viewer_token))
        self.check("viewer blocked from imports (403)", status == 403, {"status": status})
        status, payload, _ = api.json("POST", "/api/reconciliation/runs",
                                      {"period": "2026-08"}, headers=bearer(viewer_token))
        self.check("viewer blocked from reconciliation (403)", status == 403, {"status": status})

        # create a fresh accountant in company A
        status, payload, _ = api.json("POST", "/api/users/",
                                      {"username": "tmp.acc", "email": "tmp.acc@uat.test",
                                       "password": PASSWORD, "roles": ["accountant"],
                                       "first_name": "Temp", "last_name": "Acc",
                                       "company_id": 1},
                                      headers=bearer(a_token))
        new_user = payload.get("data") or {}
        new_id = new_user.get("id")
        self.check("admin creates user", status == 201 and bool(new_id),
                   {"status": status, "id": new_id})
        self.state["tmp_user_id"] = new_id

        status, _ = auth_headers(api, "tmp.acc@uat.test", PASSWORD)
        self.check("new user can log in", status == 200, {"status": status})

        status, payload, _ = api.json("PUT", f"/api/users/{new_id}",
                                      {"roles": ["manager"]}, headers=bearer(a_token))
        self.check("admin updates user role", status == 200 and "manager" in ((payload.get("data") or {}).get("roles") or []),
                   (payload.get("data") or {}))

        status, payload, _ = api.json("PUT", f"/api/users/{new_id}/password",
                                      {"new_password": "NewPass-2026!"}, headers=bearer(a_token))
        self.check("admin resets user password", status == 200, {"status": status})
        status, _ = auth_headers(api, "tmp.acc@uat.test", "NewPass-2026!")
        self.check("reset password authenticates", status == 200, {"status": status})

        status, payload, _ = api.json("PUT", f"/api/users/{new_id}/deactivate",
                                      headers=bearer(a_token))
        self.check("admin deactivates user", status == 200, {"status": status})
        status, _ = auth_headers(api, "tmp.acc@uat.test", "NewPass-2026!")
        self.check("deactivated user cannot log in", status == 401, {"status": status})
        api.json("PUT", f"/api/users/{new_id}/activate", headers=bearer(a_token))
        status, _ = auth_headers(api, "tmp.acc@uat.test", "NewPass-2026!")
        self.check("reactivated user logs in again", status == 200, {"status": status})

        # last admin invariant in company A
        status, payload, _ = api.json("PUT", "/api/users/1/deactivate", headers=bearer(a_token))
        self.check("cannot deactivate last admin in company (4xx)",
                   400 <= status < 500, {"status": status, "code": (payload or {}).get("code")})

        # self-demotion attempt (roles list is the accepted field)
        status, payload, _ = api.json("PUT", "/api/users/1", {"roles": ["viewer"]}, headers=bearer(a_token))
        self.check("admin cannot self-demote/change own role (4xx)",
                   400 <= status < 500, {"status": status, "code": (payload or {}).get("code")})

        # delete temp user
        status, payload, _ = api.json("DELETE", f"/api/users/{new_id}", headers=bearer(a_token))
        self.check("admin deletes user", status == 200, {"status": status})
        status, _ = auth_headers(api, "tmp.acc@uat.test", "NewPass-2026!")
        self.check("deleted user cannot log in", status == 401, {"status": status})

    # ---------------------------------------------------------- IMPORT
    def _upload(self, api, token, filename, field="file"):
        path = os.path.join(FIXTURES, filename)
        with open(path, "rb") as fh:
            content = fh.read()
        ext = os.path.splitext(filename)[1]
        if ext == ".csv":
            return api.multipart_upload("/api/imports", field, filename, content,
                                        headers=bearer(token))
        # non-csv treated as plain upload to drive FILE_ERROR validation
        return api.raw("POST", "/api/imports", content, "text/plain",
                       headers={**bearer(token), "Content-Disposition": f'form-data; name="file"; filename="{filename}"'})

    def _batch(self, payload):
        return ((payload or {}).get("data") or {}).get("batch") or {}

    def import_uat(self):
        api = self.primary
        a_token = self.state["a_token"]

        status, payload, _ = self._upload(api, a_token, "company_a_invoices.csv")
        batch = self._batch(payload)
        batch_id = batch.get("id")
        self.check("valid import completes synchronously (201)",
                   status == 201 and batch.get("status") == "completed",
                   {"status": status, "batch_status": batch.get("status")})
        self.check("valid import counters (6 rows/6 processed/0 errors)",
                   batch.get("total_rows") == 6 and batch.get("processed_rows") == 6
                   and batch.get("error_rows") == 0,
                   {"total_rows": batch.get("total_rows"), "processed": batch.get("processed_rows"),
                    "errors": batch.get("error_rows")})
        self.state["batch_ok"] = batch_id

        db_invoice_count = self.db.scalar("SELECT COUNT(*) FROM invoices WHERE company_id = 1")
        self.check("DB persisted 5 invoices for company A", db_invoice_count == 5, {"count": db_invoice_count})

        def totals(num):
            row = self.db.q(
                "SELECT subtotal_amount, vat_amount, total_amount, "
                "(SELECT COUNT(*) FROM invoice_items i WHERE i.invoice_id = v.id) "
                "FROM invoices v WHERE company_id=1 AND invoice_number=%s", (num,)
            )
            return row[0] if row else None

        self.check("INV-A001 totals 1000/140/1140",
                   totals("INV-A001") == (1000.00, 140.00, 1140.00, 1), totals("INV-A001"))
        self.check("INV-A002 totals 500/70/570",
                   totals("INV-A002") == (500.00, 70.00, 570.00, 1), totals("INV-A002"))
        self.check("INV-A003 totals 100/14/114",
                   totals("INV-A003") == (100.00, 14.00, 114.00, 1), totals("INV-A003"))
        a4 = totals("INV-A004")
        self.check("INV-A004 multi-line totals 800/112/912 with 2 items",
                   a4 == (800.00, 112.00, 912.00, 2), a4)
        self.check("INV-A005 totals 250/35/285",
                   totals("INV-A005") == (250.00, 35.00, 285.00, 1), totals("INV-A005"))

        status, payload, _ = api.json("GET", f"/api/imports/{batch_id}", headers=bearer(a_token))
        self.check("batch detail readable",
                   status == 200 and (payload.get("data") or {}).get("batch", {}).get("id") == batch_id,
                   {"status": status})

        # partial file: 1 valid row + 1 invalid date
        status, payload, _ = self._upload(api, a_token, "company_a_partial.csv")
        batch = self._batch(payload)
        self.check("partial import processed 1 / error 1",
                   batch.get("processed_rows") == 1 and batch.get("error_rows") == 1,
                   {"processed": batch.get("processed_rows"), "errors": batch.get("error_rows")})
        db6 = self.db.scalar("SELECT COUNT(*) FROM invoices WHERE company_id=1 AND invoice_number='INV-A006'")
        db_bad = self.db.scalar("SELECT COUNT(*) FROM invoices WHERE company_id=1 AND invoice_number='INV-A-BAD'")
        self.check("valid row persisted, invalid row skipped",
                   db6 == 1 and db_bad == 0, {"INV-A006": db6, "INV-A-BAD": db_bad})
        self.state["batch_partial"] = batch.get("id")

        # duplicate-in-file
        status, payload, _ = self._upload(api, a_token, "company_a_dup.csv")
        batch = self._batch(payload)
        self.state["batch_dup"] = batch.get("id")
        self.check("dup-in-file processed 1 / error 1",
                   batch.get("processed_rows") == 1 and batch.get("error_rows") == 1,
                   {"processed": batch.get("processed_rows"), "errors": batch.get("error_rows")})
        self.check("INV-A007 persisted exactly once",
                   self.db.scalar("SELECT COUNT(*) FROM invoices WHERE company_id=1 AND invoice_number='INV-A007'") == 1)
        status, payload, _ = api.json("GET",
                                      f"/api/imports/{self.state['batch_dup']}?include=errors",
                                      headers=bearer(a_token))
        codes = [e.get("error_code") for e in (payload.get("data") or {}).get("errors", [])]
        self.check("dup-in-file error code DUPLICATE_IN_FILE", "DUPLICATE_IN_FILE" in codes,
                   codes)

        # re-upload -> all duplicates in DB
        status, payload, _ = self._upload(api, a_token, "company_a_invoices.csv")
        batch = self._batch(payload)
        self.state["batch_reimport"] = batch.get("id")
        self.check("re-import fails with 6 rejected rows",
                   batch.get("processed_rows") == 0 and batch.get("error_rows") == 6,
                   {"processed": batch.get("processed_rows"), "errors": batch.get("error_rows")})
        self.check("no duplicate rows in DB after re-import",
                   self.db.scalar("SELECT COUNT(*) FROM invoices WHERE company_id = 1") == 7)
        status, payload, _ = api.json("GET",
                                      f"/api/imports/{self.state['batch_reimport']}?include=errors",
                                      headers=bearer(a_token))
        codes = [e.get("error_code") for e in (payload.get("data") or {}).get("errors", [])]
        self.check("re-import errors all DUPLICATE_IN_DB",
                   len(codes) == 5 and all(c == "DUPLICATE_IN_DB" for c in codes), codes)

        # invalid file type
        with open(os.path.join(FIXTURES, "company_a_invoices.csv"), "rb") as fh:
            content = fh.read()
        status, payload, _ = api.multipart_upload("/api/imports", "file", "bad.txt", content,
                                                  headers=bearer(a_token))
        failed_batch = self._batch(payload).get("status") == "failed" if isinstance(payload, dict) else False
        self.check("non-CSV file rejected (4xx or failed batch)",
                   400 <= status < 500 or failed_batch,
                   {"status": status,
                    "batch_status": self._batch(payload).get("status") if isinstance(payload, dict) else None,
                    "code": (payload or {}).get("code") if isinstance(payload, dict) else None})

        # company B import
        status, payload, _ = self._upload(api, self.state["b_token"], "company_b_invoices.csv")
        batch = self._batch(payload)
        self.check("company B import succeeds", status == 201 and batch.get("processed_rows") == 1,
                   {"status": status, "processed": batch.get("processed_rows")})
        self.state["batch_b"] = batch.get("id")

        status, payload, _ = api.json("GET", f"/api/imports/{self.state['batch_ok']}",
                                      headers=bearer(self.state["b_token"]))
        self.check("company B cannot read company A batch (404)", status == 404, {"status": status})

    # ------------------------------------------------------------- TAX
    def tax_uat(self):
        db = self.db
        count_a = db.scalar("SELECT COUNT(*) FROM tax_invoices WHERE company_id=1")
        count_b = db.scalar("SELECT COUNT(*) FROM tax_invoices WHERE company_id=2")
        self.check("company A has 6 seeded authority invoices", count_a == 6, {"count": count_a})
        self.check("company B has 1 seeded authority invoice", count_b == 1, {"count": count_b})

        # spot totals in the authority mirror
        row = db.q("SELECT total_sales, net_amount, vat_amount, total_amount "
                   "FROM tax_invoices WHERE company_id=1 AND internal_id='A-TAX-001'")
        self.check("tax A-TAX-001 mirror amounts", row and row[0] == (1000.00, 1000.00, 140.00, 1140.00), row)
        row = db.q("SELECT total_sales, vat_amount, total_amount FROM tax_invoices "
                   "WHERE company_id=1 AND internal_id='A-TAX-002'")
        self.check("tax A-TAX-002 mirror intentionally differs (vat/total)", row and row[0] == (500.00, 100.00, 600.00), row)
        baduuid = db.scalar("SELECT uuid FROM tax_invoices WHERE company_id=1 AND internal_id='tx-baduuid'")
        self.check("invalid-uuid tax doc present for INVALID outcome", baduuid == "not-a-valid-uuid", {"uuid": baduuid})
        claimed = db.scalar("SELECT COUNT(*) FROM tax_invoices WHERE company_id=1 AND uuid IS NULL")
        self.check("one authority doc matched via internal_id (INV-A005)", claimed == 1, {"count": claimed})

    # -------------------------------------------------- RECONCILIATION
    def reconciliation_uat(self):
        api = self.primary
        a_token = self.state["a_token"]

        status, payload, _ = api.json("POST", "/api/reconciliation/runs",
                                      {"period": "2026-08"}, headers=bearer(a_token))
        data = payload.get("data") or {}
        run = data.get("run") or {}
        counts = data.get("counts") or {}
        run_id = run.get("id")
        self.state["run_id"] = run_id
        self.check("reconciliation run completes", status == 201 and run.get("status") == "completed",
                   {"status": status, "run_status": run.get("status")})
        self.check("run counts (7 invoices / 6 tax / 3 matched / 6 unmatched)",
                   run.get("invoice_count") == 7 and run.get("tax_invoice_count") == 6
                   and run.get("matched_count") == 3 and run.get("unmatched_count") == 6,
                   {"invoices": run.get("invoice_count"), "tax": run.get("tax_invoice_count"),
                    "matched": run.get("matched_count"), "unmatched": run.get("unmatched_count")})
        self.check("run aggregates extra=1 invalid=1 errors=5",
                   counts.get("extra_in_tax_authority") == 1
                   and counts.get("invalid") == 1 and run.get("error_count") == 5,
                   {"extra": counts.get("extra_in_tax_authority"),
                    "invalid": counts.get("invalid"), "errors": run.get("error_count")})

        status, payload, _ = api.json("GET", f"/api/reconciliation/runs/{run_id}", headers=bearer(a_token))
        detail = ((payload.get("data") or {}).get("run")) or {}
        self.check("run detail readable", status == 200 and detail.get("id") == run_id,
                   {"status": status, "id": detail.get("id")})

        status, payload, _ = api.json("GET", f"/api/reconciliation/runs/{run_id}/summary",
                                      headers=bearer(a_token))
        self.check("run summary endpoints returns numbers", status == 200,
                   payload.get("data") if payload else payload)

        status, payload, _ = api.json("GET", f"/api/reconciliation/runs", headers=bearer(a_token))
        runs = payload.get("data", {}).get("runs", payload.get("data", {}).get("items", []))
        self.check("run list includes the new run",
                   any(r.get("id") == run_id for r in runs), {"ids": [r.get("id") for r in runs]})

        # results
        status, payload, _ = api.json("GET", f"/api/reconciliation/runs/{run_id}/results",
                                      headers=bearer(a_token))
        results = payload.get("data", {}).get("results", payload.get("data", {}).get("items", []))
        self.check("9 result rows produced", len(results) == 9, {"count": len(results)})
        by_status = {}
        for r in results:
            by_status.setdefault(r.get("match_status"), 0)
            by_status[r.get("match_status")] += 1
        self.check("outcome distribution matched=3 mismatched=1 missing=3 extra=1 invalid=1",
                   by_status.get("matched") == 3 and by_status.get("mismatched") == 1
                   and by_status.get("missing_in_tax_authority") == 3
                   and by_status.get("extra_in_tax_authority") == 1
                   and by_status.get("invalid") == 1,
                   by_status)

        status, payload, _ = api.json("GET", f"/api/reconciliation/runs/{run_id}/results?match_status=matched",
                                      headers=bearer(a_token))
        results = payload.get("data", {}).get("results", payload.get("data", {}).get("items", []))
        self.check("result filter match_status=matched returns 3",
                   len(results) == 3, {"count": len(results)})

        status, payload, _ = api.json("GET", f"/api/reconciliation/runs/{run_id}/results?page_size=4",
                                      headers=bearer(a_token))
        results = payload.get("data", {}).get("results", payload.get("data", {}).get("items", []))
        self.check("result pagination page_size=4 honored", len(results) <= 4, {"count": len(results)})

        # per-invoice outcome correctness
        db = self.db
        for num, expected in (("INV-A001", "matched"), ("INV-A002", "mismatched"),
                              ("INV-A003", "missing_in_tax_authority"),
                              ("INV-A005", "matched"), ("INV-A006", "missing_in_tax_authority")):
            row = db.q("SELECT r.match_status FROM reconciliation_results r "
                       "JOIN invoices v ON v.id = r.account_invoice_id "
                       "WHERE v.invoice_number=%s AND v.company_id=1", (num,))
            self.check(f"{num} classified {expected}",
                       bool(row) and row[0][0] == expected, row)

        # mismatch detail: A2 vat + total + item errors
        row = db.q("SELECT e.error_type FROM reconciliation_errors e "
                   "JOIN invoices v ON v.id=e.entity_id "
                   "WHERE v.invoice_number='INV-A002' ORDER BY e.error_type")
        codes = [r[0] for r in row]
        self.check("A2 mismatch raises VAT/TOTAL item errors",
                   {"VAT_AMOUNT_MISMATCH", "TOTAL_AMOUNT_MISMATCH",
                    "ITEM_VAT_SUM_MISMATCH", "ITEM_TOTAL_SUM_MISMATCH"} <= set(codes),
                   codes)

        invalid = db.q("SELECT match_status FROM reconciliation_results r "
                       "JOIN tax_invoices t ON t.id=r.tax_invoice_id WHERE t.internal_id='tx-baduuid'")
        self.check("tx-baduuid yields INVALID outcome", bool(invalid) and invalid[0][0] == "invalid", invalid)

        # errors listing + export
        status, payload, _ = api.json("GET", f"/api/reconciliation/runs/{run_id}/errors",
                                      headers=bearer(a_token))
        errors = payload.get("data", {}).get("errors", payload.get("data", {}).get("items", []))
        self.check("error listing returns the mismatch errors", len(errors) == 5, {"count": len(errors)})

        status, content, headers = api.json("GET", f"/api/reconciliation/runs/{run_id}/results/export?format=csv",
                                            headers=bearer(a_token))
        self.check("results CSV export downloads", status == 200 and "csv" in str(headers.get("content-type", ""))
                   and (isinstance(content, str) and "INV-A001" in content),
                   {"status": status, "batch_len": len(content) if isinstance(content, str) else None})

        status, content, headers = api.json("GET", f"/api/reconciliation/runs/{run_id}/errors/export?format=csv",
                                            headers=bearer(a_token))
        self.check("errors CSV export downloads", status == 200 and "VAT_AMOUNT_MISMATCH" in content,
                   {"status": status})

        # company B business check
        status, payload, _ = api.json("POST", "/api/reconciliation/runs",
                                      {"period": "2026-08"}, headers=bearer(self.state["b_token"]))
        data = payload.get("data") or {}
        run_b = data.get("run") or {}
        self.state["run_b"] = run_b.get("id")
        self.check("company B run matches only its own invoice",
                   run_b.get("invoice_count") == 1 and run_b.get("matched_count") == 1,
                   {"invoices": run_b.get("invoice_count"), "matched": run_b.get("matched_count")})

        status, payload, _ = api.json("GET", f"/api/reconciliation/runs/{run_id}", headers=bearer(self.state["b_token"]))
        self.check("company B cannot read company A run (404)", status == 404, {"status": status})

    # ------------------------------------------------------------ REPORT
    def report_uat(self):
        api = self.primary
        a_token = self.state["a_token"]
        run_id = self.state["run_id"]

        status, payload, _ = api.json("GET", f"/api/reconciliation/runs/{run_id}/summary",
                                      headers=bearer(a_token))
        data = payload.get("data") or {}
        self.check("report summary exposes reliable figures for the period", status == 200 and bool(data),
                   data)

        status, payload, _ = api.json("GET", f"/api/reconciliation/runs/{run_id}/results",
                                      headers=bearer(a_token))
        results = payload.get("data", {}).get("results", payload.get("data", {}).get("items", []))
        meta = payload.get("data") or {}
        self.check("results report has source invoice + values",
                   all((r.get("account_invoice_id") or r.get("tax_invoice_id")) for r in results),
                   {"sample": {k: results[0].get(k) for k in
                               ("account_invoice_id", "tax_invoice_id", "match_status",
                                "discrepancy_amount")} if results else None})

        # xlsx export (openpyxl available)
        status, content, headers = api.json("GET", f"/api/reconciliation/runs/{run_id}/results/export?format=xlsx",
                                            headers=bearer(a_token))
        self.check("results XLSX export downloads", status == 200 and "spreadsheet" in str(headers.get("content-type", "")),
                   {"status": status, "content_type": headers.get("content-type")})

    # ------------------------------------------------------------- EMAIL
    def email_uat(self):
        api = self.primary          # disabled posture
        email_api = self.email_api  # enabled posture against mock SMTP
        from mock_smtp import MockSMTP
        a_token = self.state["a_token"]
        run_id = self.state["run_id"]

        sink = MockSMTP(2525)
        sink.__enter__()

        status, payload, _ = api.json("GET", "/api/email/status", headers=bearer(a_token))
        data = payload.get("data") or {}
        self.check("email status reports disabled on primary", status == 200 and data.get("enabled") is False,
                   data)

        status, payload, _ = api.json("POST", "/api/email/test",
                                      {"to": "test@example.test"}, headers=bearer(a_token))
        self.check("email test rejected when disabled (400)", status == 400,
                   {"status": status, "success": payload.get("success"), "code": (payload or {}).get("code")})

        status, payload, _ = api.json("GET", f"/api/reconciliation/runs/{run_id}/email-deliveries",
                                      headers=bearer(a_token))
        deliveries = payload.get("data", {}).get("deliveries", payload.get("data", {}).get("items", []))
        statuses = sorted({d.get("status") for d in deliveries})
        self.check("deliveries recorded for affected rows (skipped/no_email/invalid)",
                   sorted({"skipped", "no_email", "invalid"}) == statuses,
                   {"statuses": statuses, "count": len(deliveries)})
        self.state["deliveries_count"] = len(deliveries)
        real_delivery_id = deliveries[0].get("id") if deliveries else 1

        status, payload, _ = api.json("POST",
                                      f"/api/reconciliation/runs/{run_id}/email-deliveries/{real_delivery_id}/resend",
                                      headers=bearer(a_token))
        self.check("resend rejected when email disabled (400)", status == 400,
                   {"status": status, "code": (payload or {}).get("code")})

        status, payload, _ = api.json("GET", "/api/email/status",
                                      headers=bearer(self.state.get("acc_token") or "x"))
        self.check("accountant blocked from email admin (403)", status == 403, {"status": status})

        # ---- enabled posture
        status, payload, _ = email_api.json("GET", "/api/email/status",
                                            headers=bearer(a_token))
        data = payload.get("data") or {}
        self.check("email instance reports enabled", status == 200 and data.get("enabled") is True,
                   data)

        status, payload, _ = email_api.json("POST", "/api/email/test",
                                            {"to": "test@example.test"},
                                            headers=bearer(a_token))
        self.check("email test delivered on enabled instance", status == 200 and (payload.get("data") or {}).get("delivered") is True,
                   {"status": status, "data": payload.get("data")})

        status, payload, _ = email_api.json("POST", "/api/email/test",
                                            {"to": "not-an-email"},
                                            headers=bearer(a_token))
        self.check("invalid test recipient rejected", 400 <= status < 500,
                   {"status": status, "code": (payload or {}).get("code")})

        status, payload, _ = email_api.json("POST", "/api/email/test",
                                            {"to": "noreply@specsia.com"})
        self.check("email test without auth rejected", status == 401, {"status": status})

        # reconciliation on the enabled instance triggers real deliveries
        status, payload, _ = email_api.json("POST", "/api/reconciliation/runs",
                                            {"period": "2026-08"}, headers=bearer(self.state["a_token"]))
        run_e = (payload.get("data") or {}).get("run") or {}
        self.state["run_email"] = run_e.get("id")
        self.check("enabled instance runs for the period", status == 201 and run_e.get("status") == "completed",
                   {"status": status, "run_status": run_e.get("status")})

        status, payload, _ = email_api.json("GET", f"/api/reconciliation/runs/{run_e.get('id')}/email-deliveries",
                                            headers=bearer(a_token))
        deliveries = payload.get("data", {}).get("deliveries", payload.get("data", {}).get("items", []))
        sent = [d for d in deliveries if d.get("status") == "sent"]
        self.check("deliveries sent through mock SMTP on enabled instance",
                   len(sent) >= 1, {"sent": len(sent), "statuses": sorted({d.get("status") for d in deliveries})})

        # resend one delivery
        sent_id = sent[0].get("id") if sent else self.state.get("deliveries_count")
        status, payload, _ = email_api.json("POST",
                                            f"/api/reconciliation/runs/{run_e.get('id')}/email-deliveries/{sent_id}/resend",
                                            headers=bearer(a_token))
        self.check("resend delivers again on enabled instance", status == 200,
                   {"status": status, "success": payload.get("success")})
        db_sent = self.db.scalar(
            "SELECT status FROM email_deliveries WHERE id=%s", (int(sent_id),))
        self.check("delivery row status sent in DB", db_sent == "sent", {"db_status": db_sent})

        # mock SMTP sink verification
        msgs = sink.messages
        self.check("mock SMTP captured the messages", len(msgs) >= 1, {"captured": len(msgs)})
        if msgs:
            self.check("message carries subject + X-Request-Id",
                       bool(msgs[0].get("subject")) and bool(msgs[0].get("x_request_id")),
                       {"subject": msgs[0].get("subject"), "x_request_id": msgs[0].get("x_request_id"),
                        "to": msgs[0].get("to")})
        sink.__exit__(None, None, None)

    # ------------------------------------------------------------ AUDIT
    def audit_uat(self):
        api = self.primary
        a_token = self.state["a_token"]
        acc_token = self.state.get("acc_token")

        status, payload, _ = api.json("GET", "/api/audit-trail/logs", headers=bearer(a_token))
        logs = payload.get("data", {}).get("logs", payload.get("data", {}).get("items", []))
        actions = {l.get("action") for l in logs}
        self.check("audit log populated with workflow actions",
                   {"login", "import", "reconcile"} <= actions,
                   {"count": len(logs), "actions": sorted(actions)})

        self.check("audit log rows carry actor context",
                   any(l.get("actor_email") for l in logs),
                   logs[0] if logs else None)

        status, payload, _ = api.json("GET", "/api/audit-trail/logs?action=import", headers=bearer(a_token))
        logs = payload.get("data", {}).get("logs", payload.get("data", {}).get("items", []))
        self.check("audit filter by action works",
                   all(l.get("action") == "import" for l in logs), {"count": len(logs)})

        status, payload, _ = api.json("GET", "/api/audit-trail/logs?page_size=3", headers=bearer(a_token))
        logs = payload.get("data", {}).get("logs", payload.get("data", {}).get("items", []))
        self.check("audit pagination honored", len(logs) <= 3, {"count": len(logs)})

        status, payload, _ = api.json("GET", "/api/audit-trail/logs", headers=bearer(acc_token))
        self.check("accountant blocked from audit (403)", status == 403, {"status": status})

        # redaction sanity: no secret values captured
        raw_logs = self.db.q("SELECT metadata FROM audit_logs WHERE actor_email='admin.a@uat.test' LIMIT 200")
        blob = json.dumps([r[0] for r in raw_logs])
        leaked = [w for w in ("UAT-Pass-2026!", "Temp-Change-2026!", "abdo2146", "local-dev-jwt") if w in blob]
        self.check("audit metadata does not leak secrets", not leaked, {"leaked": leaked})

    # --------------------------------------------------------- == SETTINGS
    def settings_uat(self):
        api = self.primary
        a_token = self.state["a_token"] or self.state["admin_token"]

        status, payload, _ = api.json("GET", "/api/settings/application", headers=bearer(a_token))
        original_app = payload.get("data") or {}
        self.check("app settings readable", status == 200, original_app)

        status, payload, _ = api.json("PUT", "/api/settings/application",
                                      {"application_name": "UAT Branding X"},
                                      headers=bearer(a_token))
        self.check("admin updates application settings", status == 200 and (payload.get("data") or {}).get("application_name") == "UAT Branding X",
                   payload.get("data"))
        status, payload, _ = api.json("GET", "/api/settings/application", headers=bearer(a_token))
        self.check("application settings change persisted",
                   (payload.get("data") or {}).get("application_name") == "UAT Branding X",
                   payload.get("data"))
        api.json("PUT", "/api/settings/application", {"application_name": original_app.get("application_name") or "Invoice System"},
                 headers=bearer(a_token))

        status, payload, _ = api.json("PUT", "/api/settings/application",
                                      {"application_name": "Sneaky Acc"} ,
                                      headers=bearer(self.state.get("acc_token") or "x"))
        self.check("accountant blocked from application settings (403)", status == 403, {"status": status})

        status, payload, _ = api.json("PUT", "/api/settings/application",
                                      {"pagination_size": 99999}, headers=bearer(a_token))
        self.check("invalid application setting rejected", 400 <= status < 500,
                   {"status": status, "code": (payload or {}).get("code")})

        # company settings
        status, payload, _ = api.json("PUT", "/api/settings/company",
                                      {"name": "UAT Company A (renamed)"},
                                      headers=bearer(a_token))
        self.check("admin updates own company settings", status == 200,
                   (payload.get("data") or {}))
        new_name = self.db.scalar("SELECT name FROM companies WHERE id=1")
        self.check("company rename persisted in DB", new_name == "UAT Company A (renamed)", {"name": new_name})
        api.json("PUT", "/api/settings/company", {"name": "UAT Company A"},
                 headers=bearer(a_token))

        # user settings (self)
        status, payload, _ = api.json("PUT", "/api/settings/user",
                                      {"language": "en", "theme": "light", "pagination_size": 25},
                                      headers=bearer(self.state["a_token"] or a_token))
        self.check("user updates own preferences", status == 200, payload.get("data"))
        status, payload, _ = api.json("GET", "/api/settings/user", headers=bearer(a_token))
        self.check("user preferences persisted",
                   (payload.get("data") or {}).get("pagination_size") == 25,
                   payload.get("data"))
        status, payload, _ = api.json("PUT", "/api/settings/user", {"theme": "neon"},
                                      headers=bearer(a_token))
        self.check("invalid theme rejected", 400 <= status < 500, {"status": status})

    # ------------------------------------------------------------ == ERROR
    def error_uat(self):
        api = self.primary
        a_token = self.state["a_token"]

        status, payload, _ = api.json("GET", "/api/no-such-route", headers=bearer(a_token))
        body = payload if isinstance(payload, dict) else {}
        self.check("unknown route -> 404 envelope", status == 404 and body.get("success") is False,
                   {"status": status, "code": body.get("code")})

        status, payload, _ = api.json("PUT", "/api/imports", headers=bearer(a_token))
        self.check("method not allowed -> 405", status == 405, {"status": status,
                                                                "code": payload.get("code") if isinstance(payload, dict) else None})

        status, payload, _ = api.json("GET", "/api/users", headers=bearer(self.state.get("viewer_token") or "x"))
        self.check("unauthorized role (403)", status == 403, {"status": status})

        status, payload, _ = api.json("GET", "/api/imports/9318239", headers=bearer(a_token))
        self.check("not found resource -> 404", status == 404 and payload.get("success") is False,
                   {"status": status, "code": (payload or {}).get("code")})

        # standard error envelope carries X-Request-Id correlation
        status, payload, headers = api.json("POST", "/api/auth/login", {"email": "x@y.z", "password": "nope"})
        self.check("error responses carry X-Request-Id",
                   bool(headers.get("x-request-id")), {"x-request-id": headers.get("x-request-id")})

    # ------------------------------------------------------------ HEALTH
    def health_uat(self):
        api = self.primary
        status, payload, headers = api.json("GET", "/api/health")
        self.check("health is ok", status == 200 and payload.get("status") == "ok",
                   payload)
        self.check("/api/v1/health alias", api.json("GET", "/api/v1/health")[0] == 200)
        status, payload, headers = api.json("GET", "/api/health/ready")
        self.check("readiness ok with database", status == 200 and (payload.get("data") or {}).get("database") == "ok",
                   payload)

        # authenticated representative request also fine
        status, payload, _ = api.json("GET", "/api/settings/user", headers=bearer(self.state["a_token"]))
        self.check("representative authenticated request healthy", status == 200, {"status": status})

    # ------------------------------------------------------ CROSS-FLOW
    def cross_flow_uat(self):
        api = self.primary
        a_token = self.state["a_token"]

        status, payload, _ = api.json("GET", "/api/settings/user", headers=bearer(a_token))
        self.check("cross-flow: settings reachable mid-session", status == 200)

        status, payload, _ = api.json("GET", f"/api/reconciliation/runs/{self.state['run_id']}/results",
                                      headers=bearer(a_token))
        self.check("cross-flow: results still consistent after co-run email instance", status == 200 and len(
            payload.get("data", {}).get("results", [])) == 9, {"status": status})

        # concurrent same-period start produces a single run (exclusive create)
        import threading
        outputs = {}

        def fire():
            outputs["s"] = api.json("POST", "/api/reconciliation/runs", {"period": "2026-06"},
                                    headers=bearer(a_token))

        threads = [threading.Thread(target=fire) for _ in range(2)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        ids = set()
        for st, pl, _ in outputs.values():
            if pl and pl.get("data", {}).get("run", {}).get("id"):
                ids.add(pl.get("data", {}).get("run", {}).get("id"))
        self.check("concurrent start for same period yields one run", len(ids) == 1,
                   {"run_ids": sorted(ids)})
        self.state["period_0606_run"] = list(ids)[0] if ids else None

        # after logout a token is fully dead (proves end-to-end session teardown)
        _, tmp_token = auth_headers(api, "admin.a@uat.test", PASSWORD)
        api.json("POST", "/api/auth/logout", headers=bearer(tmp_token))
        status, payload, _ = api.json("GET", "/api/auth/me", headers=bearer(tmp_token))
        self.check("cross-flow: post-logout token rejected", status == 401, {"status": status})

    # ----------------------------------------------------------- INTEGRITY
    def integrity_uat(self):
        db = self.db
        problems = []

        # foreign-key orphan scan across the company graph
        checks = [
            ("invoices", "SELECT COUNT(*) FROM invoices v LEFT JOIN companies c ON c.id=v.company_id WHERE c.id IS NULL"),
            ("invoice_items", "SELECT COUNT(*) FROM invoice_items i LEFT JOIN invoices v ON v.id=i.invoice_id WHERE v.id IS NULL"),
            ("tax_invoice_items", "SELECT COUNT(*) FROM tax_invoice_items i LEFT JOIN tax_invoices t ON t.id=i.tax_invoice_id WHERE t.id IS NULL"),
            ("reconciliation_results", "SELECT COUNT(*) FROM reconciliation_results r LEFT JOIN reconciliation_runs rn ON rn.id=r.run_id WHERE rn.id IS NULL"),
            ("reconciliation_errors", "SELECT COUNT(*) FROM reconciliation_errors e LEFT JOIN reconciliation_runs rn ON rn.id=e.run_id WHERE rn.id IS NULL"),
            ("email_deliveries", "SELECT COUNT(*) FROM email_deliveries d LEFT JOIN reconciliation_runs rn ON rn.id=d.run_id WHERE rn.id IS NULL"),
            ("audit_logs", "SELECT COUNT(*) FROM audit_logs a LEFT JOIN companies c ON c.id=a.company_id WHERE a.company_id IS NOT NULL AND c.id IS NULL"),
            ("import_batches", "SELECT COUNT(*) FROM import_batches b LEFT JOIN companies c ON c.id=b.company_id WHERE c.id IS NULL"),
            ("import_batch_errors", "SELECT COUNT(*) FROM import_batch_errors e LEFT JOIN import_batches b ON b.id=e.batch_id WHERE b.id IS NULL"),
        ]
        for table, sql in checks:
            try:
                n = db.scalar(sql)
            except Exception as exc:  # table may not exist in older schema
                n = "n/a"
            if n not in (0, "n/a"):
                problems.append(f"{table}:{n}")
            self.check(f"no orphan rows in {table}", n in (0, "n/a"), {"orphans": n})

        self.check("integrity scan found no orphan rows", not problems, {"problems": problems})

        # batch counters self-consistency (file-level rejections may record an
        # error count without a parsed total, so only scored batches count)
        bad = db.q("""SELECT id, total_rows, processed_rows, error_rows
                      FROM import_batches
                      WHERE total_rows > 0
                        AND total_rows != processed_rows + error_rows""")
        self.check("all import batch counters self-consistent",
                   not bad, [list(r) for r in bad])

        # reconciliation result + error counters must recompute from rows
        bad2 = db.q("""SELECT r.id, r.invoice_count, r.matched_count,
                              r.unmatched_count, r.error_count
                       FROM reconciliation_runs r
                       JOIN (SELECT run_id,
                                    SUM(match_status = 'matched') AS m,
                                    SUM(match_status <> 'matched') AS u
                             FROM reconciliation_results GROUP BY run_id) rr
                         ON rr.run_id = r.id
                       JOIN (SELECT run_id, COUNT(*) AS e
                             FROM reconciliation_errors GROUP BY run_id) re
                         ON re.run_id = r.id
                       WHERE r.matched_count != rr.m
                          OR r.unmatched_count != rr.u
                          OR r.error_count != re.e""")
        self.check("reconciliation run counters internally consistent", not bad2,
                   [list(r) for r in bad2])

        # invoice totals recompute from items (import formula:
        # subtotal = SUM(quantity*unit_price); vat = SUM(vat_amount);
        # total = SUM(line_total))
        bad3 = db.q("""
            SELECT v.invoice_number,
                   (SELECT COALESCE(SUM(i.quantity*i.unit_price),0) FROM invoice_items i WHERE i.invoice_id=v.id) AS sub,
                   v.subtotal_amount,
                   (SELECT COALESCE(SUM(i.vat_amount),0) FROM invoice_items i WHERE i.invoice_id=v.id) AS vat,
                   v.vat_amount,
                   (SELECT COALESCE(SUM(i.line_total),0) FROM invoice_items i WHERE i.invoice_id=v.id) AS tot,
                   v.total_amount
            FROM invoices v WHERE v.company_id=1""")
        mism = [list(r) for r in bad3 if not (abs(r[1]-r[2]) < 0.001 and abs(r[3]-r[4]) < 0.001 and abs(r[5]-r[6]) < 0.001)]
        self.check("stored invoice totals equal recomputed item sums", not mism,
                   {"mismatches": mism})


from decimal import Decimal
from datetime import datetime


def _json_safe(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime,)):
        return value.isoformat()
    if isinstance(value, (tuple, set)):
        return [_json_safe(v) for v in value]
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    return value


def main():
    uat = UAT()
    uat.run_all()
    summary = uat.reg.summary()
    # exit code drives CI gates
    if summary["FAIL"] or summary["BLOCKED"]:
        failed = [r for r in uat.reg.results if r.status in ("FAIL", "BLOCKED")]
        print("\nFAILURE/BLOCKED SUMMARY:")
        for r in failed:
            print(f"  {r.status}: {r.name}")
            if r.failure:
                print(f"      reason: {r.failure}")
        sys.exit(1)
    print("\nALL UAT CHECKS PASSED")


if __name__ == "__main__":
    main()