# Capability matrix

> What is implemented, partially implemented, or planned -- and where.

Back to [English README](../README.md) · [中文 README](../README.zh-CN.md)

✅ implemented and covered by tests　⚠️ partially implemented (logic inert)　📋 planned (no implementation)

| Capability | Status | Location |
|---|:--:|---|
| SQLite / MySQL / PostgreSQL source adapters | ✅ | `adapters.py` |
| Metadata scan, column profiling, enum detection, foreign keys | ✅ | `metadata.py` |
| Structural drift comparison | ✅ | `metadata.py` |
| OpenAPI import of business operations | ✅ | `operation_bindings.py`, `onboarding.py` |
| **Data source adapters are registerable** (a third party needs no fork) | ✅ | `registry.py`, `adapters.py` |
| **Executable conformance contracts ship with the package** (five extension points, self-verifiable) | ✅ | `conformance.py` |
| **Deployment preflight** (silent misconfigurations -- an unauthenticated exposure, a bad combination -- refused at the pipeline stage) | ✅ | `deployment.py`, `deploy/` |
| All three dialects as the platform's own store | ✅ | `database.py` |
| Ontology drafting from blueprints | ✅ | `ontology.py`, `industry_blueprints.py` |
| Industry blueprint import | ✅ | `industry_blueprints.py` |
| **Axioms** (six model-level constraints; a violation blocks publication) | ✅ | `axioms.py` |
| Semantic coverage report | ✅ | `coverage.py` |
| Value-domain mapping via `value_to_state` (through the review flow) | ✅ | `value_mapping.py` |
| Composite primary keys (the instance-key abstraction) | ✅ | `instance_key.py` |
| **Instance resolvers**: master-detail, discriminator-partitioned, custom SQL | ✅ | `instance_resolver.py` |
| Resolvers are registerable (third-party strategies) | ✅ | `instance_resolver.py` |
| AST-allowlist rule sandbox | ✅ | `semantic_kernel.py` |
| Fail-closed rule semantics | ✅ | `semantic_kernel.py` |
| **Rule functions are registerable** (without loosening the sandbox) | ✅ | `semantic_kernel.py`, `registry.py` |
| Expression validation at write time | ✅ | `governance.py` |
| Mapping review, version publish, derive | ✅ | `governance.py` |
| Release-readiness gate (force is audited) | ✅ | `release_readiness.py` |
| Four-layer decision trail | ✅ | `decisions.py` |
| Token auth (PBKDF2-SHA256, digest-only storage) | ✅ | `auth.py` |
| 6 capabilities × 6 roles, central route policy | ✅ | `access_policy.py` |
| **SSO** (JWT assertion verification, group→role mapping) | ✅ | `sso.py` |
| **An unmapped SSO identity is refused** (no default role is granted) | ✅ | `sso.py` |
| Audit actor taken from identity, never client-supplied | ✅ | `api.py` |
| Credential redaction | ✅ | `credentials.py` |
| **Request identity across response and logs** (`X-Request-Id`; a caller may supply one, validated first) | ✅ | `tracing.py`, `request_logger.py` |
| **Access log** (path but never query string; 5xx and 4xx at different levels) | ✅ | `request_logger.py` |
| **Structured logging** (`ONTOLOGY_LOG_FORMAT=json`, every record carrying the request id) | ✅ | `logging_config.py` |
| **A 500 that carries `requestId`** (exception text goes to the log, not the response body) | ✅ | `request_logger.py` |
| **Request rate limiting** (before authentication; off unless configured; stricter for login) | ✅ | `rate_limiter.py` |
| CSRF protection | 📋 | **not applicable as the API stands**: bearer header, no cookies — see [`SECURITY.md`](../SECURITY.md) |
| Credential encryption at rest | 📋 | none: credentials are stored plaintext in the platform database, which is therefore the credential store — see [limitations](limitations.md) |
| Domain neutrality (no built-in industry vocabulary) | ✅ | `vocabulary.py`, `config.py` |
| Natural-language semantic Q&A | ✅ | `natural_language.py` |
| Agent roles derived from onboarded domains | ✅ | `agent_roles.py`, `agent.py` |
| **Model responses normalised field by field** — one wrong-shaped field costs that field only, and is named in `unreadableModelFields` | ✅ | `model_client.py` |
| Operation preflight and HTTP writeback | ✅ | `automation.py` |
| JSON-LD / Turtle export | ✅ | `ontology.py` |
| **OWL / RDFS export** (`owl:Class`, `rdfs:domain`, `rdfs:range`, `rdfs:subClassOf`) | ✅ | `standard_vocabulary.py` |
| **SHACL shapes export** (generated from the same declaration, not hand-written) | ✅ | `standard_vocabulary.py` |
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
| **Tenant quotas** (held in the platform database, so a tenant cannot raise its own) | ✅ | `quotas.py` |
| **Relation cardinality and strength** (1:1 / N:1 / N:M, composition / aggregation / association) | ✅ | `relations.py` |
| **Junction tables collapse to many-to-many**, junction object keeps its attributes | ✅ | `relations.py` |
| **Cross-object aggregates** (declared, fail-closed, row-capped) | ✅ | `aggregation.py` |
| **Derived attributes** (expression-computed, reuses the rule sandbox) | ✅ | `derived_attributes.py` |
| **Units and dimensions** (convert within, refuse across) | ✅ | `derived_attributes.py` |
| **Type hierarchy** (subtypes inherit rules, aggregates, derived attributes) | ✅ | `type_hierarchy.py` |
| **Declared rule overrides** (validated against the ancestry) | ✅ | `type_hierarchy.py` |
| **Business events** (declared types, append-only, payload + source time) | ✅ | `events.py` |
| **Unified timeline** (workflow transitions mirrored in) | ✅ | `events.py`, `workflow_permission.py` |
| Workflow state and history per instance | ✅ | `workflow_permission.py` |
| **Audit reports** (controls that never fired, gates that were overridden, how much of the period is re-examinable) | ✅ | `audit_reports.py` |
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
| **Writeback executors are registerable** (dispatched by scheme) | ✅ | `automation.py`, `registry.py` |
| Channel integrations, scheduler | 📋 | none |
| Ontology import (SHACL / reasoner) | 📋 | export only |
| **Cross-source entity resolution** (one object spanning two sources; matching is declared) | ✅ | `entity_resolution.py` |
| **Cross-source aggregates** ("this customer's order total in the ERP") | ✅ | `aggregation.py`: `targetDataSourceId` |
| **Admin console** (React + antd; every capability above has a screen) | ✅ | `frontend/` |
| **Workbench aggregation** (what to do next, blockers first) | ✅ | `workbench.py` |
| **Knowledge graph preview** (with a diagnosis of what the model is missing) | ✅ | `graph_view.py` |
| **Bilingual console** (Chinese-first, complete English; `?lang=en` pins it for a link) | ✅ | `frontend/src/i18n/`, `test_ui_messages.py` |
| Console *copy* in the server's own error text | ⚠️ | the 156 endpoints' `detail` strings are Chinese; the console translates the sentences it is given codes for and shows the rest as sent |
| Split into multiple PyPI distributions | 📋 | single package + extras for now |
