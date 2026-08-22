"""Instance resolvers: how a business object finds its instances.

`business_object.source_table_id` is a single foreign key, so an object could only
ever mirror one table. That is generality item #1 on the roadmap and the foundation
the other items sit on, because it is the assumption that makes these unmodellable:

- an order that is `order` joined to `order_line`
- a `party` table holding customers and suppliers, split by a discriminator column
- an object whose real definition is a view or a hand-written query
- an object assembled across two data sources

A resolver turns "which rows are this object's instances" into a replaceable
strategy. `single_table` is the default and behaves exactly as before, so nothing
changes for existing ontologies -- that backwards compatibility is a requirement,
not a nicety, because these code paths produce compliance verdicts.

## What a resolver must guarantee

Any implementation, built in or third party, has to satisfy
`tests/test_instance_resolvers.py`:

1. `fetch(instance_id)` returns one record or None -- never a partial one.
2. `list_ids(limit)` returns tokens that `fetch` accepts. Round-tripping is what
   lets batch assessment work.
3. `columns()` reports every name a rule may reference, so expression validation
   can warn about typos.
4. Identifier interpolation is refused unless validated. Resolvers build SQL from
   configuration, which is an injection boundary.

Stability: experimental (ADR-0007).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Sequence

from .database import connect
from .instance_key import InstanceKey, parse_key_columns
from .registry import Registry, RegistryError, load_entry_point_plugins

logger = logging.getLogger(__name__)

# Identifiers reaching SQL text are validated rather than escaped: resolver
# configuration is operator-supplied, and a quoted-but-unvalidated name is still a
# hazard when it lands in a join clause.
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")

SINGLE_TABLE = "single_table"
JOINED_TABLES = "joined_tables"
DISCRIMINATED = "discriminated"
CUSTOM_SQL = "custom_sql"


class ResolverError(ValueError):
    """Raised when a resolver configuration or lookup is invalid."""


def validate_identifier(name: str, *, what: str = "标识符") -> str:
    """Reject anything that is not a plain SQL identifier."""
    text = (name or "").strip()
    if not IDENTIFIER_PATTERN.match(text):
        raise ResolverError(f"{what}不合法: {name!r}。只允许字母或下划线开头的字母、数字、下划线，最长 64 字符。")
    return text


@dataclass
class ResolverSpec:
    """Declarative resolver configuration, stored on the business object.

    Kept as data rather than code so an ontology stays inspectable and exportable:
    a resolver that only existed as a Python callable could not be reviewed,
    versioned or shipped in a semantic asset export.
    """

    kind: str = SINGLE_TABLE
    table: str = ""
    primary_key: str = "id"
    # joined_tables
    joins: list[dict[str, str]] = field(default_factory=list)
    # discriminated
    discriminator_column: str = ""
    discriminator_value: str = ""
    # custom_sql
    query: str = ""
    id_column: str = ""

    @classmethod
    def from_json(cls, raw: Any, *, table: str = "", primary_key: str = "id") -> "ResolverSpec":
        """Build a spec from stored JSON, defaulting to single-table.

        A malformed value degrades to single-table rather than raising: the object
        still has a table, so the conservative reading keeps it usable while the
        misconfiguration is logged.
        """
        if not raw:
            return cls(kind=SINGLE_TABLE, table=table, primary_key=primary_key or "id")
        payload = raw
        if isinstance(raw, str):
            try:
                payload = json.loads(raw)
            except (TypeError, ValueError):
                logger.warning("解析实例解析器配置失败，回退到单表: %r", raw)
                return cls(kind=SINGLE_TABLE, table=table, primary_key=primary_key or "id")
        if not isinstance(payload, dict):
            return cls(kind=SINGLE_TABLE, table=table, primary_key=primary_key or "id")
        return cls(
            kind=str(payload.get("kind") or SINGLE_TABLE),
            table=str(payload.get("table") or table),
            primary_key=str(payload.get("primaryKey") or primary_key or "id"),
            joins=list(payload.get("joins") or []),
            discriminator_column=str(payload.get("discriminatorColumn") or ""),
            discriminator_value=str(payload.get("discriminatorValue") or ""),
            query=str(payload.get("query") or ""),
            id_column=str(payload.get("idColumn") or ""),
        )

    def to_json(self) -> str:
        return json.dumps(
            {
                "kind": self.kind,
                "table": self.table,
                "primaryKey": self.primary_key,
                "joins": self.joins,
                "discriminatorColumn": self.discriminator_column,
                "discriminatorValue": self.discriminator_value,
                "query": self.query,
                "idColumn": self.id_column,
            },
            ensure_ascii=False,
        )


@dataclass
class ResolvedInstance:
    """One instance's data plus where it came from."""

    record: dict[str, Any]
    instance_id: str
    tables: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "record": self.record,
            "instanceId": self.instance_id,
            "tables": list(self.tables),
        }


class InstanceResolver:
    """Base class: locate an object's instances in a data source.

    `runtime` is an adapter runtime (`adapters.RuntimeDatabase`), so resolvers work
    across all three dialects without knowing which one they are on.
    """

    kind = "base"

    def __init__(self, spec: ResolverSpec):
        self.spec = spec
        self.validate()

    def validate(self) -> None:
        """Check the configuration. Called at construction so a bad spec fails
        before it can produce a wrong verdict."""
        raise NotImplementedError

    def fetch(self, runtime: Any, instance_id: str) -> Optional[dict[str, Any]]:
        raise NotImplementedError

    def list_ids(self, runtime: Any, limit: int = 50) -> list[str]:
        raise NotImplementedError

    def columns(self, runtime: Any) -> list[str]:
        """Names a rule may reference for this object."""
        raise NotImplementedError

    def tables(self) -> tuple[str, ...]:
        """Every table this resolver reads, for drift detection and lineage."""
        return (self.spec.table,) if self.spec.table else ()

    def describe(self) -> dict[str, Any]:
        return {"kind": self.kind, "tables": list(self.tables()), "primaryKey": self.spec.primary_key}


class SingleTableResolver(InstanceResolver):
    """One object, one table. The historical behaviour, unchanged.

    Delegates to the adapter runtime rather than building SQL, so composite keys
    and dialect quoting keep working exactly as they did (ADR-0008).
    """

    kind = SINGLE_TABLE

    def validate(self) -> None:
        validate_identifier(self.spec.table, what="来源表名")
        for column in parse_key_columns(self.spec.primary_key):
            validate_identifier(column, what="主键列名")

    def fetch(self, runtime: Any, instance_id: str) -> Optional[dict[str, Any]]:
        return runtime.fetch_one(self.spec.table, self.spec.primary_key, instance_id)

    def list_ids(self, runtime: Any, limit: int = 50) -> list[str]:
        return [str(value) for value in runtime.fetch_primary_keys(self.spec.table, self.spec.primary_key, limit)]

    def columns(self, runtime: Any) -> list[str]:
        rows, _ = runtime.browse_rows(self.spec.table, 1, 0)
        return sorted(rows[0].keys()) if rows else []


class JoinedTablesResolver(InstanceResolver):
    """An object spanning a primary table and its dependents.

    The `order` + `order_line` case. Child rows are attached under the child table
    name, so a rule can say `sum(order_line.amount) > 0` -- the same shape the
    existing related-context loader already exposes, which keeps rule syntax
    consistent whether relationships come from foreign keys or from a resolver.
    """

    kind = JOINED_TABLES

    def validate(self) -> None:
        validate_identifier(self.spec.table, what="主表名")
        for column in parse_key_columns(self.spec.primary_key):
            validate_identifier(column, what="主键列名")
        if not self.spec.joins:
            raise ResolverError("joined_tables 解析器至少需要一个 joins 配置")
        for join in self.spec.joins:
            validate_identifier(str(join.get("table", "")), what="关联表名")
            validate_identifier(str(join.get("foreignKey", "")), what="外键列名")

    def fetch(self, runtime: Any, instance_id: str) -> Optional[dict[str, Any]]:
        record = runtime.fetch_one(self.spec.table, self.spec.primary_key, instance_id)
        if record is None:
            return None
        merged = dict(record)
        key = InstanceKey.from_token(self.spec.primary_key, instance_id)
        for join in self.spec.joins:
            child_table = str(join["table"])
            foreign_key = str(join["foreignKey"])
            # The parent column the child points at; defaults to the first key
            # column, which is the overwhelmingly common case.
            parent_column = str(join.get("parentColumn") or key.columns[0])
            parent_value = key.as_mapping().get(parent_column, key.values[0])
            rows = runtime.fetch_related_many(child_table, foreign_key, parent_value)
            merged[child_table] = rows
        return merged

    def list_ids(self, runtime: Any, limit: int = 50) -> list[str]:
        return [str(value) for value in runtime.fetch_primary_keys(self.spec.table, self.spec.primary_key, limit)]

    def columns(self, runtime: Any) -> list[str]:
        names: set[str] = set()
        rows, _ = runtime.browse_rows(self.spec.table, 1, 0)
        if rows:
            names.update(rows[0].keys())
        # Child tables are addressable by name in expressions.
        names.update(str(join["table"]) for join in self.spec.joins)
        return sorted(names)

    def tables(self) -> tuple[str, ...]:
        return (self.spec.table, *(str(join["table"]) for join in self.spec.joins))


class DiscriminatedResolver(InstanceResolver):
    """One physical table holding several business objects, split by a column.

    The `party` table with `party_type in ('customer','supplier')` case. Without
    this, both objects would resolve to every row, and a rule scoped to customers
    would silently evaluate against suppliers -- a wrong verdict, not just a
    modelling inconvenience.
    """

    kind = DISCRIMINATED

    def validate(self) -> None:
        validate_identifier(self.spec.table, what="来源表名")
        validate_identifier(self.spec.discriminator_column, what="判别列名")
        for column in parse_key_columns(self.spec.primary_key):
            validate_identifier(column, what="主键列名")
        if not self.spec.discriminator_value:
            raise ResolverError("discriminated 解析器必须指定判别值")

    def fetch(self, runtime: Any, instance_id: str) -> Optional[dict[str, Any]]:
        record = runtime.fetch_one(self.spec.table, self.spec.primary_key, instance_id)
        if record is None:
            return None
        # Fetch then check, rather than trusting the caller's id to be in-partition.
        # An id from another partition must read as "not found" for this object,
        # otherwise one object could inspect another's rows.
        actual = record.get(self.spec.discriminator_column)
        if str(actual) != str(self.spec.discriminator_value):
            return None
        return dict(record)

    def list_ids(self, runtime: Any, limit: int = 50) -> list[str]:
        rows = runtime.fetch_related_many(
            self.spec.table, self.spec.discriminator_column, self.spec.discriminator_value
        )
        ids: list[str] = []
        for row in rows[: max(1, limit)]:
            ids.append(InstanceKey.from_row(self.spec.primary_key, row).token)
        return ids

    def columns(self, runtime: Any) -> list[str]:
        rows, _ = runtime.browse_rows(self.spec.table, 1, 0)
        return sorted(rows[0].keys()) if rows else []


class CustomSqlResolver(InstanceResolver):
    """An object defined by a view or a hand-written query.

    The escape hatch from ADR-0005: when structural expressiveness runs out, drop
    to SQL rather than wait for the framework to grow a feature.

    The query must expose an id column and is used as a subquery, so it stays
    read-only from the platform's side. It is operator-supplied SQL and runs with
    the data source's own privileges -- documented in docs/extending.md, because
    that is a deliberate trust decision rather than an oversight.
    """

    kind = CUSTOM_SQL

    def validate(self) -> None:
        query = (self.spec.query or "").strip().rstrip(";")
        if not query:
            raise ResolverError("custom_sql 解析器必须提供 query")
        if not re.match(r"^\s*(select|with)\b", query, re.IGNORECASE):
            raise ResolverError("custom_sql 只允许 select 或 with 查询")
        # Statement separators would allow appending a second statement.
        if ";" in query:
            raise ResolverError("custom_sql 不允许包含分号")
        validate_identifier(self.spec.id_column or "id", what="标识列名")
        self._query = query

    def fetch(self, runtime: Any, instance_id: str) -> Optional[dict[str, Any]]:
        id_column = self.spec.id_column or "id"
        sql = f"select * from ({self._query}) as resolver_source where {id_column} = ?"
        rows = _execute(runtime, sql, (instance_id,))
        return dict(rows[0]) if rows else None

    def list_ids(self, runtime: Any, limit: int = 50) -> list[str]:
        id_column = self.spec.id_column or "id"
        sql = f"select {id_column} as instance_id from ({self._query}) as resolver_source limit ?"
        rows = _execute(runtime, sql, (max(1, limit),))
        return [str(row["instance_id"]) for row in rows]

    def columns(self, runtime: Any) -> list[str]:
        sql = f"select * from ({self._query}) as resolver_source limit ?"
        rows = _execute(runtime, sql, (1,))
        return sorted(rows[0].keys()) if rows else []

    def tables(self) -> tuple[str, ...]:
        # A custom query's tables cannot be determined reliably without parsing
        # SQL, so drift detection has nothing to check here. Reported honestly as
        # empty rather than guessed.
        return ()


def _execute(runtime: Any, sql: str, params: Sequence[Any]) -> list[dict[str, Any]]:
    """Run a query through whichever runtime shape the adapter provides.

    SQLite runtimes expose `conn.execute`; the SQL runtimes use a cursor and `%s`
    placeholders. Handled here so resolvers stay dialect-agnostic.
    """
    dialect = getattr(runtime, "dialect", "sqlite")
    conn = getattr(runtime, "conn", None)
    if conn is None:
        raise ResolverError("运行时不支持自定义查询")
    if dialect == "sqlite":
        rows = conn.execute(sql, tuple(params)).fetchall()
        return [dict(row) for row in rows]
    adapted = sql.replace("?", "%s")
    with conn.cursor() as cur:
        cur.execute(adapted, tuple(params))
        fetched = cur.fetchall()
    return [dict(row) if not isinstance(row, dict) else row for row in fetched]


# -- Registry --

ResolverFactory = Callable[[ResolverSpec], InstanceResolver]

RESOLVER_REGISTRY: Registry[ResolverFactory] = Registry("实例解析器")
RESOLVER_ENTRY_POINT_GROUP = "aletheia.instance_resolvers"


def register_resolver(kind: str, factory: ResolverFactory, *, replace: bool = False) -> ResolverFactory:
    """Register a resolver strategy.

    >>> register_resolver("cross_source", CrossSourceResolver)  # doctest: +SKIP

    Run tests/test_instance_resolvers.py against a new resolver to check it upholds
    the contract; the round-trip between `list_ids` and `fetch` is the property
    most easily got wrong.
    """
    RESOLVER_REGISTRY.register(kind, factory, replace=replace)
    return factory


def build_resolver(spec: ResolverSpec) -> InstanceResolver:
    try:
        factory = RESOLVER_REGISTRY.get(spec.kind)
    except RegistryError as error:
        raise ResolverError(str(error)) from error
    return factory(spec)


def supported_resolver_kinds() -> tuple[str, ...]:
    return RESOLVER_REGISTRY.names()


def load_resolver_plugins() -> list[str]:
    return load_entry_point_plugins(
        RESOLVER_ENTRY_POINT_GROUP,
        lambda name, factory: RESOLVER_REGISTRY.register(name, factory),
    )


register_resolver(SINGLE_TABLE, SingleTableResolver)
register_resolver(JOINED_TABLES, JoinedTablesResolver)
register_resolver(DISCRIMINATED, DiscriminatedResolver)
register_resolver(CUSTOM_SQL, CustomSqlResolver)

load_resolver_plugins()


def configure_object_resolver(
    platform_db: Any,
    ontology_id: int,
    object_code: str,
    spec: ResolverSpec,
    *,
    actor: str = "system",
) -> dict[str, Any]:
    """Attach a resolver to a business object.

    The spec is built (and therefore validated) before it is stored, so an invalid
    configuration is refused here rather than surfacing later as a failed
    assessment. Published ontologies are immutable, so this is refused on them for
    the same reason rules and mappings are.
    """
    resolver = build_resolver(spec)
    with connect(platform_db) as conn:
        ontology = conn.execute("select status from ontology where id = ?", (ontology_id,)).fetchone()
        if ontology is None:
            raise ResolverError(f"本体不存在: {ontology_id}")
        if ontology["status"] == "published":
            raise ResolverError("已发布本体不可修改实例解析器，请派生新版本。")
        target = conn.execute(
            "select id from business_object where ontology_id = ? and code = ?",
            (ontology_id, object_code),
        ).fetchone()
        if target is None:
            raise ResolverError(f"业务对象不存在: {object_code}")
        conn.execute(
            "update business_object set resolver_spec = ? where id = ?",
            (spec.to_json(), int(target["id"])),
        )
        conn.execute(
            "insert into audit_log (actor, action, target_type, target_id, detail) values (?, ?, ?, ?, ?)",
            (
                actor,
                "configure_instance_resolver",
                "business_object",
                object_code,
                json.dumps({"kind": spec.kind, "tables": list(resolver.tables())}, ensure_ascii=False),
            ),
        )
    return {
        "objectCode": object_code,
        "resolver": resolver.describe(),
        "note": "解析器已生效；如需回到单表行为，将 kind 设为 single_table。",
    }


def get_object_resolver(platform_db: Any, ontology_id: int, object_code: str) -> dict[str, Any]:
    """Report the resolver in effect for an object."""
    with connect(platform_db) as conn:
        row = conn.execute(
            """
            select bo.resolver_spec, st.table_name, st.primary_key
            from business_object bo
            left join source_table st on st.id = bo.source_table_id
            where bo.ontology_id = ? and bo.code = ?
            """,
            (ontology_id, object_code),
        ).fetchone()
    if row is None:
        raise ResolverError(f"业务对象不存在: {object_code}")
    raw = ""
    try:
        raw = row["resolver_spec"] or ""
    except (KeyError, IndexError, TypeError):
        raw = ""
    spec = ResolverSpec.from_json(raw, table=row["table_name"] or "", primary_key=row["primary_key"] or "id")
    return {
        "objectCode": object_code,
        "kind": spec.kind,
        "configured": bool(raw),
        "resolver": build_resolver(spec).describe(),
        "supportedKinds": list(supported_resolver_kinds()),
    }
