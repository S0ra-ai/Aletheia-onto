from __future__ import annotations

import ast
import json
import logging
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from .adapters import RuntimeDatabase, get_adapter
from .aggregation import aggregate_context, compute_aggregates, load_aggregate_specs
from .config import clamp_page_size, clamp_sample_size
from .database import connect, last_insert_id
from .decisions import record_decision_in_connection
from .derived_attributes import (
    apply_units,
    bind_sandbox,
    compute_derived,
    derived_context,
    load_attribute_units,
    load_derived_specs,
)
from .instance_key import parse_key_columns
from .ontology import explain_instance
from .registry import Registry, load_entry_point_plugins
from .relations import MANY_TO_MANY
from .type_hierarchy import expand, inherited_rule_scopes
from .value_mapping import load_value_mappings_in_connection, state_for

logger = logging.getLogger(__name__)


class RowObject:
    def __init__(self, values: dict[str, Any]):
        self._values = values

    def __getattr__(self, name: str) -> Any:
        return self._values.get(name)

    def as_dict(self) -> dict[str, Any]:
        return dict(self._values)


class MappedValue(str):
    """A legacy code that also compares equal to its semantic state name.

    Subclasses str so every existing operation on the column value keeps working
    -- comparison, `in`, string methods, JSON serialisation. What changes is that
    ``status == 'A'`` and ``status == '生效中'`` are both true for the same cell,
    which is what lets a rule be written in business language without breaking
    rules already written against the raw code.
    """

    state: str

    def __new__(cls, raw: Any, state: str) -> "MappedValue":
        instance = super().__new__(cls, "" if raw is None else str(raw))
        instance.state = state
        return instance

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str):
            return str(self) == other or self.state == other
        return NotImplemented

    def __ne__(self, other: object) -> bool:
        result = self.__eq__(other)
        return NotImplemented if result is NotImplemented else not result

    def __hash__(self) -> int:
        # Equality spans two strings, so hash on the raw value only; dict lookups
        # by state name are not supported and would be ambiguous anyway.
        return str.__hash__(self)


def _apply_value_mappings(
    context: dict[str, Any], table_name: str, mappings: dict[str, dict[str, str]]
) -> dict[str, Any]:
    updated = dict(context)
    for column, value in context.items():
        state = state_for(mappings, table_name, column, value)
        if state is not None and not isinstance(value, MappedValue):
            updated[column] = MappedValue(value, state)
    return updated


class RelatedValues(list[Any]):
    def __eq__(self, other: object) -> list[bool]:  # type: ignore[override]
        return [value == other for value in self]

    def __ne__(self, other: object) -> list[bool]:  # type: ignore[override]
        return [value != other for value in self]

    # Comparisons deliberately broadcast element-wise so a rule can say
    # `payment_plan.amount > 0` against every related row. That is incompatible
    # with list's own comparison signature, hence the overrides.
    def __lt__(self, other: object) -> list[bool]:  # type: ignore[override]
        return [_safe_compare(value, other, "lt") for value in self]

    def __le__(self, other: object) -> list[bool]:  # type: ignore[override]
        return [_safe_compare(value, other, "le") for value in self]

    def __gt__(self, other: object) -> list[bool]:  # type: ignore[override]
        return [_safe_compare(value, other, "gt") for value in self]

    def __ge__(self, other: object) -> list[bool]:  # type: ignore[override]
        return [_safe_compare(value, other, "ge") for value in self]


class RelatedRows:
    def __init__(self, rows: list[dict[str, Any]]):
        self._rows = [RowObject(row) for row in rows]

    def __getattr__(self, name: str) -> RelatedValues:
        return RelatedValues([row.as_dict().get(name) for row in self._rows])

    def __len__(self) -> int:
        return len(self._rows)

    def as_list(self) -> list[dict[str, Any]]:
        return [row.as_dict() for row in self._rows]


@dataclass(frozen=True)
class SemanticRuntime:
    ontology_id: int
    ontology_version: str
    object_code: str
    object_name: str
    source_table: str
    primary_key: str
    instance_id: str
    data_source_id: int
    data_source_uri: str
    record: dict[str, Any]
    context: dict[str, Any]
    related: dict[str, Any]
    # Cross-object aggregates, kept so a verdict can state what an aggregate was
    # rather than only the number it produced. Defaulted so existing constructions
    # keep working.
    aggregates: dict[str, Any] = field(default_factory=dict)
    # Derived attributes, kept so a verdict can state the expression behind a
    # computed value rather than only the number.
    derived: dict[str, Any] = field(default_factory=dict)


ALLOWED_AST_NODES = (
    ast.Expression,
    ast.BoolOp,
    ast.BinOp,
    ast.UnaryOp,
    ast.Compare,
    ast.Call,
    ast.Name,
    ast.Load,
    ast.Constant,
    ast.Attribute,
    ast.And,
    ast.Or,
    ast.Not,
    ast.USub,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Mod,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.Is,
    ast.IsNot,
)

# Rule functions callable from a business rule expression.
#
# Open for registration so a deployment can express domain-specific predicates
# without forking, but every entry still runs inside the AST allowlist sandbox:
# registering a function grants the right to *call* it, never the right to
# bypass node validation. Keep implementations pure and total -- a function that
# raises turns into a fail-closed "not passed" verdict for every instance of the
# scoped object (ADR-0002).
#
# Experimental: this signature may change before 1.0 (ADR-0007).
RULE_FUNCTION_REGISTRY: Registry[Callable[..., Any]] = Registry("规则函数")

RULE_FUNCTION_ENTRY_POINT_GROUP = "aletheia.rule_functions"


def register_rule_function(
    name: str,
    implementation: Callable[..., Any],
    *,
    replace: bool = False,
) -> Callable[..., Any]:
    """Make a function callable from rule expressions.

    >>> register_rule_function("abs", abs)                 # doctest: +SKIP
    >>> register_rule_function("days_between", days_between)  # doctest: +SKIP

    Names must be plain identifiers: the sandbox matches `ast.Name` nodes, so a
    dotted name could never be resolved and would fail confusingly at eval time.
    """
    if not name.isidentifier():
        raise ValueError(f"规则函数名必须是合法标识符: {name!r}")
    if name.startswith("_"):
        raise ValueError(f"规则函数名不能以下划线开头，避免与沙箱内部名冲突: {name!r}")
    if not callable(implementation):
        raise ValueError(f"规则函数 {name!r} 必须可调用")
    RULE_FUNCTION_REGISTRY.register(name, implementation, replace=replace)
    return implementation


def allowed_rule_function_names() -> frozenset[str]:
    return frozenset(RULE_FUNCTION_REGISTRY.names())


def load_rule_function_plugins() -> list[str]:
    return load_entry_point_plugins(
        RULE_FUNCTION_ENTRY_POINT_GROUP,
        lambda name, func: register_rule_function(name, func),
    )


# Attribute access is needed to reach related rows (payment_plan.amount), but
# dunder attributes are the entry point for sandbox escapes via __class__,
# __globals__ and friends.
FORBIDDEN_ATTRIBUTE_PREFIXES = ("__",)


def assess_instance(platform_db: Path | str, ontology_id: int, object_code: str, instance_id: str) -> dict[str, Any]:
    with connect(platform_db) as platform:
        runtime = build_runtime(platform, ontology_id, object_code, instance_id)
        today = date.today().isoformat()
        # Rules apply to the object *and to every declared ancestor* (generality #6).
        # Without this, a rule that governs all customers has to be copied onto each
        # subtype -- and the copies drift, so the same business question gets two
        # answers depending on which subtype the instance happens to be.
        expansion = expand(platform, ontology_id, object_code)
        scopes = inherited_rule_scopes(platform, ontology_id, object_code)
        # A rule the subtype declared as superseding an ancestor's removes that
        # ancestor rule from the expansion. Weakening is allowed -- a legitimate
        # business exception exists -- but only when declared, never by accident.
        origin_by_code = {rule.code: rule.origin_object_code for rule in expansion.rules}
        placeholders = ", ".join("?" for _ in scopes)
        rules = [
            rule
            for rule in platform.execute(
                f"""
                select *
                from business_rule
                where ontology_id = ?
                  and scope_object_code in ({placeholders})
                  and status = 'published'
                  and (effective_start is null or effective_start <= ?)
                  and (effective_end is null or effective_end >= ?)
                order by priority desc, severity, code
                """,
                (ontology_id, *scopes, today, today),
            ).fetchall()
            if rule["code"] in origin_by_code
        ]

        # Honour declared dependencies. `depends_on` was read and written but
        # never used during evaluation, so a rule that only makes sense after a
        # prerequisite passed could run first and produce a misleading failure.
        rules = order_rules_by_dependency(rules)
        satisfied: set[str] = set()

        results = []
        for rule in rules:
            blocked_by = _unsatisfied_dependencies(rule, satisfied)
            passed: bool
            error: str | None
            if blocked_by:
                # A dependency that did not pass makes this rule's verdict
                # meaningless, so report it as not passed with the reason rather
                # than evaluating it against a precondition known to be false.
                passed, error = False, (f"前置规则未通过：{'、'.join(blocked_by)}")
            else:
                passed, error = _evaluate_rule(rule["expression"], runtime.context)
            skipped = error is not None
            # Fail closed: an expression that cannot be evaluated (renamed
            # column, type mismatch, bad syntax) must not be reported as a
            # pass, otherwise structural drift silently disables a blocking
            # rule and automation keeps running on unverified data.
            decision_passed = False if skipped else passed
            explanation = _build_explanation(rule, passed, error)
            evidence = {
                "record": runtime.record,
                "related": _serializable_related(runtime.related),
                "expression": rule["expression"],
                "skipped": skipped,
                "evaluationError": error or "",
            }
            # A verdict citing an inherited rule must say which type guarantees it,
            # or the operator cannot tell where to go to change it.
            inherited = origin_by_code.get(rule["code"], object_code) != object_code
            if inherited:
                evidence["inheritedFrom"] = rule["scope_object_code"]
            platform.execute(
                """
                insert into inference_result (
                    rule_id, object_code, instance_id, result_type, severity, passed, explanation, evidence
                )
                values (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rule["id"],
                    object_code,
                    instance_id,
                    rule["rule_type"],
                    rule["severity"],
                    1 if decision_passed else 0,
                    explanation,
                    _json_dumps(evidence),
                ),
            )
            inference_id = last_insert_id(platform)
            platform.execute(
                """
                insert into explanation_trace (
                    inference_result_id, ontology_version, mapping_refs, source_refs, rule_refs
                )
                values (?, ?, ?, ?, ?)
                """,
                (
                    inference_id,
                    runtime.ontology_version,
                    _json_dumps(_mapping_refs(platform, ontology_id, runtime.source_table)),
                    _json_dumps(
                        {"table": runtime.source_table, "primaryKey": runtime.primary_key, "instanceId": instance_id}
                    ),
                    _json_dumps({"ruleId": rule["id"], "ruleCode": rule["code"]}),
                ),
            )
            results.append(
                {
                    "ruleCode": rule["code"],
                    "ruleName": rule["name"],
                    "ruleType": rule["rule_type"],
                    "severity": rule["severity"],
                    "passed": decision_passed,
                    "skipped": skipped,
                    "evaluationError": error or "",
                    "explanation": explanation,
                    "naturalLanguage": rule["natural_language"],
                    # Empty unless the rule came from an ancestor type.
                    "inheritedFrom": rule["scope_object_code"] if inherited else "",
                }
            )
            if decision_passed:
                satisfied.add(rule["code"])

        failed = [result for result in results if not result["passed"]]
        decision = _decision_from_results(failed)
        decision_record = record_decision_in_connection(
            platform,
            "instance_assessment",
            decision["status"],
            decision["recommendation"],
            ontology_id=ontology_id,
            object_code=object_code,
            instance_id=instance_id,
            input_ref={"objectCode": object_code, "instanceId": instance_id},
            rule_results=results,
            evidence={
                "failedRules": [item["ruleCode"] for item in failed],
                "ontologyVersion": runtime.ontology_version,
            },
            actor="semantic_kernel",
        )
        decision["decisionId"] = decision_record["decisionId"]
        platform.execute(
            "insert into audit_log (actor, action, target_type, target_id, detail) values (?, ?, ?, ?, ?)",
            (
                "semantic_kernel",
                "assess_instance",
                object_code,
                instance_id,
                _json_dumps(
                    {
                        "ontologyId": ontology_id,
                        "decision": decision["status"],
                        "decisionId": decision["decisionId"],
                        "failedRules": len(failed),
                    }
                ),
            ),
        )
        # Distinct from the per-rule `explanation` string built in the loop
        # above: this is the structured instance explanation.
        instance_explanation = explain_instance(platform_db, ontology_id, object_code, instance_id)
        return {
            "semanticKernel": {
                "ontologyId": ontology_id,
                "ontologyVersion": runtime.ontology_version,
                "objectCode": object_code,
                "instanceId": instance_id,
            },
            "explanation": instance_explanation,
            "relatedContext": _serializable_related(runtime.related),
            "ruleResults": results,
            "decision": decision,
        }


def assess_decision_consistency(
    platform_db: Path | str,
    ontology_id: int,
    object_code: str,
    instance_ids: list[str] | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    resolved_limit = clamp_sample_size(limit)
    ids = [str(item) for item in instance_ids or [] if str(item).strip()]
    if not ids:
        ids = [str(item) for item in list_instance_ids(platform_db, ontology_id, object_code, resolved_limit)]
    else:
        ids = ids[:resolved_limit]

    assessments: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for instance_id in ids:
        try:
            assessment = assess_instance(platform_db, ontology_id, object_code, instance_id)
            failed_rules = [rule for rule in assessment["ruleResults"] if not rule["passed"]]
            assessments.append(
                {
                    "instanceId": instance_id,
                    "decision": assessment["decision"]["status"],
                    "recommendation": assessment["decision"]["recommendation"],
                    "decisionId": assessment["decision"]["decisionId"],
                    "failedRules": [rule["ruleCode"] for rule in failed_rules],
                    "failedRuleCount": len(failed_rules),
                }
            )
        except ValueError as error:
            errors.append({"instanceId": instance_id, "error": str(error)})

    status_counts = _status_counts(assessments)
    failed_rule_counts = _failed_rule_counts(assessments)
    report_status = _consistency_status(status_counts, errors)
    report = {
        "ontologyId": ontology_id,
        "objectCode": object_code,
        "sampleSize": len(ids),
        "assessed": len(assessments),
        "errorCount": len(errors),
        "status": report_status,
        "summary": {
            "approved": status_counts.get("approved", 0),
            "review": status_counts.get("review", 0),
            "blocked": status_counts.get("blocked", 0),
            "errors": len(errors),
            "uniqueDecisionStatuses": len([value for value in status_counts.values() if value > 0]),
        },
        "ruleFailures": failed_rule_counts,
        "items": assessments,
        "errors": errors,
        "nextActions": _consistency_next_actions(report_status, status_counts, failed_rule_counts, errors),
    }
    with connect(platform_db) as conn:
        conn.execute(
            "insert into audit_log (actor, action, target_type, target_id, detail) values (?, ?, ?, ?, ?)",
            (
                "semantic_kernel",
                "assess_decision_consistency",
                object_code,
                str(ontology_id),
                _json_dumps(
                    {
                        "sampleSize": report["sampleSize"],
                        "assessed": report["assessed"],
                        "status": report["status"],
                        "summary": report["summary"],
                    }
                ),
            ),
        )
    return report


def list_instance_ids(platform_db: Path | str, ontology_id: int, object_code: str, limit: int = 50) -> list[Any]:
    resolved_limit = clamp_page_size(limit)
    with connect(platform_db) as platform:
        runtime = _runtime_target(platform, ontology_id, object_code)
        adapter = get_adapter(runtime["source_type"])
        with adapter.runtime(runtime["connection_uri"]) as database:
            # Through the resolver, so a discriminated object lists only its own
            # partition and a custom-SQL object lists what its query returns.
            # Listing raw primary keys would hand batch assessment ids that the
            # object's own fetch() then rejects.
            return list(runtime["resolver"].list_ids(database, resolved_limit))


def available_rule_names(platform_db: Path | str, ontology_id: int, object_code: str) -> list[str]:
    """List the names a rule for this object may reference.

    Combines the source table's own columns with the related table names that
    the runtime loads as context, so the UI can warn about typos and drift.
    """
    with connect(platform_db) as platform:
        business_object = platform.execute(
            "select source_table_id from business_object where ontology_id = ? and code = ?",
            (ontology_id, object_code),
        ).fetchone()
        if business_object is None or business_object["source_table_id"] is None:
            return []
        source_table_id = business_object["source_table_id"]
        source_table = platform.execute(
            "select table_name, data_source_id from source_table where id = ?",
            (source_table_id,),
        ).fetchone()
        if source_table is None:
            return []
        names = {
            row["column_name"]
            for row in platform.execute(
                "select column_name from source_column where source_table_id = ?",
                (source_table_id,),
            ).fetchall()
        }
        names.update(
            row["target_table"]
            for row in platform.execute(
                "select target_table from source_foreign_key where source_table_id = ?",
                (source_table_id,),
            ).fetchall()
        )
        names.update(
            row["child_table"]
            for row in platform.execute(
                """
                select st.table_name as child_table
                from source_foreign_key fk
                join source_table st on st.id = fk.source_table_id
                where st.data_source_id = ? and fk.target_table = ?
                """,
                (source_table["data_source_id"], source_table["table_name"]),
            ).fetchall()
        )
        return sorted(names)


def _wrap_resolver_children(record: dict[str, Any]) -> dict[str, Any]:
    """Give resolver output the same shape foreign-key discovery produces.

    A resolver may attach a child collection (`joined_tables`) or a single related
    row. Rules address those by attribute -- `sum(order_line.amount)` -- which only
    works on RelatedRows/RowObject, not on the raw list or dict a resolver returns.

    Scalars are left untouched: a column holding a JSON string must stay a string,
    or rules comparing it would break.
    """
    wrapped: dict[str, Any] = {}
    for name, value in record.items():
        if isinstance(value, list) and all(isinstance(item, dict) for item in value):
            wrapped[name] = RelatedRows(value)
        elif isinstance(value, dict):
            wrapped[name] = RowObject(value)
        else:
            wrapped[name] = value
    return wrapped


def resolver_for(business_object: Any, source_table: Any) -> Any:
    """Build the resolver for a business object.

    Falls back to single-table when `resolver_spec` is unset or unreadable, so an
    object created before resolvers existed -- or by an older build -- keeps working.
    """
    from .instance_resolver import ResolverSpec, build_resolver

    raw = ""
    try:
        raw = business_object["resolver_spec"] or ""
    except (KeyError, IndexError, TypeError):
        raw = ""
    spec = ResolverSpec.from_json(
        raw,
        table=source_table["table_name"] if source_table is not None else "",
        primary_key=(source_table["primary_key"] or "id") if source_table is not None else "id",
    )
    return build_resolver(spec)


def build_runtime(
    platform: sqlite3.Connection, ontology_id: int, object_code: str, instance_id: str
) -> SemanticRuntime:
    ontology = platform.execute("select * from ontology where id = ?", (ontology_id,)).fetchone()
    if ontology is None:
        raise ValueError(f"本体不存在: {ontology_id}")
    business_object = platform.execute(
        "select * from business_object where ontology_id = ? and code = ?",
        (ontology_id, object_code),
    ).fetchone()
    if business_object is None:
        raise ValueError(f"业务对象不存在: {object_code}")
    source_table = platform.execute(
        "select * from source_table where id = ?", (business_object["source_table_id"],)
    ).fetchone()
    if source_table is None:
        raise ValueError(f"业务对象未绑定来源表: {object_code}")
    data_source = platform.execute(
        "select ds.* from data_source ds join source_table st on st.data_source_id = ds.id where st.id = ?",
        (source_table["id"],),
    ).fetchone()
    primary_key = source_table["primary_key"] or "id"
    adapter = get_adapter(data_source["source_type"])
    with adapter.runtime(data_source["connection_uri"]) as runtime:
        # Route through the object's resolver. An unset resolver_spec yields the
        # single-table resolver, whose behaviour is identical to the previous
        # direct fetch_one call -- required, since this path produces verdicts.
        resolver = resolver_for(business_object, source_table)
        record = resolver.fetch(runtime, instance_id)
        if record is None:
            raise ValueError(f"实例不存在: {object_code}/{instance_id}")
        # Wrap resolver-provided child rows the way foreign-key discovery does.
        # Without this a rule reading `order_line.amount` receives a plain list and
        # fails with "'list' object has no attribute 'amount'"; fail-closed then
        # reports that as a blocking violation, turning a wiring detail into a
        # wrong verdict.
        context: dict[str, Any] = _wrap_resolver_children(record)
        related = _load_related_context(
            platform, runtime, ontology_id, data_source["id"], source_table, primary_key, record
        )
        # Collapsed many-to-many relations, exposed as the far side's rows so a rule
        # never has to hop through the junction table by hand.
        related.update(_load_many_to_many_context(platform, runtime, ontology_id, object_code, record, primary_key))
        # Resolver-provided children take precedence: they were declared
        # explicitly, whereas foreign-key discovery is inferred.
        for name, value in related.items():
            context.setdefault(name, value)

        # Cross-object aggregates (generality #5). Computed here, inside the
        # runtime block, because they read the same data source. Only successful
        # ones enter the context: a referenced-but-uncomputable aggregate must
        # raise NameError so the rule fails closed with a reason, rather than
        # comparing a threshold against a fabricated zero.
        # Along the ancestry, so an aggregate declared on 客户 is available to rules
        # on 企业客户. Nearest first, and a nearer declaration of the same name wins:
        # a subtype refining an aggregate is the same override semantics as rules.
        aggregate_specs = _inherited_aggregate_specs(platform, ontology_id, object_code)
        aggregate_results = compute_aggregates(runtime, aggregate_specs, record) if aggregate_specs else {}
        context.update(aggregate_context(aggregate_results))

    # Declared units (generality #10). Applied to the stored record before anything
    # derived is computed, so a derived expression over united columns inherits
    # units rather than mixing scales.
    attribute_units = load_attribute_units(platform, ontology_id, object_code)
    if attribute_units:
        context = apply_units(context, attribute_units)

    # Confirmed value mappings let a rule be written in business language
    # (status == '生效中') instead of against a legacy code (status == 'A').
    # Both forms must evaluate identically, so each mapped column is exposed as
    # a value that compares equal to the code and to the state name.
    value_mappings = load_value_mappings_in_connection(platform, ontology_id)
    if value_mappings:
        context = _apply_value_mappings(context, source_table["table_name"], value_mappings)

    # Derived attributes (generality #7). Last, so they can read stored columns,
    # related rows, aggregates and united values. Only computed ones enter the
    # context: a referenced-but-uncomputable derived value must raise NameError so
    # the rule fails closed, rather than comparing against a fabricated None.
    # Along the ancestry too: a 毛利率 defined on 合同 must be available to 框架合同.
    derived_specs = _inherited_derived_specs(platform, ontology_id, object_code)
    derived_results = compute_derived(derived_specs, context) if derived_specs else {}
    context.update(derived_context(derived_results))

    return SemanticRuntime(
        ontology_id=ontology_id,
        ontology_version=ontology["version"],
        object_code=object_code,
        object_name=business_object["name"],
        source_table=source_table["table_name"],
        primary_key=primary_key,
        instance_id=instance_id,
        data_source_id=data_source["id"],
        data_source_uri=data_source["connection_uri"],
        record=record,
        context=context,
        related=related,
        aggregates={name: result.as_dict() for name, result in aggregate_results.items()},
        derived={code: result.as_dict() for code, result in derived_results.items()},
    )


def _inherited_derived_specs(platform: sqlite3.Connection, ontology_id: int, object_code: str) -> list[Any]:
    """Derived attributes along the ancestry, nearest declaration winning.

    Same reasoning as inherited aggregates: one name must resolve to one definition,
    or which one a rule saw would depend on load order.
    """
    specs: list[Any] = []
    claimed: set[str] = set()
    for scope in inherited_rule_scopes(platform, ontology_id, object_code):
        for spec in load_derived_specs(platform, ontology_id, scope):
            if spec.code in claimed:
                continue
            claimed.add(spec.code)
            specs.append(spec)
    return specs


def _inherited_aggregate_specs(platform: sqlite3.Connection, ontology_id: int, object_code: str) -> list[Any]:
    """Aggregates declared on the object and on every ancestor, nearest first.

    A nearer declaration of the same name wins, which is the same override semantics
    rules have: a subtype refining «客户合同总额» must not end up with two values under
    one name, because which one a rule saw would then depend on load order.
    """
    specs: list[Any] = []
    claimed: set[str] = set()
    for scope in inherited_rule_scopes(platform, ontology_id, object_code):
        for spec in load_aggregate_specs(platform, ontology_id, scope):
            if spec.name in claimed:
                continue
            claimed.add(spec.name)
            specs.append(spec)
    return specs


def _load_related_context(
    platform: sqlite3.Connection,
    runtime: RuntimeDatabase,
    ontology_id: int,
    data_source_id: int,
    source_table: sqlite3.Row,
    primary_key: str,
    record: dict[str, Any],
) -> dict[str, Any]:
    related: dict[str, Any] = {}
    # Rules are written in ontology language, so a related object must be
    # addressable by its business object code -- `customer.credit_status` -- and
    # not only by the physical table name that happens to back it (`customers`).
    # Both keys are exposed: dropping the table name would break rules already
    # written against it, and the blueprint templates use the object code.
    object_codes = _related_object_codes(platform, ontology_id, data_source_id)

    def _publish(table_name: str, value: Any) -> None:
        related[table_name] = value
        code = object_codes.get(table_name)
        if code and code != table_name:
            related[code] = value

    direct_foreign_keys = platform.execute(
        "select * from source_foreign_key where source_table_id = ?",
        (source_table["id"],),
    ).fetchall()
    for foreign_key in direct_foreign_keys:
        value = record.get(foreign_key["column_name"])
        if value is None:
            continue
        row = runtime.fetch_related_one(foreign_key["target_table"], foreign_key["target_column"], value)
        if row is not None:
            _publish(foreign_key["target_table"], RowObject(row))

    reverse_foreign_keys = platform.execute(
        """
        select fk.*, st.table_name as child_table, st.primary_key as child_primary_key
        from source_foreign_key fk
        join source_table st on st.id = fk.source_table_id
        where st.data_source_id = ?
          and fk.target_table = ?
        """,
        (data_source_id, source_table["table_name"]),
    ).fetchall()
    current_key = record.get(primary_key)
    for foreign_key in reverse_foreign_keys:
        rows = runtime.fetch_related_many(foreign_key["child_table"], foreign_key["column_name"], current_key)
        # A child whose entire primary key *is* the foreign key can only ever have
        # one row per parent, so it is published as that row rather than as a
        # collection. This matters for correctness, not convenience: on a
        # collection, `profile.status != 'x'` evaluates to `[False]`, which is
        # truthy, so a rule written the obvious way would silently pass.
        if tuple(parse_key_columns(foreign_key["child_primary_key"])) == (foreign_key["column_name"],):
            _publish(foreign_key["child_table"], RowObject(rows[0]) if rows else RowObject({}))
        else:
            _publish(foreign_key["child_table"], RelatedRows(rows))

    return related


def _load_many_to_many_context(
    platform: sqlite3.Connection,
    runtime: RuntimeDatabase,
    ontology_id: int,
    object_code: str,
    record: dict[str, Any],
    primary_key: str,
) -> dict[str, Any]:
    """Expose collapsed many-to-many relations as collections of the far side.

    Without this a rule about "the contract's tags" has to hop through the junction
    table by hand -- `contract_tag.tag_id` gives ids, not tags -- which is exactly the
    modelling detail the relation was collapsed to hide.

    Traversal is two hops read through the adapter rather than a join, so it works
    identically on every dialect and honours whatever quoting the adapter applies.
    """
    relations = platform.execute(
        """
        select br.junction_table, br.junction_source_column, br.junction_target_column,
               tobj.code as target_code, st.table_name as target_table, st.primary_key as target_primary_key
        from business_relation br
        join business_object so on so.id = br.source_object_id
        join business_object tobj on tobj.id = br.target_object_id
        join source_table st on st.id = tobj.source_table_id
        where br.ontology_id = ? and so.code = ? and br.cardinality = ?
          and br.junction_table <> ''
        """,
        (ontology_id, object_code, MANY_TO_MANY),
    ).fetchall()
    current_key = record.get(primary_key)
    if current_key is None:
        return {}
    context: dict[str, Any] = {}
    for relation in relations:
        links = runtime.fetch_related_many(relation["junction_table"], relation["junction_source_column"], current_key)
        target_key = parse_key_columns(relation["target_primary_key"])[0]
        rows = []
        for link in links:
            far_value = link.get(relation["junction_target_column"])
            if far_value is None:
                continue
            row = runtime.fetch_related_one(relation["target_table"], target_key, far_value)
            if row is not None:
                rows.append(row)
        # Addressable by object code and by table name, same as direct relations.
        collection = RelatedRows(rows)
        context[relation["target_code"]] = collection
        context.setdefault(relation["target_table"], collection)
    return context


def _related_object_codes(platform: sqlite3.Connection, ontology_id: int, data_source_id: int) -> dict[str, str]:
    """Physical table name -> business object code, for this ontology's objects.

    Only objects of the same ontology are considered: a table reachable in the
    data source but not modelled has no object code, so it stays addressable by
    its table name alone.
    """
    rows = platform.execute(
        """
        select st.table_name as table_name, bo.code as code
        from business_object bo
        join source_table st on st.id = bo.source_table_id
        where bo.ontology_id = ? and st.data_source_id = ?
        """,
        (ontology_id, data_source_id),
    ).fetchall()
    return {row["table_name"]: row["code"] for row in rows}


def parse_depends_on(raw: Any) -> list[str]:
    """Read the stored dependency list, tolerating malformed values.

    Stored as a JSON array of rule codes. A malformed value degrades to "no
    dependencies" rather than breaking assessment: losing an ordering hint is
    recoverable, refusing to evaluate any rule is not.
    """
    if not raw:
        return []
    if isinstance(raw, (list, tuple)):
        return [str(code).strip() for code in raw if str(code).strip()]
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(parsed, list):
        return []
    return [str(code).strip() for code in parsed if str(code).strip()]


def order_rules_by_dependency(rules: Sequence[Any]) -> list[Any]:
    """Topologically order rules so prerequisites evaluate first.

    Ties keep the existing ordering (priority desc, severity, code), so behaviour
    is unchanged for the common case where nothing declares a dependency.

    Cycles are broken rather than raised: a cyclic declaration is a modelling
    mistake, but refusing to assess the instance at all would turn a bad hint into
    an outage. Rules in a cycle are appended in their original order and the cycle
    is logged.
    """
    by_code = {rule["code"]: rule for rule in rules}
    remaining = list(rules)
    ordered: list[Any] = []
    placed: set[str] = set()

    while remaining:
        progressed = False
        deferred = []
        for rule in remaining:
            # Only dependencies that exist in this scope can gate ordering; a
            # reference to an unknown or out-of-scope code is ignored here and
            # surfaced at evaluation time instead.
            pending = [
                code
                for code in parse_depends_on(rule["depends_on"] if "depends_on" in rule.keys() else None)  # noqa: SIM118
                if code in by_code and code not in placed and code != rule["code"]
            ]
            if pending:
                deferred.append(rule)
            else:
                ordered.append(rule)
                placed.add(rule["code"])
                progressed = True
        if not progressed:
            logger.warning(
                "规则依赖存在循环，已按原顺序追加: %s",
                "、".join(str(rule["code"]) for rule in deferred),
            )
            ordered.extend(deferred)
            break
        remaining = deferred
    return ordered


def _unsatisfied_dependencies(rule: Any, satisfied: set[str]) -> list[str]:
    """Declared prerequisites that have not passed in this run."""
    declared = parse_depends_on(rule["depends_on"] if "depends_on" in rule.keys() else None)  # noqa: SIM118
    return [code for code in declared if code and code not in satisfied]


def evaluate_rule_expression(expression: str, context: dict[str, Any]) -> tuple[bool, str | None]:
    """Evaluate an expression in the rule sandbox.

    Public entry point for callers outside the rule engine -- currently workflow
    transition guards. Exposed deliberately rather than letting other modules
    reach for the private `_evaluate_rule`, so there is exactly one sandbox to
    audit and guards inherit its hardening.

    Returns (passed, error). A non-None error means the expression could not be
    evaluated; callers are expected to treat that as *not passed* (ADR-0002).
    """
    return _evaluate_rule(expression, context)


def _evaluate_rule(expression: str, context: dict[str, Any]) -> tuple[bool, str | None]:
    value, error = evaluate_expression_value(expression, context)
    if error is not None:
        return False, error
    return bool(value), None


def evaluate_expression_value(expression: str, context: dict[str, Any]) -> tuple[Any, str | None]:
    """Evaluate an expression and return its *value* rather than its truthiness.

    Rules only need a verdict, but a derived attribute needs the number. Both go
    through this one function so there is exactly one sandbox to audit -- a second
    evaluator would drift, and the looser of the two would become the way in.

    Returns (value, error). A non-None error means the expression could not be
    evaluated; callers are expected to treat that as unusable (ADR-0002), never to
    substitute a default.
    """
    normalized = _normalize_expression(expression)
    try:
        tree = ast.parse(normalized, mode="eval")
        _validate_ast(tree)
        value = eval(compile(tree, "<business-rule>", "eval"), {"__builtins__": {}}, _allowed_names(context))
        return value, None
    except Exception as error:
        return None, str(error)


def _normalize_expression(expression: str) -> str:
    normalized = re.sub(r"\bnull\b", "None", expression)
    normalized = normalized.replace(" is not None", " != None").replace(" is None", " == None")
    return normalized


def _validate_ast(tree: ast.AST) -> None:
    for node in ast.walk(tree):
        if not isinstance(node, ALLOWED_AST_NODES):
            raise ValueError(f"不允许的规则表达式节点: {type(node).__name__}")
        if isinstance(node, ast.Call):
            allowed = allowed_rule_function_names()
            if not isinstance(node.func, ast.Name) or node.func.id not in allowed:
                raise ValueError(f"只允许 {'、'.join(sorted(allowed))} 函数")
            if node.keywords:
                raise ValueError("规则函数不支持关键字参数")
        if isinstance(node, ast.Attribute) and node.attr.startswith(FORBIDDEN_ATTRIBUTE_PREFIXES):
            raise ValueError(f"不允许访问内部属性: {node.attr}")


def validate_rule_expression(expression: str, available_names: Iterable[str] | None = None) -> dict[str, Any]:
    """Statically check a business rule expression.

    Called when a rule is written so an unparseable expression is rejected up
    front instead of silently failing during assessment.
    """
    text = (expression or "").strip()
    if not text:
        return {"valid": False, "error": "规则表达式不能为空", "referencedNames": []}
    normalized = _normalize_expression(text)
    try:
        tree = ast.parse(normalized, mode="eval")
        _validate_ast(tree)
    except SyntaxError as error:
        return {"valid": False, "error": f"规则表达式语法错误: {error.msg}", "referencedNames": []}
    except ValueError as error:
        return {"valid": False, "error": str(error), "referencedNames": []}

    referenced = sorted(
        {
            node.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Name) and node.id not in allowed_rule_function_names() and node.id != "None"
        }
    )
    result: dict[str, Any] = {"valid": True, "error": "", "referencedNames": referenced}
    if available_names is not None:
        known = set(available_names)
        unknown = [name for name in referenced if name not in known]
        result["unknownNames"] = unknown
        if unknown:
            result["warning"] = "表达式引用了当前来源结构中不存在的字段: " + "、".join(unknown)
    return result


def _allowed_names(context: dict[str, Any]) -> dict[str, Any]:
    names = dict(context)
    # Registered functions are added after the context so a column named `sum`
    # cannot shadow the function and silently change what a rule means.
    names.update(dict(RULE_FUNCTION_REGISTRY.items()))
    names["None"] = None
    return names


# Derived attributes evaluate in this same sandbox, injected rather than imported so
# the dependency stays one-directional (see `derived_attributes`).
bind_sandbox(evaluate_expression_value, validate_rule_expression)


def _count(value: Any) -> int:
    if isinstance(value, (RelatedValues, list, tuple)):
        return sum(1 for item in value if item)
    if isinstance(value, RelatedRows):
        return len(value)
    return 1 if value else 0


def _safe_compare(left: Any, right: object, operator: str) -> bool:
    try:
        if operator == "lt":
            return left < right
        if operator == "le":
            return left <= right
        if operator == "gt":
            return left > right
        if operator == "ge":
            return left >= right
    except TypeError:
        return False
    return False


def _serializable_related(related: dict[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in related.items():
        if isinstance(value, RowObject):
            output[key] = value.as_dict()
        elif isinstance(value, RelatedRows):
            output[key] = value.as_list()
        else:
            output[key] = value
    return output


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _mapping_refs(platform: sqlite3.Connection, ontology_id: int, source_table: str) -> list[str]:
    rows = platform.execute(
        """
        select source_ref
        from semantic_mapping
        where ontology_id = ?
          and source_ref like ?
        order by id
        """,
        (ontology_id, f"table:{source_table}%"),
    ).fetchall()
    return [row["source_ref"] for row in rows]


def _build_explanation(rule: sqlite3.Row, passed: bool, error: str | None) -> str:
    if error is not None:
        return (
            f"规则“{rule['name']}”无法在当前数据结构上求值，已按未通过处理，需人工复核规则表达式或来源字段。"
            f"（原因：{error}）"
        )
    prefix = "通过" if passed else "未通过"
    return f"{prefix}：{rule['natural_language']}"


def _decision_from_results(failed: list[dict[str, Any]]) -> dict[str, Any]:
    unevaluable = [result for result in failed if result.get("skipped")]
    if any(result["severity"] == "blocking" for result in failed):
        if unevaluable:
            return {
                "status": "blocked",
                "recommendation": (
                    "存在阻断级规则未通过，且部分规则无法求值（可能由结构漂移导致）。"
                    "应暂停自动化操作，先修复规则表达式或来源字段映射。"
                ),
            }
        return {
            "status": "blocked",
            "recommendation": "存在阻断级规则未通过，应暂停自动化操作并要求业务人员复核。",
        }
    if failed:
        if unevaluable:
            return {
                "status": "review",
                "recommendation": (
                    "部分规则无法在当前数据结构上求值，已按未通过处理，应人工复核规则表达式与来源字段后再恢复自动化。"
                ),
            }
        return {
            "status": "review",
            "recommendation": "存在风险或警告，应进入人工复核或触发后续治理流程。",
        }
    return {
        "status": "approved",
        "recommendation": "未发现阻断或风险规则，允许进入后续自动化流程。",
    }


def _runtime_target(platform: sqlite3.Connection, ontology_id: int, object_code: str) -> dict[str, Any]:
    business_object = platform.execute(
        "select * from business_object where ontology_id = ? and code = ?",
        (ontology_id, object_code),
    ).fetchone()
    if business_object is None:
        raise ValueError(f"业务对象不存在: {object_code}")
    source_table = platform.execute(
        "select * from source_table where id = ?", (business_object["source_table_id"],)
    ).fetchone()
    if source_table is None:
        raise ValueError(f"业务对象未绑定来源表: {object_code}")
    primary_key = source_table["primary_key"] or "id"
    data_source = platform.execute(
        "select ds.* from data_source ds join source_table st on st.data_source_id = ds.id where st.id = ?",
        (source_table["id"],),
    ).fetchone()
    return {
        "source_type": data_source["source_type"],
        "connection_uri": data_source["connection_uri"],
        "table_name": source_table["table_name"],
        "primary_key": primary_key,
        "resolver": resolver_for(business_object, source_table),
    }


def _status_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"approved": 0, "review": 0, "blocked": 0}
    for item in items:
        counts[item["decision"]] = counts.get(item["decision"], 0) + 1
    return counts


def _failed_rule_counts(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for item in items:
        for rule_code in item["failedRules"]:
            counts[rule_code] = counts.get(rule_code, 0) + 1
    return [
        {"ruleCode": rule_code, "failures": failures}
        for rule_code, failures in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
    ]


def _consistency_status(status_counts: dict[str, int], errors: list[dict[str, str]]) -> str:
    if errors:
        return "incomplete"
    active_statuses = [status for status, count in status_counts.items() if count > 0]
    if not active_statuses:
        return "empty"
    if len(active_statuses) <= 1:
        return "consistent"
    if status_counts.get("blocked", 0):
        return "mixed_with_blockers"
    return "mixed"


def _consistency_next_actions(
    status: str,
    status_counts: dict[str, int],
    failed_rule_counts: list[dict[str, Any]],
    errors: list[dict[str, str]],
) -> list[str]:
    if status == "empty":
        return ["没有可评估实例，请检查来源表数据或显式传入实例 ID。"]
    if status == "consistent" and status_counts.get("approved", 0):
        return ["样本决策全部通过，可继续扩大批量验证范围。"]
    if status == "consistent":
        return ["样本决策结果一致但未全部通过，应确认该业务对象当前规则阈值是否符合预期。"]
    actions: list[str] = []
    if errors:
        actions.append("先处理批量评估中的实例读取或规则执行错误。")
    if failed_rule_counts:
        actions.append(f"优先复核失败次数最高的规则：{failed_rule_counts[0]['ruleCode']}。")
    if status_counts.get("blocked", 0):
        actions.append("存在阻断级决策，自动化执行前必须完成规则或数据治理。")
    if not actions:
        actions.append("决策结果存在分化，建议扩大样本并复核规则分层。")
    return actions


# -- Built-in rule functions --
#
# Registered at import time so behaviour matches the previous frozen set
# exactly. `count` is ours; the rest are Python builtins, deliberately exposed
# one by one rather than by handing the sandbox __builtins__.
register_rule_function("sum", sum)
register_rule_function("len", len)
register_rule_function("count", _count)
register_rule_function("any", any)
register_rule_function("all", all)

# Deployment-specific predicates shipped as installable packages.
load_rule_function_plugins()
