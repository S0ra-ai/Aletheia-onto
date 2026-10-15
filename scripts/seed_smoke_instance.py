#!/usr/bin/env python3
"""Populate a platform database so the render check has a table on every screen.

`aletheia demo` runs the whole loop -- source, scan, draft, verdict, event, value,
workflow -- and leaves eight screens with no rows to render: the knowledge base, the
feedback console, the permission and tool tables, tenancy, the backup list, the tool
review queue. A screen with no rows is a screen whose columns nobody has looked at, which
is how a column that renders blank for every row survives: **an empty table makes every
column look correct**, and eight of those defects were found only after somebody seeded
one by hand.

This is that seeding, as a script rather than as an afternoon. It is deliberately not part
of the platform: nothing here is a feature, and a deployment should never run it.

Usage:

    python scripts/seed_smoke_instance.py --platform-db /path/to/platform.sqlite3

It is additive and idempotent enough to re-run: the pieces that would collide are checked
first, and a second run changes nothing.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from ontology_platform.backup import create_backup
from ontology_platform.context import PlatformContext
from ontology_platform.database import connect
from ontology_platform.knowledge_base import initialize_knowledge_base
from ontology_platform.tenancy import provision_tenant
from ontology_platform.workflow_permission import (
    create_role,
    init_workflow_and_permission_schema,
    register_tool,
    upsert_permission_policy,
)

POLICY_DOCUMENT = """合同审批制度

第一条 合同金额超过一百万元的，应当由业务部门负责人审批后，再提交法务复核。
第二条 客户处于黑名单状态的，不得签订新合同。
"""


def seed(platform_db: Path) -> dict[str, object]:
    done: dict[str, object] = {}

    # A knowledge base, which also gives the ontology detail page a document and an entry.
    ontology_id = _first_ontology_id(platform_db)
    if ontology_id is None:
        raise SystemExit("平台库还没有本体：先运行 `aletheia demo`")
    initialize_knowledge_base(platform_db, _first_source_id(platform_db))
    done["knowledgeBase"] = True

    with connect(platform_db) as conn:
        init_workflow_and_permission_schema(conn)
        role = conn.execute("select id from permission_role order by id limit 1").fetchone()
        if role is None:
            role_id = int(create_role(platform_db, "reviewer", "审核员", "渲染检查用")["id"])
        else:
            role_id = int(role[0])
        existing_policy = conn.execute(
            "select id from permission_policy where role_id = ? and object_code = 'contract'", (role_id,)
        ).fetchone()
        tool = conn.execute("select id from tool_definition where code = 'smoke_submit'").fetchone()

    if existing_policy is None:
        upsert_permission_policy(
            platform_db, role_id, "contract", can_read=True, can_write=True, description="渲染检查用"
        )
    done["policy"] = True

    if tool is None:
        tool_id = int(
            register_tool(
                platform_db,
                "smoke_submit",
                "提交（渲染检查）",
                tool_type="mutation",
                input_schema="{}",
                risk_level="high",
                requires_review=True,
            )["id"]
        )
        # One execution waiting for review, so the queue has a row. Without it that table is
        # empty on every deployment -- which is exactly how its eight blank columns survived.
        with connect(platform_db) as conn:
            conn.execute(
                "insert into tool_execution_log (tool_id, tool_code, agent_role, object_code, instance_id,"
                " input_args, result_summary, status, error, duration_ms, requires_review)"
                " values (?, 'smoke_submit', 'reviewer', 'contract', '1', '{}', '', 'success', '', 12, 1)",
                (tool_id,),
            )
    done["tools"] = True

    with connect(platform_db) as conn:
        has_tenant = conn.execute("select 1 from tenant_quota limit 1").fetchone() is not None
    if not has_tenant:
        provision_tenant(PlatformContext(db_type="sqlite", connection_uri=str(platform_db)), "smoke")
    done["tenant"] = True

    backup_dir = _backup_directory()
    create_backup(platform_db, "smoke", backup_dir=backup_dir)
    done["backup"] = str(backup_dir)

    with connect(platform_db) as conn:
        document = conn.execute("select id from knowledge_document order by id limit 1").fetchone()
        has_entry = conn.execute("select 1 from knowledge_entry limit 1").fetchone() is not None
        has_invocation = conn.execute("select 1 from model_invocation limit 1").fetchone() is not None
    if document is not None and not has_entry:
        with connect(platform_db) as conn:
            conn.execute(
                "insert into knowledge_entry (document_id, ordinal, citation, heading, content,"
                " object_code, rule_code, status, reviewer)"
                " values (?, 1, '第 1 段', '合同审批制度', ?, 'contract', '', 'confirmed', 'smoke')",
                (int(document[0]), POLICY_DOCUMENT.strip()),
            )
    done["knowledgeEntry"] = True

    if not has_invocation:
        # The model-invocation table is where four columns once rendered blank for every row,
        # and it stayed invisible afterwards because no screen had a row to check: the demo
        # never calls a model. A synthetic invocation is not a claim that one happened -- this
        # script exists so that every table has a row to render, and it says so at the top.
        with connect(platform_db) as conn:
            conn.execute(
                "insert into model_invocation (provider, model, purpose, prompt_tokens, completion_tokens,"
                " total_tokens, status, error) values ('openai-compatible', 'smoke-model', 'render-check',"
                " 120, 40, 160, 'success', '')"
            )
    done["modelInvocation"] = True

    return done


def _backup_directory() -> Path:
    """Where the platform itself keeps backups.

    Not a temporary directory: a backup written somewhere the application does not look is a
    row that exists only for the person who wrote it, so the backup screen stayed empty on
    every machine while the seeding reported `"backup": ".../aletheia-smoke-backups"`.
    """
    from ontology_platform.backup import BACKUP_DIR

    return Path(BACKUP_DIR).expanduser()


def _first_ontology_id(platform_db: Path) -> int | None:
    with connect(platform_db) as conn:
        row = conn.execute("select id from ontology order by id limit 1").fetchone()
    return int(row[0]) if row else None


def _first_source_id(platform_db: Path) -> int:
    with connect(platform_db) as conn:
        row = conn.execute("select id from data_source order by id limit 1").fetchone()
    if row is None:
        raise SystemExit("平台库还没有数据源：先运行 `aletheia demo`")
    return int(row[0])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--platform-db", required=True, help="要填充的平台库")
    args = parser.parse_args()

    import json

    database = Path(args.platform_db)
    if not database.exists():
        print(f"平台库不存在: {database}", file=sys.stderr)
        return 2
    print(json.dumps(seed(database), ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
