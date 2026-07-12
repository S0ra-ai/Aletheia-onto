from __future__ import annotations

import importlib
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Optional, Protocol
from urllib.parse import urlparse


DEFAULT_DATA_DIR = Path("data")
DEFAULT_PLATFORM_DB = DEFAULT_DATA_DIR / "platform.sqlite3"

_platform_db_type: str = "sqlite"
_platform_db_uri: str = str(DEFAULT_PLATFORM_DB)
_platform_adapter: Optional["PlatformAdapter"] = None


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

    def execute(self, sql: str, params: Iterable[object] = ()) -> Any:
        adapted_sql = _adapt_placeholders(sql, self._adapter.db_type)
        adapted_params = tuple(params)
        return self._conn.execute(adapted_sql, adapted_params)

    def executemany(self, sql: str, params: Iterable[Iterable[object]]) -> Any:
        adapted_sql = _adapt_placeholders(sql, self._adapter.db_type)
        if hasattr(self._conn, "executemany"):
            return self._conn.executemany(adapted_sql, params)
        with self._conn.cursor() as cur:
            for param_set in params:
                cur.execute(adapted_sql, tuple(param_set))
            self._conn.commit()
            return cur

    def cursor(self) -> Any:
        if hasattr(self._conn, "cursor"):
            return self._conn.cursor()
        return self._conn

    def commit(self) -> None:
        if hasattr(self._conn, "commit"):
            self._conn.commit()

    def close(self) -> None:
        if hasattr(self._conn, "close"):
            self._conn.close()

    def __enter__(self) -> "PlatformConnection":
        return self

    def __exit__(self, *args: Any) -> None:
        if hasattr(self._conn, "__exit__"):
            self._conn.__exit__(*args)
        else:
            try:
                self._conn.close()
            except Exception:
                pass

    def last_insert_id(self) -> int:
        return self._adapter.last_insert_id(self._conn)

    def raw(self) -> Any:
        return self._conn


def _adapt_placeholders(sql: str, db_type: str) -> str:
    if db_type in ("postgresql", "postgres"):
        return sql.replace("?", "%s")
    return sql


# -- SQLite Platform Adapter --


class SQLitePlatformAdapter:
    db_type = "sqlite"

    def __init__(self, connection_uri: str = ""):
        self.connection_uri = connection_uri or str(DEFAULT_PLATFORM_DB)

    def connect(self) -> sqlite3.Connection:
        path = Path(self.connection_uri)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        conn.execute("pragma foreign_keys = on")
        return conn

    def init_schema(self, conn: sqlite3.Connection) -> None:
        for statement in self._schema_statements():
            conn.execute(statement)
        for statement in self._migration_statements():
            try:
                conn.execute(statement)
            except sqlite3.OperationalError as error:
                if "duplicate column name" not in str(error).lower():
                    raise
        self._migrate_model_config_schema(conn)

    def last_insert_id(self, conn: sqlite3.Connection) -> int:
        return int(conn.execute("select last_insert_rowid()").fetchone()[0])

    def _schema_statements(self) -> list[str]:
        return [_sqlite_ddl(stmt) for stmt in SCHEMA_DEFINITIONS]

    def _migration_statements(self) -> list[str]:
        return MIGRATION_STATEMENTS

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
                legacy.get("base_url", "https://openrouter.ai/api/v1"),
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
        return psycopg.connect(self.connection_uri, connect_timeout=5)

    def init_schema(self, conn: Any) -> None:
        for statement in self._schema_statements():
            with conn.cursor() as cur:
                cur.execute(statement)
        for statement in self._migration_statements():
            try:
                with conn.cursor() as cur:
                    cur.execute(statement)
            except Exception as error:
                if "already exists" not in str(error).lower():
                    pass
        conn.commit()

    def last_insert_id(self, conn: Any) -> int:
        with conn.cursor() as cur:
            cur.execute("select lastval()")
            return int(cur.fetchone()[0])

    def _schema_statements(self) -> list[str]:
        return [_postgresql_ddl(stmt) for stmt in SCHEMA_DEFINITIONS]

    def _migration_statements(self) -> list[str]:
        return [_postgresql_migration(stmt) for stmt in MIGRATION_STATEMENTS]


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
        for statement in self._migration_statements():
            try:
                with conn.cursor() as cur:
                    cur.execute(statement)
            except Exception:
                pass
        conn.commit()

    def last_insert_id(self, conn: Any) -> int:
        with conn.cursor() as cur:
            cur.execute("select last_insert_id() as id")
            result = cur.fetchone()
            return int(result["id"])

    def _schema_statements(self) -> list[str]:
        return [_mysql_ddl(stmt) for stmt in SCHEMA_DEFINITIONS]

    def _migration_statements(self) -> list[str]:
        return [_mysql_migration(stmt) for stmt in MIGRATION_STATEMENTS]


# -- Schema definitions (dialect-neutral) --

_MODEL_CONFIG_DDL = {
    "sqlite": "create table if not exists model_config (id integer primary key check (id = 1), provider text not null default 'openrouter', api_key text not null default '', model text not null default '~openai/gpt-latest', base_url text not null default 'https://openrouter.ai/api/v1', http_referer text not null default '', app_title text not null default 'Ontology Transformation Platform', service_tier text not null default 'auto', timeout_seconds real not null default 30, updated_at text not null default current_timestamp)",
    "postgresql": "create table if not exists model_config (id integer primary key check (id = 1), provider text not null default 'openrouter', api_key text not null default '', model text not null default '~openai/gpt-latest', base_url text not null default 'https://openrouter.ai/api/v1', http_referer text not null default '', app_title text not null default 'Ontology Transformation Platform', service_tier text not null default 'auto', timeout_seconds real not null default 30, updated_at timestamp not null default current_timestamp)",
    "mysql": "create table if not exists model_config (id integer primary key, provider varchar(100) not null default 'openrouter', api_key text not null default '', model varchar(255) not null default '~openai/gpt-latest', base_url text not null default 'https://openrouter.ai/api/v1', http_referer text not null default '', app_title varchar(255) not null default 'Ontology Transformation Platform', service_tier varchar(50) not null default 'auto', timeout_seconds double not null default 30, updated_at datetime not null default current_timestamp)",
}


SCHEMA_DEFINITIONS: tuple[dict[str, str], ...] = (
    {
        "sqlite": "create table if not exists data_source (id integer primary key autoincrement, name text not null unique, domain text not null default '', system_category text not null default 'database', source_type text not null, connection_uri text not null, api_base_url text not null default '', api_headers text not null default '{}', capabilities text not null default '[]', created_at text not null default current_timestamp)",
        "postgresql": "create table if not exists data_source (id serial primary key, name text not null unique, domain text not null default '', system_category text not null default 'database', source_type text not null, connection_uri text not null, api_base_url text not null default '', api_headers text not null default '{}', capabilities text not null default '[]', created_at timestamp not null default current_timestamp)",
        "mysql": "create table if not exists data_source (id integer primary key auto_increment, name varchar(255) not null unique, domain varchar(255) not null default '', system_category varchar(100) not null default 'database', source_type varchar(100) not null, connection_uri text not null, api_base_url text not null default '', api_headers text not null default '{}', capabilities text not null default '[]', created_at datetime not null default current_timestamp)",
    },
    {
        "sqlite": "create table if not exists source_table (id integer primary key autoincrement, data_source_id integer not null references data_source(id), table_name text not null, row_count integer not null default 0, primary_key text, scanned_at text not null default current_timestamp, unique(data_source_id, table_name))",
        "postgresql": "create table if not exists source_table (id serial primary key, data_source_id integer not null references data_source(id), table_name text not null, row_count integer not null default 0, primary_key text, scanned_at timestamp not null default current_timestamp, unique(data_source_id, table_name))",
        "mysql": "create table if not exists source_table (id integer primary key auto_increment, data_source_id integer not null references data_source(id), table_name varchar(255) not null, row_count integer not null default 0, primary_key text, scanned_at datetime not null default current_timestamp, unique(data_source_id, table_name))",
    },
    {
        "sqlite": "create table if not exists source_column (id integer primary key autoincrement, source_table_id integer not null references source_table(id), column_name text not null, data_type text not null, nullable integer not null, ordinal integer not null, is_primary_key integer not null default 0, sample_values text not null default '[]', null_ratio real not null default 0, distinct_count integer not null default 0, enum_candidate integer not null default 0, unique(source_table_id, column_name))",
        "postgresql": "create table if not exists source_column (id serial primary key, source_table_id integer not null references source_table(id), column_name text not null, data_type text not null, nullable integer not null, ordinal integer not null, is_primary_key integer not null default 0, sample_values text not null default '[]', null_ratio real not null default 0, distinct_count integer not null default 0, enum_candidate integer not null default 0, unique(source_table_id, column_name))",
        "mysql": "create table if not exists source_column (id integer primary key auto_increment, source_table_id integer not null references source_table(id), column_name varchar(255) not null, data_type varchar(255) not null, nullable tinyint not null, ordinal integer not null, is_primary_key tinyint not null default 0, sample_values text not null default '[]', null_ratio double not null default 0, distinct_count integer not null default 0, enum_candidate tinyint not null default 0, unique(source_table_id, column_name))",
    },
    {
        "sqlite": "create table if not exists source_foreign_key (id integer primary key autoincrement, source_table_id integer not null references source_table(id), column_name text not null, target_table text not null, target_column text not null)",
        "postgresql": "create table if not exists source_foreign_key (id serial primary key, source_table_id integer not null references source_table(id), column_name text not null, target_table text not null, target_column text not null)",
        "mysql": "create table if not exists source_foreign_key (id integer primary key auto_increment, source_table_id integer not null references source_table(id), column_name varchar(255) not null, target_table varchar(255) not null, target_column varchar(255) not null)",
    },
    {
        "sqlite": "create table if not exists source_api (id integer primary key autoincrement, data_source_id integer not null references data_source(id), operation_code text not null, name text not null, method text not null, path text not null, semantic_action text not null default '', request_schema text not null default '{}', response_schema text not null default '{}', created_at text not null default current_timestamp, unique(data_source_id, operation_code))",
        "postgresql": "create table if not exists source_api (id serial primary key, data_source_id integer not null references data_source(id), operation_code text not null, name text not null, method text not null, path text not null, semantic_action text not null default '', request_schema text not null default '{}', response_schema text not null default '{}', created_at timestamp not null default current_timestamp, unique(data_source_id, operation_code))",
        "mysql": "create table if not exists source_api (id integer primary key auto_increment, data_source_id integer not null references data_source(id), operation_code varchar(255) not null, name varchar(255) not null, method varchar(20) not null, path varchar(500) not null, semantic_action varchar(255) not null default '', request_schema text not null default '{}', response_schema text not null default '{}', created_at datetime not null default current_timestamp, unique(data_source_id, operation_code))",
    },
    {
        "sqlite": "create table if not exists ontology (id integer primary key autoincrement, name text not null, domain text not null, version text not null, status text not null, published_at text, created_at text not null default current_timestamp, unique(name, version))",
        "postgresql": "create table if not exists ontology (id serial primary key, name text not null, domain text not null, version text not null, status text not null, published_at timestamp, created_at timestamp not null default current_timestamp, unique(name, version))",
        "mysql": "create table if not exists ontology (id integer primary key auto_increment, name varchar(255) not null, domain varchar(255) not null, version varchar(50) not null, status varchar(50) not null, published_at datetime, created_at datetime not null default current_timestamp, unique(name, version))",
    },
    {
        "sqlite": "create table if not exists business_object (id integer primary key autoincrement, ontology_id integer not null references ontology(id), code text not null, name text not null, description text not null default '', source_table_id integer references source_table(id), status text not null default 'draft', unique(ontology_id, code))",
        "postgresql": "create table if not exists business_object (id serial primary key, ontology_id integer not null references ontology(id), code text not null, name text not null, description text not null default '', source_table_id integer references source_table(id), status text not null default 'draft', unique(ontology_id, code))",
        "mysql": "create table if not exists business_object (id integer primary key auto_increment, ontology_id integer not null references ontology(id), code varchar(255) not null, name varchar(255) not null, description text not null default '', source_table_id integer references source_table(id), status varchar(50) not null default 'draft', unique(ontology_id, code))",
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
        "mysql": "create table if not exists semantic_mapping (id integer primary key auto_increment, ontology_id integer not null references ontology(id), mapping_type varchar(100) not null, source_ref text not null, target_ref text not null, confidence double not null, status varchar(50) not null, evidence text not null default '', reviewer varchar(255) not null default '', reviewed_at datetime, created_at datetime not null default current_timestamp)",
    },
    {
        "sqlite": "create table if not exists business_rule (id integer primary key autoincrement, ontology_id integer not null references ontology(id), code text not null, name text not null, rule_type text not null, scope_object_code text not null, expression text not null, severity text not null, natural_language text not null, status text not null default 'published', priority integer not null default 0, category text not null default '', effective_start text, effective_end text, depends_on text not null default '[]', unique(ontology_id, code))",
        "postgresql": "create table if not exists business_rule (id serial primary key, ontology_id integer not null references ontology(id), code text not null, name text not null, rule_type text not null, scope_object_code text not null, expression text not null, severity text not null, natural_language text not null, status text not null default 'published', priority integer not null default 0, category text not null default '', effective_start text, effective_end text, depends_on text not null default '[]', unique(ontology_id, code))",
        "mysql": "create table if not exists business_rule (id integer primary key auto_increment, ontology_id integer not null references ontology(id), code varchar(255) not null, name varchar(255) not null, rule_type varchar(100) not null, scope_object_code varchar(255) not null, expression text not null, severity varchar(50) not null, natural_language text not null, status varchar(50) not null default 'published', priority integer not null default 0, category varchar(255) not null default '', effective_start date, effective_end date, depends_on text not null default '[]', unique(ontology_id, code))",
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
        "mysql": "create table if not exists model_invocation (id integer primary key auto_increment, provider varchar(255) not null, model varchar(255) not null, purpose varchar(255) not null, prompt_tokens integer, completion_tokens integer, total_tokens integer, status varchar(50) not null, error text not null default '', created_at datetime not null default current_timestamp)",
    },
    {
        "sqlite": "create table if not exists decision_record (id integer primary key autoincrement, decision_id text not null unique, decision_type text not null, ontology_id integer, object_code text not null default '', instance_id text not null default '', operation_code text not null default '', status text not null, recommendation text not null default '', input_ref text not null default '{}', rule_results text not null default '[]', evidence text not null default '{}', actor text not null default 'semantic_kernel', created_at text not null default current_timestamp)",
        "postgresql": "create table if not exists decision_record (id serial primary key, decision_id text not null unique, decision_type text not null, ontology_id integer, object_code text not null default '', instance_id text not null default '', operation_code text not null default '', status text not null, recommendation text not null default '', input_ref text not null default '{}', rule_results text not null default '[]', evidence text not null default '{}', actor text not null default 'semantic_kernel', created_at timestamp not null default current_timestamp)",
        "mysql": "create table if not exists decision_record (id integer primary key auto_increment, decision_id varchar(255) not null unique, decision_type varchar(100) not null, ontology_id integer, object_code varchar(255) not null default '', instance_id varchar(500) not null default '', operation_code varchar(255) not null default '', status varchar(50) not null, recommendation text not null default '', input_ref text not null default '{}', rule_results text not null default '[]', evidence text not null default '{}', actor varchar(255) not null default 'semantic_kernel', created_at datetime not null default current_timestamp)",
    },
    {
        "sqlite": "create table if not exists industry_blueprint (id text primary key, name text not null, domain text not null, description text not null default '', object_hints text not null default '{}', attribute_hints text not null default '{}', rule_templates text not null default '[]', table_keywords text not null default '[]', capability_tags text not null default '[]', source text not null default 'custom', created_at text not null default current_timestamp, updated_at text not null default current_timestamp)",
        "postgresql": "create table if not exists industry_blueprint (id text primary key, name text not null, domain text not null, description text not null default '', object_hints text not null default '{}', attribute_hints text not null default '{}', rule_templates text not null default '[]', table_keywords text not null default '[]', capability_tags text not null default '[]', source text not null default 'custom', created_at timestamp not null default current_timestamp, updated_at timestamp not null default current_timestamp)",
        "mysql": "create table if not exists industry_blueprint (id varchar(255) primary key, name varchar(255) not null, domain varchar(255) not null, description text not null default '', object_hints text not null default '{}', attribute_hints text not null default '{}', rule_templates text not null default '[]', table_keywords text not null default '[]', capability_tags text not null default '[]', source varchar(100) not null default 'custom', created_at datetime not null default current_timestamp, updated_at datetime not null default current_timestamp)",
    },
    _MODEL_CONFIG_DDL,
)

MIGRATION_STATEMENTS: tuple[str, ...] = (
    "alter table data_source add column domain text not null default ''",
    "alter table data_source add column system_category text not null default 'database'",
    "alter table data_source add column capabilities text not null default '[]'",
    "alter table data_source add column api_base_url text not null default ''",
    "alter table data_source add column api_headers text not null default '{}'",
    "alter table ontology add column published_at text",
    "alter table semantic_mapping add column reviewer text not null default ''",
    "alter table semantic_mapping add column reviewed_at text",
    "alter table business_rule add column priority integer not null default 0",
    "alter table business_rule add column category text not null default ''",
    "alter table business_rule add column effective_start text",
    "alter table business_rule add column effective_end text",
    "alter table business_rule add column depends_on text not null default '[]'",
)


def _sqlite_ddl(stmt: dict[str, str]) -> str:
    return stmt.get("sqlite", list(stmt.values())[0])


def _postgresql_ddl(stmt: dict[str, str]) -> str:
    return stmt.get("postgresql", list(stmt.values())[0])


def _mysql_ddl(stmt: dict[str, str]) -> str:
    return stmt.get("mysql", list(stmt.values())[0])


def _postgresql_migration(stmt: str) -> str:
    return stmt


def _mysql_migration(stmt: str) -> str:
    return stmt


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
        with conn:
            _platform_adapter.init_schema(conn)
        return

    resolved = str(Path(db_path) if db_path else DEFAULT_PLATFORM_DB)
    adapter = SQLitePlatformAdapter(resolved)
    conn = adapter.connect()
    with conn:
        adapter.init_schema(conn)


def last_insert_id(conn: Any) -> int:
    if isinstance(conn, PlatformConnection):
        return conn.last_insert_id()
    return int(conn.execute("select last_insert_rowid()").fetchone()[0])


def fetch_one(conn: Any, query: str, params: Iterable[object] = ()) -> Optional[Any]:
    return conn.execute(query, tuple(params)).fetchone()


def fetch_all(conn: Any, query: str, params: Iterable[object] = ()) -> list[Any]:
    return list(conn.execute(query, tuple(params)).fetchall())
