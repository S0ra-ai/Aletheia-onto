"""Code generation from a published ontology.

ROADMAP stage F's last item. The frontend keeps 1143 hand-written lines mirroring the
backend, and what makes that debt is not the duplication but that **the two copies can
disagree with nothing failing** -- the model configuration endpoint silently discarded four
fields the frontend had always sent.

Generating the platform's own types from OpenAPI stays blocked: every endpoint returns
`dict[str, object]`, so there is no response schema to generate from. What is generatable,
and more valuable, is the layer nobody could hand-write correctly: **the types of a user's
own business objects**, where `contract.amount` is a decimal with a unit and
`contract.customer_id` points at a customer rather than being "a number".

The properties worth pinning down:

- **relations are typed as the object they point at.** A hand-written mirror types every
  foreign key as a number, so nothing stops passing a contract id where a customer is
  expected. This is the single most useful thing generation adds.
- **only published ontologies.** A draft's shape changes while mappings are under review, so
  generated types would describe a model nobody agreed to.
- **the output compiles.** Checked with the real `tsc`, because "looks like TypeScript" and
  "is TypeScript" are different claims and only one of them is useful.
- **regeneration overwrites.** The opposite of `scaffold.py`, deliberately: generated types
  are a projection that must track the ontology, so refusing to overwrite would make a stale
  projection the default.
"""

from __future__ import annotations

import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from ontology_platform.codegen import (
    TS_BY_DATA_TYPE,
    CodegenError,
    generate_typescript,
    write_typescript,
)
from ontology_platform.database import connect, initialize_platform_db
from ontology_platform.governance import publish_ontology
from ontology_platform.metadata import register_data_source, scan_data_source
from ontology_platform.ontology import generate_ontology_draft

TSC = ROOT / "frontend" / "node_modules" / ".bin" / "tsc"


@pytest.fixture
def published(tmp_path: Path):
    """A published ontology over a schema with the shapes codegen is about.

    `contracts.customer_id` is a real foreign key, so the relation exists and can be typed;
    `memo` is nullable, so optionality is observable; `amount` is numeric, so the precision
    note is emitted.
    """
    source = tmp_path / "business.sqlite3"
    connection = sqlite3.connect(source)
    connection.executescript(
        """
        create table customers (
            id integer primary key,
            name text not null,
            credit_limit numeric
        );
        create table contracts (
            id integer primary key,
            customer_id integer not null references customers(id),
            amount numeric not null,
            signed_date text,
            memo text
        );
        insert into customers values (1, '甲公司', 500);
        insert into contracts values (1, 1, 100, '2026-01-01', null);
        """
    )
    connection.commit()
    connection.close()

    platform_db = tmp_path / "platform.sqlite3"
    initialize_platform_db(platform_db)
    data_source = register_data_source(platform_db, "业务系统", "sqlite", str(source), domain="合同管理")
    scan_data_source(platform_db, data_source.id)
    ontology_id = generate_ontology_draft(platform_db, data_source.id)["ontology"]["id"]

    with connect(platform_db) as conn:
        conn.execute(
            "update semantic_mapping set status = 'confirmed' where ontology_id = ?",
            (ontology_id,),
        )
    publish_ontology(platform_db, ontology_id, "tester")

    # Read the codes rather than assuming them. The draft generator applies its own naming
    # (it singularises table names), and a test that hardcoded `Contracts` would be asserting
    # that convention rather than the property under test.
    with connect(platform_db) as conn:
        codes = {
            row["table_name"]: row["code"]
            for row in conn.execute(
                "select bo.code, st.table_name from business_object bo"
                " join source_table st on st.id = bo.source_table_id where bo.ontology_id = ?",
                (ontology_id,),
            ).fetchall()
        }
    return {"platform_db": platform_db, "ontology_id": ontology_id, "codes": codes}


def _interface(code: str) -> str:
    from ontology_platform.codegen import _identifier

    return _identifier(code)


# -- Only published ontologies --


def test_a_draft_is_refused(tmp_path: Path) -> None:
    """Generated types would describe a model nobody has agreed to, and the first symptom is
    a compile error in code that was correct yesterday."""
    source = tmp_path / "b.sqlite3"
    sqlite3.connect(source).executescript("create table t (id integer primary key);")
    platform_db = tmp_path / "p.sqlite3"
    initialize_platform_db(platform_db)
    data_source = register_data_source(platform_db, "s", "sqlite", str(source), domain="合同管理")
    scan_data_source(platform_db, data_source.id)
    ontology_id = generate_ontology_draft(platform_db, data_source.id)["ontology"]["id"]

    with pytest.raises(CodegenError, match="仅已发布本体"):
        generate_typescript(platform_db, ontology_id)

    # Available for local iteration, and explicitly opted into.
    assert generate_typescript(platform_db, ontology_id, allow_draft=True)


def test_a_missing_ontology_is_refused(published) -> None:
    with pytest.raises(ValueError, match="本体不存在"):
        generate_typescript(published["platform_db"], 999)


# -- What the generated types express --


def test_each_business_object_becomes_an_interface(published) -> None:
    output = generate_typescript(published["platform_db"], published["ontology_id"])
    for table in ("contracts", "customers"):
        interface = _interface(published["codes"][table])
        assert f"export interface {interface} {{" in output, f"{table} 未生成接口"


def test_a_relation_is_typed_as_its_target_object(published) -> None:
    """The single most useful thing generation adds.

    A hand-written mirror types every foreign key as `number`, so nothing stops a developer
    passing a contract id where a customer is expected -- and the API accepts it, because at
    the wire level both are numbers.
    """
    output = generate_typescript(published["platform_db"], published["ontology_id"])
    customer = _interface(published["codes"]["customers"])
    relation_lines = [line for line in output.splitlines() if f": {customer};" in line]
    assert relation_lines, f"关系未被类型化为目标对象 {customer}:\n{output}"


def test_a_nullable_column_is_optional_and_a_not_null_one_is_not(published) -> None:
    """Optionality comes from the scanned schema, so it cannot contradict the source."""
    output = generate_typescript(published["platform_db"], published["ontology_id"])
    assert "  amount: number;" in output, "NOT NULL 列不应为可选"
    assert "  memo?: string;" in output, "可空列应为可选"


def test_a_numeric_field_warns_about_javascript_precision(published) -> None:
    """A generator that silently emitted `string` for money would break every arithmetic the
    developer writes; one that emitted `number` without saying so hides a real hazard."""
    output = generate_typescript(published["platform_db"], published["ontology_id"])
    assert "精度有限" in output


def test_the_header_names_the_ontology_and_version(published) -> None:
    """So a reviewer seeing a conflict knows whether they are looking at a regeneration or at
    someone's edit."""
    output = generate_typescript(published["platform_db"], published["ontology_id"])
    head = output.splitlines()[:6]
    assert any("请勿手工编辑" in line for line in head)
    assert any("版本" in line for line in head)


def test_the_object_code_union_covers_every_object(published) -> None:
    output = generate_typescript(published["platform_db"], published["ontology_id"])
    assert "export type ObjectCode" in output
    for code in published["codes"].values():
        assert f'"{code}"' in output, f"ObjectCode 未包含 {code}"


def test_the_client_only_wraps_endpoints_with_a_known_shape(published) -> None:
    """The rest of the API returns `dict[str, object]`. A client claiming to know their shape
    would assert something the platform does not guarantee -- a lie that compiles.
    """
    output = generate_typescript(published["platform_db"], published["ontology_id"])
    assert "async assess(" in output
    assert "async explain(" in output
    assert "async timeline(" in output
    # Endpoints whose response shape is undeclared must not be wrapped.
    for absent in ("async listOntologies(", "async workbench(", "async audit("):
        assert absent not in output
    # The typed assessment exposes the per-rule reasoning, not only the verdict.
    assert "ruleResults: RuleResult[];" in output


def test_the_decision_type_is_three_valued(published) -> None:
    """`review` means "a human must look", which is a different business action from
    "rejected". A boolean would collapse them."""
    output = generate_typescript(published["platform_db"], published["ontology_id"])
    assert '"approved" | "review" | "blocked"' in output


# -- The output is real TypeScript --


@pytest.mark.skipif(not TSC.exists(), reason="需要 frontend/node_modules 里的 tsc")
def test_the_generated_typescript_compiles_under_strict_mode(published, tmp_path: Path) -> None:
    """ "Looks like TypeScript" and "is TypeScript" are different claims, and only one is
    useful. Compiled with `--strict` because that is what the project's own frontend uses --
    output that only survives loose mode would fail in the codebase it is generated for.
    """
    target = tmp_path / "ontology.ts"
    write_typescript(published["platform_db"], published["ontology_id"], target)

    result = subprocess.run(
        [
            str(TSC),
            "--noEmit",
            "--strict",
            "--ignoreConfig",
            "--target",
            "ES2022",
            "--module",
            "ESNext",
            "--lib",
            "ES2022,DOM",
            str(target),
        ],
        capture_output=True,
        text=True,
        cwd=ROOT / "frontend",
    )
    assert result.returncode == 0, f"生成的 TypeScript 无法编译:\n{result.stdout}\n{result.stderr}"


def test_an_object_code_with_no_ascii_characters_is_refused(published) -> None:
    """A type name is read and typed by a developer, so a percent-encoded one is unusable.
    Refused rather than silently collapsed, because two objects collapsing to one name would
    produce a duplicate-interface compile error nobody could trace back to a code.
    """
    with connect(published["platform_db"]) as conn:
        conn.execute(
            "insert into business_object (ontology_id, code, name, description) values (?, '合同', '合同', '')",
            (published["ontology_id"],),
        )
    with pytest.raises(CodegenError, match="不含可用于类型名的字符"):
        generate_typescript(published["platform_db"], published["ontology_id"])


# -- Writing --


def test_regenerating_overwrites(published, tmp_path: Path) -> None:
    """The opposite decision from `scaffold.py`, deliberately.

    A scaffold is a starting point the user then owns; generated types are a projection of the
    ontology that must be regenerated whenever it changes. Refusing to overwrite would make a
    stale projection the default, which defeats the purpose.
    """
    target = tmp_path / "out" / "ontology.ts"
    first = write_typescript(published["platform_db"], published["ontology_id"], target)
    assert first["overwritten"] is False

    target.write_text("// 手工改动\n", encoding="utf-8")
    second = write_typescript(published["platform_db"], published["ontology_id"], target)
    assert second["overwritten"] is True
    assert "手工改动" not in target.read_text(encoding="utf-8")


def test_the_datatype_table_covers_what_the_scanner_produces() -> None:
    """An unmapped common type degrades every generated interface containing it."""
    for data_type in ("string", "integer", "numeric", "boolean", "date", "datetime", "text"):
        assert data_type in TS_BY_DATA_TYPE, f"{data_type} 未映射到 TypeScript 类型"


@pytest.mark.skipif(shutil.which("node") is None, reason="需要 node")
def test_the_cli_writes_a_file(published, tmp_path: Path, capsys) -> None:
    from ontology_platform.cli import main

    target = tmp_path / "generated" / "ontology.ts"
    exit_code = main(
        [
            "--platform-db",
            str(published["platform_db"]),
            "codegen",
            str(published["ontology_id"]),
            "--output",
            str(target),
        ]
    )
    capsys.readouterr()
    assert exit_code == 0
    assert target.exists()


def test_the_cli_refuses_a_draft_without_a_traceback(tmp_path: Path, capsys) -> None:
    """A traceback tells the caller the tool broke; a message tells them what to do."""
    from ontology_platform.cli import main

    source = tmp_path / "b.sqlite3"
    sqlite3.connect(source).executescript("create table t (id integer primary key);")
    platform_db = tmp_path / "p.sqlite3"
    initialize_platform_db(platform_db)
    data_source = register_data_source(platform_db, "s", "sqlite", str(source), domain="合同管理")
    scan_data_source(platform_db, data_source.id)
    ontology_id = generate_ontology_draft(platform_db, data_source.id)["ontology"]["id"]

    exit_code = main(["--platform-db", str(platform_db), "codegen", str(ontology_id)])
    captured = capsys.readouterr()
    assert exit_code != 0
    assert "Traceback" not in captured.out + captured.err
    assert "仅已发布本体" in captured.out + captured.err
