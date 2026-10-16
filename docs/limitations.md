# Current limitations

> Honestly: what it cannot do, and why that is design rather than defect.

Back to [English README](../README.md) · [中文 README](../README.zh-CN.md)

## Stored but inert

**This section has been emptied out.** It was the most dangerous category, because an
interface can look functional while silently ignoring stored logic. In particular,
`guard_expression`, `filter_expression`, `depends_on` and the ontology dimension of
permission policy are live and fail closed. Derived versions now carry the workflow and
rule-evaluation metadata needed to reproduce a verdict.

- **List endpoints are paginated where the row count is a function of the customer's data, and
  deliberately not where it is not.** Six take a page and return a `pagination` block:
  `/ontologies/{id}/mappings` (the one that can realistically reach tens of thousands -- a row
  per mapped column), `/ontologies/{id}/rules`, `/ontologies`, `/data-sources`,
  `/data-sources/{id}/apis`, `/auth/users`, `/ontologies/{id}/knowledge/documents`, plus the two
  that already did and the three histories capped with an explicit `truncated` flag (events at
  500, attribute versions at 1 000). Not passing a `limit` still returns **everything**, which is
  the property the current screens rely on -- several read `array.length` for a tab count and
  several key their empty state off it, so a quiet default cap would have made those numbers
  wrong without making anything fail.

  The lists left unpaginated are ones whose length is bounded by *platform configuration* rather
  than by the customer's schema: `/permissions/roles`, `/permissions/policies`, `/tools`,
  `/tenants`, `/industry-blueprints`, the quota resources, and the static catalogs
  (`/units`, `/resolvers`, `/axiom-kinds`, `/source-types`, `/writeback-channels`). A pager on
  six built-in roles is ceremony, and the honest thing is to say so rather than to add one.
  `/conversations/{id}`'s messages are the one judgement call left: they are bounded by how long
  a person keeps typing, and a session long enough to need a page is not one this console has.

  The other half of the same sentence *was* a defect and is fixed: four endpoints
  (`/governance/audit-log`, `/governance/model-invocations`, `/governance/decisions`,
  `/tools/pending-reviews`) accepted a `limit` and forwarded it to SQL unclamped, and SQLite
  reads `LIMIT -1` as *no limit*. `?limit=-1` returned every row the deployment had ever
  written -- not a large response but an undeclared export endpoint. `tests/test_query_limit_clamping.py`
  holds that both ways (a live request with a hostile `limit`; a source check that every route
  taking a `limit` clamps it or hands it to something that does), and
  `tests/test_list_pagination.py` holds the two properties above: no limit returns everything,
  and `total` is a real count rather than the size of the page.

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
- **Credentials are still not encrypted at rest — but they no longer have to be stored.** A
  data source password or a model API key written straight into the row sits in the platform
  database in plaintext, so in that configuration that database *is* the credential store:
  protect it with filesystem permissions and database access controls. What changed is that
  there is now an alternative. Either value may be a **reference** instead of the secret:

      connection_uri = "env:CONTRACTS_DSN"
      api_key        = "file:/run/secrets/azure-openai-key"

  Resolved at connect time, in the one place every adapter goes through (`get_adapter`), and
  never on a display path — the settings page shows the reference, which is what tells an
  operator which secret a row is using. A reference that resolves to nothing raises rather than
  connecting with an empty credential, because an empty password fails as *"the password is
  wrong"* and sends the reader to the wrong problem.

  This is deliberately not encryption. A per-row encryption layer needs a crypto dependency the
  zero-dependency kernel does not carry, and one whose key is stored beside the ciphertext is
  worse than none because it looks like protection. Not storing the secret is the option that
  needs nothing, and it removes the row rather than obscuring it.
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
  client. That last gap is closed now -- see the frontend test runner below -- which is what
  made the missing normalisation testable rather than merely documented.
  `scripts/ui_smoke.py` covers the rest by inspection, reporting columns that are empty in
  every row; it needs a browser and a live instance, which is why it is a diagnostic rather
  than a gate. It has just had three blind spots closed — tabs (a page must put its active
  tab in the URL), tables that render only after a click, and cells holding an icon rather
  than text, which were reported as empty forever. A diagnostic that reports a standing
  false positive is teaching its reader to skim past the real findings.
- **The interface is bilingual, and most of what the server says can be translated with it; what is
  left is the CLI, and the refusals nobody has named yet.** Nineteen screens read from
  `i18n/messages/`; the sentences the server composes -- advice, gate verdicts, audit findings, the
  kernel's recommendation, the explanation of an instance -- now travel with a **stable code and the
  facts they are about**, so the console says them in the reader's language and falls back to the
  server's sentence only for a code it does not know. `scripts/i18n_audit.py` holds that in CI, and it
  now needs **no allowance at all**: `KNOWN_BACKEND_PROSE` is empty, kept because the mechanism is
  what notices the *next* untranslated server sentence, and an entry that matches nothing fails the
  run. **Failures** joined them: `error_codes.py` identifies a refusal from the sentence the domain
  layer raised, `decorate` puts `code` and `facts` beside `detail` on the way out, and the console
  says its own sentence when it knows the code. That covers authentication and authorization, the
  login and password rules, and the governance refusals a reader is most likely to meet -- publishing
  without confirmed mappings, editing a published ontology, an object with no source table.

  What is left is measurable rather than vague: of the 101 single-sentence Chinese refusals the
  backend raises, **51 are named**, and `tests/test_error_codes.py` holds that count as a ceiling so
  it can only fall. An unnamed refusal is not broken -- the console shows the server's sentence, which
  is true and readable, just in the other language. What is left is mostly internal invariants a user
  cannot reach at all (`instance_key` rejecting a malformed key, `schema` rejecting an empty DDL
  declaration, the extension registry rejecting a duplicate name), where a translation nobody reads
  would only look like coverage. The CLI's output is Chinese-first throughout and
  has no `--lang`; it is a tool for the operator who deployed the platform, not for the console's
  reader.

- **The frontend has a test runner now, and it covers the layer it can.** `npm test` runs
  vitest in `node` with **no DOM** -- no jsdom, no Testing Library, no component rendering --
  over the pure code between the wire and the screens: the payload normalisers (moved out of
  `api/index.ts` into `api/normalise.ts` so they could be), `label()`'s fallback, the sentence
  helpers in `i18n/text.ts`, and the lookup in `i18n/translate.ts`. That is where the silent
  failures lived: four times a table drew nothing for every row because a normaliser read
  `camelCase` off a `snake_case` payload, and nothing anywhere failed.
  What it deliberately does **not** cover is anything that needs a rendered component -- a
  mis-sorted list, a button wired to the wrong handler, layout. Those stay with
  `scripts/ui_smoke.py` and `scripts/i18n_audit.py`, which drive a real browser, and with
  `tests/test_frontend_type_agreement.py`, which holds each screen's fields to what its
  endpoint sends. Three checks, three questions, no overlap claimed.
- **Versioned migrations exist** (`migrations.py`). Alembic is deliberately not used:
  it depends on SQLAlchemy and would break the zero-dependency kernel, while its useful
  properties here—a version ledger and ordered application—are provided directly.
- **Not yet split into multiple PyPI distributions.** One package plus optional extras;
  the extras carry the eventual seams without freezing them.

See [`docs/architecture-debt.md`](architecture-debt.md) for located details and
[`ROADMAP.md`](../ROADMAP.md) for sequencing and blockers.
