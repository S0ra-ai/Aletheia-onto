"""Platform context: the object that replaces the module-level singleton.

`database._platform_adapter` is a module-level global, so a process can hold
exactly one platform configuration. That blocks two things the framework needs:

- **Multi-tenancy** (ADR-0006). Per-tenant schema routing requires a connection
  bound to a tenant, which a single global cannot express.
- **Testing and embedding.** Verifying two dialects in one process, or embedding
  the kernel twice in one application, is currently impossible.

A `PlatformContext` carries what the global held -- dialect, connection URI, cached
adapter -- plus the tenant identity that multi-tenancy will need. Contexts are
independent: creating one does not disturb another, and none of them disturbs the
process-wide default.

## Why the old API still works

156 function signatures take `platform_db: Path | str`. Rewriting all of them in
one change would be a very large diff with the failure mode "missed one", and a
missed one in a tenancy context means cross-tenant data access. So this lands as a
*widening* rather than a replacement:

- `connect()` and `initialize_platform_db()` accept a `PlatformContext` wherever
  they accepted a path, because `resolve_context()` treats a path, a string, a
  context, or nothing as valid input.
- The global default remains for callers that never opt in.

That makes the migration incremental and reviewable: a module moves to explicit
contexts when it is touched, and both styles work meanwhile. `use_context()` marks
the boundary where a request-scoped context is bound.

Stability: experimental (ADR-0007).
"""

from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Optional, Union

logger = logging.getLogger(__name__)

# The tenant identifier used when a deployment is single-tenant. ADR-0006 chose
# separate schemas plus a tenant_id column; until that lands, everything runs in
# this one logical tenant, so the value exists to be threaded through rather than
# retrofitted later.
DEFAULT_TENANT = "default"


@dataclass
class PlatformContext:
    """One platform database binding.

    Holds the adapter so repeated `connect()` calls on the same context reuse it,
    matching what the global did. Not a connection pool -- that remains open work
    recorded in docs/architecture-debt.md.
    """

    db_type: str = "sqlite"
    connection_uri: str = ""
    tenant: str = DEFAULT_TENANT
    schema: str = ""
    _adapter: Optional[Any] = field(default=None, repr=False, compare=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def __post_init__(self) -> None:
        from .database import DEFAULT_PLATFORM_DB, _default_uri

        self.db_type = (self.db_type or "sqlite").lower()
        if not self.connection_uri:
            self.connection_uri = str(DEFAULT_PLATFORM_DB) if self.db_type == "sqlite" else _default_uri(self.db_type)

    @property
    def adapter(self) -> Any:
        """The adapter for this context, created once.

        Lock-guarded because FastAPI serves requests on a thread pool: two threads
        touching a fresh context would otherwise each build an adapter, and one
        would be silently discarded along with any state it held.
        """
        if self._adapter is None:
            with self._lock:
                if self._adapter is None:
                    from .database import _create_adapter

                    # Passing the schema is what activates per-tenant routing
                    # (ADR-0006); an empty schema keeps the single-tenant path.
                    self._adapter = _create_adapter(self.db_type, self.connection_uri, self.schema)
        return self._adapter

    def connect(self) -> Any:
        """A connection bound to this context."""
        from .database import PlatformConnection

        return PlatformConnection(self.adapter.connect(), self.adapter)

    def initialize(self) -> None:
        """Create the base schema for this context."""
        conn = self.adapter.connect()
        try:
            self.adapter.init_schema(conn)
        finally:
            try:
                conn.close()
            except Exception as error:  # pragma: no cover - driver-specific
                logger.warning("关闭平台库连接失败: %s", error)

    def describe(self) -> dict[str, Any]:
        """Diagnostic summary. Never includes the connection URI, which carries
        credentials -- see credentials.redact_connection_uri."""
        from .credentials import redact_connection_uri

        return {
            "dbType": self.db_type,
            "connectionUri": redact_connection_uri(self.connection_uri),
            "tenant": self.tenant,
            "schema": self.schema,
            "adapterReady": self._adapter is not None,
        }

    def for_tenant(self, tenant: str, *, schema: str = "") -> "PlatformContext":
        """A sibling context for another tenant.

        Returns a new context rather than mutating this one: a request handler must
        not be able to change the tenant of a context another request is using.
        The adapter is deliberately not shared, since per-tenant schema routing
        will need its own connection settings.
        """
        return PlatformContext(
            db_type=self.db_type,
            connection_uri=self.connection_uri,
            tenant=tenant or DEFAULT_TENANT,
            schema=schema,
        )


# -- Process-wide default --
#
# Kept so callers that never opt in behave exactly as before. Thread-local
# override on top, so binding a context for one request does not leak into
# another thread.

_default_context: Optional[PlatformContext] = None
_default_lock = threading.Lock()
_local = threading.local()


def configure_default_context(
    db_type: str = "sqlite", connection_uri: str = "", *, tenant: str = DEFAULT_TENANT
) -> PlatformContext:
    """Set the process-wide default context."""
    global _default_context
    with _default_lock:
        _default_context = PlatformContext(db_type=db_type, connection_uri=connection_uri, tenant=tenant)
    return _default_context


def get_default_context() -> Optional[PlatformContext]:
    return _default_context


def reset_default_context() -> None:
    """Drop the default context. Intended for tests."""
    global _default_context
    with _default_lock:
        _default_context = None


def current_context() -> Optional[PlatformContext]:
    """The context bound to this thread, else the process default."""
    bound = getattr(_local, "context", None)
    return bound if bound is not None else _default_context


@contextmanager
def use_context(context: PlatformContext) -> Iterator[PlatformContext]:
    """Bind a context for the current thread.

    This is the seam a request handler will use to pin a tenant. Thread-local
    rather than global because FastAPI handles requests concurrently, and the
    previous global would have let one request's binding affect another's.
    """
    previous = getattr(_local, "context", None)
    _local.context = context
    try:
        yield context
    finally:
        _local.context = previous


ContextLike = Union[PlatformContext, Path, str, None]


def resolve_context(source: ContextLike = None) -> PlatformContext:
    """Interpret whatever a caller passed as a context.

    Accepting four shapes is what lets 156 existing `platform_db: Path | str`
    signatures keep working untouched while new code passes a context explicitly:

    - a `PlatformContext` -- used directly
    - a path or non-empty string -- a SQLite file, the old default meaning
    - empty or None -- the thread-bound context, else the process default, else a
      fresh SQLite context on the default path

    Contexts built from a path are not cached: the old `connect(path)` created a
    fresh adapter per call, and caching here would change lifetime semantics for
    existing callers.
    """
    if isinstance(source, PlatformContext):
        return source
    if source not in (None, ""):
        return PlatformContext(db_type="sqlite", connection_uri=str(source))
    existing = current_context()
    if existing is not None:
        return existing
    from .database import DEFAULT_PLATFORM_DB

    return PlatformContext(db_type="sqlite", connection_uri=str(DEFAULT_PLATFORM_DB))
