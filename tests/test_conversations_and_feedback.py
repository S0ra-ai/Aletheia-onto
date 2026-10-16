"""Conversation persistence and the feedback loop.

Two ROADMAP stage-A gaps. History used to live entirely in the client, so a
refresh lost the thread and nothing tied an answer to the question behind it --
which is also why feedback was impossible to attribute. And nothing recorded
whether an answer was right, which is a conspicuous hole for a product whose claim
is auditability.

The properties worth pinning down: history round-trips, feedback reaches the
decision record, and a correction is *stored* rather than silently becoming truth.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from ontology_platform.agent import _extract_tool_calls, _strip_tool_calls, _tool_marker_spans, agent_chat
from ontology_platform.conversations import (
    FEEDBACK_RATINGS,
    append_message,
    ensure_conversation,
    escalate_conversation,
    feedback_summary,
    get_conversation,
    init_conversation_schema,
    list_conversations,
    list_feedback,
    load_history,
    resolve_feedback,
    set_conversation_status,
    submit_feedback,
)
from ontology_platform.database import connect, initialize_platform_db
from ontology_platform.metadata import register_data_source, scan_data_source
from ontology_platform.ontology import generate_ontology_draft
from ontology_platform.workbench import build_workbench


@pytest.fixture
def platform(tmp_path: Path):
    platform_db = tmp_path / "platform.sqlite3"
    business_db = tmp_path / "business.sqlite3"
    initialize_platform_db(platform_db)
    conn = sqlite3.connect(business_db)
    conn.executescript(
        """
        create table ticket (id integer primary key, subject text not null, status text not null);
        insert into ticket values (1, '退款申请', 'open');
        """
    )
    conn.commit()
    conn.close()
    source = register_data_source(platform_db, "工单系统", "sqlite", str(business_db), domain="客户服务")
    scan_data_source(platform_db, source.id)
    ontology = generate_ontology_draft(platform_db, source.id)
    with connect(platform_db) as c:
        init_conversation_schema(c)
        # Idempotent: startup runs this on every boot.
        init_conversation_schema(c)
    return {
        "platform_db": platform_db,
        "source_id": source.id,
        "ontology_id": ontology["ontology"]["id"],
    }


# -- Conversation persistence --


def test_conversation_is_created_without_a_supplied_session_id(platform) -> None:
    """ "Just start chatting" must need no setup."""
    conversation = ensure_conversation(platform["platform_db"])
    assert conversation["sessionId"]
    assert conversation["status"] == "active"


def test_ensure_is_idempotent_for_the_same_session(platform) -> None:
    first = ensure_conversation(platform["platform_db"], "sess-1")
    second = ensure_conversation(platform["platform_db"], "sess-1")
    assert first["id"] == second["id"]
    assert len(list_conversations(platform["platform_db"])) == 1


def test_history_round_trips_in_chronological_order(platform) -> None:
    db = platform["platform_db"]
    append_message(db, "sess-1", "user", "第一个问题")
    append_message(db, "sess-1", "assistant", "第一个回答")
    append_message(db, "sess-1", "user", "第二个问题")

    history = load_history(db, "sess-1")
    assert [turn["role"] for turn in history] == ["user", "assistant", "user"]
    assert history[0]["content"] == "第一个问题"


def test_history_keeps_the_most_recent_turns_in_order(platform) -> None:
    """A model prompt needs recent context, but in the order it was said."""
    db = platform["platform_db"]
    for index in range(10):
        append_message(db, "sess-1", "user", f"问题 {index}")

    history = load_history(db, "sess-1", limit=3)
    assert [turn["content"] for turn in history] == ["问题 7", "问题 8", "问题 9"]


def test_history_of_an_unknown_session_is_empty_not_an_error(platform) -> None:
    assert load_history(platform["platform_db"], "never-existed") == []


def test_the_first_user_turn_names_the_conversation(platform) -> None:
    """So the list is scannable without opening every thread."""
    db = platform["platform_db"]
    append_message(db, "sess-1", "user", "订单为什么不能退款")
    append_message(db, "sess-1", "user", "第二个问题不应改标题")
    assert get_conversation(db, "sess-1")["title"] == "订单为什么不能退款"


def test_message_count_tracks_appended_turns(platform) -> None:
    db = platform["platform_db"]
    for _ in range(3):
        append_message(db, "sess-1", "user", "x")
    assert get_conversation(db, "sess-1")["messageCount"] == 3


def test_system_messages_are_excluded_from_model_history(platform) -> None:
    """A system note is bookkeeping, not conversational context."""
    db = platform["platform_db"]
    append_message(db, "sess-1", "system", "会话已转人工")
    append_message(db, "sess-1", "user", "真实问题")
    assert [turn["role"] for turn in load_history(db, "sess-1")] == ["user"]


def test_unknown_message_role_is_rejected(platform) -> None:
    with pytest.raises(ValueError, match="不支持的消息角色"):
        append_message(platform["platform_db"], "sess-1", "robot", "x")


def test_unknown_conversation_raises(platform) -> None:
    with pytest.raises(ValueError, match="会话不存在"):
        get_conversation(platform["platform_db"], "nope")


# -- agent_chat integration --


def test_agent_chat_persists_both_turns(platform) -> None:
    """Previously nothing was stored, so a refresh lost the thread."""
    result = agent_chat(
        platform["platform_db"],
        "工单 1 的状态是什么？",
        data_source_id=platform["source_id"],
        session_id="chat-1",
        actor="tester",
    )
    assert result["sessionId"] == "chat-1"
    assert result["messageId"]

    conversation = get_conversation(platform["platform_db"], "chat-1")
    roles = [message["role"] for message in conversation["messages"]]
    assert roles == ["user", "assistant"], roles


def test_agent_chat_uses_stored_history_on_the_next_turn(platform) -> None:
    db = platform["platform_db"]
    agent_chat(db, "第一个问题", data_source_id=platform["source_id"], session_id="chat-1")
    agent_chat(db, "第二个问题", data_source_id=platform["source_id"], session_id="chat-1")
    conversation = get_conversation(db, "chat-1")
    assert conversation["messageCount"] == 4
    assert conversation["messages"][0]["content"] == "第一个问题"


def test_explicit_history_still_wins(platform) -> None:
    """Existing callers that manage their own context must be unaffected."""
    db = platform["platform_db"]
    result = agent_chat(
        db,
        "问题",
        data_source_id=platform["source_id"],
        history=[{"role": "user", "content": "调用方自带上下文"}],
        session_id="chat-1",
    )
    assert result["sessionId"] == "chat-1"


def test_persist_false_writes_nothing(platform) -> None:
    """Previews and tests must be able to run without leaving state."""
    db = platform["platform_db"]
    result = agent_chat(db, "问题", data_source_id=platform["source_id"], persist=False)
    assert "sessionId" not in result
    assert list_conversations(db) == []


def test_agent_chat_without_a_session_id_creates_one(platform) -> None:
    result = agent_chat(platform["platform_db"], "问题", data_source_id=platform["source_id"])
    assert result["sessionId"]
    assert len(list_conversations(platform["platform_db"])) == 1


# -- Feedback --


def _message_id(platform, session: str = "sess-1") -> int:
    append_message(platform["platform_db"], session, "user", "问题")
    stored = append_message(platform["platform_db"], session, "assistant", "回答", decision_id="dec-123")
    return int(stored["messageId"])


@pytest.mark.parametrize("rating", FEEDBACK_RATINGS)
def test_each_rating_is_accepted(platform, rating) -> None:
    message_id = _message_id(platform)
    result = submit_feedback(platform["platform_db"], message_id, rating, actor="user-1")
    assert result["rating"] == rating


def test_unknown_rating_is_rejected(platform) -> None:
    message_id = _message_id(platform)
    with pytest.raises(ValueError, match="不支持的反馈类型"):
        submit_feedback(platform["platform_db"], message_id, "五星好评")


def test_feedback_inherits_the_decision_id_from_the_message(platform) -> None:
    """Taken from the message, not the caller, so it cannot be misattributed."""
    message_id = _message_id(platform)
    result = submit_feedback(platform["platform_db"], message_id, "incorrect", actor="user-1")
    assert result["decisionId"] == "dec-123"


def test_feedback_on_an_unknown_message_is_rejected(platform) -> None:
    with pytest.raises(ValueError, match="消息不存在"):
        submit_feedback(platform["platform_db"], 999999, "helpful")


def test_a_correction_is_stored_but_not_applied(platform) -> None:
    """A correction is one user's claim, not a new rule (ADR-0002)."""
    message_id = _message_id(platform)
    result = submit_feedback(
        platform["platform_db"],
        message_id,
        "incorrect",
        correction="应该允许退款，签收未超 15 天",
        rule_code="refund_window_check",
        actor="user-1",
    )
    assert "不会自动生效" in result["note"]

    stored = list_feedback(platform["platform_db"])[0]
    assert stored["correction"].startswith("应该允许退款")
    assert stored["status"] == "open"
    # Nothing was promoted into the rule set.
    with connect(platform["platform_db"]) as conn:
        rules = conn.execute("select count(*) as c from business_rule").fetchone()["c"]
    assert rules == 0


def test_feedback_is_visible_on_the_message_it_concerns(platform) -> None:
    """ "This answer was wrong" is only actionable if you know which answer."""
    message_id = _message_id(platform)
    submit_feedback(platform["platform_db"], message_id, "unhelpful", comment="没回答我的问题")
    conversation = get_conversation(platform["platform_db"], "sess-1")
    assistant = next(m for m in conversation["messages"] if m["role"] == "assistant")
    assert assistant["feedback"]
    assert assistant["feedback"][0]["comment"] == "没回答我的问题"


def test_feedback_is_recorded_in_the_audit_log(platform) -> None:
    message_id = _message_id(platform)
    submit_feedback(platform["platform_db"], message_id, "incorrect", actor="user-1")
    with connect(platform["platform_db"]) as conn:
        rows = conn.execute("select actor, action from audit_log where action = 'submit_answer_feedback'").fetchall()
    assert rows and rows[0]["actor"] == "user-1"


def test_feedback_can_be_resolved(platform) -> None:
    message_id = _message_id(platform)
    feedback = submit_feedback(platform["platform_db"], message_id, "incorrect")
    resolve_feedback(platform["platform_db"], feedback["id"], resolution="resolved", actor="ops")
    stored = list_feedback(platform["platform_db"])[0]
    assert stored["status"] == "resolved"
    assert stored["resolvedBy"] == "ops"


def test_resolving_unknown_feedback_is_rejected(platform) -> None:
    with pytest.raises(ValueError, match="反馈不存在"):
        resolve_feedback(platform["platform_db"], 999999)


def test_feedback_can_be_filtered_by_rating_and_status(platform) -> None:
    db = platform["platform_db"]
    first = _message_id(platform, "sess-1")
    second = _message_id(platform, "sess-2")
    submit_feedback(db, first, "helpful")
    submit_feedback(db, second, "incorrect")
    assert len(list_feedback(db, rating="incorrect")) == 1
    assert len(list_feedback(db, status="open")) == 2


# -- Escalation --


def test_escalation_sets_a_status_not_just_a_log_line(platform) -> None:
    """It must show up in the queue an operator works from."""
    db = platform["platform_db"]
    ensure_conversation(db, "sess-1")
    escalate_conversation(db, "sess-1", assignee="alice", reason="涉及金额争议", actor="bot")

    conversation = get_conversation(db, "sess-1")
    assert conversation["status"] == "escalated"
    assert conversation["escalatedTo"] == "alice"
    assert conversation["escalationReason"] == "涉及金额争议"
    assert len(list_conversations(db, status="escalated")) == 1


def test_escalating_an_unknown_session_is_rejected(platform) -> None:
    with pytest.raises(ValueError, match="会话不存在"):
        escalate_conversation(platform["platform_db"], "nope")


def test_conversation_status_can_be_set_and_validated(platform) -> None:
    db = platform["platform_db"]
    ensure_conversation(db, "sess-1")
    set_conversation_status(db, "sess-1", "resolved", actor="ops")
    assert get_conversation(db, "sess-1")["status"] == "resolved"
    with pytest.raises(ValueError, match="不支持的会话状态"):
        set_conversation_status(db, "sess-1", "magic")


# -- Aggregation --


def test_summary_reports_counts_not_an_average(platform) -> None:
    """An average score does not tell you which answer to fix."""
    db = platform["platform_db"]
    first = _message_id(platform, "sess-1")
    second = _message_id(platform, "sess-2")
    submit_feedback(db, first, "helpful")
    submit_feedback(db, second, "incorrect", correction="应为允许")

    summary = feedback_summary(db)
    assert summary["helpful"] == 1
    assert summary["incorrect"] == 1
    assert summary["corrections"] == 1
    assert summary["openItems"] == 2
    assert "average" not in summary


def test_incorrect_answers_surface_as_a_workbench_blocker(platform) -> None:
    """A human saying a verdict is wrong is the strongest signal available."""
    db = platform["platform_db"]
    message_id = _message_id(platform)
    submit_feedback(db, message_id, "incorrect")

    result = build_workbench(db)
    codes = [item["code"] for item in result["actionItems"]]
    assert "incorrect_answers_reported" in codes
    item = next(i for i in result["actionItems"] if i["code"] == "incorrect_answers_reported")
    assert item["severity"] == "blocker"
    assert item["route"] == "/feedback"


def test_escalated_conversations_surface_in_the_workbench(platform) -> None:
    db = platform["platform_db"]
    ensure_conversation(db, "sess-1")
    escalate_conversation(db, "sess-1", assignee="alice")
    codes = [item["code"] for item in build_workbench(db)["actionItems"]]
    assert "escalated_conversations" in codes


def test_workbench_still_works_without_the_conversation_tables(tmp_path: Path) -> None:
    """The tables are optional; a library-only install lacks them."""
    platform_db = tmp_path / "platform.sqlite3"
    initialize_platform_db(platform_db)
    result = build_workbench(platform_db)
    assert result["feedback"]["total"] == 0


def test_feedback_endpoints_require_sensible_capabilities() -> None:
    """Anyone who saw the answer can report it; acting on reports is governance."""
    from ontology_platform.access_policy import required_capability

    assert required_capability("POST", "/conversations/messages/5/feedback") == "platform:read"
    assert required_capability("POST", "/conversations/abc/escalate") == "governance:review"
    assert required_capability("POST", "/feedback/1/resolve") == "governance:review"


# -- tool-call markers --


class TestToolCallMarkers:
    """Parsing the marker the agent prompt asks the model to emit.

    The pattern this replaced used `[^{}]*` between the braces, which cannot span a nested
    object -- so one nested level anywhere inside `args` made the whole marker unmatched.
    The failure was silent in both directions at once: the tool was never executed, and the
    raw JSON stayed in the answer the user read. An extraction whose depth is not known in
    advance is not a regular language, which is why this is brace counting now.
    """

    def test_a_flat_marker_is_extracted_and_stripped(self) -> None:
        text = '好的。{"tool": "preflight_operation", "args": {"instanceId": "1"}} 以上。'
        assert [call["tool"] for call in _extract_tool_calls(text)] == ["preflight_operation"]
        assert _strip_tool_calls(text) == "好的。 以上。"

    def test_a_nested_argument_object_is_extracted(self) -> None:
        """The case the regex silently dropped."""
        text = (
            '{"tool": "preflight_operation", "args": '
            '{"operationCode": "submit", "instanceId": "1", "context": {"source": "chat"}}}'
        )
        calls = _extract_tool_calls(text)
        assert [call["tool"] for call in calls] == ["preflight_operation"]
        assert calls[0]["args"]["context"] == {"source": "chat"}
        assert _strip_tool_calls(text) == ""

    def test_several_markers_in_one_answer(self) -> None:
        text = '先看这个 {"tool": "a", "args": {"x": {"y": 1}}} 再看 {"tool": "b", "args": {}}'
        assert [call["tool"] for call in _extract_tool_calls(text)] == ["a", "b"]
        assert _strip_tool_calls(text) == "先看这个  再看"

    def test_a_brace_inside_a_string_does_not_confuse_the_depth(self) -> None:
        text = '{"tool": "x", "args": {"note": "a } brace and { another"}}'
        assert [call["tool"] for call in _extract_tool_calls(text)] == ["x"]
        assert _strip_tool_calls(text) == ""

    def test_prose_containing_json_that_is_not_a_call_is_left_alone(self) -> None:
        text = '规则是这样的：{"expression": "amount > 0"}，请确认。'
        assert _extract_tool_calls(text) == []
        assert _strip_tool_calls(text) == text

    def test_extraction_and_stripping_agree(self) -> None:
        """They used to run the same regex independently, so anything it missed failed
        twice over: no call executed *and* the marker left in the prose."""
        for text in (
            '前言 {"tool": "a", "args": {}} 后语',
            '{"tool": "a", "args": {"deep": {"deeper": {"deepest": 1}}}}',
            "没有标记",
            '{"not_a_tool": true}',
        ):
            spans = _tool_marker_spans(text)
            calls = _extract_tool_calls(text)
            assert len(spans) == len(calls)
            if calls:
                assert text not in _strip_tool_calls(text)


def test_every_workbench_action_route_is_a_page_the_console_serves(platform) -> None:
    """The 去处理 buttons navigate to these strings, so each has to be a route that exists.

    `escalated_conversations` pointed at `/conversations` -- the *API's* namespace, not a page.
    The only way into an escalated conversation therefore ended on 页面不存在, and nothing
    noticed: the backend's own test asserted the item's presence, and the frontend cannot check
    a string it receives at runtime.

    Read from `App.tsx`, which is where the routes actually are, rather than from a list kept
    beside it -- a second copy of the route table is how the sweep came to hold a path the
    application does not serve.
    """
    import re

    db = platform["platform_db"]
    ensure_conversation(db, "sess-1")
    escalate_conversation(db, "sess-1", assignee="alice")
    routes = {item["route"] for item in build_workbench(db)["actionItems"]}
    assert routes, "这个平台状态下应当至少有一条待处理事项"

    app_source = (Path(__file__).resolve().parents[1] / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
    # The console's routes are children of the `/admin` basename, and the workbench writes them
    # the way `navigate()` takes them -- relative to that basename. Compared on that basis, not
    # on the literal prefix: the two are the same path spelled for different layers.
    served = {
        "/" + path.strip("/")
        for path in re.findall(r'<Route\s+path="([^"]+)"', app_source)
        if path.strip("/") not in ("*", "")
    }
    unknown = sorted(route for route in routes if route not in served)
    assert not unknown, f"工作台的事项指向控制台没有的页面：{unknown}（前端实际服务：{sorted(served)}）"


def test_an_interactive_model_call_reaches_the_invocation_ledger(platform) -> None:
    """The ledger recorded four purposes, and none of the interactive ones.

    `record_model_invocation` was called from the non-interactive paths only
    (`ontology_suggestions`, `blueprint_draft`, `ontology_reasoning_chain`, `model_config_test`),
    while the comment in `agent.py`'s except-branch said the ledger 「already keeps a durable
    record for the admin UI」. So the calls an operator most wants to account for -- the ones a
    person triggered, and the ones that failed -- were exactly the ones missing, in a platform
    whose accountability story rests on 「which answers involved a model」.
    """
    from ontology_platform.agent import _llm_agent_chat, resolve_agent_role
    from ontology_platform.model_client import OpenRouterClient, OpenRouterConfig

    def transport(url: str, headers: dict[str, str], payload: dict[str, object], timeout_seconds: float):
        return {
            "model": "test-model",
            "choices": [{"message": {"content": "合同 1 没有问题。"}}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 16},
        }

    db = platform["platform_db"]
    client = OpenRouterClient(
        OpenRouterConfig(
            api_key="test-key",
            model="test-model",
            base_url="https://openrouter.ai/api/v1",
            http_referer="",
            app_title="",
            service_tier="auto",
            timeout_seconds=10,
        ),
        transport=transport,
    )
    role = resolve_agent_role(db, "business_expert")

    _llm_agent_chat(db, client, "合同 1 是否合规？", role, platform["source_id"], None, [], "chat-ledger")

    with connect(db) as conn:
        rows = conn.execute(
            "select purpose, status, total_tokens from model_invocation where purpose = 'agent_chat'"
        ).fetchall()
    assert rows, "交互式调用没有进入模型调用台账"
    assert rows[0]["status"] == "success"
    assert rows[0]["total_tokens"] == 16

    # And a failure is recorded too: an error an operator cannot see is a call they cannot
    # account for.
    def failing_transport(url: str, headers: dict[str, str], payload: dict[str, object], timeout_seconds: float):
        raise RuntimeError("连接被拒绝")

    broken = OpenRouterClient(
        OpenRouterConfig(
            api_key="test-key",
            model="test-model",
            base_url="https://openrouter.ai/api/v1",
            http_referer="",
            app_title="",
            service_tier="auto",
            timeout_seconds=10,
        ),
        transport=failing_transport,
    )
    _llm_agent_chat(db, broken, "再来一次", role, platform["source_id"], None, [], "chat-ledger")

    with connect(db) as conn:
        failed = conn.execute(
            "select status, error from model_invocation where purpose = 'agent_chat' and status = 'error'"
        ).fetchall()
    assert failed, "失败的交互式调用没有进入台账"
    assert "连接被拒绝" in failed[0]["error"]
