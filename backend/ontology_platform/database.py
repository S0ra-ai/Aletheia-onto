from __future__ import annotations

import importlib
import logging
import os
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Optional, Protocol
from urllib.parse import urlparse


logger = logging.getLogger(__name__)

DEFAULT_DATA_DIR = Path("data")
DEFAULT_PLATFORM_DB = DEFAULT_DATA_DIR / "platform.sqlite3"

_platform_db_type: str = "sqlite"
_platform_db_uri: str = str(DEFAULT_PLATFORM_DB)
_platform_adapter: Optional["PlatformAdapter"] = None

SQLITE_BUSY_TIMEOUT_MS = int(os.environ.get("ONTOLOGY_PLATFORM_SQLITE_BUSY_TIMEOUT_MS", "5000"))


def _model_provider_base_url() -> str:
    """Default model endpoint, imported lazily to avoid a circular import."""
    from .config import MODEL_PROVIDER_DEFAULTS

    return MODEL_PROVIDER_DEFAULTS.base_url


@dataclass
class PlatformDbConfig:
    db_type: str = "sqlite"
    connection_uri: str = ""
    host: str = ""
    port: int = 0
    user: str = ""
    password: str = ""
    database: str = ""


def get_platform_config() -> PlatformDbConfig:
    return PlatformDbConfig(db_type=_platform_db_type, connection_uri=_platform_db_uri)


def configure_platform_db(db_type: str, connection_uri: str = "") -> None:
    global _platform_db_type, _platform_db_uri, _platform_adapter
    _platform_db_type = db_type
    _platform_db_uri = connection_uri if connection_uri else _default_uri(db_type)
    _platform_adapter = _create_adapter(db_type, _platform_db_uri)


def _default_uri(db_type: str) -> str:
    if db_type == "sqlite":
        return str(DEFAULT_PLATFORM_DB)
    if db_type in ("postgresql", "postgres"):
        return "postgresql://localhost:5432/ontology_platform"
    if db_type == "mysql":
        return "mysql://root:password@localhost:3306/ontology_platform"
    return str(DEFAULT_PLATFORM_DB)


def _create_adapter(db_type: str, connection_uri: str) -> PlatformAdapter:
    normalized = db_type.lower()
    if normalized == "sqlite":
        return SQLitePlatformAdapter(connection_uri)
    if normalized in ("postgresql", "postgres"):
        return PostgreSQLPlatformAdapter(connection_uri)
    if normalized == "mysql":
        return MySQLPlatformAdapter(connection_uri)
    raise ValueError(f"不支持的平台数据库类型: {db_type}")


class PlatformAdapter(Protocol):
    db_type: str
    connection_uri: str

    def connect(self) -> Any: ...

    def init_schema(self, conn: Any) -> None: ...

    def last_insert_id(self, conn: Any) -> int: ...


class PlatformConnection:
    def __init__(self, conn: Any, adapter: PlatformAdapter):
        self._conn = conn
        self._adapter = adapter
        self._closed = False

    def execute(self, sql: str, params: Iterable[object] = ()) -> Any:
        adapted_sql = _adapt_sql(sql, self._adapter.db_type)
        adapted_params = tuple(params)
        if hasattr(self._conn, "execute"):
            return self._conn.execute(adapted_sql, adapted_params)
        cursor = self._conn.cursor()
        cursor.execute(adapted_sql, adapted_params)
        return cursor

    def executemany(self, sql: str, params: Iterable[Iterable[object]]) -> Any:
        adapted_sql = _adapt_sql(sql, self._adapter.db_type)
        if hasattr(self._conn, "executemany"):
            return self._conn.executemany(adapted_sql, params)
        with self._conn.cursor() as cur:
            for param_set in params:
                cur.execute(adapted_sql, tuple(param_set))
            return cur

    def cursor(self) -> Any:
        if hasattr(self._conn, "cursor"):
            return self._conn.cursor()
        return self._conn

    def commit(self) -> None:
        if hasattr(self._conn, "commit"):
            self._conn.commit()

    def rollback(self) -> None:
        if hasattr(self._conn, "rollback"):
            self._conn.rollback()

    def close(self) -> None:
        if not self._closed and hasattr(self._conn, "close"):
            self._closed = True
            self._conn.close()

    def __enter__(self) -> "PlatformConnection":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        # Every driver behaves differently on context-manager exit: sqlite3
        # commits but keeps the connection open, pymysql closes without
        # committing, psycopg commits and closes. Owning the decision here is
        # what makes writes durable on all three platform databases.
        try:
            if exc_type is None:
                self.commit()
            else:
                try:
                    self.rollback()
                except Exception as rollback_error:
                    logger.warning("平台库回滚失败: %s", rollback_error)
        finally:
            self.close()

    def last_insert_id(self) -> int:
        return self._adapter.last_insert_id(self._conn)

    def raw(self) -> Any:
        return self._conn


_UPSERT_PATTERN = re.compile(
    r"on\s+conflict\s*\([^)]*\)\s*do\s+update\s+set\s+",
    re.IGNORECASE,
)
_EXCLUDED_PATTERN = re.compile(r"\bexcluded\.([a-z_][a-z0-9_]*)", re.IGNORECASE)


def _adapt_sql(sql: str, db_type: str) -> str:
    """Translate the SQLite-flavoured SQL used across the platform to a dialect."""
    normalized = db_type.lower()
    if normalized == "sqlite":
        return sql
    adapted = sql
    if normalized == "mysql":
        # MySQL has no `on conflict (...) do update set`; the equivalent is
        # `on duplicate key update`, and `excluded.col` becomes `values(col)`.
        match = _UPSERT_PATTERN.search(adapted)
        if match is not None:
            head, tail = adapted[: match.start()], adapted[match.end() :]
            tail = _EXCLUDED_PATTERN.sub(r"values(\1)", tail)
            adapted = f"{head}on duplicate key update {tail}"
    if normalized in ("postgresql", "postgres", "mysql"):
        adapted = adapted.replace("?", "%s")
    return adapted


def _adapt_placeholders(sql: str, db_type: str) -> str:
    """Backwards-compatible alias retained for callers outside this module."""
    return _adapt_sql(sql, db_type)


# -- SQLite Platform Adapter --


class SQLitePlatformAdapter:
    db_type = "sqlite"

    def __init__(self, connection_uri: str = ""):
        self.connection_uri = connection_uri or str(DEFAULT_PLATFORM_DB)

    def connect(self) -> sqlite3.Connection:
        path = Path(self.connection_uri)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, timeout=SQLITE_BUSY_TIMEOUT_MS / 1000)
        conn.row_factory = sqlite3.Row
        conn.execute("pragma foreign_keys = on")
        # Concurrent FastAPI worker threads otherwise collide with
        # "database is locked" as soon as two requests write at once.
        conn.execute("pragma journal_mode = wal")
        conn.execute(f"pragma busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
        return conn

    def init_schema(self, conn: sqlite3.Connection) -> None:
        for statement in self._schema_statements():
            conn.execute(statement)
        _apply_column_migrations(conn, self.db_type)
        self._migrate_model_config_schema(conn)
        conn.commit()

    def last_insert_id(self, conn: sqlite3.Connection) -> int:
        return int(conn.execute("select last_insert_rowid()").fetchone()[0])

    def _schema_statements(self) -> list[str]:
        return [_sqlite_ddl(stmt) for stmt in SCHEMA_DEFINITIONS]

    def _migrate_model_config_schema(self, conn: sqlite3.Connection) -> None:
        try:
            columns = {row["name"] for row in conn.execute("pragma table_info(model_config)").fetchall()}
        except Exception:
            columns = set()
        if "api_key" in columns:
            return
        if not {"config_key", "config_value"}.issubset(columns):
            return
        legacy_rows = conn.execute("select config_key, config_value from model_config").fetchall()
        legacy = {row["config_key"]: row["config_value"] for row in legacy_rows}
        conn.execute("alter table model_config rename to model_config_legacy")
        conn.execute(_sqlite_ddl(_MODEL_CONFIG_DDL))
        conn.execute(
            """
            insert into model_config (
                id, provider, api_key, model, base_url, http_referer,
                app_title, service_tier, timeout_seconds
            )
            values (1, 'openrouter', ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                legacy.get("api_key", ""),
                legacy.get("model", "~openai/gpt-latest"),
                legacy.get("base_url", _model_provider_base_url()),
                legacy.get("http_referer", ""),
                legacy.get("app_title", "Ontology Transformation Platform"),
                legacy.get("service_tier", "auto"),
                float(legacy.get("timeout_seconds") or 30),
            ),
        )


# -- PostgreSQL Platform Adapter --


class PostgreSQLPlatformAdapter:
    db_type = "postgresql"

    def __init__(self, connection_uri: str = ""):
        self.connection_uri = connection_uri or "postgresql://localhost:5432/ontology_platform"

    def connect(self) -> Any:
        psycopg = importlib.import_module("psycopg")
        rows = importlib.import_module("psycopg.rows")
        # The whole platform accesses columns by name (row["id"]); psycopg
        # returns tuples unless a dict row factory is configured.
        return psycopg.connect(self.connection_uri, connect_timeout=5, row_factory=rows.dict_row)

    def init_schema(self, conn: Any) -> None:
        # Postgres aborts the whole transaction on the first error, so each
        # statement gets its own transaction and migrations are only applied
        # after checking the live catalog.
        for statement in self._schema_statements():
            with conn.cursor() as cur:
                cur.execute(statement)
            conn.commit()
        _apply_column_migrations(conn, self.db_type)
        conn.commit()

    def last_insert_id(self, conn: Any) -> int:
        with conn.cursor() as cur:
            cur.execute("select lastval()")
            return _scalar(cur.fetchone())

    def _schema_statements(self) -> list[str]:
        return [_postgresql_ddl(stmt) for stmt in SCHEMA_DEFINITIONS]


# -- MySQL Platform Adapter --


class MySQLPlatformAdapter:
    db_type = "mysql"

    def __init__(self, connection_uri: str = ""):
        self.connection_uri = connection_uri or "mysql://root:password@localhost:3306/ontology_platform"

    def connect(self) -> Any:
        pymysql = importlib.import_module("pymysql")
        options = _parse_mysql_uri(self.connection_uri)
        options["connect_timeout"] = 5
        options["cursorclass"] = pymysql.cursors.DictCursor
        options["charset"] = "utf8mb4"
        return pymysql.connect(**options)

    def init_schema(self, conn: Any) -> None:
        for statement in self._schema_statements():
            with conn.cursor() as cur:
                cur.execute(statement)
        conn.commit()
        _apply_column_migrations(conn, self.db_type)
        conn.commit()

    def last_insert_id(self, conn: Any) -> int:
        with conn.cursor() as cur:
            cur.execute("select last_insert_id() as id")
            return _scalar(cur.fetchone())

    def _schema_statements(self) -> list[str]:
        return [_mysql_ddl(stmt) for stmt in SCHEMA_DEFINITIONS]


# -- Schema definitions (dialect-neutral) --

_MODEL_CONFIG_DDL = {
    "sqlite": "create table if not exists model_config (id integer primary key check (id = 1), provider text not null default 'openrouter', api_key text not null default '', model text not null default '~openai/gpt-latest', base_url text not null default 'https://openrouter.ai/api/v1', http_referer text not null default '', app_title text not null default 'Ontology Transformation Platform', service_tier text not null default 'auto', timeout_seconds real not null default 30, updated_at text not null default current_timestamp)",
    "postgresql": "create table if not exists model_config (id integer primary key check (id = 1), provider text not null default 'openrouter', api_key text not null default '', model text not null default '~openai/gpt-latest', base_url text not null default 'https://openrouter.ai/api/v1', http_referer text not null default '', app_title text not null default 'Ontology Transformation Platform', service_tier text not null default 'auto', timeout_seconds real not null default 30, updated_at timestamp not null default current_timestamp)",
    "mysql": "create table if not exists model_config (id integer primary key, provider varchar(100) not null default 'openrouter', api_key text not null default (''), model varchar(255) not null default '~openai/gpt-latest', base_url text not null default ('https://openrouter.ai/api/v1'), http_referer text not null default (''), app_title varchar(255) not null default 'Ontology Transformation Platform', service_tier varchar(50) not null default 'auto', timeout_seconds double not null default 30, updated_at datetime not null default current_timestamp)",
}


SCHEMA_DEFINITIONS: tuple[dict[str, str], ...] = (
    {
        "sqlite": "create table if not exists data_source (id integer primary key autoincrement, name text not null unique, domain text not null default '', system_category text not null default 'database', source_type text not null, connection_uri text not null, api_base_url text not null default '', api_headers text not null default '{}', capabilities text not null default '[]', created_at text not null default current_timestamp)",
        "postgresql": "create table if not exists data_source (id serial primary key, name text not null unique, domain text not null default '', system_category text not null default 'database', source_type text not null, connection_uri text not null, api_base_url text not null default '', api_headers text not null default '{}', capabilities text not null default '[]', created_at timestamp not null default current_timestamp)",
        "mysql": "create table if not exists data_source (id integer primary key auto_increment, name varchar(255) not null unique, domain varchar(255) not null default '', system_category varchar(100) not null default 'database', source_type varchar(100) not null, connection_uri text not null, api_base_url text not null default (''), api_headers text not null default ('{}'), capabilities text not null default ('[]'), created_at datetime not null default current_timestamp)",
    },
    {
        "sqlite": "create table if not exists source_table (id integer primary key autoincrement, data_source_id integer not null references data_source(id), table_name text not null, row_count integer not null default 0, primary_key text, scanned_at text not null default current_timestamp, unique(data_source_id, table_name))",
        "postgresql": "create table if not exists source_table (id serial primary key, data_source_id integer not null references data_source(id), table_name text not null, row_count integer not null default 0, primary_key text, scanned_at timestamp not null default current_timestamp, unique(data_source_id, table_name))",
        "mysql": "create table if not exists source_table (id integer primary key auto_increment, data_source_id integer not null references data_source(id), table_name varchar(255) not null, row_count integer not null default 0, primary_key text, scanned_at datetime not null default current_timestamp, unique(data_source_id, table_name))",
    },
    {
        "sqlite": "create table if not exists source_column (id integer primary key autoincrement, source_table_id integer not null references source_table(id), column_name text not null, data_type text not null, nullable integer not null, ordinal integer not null, is_primary_key integer not null default 0, sample_values text not null default '[]', null_ratio real not null default 0, distinct_count integer not null default 0, enum_candidate integer not null default 0, unique(source_table_id, column_name))",
        "postgresql": "create table if not exists source_column (id serial primary key, source_table_id integer not null references source_table(id), column_name text not null, data_type text not null, nullable integer not null, ordinal integer not null, is_primary_key integer not null default 0, sample_values text not null default '[]', null_ratio real not null default 0, distinct_count integer not null default 0, enum_candidate integer not null default 0, unique(source_table_id, column_name))",
        "mysql": "create table if not exists source_column (id integer primary key auto_increment, source_table_id integer not null references source_table(id), column_name varchar(255) not null, data_type varchar(255) not null, nullable tinyint not null, ordinal integer not null, is_primary_key tinyint not null default 0, sample_values text not null default ('[]'), null_ratio double not null default 0, distinct_count integer not null default 0, enum_candidate tinyint not null default 0, unique(source_table_id, column_name))",
    },
    {
        "sqlite": "create table if not exists source_foreign_key (id integer primary key autoincrement, source_table_id integer not null references source_table(id), column_name text not null, target_table text not null, target_column text not null)",
        "postgresql": "create table if not exists source_foreign_key (id serial primary key, source_table_id integer not null references source_table(id), column_name text not null, target_table text not null, target_column text not null)",
        "mysql": "create table if not exists source_foreign_key (id integer primary key auto_increment, source_table_id integer not null references source_table(id), column_name varchar(255) not null, target_table varchar(255) not null, target_column varchar(255) not null)",
    },
    {
        "sqlite": "create table if not exists source_api (id integer primary key autoincrement, data_source_id integer not null references data_source(id), operation_code text not null, name text not null, method text not null, path text not null, semantic_action text not null default '', request_schema text not null default '{}', response_schema text not null default '{}', created_at text not null default current_timestamp, unique(data_source_id, operation_code))",
        "postgresql": "create table if not exists source_api (id serial primary key, data_source_id integer not null references data_source(id), operation_code text not null, name text not null, method text not null, path text not null, semantic_action text not null default '', request_schema text not null default '{}', response_schema text not null default '{}', created_at timestamp not null default current_timestamp, unique(data_source_id, operation_code))",
        "mysql": "create table if not exists source_api (id integer primary key auto_increment, data_source_id integer not null references data_source(id), operation_code varchar(255) not null, name varchar(255) not null, method varchar(20) not null, path varchar(500) not null, semantic_action varchar(255) not null default '', request_schema text not null default ('{}'), response_schema text not null default ('{}'), created_at datetime not null default current_timestamp, unique(data_source_id, operation_code))",
    },
    {
        "sqlite": "create table if not exists ontology (id integer primary key autoincrement, name text not null, domain text not null, version text not null, status text not null, published_at text, created_at text not null default current_timestamp, unique(name, version))",
        "postgresql": "create table if not exists ontology (id serial primary key, name text not null, domain text not null, version text not null, status text not null, published_at timestamp, created_at timestamp not null default current_timestamp, unique(name, version))",
        "mysql": "create table if not exists ontology (id integer primary key auto_increment, name varchar(255) not null, domain varchar(255) not null, version varchar(50) not null, status varchar(50) not null, published_at datetime, created_at datetime not null default current_timestamp, unique(name, version))",
    },
    {
        "sqlite": "create table if not exists business_object (id integer primary key autoincrement, ontology_id integer not null references ontology(id), code text not null, name text not null, description text not null default '', source_table_id integer references source_table(id), status text not null default 'draft', unique(ontology_id, code))",
        "postgresql": "create table if not exists business_object (id serial primary key, ontology_id integer not null references ontology(id), code text not null, name text not null, description text not null default '', source_table_id integer references source_table(id), status text not null default 'draft', unique(ontology_id, code))",
        "mysql": "create table if not exists business_object (id integer primary key auto_increment, ontology_id integer not null references ontology(id), code varchar(255) not null, name varchar(255) not null, description text not null default (''), source_table_id integer references source_table(id), status varchar(50) not null default 'draft', unique(ontology_id, code))",
    },
    {
        "sqlite": "create table if not exists business_attribute (id integer primary key autoincrement, object_id integer not null references business_object(id), code text not null, name text not null, data_type text not null, required integer not null default 0, source_column_id integer references source_column(id), unique(object_id, code))",
        "postgresql": "create table if not exists business_attribute (id serial primary key, object_id integer not null references business_object(id), code text not null, name text not null, data_type text not null, required integer not null default 0, source_column_id integer references source_column(id), unique(object_id, code))",
        "mysql": "create table if not exists business_attribute (id integer primary key auto_increment, object_id integer not null references business_object(id), code varchar(255) not null, name varchar(255) not null, data_type varchar(255) not null, required tinyint not null default 0, source_column_id integer references source_column(id), unique(object_id, code))",
    },
    {
        "sqlite": "create table if not exists business_relation (id integer primary key autoincrement, ontology_id integer not null references ontology(id), source_object_id integer not null references business_object(id), target_object_id integer not null references business_object(id), code text not null, name text not null, relation_type text not null, source_foreign_key_id integer references source_foreign_key(id))",
        "postgresql": "create table if not exists business_relation (id serial primary key, ontology_id integer not null references ontology(id), source_object_id integer not null references business_object(id), target_object_id integer not null references business_object(id), code text not null, name text not null, relation_type text not null, source_foreign_key_id integer references source_foreign_key(id))",
        "mysql": "create table if not exists business_relation (id integer primary key auto_increment, ontology_id integer not null references ontology(id), source_object_id integer not null references business_object(id), target_object_id integer not null references business_object(id), code varchar(255) not null, name varchar(255) not null, relation_type varchar(100) not null, source_foreign_key_id integer references source_foreign_key(id))",
    },
    {
        "sqlite": "create table if not exists semantic_mapping (id integer primary key autoincrement, ontology_id integer not null references ontology(id), mapping_type text not null, source_ref text not null, target_ref text not null, confidence real not null, status text not null, evidence text not null default '', reviewer text not null default '', reviewed_at text, created_at text not null default current_timestamp)",
        "postgresql": "create table if not exists semantic_mapping (id serial primary key, ontology_id integer not null references ontology(id), mapping_type text not null, source_ref text not null, target_ref text not null, confidence real not null, status text not null, evidence text not null default '', reviewer text not null default '', reviewed_at timestamp, created_at timestamp not null default current_timestamp)",
        "mysql": "create table if not exists semantic_mapping (id integer primary key auto_increment, ontology_id integer not null references ontology(id), mapping_type varchar(100) not null, source_ref text not null, target_ref text not null, confidence double not null, status varchar(50) not null, evidence text not null default (''), reviewer varchar(255) not null default '', reviewed_at datetime, created_at datetime not null default current_timestamp)",
    },
    {
        "sqlite": "create table if not exists business_rule (id integer primary key autoincrement, ontology_id integer not null references ontology(id), code text not null, name text not null, rule_type text not null, scope_object_code text not null, expression text not null, severity text not null, natural_language text not null, status text not null default 'published', priority integer not null default 0, category text not null default '', effective_start text, effective_end text, depends_on text not null default '[]', unique(ontology_id, code))",
        "postgresql": "create table if not exists business_rule (id serial primary key, ontology_id integer not null references ontology(id), code text not null, name text not null, rule_type text not null, scope_object_code text not null, expression text not null, severity text not null, natural_language text not null, status text not null default 'published', priority integer not null default 0, category text not null default '', effective_start text, effective_end text, depends_on text not null default '[]', unique(ontology_id, code))",
        "mysql": "create table if not exists business_rule (id integer primary key auto_increment, ontology_id integer not null references ontology(id), code varchar(255) not null, name varchar(255) not null, rule_type varchar(100) not null, scope_object_code varchar(255) not null, expression text not null, severity varchar(50) not null, natural_language text not null, status varchar(50) not null default 'published', priority integer not null default 0, category varchar(255) not null default '', effective_start date, effective_end date, depends_on text not null default ('[]'), unique(ontology_id, code))",
    },
    {
        "sqlite": "create table if not exists inference_result (id integer primary key autoincrement, rule_id integer references business_rule(id), object_code text not null, instance_id text not null, result_type text not null, severity text not null, passed integer not null, explanation text not null, evidence text not null, created_at text not null default current_timestamp)",
        "postgresql": "create table if not exists inference_result (id serial primary key, rule_id integer references business_rule(id), object_code text not null, instance_id text not null, result_type text not null, severity text not null, passed integer not null, explanation text not null, evidence text not null, created_at timestamp not null default current_timestamp)",
        "mysql": "create table if not exists inference_result (id integer primary key auto_increment, rule_id integer references business_rule(id), object_code varchar(255) not null, instance_id varchar(500) not null, result_type varchar(100) not null, severity varchar(50) not null, passed tinyint not null, explanation text not null, evidence text not null, created_at datetime not null default current_timestamp)",
    },
    {
        "sqlite": "create table if not exists explanation_trace (id integer primary key autoincrement, inference_result_id integer references inference_result(id), ontology_version text not null, mapping_refs text not null, source_refs text not null, rule_refs text not null, created_at text not null default current_timestamp)",
        "postgresql": "create table if not exists explanation_trace (id serial primary key, inference_result_id integer references inference_result(id), ontology_version text not null, mapping_refs text not null, source_refs text not null, rule_refs text not null, created_at timestamp not null default current_timestamp)",
        "mysql": "create table if not exists explanation_trace (id integer primary key auto_increment, inference_result_id integer references inference_result(id), ontology_version varchar(255) not null, mapping_refs text not null, source_refs text not null, rule_refs text not null, created_at datetime not null default current_timestamp)",
    },
    {
        "sqlite": "create table if not exists audit_log (id integer primary key autoincrement, actor text not null, action text not null, target_type text not null, target_id text not null, detail text not null, created_at text not null default current_timestamp)",
        "postgresql": "create table if not exists audit_log (id serial primary key, actor text not null, action text not null, target_type text not null, target_id text not null, detail text not null, created_at timestamp not null default current_timestamp)",
        "mysql": "create table if not exists audit_log (id integer primary key auto_increment, actor varchar(255) not null, action varchar(255) not null, target_type varchar(255) not null, target_id varchar(255) not null, detail text not null, created_at datetime not null default current_timestamp)",
    },
    {
        "sqlite": "create table if not exists model_invocation (id integer primary key autoincrement, provider text not null, model text not null, purpose text not null, prompt_tokens integer, completion_tokens integer, total_tokens integer, status text not null, error text not null default '', created_at text not null default current_timestamp)",
        "postgresql": "create table if not exists model_invocation (id serial primary key, provider text not null, model text not null, purpose text not null, prompt_tokens integer, completion_tokens integer, total_tokens integer, status text not null, error text not null default '', created_at timestamp not null default current_timestamp)",
        "mysql": "create table if not exists model_invocation (id integer primary key auto_increment, provider varchar(255) not null, model varchar(255) not null, purpose varchar(255) not null, prompt_tokens integer, completion_tokens integer, total_tokens integer, status varchar(50) not null, error text not null default (''), created_at datetime not null default current_timestamp)",
    },
    {
        "sqlite": "create table if not exists decision_record (id integer primary key autoincrement, decision_id text not null unique, decision_type text not null, ontology_id integer, object_code text not null default '', instance_id text not null default '', operation_code text not null default '', status text not null, recommendation text not null default '', input_ref text not null default '{}', rule_results text not null default '[]', evidence text not null default '{}', actor text not null default 'semantic_kernel', created_at text not null default current_timestamp)",
        "postgresql": "create table if not exists decision_record (id serial primary key, decision_id text not null unique, decision_type text not null, ontology_id integer, object_code text not null default '', instance_id text not null default '', operation_code text not null default '', status text not null, recommendation text not null default '', input_ref text not null default '{}', rule_results text not null default '[]', evidence text not null default '{}', actor text not null default 'semantic_kernel', created_at timestamp not null default current_timestamp)",
        "mysql": "create table if not exists decision_record (id integer primary key auto_increment, decision_id varchar(255) not null unique, decision_type varchar(100) not null, ontology_id integer, object_code varchar(255) not null default '', instance_id varchar(500) not null default '', operation_code varchar(255) not null default '', status varchar(50) not null, recommendation text not null default (''), input_ref text not null default ('{}'), rule_results text not null default ('[]'), evidence text not null default ('{}'), actor varchar(255) not null default 'semantic_kernel', created_at datetime not null default current_timestamp)",
    },
    {
        "sqlite": "create table if not exists industry_blueprint (id text primary key, name text not null, domain text not null, description text not null default '', object_hints text not null default '{}', attribute_hints text not null default '{}', rule_templates text not null default '[]', table_keywords text not null default '[]', capability_tags text not null default '[]', source text not null default 'custom', created_at text not null default current_timestamp, updated_at text not null default current_timestamp)",
        "postgresql": "create table if not exists industry_blueprint (id text primary key, name text not null, domain text not null, description text not null default '', object_hints text not null default '{}', attribute_hints text not null default '{}', rule_templates text not null default '[]', table_keywords text not null default '[]', capability_tags text not null default '[]', source text not null default 'custom', created_at timestamp not null default current_timestamp, updated_at timestamp not null default current_timestamp)",
        "mysql": "create table if not exists industry_blueprint (id varchar(255) primary key, name varchar(255) not null, domain varchar(255) not null, description text not null default (''), object_hints text not null default ('{}'), attribute_hints text not null default ('{}'), rule_templates text not null default ('[]'), table_keywords text not null default ('[]'), capability_tags text not null default ('[]'), source varchar(100) not null default 'custom', created_at datetime not null default current_timestamp, updated_at datetime not null default current_timestamp)",
    },
    _MODEL_CONFIG_DDL,
)

@dataclass(frozen=True)
class ColumnMigration:
    """A column that must exist on an already-deployed platform database.

    Types are declared per dialect because `text` and `timestamp` are not
    portable. The runner checks the live catalog before issuing DDL, so it is
    idempotent without relying on driver-specific error strings.
    """

    table: str
    column: str
    sqlite_type: str
    postgresql_type: str
    mysql_type: str

    def ddl(self, db_type: str) -> str:
        column_type = {
            "sqlite": self.sqlite_type,
            "postgresql": self.postgresql_type,
            "postgres": self.postgresql_type,
            "mysql": self.mysql_type,
        }.get(db_type.lower(), self.sqlite_type)
        return f"alter table {self.table} add column {self.column} {column_type}"


COLUMN_MIGRATIONS: tuple[ColumnMigration, ...] = (
    ColumnMigration("data_source", "domain", "text not null default ''", "text not null default ''", "varchar(255) not null default ''"),
    ColumnMigration("data_source", "system_category", "text not null default 'database'", "text not null default 'database'", "varchar(100) not null default 'database'"),
    ColumnMigration("data_source", "capabilities", "text not null default '[]'", "text not null default '[]'", "text"),
    ColumnMigration("data_source", "api_base_url", "text not null default ''", "text not null default ''", "text"),
    ColumnMigration("data_source", "api_headers", "text not null default '{}'", "text not null default '{}'", "text"),
    ColumnMigration("ontology", "published_at", "text", "timestamp", "datetime"),
    ColumnMigration("semantic_mapping", "reviewer", "text not null default ''", "text not null default ''", "varchar(255) not null default ''"),
    ColumnMigration("semantic_mapping", "reviewed_at", "text", "timestamp", "datetime"),
    ColumnMigration("business_rule", "priority", "integer not null default 0", "integer not null default 0", "integer not null default 0"),
    ColumnMigration("business_rule", "category", "text not null default ''", "text not null default ''", "varchar(255) not null default ''"),
    ColumnMigration("business_rule", "effective_start", "text", "text", "date"),
    ColumnMigration("business_rule", "effective_end", "text", "text", "date"),
    ColumnMigration("business_rule", "depends_on", "text not null default '[]'", "text not null default '[]'", "text"),
)


def _existing_columns(conn: Any, table: str, db_type: str) -> set[str]:
    normalized = db_type.lower()
    try:
        if normalized == "sqlite":
            return {row["name"] for row in conn.execute(f"pragma table_info({table})").fetchall()}
        query = "select column_name from information_schema.columns where table_name = %s and table_schema = current_schema()"
        if normalized == "mysql":
            query = "select column_name from information_schema.columns where table_name = %s and table_schema = database()"
        with conn.cursor() as cur:
            cur.execute(query, (table,))
            rows = cur.fetchall()
        names: set[str] = set()
        for row in rows:
            if isinstance(row, dict):
                value = row.get("column_name") or row.get("COLUMN_NAME")
            else:
                value = row[0]
            if value:
                names.add(str(value).lower())
        return names
    except Exception as error:
        logger.warning("读取表 %s 的列信息失败: %s", table, error)
        return set()


def _apply_column_migrations(conn: Any, db_type: str) -> list[str]:
    """Add any missing columns, checking the catalog instead of catching errors."""
    applied: list[str] = []
    tables = {migration.table for migration in COLUMN_MIGRATIONS}
    existing = {table: _existing_columns(conn, table, db_type) for table in tables}
    for migration in COLUMN_MIGRATIONS:
        columns = existing.get(migration.table, set())
        if not columns:
            # Table is absent or unreadable; the base DDL already created the
            # column set for fresh installs, so there is nothing to migrate.
            continue
        if migration.column.lower() in columns:
            continue
        statement = migration.ddl(db_type)
        try:
            if db_type.lower() == "sqlite":
                conn.execute(statement)
            else:
                with conn.cursor() as cur:
                    cur.execute(statement)
            if hasattr(conn, "commit"):
                conn.commit()
            applied.append(statement)
        except Exception as error:
            logger.error("列迁移失败 %s: %s", statement, error)
            if hasattr(conn, "rollback"):
                conn.rollback()
            raise
    return applied


def _sqlite_ddl(stmt: dict[str, str]) -> str:
    return stmt.get("sqlite", list(stmt.values())[0])


def _postgresql_ddl(stmt: dict[str, str]) -> str:
    return stmt.get("postgresql", list(stmt.values())[0])


def _mysql_ddl(stmt: dict[str, str]) -> str:
    return stmt.get("mysql", list(stmt.values())[0])


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
    }


def _scalar(row: Any) -> int:
    """Read a single-column result across tuple and dict row factories."""
    if row is None:
        raise ValueError("数据库未返回自增主键")
    if isinstance(row, dict):
        return int(next(iter(row.values())))
    return int(row[0])


# -- Backward-compatible API --


def connect(db_path: Path | str = "") -> Any:
    global _platform_adapter
    if _platform_adapter is not None:
        return PlatformConnection(_platform_adapter.connect(), _platform_adapter)

    resolved = str(Path(db_path) if db_path else DEFAULT_PLATFORM_DB)
    adapter = SQLitePlatformAdapter(resolved)
    raw = adapter.connect()
    return PlatformConnection(raw, adapter)


def initialize_platform_db(db_path: Path | str = "") -> None:
    global _platform_adapter
    if _platform_adapter is not None:
        conn = _platform_adapter.connect()
        try:
            _platform_adapter.init_schema(conn)
        finally:
            try:
                conn.close()
            except Exception as error:
                logger.warning("关闭平台库连接失败: %s", error)
        return

    resolved = str(Path(db_path) if db_path else DEFAULT_PLATFORM_DB)
    adapter = SQLitePlatformAdapter(resolved)
    conn = adapter.connect()
    try:
        adapter.init_schema(conn)
    finally:
        conn.close()


def last_insert_id(conn: Any) -> int:
    if isinstance(conn, PlatformConnection):
        return conn.last_insert_id()
    return int(conn.execute("select last_insert_rowid()").fetchone()[0])


def fetch_one(conn: Any, query: str, params: Iterable[object] = ()) -> Optional[Any]:
    return conn.execute(query, tuple(params)).fetchone()


def fetch_all(conn: Any, query: str, params: Iterable[object] = ()) -> list[Any]:
    return list(conn.execute(query, tuple(params)).fetchall())
