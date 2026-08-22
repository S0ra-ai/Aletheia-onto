"""Writeback into a legacy database, and via stored procedures.

Generality item #13. HTTP was the only channel, which excludes the systems this platform
exists for -- a large share of legacy business systems have no API, and their integration
surface is a table or a stored procedure. Without this the automation loop stops one step
short: the platform can judge an operation and then not perform it.

This is the most dangerous code in the repository: it runs after a verdict, with the
platform's credentials, against a production system. So most of what is tested here is
what it **refuses**:

- SQL is never composed from a request. Declarations supply identifiers; requests supply
  values, always bound.
- An UPDATE or DELETE without a WHERE clause is refused. One forgotten WHERE rewrites a
  whole table, and the verdict that authorised it still looks reasonable afterwards.
- DDL, privilege changes and multi-statement bodies are refused outright.
- DELETE requires per-writeback opt-in, so destroying data is a recorded decision rather
  than an implication of a URI.
- An update that matched zero rows is a failure, because "returned fine, changed nothing"
  is the failure operators find hardest to notice.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from ontology_platform.automation import ExecutionRequest, resolve_executor, supported_executor_schemes
from ontology_platform.db_executors import (
    DatabaseTarget,
    SqlWriteback,
    WritebackError,
    execute_sql_writeback,
    get_database_target,
    register_database_target,
    registered_database_targets,
)

# -- Declaration safety --


def test_an_update_without_key_columns_is_refused() -> None:
    """A missing WHERE rewrites the whole table, and nothing in the decision record would
    show that it did."""
    with pytest.raises(WritebackError, match="keyColumns"):
        SqlWriteback(name="w", kind="update", table="contracts", columns=("status",)).validate()


def test_an_explicit_update_statement_must_contain_where() -> None:
    with pytest.raises(WritebackError, match="WHERE"):
        SqlWriteback(name="w", kind="update", statement="update contracts set status = :s").validate()


def test_delete_requires_explicit_opt_in() -> None:
    """Automation advances business state; destroying data is a separate decision."""
    with pytest.raises(WritebackError, match="allowDelete"):
        SqlWriteback(name="w", kind="delete", table="contracts", key_columns=("id",)).validate()
    allowed = SqlWriteback(
        name="w", kind="delete", table="contracts", key_columns=("id",), allow_delete=True
    ).validate()
    assert allowed.kind == "delete"


@pytest.mark.parametrize(
    "statement",
    [
        "update t set a = :a where id = :i; drop table t",
        "drop table contracts",
        "alter table contracts add column x text",
        "grant all on contracts to public",
        "truncate table contracts",
    ],
)
def test_structural_and_privilege_statements_are_refused(statement: str) -> None:
    with pytest.raises(WritebackError):
        SqlWriteback(name="w", kind="update", statement=statement, allow_delete=True).validate()


@pytest.mark.parametrize("bad", ["contracts; drop table x", 'contracts"', "1bad", ""])
def test_identifiers_reaching_sql_are_validated(bad: str) -> None:
    with pytest.raises(WritebackError):
        SqlWriteback(name="w", kind="insert", table=bad, columns=("a",)).validate()


def test_an_unknown_kind_is_refused() -> None:
    with pytest.raises(WritebackError, match="写回类型"):
        SqlWriteback(name="w", kind="upsert", table="t", columns=("a",)).validate()


def test_a_call_writeback_needs_a_procedure() -> None:
    with pytest.raises(WritebackError, match="procedure"):
        SqlWriteback(name="w", kind="call").validate()


# -- Rendering: identifiers declared, values bound --


def test_values_are_always_bound_never_interpolated() -> None:
    """The whole safety argument. No request content reaches SQL text."""
    writeback = SqlWriteback(
        name="approve", kind="update", table="contracts", columns=("status",), key_columns=("id",)
    ).validate()
    statement, parameters = writeback.render({"status": "'; drop table contracts --", "id": 1})
    assert "drop" not in statement.lower()
    assert parameters == ("'; drop table contracts --", 1)
    assert statement.count("%s") == 2


def test_insert_renders_columns_and_markers_in_order() -> None:
    writeback = SqlWriteback(name="add", kind="insert", table="audit", columns=("actor", "note")).validate()
    statement, parameters = writeback.render({"actor": "a", "note": "n"})
    assert statement == 'insert into "audit" ("actor", "note") values (%s, %s)'
    assert parameters == ("a", "n")


def test_named_placeholders_become_positional_markers() -> None:
    """Declarations use names because a positional declaration breaks silently when
    someone reorders columns."""
    writeback = SqlWriteback(name="w", kind="update", statement="update t set a = :a where id = :i").validate()
    statement, parameters = writeback.render({"a": 1, "i": 2})
    assert statement == "update t set a = %s where id = %s"
    assert parameters == (1, 2)


def test_a_missing_value_is_refused_rather_than_becoming_null() -> None:
    """A missing value silently becoming NULL is how an update wipes a column it was
    meant to leave alone."""
    writeback = SqlWriteback(
        name="approve", kind="update", table="contracts", columns=("status",), key_columns=("id",)
    ).validate()
    with pytest.raises(WritebackError, match="缺少参数"):
        writeback.render({"id": 1})


def test_placeholders_follow_the_declared_dialect() -> None:
    """Oracle binds positionally by number; SQLite uses `?`."""
    for dialect, expected in (("sqlite", "?"), ("oracle", ":1"), ("mysql", "%s")):
        writeback = SqlWriteback(name="w", kind="insert", table="t", columns=("a",), dialect_name=dialect).validate()
        statement, _ = writeback.render({"a": 1})
        assert expected in statement, (dialect, statement)


def test_quoting_follows_the_declared_dialect() -> None:
    mysql = SqlWriteback(name="w", kind="insert", table="t", columns=("a",), dialect_name="mysql").validate()
    statement, _ = mysql.render({"a": 1})
    assert "`t`" in statement


# -- Targets --


@pytest.fixture
def legacy_db(tmp_path: Path) -> Path:
    path = tmp_path / "legacy.sqlite3"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        create table contracts (id integer primary key, status text not null, amount numeric not null);
        create table audit (id integer primary key autoincrement, actor text not null, note text not null);
        insert into contracts values (1, 'draft', 500);
        insert into contracts values (2, 'draft', 900);
        """
    )
    conn.commit()
    conn.close()
    return path


def _target(legacy_db: Path, scheme: str = "dbwrite", **overrides) -> DatabaseTarget:
    writebacks = overrides.pop(
        "writebacks",
        {
            "approve": SqlWriteback(
                name="approve",
                kind="update",
                table="contracts",
                columns=("status",),
                key_columns=("id",),
                dialect_name="sqlite",
            ),
            "log": SqlWriteback(
                name="log",
                kind="insert",
                table="audit",
                columns=("actor", "note"),
                dialect_name="sqlite",
            ),
        },
    )
    return DatabaseTarget(
        scheme=scheme,
        connection_uri=str(legacy_db),
        dialect_name="sqlite",
        driver_module="sqlite3",
        writebacks=writebacks,
        **overrides,
    )


def test_a_target_needs_a_driver_and_a_connection() -> None:
    with pytest.raises(WritebackError, match="连接串"):
        DatabaseTarget(scheme="x", connection_uri="", driver_module="sqlite3").validate()
    with pytest.raises(WritebackError, match="驱动模块"):
        DatabaseTarget(scheme="x", connection_uri="f.db", driver_module="").validate()


def test_registering_a_target_exposes_it_as_an_executor_scheme(legacy_db: Path) -> None:
    register_database_target(_target(legacy_db, scheme="dbtest"), replace=True)
    assert "dbtest" in supported_executor_schemes()
    assert resolve_executor("dbtest://contracts/approve") is not None


def test_a_request_cannot_name_an_undeclared_writeback(legacy_db: Path) -> None:
    """Otherwise a caller could compose arbitrary SQL through the operation path."""
    target = register_database_target(_target(legacy_db, scheme="dbdeny"), replace=True)
    with pytest.raises(WritebackError, match="未声明的写回"):
        target.writeback("delete_everything")


def test_a_request_cannot_supply_its_own_connection_string(legacy_db: Path) -> None:
    """The connection belongs to the declared target. A request that could name one would
    let a caller point automation at any reachable database."""
    register_database_target(_target(legacy_db, scheme="dbfixed"), replace=True)
    target = get_database_target("dbfixed")
    assert target is not None
    assert target.connection_uri == str(legacy_db)
    # `ExecutionRequest.target` carries the scheme, not a connection string.
    request = ExecutionRequest(target="dbfixed://x", plan={"path": "/approve", "payload": {}}, timeout_seconds=5)
    assert "sqlite" not in request.target


def test_targets_are_reviewable(legacy_db: Path) -> None:
    register_database_target(_target(legacy_db, scheme="dbreview"), replace=True)
    described = registered_database_targets()["dbreview"]
    assert described["driverModule"] == "sqlite3"
    assert set(described["writebacks"]) == {"approve", "log"}
    assert described["writebacks"]["approve"]["keyColumns"] == ["id"]


# -- Real execution --


def _request(path: str, payload: dict) -> ExecutionRequest:
    return ExecutionRequest(target="dbwrite://legacy", plan={"path": path, "payload": payload}, timeout_seconds=5)


def test_an_update_writes_and_reports_affected_rows(legacy_db: Path) -> None:
    target = _target(legacy_db).validate()
    result = execute_sql_writeback(target, _request("/approve", {"status": "approved", "id": 1}))
    assert result["affectedRows"] == 1
    assert result["kind"] == "update"
    # The statement text is recorded so an auditor knows what ran.
    assert "update" in result["statement"].lower()

    with sqlite3.connect(legacy_db) as conn:
        rows = dict(conn.execute("select id, status from contracts").fetchall())
    assert rows[1] == "approved"
    # The other row is untouched: the WHERE clause did its job.
    assert rows[2] == "draft"


def test_an_insert_writes_a_row(legacy_db: Path) -> None:
    target = _target(legacy_db).validate()
    result = execute_sql_writeback(target, _request("/log", {"actor": "tester", "note": "已审批"}))
    assert result["affectedRows"] == 1
    with sqlite3.connect(legacy_db) as conn:
        assert conn.execute("select count(*) from audit").fetchone()[0] == 1


def test_matching_zero_rows_is_a_failure_not_a_success(legacy_db: Path) -> None:
    """ "Returned fine, changed nothing" is the failure operators find hardest to notice."""
    target = _target(legacy_db).validate()
    with pytest.raises(WritebackError, match="影响 0 行"):
        execute_sql_writeback(target, _request("/approve", {"status": "approved", "id": 999}))


def test_zero_rows_can_be_accepted_when_declared_idempotent(legacy_db: Path) -> None:
    """Some writes are legitimately idempotent, but that has to be declared rather than
    assumed."""
    target = _target(
        legacy_db,
        writebacks={
            "approve": SqlWriteback(
                name="approve",
                kind="update",
                table="contracts",
                columns=("status",),
                key_columns=("id",),
                dialect_name="sqlite",
                require_affected_rows=False,
            )
        },
    ).validate()
    result = execute_sql_writeback(target, _request("/approve", {"status": "approved", "id": 999}))
    assert result["affectedRows"] == 0


def test_a_failed_write_leaves_no_partial_change(legacy_db: Path) -> None:
    """A rolled-back write must not leave provenance claiming it happened."""
    target = _target(
        legacy_db,
        writebacks={
            "bad": SqlWriteback(
                name="bad",
                kind="insert",
                table="audit",
                # `note` is NOT NULL in the schema, so omitting it fails at the driver.
                columns=("actor",),
                dialect_name="sqlite",
            )
        },
    ).validate()
    with pytest.raises(WritebackError, match="写回失败"):
        execute_sql_writeback(target, _request("/bad", {"actor": "tester"}))
    with sqlite3.connect(legacy_db) as conn:
        assert conn.execute("select count(*) from audit").fetchone()[0] == 0


def test_the_operation_path_selects_the_writeback(legacy_db: Path) -> None:
    """The existing operation registry keeps naming what happens; the request contributes
    only values."""
    target = _target(legacy_db).validate()
    result = execute_sql_writeback(
        target, _request("/contracts/1/log", {"actor": "tester", "note": "路径末段决定写回"})
    )
    assert result["writeback"] == "log"


def test_an_unresolvable_path_is_refused(legacy_db: Path) -> None:
    target = _target(legacy_db).validate()
    with pytest.raises(WritebackError):
        execute_sql_writeback(target, _request("/", {}))


def test_a_missing_driver_reports_which_package_to_install(legacy_db: Path) -> None:
    target = DatabaseTarget(
        scheme="dbmissing",
        connection_uri=str(legacy_db),
        dialect_name="postgresql",
        driver_module="definitely_not_a_driver",
        writebacks={"log": SqlWriteback(name="log", kind="insert", table="audit", columns=("actor",))},
    ).validate()
    with pytest.raises(WritebackError, match="definitely_not_a_driver"):
        execute_sql_writeback(target, _request("/log", {"actor": "x"}))


def test_a_delete_writeback_runs_only_when_opted_in(legacy_db: Path) -> None:
    target = _target(
        legacy_db,
        writebacks={
            "remove": SqlWriteback(
                name="remove",
                kind="delete",
                table="contracts",
                key_columns=("id",),
                allow_delete=True,
                dialect_name="sqlite",
            )
        },
    ).validate()
    result = execute_sql_writeback(target, _request("/remove", {"id": 2}))
    assert result["affectedRows"] == 1
    with sqlite3.connect(legacy_db) as conn:
        assert conn.execute("select count(*) from contracts").fetchone()[0] == 1


def test_http_remains_available(legacy_db: Path) -> None:
    """Adding database channels must not displace the existing one."""
    assert {"http", "https"} <= set(supported_executor_schemes())
