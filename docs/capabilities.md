# Capability matrix

> What is implemented, partially implemented, or planned -- and where.

Back to [English README](../README.md) · [中文 README](../README.zh-CN.md)

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
