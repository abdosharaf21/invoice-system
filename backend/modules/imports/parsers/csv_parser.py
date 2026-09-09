"""CSV file parser for accounting imports.

Handles the messy reality of CSV files exported from accounting
software: different delimiters (comma, semicolon, tab), a UTF-8 BOM,
and rows whose number of cells does not match the header row. Rows are
padded with empty strings so every row reports the same column count.
"""

import csv
import io

from backend.modules.imports.parsers.base import FileParseError, FileParser, ParsedFile

_DELIMITERS = (",", ";", "\t", "|")

_BOM = "\ufeff"


def _sniff_delimiter(sample: str) -> str:
    best = ","
    best_score = -1
    first_line = sample.splitlines()[0] if sample.splitlines() else ""
    for delimiter in _DELIMITERS:
        score = first_line.count(delimiter)
        if score > best_score:
            best = delimiter
            best_score = score
    return best


def _clean_cell(value) -> str:
    if value is None:
        return ""
    text = str(value)
    return text.lstrip(_BOM)


class CsvParser(FileParser):
    """Parses comma/semicolon/tab delimited accounting files."""

    @property
    def file_type(self) -> str:
        return "csv"

    def parse(self, content: bytes) -> ParsedFile:
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise FileParseError("CSV file must be UTF-8 encoded")

        if text.startswith(_BOM):
            text = text[len(_BOM):]

        sample = text[:4096]
        delimiter = _sniff_delimiter(sample)

        reader = csv.reader(io.StringIO(text), delimiter=delimiter)
        try:
            rows = [ [ _clean_cell(cell) for cell in row ] for row in reader ]
        except csv.Error as e:
            raise FileParseError(f"Could not parse CSV content: {e}")

        rows = [row for row in rows if any(cell != "" for cell in row)]
        if not rows:
            raise FileParseError("CSV file is empty")

        headers = rows[0]
        header_width = len(headers)
        data_rows = [
            row + [""] * (header_width - len(row))
            if len(row) < header_width else row[:header_width]
            for row in rows[1:]
        ]
        return ParsedFile(headers=headers, rows=data_rows)