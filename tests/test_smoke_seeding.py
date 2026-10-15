"""The render check's seeding script, held to what it says it did.

`scripts/seed_smoke_instance.py` exists so that every screen has a row to render: a screen
with no rows is a screen whose columns nobody has looked at, which is how eight blank-column
defects survived type checks, lint and the whole test suite. That makes the script's own
report the thing to check -- it returned `"knowledgeEntry": true` for a step that had
inserted nothing, because no knowledge document existed to hang the entry on, and
`"backup": ".../aletheia-smoke-backups"` for an archive written to a temporary directory
the application never reads. Both read as success.

So these assert the database, not the script's return value: what a screen can render is
rows, and a dict saying `true` is not one.
"""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def _load_seeder():
    spec = importlib.util.spec_from_file_location(
        "seed_smoke_instance_under_test", ROOT / "scripts" / "seed_smoke_instance.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def seeded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, dict]:
    """A demo instance, seeded the way the CI job seeds one."""
    import ontology_platform.backup as backup_module
    from ontology_platform.bootstrap import prepare_database
    from ontology_platform.database import connect, initialize_platform_db
    from ontology_platform.demo import run_contract_demo

    # The script deliberately writes its backup where the platform looks for backups, which
    # is the point of it; a test must not write to the developer's own backup directory.
    monkeypatch.setattr(backup_module, "BACKUP_DIR", tmp_path / "backups")

    platform_db = tmp_path / "platform.sqlite3"
    initialize_platform_db(platform_db)
    # The optional feature schemas, the same call the CLI's `init` makes: a database with
    # only the core tables has no document, conversation or workflow tables at all, and the
    # seeding would fail on the first screen it touches.
    with connect(platform_db) as conn:
        prepare_database(conn)
    run_contract_demo(platform_db, tmp_path / "sample.sqlite3")
    report = _load_seeder().seed(platform_db)
    return platform_db, report


def _count(platform_db: Path, table: str) -> int:
    with sqlite3.connect(platform_db) as conn:
        return int(conn.execute(f"select count(*) from {table}").fetchone()[0])


def test_every_screen_the_seeding_names_has_a_row(seeded) -> None:
    """One row per screen the demo leaves empty, counted in the database."""
    platform_db, _ = seeded
    for table in (
        "knowledge_document",
        "knowledge_entry",
        "permission_policy",
        "tool_execution_log",
        "model_invocation",
        "answer_feedback",
    ):
        assert _count(platform_db, table) > 0, f"{table} 一行都没有：对应页面渲染不出任何一列"
    # Not `tenant_quota`: a tenant with no quota row is *unlimited*, which the tenancy screen
    # renders as such (`不限量`), so the screen has its rows either way. Quotas are a
    # deployment's own decision, and a seeding script that invented them would be configuring
    # somebody's limits.


def test_the_knowledge_document_it_creates_can_be_cited(seeded) -> None:
    """A document is not a knowledge base unless an entry of it is confirmed.

    Ingestion lands every entry `pending`, and a pending entry is not retrievable -- so a
    seeded instance whose entries are all pending shows the screen but cannot answer the
    question the screen exists for.
    """
    platform_db, _ = seeded
    with sqlite3.connect(platform_db) as conn:
        confirmed = conn.execute("select count(*) from knowledge_entry where status = 'confirmed'").fetchone()[0]
        document = conn.execute("select id from knowledge_document limit 1").fetchone()
        linked = conn.execute(
            "select count(*) from knowledge_entry where document_id = ?", (int(document[0]),)
        ).fetchone()[0]
    assert confirmed > 0, "没有一条已确认的知识条目"
    assert linked > 0, "知识条目没有挂在文档上，文档表因此没有内容"


def test_the_backup_it_writes_is_one_the_application_will_list(seeded, tmp_path: Path) -> None:
    """Written where the platform looks, not to a directory of the script's own choosing.

    A backup in a temporary directory is a row that exists for whoever wrote it and for
    nobody else: the backup screen was empty on every machine, including the one that had
    just made an archive.
    """
    from ontology_platform.backup import list_backups

    platform_db, _ = seeded
    assert list_backups(), "平台自己的备份列表是空的——种子写的归档不在它读的目录里"
    assert _count(platform_db, "permission_role") > 0


def test_running_it_twice_changes_nothing(seeded) -> None:
    """Idempotent enough to re-run, which the docstring promises and CI relies on."""
    platform_db, _ = seeded
    before = {table: _count(platform_db, table) for table in ("knowledge_document", "answer_feedback")}
    _load_seeder().seed(platform_db)
    after = {table: _count(platform_db, table) for table in ("knowledge_document", "answer_feedback")}
    assert before == after, "第二次运行又插了一份"
