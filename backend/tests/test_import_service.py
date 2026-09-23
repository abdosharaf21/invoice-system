"""End-to-end tests for the import service orchestration.

Uses mock repositories so the full import pipeline (parse -> normalize
-> group -> duplicate check -> persist) runs without a database.
"""

from decimal import Decimal
from unittest.mock import MagicMock

import mysql.connector
import pytest

from backend.modules.imports import errors as const
from backend.modules.imports.service import ImportService

UUID_1 = "d3c6e4f7-1a2b-4c3d-8e5f-6a7b8c9d0e1f"
UUID_2 = "e4d5f6a8-2b3c-4d5e-9f6a-7b8c9d0e1f23"


class _Harness:
    def __init__(self, get_by_uuid=None, get_by_number=None, batch_id=7):
        self.batch_repo = MagicMock()
        self.invoice_repo = MagicMock()
        self.invoice_repo.get_by_uuid.return_value = get_by_uuid
        self.invoice_repo.get_by_company_and_number.return_value = get_by_number
        self.batch = MagicMock()
        self.batch.id = batch_id
        self.batch_repo.create.return_value = self.batch
        self.service = ImportService(self.batch_repo, self.invoice_repo)

    def import_csv(self, text: str, content_type: str = "text/csv") -> "ImportService":
        return self.service.import_file(1, 7, "invoices.csv", content_type, text.encode())

    @property
    def created_invoices(self):
        return [call.args[0] for call in self.invoice_repo.create.call_args_list]


class TestImportService:
    def test_happy_path_persists_grouped_invoices(self):
        harness = _Harness()
        result = harness.import_csv(
            "uuid,invoice_number,invoice_date,currency,counterparty_name,item_description,quantity,unit_price,vat_rate\n"
            f"{UUID_1},INV-001,2024-01-15,EGP,Acme Corp,Widget A,2,100.00,14\n"
            f"{UUID_1},INV-001,2024-01-15,EGP,Acme Corp,Widget B,1,50.00,14\n"
            f"{UUID_2},INV-002,2024-01-16,EGP,Globex Ltd,Gadget,5,20.00,0\n"
        )
        assert result.batch.status == "completed"
        assert result.batch.total_rows == 3
        assert result.batch.processed_rows == 3
        assert result.batch.error_rows == 0
        assert result.errors == []

        invoices = harness.created_invoices
        assert len(invoices) == 2
        first = invoices[0]
        assert first.invoice_number == "INV-001"
        assert first.import_batch_id == 7
        assert first.subtotal_amount == Decimal("250.00")
        assert first.vat_amount == Decimal("35.00")
        assert first.total_amount == Decimal("285.00")
        assert len(first.items) == 2

    def test_computes_line_totals(self):
        harness = _Harness()
        harness.import_csv(
            "invoice_number,invoice_date,counterparty_name,item_description,quantity,unit_price,vat_rate\n"
            "INV-10,2024-01-10,Acme,Widget,2,100.00,14\n"
        )
        invoice = harness.created_invoices[0]
        item = invoice.items[0]
        assert item.quantity == Decimal("2.0000")
        assert item.unit_price == Decimal("100.00")
        assert item.vat_amount == Decimal("28.00")
        assert item.line_total == Decimal("228.00")

    def test_respects_provided_totals(self):
        harness = _Harness()
        harness.import_csv(
            "invoice_number,invoice_date,counterparty_name,item_description,quantity,unit_price,vat_amount,line_total\n"
            "INV-11,2024-01-11,Acme,Widget,1,100.00,7.50,107.50\n"
        )
        item = harness.created_invoices[0].items[0]
        assert item.vat_amount == Decimal("7.50")
        assert item.line_total == Decimal("107.50")

    def test_bad_row_recorded_does_not_block_good_rows(self):
        harness = _Harness()
        result = harness.import_csv(
            "invoice_number,invoice_date,counterparty_name,item_description,unit_price\n"
            "INV-GOOD,2024-01-01,Acme,Widget,10.00\n"
            "INV-BAD,2024-01-02,Acme,Widget,not-a-number\n"
        )
        assert result.batch.status == "completed"
        assert result.batch.processed_rows == 1
        assert result.batch.error_rows == 1
        assert len(harness.created_invoices) == 1
        assert result.errors[0].row_number == 2
        assert result.errors[0].error_code == "INVALID_MONEY"

    def test_row_errors_persisted_on_completed_batch(self):
        harness = _Harness()
        harness.import_csv(
            "invoice_number,invoice_date,counterparty_name,item_description,unit_price\n"
            "INV-GOOD,2024-01-01,Acme,Widget,10.00\n"
            "INV-BAD,2024-01-02,Acme,Widget,not-a-number\n"
        )
        assert harness.batch_repo.add_error.call_count == 1
        error = harness.batch_repo.add_error.call_args.args[0]
        assert error.batch_id == 7
        assert error.row_number == 2
        assert error.error_code == "INVALID_MONEY"
        assert error.field == "unit_price"

    def test_in_file_duplicate_detected(self):
        harness = _Harness()
        result = harness.import_csv(
            f"uuid,invoice_number,invoice_date,counterparty_name,item_description\n"
            f"{UUID_1},INV-A,2024-01-01,Acme,Item\n"
            f",INV-A,2024-01-01,Acme,Item2\n"
        )
        codes = [e.error_code for e in result.errors]
        assert const.E_DUPLICATE_IN_FILE in codes
        assert result.batch.error_rows == 1

    def test_db_duplicate_by_uuid_detected(self):
        harness = _Harness(get_by_uuid=MagicMock())
        result = harness.import_csv(
            f"uuid,invoice_number,invoice_date,counterparty_name,item_description\n"
            f"{UUID_1},INV-B,2024-01-01,Acme,Item\n"
        )
        assert result.errors[0].error_code == const.E_DUPLICATE_IN_DB
        assert result.batch.status == "failed"
        assert harness.created_invoices == []

    def test_db_duplicate_by_number_detected(self):
        harness = _Harness(get_by_number=MagicMock())
        result = harness.import_csv(
            "invoice_number,invoice_date,counterparty_name,item_description\n"
            "INV-C,2024-01-01,Acme,Item\n"
        )
        assert result.errors[0].error_code == const.E_DUPLICATE_IN_DB

    def test_uuid_checked_before_number(self):
        harness = _Harness(get_by_uuid=MagicMock(), get_by_number=MagicMock())
        harness.import_csv(
            f"uuid,invoice_number,invoice_date,counterparty_name,item_description\n"
            f"{UUID_1},INV-D,2024-01-01,Acme,Item\n"
        )
        get_by_uuid_called = harness.invoice_repo.get_by_uuid.called
        assert get_by_uuid_called
        assert not harness.invoice_repo.get_by_company_and_number.called

    def test_rejected_extension_fails_batch(self):
        harness = _Harness()
        result = harness.service.import_file(1, 7, "invoice.pdf", "text/csv", b"stuff")
        assert result.batch.status == "failed"
        assert result.errors[0].error_code == const.E_FILE_ERROR
        assert harness.created_invoices == []

    def test_company_for_user(self):
        user = MagicMock()
        user.company_id = 42
        user_repo = MagicMock()
        user_repo.get_by_id.return_value = user
        service = ImportService(MagicMock(), MagicMock(), user_repo)
        assert service.company_for_user(5) == 42

    def test_company_for_user_missing(self):
        user_repo = MagicMock()
        user_repo.get_by_id.return_value = None
        service = ImportService(MagicMock(), MagicMock(), user_repo)
        assert service.company_for_user(5) is None


class TestBatchCounterIntegrity:
    """Verifies `total_rows` is persisted with `update_counts` (Phase 3).

    The completed path used to drop `total_rows`, leaving batches stuck at
    0 while processed/error counters were populated. Every terminal path
    must hand the counter to the repository.
    """

    def test_completed_path_persists_total_rows(self):
        harness = _Harness()
        harness.import_csv(
            "uuid,invoice_number,invoice_date,currency,counterparty_name,item_description,quantity,unit_price,vat_rate\n"
            f"{UUID_1},INV-001,2024-01-15,EGP,Acme Corp,Widget,2,100.00,14\n"
            f"{UUID_2},INV-002,2024-01-16,EGP,Globex Ltd,Gadget,5,20.00,0\n"
        )
        call = harness.batch_repo.update_counts.call_args
        assert call.kwargs["total_rows"] == 2
        assert call.kwargs["processed_rows"] == 2
        assert call.kwargs["error_rows"] == 0

    def test_completed_path_counter_invariant_holds(self):
        harness = _Harness()
        harness.import_csv(
            "invoice_number,invoice_date,counterparty_name,item_description,unit_price\n"
            "INV-A,2024-01-01,Acme,Widget,10.00\n"
            "INV-B,2024-01-02,Acme,Widgetable,20.00\n"
            "INV-C,2024-01-03,Acme,Gadget,30.00\n"
        )
        call = harness.batch_repo.update_counts.call_args
        total = call.kwargs["total_rows"]
        processed = call.kwargs["processed_rows"]
        error = call.kwargs["error_rows"]
        assert total >= 0 and processed >= 0 and error >= 0
        assert processed + error == total

    def test_error_path_persists_total_rows(self):
        harness = _Harness()
        harness.import_csv(
            "invoice_number,invoice_date,counterparty_name,item_description,unit_price\n"
            "INV-GOOD,2024-01-01,Acme,Widget,10.00\n"
            "INV-BAD,2024-01-02,Acme,Widget,not-a-number\n"
        )
        call = harness.batch_repo.update_counts.call_args
        assert call.kwargs["total_rows"] == 2
        assert call.kwargs["processed_rows"] == 1
        assert call.kwargs["error_rows"] == 1

    def test_header_error_path_persists_parsed_total_rows(self):
        harness = _Harness()
        harness.service.import_file(
            1, 7, "invoices.csv", "text/csv",
            b"invoice_number,currency,counterparty_name,item_description\n"
            b"INV-1,EGP,Acme,Widget\n"
        )
        call = harness.batch_repo.update_counts.call_args
        assert call.kwargs["status"] == "failed"
        assert call.kwargs["total_rows"] == 1
        assert call.kwargs["processed_rows"] == 0
        assert call.kwargs["error_rows"] == 1

    def test_file_failure_path_forces_zero_total_rows(self):
        harness = _Harness()
        harness.service.import_file(1, 7, "invoice.pdf", "text/csv", b"stuff")
        call = harness.batch_repo.update_counts.call_args
        assert call.kwargs["status"] == "failed"
        assert call.kwargs["total_rows"] == 0
        assert call.kwargs["processed_rows"] == 0
        assert call.kwargs["error_rows"] == 1

    def test_unexpected_db_error_marks_batch_failed_and_reraises(self):
        """A mid-pipeline DB error must leave the batch failed, not stuck."""
        harness = _Harness()
        harness.invoice_repo.get_by_uuid.side_effect = mysql.connector.Error(
            "connection lost"
        )

        with pytest.raises(mysql.connector.Error):
            harness.import_csv(
                "uuid,invoice_number,invoice_date,currency,counterparty_name,"
                "item_description,quantity,unit_price,vat_rate\n"
                f"{UUID_1},INV-001,2024-01-15,EGP,Acme Corp,Widget A,2,100.00,14\n"
            )

        failed_call = None
        for call in harness.batch_repo.update_counts.call_args_list:
            if call.kwargs.get("status") == "failed":
                failed_call = call
        assert failed_call is not None
        assert failed_call.kwargs["total_rows"] == 1
        assert harness.batch.status == "failed"
        assert harness.batch_repo.add_error.called


class TestBatchRecovery:
    def test_recover_interrupted_delegates_to_repository(self):
        harness = _Harness()
        harness.batch_repo.recover_interrupted_batches.return_value = 2
        assert harness.service.recover_interrupted() == 2
        harness.batch_repo.recover_interrupted_batches.assert_called_once_with()