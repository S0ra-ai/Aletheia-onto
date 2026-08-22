"""The `aletheia` command line.

ROADMAP stage F. What is being tested is not argument parsing -- it is the two
properties that make a CLI safe to hand to an operator:

- **The governance gate is not bypassable by convenience.** `publish` without `--force`
  must refuse and say why. A CLI flag that skipped the release gate would make the gate
  advisory, which is the same failure as ADR-0002's "skip on error".
- **A CLI-initialised database is not missing tables.** If `init` created fewer schemas
  than the HTTP startup does, the difference surfaces much later as "this feature
  returns nothing", which reads as a bug rather than as a setup gap.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from ontology_platform.cli import build_parser, main


def _run(capsys, *argv: str) -> tuple[int, str, str]:
    code = main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _json(capsys, *argv: str) -> dict:
    code, out, _ = _run(capsys, *argv)
    assert code == 0, out
    # Some commands print more than one document (demo runs init first); take the last.
    documents = [chunk for chunk in out.split("\n{") if chunk.strip()]
    payload = documents[-1]
    if not payload.lstrip().startswith("{"):
        payload = "{" + payload
    return json.loads(payload)


@pytest.fixture
def platform_db(tmp_path: Path) -> Path:
    return tmp_path / "platform.sqlite3"


@pytest.fixture
def source_db(tmp_path: Path) -> Path:
    path = tmp_path / "business.sqlite3"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        create table customers (id integer primary key, name text not null, credit_status text not null);
        create table contracts (
            id integer primary key,
            customer_id integer not null references customers(id),
            amount numeric not null,
            status text not null,
            signed_date text
        );
        insert into customers values (1, '甲公司', 'normal');
        insert into contracts values (1, 1, 500, 'effective', '2026-01-01');
        """
    )
    conn.commit()
    conn.close()
    return path


# -- Surface --


def test_every_subcommand_is_reachable() -> None:
    """A subcommand with no handler wired up fails only when someone runs it."""
    parser = build_parser()
    actions = [action for action in parser._actions if action.dest == "command"]
    assert actions, "未找到子命令分组"
    for name, subparser in actions[0].choices.items():
        assert subparser.get_default("func") is not None, f"{name} 未绑定处理函数"


def test_expected_commands_exist() -> None:
    parser = build_parser()
    choices = next(action for action in parser._actions if action.dest == "command").choices
    assert {"init", "connect", "model", "assess", "publish", "demo", "serve", "doctor"} <= set(choices)


def test_a_command_is_required() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args([])


# -- init --


def test_init_creates_the_platform_database_and_reports_where(capsys, platform_db) -> None:
    """A CLI that silently defaults elsewhere produces work that cannot be found."""
    payload = _json(capsys, "--platform-db", str(platform_db), "init")
    assert payload["platformDb"] == str(platform_db)
    assert platform_db.exists()


def test_init_creates_every_schema_the_server_would(capsys, platform_db) -> None:
    """Otherwise a missing table surfaces later as "this feature returns nothing"."""
    _json(capsys, "--platform-db", str(platform_db), "init")
    with sqlite3.connect(platform_db) as conn:
        tables = {row[0] for row in conn.execute("select name from sqlite_master where type='table'")}
    # One representative table per optional feature schema.
    expected = {
        "business_object",
        "business_rule",
        "platform_user",
        "workflow_definition",
        "agent_role",
        "knowledge_document",
        "cross_object_aggregate",
        "business_event",
        "conversation",
    }
    assert expected <= tables, f"缺少表: {sorted(expected - tables)}"


def test_init_is_idempotent(capsys, platform_db) -> None:
    _json(capsys, "--platform-db", str(platform_db), "init")
    payload = _json(capsys, "--platform-db", str(platform_db), "init")
    # The bootstrap admin already exists, so no new credentials are minted.
    assert payload["bootstrapAdmin"] is None


# -- The loop --


def test_connect_scans_and_points_at_the_next_step(capsys, platform_db, source_db) -> None:
    _json(capsys, "--platform-db", str(platform_db), "init")
    payload = _json(capsys, "--platform-db", str(platform_db), "connect", str(source_db), "--domain", "合同管理")
    assert payload["dataSourceId"] == 1
    assert "model 1" in payload["next"]


def test_model_generates_a_draft_that_is_not_published(capsys, platform_db, source_db) -> None:
    """A draft whose mappings are unreviewed must not be publishable by accident."""
    _json(capsys, "--platform-db", str(platform_db), "init")
    _json(capsys, "--platform-db", str(platform_db), "connect", str(source_db), "--domain", "合同管理")
    payload = _json(capsys, "--platform-db", str(platform_db), "model", "1")
    assert payload["status"] == "draft"
    assert payload["objects"]


def test_assess_leads_with_the_verdict(capsys, platform_db, source_db) -> None:
    """Printing all the evidence by default would bury the answer."""
    _json(capsys, "--platform-db", str(platform_db), "init")
    _json(capsys, "--platform-db", str(platform_db), "connect", str(source_db), "--domain", "合同管理")
    _json(capsys, "--platform-db", str(platform_db), "model", "1")
    payload = _json(capsys, "--platform-db", str(platform_db), "assess", "1", "contract", "1")
    assert payload["decision"] in {"approved", "review", "blocked"}
    assert "failedRules" in payload
    assert "record" not in payload


def test_verbose_assess_carries_the_full_evidence(capsys, platform_db, source_db) -> None:
    _json(capsys, "--platform-db", str(platform_db), "init")
    _json(capsys, "--platform-db", str(platform_db), "connect", str(source_db), "--domain", "合同管理")
    _json(capsys, "--platform-db", str(platform_db), "model", "1")
    payload = _json(capsys, "--platform-db", str(platform_db), "assess", "1", "contract", "1", "--verbose")
    assert "ruleResults" in payload


# -- The gate --


def test_publish_refuses_when_the_gate_finds_a_blocker(capsys, platform_db, source_db) -> None:
    """The property that matters most here. A convenience flag that skipped the gate
    would make the gate advisory."""
    _json(capsys, "--platform-db", str(platform_db), "init")
    _json(capsys, "--platform-db", str(platform_db), "connect", str(source_db), "--domain", "合同管理")
    _json(capsys, "--platform-db", str(platform_db), "model", "1")
    code, _, _ = _run(capsys, "--platform-db", str(platform_db), "publish", "1")
    assert code == 1


def test_the_refusal_says_what_to_do_about_it(capsys, platform_db, source_db) -> None:
    _json(capsys, "--platform-db", str(platform_db), "init")
    _json(capsys, "--platform-db", str(platform_db), "connect", str(source_db), "--domain", "合同管理")
    _json(capsys, "--platform-db", str(platform_db), "model", "1")
    _, _, error = _run(capsys, "--platform-db", str(platform_db), "publish", "1")
    assert "--force" in error
    assert "审核" in error or "门禁" in error


def test_force_publish_is_audited(capsys, platform_db, source_db) -> None:
    """An override that left no trace would be indistinguishable from a clean release.

    Note what `--force` does *not* cover: unreviewed mappings are a hard precondition,
    not a gate finding, so force cannot skip them. That distinction is deliberate --
    publishing an ontology whose mappings nobody looked at would make every verdict
    derived from it unaccountable, and no flag should be able to authorise that.
    """
    from ontology_platform.governance import list_semantic_mappings, review_semantic_mapping

    _json(capsys, "--platform-db", str(platform_db), "init")
    _json(capsys, "--platform-db", str(platform_db), "connect", str(source_db), "--domain", "合同管理")
    _json(capsys, "--platform-db", str(platform_db), "model", "1")
    for mapping in list_semantic_mappings(platform_db, 1)["items"]:
        review_semantic_mapping(platform_db, mapping["id"], "confirmed", "reviewer", "")
    _json(capsys, "--platform-db", str(platform_db), "publish", "1", "--force", "--actor", "tester")
    with sqlite3.connect(platform_db) as conn:
        rows = conn.execute("select actor, detail from audit_log where action like '%publish%'").fetchall()
    assert rows, "强制发布未写入审计"
    assert any(row[0] == "tester" for row in rows)


def test_force_cannot_skip_unreviewed_mappings(capsys, platform_db, source_db) -> None:
    """Publishing an ontology whose mappings nobody reviewed would make every verdict
    derived from it unaccountable. No flag authorises that."""
    _json(capsys, "--platform-db", str(platform_db), "init")
    _json(capsys, "--platform-db", str(platform_db), "connect", str(source_db), "--domain", "合同管理")
    _json(capsys, "--platform-db", str(platform_db), "model", "1")
    code, _, error = _run(capsys, "--platform-db", str(platform_db), "publish", "1", "--force")
    assert code == 1
    assert "待审核" in error


# -- demo and doctor --


def test_demo_runs_the_whole_loop(capsys, tmp_path) -> None:
    payload = _json(
        capsys,
        "--platform-db",
        str(tmp_path / "demo.sqlite3"),
        "demo",
        "--sample-db",
        str(tmp_path / "sample.sqlite3"),
    )
    assert payload["decision"] in {"approved", "review", "blocked"}
    assert payload["objectCode"], "样例对象编码应从蓝图词汇中发现，而不是硬编码"


def test_quiet_demo_emits_exactly_one_document(capsys, tmp_path) -> None:
    """A caller parsing the output wants one document, not a concatenated stream --
    splitting one is fiddly enough that everyone gets it slightly wrong."""
    code, out, _ = _run(
        capsys,
        "--platform-db",
        str(tmp_path / "demo.sqlite3"),
        "demo",
        "--quiet",
        "--sample-db",
        str(tmp_path / "sample.sqlite3"),
    )
    assert code == 0
    payload = json.loads(out)
    assert payload["decision"] in {"approved", "review", "blocked"}


def test_doctor_reports_configuration_and_extension_points(capsys, platform_db) -> None:
    """The three things that account for most "it does nothing" reports."""
    _json(capsys, "--platform-db", str(platform_db), "init")
    payload = _json(capsys, "--platform-db", str(platform_db), "doctor")
    assert payload["initialised"] is True
    assert payload["sourceTypes"]
    assert payload["resolverKinds"]
    assert payload["ruleFunctions"]
    assert set(payload["extras"]) == {"web", "postgresql", "mysql", "documents"}


def test_doctor_says_which_driver_an_inactive_source_needs(capsys, platform_db) -> None:
    """ "Why is Oracle not in the list" is the most common question here, so it is answered
    rather than requiring someone to read the source."""
    _json(capsys, "--platform-db", str(platform_db), "init")
    payload = _json(capsys, "--platform-db", str(platform_db), "doctor")
    declared = {item["sourceType"]: item for item in payload["declaredSqlSources"]}
    assert {"oracle", "sqlserver", "dameng", "kingbase"} <= set(declared)
    for item in declared.values():
        # Either it works, or it names the package to install.
        assert item["available"] or item["hint"], item
    assert payload["writebackSchemes"], "写回通道应可见"
    assert "csv" in payload["sourceTypes"], "CSV 无需驱动，应默认可用"


def test_assess_can_target_a_past_moment(capsys, platform_db, source_db) -> None:
    """A past-tense verdict must echo the moment, or it is indistinguishable from one about
    the present."""
    from ontology_platform.temporal import record_attribute_version

    _json(capsys, "--platform-db", str(platform_db), "init")
    _json(capsys, "--platform-db", str(platform_db), "connect", str(source_db), "--domain", "合同管理")
    _json(capsys, "--platform-db", str(platform_db), "model", "1")
    record_attribute_version(platform_db, 1, "contract", "1", "amount", 99999, valid_from="2026-01-01")
    payload = _json(capsys, "--platform-db", str(platform_db), "assess", "1", "contract", "1", "--as-of", "2026-02-01")
    assert payload["asOf"] == "2026-02-01 00:00:00"


def test_an_unparseable_as_of_is_refused(capsys, platform_db, source_db) -> None:
    """Silently ignoring it would return a present-tense verdict to a caller who asked for a
    past one."""
    _json(capsys, "--platform-db", str(platform_db), "init")
    _json(capsys, "--platform-db", str(platform_db), "connect", str(source_db), "--domain", "合同管理")
    _json(capsys, "--platform-db", str(platform_db), "model", "1")
    code, _, error = _run(capsys, "--platform-db", str(platform_db), "assess", "1", "contract", "1", "--as-of", "去年")
    assert code == 1
    assert "Traceback" not in error


def test_doctor_says_what_to_do_when_uninitialised(capsys, tmp_path) -> None:
    payload = _json(capsys, "--platform-db", str(tmp_path / "absent.sqlite3"), "doctor")
    # An empty SQLite file is created on connect, so "initialised" may be true while the
    # schema is absent; either way doctor must not raise.
    assert "platformDb" in payload


def test_an_error_is_a_message_not_a_traceback(capsys, platform_db) -> None:
    """A stack trace is the wrong output for an operator running a command."""
    _json(capsys, "--platform-db", str(platform_db), "init")
    code = main(["--platform-db", str(platform_db), "model", "999"])
    captured = capsys.readouterr()
    assert code == 1
    assert "Traceback" not in captured.err
    assert "aletheia:" in captured.err
