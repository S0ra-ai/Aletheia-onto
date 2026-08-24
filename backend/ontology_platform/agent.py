from __future__ import annotations

import json
import logging
import re
import time as _time
from dataclasses import dataclass, replace
from typing import Any

from .agent_roles import AgentRole, build_system_prompt, list_agent_roles, resolve_agent_role
from .automation import preflight_operation
from .config import ANSWER_CONFIDENCE
from .context import PlatformDb
from .conversations import append_message, ensure_conversation, load_history
from .database import connect
from .knowledge_base import build_reasoning_chain, list_knowledge_bases
from .model_client import OpenRouterClient, OpenRouterConfig
from .natural_language import (
    INTENT_COMPLIANCE,
    INTENT_CONSISTENCY,
    INTENT_EXPLAIN,
    INTENT_KNOWLEDGE_OVERVIEW,
    INTENT_PREFLIGHT,
    INTENT_UNKNOWN,
    compact_evidence,
    compact_json,
    detect_intent,
    query_natural_language,
)
from .ontology import explain_instance
from .semantic_kernel import assess_decision_consistency, assess_instance
from .vocabulary import load_vocabulary
from .workflow_permission import check_tool_authorization, log_tool_execution

logger = logging.getLogger(__name__)


def get_agent_roles(platform_db: PlatformDb) -> list[dict[str, Any]]:
    """Roles available for the domains that have actually been onboarded."""
    return [role.public_dict() for role in list_agent_roles(platform_db)]


def get_agent_role(platform_db: PlatformDb, role_id: str) -> dict[str, Any] | None:
    for role in list_agent_roles(platform_db):
        if role.id == role_id:
            return role.public_dict()
    return None


@dataclass(frozen=True)
class AgentTurn:
    answer: str
    intent: str
    confidence: float
    resolved: dict[str, Any]
    evidence: dict[str, Any]
    next_actions: list[str]
    model_info: dict[str, Any]
    tool_calls: list[dict[str, Any]]


def agent_chat(
    platform_db: PlatformDb,
    message: str,
    role_id: str | None = None,
    data_source_id: int | None = None,
    object_code: str | None = None,
    history: list[dict[str, str]] | None = None,
    session_id: str | None = None,
    actor: str = "",
    persist: bool = True,
    role_code: str = "",
) -> dict[str, Any]:
    """Answer one turn, persisting the exchange by default.

    History used to come only from the caller, so a page refresh lost the thread
    and nothing linked an answer to the question that produced it. When
    `session_id` is given and `persist` is on, the stored history is used and both
    turns are recorded.

    An explicitly supplied `history` still wins, so existing callers that manage
    their own context are unaffected. `persist=False` exists for callers that must
    not write -- previews and tests.
    """
    role = resolve_agent_role(platform_db, role_id)
    # A derived role knows its data source; honour it when the caller did not
    # pin one explicitly.
    if data_source_id is None:
        data_source_id = role.data_source_id
    model_client = OpenRouterClient(OpenRouterConfig.from_db_or_env(platform_db))

    conversation: dict[str, Any] | None = None
    if persist:
        conversation = ensure_conversation(
            platform_db,
            session_id,
            role_id=role.id,
            data_source_id=data_source_id,
            object_code=object_code or "",
            actor=actor,
        )
        session_id = conversation["sessionId"]
        if history is None:
            history = load_history(platform_db, session_id)
        append_message(platform_db, session_id, "user", message, actor=actor)
    history = history or []

    if not model_client.configured:
        result = _fallback_agent_chat(
            platform_db, message, role, data_source_id, object_code, history, role_code=role_code
        )
    else:
        result = _llm_agent_chat(
            platform_db, model_client, message, role, data_source_id, object_code, history, session_id
        )

    if conversation is not None:
        stored = append_message(
            platform_db,
            session_id or conversation["sessionId"],
            "assistant",
            str(result.get("answer") or ""),
            intent=str(result.get("intent") or ""),
            confidence=result.get("confidence"),
            # Carry the decision id and citations so feedback can reach the
            # verdict and the clause behind it.
            decision_id=_decision_id_from(result),
            citations=_citations_from(result),
            actor=actor,
        )
        result = {
            **result,
            "sessionId": conversation["sessionId"],
            "conversationId": conversation["id"],
            "messageId": stored["messageId"],
        }
    return result


def _decision_id_from(result: dict[str, Any]) -> str:
    """Pull the decision id out of whichever evidence shape produced it."""
    evidence = result.get("evidence")
    if not isinstance(evidence, dict):
        return ""
    record = evidence.get("decisionRecord")
    if isinstance(record, dict) and record.get("decisionId"):
        return str(record["decisionId"])
    decision = evidence.get("decision")
    if isinstance(decision, dict) and decision.get("decisionId"):
        return str(decision["decisionId"])
    return ""


def _citations_from(result: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = result.get("evidence")
    if isinstance(evidence, dict):
        citations = evidence.get("citations")
        if isinstance(citations, list):
            return citations
    return []


def _llm_agent_chat(
    platform_db: PlatformDb,
    model_client: OpenRouterClient,
    message: str,
    role: AgentRole,
    data_source_id: int | None,
    object_code: str | None,
    history: list[dict[str, str]],
    session_id: str | None,
) -> dict[str, Any]:
    semantic_context = _build_agent_context(platform_db, data_source_id)
    knowledge_context = _build_knowledge_context(platform_db, data_source_id, object_code)

    tool_descriptions = (
        "你可以调用以下工具函数来获取精确的业务数据：\n"
        "- explain_instance(objectCode, instanceId): 解释业务实例的详细信息\n"
        "- assess_instance(objectCode, instanceId): 对业务实例执行合规研判\n"
        "- preflight_operation(operationCode, instanceId): 预检操作是否可执行\n"
        "- knowledge_overview(objectCode): 查看业务对象的规则和关系概览\n"
        "- decision_consistency(objectCode): 批量评估决策一致性\n"
        "\n要调用工具，在回答中输出如下 JSON 标记（可多个）：\n"
        '{"tool": "工具名", "args": {"参数名": "值"}}\n'
        "系统会自动执行工具并返回结果，你可以基于结果生成最终回答。\n"
        "如果不需要工具，直接用自然语言回答即可。\n"
    )

    messages = [
        # The prompt is rendered against the live ontology so the model only
        # sees business objects that actually exist.
        {"role": "system", "content": build_system_prompt(role, knowledge_context)},
        {
            "role": "system",
            "content": (
                "## 可用业务上下文\n"
                f"{compact_json(semantic_context)}\n\n"
                f"## 已初始化知识库\n"
                f"{compact_json(knowledge_context)}\n\n"
                f"## 工具调用说明\n"
                f"{tool_descriptions}"
            ),
        },
    ]

    for turn in history[-10:]:
        messages.append({"role": turn["role"], "content": turn["content"]})

    messages.append({"role": "user", "content": message})

    try:
        timeout_client = _client_with_timeout(model_client, 30)
        result = timeout_client.chat(messages, purpose="agent_chat", session_id=session_id or "ontology-agent")
        raw_content = result.content.strip()

        tool_calls = _extract_tool_calls(raw_content)
        clean_answer = _strip_tool_calls(raw_content)

        if tool_calls:
            tool_results = _execute_tool_calls(platform_db, tool_calls, data_source_id, object_code, role.id)
            if tool_results:
                followup_messages = [
                    *messages,
                    {"role": "assistant", "content": clean_answer},
                    {
                        "role": "user",
                        "content": (
                            "以下是工具调用返回的精确数据，请基于这些数据完善你的回答，"
                            "用自然、专业的语言直接回应用户的问题：\n" + compact_json(tool_results)
                        ),
                    },
                ]
                followup = timeout_client.chat(
                    followup_messages, purpose="agent_chat_followup", session_id=session_id or "ontology-agent"
                )
                if followup.content.strip():
                    clean_answer = followup.content.strip()

        intent = _infer_intent_from_answer(clean_answer, message)
        evidence = _build_answer_evidence(tool_calls, tool_results if tool_calls else [])
        confidence = (
            ANSWER_CONFIDENCE.grounded
            if clean_answer and not clean_answer.startswith("我暂时")
            else ANSWER_CONFIDENCE.ungrounded
        )

        return {
            "answer": clean_answer,
            "intent": intent,
            "confidence": confidence,
            "resolved": {
                "dataSourceId": data_source_id,
                "objectCode": object_code,
            },
            "evidence": evidence,
            "nextActions": _suggest_next_actions(intent),
            "model": {
                "configured": True,
                "usedForUnderstanding": True,
                "usedForSummary": False,
                "name": result.model,
            },
            "toolCalls": tool_calls,
            "roleId": role.id,
        }
    except Exception as exc:
        return {
            "answer": f"抱歉，我在处理你的问题时遇到了一些困难：{exc}。请稍后重试，或尝试换一种方式提问。",
            "intent": INTENT_UNKNOWN,
            "confidence": 0.1,
            "resolved": {"dataSourceId": data_source_id, "objectCode": object_code},
            "evidence": {},
            "nextActions": ["重试或检查模型配置"],
            "model": {"configured": model_client.configured, "name": model_client.config.model, "error": str(exc)},
            "toolCalls": [],
            "roleId": role.id,
        }


def _fallback_agent_chat(
    platform_db: PlatformDb,
    message: str,
    role: AgentRole,
    data_source_id: int | None,
    object_code: str | None,
    history: list[dict[str, str]],
    *,
    role_code: str = "",
) -> dict[str, Any]:
    intent = detect_intent(message)
    try:
        result = query_natural_language(
            platform_db,
            message,
            data_source_id=data_source_id,
            object_code=object_code,
            history=history,
            use_model=False,
            # The permission role, not the agent role: citations must be filtered by what
            # the *caller* may read, and an agent persona is not an authorisation.
            role_code=role_code,
        )
        answer = result.get("answer", "")
        # Frame the answer in the role's own domain rather than matching against
        # a built-in list of industries.
        if role.domain and role.domain not in answer:
            answer = f"从{role.domain}角度来看：{answer}"
        return {
            "answer": answer,
            "intent": result.get("intent", intent),
            "confidence": result.get("confidence", ANSWER_CONFIDENCE.neutral),
            "resolved": result.get("resolved", {}),
            "evidence": result.get("evidence", {}),
            "nextActions": result.get("nextActions", []),
            "model": {"configured": False, "fallbackReason": "model_not_configured"},
            "toolCalls": [],
            "roleId": role.id,
        }
    except Exception as exc:
        return {
            "answer": (
                f"你好，我是{role.name}。目前模型服务未配置，我暂时无法进行深度语义研判。\n"
                "你可以在设置中配置 OpenRouter API Key 来启用完整的智能体能力。\n"
                "现在我可以基于规则引擎进行基础的业务研判，请告诉我你想了解什么。"
            ),
            "intent": INTENT_UNKNOWN,
            "confidence": ANSWER_CONFIDENCE.ungrounded,
            "resolved": {"dataSourceId": data_source_id, "objectCode": object_code},
            "evidence": {},
            "nextActions": ["配置 OpenRouter API Key 以启用完整智能体"],
            "model": {"configured": False, "fallbackReason": str(exc)},
            "toolCalls": [],
            "roleId": role.id,
        }


def _build_agent_context(platform_db: PlatformDb, data_source_id: int | None) -> dict[str, Any]:
    with connect(platform_db) as conn:
        sources = conn.execute(
            "select id, name, domain, system_category from data_source order by id desc limit 10"
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
        if data_source_id:
            tables = conn.execute(
                """
                select st.table_name, st.primary_key, st.row_count
                from source_table st
                where st.data_source_id = ?
                order by st.table_name
                """,
                (data_source_id,),
            ).fetchall()
            return {
                "dataSources": [dict(row) for row in sources if dict(row)["id"] == data_source_id],
                "objects": [dict(row) for row in objects if dict(row).get("dataSourceId") == data_source_id],
                "tables": [dict(row) for row in tables],
            }
        return {
            "dataSources": [dict(row) for row in sources],
            "objects": [dict(row) for row in objects],
        }


def _build_knowledge_context(
    platform_db: PlatformDb, data_source_id: int | None, object_code: str | None
) -> dict[str, Any]:
    bases = list_knowledge_bases(platform_db)
    if data_source_id:
        bases = [b for b in bases if b["dataSourceId"] == data_source_id]
    if not bases:
        return {"available": False, "message": "尚未初始化知识库"}
    base = bases[0]
    result: dict[str, Any] = {
        "available": True,
        "name": base.get("name", ""),
        "domain": base.get("domain", ""),
        "objectCount": len(base.get("objects", [])),
        "objects": base.get("objects", []),
    }
    if object_code and data_source_id:
        try:
            chain = build_reasoning_chain(platform_db, data_source_id)
            result["rules"] = [rule for rule in chain.get("rules", []) if rule.get("scopeObjectCode") == object_code][
                :10
            ]
            result["relations"] = [
                rel
                for rel in chain.get("relations", [])
                if object_code in {rel.get("sourceObject"), rel.get("targetObject")}
            ][:10]
        except Exception:
            pass
    return result


def _extract_tool_calls(content: str) -> list[dict[str, Any]]:
    calls = []
    pattern = re.compile(r'\{[^{}]*"tool"\s*:\s*"[^"]+"[^{}]*"args"\s*:\s*\{[^{}]*\}[^{}]*\}', re.DOTALL)
    for match in pattern.finditer(content):
        try:
            parsed = json.loads(match.group())
            if "tool" in parsed and "args" in parsed:
                calls.append(parsed)
        except json.JSONDecodeError:
            continue
    return calls


def _strip_tool_calls(content: str) -> str:
    cleaned = re.sub(r'\{[^{}]*"tool"\s*:\s*"[^"]+"[^{}]*"args"\s*:\s*\{[^{}]*\}[^{}]*\}', "", content, flags=re.DOTALL)
    return cleaned.strip()


# Agent tool calls are always authorized as the platform's AI agent principal,
# independent of which domain persona is answering. The persona shapes wording,
# not privileges.
AGENT_TOOL_PRINCIPAL_ROLE = "ai_agent"


def _execute_tool_calls(
    platform_db: PlatformDb,
    tool_calls: list[dict[str, Any]],
    data_source_id: int | None,
    object_code: str | None,
    role_id: str = "",
) -> list[dict[str, Any]]:
    results = []
    auth_role = AGENT_TOOL_PRINCIPAL_ROLE
    # Resolve the implicit object once, from what is modelled for this source.
    fallback_object = _default_object_code(platform_db, data_source_id)
    for call in tool_calls:
        tool_name = call["tool"]
        args = call.get("args", {})

        auth_result = check_tool_authorization(platform_db, auth_role, tool_name)
        if not auth_result.get("allowed", False):
            results.append(
                {
                    "tool": tool_name,
                    "args": args,
                    "error": f"工具未授权: {auth_result.get('reason', '无权限')}",
                    "authBlocked": True,
                }
            )
            continue

        t0 = _time.monotonic()
        try:
            oc = args.get("objectCode") or object_code or fallback_object
            if not oc:
                results.append(
                    {
                        "tool": tool_name,
                        "args": args,
                        "error": "尚未建模任何业务对象，请先接入数据源并生成本体草案",
                    }
                )
                continue
            if tool_name == "explain_instance":
                iid = args.get("instanceId", "")
                oid = _find_ontology_id(platform_db, data_source_id, oc)
                if oid and iid:
                    result = explain_instance(platform_db, oid, oc, iid)
                    results.append({"tool": tool_name, "args": args, "result": compact_evidence(result)})
            elif tool_name == "assess_instance":
                iid = args.get("instanceId", "")
                oid = _find_ontology_id(platform_db, data_source_id, oc)
                if oid and iid:
                    result = assess_instance(platform_db, oid, oc, iid)
                    results.append({"tool": tool_name, "args": args, "result": compact_evidence(result)})
            elif tool_name == "preflight_operation":
                iid = args.get("instanceId", "")
                oid = _find_ontology_id(platform_db, data_source_id, oc)
                sid = data_source_id or _find_data_source_id(platform_db, oid, oc)
                # Resolve against registered operations instead of guessing a
                # `submit_<object>` name that the legacy system may not use.
                op = args.get("operationCode") or _resolve_operation_code(platform_db, sid, oc)
                if not op:
                    results.append(
                        {
                            "tool": tool_name,
                            "args": args,
                            "error": f"业务对象 {oc} 尚未登记可执行的业务操作",
                        }
                    )
                    continue
                if oid and sid and iid:
                    result = preflight_operation(platform_db, oid, sid, op, iid, oc)
                    results.append({"tool": tool_name, "args": args, "result": compact_evidence(result)})
            elif tool_name == "knowledge_overview":
                sid = data_source_id or _find_data_source_id(platform_db, None, oc)
                if sid:
                    chain = build_reasoning_chain(platform_db, sid)
                    rules = [r for r in chain.get("rules", []) if r.get("scopeObjectCode") == oc]
                    relations = [
                        r for r in chain.get("relations", []) if oc in {r.get("sourceObject"), r.get("targetObject")}
                    ]
                    results.append(
                        {
                            "tool": tool_name,
                            "args": args,
                            "result": {
                                "objectCode": oc,
                                "rules": rules[:10],
                                "relations": relations[:10],
                                "steps": chain.get("steps", [])[:5],
                            },
                        }
                    )
            elif tool_name == "decision_consistency":
                oid = _find_ontology_id(platform_db, data_source_id, oc)
                if oid:
                    result = assess_decision_consistency(platform_db, oid, oc, limit=20)
                    results.append({"tool": tool_name, "args": args, "result": compact_evidence(result)})
            else:
                results.append({"tool": tool_name, "args": args, "error": f"未知工具: {tool_name}"})
        except Exception as exc:
            results.append({"tool": tool_name, "args": args, "error": str(exc)})

        elapsed_ms = int((_time.monotonic() - t0) * 1000)
        last = results[-1] if results else None
        st = "error" if last and "error" in last else "success"
        err_msg = last.get("error", "") if last else ""
        requires_rev = bool(auth_result.get("requiresReview", False))
        try:
            log_tool_execution(
                str(platform_db),
                tool_name,
                agent_role=role_id,
                object_code=object_code or "",
                instance_id=args.get("instanceId", ""),
                input_args=args,
                result_summary=err_msg or "ok",
                status=st,
                error=err_msg,
                duration_ms=elapsed_ms,
                requires_review=requires_rev,
            )
        except Exception as log_error:
            # Tool execution logging must not mask the tool result, but a
            # silent failure here would hide an audit gap.
            logger.warning("记录工具执行日志失败 (%s): %s", tool_name, log_error)

    return results


def _default_object_code(platform_db: PlatformDb, data_source_id: int | None) -> str:
    """The object to assume when the model names none.

    Derived from the modelled ontology, so it adapts to whichever domain was
    onboarded instead of assuming a specific industry.
    """
    vocabulary = load_vocabulary(platform_db, data_source_id=data_source_id)
    term = vocabulary.default_object()
    return term.code if term is not None else ""


def _resolve_operation_code(platform_db: PlatformDb, data_source_id: int | None, object_code: str) -> str:
    """Find a registered operation bound to this business object."""
    if data_source_id is None:
        return ""
    with connect(platform_db) as conn:
        rows = conn.execute(
            """
            select operation_code, semantic_action
            from source_api
            where data_source_id = ?
            order by operation_code
            """,
            (data_source_id,),
        ).fetchall()
    for row in rows:
        if row["semantic_action"].startswith(f"{object_code}."):
            return row["operation_code"]
    for row in rows:
        if object_code in row["operation_code"]:
            return row["operation_code"]
    return rows[0]["operation_code"] if rows else ""


def _find_ontology_id(platform_db: PlatformDb, data_source_id: int | None, object_code: str) -> int | None:
    with connect(platform_db) as conn:
        if data_source_id:
            row = conn.execute(
                """
                select o.id from ontology o
                join business_object bo on bo.ontology_id = o.id
                join source_table st on st.id = bo.source_table_id
                where st.data_source_id = ? and bo.code = ?
                order by o.id desc limit 1
                """,
                (data_source_id, object_code),
            ).fetchone()
            if row:
                return int(row["id"])
        row = conn.execute(
            """
            select o.id from ontology o
            join business_object bo on bo.ontology_id = o.id
            where bo.code = ?
            order by o.id desc limit 1
            """,
            (object_code,),
        ).fetchone()
        return int(row["id"]) if row else None


def _find_data_source_id(platform_db: PlatformDb, ontology_id: int | None, object_code: str) -> int | None:
    with connect(platform_db) as conn:
        if ontology_id:
            row = conn.execute(
                "select st.data_source_id from business_object bo join source_table st on st.id = bo.source_table_id where bo.ontology_id = ? and bo.code = ? limit 1",
                (ontology_id, object_code),
            ).fetchone()
            if row:
                return int(row["data_source_id"])
        row = conn.execute(
            "select st.data_source_id from business_object bo join source_table st on st.id = bo.source_table_id join ontology o on o.id = bo.ontology_id where bo.code = ? order by o.id desc limit 1",
            (object_code,),
        ).fetchone()
        return int(row["data_source_id"]) if row else None


def _infer_intent_from_answer(answer: str, question: str) -> str:
    combined = question + " " + answer
    if any(k in combined for k in ["合规", "风险", "研判", "审查", "通过", "阻断"]):
        return INTENT_COMPLIANCE
    if any(k in combined for k in ["预检", "提交", "审批", "执行"]):
        return INTENT_PREFLIGHT
    if any(k in combined for k in ["解释", "详情", "是什么", "属性", "字段"]):
        return INTENT_EXPLAIN
    if any(k in combined for k in ["一致", "批量", "分布"]):
        return INTENT_CONSISTENCY
    if any(k in combined for k in ["规则", "关系", "概览", "对象"]):
        return INTENT_KNOWLEDGE_OVERVIEW
    return INTENT_UNKNOWN


def _build_answer_evidence(
    tool_calls: list[dict[str, Any]],
    tool_results: list[dict[str, Any]],
) -> dict[str, Any]:
    if not tool_calls:
        return {"source": "llm_reasoning"}
    return {
        "source": "tool_enhanced",
        "toolsUsed": [c["tool"] for c in tool_calls],
        "toolResults": tool_results,
    }


def _suggest_next_actions(intent: str) -> list[str]:
    suggestions = {
        INTENT_COMPLIANCE: ["指定具体实例进行深入研判", "查看批量决策一致性"],
        INTENT_PREFLIGHT: ["确认操作结果", "查看关联业务对象"],
        INTENT_EXPLAIN: ["对该实例进行合规研判", "查看关联规则"],
        INTENT_CONSISTENCY: ["对异常实例进行单独研判", "调整业务规则"],
        INTENT_KNOWLEDGE_OVERVIEW: ["指定具体实例查看详细信息", "对该对象进行合规研判"],
    }
    return suggestions.get(intent, ["告诉我你想了解什么"])


def _client_with_timeout(client: OpenRouterClient, timeout_seconds: float) -> OpenRouterClient:
    config = replace(client.config, timeout_seconds=min(client.config.timeout_seconds, timeout_seconds))
    return OpenRouterClient(config, client.transport)
