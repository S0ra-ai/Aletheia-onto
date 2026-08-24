"""A data source adapter for any PEP 249 driver.

Generality item #12: Oracle / SQL Server / 达梦 / 人大金仓 are B2B table stakes, and
writing a bespoke adapter for each was the obvious-but-wrong answer. The three existing
adapters are almost entirely identical -- they differ in which module to import, how to
turn a URI into connect arguments, and six dialect details now declared in
`sql_dialects`. Everything else is the shared `information_schema` scanner.

So a new database is a **declaration**, not an implementation:

```python
from ontology_platform.generic_sql_adapter import DriverSpec, register_sql_source
from ontology_platform.sql_dialects import ORACLE

register_sql_source(DriverSpec(
    source_type="oracle",
    dialect=ORACLE,
    module="oracledb",
    install_hint="Oracle 接入需要安装 oracledb。",
))
```

That is the whole integration. It gets metadata scanning, column profiling, foreign key
discovery, instance resolution, every rule feature and the runtime reads.

## Why the platform does not ship these registrations enabled

Each needs a driver the kernel deliberately does not depend on, and several
(`oracledb` thick mode, 达梦's `dmPython`) need client libraries that cannot be
installed from PyPI alone. Shipping them as *specs* rather than as active adapters means
the platform can describe how to reach them -- `aletheia doctor` lists which are
available -- without claiming support it cannot demonstrate in CI.

`BUNDLED_SPECS` is the catalogue. `register_bundled_sql_sources()` activates whichever
drivers are actually installed, and reports what it skipped and why. A source type that
silently did not appear would look like a platform bug rather than a missing driver.

## Connection URIs stay opaque

`connect_arguments` receives the raw URI and returns driver kwargs. Deliberately not a
generic URI parser: Oracle service names, SQL Server instance names and DSN aliases are
not expressible as a common shape, and a parser that got 80% of them right would fail
confusingly on the rest. A spec that needs custom parsing supplies a callable.

Drivers that take the whole connection string disagree on what to call it -- psycopg
names it `conninfo`, oracledb `dsn`, sqlite3 takes it positionally. So a spec can pass it
as a positional argument (`passes_uri_positionally`) instead of guessing a keyword; a
wrong guess surfaces as `invalid connection option "dsn"`, which reads as a
configuration error rather than as a spec mistake.

Stability: experimental (ADR-0007).
"""

from __future__ import annotations

import importlib
import logging
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, Optional
from urllib.parse import parse_qsl, urlparse

from .adapters import (
    SourceTableInfo,
    SQLRuntime,
    connection_status,
    register_adapter,
    scan_information_schema,
)
from .sql_dialects import DAMENG, KINGBASE, ORACLE, POSTGRESQL, SQLSERVER, SqlDialect

logger = logging.getLogger(__name__)


class DriverError(RuntimeError):
    """Raised when a declared driver is unavailable or a spec is invalid."""


def default_connect_arguments(connection_uri: str) -> dict[str, Any]:
    """Turn a URL-shaped connection string into common DB-API kwargs.

    Covers the `scheme://user:pass@host:port/database?k=v` shape that most drivers
    accept. A driver whose connection string is not URL-shaped supplies its own
    callable rather than being forced through this.
    """
    parsed = urlparse(connection_uri)
    arguments: dict[str, Any] = {}
    if parsed.hostname:
        arguments["host"] = parsed.hostname
    if parsed.port:
        arguments["port"] = parsed.port
    if parsed.username:
        arguments["user"] = parsed.username
    if parsed.password:
        arguments["password"] = parsed.password
    database = (parsed.path or "").lstrip("/")
    if database:
        arguments["database"] = database
    # Query parameters pass through, so a deployment can set driver options
    # (`?charset=utf8mb4`, `?encrypt=yes`) without the platform knowing them.
    arguments.update(dict(parse_qsl(parsed.query)))
    return arguments


def dsn_connect_arguments(connection_uri: str) -> dict[str, Any]:
    """Pass the connection string through under the `dsn` keyword.

    For drivers that own their connection string format *and* name it `dsn` -- oracledb,
    ksycopg2. Drivers that take it positionally or under another name should set
    `passes_uri_positionally` instead; see `whole_uri`.
    """
    return {"dsn": connection_uri}


def whole_uri(_connection_uri: str) -> dict[str, Any]:
    """No keyword arguments: the URI is passed positionally.

    Used with `passes_uri_positionally=True`. This exists because drivers disagree on
    what to call the connection string -- psycopg says `conninfo`, oracledb says `dsn`,
    sqlite3 takes it positionally -- and guessing wrong produces
    `invalid connection option "dsn"`, which looks like a configuration error rather
    than a spec mistake.
    """
    return {}


@dataclass(frozen=True)
class DriverSpec:
    """How to reach one SQL database.

    Everything a `GenericSQLAdapter` needs. Frozen data so a spec is reviewable and can
    be declared by a plugin without importing anything heavier than this module.
    """

    source_type: str
    dialect: SqlDialect
    # Python module providing the PEP 249 `connect`, e.g. `oracledb`.
    module: str
    # Shown when the module is missing. An actionable message, not an ImportError.
    install_hint: str = ""
    # Attribute on the module to call. `connect` for almost everything.
    connect_attribute: str = "connect"
    connect_arguments: Callable[[str], dict[str, Any]] = default_connect_arguments
    # Extra kwargs merged into every connection, e.g. a row factory or charset.
    connect_extras: dict[str, Any] = field(default_factory=dict)
    # Timeout kwarg name, if the driver has one. Used only for `test_connection`, so a
    # broken host fails fast instead of hanging the onboarding screen.
    timeout_argument: str = ""
    timeout_seconds: int = 3
    # Whether cursors already yield mappings. When false, rows are zipped with
    # `cursor.description`, which is how most drivers behave.
    rows_are_mappings: bool = False
    # Pass the connection URI as the first positional argument. Set this when the driver
    # takes the whole connection string but does not call it `dsn`.
    passes_uri_positionally: bool = False

    def validate(self) -> "DriverSpec":
        if not self.source_type or not self.source_type.replace("_", "").isalnum():
            raise DriverError(f"数据源类型必须是字母数字或下划线: {self.source_type!r}")
        if not self.module:
            raise DriverError(f"{self.source_type} 未声明驱动模块")
        return self

    def driver_available(self) -> bool:
        """Whether the driver can be imported, without raising.

        Used by `doctor` and by bundled registration, where a missing driver is
        expected rather than exceptional.
        """
        try:
            importlib.import_module(self.module)
            return True
        except ImportError:
            return False

    def load_driver(self) -> Any:
        try:
            return importlib.import_module(self.module)
        except ImportError as error:
            hint = self.install_hint or f"{self.source_type} 接入需要安装 {self.module}。"
            raise DriverError(hint) from error


class _MappingCursor:
    """Wraps a positional-row cursor so it yields dicts.

    The shared scanner and `SQLRuntime` both read rows by column name, which most
    drivers do not provide. Rather than requiring every driver to have a dict cursor,
    rows are zipped with `cursor.description` here -- one place, so a driver's row shape
    is not a reason to write a new adapter.
    """

    def __init__(self, cursor: Any):
        self._cursor = cursor

    def execute(self, query: str, params: Any = ()) -> Any:
        self._cursor.execute(query, params or ())
        return self

    def _columns(self) -> list[str]:
        description = self._cursor.description or []
        return [str(column[0]) for column in description]

    def fetchone(self) -> Optional[dict[str, Any]]:
        row = self._cursor.fetchone()
        return None if row is None else self._as_mapping(row)

    def fetchall(self) -> list[dict[str, Any]]:
        return [self._as_mapping(row) for row in self._cursor.fetchall()]

    def _as_mapping(self, row: Any) -> dict[str, Any]:
        if isinstance(row, dict):
            return row
        return dict(zip(self._columns(), row))

    def close(self) -> None:
        self._cursor.close()

    def __enter__(self) -> "_MappingCursor":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()


class _MappingConnection:
    """A connection whose cursors yield dicts. See `_MappingCursor`."""

    def __init__(self, conn: Any):
        self._conn = conn

    def cursor(self) -> _MappingCursor:
        return _MappingCursor(self._conn.cursor())

    def execute(self, query: str, params: Any = ()) -> _MappingCursor:
        return self.cursor().execute(query, params)

    def commit(self) -> None:
        if hasattr(self._conn, "commit"):
            self._conn.commit()

    def rollback(self) -> None:
        if hasattr(self._conn, "rollback"):
            self._conn.rollback()

    def close(self) -> None:
        self._conn.close()


class GenericSQLAdapter:
    """A `DatabaseAdapter` built from a `DriverSpec`.

    Holds no per-database logic: scanning is the shared `information_schema` walk, and
    runtime reads are `SQLRuntime`. What varies comes from the spec and its dialect.
    """

    def __init__(self, spec: DriverSpec):
        self.spec = spec.validate()
        self.source_type = spec.source_type

    def _connect(self, connection_uri: str, *, with_timeout: bool = False) -> Any:
        driver = self.spec.load_driver()
        connect = getattr(driver, self.spec.connect_attribute, None)
        if connect is None:
            raise DriverError(f"驱动 {self.spec.module} 没有 {self.spec.connect_attribute}()，无法建立连接。")
        arguments = dict(self.spec.connect_arguments(connection_uri))
        arguments.update(self.spec.connect_extras)
        if with_timeout and self.spec.timeout_argument:
            arguments[self.spec.timeout_argument] = self.spec.timeout_seconds
        if self.spec.passes_uri_positionally:
            conn = connect(connection_uri, **arguments)
        else:
            conn = connect(**arguments)
        return conn if self.spec.rows_are_mappings else _MappingConnection(conn)

    def test_connection(self, connection_uri: str) -> dict[str, Any]:
        """Probe reachability, distinguishing a missing driver from an unreachable host.

        The distinction matters operationally: one is fixed by installing a package, the
        other by fixing a network or a credential. Collapsing them into "failed" sends
        people to the wrong place.
        """
        try:
            self.spec.load_driver()
        except DriverError as error:
            return connection_status(self.source_type, False, "driver_missing", str(error))
        try:
            conn = self._connect(connection_uri, with_timeout=True)
            try:
                cursor = conn.cursor()
                cursor.execute("select 1")
                cursor.fetchone()
            finally:
                conn.close()
            return connection_status(self.source_type, True, "ok", f"{self.source_type} 数据库连接成功。")
        except Exception as error:
            return connection_status(self.source_type, False, "connection_error", str(error))

    def scan(self, connection_uri: str) -> list[SourceTableInfo]:
        conn = self._connect(connection_uri)
        try:
            return scan_information_schema(conn, self.spec.dialect)
        finally:
            conn.close()

    @contextmanager
    def runtime(self, connection_uri: str) -> Iterator[SQLRuntime]:
        conn = self._connect(connection_uri)
        try:
            yield SQLRuntime(conn, self.spec.dialect)
        finally:
            conn.close()


def register_sql_source(spec: DriverSpec, *, replace: bool = False) -> DriverSpec:
    """Make a SQL database available as a data source type.

    Registers eagerly: the driver is imported only on first use, so declaring a source
    type does not require its driver to be installed. A deployment therefore sees the
    type in the onboarding list and gets an actionable "install X" message rather than
    wondering why the type is absent.
    """
    spec.validate()
    register_adapter(spec.source_type, lambda: GenericSQLAdapter(spec), replace=replace)
    return spec


# -- Bundled catalogue -------------------------------------------------------
#
# Declared, not activated. See the module docstring: each needs a driver the kernel does
# not depend on, and several need client libraries that PyPI alone cannot provide.

BUNDLED_SPECS: tuple[DriverSpec, ...] = (
    DriverSpec(
        source_type="oracle",
        dialect=ORACLE,
        module="oracledb",
        install_hint="Oracle 接入需要安装 oracledb：pip install oracledb",
        # oracledb accepts `user`/`password`/`dsn`; the DSN carries host, port and
        # service name, which a generic URI parser cannot reconstruct correctly.
        connect_arguments=lambda uri: _oracle_arguments(uri),
    ),
    DriverSpec(
        source_type="sqlserver",
        dialect=SQLSERVER,
        module="pymssql",
        install_hint="SQL Server 接入需要安装 pymssql：pip install pymssql",
        timeout_argument="timeout",
    ),
    DriverSpec(
        source_type="dameng",
        dialect=DAMENG,
        module="dmPython",
        install_hint="达梦接入需要安装 dmPython（随达梦客户端提供，不在 PyPI 上）。",
    ),
    DriverSpec(
        source_type="kingbase",
        dialect=KINGBASE,
        module="ksycopg2",
        install_hint="人大金仓接入需要安装 ksycopg2（随 KingbaseES 客户端提供）。",
        connect_arguments=whole_uri,
        passes_uri_positionally=True,
    ),
    # PostgreSQL-compatible distributions. Registered under their own names so a
    # deployment's data source list reflects what they actually run -- and so a future
    # divergence gets its own dialect profile rather than silently inheriting one.
    DriverSpec(
        source_type="opengauss",
        dialect=POSTGRESQL,
        module="psycopg2",
        install_hint="openGauss 接入需要安装 psycopg2。",
        connect_arguments=whole_uri,
        passes_uri_positionally=True,
    ),
)


def _oracle_arguments(connection_uri: str) -> dict[str, Any]:
    """Split `oracle://user:pass@host:port/service` into oracledb kwargs.

    Oracle's DSN is `host:port/service_name`, which is why this cannot use the default
    parser: `database` is not a keyword oracledb accepts.
    """
    parsed = urlparse(connection_uri)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 1521
    service = (parsed.path or "").lstrip("/") or "ORCL"
    arguments: dict[str, Any] = {"dsn": f"{host}:{port}/{service}"}
    if parsed.username:
        arguments["user"] = parsed.username
    if parsed.password:
        arguments["password"] = parsed.password
    return arguments


def register_bundled_sql_sources(*, replace: bool = False) -> dict[str, str]:
    """Activate the bundled specs whose drivers are installed.

    Returns a status per source type so a caller can report it. Skipping silently would
    make a missing driver look like a platform bug.
    """
    outcome: dict[str, str] = {}
    for spec in BUNDLED_SPECS:
        if not spec.driver_available():
            outcome[spec.source_type] = "driver_missing"
            logger.debug("跳过 %s：驱动 %s 未安装", spec.source_type, spec.module)
            continue
        try:
            register_sql_source(spec, replace=replace)
            outcome[spec.source_type] = "registered"
        except Exception as error:
            outcome[spec.source_type] = f"error: {error}"
            logger.warning("注册 %s 失败: %s", spec.source_type, error)
    return outcome


def describe_bundled_sql_sources() -> list[dict[str, Any]]:
    """The catalogue as reviewable data, for `doctor` and the API."""
    return [
        {
            "sourceType": spec.source_type,
            "dialect": spec.dialect.name,
            "driverModule": spec.module,
            "driverAvailable": spec.driver_available(),
            "installHint": spec.install_hint,
        }
        for spec in BUNDLED_SPECS
    ]
