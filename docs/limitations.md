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
- **Versioned migrations exist** (`migrations.py`). Alembic is deliberately not used:
  it depends on SQLAlchemy and would break the zero-dependency kernel, while its useful
  properties here—a version ledger and ordered application—are provided directly.
- **Not yet split into multiple PyPI distributions.** One package plus optional extras;
  the extras carry the eventual seams without freezing them.

See [`docs/architecture-debt.md`](architecture-debt.md) for located details and
[`ROADMAP.md`](../ROADMAP.md) for sequencing and blockers.
