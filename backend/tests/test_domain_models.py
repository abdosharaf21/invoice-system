"""Tests for the Phase 2 domain models.

Verifies serialization round-trips for the domain models defined for the
E-Invoice database design: companies, invoices, tax invoices, imports and
reconciliation. These tests do not require a database.
"""

from datetime import date, datetime

from backend.modules.companies.model import Company
from backend.modules.imports.model import ImportBatch, ImportBatchError
from backend.modules.invoices.model import Invoice, InvoiceItem
from backend.modules.reconciliation.model import (
    ReconciliationError,
    ReconciliationResult,
    ReconciliationRun,
)
from backend.modules.tax_authority.model import TaxInvoice, TaxInvoiceItem

_ISO = "2025-02-01T12:00:00"


# ---------------------------------------------------------------------------
# Companies
# ---------------------------------------------------------------------------

class TestCompanyModel:
    def test_round_trip(self):
        data = {
            "id": 1,
            "name": "Acme E-Invoice S.A.E.",
            "tax_registration_number": "123456789",
            "email": "billing@acme.eg",
            "phone": "+20234567890",
            "address": "Cairo, Egypt",
            "is_active": True,
            "created_at": _ISO,
            "updated_at": _ISO,
        }
        company = Company.from_dict(data)
        assert company.tax_registration_number == "123456789"
        assert company.is_active is True
        assert company.to_dict()["name"] == "Acme E-Invoice S.A.E."


# ---------------------------------------------------------------------------
# Accounting invoices
# ---------------------------------------------------------------------------

class TestInvoiceModel:
    def test_round_trip_with_items(self):
        data = {
            "id": 10,
            "company_id": 1,
            "import_batch_id": 3,
            "invoice_number": "INV-2025-0001",
            "invoice_type": "sales",
            "invoice_date": "2025-02-01",
            "due_date": "2025-03-01",
            "currency": "EGP",
            "counterparty_name": "Retail Co.",
            "counterparty_tax_id": "987654321",
            "subtotal_amount": "1000.00",
            "discount_amount": "50.00",
            "vat_amount": "133.00",
            "total_amount": "1083.00",
            "status": "issued",
            "items": [
                {
                    "description": "Laptop",
                    "quantity": "2",
                    "unit_price": "500.00",
                    "vat_rate": "14.00",
                    "vat_amount": "133.00",
                    "line_total": "1083.00",
                }
            ],
            "created_at": _ISO,
            "updated_at": _ISO,
        }
        invoice = Invoice.from_dict(data)
        assert invoice.invoice_date == date(2025, 2, 1)
        assert invoice.counterparty_tax_id == "987654321"
        assert len(invoice.items) == 1
        assert invoice.items[0].description == "Laptop"
        assert invoice.to_dict()["invoice_number"] == "INV-2025-0001"
        assert invoice.to_dict()["total_amount"] == 1083.0
        assert invoice.to_dict()["items"][0]["quantity"] == 2.0


# ---------------------------------------------------------------------------
# Tax authority invoices
# ---------------------------------------------------------------------------

class TestTaxInvoiceModel:
    def test_round_trip_with_items(self):
        data = {
            "id": 20,
            "company_id": 1,
            "account_invoice_id": 10,
            "uuid": "b12f5c3a-0000-4d00-8000-0123456789ab",
            "internal_id": "INV-2025-0001",
            "document_type": "invoice",
            "issue_datetime": "2025-02-01T14:30:00",
            "currency": "EGP",
            "exchange_rate": "1.000000",
            "seller_name": "Acme E-Invoice S.A.E.",
            "seller_tax_id": "123456789",
            "buyer_name": "Retail Co.",
            "buyer_tax_id": "987654321",
            "total_sales": "1000.00",
            "total_discount": "50.00",
            "net_amount": "950.00",
            "vat_amount": "133.00",
            "other_charges": "0.00",
            "total_amount": "1083.00",
            "submission_status": "approved",
            "items": [
                {
                    "description": "Laptop",
                    "item_type": "taxable_item",
                    "quantity": "2",
                    "unit_value": "500.00",
                    "vat_rate": "14.00",
                    "vat_amount": "133.00",
                    "total_amount": "1083.00",
                }
            ],
        }
        tax_invoice = TaxInvoice.from_dict(data)
        assert tax_invoice.uuid == "b12f5c3a-0000-4d00-8000-0123456789ab"
        assert tax_invoice.account_invoice_id == 10
        assert tax_invoice.submission_status == "approved"
        assert tax_invoice.issue_datetime == datetime(2025, 2, 1, 14, 30, 0)
        assert len(tax_invoice.items) == 1
        assert tax_invoice.to_dict()["net_amount"] == 950.0


# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------

class TestImportBatchModel:
    def test_round_trip(self):
        data = {
            "id": 3,
            "company_id": 1,
            "filename": "invoices-feb-2025.csv",
            "file_type": "csv",
            "status": "completed",
            "total_rows": 100,
            "processed_rows": 98,
            "error_rows": 2,
            "uploaded_by": 1,
            "started_at": _ISO,
            "finished_at": _ISO,
        }
        batch = ImportBatch.from_dict(data)
        assert batch.filename == "invoices-feb-2025.csv"
        assert batch.status == "completed"
        assert batch.error_rows == 2
        assert batch.to_dict()["total_rows"] == 100

    def test_error_round_trip(self):
        error = ImportBatchError.from_dict({
            "id": 1,
            "batch_id": 3,
            "row_number": 5,
            "error_message": "invalid tax id",
            "raw_data": '{"col": "x"}',
        })
        assert error.row_number == 5
        assert error.to_dict()["error_message"] == "invalid tax id"


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------

class TestReconciliationModel:
    def test_run_round_trip(self):
        data = {
            "id": 1,
            "company_id": 1,
            "period": "2025-02",
            "status": "completed",
            "invoice_count": 100,
            "tax_invoice_count": 95,
            "matched_count": 92,
            "unmatched_count": 6,
            "error_count": 2,
            "started_at": _ISO,
            "finished_at": _ISO,
        }
        run = ReconciliationRun.from_dict(data)
        assert run.period == "2025-02"
        assert run.to_dict()["matched_count"] == 92

    def test_result_round_trip(self):
        result = ReconciliationResult.from_dict({
            "id": 1,
            "run_id": 1,
            "account_invoice_id": 10,
            "tax_invoice_id": 20,
            "match_status": "matched",
            "discrepancy_amount": "0.00",
            "notes": "auto-matched",
        })
        assert result.to_dict()["match_status"] == "matched"
        assert result.to_dict()["discrepancy_amount"] == 0.0

    def test_error_round_trip(self):
        error = ReconciliationError.from_dict({
            "id": 1,
            "run_id": 1,
            "source_type": "account",
            "entity_id": 10,
            "error_type": "duplicate_number",
            "message": "duplicate invoice number",
        })
        assert error.error_type == "duplicate_number"
        assert error.to_dict()["source_type"] == "account"