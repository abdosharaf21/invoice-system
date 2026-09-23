"""Regression tests for the Phase 8 N+1 query eliminations.

Asserts that the period list loaders for invoices, tax invoices and users
issue exactly two queries (headers + one batched child query) instead of a
per-row child query, and that pool replenishment builds a ``MySQLConnection``
from connection args (not pool-only options).
"""

from contextlib import contextmanager
from datetime import datetime

import backend.database.connection as connection_mod
from backend.database.connection import Database
from backend.modules.invoices.repository import InvoiceRepository
from backend.modules.tax_authority.repository import TaxInvoiceRepository
from backend.modules.users.repository import UserRepository

DT = datetime(2024, 3, 1)


class FakeCursor:
    def __init__(self, fetch_results=None):
        self.fetch_results = list(fetch_results or [])
        self.calls = []
        self.queries = []

    def execute(self, query, params=None):
        self.queries.append(query)
        self.calls.append((query, params))
        return None

    def executemany(self, query, params):
        self.queries.append(query)
        self.calls.append((query, params))
        return len(params)

    def fetchone(self):
        if self.fetch_results:
            return self.fetch_results.pop(0)
        return None

    def fetchall(self):
        if self.fetch_results:
            return self.fetch_results.pop(0)
        return []

    def close(self):
        return None


class FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self, **kwargs):
        return self._cursor

    def commit(self):
        return None

    def rollback(self):
        return None


class FakeDatabase:
    def __init__(self, fetch_results=None):
        self.conn = FakeConn(FakeCursor(fetch_results))

    @contextmanager
    def connection(self):
        yield self.conn


_INVOICE = (
    1, "uuid-1", 1, None, "INV-1", "sales", DT.date(), None, "EGP",
    "Acme", "12345", "a@example.com", "1000.00", "0.00", "140.00", "1140.00",
    "completed", DT, DT,
)

_ITEM = (1, 1, "Widget", 2, "100.00", "0.00", "14.00", "28.00", "228.00", DT)


def test_invoice_period_list_loads_items_without_n_plus_one():
    database = FakeDatabase(fetch_results=[
        [_INVOICE, _INVOICE[:0] + (2,) + _INVOICE[1:]],
        [_ITEM, (2, 2, "Gadget", 1, "50.00", "0.00", "14.00", "7.00", "57.00", DT)],
    ])
    repo = InvoiceRepository(database)

    invoices = repo.list_by_company_and_period(1, "2024-03")

    assert len(invoices) == 2
    assert [len(i.items) for i in invoices] == [1, 1]
    assert invoices[0].items[0].description == "Widget"
    # One headers query + one batched items query and nothing else.
    assert len(database.conn._cursor.queries) == 2
    _, params = database.conn._cursor.calls[1]
    assert "IN (" in database.conn._cursor.calls[1][0]
    assert params == [1, 2]
    assert "WHERE invoice_id = %s" not in database.conn._cursor.calls[1][0]


def test_tax_period_list_loads_items_without_n_plus_one():
    tx_row = (
        1, 1, 1, None, "uuid-1", "T-1", "invoice", DT, "EGP", "1.000000",
        "Seller", "TAX-1", "Acme", "12345",
        "1000.00", "0.00", "1000.00", "140.00", "0.00", "1140.00",
        "submitted", None, DT, DT,
    )
    tx_item = (1, 1, "Widget", "composite", 2, "100.00",
               "14.00", "28.00", "0.00", "228.00", DT)
    database = FakeDatabase(fetch_results=[
        [tx_row],
        [tx_item, (2, 1, "Gadget", "composite", 1, "50.00",
                   "14.00", "7.00", "0.00", "57.00", DT)],
    ])
    repo = TaxInvoiceRepository(database)

    taxes = repo.list_by_company_and_period(1, "2024-03")

    assert len(taxes) == 1
    assert len(taxes[0].items) == 2
    assert len(database.conn._cursor.queries) == 2
    assert "WHERE tax_invoice_id = %s" not in database.conn._cursor.calls[1][0]


def test_tax_period_list_with_no_rows_skips_items_query():
    database = FakeDatabase(fetch_results=[[]])
    repo = TaxInvoiceRepository(database)

    taxes = repo.list_by_company_and_period(1, "2024-03")

    assert taxes == []
    assert len(database.conn._cursor.queries) == 1


_USER = (
    1, 1, "user1", "u@example.com", "hash", "First", "User", 1,
    None, DT, DT, "en", "light", "YYYY-MM-DD", "#,##0.00", "UTC", None, 25,
)


def test_users_get_all_loads_roles_without_n_plus_one():
    database = FakeDatabase(fetch_results=[
        [_USER, _USER[:0] + (2,) + _USER[1:]],
        [(1, "admin"), (1, "viewer"), (2, "manager")],
    ])
    repo = UserRepository(database)

    users = repo.get_all()

    assert len(users) == 2
    assert users[0].roles == ["admin", "viewer"]
    assert users[1].roles == ["manager"]
    assert len(database.conn._cursor.queries) == 2
    query, params = database.conn._cursor.calls[1]
    assert "FROM roles r INNER JOIN user_roles ur ON ur.role_id = r.id" in query
    assert params == [1, 2]


def test_pool_replenishment_uses_connection_args_not_pool_args(monkeypatch):
    class Config:
        pool_name = "pool"
        pool_size = 5

        def to_connection_args(self):
            return {"host": "127.0.0.1", "user": "root"}

        def to_pool_args(self):
            return {"pool_name": self.pool_name, "pool_size": self.pool_size,
                    "host": "127.0.0.1"}

    created = {}

    class FakeMySQLConnection:
        def __init__(self, **kwargs):
            created["kwargs"] = kwargs

    class FakePool:
        def __init__(self, **kwargs):
            created["pool_kwargs"] = kwargs

        def add_connection(self, conn):
            created["added"] = conn

    monkeypatch.setattr(connection_mod, "MySQLConnection", FakeMySQLConnection)
    monkeypatch.setattr(connection_mod, "MySQLConnectionPool", FakePool)

    database = Database(config=Config())

    assert created["pool_kwargs"]["pool_name"] == "pool"
    database._replenish_pool()

    assert created["added"] is not None
    # Pool-only options must not leak into MySQLConnection(...).
    assert created["kwargs"] == {"host": "127.0.0.1", "user": "root"}
    assert "pool_name" not in created["kwargs"]
    assert "pool_size" not in created["kwargs"]