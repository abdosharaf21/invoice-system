"""Tests for row grouping and invoice-consistency checks.

Verifies that line rows fold into invoices by uuid first then by
invoice number, and that inconsistent invoice-level values across rows
of the same invoice are reported. No database required.
"""

from backend.modules.imports.grouping import ROW_NUMBER_KEY, group_rows
from backend.modules.imports.errors import E_INCONSISTENT_GROUP

UUID_1 = "d3c6e4f7-1a2b-4c3d-8e5f-6a7b8c9d0e1f"
UUID_2 = "e4d5f6a8-2b3c-4d5e-9f6a-7b8c9d0e1f23"


def _row(number, invoice_number=None, uuid=None, date="2024-01-01", counterparty="Acme"):
    row = {
        "invoice_number": invoice_number,
        "invoice_date": date,
        "counterparty_name": counterparty,
        "item_description": f"item-{number}",
        ROW_NUMBER_KEY: number,
    }
    if uuid:
        row["uuid"] = uuid
    return row


class TestGroupRows:
    def test_groups_by_uuid(self):
        rows = [
            _row(1, "INV-1", uuid=UUID_1),
            _row(2, "INV-1", uuid=UUID_1),
            _row(3, "INV-2", uuid=UUID_2),
        ]
        groups, errors = group_rows(rows, {r[ROW_NUMBER_KEY]: [] for r in rows})
        assert errors == []
        assert len(groups) == 2
        assert groups[0].first_row == 1
        assert len(groups[0].item_values) == 2
        assert groups[1].first_row == 3

    def test_groups_by_invoice_number_when_no_uuid(self):
        rows = [
            _row(10, "INV-A"),
            _row(11, "INV-A"),
            _row(12, "INV-B"),
        ]
        groups, errors = group_rows(rows, {})
        assert errors == []
        assert [g.invoice_number for g in groups] == ["INV-A", "INV-B"]
        assert len(groups[0].item_values) == 2

    def test_inconsistent_invoice_date_flagged(self):
        rows = [
            _row(1, "INV-C", date="2024-01-01"),
            _row(2, "INV-C", date="2024-01-02"),
        ]
        groups, errors = group_rows(rows, {})
        assert errors == []
        assert len(groups) == 1
        assert len(groups[0].errors) == 1
        assert groups[0].errors[0].error_code == E_INCONSISTENT_GROUP
        assert groups[0].errors[0].row_number == 2
        assert groups[0].errors[0].field == "invoice_date"

    def test_inconsistent_counterparty_flagged(self):
        rows = [
            _row(1, "INV-D"),
            _row(2, "INV-D", counterparty="Globex"),
        ]
        groups, _ = group_rows(rows, {})
        assert groups[0].errors[0].field == "counterparty_name"

    def test_blank_key_is_rejected(self):
        rows = [{
            "invoice_number": None,
            "uuid": None,
            "item_description": "x",
            ROW_NUMBER_KEY: 5,
        }]
        groups, errors = group_rows(rows, {})
        assert groups == []
        assert errors[0].row_number == 5
        assert errors[0].error_code == E_INCONSISTENT_GROUP