# Aletheia

> Surface the business semantics buried in your schema, and make every verdict verifiable.

[![CI](https://github.com/S0ra-ai/Aletheia-onto/actions/workflows/ci.yml/badge.svg)](https://github.com/S0ra-ai/Aletheia-onto/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)

English | [简体中文](README.md)

Aletheia (ἀλήθεια) is the ancient Greek word for truth and the name of its goddess.
Literally it means **"un-concealment" — making hidden things appear**. That is the
job here: business meaning is buried in table names, columns and foreign keys, and
Aletheia surfaces it as a governed domain ontology where every verdict can be checked.

Its mythological opposite is Pseudologoi, the spirit of lies — plausible speech that
cannot be verified. That is precisely the problem this project exists to solve.

---

## The problem

General RAG frameworks optimise for whether retrieved text *looks like* an answer.
Aletheia optimises for whether **an answer can withstand being questioned**.

For decisions about entitlements, amounts, compliance or approvals, an answer that
merely looks right is worthless, because nobody can sign off on it. Every verdict
here carries four things:

| | Source |
|---|---|
| **Verdict** — order A123 does not qualify for a refund | rule engine |
| **Governing rule** — `refund_window_check` | business rule definition |
| **Evidence** — delivered 2026-07-28, 24 days ago, past the 15-day window | structured query |
| **Decision record** — a persisted `decision_record`, auditable and attributable | decision trail |

The target is a support reply like:

> "Order A123 does not qualify for a refund: it was delivered more than 15 days ago
> (rule `refund_window_check`), per After-Sales Policy §3.2."

"more than 15 days" comes from a structured query, "does not qualify" from the rule
engine, "§3.2" from document retrieval.

**The first two work today. The third does not.** Document retrieval is not
implemented — see [Current limitations](#current-limitations). This project will not
use phrasing like "knowledge-base Q&A" to imply document RAG it does not have.

The difference from Dify / FastGPT / LangChain is not retrieval quality. It is
whether a conclusion can be interrogated.

## Screenshots

All captured from a running instance, not mockups. The data comes from the
bundled synthetic examples and contains no real business information.

### Workbench: what to do next, in one screen

![Workbench](docs/images/06-workbench.png)

Action items are ordered blockers-first and each one links to the screen that
resolves it. Every figure is a read-only projection of existing tables, so the
workbench cannot disagree with the screens it summarises.

### Semantic Q&A: verdict, governing rules, evidence

![Semantic Q&A with evidence](docs/images/01-semantic-qa-with-evidence.png)

Answers come back structured, not as a paragraph of prose: a bolded conclusion,
one bullet per rule carrying the rule code (`clause_content_required`) so it can
be looked up, and result distributions as tables. Answers render as Markdown, so
which rule fired, why, and what the verdict is stay distinguishable.

The agent role shown ("设备运维业务专家", equipment-maintenance expert) is derived
at runtime from the onboarded domain; no industry roles are built in.

### Data source onboarding and metadata scan

![Data source onboarding](docs/images/02-data-source-onboarding.png)

Tables, columns, types, foreign keys, enum candidates and a readiness score,
scanned from an existing database. The password segment of the connection string
is redacted.

### Domain ontology and business objects

![Ontology objects](docs/images/03-ontology-objects.png)

### Governance and the release gate

![Governance and release gate](docs/images/04-governance-release-gate.png)

Publishing is refused while blocking gates are open; a `force` override is
written to the audit log together with the count of failed gates.

### Roles and object permissions

![Roles and permissions](docs/images/05-roles-and-permissions.png)

> ⚠️ The row-filter expression field visible here is **stored but inert** --
> `check_permission` returns it verbatim and applies no filtering. See
> [Current limitations](#current-limitations).

### Knowledge graph preview

![Knowledge graph preview](docs/images/07-knowledge-graph.png)

An ontology is a graph, but every other screen renders it as tables, which hides
the problems a reviewer needs to see: isolated objects nothing points at,
self-referencing hierarchies, and clusters that produce no verdict. Colour encodes
a diagnosis rather than decoration -- red for unbound to a source table, amber for
carries no rules. The relation-expressiveness limitation is stated in the view
itself: `relation_type` is always `references`, with no cardinality and no
many-to-many.

### Document knowledge base

![Document knowledge base](docs/images/09-knowledge-base.png)

Policy and contract clauses are split on their numbering (`第3.2条`, `3.1`,
`一、`, `Article 7`), preserving a locator a human can quote. Two governance
constraints are enforced by the workflow:

1. **Entries are pending by default and are not retrievable until confirmed.** A
   mis-split clause that silently became judgement evidence would produce a
   verdict that looks sourced but is not -- worse than no citation.
2. **Confirming requires an anchor** (business object or rule). Unanchored text
   cannot answer "why does this passage support this verdict".

Retrieval narrows by anchor *before* ranking, which is the opposite of searching
everything and inspecting the hits. That ordering is what makes a citation
attributable rather than merely similar.

### Feedback loop

![Feedback loop](docs/images/10-feedback-loop.png)

Ratings attach to a specific message and its decision record -- "this verdict is
wrong" is only actionable when you know which verdict.

Two deliberate omissions: there is no average satisfaction score, because an
average does not tell you which answer to fix; and there is no one-click "apply
correction", because a correction is one user's claim rather than a new rule, and
promoting it goes through governance (ADR-0002).

### Model configuration for custom endpoints

![Model configuration](docs/images/08-model-config.png)

The platform speaks the OpenAI chat-completions protocol, so any service
implementing it works. A configurable base URL alone is not enough, because
providers differ in how they pass credentials and which extra body fields they
tolerate:

| Setting | Problem it solves |
|---|---|
| Auth style (bearer / api-key / custom / none) | Azure uses an `api-key` header; local servers often need no key |
| Provider extras toggle | vLLM and LM Studio reject unknown body fields with a 400 |
| Extra headers (JSON) | Some gateways require a tenant or group identifier |

Presets ship for OpenRouter, OpenAI, relay gateways, Azure, self-hosted vLLM and
DashScope, and the screen shows the full URL that will actually be called.

## Quick start

Requires Python 3.11+ (Node.js 18+ for the frontend). CI runs the full suite on
3.11, 3.12 and 3.13 -- a version that is claimed but never executed breaks in a
user's environment first. Every command below was run in a
clean environment.

### Install as a package

The kernel has **no third-party dependencies** -- it runs the whole loop without a web
server installed.

```bash
pip install aletheia-onto          # kernel: ontology, rules, verdicts, provenance
pip install 'aletheia-onto[all]'   # plus HTTP layer, PostgreSQL/MySQL, document parsing
```

```bash
aletheia demo      # onboard → model → assess, against a built-in sample system
aletheia doctor    # report configuration, installed extras, registered extension points
```

Connect a real system:

```bash
aletheia init
aletheia connect postgresql://user:pass@host/db --domain 合同管理
aletheia model 1
aletheia assess 1 contract 1
```

**Sources are not limited to databases.** When production credentials are weeks away, an
extract or an API runs the same pipeline:

```bash
aletheia connect /path/to/extract --type csv --domain 合同管理   # a directory of CSVs
aletheia doctor        # available source types, and which driver the inactive ones need
```

Oracle / SQL Server / 达梦 / 人大金仓 / openGauss ship as declarations with their dialects;
installing the driver makes them appear. Adding a SQL database that is *not* declared does
not require writing an adapter — four lines of declaration, see
[the extension guide](docs/extending.md#10-接一个新的-sql-数据库).

**Assess as of a past moment.** A compliance audit usually asks about the past:

```bash
aletheia assess 1 contract 1 --as-of 2026-01-31
```

It uses the values that were valid then, and the rules that were in force then. Assessing
against today's values answers a different question.

`aletheia assess` prints the verdict and the rules that failed; use `--verbose` for the
full evidence. `aletheia publish` is subject to the release gate, and **unreviewed
mappings cannot be skipped with `--force`** -- publishing on mappings nobody looked at
would make every verdict derived from them unaccountable.

### Run from source

```bash
git clone git@github.com:S0ra-ai/Aletheia-onto.git && cd Aletheia-onto
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
ONTOLOGY_ADMIN_PASSWORD=change-me-please .venv/bin/python -m uvicorn \
    ontology_platform.api:app --app-dir backend --host 127.0.0.1 --port 8000
```

Then:

- Health check `http://127.0.0.1:8000/health` → `{"status":"ok"}`
- API docs `http://127.0.0.1:8000/docs`

Every endpoint is served both bare and under `/v1` (`/ontologies/1` and
`/v1/ontologies/1`), through the same authorization middleware and the same policy
table. New integrations should pin `/v1`.

The default platform database is SQLite, so **no external database service is
needed**. If `ONTOLOGY_ADMIN_PASSWORD` is unset, a random admin password is generated
and printed to the startup log.

### Log in and ask one question

```bash
TOKEN=$(curl -fsS -X POST http://127.0.0.1:8000/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"change-me-please"}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')

curl -fsS -X POST http://127.0.0.1:8000/demo/bootstrap \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'

curl -fsS -X POST http://127.0.0.1:8000/semantic/natural-language/query \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"question":"整体合规情况如何？","ontologyId":1,"useModel":false}'
```

Actual response from step 3 (no model key configured, so the local heuristic answers):

```json
{
  "answer": "合同 的批量决策一致性为 mixed。已评估 3 条：通过 2、复核 1、阻断 0、错误 0。",
  "intent": "decision_consistency",
  "confidence": 0.82
}
```

Answers are currently rendered in Chinese. Calling a protected endpoint without a
token returns `401`. CI re-runs this exact sequence on every push.

### Frontend (optional)

```bash
cd frontend && npm install && npm run dev
```

## Ontology vocabulary

Terms in this space are used loosely, so each entry states what the platform means
by it and, where it matters, **what it deliberately is not**.

### Ontology structure

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

### Mapping onto the legacy system

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

### Assessment and provenance

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

## Capability matrix

✅ implemented and covered by tests　⚠️ partially implemented (logic inert)　📋 planned (no implementation)

| Capability | Status | Location |
|---|:--:|---|
| SQLite / MySQL / PostgreSQL source adapters | ✅ | `adapters.py` |
| Metadata scan, column profiling, enum detection, foreign keys | ✅ | `metadata.py` |
| Structural drift comparison | ✅ | `metadata.py` |
| OpenAPI import of business operations | ✅ | `operation_bindings.py` |
| All three dialects as the platform's own store | ✅ | `database.py` |
| Ontology drafting from blueprints | ✅ | `ontology.py` |
| AST-allowlist rule sandbox | ✅ | `semantic_kernel.py` |
| Fail-closed rule semantics | ✅ | `semantic_kernel.py` |
| Expression validation at write time | ✅ | `governance.py` |
| Mapping review, version publish, derive | ✅ | `governance.py` |
| Release-readiness gate (force is audited) | ✅ | `release_readiness.py` |
| Four-layer decision trail | ✅ | `decisions.py` |
| Token auth (PBKDF2-SHA256, digest-only storage) | ✅ | `auth.py` |
| 6 capabilities × 6 roles, central route policy | ✅ | `access_policy.py` |
| Audit actor taken from identity, never client-supplied | ✅ | `api.py` |
| Credential redaction | ✅ | `credentials.py` |
| Domain neutrality (no built-in industry vocabulary) | ✅ | `vocabulary.py` |
| Natural-language semantic Q&A | ✅ | `natural_language.py` |
| Agent roles derived from onboarded domains | ✅ | `agent_roles.py` |
| Operation preflight and HTTP writeback | ✅ | `automation.py` |
| JSON-LD / Turtle export | ✅ | `ontology.py` |
| Workflow `guard_expression` | ✅ | evaluated on transition, fail-closed |
| Permission `filter_expression` | ✅ | evaluated when an instance is supplied |
| **Retrieval-time permission filtering** (citations cannot exceed what the caller may read) | ✅ | `retrieval.py`: after anchoring, before ranking, denying on failure |
| Rule `depends_on` | ✅ | topologically ordered; dependents skip when a prerequisite fails |
| Permission policy ontology dimension | ✅ | keyed on (role, ontology, object); 0 means any |
| Manual CRUD for objects/attributes/relations | ⚠️ | no endpoints |
| List endpoint pagination | ⚠️ | mostly absent |
| Document knowledge base (clause chunking, citations) | ✅ | `knowledge_documents.py` |
| Entries anchored to objects / rules | ✅ | `knowledge_documents.py` |
| Retrieval backend SPI (BM25 default) | ✅ | `retrieval.py` |
| Embedding model SPI (hashed n-gram default) | ✅ | `retrieval.py` |
| Cited verdicts | ✅ | `natural_language.py` |
| Bundled vector database integration | 📋 | register via SPI |
| Conversation persistence | ✅ | `conversations.py` |
| Feedback loop (rating / correction / escalation) | ✅ | `conversations.py` |
| Multi-tenancy (separate schema + tenant_id) | ✅ | `tenancy.py` |
| Tenant provisioning and discovery | ✅ | `tenancy.py` |
| **Relation cardinality and strength** (1:1 / N:1 / N:M, composition / aggregation / association) | ✅ | `relations.py` |
| **Junction tables collapse to many-to-many**, junction object keeps its attributes | ✅ | `relations.py` |
| **Cross-object aggregates** (declared, fail-closed, row-capped) | ✅ | `aggregation.py` |
| **Derived attributes** (expression-computed, reuses the rule sandbox) | ✅ | `derived_attributes.py` |
| **Units and dimensions** (convert within, refuse across) | ✅ | `derived_attributes.py` |
| **Type hierarchy** (subtypes inherit rules, aggregates, derived attributes) | ✅ | `type_hierarchy.py` |
| **Declared rule overrides** (validated against the ancestry) | ✅ | `type_hierarchy.py` |
| **Business events** (declared types, append-only, payload + source time) | ✅ | `events.py` |
| **Unified timeline** (workflow transitions mirrored in) | ✅ | `events.py` |
| **Installable package with a CLI** (`aletheia init/connect/model/assess/...`) | ✅ | `cli.py`, `pyproject.toml` |
| **`/v1` path prefix** (same middleware and policy as bare paths) | ✅ | `api.py`, `access_policy.py` |
| **SQL dialect profiles** (six differences declared as data, not branches) | ✅ | `sql_dialects.py` |
| **Generic DB-API adapter** — a new SQL database is a declaration, not an adapter | ✅ | `generic_sql_adapter.py` |
| Oracle / SQL Server / 达梦 / 人大金仓 / openGauss declarations | ⚠️ | declared with dialects; usable once the driver is installed, but **CI cannot install the drivers, so untested** |
| **CSV / TSV directory source** (types and keys inferred, foreign keys never guessed) | ✅ | `file_adapter.py` |
| **REST / OpenAPI source** (fields declared, never sampled) | ✅ | `rest_adapter.py` |
| **Attribute-level temporality** (valid time and transaction time kept apart) | ✅ | `temporal.py` |
| **As-of assessment** (past values, and the rules in force at the time) | ✅ | `temporal.py`, `semantic_kernel.py` |
| **Direct-database and stored-procedure writeback** (declared statements, bound values, WHERE required) | ✅ | `db_executors.py` |
| Channel integrations, scheduler | 📋 | none |
| Ontology import (SHACL / reasoner) | 📋 | export only |
| **Cross-source entity resolution** (one object spanning two sources; matching is declared) | ✅ | `entity_resolution.py` |
| **Cross-source aggregates** ("this customer's order total in the ERP") | ✅ | `aggregation.py`: `targetDataSourceId` |
| Split into multiple PyPI distributions | 📋 | single package + extras for now |

## Current limitations

### Stored but inert

Most dangerous category, because the API looks functional. Nearly emptied out:
`guard_expression`, `filter_expression`, `depends_on` and the policy's ontology
dimension are all live now, and Event / State from `docs/02` are implemented.

- Deriving a new ontology version does not copy workflow configuration.
- List endpoints are mostly unpaginated.

### Structural expressiveness ceiling

By design, not bugs. These are the next phase's work.

| Constraint | Location |
|---|---|
| **Cross-source matching happens in memory**: the secondary source is read row by row and compared, under a row cap; slow when its match column is unindexed | `entity_resolution.py` |
| **No transitive inference across sources**: A↔B and B↔C never imply A↔C — that would introduce a correspondence nobody declared | `entity_resolution.py` |
| **History covers only what the platform observed**: a source that overwrites values in place still lost its own history. `coverage` reports the window it can actually answer for | `temporal.py` |
| **Aggregates compute in Python**, not pushed down as SQL. Buys identical behaviour across all three dialects; costs a row cap | `aggregation.py` |
| **Relation classification depends on schema quality**: a database without foreign keys or NOT NULL gets the weakest classification | `relations.py` |
| **CSV and REST never infer foreign keys**: relation semantics require declared structure, and a relation resting on a naming coincidence cannot be explained | `file_adapter.py`, `rest_adapter.py` |
| **CSV reads the whole file per query**: fine at extract scale, wrong at warehouse scale | `file_adapter.py` |
| Type hierarchy caps at 16 levels; derivation at 5 passes | `type_hierarchy.py`, `derived_attributes.py` |
| **No full OWL/DL reasoning**, no open-world assumption | deliberate, see [ADR-0005](docs/adr/0005-semantic-generality-ceiling.md) |

> Extension points are no longer on this list: data source adapters, rule functions,
> route policies and writeback executors are all registrable. See
> [the extension guide](docs/extending.md).

### Engineering limitations

- No connection pooling; no unified transaction boundary across `connect()` calls.
- 172 `platform_db: Path | str` signatures are **not yet migrated to the context
  object** -- they accept one, but the per-module migration is outstanding
  ([ADR-0010](docs/adr/0010-platform-context-replaces-global-singleton.md)).
- `api.py` holds 133 endpoints in one file, **not yet split into APIRouters**
  (the `/v1` prefix is in place).
- `frontend/src/types/index.ts` hand-mirrors backend models in 1143 lines; the backend
  emits both camelCase and snake_case.
- DDL dispatch is unified in `schema.py`, but **not yet migrated to Alembic** -- a
  migration has to belong to a distribution, so this is blocked on the package split.
- **Not yet split into multiple PyPI distributions.** One package plus optional extras;
  the extras carry the eventual seams without freezing them.

See [`docs/architecture-debt.md`](docs/architecture-debt.md) for located details and
[`ROADMAP.md`](ROADMAP.md) for sequencing and blockers.

## Design decisions

Full records, including rejected alternatives, in [`docs/adr/`](docs/adr/).

**1. Fail-closed rules.** An expression that cannot be evaluated counts as *not
passed*, never as passed. A renamed column would otherwise silently disable a
blocking rule, let preflight through, and let automation continue — the very scenario
drift detection claims to prevent.
[ADR-0002](docs/adr/0002-rule-engine-fail-closed.md)

**2. Enforced release gate.** Publishing is refused while blocking gates are open;
`force` is recorded in the audit log with the blocker count. Auto-generated drafts are
not production truth.

**3. No built-in domain vocabulary.** Any shipped word list degrades the platform into
a single-industry product. Terms enter only through metadata scanning and
user-imported blueprints. The cost: without a blueprint, draft labels are raw column
names. Ugly but correct beats pretty but only correct for two industries.
[ADR-0003](docs/adr/0003-no-builtin-domain-vocabulary.md)

**4. An explicit ceiling on semantic generality: no full OWL/DL reasoning.** A DL
reasoner's conclusions are products of global entailment and cannot be explained as
"because §3.2", which is directly opposed to verifiability. Generality comes from
structural expressiveness plus escape hatches, not from inference. Open-world
assumption is also wrong here: no payment row means unpaid, not "unknown".
[ADR-0005](docs/adr/0005-semantic-generality-ceiling.md)

**5. Relations are classified from declared structure, never from data.** A relation
inferred from a sample changes meaning when the data changes, and a verdict citing it
would be unreproducible. Every classification records the structural fact it rests on,
because a classification with no stated basis cannot be reviewed.
[ADR-0012](docs/adr/0012-cross-object-aggregation-and-relation-semantics.md)

**6. Aggregates are declared data, not inline joins.** The answer to "why" has to be a
definition an operator can read, review and export -- not a query nobody looked at. An
aggregate that cannot be computed makes its rule fail rather than compare a threshold
against a fabricated zero.
[ADR-0012](docs/adr/0012-cross-object-aggregation-and-relation-semantics.md)

**7. Units convert within a dimension and are refused across.** Without units, mixing
万元 and 元 makes `amount 500 > limit 1000000` report "within limit" — a wrong verdict
produced from correct data. Cross-dimension conversion raises instead of quietly passing
the number through, because comparing a duration to a mass is a modelling error.
Exchange rates stay out: a rate is time-varying data, and embedding one would make a
verdict unreproducible.
[ADR-0013](docs/adr/0013-derived-attributes-and-units.md)

**8. Rule overrides are declared, not inferred from a name collision.** A collision is
ambiguous — two teams can pick the same code by accident, and inference would silently
disable one team's control. Weakening an inherited rule is allowed, because legitimate
business exceptions exist; weakening it *invisibly* is not.
[ADR-0014](docs/adr/0014-type-hierarchy-and-business-events.md)

**9. Events are records, never triggers.** An event that could fire automation would
make the audit trail load-bearing for side effects, so replaying history — backfilling,
correcting, migrating — would re-execute business actions. The stream is append-only for
the same reason: a wrong event is corrected by a compensating one, because deleting
would leave a state with no explanation for how it was reached.
[ADR-0014](docs/adr/0014-type-hierarchy-and-business-events.md)

## Self-hosted deployment

```bash
cp deploy/.env.example deploy/.env    # fill in real values; the example has no usable defaults
docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d
```

Two-stage image, non-root, no bundled credentials and no seeded database. The reference
compose file uses PostgreSQL as the platform store and does not publish the database port.

### Deployment preflight

```bash
aletheia preflight --workers 4 --expect-origin https://ontology.example.com
```

Exits 1 on a blocker, so it works as a pipeline gate. `aletheia serve` runs it
**automatically** when binding to a non-loopback address and refuses to start — nobody
remembers to run a separate command, and the one deployment where it matters is the one
where `ONTOLOGY_AUTH_DISABLED=1` was left behind.

Every check catches a **silent** failure: the platform starts, serves traffic, and looks
healthy.

| Misconfiguration | What actually happens | Level |
|---|---|:--:|
| `ONTOLOGY_AUTH_DISABLED=1` left on | the whole API is reachable with no token, **including writeback** | blocker |
| CORS set to `*` | any site can drive the API carrying a user's credentials | blocker |
| admin password is a placeholder or under 12 chars | somebody chose it and will assume it was changed | blocker |
| SQLite with several workers | writes serialise; the symptom is **intermittent timeouts**, not a config error | blocker |
| platform DB file readable by group/other | that file holds every data source's connection string | blocker |
| CORS still localhost | the real frontend is blocked, and the next step someone takes is `*` | warning |
| admin password unset | a random one is printed once, and container logs rotate | warning |
| password inline in the connection URI | it appears in the process list, container inspect, and crash logs | warning |

A single-node SQLite evaluation deployment is legitimate, so one worker does not block —
refusing it would push people to skip the check entirely.

Full reasoning in [ADR-0017](docs/adr/0017-deployment-preflight.md).

## Roles and capabilities

Six capabilities across six roles. The central route-to-capability table lives in
`access_policy.py`, and **unlisted routes default to admin-only**.

| Role | `platform:read` | `platform:write` | `governance:review` | `governance:publish` | `automation:execute` | `platform:admin` |
|---|:--:|:--:|:--:|:--:|:--:|:--:|
| `admin` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `ontology_engineer` | ✅ | ✅ | | ✅ | | |
| `business_expert` | ✅ | ✅ | ✅ | | | |
| `operator` | ✅ | | | | ✅ | |
| `analyst` | ✅ | | | | | |
| `ai_agent` | ✅ | | | | | |

New users default to `analyst`. Tokens are stored as digests only; sessions expire and
can be revoked, and changing a password invalidates all existing sessions.

## Tests

```bash
.venv/bin/python -m pytest
```

**1179 tests**, all passing. Two skip by environment: the MySQL/PostgreSQL cases skip when
no server is reachable.

| File | Count | Covers |
|---|--:|---|
| `test_extension_registry.py` | 45 | extension registries, doubling as the third-party conformance suite |
| `test_composite_instance_keys.py` | 31 | composite keys end to end, instance-key round-trips |
| `test_value_domain_mapping.py` | 13 | value domain mapping and backwards compatibility |
| `test_custom_model_endpoints.py` | 21 | custom model endpoint compatibility |
| `test_workbench_and_graph.py` | 14 | workbench aggregation and graph projection |
| `test_document_knowledge.py` | 27 | clause chunking, anchored retrieval, cited answers |
| `test_inert_fields_activated.py` | 28 | guards, row filters, rule dependencies, policy scoping |
| `test_conversations_and_feedback.py` | 35 | conversation persistence, feedback attribution, escalation |
| `test_platform_context.py` | 23 | multi-instance isolation, thread binding, compatibility |
| `test_multi_tenancy.py` | 42 | schema routing, tenant_id defence in depth, cross-tenant detection |
| `test_instance_resolvers.py` | 57 | four resolver kinds, conformance contract, injection guards |
| `test_cross_object_aggregation.py` | 46 | aggregate validation, fail-closed, row cap, end to end |
| `test_type_hierarchy_and_events.py` | 42 | inheritance expansion, declared overrides, cycles, append-only events |
| `test_derived_attributes_and_units.py` | 42 | multi-pass derivation, unit conversion, cross-dimension refusal |
| `test_relation_expressiveness.py` | 22 | cardinality and strength inference, junction collapse, one-to-one as a row |
| `test_cross_source_resolution.py` | 46 | cross-source: declared matching, refusing one-to-many, conflict marking, cross-source aggregates |
| `test_retrieval_permission_filtering.py` | 12 | retrieval-time permission filtering: forbidden citations dropped, denial on failure |
| `test_answer_regression.py` | 28 | answer regression: every conclusion cites evidence, routing is stable, answers agree with verdicts |
| `test_deployment_preflight.py` | 41 | preflight: unauthenticated exposure, wildcard CORS, SQLite with workers, image and compose artefacts |
| `test_conformance_suites.py` | 44 | executable contracts for five extension points, with a negative case per property |
| `test_sql_dialects_and_generic_adapter.py` | 54 | dialect profiles, generic DB-API adapter, proven against a real PostgreSQL onboarded by declaration alone |
| `test_file_and_rest_sources.py` | 46 | CSV type/key inference, declared REST sources, end to end to a verdict |
| `test_database_writeback.py` | 35 | declared statements, bound values, WHERE required, zero rows is a failure, real writes and rollback |
| `test_temporal_validity.py` | 35 | half-open windows, backdated inserts, as-of verdicts use past values, absence is not interpolated |
| `test_cli.py` | 35 | CLI loop, release gate not bypassable, errors without tracebacks |
| `test_api_versioning.py` | 20 | `/v1` and bare paths authorize identically, public paths survive versioning, no endpoint silently lands on the admin default |
| `test_packaging.py` | 15 | dependency-free kernel, single source of pins, PEP 561, cwd-independent default path |
| `test_module_boundaries.py` | 6 | no import cycles, no cross-module private imports, resolvable `__all__` |
| `test_metadata_flow.py` | 34 | onboarding, scanning, drafting, readiness |
| `test_api_authentication.py` | 27 | auth, sessions, capability policy, trusted actor |
| `test_domain_neutrality.py` | 25 | unknown domain end to end, plus static guards |
| `test_rule_engine_safety.py` | 17 | sandbox escapes, fail-closed, release gate |
| `test_platform_database_dialects.py` | 10 | all three dialects as platform store |
| `test_credential_protection.py` | 8 | connection string and API key redaction |
| `test_data_source_knowledge_base.py` | 11 | data source knowledge base |

Dialect tests skip automatically when no server is reachable, so CI without service
containers stays green rather than falsely red.

```bash
.venv/bin/python -m ruff check backend tests scripts
.venv/bin/python -m mypy
cd frontend && npm run build
```

## Scale

29 backend modules, roughly 13,400 lines, 98 API endpoints, 31 platform tables,
React + antd frontend.

## Examples

[`examples/contract-system/`](examples/contract-system/) is a minimal contract system
standing in for a legacy application. **All company names, contacts, phone numbers,
emails and credit codes in it are synthetic placeholders** and correspond to no real
entity.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Two hard rules:

1. **Never make a test pass by editing its assertions.**
2. **Documentation may only describe capabilities that exist and are covered by tests.**

Report security issues privately per [SECURITY.md](SECURITY.md).

## License

[Apache-2.0](LICENSE), including the patent grant.
