"""Row grouping and column mapping for accounting imports.

Accounting files use one row per invoice line item. Rows belonging to
the same invoice must be folded back into a single invoice before
persistence. Grouping keys are, in order of preference:

1. ``uuid`` - when the source rows carry the invoice UUID, and
2. ``invoice_number`` - otherwise (matching the company+number
   unique key on ``invoices``).

Invoice-level fields are taken from the first row of a group and every
following row must agree on them; a row that disagrees is flagged with a
group-level ``INCONSISTENT_GROUP`` error instead of silently dropping
data.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from backend.modules.imports.contract import (
    INVOICE_LEVEL_FIELDS,
    ITEM_LEVEL_FIELDS,
    resolve_header,
)
from backend.modules.imports.errors import (
    E_DUPLICATE_HEADER,
    E_INCONSISTENT_GROUP,
    ImportErrorInfo,
)

ROW_NUMBER_KEY = "_row_number"
RAW_KEY = "_raw"


def build_column_map(headers: List[Any]) -> Tuple[List[Optional[str]], List[ImportErrorInfo]]:
    """Map raw header cells to canonical field names.

    Unknown headers map to ``None`` (and are ignored). Two different
    headers resolving to the same canonical field are reported as a
    duplicate-header error so ambiguous files are rejected early.

    Returns:
        A ``(column_map, errors)`` tuple. ``column_map`` is parallel to
        ``headers`` and holds the canonical name (or None) per column.
    """
    mapping: List[Optional[str]] = []
    seen: Dict[str, int] = {}
    errors: List[ImportErrorInfo] = []

    for index, header in enumerate(headers):
        canonical = resolve_header(header)
        if canonical is None:
            mapping.append(None)
            continue
        if canonical in seen:
            errors.append(ImportErrorInfo(
                row_number=0,
                field=canonical,
                error_code=E_DUPLICATE_HEADER,
                message=(
                    f"Columns '{headers[seen[canonical]]}' and '{header}' "
                    f"both map to '{canonical}'."
                ),
            ))
            mapping.append(None)
            continue
        seen[canonical] = index
        mapping.append(canonical)

    return mapping, errors


def map_row(mapping: List[Optional[str]], cells: List[Any], row_number: int) -> Dict[str, Any]:
    """Map one raw row's cells onto canonical field names."""
    values: Dict[str, Any] = {}
    width = min(len(mapping), len(cells))
    for index in range(width):
        canonical = mapping[index]
        if canonical is not None:
            values[canonical] = cells[index]
    values[ROW_NUMBER_KEY] = row_number
    return values


@dataclass
class InvoiceGroup:
    """The rows of a single invoice collected from an accounting file.

    Attributes:
        key: Grouping key (uuid when present, else invoice_number).
        uuid: Group invoice UUID, if any.
        invoice_number: Group invoice number.
        row_numbers: File line numbers of the group's rows.
        invoice_values: Canonical invoice-level values (first row).
        item_values: Canonical item-level values, one per line item.
        raw_rows: Raw cell lists for the group, in file order.
        errors: Group-level errors reported for this group.
        first_row: Lowest row number in the group.
    """

    key: str
    uuid: Optional[str]
    invoice_number: Optional[str]
    row_numbers: List[int] = field(default_factory=list)
    invoice_values: Dict[str, Any] = field(default_factory=dict)
    item_values: List[Dict[str, Any]] = field(default_factory=list)
    raw_rows: List[List[Any]] = field(default_factory=list)
    errors: List[ImportErrorInfo] = field(default_factory=list)

    @property
    def first_row(self) -> int:
        return self.row_numbers[0] if self.row_numbers else 0

    def add_row(self, row: Dict[str, Any], raw_cells: List[Any]) -> None:
        """Merge a normalized row into this group, flagging conflicts."""

        for field_name in INVOICE_LEVEL_FIELDS:
            value = row.get(field_name)
            if value is None:
                continue
            if field_name in self.invoice_values:
                if self.invoice_values[field_name] != value:
                    self.errors.append(ImportErrorInfo(
                        row_number=row[ROW_NUMBER_KEY],
                        field=field_name,
                        error_code=E_INCONSISTENT_GROUP,
                        message=(
                            f"Row value '{value}' for '{field_name}' conflicts "
                            f"with '{self.invoice_values[field_name]}' declared "
                            "elsewhere in the same invoice."
                        ),
                    ))
                continue
            self.invoice_values[field_name] = value

        self.row_numbers.append(row[ROW_NUMBER_KEY])
        self.raw_rows.append(list(raw_cells))
        item = {name: row.get(name) for name in ITEM_LEVEL_FIELDS if row.get(name) is not None}
        self.item_values.append(item)


def group_rows(
    rows: List[Dict[str, Any]],
    raw_rows_by_number: Dict[int, List[Any]],
) -> Tuple[List[InvoiceGroup], List[ImportErrorInfo]]:
    """Group normalized rows into invoices.

    Args:
        rows: Normalized rows (parallel to their items).
        raw_rows_by_number: File line number -> raw cells, for reporting.

    Returns:
        A ``(groups, errors)`` tuple. Groups are ordered by first
        appearance in the file; errors are rows that could not be
        assigned to any invoice.
    """
    groups: List[InvoiceGroup] = []
    by_key: Dict[str, InvoiceGroup] = {}
    errors: List[ImportErrorInfo] = []

    for row in rows:
        uuid = row.get("uuid")
        invoice_number = row.get("invoice_number")
        key = uuid or invoice_number
        raw_cells = raw_rows_by_number.get(row[ROW_NUMBER_KEY], [])

        if not key:
            errors.append(ImportErrorInfo(
                row_number=row[ROW_NUMBER_KEY],
                field="invoice_number",
                error_code=E_INCONSISTENT_GROUP,
                message="Row has neither a uuid nor an invoice_number to group on.",
            ))
            continue

        group = by_key.get(key)
        if group is None:
            group = InvoiceGroup(key=key, uuid=uuid, invoice_number=invoice_number)
            by_key[key] = group
            groups.append(group)

        group.add_row(row, raw_cells)

    return groups, errors