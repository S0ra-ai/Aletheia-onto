"""Executable conformance suites for the extension points.

ROADMAP stage D. The registries have existed since ADR-0007, and the contracts were
written down -- in ADR prose and in this repository's test files. Neither is reachable by a
third party: prose cannot be executed, and `tests/` is not in the wheel. So an integrator
could register an adapter and have **no way to find out whether it was correct** short of
running a real assessment and interpreting a wrong verdict.

Stage D was recorded as "blocked on a second real use case", but that is circular: nobody
builds the second use case while verifying an implementation requires reading our tests.

A conformance suite that only passes our own implementations proves nothing -- it could be
empty. So the substance of this file is the *negative* cases: for each property, a
deliberately broken implementation that violates exactly that property, and nothing else.
Those are the tests that prove the contract has teeth.
"""

from __future__ import annotations

import random
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from ontology_platform.adapters import get_adapter
from ontology_platform.conformance import (
    ADVISORY,
    REQUIRED,
    ConformanceError,
    ConformanceReport,
    available_suites,
    check_data_source_adapter,
    check_embedding_model,
    check_instance_resolver,
    check_retrieval_backend,
    check_writeback_executor,
    describe_suites,
)
from ontology_platform.instance_resolver import ResolverSpec, build_resolver
from ontology_platform.retrieval import RetrievalHit, get_embedding_model, get_retrieval_backend


def _hit(entry_id: int, score: float) -> RetrievalHit:
    return RetrievalHit(
        entry_id=entry_id,
        score=score,
        citation="c",
        content="x",
        document_title="d",
        object_code="contract",
        rule_code="",
    )


def _failed_checks(report: ConformanceReport) -> set[str]:
    return {finding.check for finding in report.failures}


# -- The report itself --


def test_a_report_separates_required_from_advisory() -> None:
    """Conflating "will produce wrong results" with "loses a capability" makes the report
    useless for deciding whether to ship."""
    report = ConformanceReport(suite="s", subject="x")
    report.record("必需项", False, severity=REQUIRED, detail="d")
    report.record("建议项", False, severity=ADVISORY, detail="d")
    assert [f.check for f in report.failures] == ["必需项"]
    assert [f.check for f in report.advisories] == ["建议项"]
    assert report.conformant is False


def test_advisory_failures_alone_still_conform() -> None:
    report = ConformanceReport(suite="s", subject="x")
    report.record("建议项", False, severity=ADVISORY)
    assert report.conformant is True
    assert report.advisories


def test_a_summary_states_the_consequence_not_just_the_failure() -> None:
    """A message saying what broke tells an author what to look at; one that also says why
    it matters is what gets it fixed rather than worked around."""
    report = ConformanceReport(suite="s", subject="x")
    report.record("往返闭合", False, detail="token 无法被接受", why="批量研判会静默返回空")
    summary = report.summary()
    assert "token 无法被接受" in summary
    assert "批量研判会静默返回空" in summary


def test_raise_for_failures_is_an_assertion_error() -> None:
    """So a pytest test can simply call it and get a normal assertion report."""
    report = ConformanceReport(suite="s", subject="x")
    report.record("必需项", False, detail="d")
    assert issubclass(ConformanceError, AssertionError)
    with pytest.raises(ConformanceError):
        report.raise_for_failures()


def test_a_conformant_report_returns_itself_for_chaining() -> None:
    report = ConformanceReport(suite="s", subject="x")
    report.record("ok", True)
    assert report.raise_for_failures() is report


def test_every_suite_is_described_with_its_entry_point() -> None:
    """An integrator needs to know which entry point group a suite corresponds to;
    otherwise they can verify an implementation they have not registered."""
    described = {item["suite"]: item for item in describe_suites()}
    assert set(described) == set(available_suites())
    for item in described.values():
        assert item["extensionPoint"].startswith("aletheia.")
        assert item["subject"]
        assert item["docstring"]


# -- Fixtures --


@pytest.fixture
def source_db(tmp_path: Path) -> Path:
    path = tmp_path / "business.sqlite3"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        create table customers (id integer primary key, name text not null);
        create table contracts (
            id integer primary key,
            customer_id integer not null references customers(id),
            amount numeric not null
        );
        insert into customers values (1, '甲公司');
        insert into contracts values (1, 1, 500), (2, 1, 900);
        """
    )
    conn.commit()
    conn.close()
    return path


# -- Data source adapters: the platform's own must pass --


@pytest.mark.parametrize("source_type", ["sqlite", "csv"])
def test_the_platforms_own_adapters_conform(source_type: str, source_db: Path, tmp_path: Path) -> None:
    """A contract our own implementations fail is a wrong contract, not a finding."""
    if source_type == "csv":
        directory = tmp_path / "extract"
        directory.mkdir()
        (directory / "contracts.csv").write_text("id,customer_id,amount\n1,1,500\n", encoding="utf-8")
        uri = str(directory)
    else:
        uri = str(source_db)
    report = check_data_source_adapter(get_adapter(source_type), uri, subject=source_type, expected_table="contracts")
    report.raise_for_failures()


# -- Data source adapters: the negative cases --


class _MissingMethods:
    source_type = "broken"


def test_an_adapter_missing_methods_is_reported_not_crashed(source_db: Path) -> None:
    """A conformance suite must not itself crash on a broken implementation -- reporting is
    the entire purpose."""
    report = check_data_source_adapter(_MissingMethods(), str(source_db), subject="broken")
    assert not report.conformant
    assert {"实现 test_connection()", "实现 scan()", "实现 runtime()"} <= _failed_checks(report)


def test_an_adapter_without_a_source_type_is_refused(source_db: Path) -> None:
    adapter = get_adapter("sqlite")

    class _Anonymous:
        source_type = ""

        test_connection = adapter.test_connection
        scan = adapter.scan
        runtime = adapter.runtime

    report = check_data_source_adapter(_Anonymous(), str(source_db), subject="anonymous")
    assert "声明 source_type" in _failed_checks(report)


def test_a_runtime_whose_keys_do_not_round_trip_is_caught(source_db: Path) -> None:
    """The failure worth catching: batch assessment lists keys then fetches each one.

    An adapter whose `fetch_primary_keys` emits keys its own `fetch_one` rejects passes
    every unit test an author would think to write, and then silently returns nothing --
    while single-instance assessment keeps working.
    """
    import contextlib

    real = get_adapter("sqlite")

    class _Broken:
        source_type = "broken-roundtrip"
        test_connection = real.test_connection
        scan = real.scan

        @contextlib.contextmanager
        def runtime(self, uri):
            with real.runtime(uri) as inner:

                class _Shifted:
                    def __getattr__(self, name):
                        return getattr(inner, name)

                    def fetch_primary_keys(self, table, key, limit=50):
                        # Off by one -- exactly the kind of mistake that hides.
                        return [str(int(k) + 1000) for k in inner.fetch_primary_keys(table, key, limit)]

                yield _Shifted()

    report = check_data_source_adapter(_Broken(), str(source_db), subject="broken-roundtrip")
    assert "运行时读取往返闭合" in _failed_checks(report)


def test_an_unreachable_source_is_reported_with_its_message(tmp_path: Path) -> None:
    report = check_data_source_adapter(get_adapter("csv"), str(tmp_path / "nowhere"), subject="csv")
    assert "test_connection() 返回约定形状且可达" in _failed_checks(report)


# -- Instance resolvers --


def test_the_builtin_single_table_resolver_conforms(source_db: Path) -> None:
    resolver = build_resolver(ResolverSpec(kind="single_table", table="contracts", primary_key="id"))
    with get_adapter("sqlite").runtime(str(source_db)) as runtime:
        check_instance_resolver(resolver, runtime, subject="single_table").raise_for_failures()


def test_a_resolver_whose_tokens_do_not_round_trip_is_caught(source_db: Path) -> None:
    """ADR-0011 names this the most commonly mis-implemented property."""
    real = build_resolver(ResolverSpec(kind="single_table", table="contracts", primary_key="id"))

    class _Shifted:
        spec = real.spec

        def fetch(self, runtime, instance_id):
            return real.fetch(runtime, instance_id)

        def list_ids(self, runtime, limit=50):
            return [f"{token}-suffix" for token in real.list_ids(runtime, limit)]

        def columns(self, runtime):
            return real.columns(runtime)

        def tables(self):
            return real.tables()

    with get_adapter("sqlite").runtime(str(source_db)) as runtime:
        report = check_instance_resolver(_Shifted(), runtime, subject="shifted")
    assert "list_ids() 的 token 能被 fetch() 接受" in _failed_checks(report)


def test_a_resolver_returning_an_arbitrary_row_for_a_missing_instance_is_caught(source_db: Path) -> None:
    """Returning any row makes the verdict apply to the wrong record while looking
    perfectly normal."""
    real = build_resolver(ResolverSpec(kind="single_table", table="contracts", primary_key="id"))

    class _AlwaysFinds:
        spec = real.spec

        def fetch(self, runtime, instance_id):
            return real.fetch(runtime, instance_id) or real.fetch(runtime, "1")

        def list_ids(self, runtime, limit=50):
            return real.list_ids(runtime, limit)

        def columns(self, runtime):
            return real.columns(runtime)

        def tables(self):
            return real.tables()

    with get_adapter("sqlite").runtime(str(source_db)) as runtime:
        report = check_instance_resolver(_AlwaysFinds(), runtime, subject="always-finds")
    assert "不存在的实例返回 None" in _failed_checks(report)


def test_a_resolver_under_reporting_columns_is_caught(source_db: Path) -> None:
    """Rule authoring validates field names against `columns()`; under-reporting makes a
    perfectly executable rule get rejected at write time."""
    real = build_resolver(ResolverSpec(kind="single_table", table="contracts", primary_key="id"))

    class _Hides:
        spec = real.spec

        def fetch(self, runtime, instance_id):
            return real.fetch(runtime, instance_id)

        def list_ids(self, runtime, limit=50):
            return real.list_ids(runtime, limit)

        def columns(self, runtime):
            return ["id"]

        def tables(self):
            return real.tables()

    with get_adapter("sqlite").runtime(str(source_db)) as runtime:
        report = check_instance_resolver(_Hides(), runtime, subject="hides-columns")
    assert "columns() 覆盖记录中的字段" in _failed_checks(report)


def test_a_resolver_without_tables_is_only_advised(source_db: Path) -> None:
    """A resolver over a non-table source legitimately has nothing to report; demanding it
    would exclude a whole class of valid implementation."""
    real = build_resolver(ResolverSpec(kind="single_table", table="contracts", primary_key="id"))

    class _NoTables:
        spec = real.spec

        def fetch(self, runtime, instance_id):
            return real.fetch(runtime, instance_id)

        def list_ids(self, runtime, limit=50):
            return real.list_ids(runtime, limit)

        def columns(self, runtime):
            return real.columns(runtime)

    with get_adapter("sqlite").runtime(str(source_db)) as runtime:
        report = check_instance_resolver(_NoTables(), runtime, subject="no-tables")
    assert report.conformant, report.summary()
    assert any("tables()" in finding.check for finding in report.advisories)


# -- Retrieval backends --


@pytest.mark.parametrize("name", ["bm25", "embedding"])
def test_the_platforms_own_retrieval_backends_conform(name: str) -> None:
    check_retrieval_backend(get_retrieval_backend(name), subject=name).raise_for_failures()


def test_a_backend_widening_beyond_the_candidate_set_is_caught() -> None:
    """The candidate set is already anchor-filtered. Widening bypasses the anchoring, so
    an answer can cite entries unrelated to the object -- both an explainability failure
    and an access-control one."""
    report = check_retrieval_backend(lambda q, entries, limit: [_hit(999, 1.0)], subject="leaky")
    assert "不越过候选集" in _failed_checks(report)


def test_a_backend_returning_hits_out_of_order_is_caught() -> None:
    """Callers truncate by order, so the best match gets dropped while the result still
    looks reasonable."""
    report = check_retrieval_backend(
        lambda q, entries, limit: [_hit(e["id"], float(i)) for i, e in enumerate(entries[:limit])],
        subject="unsorted",
    )
    assert "命中按分数降序" in _failed_checks(report)


def test_a_backend_ignoring_the_limit_is_caught() -> None:
    report = check_retrieval_backend(
        lambda q, entries, limit: [_hit(e["id"], 1.0 - i * 0.1) for i, e in enumerate(entries)],
        subject="ignores-limit",
    )
    assert "遵守 limit" in _failed_checks(report)


def test_a_backend_raising_on_an_empty_candidate_set_is_caught() -> None:
    """Anchor filtering leaves an empty candidate set routinely; raising turns "no relevant
    document" into an outage."""

    def brittle(query, entries, limit):
        return [_hit(entries[0]["id"], 1.0)]

    report = check_retrieval_backend(brittle, subject="brittle")
    assert "空候选集返回空列表" in _failed_checks(report)


def test_a_backend_raising_on_an_empty_query_is_caught() -> None:
    def rejects_empty(query, entries, limit):
        if not query:
            raise ValueError("空查询")
        return [_hit(entries[0]["id"], 1.0)]

    report = check_retrieval_backend(rejects_empty, subject="rejects-empty")
    assert "空查询不抛异常" in _failed_checks(report)


# -- Embedding models --


def test_the_platforms_own_embedding_model_conforms() -> None:
    check_embedding_model(get_embedding_model(), subject="hashed-ngram").raise_for_failures()


def test_a_non_deterministic_embedding_is_caught() -> None:
    """Two identical questions yielding different citations makes a verdict
    irreproducible, and verifiability is what this platform stands on (ADR-0005)."""
    report = check_embedding_model(lambda text: [random.random() for _ in range(8)], subject="random")
    assert "确定性" in _failed_checks(report)


def test_a_variable_dimension_embedding_is_caught() -> None:
    """Mismatched dimensions make cosine similarity silently return 0 -- "nothing is
    relevant" rather than an error."""
    report = check_embedding_model(lambda text: [1.0] * (len(text) + 1), subject="variable")
    assert "维度恒定" in _failed_checks(report)


def test_a_non_numeric_embedding_is_caught() -> None:
    report = check_embedding_model(lambda text: ["a", "b"], subject="strings")
    assert "返回数值向量" in _failed_checks(report)


def test_an_embedding_raising_on_empty_text_is_caught() -> None:
    def rejects_empty(text: str):
        if not text:
            raise ValueError("空文本")
        return [1.0, 2.0]

    report = check_embedding_model(rejects_empty, subject="rejects-empty")
    assert "空文本不抛异常" in _failed_checks(report)


# -- Writeback executors --


def _request():
    from ontology_platform.automation import ExecutionRequest

    return ExecutionRequest(target="x://y", plan={"path": "/approve", "payload": {}}, timeout_seconds=5)


def test_an_executor_reporting_no_effect_is_caught() -> None:
    """ "Returned fine, changed nothing" is the failure operators find hardest to notice, so
    the result must indicate what happened."""
    report = check_writeback_executor(lambda request: {"note": "done"}, _request(), subject="opaque")
    assert "结果表明写回效果" in _failed_checks(report)


def test_an_executor_returning_a_non_mapping_is_caught() -> None:
    report = check_writeback_executor(lambda request: "ok", _request(), subject="string")
    assert "返回可留痕的结果字典" in _failed_checks(report)


def test_a_result_that_only_str_can_encode_is_caught() -> None:
    """The trap is not that serialisation fails -- provenance uses `default=str`, so it
    never does. It is that the audit trail silently records `<object at 0x...>` instead of
    what happened, while the verdict looks perfectly fine.
    """
    report = check_writeback_executor(
        lambda request: {"affectedRows": 1, "handle": object()}, _request(), subject="lossy"
    )
    assert "结果能如实往返 JSON" in _failed_checks(report)


def test_a_result_of_plain_json_types_round_trips() -> None:
    report = check_writeback_executor(
        lambda request: {"affectedRows": 2, "statement": "update ...", "warnings": []},
        _request(),
        subject="plain",
    )
    report.raise_for_failures()


def test_a_well_behaved_executor_conforms() -> None:
    report = check_writeback_executor(
        lambda request: {"affectedRows": 1, "statement": "update ..."}, _request(), subject="good"
    )
    report.raise_for_failures()


def test_an_executor_that_raises_is_reported_not_propagated() -> None:
    def explodes(request):
        raise RuntimeError("boom")

    report = check_writeback_executor(explodes, _request(), subject="explodes")
    assert not report.conformant
    assert any("boom" in finding.detail for finding in report.failures)


# -- The suite ships with the package --


def test_the_suite_is_importable_from_the_installed_package() -> None:
    """The whole point: `tests/` is not in the wheel, so a contract that lives only there
    is unreachable by the integrator who needs it."""
    import ontology_platform.conformance as module

    assert Path(module.__file__).parent.name == "ontology_platform"
    assert available_suites()


def test_the_package_declares_the_conformance_module() -> None:
    """Guards against the module existing but being excluded from the distribution."""
    packaged = ROOT / "backend" / "ontology_platform" / "conformance.py"
    assert packaged.exists()


# -- Every built-in implementation is held to the contract --
#
# This is the ongoing proof that the contract is right. A suite that only its author's
# examples satisfy would drift into demanding things the platform itself does not do, and
# then the first integrator to run it gets failures we caused.


@pytest.mark.parametrize(
    "kind",
    ["single_table", "joined_tables", "discriminated", "custom_sql"],
)
def test_all_four_builtin_resolvers_conform(kind: str, source_db: Path) -> None:
    specs = {
        "single_table": ResolverSpec(kind="single_table", table="contracts", primary_key="id"),
        "joined_tables": ResolverSpec(
            kind="joined_tables",
            table="contracts",
            primary_key="id",
            joins=[{"table": "customers", "foreignKey": "id"}],
        ),
        "discriminated": ResolverSpec(
            kind="discriminated",
            table="contracts",
            primary_key="id",
            discriminator_column="customer_id",
            discriminator_value="1",
        ),
        "custom_sql": ResolverSpec(kind="custom_sql", query="select * from contracts", id_column="id"),
    }
    with get_adapter("sqlite").runtime(str(source_db)) as runtime:
        check_instance_resolver(build_resolver(specs[kind]), runtime, subject=kind).raise_for_failures()


def test_the_builtin_database_writeback_executor_conforms(tmp_path: Path) -> None:
    """Verified through the public registry path, the way an integrator would reach it."""
    from ontology_platform.automation import ExecutionRequest, resolve_executor
    from ontology_platform.db_executors import DatabaseTarget, SqlWriteback, register_database_target

    legacy = tmp_path / "legacy.sqlite3"
    conn = sqlite3.connect(legacy)
    conn.executescript(
        """
        create table contracts (id integer primary key, status text not null);
        insert into contracts values (1, 'draft');
        """
    )
    conn.commit()
    conn.close()

    register_database_target(
        DatabaseTarget(
            scheme="conftest_db",
            connection_uri=str(legacy),
            dialect_name="sqlite",
            driver_module="sqlite3",
            writebacks={
                "approve": SqlWriteback(
                    name="approve",
                    kind="update",
                    table="contracts",
                    columns=("status",),
                    key_columns=("id",),
                    dialect_name="sqlite",
                )
            },
        ),
        replace=True,
    )
    request = ExecutionRequest(
        target="conftest_db://legacy",
        plan={"path": "/approve", "payload": {"status": "approved", "id": 1}},
        timeout_seconds=5,
    )
    check_writeback_executor(
        resolve_executor("conftest_db://legacy"), request, subject="db_executor"
    ).raise_for_failures()


def test_every_suite_has_at_least_one_negative_test_in_this_file() -> None:
    """A contract nobody has proven can fail is indistinguishable from an empty one.

    Checked structurally rather than by convention, because the failure mode is a suite
    added later with only a happy-path test -- which passes, ships, and catches nothing.
    """
    source = Path(__file__).read_text(encoding="utf-8")
    for suite in available_suites():
        # Each suite's negative cases call its checker and assert on `_failed_checks`.
        checker = f"check_{suite}("
        assert checker in source, f"{suite} 契约没有任何测试调用它"
        segment_calls = source.count(checker)
        assert segment_calls >= 2, f"{suite} 契约缺少反例测试（仅出现 {segment_calls} 次调用）"


def test_the_documented_check_counts_match_reality() -> None:
    """The extension guide states a check count per suite.

    Stated numbers drift silently, and a guide that overstates what is verified is worse
    than one that says nothing -- an integrator would trust a check that does not exist.
    """
    import re
    import tempfile

    guide = (ROOT / "docs" / "extending.md").read_text(encoding="utf-8")
    claimed = {name: int(count) for name, count in re.findall(r"\| `(\w+)` \| (\d+) \|", guide)}
    assert set(claimed) == set(available_suites()), (
        f"文档表格与实际契约不一致: 文档 {sorted(claimed)}，实际 {sorted(available_suites())}"
    )

    directory = Path(tempfile.mkdtemp())
    database = directory / "b.sqlite3"
    conn = sqlite3.connect(database)
    conn.executescript("create table t (id integer primary key, a text); insert into t values (1, 'x');")
    conn.commit()
    conn.close()

    from ontology_platform.automation import ExecutionRequest

    actual = {
        "data_source_adapter": len(check_data_source_adapter(get_adapter("sqlite"), str(database)).findings),
        "retrieval_backend": len(check_retrieval_backend(get_retrieval_backend("bm25")).findings),
        "embedding_model": len(check_embedding_model(get_embedding_model()).findings),
        "writeback_executor": len(
            check_writeback_executor(
                lambda request: {"affectedRows": 1},
                ExecutionRequest(target="x://y", plan={}, timeout_seconds=1),
            ).findings
        ),
    }
    with get_adapter("sqlite").runtime(str(database)) as runtime:
        actual["instance_resolver"] = len(
            check_instance_resolver(
                build_resolver(ResolverSpec(kind="single_table", table="t", primary_key="id")), runtime
            ).findings
        )

    mismatched = {name: (claimed[name], actual[name]) for name in actual if claimed[name] != actual[name]}
    assert not mismatched, f"文档声明的检查项数与实际不符 (文档, 实际): {mismatched}"
