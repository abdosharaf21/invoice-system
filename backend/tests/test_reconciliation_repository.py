"""Repository tests for reconciliation error mapping and transactional finish.

These exercise the SQL column mapping and single-transaction persistence path
against a fake database connector (no real MySQL needed).
"""

from contextlib import contextmanager
from datetime import datetime

import mysql.connector
import pytest

from backend.modules.reconciliation import contract as c
from backend.modules.reconciliation.model import (
    ReconciliationError,
    ReconciliationResult,
)
from backend.modules.reconciliation.repository import ReconciliationRepository


class FakeCursor:
    """Cursor that records queries and returns scripted fetch results."""

    def __init__(self, fetch_results=None):
        self.fetch_results = list(fetch_results or [])
        self.queries = []
        self.calls = []
        self.lastrowid = 1
        self.rowcount = 1

    def execute(self, query, params=None):
        self.queries.append(query)
        self.calls.append((query, params))
        return None

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
        self.committed = False
        self.rolled_back = False

    def cursor(self, **kwargs):
        return self._cursor

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


class FakeDatabase:
    def __init__(self, fetch_results=None):
        self.conn = FakeConn(FakeCursor(fetch_results))
        self.connection_calls = 0

    @contextmanager
    def connection(self):
        self.connection_calls += 1
        yield self.conn


_ERROR_ROW = (
    1,                    # id
    7,                    # run_id
    "account",            # source_type
    42,                   # entity_id
    "total_amount",       # field
    "1150.00",            # accounting_value
    "1200.00",            # tax_authority_value
    50.0,                 # difference
    c.E_TOTAL_AMOUNT_MISMATCH,  # error_type
    "total_amount differs",     # message
    datetime(2024, 6, 1),       # created_at
)


def test_list_errors_maps_columns_in_schema_order():
    database = FakeDatabase(fetch_results=[[_ERROR_ROW]])
    repo = ReconciliationRepository(database)
    errors = repo.list_errors(7)

    assert len(errors) == 1
    error = errors[0]
    assert error.error_type == c.E_TOTAL_AMOUNT_MISMATCH
    assert error.field == "total_amount"
    assert error.accounting_value == "1150.00"
    assert error.tax_authority_value == "1200.00"
    assert error.difference == 50.0
    assert error.message == "total_amount differs"
    assert error.source_type == "account"
    assert error.entity_id == 42
    assert error.run_id == 7


def test_add_error_writes_all_detail_columns():
    database = FakeDatabase()
    repo = ReconciliationRepository(database)
    error = ReconciliationError(
        run_id=7, source_type="tax", entity_id=99,
        error_type=c.E_INVALID_UUID, field="uuid",
        accounting_value=None, tax_authority_value="garbage",
        difference=None, message="identity untrustworthy",
    )
    repo.add_error(error)

    insert = database.conn._cursor.queries[0]
    assert "accounting_value" in insert
    assert "tax_authority_value" in insert
    assert "difference" in insert
    assert database.conn.committed is True


def test_finish_run_transaction_writes_results_errors_and_status_once():
    database = FakeDatabase()
    repo = ReconciliationRepository(database)
    results = [
        ReconciliationResult(
            account_invoice_id=1, tax_invoice_id=10,
            match_status=c.MATCHED, discrepancy_amount=0.0,
        ),
        ReconciliationResult(
            account_invoice_id=2, tax_invoice_id=None,
            match_status=c.MISSING_IN_TAX_AUTHORITY, discrepancy_amount=0.0,
        ),
    ]
    errors = [
        ReconciliationError(
            source_type="account", entity_id=9,
            error_type=c.E_TOTAL_AMOUNT_MISMATCH, field="total_amount",
            accounting_value="1.00", tax_authority_value="2.00",
            difference=1.0, message="differs",
        ),
    ]

    repo.finish_run_transaction(
        7, results, errors,
        invoice_count=2, tax_invoice_count=1,
        matched_count=1, unmatched_count=1, error_count=1,
    )

    queries = database.conn._cursor.queries
    assert len(queries) == 4  # 2 result inserts + 1 error insert + 1 update
    assert set(queries[0].split()[:2]) == {"INSERT", "INTO"}
    assert "status = 'completed'" in queries[3]
    assert "error_count" in queries[3]
    assert database.conn.committed is True
    assert database.conn.rolled_back is False


def test_finish_run_transaction_rolls_back_on_error():
    class BoomCursor(FakeCursor):
        def execute(self, query, params=None):
            raise mysql.connector.Error("db exploded")

    database = FakeDatabase()
    database.conn = FakeConn(BoomCursor())
    repo = ReconciliationRepository(database)

    with pytest.raises(mysql.connector.Error):
        repo.finish_run_transaction(
            7,
            [ReconciliationResult(match_status=c.MATCHED)],
            [],
            invoice_count=1, tax_invoice_count=1,
            matched_count=1, unmatched_count=0, error_count=0,
        )

    assert database.conn.rolled_back is True
    assert database.conn.committed is False


_RESULT_ROW = (
    1, 7, 10, 20, c.MATCHED, 0.0, None, datetime(2024, 6, 1),
    "INV-100", "uuid-100", datetime(2024, 3, 1).date(), "EGP",
    "Acme Corp", "12345",
    None, None, None,
    "uuid-100", "T-100", datetime(2024, 3, 1, 9, 0, 0), "EGP",
    None, None, None, None,
)


def test_count_results_binds_filters_as_parameters():
    database = FakeDatabase(fetch_results=[[5]])
    repo = ReconciliationRepository(database)
    total = repo.count_results(7, {
        "match_status": c.MISMATCHED,
        "uuid": "abc",
        "invoice_number": "INV-1",
        "date_from": "2024-03-01",
        "date_to": "2024-03-31",
    })

    assert total == 5
    query, params = database.conn._cursor.calls[0]
    assert "COUNT(*)" in query
    assert params == [7, c.MISMATCHED, "abc", "abc", "INV-1", "2024-03-01", "2024-03-31"]
    assert params.count("abc") == 2


def test_list_results_report_applies_matching_and_pagination():
    database = FakeDatabase(fetch_results=[[_RESULT_ROW]])
    repo = ReconciliationRepository(database)
    rows = repo.list_results_report(7, limit=10, offset=20, filters={
        "match_status": c.MATCHED,
    })

    assert rows[0]["account_invoice_number"] == "INV-100"
    assert rows[0]["account_uuid"] == "uuid-100"
    assert rows[0]["tax_internal_id"] == "T-100"
    query, params = database.conn._cursor.calls[0]
    assert "ORDER BY r.id" in query
    assert "LIMIT %s OFFSET %s" in query
    assert params[-2:] == [10, 20]


def test_count_errors_and_list_bind_error_filters():
    database = FakeDatabase(fetch_results=[[2]])
    repo = ReconciliationRepository(database)
    total_errors = repo.count_errors(7, {
        "error_type": c.E_TOTAL_AMOUNT_MISMATCH,
        "source_type": "account",
    })
    assert total_errors == 2
    query, params = database.conn._cursor.calls[0]
    assert params == [7, c.E_TOTAL_AMOUNT_MISMATCH, "account"]


def test_iter_results_report_streams_in_batches():
    database = FakeDatabase(fetch_results=[
        [_RESULT_ROW, _RESULT_ROW],   # full first batch (2 rows)
        [_RESULT_ROW],                # partial second batch (1 row)
    ])
    repo = ReconciliationRepository(database)
    rows = list(repo.iter_results_report(7, batch_size=2))
    assert len(rows) == 3
    assert len(database.conn._cursor.calls) == 2
    query, params = database.conn._cursor.calls[1]
    assert params[-2:] == [2, 2]