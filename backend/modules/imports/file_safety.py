"""File-level safety checks for accounting import uploads.

An uploaded file is validated before anything is parsed or persisted:

* the extension must be a supported accounting format (.csv/.xlsx),
* the reported size must be within the configured limit,
* the filename must be a plain basename (no path traversal),
* the content must actually look like the declared format.

Failures produce a single :class:`ImportErrorInfo` with ``row_number=0``
so callers can surface the problem with the same structured shape used
for row-level errors.
"""

import os
import re
from typing import Optional, Tuple

from backend.modules.imports.contract import MAX_FILE_SIZE, UPLOAD_EXTENSIONS
from backend.modules.imports.errors import E_FILE_ERROR, ImportErrorInfo

_ZIP_MAGIC = b"PK\x03\x04"
_CSV_CONTROL = re.compile(rb"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_ABSOLUTE_PATH = re.compile(r"^[A-Za-z]:[\\/]|^[\\/]")


def _looks_like_text(content: bytes) -> bool:
    if not content:
        return False
    sample = content[:8192]
    if b"\x00" in sample:
        return False
    printable = sum(1 for byte in sample if 32 <= byte <= 126 or byte in (9, 10, 13))
    return printable / len(sample) >= 0.9


def _validate_filename(filename: str) -> Optional[ImportErrorInfo]:
    if not filename or filename != os.path.basename(filename):
        return ImportErrorInfo(
            row_number=0,
            field="filename",
            error_code=E_FILE_ERROR,
            message="Filename must be a plain file name without a path.",
        )
    if _ABSOLUTE_PATH.match(filename):
        return ImportErrorInfo(
            row_number=0,
            field="filename",
            error_code=E_FILE_ERROR,
            message="Filename must not contain a path.",
        )
    if "\x00" in filename:
        return ImportErrorInfo(
            row_number=0,
            field="filename",
            error_code=E_FILE_ERROR,
            message="Filename contains invalid characters.",
        )
    return None


def validate_file(
    filename: str,
    content_type: str,
    content: bytes,
) -> Tuple[Optional[str], Optional[ImportErrorInfo]]:
    """Validate an uploaded accounting file.

    Args:
        filename: Multipart upload filename.
        content_type: Client-reported Content-Type header.
        content: Raw uploaded bytes.

    Returns:
        A ``(file_type, error)`` tuple. ``file_type`` is the normalized
        parser key ('csv' or 'xlsx') and is set only when the checks
        pass; ``error`` is None when the file is acceptable.
    """
    name_error = _validate_filename(filename)
    if name_error:
        return None, name_error

    ext = os.path.splitext(filename)[1].lower()
    if ext not in UPLOAD_EXTENSIONS:
        return None, ImportErrorInfo(
            row_number=0,
            field="filename",
            error_code=E_FILE_ERROR,
            message=(
                f"Unsupported file type '{ext or '(none)'}'. "
                f"Supported formats: {', '.join(sorted(UPLOAD_EXTENSIONS))}."
            ),
        )

    if len(content) > MAX_FILE_SIZE:
        size_mb = MAX_FILE_SIZE / (1024 * 1024)
        return None, ImportErrorInfo(
            row_number=0,
            field="file_size",
            error_code=E_FILE_ERROR,
            message=f"File exceeds the maximum size of {size_mb:.0f} MB.",
        )

    if ext == ".csv":
        if content_type and not content_type.lower().startswith("text/"):
            if not _looks_like_text(content):
                return None, ImportErrorInfo(
                    row_number=0,
                    field="file_content",
                    error_code=E_FILE_ERROR,
                    message="File content does not match the CSV format.",
                )
        if not _looks_like_text(content):
            return None, ImportErrorInfo(
                row_number=0,
                field="file_content",
                error_code=E_FILE_ERROR,
                message="File content does not look like a plain-text CSV.",
            )
        if _CSV_CONTROL.search(content[:8192]):
            return None, ImportErrorInfo(
                row_number=0,
                field="file_content",
                error_code=E_FILE_ERROR,
                message="CSV content contains unexpected control characters.",
            )
        file_type = "csv"
    elif ext == ".xlsx":
        if content[:4] != _ZIP_MAGIC:
            return None, ImportErrorInfo(
                row_number=0,
                field="file_content",
                error_code=E_FILE_ERROR,
                message="File content does not look like a valid XLSX workbook.",
            )
        file_type = "xlsx"
    else:
        return None, ImportErrorInfo(
            row_number=0,
            field="filename",
            error_code=E_FILE_ERROR,
            message=f"Unsupported file type '{ext}'.",
        )

    return file_type, None