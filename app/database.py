"""Database connection and schema management for X Research Collector."""

import psycopg2
import psycopg2.extras
from contextlib import contextmanager
from app.config import Config
from app.logging_config import setup_logging

logger = setup_logging()


class Database:
    """PostgreSQL database connection manager."""

    def __init__(self, config: Config):
        self.config = config
        self._conn = None

    def connect(self):
        """Establish database connection."""
        try:
            self._conn = psycopg2.connect(
                host=self.config.db_host,
                port=self.config.db_port,
                dbname=self.config.db_name,
                user=self.config.db_user,
                password=self.config.db_password,
            )
            self._conn.autocommit = False
            logger.info("Database connection established")
        except psycopg2.Error as e:
            logger.error(f"Database connection failed: {e}")
            raise

    def close(self):
        """Close the database connection."""
        if self._conn and not self._conn.closed:
            self._conn.close()
            logger.info("Database connection closed")

    @contextmanager
    def cursor(self):
        """Context manager for database cursor."""
        if not self._conn or self._conn.closed:
            self.connect()
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        try:
            yield cur
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        finally:
            cur.close()

    def initialize_schema(self):
        """Create tables if they don't exist."""
        import os
        schema_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sql", "schema.sql")

        with open(schema_path, "r") as f:
            schema_sql = f.read()

        with self.cursor() as cur:
            cur.execute(schema_sql)

        logger.info("Database schema initialized")

    @property
    def connection(self):
        """Get the raw connection."""
        if not self._conn or self._conn.closed:
            self.connect()
        return self._conn
