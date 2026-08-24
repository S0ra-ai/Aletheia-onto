"""Runtime domain vocabulary.

A general-purpose ontology platform cannot ship a fixed list of business
objects. Any built-in table of terms ("contract" means 合同) silently makes the
platform a single-industry product: the first customer in a domain nobody
anticipated gets worse object detection, worse labels and wrong fallbacks.

So the vocabulary is derived at runtime from assets the platform already owns:

1. Business objects of the relevant ontologies (code, name, description).
2. Business attributes, for column level naming.
3. Industry blueprints, including user imported ones.

Nothing here contains industry terms. Domain knowledge enters through
blueprints and scanned metadata, both of which are user maintainable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .database import connect
from .industry_blueprints import list_industry_blueprints


@dataclass(frozen=True)
class ObjectTerm:
    """One business object as the language layer sees it."""

    ontology_id: int
    code: str
    name: str
    description: str = ""
    data_source_id: Optional[int] = None
    source_table: str = ""
    instance_count_hint: int = 0

    @property
    def label(self) -> str:
        return self.name or self.code


@dataclass
class DomainVocabulary:
    """The set of business terms currently modelled in the platform."""

    objects: tuple[ObjectTerm, ...] = field(default_factory=tuple)
    attribute_labels: dict[str, str] = field(default_factory=dict)

    # -- Lookups --

    def label_for(self, object_code: str) -> str:
        for term in self.objects:
            if term.code == object_code:
                return term.label
        return object_code

    def codes(self) -> tuple[str, ...]:
        return tuple(term.code for term in self.objects)

    def get(self, object_code: str) -> Optional[ObjectTerm]:
        for term in self.objects:
            if term.code == object_code:
                return term
        return None

    def attribute_label(self, column_name: str) -> str:
        return self.attribute_labels.get(column_name, "")

    # -- Detection --

    def detect(self, text: str) -> Optional[ObjectTerm]:
        """Find the business object a question refers to.

        Matching is ordered from most to least specific: an explicit code, then
        the display label, then a loose token match. Longer labels are tried
        first so "付款计划" is preferred over a hypothetical "付款".
        """
        if not text:
            return None
        lowered = text.lower()

        for term in sorted(self.objects, key=lambda item: len(item.code), reverse=True):
            if term.code and re.search(rf"\b{re.escape(term.code)}\b", lowered):
                return term

        for term in sorted(self.objects, key=lambda item: len(item.name or ""), reverse=True):
            if term.name and term.name in text:
                return term

        # Fall back to the source table name, which is what a technical user
        # may well type instead of the business label.
        for term in sorted(self.objects, key=lambda item: len(item.source_table or ""), reverse=True):
            if term.source_table and term.source_table.lower() in lowered:
                return term

        return None

    def default_object(self) -> Optional[ObjectTerm]:
        """The object to assume when a question names none.

        Preference goes to the object with the most relationships and rules,
        which is computed by the caller and passed in as a hint. Falling back to
        a fixed code such as "contract" would be a domain assumption.
        """
        if not self.objects:
            return None
        return max(self.objects, key=lambda term: (term.instance_count_hint, term.code))


def load_vocabulary(
    platform_db: Path | str,
    ontology_id: int | None = None,
    data_source_id: int | None = None,
) -> DomainVocabulary:
    """Build the vocabulary from modelled ontology assets.

    Narrowing by ontology or data source keeps detection scoped to the systems
    the caller is actually working with.
    """
    filters: list[str] = []
    params: list[Any] = []
    if ontology_id is not None:
        filters.append("bo.ontology_id = ?")
        params.append(ontology_id)
    if data_source_id is not None:
        filters.append("st.data_source_id = ?")
        params.append(data_source_id)
    where = f"where {' and '.join(filters)}" if filters else ""

    with connect(platform_db) as conn:
        rows = conn.execute(
            f"""
            select bo.ontology_id, bo.code, bo.name, bo.description,
                   st.data_source_id, st.table_name,
                   (select count(*) from business_relation br
                     where br.source_object_id = bo.id or br.target_object_id = bo.id) as relation_count,
                   (select count(*) from business_rule r
                     where r.ontology_id = bo.ontology_id and r.scope_object_code = bo.code) as rule_count
            from business_object bo
            left join source_table st on st.id = bo.source_table_id
            {where}
            order by bo.ontology_id desc, bo.code
            """,
            params,
        ).fetchall()

        attribute_rows = conn.execute(
            f"""
            select distinct sc.column_name, ba.name
            from business_attribute ba
            join business_object bo on bo.id = ba.object_id
            left join source_column sc on sc.id = ba.source_column_id
            left join source_table st on st.id = bo.source_table_id
            {where}
            """,
            params,
        ).fetchall()

    objects = tuple(
        ObjectTerm(
            ontology_id=int(row["ontology_id"]),
            code=row["code"],
            name=row["name"] or row["code"],
            description=row["description"] or "",
            data_source_id=row["data_source_id"],
            source_table=row["table_name"] or "",
            # Richer objects (more relations and rules) are better defaults than
            # an arbitrary alphabetical first pick.
            instance_count_hint=int(row["relation_count"] or 0) + int(row["rule_count"] or 0),
        )
        for row in rows
    )

    attribute_labels = {row["column_name"]: row["name"] for row in attribute_rows if row["column_name"] and row["name"]}
    return DomainVocabulary(objects=objects, attribute_labels=attribute_labels)


def blueprint_attribute_labels(platform_db: Path | str) -> dict[str, str]:
    """Column labels contributed by every registered industry blueprint.

    Used while generating a first draft, before business attributes exist.
    """
    labels: dict[str, str] = {}
    for blueprint in list_industry_blueprints(platform_db):
        hints = blueprint.get("attributeHints") or {}
        if isinstance(hints, dict):
            for column, label in hints.items():
                labels.setdefault(str(column), str(label))
    return labels


def blueprint_object_labels(platform_db: Path | str) -> dict[str, str]:
    """Object labels contributed by every registered industry blueprint."""
    labels: dict[str, str] = {}
    for blueprint in list_industry_blueprints(platform_db):
        hints = blueprint.get("objectHints") or {}
        if isinstance(hints, dict):
            for code, label in hints.items():
                labels.setdefault(str(code), str(label))
    return labels


def default_object_code_for_ontology(platform_db: Path | str, ontology_id: int) -> str:
    """The most connected business object of an ontology.

    Used as an implicit scope when an imported artefact does not name one.
    """
    vocabulary = load_vocabulary(platform_db, ontology_id=ontology_id)
    term = vocabulary.default_object()
    return term.code if term is not None else ""
