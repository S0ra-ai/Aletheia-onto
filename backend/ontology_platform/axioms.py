"""Axioms: statements about the model that must hold before it can be published.

GB/T 48000.3—2026 lists five components of an ontology -- entity types, data
properties, object properties, **axioms**, and rules. This platform had four of them.
Axioms were the gap, and the gap was not cosmetic: a rule and an axiom answer different
questions, and the one axioms answer had no home.

## An axiom is not a rule

A **rule** evaluates an instance and produces a verdict: "this contract's amount
exceeds this customer's credit limit, so block it". It needs data, it runs per
instance, and its output is a decision with an explanation.

An **axiom** asserts something about the *model*: "a contract's first party and second
party can never be the same object", "an individual customer is never also a corporate
customer", "an equipment record belongs to exactly one family". It needs no instance
data, it is checked once per model version, and its output is whether the model is
self-consistent.

Conflating them has a specific cost. Written as a rule, "the two parties differ" is
re-evaluated on every assessment of every contract forever -- and it can only ever
report a *violated instance*, never the real problem, which is that the model permits a
shape the business does not. Worse, a model that contradicts itself still publishes:
nothing in the release gates looks at whether the declarations can all be true at once.

So axioms are checked at **modelling time** and block publication. The person who
caused the contradiction sees it, with the contradiction named, instead of an end user
seeing a verdict nobody can explain.

## Violations are refused at declaration, and re-checked at publication

Both, for different failure modes. Refusing at declaration gives immediate feedback to
whoever wrote it. Re-checking at publication catches the case the declaration check
cannot see: an axiom that was satisfiable when written and became unsatisfiable later,
because the *model* changed underneath it -- a subtype added, a relation retargeted.

A model that fails its own axioms must not publish. This is deliberately a blocker
rather than a warning: a warning on "your model contradicts itself" is a warning on a
condition that makes every verdict from that model suspect.

## Six axiom kinds, and why not more

Only shapes that can be checked against declared structure alone:

- `disjoint_types` -- two types share no instances
- `irreflexive_relation` -- nothing relates to itself through this relation
- `asymmetric_relation` -- if A relates to B, B does not relate to A
- `functional_relation` -- an instance relates to at most one target
- `required_attribute` -- an attribute must exist and be non-optional
- `disjoint_attributes` -- two attributes are mutually exclusive

What is deliberately absent is anything requiring open-world inference: no
`equivalentClass`, no property chains, no cardinality restrictions that imply the
existence of unseen instances. Those need DL subsumption, and ADR-0005 rules it out
because an inferred conclusion cannot be traced to a declaration a human made. An
axiom here is always checkable by reading the model, which is what makes a violation
explainable.

Stability: experimental (ADR-0007).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Optional

from .context import PlatformDb
from .database import connect, last_insert_id
from .schema import SchemaBundle

logger = logging.getLogger(__name__)

__all__ = [
    "AXIOM_KINDS",
    "SCHEMA",
    "AxiomError",
    "AxiomSpec",
    "AxiomViolation",
    "check_axioms",
    "declare_axiom",
    "describe_axiom_kinds",
    "init_axiom_schema",
    "list_axioms",
    "remove_axiom",
]

DISJOINT_TYPES = "disjoint_types"
IRREFLEXIVE_RELATION = "irreflexive_relation"
ASYMMETRIC_RELATION = "asymmetric_relation"
FUNCTIONAL_RELATION = "functional_relation"
REQUIRED_ATTRIBUTE = "required_attribute"
DISJOINT_ATTRIBUTES = "disjoint_attributes"

AXIOM_KINDS = (
    DISJOINT_TYPES,
    IRREFLEXIVE_RELATION,
    ASYMMETRIC_RELATION,
    FUNCTIONAL_RELATION,
    REQUIRED_ATTRIBUTE,
    DISJOINT_ATTRIBUTES,
)

# What each kind constrains, and what a violation of it would mean in business terms.
# Surfaced through the API so a modeller choosing a kind does not have to read this file.
AXIOM_KIND_NOTES = {
    DISJOINT_TYPES: (
        "两个类型不共享实例",
        "个人客户与企业客户不应同时成立。若某对象同时继承两者，判定会同时套用两套规则。",
    ),
    IRREFLEXIVE_RELATION: (
        "关系不可自反",
        "合同的甲方与乙方不能是同一主体。自反会让「上级」「关联方」这类关系产生自我引用。",
    ),
    ASYMMETRIC_RELATION: (
        "关系不可双向成立",
        "A 是 B 的上级，则 B 不能是 A 的上级。双向成立会让层级遍历不终止。",
    ),
    FUNCTIONAL_RELATION: (
        "一个实例最多关联一个目标",
        "一台设备只归属一个设备族。多于一个会让「该设备适用哪套规则」没有确定答案。",
    ),
    REQUIRED_ATTRIBUTE: (
        "属性必须存在且非空",
        "判定依赖的字段缺失时，规则会 fail-closed——表现为「全部不通过」而非「缺字段」。",
    ),
    DISJOINT_ATTRIBUTES: (
        "两个属性互斥",
        "同一笔金额不应既记在「预付」又记在「尾款」。两者同时有值意味着口径不一致。",
    ),
}

SCHEMA = SchemaBundle(
    name="axioms",
    tables=[
        {
            "sqlite": (
                "create table if not exists ontology_axiom ("
                "id integer primary key autoincrement,"
                " ontology_id integer not null references ontology(id),"
                " code text not null,"
                " kind text not null,"
                " subject text not null,"
                " object text not null default '',"
                " note text not null default '',"
                " unique(ontology_id, code))"
            ),
            "postgresql": (
                "create table if not exists ontology_axiom ("
                "id serial primary key,"
                " ontology_id integer not null references ontology(id),"
                " code text not null,"
                " kind text not null,"
                " subject text not null,"
                " object text not null default '',"
                " note text not null default '',"
                " unique(ontology_id, code))"
            ),
            "mysql": (
                "create table if not exists ontology_axiom ("
                "id integer primary key auto_increment,"
                " ontology_id integer not null references ontology(id),"
                " code varchar(255) not null,"
                " kind varchar(100) not null,"
                " subject varchar(500) not null,"
                " object varchar(500) not null default '',"
                " note text not null,"
                " unique(ontology_id, code))"
            ),
        }
    ],
    table_names=["ontology_axiom"],
)


class AxiomError(ValueError):
    """Raised when an axiom declaration is malformed or the model already violates it."""


@dataclass(frozen=True)
class AxiomSpec:
    """One axiom declaration.

    `subject` and `object` are interpreted per kind, which keeps one table rather than
    six: a relation axiom names the relation in `subject`, a disjointness axiom names
    two object codes, an attribute axiom names `object_code.attribute_code`. The
    interpretation is validated at declaration time, so a wrong shape cannot be stored.
    """

    code: str
    kind: str
    subject: str
    object: str = ""
    note: str = ""

    def __post_init__(self) -> None:
        if not self.code.strip():
            raise AxiomError("公理编码不能为空")
        if self.kind not in AXIOM_KINDS:
            raise AxiomError(f"未知公理类型 {self.kind}，支持: {'、'.join(AXIOM_KINDS)}")
        if not self.subject.strip():
            raise AxiomError("公理主体不能为空")
        if self.kind in (DISJOINT_TYPES, DISJOINT_ATTRIBUTES) and not self.object.strip():
            raise AxiomError(f"{self.kind} 需要两个操作数，object 不能为空")
        if self.kind in (DISJOINT_TYPES, DISJOINT_ATTRIBUTES) and self.subject.strip() == self.object.strip():
            # An axiom asserting a thing is disjoint from itself can never hold, and a
            # stored one would block publication with a message nobody can act on.
            raise AxiomError(f"{self.kind} 的两个操作数不能相同: {self.subject}")


@dataclass(frozen=True)
class AxiomViolation:
    """A model-level contradiction, named precisely enough to fix."""

    code: str
    kind: str
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "kind": self.kind, "detail": self.detail}


def init_axiom_schema(conn: Any) -> None:
    SCHEMA.apply(conn)


def describe_axiom_kinds() -> list[dict[str, str]]:
    """Every kind with its meaning and the consequence of violating it.

    The consequence matters more than the definition. "Irreflexive" tells a modeller
    nothing; "the two parties of a contract cannot be the same entity" tells them
    whether they need it.
    """
    return [
        {"kind": kind, "summary": AXIOM_KIND_NOTES[kind][0], "consequence": AXIOM_KIND_NOTES[kind][1]}
        for kind in AXIOM_KINDS
    ]


def declare_axiom(platform_db: PlatformDb, ontology_id: int, spec: AxiomSpec) -> dict[str, Any]:
    """Store an axiom, refusing one the model already violates.

    Checked before storing, not after. An axiom accepted into a model that contradicts
    it would block publication later, at which point the person who has to fix it is
    whoever tries to publish -- not whoever wrote the axiom.
    """
    with connect(platform_db) as conn:
        init_axiom_schema(conn)
        _require_ontology(conn, ontology_id)
        _validate_operands(conn, ontology_id, spec)

        violations = _check_one(conn, ontology_id, spec)
        if violations:
            raise AxiomError("模型当前违反该公理: " + "；".join(item.detail for item in violations))

        conn.execute(
            "delete from ontology_axiom where ontology_id = ? and code = ?",
            (ontology_id, spec.code),
        )
        conn.execute(
            "insert into ontology_axiom (ontology_id, code, kind, subject, object, note) values (?, ?, ?, ?, ?, ?)",
            (ontology_id, spec.code, spec.kind, spec.subject, spec.object, spec.note),
        )
        axiom_id = last_insert_id(conn)

    return {
        "id": axiom_id,
        "ontologyId": ontology_id,
        "code": spec.code,
        "kind": spec.kind,
        "subject": spec.subject,
        "object": spec.object,
        "note": spec.note,
    }


def remove_axiom(platform_db: PlatformDb, ontology_id: int, code: str) -> dict[str, Any]:
    with connect(platform_db) as conn:
        init_axiom_schema(conn)
        cursor = conn.execute(
            "delete from ontology_axiom where ontology_id = ? and code = ?",
            (ontology_id, code),
        )
        removed = getattr(cursor, "rowcount", 0) or 0
    if not removed:
        raise AxiomError(f"公理不存在: {code}")
    return {"removed": code}


def list_axioms(platform_db: PlatformDb, ontology_id: int) -> list[dict[str, Any]]:
    with connect(platform_db) as conn:
        if not SCHEMA.has_tables(conn):
            return []
        rows = conn.execute(
            "select code, kind, subject, object, note from ontology_axiom where ontology_id = ? order by code",
            (ontology_id,),
        ).fetchall()
    return [
        {
            "code": row["code"],
            "kind": row["kind"],
            "subject": row["subject"],
            "object": row["object"],
            "note": row["note"],
            "summary": AXIOM_KIND_NOTES.get(row["kind"], ("", ""))[0],
        }
        for row in rows
    ]


def check_axioms(platform_db: PlatformDb, ontology_id: int) -> dict[str, Any]:
    """Re-check every axiom against the current model.

    Called by the release gates. Separate from `declare_axiom`'s check because the model
    moves after an axiom is written: a subtype added later, a relation retargeted, an
    attribute made optional. An axiom that held when declared is not an axiom that holds.
    """
    with connect(platform_db) as conn:
        if not SCHEMA.has_tables(conn):
            return {"ontologyId": ontology_id, "declared": 0, "satisfied": True, "violations": []}
        rows = conn.execute(
            "select code, kind, subject, object, note from ontology_axiom where ontology_id = ? order by code",
            (ontology_id,),
        ).fetchall()

        violations: list[AxiomViolation] = []
        for row in rows:
            spec = AxiomSpec(
                code=row["code"],
                kind=row["kind"],
                subject=row["subject"],
                object=row["object"],
                note=row["note"],
            )
            violations.extend(_check_one(conn, ontology_id, spec))

    return {
        "ontologyId": ontology_id,
        "declared": len(rows),
        "satisfied": not violations,
        "violations": [item.as_dict() for item in violations],
    }


# -- Operand validation --


def _require_ontology(conn: Any, ontology_id: int) -> None:
    if conn.execute("select id from ontology where id = ?", (ontology_id,)).fetchone() is None:
        raise AxiomError(f"本体不存在: {ontology_id}")


def _object_codes(conn: Any, ontology_id: int) -> set[str]:
    return {
        row["code"]
        for row in conn.execute("select code from business_object where ontology_id = ?", (ontology_id,)).fetchall()
    }


def _relation(conn: Any, ontology_id: int, code: str) -> Optional[Any]:
    return conn.execute(
        """
        select br.code, br.name, br.relation_type,
               src.code as source_code, tgt.code as target_code
        from business_relation br
        join business_object src on src.id = br.source_object_id
        join business_object tgt on tgt.id = br.target_object_id
        where br.ontology_id = ? and br.code = ?
        """,
        (ontology_id, code),
    ).fetchone()


def _split_attribute(reference: str) -> tuple[str, str]:
    if "." not in reference:
        raise AxiomError(f"属性引用需为 对象编码.属性编码 形式: {reference}")
    object_code, _, attribute_code = reference.partition(".")
    if not object_code.strip() or not attribute_code.strip():
        raise AxiomError(f"属性引用不完整: {reference}")
    return object_code.strip(), attribute_code.strip()


def _attribute(conn: Any, ontology_id: int, reference: str) -> Any:
    object_code, attribute_code = _split_attribute(reference)
    row = conn.execute(
        """
        select ba.code, ba.required, bo.code as object_code
        from business_attribute ba
        join business_object bo on bo.id = ba.object_id
        where bo.ontology_id = ? and bo.code = ? and ba.code = ?
        """,
        (ontology_id, object_code, attribute_code),
    ).fetchone()
    return row


def _validate_operands(conn: Any, ontology_id: int, spec: AxiomSpec) -> None:
    """Refuse an axiom that names something the model does not contain.

    An axiom about a misspelled relation is vacuously satisfied -- it constrains nothing
    and reports nothing, so the modeller believes a control is in place that is not.
    That is strictly worse than having no axiom, which is why this is refused rather
    than warned about.
    """
    if spec.kind == DISJOINT_TYPES:
        codes = _object_codes(conn, ontology_id)
        missing = [code for code in (spec.subject, spec.object) if code not in codes]
        if missing:
            raise AxiomError(f"业务对象不存在: {'、'.join(missing)}")
        return

    if spec.kind in (IRREFLEXIVE_RELATION, ASYMMETRIC_RELATION, FUNCTIONAL_RELATION):
        if _relation(conn, ontology_id, spec.subject) is None:
            raise AxiomError(f"业务关系不存在: {spec.subject}")
        return

    if spec.kind == REQUIRED_ATTRIBUTE:
        if _attribute(conn, ontology_id, spec.subject) is None:
            raise AxiomError(f"业务属性不存在: {spec.subject}")
        return

    if spec.kind == DISJOINT_ATTRIBUTES:
        for reference in (spec.subject, spec.object):
            if _attribute(conn, ontology_id, reference) is None:
                raise AxiomError(f"业务属性不存在: {reference}")
        left_object, _ = _split_attribute(spec.subject)
        right_object, _ = _split_attribute(spec.object)
        if left_object != right_object:
            # Two attributes on different objects are never in conflict: there is no
            # single record on which both could be set.
            raise AxiomError(f"互斥属性必须属于同一对象: {left_object} / {right_object}")


# -- Checking --


def _check_one(conn: Any, ontology_id: int, spec: AxiomSpec) -> list[AxiomViolation]:
    checker = {
        DISJOINT_TYPES: _check_disjoint_types,
        IRREFLEXIVE_RELATION: _check_irreflexive,
        ASYMMETRIC_RELATION: _check_asymmetric,
        FUNCTIONAL_RELATION: _check_functional,
        REQUIRED_ATTRIBUTE: _check_required_attribute,
        DISJOINT_ATTRIBUTES: _check_disjoint_attributes,
    }[spec.kind]
    return checker(conn, ontology_id, spec)


def _ancestors(conn: Any, ontology_id: int, object_code: str) -> list[str]:
    """Declared parent chain, imported lazily-free.

    Uses `type_hierarchy` rather than re-walking `parent_object_code`, so "what does
    this type inherit" has one answer. A second walk here would be a second definition
    of the hierarchy, and the two would disagree the first time either changed.
    """
    from .type_hierarchy import ancestors_of

    return ancestors_of(conn, ontology_id, object_code)


def _check_disjoint_types(conn: Any, ontology_id: int, spec: AxiomSpec) -> list[AxiomViolation]:
    """Two types share no instances.

    Checked structurally: a type that inherits from both is a type whose instances are
    instances of both, which is exactly what the axiom forbids. This is the one shape
    that can be established without data, and it is also the shape a modeller actually
    creates by accident.
    """
    codes = _object_codes(conn, ontology_id)
    for code in sorted(codes):
        lineage = {code, *_ancestors(conn, ontology_id, code)}
        if spec.subject in lineage and spec.object in lineage:
            return [
                AxiomViolation(
                    spec.code,
                    spec.kind,
                    f"对象 {code} 同时继承互斥类型 {spec.subject} 与 {spec.object}",
                )
            ]
    return []


def _check_irreflexive(conn: Any, ontology_id: int, spec: AxiomSpec) -> list[AxiomViolation]:
    relation = _relation(conn, ontology_id, spec.subject)
    if relation is None:
        return [AxiomViolation(spec.code, spec.kind, f"业务关系已不存在: {spec.subject}")]
    if relation["source_code"] == relation["target_code"]:
        return [
            AxiomViolation(
                spec.code,
                spec.kind,
                f"关系 {spec.subject} 的两端均为 {relation['source_code']}，允许自反",
            )
        ]
    return []


def _check_asymmetric(conn: Any, ontology_id: int, spec: AxiomSpec) -> list[AxiomViolation]:
    """No declared relation runs the other way between the same pair.

    Asymmetry is violated by the *model*, not by a row: if `subordinate_of` goes
    Employee→Employee and another relation goes the same way, the pair can be related in
    both directions and a hierarchy walk need not terminate.
    """
    relation = _relation(conn, ontology_id, spec.subject)
    if relation is None:
        return [AxiomViolation(spec.code, spec.kind, f"业务关系已不存在: {spec.subject}")]
    if relation["source_code"] == relation["target_code"]:
        return [
            AxiomViolation(
                spec.code,
                spec.kind,
                f"关系 {spec.subject} 两端同为 {relation['source_code']}，无法保证非对称",
            )
        ]
    inverse = conn.execute(
        """
        select br.code
        from business_relation br
        join business_object src on src.id = br.source_object_id
        join business_object tgt on tgt.id = br.target_object_id
        where br.ontology_id = ? and br.code <> ?
          and src.code = ? and tgt.code = ?
        """,
        (ontology_id, spec.subject, relation["target_code"], relation["source_code"]),
    ).fetchone()
    if inverse is not None:
        return [
            AxiomViolation(
                spec.code,
                spec.kind,
                f"关系 {spec.subject} 存在反向关系 {inverse['code']}，两者可同时成立",
            )
        ]
    return []


def _check_functional(conn: Any, ontology_id: int, spec: AxiomSpec) -> list[AxiomViolation]:
    """At most one target per instance, established from the declared cardinality.

    `relations.py` already classifies cardinality from the schema, so this reads that
    classification rather than re-deriving it. A relation declared one-to-many or
    many-to-many contradicts functionality by construction.
    """
    relation = _relation(conn, ontology_id, spec.subject)
    if relation is None:
        return [AxiomViolation(spec.code, spec.kind, f"业务关系已不存在: {spec.subject}")]

    cardinality = _relation_cardinality(conn, ontology_id, spec.subject)
    if cardinality in ("one_to_many", "many_to_many"):
        return [
            AxiomViolation(
                spec.code,
                spec.kind,
                f"关系 {spec.subject} 的基数为 {cardinality}，与「最多关联一个」冲突",
            )
        ]
    return []


def _relation_cardinality(conn: Any, ontology_id: int, code: str) -> str:
    """The relation's cardinality, or empty when the column has not shipped yet.

    Tolerant of a missing column because `cardinality` was added after
    `business_relation` shipped: on an installation that has not applied the addition,
    an axiom check must report "cannot determine" by staying silent rather than raising
    an error a user cannot act on.
    """
    try:
        row = conn.execute(
            "select cardinality from business_relation where ontology_id = ? and code = ?",
            (ontology_id, code),
        ).fetchone()
    except Exception:  # pragma: no cover - pre-migration installations only
        logger.debug("business_relation.cardinality 不可用，跳过基数公理检查")
        return ""
    return (row["cardinality"] or "") if row is not None else ""


def _check_required_attribute(conn: Any, ontology_id: int, spec: AxiomSpec) -> list[AxiomViolation]:
    row = _attribute(conn, ontology_id, spec.subject)
    if row is None:
        return [AxiomViolation(spec.code, spec.kind, f"业务属性已不存在: {spec.subject}")]
    if not row["required"]:
        return [
            AxiomViolation(
                spec.code,
                spec.kind,
                f"属性 {spec.subject} 声明为可空，与「必须存在」冲突",
            )
        ]
    return []


def _check_disjoint_attributes(conn: Any, ontology_id: int, spec: AxiomSpec) -> list[AxiomViolation]:
    """Mutually exclusive attributes cannot both be mandatory.

    That is the contradiction visible without data: if both are required, every record
    must set both, and the axiom says no record may. Whether a *particular* record sets
    both is a rule's question, not an axiom's.
    """
    left = _attribute(conn, ontology_id, spec.subject)
    right = _attribute(conn, ontology_id, spec.object)
    for reference, row in ((spec.subject, left), (spec.object, right)):
        if row is None:
            return [AxiomViolation(spec.code, spec.kind, f"业务属性已不存在: {reference}")]
    if left["required"] and right["required"]:
        return [
            AxiomViolation(
                spec.code,
                spec.kind,
                f"属性 {spec.subject} 与 {spec.object} 同为必填，无法互斥",
            )
        ]
    return []


def axioms_as_json(platform_db: PlatformDb, ontology_id: int) -> str:
    """Declared axioms as JSON, for the kernel package and exports."""
    return json.dumps(list_axioms(platform_db, ontology_id), ensure_ascii=False)
