"""Domain neutrality tests.

The platform claims to serve any industry. That only holds if no business
vocabulary is baked into the code: the moment a module contains a table like
{"contract": "合同"}, the first customer in an unanticipated domain gets worse
object detection, wrong fallbacks and misleading prompts.

These tests use a veterinary clinic schema — a domain the platform ships no
knowledge of — and assert that modelling, language understanding, agent roles,
permissions and operation routing all adapt without code changes.
"""

from __future__ import annotations

import io
import sqlite3
import tokenize
from pathlib import Path

import pytest

from ontology_platform.agent_roles import (
    build_system_prompt,
    init_agent_role_schema,
    list_agent_roles,
    resolve_agent_role,
    slugify_domain,
    upsert_agent_role,
)
from ontology_platform.database import connect, initialize_platform_db
from ontology_platform.industry_blueprints import upsert_industry_blueprint
from ontology_platform.metadata import register_data_source, register_source_api, scan_data_source
from ontology_platform.natural_language import (
    _default_operation_code,
    _identifier_columns,
    query_natural_language,
)
from ontology_platform.ontology import generate_ontology_draft, resolve_ontology_for_object
from ontology_platform.vocabulary import load_vocabulary
from ontology_platform.workflow_permission import (
    init_workflow_and_permission_schema,
    list_policies,
    seed_default_roles_and_policies,
    seed_default_tools,
)


CLINIC_SCHEMA = """
create table pet_owner (id integer primary key, owner_name text, phone text, city text);
create table pet (id integer primary key, pet_name text, species text,
                  owner_id integer references pet_owner(id), birth_date text);
create table consultation (id integer primary key, visit_no text,
                           pet_id integer references pet(id), diagnosis text,
                           fee real, visit_date text, status text);
insert into pet_owner values (1,'张三','13800000000','上海'),(2,'李四','13900000000','北京');
insert into pet values (1,'旺财','犬',1,'2020-03-01'),(2,'咪咪','猫',2,'2021-07-15');
insert into consultation values
  (1,'MZ-2026-001',1,'皮肤过敏',320.0,'2026-05-01','completed'),
  (2,'MZ-2026-002',2,'疫苗接种',180.0,'2026-05-06','draft');
"""

CLINIC_BLUEPRINT = {
    "id": "veterinary-clinic",
    "name": "宠物诊疗蓝图",
    "domain": "宠物诊疗",
    "description": "宠物主、宠物与诊疗记录",
    "objectHints": {"pet_owner": "宠物主", "pet": "宠物", "consultation": "诊疗记录"},
    "attributeHints": {
        "owner_name": "主人姓名",
        "pet_name": "宠物昵称",
        "species": "物种",
        "visit_no": "就诊编号",
        "diagnosis": "诊断结论",
        "fee": "诊疗费用",
    },
    "rules": [
        {
            "code": "fee_non_negative",
            "name": "诊疗费用不能为负",
            "ruleType": "validation",
            "scopeObjectCode": "consultation",
            "expression": "fee >= 0",
            "severity": "blocking",
            "naturalLanguage": "诊疗费用必须大于或等于零。",
        }
    ],
    "tableKeywords": ["pet", "consultation", "owner"],
    "capabilityTags": ["semantic_mapping"],
}


@pytest.fixture
def clinic(tmp_path: Path) -> dict[str, object]:
    """An onboarded veterinary clinic: a domain the platform does not ship."""
    platform_db = tmp_path / "platform.sqlite3"
    legacy_db = tmp_path / "clinic.sqlite3"
    connection = sqlite3.connect(legacy_db)
    connection.executescript(CLINIC_SCHEMA)
    connection.commit()
    connection.close()

    initialize_platform_db(platform_db)
    with connect(platform_db) as conn:
        init_workflow_and_permission_schema(conn)
        init_agent_role_schema(conn)
    seed_default_tools(platform_db)
    upsert_industry_blueprint(platform_db, CLINIC_BLUEPRINT)

    source = register_data_source(
        platform_db, "宠物诊疗系统", "sqlite", str(legacy_db), domain="宠物诊疗"
    )
    scan_data_source(platform_db, source.id)
    register_source_api(
        platform_db, source.id, "closeVisitRecord", "关闭诊疗记录",
        "POST", "/visits/{id}/close", "consultation.close",
    )
    register_source_api(
        platform_db, source.id, "applyVisitReview", "提交诊疗复核",
        "POST", "/visits/{id}/apply", "consultation.submit",
    )
    ontology = generate_ontology_draft(platform_db, source.id, blueprint_id="veterinary-clinic")
    seed_default_roles_and_policies(platform_db)
    return {
        "platform_db": platform_db,
        "source_id": source.id,
        "ontology_id": ontology["id"],
        "ontology": ontology,
    }


# -- No built-in vocabulary --


def _code_lines(path: Path) -> list[tuple[int, str]]:
    """Source lines with comments and string literals removed.

    Uses the tokenizer so prose that merely mentions a business term cannot
    trigger a false positive, while a real literal such as `or "contract"` does.
    """
    text = path.read_text(encoding="utf-8")
    blanked: dict[int, str] = {}
    for index, line in enumerate(text.splitlines(), start=1):
        blanked[index] = line
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except tokenize.TokenError:
        return list(blanked.items())
    drop: set[int] = set()
    keep_strings: dict[int, list[str]] = {}
    for token in tokens:
        if token.type == tokenize.COMMENT:
            drop.add(token.start[0])
        elif token.type == tokenize.STRING:
            # A docstring spans lines; blank them all. Short inline strings are
            # kept so dict literals of domain terms are still caught.
            if token.start[0] != token.end[0]:
                for line_number in range(token.start[0], token.end[0] + 1):
                    drop.add(line_number)
            else:
                keep_strings.setdefault(token.start[0], []).append(token.string)
    result: list[tuple[int, str]] = []
    for line_number, line in blanked.items():
        if line_number in drop:
            # Preserve any single-line strings that shared the line.
            retained = " ".join(keep_strings.get(line_number, []))
            if retained:
                result.append((line_number, retained))
            continue
        result.append((line_number, line))
    return result


def test_platform_modules_contain_no_industry_vocabulary() -> None:
    """Guard against reintroducing a built-in domain lexicon.

    Domain terms belong in industry blueprints and scanned metadata, both of
    which users maintain. Sample data and blueprint definitions are exempt
    because that is exactly where such vocabulary is supposed to live.
    """
    package = Path(__file__).resolve().parents[1] / "backend" / "ontology_platform"
    exempt = {"industry_blueprints.py", "sample_data.py"}
    # Object codes that used to be hardcoded as fallbacks across the platform.
    forbidden = ['"contract"', '"customer"', '"payment_plan"', '"invoice"', '"work_order"', '"equipment"']
    offenders: list[str] = []
    for path in sorted(package.glob("*.py")):
        if path.name in exempt:
            continue
        # Compare executable code only: docstrings and comments may legitimately
        # discuss the vocabulary problem this test guards against.
        for line_number, line in _code_lines(path):
            for token in forbidden:
                if token in line:
                    offenders.append(f"{path.name}:{line_number}: {line.strip()[:90]}")
    assert offenders == [], "发现内置领域词汇硬编码:\n" + "\n".join(offenders)


def test_agent_module_has_no_hardcoded_personas() -> None:
    package = Path(__file__).resolve().parents[1] / "backend" / "ontology_platform"
    agent_text = (package / "agent.py").read_text(encoding="utf-8")
    assert "contract-expert" not in agent_text
    assert "equipment-expert" not in agent_text
    assert "AGENT_ROLES" not in agent_text


# -- Modelling adapts to the domain --


def test_unknown_domain_is_modelled_with_its_own_labels(clinic: dict[str, object]) -> None:
    objects = {item["code"]: item["name"] for item in clinic["ontology"]["objects"]}
    assert objects == {"pet_owner": "宠物主", "pet": "宠物", "consultation": "诊疗记录"}


def test_blueprint_rules_are_generated_for_the_domain(clinic: dict[str, object]) -> None:
    codes = {rule["code"] for rule in clinic["ontology"]["rules"]}
    assert "fee_non_negative" in codes


def test_vocabulary_is_derived_from_the_ontology(clinic: dict[str, object]) -> None:
    vocabulary = load_vocabulary(clinic["platform_db"], clinic["ontology_id"])
    assert set(vocabulary.codes()) == {"pet_owner", "pet", "consultation"}
    assert vocabulary.label_for("consultation") == "诊疗记录"
    # An unmodelled code degrades to itself rather than to a built-in default.
    assert vocabulary.label_for("nonexistent") == "nonexistent"


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("宠物 1 是什么", "pet"),
        ("诊疗记录整体是否一致", "consultation"),
        ("宠物主 2 是否合规", "pet_owner"),
        ("consultation 有哪些规则", "consultation"),
    ],
)
def test_domain_objects_are_detected_from_the_vocabulary(
    clinic: dict[str, object], question: str, expected: str
) -> None:
    vocabulary = load_vocabulary(clinic["platform_db"], clinic["ontology_id"])
    detected = vocabulary.detect(question)
    assert detected is not None
    assert detected.code == expected


def test_default_object_is_the_most_connected_not_a_fixed_code(clinic: dict[str, object]) -> None:
    vocabulary = load_vocabulary(clinic["platform_db"], clinic["ontology_id"])
    default = vocabulary.default_object()
    assert default is not None
    assert default.code in {"pet_owner", "pet", "consultation"}


# -- Language understanding --


def test_questions_route_to_domain_objects_end_to_end(clinic: dict[str, object]) -> None:
    result = query_natural_language(
        clinic["platform_db"], "宠物 1 是什么？", clinic["ontology_id"], clinic["source_id"], use_model=False
    )
    assert result["resolved"]["objectCode"] == "pet"
    assert "宠物" in result["answer"]


def test_business_code_resolves_its_own_object(clinic: dict[str, object]) -> None:
    """A pasted document number identifies its object without being named.

    Previously any business code was assumed to be a contract number.
    """
    result = query_natural_language(
        clinic["platform_db"], "MZ-2026-001 是否合规？", clinic["ontology_id"], clinic["source_id"], use_model=False
    )
    assert result["resolved"]["objectCode"] == "consultation"
    assert result["resolved"]["instanceId"] == "1"


def test_error_hints_reference_modelled_objects(clinic: dict[str, object]) -> None:
    with pytest.raises(ValueError) as error:
        query_natural_language(
            clinic["platform_db"], "解释一下详情", clinic["ontology_id"], clinic["source_id"], use_model=False
        )
    message = str(error.value)
    assert "合同" not in message
    assert any(label in message for label in ("宠物", "诊疗记录", "宠物主"))


def test_identifier_columns_recognise_conventions_not_industry_names() -> None:
    columns = ["id", "visit_no", "asset_code", "order_number", "diagnosis", "created_at"]
    identifiers = _identifier_columns(columns)
    assert "visit_no" in identifiers
    assert "asset_code" in identifiers
    assert "order_number" in identifiers
    assert "diagnosis" not in identifiers


# -- Operation routing --


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("MZ-2026-001 可以关闭吗", "closeVisitRecord"),
        ("MZ-2026-001 能提交审批吗", "applyVisitReview"),
    ],
)
def test_operations_resolve_from_registered_apis(
    clinic: dict[str, object], question: str, expected: str
) -> None:
    """Endpoint names follow no `submit_<object>` convention here."""
    resolved = _default_operation_code(
        clinic["platform_db"], question, "consultation", clinic["source_id"]
    )
    assert resolved == expected


def test_operation_resolution_returns_none_without_registered_apis(clinic: dict[str, object]) -> None:
    assert _default_operation_code(clinic["platform_db"], "提交", "consultation", None) is None


# -- Agent roles --


def test_agent_role_is_derived_from_the_onboarded_domain(clinic: dict[str, object]) -> None:
    roles = list_agent_roles(clinic["platform_db"])
    assert len(roles) == 1
    role = roles[0]
    assert role.domain == "宠物诊疗"
    assert "宠物诊疗" in role.name
    assert role.source == "derived"


def test_agent_prompt_lists_only_modelled_objects(clinic: dict[str, object]) -> None:
    role = resolve_agent_role(clinic["platform_db"], None)
    prompt = build_system_prompt(
        role,
        {
            "available": True,
            "name": "宠物诊疗系统",
            "domain": "宠物诊疗",
            "objects": [{"code": "pet", "name": "宠物"}, {"code": "consultation", "name": "诊疗记录"}],
        },
    )
    assert "宠物诊疗" in prompt
    assert "诊疗记录(consultation)" in prompt
    assert "合同" not in prompt


def test_custom_agent_role_can_be_persisted(clinic: dict[str, object]) -> None:
    upsert_agent_role(
        clinic["platform_db"], "clinic-advisor", "诊疗顾问",
        description="专注宠物诊疗复核", domain="宠物诊疗",
    )
    role_ids = {role.id for role in list_agent_roles(clinic["platform_db"])}
    assert "clinic-advisor" in role_ids
    assert resolve_agent_role(clinic["platform_db"], "clinic-advisor").name == "诊疗顾问"


def test_unknown_role_id_falls_back_without_error(clinic: dict[str, object]) -> None:
    role = resolve_agent_role(clinic["platform_db"], "contract-expert")
    assert role.domain == "宠物诊疗"


def test_slugify_domain_handles_latin_and_non_latin() -> None:
    assert slugify_domain("Supply Chain") == "supply-chain-expert"
    assert slugify_domain("宠物诊疗").endswith("-expert")
    assert slugify_domain("") == "domain-expert"


def test_slugify_domain_is_stable_across_processes() -> None:
    """Role ids must not depend on PYTHONHASHSEED.

    A randomized id would invalidate saved role selections and make audit
    records unmatchable after a restart.
    """
    import subprocess
    import sys

    script = (
        "import sys; sys.path.insert(0, 'backend');"
        "from ontology_platform.agent_roles import slugify_domain;"
        "print(slugify_domain('宠物诊疗'))"
    )
    root = Path(__file__).resolve().parents[1]
    outputs = set()
    for seed in ("0", "1", "12345"):
        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=root,
            capture_output=True,
            text=True,
            env={"PYTHONHASHSEED": seed, "PATH": "/usr/bin:/bin"},
            check=True,
        )
        outputs.add(completed.stdout.strip())
    assert len(outputs) == 1, f"角色 ID 在不同哈希种子下不稳定: {outputs}"


# -- Permissions and ontology resolution --


def test_default_policies_follow_modelled_objects(clinic: dict[str, object]) -> None:
    policies = list_policies(clinic["platform_db"])
    covered = {policy["object_code"] for policy in policies}
    assert covered == {"pet_owner", "pet", "consultation"}
    assert "contract" not in covered


def test_ontology_is_resolved_by_object_not_by_id_one(clinic: dict[str, object]) -> None:
    resolved = resolve_ontology_for_object(clinic["platform_db"], "consultation")
    assert resolved == clinic["ontology_id"]
    with pytest.raises(ValueError):
        resolve_ontology_for_object(clinic["platform_db"], "contract")
