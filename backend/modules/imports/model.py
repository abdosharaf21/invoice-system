"""Import models representing the import_batches and import_batch_errors tables."""

from datetime import datetime
from typing import Optional


def _parse_datetime(value):
    if value and isinstance(value, str):
        return datetime.fromisoformat(value)
    return value


class ImportBatchError:
    """Represents a row-level error captured during an import."""

    def __init__(
        self,
        id: Optional[int] = None,
        batch_id: Optional[int] = None,
        row_number: Optional[int] = None,
        error_message: Optional[str] = None,
        raw_data: Optional[str] = None,
        created_at: Optional[datetime] = None
    ) -> None:
        self.id = id
        self.batch_id = batch_id
        self.row_number = row_number
        self.error_message = error_message
        self.raw_data = raw_data
        self.created_at = created_at or datetime.now()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "batch_id": self.batch_id,
            "row_number": self.row_number,
            "error_message": self.error_message,
            "raw_data": self.raw_data,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ImportBatchError":
        return cls(
            id=data.get("id"),
            batch_id=data.get("batch_id"),
            row_number=data.get("row_number"),
            error_message=data.get("error_message"),
            raw_data=data.get("raw_data"),
            created_at=_parse_datetime(data.get("created_at"))
        )

    def __repr__(self) -> str:
        return f"ImportBatchError(id={self.id}, row={self.row_number})"


class ImportBatch:
    """Represents an upload/import of invoice data in the import_batches table.

    Tracks the lifecycle of a file import (CSV/Excel) so progress and
    per-row errors can be monitored. Individual rows that fail are
    recorded as ImportBatchError records.
    """

    def __init__(
        self,
        id: Optional[int] = None,
        company_id: Optional[int] = None,
        filename: Optional[str] = None,
        file_type: str = "csv",
        status: str = "uploaded",
        total_rows: int = 0,
        processed_rows: int = 0,
        error_rows: int = 0,
        uploaded_by: Optional[int] = None,
        started_at: Optional[datetime] = None,
        finished_at: Optional[datetime] = None,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None
    ) -> None:
        self.id = id
        self.company_id = company_id
        self.filename = filename
        self.file_type = file_type
        self.status = status
        self.total_rows = total_rows
        self.processed_rows = processed_rows
        self.error_rows = error_rows
        self.uploaded_by = uploaded_by
        self.started_at = started_at
        self.finished_at = finished_at
        self.created_at = created_at or datetime.now()
        self.updated_at = updated_at or datetime.now()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "company_id": self.company_id,
            "filename": self.filename,
            "file_type": self.file_type,
            "status": self.status,
            "total_rows": self.total_rows,
            "processed_rows": self.processed_rows,
            "error_rows": self.error_rows,
            "uploaded_by": self.uploaded_by,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ImportBatch":
        return cls(
            id=data.get("id"),
            company_id=data.get("company_id"),
            filename=data.get("filename"),
            file_type=data.get("file_type", "csv"),
            status=data.get("status", "uploaded"),
            total_rows=data.get("total_rows", 0),
            processed_rows=data.get("processed_rows", 0),
            error_rows=data.get("error_rows", 0),
            uploaded_by=data.get("uploaded_by"),
            started_at=_parse_datetime(data.get("started_at")),
            finished_at=_parse_datetime(data.get("finished_at")),
            created_at=_parse_datetime(data.get("created_at")),
            updated_at=_parse_datetime(data.get("updated_at"))
        )

    def __str__(self) -> str:
        return f"ImportBatch(id={self.id}, filename={self.filename}, status={self.status})"

    def __repr__(self) -> str:
        return self.__str__()