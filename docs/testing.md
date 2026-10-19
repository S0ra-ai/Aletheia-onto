# Tests

> Test distribution and static checks, and why each assertion is shaped that way.

Back to [English README](../README.md) · [中文 README](../README.zh-CN.md)

```bash
.venv/bin/python -m pytest
```

**1884 tests**, all passing. A case that needs something this machine does not have skips
rather than fails: the MySQL and PostgreSQL cases without their driver or a reachable server,
the frontend ones without a build. That is **nine** skips on a developer machine with neither
database driver and **three** in CI, which installs both drivers and runs both databases as
service containers. A fixed number here would describe the reader's machine rather than the
suite, which is why the claim is not one.

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
| `test_documentation_links.py` | 138 | Documentation links resolve, and the entry points a newcomer needs exist |
| `test_error_codes.py` | 14 | Refusal codes: the registry quotes sentences the platform says, and the console can name every one of them |
| `test_query_limit_clamping.py` | 8 | A caller-supplied `limit` cannot widen a response past the cap (SQLite reads `LIMIT -1` as "no limit") |
| `test_list_pagination.py` | 21 | Every list that grows with the customer's data takes a page; not passing a limit still returns everything |
| `test_connection_pool.py` | 14 | A pooled connection is never handed to a context whose schema or database differs, and never returned with an open transaction |
| `test_framework_readiness.py` | 9 | Every citation on the framework-readiness page still resolves, and its gap list is still there |
| `test_cli_language.py` | 12 | The CLI's own sentences in both languages, including the help text a flag parsed by the parser cannot otherwise reach |
| `test_generated_types.py` | 9 | The generated response types are current, and the generator's own naming is pinned |
| `test_instance_resolvers.py` | 57 | Instance resolvers: the conformance suite |
| `test_sql_dialects_and_generic_adapter.py` | 54 | SQL dialect profiles and the generic DB-API adapter |
| `test_cross_object_aggregation.py` | 46 | Cross-object aggregation: rules that reason over more than one instance |
| `test_cross_source_resolution.py` | 46 | Cross-source entity resolution. The last structural gap on the ROADMAP generality list. |
| `test_file_and_rest_sources.py` | 46 | CSV directories and REST APIs as data sources |
| `test_extension_registry.py` | 45 | Contract tests for the platform's extension points |
| `test_conformance_suites.py` | 46 | Executable conformance suites for the extension points, each with a counter-example |
| `test_derived_attributes_and_units.py` | 42 | Derived attributes and units of measure |
| `test_multi_tenancy.py` | 42 | Multi-tenant isolation: separate schema plus a tenant_id column |
| `test_request_observability.py` | 42 | Request identity, the access log, and structured logging |
| `test_type_hierarchy_and_events.py` | 42 | Type hierarchy and business events |
| `test_deployment_preflight.py` | 48 | Pre-flight checks for a production deployment |
| `test_cli.py` | 41 | The `aletheia` command line |
| `test_conversations_and_feedback.py` | 43 | Conversation persistence and the feedback loop |
| `test_database_writeback.py` | 35 | Writeback into a legacy database, and via stored procedures |
| `test_temporal_validity.py` | 35 | Temporal validity: what was true, and when |
| `test_metadata_flow.py` | 80 | Metadata to a served API: scanning, drafting, mapping review, readiness and export |
| `test_sso.py` | 32 | SSO: the provider proves who, the platform decides what |
| `test_composite_instance_keys.py` | 31 | Composite primary keys, end to end |
| `test_answer_regression.py` | 28 | The question-answering regression set. ROADMAP stage G. |
| `test_api_authentication.py` | 57 | End-to-end authentication and authorization tests |
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
| `test_backup.py` | 14 | Safe SQLite backup inventory, atomic restore, the snapshot taken before it, and the audit rows both leave |
| `test_bilingual_documents.py` | 22 | Both language editions of a page describe the same platform: the same code blocks, the same commands, the same modules |
| `test_axioms.py` | 20 | Axioms: the fifth component of an ontology, and the release gate that uses it |
| `test_scaffold.py` | 21 | Project scaffolding: generated code must actually run |
| `test_audit_reports.py` | 18 | Audit reports: the questions an auditor arrives with, not "what happened recently" |
| `test_rule_engine_safety.py` | 36 | Rule engine safety, release gates, and the window between reading the preconditions and writing the publication |
| `test_codegen.py` | 16 | Code generation from a published ontology |
| `test_tenant_quotas.py` | 16 | Tenant quotas: ROADMAP stage B's last open item |
| `test_quota_enforcement.py` | 9 | A declared quota binds to the rows the platform actually writes |
| `test_packaging.py` | 16 | Packaging: the project is installable, and the install is usable |
| `test_workbench_and_graph.py` | 15 | Workbench aggregation and knowledge graph projection |
| `test_value_domain_mapping.py` | 13 | Value domain mapping: legacy codes to semantic states |
| `test_frontend_type_agreement.py` | 97 | The frontend's hand-written types must agree with the API they mirror, on both sides |
| `test_frontend_serving.py` | 4 | Same-origin production admin shell and API transport prefix |
| `test_metrics.py` | 5 | Prometheus-compatible runtime metrics and safe re-initialisation |
| `test_migrations.py` | 12 | Versioned migrations: the schema changes `SchemaBundle` cannot express |
| `test_retrieval_permission_filtering.py` | 12 | Permission filtering at retrieval time. ROADMAP stage B's last item. |
| `test_data_source_knowledge_base.py` | 13 | The data source's own knowledge base: browsing its rows, answering with its rules, and the shape of the answer |
| `test_platform_database_dialects.py` | 11 | Platform database durability and dialect tests |
| `test_credential_protection.py` | 14 | Credential exposure, and `env:`/`file:` references that keep a secret out of the database |
| `test_derive_completeness.py` | 7 | `derive` must carry forward everything that decides a verdict |
| `test_platform_db_consistency.py` | 7 | `--platform-db` must mean the same database in every command, including `serve` |
| `test_ui_smoke_guards.py` | 18 | The render check's own guards, exercised without a browser |
| `test_frontend_enum_rendering.py` | 2 | No table column prints an enum value itself; it goes through the label maps |
| `test_demo_bootstrap.py` | 2 | The demo buttons, and what they report having destroyed |
| `test_ui_messages.py` | 9 | The bilingual dictionary: both languages, one set of placeholders, no orphan keys, and no `as never` turning the key check off |
| `test_ci_workflow.py` | 3 | The workflow GitHub runs is the workflow the file describes |
| `test_smoke_seeding.py` | 4 | The render check's seeding gives every screen a row, and says only what it did |
| `test_every_route_answers.py` | 1 | Every route called once; none may crash |
| `test_documented_claims.py` | 18 | Documented numbers match the code they describe |
| `test_module_boundaries.py` | 6 | Module boundaries: no import cycles, and no reaching into private names |
| `test_object_service.py` | 14 | Generic business-object browsing over HTTP and in the service, metadata, pagination cost, row-level permission filtering |

## Static checks and frontend build

```bash
.venv/bin/python -m ruff check backend tests scripts
.venv/bin/python -m ruff format --check backend tests scripts
.venv/bin/python -m mypy
cd frontend && npm run build
```

## What static checks cannot see: an empty table column

None of the above catches a column whose `dataIndex` does not match the field name the
endpoint returns. antd draws nothing for a missing key, the linter sees a valid string, and
mypy sees a valid `string`. The frontend has a test runner now (`npm test`), but it runs in
`node` with no DOM, so **there is still no component test** that renders a table and asserts a
cell has text -- and adding one would mean jsdom and a rendering library, which is a different
decision from adding a runner.

Three columns of the governance audit table and four of the model-invocation table were blank
in every row for exactly this reason, and only a browser showed it. What covers the class now
is a browser and a check on the API: the render sweep below reads the drawn rows, and
`test_frontend_type_agreement.py` holds each screen's fields to what its endpoint sends.

`scripts/ui_smoke.py` drives the running application headlessly and reports every column that
is empty in *every* data row. It needs a browser and a live instance, which is precisely why
it is **not in the test suite**: a suite that depends on either fails for reasons unrelated to
the change.

It runs in CI as its own job, where a browser is the subject rather than an incidental
dependency — a job that cannot start one genuinely cannot do its work. The job builds the
frontend, loads a demo instance, and sweeps 43 routes: every screen that charts a table, every
tab that puts one behind it, the login page, and the detail pages for the first ontology and
data source, whose ids are read from the instance rather than written down.

The login page is swept at **`/admin/login`**, and that is where the defect was. The SPA is
mounted under `/admin` in production, so the router's `/login` is not a path the server serves
as a page at all: the auth middleware answers it with `401 {"detail":"缺少访问令牌"}`, which
Chrome renders as a `<pre>` of JSON. The sweep listed `/login` for as long as it has existed,
read `0 table(s), 0 row(s)`, and found nothing to complain about — a route with no table is what
the login page is, and the failure markers looked *inside* the application's own text, so none
of them fired. **It had never rendered the login page once**, and the same mistake was in the
redirect an expired session takes (`window.location.assign('/login')`), which put the reader on
that page of JSON. Both are fixed, and the sweep now asks every dumped document for the
application's mount point: a document without `<div id="root">` was produced by something else,
whatever it says.

The route list is held to the router, in both directions, by `tests/test_ui_smoke_guards.py`:
every path `App.tsx` serves must be swept, and every swept path must be one it serves. Two
screens had never been visited — `/admin/demo` and `/admin/model`, absent rather than
misspelled — and the sweep held `/admin/backup`, which is the API's namespace, not a route: a
browser navigation to it returns `401 {"detail":"缺少访问令牌"}`, the line read
`0 table(s), 0 row(s)`, and the backup screen at `/admin/data-backup` was never loaded at all.

A route that renders no table now fails the sweep unless `NO_TABLE_ROUTES` lists it with a
reason, and a listed route that *does* render one fails as well. Both directions are asserted
because the two failures are different: the first is a screen that stopped working, the second
is an allowance that outlived its reason and started hiding one.

Every route is also read for the text the application renders when a screen did not load
(「页面加载失败」 from the error boundary, 「页面不存在」 from the catch-all route). Without
that, a page that throws in render and a page that has no table by design produce the same
line — and the second is on an exemption list.

Screens that answer a form, or pick a record, are swept through a URL that names what to
show (`/admin/semantic?tab=explain&object=contract&instance=1&ontology=1`,
`/admin/knowledge?ontology=1`, `/admin/objects?ontology=1&object=contract&instance=1`): each page reads the query from the URL for the same reason
tabs do, which also makes an explanation something a person can paste into a ticket. The
object code and the instance id are read from the instance, so the sweep answers for a row
that exists — an explanation of an instance that does not exist renders the same table with
nothing in it, which this check cannot tell from a defect.

Columns that are empty because the *data* has nothing in them are listed in `KNOWN_SPARSE`
and printed on every run. The script cannot tell those from a field-name mismatch, and a
checker that guessed would either miss real defects or fail on real data — so the allowance is
explicit, and anything not on it still fails the job.

The job then runs the sweep **once more with the allowance switched off**, and asserts that
what it reports is exactly what the list contains. An allowance suppresses a finding, so a
stale entry suppresses the very thing this check exists to find; the first run of that
assertion removed an entry that the seeding had made obsolete.

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

## The first five minutes, with no data at all

The sweep above runs against a *seeded* instance, because a table with no rows checks nothing. That
leaves the state every deployment starts in untested -- and it is the state where a wrong screen
costs the most, because there is nothing else to try.

`python scripts/ui_smoke.py --expect-empty` walks the same routes against an instance whose platform
database is empty and asks one question of each: did it render? No table, no empty-column finding
and no rows are expected, so the data-shaped checks are switched off and the two that remain are the
ones that mean something here -- a page that crashed, and a response that is not the application.
Detail routes that need an id the instance does not have are **named**, not silently dropped.

Running it by hand found the two screens it was built to find: `/admin/mapping` said 「没有可审核的本体」
and stopped, and the workbench's decision card said 「尚无决策记录」. Neither named a next step, which
is the whole of what a reader has to go on at that point. Both now do.

It runs in CI as its own step, against a second instance on port 8078.

## Is the English interface actually English?

`scripts/i18n_audit.py` answers the other question a bilingual console raises, and the one
nothing checked. The dictionary tests can only read the dictionary, so a screen that keeps its
own copy of a Chinese string compiles, type-checks, and passes every test in the suite. One did:
the sidebar rendered 「本体改造研发平台」 as a literal while `shell.app.name` sat in the dictionary
unused — on every screen, for the whole life of the migration.

It walks the same routes with `?lang=en` and reads the rendered text, then subtracts what the
instance holds: ontology names, business objects, knowledge clauses, a reader's display name.
Those belong in Chinese on an English screen — translating somebody's data would be a defect of
its own — so the audit asks the API for its strings and treats a fragment as data when it
survives them. What is left is the interface's own words.

The first run put the size of the problem at three things: the sidebar's hardcoded brand, the
static `<title>` in `index.html`, and sentences the *server* composes — the audit report, the
release gate's wording, the reasoning chain, the consistency advice. Twenty of the 43 routes
were already clean, and the rest has since been given codes the console translates.

The server's sentences were listed in `KNOWN_BACKEND_PROSE` one by one with a reason while that work
went on. **The list is empty now** -- every sentence the audit found has a code beside it, so the
console says it in the reader's language -- and it stays because the mechanism is what notices the
*next* server sentence that arrives without one. An entry that matches nothing still fails the run:
an allowance outlives its reason, and the next thing it hides is a defect.

The language is pinned with `?lang=en` or `?lang=zh`, which is a feature before it is a test
hook: a link that opens in the other language, for a reader whose console is set to Chinese. The
link's choice is adopted and the parameter is then taken back out of the address, so the switch
in the header is not overruled by the URL on the next reload.

It is not a proofreader. It reads CJK, so it catches "this sentence was never translated" and
cannot catch "this sentence was translated badly" — that half is `tests/test_ui_messages.py`,
which holds the two languages to the same placeholders and the same keys.

## Scale

92 backend modules, roughly 39,400 lines, 156 API endpoints, 45 platform tables, React +
antd frontend.

CI also has a `scaffold` job that walks the path a *new* deployment takes --
`aletheia new`, install, `init`, `connect`, `model`, `verify.py` -- because three
defects in that path were found by walking it by hand rather than by any check.

CI also has a `quickstart` job that replays the README quick start in a clean environment --
install, serve, log in, ask one question -- because a documented path that stopped working is
a defect a reader meets before a maintainer does.

**The numbers here are written by a script, not by hand.** `scripts/sync_test_counts.py`
collects the tests and rewrites every place the count is stated: the two README badges, the two
README sentences, and the total and per-file columns on these two pages. Adding one test used to
mean editing six documents, each of them a chance to stop halfway, and `tests/test_documented_claims.py`
would fail until all six agreed -- correct, and a chore. Now it is one command:

```
python scripts/sync_test_counts.py            # update the documents
python scripts/sync_test_counts.py --check    # report what is stale, change nothing
```

What it will not write is prose. A test file with no row here is **reported**, not inserted: the
number is mechanical and the sentence beside it is not, and a script that invented 「覆盖什么」
would be writing documentation nobody read. The same goes for a row whose file is gone -- deleting
it is a judgement about this page rather than a number to fill in.

The pattern for each claim lives in that script and nowhere else, because two copies of the same
regular expression is how the chore came about in the first place: one that drifted from the
other would report "nothing to do" while the check failed on a file it had just called current.

The workflow file is checked as well, because it is written by hand and two hand-written
mistakes reached GitHub with nothing local objecting. A `run:` continued with a shell
backslash: YAML folds the line break into a space first, so the backslash lands on that
space, the script is handed `" --base-url"` — one argument with a leading space — and
argparse reports it as unrecognized. And three job keys duplicated: `yaml.safe_load` returns
the last copy without complaint while GitHub refuses the whole file, so no job ran at all.
`test_ci_workflow.py` reads the file as YAML *nodes*, where the source style and the
discarded duplicates both still exist; it has been confirmed to fail on each.
