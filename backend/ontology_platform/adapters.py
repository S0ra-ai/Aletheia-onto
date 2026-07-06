from __future__ import annotations

import importlib
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Protocol
from urllib.parse import urlparse


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

    def scan(self, connection_uri: str) -> list[SourceTableInfo]:
        ...

    @contextmanager
    def runtime(self, connection_uri: str) -> Iterator["RuntimeDatabase"]:
        ...


class RuntimeDatabase(Protocol):
    def fetch_one(self, table_name: str, primary_key: str, instance_id: str) -> dict[str, Any] | None:
        ...

    def fetch_related_one(self, table_name: str, column_name: str, value: Any) -> dict[str, Any] | None:
        ...

    def fetch_related_many(self, table_name: str, column_name: str, value: Any) -> list[dict[str, Any]]:
        ...


SUPPORTED_SOURCE_TYPES = ("sqlite", "postgresql", "mysql")


def get_adapter(source_type: str) -> DatabaseAdapter:
    normalized = source_type.lower()
    if normalized == "sqlite":
        return SQLiteAdapter()
    if normalized in {"postgresql", "postgres", "pgsql"}:
        return PostgreSQLAdapter()
    if normalized == "mysql":
        return MySQLAdapter()
    raise ValueError(f"不支持的数据源类型: {source_type}。当前支持: {', '.join(SUPPORTED_SOURCE_TYPES)}")


class SQLiteRuntime:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def fetch_one(self, table_name: str, primary_key: str, instance_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            f'select * from "{table_name}" where "{primary_key}" = ?',
            (instance_id,),
        ).fetchone()
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

    def fetch_one(self, table_name: str, primary_key: str, instance_id: str) -> dict[str, Any] | None:
        return self._fetch_one(f"select * from {_quote_identifier(table_name, self.dialect)} where {_quote_identifier(primary_key, self.dialect)} = %s", (instance_id,))

    def fetch_related_one(self, table_name: str, column_name: str, value: Any) -> dict[str, Any] | None:
        return self._fetch_one(f"select * from {_quote_identifier(table_name, self.dialect)} where {_quote_identifier(column_name, self.dialect)} = %s", (value,))

    def fetch_related_many(self, table_name: str, column_name: str, value: Any) -> list[dict[str, Any]]:
        return self._fetch_all(f"select * from {_quote_identifier(table_name, self.dialect)} where {_quote_identifier(column_name, self.dialect)} = %s", (value,))

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


def _profile_sqlite_column(conn: sqlite3.Connection, table_name: str, column_name: str, row_count: int) -> ColumnProfile:
    quoted_table = f'"{table_name}"'
    quoted_column = f'"{column_name}"'
    null_count = conn.execute(f"select count(*) as count from {quoted_table} where {quoted_column} is null").fetchone()["count"]
    distinct_count = conn.execute(f"select count(distinct {quoted_column}) as count from {quoted_table}").fetchone()["count"]
    sample_rows = conn.execute(
        f"""
        select distinct {quoted_column} as value from {quoted_table}
        where {quoted_column} is not null
        limit 5
        """
    ).fetchall()
    samples = [row["value"] for row in sample_rows]
    null_ratio = 0 if row_count == 0 else null_count / row_count
    enum_candidate = row_count > 0 and 1 < distinct_count <= min(20, max(3, row_count))
    return ColumnProfile(samples=samples, null_ratio=null_ratio, distinct_count=distinct_count, enum_candidate=enum_candidate)


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
    enum_candidate = row_count > 0 and 1 < distinct_count <= min(20, max(3, row_count))
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
    return [dict(row) for row in rows]


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
