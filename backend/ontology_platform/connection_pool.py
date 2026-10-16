"""Reusable platform-database connections, keyed by the context that owns their state.

`docs/limitations.md` recorded "no connection pooling" with a reason and no design. The reason
was right and incomplete: a pool is unsafe if it hands a connection to a caller who asked for a
different tenant, and the fix is not to avoid pooling but to **key the pool by everything the
connection's session state depends on**.

That key is `(db type, connection URI, schema)`, and it is exactly the set of things each
adapter configures when it opens a connection -- PostgreSQL sets `search_path` to the tenant's
schema, MySQL sets the session time zone. Two contexts that differ in any of the three differ in
what a borrowed connection would be *pointed at*, so they can never share one. A pool keyed this
way cannot leak across tenants, because borrowing for tenant B misses the entry tenant A left.

## What is not pooled, and why it is correctness rather than taste

**SQLite is never pooled.** `sqlite3.connect` defaults to `check_same_thread=True`, so a
connection may only be used from the thread that opened it. A pool is thread-safe by
construction -- that is the point of it -- and a thread-safe pool that hands one thread's SQLite
connection to another raises `ProgrammingError` at the point of use, inside whichever query
happened to run first. The same reasoning applies to the open file handle each connection holds.
The platform database is SQLite in most deployments, so this is the common case, not an edge.

**An exhausted pool opens a new connection rather than waiting.** Blocking would turn a
thread-pool thread into a queue slot, and a bounded wait is a latency cliff that appears only
under the load that made the pool necessary. Opening one more is what the code did before the
pool existed, and it degrades to exactly that behaviour.

## What returns a connection

`PlatformConnection.close()` does, and that is the only path. The `with` block's `__exit__`
commits or rolls back first, so a returned connection has no open transaction; the release path
rolls back again anyway, because a caller that never entered the `with` block could still have
one open, and the next borrower inheriting it would be a defect that shows up in somebody else's
request. A rollback that itself fails means the connection is in an unknown state, and it is
closed rather than returned.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable

logger = logging.getLogger(__name__)

__all__ = ["ConnectionPool", "pool_for"]

# How many idle connections to keep per key. Small: the point is to avoid a handshake per
# request, not to pre-open an arbitrary number. Beyond this the oldest is closed.
_MAX_IDLE_PER_KEY = 8


class ConnectionPool:
    """Idle driver connections, keyed by the session state they were opened with.

    Thread-safe: `acquire` and `release` take a lock, and the lock is held only while the
    bookkeeping happens -- never across the `factory()` call that opens a connection, which
    would serialise every request in the process on one mutex.
    """

    def __init__(self, size: int = 0) -> None:
        self.size = max(0, int(size))
        self._idle: dict[tuple[str, str, str], list[Any]] = {}
        self._lock = threading.Lock()
        self.opened = 0
        self.reused = 0

    @property
    def enabled(self) -> bool:
        return self.size > 0

    def acquire(self, key: tuple[str, str, str], factory: Callable[[], Any]) -> Any:
        """A connection for this key: an idle one if there is one, otherwise a new one."""
        if not self.enabled:
            return factory()
        with self._lock:
            idle = self._idle.get(key)
            if idle:
                connection = idle.pop()
                self.reused += 1
                return connection
        # Outside the lock: opening a connection can take a network round trip, and holding the
        # mutex across it would make the pool a serialisation point worse than no pool.
        connection = factory()
        self.opened += 1
        return connection

    def release(self, key: tuple[str, str, str], connection: Any) -> None:
        """Return a connection, or close it if it cannot be returned safely.

        The rollback is unconditional. `PlatformConnection.__exit__` has already settled the
        transaction in the ordinary case, so this is usually a no-op -- and in the case where it
        is not, it is the difference between a stale transaction being rolled back here and being
        inherited by whichever request borrows this connection next.
        """
        if not self.enabled or connection is None:
            return
        try:
            if hasattr(connection, "rollback"):
                connection.rollback()
            if getattr(connection, "closed", False):
                # psycopg marks a connection closed rather than raising on use.
                raise RuntimeError("connection is closed")
        except Exception as error:
            logger.warning("连接无法安全归还，已关闭: %s", error)
            self.discard(connection)
            return
        with self._lock:
            bucket = self._idle.setdefault(key, [])
            if len(bucket) >= _MAX_IDLE_PER_KEY:
                # Over the idle cap for this key. The oldest goes, so the pool tracks the
                # connections actually in rotation rather than the first ones ever opened.
                stale = bucket.pop(0)
                self._close_quietly(stale)
            bucket.append(connection)

    def discard(self, connection: Any) -> None:
        self._close_quietly(connection)

    def clear(self) -> None:
        """Close every idle connection. For tests, and for a clean shutdown."""
        with self._lock:
            buckets = list(self._idle.values())
            self._idle.clear()
        for bucket in buckets:
            for connection in bucket:
                self._close_quietly(connection)

    @staticmethod
    def _close_quietly(connection: Any) -> None:
        try:
            if hasattr(connection, "close"):
                connection.close()
        except Exception as error:  # pragma: no cover - driver-specific
            logger.warning("关闭连接失败: %s", error)


# One pool per process, sized from the configuration. A module-level object rather than state on
# the context, because a pool per context would be a pool that never sees a second borrower.
_pool: ConnectionPool | None = None
_pool_lock = threading.Lock()


def pool_for(size: int | None = None) -> ConnectionPool:
    """The process's pool, sized from `ONTOLOGY_CONNECTION_POOL_SIZE` unless told otherwise."""
    global _pool
    with _pool_lock:
        if _pool is None:
            if size is None:
                from .config import CONNECTION_POOL

                size = CONNECTION_POOL.size
            _pool = ConnectionPool(size)
        return _pool


def _reset_pool(size: int | None = None) -> ConnectionPool:
    """Rebuild the process pool. Tests and a configuration reload."""
    global _pool
    with _pool_lock:
        if _pool is not None:
            _pool.clear()
        _pool = ConnectionPool(size if size is not None else 0)
        return _pool
