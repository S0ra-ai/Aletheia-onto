"""Cross-object aggregation: rules that reason over more than one instance.

Rules are scoped to a single object via `scope_object_code`, so every expression
could only see the instance under assessment and its directly related rows. That
rules out an entire class of B2B requirement -- the ones that are actually about a
*group*:

    「客户所有合同总额不得超过其信用额度」
    「同一设备的未关闭工单不得超过 3 个」
    「本月该客户的退款次数不得超过 2 次」

This is generality item #5. It is deliberately *not* general-purpose reasoning: an
aggregate is a named, declared, reviewable value, not an ad-hoc join written inside
a rule expression. That distinction is what keeps a verdict explainable -- the
answer to "why" is a specific aggregate definition an operator can read, rather
than a query nobody reviewed.

## The shape

An aggregate declares: from the instance under assessment, follow a link to a
grouping value, then apply a function over the matching rows of a target object.

    customer_total_amount = sum(contract.total_amount)
                            where contract.customer_id = <this instance's customer_id>

The value lands in the sandbox as a plain number, so rules stay simple:

    customer_total_amount <= credit_limit

## Design decisions

- **Declared, not inline.** Stored as data on the ontology, so it is reviewable,
  versioned and exportable -- the same reasoning as ADR-0011.
- **Fail-closed.** An aggregate that cannot be computed makes its rule fail rather
  than evaluate against a missing value. Returning 0 for "could not compute" would
  make a limit check silently pass, which is precisely the ADR-0002 failure.
- **Bounded.** Aggregates read rows; an unbounded one on a large table would turn
  every assessment into a table scan. `MAX_AGGREGATION_ROWS` caps it and the cap
  being hit is reported rather than silently truncating the answer.
- **Self-exclusion is explicit.** "Total of the customer's *other* contracts"
  differs from "including this one" by exactly one row, which changes whether a
  limit is breached. The spec says which, rather than leaving it to be guessed.

Stability: experimental (ADR-0007).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from .database import connect
from .instance_resolver import ResolverError
from .instance_resolver import validate_identifier as _validate_sql_identifier
from .schema import ColumnAddition, SchemaBundle, table_exists

logger = logging.getLogger(__name__)

# Table name, referenced by both the DDL and the catalog probe. Defined once so the
# probe can never name a table the DDL did not create.
AGGREGATE_TABLE = "cross_object_aggregate"

# Aggregate functions. Deliberately small: each maps to something a reviewer can
# read in a verdict. `avg` is included because credit and risk thresholds use it;
# anything requiring a window function belongs in a custom_sql resolver instead.
AGGREGATE_FUNCTIONS = ("sum", "count", "min", "max", "avg")

# An aggregate runs on every assessment of its object, so it must stay cheap.
# Hitting the cap is reported, never silently truncated.
MAX_AGGREGATION_ROWS = 10_000


class AggregationError(ValueError):
    """Raised when an aggregate definition or evaluation is invalid."""


def _identifier(name: str, *, what: str) -> str:
    """Validate an identifier, reporting failures as an aggregation error.

    The check itself is shared with the resolver module -- one place to audit for
    SQL-identifier safety -- but a caller of the aggregation API should not have to
    catch ResolverError to handle a bad aggregate definition.
    """
    try:
        return _validate_sql_identifier(name, what=what)
    except ResolverError as error:
        raise AggregationError(str(error)) from error


@dataclass
class AggregateSpec:
    """One named cross-object aggregate.

    `group_column` is read from the instance under assessment; `target_column` is
    the column on the target object that must match it. For the credit example:
    group_column=`customer_id` on the contract being assessed, target_table
    `contracts`, target_column `customer_id`, function `sum`, value_column
    `total_amount`.
    """

    name: str
    function: str
    target_table: str
    target_column: str
    group_column: str
    value_column: str = ""
    # Exclude the instance under assessment from its own aggregate. Matters for
    # "the customer's *other* contracts", which differs by exactly one row.
    exclude_self: bool = False
    self_column: str = ""
    # Optional equality filter, e.g. status = 'active'.
    filter_column: str = ""
    filter_value: str = ""
    # Which data source holds the target table. `0` means the instance's own source,
    # which is what every existing aggregate does -- so this widens the feature without
    # changing any stored definition.
    #
    # A cross-source aggregate reads a table the assessed instance's source knows nothing
    # about, e.g. "total of this customer's contracts in the ERP" while the customer lives
    # in the CRM. The rows are still matched by an equality on a declared column, so the
    # aggregate stays as explainable as a same-source one.
    target_data_source_id: int = 0

    def validate(self) -> "AggregateSpec":
        """Check the definition. Identifiers reach SQL text, so they are validated
        rather than quoted -- same boundary as ADR-0011."""
        if not self.name or not self.name.isidentifier():
            raise AggregationError(f"聚合名必须是合法标识符: {self.name!r}（规则表达式要按此名引用它）")
        if self.name.startswith("_"):
            raise AggregationError("聚合名不能以下划线开头，避免与沙箱内部名冲突")
        function = (self.function or "").strip().lower()
        if function not in AGGREGATE_FUNCTIONS:
            raise AggregationError(f"不支持的聚合函数: {self.function!r}。可选: {'、'.join(AGGREGATE_FUNCTIONS)}")
        self.function = function
        _identifier(self.target_table, what="聚合目标表名")
        _identifier(self.target_column, what="聚合关联列名")
        _identifier(self.group_column, what="分组取值列名")
        if function != "count":
            if not self.value_column:
                raise AggregationError(f"{function} 聚合必须指定 valueColumn")
            _identifier(self.value_column, what="聚合值列名")
        if self.exclude_self:
            if not self.self_column:
                raise AggregationError("excludeSelf 为真时必须指定 selfColumn")
            _identifier(self.self_column, what="自身标识列名")
        if self.filter_column:
            _identifier(self.filter_column, what="过滤列名")
        if self.target_data_source_id < 0:
            raise AggregationError(f"目标数据源 id 不能为负: {self.target_data_source_id}")
        return self

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "function": self.function,
            "targetTable": self.target_table,
            "targetColumn": self.target_column,
            "groupColumn": self.group_column,
            "valueColumn": self.value_column,
            "excludeSelf": self.exclude_self,
            "selfColumn": self.self_column,
            "filterColumn": self.filter_column,
            "filterValue": self.filter_value,
            "targetDataSourceId": self.target_data_source_id,
        }

    @classmethod
    def from_row(cls, row: Any) -> "AggregateSpec":
        # Read defensively: the column postdates the table, so a row from an older
        # deployment simply means "the instance's own source" -- its prior behaviour.
        try:
            target_source = int(row["target_data_source_id"] or 0)
        except (KeyError, IndexError, TypeError, ValueError):
            target_source = 0
        return cls(
            name=row["name"],
            function=row["function"],
            target_table=row["target_table"],
            target_column=row["target_column"],
            group_column=row["group_column"],
            value_column=row["value_column"] or "",
            exclude_self=bool(row["exclude_self"]),
            self_column=row["self_column"] or "",
            filter_column=row["filter_column"] or "",
            filter_value=row["filter_value"] or "",
            target_data_source_id=target_source,
        )

    def describe(self) -> str:
        """Human-readable definition, used in explanations.

        A verdict that cites an aggregate has to be able to say what the aggregate
        *was*, otherwise the number is unexplainable.
        """
        target = f"{self.function}({self.target_table}.{self.value_column or '*'})"
        if self.target_data_source_id:
            # 跨源聚合必须在定义里写明目标在哪个源，否则同名表会让人以为读的是本源。
            target = (
                f"{self.function}(数据源#{self.target_data_source_id}.{self.target_table}.{self.value_column or '*'})"
            )
        clause = f"{self.target_table}.{self.target_column} = 本实例.{self.group_column}"
        if self.filter_column:
            clause += f" 且 {self.filter_column} = {self.filter_value!r}"
        if self.exclude_self:
            clause += "（排除本实例）"
        return f"{self.name} = {target} where {clause}"


AGGREGATE_SCHEMA: tuple[dict[str, str], ...] = (
    {
        "sqlite": """
        create table if not exists cross_object_aggregate (
            id integer primary key autoincrement,
            ontology_id integer not null references ontology(id),
            scope_object_code text not null,
            name text not null,
            function text not null,
            target_table text not null,
            target_column text not null,
            group_column text not null,
            value_column text not null default '',
            exclude_self integer not null default 0,
            self_column text not null default '',
            filter_column text not null default '',
            filter_value text not null default '',
            description text not null default '',
            created_at text not null default current_timestamp,
            unique(ontology_id, scope_object_code, name)
        )""",
        "postgresql": """
        create table if not exists cross_object_aggregate (
            id serial primary key,
            ontology_id integer not null references ontology(id),
            scope_object_code text not null,
            name text not null,
            function text not null,
            target_table text not null,
            target_column text not null,
            group_column text not null,
            value_column text not null default '',
            exclude_self boolean not null default false,
            self_column text not null default '',
            filter_column text not null default '',
            filter_value text not null default '',
            description text not null default '',
            created_at timestamp not null default current_timestamp,
            unique(ontology_id, scope_object_code, name)
        )""",
        "mysql": """
        create table if not exists cross_object_aggregate (
            id integer primary key auto_increment,
            ontology_id integer not null,
            scope_object_code varchar(255) not null,
            name varchar(255) not null,
            function varchar(50) not null,
            target_table varchar(255) not null,
            target_column varchar(255) not null,
            group_column varchar(255) not null,
            value_column varchar(255) not null default '',
            exclude_self tinyint not null default 0,
            self_column varchar(255) not null default '',
            filter_column varchar(255) not null default '',
            filter_value varchar(500) not null default '',
            description text,
            created_at datetime not null default current_timestamp,
            unique key uniq_aggregate (ontology_id, scope_object_code, name)
        )""",
    },
)


SCHEMA = SchemaBundle(
    name="aggregation",
    tables=AGGREGATE_SCHEMA,
    table_names=(AGGREGATE_TABLE,),
    columns=(
        # Added after the table shipped, so deployed databases need the ALTER. Default 0
        # means "the instance's own source", which is exactly what every stored aggregate
        # already did -- an upgrade therefore changes no result.
        ColumnAddition(
            table=AGGREGATE_TABLE,
            column="target_data_source_id",
            sqlite_type="integer not null default 0",
            postgresql_type="integer not null default 0",
            mysql_type="integer not null default 0",
        ),
    ),
)
SCHEMA.verify_declared_names()


def init_aggregate_schema(conn: Any) -> None:
    SCHEMA.apply(conn)


def define_aggregate(
    platform_db: Path | str,
    ontology_id: int,
    scope_object_code: str,
    spec: AggregateSpec,
    *,
    description: str = "",
    actor: str = "system",
) -> dict[str, Any]:
    """Declare an aggregate available to rules scoped to an object.

    Validated before storage, so a bad definition is refused here rather than
    surfacing as a failed assessment. Published ontologies are immutable.
    """
    spec.validate()
    with connect(platform_db) as conn:
        ontology = conn.execute("select status from ontology where id = ?", (ontology_id,)).fetchone()
        if ontology is None:
            raise AggregationError(f"本体不存在: {ontology_id}")
        if ontology["status"] == "published":
            raise AggregationError("已发布本体不可修改聚合定义，请派生新版本。")
        if spec.target_data_source_id and (
            conn.execute("select id from data_source where id = ?", (spec.target_data_source_id,)).fetchone() is None
        ):
            # 入库前拒绝：一个指向不存在数据源的跨源聚合，会在每次判定时 fail-closed，
            # 表现为「规则永远不通过」而不是「配置写错了」。
            raise AggregationError(f"跨源聚合的目标数据源不存在: {spec.target_data_source_id}")

        existing = conn.execute(
            """
            select id from cross_object_aggregate
            where ontology_id = ? and scope_object_code = ? and name = ?
            """,
            (ontology_id, scope_object_code, spec.name),
        ).fetchone()
        columns = (
            spec.function,
            spec.target_table,
            spec.target_column,
            spec.group_column,
            spec.value_column,
            1 if spec.exclude_self else 0,
            spec.self_column,
            spec.filter_column,
            spec.filter_value,
            description,
            spec.target_data_source_id,
        )
        if existing is not None:
            conn.execute(
                """
                update cross_object_aggregate
                set function = ?, target_table = ?, target_column = ?, group_column = ?,
                    value_column = ?, exclude_self = ?, self_column = ?,
                    filter_column = ?, filter_value = ?, description = ?,
                    target_data_source_id = ?
                where id = ?
                """,
                (*columns, int(existing["id"])),
            )
        else:
            conn.execute(
                """
                insert into cross_object_aggregate
                    (ontology_id, scope_object_code, name, function, target_table,
                     target_column, group_column, value_column, exclude_self,
                     self_column, filter_column, filter_value, description,
                     target_data_source_id)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (ontology_id, scope_object_code, spec.name, *columns),
            )
        conn.execute(
            "insert into audit_log (actor, action, target_type, target_id, detail) values (?, ?, ?, ?, ?)",
            (
                actor,
                "define_cross_object_aggregate",
                "cross_object_aggregate",
                f"{scope_object_code}.{spec.name}",
                json.dumps(spec.to_json(), ensure_ascii=False),
            ),
        )
    return {
        "name": spec.name,
        "scopeObjectCode": scope_object_code,
        "definition": spec.describe(),
        "note": "规则表达式可直接按该名称引用此聚合值。",
    }


def list_aggregates(platform_db: Path | str, ontology_id: int, scope_object_code: str = "") -> list[dict[str, Any]]:
    clauses = ["ontology_id = ?"]
    params: list[Any] = [ontology_id]
    if scope_object_code:
        clauses.append("scope_object_code = ?")
        params.append(scope_object_code)
    with connect(platform_db) as conn:
        try:
            rows = conn.execute(
                f"select * from cross_object_aggregate where {' and '.join(clauses)} order by name",
                tuple(params),
            ).fetchall()
        except Exception as error:
            logger.debug("聚合表尚未创建: %s", error)
            return []
    return [
        {
            **AggregateSpec.from_row(row).to_json(),
            "scopeObjectCode": row["scope_object_code"],
            "description": row["description"] or "",
            "definition": AggregateSpec.from_row(row).describe(),
        }
        for row in rows
    ]


def load_aggregate_specs(conn: Any, ontology_id: int, scope_object_code: str) -> list[AggregateSpec]:
    """Specs for one object, loaded on the caller's connection.

    Missing table is treated as "no aggregates" rather than an error: the schema is
    optional, and an assessment must still work without it.

    Probed via the catalog rather than by catching the error: on PostgreSQL a failed
    statement aborts the transaction, so every later command in the same assessment
    would fail (ADR-0004).
    """
    if not table_exists(conn, AGGREGATE_TABLE):
        return []
    rows = conn.execute(
        """
        select * from cross_object_aggregate
        where ontology_id = ? and scope_object_code = ?
        order by name
        """,
        (ontology_id, scope_object_code),
    ).fetchall()
    specs = []
    for row in rows:
        try:
            specs.append(AggregateSpec.from_row(row).validate())
        except AggregationError as error:
            # A stored definition that no longer validates is skipped and logged.
            # It will make its rule fail closed, which is the safe direction.
            logger.warning("聚合定义 %s 不合法，已跳过: %s", row["name"], error)
    return specs


@dataclass
class AggregateResult:
    """One computed aggregate, with enough detail to explain a verdict."""

    name: str
    value: Optional[float]
    definition: str
    row_count: int
    truncated: bool = False
    error: str = ""

    @property
    def computed(self) -> bool:
        return self.error == ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "definition": self.definition,
            "rowCount": self.row_count,
            "truncated": self.truncated,
            "error": self.error,
        }


def compute_aggregate(runtime: Any, spec: AggregateSpec, record: dict[str, Any]) -> AggregateResult:
    """Evaluate one aggregate against the data source.

    Reads matching rows through the adapter runtime rather than issuing aggregate
    SQL, so this works identically on all three dialects and honours whatever
    quoting the adapter already does. The row cap is the trade: correctness across
    dialects over pushing the computation into the database.
    """
    group_value = record.get(spec.group_column)
    if group_value is None:
        # No grouping value means the aggregate is undefined for this instance --
        # reported as an error so the rule fails closed rather than comparing
        # against a fabricated zero.
        return AggregateResult(
            name=spec.name,
            value=None,
            definition=spec.describe(),
            row_count=0,
            error=f"本实例的 {spec.group_column} 为空，无法计算聚合",
        )
    try:
        rows = runtime.fetch_related_many(spec.target_table, spec.target_column, group_value)
    except Exception as error:
        return AggregateResult(
            name=spec.name,
            value=None,
            definition=spec.describe(),
            row_count=0,
            error=f"读取聚合目标失败: {error}",
        )

    truncated = len(rows) > MAX_AGGREGATION_ROWS
    if truncated:
        rows = rows[:MAX_AGGREGATION_ROWS]

    if spec.filter_column:
        rows = [row for row in rows if str(row.get(spec.filter_column)) == spec.filter_value]
    if spec.exclude_self:
        self_value = record.get(spec.self_column)
        rows = [row for row in rows if str(row.get(spec.self_column)) != str(self_value)]

    if spec.function == "count":
        return AggregateResult(
            name=spec.name,
            value=float(len(rows)),
            definition=spec.describe(),
            row_count=len(rows),
            truncated=truncated,
        )

    values: list[float] = []
    for row in rows:
        raw = row.get(spec.value_column)
        if raw is None:
            continue
        try:
            values.append(float(raw))
        except (TypeError, ValueError):
            # A non-numeric value in a numeric aggregate is a modelling error;
            # failing closed beats quietly ignoring it.
            return AggregateResult(
                name=spec.name,
                value=None,
                definition=spec.describe(),
                row_count=len(rows),
                truncated=truncated,
                error=f"列 {spec.value_column} 含非数值内容: {raw!r}",
            )

    if not values:
        # An empty set is a legitimate answer for sum and count, but min/max/avg
        # of nothing is undefined. Saying so keeps a threshold rule from passing
        # on absent data.
        if spec.function == "sum":
            return AggregateResult(spec.name, 0.0, spec.describe(), 0, truncated)
        return AggregateResult(
            name=spec.name,
            value=None,
            definition=spec.describe(),
            row_count=0,
            truncated=truncated,
            error=f"{spec.function} 聚合没有可用数据",
        )

    computed = {
        "sum": sum(values),
        "min": min(values),
        "max": max(values),
        "avg": sum(values) / len(values),
    }[spec.function]
    return AggregateResult(
        name=spec.name,
        value=float(computed),
        definition=spec.describe(),
        row_count=len(values),
        truncated=truncated,
    )


def compute_aggregates(
    runtime: Any,
    specs: list[AggregateSpec],
    record: dict[str, Any],
    *,
    runtime_for: Any = None,
) -> dict[str, AggregateResult]:
    """Evaluate every aggregate, opening a secondary runtime only when one is needed.

    `runtime_for(data_source_id)` yields a runtime context for another source. Passed in
    rather than imported so this module does not need to know how adapters are built --
    that knowledge lives in the kernel, and importing it here would be a cycle.

    A cross-source aggregate whose source cannot be reached reports the failure rather
    than falling back to the local runtime: reading the *wrong* table would silently
    produce a plausible number (ADR-0002).
    """
    results: dict[str, AggregateResult] = {}
    for spec in specs:
        if not spec.target_data_source_id:
            results[spec.name] = compute_aggregate(runtime, spec, record)
            continue
        if runtime_for is None:
            results[spec.name] = AggregateResult(
                name=spec.name,
                value=None,
                definition=spec.describe(),
                row_count=0,
                error="跨源聚合需要调用方提供 runtime_for，当前上下文不支持跨源读取",
            )
            continue
        try:
            with runtime_for(spec.target_data_source_id) as secondary:
                results[spec.name] = compute_aggregate(secondary, spec, record)
        except Exception as error:
            results[spec.name] = AggregateResult(
                name=spec.name,
                value=None,
                definition=spec.describe(),
                row_count=0,
                error=f"无法连接副源数据源 #{spec.target_data_source_id}: {error}",
            )
    return results


def aggregate_context(results: dict[str, AggregateResult]) -> dict[str, Any]:
    """Values to inject into the rule sandbox.

    Only successfully computed aggregates are injected. An uncomputable one is
    deliberately absent, so a rule referencing it raises NameError -- which the
    kernel's fail-closed handling turns into "not passed" with the reason attached.
    Injecting None instead would let `x <= limit` evaluate misleadingly.
    """
    return {name: result.value for name, result in results.items() if result.computed}
