"""The demo buttons, and what they report having destroyed.

「一键体验」 is the first thing a new user presses, and it is *destructive on the second
press*: the scenario registers a source, scans it, and drafts an ontology, and drafting a
source that already has a draft rebuilds it -- which clears the rules, mappings, relations
and workflows attached to the old one. A live run of it printed
`9 条规则、32 条映射、3 条关系、1 个工作流` as what a second click had just removed.

The backend has reported that since the rebuild landed (`discardedSummary`). These tests pin
the *HTTP* half of it, because that is the layer the screen reads: the library-level contract
is covered in `test_metadata_flow.py`, and a route that dropped the field on the way out
would leave every test there green while the button kept answering with a success message.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

ADMIN_PASSWORD = "demo-bootstrap-password"


@pytest.fixture
def demo_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """A live app whose platform *and* sample databases are throwaway files.

    The sample database matters: `aletheia demo` writes one, and a test that let it land on
    the default path would leave a file in the data directory and read another test's rows.
    """
    platform_db = tmp_path / "platform.sqlite3"
    monkeypatch.delenv("ONTOLOGY_AUTH_DISABLED", raising=False)
    monkeypatch.setenv("ONTOLOGY_ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ONTOLOGY_ADMIN_PASSWORD", ADMIN_PASSWORD)

    import ontology_platform.api as api_module
    import ontology_platform.database as database_module

    database_module._platform_adapter = None
    monkeypatch.setattr(database_module, "DEFAULT_PLATFORM_DB", platform_db)
    api_module = importlib.reload(api_module)
    monkeypatch.setattr(api_module, "DEFAULT_PLATFORM_DB", platform_db)
    monkeypatch.setattr(api_module, "DEFAULT_SAMPLE_DB", tmp_path / "legacy_contracts.sqlite3")
    monkeypatch.setattr(api_module, "DEFAULT_EQUIPMENT_SAMPLE_DB", tmp_path / "legacy_equipment.sqlite3")

    with TestClient(api_module.app) as client:
        login = client.post("/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD})
        assert login.status_code == 200, login.text
        client.headers.update({"Authorization": f"Bearer {login.json()['token']}"})
        yield client

    database_module._platform_adapter = None


def test_the_first_demo_reports_nothing_discarded(demo_client: TestClient) -> None:
    """A fresh instance has nothing to lose, and claiming otherwise teaches people to ignore it."""
    response = demo_client.post("/demo/bootstrap")
    assert response.status_code == 200, response.text

    ontology = response.json()["ontology"]
    assert ontology["discarded"] == {}
    assert "discardedSummary" not in ontology


def test_pressing_the_demo_button_again_says_what_it_destroyed(demo_client: TestClient) -> None:
    """The field the demo screen branches on. Without it the second press is a silent loss.

    Counted rather than described: the route returns the summary verbatim, and asserting the
    numbers is what would catch a rebuild that stopped reporting one of the categories.
    """
    first = demo_client.post("/demo/bootstrap")
    assert first.status_code == 200, first.text

    again = demo_client.post("/demo/bootstrap")
    assert again.status_code == 200, again.text

    ontology = again.json()["ontology"]
    discarded = ontology["discarded"]
    assert discarded.get("rules", 0) > 0, f"重建没有报告被清除的规则：{discarded}"
    assert discarded.get("mappings", 0) > 0, f"重建没有报告被清除的映射：{discarded}"
    assert ontology["discardedSummary"], "第二次运行没有给出可读的损失说明"
    assert str(discarded["rules"]) in ontology["discardedSummary"], (
        f"说明里的数字与计数字段对不上：{ontology['discardedSummary']!r} vs {discarded}"
    )
