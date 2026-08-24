"""Business events: what happened, as a first-class part of the ontology.

Generality item #9, and the last piece of the metamodel in
`docs/02-核心元模型设计.md` that had no implementation. Objects, attributes,
relations, states and rules were modelled; events were not.

That gap has a concrete consequence. The platform could answer

    「这份合同现在是什么状态？」            -- State, via the workflow
    「这份合同现在合规吗？」                -- Rule, via assessment

but not

    「这份合同为什么变成现在这样？」        -- needs the event history
    「上个月有多少份合同被驳回？」          -- needs events as data
    「谁在什么时候改了金额？」              -- needs events with a payload

A state without the events that produced it is a snapshot with no history: the
platform can say what is true, but not what happened. And "what happened" is what an
audit actually asks for.

## An event is a record, never a trigger

Recording an event does not run anything. Deliberately: an event that could fire
automation would make the audit trail load-bearing for side effects, and then a
replay of history -- backfilling, correcting, migrating -- would re-execute business
actions. Automation stays where it is (`automation.py`), driven by decisions.

## Events are append-only

There is no update and no delete. A recorded event that turned out to be wrong is
corrected by recording a compensating event, which is how a ledger works and the only
shape that keeps history honest. Deleting would leave a state with no explanation for
how it was reached.

## The payload is schema-checked, loosely

An event type declares the fields its payload should carry. A missing field is
reported on the record rather than refused: a legacy system that stopped sending one
field must not silently stop producing history, which is what a strict refusal would
cause. Extra fields are kept -- discarding data an integrator sent is worse than
storing a field nobody declared.

Stability: experimental (ADR-0007).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from .context import PlatformDb
from .database import connect, last_insert_id
from .schema import SchemaBundle

logger = logging.getLogger(__name__)

# What kind of change an event describes. Kept small and structural: these are the
# distinctions an audit or an explanation needs to make, not a domain taxonomy
# (ADR-0003 -- domain vocabulary comes from blueprints, not from platform code).
LIFECYCLE = "lifecycle"  # created, archived, deleted
STATE_CHANGE = "state_change"  # moved between workflow states
ATTRIBUTE_CHANGE = "attribute_change"  # a value was changed
INTERACTION = "interaction"  # someone did something to it
EXTERNAL = "external"  # something happened elsewhere that concerns it
EVENT_CATEGORIES = (LIFECYCLE, STATE_CHANGE, ATTRIBUTE_CHANGE, INTERACTION, EXTERNAL)

EVENT_CATEGORY_LABELS = {
    LIFECYCLE: "生命周期",
    STATE_CHANGE: "状态变更",
    ATTRIBUTE_CHANGE: "属性变更",
    INTERACTION: "业务交互",
    EXTERNAL: "外部事件",
}

# An instance's event history is read on every explanation, so it is capped. Hitting
# the cap is reported rather than silently truncating: a history that is quietly
# incomplete would make an explanation wrong rather than partial.
MAX_EVENT_HISTORY = 500

# Table names, referenced by both the DDL and the catalog probe. Defined once so the
# probe can never name a table the DDL did not create.
EVENT_TYPE_TABLE = "business_event_type"
EVENT_TABLE = "business_event"
EVENT_INSTANCE_INDEX = "idx_business_event_instance"

# The empty-JSON default, kept as a constant because it appears inside f-string DDL
# where a bare `'{}'` would be read as a format placeholder.
_EMPTY_JSON = "'{}'"


class EventError(ValueError):
    """Raised when an event type or record is invalid."""


@dataclass
class EventType:
    """A declared kind of thing that happens to instances of one object.

    Declared rather than free-form so history is queryable and reviewable: an event
    stream of arbitrary strings can be stored but not reasoned about, and «驳回» vs
    «拒绝» vs «rejected» would become three unrelated facts.
    """

    code: str
    name: str
    object_code: str
    category: str = INTERACTION
    # Field names the payload is expected to carry. Advisory (see module docstring).
    payload_fields: list[str] = field(default_factory=list)
    description: str = ""

    def validate(self) -> "EventType":
        if not self.code or not self.code.isidentifier():
            raise EventError(f"事件编码必须是合法标识符: {self.code!r}")
        if not self.name:
            raise EventError("事件名称不能为空")
        category = (self.category or INTERACTION).strip().lower()
        if category not in EVENT_CATEGORIES:
            raise EventError(f"不支持的事件类别: {self.category!r}。可选: {'、'.join(EVENT_CATEGORIES)}")
        self.category = category
        for name in self.payload_fields:
            if not str(name).isidentifier():
                raise EventError(f"载荷字段名必须是合法标识符: {name!r}")
        return self

    def to_json(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "objectCode": self.object_code,
            "category": self.category,
            "categoryLabel": EVENT_CATEGORY_LABELS.get(self.category, self.category),
            "payloadFields": list(self.payload_fields),
            "description": self.description,
        }

    @classmethod
    def from_row(cls, row: Any) -> "EventType":
        try:
            fields = json.loads(row["payload_fields"] or "[]")
        except (TypeError, ValueError):
            fields = []
        return cls(
            code=row["code"],
            name=row["name"],
            object_code=row["object_code"],
            category=row["category"],
            payload_fields=[str(item) for item in fields] if isinstance(fields, list) else [],
            description=row["description"] or "",
        )


# DDL is built from the table-name constants so the catalog probe and the create
# statements can never name different tables.
EVENT_SCHEMA: tuple[dict[str, str], ...] = (
    {
        "sqlite": """
        create table if not exists business_event_type (
            id integer primary key autoincrement,
            ontology_id integer not null references ontology(id),
            object_code text not null,
            code text not null,
            name text not null,
            category text not null default 'interaction',
            payload_fields text not null default '[]',
            description text not null default '',
            created_at text not null default current_timestamp,
            unique(ontology_id, object_code, code)
        )""",
        "postgresql": """
        create table if not exists business_event_type (
            id serial primary key,
            ontology_id integer not null references ontology(id),
            object_code text not null,
            code text not null,
            name text not null,
            category text not null default 'interaction',
            payload_fields text not null default '[]',
            description text not null default '',
            created_at timestamp not null default current_timestamp,
            unique(ontology_id, object_code, code)
        )""",
        "mysql": """
        create table if not exists business_event_type (
            id integer primary key auto_increment,
            ontology_id integer not null,
            object_code varchar(255) not null,
            code varchar(255) not null,
            name varchar(255) not null,
            category varchar(50) not null default 'interaction',
            payload_fields text,
            description text,
            created_at datetime not null default current_timestamp,
            unique key uniq_event_type (ontology_id, object_code, code)
        )""",
    },
    {
        # Append-only. No update or delete path exists: a wrong event is corrected by
        # recording a compensating one, which is the only shape that keeps history
        # honest.
        "sqlite": """
        create table if not exists business_event (
            id integer primary key autoincrement,
            ontology_id integer not null references ontology(id),
            object_code text not null,
            instance_id text not null,
            event_code text not null,
            category text not null default 'interaction',
            actor text not null default '',
            payload text not null default '{}',
            occurred_at text not null default current_timestamp,
            recorded_at text not null default current_timestamp,
            payload_warning text not null default '',
            correlation_id text not null default ''
        )""",
        "postgresql": """
        create table if not exists business_event (
            id serial primary key,
            ontology_id integer not null references ontology(id),
            object_code text not null,
            instance_id text not null,
            event_code text not null,
            category text not null default 'interaction',
            actor text not null default '',
            payload text not null default '{}',
            occurred_at timestamp not null default current_timestamp,
            recorded_at timestamp not null default current_timestamp,
            payload_warning text not null default '',
            correlation_id text not null default ''
        )""",
        "mysql": """
        create table if not exists business_event (
            id integer primary key auto_increment,
            ontology_id integer not null,
            object_code varchar(255) not null,
            instance_id varchar(255) not null,
            event_code varchar(255) not null,
            category varchar(50) not null default 'interaction',
            actor varchar(255) not null default '',
            payload text,
            occurred_at datetime not null default current_timestamp,
            recorded_at datetime not null default current_timestamp,
            payload_warning text,
            correlation_id varchar(255) not null default ''
        )""",
    },
)

# History is read per instance on every explanation, so the lookup path is indexed
# rather than left to a scan that grows with total event volume.
EVENT_INDEXES: tuple[dict[str, str], ...] = (
    {
        "sqlite": """
        create index if not exists idx_business_event_instance
        on business_event (ontology_id, object_code, instance_id)""",
        "postgresql": """
        create index if not exists idx_business_event_instance
        on business_event (ontology_id, object_code, instance_id)""",
        "mysql": """
        create index idx_business_event_instance
        on business_event (ontology_id, object_code, instance_id)""",
    },
)


# Tables and the per-instance index this module owns. The index is declared separately
# because MySQL has no `create index if not exists` and raises on a re-run, while
# `create table if not exists` is idempotent on all three dialects.
SCHEMA = SchemaBundle(
    name="events",
    tables=EVENT_SCHEMA,
    indexes=EVENT_INDEXES,
    table_names=(EVENT_TYPE_TABLE, EVENT_TABLE),
)
# Fails at import time if a rename updated the DDL but not the declared names, which
# would otherwise make the probe report "not configured" for tables that exist.
SCHEMA.verify_declared_names()


def event_tables_exist(conn: Any) -> bool:
    """Whether the event tables are present.

    A missing schema means the feature is not configured, which must read as an
    empty history rather than an error. Probed via the catalog, never by catching
    the error: on PostgreSQL a failed statement aborts the transaction, so every
    later command on the same connection would fail (ADR-0004).
    """
    return SCHEMA.has_tables(conn)


def init_event_schema(conn: Any) -> None:
    """Create the event tables. Idempotent -- startup runs it on every boot."""
    SCHEMA.apply(conn)


def declare_event_type(
    platform_db: PlatformDb,
    ontology_id: int,
    event_type: EventType,
    *,
    actor: str = "system",
) -> dict[str, Any]:
    """Declare a kind of event that can happen to instances of an object."""
    event_type.validate()
    with connect(platform_db) as conn:
        ontology = conn.execute("select status from ontology where id = ?", (ontology_id,)).fetchone()
        if ontology is None:
            raise EventError(f"本体不存在: {ontology_id}")
        if ontology["status"] == "published":
            raise EventError("已发布本体不可修改事件定义，请派生新版本。")
        if (
            conn.execute(
                "select id from business_object where ontology_id = ? and code = ?",
                (ontology_id, event_type.object_code),
            ).fetchone()
            is None
        ):
            raise EventError(f"业务对象不存在: {event_type.object_code}")

        existing = conn.execute(
            "select id from business_event_type where ontology_id = ? and object_code = ? and code = ?",
            (ontology_id, event_type.object_code, event_type.code),
        ).fetchone()
        payload_fields = json.dumps(event_type.payload_fields, ensure_ascii=False)
        if existing is not None:
            conn.execute(
                """
                update business_event_type
                set name = ?, category = ?, payload_fields = ?, description = ?
                where id = ?
                """,
                (
                    event_type.name,
                    event_type.category,
                    payload_fields,
                    event_type.description,
                    int(existing["id"]),
                ),
            )
        else:
            conn.execute(
                """
                insert into business_event_type
                    (ontology_id, object_code, code, name, category, payload_fields, description)
                values (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ontology_id,
                    event_type.object_code,
                    event_type.code,
                    event_type.name,
                    event_type.category,
                    payload_fields,
                    event_type.description,
                ),
            )
        conn.execute(
            "insert into audit_log (actor, action, target_type, target_id, detail) values (?, ?, ?, ?, ?)",
            (
                actor,
                "declare_event_type",
                "business_event_type",
                f"{event_type.object_code}.{event_type.code}",
                json.dumps(event_type.to_json(), ensure_ascii=False),
            ),
        )
    return event_type.to_json()


def list_event_types(platform_db: PlatformDb, ontology_id: int, object_code: str = "") -> list[dict[str, Any]]:
    clauses = ["ontology_id = ?"]
    params: list[Any] = [ontology_id]
    if object_code:
        clauses.append("object_code = ?")
        params.append(object_code)
    with connect(platform_db) as conn:
        if not event_tables_exist(conn):
            return []
        rows = conn.execute(
            f"select * from business_event_type where {' and '.join(clauses)} order by object_code, code",
            tuple(params),
        ).fetchall()
    return [EventType.from_row(row).to_json() for row in rows]


def record_event(
    platform_db: PlatformDb,
    ontology_id: int,
    object_code: str,
    instance_id: str,
    event_code: str,
    *,
    payload: Optional[dict[str, Any]] = None,
    actor: str = "system",
    occurred_at: str = "",
    correlation_id: str = "",
    declare_if_missing: Optional["EventType"] = None,
) -> dict[str, Any]:
    """Append one event to an instance's history.

    Recording does **not** trigger anything (see module docstring). An undeclared
    event code is refused: accepting it would let «驳回», «拒绝» and «rejected» become
    three unrelated facts, and history would stop being queryable.

    `declare_if_missing` is the one exception, used by the workflow mirror. A
    transition the workflow already permits is by definition a legitimate thing to
    have happened, and a published ontology refuses type declarations -- so without
    this, every state change on a published ontology would silently vanish from
    history. The declaration it inserts is a record of a fact, not a modelling
    change, which is why the published-immutability rule does not apply to it.
    """
    with connect(platform_db) as conn:
        declared = conn.execute(
            "select * from business_event_type where ontology_id = ? and object_code = ? and code = ?",
            (ontology_id, object_code, event_code),
        ).fetchone()
        if declared is None and declare_if_missing is not None:
            declare_if_missing.validate()
            conn.execute(
                """
                insert into business_event_type
                    (ontology_id, object_code, code, name, category, payload_fields, description)
                values (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ontology_id,
                    object_code,
                    event_code,
                    declare_if_missing.name,
                    declare_if_missing.category,
                    json.dumps(declare_if_missing.payload_fields, ensure_ascii=False),
                    declare_if_missing.description,
                ),
            )
            declared = conn.execute(
                "select * from business_event_type where ontology_id = ? and object_code = ? and code = ?",
                (ontology_id, object_code, event_code),
            ).fetchone()
        if declared is None:
            raise EventError(
                f"未声明的事件类型: {object_code}.{event_code}。请先声明事件类型，否则历史将无法按类型检索。"
            )
        event_type = EventType.from_row(declared)
        body = dict(payload or {})
        # Advisory: a legacy system that stopped sending a field must not silently
        # stop producing history, which a strict refusal would cause.
        missing = [name for name in event_type.payload_fields if name not in body]
        warning = ("载荷缺少已声明字段: " + "、".join(missing)) if missing else ""
        if warning:
            logger.info("事件 %s.%s %s", object_code, event_code, warning)

        columns: list[str] = [
            "ontology_id",
            "object_code",
            "instance_id",
            "event_code",
            "category",
            "actor",
            "payload",
            "payload_warning",
            "correlation_id",
        ]
        values: list[Any] = [
            ontology_id,
            object_code,
            str(instance_id),
            event_code,
            event_type.category,
            actor,
            json.dumps(body, ensure_ascii=False),
            warning,
            correlation_id,
        ]
        if occurred_at:
            # When the source system knows when it happened, that time is what
            # history must order by -- ingestion time would reorder a backfill.
            columns.append("occurred_at")
            values.append(occurred_at)
        placeholders = ", ".join("?" for _ in columns)
        conn.execute(
            f"insert into business_event ({', '.join(columns)}) values ({placeholders})",
            tuple(values),
        )
        event_id = last_insert_id(conn)
    return {
        "id": event_id,
        "objectCode": object_code,
        "instanceId": str(instance_id),
        "eventCode": event_code,
        "category": event_type.category,
        "actor": actor,
        "payload": body,
        "payloadWarning": warning,
        "correlationId": correlation_id,
    }


def instance_timeline(
    platform_db: PlatformDb,
    ontology_id: int,
    object_code: str,
    instance_id: str,
    limit: int = MAX_EVENT_HISTORY,
) -> dict[str, Any]:
    """One instance's event history, newest first.

    Returns `truncated` explicitly: a history that is quietly incomplete would make
    an explanation wrong rather than partial.
    """
    capped = max(1, min(int(limit or MAX_EVENT_HISTORY), MAX_EVENT_HISTORY))
    with connect(platform_db) as conn:
        if not event_tables_exist(conn):
            return {"items": [], "total": 0, "truncated": False}
        rows = conn.execute(
            """
            select be.*, bet.name as event_name
            from business_event be
            left join business_event_type bet
                on bet.ontology_id = be.ontology_id
               and bet.object_code = be.object_code
               and bet.code = be.event_code
            where be.ontology_id = ? and be.object_code = ? and be.instance_id = ?
            order by be.occurred_at desc, be.id desc
            """,
            (ontology_id, object_code, str(instance_id)),
        ).fetchall()
    total = len(rows)
    return {
        "items": [_event_row(row) for row in rows[:capped]],
        "total": total,
        "truncated": total > capped,
    }


def count_events(
    platform_db: PlatformDb,
    ontology_id: int,
    object_code: str,
    event_code: str,
    *,
    instance_id: str = "",
    since: str = "",
) -> int:
    """How many times something happened.

    This is what makes events *data* rather than a log: 「上个月有多少份合同被驳回」
    is a count over declared event types, answerable without reading text.
    """
    clauses = ["ontology_id = ?", "object_code = ?", "event_code = ?"]
    params: list[Any] = [ontology_id, object_code, event_code]
    if instance_id:
        clauses.append("instance_id = ?")
        params.append(str(instance_id))
    if since:
        clauses.append("occurred_at >= ?")
        params.append(since)
    with connect(platform_db) as conn:
        if not event_tables_exist(conn):
            return 0
        row = conn.execute(
            f"select count(*) as total from business_event where {' and '.join(clauses)}",
            tuple(params),
        ).fetchone()
    return int(row["total"]) if row is not None else 0


def _event_row(row: Any) -> dict[str, Any]:
    try:
        payload = json.loads(row["payload"] or "{}")
    except (TypeError, ValueError):
        payload = {}
    category = row["category"]
    return {
        "id": row["id"],
        "eventCode": row["event_code"],
        "eventName": _row_value(row, "event_name") or row["event_code"],
        "category": category,
        "categoryLabel": EVENT_CATEGORY_LABELS.get(category, category),
        "actor": row["actor"],
        "payload": payload,
        "payloadWarning": row["payload_warning"] or "",
        "occurredAt": str(row["occurred_at"]),
        "recordedAt": str(row["recorded_at"]),
        "correlationId": row["correlation_id"] or "",
    }


def _row_value(row: Any, column: str) -> Any:
    try:
        return row[column]
    except (KeyError, IndexError, TypeError):
        return None
