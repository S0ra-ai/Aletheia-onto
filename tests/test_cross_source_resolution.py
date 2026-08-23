"""跨源实体消解。ROADMAP 通用性清单最后一项结构性空白。

一个业务对象此前只能绑一个数据源，于是这类需求完全无法表达——而它在 B 端是常态：
客户主数据在 CRM、合同在 ERP，两边都有「客户」但主键不同。

跨源判定必须先回答「CRM 第 42 行和 ERP 第 7 行是同一个客户吗」，
而那个判断会进入判定链。**若它不可核验，基于它的每个结论都不可解释。**

因此本测试集的重心不是「能读到另一个源」，而是几条拒绝：

- 匹配是声明的，不是相似度推断的
- 副源匹配到多行时**拒绝**，而不是挑第一行
- 两侧同名字段取值不同时**标记冲突**，而不是让某一侧静默胜出
- 匹配失败时**不注入任何字段**，让引用它的规则 fail-closed
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from ontology_platform.adapters import get_adapter
from ontology_platform.aggregation import AggregateSpec, define_aggregate, init_aggregate_schema
from ontology_platform.database import connect, initialize_platform_db
from ontology_platform.entity_resolution import (
    CONFLICT_MARK,
    PREFER_PRIMARY,
    PREFER_SECONDARY,
    ConflictingValue,
    CrossSourceLink,
    EntityResolutionError,
    MatchKey,
    declare_cross_source_link,
    describe_cross_source,
    entity_resolution_tables_exist,
    init_entity_resolution_schema,
    list_cross_source_links,
    load_links,
    resolve_cross_source,
)
from ontology_platform.governance import upsert_business_rule
from ontology_platform.metadata import register_data_source, scan_data_source
from ontology_platform.ontology import generate_ontology_draft
from ontology_platform.semantic_kernel import assess_instance, build_runtime

# -- 声明校验 --


def _link(**overrides) -> CrossSourceLink:
    defaults = {
        "name": "crm_to_erp",
        "primary_object_code": "customer",
        "secondary_data_source_id": 2,
        "secondary_table": "clients",
        "match_keys": (MatchKey(primary_column="tax_id", secondary_column="taxpayer_no"),),
    }
    return CrossSourceLink(**{**defaults, **overrides})


def test_a_link_must_declare_at_least_one_match_key() -> None:
    """没有匹配键就没有「同一实例」的依据。

    这是整个模块存在的理由：匹配必须是声明的，不能是推断的。
    """
    with pytest.raises(EntityResolutionError, match="匹配列对"):
        _link(match_keys=()).validate()


@pytest.mark.parametrize("bad", ["clients; drop table x", 'clients"', "1bad", ""])
def test_identifiers_reaching_sql_are_validated(bad: str) -> None:
    with pytest.raises(EntityResolutionError):
        _link(secondary_table=bad).validate()


def test_match_key_columns_are_validated() -> None:
    with pytest.raises(EntityResolutionError):
        _link(match_keys=(MatchKey(primary_column="a; drop", secondary_column="b"),)).validate()


def test_an_unknown_conflict_strategy_is_refused() -> None:
    with pytest.raises(EntityResolutionError, match="冲突策略"):
        _link(merge_strategy="whatever").validate()


def test_a_link_name_must_bind_as_an_identifier() -> None:
    with pytest.raises(EntityResolutionError):
        _link(name="not an identifier").validate()


def test_normalisation_is_deterministic_only() -> None:
    """只做去空白与统一大小写。同义词替换或拼写纠正会让匹配结果随词表变化，
    而那会让同一份数据在不同时间得出不同判定。"""
    key = MatchKey(primary_column="a", secondary_column="b")
    assert key.normalized("  ABC  ") == key.normalized("abc")
    assert key.normalized(None) == ""
    # 类型不同但业务键相同：CRM 存 varchar，ERP 存 bigint。
    assert key.normalized(123) == key.normalized("123")


def test_normalisation_can_be_turned_off() -> None:
    key = MatchKey(primary_column="a", secondary_column="b", normalize=False)
    assert key.normalized("ABC") != key.normalized("abc")


def test_the_definition_states_how_identity_was_decided() -> None:
    """引用了跨源字段的判定必须能说出「同一实例」是按什么判定的。"""
    definition = _link().describe()
    assert "tax_id" in definition and "taxpayer_no" in definition


# -- 匹配求解 --


@pytest.fixture
def erp(tmp_path: Path) -> Path:
    """副源：ERP，客户表主键与 CRM 不同，靠税号对应。"""
    path = tmp_path / "erp.sqlite3"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        create table clients (
            id integer primary key,
            taxpayer_no text not null,
            credit_limit numeric not null,
            region text not null
        );
        create table orders (
            id integer primary key,
            client_taxpayer_no text not null,
            amount numeric not null
        );
        insert into clients values (7, 'TX-001', 500000, '华东');
        insert into clients values (8, 'TX-002', 800000, '华北');
        -- 重复税号：用于验证一对多被拒绝。
        insert into clients values (9, 'TX-DUP', 100, 'A');
        insert into clients values (10, 'TX-DUP', 200, 'B');
        insert into orders values (1, 'TX-001', 300);
        insert into orders values (2, 'TX-001', 700);
        insert into orders values (3, 'TX-002', 50);
        """
    )
    conn.commit()
    conn.close()
    return path


def _resolve(erp: Path, link: CrossSourceLink, record: dict):
    with get_adapter("sqlite").runtime(str(erp)) as runtime:
        return resolve_cross_source(link.validate(), record, runtime)


def test_a_declared_match_finds_the_corresponding_row(erp: Path) -> None:
    result = _resolve(erp, _link(prefix="erp"), {"id": 42, "tax_id": "TX-001"})
    assert result.matched is True
    assert result.fields["erp_credit_limit"] == 500000
    assert result.fields["erp_region"] == "华东"


def test_no_match_injects_nothing(erp: Path) -> None:
    """注入 None 会让 `erp_credit_limit > 0` 求值为假，与真实业务违规无法区分。
    缺席则触发 NameError，由 fail-closed 转为「未通过 + 原因」（ADR-0002）。"""
    result = _resolve(erp, _link(prefix="erp"), {"id": 1, "tax_id": "TX-NOPE"})
    assert result.matched is False
    assert result.fields == {}


def test_multiple_matches_are_refused_not_picked(erp: Path) -> None:
    """最危险的失败不是找不到，而是找到了多个。

    挑第一行会让判定作用在一条任意选中的记录上，而结果看起来完全正常。
    """
    result = _resolve(erp, _link(prefix="erp"), {"id": 1, "tax_id": "TX-DUP"})
    assert result.matched is False
    assert "2 行" in result.error
    assert result.fields == {}


def test_multiple_matches_can_be_allowed_when_declared(erp: Path) -> None:
    """有的场景确实允许取任一行，但那必须是声明的，不能是默认。"""
    result = _resolve(erp, _link(prefix="erp", require_unique=False), {"id": 1, "tax_id": "TX-DUP"})
    assert result.matched is True


def test_a_missing_match_key_on_the_primary_side_is_reported(erp: Path) -> None:
    """主源缺匹配键时，「同一实例」无从成立。

    若不报错而是匹配全部行，会静默地把一个实例对应到任意一行。
    """
    result = _resolve(erp, _link(prefix="erp"), {"id": 1, "tax_id": None})
    assert result.matched is False
    assert "匹配键" in result.error


def test_multiple_match_keys_are_conjunctive(erp: Path) -> None:
    """多个键为 AND：全部相等才算同一实例。任一不等即不匹配。"""
    link = _link(
        prefix="erp",
        match_keys=(
            MatchKey(primary_column="tax_id", secondary_column="taxpayer_no"),
            MatchKey(primary_column="area", secondary_column="region"),
        ),
    )
    assert _resolve(erp, link, {"tax_id": "TX-001", "area": "华东"}).matched is True
    assert _resolve(erp, link, {"tax_id": "TX-001", "area": "华北"}).matched is False


def test_an_unreadable_secondary_table_is_reported(erp: Path) -> None:
    result = _resolve(erp, _link(prefix="erp", secondary_table="no_such_table"), {"tax_id": "TX-001"})
    assert result.matched is False
    assert result.error


# -- 冲突处理 --


def test_a_conflicting_field_is_marked_not_silently_resolved(erp: Path) -> None:
    """两侧对同名字段给出不同值时，没人能说清该用哪一侧。

    默认标记冲突，规则引用它会抛 TypeError，由 fail-closed 转为「未通过 + 原因」。
    """
    result = _resolve(erp, _link(merge_strategy=CONFLICT_MARK), {"tax_id": "TX-001", "credit_limit": 999})
    assert result.matched is True
    assert isinstance(result.fields["credit_limit"], ConflictingValue)
    assert result.conflicts["credit_limit"]["used"] == "none"


def test_a_conflicting_value_refuses_comparison() -> None:
    """比较时选一侧会让判定悄悄基于一个没人确认过的值。"""
    conflicted = ConflictingValue("credit_limit", 1000000, 500000)
    for operation in (
        lambda: conflicted > 0,
        lambda: conflicted == 1000000,
        lambda: conflicted <= 500000,
    ):
        with pytest.raises(TypeError, match="取值不同"):
            operation()


def test_a_conflicting_value_still_serialises_for_provenance() -> None:
    """判定记录以 JSON 存储且带 default=str，因此留痕里必须能看出这是冲突。"""
    import json

    encoded = json.dumps({"x": ConflictingValue("amount", 1, 2)}, ensure_ascii=False, default=str)
    assert "跨源冲突" in encoded


def test_preferring_one_side_is_possible_but_recorded(erp: Path) -> None:
    """允许声明取哪一侧，但选择本身必须留痕——否则事后无法解释用了哪个值。"""
    primary = _resolve(erp, _link(merge_strategy=PREFER_PRIMARY), {"tax_id": "TX-001", "credit_limit": 999})
    assert primary.fields.get("credit_limit") is None, "prefer_primary 不应覆盖主源值"
    assert primary.conflicts["credit_limit"]["used"] == "primary"

    secondary = _resolve(erp, _link(merge_strategy=PREFER_SECONDARY), {"tax_id": "TX-001", "credit_limit": 999})
    assert secondary.fields["credit_limit"] == 500000
    assert secondary.conflicts["credit_limit"]["used"] == "secondary"


def test_identical_values_are_not_a_conflict(erp: Path) -> None:
    result = _resolve(erp, _link(), {"tax_id": "TX-001", "region": "华东"})
    assert "region" not in result.conflicts


def test_a_prefix_avoids_conflicts_entirely(erp: Path) -> None:
    """有前缀时两侧字段不会同名，因此不存在「该用哪一侧」的问题。"""
    result = _resolve(erp, _link(prefix="erp"), {"tax_id": "TX-001", "credit_limit": 999})
    assert result.conflicts == {}
    assert result.fields["erp_credit_limit"] == 500000


# -- 持久化 --


@pytest.fixture
def modelled(tmp_path: Path, erp: Path):
    """主源 CRM 已建模，ERP 作为副源登记。"""
    crm = tmp_path / "crm.sqlite3"
    conn = sqlite3.connect(crm)
    conn.executescript(
        """
        create table customers (
            id integer primary key,
            name text not null,
            tax_id text not null,
            credit_status text not null
        );
        insert into customers values (42, '甲公司', 'TX-001', 'normal');
        insert into customers values (43, '乙公司', 'TX-002', 'normal');
        """
    )
    conn.commit()
    conn.close()

    platform_db = tmp_path / "platform.sqlite3"
    initialize_platform_db(platform_db)
    with connect(platform_db) as conn:
        init_entity_resolution_schema(conn)
        # 幂等：每次启动都会执行。
        init_entity_resolution_schema(conn)
        init_aggregate_schema(conn)
    primary = register_data_source(platform_db, "CRM", "sqlite", str(crm), domain="客户管理")
    scan_data_source(platform_db, primary.id)
    secondary = register_data_source(platform_db, "ERP", "sqlite", str(erp), domain="合同管理")
    scan_data_source(platform_db, secondary.id)
    ontology_id = generate_ontology_draft(platform_db, primary.id)["ontology"]["id"]
    with connect(platform_db) as conn:
        object_code = conn.execute(
            """
            select bo.code from business_object bo
            join source_table st on st.id = bo.source_table_id
            where bo.ontology_id = ? and st.table_name = 'customers'
            """,
            (ontology_id,),
        ).fetchone()["code"]
    return {
        "platform_db": platform_db,
        "ontology_id": ontology_id,
        "object_code": object_code,
        "secondary_id": secondary.id,
    }


def _declare(modelled, **overrides):
    link = CrossSourceLink(
        name="crm_to_erp",
        primary_object_code=modelled["object_code"],
        secondary_data_source_id=modelled["secondary_id"],
        secondary_table="clients",
        match_keys=(MatchKey(primary_column="tax_id", secondary_column="taxpayer_no"),),
        prefix="erp",
        **overrides,
    )
    return declare_cross_source_link(modelled["platform_db"], modelled["ontology_id"], link, actor="tester")


def test_declaring_and_listing_a_link(modelled) -> None:
    _declare(modelled)
    items = list_cross_source_links(modelled["platform_db"], modelled["ontology_id"])
    assert [item["name"] for item in items] == ["crm_to_erp"]
    assert "taxpayer_no" in items[0]["definition"]


def test_redeclaring_updates_rather_than_duplicating(modelled) -> None:
    _declare(modelled)
    _declare(modelled, merge_strategy=PREFER_SECONDARY)
    items = list_cross_source_links(modelled["platform_db"], modelled["ontology_id"])
    assert len(items) == 1
    assert items[0]["mergeStrategy"] == PREFER_SECONDARY


def test_an_unknown_primary_object_is_refused(modelled) -> None:
    link = CrossSourceLink(
        name="bad",
        primary_object_code="no_such_object",
        secondary_data_source_id=modelled["secondary_id"],
        secondary_table="clients",
        match_keys=(MatchKey(primary_column="a", secondary_column="b"),),
    )
    with pytest.raises(EntityResolutionError, match="业务对象不存在"):
        declare_cross_source_link(modelled["platform_db"], modelled["ontology_id"], link)


def test_an_unknown_secondary_data_source_is_refused(modelled) -> None:
    """入库前拒绝：指向不存在数据源的声明会在每次判定时失败，
    表现为「规则永远不通过」而不是「配置写错了」。"""
    link = CrossSourceLink(
        name="bad",
        primary_object_code=modelled["object_code"],
        secondary_data_source_id=9999,
        secondary_table="clients",
        match_keys=(MatchKey(primary_column="a", secondary_column="b"),),
    )
    with pytest.raises(EntityResolutionError, match="数据源不存在"):
        declare_cross_source_link(modelled["platform_db"], modelled["ontology_id"], link)


def test_a_published_ontology_refuses_link_changes(modelled) -> None:
    from ontology_platform.governance import (
        list_semantic_mappings,
        publish_ontology,
        review_semantic_mapping,
    )

    platform_db, ontology_id = modelled["platform_db"], modelled["ontology_id"]
    for mapping in list_semantic_mappings(platform_db, ontology_id)["items"]:
        review_semantic_mapping(platform_db, mapping["id"], "confirmed", "tester", "")
    publish_ontology(platform_db, ontology_id, "tester", force=True)
    with pytest.raises(EntityResolutionError, match="已发布"):
        _declare(modelled)


def test_the_declaration_is_audited(modelled) -> None:
    _declare(modelled)
    with connect(modelled["platform_db"]) as conn:
        rows = conn.execute("select actor from audit_log where action = 'declare_cross_source_link'").fetchall()
    assert rows and rows[0]["actor"] == "tester"


def test_a_stored_declaration_that_stops_validating_is_skipped(modelled) -> None:
    """它会让引用跨源字段的规则 fail-closed，那是安全的方向。"""
    _declare(modelled)
    with connect(modelled["platform_db"]) as conn:
        conn.execute("update cross_source_link set match_keys = '[]'")
    with connect(modelled["platform_db"]) as conn:
        assert load_links(conn, modelled["ontology_id"], modelled["object_code"]) == []


def test_a_database_without_the_link_table_reads_as_no_links(tmp_path: Path) -> None:
    """走目录探测而非捕获异常：PostgreSQL 上一条失败语句会中止整个事务（ADR-0004）。"""
    bare = tmp_path / "bare.sqlite3"
    initialize_platform_db(bare)
    with connect(bare) as conn:
        assert entity_resolution_tables_exist(conn) is False
        assert load_links(conn, 1, "customer") == []


def test_the_description_states_that_matching_is_declared(modelled) -> None:
    _declare(modelled)
    described = describe_cross_source(modelled["platform_db"], modelled["ontology_id"])
    assert described["links"]
    assert "声明的" in described["note"]


# -- 端到端：跨源字段进入判定 --


def test_a_rule_can_reference_a_cross_source_field(modelled) -> None:
    """核心能力：一个对象跨两个数据源，且规则能读到副源字段。"""
    _declare(modelled)
    platform_db, ontology_id = modelled["platform_db"], modelled["ontology_id"]
    object_code = modelled["object_code"]
    with connect(platform_db) as conn:
        runtime = build_runtime(conn, ontology_id, object_code, "42")
    assert runtime.record["erp_credit_limit"] == 500000
    # 判定必须能说出「同一实例」是按什么判定的。
    assert runtime.cross_source["crm_to_erp"]["matched"] is True
    assert "taxpayer_no" in runtime.cross_source["crm_to_erp"]["definition"]


def test_a_cross_source_rule_reaches_a_verdict(modelled) -> None:
    _declare(modelled)
    platform_db, ontology_id = modelled["platform_db"], modelled["ontology_id"]
    object_code = modelled["object_code"]
    upsert_business_rule(
        platform_db,
        ontology_id,
        code="erp_credit_present",
        name="ERP 信用额度必须为正",
        rule_type="validation",
        scope_object_code=object_code,
        expression="erp_credit_limit > 0",
        severity="blocking",
        natural_language="ERP 中的信用额度必须为正。",
        actor="tester",
    )
    result = assess_instance(platform_db, ontology_id, object_code, "42")
    rule = next(item for item in result["ruleResults"] if item["ruleCode"] == "erp_credit_present")
    assert rule["passed"] is True, rule


def test_an_unmatched_instance_makes_its_cross_source_rule_fail_closed(modelled) -> None:
    """副源没有对应行时，引用跨源字段的规则必须失败而不是静默通过。"""
    platform_db, ontology_id = modelled["platform_db"], modelled["ontology_id"]
    object_code = modelled["object_code"]
    # 声明一个匹配不到任何行的对应。
    link = CrossSourceLink(
        name="never_matches",
        primary_object_code=object_code,
        secondary_data_source_id=modelled["secondary_id"],
        secondary_table="clients",
        match_keys=(MatchKey(primary_column="name", secondary_column="taxpayer_no"),),
        prefix="erp",
    )
    declare_cross_source_link(platform_db, ontology_id, link)
    upsert_business_rule(
        platform_db,
        ontology_id,
        code="needs_erp",
        name="需要 ERP 数据",
        rule_type="validation",
        scope_object_code=object_code,
        expression="erp_credit_limit > 0",
        severity="blocking",
        natural_language="需要 ERP 信用额度。",
        actor="tester",
    )
    result = assess_instance(platform_db, ontology_id, object_code, "42")
    rule = next(item for item in result["ruleResults"] if item["ruleCode"] == "needs_erp")
    assert rule["passed"] is False
    assert rule["skipped"] is True, rule


# -- 跨源聚合 --


def test_a_cross_source_aggregate_reads_the_other_source(modelled) -> None:
    """「这个客户在 ERP 里的订单总额」——客户在 CRM，订单在 ERP。"""
    platform_db, ontology_id = modelled["platform_db"], modelled["ontology_id"]
    object_code = modelled["object_code"]
    define_aggregate(
        platform_db,
        ontology_id,
        object_code,
        AggregateSpec(
            name="erp_order_total",
            function="sum",
            target_table="orders",
            target_column="client_taxpayer_no",
            group_column="tax_id",
            value_column="amount",
            target_data_source_id=modelled["secondary_id"],
        ),
        actor="tester",
    )
    with connect(platform_db) as conn:
        runtime = build_runtime(conn, ontology_id, object_code, "42")
    # TX-001 在 ERP 有两笔订单：300 + 700。
    assert runtime.aggregates["erp_order_total"]["value"] == 1000.0
    # 定义里必须写明目标在哪个源，否则同名表会让人以为读的是本源。
    assert "数据源#" in runtime.aggregates["erp_order_total"]["definition"]


def test_a_cross_source_aggregate_can_drive_a_rule(modelled) -> None:
    platform_db, ontology_id = modelled["platform_db"], modelled["ontology_id"]
    object_code = modelled["object_code"]
    define_aggregate(
        platform_db,
        ontology_id,
        object_code,
        AggregateSpec(
            name="erp_order_total",
            function="sum",
            target_table="orders",
            target_column="client_taxpayer_no",
            group_column="tax_id",
            value_column="amount",
            target_data_source_id=modelled["secondary_id"],
        ),
    )
    upsert_business_rule(
        platform_db,
        ontology_id,
        code="erp_total_limit",
        name="ERP 订单总额上限",
        rule_type="validation",
        scope_object_code=object_code,
        expression="erp_order_total <= 500",
        severity="blocking",
        natural_language="ERP 订单总额不得超过 500。",
        actor="tester",
    )
    result = assess_instance(platform_db, ontology_id, object_code, "42")
    rule = next(item for item in result["ruleResults"] if item["ruleCode"] == "erp_total_limit")
    # 总额 1000 超过 500。
    assert rule["passed"] is False, rule


def test_an_aggregate_pointing_at_a_missing_source_is_refused(modelled) -> None:
    from ontology_platform.aggregation import AggregationError

    with pytest.raises(AggregationError, match="目标数据源不存在"):
        define_aggregate(
            modelled["platform_db"],
            modelled["ontology_id"],
            modelled["object_code"],
            AggregateSpec(
                name="bad",
                function="sum",
                target_table="orders",
                target_column="a",
                group_column="b",
                value_column="amount",
                target_data_source_id=9999,
            ),
        )


def test_same_source_aggregates_keep_working(modelled) -> None:
    """`target_data_source_id` 默认 0 表示本源，因此升级不改变任何既有聚合的结果。"""
    platform_db, ontology_id = modelled["platform_db"], modelled["ontology_id"]
    object_code = modelled["object_code"]
    define_aggregate(
        platform_db,
        ontology_id,
        object_code,
        AggregateSpec(
            name="same_source_count",
            function="count",
            target_table="customers",
            target_column="credit_status",
            group_column="credit_status",
        ),
    )
    with connect(platform_db) as conn:
        runtime = build_runtime(conn, ontology_id, object_code, "42")
    assert runtime.aggregates["same_source_count"]["value"] == 2.0


def test_the_new_column_is_added_to_deployed_databases() -> None:
    """`create table if not exists` 对已存在的表什么都不做，
    因此新字段必须走 ALTER——否则它只对全新部署生效，
    而那意味着功能在开发机上能用、升级后不能用。"""
    from ontology_platform.aggregation import SCHEMA

    added = {column.column for column in SCHEMA.columns}
    assert "target_data_source_id" in added
    for column in SCHEMA.columns:
        # 默认 0 = 本源，等于既有行为，因此升级不改变任何结果。
        assert "default 0" in column.sqlite_type


def test_column_additions_are_idempotent(tmp_path: Path) -> None:
    """启动时会反复执行。重复加列必须无害，否则第二次启动就会失败。"""
    from ontology_platform.aggregation import init_aggregate_schema

    platform_db = tmp_path / "p.sqlite3"
    initialize_platform_db(platform_db)
    with connect(platform_db) as conn:
        init_aggregate_schema(conn)
        init_aggregate_schema(conn)
        init_aggregate_schema(conn)
    with connect(platform_db) as conn:
        columns = {row["name"] for row in conn.execute("pragma table_info(cross_object_aggregate)").fetchall()}
    assert "target_data_source_id" in columns


# -- API 与留痕 --


def test_the_verdict_records_how_identity_was_decided(modelled) -> None:
    """跨源判定的依据必须进入判定记录。

    只存「结论」而不存「按什么判定为同一实例」，事后就无法回答
    「这个数字来自哪一行」——而那是跨源判定最容易被质疑的一点。
    """
    _declare(modelled)
    platform_db, ontology_id = modelled["platform_db"], modelled["ontology_id"]
    result = assess_instance(platform_db, ontology_id, modelled["object_code"], "42")
    assert result["crossSource"]["crm_to_erp"]["matched"] is True
    with connect(platform_db) as conn:
        row = conn.execute("select evidence from decision_record order by id desc limit 1").fetchone()
    assert "crm_to_erp" in str(row["evidence"])
    assert "taxpayer_no" in str(row["evidence"])


def test_the_endpoint_requires_write_capability() -> None:
    """跨源对应决定每次判定读到的数据，因此是建模写操作，不是读。"""
    from ontology_platform.access_policy import required_capability

    assert required_capability("PUT", "/ontologies/1/objects/customer/cross-source-links") == "platform:write"
    assert required_capability("GET", "/ontologies/1/cross-source-links") == "platform:read"


def test_the_api_exposes_links_with_the_declared_matching_note() -> None:
    """只看到列表的调用方会以为平台在做模糊匹配。"""
    from ontology_platform.api import ontology_cross_source_links

    payload = ontology_cross_source_links(1)
    assert "note" in payload
    assert "声明的" in payload["note"]


def test_the_cli_creates_the_link_table(tmp_path: Path, capsys) -> None:
    """CLI 初始化的库不能缺表：缺表会在很久之后表现为「跨源对应保存不上」。"""
    from ontology_platform.cli import main

    database = tmp_path / "platform.sqlite3"
    assert main(["--platform-db", str(database), "init"]) == 0
    capsys.readouterr()
    with sqlite3.connect(database) as conn:
        tables = {row[0] for row in conn.execute("select name from sqlite_master where type='table'")}
    assert "cross_source_link" in tables
