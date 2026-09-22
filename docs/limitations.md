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
| **Relation classification depends on schema quality**: a database without foreign keys or NOT NULL gets the weakest classification | `relations.py` |
| **CSV and REST never infer foreign keys**: relation semantics require declared structure, and a relation resting on a naming coincidence cannot be explained | `file_adapter.py`, `rest_adapter.py` |
| **CSV reads the whole file per query**: fine at extract scale, wrong at warehouse scale | `file_adapter.py` |
| Type hierarchy caps at 16 levels; derivation at 5 passes | `type_hierarchy.py`, `derived_attributes.py` |
| **No full OWL/DL reasoning**, no open-world assumption | deliberate, see [ADR-0005](adr/0005-semantic-generality-ceiling.md) |

> Extension points are no longer on this list: data source adapters, rule functions,
> route policies and writeback executors are all registrable. See
> [the extension guide](extending.md).

## Engineering limitations

- No connection pooling; no unified transaction boundary across `connect()` calls.
- `platform_db` signatures are **all widened to `PlatformDb`** (context, path or string).
  The former `Path | str` annotation rejected contexts in type checkers even though
  runtime accepted it ([ADR-0010](adr/0010-platform-context-replaces-global-singleton.md)).
- The HTTP layer has 153 endpoints and **APIRouter extraction has started**
  (`routers/`); `api.py` still owns 40 of them.
- `frontend/src/types/index.ts` hand-mirrors backend models in 1143 lines; the backend
  emits both camelCase and snake_case.
- **Versioned migrations exist** (`migrations.py`). Alembic is deliberately not used:
  it depends on SQLAlchemy and would break the zero-dependency kernel, while its useful
  properties here—a version ledger and ordered application—are provided directly.
- **Not yet split into multiple PyPI distributions.** One package plus optional extras;
  the extras carry the eventual seams without freezing them.

See [`docs/architecture-debt.md`](architecture-debt.md) for located details and
[`ROADMAP.md`](../ROADMAP.md) for sequencing and blockers.
