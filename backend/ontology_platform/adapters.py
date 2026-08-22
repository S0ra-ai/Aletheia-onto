from __future__ import annotations

import importlib
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Protocol
from urllib.parse import urlparse

from .config import QUERY_LIMITS
from .instance_key import InstanceKey, parse_key_columns
from .registry import Registry, RegistryError, load_entry_point_plugins


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
            return _connection_status(self.source_type, False, "not_found", f"SQLite 数据库文件不存在: {path}")
        try:
            with sqlite3.connect(path) as conn:
                conn.execute("select 1").fetchone()
            return _connection_status(self.source_type, True, "ok", "SQLite 数据库连接成功。")
        except sqlite3.Error as error:
            return _connection_status(self.source_type, False, "connection_error", str(error))

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
            return _connection_status(self.source_type, False, "driver_missing", str(error))
        try:
            with psycopg.connect(connection_uri, connect_timeout=3) as conn:
                with conn.cursor() as cursor:
                    cursor.execute("select 1")
                    cursor.fetchone()
            return _connection_status(self.source_type, True, "ok", "PostgreSQL 数据库连接成功。")
        except Exception as error:
            return _connection_status(self.source_type, False, "connection_error", str(error))

    def scan(self, connection_uri: str) -> list[SourceTableInfo]:
        psycopg = _optional_import("psycopg", "PostgreSQL 接入需要安装 psycopg。")
        with psycopg.connect(connection_uri, row_factory=psycopg.rows.dict_row) as conn:
            return _scan_information_schema(conn, "postgresql")

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
            return _connection_status(self.source_type, False, "driver_missing", str(error))
        try:
            options = _parse_mysql_uri(connection_uri)
            options["connect_timeout"] = 3
            with pymysql.connect(cursorclass=pymysql.cursors.DictCursor, **options) as conn:
                with conn.cursor() as cursor:
                    cursor.execute("select 1")
                    cursor.fetchone()
            return _connection_status(self.source_type, True, "ok", "MySQL 数据库连接成功。")
        except Exception as error:
            return _connection_status(self.source_type, False, "connection_error", str(error))

    def scan(self, connection_uri: str) -> list[SourceTableInfo]:
        pymysql = _optional_import("pymysql", "MySQL 接入需要安装 PyMySQL。")
        options = _parse_mysql_uri(connection_uri)
        with pymysql.connect(cursorclass=pymysql.cursors.DictCursor, **options) as conn:
            return _scan_information_schema(conn, "mysql")

    @contextmanager
    def runtime(self, connection_uri: str) -> Iterator[RuntimeDatabase]:
        pymysql = _optional_import("pymysql", "MySQL 运行时读取需要安装 PyMySQL。")
        options = _parse_mysql_uri(connection_uri)
        with pymysql.connect(cursorclass=pymysql.cursors.DictCursor, **options) as conn:
            yield SQLRuntime(conn, "mysql")


class SQLRuntime:
    def __init__(self, conn: Any, dialect: str):
        self.conn = conn
        self.dialect = dialect

    def fetch_primary_keys(self, table_name: str, primary_key: str, limit: int = 50) -> list[Any]:
        columns = parse_key_columns(primary_key)
        table = _quote_identifier(table_name, self.dialect)
        if len(columns) == 1:
            column = _quote_identifier(columns[0], self.dialect)
            rows = self._fetch_all(
                f"select {column} as instance_id from {table} order by {column} limit %s",
                (limit,),
            )
            return [row["instance_id"] for row in rows]
        selected = ", ".join(_quote_identifier(column, self.dialect) for column in columns)
        rows = self._fetch_all(f"select {selected} from {table} order by {selected} limit %s", (limit,))
        return [InstanceKey.from_row(primary_key, row).token for row in rows]

    def browse_rows(self, table_name: str, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
        table = _quote_identifier(table_name, self.dialect)
        total_row = self._fetch_one(f"select count(*) as row_count from {table}", ()) or {"row_count": 0}
        rows = self._fetch_all(f"select * from {table} limit %s offset %s", (limit, offset))
        return rows, int(total_row["row_count"])

    def fetch_one(self, table_name: str, primary_key: str, instance_id: str) -> dict[str, Any] | None:
        key = InstanceKey.from_token(primary_key, instance_id)
        conditions, params = key.where_clause(lambda column: _quote_identifier(column, self.dialect), placeholder="%s")
        return self._fetch_one(
            f"select * from {_quote_identifier(table_name, self.dialect)} where {conditions}",
            params,
        )

    def fetch_related_one(self, table_name: str, column_name: str, value: Any) -> dict[str, Any] | None:
        return self._fetch_one(
            f"select * from {_quote_identifier(table_name, self.dialect)} where {_quote_identifier(column_name, self.dialect)} = %s",
            (value,),
        )

    def fetch_related_many(self, table_name: str, column_name: str, value: Any) -> list[dict[str, Any]]:
        return self._fetch_all(
            f"select * from {_quote_identifier(table_name, self.dialect)} where {_quote_identifier(column_name, self.dialect)} = %s",
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
        limit 5
        """
    ).fetchall()
    samples = [row["value"] for row in sample_rows]
    null_ratio = 0 if row_count == 0 else null_count / row_count
    enum_candidate = _is_enum_candidate(row_count, distinct_count)
    return ColumnProfile(
        samples=samples, null_ratio=null_ratio, distinct_count=distinct_count, enum_candidate=enum_candidate
    )


def _scan_information_schema(conn: Any, dialect: str) -> list[SourceTableInfo]:
    table_rows = _fetch_dicts(
        conn,
        """
        select table_name
        from information_schema.tables
        where table_schema = current_schema()
          and table_type = 'BASE TABLE'
        order by table_name
        """
        if dialect == "postgresql"
        else """
        select table_name
        from information_schema.tables
        where table_schema = database()
          and table_type = 'BASE TABLE'
        order by table_name
        """,
    )
    return [_scan_information_schema_table(conn, row["table_name"], dialect) for row in table_rows]


def _scan_information_schema_table(conn: Any, table_name: str, dialect: str) -> SourceTableInfo:
    row_count = _estimated_row_count(conn, table_name, dialect)
    column_rows = _fetch_dicts(
        conn,
        """
        select column_name, data_type, is_nullable, ordinal_position
        from information_schema.columns
        where table_schema = current_schema()
          and table_name = %s
        order by ordinal_position
        """
        if dialect == "postgresql"
        else """
        select column_name, data_type, is_nullable, ordinal_position
        from information_schema.columns
        where table_schema = database()
          and table_name = %s
        order by ordinal_position
        """,
        (table_name,),
    )
    primary_keys = _primary_keys(conn, table_name, dialect)
    columns = [
        SourceColumnInfo(
            name=row["column_name"],
            data_type=row["data_type"],
            nullable=row["is_nullable"].upper() == "YES",
            ordinal=int(row["ordinal_position"]) - 1,
            is_primary_key=row["column_name"] in primary_keys,
            profile=_profile_sql_column(conn, table_name, row["column_name"], row_count, dialect),
        )
        for row in column_rows
    ]
    return SourceTableInfo(
        name=table_name,
        row_count=row_count,
        primary_key=",".join(primary_keys),
        columns=columns,
        foreign_keys=_foreign_keys(conn, table_name, dialect),
    )


def _estimated_row_count(conn: Any, table_name: str, dialect: str) -> int:
    try:
        rows = _fetch_dicts(conn, f"select count(*) as count from {_quote_identifier(table_name, dialect)}")
        return int(rows[0]["count"]) if rows else 0
    except Exception:
        return 0


def _profile_sql_column(conn: Any, table_name: str, column_name: str, row_count: int, dialect: str) -> ColumnProfile:
    table_ref = _quote_identifier(table_name, dialect)
    column_ref = _quote_identifier(column_name, dialect)
    try:
        null_rows = _fetch_dicts(conn, f"select count(*) as count from {table_ref} where {column_ref} is null")
        distinct_rows = _fetch_dicts(conn, f"select count(distinct {column_ref}) as count from {table_ref}")
        sample_rows = _fetch_dicts(
            conn,
            f"select distinct {column_ref} as value from {table_ref} where {column_ref} is not null limit 5",
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


def _primary_keys(conn: Any, table_name: str, dialect: str) -> list[str]:
    rows = _fetch_dicts(
        conn,
        """
        select kcu.column_name
        from information_schema.table_constraints tc
        join information_schema.key_column_usage kcu
          on tc.constraint_name = kcu.constraint_name
         and tc.table_schema = kcu.table_schema
         and tc.table_name = kcu.table_name
        where tc.constraint_type = 'PRIMARY KEY'
          and tc.table_schema = current_schema()
          and tc.table_name = %s
        order by kcu.ordinal_position
        """
        if dialect == "postgresql"
        else """
        select kcu.column_name
        from information_schema.table_constraints tc
        join information_schema.key_column_usage kcu
          on tc.constraint_name = kcu.constraint_name
         and tc.table_schema = kcu.table_schema
         and tc.table_name = kcu.table_name
        where tc.constraint_type = 'PRIMARY KEY'
          and tc.table_schema = database()
          and tc.table_name = %s
        order by kcu.ordinal_position
        """,
        (table_name,),
    )
    return [row["column_name"] for row in rows]


def _foreign_keys(conn: Any, table_name: str, dialect: str) -> list[SourceForeignKeyInfo]:
    rows = _fetch_dicts(
        conn,
        """
        select kcu.column_name, ccu.table_name as target_table, ccu.column_name as target_column
        from information_schema.table_constraints tc
        join information_schema.key_column_usage kcu
          on tc.constraint_name = kcu.constraint_name
         and tc.table_schema = kcu.table_schema
        join information_schema.constraint_column_usage ccu
          on ccu.constraint_name = tc.constraint_name
         and ccu.table_schema = tc.table_schema
        where tc.constraint_type = 'FOREIGN KEY'
          and tc.table_schema = current_schema()
          and tc.table_name = %s
        """
        if dialect == "postgresql"
        else """
        select kcu.column_name, kcu.referenced_table_name as target_table, kcu.referenced_column_name as target_column
        from information_schema.key_column_usage kcu
        where kcu.table_schema = database()
          and kcu.table_name = %s
          and kcu.referenced_table_name is not null
        """,
        (table_name,),
    )
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


def _quote_identifier(identifier: str, dialect: str = "postgresql") -> str:
    if dialect == "mysql":
        return "`" + identifier.replace("`", "``") + "`"
    return '"' + identifier.replace('"', '""') + '"'


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


def _connection_status(source_type: str, reachable: bool, status: str, message: str) -> dict[str, Any]:
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

# Third-party adapters shipped as installable packages. Failures are logged, not
# raised: a broken plugin must not stop the platform from starting.
load_adapter_plugins()
