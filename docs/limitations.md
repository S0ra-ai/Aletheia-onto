# Current limitations

> Honestly: what it cannot do, and why that is design rather than defect.

Back to [English README](../README.md) · [中文 README](../README.zh-CN.md)

## Stored but inert

**This section has been emptied out.** It was the most dangerous category, because an
interface can look functional while silently ignoring stored logic. In particular,
`guard_expression`, `filter_expression`, `depends_on` and the ontology dimension of
permission policy are live and fail closed. Derived versions now carry the workflow and
rule-evaluation metadata needed to reproduce a verdict.

- List endpoints are mostly unpaginated.

## Structural expressiveness ceiling

By design, not bugs. These are the next phase's work.

| Constraint | Location |
|---|---|
| **Cross-source matching happens in memory**: the secondary source is read row by row and compared, under a row cap; slow when its match column is unindexed | `entity_resolution.py` |
| **No transitive inference across sources**: A↔B and B↔C never imply A↔C — that would introduce a correspondence nobody declared | `entity_resolution.py` |
| **History covers only what the platform observed**: a source that overwrites values in place still lost its own history. `coverage` reports the window it can actually answer for | `temporal.py` |
| **Aggregates compute in Python**, not pushed down as SQL. Buys identical behaviour across all three dialects; costs a row cap | `aggregation.py` |
| **Row-level permission filters are judged per candidate row.** The filter is an arbitrary sandboxed expression, so it cannot be pushed into SQL: with a filter configured, listing an object reads one row per candidate up to the candidate cap. Without one, only the returned page is read | `object_service.py`, `workflow_permission.py` |
| **Object listings consider at most 100 000 candidate rows**, so `total` is a count within that window rather than a `COUNT(*)` of the source | `object_service.py` |
| **Relation classification depends on schema quality**: a database without foreign keys or NOT NULL gets the weakest classification | `relations.py` |
| **CSV and REST never infer foreign keys**: relation semantics require declared structure, and a relation resting on a naming coincidence cannot be explained | `file_adapter.py`, `rest_adapter.py` |
| **CSV reads the whole file per query**: fine at extract scale, wrong at warehouse scale | `file_adapter.py` |
| Type hierarchy caps at 16 levels; derivation at 5 passes | `type_hierarchy.py`, `derived_attributes.py` |
| **No full OWL/DL reasoning**, no open-world assumption | deliberate, see [ADR-0005](adr/0005-semantic-generality-ceiling.md) |

> Extension points are no longer on this list: data source adapters, rule functions,
> route policies and writeback executors are all registrable. See
> [the extension guide](extending.md).

## Engineering limitations

- **No connection pooling.** Every `connect()` opens a connection. A pool is not a
  drop-in: connections here are tenant-scoped, and returning one to a shared pool without
  respecting the schema it was opened against would hand a caller another tenant's data.
  Also no unified transaction boundary across `connect()` calls.
- **Credentials are stored as given — there is no encryption at rest.** Data source
  passwords and model API keys sit in the platform database in plaintext, so that database
  *is* the credential store: protect it with filesystem permissions and database access
  controls, and prefer environment variables for the model keys
  (`docs/configuration.md`). A per-row encryption layer needs a crypto dependency the
  zero-dependency kernel does not carry, and an encryption layer whose key is stored beside
  the ciphertext is worse than none, because it looks like protection.
- **Rate limiting is off unless configured.** Set `ONTOLOGY_RATE_LIMIT_PER_MINUTE`;
  `aletheia preflight` reports an externally reachable deployment that has not. Counters are
  per process, so the effective limit is the configured value times the worker count.
- **CSRF protection is not implemented, and is not applicable as the API stands.** The
  platform authenticates with an `Authorization: Bearer` header and sets no cookies, so a
  browser never attaches credentials to a cross-site request on its own. Reintroducing
  cookie-based sessions would make it applicable — see `SECURITY.md`.
- `platform_db` signatures are **all widened to `PlatformDb`** (context, path or string).
  The former `Path | str` annotation rejected contexts in type checkers even though
  runtime accepted it ([ADR-0010](adr/0010-platform-context-replaces-global-singleton.md)).
- The HTTP layer has 156 endpoints and **APIRouter extraction has started**
  (`routers/`); `api.py` still owns most of them.
- **`frontend/src/types/index.ts` hand-mirrors backend models**, and the convention is not
  uniform: `decisions._decision_row` deliberately emits both spellings, while
  `/governance/audit-log` and `/governance/model-invocations` return `dict(row)` — snake_key
  only. Three columns of the audit table and four of the model-invocation table asked for
  camelCase against those payloads and rendered **empty for every row**, which no test and no
  linter reports: an antd column whose `dataIndex` does not exist is simply blank. The fix
  here was to match each table to its own endpoint; the real fix is for one naming
  convention to win.

  **It keeps recurring.** Found afterwards: all seven columns of `/permissions/policies`,
  the type and risk columns of `/tools`, and five of seven on `/ontologies/{id}/mappings` —
  where the more galling part is that the serializer producing exactly the right fields
  already existed in the same repository and the endpoint simply did not call it. Those three
  are now normalised in `api/index.ts`, because mapping the wire onto the application's shape
  is that file's job, and correcting one page at a time is how the same defect arrived four
  times.

  Response-side consistency is now checked in two places, neither of them complete.
  `tests/test_frontend_type_agreement.py` lists the fields each screen reads and asserts the
  endpoint still sends them — a written-down contract, per screen, not generated agreement.
  It covers the endpoints a screen charts; an endpoint no screen reads is not covered, and
  adding a field to a screen without adding it there is not caught.
  It also reads the *wire* fields an endpoint still sends — not the fields a screen consumes.
  `/workflows/{id}/instances/{id}/actions` and `.../history` were charted with their wire
  spellings (`action_code`, `to_state`) and tested, while the client merely `as`-cast them to
  camelCase: the transition buttons showed no target state and always answered 422, the history
  timeline rendered 「初始 → 」, and both the chart and its reverse check stayed green (those
  words appear in an unrelated normaliser). What would catch it is a behavioural test of the
  client, and the frontend has no test runner (below).
  `scripts/ui_smoke.py` covers the rest by inspection, reporting columns that are empty in
  every row; it needs a browser and a live instance, which is why it is a diagnostic rather
  than a gate. It has just had three blind spots closed — tabs (a page must put its active
  tab in the URL), tables that render only after a click, and cells holding an icon rather
  than text, which were reported as empty forever. A diagnostic that reports a standing
  false positive is teaching its reader to skim past the real findings.
- **The interface is bilingual, and what the server says can be translated with it; what is left is
  the CLI and the API itself.** Nineteen screens read from `i18n/messages/`; the sentences the server
  composes -- advice, gate verdicts, audit findings, the kernel's recommendation, the explanation of
  an instance -- now travel with a **stable code and the facts they are about**, so the console says
  them in the reader's language and falls back to the server's sentence only for a code it does not
  know. `scripts/i18n_audit.py` holds that in CI, and it now needs **no allowance at all**:
  `KNOWN_BACKEND_PROSE` is empty, kept because the mechanism is what notices the *next* untranslated
  server sentence, and an entry that matches nothing fails the run. What is still Chinese-only is
  **the CLI's output and the API's own error text** (`aletheia` is Chinese-first, and so are the 156
  endpoints' `detail` strings). In English mode the console falls back to those, so the gap between
  "the interface is in English" and "what you read is in English" is still there -- it is just now
  confined to failures and to the platform describing itself.

- **The frontend has no test runner.** No vitest, no Testing Library, no `test` script in
  `package.json` -- so nothing in `frontend/src` is unit-tested: not `label()`'s fallback,
  not the payload normalisers in `api/index.ts`, not the pure helpers in `i18n/`. The
  failure modes that mattered most are covered from outside instead -- the response contract
  holds each screen's fields to what its endpoint sends, and the render sweep reads the drawn
  rows in a real browser -- which is how eight blank-column defects were found after typing
  and linting had passed. What that leaves uncovered is anything that does not change the
  shape of a rendered table: a wrong fallback, a mis-sorted list, punctuation. Adding a
  runner is a product decision about dependencies, not an oversight to fix in passing.
- **Versioned migrations exist** (`migrations.py`). Alembic is deliberately not used:
  it depends on SQLAlchemy and would break the zero-dependency kernel, while its useful
  properties here—a version ledger and ordered application—are provided directly.
- **Not yet split into multiple PyPI distributions.** One package plus optional extras;
  the extras carry the eventual seams without freezing them.

See [`docs/architecture-debt.md`](architecture-debt.md) for located details and
[`ROADMAP.md`](../ROADMAP.md) for sequencing and blockers.
