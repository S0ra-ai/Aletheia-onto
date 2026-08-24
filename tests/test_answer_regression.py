"""问答回归测试集。ROADMAP 阶段 G。

平台的差异化主张是「结论可追问」——每个判定都能说出依据的规则、映射与来源行。
那是一句营销话术，除非它是**可回归的断言**。

## 这个测试集断言什么，不断言什么

它**不**断言答案的措辞。措辞会随提示词、模型、启发式排序而变，
锚定措辞的测试会在每次无害改动时失败，然后被改成宽松匹配，最后被删掉。

它断言的是**结构性属性**——那些一旦破坏，平台的卖点就不成立：

| 属性 | 破坏后果 |
|---|---|
| 结论必带依据 | 「可追问」不成立，退化为一个说不清的黑盒 |
| 意图路由确定 | 同一问题两次得到不同类型的答案 |
| 判定与问答一致 | 问答说合规、判定说阻断，用户无法知道该信哪个 |
| 无模型时仍可用 | 部署方必须先买模型订阅才能验证平台 |
| 未知问题明说未知 | 编造一个自信的答案，比说不知道危险得多 |

## 为什么走本地启发式路径

`use_model=False`。不是为了跑得快：**带模型的回归集会因为供应商改模型而失败**，
于是它会被标记为 flaky 并跳过——那时它就不再保护任何东西。
启发式路径是确定的，因此这些断言可以是硬断言。

模型只负责措辞；**结论与依据由内核产出**，而那正是这里要保护的部分。
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from ontology_platform.database import connect, initialize_platform_db
from ontology_platform.governance import upsert_business_rule
from ontology_platform.metadata import register_data_source, scan_data_source
from ontology_platform.natural_language import (
    INTENT_COMPLIANCE,
    INTENT_CONSISTENCY,
    INTENT_EXPLAIN,
    INTENT_KNOWLEDGE_OVERVIEW,
    INTENT_PREFLIGHT,
    INTENT_UNKNOWN,
    detect_intent,
    query_natural_language,
)
from ontology_platform.ontology import generate_ontology_draft
from ontology_platform.semantic_kernel import assess_instance


@pytest.fixture
def scenario(tmp_path: Path):
    """一个含违规实例的真实场景。

    刻意让 2 号实例违规：一个全部通过的场景无法证明「阻断时也给得出依据」，
    而那恰恰是最需要依据的时候。
    """
    source = tmp_path / "business.sqlite3"
    conn = sqlite3.connect(source)
    conn.executescript(
        """
        create table customers (
            id integer primary key,
            name text not null,
            credit_status text not null
        );
        create table contracts (
            id integer primary key,
            customer_id integer not null references customers(id),
            amount numeric not null,
            status text not null,
            signed_date text
        );
        insert into customers values (1, '甲公司', 'normal');
        insert into customers values (2, '乙公司', 'blacklist');
        -- 1 号合规；2 号金额超限且客户在黑名单。
        insert into contracts values (1, 1, 500, 'effective', '2026-01-01');
        insert into contracts values (2, 2, 50000, 'effective', '2026-02-01');
        """
    )
    conn.commit()
    conn.close()

    platform_db = tmp_path / "platform.sqlite3"
    initialize_platform_db(platform_db)
    data_source = register_data_source(platform_db, "合同系统", "sqlite", str(source), domain="合同管理")
    scan_data_source(platform_db, data_source.id)
    ontology_id = generate_ontology_draft(platform_db, data_source.id)["ontology"]["id"]
    with connect(platform_db) as conn:
        object_code = conn.execute(
            """
            select bo.code from business_object bo
            join source_table st on st.id = bo.source_table_id
            where bo.ontology_id = ? and st.table_name = 'contracts'
            """,
            (ontology_id,),
        ).fetchone()["code"]
    upsert_business_rule(
        platform_db,
        ontology_id,
        code="amount_ceiling",
        name="合同金额上限",
        rule_type="validation",
        scope_object_code=object_code,
        expression="amount <= 1000",
        severity="blocking",
        natural_language="合同金额不得超过 1000。",
        actor="regression",
    )
    return {
        "platform_db": platform_db,
        "ontology_id": ontology_id,
        "object_code": object_code,
        "data_source_id": data_source.id,
    }


def _ask(scenario, question: str, **kwargs) -> dict:
    return query_natural_language(
        scenario["platform_db"],
        question,
        ontology_id=scenario["ontology_id"],
        use_model=False,
        **kwargs,
    )


# -- 意图路由必须确定 --


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("这份合同合规吗？", INTENT_COMPLIANCE),
        ("是否满足放款条件？", INTENT_COMPLIANCE),
        ("有没有违规风险？", INTENT_COMPLIANCE),
        ("为什么是这个结果？", INTENT_EXPLAIN),
        ("这个实例有哪些字段？", INTENT_EXPLAIN),
        ("能否提交审批？", INTENT_PREFLIGHT),
        ("可以执行这个操作吗？", INTENT_PREFLIGHT),
        ("整体一致性如何？", INTENT_CONSISTENCY),
        ("批量情况怎么样？", INTENT_CONSISTENCY),
        ("有哪些业务规则？", INTENT_KNOWLEDGE_OVERVIEW),
        ("本体里有哪些对象？", INTENT_KNOWLEDGE_OVERVIEW),
    ],
)
def test_intent_routing_is_stable(question: str, expected: str) -> None:
    """同一问题必须始终路由到同一意图。

    不稳定的路由意味着用户问同一句话会得到不同**类型**的答案，
    而那比答案不准更难解释。
    """
    assert detect_intent(question) == expected


def test_an_unrecognised_question_is_not_forced_into_an_intent() -> None:
    """硬塞一个意图会让平台自信地回答一个它没理解的问题。"""
    assert detect_intent("今天天气怎么样") == INTENT_UNKNOWN


def test_intent_detection_is_deterministic() -> None:
    """两次相同输入必须得到相同意图，否则回归集本身失去意义。"""
    question = "这份合同合规吗？"
    assert len({detect_intent(question) for _ in range(5)}) == 1


# -- 结论必带依据 --


def test_a_compliance_answer_carries_its_evidence(scenario) -> None:
    """核心主张。没有依据的结论就是一个说不清的黑盒。"""
    result = _ask(scenario, "这份合同合规吗？", object_code=scenario["object_code"], instance_id="2")
    assert result["answer"], "必须给出答案"
    evidence = result.get("evidence") or {}
    assert evidence, "结论必须附带 evidence"
    rules = evidence.get("ruleResults") or []
    assert rules, "合规类结论必须列出参与判定的规则"
    # 违规实例：必须能指出是哪条规则不通过，而不只是说「不合规」。
    failed = [rule for rule in rules if not rule.get("passed")]
    assert failed, "2 号实例违规，必须有未通过的规则"
    assert any(rule.get("ruleCode") for rule in failed), "未通过的规则必须有规则编码"


def test_a_failed_rule_states_its_business_meaning(scenario) -> None:
    """规则编码给工程师看，自然语言给业务人员看。缺后者，判定就无法被业务复核。"""
    result = _ask(scenario, "这份合同合规吗？", object_code=scenario["object_code"], instance_id="2")
    rules = (result.get("evidence") or {}).get("ruleResults") or []
    ceiling = next((rule for rule in rules if rule.get("ruleCode") == "amount_ceiling"), None)
    assert ceiling is not None, "自定义规则必须参与判定"
    assert ceiling.get("naturalLanguage"), "规则必须带业务语言说明"


def test_an_explanation_names_the_source_of_each_value(scenario) -> None:
    """可追问意味着能一路追到来源列，否则「依据」只是另一层不透明。"""
    result = _ask(scenario, "为什么是这个结果？", object_code=scenario["object_code"], instance_id="2")
    evidence = result.get("evidence") or {}
    attributes = evidence.get("attributes") or []
    assert attributes, "解释必须列出属性"
    assert any(item.get("sourceColumn") for item in attributes), "属性必须能追溯到来源列"


def test_every_answer_reports_which_ontology_version_it_used(scenario) -> None:
    """本体是版本化的。不记录版本，事后就无法重现当时的判定。"""
    result = _ask(scenario, "这份合同合规吗？", object_code=scenario["object_code"], instance_id="1")
    resolved = result.get("resolved") or {}
    assert resolved.get("ontologyId") == scenario["ontology_id"]


# -- 问答与判定必须一致 --


def test_the_answer_agrees_with_the_kernels_verdict(scenario) -> None:
    """两条路径给出矛盾结论时，用户无法知道该信哪个——而这比任一条错更糟。"""
    verdict = assess_instance(scenario["platform_db"], scenario["ontology_id"], scenario["object_code"], "2")
    answer = _ask(scenario, "这份合同合规吗？", object_code=scenario["object_code"], instance_id="2")
    answered = (answer.get("evidence") or {}).get("decision") or {}
    assert answered.get("status") == verdict["decision"]["status"], (
        f"问答说 {answered.get('status')}，判定说 {verdict['decision']['status']}"
    )


def test_a_compliant_instance_is_not_reported_as_blocked(scenario) -> None:
    """误报会让用户学会忽略结论，而那等于关掉了整个平台。"""
    result = _ask(scenario, "这份合同合规吗？", object_code=scenario["object_code"], instance_id="1")
    decision = (result.get("evidence") or {}).get("decision") or {}
    assert decision.get("status") != "blocked", result["answer"]


# -- 无模型时仍然可用 --


def test_the_platform_answers_without_any_model_configured(scenario) -> None:
    """否则部署方必须先买一个模型订阅才能验证平台是否有用。"""
    result = _ask(scenario, "整体合规情况如何？")
    assert result["answer"]
    assert result.get("intent")
    # 置信度必须给出，且不能伪装成模型级的确定性。
    assert 0 < float(result.get("confidence", 0)) <= 1


def test_the_local_path_is_reproducible(scenario) -> None:
    """同一问题两次必须得到同一结论。不可复现的判定无法作为依据使用（ADR-0005）。"""
    first = _ask(scenario, "这份合同合规吗？", object_code=scenario["object_code"], instance_id="2")
    second = _ask(scenario, "这份合同合规吗？", object_code=scenario["object_code"], instance_id="2")
    left = (first.get("evidence") or {}).get("decision") or {}
    right = (second.get("evidence") or {}).get("decision") or {}
    assert left.get("status") == right.get("status")
    assert first["intent"] == second["intent"]


# -- 说不知道，而不是编造 --


def test_an_unanswerable_question_says_so(scenario) -> None:
    """编造一个自信的答案，比说不知道危险得多。"""
    result = _ask(scenario, "今天天气怎么样")
    assert result["answer"]
    # 未识别意图时置信度必须低于有依据的回答。
    grounded = _ask(scenario, "整体合规情况如何？")
    assert float(result.get("confidence", 1)) <= float(grounded.get("confidence", 0))


def test_an_empty_question_is_refused(scenario) -> None:
    """空问题不该产生一个看起来合理的答案。"""
    with pytest.raises(ValueError):
        _ask(scenario, "   ")


def test_a_missing_instance_does_not_produce_a_confident_verdict(scenario) -> None:
    """对不存在的实例给出「合规」是最坏的一类错误。

    实测行为是直接抛 `ValueError`，而不是返回一个「不合规」的结论——这更强：
    连一个否定性判定都不产出，因为那也是一个关于不存在实例的断言。
    """
    with pytest.raises(ValueError, match="实例不存在"):
        _ask(scenario, "这份合同合规吗？", object_code=scenario["object_code"], instance_id="999999")


# -- 批量一致性 --


def test_a_consistency_answer_reports_the_distribution(scenario) -> None:
    """一个实例合规不代表全部合规。批量结论必须给出分布，而不是一个总评。"""
    result = _ask(scenario, "整体一致性如何？", object_code=scenario["object_code"])
    evidence = result.get("evidence") or {}
    assert evidence, "一致性结论必须附带证据"
    # 场景里 1 号通过、2 号阻断，因此分布不可能是单一状态。
    text = str(evidence)
    assert any(marker in text for marker in ("mixed", "blocked", "review")), evidence


# -- 答案里不出现内部术语 --


def test_the_answer_avoids_internal_jargon(scenario) -> None:
    """业务人员看到「本体内核」「语义研判」这类词就不会再读下去。

    这一条刻意只禁少数几个平台自造词，不去校验整体文风——
    文风类断言会在每次措辞微调时失败，然后被删掉。
    """
    result = _ask(scenario, "这份合同合规吗？", object_code=scenario["object_code"], instance_id="2")
    for jargon in ("本体内核", "语义内核", "当前研判为"):
        assert jargon not in result["answer"], f"答案含内部术语 {jargon}: {result['answer']}"


# -- 回归集自身的守卫 --


def _own_source_lines() -> list[str]:
    """本文件的源码行，排除自省测试本身。

    自省测试会匹配到自己的断言字符串，因此必须先把它们排掉——否则守卫永远失败，
    而处理方式通常是删掉守卫。
    """
    lines = Path(__file__).read_text(encoding="utf-8").splitlines()
    marker = next(index for index, line in enumerate(lines) if line.startswith("def _own_source_lines"))
    return lines[:marker]


def test_this_suite_does_not_depend_on_a_model_provider() -> None:
    """带模型的回归集会因供应商改模型而失败，随后被标记 flaky 并跳过——
    那时它不再保护任何东西。"""
    body = "\n".join(_own_source_lines())
    assert "use_model=True" not in body
    assert body.count("use_model=False") >= 1


def test_this_suite_asserts_structure_not_wording() -> None:
    """锚定措辞的断言会在无害改动时失败，然后被放宽到无意义，最后被删掉。

    以「不得断言答案完整相等」为界：允许检查关键词是否出现，
    不允许把整句答案写进断言。
    """
    body = "\n".join(_own_source_lines())
    forbidden = 'result["answer"] ' + "=="
    assert forbidden not in body, "不得断言答案的完整措辞"
