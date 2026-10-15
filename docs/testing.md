# Tests

> Test distribution and static checks, and why each assertion is shaped that way.

Back to [English README](../README.md) · [中文 README](../README.zh-CN.md)

```bash
.venv/bin/python -m pytest
```

**1675 tests**, all passing. Two skip by environment: the MySQL/PostgreSQL cases skip when
no server is reachable.

CI runs the full suite on 3.11, 3.12 and 3.13. A version that is claimed but never executed
breaks in a user's environment first: Python keeps syntax compatible but removes stdlib
modules and changes defaults, and this platform reads schemas through `sqlite3` and enforces
its rule sandbox through `ast`.

## Assert behaviour, not source text

Several assertions were rewritten from "the source contains this string" to "the behaviour
holds", because the first form let real defects survive:

- The **Turtle export** asserted that its output *contained* certain substrings — and a
  syntactically invalid document contains a substring exactly as well as a valid one. It
  shipped unreadable by any RDF parser. It is now parsed with rdflib and queried with SPARQL.
- **`/v1` coverage** compared declared path lists, and was green while `/v1` was in fact
  unreachable. It now sends unauthenticated requests and requires 401 from both forms.
- The **endpoint count** grepped decorators, so moving routes onto an `APIRouter` made the
  number drop without any endpoint disappearing.

## Counter-examples prove the assertions work

Every safety and correctness assertion has had a counter-example injected and confirmed to
fail: authentication defaulting to on, axiom violations blocking publication, quotas being
unreachable from the tenant, IRI namespace stability, forged signature rejection.
**An assertion never shown to fail is indistinguishable from an empty one.**

## Distribution

| File | Count | Covers |
|---|--:|---|
| `test_documentation_links.py` | 126 | Documentation links resolve, and the entry points a newcomer needs exist |
| `test_instance_resolvers.py` | 57 | Instance resolvers: the conformance suite |
| `test_sql_dialects_and_generic_adapter.py` | 54 | SQL dialect profiles and the generic DB-API adapter |
| `test_cross_object_aggregation.py` | 46 | Cross-object aggregation: rules that reason over more than one instance |
| `test_cross_source_resolution.py` | 46 | 跨源实体消解。ROADMAP 通用性清单最后一项结构性空白。 |
| `test_file_and_rest_sources.py` | 46 | CSV directories and REST APIs as data sources |
| `test_extension_registry.py` | 45 | Contract tests for the platform's extension points |
| `test_conformance_suites.py` | 44 | Executable conformance suites for the extension points |
| `test_derived_attributes_and_units.py` | 42 | Derived attributes and units of measure |
| `test_multi_tenancy.py` | 42 | Multi-tenant isolation: separate schema plus a tenant_id column |
| `test_request_observability.py` | 42 | Request identity, the access log, and structured logging |
| `test_type_hierarchy_and_events.py` | 42 | Type hierarchy and business events |
| `test_deployment_preflight.py` | 45 | Pre-flight checks for a production deployment |
| `test_cli.py` | 41 | The `aletheia` command line |
| `test_conversations_and_feedback.py` | 41 | Conversation persistence and the feedback loop |
| `test_database_writeback.py` | 35 | Writeback into a legacy database, and via stored procedures |
| `test_temporal_validity.py` | 35 | Temporal validity: what was true, and when |
| `test_metadata_flow.py` | 72 |  |
| `test_sso.py` | 32 | SSO: the provider proves who, the platform decides what |
| `test_composite_instance_keys.py` | 31 | Composite primary keys, end to end |
| `test_answer_regression.py` | 28 | 问答回归测试集。ROADMAP 阶段 G。 |
| `test_api_authentication.py` | 55 | End-to-end authentication and authorization tests |
| `test_inert_fields_activated.py` | 29 | Three fields that were stored but never evaluated |
| `test_document_knowledge.py` | 27 | Document knowledge layer: citations anchored to the ontology |
| `test_domain_neutrality.py` | 25 | Domain neutrality tests |
| `test_standard_vocabulary.py` | 24 | OWL/RDFS/SHACL export: the same ontology in vocabulary other tools can act on |
| `test_platform_context.py` | 23 | Platform context: the object that replaced the module-level singleton |
| `test_rate_limiter.py` | 24 | Fixed-window request rate limiting, and the middleware that applies it |
| `test_relation_expressiveness.py` | 22 | Relation semantics: cardinality, strength and many-to-many |
| `test_api_versioning.py` | 23 | The `/v1` prefix: every route served twice, with identical protection |
| `test_custom_model_endpoints.py` | 28 | Custom model endpoint compatibility |
| `test_error_messages.py` | 21 | What a user reads when something fails |
| `test_backup.py` | 10 | Safe SQLite backup inventory and atomic restore |
| `test_axioms.py` | 20 | Axioms: the fifth component of an ontology, and the release gate that uses it |
| `test_scaffold.py` | 21 | Project scaffolding: generated code must actually run |
| `test_audit_reports.py` | 18 | Audit reports: the questions an auditor arrives with, not "what happened recently" |
| `test_rule_engine_safety.py` | 34 | Rule engine safety and release gate tests |
| `test_codegen.py` | 16 | Code generation from a published ontology |
| `test_tenant_quotas.py` | 16 | Tenant quotas: ROADMAP stage B's last open item |
| `test_packaging.py` | 15 | Packaging: the project is installable, and the install is usable |
| `test_workbench_and_graph.py` | 15 | Workbench aggregation and knowledge graph projection |
| `test_value_domain_mapping.py` | 13 | Value domain mapping: legacy codes to semantic states |
| `test_frontend_type_agreement.py` | 90 | The frontend's hand-written types must agree with the API they mirror, on both sides |
| `test_frontend_serving.py` | 4 | Same-origin production admin shell and API transport prefix |
| `test_metrics.py` | 5 | Prometheus-compatible runtime metrics and safe re-initialisation |
| `test_migrations.py` | 12 | Versioned migrations: the schema changes `SchemaBundle` cannot express |
| `test_retrieval_permission_filtering.py` | 12 | 检索期权限过滤。ROADMAP 阶段 B 的最后一项。 |
| `test_data_source_knowledge_base.py` | 11 |  |
| `test_platform_database_dialects.py` | 10 | Platform database durability and dialect tests |
| `test_credential_protection.py` | 8 | Credential exposure tests |
| `test_derive_completeness.py` | 7 | `derive` must carry forward everything that decides a verdict |
| `test_platform_db_consistency.py` | 7 | `--platform-db` must mean the same database in every command, including `serve` |
| `test_ui_smoke_guards.py` | 6 | The render check's own guards, exercised without a browser |
| `test_every_route_answers.py` | 1 | Every route called once; none may crash |
| `test_documented_claims.py` | 12 | Documented numbers match the code they describe |
| `test_module_boundaries.py` | 6 | Module boundaries: no import cycles, and no reaching into private names |
| `test_object_service.py` | 13 | Generic business-object browsing over HTTP and in the service, metadata, pagination cost, row-level permission filtering |

## Static checks and frontend build

```bash
.venv/bin/python -m ruff check backend tests scripts
.venv/bin/python -m ruff format --check backend tests scripts
.venv/bin/python -m mypy
cd frontend && npm run build
```

## What static checks cannot see: an empty table column

None of the above catches a column whose `dataIndex` does not match the field name the
endpoint returns. antd draws nothing for a missing key, the linter sees a valid string, mypy
sees a valid `string`, and a component test renders the table without asserting that any cell
has text. Three columns of the governance audit table and four of the model-invocation table
were blank in every row for exactly this reason, and only a browser showed it.

`scripts/ui_smoke.py` drives the running application headlessly and reports every column that
is empty in *every* data row. It needs a browser and a live instance, which is precisely why
it is **not in the test suite**: a suite that depends on either fails for reasons unrelated to
the change.

It runs in CI as its own job, where a browser is the subject rather than an incidental
dependency — a job that cannot start one genuinely cannot do its work. The job builds the
frontend, loads a demo instance, and sweeps 35 routes: every screen that charts a table, every
tab that puts one behind it, and the detail pages for the first ontology and data source,
whose ids are read from the instance rather than written down.

Columns that are empty because the *data* has nothing in them are listed in `KNOWN_SPARSE`
and printed on every run. The script cannot tell those from a field-name mismatch, and a
checker that guessed would either miss real defects or fail on real data — so the allowance is
explicit, and anything not on it still fails the job.

Run it by hand after touching a table:

```bash
cd frontend && npm run build && cd ..
aletheia serve                                  # in another shell
python scripts/ui_smoke.py --base-url http://127.0.0.1:8000 --token "$TOKEN" --user "$USER"
```

It prints a line per route with how many tables and rows it examined, because a check that
silently visited nothing is indistinguishable from a check that found nothing. Routes that
keep their tables behind a tab are listed with the tab in the query
(`/admin/governance?tab=report`): the tool loads a route and reads the DOM, so anything below
the first tab is outside its reach unless the page puts the active tab in the URL.
## Scale

86 backend modules, roughly 36,100 lines, 156 API endpoints, 45 platform tables, React +
antd frontend.

CI also has a `scaffold` job that walks the path a *new* deployment takes --
`aletheia new`, install, `init`, `connect`, `model`, `verify.py` -- because three
defects in that path were found by walking it by hand rather than by any check.

CI also has a `quickstart` job that replays the README quick start in a clean environment and
verifies that the test count stated here matches what pytest collects.
