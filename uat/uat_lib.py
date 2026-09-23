"""Shared UAT harness library for Phase 15.

* ``Api``  — real HTTP client (stdlib) against a live application instance.
* ``Db``   — direct read access to the isolated scratch database for state
             verification (never used to mutate business data).
* ``Registry`` — collects PASS/FAIL/BLOCKED/N-A results with evidence.

UAT tooling only; not part of the shipped application.
"""

import json
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

import mysql.connector


class Api:
    """Minimal HTTP client for the UAT harness using only the stdlib."""

    def __init__(self, base: str):
        self.base = base.rstrip("/")
        self.last_request_id: Optional[str] = None

    def _call(
        self,
        method: str,
        path: str,
        body: Optional[dict] = None,
        headers: Optional[dict] = None,
        raw_body: Optional[bytes] = None,
        content_type: Optional[str] = None,
        timeout: int = 60,
    ) -> Tuple[int, Any, Dict[str, str]]:
        url = f"{self.base}{path}"
        req_headers = dict(headers or {})
        data = None
        if raw_body is not None:
            data = raw_body
            req_headers.setdefault("Content-Type", content_type or "application/octet-stream")
        elif body is not None:
            data = json.dumps(body).encode("utf-8")
            req_headers.setdefault("Content-Type", "application/json")
        request = urllib.request.Request(url, data=data, method=method, headers=req_headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                resp_headers = {k.lower(): v for k, v in response.headers.items()}
                self.last_request_id = resp_headers.get("x-request-id")
                raw = response.read()
                status = response.status
        except urllib.error.HTTPError as exc:
            resp_headers = {k.lower(): v for k, v in exc.headers.items()}
            self.last_request_id = resp_headers.get("x-request-id")
            raw = exc.read()
            status = exc.code
        text = raw.decode("utf-8", errors="replace") if isinstance(raw, (bytes, bytearray)) else ""
        try:
            parsed = json.loads(text) if text else None
        except ValueError:
            parsed = text
        return status, parsed, resp_headers

    def json(self, method: str, path: str, body: Optional[dict] = None,
             headers: Optional[dict] = None) -> Tuple[int, Any, Dict[str, str]]:
        return self._call(method, path, body=body, headers=headers)

    def raw(self, method: str, path: str, body: bytes, content_type: str,
            headers: Optional[dict] = None) -> Tuple[int, Any, Dict[str, str]]:
        return self._call(method, path, raw_body=body, content_type=content_type,
                          headers=headers)

    def multipart_upload(self, path: str, field: str, filename: str, content: bytes,
                         headers: Optional[dict] = None) -> Tuple[int, Any, Dict[str, str]]:
        boundary = "----UATBoundary7MA4YWxkTrZu0gW"
        parts = []
        parts.append(
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'
            f"Content-Type: text/csv\r\n\r\n"
        )
        parts.append(content.decode("utf-8", errors="replace"))
        parts.append(f"\r\n--{boundary}--\r\n")
        payload = "".join(parts).encode("utf-8")
        return self._call(
            "POST", path, raw_body=payload,
            content_type=f"multipart/form-data; boundary={boundary}",
            headers=headers,
        )


class Db:
    """Read-only access to the isolated scratch UAT database."""

    def __init__(self, db: str, host: str = "127.0.0.1", port: int = 3306,
                 user: str = "root", password: str = "abdo2146"):
        self._params = dict(host=host, port=port, user=user,
                            password=password, database=db)

    def q(self, sql: str, params: Optional[tuple] = None) -> List[tuple]:
        conn = mysql.connector.connect(**self._params)
        try:
            cursor = conn.cursor()
            cursor.execute(sql, params or ())
            rows = cursor.fetchall()
            cursor.close()
            return rows
        finally:
            conn.close()

    def scalar(self, sql: str, params: Optional[tuple] = None):
        rows = self.q(sql, params)
        return rows[0][0] if rows else None


class UATResult:
    __slots__ = ("status", "name", "evidence", "failure")

    def __init__(self, status: str, name: str, evidence: Optional[Any] = None,
                 failure: Optional[str] = None):
        self.status = status  # PASS | FAIL | BLOCKED | N-A
        self.name = name
        self.evidence = evidence
        self.failure = failure


class Registry:
    def __init__(self):
        self.results: List[UATResult] = []

    def record(self, status: str, name: str, evidence: Optional[Any] = None,
               failure: Optional[str] = None) -> UATResult:
        # When a plain boolean is supplied as evidence True => PASS, False => FAIL.
        if status == "PASS" and evidence is False:
            status = "FAIL"
        if status == "FAIL" and evidence is True:
            status = "PASS"
        res = UATResult(status, name, evidence, failure)
        self.results.append(res)
        return res

    def check(self, name: str, condition: bool, evidence: Any = None,
              failure: Optional[str] = None):
        return self.record("PASS" if condition else "FAIL", name, evidence,
                           failure=failure)

    def summary(self) -> Dict[str, int]:
        counts = {"PASS": 0, "FAIL": 0, "BLOCKED": 0, "N-A": 0}
        for res in self.results:
            counts[res.status] = counts.get(res.status, 0) + 1
        return counts


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def auth_headers(api: Api, email: str, password: str) -> Tuple[int, Optional[str]]:
    """Login and return (status, access_token)."""
    status, payload, _ = api.json("POST", "/api/auth/login",
                                  body={"email": email, "password": password})
    if status != 200 or not payload.get("success"):
        return status, None
    return status, payload["data"]["access_token"]