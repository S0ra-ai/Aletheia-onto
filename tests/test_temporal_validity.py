"""Temporal validity: what was true, and when.

Generality item #8, the last piece of the metamodel. Rules already had validity windows;
attributes had exactly one value -- the current one.

This is not a reporting feature, and the test that says why is
`test_a_past_verdict_uses_past_values`: a compliance audit in March asks whether the
January approval was correct *given what was known in January*. Re-assessing against
today's values answers a different question and returns a confidently wrong answer, which
is worse than refusing.

The properties pinned down here:

- an as-of read selects the version whose window contains that instant, exactly
- an attribute with no version covering the instant is **absent**, never interpolated from
  a neighbour, so a rule referencing it fails closed rather than citing a fabricated fact
- history is append-only: a correction is a new version, so a verdict recorded earlier
  still cites a value that exists
- valid time and transaction time are distinguishable, because a backdated correction
  changes what was true without changing what was known
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
from ontology_platform.ontology import generate_ontology_draft
from ontology_platform.semantic_kernel import assess_instance, build_runtime
from ontology_platform.temporal import (
    MAX_VERSIONS_PER_INSTANCE,
    AttributeVersion,
    TemporalError,
    capture_snapshot,
    coverage,
    init_temporal_schema,
    instance_history,
    load_versions,
    normalize_instant,
    record_attribute_version,
    temporal_tables_exist,
    values_as_of,
)

# -- Window arithmetic --


def _version(**overrides) -> AttributeVersion:
    defaults = {"attribute_code": "amount", "value": 1, "valid_from": "2026-01-01 00:00:00"}
    return AttributeVersion(**{**defaults, **overrides})


def test_a_window_is_half_open() -> None:
    """`[from, to)`. If both adjacent versions matched a boundary instant, which value a
    verdict used would depend on row order."""
    version = _version(valid_to="2026-02-01 00:00:00")
    assert version.covers("2026-01-01 00:00:00") is True
    assert version.covers("2026-01-15 00:00:00") is True
    assert version.covers("2026-02-01 00:00:00") is False
    assert version.covers("2025-12-31 23:59:59") is False


def test_an_open_ended_window_covers_everything_after_its_start() -> None:
    version = _version()
    assert version.open_ended is True
    assert version.covers("2099-01-01 00:00:00") is True


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-01-01", "2026-01-01 00:00:00"),
        ("2026-01-01 10:30", "2026-01-01 10:30:00"),
        ("2026-01-01T10:30:00", "2026-01-01 10:30:00"),
        ("2026-01-01 10:30:00", "2026-01-01 10:30:00"),
    ],
)
def test_instants_are_normalised(raw, expected) -> None:
    assert normalize_instant(raw) == expected


@pytest.mark.parametrize("bad", ["", None, "yesterday", "01/02/2026", "2026-13-01"])
def test_an_ambiguous_instant_is_refused(bad) -> None:
    """A misparsed instant silently selects the wrong version, and the resulting verdict
    looks perfectly ordinary."""
    with pytest.raises(TemporalError):
        normalize_instant(bad)


# -- Recording --


@pytest.fixture
def platform_db(tmp_path: Path) -> Path:
    """A platform database with the temporal schema and one ontology to hang history off.

    The ontology row is required: `attribute_version.ontology_id` is a real foreign key, so
    that history cannot outlive the model it describes -- a version referencing a deleted
    ontology would be an unattributable fact.
    """
    path = tmp_path / "platform.sqlite3"
    initialize_platform_db(path)
    with connect(path) as conn:
        init_temporal_schema(conn)
        # Idempotent: startup runs this on every boot.
        init_temporal_schema(conn)
        conn.execute(
            "insert into ontology (name, domain, version, status) values ('时态测试', '合同管理', 'v1', 'draft')"
        )
    return path


def _record(platform_db: Path, value, valid_from: str, attribute: str = "amount", **kwargs) -> dict:
    return record_attribute_version(platform_db, 1, "contract", "1", attribute, value, valid_from=valid_from, **kwargs)


def test_recording_a_version_closes_the_previous_one(platform_db: Path) -> None:
    _record(platform_db, 100, "2026-01-01")
    second = _record(platform_db, 200, "2026-02-01")
    with connect(platform_db) as conn:
        versions = load_versions(conn, 1, "contract", "1")
    assert [item.value for item in versions] == [100, 200]
    assert versions[0].valid_to == "2026-02-01 00:00:00"
    assert versions[1].open_ended is True
    assert second["supersededVersionId"] == versions[0].version_id


def test_history_is_append_only(platform_db: Path) -> None:
    """A corrected value is a new version. Rewriting history would leave a verdict citing
    a value that no longer appears anywhere."""
    import ontology_platform.temporal as temporal

    exported = [name for name in dir(temporal) if not name.startswith("_")]
    assert not [name for name in exported if "delete" in name.lower()], exported
    _record(platform_db, 100, "2026-01-01")
    _record(platform_db, 200, "2026-02-01")
    with connect(platform_db) as conn:
        assert len(load_versions(conn, 1, "contract", "1")) == 2


def test_values_keep_their_type_across_a_round_trip(platform_db: Path) -> None:
    """A number that came back as a string would make `amount > 0` compare `str > int`,
    which fail-closed reports as a violation -- storage turning into a wrong verdict."""
    _record(platform_db, 100, "2026-01-01", attribute="amount")
    _record(platform_db, 12.5, "2026-01-01", attribute="rate")
    _record(platform_db, True, "2026-01-01", attribute="active")
    _record(platform_db, None, "2026-01-01", attribute="closed_at")
    _record(platform_db, {"a": 1}, "2026-01-01", attribute="meta")
    with connect(platform_db) as conn:
        values = values_as_of(conn, 1, "contract", "1", "2026-06-01")
    assert values["amount"] == 100 and isinstance(values["amount"], int)
    assert values["rate"] == 12.5
    assert values["active"] is True
    assert values["closed_at"] is None
    assert values["meta"] == {"a": 1}


def test_a_backdated_version_splits_the_right_window(platform_db: Path) -> None:
    """Late-arriving data is the normal case in legacy integration, not an error.

    Inserting a March value after a June one must close *March's* predecessor, not the
    latest row -- otherwise the June value silently loses its window.
    """
    _record(platform_db, 100, "2026-01-01")
    _record(platform_db, 300, "2026-06-01")
    _record(platform_db, 200, "2026-03-01")
    with connect(platform_db) as conn:
        assert values_as_of(conn, 1, "contract", "1", "2026-02-01")["amount"] == 100
        assert values_as_of(conn, 1, "contract", "1", "2026-04-01")["amount"] == 200
        assert values_as_of(conn, 1, "contract", "1", "2026-07-01")["amount"] == 300


def test_a_backdated_insert_does_not_extend_coverage_past_a_known_end(platform_db: Path) -> None:
    """It inherits the closed end of the window it split, so it cannot silently claim to
    know a period the original data said nothing about."""
    _record(platform_db, 100, "2026-01-01")
    _record(platform_db, 300, "2026-06-01")
    _record(platform_db, 200, "2026-03-01")
    with connect(platform_db) as conn:
        versions = {item.valid_from: item for item in load_versions(conn, 1, "contract", "1")}
    assert versions["2026-03-01 00:00:00"].valid_to == "2026-06-01 00:00:00"


def test_a_correction_at_the_same_instant_keeps_both_rows_readable(platform_db: Path) -> None:
    """The old row becomes a zero-length window rather than being overwritten, so a
    verdict that cited it still resolves."""
    _record(platform_db, 100, "2026-01-01")
    _record(platform_db, 111, "2026-01-01")
    with connect(platform_db) as conn:
        versions = load_versions(conn, 1, "contract", "1")
        assert len(versions) == 2
        # The correction wins for any as-of read.
        assert values_as_of(conn, 1, "contract", "1", "2026-01-01")["amount"] == 111


def test_recording_requires_the_schema(tmp_path: Path) -> None:
    bare = tmp_path / "bare.sqlite3"
    initialize_platform_db(bare)
    with pytest.raises(TemporalError, match="时态表"):
        record_attribute_version(bare, 1, "contract", "1", "amount", 1)


def test_a_database_without_history_reads_as_no_history(tmp_path: Path) -> None:
    """Probed via the catalog, never by catching the error: on PostgreSQL a failed
    statement aborts the transaction (ADR-0004)."""
    bare = tmp_path / "bare.sqlite3"
    initialize_platform_db(bare)
    with connect(bare) as conn:
        assert temporal_tables_exist(conn) is False
        assert load_versions(conn, 1, "contract", "1") == []
        assert values_as_of(conn, 1, "contract", "1", "2026-01-01") == {}


def test_recording_is_audited(platform_db: Path) -> None:
    _record(platform_db, 100, "2026-01-01", actor="tester")
    with connect(platform_db) as conn:
        rows = conn.execute("select actor from audit_log where action = 'record_attribute_version'").fetchall()
    assert rows and rows[0]["actor"] == "tester"


# -- As-of reads --


def test_an_uncovered_instant_yields_absence_not_the_nearest_value(platform_db: Path) -> None:
    """The central restraint. Reaching for the closest value would fabricate a fact that
    was never recorded and put it in a verdict."""
    _record(platform_db, 100, "2026-06-01")
    with connect(platform_db) as conn:
        assert values_as_of(conn, 1, "contract", "1", "2026-01-01") == {}
        assert values_as_of(conn, 1, "contract", "1", "2026-06-01") == {"amount": 100}


def test_coverage_states_the_window_it_can_answer_for(platform_db: Path) -> None:
    """The platform records only what it observed; a source that overwrites in place still
    loses its own history. Saying so beats implying completeness."""
    _record(platform_db, 100, "2026-01-01")
    _record(platform_db, 200, "2026-03-01")
    with connect(platform_db) as conn:
        window = coverage(conn, 1, "contract", "1")
    amount = window["attributes"]["amount"]
    assert amount["earliest"] == "2026-01-01 00:00:00"
    assert amount["versionCount"] == 2
    assert amount["openEnded"] is True
    assert "未知" in window["note"]


def test_history_is_reportable_per_attribute(platform_db: Path) -> None:
    _record(platform_db, 100, "2026-01-01", attribute="amount")
    _record(platform_db, "draft", "2026-01-01", attribute="status")
    history = instance_history(platform_db, 1, "contract", "1", attribute_code="amount")
    assert [item["attributeCode"] for item in history["versions"]] == ["amount"]
    assert history["truncated"] is False


def test_the_history_limit_is_declared(platform_db: Path) -> None:
    """A partial history that looked complete would make an as-of verdict wrong rather
    than incomplete."""
    assert MAX_VERSIONS_PER_INSTANCE > 0
    history = instance_history(platform_db, 1, "contract", "1")
    assert history["truncated"] is False


# -- Snapshots --


def test_a_snapshot_records_each_attribute(platform_db: Path) -> None:
    """How history accumulates for a source system that has none of its own."""
    result = capture_snapshot(
        platform_db, 1, "contract", "1", {"amount": 100, "status": "draft"}, valid_from="2026-01-01"
    )
    assert result["recorded"] == ["amount", "status"]
    with connect(platform_db) as conn:
        assert values_as_of(conn, 1, "contract", "1", "2026-02-01") == {"amount": 100, "status": "draft"}


def test_an_unchanged_snapshot_does_not_manufacture_versions(platform_db: Path) -> None:
    """Otherwise a poll every minute makes the history look like continuous change when
    nothing changed."""
    capture_snapshot(platform_db, 1, "contract", "1", {"amount": 100}, valid_from="2026-01-01")
    second = capture_snapshot(platform_db, 1, "contract", "1", {"amount": 100}, valid_from="2026-02-01")
    assert second["unchanged"] == ["amount"]
    assert second["recorded"] == []
    with connect(platform_db) as conn:
        assert len(load_versions(conn, 1, "contract", "1")) == 1


def test_a_changed_snapshot_records_only_what_changed(platform_db: Path) -> None:
    capture_snapshot(platform_db, 1, "contract", "1", {"amount": 100, "status": "draft"}, valid_from="2026-01-01")
    second = capture_snapshot(
        platform_db, 1, "contract", "1", {"amount": 100, "status": "effective"}, valid_from="2026-02-01"
    )
    assert second["recorded"] == ["status"]
    assert second["unchanged"] == ["amount"]


# -- End to end through the kernel --


@pytest.fixture
def modelled(tmp_path: Path):
    """A contract whose amount changed, so a past verdict can differ from a present one."""
    source = tmp_path / "business.sqlite3"
    conn = sqlite3.connect(source)
    conn.executescript(
        """
        create table contracts (
            id integer primary key,
            amount numeric not null,
            status text not null
        );
        -- Today's value: within the limit.
        insert into contracts values (1, 500, 'effective');
        """
    )
    conn.commit()
    conn.close()

    platform_db = tmp_path / "platform.sqlite3"
    initialize_platform_db(platform_db)
    with connect(platform_db) as conn:
        init_temporal_schema(conn)
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
    return {"platform_db": platform_db, "ontology_id": ontology_id, "object_code": object_code}


def test_a_present_assessment_is_unaffected_by_history(modelled) -> None:
    """Absent `as_of`, nothing changes -- so adding history to a deployment does not alter
    any verdict it was already producing."""
    record_attribute_version(
        modelled["platform_db"],
        modelled["ontology_id"],
        modelled["object_code"],
        "1",
        "amount",
        99999,
        valid_from="2020-01-01",
    )
    with connect(modelled["platform_db"]) as conn:
        runtime = build_runtime(conn, modelled["ontology_id"], modelled["object_code"], "1")
    assert runtime.record["amount"] == 500, "无 as_of 时必须使用当前值"
    assert runtime.as_of == ""
    assert runtime.temporal_values == {}


def test_a_past_verdict_uses_past_values(modelled) -> None:
    """The reason this feature exists.

    An audit in March asks whether the January approval was correct given what was known in
    January. Assessing against today's values answers a different question.
    """
    platform_db, ontology_id = modelled["platform_db"], modelled["ontology_id"]
    object_code = modelled["object_code"]
    # In January the amount was 5000; today it is 500.
    record_attribute_version(platform_db, ontology_id, object_code, "1", "amount", 5000, valid_from="2026-01-01")
    record_attribute_version(platform_db, ontology_id, object_code, "1", "amount", 500, valid_from="2026-06-01")
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
        actor="tester",
    )

    today = assess_instance(platform_db, ontology_id, object_code, "1")
    january = assess_instance(platform_db, ontology_id, object_code, "1", as_of="2026-02-01")

    present = next(item for item in today["ruleResults"] if item["ruleCode"] == "amount_ceiling")
    past = next(item for item in january["ruleResults"] if item["ruleCode"] == "amount_ceiling")
    assert present["passed"] is True, "当前值 500 应通过"
    assert past["passed"] is False, "当时值 5000 应不通过 —— 否则回溯审计得到的是今天的答案"


def test_a_past_verdict_says_which_moment_it_is_about(modelled) -> None:
    """Otherwise it is indistinguishable from a judgement about the present."""
    platform_db, ontology_id = modelled["platform_db"], modelled["ontology_id"]
    object_code = modelled["object_code"]
    record_attribute_version(platform_db, ontology_id, object_code, "1", "amount", 5000, valid_from="2026-01-01")
    result = assess_instance(platform_db, ontology_id, object_code, "1", as_of="2026-02-01")
    assert result["semanticKernel"]["asOf"] == "2026-02-01 00:00:00"
    assert result["semanticKernel"]["temporalAttributes"] == ["amount"]


def test_the_stored_decision_records_the_moment(modelled) -> None:
    """A stored verdict that did not record it could later be mistaken for a judgement
    about the present."""
    platform_db, ontology_id = modelled["platform_db"], modelled["ontology_id"]
    object_code = modelled["object_code"]
    record_attribute_version(platform_db, ontology_id, object_code, "1", "amount", 5000, valid_from="2026-01-01")
    assess_instance(platform_db, ontology_id, object_code, "1", as_of="2026-02-01")
    with connect(platform_db) as conn:
        row = conn.execute("select input_ref, evidence from decision_record order by id desc limit 1").fetchone()
    assert "2026-02-01" in str(row["input_ref"])
    assert "2026-02-01" in str(row["evidence"])


def test_an_attribute_without_history_keeps_its_live_value(modelled) -> None:
    """Dropping it would turn "we have no history for this field" into "this field was
    empty" -- a different and false claim."""
    platform_db, ontology_id = modelled["platform_db"], modelled["ontology_id"]
    object_code = modelled["object_code"]
    record_attribute_version(platform_db, ontology_id, object_code, "1", "amount", 5000, valid_from="2026-01-01")
    with connect(platform_db) as conn:
        runtime = build_runtime(conn, ontology_id, object_code, "1", as_of="2026-02-01")
    assert runtime.record["amount"] == 5000, "有历史的属性应取历史值"
    assert runtime.record["status"] == "effective", "无历史的属性应保留当前值"


def test_an_invalid_as_of_is_refused_rather_than_ignored(modelled) -> None:
    """Silently ignoring it would return a present-tense verdict to a caller who asked for
    a past one."""
    with pytest.raises(TemporalError):
        assess_instance(modelled["platform_db"], modelled["ontology_id"], modelled["object_code"], "1", as_of="去年")


def test_rule_validity_windows_follow_the_assessed_moment(modelled) -> None:
    """A rule not yet in force in January must not judge a January approval."""
    platform_db, ontology_id = modelled["platform_db"], modelled["ontology_id"]
    object_code = modelled["object_code"]
    record_attribute_version(platform_db, ontology_id, object_code, "1", "amount", 5000, valid_from="2026-01-01")
    upsert_business_rule(
        platform_db,
        ontology_id,
        code="later_rule",
        name="后来才生效的规则",
        rule_type="validation",
        scope_object_code=object_code,
        expression="amount <= 1000",
        severity="blocking",
        natural_language="金额不得超过 1000。",
        actor="tester",
        effective_start="2026-05-01",
    )
    january = assess_instance(platform_db, ontology_id, object_code, "1", as_of="2026-02-01")
    assert all(item["ruleCode"] != "later_rule" for item in january["ruleResults"])
    june = assess_instance(platform_db, ontology_id, object_code, "1", as_of="2026-06-15")
    assert any(item["ruleCode"] == "later_rule" for item in june["ruleResults"])


def test_endpoints_have_sensible_capabilities() -> None:
    from ontology_platform.access_policy import required_capability

    assert required_capability("POST", "/ontologies/1/objects/contract/instances/1/versions") == "platform:write"
    assert required_capability("GET", "/ontologies/1/objects/contract/instances/1/versions") == "platform:read"
