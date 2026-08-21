from __future__ import annotations

import ast
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from .adapters import RuntimeDatabase, get_adapter
from .config import clamp_page_size, clamp_sample_size
from .database import connect, last_insert_id
from .decisions import record_decision_in_connection
from .ontology import explain_instance


class RowObject:
    def __init__(self, values: dict[str, Any]):
        self._values = values

    def __getattr__(self, name: str) -> Any:
        return self._values.get(name)

    def as_dict(self) -> dict[str, Any]:
        return dict(self._values)


class RelatedValues(list[Any]):
    def __eq__(self, other: object) -> list[bool]:  # type: ignore[override]
        return [value == other for value in self]

    def __ne__(self, other: object) -> list[bool]:  # type: ignore[override]
        return [value != other for value in self]

    def __lt__(self, other: object) -> list[bool]:
        return [_safe_compare(value, other, "lt") for value in self]

    def __le__(self, other: object) -> list[bool]:
        return [_safe_compare(value, other, "le") for value in self]

    def __gt__(self, other: object) -> list[bool]:
        return [_safe_compare(value, other, "gt") for value in self]

    def __ge__(self, other: object) -> list[bool]:
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

ALLOWED_RULE_FUNCTIONS = frozenset({"sum", "len", "count", "any", "all"})

# Attribute access is needed to reach related rows (payment_plan.amount), but
# dunder attributes are the entry point for sandbox escapes via __class__,
# __globals__ and friends.
FORBIDDEN_ATTRIBUTE_PREFIXES = ("__",)


def assess_instance(platform_db: Path | str, ontology_id: int, object_code: str, instance_id: str) -> dict[str, Any]:
    with connect(platform_db) as platform:
        runtime = build_runtime(platform, ontology_id, object_code, instance_id)
        today = date.today().isoformat()
        rules = platform.execute(
            """
            select *
            from business_rule
            where ontology_id = ?
              and scope_object_code = ?
              and status = 'published'
              and (effective_start is null or effective_start <= ?)
              and (effective_end is null or effective_end >= ?)
            order by priority desc, severity, code
            """,
            (ontology_id, object_code, today, today),
        ).fetchall()

        results = []
        for rule in rules:
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
                    _json_dumps({"table": runtime.source_table, "primaryKey": runtime.primary_key, "instanceId": instance_id}),
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
                }
            )

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
            evidence={"failedRules": [item["ruleCode"] for item in failed], "ontologyVersion": runtime.ontology_version},
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
                _json_dumps({"ontologyId": ontology_id, "decision": decision["status"], "decisionId": decision["decisionId"], "failedRules": len(failed)}),
            ),
        )
        explanation = explain_instance(platform_db, ontology_id, object_code, instance_id)
        return {
            "semanticKernel": {
                "ontologyId": ontology_id,
                "ontologyVersion": runtime.ontology_version,
                "objectCode": object_code,
                "instanceId": instance_id,
            },
            "explanation": explanation,
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
            return database.fetch_primary_keys(runtime["table_name"], runtime["primary_key"], resolved_limit)


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


def build_runtime(platform: sqlite3.Connection, ontology_id: int, object_code: str, instance_id: str) -> SemanticRuntime:
    ontology = platform.execute("select * from ontology where id = ?", (ontology_id,)).fetchone()
    if ontology is None:
        raise ValueError(f"本体不存在: {ontology_id}")
    business_object = platform.execute(
        "select * from business_object where ontology_id = ? and code = ?",
        (ontology_id, object_code),
    ).fetchone()
    if business_object is None:
        raise ValueError(f"业务对象不存在: {object_code}")
    source_table = platform.execute("select * from source_table where id = ?", (business_object["source_table_id"],)).fetchone()
    if source_table is None:
        raise ValueError(f"业务对象未绑定来源表: {object_code}")
    data_source = platform.execute(
        "select ds.* from data_source ds join source_table st on st.data_source_id = ds.id where st.id = ?",
        (source_table["id"],),
    ).fetchone()
    primary_key = source_table["primary_key"] or "id"
    if "," in primary_key:
        raise ValueError("当前原型不支持复合主键实例研判")

    adapter = get_adapter(data_source["source_type"])
    with adapter.runtime(data_source["connection_uri"]) as runtime:
        record = runtime.fetch_one(source_table["table_name"], primary_key, instance_id)
        if record is None:
            raise ValueError(f"实例不存在: {object_code}/{instance_id}")
        context: dict[str, Any] = dict(record)
        related = _load_related_context(platform, runtime, data_source["id"], source_table, primary_key, record)
        context.update(related)

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
    )


def _load_related_context(
    platform: sqlite3.Connection,
    runtime: RuntimeDatabase,
    data_source_id: int,
    source_table: sqlite3.Row,
    primary_key: str,
    record: dict[str, Any],
) -> dict[str, Any]:
    related: dict[str, Any] = {}
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
            related[foreign_key["target_table"]] = RowObject(row)

    reverse_foreign_keys = platform.execute(
        """
        select fk.*, st.table_name as child_table
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
        related[foreign_key["child_table"]] = RelatedRows(rows)

    return related


def _evaluate_rule(expression: str, context: dict[str, Any]) -> tuple[bool, str | None]:
    normalized = _normalize_expression(expression)
    try:
        tree = ast.parse(normalized, mode="eval")
        _validate_ast(tree)
        value = eval(compile(tree, "<business-rule>", "eval"), {"__builtins__": {}}, _allowed_names(context))
        return bool(value), None
    except Exception as error:
        return False, str(error)


def _normalize_expression(expression: str) -> str:
    normalized = re.sub(r"\bnull\b", "None", expression)
    normalized = normalized.replace(" is not None", " != None").replace(" is None", " == None")
    return normalized


def _validate_ast(tree: ast.AST) -> None:
    for node in ast.walk(tree):
        if not isinstance(node, ALLOWED_AST_NODES):
            raise ValueError(f"不允许的规则表达式节点: {type(node).__name__}")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in ALLOWED_RULE_FUNCTIONS:
                raise ValueError(f"只允许 {'、'.join(sorted(ALLOWED_RULE_FUNCTIONS))} 函数")
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
            if isinstance(node, ast.Name) and node.id not in ALLOWED_RULE_FUNCTIONS and node.id != "None"
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
    names.update({"sum": sum, "len": len, "count": _count, "any": any, "all": all, "None": None})
    return names


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
                    "部分规则无法在当前数据结构上求值，已按未通过处理，"
                    "应人工复核规则表达式与来源字段后再恢复自动化。"
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
    source_table = platform.execute("select * from source_table where id = ?", (business_object["source_table_id"],)).fetchone()
    if source_table is None:
        raise ValueError(f"业务对象未绑定来源表: {object_code}")
    primary_key = source_table["primary_key"] or "id"
    if "," in primary_key:
        raise ValueError("当前原型不支持复合主键批量一致性评估")
    data_source = platform.execute(
        "select ds.* from data_source ds join source_table st on st.data_source_id = ds.id where st.id = ?",
        (source_table["id"],),
    ).fetchone()
    return {
        "source_type": data_source["source_type"],
        "connection_uri": data_source["connection_uri"],
        "table_name": source_table["table_name"],
        "primary_key": primary_key,
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
