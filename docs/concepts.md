# Core concepts

> Ontology structure, the mapping to legacy systems, and the verdict trail.

Back to [English README](../README.md) · [中文 README](../README.zh-CN.md)

Terms in this space are used loosely, so each entry states what the platform means
by it and, where it matters, **what it deliberately is not**.

## Ontology structure

**Ontology** — a versioned formal expression of business objects, attributes,
relations, events, states and rules. Generated as a draft from metadata scanning,
published as an immutable version after human review. A published ontology cannot be
edited, only superseded by a new version.
_Not_: a knowledge graph, a data dictionary.

**Metamodel** — the model that describes an ontology's own structure: which objects,
relation types and lifecycle information an ontology may contain. An industry
ontology is an instance of the metamodel.

**BusinessObject** — something the business identifies and talks about: a customer, a
contract, a device, a work order. It is **not a table** — an instance resolver decides
which rows constitute its instances (ADR-0011).
_Not_: an entity, a row, a DTO.

**InstanceKey** — the column set identifying one instance. Composite keys are
supported: junction tables, versioned records and partitioned history tables are
routine in legacy schemas (ADR-0008).

**InstanceResolver** — the replaceable strategy for "which rows are this object's
instances". Four built in: single table, master/detail join, discriminated partition,
custom SQL. Third-party resolvers can be registered (ADR-0011).

**Attribute** — a named feature of an object, from one of two sources:

- **mapped**: mirrors a source column
- **derived**: computed from an expression, e.g. `margin = (revenue - cost) / revenue`.
  Defined once and shared by every rule, so one definition cannot drift across five
  copies (ADR-0013)

**Unit / Dimension** — an attribute may declare its unit. Comparison converts within a
dimension and refuses across dimensions. Not a convenience: mixing 万元 and 元 makes
`amount 500 > limit 1000000` report "within limit" — a wrong verdict from correct
data (ADR-0013).

**Relation** — a link between two objects, carrying **cardinality** (one-to-one,
many-to-one, one-to-many, many-to-many) and **strength**:

| Kind | Meaning | Inferred from |
|---|---|---|
| composition | identity-dependent; the child is meaningless without the parent | FK inside the child's primary key |
| aggregation | parent mandatory, child identity independent | FK NOT NULL, outside the key |
| association | parent optional | FK nullable |

Classification uses declared structure only, never data distribution — a relation
inferred from a sample changes meaning when the data changes, and a verdict citing it
would be unreproducible (ADR-0012).

**TypeHierarchy** — declares that "company customer is a subtype of customer". A
subtype inherits its ancestors' rules, aggregates and derived attributes. This is a
deterministic walk up a declared chain, **not DL subsumption**: nothing is inferred
about who is a subtype of whom (ADR-0014).

**Override** — a subtype may declare that one of its rules supersedes an ancestor's,
for a legitimate business exception. Declared explicitly rather than inferred from a
name collision: a collision is ambiguous, and inference would silently disable one
team's control. Weakening is allowed; weakening *invisibly* is not (ADR-0014).

**Aggregate** — a named, reviewable group-level value such as "total of all the
customer's active contracts", so a rule can say "total must not exceed the credit
limit". Stored as data rather than as an inline join inside a rule, because the answer
to "why" has to be a definition an operator can read (ADR-0012).

**State / workflow** — where an instance sits in its lifecycle and which transitions
are permitted. Transition guards evaluate in the rule sandbox and block the
transition when they cannot be evaluated.

**Event** — something that happened to an instance, append-only, with a payload, a
source timestamp and an actor. Events **trigger nothing**: an event that could fire
automation would make replaying history re-execute business actions (ADR-0014).
_Not_: a message, a log line, an analytics hit.

**Timeline** — an instance's full event sequence, ordered by source time. Workflow
transitions are mirrored into it, so an instance has one timeline rather than one per
subsystem.

**IndustryBlueprint** — one industry's object naming, attribute naming and rule
templates. The platform ships **no built-in domain vocabulary**; vocabulary is
contributed by blueprints at runtime, so a new domain is added by importing a
blueprint rather than by changing platform code (ADR-0003).

## Mapping onto the legacy system

**Onboarding** — registering a legacy system's tables, APIs, actions and capability
boundary. The platform **reads metadata; it does not move data**.

**SemanticMapping** — the traceable correspondence from legacy tables and columns to
ontology concepts. Every mapping carries a `pending`/`confirmed` status and a
reviewer.
_Not_: an ETL mapping.

**ValueMapping** — legacy code to semantic state, e.g. `status='A'` ↔ effective. Both
forms then evaluate identically in a rule, so nobody has to memorise magic values
(ADR-0008).

**Drift** — the difference between the live source schema and the scanned metadata.
The release gate checks for it, because assessing on a drifted mapping means
assessing on unverified data.

## Assessment and provenance

**BusinessRule** — an explainable condition evaluated in an AST-allowlist sandbox.
The expression is checked for executability at write time; an unexecutable rule is
refused.
_Not_: an algorithm, a model, a scripting engine.

**fail-closed** — an expression that cannot be evaluated (renamed column, type
mismatch, syntax error) is treated as **not passed**, with the reason attached. The
opposite would let structural drift silently disable a blocking rule while automation
keeps running (ADR-0002).

**Assessment** — the verdict for one instance: status, blocking reasons, recommended
action. One assessment expands the type hierarchy, computes aggregates and derived
attributes, applies units, and evaluates every applicable rule.

**Decision provenance** — one assessment writes four layers: per-rule
`inference_result`, evidence chain `explanation_trace`, decision-level
`decision_record`, operation-level `audit_log`.

**Explanation** — a readable account of one instance: attribute values, source table,
ancestor types, recent event timeline. It answers "what is it, and how did it get
this way".

**ReleaseGate** — release-readiness is assessed before publishing; a blocking finding
refuses the release. A `force` override is audited together with the number of gates
it bypassed.

**Escape hatch** — where structural expressiveness runs out, users drop down to a
custom implementation instead of waiting for a feature: custom SQL as an object
source, custom rule functions, derived expressions, write-back executor SPI, data
source adapter SPI. Generality comes from **structural expressiveness plus escape
hatches**, not from reasoning power (ADR-0005).
