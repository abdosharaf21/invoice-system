"""Tests for the import contract (header aliases and column mapping).

Verifies that raw file headers from real-world accounting files resolve
onto the canonical schema, that unknown columns are ignored, and that
duplicate headers are reported cleanly. No database required.
"""

from backend.modules.imports.contract import normalize_header, resolve_header
from backend.modules.imports.grouping import ROW_NUMBER_KEY, build_column_map, map_row


class TestHeaderAliases:
    def test_normalize_header_case_and_punctuation(self):
        assert normalize_header("Invoice Number") == "invoice_number"
        assert normalize_header("Invoice  #  ") == "invoice_no"
        assert normalize_header("Invoice#") == "invoice_no"
        assert normalize_header("  DATE ") == "date"

    def test_resolve_common_aliases(self):
        assert resolve_header("invoice_number") == "invoice_number"
        assert resolve_header("Invoice #") == "invoice_number"
        assert resolve_header("date") == "invoice_date"
        assert resolve_header("issue date") == "invoice_date"
        assert resolve_header("due date") == "due_date"
        assert resolve_header("customer_name") == "counterparty_name"
        assert resolve_header("vendor") == "counterparty_name"
        assert resolve_header("tax_rate") == "vat_rate"
        assert resolve_header("qty") == "quantity"

    def test_unknown_header_resolves_to_none(self):
        assert resolve_header("some random column") is None
        assert resolve_header("") is None


class TestColumnMap:
    def test_maps_known_headers_and_ignores_unknown(self):
        headers = ["Invoice #", "DATE", "Customer Name", "Description", "Qty", "notes"]
        mapping, errors = build_column_map(headers)
        assert errors == []
        assert mapping == [
            "invoice_number",
            "invoice_date",
            "counterparty_name",
            "item_description",
            "quantity",
            None,
        ]

    def test_duplicate_headers_reported(self):
        headers = ["Invoice #", "invoice_no"]
        mapping, errors = build_column_map(headers)
        assert len(errors) == 1
        assert errors[0].error_code == "DUPLICATE_HEADER"
        assert errors[0].field == "invoice_number"
        assert mapping[1] is None

    def test_map_row_skip_unknown_columns(self):
        mapping, _ = build_column_map(["Invoice #", "notes", "date"])
        row = map_row(mapping, ["INV-1", "irrelevant", "2024-01-01"], 7)
        assert row == {
            "invoice_number": "INV-1",
            "invoice_date": "2024-01-01",
            ROW_NUMBER_KEY: 7,
        }