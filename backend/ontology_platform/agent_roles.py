"""Agent roles derived from onboarded domains.

Shipping a fixed set of personas ("contract expert", "equipment expert") caps
the platform at the industries someone thought of in advance. Instead a role is
produced for each business domain that has actually been onboarded, with its
prompt built from that domain's ontology: objects, relationships and rule
counts. Deployments needing bespoke wording can persist custom roles.

No industry vocabulary appears in this module.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from .database import connect


logger = logging.getLogger(__name__)

GENERIC_ROLE_ID = "domain-expert"
GENERIC_ROLE_NAME = "业务语义专家"

# The prompt is domain neutral; every business specific sentence is filled from
# the ontology at request time.
SYSTEM_PROMPT_TEMPLATE = """你是{domain_clause}的资深业务专家，同时具备本体语义内核的研判能力。
你的职责是帮助用户理解业务数据、审查合规性、识别风险、预检操作条件。

## 当前领域知识
{knowledge_summary}

## 核心能力
- 实例解读：解释业务对象的关键属性、关联对象和当前状态
- 合规研判：基于已确认的业务规则判断实例是否合规
- 操作预检：判断实例是否满足执行某项业务操作的条件
- 风险识别：发现数据和流程中的潜在风险
- 规则查询：查看某个业务对象相关的规则与约束

## 工作原则
1. 所有合规、风险判断必须基于本体规则引擎的实际结果，不得编造
2. 回答像资深业务专家在对话：先直接回应问题，再用关键事实支撑
3. 语气专业但易懂，避免系统术语和模板化表达
4. 如果证据不足以得出结论，如实告知并建议补充信息
5. 用户未指定具体实例时，可给出整体概览；指定后聚焦该实例
6. 主动提示后续可能有用的操作
7. 只讨论当前领域知识中确实存在的业务对象，不要臆造对象或字段
"""


SCHEMA_SQL: tuple[dict[str, str], ...] = (
    {
        "sqlite": """
        create table if not exists agent_role (
            id integer primary key autoincrement,
            code text not null unique,
            name text not null,
            description text not null default '',
            domain text not null default '',
            system_prompt text not null default '',
            data_source_id integer references data_source(id),
            created_at text not null default current_timestamp,
            updated_at text not null default current_timestamp
        )""",
        "postgresql": """
        create table if not exists agent_role (
            id serial primary key,
            code text not null unique,
            name text not null,
            description text not null default '',
            domain text not null default '',
            system_prompt text not null default '',
            data_source_id integer references data_source(id),
            created_at timestamp not null default current_timestamp,
            updated_at timestamp not null default current_timestamp
        )""",
        "mysql": """
        create table if not exists agent_role (
            id integer primary key auto_increment,
            code varchar(191) not null unique,
            name varchar(255) not null,
            description text not null default (''),
            domain varchar(255) not null default '',
            system_prompt text not null default (''),
            data_source_id integer references data_source(id),
            created_at datetime not null default current_timestamp,
            updated_at datetime not null default current_timestamp
        )""",
    },
)


def init_agent_role_schema(conn: Any) -> None:
    from .database import _mysql_ddl, _postgresql_ddl, _sqlite_ddl

    db_type = getattr(getattr(conn, "_adapter", None), "db_type", "sqlite")
    for statement in SCHEMA_SQL:
        if db_type in ("postgresql", "postgres"):
            sql = _postgresql_ddl(statement)
        elif db_type == "mysql":
            sql = _mysql_ddl(statement)
        else:
            sql = _sqlite_ddl(statement)
        conn.execute(sql)


@dataclass(frozen=True)
class AgentRole:
    id: str
    name: str
    description: str
    domain: str
    system_prompt: str
    data_source_id: Optional[int] = None
    source: str = "derived"

    def public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "domain": self.domain,
            # The UI needs a stable short label; deriving it avoids a per-domain
            # icon table in the frontend.
            "avatar": _avatar_for(self.name, self.domain),
            "dataSourceId": self.data_source_id,
            "source": self.source,
        }


def _avatar_for(name: str, domain: str) -> str:
    """A one or two character label derived from the role name."""
    text = (domain or name or "").strip()
    if not text:
        return "AI"
    if re.match(r"^[\x00-\x7F]+$", text):
        parts = [part for part in re.split(r"[\s_-]+", text) if part]
        return "".join(part[0].upper() for part in parts[:2]) or text[:2].upper()
    return text[:2]


def slugify_domain(domain: str) -> str:
    """Stable role id for a domain name, including non-latin domains."""
    normalized = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "-", (domain or "").strip()).strip("-")
    if not normalized:
        return GENERIC_ROLE_ID
    if re.match(r"^[0-9a-zA-Z-]+$", normalized):
        return f"{normalized.lower()}-expert"
    # Non-latin domain names get an ascii-safe suffix. hashlib rather than
    # hash(), whose seed is randomized per process: a role id must stay stable
    # across restarts or saved selections and audit records would break.
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:8]
    return f"domain-{digest}-expert"


def list_agent_roles(platform_db: Path | str) -> list[AgentRole]:
    """Roles for every onboarded domain, plus any persisted custom roles."""
    roles: dict[str, AgentRole] = {}

    with connect(platform_db) as conn:
        domain_rows = conn.execute(
            """
            select ds.id as data_source_id, ds.name as source_name, ds.domain as domain,
                   count(distinct bo.id) as object_count
            from data_source ds
            join source_table st on st.data_source_id = ds.id
            join business_object bo on bo.source_table_id = st.id
            group by ds.id, ds.name, ds.domain
            order by ds.id
            """
        ).fetchall()

        custom_rows: list[Any] = []
        try:
            custom_rows = conn.execute(
                "select code, name, description, domain, system_prompt, data_source_id from agent_role order by id"
            ).fetchall()
        except Exception as error:
            logger.debug("自定义智能体角色表不可用: %s", error)

    for row in domain_rows:
        domain = (row["domain"] or "").strip()
        label = domain or row["source_name"]
        role_id = slugify_domain(domain) if domain else f"source-{row['data_source_id']}-expert"
        roles[role_id] = AgentRole(
            id=role_id,
            name=f"{label}业务专家",
            description=f"面向「{label}」领域的语义研判专家，覆盖 {row['object_count']} 个已建模业务对象。",
            domain=domain,
            system_prompt="",  # built per request against the live ontology
            data_source_id=int(row["data_source_id"]),
            source="derived",
        )

    for row in custom_rows:
        roles[row["code"]] = AgentRole(
            id=row["code"],
            name=row["name"],
            description=row["description"] or "",
            domain=row["domain"] or "",
            system_prompt=row["system_prompt"] or "",
            data_source_id=int(row["data_source_id"]) if row["data_source_id"] is not None else None,
            source="custom",
        )

    if not roles:
        roles[GENERIC_ROLE_ID] = generic_role()
    return list(roles.values())


def generic_role() -> AgentRole:
    """Fallback used before any data source has been onboarded."""
    return AgentRole(
        id=GENERIC_ROLE_ID,
        name=GENERIC_ROLE_NAME,
        description="通用业务语义专家。接入数据源并生成本体后，将按业务领域提供专属角色。",
        domain="",
        system_prompt="",
        source="generic",
    )


def resolve_agent_role(platform_db: Path | str, role_id: str | None) -> AgentRole:
    """Resolve a role id, falling back to the first available role."""
    available = list_agent_roles(platform_db)
    if role_id:
        for role in available:
            if role.id == role_id:
                return role
    return available[0] if available else generic_role()


def build_system_prompt(role: AgentRole, knowledge_context: dict[str, Any]) -> str:
    """Render the role prompt against the current ontology snapshot."""
    if role.system_prompt.strip():
        # A custom prompt may still use the same placeholders.
        template = role.system_prompt
    else:
        template = SYSTEM_PROMPT_TEMPLATE
    domain_clause = f"「{role.domain}」领域" if role.domain else "企业业务"
    return template.format(
        domain_clause=domain_clause,
        domain=role.domain or "业务",
        knowledge_summary=_summarize_knowledge(knowledge_context),
    )


def _summarize_knowledge(knowledge_context: dict[str, Any]) -> str:
    """Describe the modelled objects so the model cannot invent them."""
    if not knowledge_context.get("available"):
        return "当前尚未初始化任何业务知识库，请提示用户先接入数据源并生成本体。"
    objects = knowledge_context.get("objects") or []
    lines: list[str] = []
    name = knowledge_context.get("name") or ""
    domain = knowledge_context.get("domain") or ""
    if name:
        lines.append(f"- 业务系统：{name}" + (f"（领域：{domain}）" if domain else ""))
    if objects:
        rendered = []
        for item in objects[:20]:
            if isinstance(item, dict):
                code = item.get("code") or item.get("objectCode") or ""
                label = item.get("name") or code
                rendered.append(f"{label}({code})" if code and label != code else str(label or code))
            else:
                rendered.append(str(item))
        lines.append(f"- 可用业务对象：{'、'.join(rendered)}")
    rules = knowledge_context.get("rules") or []
    if rules:
        rule_names = "、".join(str(rule.get("name") or rule.get("code")) for rule in rules[:8])
        lines.append(f"- 相关业务规则：{rule_names}")
    relations = knowledge_context.get("relations") or []
    if relations:
        relation_names = "、".join(str(rel.get("name") or rel.get("code")) for rel in relations[:8])
        lines.append(f"- 相关关联关系：{relation_names}")
    return "\n".join(lines) if lines else "当前知识库暂无已建模的业务对象。"


def upsert_agent_role(
    platform_db: Path | str,
    code: str,
    name: str,
    description: str = "",
    domain: str = "",
    system_prompt: str = "",
    data_source_id: int | None = None,
    actor: str = "system",
) -> dict[str, Any]:
    """Persist a custom agent role."""
    normalized = re.sub(r"[^0-9a-zA-Z_-]+", "-", (code or "").strip()).strip("-").lower()
    if not normalized:
        raise ValueError("角色编码不能为空")
    if not (name or "").strip():
        raise ValueError("角色名称不能为空")
    with connect(platform_db) as conn:
        conn.execute(
            """
            insert into agent_role (code, name, description, domain, system_prompt, data_source_id)
            values (?, ?, ?, ?, ?, ?)
            on conflict(code) do update set
                name = excluded.name,
                description = excluded.description,
                domain = excluded.domain,
                system_prompt = excluded.system_prompt,
                data_source_id = excluded.data_source_id
            """,
            (normalized, name.strip(), description, domain, system_prompt, data_source_id),
        )
        conn.execute(
            "insert into audit_log (actor, action, target_type, target_id, detail) values (?, ?, ?, ?, ?)",
            (actor, "upsert_agent_role", "agent_role", normalized, json.dumps({"domain": domain}, ensure_ascii=False)),
        )
    return {"code": normalized, "name": name, "domain": domain, "source": "custom"}


def delete_agent_role(platform_db: Path | str, code: str, actor: str = "system") -> dict[str, Any]:
    with connect(platform_db) as conn:
        conn.execute("delete from agent_role where code = ?", (code,))
        conn.execute(
            "insert into audit_log (actor, action, target_type, target_id, detail) values (?, ?, ?, ?, ?)",
            (actor, "delete_agent_role", "agent_role", code, "{}"),
        )
    return {"deleted": True, "code": code}
