"""Structured error model for accounting file imports.

Every row- or group-level problem found while importing a file is
converted into an :class:`ImportErrorInfo` and persisted as an
``import_batch_errors`` row. The payload is designed to be actionable:
users see *where* the problem is (row + field), *what* kind of problem
it is (error code) and *why* (message).

Error codes are stable strings and can be referenced by fix-up tooling
and by the frontend to render field-specific help.
"""

from dataclasses import dataclass
from typing import List, Optional

E_MISSING_FIELD = "MISSING_FIELD"
E_INVALID_UUID = "INVALID_UUID"
E_INVALID_DATE = "INVALID_DATE"
E_INVALID_MONEY = "INVALID_MONEY"
E_INVALID_QUANTITY = "INVALID_QUANTITY"
E_INVALID_ENUM = "INVALID_ENUM"
E_MISSING_HEADER = "MISSING_HEADER"
E_DUPLICATE_HEADER = "DUPLICATE_HEADER"
E_UNKNOWN_HEADER = "UNKNOWN_HEADER"
E_INCONSISTENT_GROUP = "INCONSISTENT_GROUP"
E_DUPLICATE_IN_FILE = "DUPLICATE_IN_FILE"
E_DUPLICATE_IN_DB = "DUPLICATE_IN_DB"
E_FILE_ERROR = "FILE_ERROR"


@dataclass
class ImportErrorInfo:
    """A single structured import error.

    Attributes:
        row_number: 1-based line number in the source file.
        field: Canonical field name the error belongs to, if any.
        error_code: Stable machine-readable error code.
        message: Human-readable description of the problem.
        raw_data: Optional serialized raw row for debugging/fix-up.
    """

    row_number: int
    error_code: str
    message: str
    field: Optional[str] = None
    raw_data: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "row_number": self.row_number,
            "field": self.field,
            "error_code": self.error_code,
            "message": self.message,
        }


def format_raw_row(cells: list) -> str:
    """Serialize a list of raw cells to a compact text string."""
    return ",".join("" if cell is None else str(cell) for cell in cells)


def aggregate_errors(errors: List[ImportErrorInfo]) -> List[dict]:
    """Convert error objects to their dict representation."""
    return [error.to_dict() for error in errors]