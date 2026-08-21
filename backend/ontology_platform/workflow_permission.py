from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .database import connect, last_insert_id


logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _uuid() -> str:
    return uuid.uuid4().hex[:16]


SCHEMA_SQL: tuple[dict[str, str], ...] = (
    {
        "sqlite": """
        create table if not exists workflow_definition (
            id integer primary key autoincrement,
            ontology_id integer not null references ontology(id),
            object_code text not null,
            name text not null,
            description text not null default '',
            initial_state text not null,
            status text not null default 'active',
            created_at text not null default current_timestamp,
            unique(ontology_id, object_code)
        )""",
        "postgresql": """
        create table if not exists workflow_definition (
            id serial primary key,
            ontology_id integer not null references ontology(id),
            object_code text not null,
            name text not null,
            description text not null default '',
            initial_state text not null,
            status text not null default 'active',
            created_at timestamp not null default current_timestamp,
            unique(ontology_id, object_code)
        )""",
        "mysql": """
        create table if not exists workflow_definition (
            id integer primary key auto_increment,
            ontology_id integer not null references ontology(id),
            object_code varchar(255) not null,
            name varchar(255) not null,
            description text not null default (''),
            initial_state varchar(100) not null,
            status varchar(50) not null default 'active',
            created_at datetime not null default current_timestamp,
            unique(ontology_id, object_code)
        )""",
    },
    {
        "sqlite": """
        create table if not exists workflow_state (
            id integer primary key autoincrement,
            workflow_id integer not null references workflow_definition(id) on delete cascade,
            code text not null,
            name text not null,
            description text not null default '',
            is_terminal integer not null default 0,
            color text not null default '#666666',
            sort_order integer not null default 0,
            unique(workflow_id, code)
        )""",
        "postgresql": """
        create table if not exists workflow_state (
            id serial primary key,
            workflow_id integer not null references workflow_definition(id) on delete cascade,
            code text not null,
            name text not null,
            description text not null default '',
            is_terminal boolean not null default false,
            color text not null default '#666666',
            sort_order integer not null default 0,
            unique(workflow_id, code)
        )""",
        "mysql": """
        create table if not exists workflow_state (
            id integer primary key auto_increment,
            workflow_id integer not null references workflow_definition(id) on delete cascade,
            code varchar(100) not null,
            name varchar(255) not null,
            description text not null default (''),
            is_terminal tinyint not null default 0,
            color varchar(20) not null default '#666666',
            sort_order integer not null default 0,
            unique(workflow_id, code)
        )""",
    },
    {
        "sqlite": """
        create table if not exists workflow_transition (
            id integer primary key autoincrement,
            workflow_id integer not null references workflow_definition(id) on delete cascade,
            from_state text not null,
            to_state text not null,
            action_code text not null,
            name text not null,
            guard_expression text not null default '',
            requires_review integer not null default 0,
            review_role text not null default '',
            sort_order integer not null default 0,
            unique(workflow_id, from_state, action_code)
        )""",
        "postgresql": """
        create table if not exists workflow_transition (
            id serial primary key,
            workflow_id integer not null references workflow_definition(id) on delete cascade,
            from_state text not null,
            to_state text not null,
            action_code text not null,
            name text not null,
            guard_expression text not null default '',
            requires_review boolean not null default false,
            review_role text not null default '',
            sort_order integer not null default 0,
            unique(workflow_id, from_state, action_code)
        )""",
        "mysql": """
        create table if not exists workflow_transition (
            id integer primary key auto_increment,
            workflow_id integer not null references workflow_definition(id) on delete cascade,
            from_state varchar(100) not null,
            to_state varchar(100) not null,
            action_code varchar(255) not null,
            name varchar(255) not null,
            guard_expression text not null default (''),
            requires_review tinyint not null default 0,
            review_role varchar(100) not null default '',
            sort_order integer not null default 0,
            unique(workflow_id, from_state, action_code)
        )""",
    },
    {
        "sqlite": """
        create table if not exists instance_workflow (
            id integer primary key autoincrement,
            workflow_id integer not null references workflow_definition(id),
            object_code text not null,
            instance_id text not null,
            current_state text not null,
            state_entered_at text not null default current_timestamp,
            updated_at text not null default current_timestamp,
            unique(workflow_id, instance_id)
        )""",
        "postgresql": """
        create table if not exists instance_workflow (
            id serial primary key,
            workflow_id integer not null references workflow_definition(id),
            object_code text not null,
            instance_id text not null,
            current_state text not null,
            state_entered_at timestamp not null default current_timestamp,
            updated_at timestamp not null default current_timestamp,
            unique(workflow_id, instance_id)
        )""",
        "mysql": """
        create table if not exists instance_workflow (
            id integer primary key auto_increment,
            workflow_id integer not null references workflow_definition(id),
            object_code varchar(255) not null,
            instance_id varchar(500) not null,
            current_state varchar(100) not null,
            state_entered_at datetime not null default current_timestamp,
            updated_at datetime not null default current_timestamp,
            unique(workflow_id, instance_id)
        )""",
    },
    {
        "sqlite": """
        create table if not exists workflow_history (
            id integer primary key autoincrement,
            instance_workflow_id integer not null references instance_workflow(id),
            from_state text not null,
            to_state text not null,
            action_code text not null,
            actor text not null default 'system',
            reason text not null default '',
            metadata text not null default '{}',
            created_at text not null default current_timestamp
        )""",
        "postgresql": """
        create table if not exists workflow_history (
            id serial primary key,
            instance_workflow_id integer not null references instance_workflow(id),
            from_state text not null,
            to_state text not null,
            action_code text not null,
            actor text not null default 'system',
            reason text not null default '',
            metadata text not null default '{}',
            created_at timestamp not null default current_timestamp
        )""",
        "mysql": """
        create table if not exists workflow_history (
            id integer primary key auto_increment,
            instance_workflow_id integer not null references instance_workflow(id),
            from_state varchar(100) not null,
            to_state varchar(100) not null,
            action_code varchar(255) not null,
            actor varchar(255) not null default 'system',
            reason text not null default (''),
            metadata text not null default ('{}'),
            created_at datetime not null default current_timestamp
        )""",
    },
    {
        "sqlite": """
        create table if not exists permission_role (
            id integer primary key autoincrement,
            code text not null unique,
            name text not null,
            description text not null default '',
            is_system integer not null default 0,
            created_at text not null default current_timestamp
        )""",
        "postgresql": """
        create table if not exists permission_role (
            id serial primary key,
            code text not null unique,
            name text not null,
            description text not null default '',
            is_system boolean not null default false,
            created_at timestamp not null default current_timestamp
        )""",
        "mysql": """
        create table if not exists permission_role (
            id integer primary key auto_increment,
            code varchar(100) not null unique,
            name varchar(255) not null,
            description text not null default (''),
            is_system tinyint not null default 0,
            created_at datetime not null default current_timestamp
        )""",
    },
    {
        "sqlite": """
        create table if not exists permission_policy (
            id integer primary key autoincrement,
            role_id integer not null references permission_role(id) on delete cascade,
            object_code text not null,
            can_read integer not null default 1,
            can_write integer not null default 0,
            can_execute integer not null default 0,
            can_delete integer not null default 0,
            filter_expression text not null default '',
            description text not null default '',
            unique(role_id, object_code)
        )""",
        "postgresql": """
        create table if not exists permission_policy (
            id serial primary key,
            role_id integer not null references permission_role(id) on delete cascade,
            object_code text not null,
            can_read boolean not null default true,
            can_write boolean not null default false,
            can_execute boolean not null default false,
            can_delete boolean not null default false,
            filter_expression text not null default '',
            description text not null default '',
            unique(role_id, object_code)
        )""",
        "mysql": """
        create table if not exists permission_policy (
            id integer primary key auto_increment,
            role_id integer not null references permission_role(id) on delete cascade,
            object_code varchar(255) not null,
            can_read tinyint not null default 1,
            can_write tinyint not null default 0,
            can_execute tinyint not null default 0,
            can_delete tinyint not null default 0,
            filter_expression text not null default (''),
            description text not null default (''),
            unique(role_id, object_code)
        )""",
    },
    {
        "sqlite": """
        create table if not exists tool_definition (
            id integer primary key autoincrement,
            code text not null unique,
            name text not null,
            description text not null default '',
            tool_type text not null default 'function',
            input_schema text not null default '{}',
            risk_level text not null default 'low',
            requires_review integer not null default 0,
            status text not null default 'active',
            created_at text not null default current_timestamp
        )""",
        "postgresql": """
        create table if not exists tool_definition (
            id serial primary key,
            code text not null unique,
            name text not null,
            description text not null default '',
            tool_type text not null default 'function',
            input_schema text not null default '{}',
            risk_level text not null default 'low',
            requires_review boolean not null default false,
            status text not null default 'active',
            created_at timestamp not null default current_timestamp
        )""",
        "mysql": """
        create table if not exists tool_definition (
            id integer primary key auto_increment,
            code varchar(100) not null unique,
            name varchar(255) not null,
            description text not null default (''),
            tool_type varchar(50) not null default 'function',
            input_schema text not null default ('{}'),
            risk_level varchar(50) not null default 'low',
            requires_review tinyint not null default 0,
            status varchar(50) not null default 'active',
            created_at datetime not null default current_timestamp
        )""",
    },
    {
        "sqlite": """
        create table if not exists tool_authorization (
            id integer primary key autoincrement,
            role_id integer not null references permission_role(id) on delete cascade,
            tool_id integer not null references tool_definition(id) on delete cascade,
            allowed integer not null default 1,
            max_calls_per_hour integer not null default 100,
            unique(role_id, tool_id)
        )""",
        "postgresql": """
        create table if not exists tool_authorization (
            id serial primary key,
            role_id integer not null references permission_role(id) on delete cascade,
            tool_id integer not null references tool_definition(id) on delete cascade,
            allowed boolean not null default true,
            max_calls_per_hour integer not null default 100,
            unique(role_id, tool_id)
        )""",
        "mysql": """
        create table if not exists tool_authorization (
            id integer primary key auto_increment,
            role_id integer not null references permission_role(id) on delete cascade,
            tool_id integer not null references tool_definition(id) on delete cascade,
            allowed tinyint not null default 1,
            max_calls_per_hour integer not null default 100,
            unique(role_id, tool_id)
        )""",
    },
    {
        "sqlite": """
        create table if not exists tool_execution_log (
            id integer primary key autoincrement,
            tool_id integer references tool_definition(id),
            tool_code text not null,
            agent_role text not null default '',
            object_code text not null default '',
            instance_id text not null default '',
            input_args text not null default '{}',
            result_summary text not null default '',
            status text not null default 'success',
            error text not null default '',
            duration_ms integer not null default 0,
            requires_review integer not null default 0,
            reviewed_by text,
            reviewed_at text,
            review_decision text,
            created_at text not null default current_timestamp
        )""",
        "postgresql": """
        create table if not exists tool_execution_log (
            id serial primary key,
            tool_id integer references tool_definition(id),
            tool_code text not null,
            agent_role text not null default '',
            object_code text not null default '',
            instance_id text not null default '',
            input_args text not null default '{}',
            result_summary text not null default '',
            status text not null default 'success',
            error text not null default '',
            duration_ms integer not null default 0,
            requires_review boolean not null default false,
            reviewed_by text,
            reviewed_at timestamp,
            review_decision text,
            created_at timestamp not null default current_timestamp
        )""",
        "mysql": """
        create table if not exists tool_execution_log (
            id integer primary key auto_increment,
            tool_id integer references tool_definition(id),
            tool_code varchar(100) not null,
            agent_role varchar(100) not null default '',
            object_code varchar(255) not null default '',
            instance_id varchar(500) not null default '',
            input_args text not null default ('{}'),
            result_summary text not null default (''),
            status varchar(50) not null default 'success',
            error text not null default (''),
            duration_ms integer not null default 0,
            requires_review tinyint not null default 0,
            reviewed_by varchar(255),
            reviewed_at datetime,
            review_decision varchar(50),
            created_at datetime not null default current_timestamp
        )""",
    },
)


def init_workflow_and_permission_schema(conn: Any) -> None:
    from .database import _mysql_ddl, _postgresql_ddl, _sqlite_ddl

    db_type = getattr(getattr(conn, "_adapter", None), "db_type", "sqlite")

    for stmt_dict in SCHEMA_SQL:
        if db_type == "sqlite":
            sql = _sqlite_ddl(stmt_dict)
        elif db_type in ("postgresql", "postgres"):
            sql = _postgresql_ddl(stmt_dict)
        elif db_type == "mysql":
            sql = _mysql_ddl(stmt_dict)
        else:
            sql = _sqlite_ddl(stmt_dict)
        # A failure here means the workflow and permission features are broken,
        # so surface it at startup rather than at first use.
        conn.execute(sql)


# ============================================================
# Workflow Definition CRUD
# ============================================================

def create_workflow(
    platform_db: Path | str,
    ontology_id: int,
    object_code: str,
    name: str,
    description: str = "",
    initial_state: str = "draft",
) -> dict[str, Any]:
    with connect(platform_db) as conn:
        conn.execute(
            "insert into workflow_definition (ontology_id, object_code, name, description, initial_state) values (?, ?, ?, ?, ?)",
            (ontology_id, object_code, name, description, initial_state),
        )
        wf_id = last_insert_id(conn)
        _seed_default_states(conn, wf_id, initial_state)
        _seed_default_transitions(conn, wf_id)
        conn.commit()
        return get_workflow(platform_db, wf_id)


def get_workflow(platform_db: Path | str, workflow_id: int) -> dict[str, Any]:
    with connect(platform_db) as conn:
        wf = conn.execute("select * from workflow_definition where id = ?", (workflow_id,)).fetchone()
        if wf is None:
            raise ValueError(f"工作流 {workflow_id} 不存在")
        result = dict(wf)
        result["states"] = [dict(r) for r in conn.execute(
            "select * from workflow_state where workflow_id = ? order by sort_order", (workflow_id,)
        ).fetchall()]
        result["transitions"] = [dict(r) for r in conn.execute(
            "select * from workflow_transition where workflow_id = ? order by sort_order", (workflow_id,)
        ).fetchall()]
        return result


def get_workflow_by_object(platform_db: Path | str, ontology_id: int, object_code: str) -> dict[str, Any] | None:
    with connect(platform_db) as conn:
        row = conn.execute(
            "select id from workflow_definition where ontology_id = ? and object_code = ?",
            (ontology_id, object_code),
        ).fetchone()
        if row is None:
            return None
        return get_workflow(platform_db, int(row["id"]))


def list_workflows(platform_db: Path | str, ontology_id: int | None = None) -> list[dict[str, Any]]:
    with connect(platform_db) as conn:
        if ontology_id:
            rows = conn.execute(
                "select * from workflow_definition where ontology_id = ? order by id", (ontology_id,)
            ).fetchall()
        else:
            rows = conn.execute("select * from workflow_definition order by id").fetchall()
        return [dict(r) for r in rows]


def delete_workflow(platform_db: Path | str, workflow_id: int) -> None:
    with connect(platform_db) as conn:
        conn.execute("delete from workflow_definition where id = ?", (workflow_id,))
        conn.commit()


# ============================================================
# State Management
# ============================================================

def add_workflow_state(
    platform_db: Path | str,
    workflow_id: int,
    code: str,
    name: str,
    description: str = "",
    is_terminal: bool = False,
    color: str = "#666666",
    sort_order: int = 0,
) -> dict[str, Any]:
    with connect(platform_db) as conn:
        conn.execute(
            "insert into workflow_state (workflow_id, code, name, description, is_terminal, color, sort_order) values (?, ?, ?, ?, ?, ?, ?)",
            (workflow_id, code, name, description, 1 if is_terminal else 0, color, sort_order),
        )
        conn.commit()
        row = conn.execute("select * from workflow_state where workflow_id = ? and code = ?", (workflow_id, code)).fetchone()
        return dict(row)


def add_workflow_transition(
    platform_db: Path | str,
    workflow_id: int,
    from_state: str,
    to_state: str,
    action_code: str,
    name: str,
    guard_expression: str = "",
    requires_review: bool = False,
    review_role: str = "",
    sort_order: int = 0,
) -> dict[str, Any]:
    with connect(platform_db) as conn:
        conn.execute(
            """insert into workflow_transition
            (workflow_id, from_state, to_state, action_code, name, guard_expression, requires_review, review_role, sort_order)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (workflow_id, from_state, to_state, action_code, name, guard_expression, 1 if requires_review else 0, review_role, sort_order),
        )
        conn.commit()
        row = conn.execute(
            "select * from workflow_transition where workflow_id = ? and from_state = ? and action_code = ?",
            (workflow_id, from_state, action_code),
        ).fetchone()
        return dict(row)


# ============================================================
# Instance State Machine
# ============================================================

def enter_workflow(
    platform_db: Path | str,
    workflow_id: int,
    object_code: str,
    instance_id: str,
) -> dict[str, Any]:
    with connect(platform_db) as conn:
        wf = conn.execute("select initial_state from workflow_definition where id = ?", (workflow_id,)).fetchone()
        if wf is None:
            raise ValueError(f"工作流 {workflow_id} 不存在")
        initial = wf["initial_state"]
        existing = conn.execute(
            "select id from instance_workflow where workflow_id = ? and instance_id = ?",
            (workflow_id, instance_id),
        ).fetchone()
        if existing:
            raise ValueError(f"实例 {instance_id} 已在工作流中")
        conn.execute(
            "insert into instance_workflow (workflow_id, object_code, instance_id, current_state) values (?, ?, ?, ?)",
            (workflow_id, object_code, instance_id, initial),
        )
        iw_id = last_insert_id(conn)
        conn.execute(
            "insert into workflow_history (instance_workflow_id, from_state, to_state, action_code, actor, reason) values (?, '', ?, 'init', 'system', '进入工作流')",
            (iw_id, initial),
        )
        conn.commit()
        return _get_instance_state(conn, iw_id)


def get_instance_state(platform_db: Path | str, workflow_id: int, instance_id: str) -> dict[str, Any] | None:
    with connect(platform_db) as conn:
        row = conn.execute(
            "select id from instance_workflow where workflow_id = ? and instance_id = ?",
            (workflow_id, instance_id),
        ).fetchone()
        if row is None:
            return None
        return _get_instance_state(conn, int(row["id"]))


def get_available_actions(platform_db: Path | str, workflow_id: int, instance_id: str) -> list[dict[str, Any]]:
    with connect(platform_db) as conn:
        inst = conn.execute(
            "select current_state from instance_workflow where workflow_id = ? and instance_id = ?",
            (workflow_id, instance_id),
        ).fetchone()
        if inst is None:
            return []
        current = inst["current_state"]
        rows = conn.execute(
            "select * from workflow_transition where workflow_id = ? and from_state = ? order by sort_order",
            (workflow_id, current),
        ).fetchall()
        return [dict(r) for r in rows]


def transition_instance(
    platform_db: Path | str,
    workflow_id: int,
    instance_id: str,
    action_code: str,
    actor: str = "system",
    reason: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    with connect(platform_db) as conn:
        inst = conn.execute(
            "select id, current_state from instance_workflow where workflow_id = ? and instance_id = ?",
            (workflow_id, instance_id),
        ).fetchone()
        if inst is None:
            raise ValueError(f"实例 {instance_id} 不在工作流 {workflow_id} 中")
        iw_id = int(inst["id"])
        current = inst["current_state"]
        transition = conn.execute(
            "select * from workflow_transition where workflow_id = ? and from_state = ? and action_code = ?",
            (workflow_id, current, action_code),
        ).fetchone()
        if transition is None:
            raise ValueError(f"当前状态 '{current}' 不允许执行动作 '{action_code}'")
        to_state = transition["to_state"]
        now = _now()
        conn.execute(
            "update instance_workflow set current_state = ?, state_entered_at = ?, updated_at = ? where id = ?",
            (to_state, now, now, iw_id),
        )
        conn.execute(
            "insert into workflow_history (instance_workflow_id, from_state, to_state, action_code, actor, reason, metadata) values (?, ?, ?, ?, ?, ?, ?)",
            (iw_id, current, to_state, action_code, actor, reason, json.dumps(metadata or {}, ensure_ascii=False)),
        )
        conn.commit()
        return _get_instance_state(conn, iw_id)


def get_instance_history(platform_db: Path | str, workflow_id: int, instance_id: str) -> list[dict[str, Any]]:
    with connect(platform_db) as conn:
        inst = conn.execute(
            "select id from instance_workflow where workflow_id = ? and instance_id = ?",
            (workflow_id, instance_id),
        ).fetchone()
        if inst is None:
            return []
        rows = conn.execute(
            "select * from workflow_history where instance_workflow_id = ? order by id",
            (int(inst["id"]),),
        ).fetchall()
        return [dict(r) for r in rows]


def _get_instance_state(conn: Any, iw_id: int) -> dict[str, Any]:
    row = conn.execute("select * from instance_workflow where id = ?", (iw_id,)).fetchone()
    result = dict(row) if row else {}
    if result:
        wf = conn.execute(
            "select name as workflow_name from workflow_definition where id = ?",
            (result.get("workflow_id"),),
        ).fetchone()
        if wf:
            result["workflowName"] = wf["workflow_name"]
        state_info = conn.execute(
            "select * from workflow_state where workflow_id = ? and code = ?",
            (result.get("workflow_id"), result.get("current_state")),
        ).fetchone()
        if state_info:
            result["stateInfo"] = dict(state_info)
    return result


def _seed_default_states(conn: Any, workflow_id: int, initial_state: str) -> None:
    defaults = [
        ("draft", "草稿", 0, "#94a3b8", 0),
        ("pending_review", "待审核", 0, "#f59e0b", 1),
        ("approved", "已通过", 0, "#22c55e", 2),
        ("rejected", "已驳回", 1, "#ef4444", 3),
        ("active", "执行中", 0, "#3b82f6", 4),
        ("completed", "已完成", 1, "#10b981", 5),
        ("cancelled", "已取消", 1, "#6b7280", 6),
    ]
    for code, name, is_terminal, color, sort_order in defaults:
        try:
            conn.execute(
                "insert into workflow_state (workflow_id, code, name, is_terminal, color, sort_order) values (?, ?, ?, ?, ?, ?)",
                (workflow_id, code, name, is_terminal, color, sort_order),
            )
        except Exception:
            pass


def _seed_default_transitions(conn: Any, workflow_id: int) -> None:
    defaults = [
        ("draft", "pending_review", "submit", "提交审核", 0),
        ("pending_review", "approved", "approve", "审核通过", 1),
        ("pending_review", "rejected", "reject", "审核驳回", 2),
        ("rejected", "draft", "revise", "修订重提", 3),
        ("approved", "active", "activate", "激活执行", 4),
        ("active", "completed", "complete", "完成", 5),
        ("active", "cancelled", "cancel", "取消", 6),
    ]
    for from_s, to_s, action, name, sort in defaults:
        try:
            conn.execute(
                "insert into workflow_transition (workflow_id, from_state, to_state, action_code, name, sort_order) values (?, ?, ?, ?, ?, ?)",
                (workflow_id, from_s, to_s, action, name, sort),
            )
        except Exception:
            pass


# ============================================================
# Permission CRUD
# ============================================================

def create_role(
    platform_db: Path | str,
    code: str,
    name: str,
    description: str = "",
    is_system: bool = False,
) -> dict[str, Any]:
    with connect(platform_db) as conn:
        conn.execute(
            "insert into permission_role (code, name, description, is_system) values (?, ?, ?, ?)",
            (code, name, description, 1 if is_system else 0),
        )
        rid = last_insert_id(conn)
        conn.commit()
        row = conn.execute("select * from permission_role where id = ?", (rid,)).fetchone()
        return dict(row)


def list_roles(platform_db: Path | str) -> list[dict[str, Any]]:
    with connect(platform_db) as conn:
        return [dict(r) for r in conn.execute("select * from permission_role order by id").fetchall()]


def upsert_permission_policy(
    platform_db: Path | str,
    role_id: int,
    object_code: str,
    can_read: bool = True,
    can_write: bool = False,
    can_execute: bool = False,
    can_delete: bool = False,
    filter_expression: str = "",
    description: str = "",
) -> dict[str, Any]:
    with connect(platform_db) as conn:
        existing = conn.execute(
            "select id from permission_policy where role_id = ? and object_code = ?",
            (role_id, object_code),
        ).fetchone()
        if existing:
            conn.execute(
                """update permission_policy set can_read=?, can_write=?, can_execute=?, can_delete=?,
                filter_expression=?, description=? where role_id=? and object_code=?""",
                (1 if can_read else 0, 1 if can_write else 0, 1 if can_execute else 0, 1 if can_delete else 0,
                 filter_expression, description, role_id, object_code),
            )
        else:
            conn.execute(
                """insert into permission_policy (role_id, object_code, can_read, can_write, can_execute, can_delete, filter_expression, description)
                values (?, ?, ?, ?, ?, ?, ?, ?)""",
                (role_id, object_code, 1 if can_read else 0, 1 if can_write else 0, 1 if can_execute else 0, 1 if can_delete else 0,
                 filter_expression, description),
            )
        conn.commit()
        row = conn.execute(
            "select * from permission_policy where role_id = ? and object_code = ?",
            (role_id, object_code),
        ).fetchone()
        return dict(row)


def check_permission(
    platform_db: Path | str,
    role_code: str,
    object_code: str,
    operation: str = "read",
) -> dict[str, Any]:
    with connect(platform_db) as conn:
        role = conn.execute("select id from permission_role where code = ?", (role_code,)).fetchone()
        if role is None:
            return {"allowed": False, "reason": f"角色 '{role_code}' 不存在"}
        policy = conn.execute(
            "select * from permission_policy where role_id = ? and object_code = ?",
            (int(role["id"]), object_code),
        ).fetchone()
        if policy is None:
            return {"allowed": False, "reason": f"角色 '{role_code}' 对对象 '{object_code}' 无策略"}
        col = f"can_{operation}"
        allowed = bool(policy[col]) if col in policy.keys() else False
        return {
            "allowed": allowed,
            "roleCode": role_code,
            "objectCode": object_code,
            "operation": operation,
            "filterExpression": policy["filter_expression"] or None,
        }


def list_policies(platform_db: Path | str, role_id: int | None = None) -> list[dict[str, Any]]:
    with connect(platform_db) as conn:
        if role_id:
            rows = conn.execute(
                "select pp.*, pr.code as role_code, pr.name as role_name from permission_policy pp join permission_role pr on pr.id = pp.role_id where pp.role_id = ? order by pp.id",
                (role_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "select pp.*, pr.code as role_code, pr.name as role_name from permission_policy pp join permission_role pr on pr.id = pp.role_id order by pp.id"
            ).fetchall()
        return [dict(r) for r in rows]


# ============================================================
# Tool Definition & Authorization
# ============================================================

def register_tool(
    platform_db: Path | str,
    code: str,
    name: str,
    description: str = "",
    tool_type: str = "function",
    input_schema: dict[str, Any] | None = None,
    risk_level: str = "low",
    requires_review: bool = False,
) -> dict[str, Any]:
    with connect(platform_db) as conn:
        conn.execute(
            """insert into tool_definition (code, name, description, tool_type, input_schema, risk_level, requires_review)
            values (?, ?, ?, ?, ?, ?, ?)""",
            (code, name, description, tool_type, json.dumps(input_schema or {}, ensure_ascii=False),
             risk_level, 1 if requires_review else 0),
        )
        tid = last_insert_id(conn)
        conn.commit()
        row = conn.execute("select * from tool_definition where id = ?", (tid,)).fetchone()
        return dict(row)


def list_tools(platform_db: Path | str) -> list[dict[str, Any]]:
    with connect(platform_db) as conn:
        return [dict(r) for r in conn.execute("select * from tool_definition order by id").fetchall()]


def authorize_tool(
    platform_db: Path | str,
    role_id: int,
    tool_id: int,
    allowed: bool = True,
    max_calls_per_hour: int = 100,
) -> dict[str, Any]:
    with connect(platform_db) as conn:
        existing = conn.execute(
            "select id from tool_authorization where role_id = ? and tool_id = ?",
            (role_id, tool_id),
        ).fetchone()
        if existing:
            conn.execute(
                "update tool_authorization set allowed=?, max_calls_per_hour=? where role_id=? and tool_id=?",
                (1 if allowed else 0, max_calls_per_hour, role_id, tool_id),
            )
        else:
            conn.execute(
                "insert into tool_authorization (role_id, tool_id, allowed, max_calls_per_hour) values (?, ?, ?, ?)",
                (role_id, tool_id, 1 if allowed else 0, max_calls_per_hour),
            )
        conn.commit()
        row = conn.execute(
            "select * from tool_authorization where role_id = ? and tool_id = ?",
            (role_id, tool_id),
        ).fetchone()
        return dict(row)


def check_tool_authorization(
    platform_db: Path | str,
    role_code: str,
    tool_code: str,
) -> dict[str, Any]:
    with connect(platform_db) as conn:
        role = conn.execute("select id from permission_role where code = ?", (role_code,)).fetchone()
        tool = conn.execute("select id, risk_level, requires_review from tool_definition where code = ?", (tool_code,)).fetchone()
        if role is None:
            return {"allowed": False, "reason": f"角色 '{role_code}' 不存在"}
        if tool is None:
            return {"allowed": False, "reason": f"工具 '{tool_code}' 不存在"}
        auth = conn.execute(
            "select * from tool_authorization where role_id = ? and tool_id = ?",
            (int(role["id"]), int(tool["id"])),
        ).fetchone()
        if auth is None:
            return {"allowed": False, "reason": f"角色 '{role_code}' 未被授权使用工具 '{tool_code}'"}
        allowed = bool(auth["allowed"])
        return {
            "allowed": allowed,
            "roleCode": role_code,
            "toolCode": tool_code,
            "riskLevel": tool["risk_level"],
            "requiresReview": bool(tool["requires_review"]),
            "maxCallsPerHour": int(auth["max_calls_per_hour"]),
        }


def log_tool_execution(
    platform_db: Path | str,
    tool_code: str,
    agent_role: str = "",
    object_code: str = "",
    instance_id: str = "",
    input_args: dict[str, Any] | None = None,
    result_summary: str = "",
    status: str = "success",
    error: str = "",
    duration_ms: int = 0,
    requires_review: bool = False,
) -> dict[str, Any]:
    with connect(platform_db) as conn:
        tool = conn.execute("select id from tool_definition where code = ?", (tool_code,)).fetchone()
        tool_id = int(tool["id"]) if tool else None
        conn.execute(
            """insert into tool_execution_log
            (tool_id, tool_code, agent_role, object_code, instance_id, input_args, result_summary, status, error, duration_ms, requires_review)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (tool_id, tool_code, agent_role, object_code, instance_id,
             json.dumps(input_args or {}, ensure_ascii=False), result_summary,
             status, error, duration_ms, 1 if requires_review else 0),
        )
        lid = last_insert_id(conn)
        conn.commit()
        row = conn.execute("select * from tool_execution_log where id = ?", (lid,)).fetchone()
        return dict(row)


def list_pending_reviews(platform_db: Path | str, limit: int = 50) -> list[dict[str, Any]]:
    with connect(platform_db) as conn:
        rows = conn.execute(
            """select * from tool_execution_log
            where requires_review = 1 and reviewed_by is null
            order by id desc limit ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def review_tool_execution(
    platform_db: Path | str,
    log_id: int,
    reviewer: str,
    decision: str,
) -> dict[str, Any]:
    if decision not in ("approved", "rejected"):
        raise ValueError("decision 必须是 approved 或 rejected")
    with connect(platform_db) as conn:
        conn.execute(
            "update tool_execution_log set reviewed_by = ?, reviewed_at = ?, review_decision = ? where id = ?",
            (reviewer, _now(), decision, log_id),
        )
        conn.commit()
        row = conn.execute("select * from tool_execution_log where id = ?", (log_id,)).fetchone()
        return dict(row)


def seed_default_tools(platform_db: Path | str) -> None:
    defaults = [
        ("explain_instance", "解释实例", "解释业务实例的详细属性和来源", "query", "low", False),
        ("assess_instance", "合规研判", "对业务实例执行规则合规性检查", "query", "medium", False),
        ("preflight_operation", "操作预检", "预检操作是否满足执行条件", "query", "medium", False),
        ("knowledge_overview", "知识概览", "查看业务对象的规则和关系概览", "query", "low", False),
        ("decision_consistency", "一致性评估", "批量评估决策一致性分布", "query", "low", False),
        ("submit_action", "提交操作", "提交业务操作到传统系统执行", "mutation", "high", True),
        ("modify_instance", "修改实例", "修改业务实例属性", "mutation", "high", True),
    ]
    for code, name, desc, tool_type, risk, review in defaults:
        try:
            register_tool(platform_db, code, name, desc, tool_type, risk_level=risk, requires_review=review)
        except Exception as error:
            # Re-seeding on every startup is expected to hit uniqueness
            # conflicts; anything else is worth surfacing in the log.
            logger.debug("跳过工具 %s 的初始化: %s", code, error)


def seed_default_roles_and_policies(platform_db: Path | str) -> None:
    roles = [
        ("admin", "系统管理员", "拥有所有权限", True),
        ("business_expert", "业务专家", "可查看和审核业务对象", False),
        ("analyst", "分析师", "只读访问业务数据", False),
        ("operator", "操作员", "可执行业务操作", False),
        ("ai_agent", "AI智能体", "通过智能体访问本体系统", False),
    ]
    role_ids = {}
    for code, name, desc, is_sys in roles:
        try:
            r = create_role(platform_db, code, name, desc, is_sys)
            role_ids[code] = r["id"]
        except Exception as error:
            logger.debug("角色 %s 已存在或创建失败: %s", code, error)
            with connect(platform_db) as conn:
                row = conn.execute("select id from permission_role where code = ?", (code,)).fetchone()
                if row:
                    role_ids[code] = int(row["id"])

    # Seed policies for the business objects that are actually modelled, so the
    # defaults follow whichever domain was onboarded instead of a built-in list.
    with connect(platform_db) as conn:
        objects = [
            row["code"]
            for row in conn.execute("select distinct code from business_object order by code").fetchall()
        ]
    if not objects:
        # Nothing modelled yet; object policies are seeded again on a later call
        # once a data source has been onboarded. Tool authorization below does
        # not depend on business objects, so it still runs.
        logger.debug("尚无业务对象，暂不初始化对象级权限策略")

    # read, write, execute, delete
    role_permissions: dict[str, tuple[bool, bool, bool, bool]] = {
        "admin": (True, True, True, True),
        "business_expert": (True, True, False, False),
        "analyst": (True, False, False, False),
        "operator": (True, False, True, False),
        "ai_agent": (True, False, False, False),
    }
    for role_code, permissions in role_permissions.items():
        if role_code not in role_ids:
            continue
        read, write, execute, delete = permissions
        for obj in objects:
            try:
                upsert_permission_policy(platform_db, role_ids[role_code], obj, read, write, execute, delete)
            except Exception as error:
                logger.debug("策略初始化跳过 %s/%s: %s", role_code, obj, error)

    tools = list_tools(platform_db)
    tool_map = {t["code"]: t["id"] for t in tools}
    ai_tools = ["explain_instance", "assess_instance", "preflight_operation", "knowledge_overview", "decision_consistency"]
    for tool_code in ai_tools:
        if tool_code in tool_map and "ai_agent" in role_ids:
            try:
                authorize_tool(platform_db, role_ids["ai_agent"], tool_map[tool_code], True)
            except Exception as error:
                logger.debug("工具授权初始化跳过 %s: %s", tool_code, error)
