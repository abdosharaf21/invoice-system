"""XLSX file parser for accounting imports.

Reads the first worksheet of an .xlsx workbook into the same interleaved
row structure produced by the CSV parser. Cells are converted to plain
text/date/number representations that the normalizer understands, so the
rest of the pipeline is format-agnostic.
"""

import io
import zipfile
from typing import Any

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from backend.modules.imports.parsers.base import FileParseError, FileParser, ParsedFile


def _cell_to_value(cell) -> Any:
    if cell.value is None:
        return ""
    value = cell.value
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    return value


class XlsxParser(FileParser):
    """Parses the first worksheet of an .xlsx workbook."""

    @property
    def file_type(self) -> str:
        return "xlsx"

    def parse(self, content: bytes) -> ParsedFile:
        try:
            workbook = load_workbook(
                io.BytesIO(content),
                read_only=True,
                data_only=True,
            )
        except (InvalidFileException, zipfile.BadZipFile, KeyError, ValueError, OSError) as e:
            raise FileParseError(f"Could not read XLSX content: {e}")

        sheet = workbook.worksheets[0]
        rows = [
            [_cell_to_value(cell) for cell in row]
            for row in sheet.iter_rows()
        ]
        workbook.close()

        rows = [row for row in rows if any(str(cell).strip() != "" for cell in row)]
        if not rows:
            raise FileParseError("XLSX file is empty")

        headers = [_as_header(cell) for cell in rows[0]]
        header_width = len(headers)
        data_rows = [
            row + [""] * (header_width - len(row))
            if len(row) < header_width else row[:header_width]
            for row in rows[1:]
        ]
        return ParsedFile(headers=headers, rows=data_rows)


def _as_header(cell: Any) -> str:
    if isinstance(cell, str):
        return cell
    return "" if cell is None else str(cell)