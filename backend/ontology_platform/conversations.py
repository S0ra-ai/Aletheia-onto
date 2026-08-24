"""Conversation persistence and the feedback loop.

Two gaps this closes, both from ROADMAP stage A:

**Conversation history was never stored.** Callers passed `history` on every
request, so multi-turn context lived entirely in the client. Three consequences:
a page refresh lost the thread; two clients could not share a conversation; and
nothing tied an answer to the question that produced it, which made feedback
impossible to attribute.

**There was no feedback loop.** Nothing recorded whether an answer was useful,
what the correct answer would have been, or that a case needed a human. For a
product whose claim is auditability, "we cannot tell you whether our answers were
right" is a conspicuous hole.

Design decisions worth stating:

- **Feedback attaches to a message, not to a conversation.** "This answer was
  wrong" is only actionable if you know which answer.
- **Feedback links to the decision record when one exists.** That is what turns
  「这个判定不对」 into a reviewable trail: the verdict, the rules that produced it,
  and a human saying it was wrong.
- **Corrections are stored, never auto-applied.** A correction is a claim by one
  user, not a new rule. Promoting it to a rule or a knowledge entry goes through
  the existing governance flow, consistent with ADR-0002 and ADR-0009.
- **Escalation is a state on the conversation, not a side effect.** Marking a case
  for human handoff must be visible in the queue rather than only in a log.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Optional

from .context import PlatformDb
from .database import connect, last_insert_id
from .schema import SchemaBundle

logger = logging.getLogger(__name__)

# Feedback verdicts. Deliberately small: a scale invites averaging, and an
# average satisfaction score does not tell you which answer to fix.
FEEDBACK_RATINGS = ("helpful", "unhelpful", "incorrect")

CONVERSATION_STATUSES = ("active", "escalated", "resolved", "closed")

MAX_HISTORY_TURNS = 20


def _new_id() -> str:
    return uuid.uuid4().hex[:16]


CONVERSATION_SCHEMA: tuple[dict[str, str], ...] = (
    {
        "sqlite": """
        create table if not exists conversation (
            id integer primary key autoincrement,
            session_id text not null unique,
            title text not null default '',
            role_id text not null default '',
            data_source_id integer,
            ontology_id integer,
            object_code text not null default '',
            status text not null default 'active',
            actor text not null default '',
            escalated_to text not null default '',
            escalation_reason text not null default '',
            message_count integer not null default 0,
            created_at text not null default current_timestamp,
            updated_at text not null default current_timestamp
        )""",
        "postgresql": """
        create table if not exists conversation (
            id serial primary key,
            session_id text not null unique,
            title text not null default '',
            role_id text not null default '',
            data_source_id integer,
            ontology_id integer,
            object_code text not null default '',
            status text not null default 'active',
            actor text not null default '',
            escalated_to text not null default '',
            escalation_reason text not null default '',
            message_count integer not null default 0,
            created_at timestamp not null default current_timestamp,
            updated_at timestamp not null default current_timestamp
        )""",
        "mysql": """
        create table if not exists conversation (
            id integer primary key auto_increment,
            session_id varchar(64) not null unique,
            title varchar(500) not null default '',
            role_id varchar(255) not null default '',
            data_source_id integer,
            ontology_id integer,
            object_code varchar(255) not null default '',
            status varchar(50) not null default 'active',
            actor varchar(255) not null default '',
            escalated_to varchar(255) not null default '',
            escalation_reason text,
            message_count integer not null default 0,
            created_at datetime not null default current_timestamp,
            updated_at datetime not null default current_timestamp
        )""",
    },
    {
        "sqlite": """
        create table if not exists conversation_message (
            id integer primary key autoincrement,
            conversation_id integer not null references conversation(id),
            role text not null,
            content text not null,
            intent text not null default '',
            confidence real,
            decision_id text not null default '',
            citations text not null default '[]',
            evidence_ref text not null default '{}',
            actor text not null default '',
            created_at text not null default current_timestamp
        )""",
        "postgresql": """
        create table if not exists conversation_message (
            id serial primary key,
            conversation_id integer not null references conversation(id),
            role text not null,
            content text not null,
            intent text not null default '',
            confidence real,
            decision_id text not null default '',
            citations text not null default '[]',
            evidence_ref text not null default '{}',
            actor text not null default '',
            created_at timestamp not null default current_timestamp
        )""",
        "mysql": """
        create table if not exists conversation_message (
            id integer primary key auto_increment,
            conversation_id integer not null,
            role varchar(32) not null,
            content text not null,
            intent varchar(100) not null default '',
            confidence double,
            decision_id varchar(255) not null default '',
            citations text,
            evidence_ref text,
            actor varchar(255) not null default '',
            created_at datetime not null default current_timestamp
        )""",
    },
    {
        "sqlite": """
        create table if not exists answer_feedback (
            id integer primary key autoincrement,
            message_id integer not null references conversation_message(id),
            conversation_id integer not null references conversation(id),
            rating text not null,
            comment text not null default '',
            correction text not null default '',
            decision_id text not null default '',
            object_code text not null default '',
            rule_code text not null default '',
            status text not null default 'open',
            actor text not null default '',
            resolved_by text not null default '',
            resolved_at text,
            created_at text not null default current_timestamp
        )""",
        "postgresql": """
        create table if not exists answer_feedback (
            id serial primary key,
            message_id integer not null references conversation_message(id),
            conversation_id integer not null references conversation(id),
            rating text not null,
            comment text not null default '',
            correction text not null default '',
            decision_id text not null default '',
            object_code text not null default '',
            rule_code text not null default '',
            status text not null default 'open',
            actor text not null default '',
            resolved_by text not null default '',
            resolved_at timestamp,
            created_at timestamp not null default current_timestamp
        )""",
        "mysql": """
        create table if not exists answer_feedback (
            id integer primary key auto_increment,
            message_id integer not null,
            conversation_id integer not null,
            rating varchar(50) not null,
            comment text,
            correction text,
            decision_id varchar(255) not null default '',
            object_code varchar(255) not null default '',
            rule_code varchar(255) not null default '',
            status varchar(50) not null default 'open',
            actor varchar(255) not null default '',
            resolved_by varchar(255) not null default '',
            resolved_at datetime,
            created_at datetime not null default current_timestamp
        )""",
    },
)


SCHEMA = SchemaBundle(name="conversations", tables=CONVERSATION_SCHEMA)


def init_conversation_schema(conn: Any) -> None:
    """Create the conversation, message and feedback tables."""
    SCHEMA.apply(conn)


def ensure_conversation(
    platform_db: PlatformDb,
    session_id: Optional[str] = None,
    *,
    role_id: str = "",
    data_source_id: Optional[int] = None,
    ontology_id: Optional[int] = None,
    object_code: str = "",
    actor: str = "",
    title: str = "",
) -> dict[str, Any]:
    """Find or create the conversation for a session id.

    Returns the row as a dict. A caller that passes no session id gets a fresh
    conversation, so the common "just start chatting" path needs no setup.
    """
    resolved = (session_id or "").strip() or _new_id()
    with connect(platform_db) as conn:
        row = conn.execute("select * from conversation where session_id = ?", (resolved,)).fetchone()
        if row is not None:
            return _conversation_dict(row)
        conn.execute(
            """
            insert into conversation
                (session_id, title, role_id, data_source_id, ontology_id, object_code, actor)
            values (?, ?, ?, ?, ?, ?, ?)
            """,
            (resolved, title[:200], role_id, data_source_id, ontology_id, object_code, actor),
        )
        conversation_id = last_insert_id(conn)
        row = conn.execute("select * from conversation where id = ?", (conversation_id,)).fetchone()
    return _conversation_dict(row)


def _conversation_dict(row: Any) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "sessionId": row["session_id"],
        "title": row["title"],
        "roleId": row["role_id"],
        "dataSourceId": row["data_source_id"],
        "ontologyId": row["ontology_id"],
        "objectCode": row["object_code"],
        "status": row["status"],
        "actor": row["actor"],
        "escalatedTo": row["escalated_to"],
        "escalationReason": row["escalation_reason"],
        "messageCount": int(row["message_count"] or 0),
        "createdAt": str(row["created_at"]),
        "updatedAt": str(row["updated_at"]),
    }


def append_message(
    platform_db: PlatformDb,
    session_id: str,
    role: str,
    content: str,
    *,
    intent: str = "",
    confidence: Optional[float] = None,
    decision_id: str = "",
    citations: Optional[list[dict[str, Any]]] = None,
    evidence_ref: Optional[dict[str, Any]] = None,
    actor: str = "",
) -> dict[str, Any]:
    """Record one turn.

    `decision_id` and `citations` are stored on the assistant turn so feedback can
    reach the verdict and the textual authority behind it. Without that link,
    「这个判定不对」 is an opinion with nothing attached.
    """
    if role not in {"user", "assistant", "system"}:
        raise ValueError(f"不支持的消息角色: {role}")
    conversation = ensure_conversation(platform_db, session_id, actor=actor)
    with connect(platform_db) as conn:
        conn.execute(
            """
            insert into conversation_message
                (conversation_id, role, content, intent, confidence, decision_id,
                 citations, evidence_ref, actor)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                conversation["id"],
                role,
                content,
                intent,
                confidence,
                decision_id,
                json.dumps(citations or [], ensure_ascii=False, default=str),
                json.dumps(evidence_ref or {}, ensure_ascii=False, default=str),
                actor,
            ),
        )
        message_id = last_insert_id(conn)
        # The first user turn names the conversation, so the list is scannable
        # without opening each thread.
        if role == "user" and not conversation["title"]:
            conn.execute(
                "update conversation set title = ? where id = ?",
                (content[:60], conversation["id"]),
            )
        conn.execute(
            """
            update conversation
            set message_count = message_count + 1, updated_at = current_timestamp
            where id = ?
            """,
            (conversation["id"],),
        )
    return {"messageId": message_id, "conversationId": conversation["id"], "sessionId": conversation["sessionId"]}


def load_history(platform_db: PlatformDb, session_id: str, *, limit: int = MAX_HISTORY_TURNS) -> list[dict[str, str]]:
    """Recent turns in the shape the model client expects.

    Returns the *last* `limit` turns in chronological order: a model prompt needs
    the most recent context, but in the order it was said.
    """
    capped = max(1, min(int(limit), 100))
    with connect(platform_db) as conn:
        conversation = conn.execute("select id from conversation where session_id = ?", (session_id,)).fetchone()
        if conversation is None:
            return []
        rows = conn.execute(
            """
            select role, content from conversation_message
            where conversation_id = ? and role in ('user', 'assistant')
            order by id desc
            limit ?
            """,
            (int(conversation["id"]), capped),
        ).fetchall()
    return [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]


def list_conversations(platform_db: PlatformDb, *, status: str = "", limit: int = 50) -> list[dict[str, Any]]:
    capped = max(1, min(int(limit), 200))
    clauses = []
    params: list[Any] = []
    if status:
        clauses.append("status = ?")
        params.append(status)
    where = f"where {' and '.join(clauses)}" if clauses else ""
    params.append(capped)
    with connect(platform_db) as conn:
        rows = conn.execute(
            f"select * from conversation {where} order by updated_at desc, id desc limit ?",
            tuple(params),
        ).fetchall()
    return [_conversation_dict(row) for row in rows]


def get_conversation(platform_db: PlatformDb, session_id: str) -> dict[str, Any]:
    """One conversation with its messages and any feedback on them."""
    with connect(platform_db) as conn:
        row = conn.execute("select * from conversation where session_id = ?", (session_id,)).fetchone()
        if row is None:
            raise ValueError(f"会话不存在: {session_id}")
        conversation = _conversation_dict(row)
        messages = conn.execute(
            """
            select id, role, content, intent, confidence, decision_id, citations, actor, created_at
            from conversation_message where conversation_id = ? order by id
            """,
            (conversation["id"],),
        ).fetchall()
        feedback_rows = conn.execute(
            "select * from answer_feedback where conversation_id = ? order by id",
            (conversation["id"],),
        ).fetchall()

    feedback_by_message: dict[int, list[dict[str, Any]]] = {}
    for entry in feedback_rows:
        feedback_by_message.setdefault(int(entry["message_id"]), []).append(_feedback_dict(entry))

    conversation["messages"] = [
        {
            "id": int(message["id"]),
            "role": message["role"],
            "content": message["content"],
            "intent": message["intent"],
            "confidence": message["confidence"],
            "decisionId": message["decision_id"],
            "citations": _load_json(message["citations"], []),
            "actor": message["actor"],
            "createdAt": str(message["created_at"]),
            "feedback": feedback_by_message.get(int(message["id"]), []),
        }
        for message in messages
    ]
    return conversation


def _load_json(raw: Any, default: Any) -> Any:
    try:
        return json.loads(raw) if raw else default
    except (TypeError, ValueError):
        return default


def _feedback_dict(row: Any) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "messageId": int(row["message_id"]),
        "conversationId": int(row["conversation_id"]),
        "rating": row["rating"],
        "comment": row["comment"] or "",
        "correction": row["correction"] or "",
        "decisionId": row["decision_id"] or "",
        "objectCode": row["object_code"] or "",
        "ruleCode": row["rule_code"] or "",
        "status": row["status"],
        "actor": row["actor"],
        "resolvedBy": row["resolved_by"] or "",
        "resolvedAt": str(row["resolved_at"]) if row["resolved_at"] else "",
        "createdAt": str(row["created_at"]),
    }


def submit_feedback(
    platform_db: PlatformDb,
    message_id: int,
    rating: str,
    *,
    comment: str = "",
    correction: str = "",
    object_code: str = "",
    rule_code: str = "",
    actor: str = "",
) -> dict[str, Any]:
    """Record a verdict on one answer.

    The decision id is copied from the message rather than taken from the caller,
    so feedback cannot be attached to a decision the message did not produce.

    A correction is *stored*, never applied. It is one user's claim; turning it
    into a rule or a knowledge entry goes through governance (ADR-0002, ADR-0009).
    """
    if rating not in FEEDBACK_RATINGS:
        raise ValueError(f"不支持的反馈类型: {rating}。可选: {'、'.join(FEEDBACK_RATINGS)}")
    with connect(platform_db) as conn:
        message = conn.execute(
            "select id, conversation_id, decision_id from conversation_message where id = ?",
            (message_id,),
        ).fetchone()
        if message is None:
            raise ValueError(f"消息不存在: {message_id}")
        conn.execute(
            """
            insert into answer_feedback
                (message_id, conversation_id, rating, comment, correction,
                 decision_id, object_code, rule_code, actor)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message_id,
                int(message["conversation_id"]),
                rating,
                comment,
                correction,
                message["decision_id"] or "",
                object_code,
                rule_code,
                actor,
            ),
        )
        feedback_id = last_insert_id(conn)
        conn.execute(
            "insert into audit_log (actor, action, target_type, target_id, detail) values (?, ?, ?, ?, ?)",
            (
                actor or "anonymous",
                "submit_answer_feedback",
                "conversation_message",
                str(message_id),
                json.dumps(
                    {
                        "rating": rating,
                        "decisionId": message["decision_id"] or "",
                        "hasCorrection": bool(correction),
                    },
                    ensure_ascii=False,
                ),
            ),
        )
    return {
        "id": feedback_id,
        "messageId": message_id,
        "rating": rating,
        "decisionId": message["decision_id"] or "",
        "status": "open",
        "note": "纠正内容已记录，不会自动生效；如需成为规则或知识条目，请走治理流程。",
    }


def resolve_feedback(
    platform_db: PlatformDb, feedback_id: int, *, resolution: str = "resolved", actor: str = ""
) -> dict[str, Any]:
    """Close a feedback item after acting on it."""
    if resolution not in {"resolved", "dismissed", "open"}:
        raise ValueError(f"不支持的处理结果: {resolution}")
    with connect(platform_db) as conn:
        row = conn.execute("select id from answer_feedback where id = ?", (feedback_id,)).fetchone()
        if row is None:
            raise ValueError(f"反馈不存在: {feedback_id}")
        conn.execute(
            "update answer_feedback set status = ?, resolved_by = ?, resolved_at = current_timestamp where id = ?",
            (resolution, actor, feedback_id),
        )
    return {"id": feedback_id, "status": resolution, "resolvedBy": actor}


def escalate_conversation(
    platform_db: PlatformDb,
    session_id: str,
    *,
    assignee: str = "",
    reason: str = "",
    actor: str = "",
) -> dict[str, Any]:
    """Hand a conversation to a human.

    Escalation is a status on the conversation rather than only a log line, so it
    shows up in the queue an operator actually works from.
    """
    with connect(platform_db) as conn:
        row = conn.execute("select id, status from conversation where session_id = ?", (session_id,)).fetchone()
        if row is None:
            raise ValueError(f"会话不存在: {session_id}")
        conn.execute(
            """
            update conversation
            set status = 'escalated', escalated_to = ?, escalation_reason = ?,
                updated_at = current_timestamp
            where id = ?
            """,
            (assignee, reason, int(row["id"])),
        )
        conn.execute(
            "insert into audit_log (actor, action, target_type, target_id, detail) values (?, ?, ?, ?, ?)",
            (
                actor or "anonymous",
                "escalate_conversation",
                "conversation",
                session_id,
                json.dumps({"assignee": assignee, "reason": reason}, ensure_ascii=False),
            ),
        )
    return {"sessionId": session_id, "status": "escalated", "escalatedTo": assignee, "reason": reason}


def set_conversation_status(
    platform_db: PlatformDb, session_id: str, status: str, *, actor: str = ""
) -> dict[str, Any]:
    if status not in CONVERSATION_STATUSES:
        raise ValueError(f"不支持的会话状态: {status}。可选: {'、'.join(CONVERSATION_STATUSES)}")
    with connect(platform_db) as conn:
        row = conn.execute("select id from conversation where session_id = ?", (session_id,)).fetchone()
        if row is None:
            raise ValueError(f"会话不存在: {session_id}")
        conn.execute(
            "update conversation set status = ?, updated_at = current_timestamp where id = ?",
            (status, int(row["id"])),
        )
    return {"sessionId": session_id, "status": status, "actor": actor}


def list_feedback(
    platform_db: PlatformDb, *, status: str = "", rating: str = "", limit: int = 100
) -> list[dict[str, Any]]:
    capped = max(1, min(int(limit), 500))
    clauses = []
    params: list[Any] = []
    if status:
        clauses.append("status = ?")
        params.append(status)
    if rating:
        clauses.append("rating = ?")
        params.append(rating)
    where = f"where {' and '.join(clauses)}" if clauses else ""
    params.append(capped)
    with connect(platform_db) as conn:
        rows = conn.execute(f"select * from answer_feedback {where} order by id desc limit ?", tuple(params)).fetchall()
    return [_feedback_dict(row) for row in rows]


def feedback_summary(platform_db: PlatformDb) -> dict[str, Any]:
    """Aggregate counts for the workbench.

    Reports raw counts rather than an average score: an average tells you nothing
    about which answer to fix, and this project's whole premise is traceability to
    a specific case.
    """
    with connect(platform_db) as conn:
        by_rating = {
            row["rating"]: int(row["count"])
            for row in conn.execute("select rating, count(*) as count from answer_feedback group by rating").fetchall()
        }
        open_items = conn.execute("select count(*) as count from answer_feedback where status = 'open'").fetchone()
        corrections = conn.execute("select count(*) as count from answer_feedback where correction != ''").fetchone()
        escalated = conn.execute("select count(*) as count from conversation where status = 'escalated'").fetchone()
        conversations = conn.execute("select count(*) as count from conversation").fetchone()
    return {
        "total": sum(by_rating.values()),
        "byRating": by_rating,
        "helpful": by_rating.get("helpful", 0),
        "unhelpful": by_rating.get("unhelpful", 0),
        "incorrect": by_rating.get("incorrect", 0),
        "openItems": int(open_items["count"] or 0) if open_items else 0,
        "corrections": int(corrections["count"] or 0) if corrections else 0,
        "escalatedConversations": int(escalated["count"] or 0) if escalated else 0,
        "conversations": int(conversations["count"] or 0) if conversations else 0,
    }
