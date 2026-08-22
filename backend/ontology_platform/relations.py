"""Relation semantics: what a link between two objects actually means.

Relations existed before this module, but only nominally. Every foreign key
produced one row with `relation_type = "references"` -- a constant. That is not a
relation model, it is a restatement of the foreign key. Three things were missing,
and each is something a business user states in the first sentence they say about
their domain:

- **Cardinality.** "A contract has *many* payment plans, but *one* customer."
  Without it, neither an explanation nor a UI can tell a collection from a single
  related object, and a rule author cannot know whether `payment_plan` is a row or
  a list.
- **Strength.** A payment plan without its contract is garbage; a contract without
  its optional sales rep is fine. Deleting, archiving and cascading all hinge on
  that difference.
- **Many-to-many.** A junction table is not a business object. Modelling
  `contract_tag` as an object with two "references" relations forces every rule and
  every question through a row nobody in the business talks about.

## Inference is structural, never statistical

Every classification here comes from declared schema structure -- primary keys,
nullability, foreign key targets. Nothing is inferred from data distribution.
A relation classified from a sample would change meaning when the data changes, and
a verdict citing it would be unreproducible (ADR-0005). The rules:

| Structure | Cardinality | Kind |
|---|---|---|
| FK column is the child's whole primary key | one-to-one | composition |
| FK column is *part of* a composite primary key | many-to-one | composition |
| FK column is NOT NULL, outside the primary key | many-to-one | aggregation |
| FK column is nullable | many-to-one, optional | association |
| Table is a junction, PK is exactly two FKs | many-to-many | association |

"Composition" means identity-dependent: the child cannot exist without the parent,
because the parent's key is part of what identifies the child. That is a fact about
the schema, not a guess.

## Junction tables collapse, but the object stays

A junction table becomes a `many_to_many` relation between the two objects it
links. The junction's own object is **not** removed: junction tables routinely
carry attributes of their own (`role`, `valid_from`, `weight`), and dropping the
object would lose them. So both views exist -- the direct many-to-many for rules
and questions, and the junction object for its attributes.

Stability: experimental (ADR-0007).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional, Sequence

from .instance_key import parse_key_columns

logger = logging.getLogger(__name__)

# Cardinalities, named from the source object's point of view: `one_to_many` means
# one source row relates to many target rows.
ONE_TO_ONE = "one_to_one"
MANY_TO_ONE = "many_to_one"
ONE_TO_MANY = "one_to_many"
MANY_TO_MANY = "many_to_many"
CARDINALITIES = (ONE_TO_ONE, MANY_TO_ONE, ONE_TO_MANY, MANY_TO_MANY)

# Relation kinds, ordered by strength. `composition` is identity-dependent,
# `aggregation` is mandatory but independent, `association` is optional.
COMPOSITION = "composition"
AGGREGATION = "aggregation"
ASSOCIATION = "association"
RELATION_KINDS = (COMPOSITION, AGGREGATION, ASSOCIATION)

# The inverse of each cardinality, used to describe the reverse direction.
INVERSE_CARDINALITY = {
    ONE_TO_ONE: ONE_TO_ONE,
    MANY_TO_ONE: ONE_TO_MANY,
    ONE_TO_MANY: MANY_TO_ONE,
    MANY_TO_MANY: MANY_TO_MANY,
}

CARDINALITY_LABELS = {
    ONE_TO_ONE: "一对一",
    MANY_TO_ONE: "多对一",
    ONE_TO_MANY: "一对多",
    MANY_TO_MANY: "多对多",
}

KIND_LABELS = {
    COMPOSITION: "组成",
    AGGREGATION: "聚合",
    ASSOCIATION: "关联",
}


@dataclass(frozen=True)
class ForeignKeyShape:
    """The structural facts about one foreign key that determine its semantics.

    Deliberately a value object over plain data rather than a database row, so the
    classification rules can be unit-tested without a schema and read in one place.
    """

    column_name: str
    target_table: str
    target_column: str
    # Whether the FK column is inside the child table's primary key, and whether
    # that primary key consists of nothing else.
    in_primary_key: bool
    is_whole_primary_key: bool
    nullable: bool


@dataclass(frozen=True)
class RelationSemantics:
    """The classification result for one foreign key."""

    cardinality: str
    kind: str
    optional: bool
    reason: str

    @property
    def inverse_cardinality(self) -> str:
        return INVERSE_CARDINALITY[self.cardinality]

    def describe(self) -> str:
        card = CARDINALITY_LABELS.get(self.cardinality, self.cardinality)
        kind = KIND_LABELS.get(self.kind, self.kind)
        return f"{card}·{kind}（{'可选' if self.optional else '必需'}）"


def classify_foreign_key(shape: ForeignKeyShape) -> RelationSemantics:
    """Classify one foreign key into cardinality and kind.

    The reason string is stored with the result, because an operator reviewing a
    generated relation needs to know *why* it was classified that way in order to
    correct it. A classification with no stated basis cannot be reviewed.
    """
    if shape.is_whole_primary_key:
        # The child's identity *is* the parent reference: at most one child row per
        # parent, and it cannot exist without one.
        return RelationSemantics(
            cardinality=ONE_TO_ONE,
            kind=COMPOSITION,
            optional=False,
            reason=f"外键 {shape.column_name} 构成子表全部主键，与父实例一一对应且身份依赖父实例。",
        )
    if shape.in_primary_key:
        return RelationSemantics(
            cardinality=MANY_TO_ONE,
            kind=COMPOSITION,
            optional=False,
            reason=f"外键 {shape.column_name} 是复合主键的一部分，子表身份依赖父实例。",
        )
    if not shape.nullable:
        return RelationSemantics(
            cardinality=MANY_TO_ONE,
            kind=AGGREGATION,
            optional=False,
            reason=f"外键 {shape.column_name} 非空且不在主键内，父实例必需但子表身份独立。",
        )
    return RelationSemantics(
        cardinality=MANY_TO_ONE,
        kind=ASSOCIATION,
        optional=True,
        reason=f"外键 {shape.column_name} 可空，父实例可选。",
    )


@dataclass(frozen=True)
class JunctionShape:
    """A table that exists only to link two others.

    `left` and `right` are the two foreign keys forming the primary key. Which is
    which is arbitrary; the many-to-many relation is generated in both directions.
    """

    table_name: str
    left: ForeignKeyShape
    right: ForeignKeyShape


def detect_junction(
    table_name: str,
    primary_key: str | None,
    foreign_keys: Sequence[ForeignKeyShape],
) -> Optional[JunctionShape]:
    """Identify a junction table by structure alone.

    The test is strict: the primary key must be exactly two columns, and both must
    be foreign keys to *different* tables. A table with a surrogate `id` primary key
    plus two foreign keys is deliberately not treated as a junction -- it has its own
    identity, which usually means the business talks about it (an order line, an
    enrolment).

    Being conservative matters asymmetrically: wrongly collapsing a real object
    would hide it from the model entirely, whereas missing a junction only leaves an
    extra hop a modeller can collapse by hand.
    """
    key_columns = parse_key_columns(primary_key)
    if len(key_columns) != 2:
        return None
    by_column = {fk.column_name: fk for fk in foreign_keys}
    left = by_column.get(key_columns[0])
    right = by_column.get(key_columns[1])
    if left is None or right is None:
        return None
    if left.target_table == right.target_table:
        # A self-link table (`prerequisite(course_a, course_b)`) is a genuine
        # many-to-many, but collapsing it would produce a relation from an object to
        # itself whose two sides are indistinguishable. Left as a plain object.
        return None
    return JunctionShape(table_name=table_name, left=left, right=right)


def junction_semantics(junction: JunctionShape) -> RelationSemantics:
    return RelationSemantics(
        cardinality=MANY_TO_MANY,
        kind=ASSOCIATION,
        optional=True,
        reason=(
            f"中间表 {junction.table_name} 的主键恰由两个外键 "
            f"{junction.left.column_name}、{junction.right.column_name} 组成，判定为多对多关联。"
        ),
    )


def shapes_for_table(
    primary_key: str | None,
    columns: Sequence[Any],
    foreign_keys: Sequence[Any],
) -> list[ForeignKeyShape]:
    """Build shapes from scanned metadata rows.

    Takes the raw `source_column` / `source_foreign_key` rows so callers do not each
    re-derive which columns are in the primary key.
    """
    key_columns = parse_key_columns(primary_key)
    nullable_by_column: dict[str, bool] = {}
    for column in columns:
        try:
            nullable_by_column[column["column_name"]] = bool(column["nullable"])
        except (KeyError, IndexError, TypeError):  # pragma: no cover - defensive
            continue
    shapes = []
    for foreign_key in foreign_keys:
        column_name = foreign_key["column_name"]
        shapes.append(
            ForeignKeyShape(
                column_name=column_name,
                target_table=foreign_key["target_table"],
                target_column=foreign_key["target_column"],
                in_primary_key=column_name in key_columns,
                is_whole_primary_key=tuple(key_columns) == (column_name,),
                # A column absent from the scan is treated as nullable, which yields
                # the weakest classification -- the safe direction, since overstating
                # a relation's strength would licence a cascade.
                nullable=nullable_by_column.get(column_name, True),
            )
        )
    return shapes
