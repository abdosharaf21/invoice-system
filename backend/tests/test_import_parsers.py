"""Tests for the CSV/XLSX parsers and the parser registry.

Verifies detection of delimiters, BOM handling, a BOM-aware header and
XLSX workbook reading. No database required.
"""

import io

import pytest
from openpyxl import Workbook

from backend.modules.imports.parsers import get_parser
from backend.modules.imports.parsers.base import FileParseError


def _make_xlsx(rows: list) -> bytes:
    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


class TestCsvParser:
    def test_comma_delimited(self):
        parsed = get_parser("csv").parse(
            b"invoice_number;invoice_date;counterparty_name;item_description\n"
            b"INV-1;2024-01-01;Acme;Widget\n"
        )
        assert parsed.headers == ["invoice_number", "invoice_date", "counterparty_name", "item_description"]
        assert parsed.total_rows == 1
        assert parsed.rows[0] == ["INV-1", "2024-01-01", "Acme", "Widget"]

    def test_delimiter_sniffing(self):
        parsed = get_parser("csv").parse(
            b"invoice_number\tinvoice_date\nINV-1\t2024-01-01\n"
        )
        assert parsed.headers == ["invoice_number", "invoice_date"]
        assert parsed.rows[0] == ["INV-1", "2024-01-01"]

    def test_bom_stripped(self):
        parsed = get_parser("csv").parse(b"\xef\xbb\xbfinvoice_number\nINV-1\n")
        assert parsed.headers == ["invoice_number"]
        assert parsed.rows[0] == ["INV-1"]

    def test_short_rows_padded(self):
        parsed = get_parser("csv").parse(b"a,b\n1\n2,3\n")
        assert parsed.rows == [["1", ""], ["2", "3"]]

    def test_empty_file_rejected(self):
        with pytest.raises(FileParseError):
            get_parser("csv").parse(b"")
        with pytest.raises(FileParseError):
            get_parser("csv").parse(b"\n\n\n")

    def test_non_utf8_rejected(self):
        with pytest.raises(FileParseError):
            get_parser("csv").parse(b"\xff\xfe\x00bad")

    def test_extension_forms(self):
        assert get_parser("csv") is not None
        assert get_parser(".CSV").file_type == "csv"
        assert get_parser("xlsx") is not None
        assert get_parser("pdf") is None


class TestXlsxParser:
    def test_parses_first_sheet(self):
        content = _make_xlsx([
            ["invoice_number", "invoice_date", "item_description", "quantity", "unit_price"],
            ["INV-X", "2024-02-01", "Gadget", 3, 12.5],
        ])
        parsed = get_parser("xlsx").parse(content)
        assert parsed.headers == ["invoice_number", "invoice_date", "item_description", "quantity", "unit_price"]
        assert parsed.total_rows == 1
        assert parsed.rows[0][0] == "INV-X"
        assert parsed.rows[0][3] == 3

    def test_empty_workbook_rejected(self):
        content = _make_xlsx([[""]] )
        with pytest.raises(FileParseError):
            get_parser("xlsx").parse(content)

    def test_bad_content_rejected(self):
        with pytest.raises(FileParseError):
            get_parser("xlsx").parse(b"this is not a zip file")