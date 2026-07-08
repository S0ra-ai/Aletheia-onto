from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .adapters import get_adapter
from .automation import preflight_operation
from .database import connect
from .ontology import explain_instance
from .semantic_kernel import assess_decision_consistency, assess_instance


OBJECT_HINTS: tuple[tuple[str, str], ...] = (
    ("合同", "contract"),
    ("客户", "customer"),
    ("付款", "payment_plan"),
    ("收款", "payment_plan"),
    ("发票", "invoice"),
    ("设备", "equipment"),
    ("工单", "work_order"),
)
OBJECT_LABELS = {
    "contract": "合同",
    "customer": "客户",
    "payment_plan": "付款计划",
    "invoice": "发票",
    "equipment": "设备",
    "work_order": "工单",
}

INTENT_COMPLIANCE = "compliance_assessment"
INTENT_EXPLAIN = "explain_instance"
INTENT_PREFLIGHT = "operation_preflight"
INTENT_CONSISTENCY = "decision_consistency"
INTENT_UNKNOWN = "unknown"


@dataclass(frozen=True)
class ResolvedTarget:
    ontology_id: int
    data_source_id: int | None
    object_code: str
    instance_id: str | None
    operation_code: str | None = None


def query_natural_language(
    platform_db: Path | str,
    question: str,
    ontology_id: int | None = None,
    data_source_id: int | None = None,
    object_code: str | None = None,
    instance_id: str | None = None,
) -> dict[str, Any]:
    normalized_question = " ".join(question.strip().split())
    if not normalized_question:
        raise ValueError("问题不能为空")

    intent = _detect_intent(normalized_question)
    resolved = _resolve_target(platform_db, normalized_question, ontology_id, data_source_id, object_code, instance_id, intent)

    if intent == INTENT_EXPLAIN:
        if not resolved.instance_id:
            raise ValueError("请在问题中说明要解释的实例，例如：合同 1 是什么？")
        evidence = explain_instance(platform_db, resolved.ontology_id, resolved.object_code, resolved.instance_id)
        answer = _answer_explain(evidence)
    elif intent == INTENT_PREFLIGHT:
        if not resolved.instance_id:
            raise ValueError("请在问题中说明要预检的实例，例如：合同 3 能提交审批吗？")
        if resolved.data_source_id is None:
            raise ValueError("无法定位数据源，不能进行操作预检")
        operation_code = resolved.operation_code or _default_operation_code(normalized_question, resolved.object_code)
        evidence = preflight_operation(
            platform_db,
            resolved.ontology_id,
            resolved.data_source_id,
            operation_code,
            resolved.instance_id,
            resolved.object_code,
        )
        answer = _answer_preflight(evidence)
        resolved = ResolvedTarget(
            resolved.ontology_id,
            resolved.data_source_id,
            resolved.object_code,
            resolved.instance_id,
            operation_code,
        )
    elif intent == INTENT_CONSISTENCY:
        evidence = assess_decision_consistency(platform_db, resolved.ontology_id, resolved.object_code, limit=20)
        answer = _answer_consistency(evidence)
    elif intent == INTENT_COMPLIANCE:
        if not resolved.instance_id:
            evidence = assess_decision_consistency(platform_db, resolved.ontology_id, resolved.object_code, limit=20)
            answer = _answer_overall_compliance(evidence)
        else:
            evidence = assess_instance(platform_db, resolved.ontology_id, resolved.object_code, resolved.instance_id)
            answer = _answer_assessment(evidence)
    else:
        evidence = {"hint": "未识别到明确意图"}
        answer = "我还不能可靠理解这个问题。你可以尝试问：合同 1 是否合规？合同 3 能提交审批吗？合同整体决策是否一致？"

    return {
        "question": normalized_question,
        "intent": intent,
        "answer": answer,
        "confidence": _confidence(intent, resolved),
        "resolved": {
            "ontologyId": resolved.ontology_id,
            "dataSourceId": resolved.data_source_id,
            "objectCode": resolved.object_code,
            "instanceId": resolved.instance_id,
            "operationCode": resolved.operation_code,
        },
        "evidence": evidence,
        "nextActions": _next_actions(intent, evidence),
    }


def _detect_intent(question: str) -> str:
    if re.search(r"(能否|是否可以|可不可以|能不能|可以).*(提交|审批|执行|自动化|调用)", question):
        return INTENT_PREFLIGHT
    if re.search(r"(提交|审批|执行|自动执行|操作预检)", question):
        return INTENT_PREFLIGHT
    if re.search(r"(一致|批量|总体|整体|分布|稳定)", question):
        return INTENT_CONSISTENCY
    if re.search(r"(为什么|解释|详情|是什么|有哪些字段|来源)", question):
        return INTENT_EXPLAIN
    if re.search(r"(合规|违规|风险|研判|审查|审核|通过|阻断|复核)", question):
        return INTENT_COMPLIANCE
    return INTENT_COMPLIANCE if _extract_instance_hint(question) else INTENT_UNKNOWN


def _resolve_target(
    platform_db: Path | str,
    question: str,
    ontology_id: int | None,
    data_source_id: int | None,
    object_code: str | None,
    instance_id: str | None,
    intent: str,
) -> ResolvedTarget:
    resolved_object = object_code or _detect_object_code(question) or "contract"
    resolved_ontology = ontology_id or _latest_ontology_id(platform_db, data_source_id, resolved_object)
    resolved_source = data_source_id or _data_source_for_object(platform_db, resolved_ontology, resolved_object)
    instance_hint = instance_id or _extract_instance_hint(question)
    resolved_instance = _resolve_instance_id(platform_db, resolved_ontology, resolved_object, instance_hint) if instance_hint else None
    operation_code = _default_operation_code(question, resolved_object) if intent == INTENT_PREFLIGHT else None
    return ResolvedTarget(resolved_ontology, resolved_source, resolved_object, resolved_instance, operation_code)


def _detect_object_code(question: str) -> str | None:
    if re.search(r"\b[A-Z]{1,8}-\d{4}-\d{2,8}\b", question, re.IGNORECASE):
        return "contract"
    for keyword, code in OBJECT_HINTS:
        if keyword in question:
            return code
    match = re.search(r"\b([a-zA-Z][a-zA-Z0-9_]{1,64})\b", question)
    return match.group(1) if match else None


def _extract_instance_hint(question: str) -> str | None:
    contract_no = re.search(r"\b([A-Z]{1,8}-\d{4}-\d{2,8})\b", question, re.IGNORECASE)
    if contract_no:
        return contract_no.group(1).upper()
    specific = re.search(r"(?:合同|客户|付款计划|发票|设备|工单)\s*([0-9]+)\b", question)
    if specific:
        return specific.group(1)
    generic = re.search(r"(?:实例|ID|id)\s*[:：]?\s*([0-9]+)\b", question)
    if generic:
        return generic.group(1)
    return None


def _latest_ontology_id(platform_db: Path | str, data_source_id: int | None, object_code: str) -> int:
    with connect(platform_db) as conn:
        if data_source_id is not None:
            row = conn.execute(
                """
                select o.id
                from ontology o
                join business_object bo on bo.ontology_id = o.id
                join source_table st on st.id = bo.source_table_id
                where st.data_source_id = ?
                  and bo.code = ?
                order by o.id desc
                limit 1
                """,
                (data_source_id, object_code),
            ).fetchone()
            if row is not None:
                return int(row["id"])
        row = conn.execute(
            """
            select o.id
            from ontology o
            join business_object bo on bo.ontology_id = o.id
            where bo.code = ?
            order by o.id desc
            limit 1
            """,
            (object_code,),
        ).fetchone()
        if row is not None:
            return int(row["id"])
        row = conn.execute("select id from ontology order by id desc limit 1").fetchone()
        if row is None:
            raise ValueError("尚未生成本体，请先接入数据源并生成本体草案")
        return int(row["id"])


def _data_source_for_object(platform_db: Path | str, ontology_id: int, object_code: str) -> int | None:
    with connect(platform_db) as conn:
        row = conn.execute(
            """
            select st.data_source_id
            from business_object bo
            join source_table st on st.id = bo.source_table_id
            where bo.ontology_id = ?
              and bo.code = ?
            limit 1
            """,
            (ontology_id, object_code),
        ).fetchone()
        return int(row["data_source_id"]) if row is not None else None


def _resolve_instance_id(platform_db: Path | str, ontology_id: int, object_code: str, hint: str | None) -> str | None:
    if hint is None:
        return None
    if hint.isdigit():
        return hint

    with connect(platform_db) as conn:
        target = conn.execute(
            """
            select ds.source_type, ds.connection_uri, st.table_name, st.primary_key
            from business_object bo
            join source_table st on st.id = bo.source_table_id
            join data_source ds on ds.id = st.data_source_id
            where bo.ontology_id = ?
              and bo.code = ?
            limit 1
            """,
            (ontology_id, object_code),
        ).fetchone()
        if target is None:
            return hint
        columns = conn.execute(
            """
            select sc.column_name
            from source_column sc
            join source_table st on st.id = sc.source_table_id
            join business_object bo on bo.source_table_id = st.id
            where bo.ontology_id = ?
              and bo.code = ?
            order by sc.ordinal
            """,
            (ontology_id, object_code),
        ).fetchall()

    candidate_columns = _identifier_columns([row["column_name"] for row in columns])
    adapter = get_adapter(target["source_type"])
    with adapter.runtime(target["connection_uri"]) as runtime:
        for column in candidate_columns:
            row = runtime.fetch_related_one(target["table_name"], column, hint)
            if row is not None:
                primary_key = target["primary_key"] or "id"
                return str(row.get(primary_key))
    return hint


def _identifier_columns(columns: list[str]) -> list[str]:
    preferred = ["contract_no", "code", "no", "number", "serial_no"]
    lowered = {column.lower(): column for column in columns}
    output = [lowered[item] for item in preferred if item in lowered]
    output.extend(column for column in columns if column not in output and re.search(r"(_no|_code|number|编号|编码)$", column, re.IGNORECASE))
    return output


def _default_operation_code(question: str, object_code: str) -> str:
    if "提交" in question or "审批" in question:
        return "submit_contract" if object_code == "contract" else f"submit_{object_code}"
    if "归档" in question:
        return f"archive_{object_code}"
    return f"submit_{object_code}"


def _answer_explain(evidence: dict[str, Any]) -> str:
    object_name = evidence.get("object", {}).get("name") or evidence.get("objectCode", "业务对象")
    instance_id = evidence.get("instanceId", "")
    source = evidence.get("source", {})
    attributes = evidence.get("attributes", [])
    snippets = []
    for item in attributes[:4]:
        snippets.append(f"{item.get('attributeName') or item.get('attributeCode')}={item.get('value')}")
    suffix = f"主要属性：{'，'.join(snippets)}。" if snippets else ""
    return f"{object_name} {instance_id} 已映射到传统表 {source.get('table')}，可由本体内核解释和追踪来源。{suffix}"


def _answer_assessment(evidence: dict[str, Any]) -> str:
    decision = evidence["decision"]["status"]
    recommendation = evidence["decision"]["recommendation"]
    object_code = _object_label(evidence["semanticKernel"]["objectCode"])
    instance_id = evidence["semanticKernel"]["instanceId"]
    failed = [rule for rule in evidence.get("ruleResults", []) if not rule.get("passed")]
    if not failed:
        return f"{object_code} {instance_id} 当前研判为 {decision}，未发现未通过的发布规则，可视为合规。{recommendation}"
    rule_text = "；".join(f"{rule['ruleName']}：{rule['explanation']}" for rule in failed[:3])
    return f"{object_code} {instance_id} 当前研判为 {decision}，不建议直接视为合规。触发问题：{rule_text}。{recommendation}"


def _answer_preflight(evidence: dict[str, Any]) -> str:
    operation = evidence["operation"]["operationCode"]
    instance_id = evidence["target"]["instanceId"]
    if evidence["allowed"]:
        return f"{operation} 对实例 {instance_id} 的语义预检已放行，可以进入自动化执行。"
    failed = [rule for rule in evidence.get("ruleResults", []) if not rule.get("passed")]
    rule_text = "；".join(f"{rule['ruleName']}：{rule['explanation']}" for rule in failed[:3])
    return f"{operation} 对实例 {instance_id} 未通过语义预检，不建议自动执行。原因：{rule_text}。下一步：{evidence['nextAction']}。"


def _answer_consistency(evidence: dict[str, Any]) -> str:
    summary = evidence["summary"]
    return (
        f"{_object_label(evidence['objectCode'])} 的批量决策一致性为 {evidence['status']}。"
        f"已评估 {evidence['assessed']} 条：通过 {summary['approved']}、复核 {summary['review']}、阻断 {summary['blocked']}、错误 {summary['errors']}。"
    )


def _answer_overall_compliance(evidence: dict[str, Any]) -> str:
    summary = evidence["summary"]
    if summary["blocked"] == 0 and summary["review"] == 0 and summary["errors"] == 0:
        verdict = "整体可视为合规"
    elif summary["blocked"] > 0:
        verdict = "存在阻断性不合规风险"
    else:
        verdict = "存在需要复核的合规风险"
    return (
        f"{_object_label(evidence['objectCode'])} 当前{verdict}。"
        f"已评估 {evidence['assessed']} 条：通过 {summary['approved']}、复核 {summary['review']}、阻断 {summary['blocked']}、错误 {summary['errors']}。"
        "如需单份合同结论，请指定合同ID或合同编号。"
    )


def _next_actions(intent: str, evidence: dict[str, Any]) -> list[str]:
    if intent == INTENT_PREFLIGHT:
        return [evidence.get("nextAction", "review_result")]
    if intent == INTENT_CONSISTENCY:
        return list(evidence.get("nextActions", []))
    if intent == INTENT_COMPLIANCE:
        decision = evidence.get("decision", {})
        return [decision.get("recommendation", "查看规则研判详情")]
    return ["补充业务对象、实例或操作意图"]


def _confidence(intent: str, resolved: ResolvedTarget) -> float:
    if intent == INTENT_UNKNOWN:
        return 0.2
    score = 0.62
    if resolved.object_code:
        score += 0.12
    if resolved.instance_id:
        score += 0.14
    if resolved.ontology_id:
        score += 0.08
    return min(score, 0.96)


def _object_label(object_code: str) -> str:
    return OBJECT_LABELS.get(object_code, object_code)
