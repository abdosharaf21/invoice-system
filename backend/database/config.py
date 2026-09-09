"""Database configuration loaded from environment variables."""

import os
import logging
from dataclasses import dataclass, field

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()


@dataclass(frozen=True)
class DatabaseConfig:
    """Immutable database configuration.

    Reads all database connection parameters from environment
    variables via python-dotenv.

    Attributes:
        host: Database server hostname or IP.
        port: Database server port.
        name: Database name.
        user: Database username.
        password: Database password.
        pool_name: Name identifier for the connection pool.
        pool_size: Maximum number of connections in the pool.
        pool_reset_session: Actions to take when a connection is
            returned to the pool.
    """

    host: str = field(default_factory=lambda: os.getenv("DB_HOST", "localhost"))
    port: int = field(default_factory=lambda: int(os.getenv("DB_PORT", "3306")))
    name: str = field(default_factory=lambda: os.getenv("DB_NAME", "invoice_system"))
    user: str = field(default_factory=lambda: os.getenv("DB_USER", "invoice_app"))
    password: str = field(default_factory=lambda: os.getenv("DB_PASSWORD", ""))
    pool_name: str = field(default_factory=lambda: os.getenv("DB_POOL_NAME", "invoice_pool"))
    pool_size: int = field(default_factory=lambda: int(os.getenv("DB_POOL_SIZE", "5")))
    pool_reset_session: list = field(
        default_factory=lambda: ["ROLLBACK"]
    )

    def to_connection_args(self) -> dict:
        """Convert config to mysql.connector connection arguments.

        Returns:
            Dictionary suitable for mysql.connector.connect().
        """
        return {
            "host": self.host,
            "port": self.port,
            "database": self.name,
            "user": self.user,
            "password": self.password,
        }

    def to_pool_args(self) -> dict:
        """Convert config to MySQLConnectionPool arguments.

        Returns:
            Dictionary suitable for MySQLConnectionPool constructor.
        """
        return {
            "pool_name": self.pool_name,
            "pool_size": self.pool_size,
            "pool_reset_session": self.pool_reset_session,
            **self.to_connection_args(),
        }


def get_database_config() -> DatabaseConfig:
    """Factory function to create DatabaseConfig from environment.

    Returns:
        Frozen DatabaseConfig instance.
    """
    config = DatabaseConfig()
    logger.info(
        "Database config loaded: host=%s port=%s db=%s pool_size=%d",
        config.host,
        config.port,
        config.name,
        config.pool_size,
    )
    return config
