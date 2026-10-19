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
| The console's own response types are described from observed payloads, not written by hand | `frontend/src/types/generated.ts` | `tests/test_generated_types.py` |
| Seven of the screens' row types are aliases of those declarations rather than copies of them | `frontend/src/types/index.ts` | `tests/test_generated_types.py` |
| A path from nothing to a verdict that a newcomer can follow | `docs/quickstart.md` | `tests/test_documentation_links.py` |

## Extend

| Capability | Where it lives | What holds it |
|---|---|---|
| Register a data source adapter without touching platform code | `backend/ontology_platform/registry.py` | `tests/test_extension_registry.py` |
| Register a rule function, a route policy, a writeback executor | `backend/ontology_platform/registry.py` | `tests/test_extension_registry.py` |
| **Verify your own implementation** before shipping it, without pytest and without this repo | `backend/ontology_platform/conformance.py` | `tests/test_conformance_suites.py` |
| A model-provider contract, whose failure paths the implementation must supply an instance for | `backend/ontology_platform/conformance.py` | `tests/test_conformance_suites.py` |
| A credential cannot reach the log through a model endpoint's own error text | `backend/ontology_platform/model_client.py` | `tests/test_conformance_suites.py` |
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
| The two append-only lists page by **cursor**, so a row inserted mid-read cannot be skipped | `backend/ontology_platform/pagination.py` | `tests/test_list_pagination.py` |
| A caller-supplied limit cannot take the whole table | `backend/ontology_platform/config.py` | `tests/test_query_limit_clamping.py` |
| A bilingual console, checked by reading it in both languages | `frontend/src/i18n/locale.tsx` | `tests/test_ui_messages.py` |
| A bilingual CLI, whose `--help` follows the flag that its own parser reads | `backend/ontology_platform/cli_messages.py` | `tests/test_cli_language.py` |
| Cells rendered and read in process, so a blank column fails a unit test and not only a browser sweep | `frontend/src/components/TableColumns.test.tsx` | `tests/test_frontend_type_agreement.py` |
| A column of dashes counts as empty too — the fallback that used to hide a rename | `scripts/ui_smoke.py` | `tests/test_ui_smoke_guards.py` |
| Every such allowance is written down with its reason, and a stale one fails CI | `scripts/ui_smoke.py` | `scripts/check_smoke_allowance.py` |

## Not there yet

The rows above are capabilities that exist **and are checked**. These are the ones an evaluator
comparing this to a mature framework would look for and not find, stated so the comparison is
honest rather than flattering. Every one of them has a reason; none of them is a surprise to this
project.

| Gap | What it costs a third party |
|---|---|
| **Not every response type can be generated, and the split is by hand.** `generated.ts` describes the *wire*; for the endpoints the client normalises (`/permissions/policies`, `/tools`, `/data-sources/{id}/tables`), the screen's type is the normalised shape and forcing it onto the generated one would delete the normaliser the blank-column defects were fixed by. Seven types are aliases of generated declarations and the rest are hand-written. | A field rename on a *normalised* endpoint is caught by `normalise.test.ts` and by the generated file, not by one mechanism that covers both. |
| **Component tests cover thirty-five tables across sixteen screens, not every screen.** `src/components/TableColumns.test.tsx` renders the mapping queue, the rule list, ontologies, data sources, the permission roles/policies/tools/pending-execution tables, the governance audit/invocation/decision tables, the audit report's five sections, the workflow list with its transitions, the backup list, the tenant list, the ontology detail page's six tabs, the knowledge base's documents and entries, the feedback console's feedback and escalation tables, the data source detail page's scanned tables and operation bindings, the modelling extensions page's event types, and the semantic screen's explain and consistency tables, asserting every cell has text; the rest are covered by the browser sweep. | A blank column on a screen nobody wrote a test for is still found by a browser, if somebody runs one. |
| **Untranslated refusals remain**, though far fewer: 73 of 101 single-sentence Chinese refusals carry a code the console can translate, and the extension-author batch added 108 parameterised ones on top. What is left fires only when the platform itself is misassembled. | An English console can still show a Chinese sentence for a failure the platform's own assembly produced. |
| **The API's own sentences stay Chinese even in English mode** — in the CLI as well as the console, which fall back to them for a code they do not know. | Deliberate: the payload's shape and vocabulary are the contract a pipeline parses, and translating it would make the same response say different things to different callers. |
