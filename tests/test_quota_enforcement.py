"""A declared quota has to bind -- for every resource, and on the rows the platform writes.

`PUT /tenants/{tenant}/quotas` accepts any of the seven resources in `QUOTA_RESOURCES` and
answers 200 with an audit row, and the tenancy screen lists them all. Two of the seven were
checked anywhere, and both were checked against the wrong store: `check_quota` counted the
*tenant's* store -- for SQLite a separate file, for the server dialects a separate schema --
while every HTTP route writes through the platform store. The count was therefore always zero
and **a limit of one permitted three data sources**: only a limit of zero ever refused
anything, and only because `0 + 1 > 0`.

So the assertion here is not "a limit of zero refuses". It is the property that was false: with
the limit set to one more than the current usage, exactly one more write succeeds and the next
is refused. That is what "the platform counts what it writes" means, and it is the difference
between a ceiling and a decoration.

Both directions per resource, because only both together mean anything:

- **declared => counted**: `current + 1` permits one write and refuses the next.
- **undeclared => unaffected**: with no quota row the same call proceeds. The other default
  would stop every existing deployment from accepting writes the moment this shipped.
"""

from __future__ import annotations

import importlib
import sqlite3
from io import BytesIO
from pathlib import Path
from typing import Any, Iterator

import pytest
from fastapi.testclient import TestClient

ADMIN_PASSWORD = "quota-sweep-password"

# One constant for both the document and the number of entries it is worth, because the two
# disagreeing is exactly the mistake one of these tests exists to catch.
CLAUSES_PER_DOCUMENT = 4


@pytest.fixture
def quota_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """A demo instance, its quota schema, and an authenticated admin."""
    import ontology_platform.cli as cli
    import ontology_platform.database as database_module
    from ontology_platform.context import PlatformContext
    from ontology_platform.database import connect
    from ontology_platform.quotas import init_quota_schema

    platform_db = tmp_path / "platform.sqlite3"
    sample_db = tmp_path / "sample.sqlite3"

    monkeypatch.setenv("ONTOLOGY_ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ONTOLOGY_ADMIN_PASSWORD", ADMIN_PASSWORD)
    monkeypatch.delenv("ONTOLOGY_AUTH_DISABLED", raising=False)
    database_module._platform_adapter = None
    monkeypatch.setattr(database_module, "DEFAULT_PLATFORM_DB", platform_db)

    cli.main(["--platform-db", str(platform_db), "demo", "--sample-db", str(sample_db), "--quiet"])

    with connect(platform_db) as conn:
        init_quota_schema(conn)

    api_module = importlib.reload(__import__("ontology_platform.api", fromlist=["app"]))
    monkeypatch.setattr(api_module, "DEFAULT_PLATFORM_DB", platform_db)
    with TestClient(api_module.app) as client:
        login = client.post("/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD})
        assert login.status_code == 200, login.text
        client.headers.update({"Authorization": f"Bearer {login.json()['token']}"})
        client.platform_db = platform_db  # type: ignore[attr-defined]
        client.base = PlatformContext(db_type="sqlite", connection_uri=str(platform_db))  # type: ignore[attr-defined]
        yield client
    database_module._platform_adapter = None


def _usage(client: TestClient, resource: str) -> int:
    """What the platform says this tenant is currently using, from the tenancy report."""
    from ontology_platform.quotas import quota_usage
    from ontology_platform.tenancy import DEFAULT_TENANT

    report = quota_usage(client.base, DEFAULT_TENANT)  # type: ignore[attr-defined]
    return int(report["resources"][resource]["current"])


def _declare(client: TestClient, resource: str, limit: int) -> None:
    from ontology_platform.quotas import set_tenant_quota
    from ontology_platform.tenancy import DEFAULT_TENANT

    set_tenant_quota(client.base, DEFAULT_TENANT, resource, limit)  # type: ignore[attr-defined]


def _docx(marker: str) -> bytes:
    """A document the importer can actually split, and one that differs per call.

    A one-line paragraph is refused with 「切分后没有达到最小长度的条目」, and identical content
    is refused as an already-imported document -- either way the write never reaches the quota
    check, and the probe would be testing the splitter instead of the limit.
    """
    from docx import Document

    document = Document()
    document.add_paragraph(f"配额检查制度 {marker}")
    for index in range(1, CLAUSES_PER_DOCUMENT + 1):
        document.add_paragraph(
            f"第{index}条 这是第 {index} 段用于配额检查的条款文本（{marker}），长度足够被切分器识别为一条可用条目。"
        )
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _writes(index: int) -> dict[str, tuple[str, str, dict[str, Any], int]]:
    """One *creating* write per resource, and how many rows it adds.

    The row count is part of the probe, not a detail: a document becomes one knowledge entry
    per clause, so the two have to agree on what "one more write" costs. Declaring the limit
    as `current + rows` is what makes the assertion below the real property -- *this* call
    fits, the next one does not.

    Each index has to produce a body that really adds a row. Registering a data source is
    `on conflict(name) do update`, so sending the same payload twice updates the first row
    and leaves the count where it was -- a probe that re-used a body would be measuring an
    update and reporting it as a quota that failed to bind.
    """
    return {
        "data_sources": (
            "POST",
            "/data-sources",
            {
                "json": {
                    "name": f"配额检查来源 {index}",
                    "sourceType": "sqlite",
                    "connectionUri": "/tmp/quota-probe.sqlite3",
                }
            },
            1,
        ),
        "business_rules": (
            "POST",
            "/ontologies/1/rules",
            {
                "json": {
                    "code": f"quota_probe_rule_{index}",
                    "name": f"配额检查规则 {index}",
                    "ruleType": "validation",
                    "scopeObjectCode": "contract",
                    "expression": "amount > 0",
                    "severity": "warning",
                    "naturalLanguage": "金额必须大于零。",
                }
            },
            1,
        ),
        "knowledge_documents": (
            "POST",
            "/ontologies/1/knowledge/documents",
            {"files": {"file": (f"quota-{index}.docx", _docx(str(index)))}},
            1,
        ),
        "knowledge_entries": (
            "POST",
            "/ontologies/1/knowledge/documents",
            {"files": {"file": (f"quota-entry-{index}.docx", _docx(f"entry {index}"))}},
            CLAUSES_PER_DOCUMENT,
        ),
        # No session id: each first turn creates a conversation.
        "conversations": ("POST", "/agent/chat", {"json": {"message": "合同 1 是否合规？"}}, 1),
        "decision_records": (
            "POST",
            "/semantic/objects/contract/instances/1/assess",
            {"json": {"ontologyId": 1}},
            1,
        ),
    }


@pytest.mark.parametrize("resource", sorted(_writes(0)))
def test_a_declared_limit_binds_to_the_rows_the_platform_writes(quota_client: TestClient, resource: str) -> None:
    first = _writes(1)[resource]
    second = _writes(2)[resource]
    third = _writes(3)[resource]

    # Undeclared: the call proceeds. This is the half that keeps the platform usable -- an
    # undeclared quota permits the write, deliberately.
    open_call = quota_client.request(first[0], first[1], **first[2])
    assert open_call.status_code != 429, (
        f"没有声明配额时 {resource} 不该被限流：{open_call.status_code} {open_call.text[:120]}"
    )

    # Exactly what the next write costs, and one row less would fit: the call may pass, and
    # the one after it may not.
    _declare(quota_client, resource, _usage(quota_client, resource) + second[3])

    allowed = quota_client.request(second[0], second[1], **second[2])
    assert allowed.status_code not in (429, 500), (
        f"{resource} 的限额是「当前 + {second[3]}」，这一次写入应当被允许：{allowed.status_code} {allowed.text[:160]}"
    )

    refused = quota_client.request(third[0], third[1], **third[2])
    assert refused.status_code == 429, (
        f"{resource} 的配额已经用满，但 {third[0]} {third[1]} 返回 {refused.status_code}——"
        f"没有绑定到平台真正写入的那些行：{refused.text[:160]}"
    )


def test_a_document_is_measured_in_the_entries_it_will_write(quota_client: TestClient) -> None:
    """The unit of the `knowledge_entries` ceiling is the clause, not the upload.

    Asking for one slot per upload left the ceiling trivially porous: a document with one
    place left in the allowance and two hundred clauses in its body passed the check and
    wrote all two hundred. Whatever bounds the entry count has to be asked in entries.
    """
    second = _writes(2)["knowledge_entries"]
    assert second[3] > 1, "探针文档本身要不止一段，否则这条测试证明不了任何事"

    first_call = _writes(1)["knowledge_entries"]
    first = quota_client.request(first_call[0], first_call[1], **first_call[2])
    assert first.status_code not in (429, 500), first.text

    # One slot left, a document worth several: the half-written document this refuses is the
    # whole reason the check runs before the parse rather than after the insert.
    _declare(quota_client, "knowledge_entries", _usage(quota_client, "knowledge_entries") + 1)

    overflow = quota_client.request(second[0], second[1], **second[2])
    assert overflow.status_code == 429, (
        f"配额只剩 1 条，但一份 {second[3]} 条的文档被放行（{overflow.status_code}）——"
        f"配额是按「上传次数」而不是按「条目数」在算：{overflow.text[:160]}"
    )


def test_the_ontology_quota_binds_to_a_source_that_gets_drafted(quota_client: TestClient, tmp_path: Path) -> None:
    """Drafting a source that has none creates an ontology; that is what the quota counts.

    Its own test rather than a row in the table above, because the action is two calls (register
    a source, then draft it) and because the *rebuild* half matters here: drafting a source that
    already has a draft adds no row and must therefore not be refused by a limit already
    reached -- which is the case an administrator hits while fixing whatever the limit was for.
    """

    def register_source(index: int) -> int:
        # A real database with a table: a source that scans to nothing produces a draft with no
        # objects, and an objectless draft has no identity to recognise on the next request --
        # the quota then counts the re-draft as a creation, which is the conservative
        # direction, but it is not the case this test is about.
        database = tmp_path / f"probe-{index}.sqlite3"
        with sqlite3.connect(database) as raw:
            raw.execute("create table contract (id integer primary key, amount real)")

        created = quota_client.post(
            "/data-sources",
            json={
                "name": f"配额检查来源 {index}",
                "sourceType": "sqlite",
                "connectionUri": str(database),
            },
        )
        assert created.status_code in (200, 201), created.text
        source_id = int(created.json()["id"])
        quota_client.post(f"/data-sources/{source_id}/scan")
        return source_id

    def draft(source_id: int) -> Any:
        return quota_client.post("/ontologies/draft", json={"dataSourceId": source_id})

    first = draft(register_source(1))
    assert first.status_code not in (429, 500), first.text

    _declare(quota_client, "ontologies", _usage(quota_client, "ontologies") + 1)

    drafted_source = register_source(2)
    allowed = draft(drafted_source)
    assert allowed.status_code not in (429, 500), f"限额是「当前 + 1」，这一次应当被允许：{allowed.text[:160]}"

    # A rebuild of the draft that source already has adds no row, so a full quota does not
    # apply to it -- and refusing it would block fixing whatever the limit was for.
    rebuild = draft(drafted_source)
    assert rebuild.status_code != 429, f"重建已有草案被配额拒了：{rebuild.text[:160]}"

    refused = draft(register_source(3))
    assert refused.status_code == 429, (
        f"本体配额已经用满，但新建仍返回 {refused.status_code}——没有绑定到平台真正写入的那些行：{refused.text[:160]}"
    )


def test_an_update_is_not_a_creation(quota_client: TestClient) -> None:
    """A tenant at their limit must still be able to edit what they have.

    `upsert_business_rule` creates *or* updates, so the check asks whether the row exists: a
    limit of one with one rule is at the limit, not over it, and editing that rule is not the
    operation the quota was declared to stop.
    """
    body = _writes(1)["business_rules"][2]["json"]
    first = quota_client.post("/ontologies/1/rules", json=body)
    assert first.status_code in (200, 201), first.text

    _declare(quota_client, "business_rules", _usage(quota_client, "business_rules"))

    edited = quota_client.post("/ontologies/1/rules", json={**body, "name": "改过的名字"})
    assert edited.status_code in (200, 201), f"在限额内修改已有规则被拒了：{edited.text[:160]}"

    another = quota_client.post("/ontologies/1/rules", json={**body, "code": "quota_probe_rule_new"})
    assert another.status_code == 429, "超出限额的新规则没有被拒绝"
