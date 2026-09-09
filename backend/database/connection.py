"""Database connection pool manager for MySQL."""

import logging
from contextlib import contextmanager
from typing import Generator, Optional

import mysql.connector
from mysql.connector import MySQLConnection
from mysql.connector.pooling import MySQLConnectionPool, PoolError

from backend.database.config import DatabaseConfig, get_database_config

logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """Base exception for database operations."""


class DatabaseConnectionError(DatabaseError):
    """Raised when a connection cannot be obtained from the pool."""


class Database:
    """Manages a reusable MySQL connection pool.

    Provides thread-safe connection borrowing and returning
    via a context manager. Handles pool creation, connection
    validation, and graceful error handling.
    """

    def __init__(self, config: Optional[DatabaseConfig] = None) -> None:
        """Initialize the Database with configuration.

        Args:
            config: Optional DatabaseConfig. If None, loads from
                environment variables.
        """
        self._config = config or get_database_config()
        self._pool: Optional[MySQLConnectionPool] = None
        self._initialize_pool()

    def _initialize_pool(self) -> None:
        """Create the connection pool.

        Raises:
            DatabaseError: If pool creation fails.
        """
        try:
            pool_args = self._config.to_pool_args()
            self._pool = MySQLConnectionPool(**pool_args)
            logger.info(
                "Connection pool '%s' created with size %d",
                self._config.pool_name,
                self._config.pool_size,
            )
        except PoolError as e:
            logger.error("Failed to create connection pool: %s", e)
            raise DatabaseError(f"Pool creation failed: {e}") from e
        except mysql.connector.Error as e:
            logger.error("MySQL error during pool creation: %s", e)
            raise DatabaseError(f"Pool initialization failed: {e}") from e

    @contextmanager
    def connection(self) -> Generator[MySQLConnection, None, None]:
        """Borrow a connection from the pool and return it after use.

        Yields:
            MySQLConnection from the pool.

        Raises:
            DatabaseConnectionError: If no connection is available.
        """
        conn: Optional[MySQLConnection] = None
        try:
            conn = self._pool.get_connection()
            yield conn
        except PoolError as e:
            logger.error("Failed to get connection from pool: %s", e)
            raise DatabaseConnectionError(f"Connection unavailable: {e}") from e
        finally:
            if conn is not None:
                self._return_connection(conn)

    def _return_connection(self, conn: MySQLConnection) -> None:
        """Return a connection to the pool.

        If the connection is disconnected, attempt to replenish the
        pool with a fresh connection to maintain the configured pool size.

        Args:
            conn: The connection to return.
        """
        try:
            if conn.is_connected():
                raw = getattr(conn, "_cnx", conn)
                try:
                    raw.reset_session()
                except mysql.connector.Error:
                    conn.close()
                    return
                self._pool.add_connection(raw)
            else:
                self._replenish_pool()
        except PoolError:
            pass

    def _replenish_pool(self) -> None:
        """Replace a dropped connection to maintain pool size."""
        try:
            pool_args = self._config.to_pool_args()
            conn = MySQLConnection(**pool_args)
            self._pool.add_connection(conn)
            logger.info("Pool connection replenished")
        except (PoolError, mysql.connector.Error) as e:
            logger.warning("Failed to replenish pool connection: %s", e)

    def close_all(self) -> None:
        """Close all idle connections in the pool.

        Should be called once during application shutdown (e.g. via
        ``atexit`` or a ``SIGTERM`` handler), NOT per-request.
        """
        if self._pool is None:
            return

        try:
            pool_mutex = getattr(self._pool, "_pool_mutex", None)
            pool_queue = getattr(self._pool, "_pool", None)

            if pool_mutex is not None and pool_queue is not None:
                with pool_mutex:
                    closed = 0
                    while not pool_queue.empty():
                        try:
                            conn = pool_queue.get_nowait()
                            if conn.is_connected():
                                conn.close()
                                closed += 1
                        except (PoolError, AttributeError):
                            break
                logger.info("Pool closed: %d connections released", closed)
            else:
                logger.info("Pool shutdown: internal attributes unavailable, skipping manual close")
        except Exception as e:
            logger.warning("Error during pool shutdown: %s", e)

    @property
    def pool_size(self) -> int:
        """Get the configured pool size."""
        return self._config.pool_size

    @property
    def is_healthy(self) -> bool:
        """Check if the database pool is operational."""
        try:
            with self.connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                cursor.fetchone()
                cursor.close()
            return True
        except Exception as e:
            logger.error("Database health check failed: %s", e)
            return False

    def __repr__(self) -> str:
        return (
            f"Database(pool={self._config.pool_name!r}, "
            f"size={self._config.pool_size})"
        )
