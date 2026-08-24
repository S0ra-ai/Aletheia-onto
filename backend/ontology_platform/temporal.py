"""Temporal validity: what was true, and when.

Generality item #8, the last piece of the metamodel. Rules already have validity windows;
attributes did not. An instance had exactly one value per attribute -- the current one --
which makes an entire class of question unanswerable:

    「这份合同**去年 12 月**的金额是多少？」
    「客户被拉黑**之前**签的合同要不要复核？」
    「按**签约时**的信用额度，这份合同当时合规吗？」

The third one is the reason this is not a reporting feature. A compliance verdict is
usually about a *past* moment: an audit in March asks whether the January approval was
correct given what was known in January. Re-assessing against today's values answers a
different question and returns a confidently wrong answer.

## Two timelines, deliberately distinguished

| Timeline | Question it answers |
|---|---|
| **valid time** | when the fact was true in the business |
| **transaction time** | when the platform learned it |

They differ whenever data arrives late or is corrected, which in legacy integration is
most of the time. A backdated correction changes what was *true* in January without
changing what the platform *knew* in January -- and an audit needs to distinguish "we
judged correctly on the information we had" from "the information was right all along".
Collapsing them into one timestamp makes that distinction unrecoverable.

## Assessment as-of a moment is exact, never interpolated

`as_of` selects the version whose valid window contains that instant. If no version
covers it, the attribute is **absent** rather than filled from the nearest neighbour: a
rule referencing it then fails closed (ADR-0002). Interpolating, or reaching for the
closest value, would fabricate a fact that was never recorded and put it in a verdict.

## History is append-only

Recording a new version closes the previous one; nothing is updated in place and nothing
is deleted. Same reasoning as the event stream (ADR-0014): a corrected value is a new
version, because rewriting history would leave a verdict citing a value that no longer
appears anywhere.

## What this deliberately does not do

It does **not** make the legacy system temporal. The platform records versions of the
attributes it was told about, at the times it was told. A source system that overwrites
values in place still loses its own history -- the platform can only preserve what it
observed, and it says so rather than implying completeness: `coverage` reports the window
it can actually answer for.

Stability: experimental (ADR-0007).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from .context import PlatformDb
from .database import connect, last_insert_id
from .schema import SchemaBundle

logger = logging.getLogger(__name__)

VERSION_TABLE = "attribute_version"

# The open end of a validity window. Stored as NULL rather than a sentinel date: a
# far-future sentinel eventually arrives, and every comparison would then silently start
# excluding current rows.
OPEN_ENDED = None

# An instance's history is read on every as-of assessment, so it is bounded. Hitting the
# cap is reported rather than silently truncating, because a partial history that looks
# complete would make an as-of verdict wrong rather than incomplete.
MAX_VERSIONS_PER_INSTANCE = 1_000


class TemporalError(ValueError):
    """Raised when a version record or an as-of query is invalid."""


ATTRIBUTE_VERSION_SCHEMA: tuple[dict[str, str], ...] = (
    {
        "sqlite": """
        create table if not exists attribute_version (
            id integer primary key autoincrement,
            ontology_id integer not null references ontology(id),
            object_code text not null,
            instance_id text not null,
            attribute_code text not null,
            value text,
            value_type text not null default 'text',
            valid_from text not null,
            valid_to text,
            recorded_at text not null default current_timestamp,
            actor text not null default '',
            source text not null default '',
            superseded_by integer
        )""",
        "postgresql": """
        create table if not exists attribute_version (
            id serial primary key,
            ontology_id integer not null references ontology(id),
            object_code text not null,
            instance_id text not null,
            attribute_code text not null,
            value text,
            value_type text not null default 'text',
            valid_from timestamp not null,
            valid_to timestamp,
            recorded_at timestamp not null default current_timestamp,
            actor text not null default '',
            source text not null default '',
            superseded_by integer
        )""",
        "mysql": """
        create table if not exists attribute_version (
            id integer primary key auto_increment,
            ontology_id integer not null,
            object_code varchar(255) not null,
            instance_id varchar(255) not null,
            attribute_code varchar(255) not null,
            value text,
            value_type varchar(50) not null default 'text',
            valid_from datetime not null,
            valid_to datetime,
            recorded_at datetime not null default current_timestamp,
            actor varchar(255) not null default '',
            source varchar(255) not null default '',
            superseded_by integer
        )""",
    },
)

ATTRIBUTE_VERSION_INDEXES: tuple[dict[str, str], ...] = (
    {
        # Every as-of read filters on this exact prefix, and history grows without bound,
        # so the lookup must not degrade into a scan of all versions ever recorded.
        "sqlite": """
        create index if not exists idx_attribute_version_lookup
        on attribute_version (ontology_id, object_code, instance_id, attribute_code)""",
        "postgresql": """
        create index if not exists idx_attribute_version_lookup
        on attribute_version (ontology_id, object_code, instance_id, attribute_code)""",
        "mysql": """
        create index idx_attribute_version_lookup
        on attribute_version (ontology_id, object_code, instance_id, attribute_code)""",
    },
)

SCHEMA = SchemaBundle(
    name="temporal",
    tables=ATTRIBUTE_VERSION_SCHEMA,
    indexes=ATTRIBUTE_VERSION_INDEXES,
    table_names=(VERSION_TABLE,),
)
SCHEMA.verify_declared_names()


def init_temporal_schema(conn: Any) -> None:
    """Create the version table. Idempotent -- startup runs it on every boot."""
    SCHEMA.apply(conn)


def temporal_tables_exist(conn: Any) -> bool:
    """Whether history is available.

    A missing table means the feature is not configured, which must read as "no history"
    rather than an error. Probed via the catalog, never by catching the error: on
    PostgreSQL a failed statement aborts the transaction (ADR-0004).
    """
    return SCHEMA.has_tables(conn)


def now_iso() -> str:
    """The platform's notion of now, in UTC.

    UTC because a validity window compared across time zones is a source of silent
    off-by-hours errors, and a verdict is not worth debugging over a DST boundary.
    """
    return datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None).isoformat(sep=" ")


def normalize_instant(value: Any, *, what: str = "时间点") -> str:
    """Coerce a timestamp to the stored form, refusing anything ambiguous.

    Refuses rather than guessing: a misparsed instant silently selects the wrong version,
    and the resulting verdict looks perfectly ordinary.
    """
    if value is None or value == "":
        raise TemporalError(f"{what}不能为空")
    if isinstance(value, datetime):
        return value.replace(microsecond=0, tzinfo=None).isoformat(sep=" ")
    text = str(value).strip().replace("T", " ")
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, pattern).isoformat(sep=" ")
        except ValueError:
            continue
    raise TemporalError(f"无法解析{what}: {value!r}。请使用 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS。")


@dataclass(frozen=True)
class AttributeVersion:
    """One value of one attribute, over one validity window."""

    attribute_code: str
    value: Any
    valid_from: str
    valid_to: Optional[str] = None
    recorded_at: str = ""
    actor: str = ""
    source: str = ""
    value_type: str = "text"
    version_id: int = 0

    @property
    def open_ended(self) -> bool:
        return self.valid_to is None

    def covers(self, instant: str) -> bool:
        """Whether this version was valid at `instant`.

        Half-open interval `[valid_from, valid_to)`. Half-open because two adjacent
        versions must not both match a boundary instant -- if they did, which value a
        verdict used would depend on row order.
        """
        if instant < self.valid_from:
            return False
        return self.valid_to is None or instant < self.valid_to

    def as_dict(self) -> dict[str, Any]:
        return {
            "versionId": self.version_id,
            "attributeCode": self.attribute_code,
            "value": self.value,
            "valueType": self.value_type,
            "validFrom": self.valid_from,
            "validTo": self.valid_to,
            "recordedAt": self.recorded_at,
            "actor": self.actor,
            "source": self.source,
            "openEnded": self.open_ended,
        }


def _encode(value: Any) -> tuple[Optional[str], str]:
    """Store a value with its type, so it comes back as what it was.

    Rules compare against real numbers and booleans; a value that round-tripped as a
    string would make `amount > 0` compare `str > int`, which fail-closed reports as a
    violation -- a storage detail becoming a wrong verdict.
    """
    if value is None:
        return None, "null"
    if isinstance(value, bool):
        return json.dumps(value), "boolean"
    if isinstance(value, int):
        return str(value), "integer"
    if isinstance(value, float):
        return repr(value), "number"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False), "json"
    return str(value), "text"


def _decode(raw: Optional[str], value_type: str) -> Any:
    if raw is None or value_type == "null":
        return None
    try:
        if value_type == "integer":
            return int(raw)
        if value_type == "number":
            return float(raw)
        if value_type == "boolean":
            return json.loads(raw)
        if value_type == "json":
            return json.loads(raw)
    except (TypeError, ValueError):
        # A value that no longer decodes is returned raw rather than as None: None reads
        # as "absent", which is a different fact.
        logger.warning("版本值无法按 %s 解码，按原文返回", value_type)
        return raw
    return raw


def record_attribute_version(
    platform_db: PlatformDb,
    ontology_id: int,
    object_code: str,
    instance_id: str,
    attribute_code: str,
    value: Any,
    *,
    valid_from: Any = None,
    actor: str = "system",
    source: str = "",
) -> dict[str, Any]:
    """Record a new value, closing whichever version it supersedes.

    Append-only: the previous version's `valid_to` is set to this one's `valid_from`, and
    its row is marked superseded. Nothing is overwritten, so a verdict recorded earlier
    still cites a value that exists.

    A version whose `valid_from` predates existing history is accepted -- late-arriving and
    backdated data is the normal case in legacy integration, not an error.
    """
    start = normalize_instant(valid_from) if valid_from is not None else now_iso()
    stored_value, value_type = _encode(value)
    with connect(platform_db) as conn:
        if not temporal_tables_exist(conn):
            raise TemporalError("时态表尚未创建，请先运行 init_temporal_schema()。")

        # Close the version that was open at this instant, if any. Restricted to the one
        # whose window contains `start` so a backdated insert splits the right window
        # rather than closing the latest.
        covering = conn.execute(
            f"""
            select id, valid_from, valid_to from {VERSION_TABLE}
            where ontology_id = ? and object_code = ? and instance_id = ? and attribute_code = ?
              and valid_from <= ?
              and (valid_to is null or valid_to > ?)
            order by valid_from desc, id desc
            """,
            (ontology_id, object_code, str(instance_id), attribute_code, start, start),
        ).fetchone()

        conn.execute(
            f"""
            insert into {VERSION_TABLE}
                (ontology_id, object_code, instance_id, attribute_code, value, value_type,
                 valid_from, valid_to, actor, source)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ontology_id,
                object_code,
                str(instance_id),
                attribute_code,
                stored_value,
                value_type,
                start,
                # Inherit the closed end of the window being split, so a backdated insert
                # does not silently extend coverage past where it was known to end.
                covering["valid_to"] if covering is not None else None,
                actor,
                source,
            ),
        )
        version_id = last_insert_id(conn)
        if covering is not None:
            # Closed at the new version's start. When the two share an instant this makes
            # the old row a zero-length window -- a correction rather than a change -- and
            # both rows stay readable, so a verdict citing the old value still resolves.
            conn.execute(
                f"update {VERSION_TABLE} set valid_to = ?, superseded_by = ? where id = ?",
                (start, version_id, int(covering["id"])),
            )
        conn.execute(
            "insert into audit_log (actor, action, target_type, target_id, detail) values (?, ?, ?, ?, ?)",
            (
                actor,
                "record_attribute_version",
                "attribute_version",
                f"{object_code}/{instance_id}.{attribute_code}",
                json.dumps({"validFrom": start, "valueType": value_type, "source": source}, ensure_ascii=False),
            ),
        )
    return {
        "versionId": version_id,
        "objectCode": object_code,
        "instanceId": str(instance_id),
        "attributeCode": attribute_code,
        "validFrom": start,
        "supersededVersionId": int(covering["id"]) if covering is not None else None,
    }


def load_versions(
    conn: Any,
    ontology_id: int,
    object_code: str,
    instance_id: str,
    *,
    attribute_code: str = "",
) -> list[AttributeVersion]:
    """Every recorded version for one instance, oldest first.

    Read on the caller's connection so an as-of assessment does not open a second one.
    """
    if not temporal_tables_exist(conn):
        return []
    clauses = ["ontology_id = ?", "object_code = ?", "instance_id = ?"]
    params: list[Any] = [ontology_id, object_code, str(instance_id)]
    if attribute_code:
        clauses.append("attribute_code = ?")
        params.append(attribute_code)
    rows = conn.execute(
        f"""
        select * from {VERSION_TABLE}
        where {" and ".join(clauses)}
        order by valid_from, id
        """,
        tuple(params),
    ).fetchall()
    if len(rows) > MAX_VERSIONS_PER_INSTANCE:
        logger.warning("实例 %s/%s 的版本数超过 %s，已截断", object_code, instance_id, MAX_VERSIONS_PER_INSTANCE)
        rows = rows[:MAX_VERSIONS_PER_INSTANCE]
    return [
        AttributeVersion(
            attribute_code=row["attribute_code"],
            value=_decode(row["value"], row["value_type"]),
            valid_from=str(row["valid_from"]),
            valid_to=str(row["valid_to"]) if row["valid_to"] is not None else None,
            recorded_at=str(row["recorded_at"]),
            actor=row["actor"] or "",
            source=row["source"] or "",
            value_type=row["value_type"],
            version_id=int(row["id"]),
        )
        for row in rows
    ]


def values_as_of(
    conn: Any,
    ontology_id: int,
    object_code: str,
    instance_id: str,
    instant: Any,
) -> dict[str, Any]:
    """The attribute values that were valid at `instant`.

    Only attributes with a version covering that moment appear. An attribute with history
    that does not reach back that far is **absent**, not back-filled: a rule referencing it
    then fails closed, which is correct -- the platform genuinely does not know what the
    value was.
    """
    moment = normalize_instant(instant, what="as-of 时间点")
    resolved: dict[str, Any] = {}
    # Ordered oldest-first, so a later covering version overwrites an earlier one; with
    # half-open windows at most one can cover, and the ordering makes a corrected
    # zero-length window lose to its replacement deterministically.
    for version in load_versions(conn, ontology_id, object_code, instance_id):
        if version.covers(moment):
            resolved[version.attribute_code] = version.value
    return resolved


def coverage(
    conn: Any,
    ontology_id: int,
    object_code: str,
    instance_id: str,
) -> dict[str, Any]:
    """The window history can actually answer for, per attribute.

    Reported because the platform records only what it observed: a source system that
    overwrites values in place still loses its own history, and an as-of answer outside
    this window would be an absence rather than a fact. Saying so beats implying
    completeness.
    """
    versions = load_versions(conn, ontology_id, object_code, instance_id)
    by_attribute: dict[str, list[AttributeVersion]] = {}
    for version in versions:
        by_attribute.setdefault(version.attribute_code, []).append(version)
    return {
        "objectCode": object_code,
        "instanceId": str(instance_id),
        "attributes": {
            code: {
                "earliest": items[0].valid_from,
                "latestFrom": items[-1].valid_from,
                "openEnded": items[-1].open_ended,
                "versionCount": len(items),
            }
            for code, items in sorted(by_attribute.items())
        },
        "note": "平台只能回答它观测到的区间；此区间之外为“未知”，而不是“无变化”。",
    }


def instance_history(
    platform_db: PlatformDb,
    ontology_id: int,
    object_code: str,
    instance_id: str,
    *,
    attribute_code: str = "",
) -> dict[str, Any]:
    """One instance's attribute history, for review and for the API."""
    with connect(platform_db) as conn:
        versions = load_versions(conn, ontology_id, object_code, instance_id, attribute_code=attribute_code)
        window = coverage(conn, ontology_id, object_code, instance_id)
    return {
        "objectCode": object_code,
        "instanceId": str(instance_id),
        "versions": [version.as_dict() for version in versions],
        "coverage": window["attributes"],
        "truncated": len(versions) >= MAX_VERSIONS_PER_INSTANCE,
    }


def capture_snapshot(
    platform_db: PlatformDb,
    ontology_id: int,
    object_code: str,
    instance_id: str,
    record: dict[str, Any],
    *,
    valid_from: Any = None,
    actor: str = "system",
    source: str = "scan",
) -> dict[str, Any]:
    """Record the current values of an instance as a new version of each attribute.

    How history accumulates for a source system that has none of its own: each capture is
    an observation at a moment. Values equal to the currently valid version are skipped, so
    repeated captures do not manufacture a version per poll -- which would make the history
    look like continuous change when nothing changed.
    """
    start = normalize_instant(valid_from) if valid_from is not None else now_iso()
    with connect(platform_db) as conn:
        current = values_as_of(conn, ontology_id, object_code, instance_id, start)
    recorded: list[str] = []
    skipped: list[str] = []
    for attribute_code, value in record.items():
        if attribute_code in current and current[attribute_code] == value:
            skipped.append(attribute_code)
            continue
        record_attribute_version(
            platform_db,
            ontology_id,
            object_code,
            instance_id,
            attribute_code,
            value,
            valid_from=start,
            actor=actor,
            source=source,
        )
        recorded.append(attribute_code)
    return {
        "objectCode": object_code,
        "instanceId": str(instance_id),
        "validFrom": start,
        "recorded": sorted(recorded),
        "unchanged": sorted(skipped),
    }
