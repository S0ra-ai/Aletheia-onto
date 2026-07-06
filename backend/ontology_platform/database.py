from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable, Optional


DEFAULT_DATA_DIR = Path("data")
DEFAULT_PLATFORM_DB = DEFAULT_DATA_DIR / "platform.sqlite3"


SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    create table if not exists data_source (
        id integer primary key autoincrement,
        name text not null unique,
        domain text not null default '',
        system_category text not null default 'database',
        source_type text not null,
        connection_uri text not null,
        api_base_url text not null default '',
        api_headers text not null default '{}',
        capabilities text not null default '[]',
        created_at text not null default current_timestamp
    )
    """,
    """
    create table if not exists source_table (
        id integer primary key autoincrement,
        data_source_id integer not null references data_source(id),
        table_name text not null,
        row_count integer not null default 0,
        primary_key text,
        scanned_at text not null default current_timestamp,
        unique(data_source_id, table_name)
    )
    """,
    """
    create table if not exists source_column (
        id integer primary key autoincrement,
        source_table_id integer not null references source_table(id),
        column_name text not null,
        data_type text not null,
        nullable integer not null,
        ordinal integer not null,
        is_primary_key integer not null default 0,
        sample_values text not null default '[]',
        null_ratio real not null default 0,
        distinct_count integer not null default 0,
        enum_candidate integer not null default 0,
        unique(source_table_id, column_name)
    )
    """,
    """
    create table if not exists source_foreign_key (
        id integer primary key autoincrement,
        source_table_id integer not null references source_table(id),
        column_name text not null,
        target_table text not null,
        target_column text not null
    )
    """,
    """
    create table if not exists source_api (
        id integer primary key autoincrement,
        data_source_id integer not null references data_source(id),
        operation_code text not null,
        name text not null,
        method text not null,
        path text not null,
        semantic_action text not null default '',
        request_schema text not null default '{}',
        response_schema text not null default '{}',
        created_at text not null default current_timestamp,
        unique(data_source_id, operation_code)
    )
    """,
    """
    create table if not exists ontology (
        id integer primary key autoincrement,
        name text not null,
        domain text not null,
        version text not null,
        status text not null,
        published_at text,
        created_at text not null default current_timestamp,
        unique(name, version)
    )
    """,
    """
    create table if not exists business_object (
        id integer primary key autoincrement,
        ontology_id integer not null references ontology(id),
        code text not null,
        name text not null,
        description text not null default '',
        source_table_id integer references source_table(id),
        status text not null default 'draft',
        unique(ontology_id, code)
    )
    """,
    """
    create table if not exists business_attribute (
        id integer primary key autoincrement,
        object_id integer not null references business_object(id),
        code text not null,
        name text not null,
        data_type text not null,
        required integer not null default 0,
        source_column_id integer references source_column(id),
        unique(object_id, code)
    )
    """,
    """
    create table if not exists business_relation (
        id integer primary key autoincrement,
        ontology_id integer not null references ontology(id),
        source_object_id integer not null references business_object(id),
        target_object_id integer not null references business_object(id),
        code text not null,
        name text not null,
        relation_type text not null,
        source_foreign_key_id integer references source_foreign_key(id)
    )
    """,
    """
    create table if not exists semantic_mapping (
        id integer primary key autoincrement,
        ontology_id integer not null references ontology(id),
        mapping_type text not null,
        source_ref text not null,
        target_ref text not null,
        confidence real not null,
        status text not null,
        evidence text not null default '',
        reviewer text not null default '',
        reviewed_at text,
        created_at text not null default current_timestamp
    )
    """,
    """
    create table if not exists business_rule (
        id integer primary key autoincrement,
        ontology_id integer not null references ontology(id),
        code text not null,
        name text not null,
        rule_type text not null,
        scope_object_code text not null,
        expression text not null,
        severity text not null,
        natural_language text not null,
        status text not null default 'published',
        unique(ontology_id, code)
    )
    """,
    """
    create table if not exists inference_result (
        id integer primary key autoincrement,
        rule_id integer references business_rule(id),
        object_code text not null,
        instance_id text not null,
        result_type text not null,
        severity text not null,
        passed integer not null,
        explanation text not null,
        evidence text not null,
        created_at text not null default current_timestamp
    )
    """,
    """
    create table if not exists explanation_trace (
        id integer primary key autoincrement,
        inference_result_id integer references inference_result(id),
        ontology_version text not null,
        mapping_refs text not null,
        source_refs text not null,
        rule_refs text not null,
        created_at text not null default current_timestamp
    )
    """,
    """
    create table if not exists audit_log (
        id integer primary key autoincrement,
        actor text not null,
        action text not null,
        target_type text not null,
        target_id text not null,
        detail text not null,
        created_at text not null default current_timestamp
    )
    """,
    """
    create table if not exists model_invocation (
        id integer primary key autoincrement,
        provider text not null,
        model text not null,
        purpose text not null,
        prompt_tokens integer,
        completion_tokens integer,
        total_tokens integer,
        status text not null,
        error text not null default '',
        created_at text not null default current_timestamp
    )
    """,
    """
    create table if not exists decision_record (
        id integer primary key autoincrement,
        decision_id text not null unique,
        decision_type text not null,
        ontology_id integer,
        object_code text not null default '',
        instance_id text not null default '',
        operation_code text not null default '',
        status text not null,
        recommendation text not null default '',
        input_ref text not null default '{}',
        rule_results text not null default '[]',
        evidence text not null default '{}',
        actor text not null default 'semantic_kernel',
        created_at text not null default current_timestamp
    )
    """,
    """
    create table if not exists industry_blueprint (
        id text primary key,
        name text not null,
        domain text not null,
        description text not null default '',
        object_hints text not null default '{}',
        attribute_hints text not null default '{}',
        rule_templates text not null default '[]',
        table_keywords text not null default '[]',
        capability_tags text not null default '[]',
        source text not null default 'custom',
        created_at text not null default current_timestamp,
        updated_at text not null default current_timestamp
    )
    """,
    """
    create table if not exists model_config (
        id integer primary key check (id = 1),
        provider text not null default 'openrouter',
        api_key text not null default '',
        model text not null default '~openai/gpt-latest',
        base_url text not null default 'https://openrouter.ai/api/v1',
        http_referer text not null default '',
        app_title text not null default 'Ontology Transformation Platform',
        service_tier text not null default 'auto',
        timeout_seconds real not null default 30,
        updated_at text not null default current_timestamp
    )
    """,
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
)


def connect(db_path: Path | str = DEFAULT_PLATFORM_DB) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("pragma foreign_keys = on")
    return conn


def initialize_platform_db(db_path: Path | str = DEFAULT_PLATFORM_DB) -> None:
    with connect(db_path) as conn:
        for statement in SCHEMA_STATEMENTS:
            conn.execute(statement)
        for statement in MIGRATION_STATEMENTS:
            try:
                conn.execute(statement)
            except sqlite3.OperationalError as error:
                if "duplicate column name" not in str(error).lower():
                    raise
        _migrate_model_config_schema(conn)


def _migrate_model_config_schema(conn: sqlite3.Connection) -> None:
    columns = {row["name"] for row in conn.execute("pragma table_info(model_config)").fetchall()}
    if "api_key" in columns:
        return
    if not {"config_key", "config_value"}.issubset(columns):
        return

    legacy_rows = conn.execute("select config_key, config_value from model_config").fetchall()
    legacy = {row["config_key"]: row["config_value"] for row in legacy_rows}
    conn.execute("alter table model_config rename to model_config_legacy")
    conn.execute(
        """
        create table model_config (
            id integer primary key check (id = 1),
            provider text not null default 'openrouter',
            api_key text not null default '',
            model text not null default '~openai/gpt-latest',
            base_url text not null default 'https://openrouter.ai/api/v1',
            http_referer text not null default '',
            app_title text not null default 'Ontology Transformation Platform',
            service_tier text not null default 'auto',
            timeout_seconds real not null default 30,
            updated_at text not null default current_timestamp
        )
        """
    )
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


def fetch_one(conn: sqlite3.Connection, query: str, params: Iterable[object] = ()) -> Optional[sqlite3.Row]:
    return conn.execute(query, tuple(params)).fetchone()


def fetch_all(conn: sqlite3.Connection, query: str, params: Iterable[object] = ()) -> list[sqlite3.Row]:
    return list(conn.execute(query, tuple(params)).fetchall())
