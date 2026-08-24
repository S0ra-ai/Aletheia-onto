"""OWL/RDFS/SHACL export: the same ontology in vocabulary other tools can act on.

The platform already emitted JSON-LD and Turtle, and that was not interoperability. The
syntax was standard; every *term* was minted locally. A consumer that knows OWL knows
what `rdfs:domain` means and can act on it; it cannot know that `ont:sourceObject` means
the same thing. GB/T 48000.3—2026 recommends OWL/RDF precisely so that this gap does not
exist.

Every assertion here **parses** the output with a real RDF library and queries the
resulting graph. That is not thoroughness for its own sake: the previous Turtle export
was checked by substring matching, and it shipped unparseable by any RDF tool for as long
as it existed, because an invalid document contains a substring just as well as a valid
one. Text matching cannot distinguish "emits the right terms" from "emits the right terms
in a document nothing can read".
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from ontology_platform.axioms import AxiomSpec, declare_axiom, init_axiom_schema
from ontology_platform.database import connect, initialize_platform_db
from ontology_platform.metadata import register_data_source, scan_data_source
from ontology_platform.ontology import generate_ontology_draft
from ontology_platform.standard_vocabulary import (
    STANDARD_EXPORT_FORMATS,
    XSD_BY_DATA_TYPE,
    export_standard_asset,
)
from ontology_platform.type_hierarchy import declare_subtype

rdflib = pytest.importorskip("rdflib", reason="需要 rdflib 才能验证导出的 RDF 语法")

OWL = rdflib.Namespace("http://www.w3.org/2002/07/owl#")
RDFS = rdflib.Namespace("http://www.w3.org/2000/01/rdf-schema#")
SH = rdflib.Namespace("http://www.w3.org/ns/shacl#")


@pytest.fixture
def modelled(tmp_path: Path):
    source = tmp_path / "business.sqlite3"
    connection = sqlite3.connect(source)
    connection.executescript(
        """
        create table customers (
            id integer primary key,
            name text not null,
            credit_limit numeric
        );
        create table person_customers (
            id integer primary key,
            name text not null
        );
        create table contracts (
            id integer primary key,
            customer_id integer not null references customers(id),
            amount numeric not null,
            memo text
        );
        insert into customers values (1, '甲公司', 500);
        insert into person_customers values (1, '张三');
        insert into contracts values (1, 1, 100, null);
        """
    )
    connection.commit()
    connection.close()

    platform_db = tmp_path / "platform.sqlite3"
    initialize_platform_db(platform_db)
    with connect(platform_db) as conn:
        init_axiom_schema(conn)
    data_source = register_data_source(platform_db, "业务系统", "sqlite", str(source), domain="合同管理")
    scan_data_source(platform_db, data_source.id)
    ontology_id = generate_ontology_draft(platform_db, data_source.id)["ontology"]["id"]

    with connect(platform_db) as conn:
        codes = {
            row["table_name"]: row["code"]
            for row in conn.execute(
                """
                select bo.code, st.table_name from business_object bo
                join source_table st on st.id = bo.source_table_id
                where bo.ontology_id = ?
                """,
                (ontology_id,),
            ).fetchall()
        }
        relations = [
            row["code"]
            for row in conn.execute(
                "select code from business_relation where ontology_id = ? order by code",
                (ontology_id,),
            ).fetchall()
        ]
    return {
        "platform_db": platform_db,
        "ontology_id": ontology_id,
        "codes": codes,
        "relations": relations,
    }


def _graph(modelled, export_format: str):
    asset = export_standard_asset(modelled["platform_db"], modelled["ontology_id"], export_format)
    graph = rdflib.Graph()
    graph.parse(data=asset["content"], format="turtle")
    return graph, asset


# -- The output is valid RDF, not merely text containing the right words --


@pytest.mark.parametrize("export_format", STANDARD_EXPORT_FORMATS)
def test_every_standard_export_parses_as_turtle(modelled, export_format) -> None:
    """The check that the old substring assertions could not make.

    A prefixed name's local part cannot contain `/` in Turtle, which is how the earlier
    export emitted `bp:object/contract` and became unreadable. Parsing is the only way to
    know.
    """
    graph, asset = _graph(modelled, export_format)
    assert len(graph) > 0, f"{export_format} 解析成功但没有三元组"
    assert asset["mediaType"] == "text/turtle"


def test_an_unknown_format_is_refused(modelled) -> None:
    with pytest.raises(ValueError, match="仅支持"):
        export_standard_asset(modelled["platform_db"], modelled["ontology_id"], "rdfxml")


def test_a_missing_ontology_is_refused(modelled) -> None:
    with pytest.raises(ValueError, match="本体不存在"):
        export_standard_asset(modelled["platform_db"], 999, "owl")


# -- OWL: objects are classes, attributes and relations are typed properties --


def test_business_objects_become_owl_classes(modelled) -> None:
    graph, _ = _graph(modelled, "owl")
    classes = set(graph.subjects(rdflib.RDF.type, OWL.Class))
    assert len(classes) == len(modelled["codes"]), f"应为每个业务对象产出一个 owl:Class，实际 {len(classes)}"
    for subject in classes:
        assert graph.value(subject, RDFS.label) is not None, f"{subject} 缺少 rdfs:label"


def test_attributes_become_datatype_properties_with_domain_and_range(modelled) -> None:
    """`rdfs:range` is what makes the datatype usable rather than merely recorded."""
    graph, _ = _graph(modelled, "owl")
    properties = list(graph.subjects(rdflib.RDF.type, OWL.DatatypeProperty))
    assert properties, "未产出任何 owl:DatatypeProperty"
    for subject in properties:
        assert graph.value(subject, RDFS.domain) is not None, f"{subject} 缺少 rdfs:domain"
        range_value = graph.value(subject, RDFS.range)
        assert range_value is not None, f"{subject} 缺少 rdfs:range"
        assert str(range_value).startswith("http://www.w3.org/2001/XMLSchema#"), range_value


def test_relations_become_object_properties_with_domain_and_range(modelled) -> None:
    """The gap the article calls out as commonly missing, and which this model always had.

    `source_object_id` and `target_object_id` were domain and range all along -- foreign
    keyed to `business_object`, so they could not even name a class that does not exist.
    What was missing was saying so in a term a reasoner recognises.
    """
    graph, _ = _graph(modelled, "owl")
    properties = list(graph.subjects(rdflib.RDF.type, OWL.ObjectProperty))
    assert properties, "未产出任何 owl:ObjectProperty"

    classes = set(graph.subjects(rdflib.RDF.type, OWL.Class))
    for subject in properties:
        domain = graph.value(subject, RDFS.domain)
        range_value = graph.value(subject, RDFS.range)
        assert domain in classes, f"{subject} 的 rdfs:domain 不是本体内的类: {domain}"
        assert range_value in classes, f"{subject} 的 rdfs:range 不是本体内的类: {range_value}"


def test_a_declared_subtype_becomes_subclassof(modelled) -> None:
    """Declared, never inferred. The edge exists because someone wrote it down."""
    platform_db, ontology_id = modelled["platform_db"], modelled["ontology_id"]
    parent = modelled["codes"]["customers"]
    child = modelled["codes"]["person_customers"]

    graph, _ = _graph(modelled, "owl")
    assert not list(graph.subject_objects(RDFS.subClassOf)), "未声明层级时不应出现 rdfs:subClassOf"

    declare_subtype(platform_db, ontology_id, child, parent, actor="tester")

    graph, _ = _graph(modelled, "owl")
    edges = list(graph.subject_objects(RDFS.subClassOf))
    assert len(edges) == 1
    subject, parent_iri = edges[0]
    assert str(subject).endswith(child)
    assert str(parent_iri).endswith(parent)


def test_axioms_become_owl_property_characteristics(modelled) -> None:
    """Three axiom kinds have exact OWL counterparts, so emitting them loses nothing."""
    platform_db, ontology_id = modelled["platform_db"], modelled["ontology_id"]
    relation_code = modelled["relations"][0]
    declare_axiom(
        platform_db,
        ontology_id,
        AxiomSpec(code="ax_irr", kind="irreflexive_relation", subject=relation_code),
    )

    graph, _ = _graph(modelled, "owl")
    irreflexive = set(graph.subjects(rdflib.RDF.type, OWL.IrreflexiveProperty))
    assert any(str(subject).endswith(relation_code) for subject in irreflexive), (
        f"不可自反公理未映射为 owl:IrreflexiveProperty: {irreflexive}"
    )


def test_a_disjointness_axiom_becomes_owl_disjointwith(modelled) -> None:
    platform_db, ontology_id = modelled["platform_db"], modelled["ontology_id"]
    left = modelled["codes"]["customers"]
    right = modelled["codes"]["contracts"]
    declare_axiom(
        platform_db,
        ontology_id,
        AxiomSpec(code="ax_dis", kind="disjoint_types", subject=left, object=right),
    )

    graph, _ = _graph(modelled, "owl")
    pairs = list(graph.subject_objects(OWL.disjointWith))
    assert len(pairs) == 1
    assert {str(pairs[0][0]).rsplit("/", 1)[-1], str(pairs[0][1]).rsplit("/", 1)[-1]} == {left, right}


def test_no_reasoning_only_constructs_are_emitted(modelled) -> None:
    """ADR-0005 refuses DL reasoning, so the export must not imply it is available.

    Emitting `owl:equivalentClass` or a property chain would invite a consumer to run a
    reasoner and act on conclusions this platform cannot trace to a declaration -- and
    traceability is the product.
    """
    graph, _ = _graph(modelled, "owl")
    forbidden = [
        OWL.equivalentClass,
        OWL.propertyChainAxiom,
        OWL.someValuesFrom,
        OWL.hasValue,
        OWL.unionOf,
        OWL.complementOf,
    ]
    present = [term for term in forbidden if (None, term, None) in graph or (None, None, term) in graph]
    assert not present, f"导出了需要 DL 推理才能解释的构件: {present}"


# -- SHACL: shapes derived from the same declarations the gates read --


def test_each_object_gets_a_node_shape_targeting_its_class(modelled) -> None:
    owl_graph, _ = _graph(modelled, "owl")
    shape_graph, _ = _graph(modelled, "shacl")

    classes = set(owl_graph.subjects(rdflib.RDF.type, OWL.Class))
    targets = set(shape_graph.objects(None, SH.targetClass))
    assert targets == classes, f"形状目标与类不一致；仅形状有: {targets - classes}；仅类有: {classes - targets}"


def test_a_not_null_column_becomes_mincount_one(modelled) -> None:
    """The constraint comes from the scanned schema, so it cannot contradict the source.

    `contracts.amount` is NOT NULL and `contracts.memo` is nullable, so exactly one of
    the two carries `sh:minCount`.
    """
    graph, _ = _graph(modelled, "shacl")
    required, optional = None, None
    for shape in graph.objects(None, SH.property):
        path = str(graph.value(shape, SH.path) or "")
        if path.endswith(".amount"):
            required = graph.value(shape, SH.minCount)
        if path.endswith(".memo"):
            optional = graph.value(shape, SH.minCount)
    assert required is not None and int(required) == 1, "NOT NULL 列应产出 sh:minCount 1"
    assert optional is None, "可空列不应产出 sh:minCount"


def test_a_required_attribute_axiom_also_produces_mincount(modelled) -> None:
    """Two sources, one constraint. A NOT NULL column and an explicit axiom both mean
    "a record without this is invalid", so both must produce the same shape."""
    platform_db, ontology_id = modelled["platform_db"], modelled["ontology_id"]
    contracts = modelled["codes"]["contracts"]

    graph, _ = _graph(modelled, "shacl")
    before = [
        shape
        for shape in graph.objects(None, SH.property)
        if str(graph.value(shape, SH.path) or "").endswith(".memo") and graph.value(shape, SH.minCount) is not None
    ]
    assert not before

    # `memo` is nullable, so the axiom cannot be declared through the normal path -- it
    # would be refused. Written directly to prove the *generator* honours an axiom that
    # a legitimately-required attribute would carry.
    with connect(platform_db) as conn:
        conn.execute(
            "insert into ontology_axiom (ontology_id, code, kind, subject, object, note)"
            " values (?, 'ax_memo', 'required_attribute', ?, '', '')",
            (ontology_id, f"{contracts}.memo"),
        )

    graph, _ = _graph(modelled, "shacl")
    after = [
        shape
        for shape in graph.objects(None, SH.property)
        if str(graph.value(shape, SH.path) or "").endswith(".memo") and graph.value(shape, SH.minCount) is not None
    ]
    assert after, "required_attribute 公理未映射为 sh:minCount"


def test_a_many_to_one_relation_becomes_maxcount_one(modelled) -> None:
    """Derived from the cardinality `relations.py` classified, so the shape cannot
    contradict the platform's own reading of the schema."""
    graph, _ = _graph(modelled, "shacl")
    relation_shapes = [
        shape for shape in graph.objects(None, SH.property) if graph.value(shape, SH["class"]) is not None
    ]
    assert relation_shapes, "未为关系产出形状"
    assert any(graph.value(shape, SH.maxCount) is not None for shape in relation_shapes), (
        "多对一关系应产出 sh:maxCount 1"
    )


def test_mutually_exclusive_attributes_become_a_shacl_not_constraint(modelled) -> None:
    platform_db, ontology_id = modelled["platform_db"], modelled["ontology_id"]
    customers = modelled["codes"]["customers"]
    declare_axiom(
        platform_db,
        ontology_id,
        AxiomSpec(
            code="ax_excl",
            kind="disjoint_attributes",
            subject=f"{customers}.credit_limit",
            object=f"{customers}.name",
        ),
    )
    graph, _ = _graph(modelled, "shacl")
    assert list(graph.objects(None, SH["not"])), "互斥属性公理未映射为 sh:not"
    messages = [str(value) for value in graph.objects(None, SH.message)]
    assert any("互斥" in message for message in messages), messages


# -- Datatype mapping --


def test_an_unmapped_data_type_falls_back_to_string_rather_than_failing(modelled) -> None:
    """Losing precision is recoverable; losing the attribute is not.

    A consumer can read a string. A consumer cannot read a triple that was never emitted
    because an unrecognised type raised.
    """
    platform_db, ontology_id = modelled["platform_db"], modelled["ontology_id"]
    with connect(platform_db) as conn:
        object_id = conn.execute(
            "select id from business_object where ontology_id = ? and code = ?",
            (ontology_id, modelled["codes"]["customers"]),
        ).fetchone()["id"]
        conn.execute(
            "insert into business_attribute (object_id, code, name, data_type, required)"
            " values (?, 'exotic', '奇异字段', 'geography_point', 0)",
            (object_id,),
        )

    graph, _ = _graph(modelled, "owl")
    exotic = [
        subject for subject in graph.subjects(rdflib.RDF.type, OWL.DatatypeProperty) if str(subject).endswith(".exotic")
    ]
    assert exotic, "未知数据类型的属性被丢弃了"
    assert str(graph.value(exotic[0], RDFS.range)).endswith("#string")


def test_the_datatype_table_covers_the_types_the_scanner_produces() -> None:
    """An unmapped common type silently degrades every export that contains it."""
    for data_type in ("string", "integer", "numeric", "boolean", "date", "datetime"):
        assert data_type in XSD_BY_DATA_TYPE, f"{data_type} 未映射到 XSD 类型"


# -- IRI stability --


def test_deriving_a_new_version_keeps_the_namespace_and_changes_only_the_version(modelled) -> None:
    """An exported IRI is what an external consumer stores. It must move only when the
    meaning does.

    The IRI was keyed on the ontology row id, and `derive` allocates a new row while
    carrying the name forward -- so deriving 0.2.0 moved every class to a different
    namespace even though nothing about the concept changed. Nothing failed loudly: a
    consumer's stored reference simply kept resolving the superseded version forever.

    The version *does* stay in the path. Two versions can disagree about what a class
    means, so a consumer pinned to 0.1.0 must keep resolving 0.1.0 -- collapsing the
    version would silently change the meaning of an existing reference.
    """
    from ontology_platform.governance import derive_ontology_version, publish_ontology

    platform_db, ontology_id = modelled["platform_db"], modelled["ontology_id"]

    def class_iris(target_id: int) -> list[str]:
        graph = rdflib.Graph()
        graph.parse(
            data=export_standard_asset(platform_db, target_id, "owl")["content"],
            format="turtle",
        )
        return sorted(str(subject) for subject in graph.subjects(rdflib.RDF.type, OWL.Class))

    before = class_iris(ontology_id)

    with connect(platform_db) as conn:
        conn.execute(
            "update semantic_mapping set status = 'confirmed' where ontology_id = ?",
            (ontology_id,),
        )
    publish_ontology(platform_db, ontology_id, "tester")
    derived = derive_ontology_version(platform_db, ontology_id, "0.2.0", "tester")
    derived_id = derived.get("id") or derived["ontology"]["id"]

    after = class_iris(derived_id)
    assert len(before) == len(after)

    def namespace(iri: str) -> str:
        return iri.rsplit("/v/", 1)[0]

    assert namespace(before[0]) == namespace(after[0]), (
        f"派生新版本改变了命名空间：{namespace(before[0])} -> {namespace(after[0])}"
    )
    assert "/v/0.1.0/" in before[0] and "/v/0.2.0/" in after[0], (before[0], after[0])


def test_a_chinese_ontology_name_survives_in_the_iri(tmp_path: Path) -> None:
    """Two Chinese-named ontologies must not share one namespace.

    The slug helper replaced every non-ASCII run with `-` and fell back to `item`, so
    「合同管理本体」and「客户管理本体」produced identical IRIs. Merging their exported
    graphs would then conflate two unrelated models, and nothing would report it.
    """
    from ontology_platform.ontology import ontology_slug

    contract = ontology_slug("合同管理本体")
    customer = ontology_slug("客户管理本体")
    assert contract != customer, "不同中文本体名产生了相同的 IRI 片段"
    assert contract and contract != "item"
    # A slash inside a name must not introduce a path segment, or it would change the
    # shape of every IRI derived from that ontology.
    assert "/" not in ontology_slug("A/B 本体")


def test_both_exports_describe_the_same_resources(modelled) -> None:
    """One ontology, one IRI scheme.

    The platform-vocabulary export and the standard one must agree on the namespace, or a
    consumer merging them gets two disconnected graphs describing what is actually the
    same model.
    """
    from ontology_platform.ontology import export_ontology_asset

    platform_db, ontology_id = modelled["platform_db"], modelled["ontology_id"]

    platform_graph = rdflib.Graph()
    platform_graph.parse(
        data=export_ontology_asset(platform_db, ontology_id, "turtle")["content"],
        format="turtle",
    )
    standard_graph = rdflib.Graph()
    standard_graph.parse(
        data=export_standard_asset(platform_db, ontology_id, "owl")["content"],
        format="turtle",
    )

    def namespaces(graph) -> set[str]:
        return {
            str(subject).rsplit("/v/", 1)[0]
            for subject in graph.subjects()
            if isinstance(subject, rdflib.URIRef) and "/v/" in str(subject)
        }

    assert namespaces(platform_graph) == namespaces(standard_graph), (
        f"两套导出的命名空间不一致：{namespaces(platform_graph)} / {namespaces(standard_graph)}"
    )


# -- Reachable from the CLI --


@pytest.mark.parametrize("export_format", STANDARD_EXPORT_FORMATS)
def test_the_cli_writes_a_parseable_file(modelled, tmp_path, capsys, export_format) -> None:
    """The consumer of a standard export is usually a pipeline.

    Hand the file to a SHACL validator, load it into a triple store, diff it against the
    previous version -- none of which should require a running server and a token to
    obtain a file.
    """
    from ontology_platform.cli import main

    target = tmp_path / f"asset.{export_format}.ttl"
    exit_code = main(
        [
            "--platform-db",
            str(modelled["platform_db"]),
            "export",
            str(modelled["ontology_id"]),
            "--format",
            export_format,
            "--output",
            str(target),
        ]
    )
    capsys.readouterr()
    assert exit_code == 0

    graph = rdflib.Graph()
    graph.parse(target, format="turtle")
    assert len(graph) > 0


def test_the_cli_reports_an_unknown_format_without_a_traceback(modelled, capsys) -> None:
    """A traceback tells the caller the tool broke; a message tells them what to fix."""
    from ontology_platform.cli import main

    exit_code = main(
        [
            "--platform-db",
            str(modelled["platform_db"]),
            "export",
            str(modelled["ontology_id"]),
            "--format",
            "jsonld",
        ]
    )
    assert exit_code == 0
    assert "Traceback" not in capsys.readouterr().out
