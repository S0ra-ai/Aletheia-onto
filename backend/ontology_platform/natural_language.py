from __future__ import annotations

import re
import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .adapters import get_adapter
from .automation import preflight_operation
from .database import connect
from .knowledge_base import build_reasoning_chain
from .model_client import OpenRouterClient, OpenRouterConfig
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
INTENT_KNOWLEDGE_OVERVIEW = "knowledge_overview"


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
    history: list[dict[str, str]] | None = None,
    use_model: bool = True,
) -> dict[str, Any]:
    normalized_question = " ".join(question.strip().split())
    if not normalized_question:
        raise ValueError("问题不能为空")

    model_client = OpenRouterClient(OpenRouterConfig.from_db_or_env(platform_db))
    model_interpretation = _interpret_with_model(platform_db, _client_with_timeout(model_client, 12), normalized_question, history or []) if use_model else {}
    intent = str(model_interpretation.get("intent") or _detect_intent(normalized_question))
    resolved = _resolve_target(
        platform_db,
        normalized_question,
        int(ontology_id or model_interpretation.get("ontologyId")) if (ontology_id or model_interpretation.get("ontologyId")) else None,
        int(data_source_id or model_interpretation.get("dataSourceId")) if (data_source_id or model_interpretation.get("dataSourceId")) else None,
        str(object_code or model_interpretation.get("objectCode")) if (object_code or model_interpretation.get("objectCode")) else None,
        str(instance_id or model_interpretation.get("instanceId")) if (instance_id or model_interpretation.get("instanceId")) else None,
        intent,
    )

    if intent == INTENT_KNOWLEDGE_OVERVIEW:
        if resolved.data_source_id is None:
            raise ValueError("请选择已初始化的数据源")
        chain = build_reasoning_chain(platform_db, resolved.data_source_id)
        object_rules = [rule for rule in chain.get("rules", []) if rule["scopeObjectCode"] == resolved.object_code]
        related = [relation for relation in chain.get("relations", []) if resolved.object_code in {relation["sourceObject"], relation["targetObject"]}]
        evidence = {"objectCode": resolved.object_code, "rules": object_rules, "relations": related, "reasoningSteps": chain.get("steps", [])}
        answer = _answer_knowledge_overview(resolved.object_code, object_rules, related)
    elif intent == INTENT_EXPLAIN:
        if not resolved.instance_id:
            raise ValueError("请在问题中说明要解释的实例，例如：合同 1 是什么？")
        evidence = explain_instance(platform_db, resolved.ontology_id, resolved.object_code, resolved.instance_id)
        answer = _answer_explain(evidence)
    elif intent == INTENT_PREFLIGHT:
        if not resolved.instance_id:
            raise ValueError("请在问题中说明要预检的实例，例如：合同 3 能提交审批吗？")
        if resolved.data_source_id is None:
            raise ValueError("无法定位数据源，不能进行操作预检")
        operation_code = str(model_interpretation.get("operationCode") or resolved.operation_code or _default_operation_code(normalized_question, resolved.object_code))
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

    used_model_summary = False
    if use_model and model_client.configured and evidence:
        summarized = _summarize_with_model(_client_with_timeout(model_client, 12), normalized_question, answer, intent, resolved, evidence, history or [])
        if summarized:
            answer = summarized
            used_model_summary = True

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
        "model": {
            "configured": model_client.configured,
            "usedForUnderstanding": bool(model_interpretation.get("_usedModel")),
            "usedForSummary": used_model_summary,
            "name": model_client.config.model,
            "fallbackReason": model_interpretation.get("_fallbackReason", ""),
        },
    }


def _interpret_with_model(
    platform_db: Path | str,
    client: OpenRouterClient,
    question: str,
    history: list[dict[str, str]],
) -> dict[str, Any]:
    if not client.configured:
        return {"_usedModel": False, "_fallbackReason": "model_not_configured"}
    context = _semantic_context(platform_db)
    messages = [
        {
            "role": "system",
            "content": (
                "你是本体改造研发平台的自然语言理解器。只输出 JSON 对象，不要输出 Markdown。"
                "你的任务是把用户问题解析为本体语义内核可执行的调用参数。"
                "intent 只能是 compliance_assessment、explain_instance、operation_preflight、decision_consistency、knowledge_overview、unknown。"
                "字段包括 intent, ontologyId, dataSourceId, objectCode, instanceId, operationCode。无法确定则填 null。"
                "注意：你只负责理解问题，不能替代规则引擎做最终合规结论。"
            ),
        },
        {
            "role": "user",
            "content": _compact_json(
                {
                    "availableSemanticContext": context,
                    "recentConversation": history[-8:],
                    "question": question,
                }
            ),
        },
    ]
    try:
        result = client.chat(messages, purpose="natural_language_understanding", session_id="ontology-chat")
        parsed = _extract_json_object(result.content)
        parsed["_usedModel"] = True
        return parsed
    except Exception as error:
        return {"_usedModel": False, "_fallbackReason": str(error)}


def _client_with_timeout(client: OpenRouterClient, timeout_seconds: float) -> OpenRouterClient:
    config = replace(client.config, timeout_seconds=min(client.config.timeout_seconds, timeout_seconds))
    return OpenRouterClient(config, client.transport)


def _summarize_with_model(
    client: OpenRouterClient,
    question: str,
    deterministic_answer: str,
    intent: str,
    resolved: ResolvedTarget,
    evidence: dict[str, Any],
    history: list[dict[str, str]],
) -> str:
    compact_evidence = _compact_evidence(evidence)
    messages = [
        {
            "role": "system",
            "content": (
                "你是企业业务语义内核的解释助手。请基于给定 evidence 生成中文业务回答。"
                "必须忠实于 evidence，不得编造结论；合规、放行、阻断等判断必须以 evidence 中的规则结果为准。"
                "回答应像业务专家在对话：直接回应用户的问题，再用一两个关键事实解释。"
                "不要按顺序朗读推理步骤、规则编号、字段名或内部状态码；除非用户明确要求查看它们。"
                "语气自然、简洁，避免模板化的‘当前研判为’、‘本体内核’等系统术语。不要输出 JSON。"
            ),
        },
        {
            "role": "user",
            "content": _compact_json(
                {
                    "question": question,
                    "intent": intent,
                    "resolved": {
                        "ontologyId": resolved.ontology_id,
                        "dataSourceId": resolved.data_source_id,
                        "objectCode": resolved.object_code,
                        "instanceId": resolved.instance_id,
                        "operationCode": resolved.operation_code,
                    },
                    "deterministicAnswer": deterministic_answer,
                    "evidence": compact_evidence,
                    "recentConversation": history[-6:],
                }
            ),
        },
    ]
    try:
        result = client.chat(messages, purpose="natural_language_summary", session_id="ontology-chat")
        return result.content.strip() or deterministic_answer
    except Exception:
        return ""


def _detect_intent(question: str) -> str:
    if re.search(r"(有哪些|列出|介绍|概览|知识库).*(规则|关系|本体|对象)|(规则|关系|本体|对象).*(有哪些|是什么|概览)", question):
        return INTENT_KNOWLEDGE_OVERVIEW
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


def _semantic_context(platform_db: Path | str) -> dict[str, Any]:
    with connect(platform_db) as conn:
        sources = conn.execute(
            "select id, name, domain, system_category from data_source order by id desc limit 10"
        ).fetchall()
        ontologies = conn.execute(
            "select id, name, domain, version, status from ontology order by id desc limit 10"
        ).fetchall()
        objects = conn.execute(
            """
            select o.id as ontologyId, bo.code, bo.name, st.data_source_id as dataSourceId, st.table_name as sourceTable
            from business_object bo
            join ontology o on o.id = bo.ontology_id
            left join source_table st on st.id = bo.source_table_id
            order by o.id desc, bo.code
            limit 80
            """
        ).fetchall()
        operations = conn.execute(
            """
            select data_source_id as dataSourceId, operation_code as operationCode, name, semantic_action as semanticAction
            from source_api
            order by id desc
            limit 40
            """
        ).fetchall()
        return {
            "dataSources": [dict(row) for row in sources],
            "ontologies": [dict(row) for row in ontologies],
            "objects": [dict(row) for row in objects],
            "operations": [dict(row) for row in operations],
        }


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
    return f"这是{object_name} {instance_id}。{suffix}如果你想继续看它的合规情况，我可以接着帮你检查。"


def _answer_knowledge_overview(object_code: str, rules: list[dict[str, Any]], relations: list[dict[str, Any]]) -> str:
    object_name = _object_label(object_code)
    if not rules and not relations:
        return f"目前还没有为{object_name}配置专门的业务规则或关联关系。"
    parts = []
    if rules:
        descriptions = [
            f"{rule.get('name')}（{rule.get('naturalLanguage')}）" if rule.get("naturalLanguage") else str(rule.get("name"))
            for rule in rules
        ]
        parts.append(f"我会重点检查{'、'.join(descriptions)}")
    if relations:
        names = "、".join(str(item.get("name")) for item in relations[:3])
        parts.append(f"分析时也会结合{names}等关联信息")
    return f"针对{object_name}，{'；'.join(parts)}。你可以给我一个具体编号，我来帮你看实际情况。"


def _friendly_recommendation(recommendation: str) -> str:
    normalized = str(recommendation or "").strip()
    if not normalized or normalized.lower() in {"approve", "approved", "allow", "continue"}:
        return ""
    if normalized.lower() in {"manual_review", "review", "requires_review"}:
        return "建议交由业务人员再复核一次。"
    if normalized.lower() in {"block", "blocked", "reject"}:
        return "建议先暂停后续流程，处理完问题后再提交。"
    return normalized if normalized.endswith("。") else f"{normalized}。"


def _answer_assessment(evidence: dict[str, Any]) -> str:
    decision = evidence["decision"]["status"]
    recommendation = evidence["decision"]["recommendation"]
    object_code = _object_label(evidence["semanticKernel"]["objectCode"])
    instance_id = evidence["semanticKernel"]["instanceId"]
    failed = [rule for rule in evidence.get("ruleResults", []) if not rule.get("passed")]
    if not failed:
        return f"{object_code} {instance_id} 目前没有发现明确的合规问题，可以按正常流程继续。{_friendly_recommendation(recommendation)}"
    rule_text = "；".join(f"{rule['ruleName']}：{rule['explanation']}" for rule in failed[:3])
    return f"{object_code} {instance_id} 还不适合直接通过。主要是{rule_text}。{_friendly_recommendation(recommendation)}"


def _answer_preflight(evidence: dict[str, Any]) -> str:
    operation = evidence["operation"]["operationCode"]
    instance_id = evidence["target"]["instanceId"]
    if evidence["allowed"]:
        return f"实例 {instance_id} 已经具备操作条件，可以继续执行。"
    failed = [rule for rule in evidence.get("ruleResults", []) if not rule.get("passed")]
    rule_text = "；".join(f"{rule['ruleName']}：{rule['explanation']}" for rule in failed[:3])
    return f"实例 {instance_id} 现在还不宜执行这项操作，不建议自动执行。需要先处理：{rule_text}。"


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


def _extract_json_object(content: str) -> dict[str, Any]:
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start < 0 or end < start:
        raise ValueError("模型未返回 JSON 对象")
    parsed = json.loads(stripped[start : end + 1])
    return parsed if isinstance(parsed, dict) else {}


def _compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _compact_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
    if "ruleResults" in evidence:
        failed = [rule for rule in evidence.get("ruleResults", []) if not rule.get("passed")]
        return {
            "decision": evidence.get("decision"),
            "allowed": evidence.get("allowed"),
            "nextAction": evidence.get("nextAction"),
            "target": evidence.get("target") or evidence.get("semanticKernel"),
            "failedRules": failed[:8],
            "ruleCount": len(evidence.get("ruleResults", [])),
        }
    if "items" in evidence:
        return {
            "objectCode": evidence.get("objectCode"),
            "status": evidence.get("status"),
            "summary": evidence.get("summary"),
            "ruleFailures": evidence.get("ruleFailures", [])[:10],
            "sampleItems": evidence.get("items", [])[:5],
            "nextActions": evidence.get("nextActions", []),
        }
    if "attributes" in evidence:
        return {
            "object": evidence.get("object"),
            "source": evidence.get("source"),
            "attributes": evidence.get("attributes", [])[:20],
            "explanation": evidence.get("explanation"),
        }
    return evidence
