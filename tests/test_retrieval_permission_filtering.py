"""检索期权限过滤。ROADMAP 阶段 B 的最后一项。

多租户隔离已经做了，权限策略也已经带本体维度并真实求值。但两者之间有一条缝：
**知识条目的候选集按本体与锚点过滤，不按调用者的对象权限过滤。**

于是一个只能读「客户」的角色，问一个关于客户的问题时，
答案里可以引用锚定在「合同」上的条款原文——而那正是对象权限本该保护的东西。
一旦文本进了答案，它就已经被披露了。

这一层刻意放在**锚定之后、排序之前**：在排序之后再丢，
意味着已经用不该看的文本决定了展示什么。
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from ontology_platform.database import connect, initialize_platform_db
from ontology_platform.retrieval import filter_entries_for_role
from ontology_platform.workflow_permission import (
    create_role,
    init_workflow_and_permission_schema,
    upsert_permission_policy,
)


def _entry(entry_id: int, object_code: str) -> dict:
    return {"id": entry_id, "objectCode": object_code, "content": f"{object_code} 的条款原文", "title": "t"}


@pytest.fixture
def platform_db(tmp_path: Path) -> Path:
    """一个只允许 `alpha` 角色读 `alpha` 对象的策略集。"""
    path = tmp_path / "platform.sqlite3"
    initialize_platform_db(path)
    with connect(path) as conn:
        init_workflow_and_permission_schema(conn)
        conn.execute("insert into ontology (name, domain, version, status) values ('测试', '通用', 'v1', 'draft')")
    role = create_role(path, "alpha_reader", "Alpha 只读")
    upsert_permission_policy(
        path,
        int(role["id"]),
        "alpha",
        can_read=True,
        ontology_id=1,
    )
    # `beta` 未授权：策略表 deny-by-default，因此不需要显式拒绝条目。
    return path


def test_an_entry_the_role_may_read_survives(platform_db: Path) -> None:
    entries = [_entry(1, "alpha")]
    kept = filter_entries_for_role(platform_db, entries, role_code="alpha_reader", ontology_id=1)
    assert [item["id"] for item in kept] == [1]


def test_an_entry_anchored_to_a_forbidden_object_is_dropped(platform_db: Path) -> None:
    """核心缺口。锚定让引用**可归因**，不代表它**被许可**。"""
    entries = [_entry(1, "alpha"), _entry(2, "beta")]
    kept = filter_entries_for_role(platform_db, entries, role_code="alpha_reader", ontology_id=1)
    assert [item["id"] for item in kept] == [1], "beta 条目不应出现在候选集中"


def test_forbidden_content_never_reaches_the_caller(platform_db: Path) -> None:
    """断言的是内容本身不出现，而不只是 id 被过滤——文本进了答案就等于已披露。"""
    entries = [_entry(1, "alpha"), _entry(2, "beta")]
    kept = filter_entries_for_role(platform_db, entries, role_code="alpha_reader", ontology_id=1)
    assert not any("beta" in str(item.get("content", "")) for item in kept)


def test_an_unauthenticated_call_gets_nothing(platform_db: Path) -> None:
    """没有身份就没有披露依据。丢一条引用只是降级答案，多给一条则是泄露文档——
    两种失败不对称（ADR-0002）。"""
    entries = [_entry(1, "alpha")]
    kept = filter_entries_for_role(platform_db, entries, role_code="", ontology_id=1)
    assert kept == []


def test_an_unknown_role_gets_nothing(platform_db: Path) -> None:
    """未登记的角色走 deny-by-default，而不是被当作宽松处理。"""
    entries = [_entry(1, "alpha")]
    kept = filter_entries_for_role(platform_db, entries, role_code="ghost_role", ontology_id=1)
    assert kept == []


def test_a_failing_permission_check_denies_rather_than_allows(tmp_path: Path) -> None:
    """权限表不存在时判定会失败。此时必须拒绝——
    「判不出来就放行」正是 ADR-0002 要防的那类失败。"""
    bare = tmp_path / "bare.sqlite3"
    initialize_platform_db(bare)
    entries = [_entry(1, "alpha")]
    kept = filter_entries_for_role(bare, entries, role_code="alpha_reader", ontology_id=1)
    assert kept == []


def test_an_entry_without_an_object_anchor_is_kept(platform_db: Path) -> None:
    """本体级文本对能读该本体的人可见——而他们显然能读，否则拿不到这次判定。"""
    entries = [{"id": 9, "objectCode": "", "content": "本体级说明"}]
    kept = filter_entries_for_role(platform_db, entries, role_code="alpha_reader", ontology_id=1)
    assert [item["id"] for item in kept] == [9]


def test_the_permission_decision_is_made_once_per_anchor(platform_db: Path, monkeypatch) -> None:
    """一份文档会切成几十个块。逐块判定会把策略读放大几十倍。"""
    calls: list[str] = []
    import ontology_platform.workflow_permission as permissions

    original = permissions.check_permission

    def counting(platform, role_code, object_code, operation="read", **kwargs):
        calls.append(object_code)
        return original(platform, role_code, object_code, operation, **kwargs)

    monkeypatch.setattr(permissions, "check_permission", counting)
    entries = [_entry(index, "alpha") for index in range(1, 21)]
    kept = filter_entries_for_role(platform_db, entries, role_code="alpha_reader", ontology_id=1)
    assert len(kept) == 20
    assert calls.count("alpha") == 1, f"应只判定一次，实际 {calls.count('alpha')} 次"


# -- 贯穿问答链路 --


@pytest.fixture
def qa_scenario(tmp_path: Path):
    """含两个对象的真实场景，其中一个角色只被授权读其中之一。"""
    from ontology_platform.metadata import register_data_source, scan_data_source
    from ontology_platform.ontology import generate_ontology_draft

    source = tmp_path / "business.sqlite3"
    conn = sqlite3.connect(source)
    conn.executescript(
        """
        create table customers (id integer primary key, name text not null, credit_status text not null);
        create table contracts (
            id integer primary key,
            customer_id integer not null references customers(id),
            amount numeric not null,
            status text not null
        );
        insert into customers values (1, '甲公司', 'normal');
        insert into contracts values (1, 1, 50000, 'effective');
        """
    )
    conn.commit()
    conn.close()

    platform_db = tmp_path / "platform.sqlite3"
    initialize_platform_db(platform_db)
    with connect(platform_db) as conn:
        init_workflow_and_permission_schema(conn)
    data_source = register_data_source(platform_db, "合同系统", "sqlite", str(source), domain="合同管理")
    scan_data_source(platform_db, data_source.id)
    ontology_id = generate_ontology_draft(platform_db, data_source.id)["ontology"]["id"]
    with connect(platform_db) as conn:
        codes = {
            row["table_name"]: row["code"]
            for row in conn.execute(
                """
                select bo.code, st.table_name from business_object bo
                join source_table st on st.id = bo.source_table_id
                where bo.ontology_id = ?
                """,
                (ontology_id,),
            ).fetchall()
        }
    return {
        "platform_db": platform_db,
        "ontology_id": ontology_id,
        "codes": codes,
    }


def test_the_question_answering_path_accepts_a_role(qa_scenario) -> None:
    """接口必须能接收调用者身份，否则过滤无从发生。"""
    from ontology_platform.natural_language import query_natural_language

    result = query_natural_language(
        qa_scenario["platform_db"],
        "整体合规情况如何？",
        ontology_id=qa_scenario["ontology_id"],
        use_model=False,
        role_code="analyst",
    )
    assert result["answer"]


def test_the_api_takes_the_role_from_the_authenticated_identity() -> None:
    """调用方若能自报角色，就等于给自己授权任意文档。

    以源码断言，因为这是一条**不该存在**的数据流——运行时测试只能证明当前路径正确，
    无法阻止有人日后从请求体里读它。

    按 AST 取函数体，而不是按装饰器文本切片。原实现以 `api.index("@app.", ...)` 定位
    下一个端点，因此把路由改挂到 `APIRouter` 上就让它抛异常——一条安全不变量不应该
    因为一次纯结构调整而失效，何况「找不到分隔符」与「检查通过」在当时几乎无从区分。
    """
    import ast

    source = (ROOT / "backend" / "ontology_platform" / "api.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    functions = {
        node.name: node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    # 问答与智能体端点不得从请求体取权限角色。
    # （`payload.roleCode` 在创建用户端点里是正当的：那是管理员为**他人**指定角色，
    #  且该端点本身需要 platform:admin。）
    for handler in ("ask_semantic_kernel", "chat_with_agent"):
        assert handler in functions, f"未找到端点 {handler}——若已改名，请同步本测试而不是删除它"
        body = ast.unparse(functions[handler])
        assert "role_code=principal.role_code" in body, f"{handler} 未使用认证身份的角色"
        assert "payload.roleCode" not in body, f"{handler} 从请求体取了权限角色"


def test_the_agent_path_passes_the_permission_role_not_the_persona() -> None:
    """`roleId` 是智能体人格（业务视角措辞），不是授权。混用会让选个人格即提权。"""
    agent = (ROOT / "backend" / "ontology_platform" / "agent.py").read_text(encoding="utf-8")
    assert "role_code=role_code" in agent
    api = (ROOT / "backend" / "ontology_platform" / "api.py").read_text(encoding="utf-8")
    assert "role_code=principal.role_code" in api


def test_filtering_happens_between_anchoring_and_ranking() -> None:
    """排序之后再丢，意味着已经用不该看的文本决定了展示什么。

    以源码顺序断言：这是一个顺序性属性，行为测试无法区分「过滤在排序前」与「过滤在排序后
    但结果恰好相同」。
    """
    source = (ROOT / "backend" / "ontology_platform" / "natural_language.py").read_text(encoding="utf-8")
    filter_at = source.index("filter_entries_for_role(")
    rank_at = source.index("hits = retrieve(")
    assert filter_at < rank_at, "权限过滤必须出现在排序之前"
