# Framework readiness

> What a third party needs in order to adopt this as a framework rather than as a product —
> and, in the last section, what is still missing.

Back to [README](../README.md) · [Capabilities](capabilities.md) · [Current limitations](limitations.md)

## Why this page exists

Every other document here describes what the platform *does*. This one asks a different
question, and it is the question an evaluator actually has: **can I build on this without forking
it?** That is the difference between a project and a framework, and it is not answered by a
feature list — a product with every feature still fails it if changing the behaviour you need
requires editing somebody else's code.

The comparison it is written against is the shape of a mature enterprise open-source framework:
install and upgrade from a package index, scaffold a project against it, extend it through
declared points, verify your extensions yourself, and operate it under governance. Each row below
names the artifact that provides the capability and the check that holds it — because a
capability nobody verifies is a claim, and the rows that would be claims are in
[Not there yet](#not-there-yet).

**This page is itself checked.** `tests/test_framework_readiness.py` parses the tables and fails
if a cited file, test, or CLI command stops existing. A capability that quietly disappears takes
its row with it rather than leaving a promise behind.

## Adopt

| Capability | Where it lives | What holds it |
|---|---|---|
| Install from a package index; upgrade without forking | `pyproject.toml` | `tests/test_packaging.py` |
| The kernel installs with **zero** third-party dependencies | `pyproject.toml` | `tests/test_packaging.py` |
| Scaffold a project that *depends* on the platform rather than copying it | `backend/ontology_platform/scaffold.py` | `tests/test_scaffold.py` |
| Generate typed models for **your** ontology — relations typed as the object they point at | `backend/ontology_platform/codegen.py` | `tests/test_codegen.py` |
| A path from nothing to a verdict that a newcomer can follow | `docs/quickstart.md` | `tests/test_documentation_links.py` |

## Extend

| Capability | Where it lives | What holds it |
|---|---|---|
| Register a data source adapter without touching platform code | `backend/ontology_platform/registry.py` | `tests/test_extension_registry.py` |
| Register a rule function, a route policy, a writeback executor | `backend/ontology_platform/registry.py` | `tests/test_extension_registry.py` |
| **Verify your own implementation** before shipping it, without pytest and without this repo | `backend/ontology_platform/conformance.py` | `tests/test_conformance_suites.py` |
| The platform's own implementations pass the same contract third parties get | `backend/ontology_platform/conformance.py` | `tests/test_conformance_suites.py` |
| An extension point that stops being extended fails loudly, not silently | `backend/ontology_platform/registry.py` | `tests/test_module_boundaries.py` |

## Model

| Capability | Where it lives | What holds it |
|---|---|---|
| A closed metamodel — entity types, data properties, object properties, axioms, rules | `backend/ontology_platform/ontology.py` | `tests/test_axioms.py` |
| Cross-object aggregates and derived attributes with units | `backend/ontology_platform/aggregation.py` | `tests/test_cross_object_aggregation.py` |
| Attribute-level temporal validity, and verdicts as of a past instant | `backend/ontology_platform/temporal.py` | `tests/test_temporal_validity.py` |
| Export OWL/RDFS and SHACL that another tool can *interpret*, not merely parse | `backend/ontology_platform/standard_vocabulary.py` | `tests/test_standard_vocabulary.py` |
| Every verdict carries its governing rule, its evidence and a persisted decision record | `backend/ontology_platform/decisions.py` | `tests/test_answer_regression.py` |

## Govern

| Capability | Where it lives | What holds it |
|---|---|---|
| Role-based access with per-object data permissions, failing closed | `backend/ontology_platform/workflow_permission.py` | `tests/test_api_authentication.py` |
| Multi-tenant isolation that a query forgetting its tenant filter cannot breach | `backend/ontology_platform/tenancy.py` | `tests/test_multi_tenancy.py` |
| Quotas a tenant cannot raise for itself | `backend/ontology_platform/quotas.py` | `tests/test_tenant_quotas.py` |
| A state machine per business object, with guards that fail closed | `backend/ontology_platform/workflow_permission.py` | `tests/test_type_hierarchy_and_events.py` |
| An audit trail, and the authenticated principal on every row of it | `backend/ontology_platform/auth.py` | `tests/test_audit_reports.py` |
| Publication gates that `--force` cannot skip | `backend/ontology_platform/governance.py` | `tests/test_rule_engine_safety.py` |
| A refusal the console can say in the reader's language | `backend/ontology_platform/error_codes.py` | `tests/test_error_codes.py` |

## Operate

| Capability | Where it lives | What holds it |
|---|---|---|
| A preflight that **refuses** to expose an unsafe configuration | `backend/ontology_platform/deployment.py` | `tests/test_deployment_preflight.py` |
| `serve` refuses to bind a network address with an unsafe configuration | `backend/ontology_platform/cli.py` | `tests/test_deployment_preflight.py` |
| Container artifacts that run as non-root | `deploy/` | `tests/test_deployment_preflight.py` |
| Backups and a restore that keeps the way back | `backend/ontology_platform/backup.py` | `tests/test_backup.py` |
| Secrets that can stay out of the database entirely | `backend/ontology_platform/credentials.py` | `tests/test_credential_protection.py` |
| A list that grows with the customer's data takes a page | `backend/ontology_platform/pagination.py` | `tests/test_list_pagination.py` |
| A caller-supplied limit cannot take the whole table | `backend/ontology_platform/config.py` | `tests/test_query_limit_clamping.py` |
| A bilingual console, checked by reading it in both languages | `frontend/src/i18n/locale.tsx` | `tests/test_ui_messages.py` |

## Not there yet

The rows above are capabilities that exist **and are checked**. These are the ones an evaluator
comparing this to a mature framework would look for and not find, stated so the comparison is
honest rather than flattering. Every one of them has a reason; none of them is a surprise to this
project.

| Gap | What it costs a third party |
|---|---|
| **Frontend types are hand-mirrored from the backend** (`frontend/src/types/index.ts`). The request side is checked against the API models; the response side is not generated, because every endpoint returns `dict[str, object]` and a generator would emit `unknown`. | A backend field rename is caught by a test, not by the compiler. Four "column blank for every row" defects arrived this way. |
| **No component tests.** `npm test` runs vitest in `node` with no DOM, so the pure layer between the wire and the screens is covered and the rendered output is not. | A mis-sorted list or a button wired to the wrong handler is found by a browser sweep, if somebody runs one. |
| **The CLI is Chinese-only.** The console is bilingual; `aletheia` is not, and has no `--lang`. | A non-Chinese-reading operator works from the API or from the English docs. |
| **Untranslated refusals remain**: 51 of 101 single-sentence Chinese refusals carry a code the console can translate. The rest are internal invariants a reader cannot reach. | An English console can still show a Chinese sentence for an unusual failure. |
| **`aletheia preflight` warns about rate limiting rather than blocking**, because the CLI does not know which address the service will bind. `serve` **does** know, and blocks. | An operator who checks with `preflight` and then exposes the service is protected by `serve` refusing; one who skips both is not. |
| **Connection pooling is off by default** (`ONTOLOGY_CONNECTION_POOL_SIZE`). | A high-traffic PostgreSQL deployment pays a handshake per request until an operator turns it on. |
| **No pluggable model-provider SPI with a conformance suite** — model endpoints are configured, and the extension points with published contracts are instance resolvers, data source adapters, retrieval backends, embedding models and writeback executors. | Adding a genuinely new provider protocol means reading `model_client.py`. |
