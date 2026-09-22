"""Generic business-object browsing for the out-of-the-box semantic API."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from ontology_platform.database import connect, initialize_platform_db
from ontology_platform.metadata import register_data_source, scan_data_source
from ontology_platform.object_service import ObjectAccessError, get_object_instance, list_object_instances
from ontology_platform.ontology import generate_ontology_draft
from ontology_platform.workflow_permission import (
    create_role,
    init_workflow_and_permission_schema,
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
