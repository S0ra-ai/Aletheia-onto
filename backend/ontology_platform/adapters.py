from __future__ import annotations

import importlib
import logging
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Protocol, Union
from urllib.parse import urlparse

from .config import QUERY_LIMITS
from .instance_key import InstanceKey, parse_key_columns
from .registry import Registry, RegistryError, load_entry_point_plugins
from .sql_dialects import (
    SqlDialect,
    columns_query,
    foreign_keys_query,
    primary_keys_query,
    resolve_dialect,
    tables_query,
)

# Either a dialect name or a profile. Widened rather than replaced so the existing call
# sites that pass `"postgresql"` keep working.
DialectLike = Union[str, SqlDialect]

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ColumnProfile:
    samples: list[Any]
    null_ratio: float
    distinct_count: int
    enum_candidate: bool


@dataclass(frozen=True)
class SourceColumnInfo:
    name: str
    data_type: str
    nullable: bool
    ordinal: int
    is_primary_key: bool
    profile: ColumnProfile


@dataclass(frozen=True)
class SourceTableInfo:
    name: str
    row_count: int
    primary_key: str
    columns: list[SourceColumnInfo]
    foreign_keys: list["SourceForeignKeyInfo"]


@dataclass(frozen=True)
class SourceForeignKeyInfo:
    column_name: str
    target_table: str
    target_column: str


class DatabaseAdapter(Protocol):
    source_type: str

    def test_connection(self, connection_uri: str) -> dict[str, Any]: ...

    def scan(self, connection_uri: str) -> list[SourceTableInfo]: ...

    @contextmanager
    def runtime(self, connection_uri: str) -> Iterator["RuntimeDatabase"]: ...


class RuntimeDatabase(Protocol):
    def browse_rows(self, table_name: str, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]: ...

    def fetch_primary_keys(self, table_name: str, primary_key: str, limit: int = 50) -> list[Any]: ...

    def fetch_one(self, table_name: str, primary_key: str, instance_id: str) -> dict[str, Any] | None: ...

    def fetch_related_one(self, table_name: str, column_name: str, value: Any) -> dict[str, Any] | None: ...

    def fetch_related_many(self, table_name: str, column_name: str, value: Any) -> list[dict[str, Any]]: ...


# Third parties register their own adapters here instead of forking the platform.
# Experimental: the DatabaseAdapter protocol may change before 1.0 (ADR-0007).
ADAPTER_REGISTRY: Registry[Callable[[], DatabaseAdapter]] = Registry("数据源适配器")

ADAPTER_ENTRY_POINT_GROUP = "aletheia.adapters"


def register_adapter(
    source_type: str,
    factory: Callable[[], DatabaseAdapter],
    *,
    aliases: Iterable[str] = (),
    replace: bool = False,
) -> Callable[[], DatabaseAdapter]:
    """Register a data source adapter factory.

    A factory rather than an instance, because adapters are cheap to build and
    callers treat each one as independent.

    >>> register_adapter("oracle", OracleAdapter)          # doctest: +SKIP
    >>> register_adapter("dm", DamengAdapter, aliases=["dameng"])  # doctest: +SKIP

    Implementations must satisfy `DatabaseAdapter`. Run
    `tests/test_adapter_contract.py` against a new adapter to check compliance.
    """
    ADAPTER_REGISTRY.register(source_type, factory, replace=replace)
    for alias in aliases:
        ADAPTER_REGISTRY.alias(alias, source_type)
    return factory


def get_adapter(source_type: str) -> DatabaseAdapter:
    try:
        factory = ADAPTER_REGISTRY.get(source_type)
    except RegistryError as error:
        # ValueError is what callers and the API layer already handle, so keep
        # the exception type stable while improving the message.
        raise ValueError(str(error)) from error
    return factory()


def supported_source_types() -> tuple[str, ...]:
    return ADAPTER_REGISTRY.names()


def load_adapter_plugins() -> list[str]:
    """Discover adapters advertised by installed packages via entry points."""
    return load_entry_point_plugins(
        ADAPTER_ENTRY_POINT_GROUP,
        lambda name, factory: ADAPTER_REGISTRY.register(name, factory),
    )


def test_connection(source_type: str, connection_uri: str) -> dict[str, Any]:
    return get_adapter(source_type).test_connection(connection_uri)


class SQLiteRuntime:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def fetch_primary_keys(self, table_name: str, primary_key: str, limit: int = 50) -> list[Any]:
        columns = parse_key_columns(primary_key)
        if len(columns) == 1:
            rows = self.conn.execute(
                f'select "{columns[0]}" as instance_id from "{table_name}" order by "{columns[0]}" limit ?',
                (limit,),
            ).fetchall()
            return [row["instance_id"] for row in rows]
        # Composite key: return the token form so callers keep treating an
        # instance id as one opaque string.
        selected = ", ".join(f'"{column}"' for column in columns)
        ordered = ", ".join(f'"{column}"' for column in columns)
        rows = self.conn.execute(
            f'select {selected} from "{table_name}" order by {ordered} limit ?', (limit,)
        ).fetchall()
        return [InstanceKey.from_row(primary_key, dict(row)).token for row in rows]

    def browse_rows(self, table_name: str, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
        quoted = table_name.replace('"', '""')
        total = int(self.conn.execute(f'select count(*) as count from "{quoted}"').fetchone()["count"])
        rows = self.conn.execute(f'select * from "{quoted}" limit ? offset ?', (limit, offset)).fetchall()
        return [dict(row) for row in rows], total

    def fetch_one(self, table_name: str, primary_key: str, instance_id: str) -> dict[str, Any] | None:
        key = InstanceKey.from_token(primary_key, instance_id)
        conditions, params = key.where_clause(lambda column: f'"{column}"', placeholder="?")
        row = self.conn.execute(f'select * from "{table_name}" where {conditions}', params).fetchone()
        return dict(row) if row is not None else None

    def fetch_related_one(self, table_name: str, column_name: str, value: Any) -> dict[str, Any] | None:
        row = self.conn.execute(
            f'select * from "{table_name}" where "{column_name}" = ?',
            (value,),
        ).fetchone()
        return dict(row) if row is not None else None

    def fetch_related_many(self, table_name: str, column_name: str, value: Any) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            f'select * from "{table_name}" where "{column_name}" = ?',
            (value,),
        ).fetchall()
        return [dict(row) for row in rows]


class SQLiteAdapter:
    source_type = "sqlite"

    def test_connection(self, connection_uri: str) -> dict[str, Any]:
        path = Path(connection_uri)
        if not path.exists():
            return connection_status(self.source_type, False, "not_found", f"SQLite 数据库文件不存在: {path}")
        try:
            with sqlite3.connect(path) as conn:
                conn.execute("select 1").fetchone()
            return connection_status(self.source_type, True, "ok", "SQLite 数据库连接成功。")
        except sqlite3.Error as error:
            return connection_status(self.source_type, False, "connection_error", str(error))

    def scan(self, connection_uri: str) -> list[SourceTableInfo]:
        with sqlite3.connect(Path(connection_uri)) as conn:
            conn.row_factory = sqlite3.Row
            return [_scan_sqlite_table(conn, table_name) for table_name in _sqlite_tables(conn)]

    @contextmanager
    def runtime(self, connection_uri: str) -> Iterator[SQLiteRuntime]:
        with sqlite3.connect(Path(connection_uri)) as conn:
            conn.row_factory = sqlite3.Row
            yield SQLiteRuntime(conn)


class PostgreSQLAdapter:
    source_type = "postgresql"

    def test_connection(self, connection_uri: str) -> dict[str, Any]:
        try:
            psycopg = _optional_import("psycopg", "PostgreSQL 接入需要安装 psycopg。")
        except RuntimeError as error:
            return connection_status(self.source_type, False, "driver_missing", str(error))
        try:
            with psycopg.connect(connection_uri, connect_timeout=3) as conn:
                with conn.cursor() as cursor:
                    cursor.execute("select 1")
                    cursor.fetchone()
            return connection_status(self.source_type, True, "ok", "PostgreSQL 数据库连接成功。")
        except Exception as error:
            return connection_status(self.source_type, False, "connection_error", str(error))

    def scan(self, connection_uri: str) -> list[SourceTableInfo]:
        psycopg = _optional_import("psycopg", "PostgreSQL 接入需要安装 psycopg。")
        with psycopg.connect(connection_uri, row_factory=psycopg.rows.dict_row) as conn:
            return scan_information_schema(conn, "postgresql")

    @contextmanager
    def runtime(self, connection_uri: str) -> Iterator[RuntimeDatabase]:
        psycopg = _optional_import("psycopg", "PostgreSQL 运行时读取需要安装 psycopg。")
        with psycopg.connect(connection_uri, row_factory=psycopg.rows.dict_row) as conn:
            yield SQLRuntime(conn, "postgresql")


class MySQLAdapter:
    source_type = "mysql"

    def test_connection(self, connection_uri: str) -> dict[str, Any]:
        try:
            pymysql = _optional_import("pymysql", "MySQL 接入需要安装 PyMySQL。")
        except RuntimeError as error:
            return connection_status(self.source_type, False, "driver_missing", str(error))
        try:
            options = _parse_mysql_uri(connection_uri)
            options["connect_timeout"] = 3
            with pymysql.connect(cursorclass=pymysql.cursors.DictCursor, **options) as conn:
                with conn.cursor() as cursor:
                    cursor.execute("select 1")
                    cursor.fetchone()
            return connection_status(self.source_type, True, "ok", "MySQL 数据库连接成功。")
        except Exception as error:
            return connection_status(self.source_type, False, "connection_error", str(error))

    def scan(self, connection_uri: str) -> list[SourceTableInfo]:
        pymysql = _optional_import("pymysql", "MySQL 接入需要安装 PyMySQL。")
        options = _parse_mysql_uri(connection_uri)
        with pymysql.connect(cursorclass=pymysql.cursors.DictCursor, **options) as conn:
            return scan_information_schema(conn, "mysql")

    @contextmanager
    def runtime(self, connection_uri: str) -> Iterator[RuntimeDatabase]:
        pymysql = _optional_import("pymysql", "MySQL 运行时读取需要安装 PyMySQL。")
        options = _parse_mysql_uri(connection_uri)
        with pymysql.connect(cursorclass=pymysql.cursors.DictCursor, **options) as conn:
            yield SQLRuntime(conn, "mysql")


class SQLRuntime:
    """Runtime reads for any SQL database, driven by a dialect profile.

    One implementation rather than one per database: the queries are plain
    single-table selects, and everything that differs (quoting, placeholders, row
    limiting) comes from the profile.
    """

    def __init__(self, conn: Any, dialect: DialectLike):
        self.conn = conn
        self.profile = resolve_dialect(dialect)
        # Kept as the profile name so existing callers reading `.dialect` still see a
        # string, which is what they did before profiles existed.
        self.dialect = self.profile.name

    def fetch_primary_keys(self, table_name: str, primary_key: str, limit: int = 50) -> list[Any]:
        columns = parse_key_columns(primary_key)
        table = self.profile.quote(table_name)
        if len(columns) == 1:
            column = self.profile.quote(columns[0])
            rows = self._fetch_all(
                f"select {column} as instance_id from {table} order by {column} {self.profile.limit_clause(limit)}",
                (),
            )
            return [row["instance_id"] for row in rows]
        selected = ", ".join(self.profile.quote(column) for column in columns)
        rows = self._fetch_all(
            f"select {selected} from {table} order by {selected} {self.profile.limit_clause(limit)}",
            (),
        )
        return [InstanceKey.from_row(primary_key, row).token for row in rows]

    def browse_rows(self, table_name: str, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
        table = self.profile.quote(table_name)
        total_row = self._fetch_one(f"select count(*) as row_count from {table}", ()) or {"row_count": 0}
        # `fetch first` requires an ORDER BY to be deterministic, and browsing an
        # unordered page is meaningless anyway -- the same offset would return different
        # rows on consecutive calls.
        order = self._browse_order(table_name)
        rows = self._fetch_all(
            f"select * from {table}{order} {self.profile.limit_clause(limit, offset)}",
            (),
        )
        return rows, int(total_row["row_count"])

    def _browse_order(self, table_name: str) -> str:
        """An ORDER BY for paging, using the primary key when one is discoverable.

        Falls back to no ordering rather than raising: browsing is a convenience view,
        and a table without a key is still worth looking at. `fetch first` dialects
        need *some* order to page deterministically, so those get the first column.
        """
        try:
            keys = _primary_keys(self.conn, table_name, self.profile)
        except Exception:
            keys = []
        if keys:
            return " order by " + ", ".join(self.profile.quote(column) for column in keys)
        if self.profile.row_limit_style == "fetch_first":
            # Ordering by ordinal position is portable and enough to make paging stable.
            return " order by 1"
        return ""

    def fetch_one(self, table_name: str, primary_key: str, instance_id: str) -> dict[str, Any] | None:
        key = InstanceKey.from_token(primary_key, instance_id)
        conditions, params = key.where_clause(self.profile.quote, placeholder=self.profile.placeholder())
        return self._fetch_one(
            f"select * from {self.profile.quote(table_name)} where {conditions}",
            params,
        )

    def fetch_related_one(self, table_name: str, column_name: str, value: Any) -> dict[str, Any] | None:
        return self._fetch_one(
            f"select * from {self.profile.quote(table_name)} "
            f"where {self.profile.quote(column_name)} = {self.profile.placeholder()}",
            (value,),
        )

    def fetch_related_many(self, table_name: str, column_name: str, value: Any) -> list[dict[str, Any]]:
        return self._fetch_all(
            f"select * from {self.profile.quote(table_name)} "
            f"where {self.profile.quote(column_name)} = {self.profile.placeholder()}",
            (value,),
        )

    def _fetch_one(self, query: str, params: tuple[Any, ...]) -> dict[str, Any] | None:
        rows = self._fetch_all(query, params)
        return rows[0] if rows else None

    def _fetch_all(self, query: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        with self.conn.cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()
        return [dict(row) for row in rows]


def _sqlite_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        """
        select name from sqlite_master
        where type = 'table'
          and name not like 'sqlite_%'
        order by name
        """
    ).fetchall()
    return [row["name"] for row in rows]


def _scan_sqlite_table(conn: sqlite3.Connection, table_name: str) -> SourceTableInfo:
    row_count = conn.execute(f'select count(*) as count from "{table_name}"').fetchone()["count"]
    table_info = conn.execute(f'pragma table_info("{table_name}")').fetchall()
    primary_keys = [row["name"] for row in table_info if row["pk"]]
    columns = [
        SourceColumnInfo(
            name=column["name"],
            data_type=column["type"] or "text",
            nullable=not bool(column["notnull"]),
            ordinal=ordinal,
            is_primary_key=bool(column["pk"]),
            profile=_profile_sqlite_column(conn, table_name, column["name"], row_count),
        )
        for ordinal, column in enumerate(table_info)
    ]
    foreign_keys = [
        SourceForeignKeyInfo(
            column_name=foreign_key["from"],
            target_table=foreign_key["table"],
            target_column=foreign_key["to"],
        )
        for foreign_key in conn.execute(f'pragma foreign_key_list("{table_name}")').fetchall()
    ]
    return SourceTableInfo(
        name=table_name,
        row_count=row_count,
        primary_key=",".join(primary_keys),
        columns=columns,
        foreign_keys=foreign_keys,
    )


def _profile_sqlite_column(
    conn: sqlite3.Connection, table_name: str, column_name: str, row_count: int
) -> ColumnProfile:
    quoted_table = f'"{table_name}"'
    quoted_column = f'"{column_name}"'
    null_count = conn.execute(f"select count(*) as count from {quoted_table} where {quoted_column} is null").fetchone()[
        "count"
    ]
    distinct_count = conn.execute(f"select count(distinct {quoted_column}) as count from {quoted_table}").fetchone()[
        "count"
    ]
    sample_rows = conn.execute(
        f"""
        select distinct {quoted_column} as value from {quoted_table}
        where {quoted_column} is not null
        limit {QUERY_LIMITS.column_profile_samples}
        """
    ).fetchall()
    samples = [row["value"] for row in sample_rows]
    null_ratio = 0 if row_count == 0 else null_count / row_count
    enum_candidate = _is_enum_candidate(row_count, distinct_count)
    return ColumnProfile(
        samples=samples, null_ratio=null_ratio, distinct_count=distinct_count, enum_candidate=enum_candidate
    )


def scan_information_schema(conn: Any, dialect: DialectLike) -> list[SourceTableInfo]:
    """Scan every base table in the connection's schema.

    One implementation for every SQL database: `information_schema` is standard, and the
    parts that genuinely differ come from the dialect profile (see `sql_dialects`). This
    used to be a binary `if postgresql else mysql`, which meant a third database could
    not be added without editing this function -- i.e. a fork.

    Public because a third-party adapter's whole job is to supply a connection and a
    dialect and then call this. Keeping it private meant every new database had to
    reach across a module boundary for it.
    """
    profile = resolve_dialect(dialect)
    table_rows = _fetch_dicts(conn, tables_query(profile))
    return [_scan_information_schema_table(conn, row["table_name"], profile) for row in table_rows]


def _scan_information_schema_table(conn: Any, table_name: str, dialect: DialectLike) -> SourceTableInfo:
    profile = resolve_dialect(dialect)
    row_count = _estimated_row_count(conn, table_name, profile)
    # Oracle and 达梦 fold unquoted identifiers to upper case in the catalog, so a
    # lookup for `contracts` matches nothing while `CONTRACTS` succeeds -- and the
    # failure is silent: the table simply appears to have no columns.
    catalog_name = profile.catalog_name(table_name)
    column_rows = _fetch_dicts(conn, columns_query(profile), (catalog_name,))
    primary_keys = _primary_keys(conn, table_name, profile)
    columns = [
        SourceColumnInfo(
            name=row["column_name"],
            data_type=row["data_type"],
            nullable=row["is_nullable"].upper() == "YES",
            ordinal=int(row["ordinal_position"]) - 1,
            is_primary_key=row["column_name"] in primary_keys,
            profile=_profile_sql_column(conn, table_name, row["column_name"], row_count, profile),
        )
        for row in column_rows
    ]
    return SourceTableInfo(
        name=table_name,
        row_count=row_count,
        primary_key=",".join(primary_keys),
        columns=columns,
        foreign_keys=_foreign_keys(conn, table_name, profile),
    )


def _estimated_row_count(conn: Any, table_name: str, dialect: DialectLike) -> int:
    try:
        rows = _fetch_dicts(conn, f"select count(*) as count from {resolve_dialect(dialect).quote(table_name)}")
        return int(rows[0]["count"]) if rows else 0
    except Exception:
        return 0


def _profile_sql_column(
    conn: Any, table_name: str, column_name: str, row_count: int, dialect: DialectLike
) -> ColumnProfile:
    profile = resolve_dialect(dialect)
    table_ref = profile.quote(table_name)
    column_ref = profile.quote(column_name)
    try:
        null_rows = _fetch_dicts(conn, f"select count(*) as count from {table_ref} where {column_ref} is null")
        distinct_rows = _fetch_dicts(conn, f"select count(distinct {column_ref}) as count from {table_ref}")
        # `limit 5` is not portable: Oracle, SQL Server and 达梦 need `fetch first`.
        # A hardcoded `limit` here would make profiling fail on those, and the failure
        # is swallowed below -- so every column would silently come back unprofiled.
        sample_rows = _fetch_dicts(
            conn,
            f"select distinct {column_ref} as value from {table_ref} "
            f"where {column_ref} is not null order by {column_ref} "
            f"{profile.limit_clause(QUERY_LIMITS.column_profile_samples)}",
        )
    except Exception:
        return ColumnProfile(samples=[], null_ratio=0, distinct_count=0, enum_candidate=False)
    null_count = int(null_rows[0]["count"]) if null_rows else 0
    distinct_count = int(distinct_rows[0]["count"]) if distinct_rows else 0
    null_ratio = 0 if row_count == 0 else null_count / row_count
    enum_candidate = _is_enum_candidate(row_count, distinct_count)
    return ColumnProfile(
        samples=[row["value"] for row in sample_rows],
        null_ratio=null_ratio,
        distinct_count=distinct_count,
        enum_candidate=enum_candidate,
    )


def _primary_keys(conn: Any, table_name: str, dialect: DialectLike) -> list[str]:
    profile = resolve_dialect(dialect)
    rows = _fetch_dicts(conn, primary_keys_query(profile), (profile.catalog_name(table_name),))
    return [row["column_name"] for row in rows]


def _foreign_keys(conn: Any, table_name: str, dialect: DialectLike) -> list[SourceForeignKeyInfo]:
    profile = resolve_dialect(dialect)
    rows = _fetch_dicts(conn, foreign_keys_query(profile), (profile.catalog_name(table_name),))
    return [
        SourceForeignKeyInfo(
            column_name=row["column_name"],
            target_table=row["target_table"],
            target_column=row["target_column"],
        )
        for row in rows
    ]


def _fetch_dicts(conn: Any, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with conn.cursor() as cursor:
        cursor.execute(query, params)
        rows = cursor.fetchall()
    # MySQL preserves information_schema column labels as upper-case on some
    # server/driver combinations, while PostgreSQL returns lower-case labels.
    # Normalize metadata keys so the shared scanner behaves consistently.
    return [{str(key).lower(): value for key, value in dict(row).items()} for row in rows]


def _quote_identifier(identifier: str, dialect: DialectLike = "postgresql") -> str:
    """Quote an identifier for one dialect.

    Delegates to the dialect profile so a newly registered database gets correct quoting
    without this function knowing it exists. SQL Server's `[…]` is why quoting is a pair
    of characters rather than one.
    """
    return resolve_dialect(dialect).quote(identifier)


def _parse_mysql_uri(connection_uri: str) -> dict[str, Any]:
    parsed = urlparse(connection_uri)
    if parsed.scheme not in {"mysql", "mysql+pymysql"}:
        raise ValueError("MySQL 连接串应使用 mysql://user:password@host:port/database")
    return {
        "host": parsed.hostname or "127.0.0.1",
        "port": parsed.port or 3306,
        "user": parsed.username or "",
        "password": parsed.password or "",
        "database": parsed.path.lstrip("/"),
        "charset": "utf8mb4",
    }


def _optional_import(module_name: str, message: str) -> Any:
    try:
        return importlib.import_module(module_name)
    except ImportError as error:
        raise RuntimeError(message) from error


def _is_enum_candidate(row_count: int, distinct_count: int) -> bool:
    """Decide whether a column looks like an enumeration.

    A column qualifies when it has more than one distinct value but few enough
    to read as a code list. Bounds are configurable because the right ceiling
    depends on the source system.
    """
    if row_count <= 0 or distinct_count <= 1:
        return False
    ceiling = min(QUERY_LIMITS.enum_max_distinct, max(QUERY_LIMITS.enum_min_distinct, row_count))
    return distinct_count <= ceiling


def connection_status(source_type: str, reachable: bool, status: str, message: str) -> dict[str, Any]:
    """The shape every adapter's `test_connection` returns.

    Public because a third-party adapter must produce the same shape, and the frontend
    distinguishes `driver_missing` from `connection_error` to tell an operator whether to
    install a package or fix a credential.
    """
    return {
        "sourceType": source_type,
        "reachable": reachable,
        "status": status,
        "message": message,
    }


# -- Built-in adapters --
#
# Registered at import time so the defaults behave exactly as before and
# supported_source_types() reports a complete list. Declared here, after the
# classes exist, rather than next to the registry definition above.
register_adapter("sqlite", SQLiteAdapter)
register_adapter("postgresql", PostgreSQLAdapter, aliases=("postgres", "pgsql"))
register_adapter("mysql", MySQLAdapter)


def load_builtin_optional_adapters() -> list[str]:
    """Register the built-in adapters that live in their own modules.

    CSV needs no driver, so it should be available without the caller knowing to import
    `file_adapter` -- nobody would guess that. It cannot be registered at this module's
    import time, though: `file_adapter` imports *this* module, so a top-level import here
    would be a cycle (see `tests/test_module_boundaries.py`).

    Called from `load_adapter_plugins`, which every entry point already runs through, so
    a plain `import ontology_platform.adapters` ends up with CSV available.
    """
    registered: list[str] = []
    for module_name in ("file_adapter", "rest_adapter"):
        try:
            importlib.import_module(f".{module_name}", __package__)
            registered.append(module_name)
        except Exception as error:  # pragma: no cover - defensive
            # A built-in adapter failing to import is a platform bug, but it must not
            # stop the platform from starting with the adapters that do work.
            logger.warning("内置适配器 %s 注册失败: %s", module_name, error)
    return registered


load_builtin_optional_adapters()

# Third-party adapters shipped as installable packages. Failures are logged, not
# raised: a broken plugin must not stop the platform from starting.
load_adapter_plugins()
