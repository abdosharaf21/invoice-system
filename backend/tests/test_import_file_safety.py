"""Tests for file-level safety checks on accounting uploads.

Covers extension allow-listing, size limits, path traversal and
content sniffing. No database required.
"""

import pytest

from backend.modules.imports.file_safety import validate_file

_CSV = b"invoice_number\nINV-1\n"


class TestFileSafety:
    def test_valid_csv(self):
        file_type, error = validate_file("invoices.csv", "text/csv", _CSV)
        assert file_type == "csv"
        assert error is None

    def test_valid_xlsx(self):
        zip_content = b"PK\x03\x04dummy"
        file_type, error = validate_file("invoices.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", zip_content)
        assert file_type == "xlsx"
        assert error is None

    def test_reject_unsupported_extension(self):
        _, error = validate_file("invoices.pdf", "text/csv", _CSV)
        assert error is not None
        assert error.error_code == "FILE_ERROR"
        assert "pdf" in error.message

    def test_reject_path_traversal(self):
        _, error = validate_file("../etc/passwd.csv", "text/csv", _CSV)
        assert error is not None
        assert "path" in error.message.lower()
        _, error = validate_file("/etc/passwd.csv", "text/csv", _CSV)
        assert error is not None

    def test_reject_oversized_file(self):
        big = b"a" * (10 * 1024 * 1024 + 1)
        _, error = validate_file("big.csv", "text/csv", big)
        assert error is not None
        assert "maximum size" in error.message

    def test_reject_binary_disguised_as_csv(self):
        junk = b"MZ\x90\x00\x00\x00" + b"\x00" * 64
        _, error = validate_file("fake.csv", "text/csv", junk)
        assert error is not None

    def test_reject_non_zip_disguised_as_xlsx(self):
        _, error = validate_file("fake.xlsx", "text/csv", b"<html></html>")
        assert error is not None
        assert "xlsx" in error.message.lower()