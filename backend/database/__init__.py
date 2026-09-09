"""Database package for the E-Invoice System.

Provides a production-ready connection pool for MySQL with
environment-based configuration.
"""

from backend.database.connection import Database, DatabaseError, DatabaseConnectionError
from backend.database.config import DatabaseConfig, get_database_config

__all__ = [
    "Database",
    "DatabaseConfig",
    "DatabaseError",
    "DatabaseConnectionError",
    "get_database_config",
]
