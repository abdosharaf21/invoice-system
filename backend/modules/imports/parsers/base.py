"""File parser abstraction for accounting imports.

A :class:`FileParser` turns the bytes of an uploaded file into a
header row and a list of raw data rows. Parsers are format-specific
(CSV vs XLSX) and registered in the parser registry so the import
service can resolve the right parser from a file extension without
importing every format directly.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, List


class FileParseError(Exception):
    """Raised when a file cannot be read as its declared format."""


@dataclass
class ParsedFile:
    """Result of parsing an accounting file's rows.

    Attributes:
        headers: Raw header cells in file order.
        rows: Raw data row cells; each row has exactly as many cells
            as there are headers (missing trailing cells are padded).
        total_rows: Number of data rows.
    """

    headers: List[Any]
    rows: List[List[Any]]
    total_rows: int = 0

    def __post_init__(self) -> None:
        self.total_rows = len(self.rows)


class FileParser(ABC):
    """Base class for format-specific file parsers."""

    @property
    @abstractmethod
    def file_type(self) -> str:
        """Registry key for this parser (e.g. 'csv', 'xlsx')."""

    @abstractmethod
    def parse(self, content: bytes) -> ParsedFile:
        """Parse raw file content into a ParsedFile.

        Raises:
            FileParseError: If the content cannot be parsed.
        """