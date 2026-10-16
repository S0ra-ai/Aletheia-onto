"""Generic business-object browsing for the out-of-the-box semantic API."""

from __future__ import annotations

import importlib
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from ontology_platform import instance_resolver
from ontology_platform.auth import create_user
from ontology_platform.database import connect, initialize_platform_db
from ontology_platform.metadata import register_data_source, scan_data_source
from ontology_platform.object_service import ObjectAccessError, get_object_instance, list_object_instances
from ontology_platform.ontology import generate_ontology_draft
from ontology_platform.workflow_permission import (
    create_role,
    init_workflow_and_permission_schema,
    seed_default_roles_and_policies,
    upsert_permission_policy,
)


@pytest.fixture
def scenario(tmp_path: Path) -> dict[str, object]:
    source_path = tmp_path / "business.sqlite3"
    with sqlite3.connect(source_path) as source:
        source.executescript(
            """
            create table customer (id integer primary key, name text not null, tier text not null);
            insert into customer values (1, '甲公司', 'gold');
            insert into customer values (2, '乙公司', 'silver');
            insert into customer values (3, '丙公司', 'gold');
            """
        )

    platform = tmp_path / "platform.sqlite3"
    initialize_platform_db(platform)
    with connect(platform) as conn:
        init_workflow_and_permission_schema(conn)
    source = register_data_source(platform, "客户系统", "sqlite", str(source_path), domain="客户管理")
    scan_data_source(platform, source.id)
    ontology = generate_ontology_draft(platform, source.id)
    ontology_id = int(ontology["ontology"]["id"])
    with connect(platform) as conn:
        object_code = conn.execute(
            "select bo.code from business_object bo join source_table st on st.id = bo.source_table_id "
            "where bo.ontology_id = ? and st.table_name = 'customer'",
            (ontology_id,),
        ).fetchone()["code"]
    role = create_role(platform, "customer_reader", "客户只读")
    upsert_permission_policy(platform, int(role["id"]), object_code, can_read=True, ontology_id=ontology_id)
    return {"platform": platform, "ontology_id": ontology_id, "object_code": object_code}


def test_list_business_object_instances_returns_metadata_and_rows(scenario: dict[str, object]) -> None:
    result = list_object_instances(
        scenario["platform"],  # type: ignore[arg-type]
        int(scenario["ontology_id"]),
        str(scenario["object_code"]),
        role_code="customer_reader",
        limit=2,
    )

    assert result["object"]["code"] == scenario["object_code"]
    assert result["object"]["sourceTable"] == "customer"
    assert result["pagination"] == {"limit": 2, "offset": 0, "total": 3, "hasMore": True}
    assert [item["instanceId"] for item in result["items"]] == ["1", "2"]
    assert result["items"][0]["record"]["name"] == "甲公司"
    assert result["attributes"]


def test_get_business_object_instance_uses_same_permission_boundary(scenario: dict[str, object]) -> None:
    result = get_object_instance(
        scenario["platform"],  # type: ignore[arg-type]
        int(scenario["ontology_id"]),
        str(scenario["object_code"]),
        "2",
        role_code="customer_reader",
    )

    assert result["instanceId"] == "2"
    assert result["record"]["tier"] == "silver"


def test_row_filter_is_applied_before_rows_reach_the_caller(scenario: dict[str, object]) -> None:
    platform = scenario["platform"]
    ontology_id = int(scenario["ontology_id"])
    object_code = str(scenario["object_code"])
    with connect(platform) as conn:  # type: ignore[arg-type]
        role = conn.execute("select id from permission_role where code = 'customer_reader'").fetchone()
    upsert_permission_policy(
        platform,  # type: ignore[arg-type]
        int(role["id"]),
        object_code,
        can_read=True,
        filter_expression="tier == 'gold'",
        ontology_id=ontology_id,
    )

    result = list_object_instances(platform, ontology_id, object_code, role_code="customer_reader", limit=50)  # type: ignore[arg-type]
    assert [item["instanceId"] for item in result["items"]] == ["1", "3"]
    with pytest.raises(ObjectAccessError):
        get_object_instance(platform, ontology_id, object_code, "2", role_code="customer_reader")  # type: ignore[arg-type]


def test_unknown_role_is_denied_closed(scenario: dict[str, object]) -> None:
    with pytest.raises(ObjectAccessError):
        list_object_instances(
            scenario["platform"],  # type: ignore[arg-type]
            int(scenario["ontology_id"]),
            str(scenario["object_code"]),
            role_code="missing-role",
        )


def _counting_fetches(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record every instance the resolver materialises, so cost is measured not assumed."""
    fetched: list[str] = []
    original = instance_resolver.SingleTableResolver.fetch

    def counting_fetch(self, runtime, instance_id):  # type: ignore[no-untyped-def]
        fetched.append(str(instance_id))
        return original(self, runtime, instance_id)

    monkeypatch.setattr(instance_resolver.SingleTableResolver, "fetch", counting_fetch)
    return fetched


@pytest.fixture
def large_scenario(tmp_path: Path) -> dict[str, object]:
    """A source larger than one page, which is where the cost question appears."""
    source_path = tmp_path / "business.sqlite3"
    with sqlite3.connect(source_path) as source:
        source.execute("create table customer (id integer primary key, name text not null, tier text not null)")
        source.executemany(
            "insert into customer values (?, ?, ?)",
            [(number, f"公司{number}", "gold" if number % 2 else "silver") for number in range(1, 301)],
        )

    platform = tmp_path / "platform.sqlite3"
    initialize_platform_db(platform)
    with connect(platform) as conn:
        init_workflow_and_permission_schema(conn)
    source = register_data_source(platform, "客户系统", "sqlite", str(source_path), domain="客户管理")
    scan_data_source(platform, source.id)
    ontology = generate_ontology_draft(platform, source.id)
    ontology_id = int(ontology["ontology"]["id"])
    with connect(platform) as conn:
        object_code = conn.execute(
            "select bo.code from business_object bo join source_table st on st.id = bo.source_table_id "
            "where bo.ontology_id = ? and st.table_name = 'customer'",
            (ontology_id,),
        ).fetchone()["code"]
    role = create_role(platform, "customer_reader", "客户只读")
    upsert_permission_policy(platform, int(role["id"]), object_code, can_read=True, ontology_id=ontology_id)
    return {"platform": platform, "ontology_id": ontology_id, "object_code": object_code}


def test_a_page_only_materialises_the_rows_it_returns(
    large_scenario: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    """One page must not cost one query per row in the source.

    The listing walks candidate instance ids so that row-level authorization is applied
    uniformly across every resolver kind. That is the right security shape, but it does
    not follow that each candidate must be *materialised*: with no row filter configured,
    `check_permission` decides from the policy alone and returns without ever reading the
    instance. Fetching anyway turns a twenty-row page into one query per row in the
    source -- against a legacy system that is frequently on the far side of a WAN link,
    and for a request an administrator performs by opening a page.
    """
    fetched = _counting_fetches(monkeypatch)

    result = list_object_instances(
        large_scenario["platform"],  # type: ignore[arg-type]
        int(large_scenario["ontology_id"]),
        str(large_scenario["object_code"]),
        role_code="customer_reader",
        limit=20,
    )

    assert len(result["items"]) == 20
    assert result["pagination"]["total"] == 300
    assert len(fetched) == 20, f"一页 20 行却读取了 {len(fetched)} 行"


def test_a_row_filter_still_reads_every_candidate_it_must_judge(
    large_scenario: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The filter is arbitrary, so it can only be judged against a materialised row.

    The counterpart to the test above: correctness here is why the candidate walk exists,
    so the optimization must not be allowed to skip rows a filter has to inspect. One read
    per candidate is the floor when a filter is configured; the assertion allows exactly
    that plus one per returned row, because the read the filter performs happens inside the
    permission check and cannot be handed to the caller.
    """
    platform = large_scenario["platform"]
    ontology_id = int(large_scenario["ontology_id"])
    object_code = str(large_scenario["object_code"])
    with connect(platform) as conn:  # type: ignore[arg-type]
        role = conn.execute("select id from permission_role where code = 'customer_reader'").fetchone()
    upsert_permission_policy(
        platform,  # type: ignore[arg-type]
        int(role["id"]),
        object_code,
        can_read=True,
        filter_expression="tier == 'gold'",
        ontology_id=ontology_id,
    )
    fetched = _counting_fetches(monkeypatch)

    result = list_object_instances(platform, ontology_id, object_code, role_code="customer_reader", limit=5)  # type: ignore[arg-type]

    assert [item["instanceId"] for item in result["items"]] == ["1", "3", "5", "7", "9"]
    # Every one of the 300 rows was judged; that is what makes the total trustworthy.
    assert result["pagination"]["total"] == 150
    assert result["rowFilterApplied"] is True
    assert len(fetched) == 300 + len(result["items"]), (
        f"逐行判定之外还多读了 {len(fetched) - 300 - len(result['items'])} 行"
    )


def test_an_absurd_offset_cannot_inflate_the_candidate_query(
    large_scenario: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    """`offset` is caller-supplied and was previously unbounded.

    It was used as `max(offset + limit, 100000)`, so the "bounded but generous" id fetch
    grew with whatever the caller sent: `?offset=100000000` asked the legacy system for a
    hundred million primary keys. Nothing about serving a page needs that -- a page beyond
    the candidate window either returns empty, or the source is asked for at most the
    declared bound.
    """
    asked: list[int] = []
    original = instance_resolver.SingleTableResolver.list_ids

    def counting_list_ids(self, runtime, limit: int = 50):  # type: ignore[no-untyped-def]
        asked.append(limit)
        return original(self, runtime, limit)

    monkeypatch.setattr(instance_resolver.SingleTableResolver, "list_ids", counting_list_ids)

    result = list_object_instances(
        large_scenario["platform"],  # type: ignore[arg-type]
        int(large_scenario["ontology_id"]),
        str(large_scenario["object_code"]),
        role_code="customer_reader",
        limit=20,
        offset=10**8,
    )

    assert result["items"] == []
    assert result["pagination"]["hasMore"] is False
    # Asking for nothing is the better outcome; asking for anything must respect the bound.
    assert max(asked, default=0) <= 100_000, f"向数据源索要了 {max(asked)} 个主键"


class TestTheBrowsingEndpoint:
    """The HTTP surface, which is what the feature was shipped for.

    Only the service function was covered, so the response contract a caller actually
    receives -- pagination fields, the row-filter flag, and the query parameters that drive
    them -- was asserted nowhere. A pass-through is exactly where such a gap hides: it looks
    too thin to need a test, and it is the only thing a caller ever sees.
    """

    @pytest.fixture
    def browsing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        source_path = tmp_path / "business.sqlite3"
        with sqlite3.connect(source_path) as source:
            source.execute("create table customer (id integer primary key, name text not null, tier text not null)")
            source.executemany(
                "insert into customer values (?, ?, ?)",
                [(n, f"公司{n}", "gold" if n % 2 else "silver") for n in range(1, 31)],
            )

        platform = tmp_path / "platform.sqlite3"
        monkeypatch.delenv("ONTOLOGY_AUTH_DISABLED", raising=False)
        monkeypatch.delenv("ONTOLOGY_RATE_LIMIT_PER_MINUTE", raising=False)
        monkeypatch.setenv("ONTOLOGY_ADMIN_PASSWORD", "admin-password-123")
        monkeypatch.setenv("ONTOLOGY_ALLOWED_ORIGINS", "http://localhost:3000")

        import ontology_platform.api as api_module
        import ontology_platform.database as database_module

        database_module._platform_adapter = None
        monkeypatch.setattr(database_module, "DEFAULT_PLATFORM_DB", platform)
        reloaded = importlib.reload(api_module)
        monkeypatch.setattr(reloaded, "DEFAULT_PLATFORM_DB", platform)

        try:
            with TestClient(reloaded.app) as client:
                # Modelled after startup, so the platform's own seeding is re-run afterwards
                # and the read-only role receives its policy through the supported path
                # rather than a hand-written row.
                data_source = register_data_source(platform, "客户系统", "sqlite", str(source_path), domain="客户管理")
                scan_data_source(platform, data_source.id)
                ontology = generate_ontology_draft(platform, data_source.id)
                ontology_id = int(ontology["ontology"]["id"])
                with connect(platform) as conn:
                    object_code = conn.execute(
                        "select bo.code from business_object bo join source_table st on st.id = bo.source_table_id "
                        "where bo.ontology_id = ? and st.table_name = 'customer'",
                        (ontology_id,),
                    ).fetchone()["code"]
                seed_default_roles_and_policies(platform)
                create_user(platform, "reader", "reader-password-123", role_code="analyst")

                token = client.post(
                    "/auth/login", json={"username": "reader", "password": "reader-password-123"}
                ).json()["token"]
                yield client, platform, ontology_id, object_code, {"Authorization": f"Bearer {token}"}
        finally:
            database_module._platform_adapter = None

    def test_a_page_is_served_with_its_pagination(self, browsing) -> None:
        client, _platform, ontology_id, object_code, headers = browsing
        response = client.get(
            f"/semantic/objects/{object_code}/instances?ontologyId={ontology_id}&limit=5&offset=5",
            headers=headers,
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert [item["instanceId"] for item in payload["items"]] == ["6", "7", "8", "9", "10"]
        assert payload["pagination"] == {"limit": 5, "offset": 5, "total": 30, "hasMore": True}
        assert payload["rowFilterApplied"] is False

    def test_a_configured_row_filter_narrows_the_wire_response(self, browsing) -> None:
        """The flag and the filtering itself, over HTTP.

        `SECURITY.md` requires callers to check whether a row filter participated in the
        decision; a flag the response never carries is a requirement nobody can satisfy.
        """
        client, platform, ontology_id, object_code, headers = browsing
        with connect(platform) as conn:
            role = conn.execute("select id from permission_role where code = 'analyst'").fetchone()
        upsert_permission_policy(
            platform,
            int(role["id"]),
            object_code,
            can_read=True,
            filter_expression="tier == 'gold'",
            ontology_id=ontology_id,
        )

        payload = client.get(
            f"/semantic/objects/{object_code}/instances?ontologyId={ontology_id}&limit=3", headers=headers
        ).json()

        assert payload["rowFilterApplied"] is True
        assert [item["instanceId"] for item in payload["items"]] == ["1", "3", "5"]
        assert payload["pagination"]["total"] == 15

    def test_an_oversized_page_is_clamped_rather_than_honoured(self, browsing) -> None:
        """A caller asking for a million rows must not be given the chance."""
        client, _platform, ontology_id, object_code, headers = browsing
        payload = client.get(
            f"/semantic/objects/{object_code}/instances?ontologyId={ontology_id}&limit=1000000", headers=headers
        ).json()

        assert payload["pagination"]["limit"] <= 1000
        assert len(payload["items"]) == 30


class TestAnUnevaluableRowFilterIsNotAnEmptyResult:
    """A filter that cannot run is not the same as a filter that excluded everything.

    Both deny every row, so both produce an empty page. The first is a misconfiguration
    someone can fix; the second is the policy working. Reporting them identically tells the
    reader "there is nothing here" when the truth is "your policy is broken", on the surface
    where the governed data is supposed to be visible.
    """

    def _apply_filter(self, scenario: dict[str, object], expression: str) -> None:
        platform = scenario["platform"]
        with connect(platform) as conn:  # type: ignore[arg-type]
            role = conn.execute("select id from permission_role where code = 'customer_reader'").fetchone()
        upsert_permission_policy(
            platform,  # type: ignore[arg-type]
            int(role["id"]),
            str(scenario["object_code"]),
            can_read=True,
            filter_expression=expression,
            ontology_id=int(scenario["ontology_id"]),
        )

    def test_a_filter_that_cannot_be_evaluated_is_reported(self, scenario: dict[str, object]) -> None:
        # `tier` holds 'gold'/'silver', so comparing it to a number cannot be evaluated.
        self._apply_filter(scenario, "tier > 0")

        result = list_object_instances(
            scenario["platform"],  # type: ignore[arg-type]
            int(scenario["ontology_id"]),
            str(scenario["object_code"]),
            role_code="customer_reader",
            limit=10,
        )

        assert result["items"] == []
        assert result["rowFilterApplied"] is True
        assert "无法求值" in result["rowFilterError"]
        # And it says which expression, so the reader knows where to go.
        assert "行级访问过滤" in result["rowFilterError"]

    def test_a_filter_that_excluded_every_row_reports_nothing(self, scenario: dict[str, object]) -> None:
        """The working case must stay quiet, or the signal is lost in the noise."""
        self._apply_filter(scenario, "tier == 'platinum'")

        result = list_object_instances(
            scenario["platform"],  # type: ignore[arg-type]
            int(scenario["ontology_id"]),
            str(scenario["object_code"]),
            role_code="customer_reader",
            limit=10,
        )

        assert result["items"] == []
        assert result["rowFilterApplied"] is True
        assert result["rowFilterError"] == ""

    def test_no_filter_reports_neither(self, scenario: dict[str, object]) -> None:
        result = list_object_instances(
            scenario["platform"],  # type: ignore[arg-type]
            int(scenario["ontology_id"]),
            str(scenario["object_code"]),
            role_code="customer_reader",
            limit=10,
        )

        assert result["items"]
        assert result["rowFilterApplied"] is False
        assert result["rowFilterError"] == ""


def test_a_row_is_keyed_by_its_source_columns_and_codes_can_differ(tmp_path: Path) -> None:
    """The contract the object table reads by, stated where a change would break it.

    A declared column keeps its spelling -- `Id`, `TotalAmount`, `CustomerName` -- while the
    generated attribute code is folded to lowercase (or replaced by a blueprint's own name).
    The console read `record[attribute.code]`, so on any source whose columns are not already
    all-lowercase *every cell* rendered the 「—」 that means "this row has no value here":
    a grid of plausible dashes over a table full of values. The demo schema is all-lowercase,
    which is why it survived every check until an audit read the two spellings side by side.

    So: `record` is keyed by source columns, and the two strings are not interchangeable.
    """
    source_path = tmp_path / "orders.sqlite3"
    with sqlite3.connect(source_path) as source:
        source.executescript(
            """
            create table orders (Id integer primary key, TotalAmount real, CustomerName text);
            insert into orders values (1, 1250.5, '能源设备');
            """
        )

    platform = tmp_path / "platform.sqlite3"
    initialize_platform_db(platform)
    with connect(platform) as conn:
        init_workflow_and_permission_schema(conn)
    source = register_data_source(platform, "订单系统", "sqlite", str(source_path), domain="订单管理")
    scan_data_source(platform, source.id)
    draft = generate_ontology_draft(platform, source.id)
    ontology_id = int(draft["ontology"]["id"])
    with connect(platform) as conn:
        object_code = conn.execute(
            "select bo.code from business_object bo join source_table st on st.id = bo.source_table_id "
            "where bo.ontology_id = ? and st.table_name = 'orders'",
            (ontology_id,),
        ).fetchone()["code"]
        pairs = [
            (row["code"], row["column_name"])
            for row in conn.execute(
                """select ba.code, sc.column_name from business_attribute ba
                   left join source_column sc on sc.id = ba.source_column_id
                   where ba.object_id = (select id from business_object where ontology_id = ? and code = ?)""",
                (ontology_id, object_code),
            ).fetchall()
        ]
    role = create_role(platform, "order_reader", "订单只读")
    upsert_permission_policy(platform, int(role["id"]), object_code, can_read=True, ontology_id=ontology_id)

    page = list_object_instances(platform, ontology_id, object_code, role_code="order_reader", limit=5)
    record = page["items"][0]["record"]

    assert set(record) == {"Id", "TotalAmount", "CustomerName"}
    assert {code for code, _column in pairs} != {column for _code, column in pairs}, (
        "前提：示例的属性编码与来源列名应当不同，否则这条测试什么也没证明"
    )
    assert all(record.get(code) is None for code, _column in pairs), (
        "属性编码在记录里取不到值——这正是「整表渲染成 —」的成因"
    )
    assert all(record.get(column) is not None for _code, column in pairs), (
        "按来源列名取值应当拿得到值——界面就是靠这一条读出每个单元格的"
    )
