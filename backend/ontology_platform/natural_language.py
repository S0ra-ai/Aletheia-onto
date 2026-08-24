from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, replace
from typing import Any, Iterable

from .adapters import get_adapter
from .automation import preflight_operation
from .config import RESOLUTION_CONFIDENCE
from .context import PlatformDb
from .database import connect
from .knowledge_base import build_reasoning_chain
from .knowledge_documents import load_confirmed_entries
from .model_client import OpenRouterClient, OpenRouterConfig
from .ontology import explain_instance
from .retrieval import filter_entries_for_role, retrieve
from .semantic_kernel import assess_decision_consistency, assess_instance
from .vocabulary import DomainVocabulary, load_vocabulary

logger = logging.getLogger(__name__)

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


def _first_int(*candidates: Any) -> int | None:
    """First candidate that is present, coerced to int.

    The caller's explicit argument wins over the model's interpretation, and an
    absent value stays None rather than becoming 0.
    """
    for candidate in candidates:
        if candidate:
            return int(candidate)
    return None


def _first_str(*candidates: Any) -> str | None:
    """First candidate that is present, coerced to str."""
    for candidate in candidates:
        if candidate:
            return str(candidate)
    return None


def query_natural_language(
    platform_db: PlatformDb,
    question: str,
    ontology_id: int | None = None,
    data_source_id: int | None = None,
    object_code: str | None = None,
    instance_id: str | None = None,
    history: list[dict[str, str]] | None = None,
    use_model: bool = True,
    role_code: str = "",
) -> dict[str, Any]:
    normalized_question = " ".join(question.strip().split())
    if not normalized_question:
        raise ValueError("问题不能为空")

    model_client = OpenRouterClient(OpenRouterConfig.from_db_or_env(platform_db))
    model_interpretation = (
        _interpret_with_model(platform_db, _client_with_timeout(model_client, 12), normalized_question, history or [])
        if use_model
        else {}
    )
    intent = str(model_interpretation.get("intent") or detect_intent(normalized_question))
    resolved = _resolve_target(
        platform_db,
        normalized_question,
        _first_int(ontology_id, model_interpretation.get("ontologyId")),
        _first_int(data_source_id, model_interpretation.get("dataSourceId")),
        _first_str(object_code, model_interpretation.get("objectCode")),
        _first_str(instance_id, model_interpretation.get("instanceId")),
        intent,
    )

    vocabulary = load_vocabulary(platform_db, resolved.ontology_id, resolved.data_source_id)
    example = _question_examples(vocabulary)

    if intent == INTENT_KNOWLEDGE_OVERVIEW:
        if resolved.data_source_id is None:
            raise ValueError("请选择已初始化的数据源")
        chain = build_reasoning_chain(platform_db, resolved.data_source_id)
        object_rules = [rule for rule in chain.get("rules", []) if rule["scopeObjectCode"] == resolved.object_code]
        related = [
            relation
            for relation in chain.get("relations", [])
            if resolved.object_code in {relation["sourceObject"], relation["targetObject"]}
        ]
        evidence = {
            "objectCode": resolved.object_code,
            "rules": object_rules,
            "relations": related,
            "reasoningSteps": chain.get("steps", []),
        }
        answer = _answer_knowledge_overview(resolved.object_code, object_rules, related, vocabulary)
    elif intent == INTENT_EXPLAIN:
        if not resolved.instance_id:
            raise ValueError(f"请在问题中说明要解释的实例，例如：{example['explain']}")
        evidence = explain_instance(platform_db, resolved.ontology_id, resolved.object_code, resolved.instance_id)
        answer = _answer_explain(evidence, vocabulary)
    elif intent == INTENT_PREFLIGHT:
        if not resolved.instance_id:
            raise ValueError(f"请在问题中说明要预检的实例，例如：{example['preflight']}")
        if resolved.data_source_id is None:
            raise ValueError("无法定位数据源，不能进行操作预检")
        operation_code = str(
            model_interpretation.get("operationCode")
            or resolved.operation_code
            or _default_operation_code(platform_db, normalized_question, resolved.object_code, resolved.data_source_id)
            or ""
        )
        if not operation_code:
            raise ValueError("该数据源尚未登记任何业务操作，无法进行操作预检")
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
        answer = _answer_consistency(evidence, vocabulary)
    elif intent == INTENT_COMPLIANCE:
        if not resolved.instance_id:
            evidence = assess_decision_consistency(platform_db, resolved.ontology_id, resolved.object_code, limit=20)
            answer = _answer_overall_compliance(evidence, vocabulary)
        else:
            evidence = assess_instance(platform_db, resolved.ontology_id, resolved.object_code, resolved.instance_id)
            # Retrieve textual grounding for the rules that actually failed, so a
            # verdict can cite the clause behind it (ADR-0009). Anchored to those
            # rule codes, not to the raw question.
            citations = _retrieve_citations(
                platform_db,
                resolved.ontology_id,
                normalized_question,
                object_code=resolved.object_code,
                rule_codes=[
                    rule.get("ruleCode", "") for rule in evidence.get("ruleResults", []) if not rule.get("passed")
                ],
                role_code=role_code,
            )
            answer = _answer_assessment(evidence, vocabulary, citations)
            if citations:
                evidence = {**evidence, "citations": citations}
    else:
        evidence = {"hint": "未识别到明确意图"}
        answer = (
            "我还不能可靠理解这个问题。你可以尝试问："
            f"{example['compliance']}？{example['preflight']}？{example['consistency']}？"
        )

    used_model_summary = False
    if use_model and model_client.configured and evidence:
        summarized = _summarize_with_model(
            _client_with_timeout(model_client, 12),
            normalized_question,
            answer,
            intent,
            resolved,
            evidence,
            history or [],
        )
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
    platform_db: PlatformDb,
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
            "content": compact_json(
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
    trimmed_evidence = compact_evidence(evidence)
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
            "content": compact_json(
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
                    "evidence": trimmed_evidence,
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


def detect_intent(question: str) -> str:
    """Classify a question into one of the routing intents.

    Public because `agent` routes on it. It used to be private and imported across the
    module boundary anyway, which is the worst of both: a name we never promised to
    keep, that something already depended on.
    """
    if re.search(
        r"(有哪些|列出|介绍|概览|知识库).*(规则|关系|本体|对象)|(规则|关系|本体|对象).*(有哪些|是什么|概览)", question
    ):
        return INTENT_KNOWLEDGE_OVERVIEW
    if re.search(r"(能否|是否可以|可不可以|能不能|可以).*(提交|审批|执行|自动化|调用)", question):
        return INTENT_PREFLIGHT
    if re.search(r"(提交|审批|执行|自动执行|操作预检)", question):
        return INTENT_PREFLIGHT
    if re.search(r"(一致|批量|总体|整体|分布|稳定)", question):
        return INTENT_CONSISTENCY
    if re.search(r"(为什么|解释|详情|是什么|有哪些字段|来源)", question):
        return INTENT_EXPLAIN
    # "是否满足…条件" is the natural way to ask a judgement question -- it is the
    # exact phrasing in the product's own refund example -- and was previously
    # unrecognised, falling through to "unknown".
    if re.search(r"(满足|符合|达到).{0,6}(条件|要求|标准|门槛)", question):
        return INTENT_COMPLIANCE
    if re.search(r"(合规|违规|风险|研判|审查|审核|通过|阻断|复核|资格)", question):
        return INTENT_COMPLIANCE
    return INTENT_COMPLIANCE if _extract_instance_hint(question) else INTENT_UNKNOWN


def _semantic_context(platform_db: PlatformDb) -> dict[str, Any]:
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
    platform_db: PlatformDb,
    question: str,
    ontology_id: int | None,
    data_source_id: int | None,
    object_code: str | None,
    instance_id: str | None,
    intent: str,
) -> ResolvedTarget:
    # The vocabulary is derived from what is actually modelled, so object
    # detection works for any industry rather than a built-in list.
    vocabulary = load_vocabulary(platform_db, ontology_id, data_source_id)
    resolved_object = object_code or _detect_object_code(question, vocabulary)
    instance_hint = instance_id or _extract_instance_hint(question, vocabulary)
    if not resolved_object and instance_hint and not str(instance_hint).isdigit():
        # A bare business code such as MZ-2026-001 identifies its own object:
        # find which modelled object has a matching identifier column value.
        resolved_object = _object_for_business_code(platform_db, vocabulary, str(instance_hint))
    if not resolved_object:
        default_term = vocabulary.default_object()
        if default_term is None:
            raise ValueError("尚未建模任何业务对象，请先接入数据源并生成本体草案")
        resolved_object = default_term.code
    resolved_ontology = ontology_id or _latest_ontology_id(platform_db, data_source_id, resolved_object)
    resolved_source = data_source_id or _data_source_for_object(platform_db, resolved_ontology, resolved_object)
    resolved_instance = (
        _resolve_instance_id(platform_db, resolved_ontology, resolved_object, instance_hint) if instance_hint else None
    )
    operation_code = (
        _default_operation_code(platform_db, question, resolved_object, resolved_source)
        if intent == INTENT_PREFLIGHT
        else None
    )
    return ResolvedTarget(resolved_ontology, resolved_source, resolved_object, resolved_instance, operation_code)


def _object_for_business_code(
    platform_db: PlatformDb,
    vocabulary: DomainVocabulary,
    business_code: str,
) -> str | None:
    """Find the business object whose identifier column holds this code.

    Lets a user paste a document number without naming the object, without the
    platform assuming which object business codes belong to.
    """
    for term in vocabulary.objects:
        if not term.source_table or term.data_source_id is None:
            continue
        with connect(platform_db) as conn:
            source = conn.execute(
                "select source_type, connection_uri from data_source where id = ?",
                (term.data_source_id,),
            ).fetchone()
            columns = [
                row["column_name"]
                for row in conn.execute(
                    """
                    select sc.column_name
                    from source_column sc
                    join source_table st on st.id = sc.source_table_id
                    where st.data_source_id = ? and st.table_name = ?
                    order by sc.ordinal
                    """,
                    (term.data_source_id, term.source_table),
                ).fetchall()
            ]
        if source is None:
            continue
        candidates = _identifier_columns(columns)
        if not candidates:
            continue
        try:
            adapter = get_adapter(source["source_type"])
            with adapter.runtime(source["connection_uri"]) as runtime:
                for column in candidates:
                    if runtime.fetch_related_one(term.source_table, column, business_code) is not None:
                        return term.code
        except Exception:
            # An unreachable source must not break question routing.
            continue
    return None


def _detect_object_code(question: str, vocabulary: DomainVocabulary) -> str | None:
    """Resolve the referenced object against the modelled vocabulary."""
    term = vocabulary.detect(question)
    if term is not None:
        return term.code
    # A bare identifier may name an object that is not modelled yet; only accept
    # it when it actually matches a known code.
    known = set(vocabulary.codes())
    for candidate in re.findall(r"\b([a-zA-Z][a-zA-Z0-9_]{1,64})\b", question):
        if candidate in known:
            return candidate
    return None


# A business document number: uppercase prefix, digits, separated by - or /.
# Structural rather than domain specific, so it matches order, ticket and asset
# numbers just as well as contract numbers.
BUSINESS_CODE_PATTERN = re.compile(r"\b([A-Z][A-Z0-9]{0,9}[-/]\d{2,8}(?:[-/]\d{1,8})*)\b", re.IGNORECASE)


def _extract_instance_hint(question: str, vocabulary: DomainVocabulary | None = None) -> str | None:
    """Pull an instance identifier out of the question.

    Business codes are matched by shape. Numeric ids are accepted after any
    modelled object label, so the recognised prefixes grow with the ontology
    instead of being fixed in code. The vocabulary is optional so early intent
    detection, which runs before a target is resolved, can still use it.
    """
    business_code = BUSINESS_CODE_PATTERN.search(question)
    if business_code:
        return business_code.group(1).upper()

    if vocabulary is not None:
        labels = [term.name for term in vocabulary.objects if term.name]
        labels.extend(term.code for term in vocabulary.objects if term.code)
        for label in sorted(labels, key=len, reverse=True):
            match = re.search(rf"{re.escape(label)}\s*#?([0-9]+)\b", question, re.IGNORECASE)
            if match:
                return match.group(1)

    generic = re.search(r"(?:实例|编号|ID|id)\s*[:：#]?\s*([0-9]+)\b", question)
    if generic:
        return generic.group(1)
    return None


def _latest_ontology_id(platform_db: PlatformDb, data_source_id: int | None, object_code: str) -> int:
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


def _data_source_for_object(platform_db: PlatformDb, ontology_id: int, object_code: str) -> int | None:
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


def _resolve_instance_id(platform_db: PlatformDb, ontology_id: int, object_code: str, hint: str | None) -> str | None:
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


# Column names that carry a human facing business identifier. The patterns are
# naming conventions, not industry terms, so `contract_no`, `visit_no`,
# `order_code` and `asset_number` are all recognised.
IDENTIFIER_COLUMN_PATTERN = re.compile(
    r"(^|_)(no|code|number|serial|ref|key)$|(_no|_code|_number|_serial|_ref)$|(编号|编码|单号)$",
    re.IGNORECASE,
)


def _identifier_columns(columns: list[str]) -> list[str]:
    """Columns likely to hold a business identifier, most specific first."""
    exact = [column for column in columns if column.lower() in {"code", "no", "number", "serial_no"}]
    suffixed = [column for column in columns if column not in exact and IDENTIFIER_COLUMN_PATTERN.search(column)]
    return exact + suffixed


# Intent keywords map to the semantic action verbs used when registering a
# business API. They describe how users phrase requests, not any one industry.
ACTION_KEYWORDS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("提交", "送审", "报批"), ("submit", "apply", "request")),
    (("审批", "批准", "通过"), ("approve", "confirm", "review")),
    (("归档", "关闭", "结束"), ("archive", "close", "finish", "complete")),
    (("取消", "作废", "撤销"), ("cancel", "void", "revoke")),
)


def _default_operation_code(
    platform_db: PlatformDb,
    question: str,
    object_code: str,
    data_source_id: int | None,
) -> str | None:
    """Pick the registered operation that best matches the question.

    Operations are resolved from `source_api` rather than assembled from string
    templates, so a legacy system whose endpoint is `contract_submit_v2` or
    `createWorkOrder` still resolves.
    """
    if data_source_id is None:
        return None
    with connect(platform_db) as conn:
        rows = conn.execute(
            """
            select operation_code, semantic_action, name
            from source_api
            where data_source_id = ?
            order by operation_code
            """,
            (data_source_id,),
        ).fetchall()
    if not rows:
        return None

    candidates = [dict(row) for row in rows]
    # Prefer operations bound to this object through their semantic action.
    scoped = [
        item
        for item in candidates
        if item["semantic_action"].startswith(f"{object_code}.") or object_code in item["operation_code"]
    ] or candidates

    wanted_verbs: tuple[str, ...] = ()
    for phrases, verbs in ACTION_KEYWORDS:
        if any(phrase in question for phrase in phrases):
            wanted_verbs = verbs
            break

    if wanted_verbs:
        for item in scoped:
            haystack = f"{item['operation_code']} {item['semantic_action']}".lower()
            if any(verb in haystack for verb in wanted_verbs):
                return item["operation_code"]

    return scoped[0]["operation_code"]


def _answer_explain(evidence: dict[str, Any], vocabulary: DomainVocabulary) -> str:
    object_name = (
        evidence.get("object", {}).get("name")
        or vocabulary.label_for(str(evidence.get("objectCode", "")))
        or "业务对象"
    )
    instance_id = evidence.get("instanceId", "")
    attributes = evidence.get("attributes", [])
    snippets = []
    for item in attributes[:4]:
        snippets.append(f"{item.get('attributeName') or item.get('attributeCode')}={item.get('value')}")
    suffix = f"主要属性：{'，'.join(snippets)}。" if snippets else ""
    return f"这是{object_name} {instance_id}。{suffix}如果你想继续看它的合规情况，我可以接着帮你检查。"


def _answer_knowledge_overview(
    object_code: str,
    rules: list[dict[str, Any]],
    relations: list[dict[str, Any]],
    vocabulary: DomainVocabulary,
) -> str:
    object_name = vocabulary.label_for(object_code)
    if not rules and not relations:
        return f"目前还没有为{object_name}配置专门的业务规则或关联关系。"
    parts = []
    if rules:
        descriptions = [
            f"{rule.get('name')}（{rule.get('naturalLanguage')}）"
            if rule.get("naturalLanguage")
            else str(rule.get("name"))
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


def _retrieve_citations(
    platform_db: PlatformDb,
    ontology_id: int,
    question: str,
    *,
    object_code: str = "",
    rule_codes: Iterable[str] = (),
    limit: int = 3,
    role_code: str = "",
) -> list[dict[str, Any]]:
    """Find confirmed knowledge entries backing the rules under discussion.

    Anchoring comes first: candidates are narrowed to entries declared for this
    object or these rules, and only then ranked. That ordering is what makes a
    citation attributable rather than merely similar (ADR-0009).

    Permission filtering comes between the two. Anchoring makes a citation
    *attributable*; it does not make it *permitted*. An entry anchored to an object the
    caller cannot read is still an object they cannot read, and putting its text in an
    answer discloses exactly what the object permission was protecting.

    Failures are swallowed deliberately -- the knowledge tables are optional, and
    a deployment without them must still get its verdict. A missing citation
    degrades the answer; a raised exception would remove it entirely.
    """
    codes = [code for code in rule_codes if code]
    try:
        with connect(platform_db) as conn:
            entries = load_confirmed_entries(
                conn,
                ontology_id,
                object_codes=[object_code] if object_code else (),
                rule_codes=codes,
            )
        if not entries:
            return []
        # Between anchoring and ranking: dropping a permitted-set violation *after*
        # ranking would already have used forbidden text to decide what to show.
        if role_code:
            entries = filter_entries_for_role(platform_db, entries, role_code=role_code, ontology_id=ontology_id)
            if not entries:
                return []
        # Prefer entries anchored to a failed rule; fall back to object-level
        # entries only when no rule-specific text exists.
        rule_anchored = [entry for entry in entries if entry.get("ruleCode") in codes]
        candidates = rule_anchored or entries
        hits = retrieve(question, candidates, limit=limit)
        return [hit.as_dict() for hit in hits]
    except Exception as error:
        logger.debug("知识条目检索跳过: %s", error)
        return []


def _answer_assessment(
    evidence: dict[str, Any],
    vocabulary: DomainVocabulary,
    citations: list[dict[str, Any]] | None = None,
) -> str:
    recommendation = evidence["decision"]["recommendation"]
    object_code = vocabulary.label_for(evidence["semanticKernel"]["objectCode"])
    instance_id = evidence["semanticKernel"]["instanceId"]
    failed = [rule for rule in evidence.get("ruleResults", []) if not rule.get("passed")]
    if not failed:
        return f"{object_code} {instance_id} 目前没有发现明确的合规问题，可以按正常流程继续。{_friendly_recommendation(recommendation)}"
    # Markdown: a verdict is only useful if the reader can tell the rules apart.
    # Each failed rule becomes its own bullet carrying the rule code, so the
    # conclusion can be traced back to a named rule rather than to prose.
    lines = [f"**{object_code} {instance_id} 还不适合直接通过。**", ""]
    # Citations are keyed by rule code so a clause attaches to the rule it
    # actually justifies, rather than being appended as a loose reading list.
    by_rule: dict[str, dict[str, Any]] = {}
    for citation in citations or []:
        rule_code = citation.get("ruleCode") or ""
        if rule_code and rule_code not in by_rule:
            by_rule[rule_code] = citation
    for rule in failed[:5]:
        code = rule.get("ruleCode") or ""
        marker = "🚫" if rule.get("severity") == "blocking" else "⚠️"
        suffix = f"（规则 `{code}`）" if code else ""
        line = f"- {marker} **{rule['ruleName']}**{suffix}：{rule['explanation']}"
        source = by_rule.get(code)
        if source:
            document = source.get("documentTitle") or "制度文件"
            line += f"　依据《{document}》{source.get('citation', '')}"
        lines.append(line)
    remaining = len(failed) - 5
    if remaining > 0:
        lines.append(f"- 另有 {remaining} 条规则未通过，可在决策留痕中查看完整清单。")
    unevaluable = [rule for rule in failed if rule.get("skipped")]
    if unevaluable:
        lines += [
            "",
            f"> 其中 {len(unevaluable)} 条规则**无法在当前数据结构上求值**，"
            "已按未通过处理（可能由字段更名等结构漂移导致），需人工复核规则表达式。",
        ]
    lines += ["", _friendly_recommendation(recommendation)]
    return "\n".join(lines)


def _answer_preflight(evidence: dict[str, Any]) -> str:
    instance_id = evidence["target"]["instanceId"]
    if evidence["allowed"]:
        return f"实例 {instance_id} 已经具备操作条件，可以继续执行。"
    failed = [rule for rule in evidence.get("ruleResults", []) if not rule.get("passed")]
    lines = [f"**实例 {instance_id} 现在还不宜执行这项操作**，不建议自动执行。", "", "需要先处理："]
    for rule in failed[:5]:
        code = rule.get("ruleCode") or ""
        suffix = f"（规则 `{code}`）" if code else ""
        lines.append(f"- **{rule['ruleName']}**{suffix}：{rule['explanation']}")
    remaining = len(failed) - 5
    if remaining > 0:
        lines.append(f"- 另有 {remaining} 条未通过。")
    return "\n".join(lines)


def _answer_consistency(evidence: dict[str, Any], vocabulary: DomainVocabulary) -> str:
    summary = evidence["summary"]
    # A distribution reads far better as a table than as a run-on sentence.
    label = vocabulary.label_for(evidence["objectCode"])
    return "\n".join(
        [
            f"**{label} 的批量决策一致性：{evidence['status']}**（已评估 {evidence['assessed']} 条）",
            "",
            "| 结果 | 数量 |",
            "| --- | ---: |",
            f"| 通过 | {summary['approved']} |",
            f"| 需复核 | {summary['review']} |",
            f"| 阻断 | {summary['blocked']} |",
            f"| 求值错误 | {summary['errors']} |",
        ]
    )


def _answer_overall_compliance(evidence: dict[str, Any], vocabulary: DomainVocabulary) -> str:
    summary = evidence["summary"]
    if summary["blocked"] == 0 and summary["review"] == 0 and summary["errors"] == 0:
        verdict = "整体可视为合规"
    elif summary["blocked"] > 0:
        verdict = "存在阻断性不合规风险"
    else:
        verdict = "存在需要复核的合规风险"
    object_label = vocabulary.label_for(evidence["objectCode"])
    return (
        f"{object_label} 当前{verdict}。"
        f"已评估 {evidence['assessed']} 条：通过 {summary['approved']}、复核 {summary['review']}、阻断 {summary['blocked']}、错误 {summary['errors']}。"
        f"如需单条结论，请指定{object_label}的 ID 或业务编号。"
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
        return RESOLUTION_CONFIDENCE.unknown_intent
    score = RESOLUTION_CONFIDENCE.base
    if resolved.object_code:
        score += RESOLUTION_CONFIDENCE.object_bonus
    if resolved.instance_id:
        score += RESOLUTION_CONFIDENCE.instance_bonus
    if resolved.ontology_id:
        score += RESOLUTION_CONFIDENCE.ontology_bonus
    return min(score, RESOLUTION_CONFIDENCE.ceiling)


def _question_examples(vocabulary: DomainVocabulary) -> dict[str, str]:
    """Build sample questions from the modelled vocabulary.

    Prompts and error hints therefore reference the user's own business objects
    instead of a built-in domain.
    """
    term = vocabulary.default_object()
    label = term.label if term is not None else "业务对象"
    return {
        "explain": f"{label} 1 是什么",
        "compliance": f"{label} 1 是否合规",
        "preflight": f"{label} 1 能提交审批吗",
        "consistency": f"{label}整体决策是否一致",
    }


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


def compact_json(value: Any) -> str:
    """JSON for a model prompt: no ASCII escaping, and never raises on odd types.

    `default=str` matters -- a Decimal or date in a record would otherwise raise mid
    prompt-assembly and turn a serialisation detail into a failed answer.
    """
    return json.dumps(value, ensure_ascii=False, default=str)


def compact_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
    """Shrink an evidence payload to what a model prompt can carry.

    Public because `agent` assembles prompts from the same evidence shapes. Truncation
    is deliberate and lossy: the full evidence stays in the decision record, which is
    what an audit reads, while the prompt gets the part that fits.
    """
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
