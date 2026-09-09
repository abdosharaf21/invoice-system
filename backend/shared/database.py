"""Shared database access helpers for repositories.

Provides a context manager that centralizes cursor creation and cleanup
so repositories never repeat the open/close cursor boilerplate.
"""

from contextlib import contextmanager
from typing import Iterator


@contextmanager
def db_cursor(connection, **kwargs) -> Iterator:
    """Yield a cursor for the given connection and close it on exit.

    Args:
        connection: An open database connection.
        **kwargs: Cursor factory options (e.g. dictionary=True).

    Yields:
        A configured cursor bound to the connection.
    """
    cursor = connection.cursor(**kwargs)
    try:
        yield cursor
    finally:
        cursor.close()
