from __future__ import annotations

import ast
import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .adapters import RuntimeDatabase, get_adapter
from .database import connect
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


def assess_instance(platform_db: Path | str, ontology_id: int, object_code: str, instance_id: str) -> dict[str, Any]:
    with connect(platform_db) as platform:
        runtime = build_runtime(platform, ontology_id, object_code, instance_id)
        rules = platform.execute(
            """
            select *
            from business_rule
            where ontology_id = ?
              and scope_object_code = ?
              and status = 'published'
            order by severity, code
            """,
            (ontology_id, object_code),
        ).fetchall()

        results = []
        for rule in rules:
            passed, error = _evaluate_rule(rule["expression"], runtime.context)
            explanation = _build_explanation(rule, passed, error)
            evidence = {
                "record": runtime.record,
                "related": _serializable_related(runtime.related),
                "expression": rule["expression"],
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
                    1 if passed else 0,
                    explanation,
                    json.dumps(evidence, ensure_ascii=False),
                ),
            )
            inference_id = int(platform.execute("select last_insert_rowid()").fetchone()[0])
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
                    json.dumps(_mapping_refs(platform, ontology_id, runtime.source_table), ensure_ascii=False),
                    json.dumps({"table": runtime.source_table, "primaryKey": runtime.primary_key, "instanceId": instance_id}, ensure_ascii=False),
                    json.dumps({"ruleId": rule["id"], "ruleCode": rule["code"]}, ensure_ascii=False),
                ),
            )
            results.append(
                {
                    "ruleCode": rule["code"],
                    "ruleName": rule["name"],
                    "ruleType": rule["rule_type"],
                    "severity": rule["severity"],
                    "passed": passed,
                    "explanation": explanation,
                    "naturalLanguage": rule["natural_language"],
                }
            )

        failed = [result for result in results if not result["passed"]]
        decision = _decision_from_results(failed)
        platform.execute(
            "insert into audit_log (actor, action, target_type, target_id, detail) values (?, ?, ?, ?, ?)",
            (
                "semantic_kernel",
                "assess_instance",
                object_code,
                instance_id,
                json.dumps({"ontologyId": ontology_id, "decision": decision["status"], "failedRules": len(failed)}, ensure_ascii=False),
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
            if not isinstance(node.func, ast.Name) or node.func.id not in {"sum", "len", "count", "any", "all"}:
                raise ValueError("只允许 sum、len、count、any、all 函数")


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
        return f"规则执行失败：{rule['name']}。错误：{error}"
    prefix = "通过" if passed else "未通过"
    return f"{prefix}：{rule['natural_language']}"


def _decision_from_results(failed: list[dict[str, Any]]) -> dict[str, Any]:
    if any(result["severity"] == "blocking" for result in failed):
        return {
            "status": "blocked",
            "recommendation": "存在阻断级规则未通过，应暂停自动化操作并要求业务人员复核。",
        }
    if failed:
        return {
            "status": "review",
            "recommendation": "存在风险或警告，应进入人工复核或触发后续治理流程。",
        }
    return {
        "status": "approved",
        "recommendation": "未发现阻断或风险规则，允许进入后续自动化流程。",
    }
