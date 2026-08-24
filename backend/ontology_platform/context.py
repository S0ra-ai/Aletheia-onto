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

## Both a path and a context are accepted, everywhere

Every function taking `platform_db` is annotated `PlatformDb`, which is a context, a
path, or a string. The runtime always accepted all three -- each one resolves through
`connect()` / `resolve_context()` -- but the annotations said `Path | str`, and that
was worse than saying nothing: it told a type checker to **reject code that works**.
So multi-tenancy and embedding were documented as supported while being unreachable
for any downstream that runs mypy.

Widened rather than replaced. A hard switch to context-only would break every
existing caller for no behavioural gain, and the global default is what makes the
single-tenant case free of ceremony. `use_context()` marks the boundary where a
request-scoped context is bound.

Stability: experimental (ADR-0007).
"""

from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Optional, Union

from .credentials import redact_connection_uri

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
        from .database import DEFAULT_PLATFORM_DB, default_platform_uri

        self.db_type = (self.db_type or "sqlite").lower()
        if not self.connection_uri:
            self.connection_uri = (
                str(DEFAULT_PLATFORM_DB) if self.db_type == "sqlite" else default_platform_uri(self.db_type)
            )

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
                    from .database import create_platform_adapter

                    # Passing the schema is what activates per-tenant routing
                    # (ADR-0006); an empty schema keeps the single-tenant path.
                    self._adapter = create_platform_adapter(self.db_type, self.connection_uri, self.schema)
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

# What a function that *requires* a platform binding accepts. Separate from `ContextLike`
# because that one includes `None`, which means "use the process default" -- correct for
# `resolve_context`, wrong for a parameter the caller must supply. Annotating a required
# argument as optional would tell a type checker that omitting it is fine, and the failure
# would then be a runtime resolution against whatever default happened to be configured.
PlatformDb = Union[PlatformContext, Path, str]


def resolve_context(source: ContextLike = None) -> PlatformContext:
    """Interpret whatever a caller passed as a context.

    Accepting four shapes is what lets every `platform_db: PlatformDb`
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
