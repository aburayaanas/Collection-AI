import oracledb
import logging
from contextlib import contextmanager
from typing import Generator
from src.core.config import settings

logger = logging.getLogger(__name__)

class OracleDatabase:
    def __init__(self):
        self._pool = None

    def initialize_pool(self):
        """
        Initializes the connection pool. 
        Call this ONLY ONCE at the start of your main.py.
        """
        if self._pool is not None:
            logger.warning("Database pool already initialized.")
            return

        if not settings.DB_USER or not settings.DB_DSN or not settings.DB_PASSWORD.get_secret_value():
            raise RuntimeError(
                "Database credentials are not configured (DB_USER/DB_PASSWORD/DB_DSN). "
                "Open the Configuration app's Database tab and save valid credentials, "
                "or set them in .env directly."
            )

        try:
            self._pool = oracledb.create_pool(
                user=settings.DB_USER,
                password=settings.DB_PASSWORD.get_secret_value(),
                dsn=settings.DB_DSN,
                min=settings.DB_MIN_POOL,
                max=settings.DB_MAX_POOL,
                increment=1,
                getmode=oracledb.POOL_GETMODE_WAIT,
            )
            logger.info(
                f"Pool config: min={settings.DB_MIN_POOL}, max={settings.DB_MAX_POOL}"
            )
            logger.info("Oracle Connection Pool initialized successfully (Thin Mode).")
        except oracledb.Error as e:
            logger.critical(f"Failed to connect to Oracle Database: {e}")
            raise

    def close_pool(self):
        """Closes the entire pool. Call this on app shutdown."""
        if self._pool:
            self._pool.close()
            self._pool = None
            logger.info("Oracle Connection Pool closed.")

    @contextmanager
    def get_connection(self) -> Generator[oracledb.Connection, None, None]:
        """
        Usage:
            with db.get_connection() as conn:
                cursor = conn.cursor()
                ...
        
        Handles getting a connection from the pool and putting it back automatically.
        """
        if self._pool is None:
            raise Exception("Database pool not initialized. Call db.initialize_pool() first.")

        connection = None
        try:
            connection = self._pool.acquire()
            yield connection

        except oracledb.Error as e:
            if connection:
                connection.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            if connection:
                self._pool.release(connection)


db = OracleDatabase()