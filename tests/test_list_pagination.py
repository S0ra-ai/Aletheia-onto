"""The list endpoints that can grow with the customer's data take a page, and say so.

`docs/limitations.md` used to read "List endpoints are mostly unpaginated", and the honest
version of that is not "we should paginate everything" -- a list bounded by *platform
configuration* (the six built-in roles, the quota resource kinds, the axiom kinds) does not need
a pager, and adding one would be ceremony. It is: every list whose length is a function of
**the customer's schema** takes a page, and returns a block saying how much of the list it is.

Two properties are what this file is for, and both are easy to get wrong in a way nothing shows:

* **Not passing a limit returns everything.** These endpoints returned the whole list before
  they took a `limit`, and several screens read `array.length` for a tab count or key their
  empty state off it. Quietly capping the default at fifty would have made those numbers wrong
  without making anything fail -- the same shape as the blank columns.
* **`total` is a real count.** A pager showing "51 of 51" over nine hundred rows is worse than
  no pager, because it looks like an answer. So the count is asserted against rows that are
  actually there, not against the size of the page.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from ontology_platform.config import QUERY_LIMITS
from ontology_platform.database import connect
from ontology_platform.pagination import page_block, resolve_page

ADMIN_PASSWORD = "paged-list-password-123"

# Well past `max_page_size`, so a page is a page and the counts mean something.
FILLER = QUERY_LIMITS.max_page_size + 37


def test_a_page_is_clamped_and_an_absent_limit_means_everything() -> None:
    """The two decisions the whole feature rests on, asserted directly.

    `resolve_page` is where "no limit" and "a limit" are told apart, and every endpoint routes
    through it. If it ever started defaulting to a page size, every caller that does not pass
    one would silently start receiving a truncated list.
    """
    assert resolve_page(None) == (None, 0)
    assert resolve_page(None, 5) == (None, 5)
    assert resolve_page(10) == (10, 0)
    assert resolve_page(10, 30) == (10, 30)
    # Clamped, not trusted: `LIMIT -1` is "no limit" in SQLite, which is the defect
    # `tests/test_query_limit_clamping.py` exists for.
    assert resolve_page(-1) == (1, 0)
    assert resolve_page(0) == (1, 0)
    assert resolve_page(10**9) == (QUERY_LIMITS.max_page_size, 0)
    assert resolve_page(50, -20) == (50, 0)


def test_the_block_says_whether_there_is_more() -> None:
    assert page_block(limit=None, offset=0, total=900, returned=900)["hasMore"] is False
    assert page_block(limit=50, offset=0, total=900, returned=50)["hasMore"] is True
    assert page_block(limit=50, offset=850, total=900, returned=50)["hasMore"] is False
    # A last page that is short: offset + returned reaches the total exactly.
    assert page_block(limit=50, offset=880, total=900, returned=20)["hasMore"] is False
    # And one row short of the end still has more.
    assert page_block(limit=50, offset=880, total=901, returned=20)["hasMore"] is True


@pytest.fixture
def seeded_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """A live app whose paginated lists hold more rows than one page."""
    platform_db = tmp_path / "platform.sqlite3"
    sample_db = tmp_path / "legacy_contracts.sqlite3"
    monkeypatch.delenv("ONTOLOGY_AUTH_DISABLED", raising=False)
    monkeypatch.setenv("ONTOLOGY_ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ONTOLOGY_ADMIN_PASSWORD", ADMIN_PASSWORD)

    import ontology_platform.api as api_module
    import ontology_platform.database as database_module
    from ontology_platform.database import connect, initialize_platform_db
    from ontology_platform.onboarding import run_onboarding_pipeline
    from ontology_platform.sample_data import create_contract_sample_db

    database_module._platform_adapter = None
    monkeypatch.setattr(database_module, "DEFAULT_PLATFORM_DB", platform_db)

    initialize_platform_db(platform_db)
    create_contract_sample_db(sample_db)
    run_onboarding_pipeline(
        platform_db,
        "分页样例系统",
        "sqlite",
        str(sample_db),
        domain="合同管理",
        system_category="database+api",
        blueprint_id="contract-management",
    )

    from ontology_platform.bootstrap import prepare_database
    from ontology_platform.ontology import generate_ontology_draft

    with connect(platform_db) as conn:
        prepare_database(conn)
        source_id = int(conn.execute("select id from data_source").fetchone()["id"])
        ontology_id = int(conn.execute("select id from ontology").fetchone()["id"])

    draft = generate_ontology_draft(platform_db, source_id)
    del draft

    # The administrator *first*, and outside the connection below. `ensure_bootstrap_admin`
    # creates one only when `platform_user` is empty, so filler rows inserted before it would
    # leave the fixture with accounts nobody can sign in as -- surfacing as `KeyError: 'token'`
    # three frames from the cause. And it opens its own connection, which SQLite refuses while
    # one is already open: the same `database is locked` that would otherwise look like a flake.
    from ontology_platform.auth import ensure_bootstrap_admin, hash_password

    ensure_bootstrap_admin(platform_db)

    with connect(platform_db) as conn:
        # Mappings and rules for the ontology, source operations for the data source, and
        # ontology versions. All four are relationships the platform defines, so the rows are
        # well-formed rather than filler that only the count can see.
        conn.executemany(
            "insert into semantic_mapping (ontology_id, mapping_type, source_ref, target_ref,"
            " confidence, status, evidence) values (?, 'table', ?, ?, 0.9, 'pending', '')",
            [(ontology_id, f"table:t{index}", "table:t0") for index in range(FILLER)],
        )
        conn.executemany(
            "insert into business_rule (ontology_id, code, name, rule_type, scope_object_code,"
            " expression, severity, natural_language, status) values (?, ?, ?, 'validation',"
            " 'contract', 'amount > 0', 'warning', '', 'draft')",
            [(ontology_id, f"rule_{index}", f"规则 {index}") for index in range(FILLER)],
        )
        conn.executemany(
            "insert into source_api (data_source_id, operation_code, name, method, path, semantic_action)"
            " values (?, ?, ?, 'GET', ?, '')",
            [(source_id, f"op_{index}", f"操作 {index}", f"/o/{index}") for index in range(FILLER)],
        )
        conn.executemany(
            "insert into ontology (name, domain, version, status) values (?, '测试', '0.1.0', 'draft')",
            [(f"副本 {index}",) for index in range(FILLER)],
        )
        # Enough audit rows that a page is a page and the offset-versus-cursor tests have a
        # boundary to cross. Every action the platform has taken so far is also in this table;
        # these are added on top of it.
        conn.executemany(
            "insert into audit_log (actor, action, target_type, target_id, detail)"
            " values ('seeder', 'filler', 'test', ?, '{}')",
            [(str(index),) for index in range(40)],
        )

        user_hash, user_salt, _iterations = hash_password("filler-password-123")
        conn.executemany(
            "insert into platform_user (username, display_name, role_code, password_hash,"
            " password_salt) values (?, '', 'analyst', ?, ?)",
            [(f"analyst_{index}", user_hash, user_salt) for index in range(QUERY_LIMITS.max_page_size + 5)],
        )

    api_module = importlib.reload(api_module)
    monkeypatch.setattr(api_module, "DEFAULT_PLATFORM_DB", platform_db)

    with TestClient(api_module.app) as client:
        client.platform_db = platform_db  # type: ignore[attr-defined]
        client.ontology_id = ontology_id  # type: ignore[attr-defined]
        client.source_id = source_id  # type: ignore[attr-defined]
        yield client

    database_module._platform_adapter = None


def _headers(client: TestClient) -> dict[str, str]:
    token = client.post("/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


# `(path, the key the rows come under)`. Every one of these is a list whose length is a function
# of the customer's schema or of how long they have been using the platform -- which is the
# whole distinction between a list that needs a page and one that does not.
PAGED_LISTS = (
    ("/ontologies/{ontology}/mappings", "items"),
    ("/ontologies/{ontology}/rules", "items"),
    ("/data-sources/{source}/apis", "apis"),
    ("/ontologies", "items"),
    ("/auth/users", "items"),
)


def _fill(path: str, client: TestClient) -> str:
    return path.format(
        ontology=client.ontology_id,  # type: ignore[attr-defined]
        source=client.source_id,  # type: ignore[attr-defined]
    )


@pytest.mark.parametrize(("template", "key"), PAGED_LISTS)
def test_the_whole_list_comes_back_when_no_limit_is_asked_for(
    seeded_client: TestClient, template: str, key: str
) -> None:
    """The property every existing caller depends on, and the one a default cap would break.

    Several screens read `array.length` for a tab count and several key their empty state off
    it. A quiet default page size would have made those numbers wrong without making anything
    fail -- which is how this codebase has shipped seven blank columns already.
    """
    path = _fill(template, seeded_client)
    response = seeded_client.get(path, headers=_headers(seeded_client))
    assert response.status_code == 200, response.text
    payload = response.json()

    rows = payload[key]
    assert len(rows) > QUERY_LIMITS.max_page_size, f"{path} 只返回了 {len(rows)} 行，不足以证明「不传 limit 就全给」"
    assert payload["pagination"]["limit"] is None, payload["pagination"]
    assert payload["pagination"]["hasMore"] is False, payload["pagination"]
    assert payload["pagination"]["total"] == len(rows), payload["pagination"]


@pytest.mark.parametrize(("template", "key"), PAGED_LISTS)
def test_a_page_is_a_page_and_the_total_is_the_real_count(seeded_client: TestClient, template: str, key: str) -> None:
    path = _fill(template, seeded_client)
    headers = _headers(seeded_client)
    everything = seeded_client.get(path, headers=headers).json()
    total = everything["pagination"]["total"]

    seen: set[str] = set()
    offset = 0
    pages = 0
    while True:
        response = seeded_client.get(f"{path}?limit=50&offset={offset}", headers=headers)
        assert response.status_code == 200, response.text
        payload = response.json()
        rows = payload[key]
        assert len(rows) <= 50, f"{path} 一页返回了 {len(rows)} 行"
        assert payload["pagination"]["total"] == total, (
            f"{path} 的 total 在翻页之间变了：{payload['pagination']['total']} vs {total}"
        )
        assert payload["pagination"]["offset"] == offset, payload["pagination"]

        # Walks every row rather than comparing counts: a pager that returns the first page
        # forever also returns 50 rows a page, and only the walk notices.
        for row in rows:
            identity = str(row.get("id") or row.get("code") or row.get("operationCode"))
            assert identity not in seen, f"{path} 在第 {pages} 页重复了 {identity}"
            seen.add(identity)

        pages += 1
        if not payload["pagination"]["hasMore"]:
            break
        offset += 50
        assert pages < 5000, "翻页没有终止"

    assert len(seen) == total, f"{path} 翻完只见到 {len(seen)} 行，total 说是 {total}"


@pytest.mark.parametrize(("template", "key"), PAGED_LISTS)
def test_a_page_past_the_end_is_empty_rather_than_an_error(seeded_client: TestClient, template: str, key: str) -> None:
    """A reader who deletes rows while paging lands here, and it is not an error condition."""
    path = _fill(template, seeded_client)
    response = seeded_client.get(f"{path}?limit=50&offset={10**9}", headers=_headers(seeded_client))
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload[key] == []
    assert payload["pagination"]["hasMore"] is False
    assert payload["pagination"]["total"] > 0, "空页不该把 total 也清掉——分页器要用它"


# -- Cursors, for the two lists that are appended to while they are read --


def test_offset_paging_loses_a_row_when_the_list_is_appended_to(seeded_client: TestClient) -> None:
    """The defect cursors exist for, demonstrated rather than asserted in prose.

    `limit`/`offset` answers "the rows after the first N" and re-counts N from the top every
    time. On an append-only list that is being written to while it is read, a row arriving
    between page one and page two pushes everything down by one -- so the last row of page one
    reappears as the first row of page two and the reader never sees the row that fell across
    the boundary. On an audit trail, "never" is the one that matters: the row that went missing
    is exactly the kind an investigation is looking for.
    """
    headers = _headers(seeded_client)
    path = "/governance/audit-log?limit=10"

    first = seeded_client.get(path, headers=headers).json()["items"]
    assert len(first) == 10
    seen_first = {row["id"] for row in first}

    # Somebody writes to the platform while the reader is looking at page one.
    with connect(seeded_client.platform_db) as conn:  # type: ignore[attr-defined]
        conn.execute(
            "insert into audit_log (actor, action, target_type, target_id, detail)"
            " values ('racer', 'arrived_between_pages', 'test', '1', '{}')"
        )

    second = seeded_client.get(path + "&offset=10", headers=headers).json()["items"]
    seen_second = {row["id"] for row in second}

    # The offset page repeats the row that slid across the boundary, and skips the one that
    # slid off the end of page one. Both halves are the defect.
    assert seen_first & seen_second, "偏移分页没有重复行——这个复现没有成立，断言因此没有意义"


def test_cursor_paging_sees_every_row_despite_the_same_insert(seeded_client: TestClient) -> None:
    """The same interleaving, with the cursor the endpoints now take.

    A cursor names a position in the ordering rather than a count from the start, so an insert
    elsewhere cannot move the boundary. This walks the whole trail in pages while rows are being
    added, and asserts that everything that existed at the start is still seen exactly once.
    """
    headers = _headers(seeded_client)
    with connect(seeded_client.platform_db) as conn:  # type: ignore[attr-defined]
        before = {int(row["id"]) for row in conn.execute("select id from audit_log").fetchall()}

    seen: list[int] = []
    before_id = None
    for _page in range(200):
        query = "/governance/audit-log?limit=10"
        if before_id is not None:
            query += f"&beforeId={before_id}"
        payload = seeded_client.get(query, headers=headers).json()
        rows = payload["items"]
        if not rows:
            break
        seen.extend(int(row["id"]) for row in rows)
        before_id = payload["cursors"]["nextBefore"]
        assert before_id is not None
        # And somebody writes, between every pair of pages.
        with connect(seeded_client.platform_db) as conn:  # type: ignore[attr-defined]
            conn.execute(
                "insert into audit_log (actor, action, target_type, target_id, detail)"
                " values ('racer', 'arrived_between_pages', 'test', '1', '{}')"
            )

    assert len(seen) == len(set(seen)), "游标分页重复了行"
    assert before <= set(seen), (
        f"翻完整个审计日志，最初存在的行里少了 {sorted(before - set(seen))}——"
        "而审计留痕里「少了一行」正是最要紧的那种丢失"
    )


def test_a_cursor_page_says_where_to_continue(seeded_client: TestClient) -> None:
    """Both directions, because "older" and "newer" are different questions.

    A reader walking back through an audit trail wants the rows before what they have; a poller
    wants the rows after. Each is derivable from the other plus the ordering, which is a second
    place for it to be wrong -- so both are sent.
    """
    headers = _headers(seeded_client)
    payload = seeded_client.get("/governance/audit-log?limit=5", headers=headers).json()
    ids = [row["id"] for row in payload["items"]]

    assert payload["cursors"]["nextBefore"] == min(ids)
    assert payload["cursors"]["nextAfter"] == max(ids)

    # And it is usable: asking for what came after a row returns rows newer than it.
    after = seeded_client.get(f"/governance/audit-log?limit=5&afterId={min(ids)}", headers=headers).json()["items"]
    assert after, "afterId 没有返回任何行，游标不可用"
    assert all(row["id"] > min(ids) for row in after)


def test_cursors_are_absent_when_there_is_no_page(seeded_client: TestClient) -> None:
    """An unpaginated response has no position to continue from, and saying `null` is the answer.

    A client that paged anyway would ask for `beforeId=null` and get the newest rows again --
    which on a polling loop is an infinite re-read of the same page.
    """
    from ontology_platform.pagination import cursor_block

    assert cursor_block(rows=[], limit=10) == {"nextBefore": None, "nextAfter": None}
    assert cursor_block(rows=[{"id": 1}], limit=None) == {"nextBefore": None, "nextAfter": None}
