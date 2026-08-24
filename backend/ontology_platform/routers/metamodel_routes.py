"""Metamodel expressiveness routes: what a business object can say about itself.

These are the declarations that make `business_object` more than a mirror of one table
-- instance resolvers, cross-object aggregates, derived attributes and units, subtype
hierarchies, business events, attribute-level temporal versions, and cross-source
identity links. They are grouped together because they share one property: each is a
*declaration* the platform stores and can explain, never an inference.

That is the whole basis of the generality ceiling (ADR-0005). A subtype relationship is
declared, not induced from data; a cross-source match is declared as "CRM.tax_id ↔
ERP.taxpayer_no", not decided by a similarity threshold. A verdict that changed because
a threshold moved could not answer "why is this the same instance", and the answer is
the product.

Stability: internal. Routers are an implementation detail of the HTTP layer.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..aggregation import AggregateSpec, AggregationError, define_aggregate, list_aggregates
from ..auth import Principal
from ..axioms import (
    AxiomError,
    AxiomSpec,
    check_axioms,
    declare_axiom,
    describe_axiom_kinds,
    list_axioms,
    remove_axiom,
)
from ..derived_attributes import (
    DerivedAttributeError,
    DerivedSpec,
    UnitError,
    define_derived_attribute,
    known_units,
    list_derived_attributes,
    set_attribute_unit,
)
from ..entity_resolution import (
    CrossSourceLink,
    EntityResolutionError,
    MatchKey,
    declare_cross_source_link,
    describe_cross_source,
)
from ..events import (
    MAX_EVENT_HISTORY,
    EventError,
    EventType,
    declare_event_type,
    instance_timeline,
    list_event_types,
    record_event,
)
from ..http_runtime import current_principal, platform_db
from ..instance_resolver import (
    ResolverError,
    ResolverSpec,
    configure_object_resolver,
    get_object_resolver,
    supported_resolver_kinds,
)
from ..temporal import TemporalError, instance_history, record_attribute_version
from ..type_hierarchy import HierarchyError, declare_subtype, describe_hierarchy

router = APIRouter()


# -- Request models --


class AxiomDeclare(BaseModel):
    code: str
    kind: str
    subject: str
    object: str = ""
    note: str = ""


class ResolverConfigure(BaseModel):
    kind: str
    table: str = ""
    primaryKey: str = "id"
    joins: list[dict[str, str]] = Field(default_factory=list)
    discriminatorColumn: str = ""
    discriminatorValue: str = ""
    query: str = ""
    idColumn: str = ""


class AggregateDefine(BaseModel):
    name: str
    function: str
    targetTable: str
    targetColumn: str
    groupColumn: str
    valueColumn: str = ""
    excludeSelf: bool = False
    selfColumn: str = ""
    filterColumn: str = ""
    filterValue: str = ""
    description: str = ""


class DerivedAttributeDefine(BaseModel):
    code: str
    name: str
    expression: str
    unit: str = ""
    description: str = ""


class AttributeUnitDeclare(BaseModel):
    unit: str = ""


class EventTypeDeclare(BaseModel):
    code: str
    name: str
    category: str = "interaction"
    payloadFields: list[str] = Field(default_factory=list)
    description: str = ""


class EventRecord(BaseModel):
    eventCode: str
    payload: dict[str, object] = Field(default_factory=dict)
    occurredAt: str = ""
    correlationId: str = ""


class SubtypeDeclare(BaseModel):
    parentObjectCode: str = ""


class AttributeVersionRecord(BaseModel):
    attributeCode: str
    value: object = None
    validFrom: str = ""
    source: str = ""


class MatchKeyDeclare(BaseModel):
    primaryColumn: str
    secondaryColumn: str
    normalize: bool = True


class CrossSourceLinkDeclare(BaseModel):
    name: str
    secondaryDataSourceId: int
    secondaryTable: str
    matchKeys: list[MatchKeyDeclare] = Field(default_factory=list)
    prefix: str = ""
    mergeStrategy: str = "conflict"
    requireUnique: bool = True
    description: str = ""


@router.get("/ontologies/{ontology_id}/objects/{object_code}/resolver")
def object_resolver(ontology_id: int, object_code: str) -> dict[str, object]:
    """The instance resolver in effect for a business object."""
    try:
        return get_object_resolver(platform_db(), ontology_id, object_code)
    except ResolverError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.put("/ontologies/{ontology_id}/objects/{object_code}/resolver")
def set_object_resolver(
    ontology_id: int,
    object_code: str,
    payload: ResolverConfigure,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    """Attach a resolver so an object is no longer limited to one table.

    The spec is validated before storage, so an invalid configuration fails here
    rather than later as a failed assessment.
    """
    spec = ResolverSpec(
        kind=payload.kind,
        table=payload.table,
        primary_key=payload.primaryKey,
        joins=payload.joins,
        discriminator_column=payload.discriminatorColumn,
        discriminator_value=payload.discriminatorValue,
        query=payload.query,
        id_column=payload.idColumn,
    )
    try:
        return configure_object_resolver(platform_db(), ontology_id, object_code, spec, actor=principal.actor)
    except ResolverError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/resolvers")
def resolvers() -> dict[str, object]:
    return {"kinds": list(supported_resolver_kinds())}


@router.get("/ontologies/{ontology_id}/aggregates")
def ontology_aggregates(ontology_id: int, objectCode: str = "") -> dict[str, object]:
    """Cross-object aggregates available to rules."""
    return {"items": list_aggregates(platform_db(), ontology_id, objectCode)}


@router.put("/ontologies/{ontology_id}/objects/{object_code}/aggregates")
def define_object_aggregate(
    ontology_id: int,
    object_code: str,
    payload: AggregateDefine,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    """Declare an aggregate that rules for this object may reference by name.

    Validated before storage, so an invalid definition is refused here rather than
    surfacing later as a failed assessment.
    """
    spec = AggregateSpec(
        name=payload.name,
        function=payload.function,
        target_table=payload.targetTable,
        target_column=payload.targetColumn,
        group_column=payload.groupColumn,
        value_column=payload.valueColumn,
        exclude_self=payload.excludeSelf,
        self_column=payload.selfColumn,
        filter_column=payload.filterColumn,
        filter_value=payload.filterValue,
    )
    try:
        return define_aggregate(
            platform_db(),
            ontology_id,
            object_code,
            spec,
            description=payload.description,
            actor=principal.actor,
        )
    except AggregationError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/units")
def units() -> dict[str, object]:
    """Units available for attribute declarations, grouped by dimension.

    Comparison converts within a dimension and refuses across dimensions, so a
    caller needs the dimension to know which units are interchangeable.
    """
    return {
        "items": [
            {
                "code": unit.code,
                "name": unit.name,
                "dimension": unit.dimension,
                "toCanonical": unit.to_canonical,
            }
            for unit in known_units()
        ]
    }


@router.get("/ontologies/{ontology_id}/derived-attributes")
def ontology_derived_attributes(ontology_id: int, objectCode: str = "") -> dict[str, object]:
    return {"items": list_derived_attributes(platform_db(), ontology_id, objectCode)}


@router.put("/ontologies/{ontology_id}/objects/{object_code}/derived-attributes")
def define_object_derived_attribute(
    ontology_id: int,
    object_code: str,
    payload: DerivedAttributeDefine,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    """Declare a computed attribute that rules may reference by code.

    Validated through the rule sandbox before storage, so an unusable expression is
    refused here rather than surfacing later as a failed assessment.
    """
    try:
        return define_derived_attribute(
            platform_db(),
            ontology_id,
            object_code,
            DerivedSpec(
                code=payload.code,
                name=payload.name,
                expression=payload.expression,
                unit=payload.unit,
                description=payload.description,
            ),
            actor=principal.actor,
        )
    except (DerivedAttributeError, UnitError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.put("/ontologies/{ontology_id}/objects/{object_code}/attributes/{attribute_code}/unit")
def declare_attribute_unit(
    ontology_id: int,
    object_code: str,
    attribute_code: str,
    payload: AttributeUnitDeclare,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    """Declare the unit an attribute is measured in. An empty unit clears it."""
    try:
        return set_attribute_unit(
            platform_db(),
            ontology_id,
            object_code,
            attribute_code,
            payload.unit,
            actor=principal.actor,
        )
    except (DerivedAttributeError, UnitError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/ontologies/{ontology_id}/event-types")
def ontology_event_types(ontology_id: int, objectCode: str = "") -> dict[str, object]:
    return {"items": list_event_types(platform_db(), ontology_id, objectCode)}


@router.put("/ontologies/{ontology_id}/objects/{object_code}/event-types")
def declare_object_event_type(
    ontology_id: int,
    object_code: str,
    payload: EventTypeDeclare,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    """Declare a kind of event that can happen to instances of this object."""
    try:
        return declare_event_type(
            platform_db(),
            ontology_id,
            EventType(
                code=payload.code,
                name=payload.name,
                object_code=object_code,
                category=payload.category,
                payload_fields=list(payload.payloadFields),
                description=payload.description,
            ),
            actor=principal.actor,
        )
    except EventError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/ontologies/{ontology_id}/objects/{object_code}/instances/{instance_id}/events")
def append_instance_event(
    ontology_id: int,
    object_code: str,
    instance_id: str,
    payload: EventRecord,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    """Append one event to an instance's history.

    Recording does not trigger automation: an event that could fire side effects
    would make replaying history re-execute business actions.
    """
    try:
        return record_event(
            platform_db(),
            ontology_id,
            object_code,
            instance_id,
            payload.eventCode,
            payload=dict(payload.payload),
            actor=principal.actor,
            occurred_at=payload.occurredAt,
            correlation_id=payload.correlationId,
        )
    except EventError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/ontologies/{ontology_id}/objects/{object_code}/instances/{instance_id}/events")
def instance_events(
    ontology_id: int, object_code: str, instance_id: str, limit: int = MAX_EVENT_HISTORY
) -> dict[str, object]:
    """One instance's event history, newest first."""
    return instance_timeline(platform_db(), ontology_id, object_code, instance_id, limit)


@router.post("/ontologies/{ontology_id}/objects/{object_code}/instances/{instance_id}/versions")
def record_instance_attribute_version(
    ontology_id: int,
    object_code: str,
    instance_id: str,
    payload: AttributeVersionRecord,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    """Record a new value for one attribute, closing the version it supersedes.

    Append-only: nothing is overwritten, so a verdict recorded earlier still cites a value
    that exists.
    """
    try:
        return record_attribute_version(
            platform_db(),
            ontology_id,
            object_code,
            instance_id,
            payload.attributeCode,
            payload.value,
            valid_from=payload.validFrom or None,
            actor=principal.actor,
            source=payload.source,
        )
    except TemporalError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/ontologies/{ontology_id}/objects/{object_code}/instances/{instance_id}/versions")
def instance_attribute_history(
    ontology_id: int, object_code: str, instance_id: str, attributeCode: str = ""
) -> dict[str, object]:
    """One instance's attribute history, with the window it can actually answer for."""
    return instance_history(platform_db(), ontology_id, object_code, instance_id, attribute_code=attributeCode)


@router.get("/ontologies/{ontology_id}/cross-source-links")
def ontology_cross_source_links(ontology_id: int) -> dict[str, object]:
    """本体的跨源对应声明。

    一并返回说明文字，因为「匹配是声明的、不是推断的」是这套机制的前提，
    而一个只看到列表的调用方会以为平台在做模糊匹配。
    """
    return describe_cross_source(platform_db(), ontology_id)


@router.put("/ontologies/{ontology_id}/objects/{object_code}/cross-source-links")
def declare_object_cross_source_link(
    ontology_id: int,
    object_code: str,
    payload: CrossSourceLinkDeclare,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    """声明这个对象如何对应到另一个数据源的一张表。

    匹配键必须显式给出：跨源判定会把「这两行是同一实例」写进判定链，
    因此它必须是可审阅的声明，而不是相似度推断出来的结果。
    """
    try:
        return declare_cross_source_link(
            platform_db(),
            ontology_id,
            CrossSourceLink(
                name=payload.name,
                primary_object_code=object_code,
                secondary_data_source_id=payload.secondaryDataSourceId,
                secondary_table=payload.secondaryTable,
                match_keys=tuple(
                    MatchKey(
                        primary_column=key.primaryColumn,
                        secondary_column=key.secondaryColumn,
                        normalize=key.normalize,
                    )
                    for key in payload.matchKeys
                ),
                prefix=payload.prefix,
                merge_strategy=payload.mergeStrategy,
                require_unique=payload.requireUnique,
                description=payload.description,
            ),
            actor=principal.actor,
        )
    except EntityResolutionError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/ontologies/{ontology_id}/hierarchy")
def ontology_hierarchy(ontology_id: int) -> dict[str, object]:
    """The declared type hierarchy, with inherited rule counts and overrides."""
    return {"items": describe_hierarchy(platform_db(), ontology_id)}


@router.put("/ontologies/{ontology_id}/objects/{object_code}/parent")
def declare_object_subtype(
    ontology_id: int,
    object_code: str,
    payload: SubtypeDeclare,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    """Declare this object as a subtype of another, or clear the declaration.

    A subtype evaluates its ancestors' rules as well as its own, so this changes what
    every assessment of the object checks.
    """
    try:
        return declare_subtype(
            platform_db(),
            ontology_id,
            object_code,
            payload.parentObjectCode,
            actor=principal.actor,
        )
    except HierarchyError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


# -- Axioms --


@router.get("/axiom-kinds")
def axiom_kinds() -> dict[str, object]:
    """Every axiom kind, with the consequence of violating it.

    The consequence is the useful half. "Irreflexive" tells a modeller nothing; "a
    contract's two parties cannot be the same entity" tells them whether they need it.
    """
    return {"items": describe_axiom_kinds()}


@router.get("/ontologies/{ontology_id}/axioms")
def ontology_axioms(ontology_id: int) -> dict[str, object]:
    """Declared axioms, plus whether the model currently satisfies them.

    Both in one response because the list alone is misleading: an axiom that is declared
    but violated looks identical to one that holds, and the difference decides whether
    this ontology can be published.
    """
    report = check_axioms(platform_db(), ontology_id)
    return {
        "items": list_axioms(platform_db(), ontology_id),
        "satisfied": report["satisfied"],
        "violations": report["violations"],
        "note": "公理描述模型本身，不针对单个实例；违反公理会阻断发布。",
    }


@router.put("/ontologies/{ontology_id}/axioms")
def declare_ontology_axiom(
    ontology_id: int,
    payload: AxiomDeclare,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    """Declare an axiom, refused if the model already violates it.

    Refused rather than stored-and-reported, so the person who wrote the axiom sees the
    contradiction. Storing it would defer the failure to whoever next tries to publish.
    """
    try:
        return declare_axiom(
            platform_db(),
            ontology_id,
            AxiomSpec(
                code=payload.code,
                kind=payload.kind,
                subject=payload.subject,
                object=payload.object,
                note=payload.note,
            ),
        )
    except AxiomError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.delete("/ontologies/{ontology_id}/axioms/{code}")
def remove_ontology_axiom(
    ontology_id: int,
    code: str,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    try:
        return remove_axiom(platform_db(), ontology_id, code)
    except AxiomError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
