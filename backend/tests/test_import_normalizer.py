"""Tests for the import value normalizer.

Covers typed normalization of UUIDs, dates, money and quantities plus
missing-required-field error reporting. No database required.
"""

from datetime import date
from decimal import Decimal

from backend.modules.imports.normalizer import (
    normalize_row,
    normalize_uuid,
    parse_money,
    parse_quantity,
)


class TestMoney:
    def test_integer_and_string(self):
        assert parse_money("100") == Decimal("100.00")
        assert parse_money(100.5) == Decimal("100.50")

    def test_thousand_separators_variants(self):
        assert parse_money("1,234.56") == Decimal("1234.56")
        assert parse_money("1.234,56") == Decimal("1234.56")
        assert parse_money("1,000") == Decimal("1000.00")

    def test_currency_symbols_stripped(self):
        assert parse_money("EGP 1,000.50") == Decimal("1000.50")
        assert parse_money("ج.م 500") == Decimal("500.00")
        assert parse_money("$12.50") == Decimal("12.50")

    def test_parenthesized_negative(self):
        assert parse_money("(100.00)") == Decimal("-100.00")
        assert parse_money("-50.25") == Decimal("-50.25")

    def test_invalid_money(self):
        assert parse_money("abc") is None
        assert parse_money("") is None
        assert parse_money(None) is None


class TestQuantity:
    def test_rounds_to_four_places(self):
        assert parse_quantity("2.5") == Decimal("2.5000")
        assert parse_quantity("1.23456") == Decimal("1.2346")

    def test_invalid(self):
        assert parse_quantity("n/a") is None


class TestUuid:
    def test_normalizes_dashed_lowercase(self):
        assert normalize_uuid("D3C6E4F7-1A2B-4C3D-8E5F-6A7B8C9D0E1F") == (
            "d3c6e4f7-1a2b-4c3d-8e5f-6a7b8c9d0e1f"
        )

    def test_accepts_plain_hex(self):
        assert normalize_uuid("d3c6e4f71a2b4c3d8e5f6a7b8c9d0e1f") == (
            "d3c6e4f7-1a2b-4c3d-8e5f-6a7b8c9d0e1f"
        )

    def test_rejects_garbage(self):
        assert normalize_uuid("not-a-uuid") is None
        assert normalize_uuid("") is None


class TestDate:
    def _parse(self, value):
        normalized, errors = normalize_row(1, {
            "invoice_number": "INV-1",
            "invoice_date": value,
            "counterparty_name": "Acme",
            "item_description": "Widget",
        })
        return normalized.get("invoice_date"), errors

    def test_iso_date(self):
        result, errors = self._parse("2024-01-15")
        assert errors == []
        assert result == date(2024, 1, 15)

    def test_dmy_format(self):
        result, _ = self._parse("15/01/2024")
        assert result == date(2024, 1, 15)

    def test_mdy_format(self):
        result, _ = self._parse("01/15/2024")
        assert result == date(2024, 1, 15)

    def test_excel_serial(self):
        result, _ = self._parse(45292)
        assert result == date(2024, 1, 1)

    def test_invalid_date(self):
        _, errors = self._parse("not a date")
        assert len(errors) == 1
        assert errors[0].error_code == "INVALID_DATE"
        assert errors[0].row_number == 1
        assert errors[0].field == "invoice_date"


class TestNormalizeRow:
    def test_missing_required_fields(self):
        _, errors = normalize_row(3, {"item_description": "T"})
        codes = {e.field for e in errors}
        assert {"invoice_number", "invoice_date", "counterparty_name"} <= codes
        assert all(e.error_code == "MISSING_FIELD" for e in errors)
        assert all(e.row_number == 3 for e in errors)

    def test_defaults_applied(self):
        normalized, errors = normalize_row(1, {
            "invoice_number": "INV-9",
            "invoice_date": "2024-01-01",
            "counterparty_name": "Acme",
            "item_description": "Widget",
        })
        assert errors == []
        assert normalized["currency"] == "EGP"
        assert normalized["invoice_type"] == "sales"
        assert normalized["quantity"] == Decimal("1.0000")
        assert normalized["unit_price"] == Decimal("0.00")

    def test_invalid_enum(self):
        normalized, errors = normalize_row(2, {
            "invoice_number": "INV-1",
            "invoice_date": "2024-01-01",
            "counterparty_name": "Acme",
            "item_description": "Widget",
            "invoice_type": "shredding",
        })
        assert normalized.get("invoice_type") is None
        assert errors[0].error_code == "INVALID_ENUM"
        assert errors[0].field == "invoice_type"

    def test_valid_enum_case_insensitive(self):
        normalized, errors = normalize_row(2, {
            "invoice_number": "INV-1",
            "invoice_date": "2024-01-01",
            "counterparty_name": "Acme",
            "item_description": "Widget",
            "invoice_type": "Purchase",
        })
        assert errors == []
        assert normalized["invoice_type"] == "purchase"