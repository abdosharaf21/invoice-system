"""Parser registry for accounting file imports.

Resolves a :class:`FileParser` from a file extension and keeps the
format-specific parser classes decoupled from the import service.
"""

from typing import Dict, Optional, Type

from backend.modules.imports.parsers.base import FileParser
from backend.modules.imports.parsers.csv_parser import CsvParser
from backend.modules.imports.parsers.xlsx_parser import XlsxParser

_PARSERS: Dict[str, Type[FileParser]] = {
    "csv": CsvParser,
    "xlsx": XlsxParser,
}

ALLOWED_EXTENSIONS = frozenset(_PARSERS.keys())


def get_parser(file_type: str) -> Optional[FileParser]:
    """Return a parser instance for the given file type key.

    Args:
        file_type: Lower-case extension without the dot (e.g. 'csv'),
            or any string ending in '.csv'/'.xlsx'.

    Returns:
        A parser instance, or None when the type is unsupported.
    """
    key = file_type.strip().lower().lstrip(".")
    parser_class = _PARSERS.get(key)
    return parser_class() if parser_class else None


__all__ = ["FileParser", "get_parser", "ALLOWED_EXTENSIONS", "CsvParser", "XlsxParser"]