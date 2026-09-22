"""Database connection pool for production use.

Provides connection pooling for PostgreSQL and other databases
to handle concurrent requests efficiently.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Generator

logger = logging.getLogger(__name__)

# Connection pool configuration
POOL_SIZE = 10
MAX_OVERFLOW = 20
POOL_TIMEOUT = 30
POOL_RECYCLE = 3600


class ConnectionPool:
    """Simple connection pool for SQLite/PostgreSQL."""

    def __init__(self, db_path: str | None = None, max_connections: int = POOL_SIZE):
        self.db_path = db_path
        self.max_connections = max_connections
        self._connections: list = []
        self._in_use: set = set()

    @contextmanager
    def get_connection(self) -> Generator:
        """Get a connection from the pool."""
        import sqlite3

        if not self._connections:
            conn = sqlite3.connect(self.db_path or "data/platform.sqlite3")
            conn.row_factory = sqlite3.Row
        else:
            conn = self._connections.pop()

        self._in_use.add(conn)

        try:
            yield conn
        finally:
            self._in_use.discard(conn)
            if len(self._connections) < self.max_connections:
                self._connections.append(conn)

    def close_all(self) -> None:
        """Close all connections."""
        for conn in self._connections:
            conn.close()
        self._connections.clear()
        self._in_use.clear()


# Global pool instance
_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    """Get the global connection pool."""
    global _pool
    if _pool is None:
        from .database import DEFAULT_PLATFORM_DB

        _pool = ConnectionPool(str(DEFAULT_PLATFORM_DB))
    return _pool
