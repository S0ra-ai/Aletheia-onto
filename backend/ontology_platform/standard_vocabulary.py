"""OWL/RDFS/SHACL serialisation: the same ontology in vocabulary other tools understand.

The platform already exported JSON-LD and Turtle, and that was not enough. The syntax
was standard; the *vocabulary* was not. Every term was minted here -- `ont:BusinessObject`,
`ont:sourceObject`, `ont:required` -- so a standard RDF tool receiving the export saw a
graph of predicates it had never heard of.

The distinction matters because it is exactly the one that interoperability turns on. A
consumer that knows OWL knows that `rdfs:domain` constrains which class a property
applies to, and can act on it. It cannot know that `ont:sourceObject` means the same
thing. So the export was machine-*readable* and not machine-*interpretable*, and
semantic interoperability -- the stated purpose of GB/T 48000.3—2026 -- needs the second.

## Mapping, not replacement

`ontology.py`'s `ont:` export stays. It has consumers (the frontend, the kernel package),
and it carries fields standard vocabulary has no term for: `sourceTable`, `cardinality`
as a named enum, rule expressions. Dropping them to be standards-pure would lose the
information that makes an export usable for *this* platform's purpose.

So this module adds a second serialisation rather than changing the first:

| platform concept | standard term |
|---|---|
| business object | `owl:Class` |
| business attribute | `owl:DatatypeProperty` + `rdfs:domain` + `rdfs:range` |
| business relation | `owl:ObjectProperty` + `rdfs:domain` + `rdfs:range` |
| subtype declaration | `rdfs:subClassOf` |
| disjoint types axiom | `owl:disjointWith` |
| irreflexive / asymmetric / functional axiom | `owl:IrreflexiveProperty` etc. |
| required attribute | `sh:minCount 1` |

`rdfs:domain` and `rdfs:range` are the ones worth calling out: they were always present
in the model as `source_object_id` and `target_object_id`, foreign-keyed to
`business_object`. What was missing was saying so in a term a reasoner recognises.

## SHACL shapes are generated, never hand-written

A hand-written shape file would drift from the release gates it is supposed to mirror,
and the drifted copy would state constraints the platform does not enforce -- which is
worse than shipping no shapes, because a consumer would validate against them and
believe the result.

So shapes are derived from the same declarations the gates read: `required` attributes
become `sh:minCount 1`, declared datatypes become `sh:datatype`, functional relations
become `sh:maxCount 1`, disjointness becomes `sh:not`. If a declaration changes, the
shape changes with it because there is only one source.

## What is deliberately not emitted

No `owl:equivalentClass`, no property chains, no cardinality restrictions that assert
the existence of unseen instances. Those are the constructs that require DL reasoning to
be useful, and ADR-0005 rules that out: a conclusion reached by subsumption cannot be
traced back to a declaration a human made, and traceability is what this platform sells.

Adopting OWL as a *vocabulary* and refusing OWL *reasoning* is a coherent position, and
the standard's recommendation of OWL is a recommendation about the former.

Stability: experimental (ADR-0007).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .axioms import (
    ASYMMETRIC_RELATION,
    DISJOINT_ATTRIBUTES,
    DISJOINT_TYPES,
    FUNCTIONAL_RELATION,
    IRREFLEXIVE_RELATION,
    REQUIRED_ATTRIBUTE,
    list_axioms,
)
from .config import SEMANTIC_ASSET_NAMING
from .database import connect

__all__ = [
    "STANDARD_EXPORT_FORMATS",
    "XSD_BY_DATA_TYPE",
    "export_owl_turtle",
    "export_shacl_shapes",
    "export_standard_asset",
]

STANDARD_EXPORT_FORMATS = ("owl", "shacl")

# Platform data types to XSD. `xsd:string` is the fallback rather than an error: an
# unmapped type must still export, because a consumer can read a string and cannot read
# a missing triple. Losing precision is recoverable; losing the attribute is not.
XSD_BY_DATA_TYPE = {
    "string": "xsd:string",
    "text": "xsd:string",
    "integer": "xsd:integer",
    "int": "xsd:integer",
    "number": "xsd:decimal",
    "numeric": "xsd:decimal",
    "decimal": "xsd:decimal",
    "float": "xsd:double",
    "double": "xsd:double",
    "boolean": "xsd:boolean",
    "bool": "xsd:boolean",
    "date": "xsd:date",
    "datetime": "xsd:dateTime",
    "timestamp": "xsd:dateTime",
    "json": "rdf:JSON",
}

# Cardinalities that permit more than one target. Used to decide `sh:maxCount`.
_MULTI_VALUED = {"one_to_many", "many_to_many"}

_PREFIXES = [
    "@prefix owl: <http://www.w3.org/2002/07/owl#> .",
    "@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .",
    "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
    "@prefix sh: <http://www.w3.org/ns/shacl#> .",
    "@prefix skos: <http://www.w3.org/2004/02/skos/core#> .",
    "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .",
]


def export_standard_asset(
    platform_db: Path | str,
    ontology_id: int,
    export_format: str = "owl",
) -> dict[str, str]:
    """One ontology as OWL or as SHACL shapes.

    Same signature shape as `ontology.export_ontology_asset`, so a caller choosing
    between platform and standard vocabulary does not have to switch call styles.
    """
    normalized = export_format.lower()
    if normalized not in STANDARD_EXPORT_FORMATS:
        raise ValueError(f"仅支持 {'、'.join(STANDARD_EXPORT_FORMATS)} 导出格式")

    detail = _model(platform_db, ontology_id)
    if normalized == "owl":
        content = export_owl_turtle(detail)
        suffix, media = "owl.ttl", "text/turtle"
    else:
        content = export_shacl_shapes(detail)
        suffix, media = "shapes.ttl", "text/turtle"

    return {
        "content": content,
        "mediaType": media,
        "filename": f"ontology-{ontology_id}-v{detail['ontology']['version']}.{suffix}",
    }


def _model(platform_db: Path | str, ontology_id: int) -> dict[str, Any]:
    """Everything the two serialisations need, read once.

    Read here rather than through `summarize_ontology` because the standard forms need
    two things that summary does not carry: the declared parent chain (for
    `rdfs:subClassOf`) and the axioms (for OWL characteristics and SHACL constraints).
    """
    with connect(platform_db) as conn:
        ontology = conn.execute("select * from ontology where id = ?", (ontology_id,)).fetchone()
        if ontology is None:
            raise ValueError(f"本体不存在: {ontology_id}")

        objects = [
            dict(row)
            for row in conn.execute(
                """
                select bo.id, bo.code, bo.name, bo.description, bo.parent_object_code
                from business_object bo
                where bo.ontology_id = ?
                order by bo.code
                """,
                (ontology_id,),
            ).fetchall()
        ]
        attributes = [
            dict(row)
            for row in conn.execute(
                """
                select ba.code, ba.name, ba.data_type, ba.required, bo.code as object_code
                from business_attribute ba
                join business_object bo on bo.id = ba.object_id
                where bo.ontology_id = ?
                order by bo.code, ba.code
                """,
                (ontology_id,),
            ).fetchall()
        ]
        relations = [
            dict(row)
            for row in conn.execute(
                """
                select br.code, br.name, src.code as source_code, tgt.code as target_code
                from business_relation br
                join business_object src on src.id = br.source_object_id
                join business_object tgt on tgt.id = br.target_object_id
                where br.ontology_id = ?
                order by br.code
                """,
                (ontology_id,),
            ).fetchall()
        ]
        cardinality_by_code = _cardinalities(conn, ontology_id)

    return {
        "ontology": dict(ontology),
        "objects": objects,
        "attributes": attributes,
        "relations": relations,
        "cardinality": cardinality_by_code,
        "axioms": list_axioms(platform_db, ontology_id),
    }


def _cardinalities(conn: Any, ontology_id: int) -> dict[str, str]:
    """Relation code to cardinality, empty when the column has not shipped.

    Tolerant because `cardinality` was added after `business_relation`: on an
    installation that has not applied the addition, an export must still succeed with
    less precision rather than fail.
    """
    try:
        rows = conn.execute(
            "select code, cardinality from business_relation where ontology_id = ?",
            (ontology_id,),
        ).fetchall()
    except Exception:  # pragma: no cover - pre-migration installations only
        return {}
    return {row["code"]: (row["cardinality"] or "") for row in rows}


def _base(ontology: dict[str, Any]) -> str:
    base = SEMANTIC_ASSET_NAMING.ontology_base.rstrip("/")
    return f"{base}/{ontology['id']}/v/{_slug(str(ontology['version']))}/"


def _slug(value: str) -> str:
    import re

    normalized = re.sub(r"[^0-9a-zA-Z_.-]+", "-", value.strip())
    return re.sub(r"-+", "-", normalized).strip("-") or "item"


def _literal(value: object) -> str:
    return json.dumps("" if value is None else str(value), ensure_ascii=False)


# IRIs are written in full inside angle brackets rather than as `bp:class/x`.
#
# A prefixed name's local part cannot contain `/` in Turtle -- the parser stops at the
# slash and the statement is a syntax error. This was not a hypothetical: the existing
# `ont:` Turtle export emitted `bp:object/contract` and **no RDF parser could read it**,
# for as long as it has shipped. The tests never caught it because they asserted that
# the output *contained* certain substrings, which a syntactically invalid document does
# just as well as a valid one.
#
# So every IRI here goes through these helpers, and the tests parse the result with a
# real RDF library instead of matching text.
def _class_iri(base: str, code: str) -> str:
    return f"<{base}class/{_slug(code)}>"


def _property_iri(base: str, object_code: str, attribute_code: str) -> str:
    return f"<{base}property/{_slug(object_code)}.{_slug(attribute_code)}>"


def _relation_iri(base: str, code: str) -> str:
    return f"<{base}relation/{_slug(code)}>"


def _shape_iri(base: str, code: str) -> str:
    return f"<{base}shape/{_slug(code)}>"


def _xsd_for(data_type: str) -> str:
    return XSD_BY_DATA_TYPE.get((data_type or "").strip().lower(), "xsd:string")


def export_owl_turtle(detail: dict[str, Any]) -> str:
    """The ontology as OWL, in Turtle.

    Objects become classes, attributes become datatype properties, relations become
    object properties -- each with `rdfs:domain` and `rdfs:range`, which is what lets a
    consumer know that `purchase` runs from Customer to Product rather than merely
    existing.
    """
    ontology = detail["ontology"]
    base = _base(ontology)
    lines = [*_PREFIXES, f"@prefix bp: <{base}> .", ""]

    lines += [
        "bp: a owl:Ontology ;",
        f"  rdfs:label {_literal(ontology['name'])} ;",
        f"  owl:versionInfo {_literal(ontology['version'])} ;",
        # skos:note rather than a minted predicate: the domain is editorial metadata,
        # and a consumer that knows SKOS can display it.
        f"  skos:note {_literal(ontology['domain'])} .",
        "",
    ]

    object_codes = {item["code"] for item in detail["objects"]}
    for item in detail["objects"]:
        statements = [
            f"{_class_iri(base, item['code'])} a owl:Class ;",
            f"  rdfs:label {_literal(item['name'])} ;",
            "  rdfs:isDefinedBy bp: ;",
        ]
        if item.get("description"):
            statements.append(f"  rdfs:comment {_literal(item['description'])} ;")
        parent = (item.get("parent_object_code") or "").strip()
        if parent and parent in object_codes:
            # The declared hierarchy, stated in the term a reasoner acts on. Nothing is
            # inferred: this edge exists because someone declared it.
            statements.append(f"  rdfs:subClassOf {_class_iri(base, parent)} ;")
        statements[-1] = statements[-1].rstrip(" ;") + " ."
        lines += [*statements, ""]

    for item in detail["attributes"]:
        lines += [
            f"{_property_iri(base, item['object_code'], item['code'])} a owl:DatatypeProperty ;",
            f"  rdfs:label {_literal(item['name'])} ;",
            f"  rdfs:domain {_class_iri(base, item['object_code'])} ;",
            f"  rdfs:range {_xsd_for(item['data_type'])} .",
            "",
        ]

    characteristics = _relation_characteristics(detail["axioms"])
    for item in detail["relations"]:
        statements = [
            f"{_relation_iri(base, item['code'])} a owl:ObjectProperty ;",
            f"  rdfs:label {_literal(item['name'])} ;",
            # Domain and range were always in the model as two foreign keys. This is the
            # first time they are said in a term a standard tool recognises.
            f"  rdfs:domain {_class_iri(base, item['source_code'])} ;",
            f"  rdfs:range {_class_iri(base, item['target_code'])} ;",
        ]
        for characteristic in characteristics.get(item["code"], ()):
            statements.append(f"  a {characteristic} ;")
        statements[-1] = statements[-1].rstrip(" ;") + " ."
        lines += [*statements, ""]

    for axiom in detail["axioms"]:
        if axiom["kind"] == DISJOINT_TYPES:
            lines += [
                f"{_class_iri(base, axiom['subject'])} owl:disjointWith {_class_iri(base, axiom['object'])} .",
                "",
            ]

    return "\n".join(lines).rstrip() + "\n"


def _relation_characteristics(axioms: list[dict[str, Any]]) -> dict[str, tuple[str, ...]]:
    """Axiom kinds that are OWL property characteristics.

    These three have exact OWL counterparts, so emitting them loses nothing. The other
    kinds are attribute-level and appear in the SHACL shapes instead -- OWL has no
    vocabulary for "these two attributes are mutually exclusive" that does not require
    reasoning to interpret.
    """
    mapping = {
        IRREFLEXIVE_RELATION: "owl:IrreflexiveProperty",
        ASYMMETRIC_RELATION: "owl:AsymmetricProperty",
        FUNCTIONAL_RELATION: "owl:FunctionalProperty",
    }
    result: dict[str, list[str]] = {}
    for axiom in axioms:
        term = mapping.get(axiom["kind"])
        if term:
            result.setdefault(axiom["subject"], []).append(term)
    return {code: tuple(sorted(set(terms))) for code, terms in result.items()}


def export_shacl_shapes(detail: dict[str, Any]) -> str:
    """SHACL node shapes derived from the same declarations the release gates read.

    Generated rather than authored. A hand-written shape file would drift from the gates
    it mirrors, and a drifted shape states a constraint the platform does not enforce --
    a consumer would validate against it and trust the result.
    """
    ontology = detail["ontology"]
    base = _base(ontology)
    lines = [*_PREFIXES, f"@prefix bp: <{base}> .", ""]

    attributes_by_object: dict[str, list[dict[str, Any]]] = {}
    for item in detail["attributes"]:
        attributes_by_object.setdefault(item["object_code"], []).append(item)

    relations_by_source: dict[str, list[dict[str, Any]]] = {}
    for item in detail["relations"]:
        relations_by_source.setdefault(item["source_code"], []).append(item)

    required_by_axiom = {axiom["subject"] for axiom in detail["axioms"] if axiom["kind"] == REQUIRED_ATTRIBUTE}
    functional_relations = {axiom["subject"] for axiom in detail["axioms"] if axiom["kind"] == FUNCTIONAL_RELATION}
    disjoint_attributes = [
        (axiom["subject"], axiom["object"]) for axiom in detail["axioms"] if axiom["kind"] == DISJOINT_ATTRIBUTES
    ]

    for item in detail["objects"]:
        code = item["code"]
        blocks = [
            _shape_iri(base, code) + " a sh:NodeShape ;",
            f"  sh:targetClass {_class_iri(base, code)} ;",
            f"  rdfs:label {_literal(item['name'])} ;",
        ]

        for attribute in attributes_by_object.get(code, []):
            reference = f"{code}.{attribute['code']}"
            # Required from either source: the scanned schema's NOT NULL, or an explicit
            # axiom. Both mean "a record without this is invalid", so both produce the
            # same constraint.
            required = bool(attribute["required"]) or reference in required_by_axiom
            constraint = [
                "  sh:property [",
                f"    sh:path {_property_iri(base, code, attribute['code'])} ;",
                f"    sh:datatype {_xsd_for(attribute['data_type'])} ;",
                f"    sh:name {_literal(attribute['name'])} ;",
            ]
            if required:
                constraint.append("    sh:minCount 1 ;")
            constraint.append("  ] ;")
            blocks += constraint

        for relation in relations_by_source.get(code, []):
            constraint = [
                "  sh:property [",
                f"    sh:path {_relation_iri(base, relation['code'])} ;",
                f"    sh:class {_class_iri(base, relation['target_code'])} ;",
                f"    sh:name {_literal(relation['name'])} ;",
            ]
            cardinality = detail["cardinality"].get(relation["code"], "")
            if relation["code"] in functional_relations or (cardinality and cardinality not in _MULTI_VALUED):
                # At most one target. Derived from the declared cardinality so the shape
                # cannot contradict what `relations.py` classified.
                constraint.append("    sh:maxCount 1 ;")
            constraint.append("  ] ;")
            blocks += constraint

        for left, right in disjoint_attributes:
            left_object, _, left_code = left.partition(".")
            if left_object != code:
                continue
            _, _, right_code = right.partition(".")
            # Mutual exclusion as SHACL sees it: if this path has a value, the other must
            # not. Expressed on one side only -- the pair is symmetric, and emitting both
            # directions would report every violation twice.
            blocks += [
                "  sh:property [",
                f"    sh:path {_property_iri(base, code, left_code)} ;",
                "    sh:not [",
                f"      sh:path {_property_iri(base, code, right_code)} ;",
                "      sh:minCount 1 ;",
                "    ] ;",
                f"    sh:message {_literal(f'{left} 与 {right} 互斥，不能同时有值')} ;",
                "  ] ;",
            ]

        blocks[-1] = blocks[-1].rstrip(" ;") + " ."
        lines += [*blocks, ""]

    return "\n".join(lines).rstrip() + "\n"
