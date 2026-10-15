# Extending Aletheia

No fork required. Ten extension points are open as runtime registries: data source
adapters, rule functions, route policies, writeback executors, retrieval backends,
embedding models, instance resolvers, units, SQL dialects and database writeback targets.

> ⚠️ **Stability: all of these are experimental.** Signatures may change between minor
> releases before 1.0, and changes are recorded in the [CHANGELOG](../CHANGELOG.md). The
> reasoning is in [ADR-0007](adr/0007-extension-registry-without-api-stability.md).
>
> **To prove your implementation conforms, run the conformance contract** — it ships with
> the package, so you do not need this repository or pytest:
>
> ```bash
> aletheia verify --list
> aletheia verify data_source_adapter --source-type mydb --uri "mydb://host/db" --table contracts
> ```
>
> This replaced an earlier instruction to run `tests/test_extension_registry.py`. A test
> file is not in the wheel, so telling an integrator to run it was telling them to obtain
> the platform's source — the thing ADR-0016 exists to avoid. See
> [§14](#14-verify-your-implementation-the-conformance-contract).

Two ways to register:

- **In-process** — call `register_*()` from your application's startup code
- **As a plugin** — declare entry points; installing it is enough, the platform discovers
  it. See [Packaging as a plugin](#packaging-as-a-plugin-entry-points).

---

## 1. Data source adapters

For a database the platform does not support yet.

```python
from ontology_platform.adapters import register_adapter

class OracleAdapter:
    def test_connection(self, connection_uri: str) -> dict:
        # returns {"sourceType", "reachable", "status", "message"}
        ...

    def scan(self, connection_uri: str) -> list:
        # returns SourceTableInfo entries: tables, columns, foreign keys
        ...

    def runtime(self, connection_uri: str):
        # context manager yielding a RuntimeDatabase
        ...

register_adapter("oracle", OracleAdapter, aliases=("ora",))
```

Implement the `DatabaseAdapter` protocol (see `adapters.py`). What you register is a
**factory**, not an instance — construction is cheap and every call is treated as an
independent object.

> For a new *SQL* database you almost certainly do not want this: see
> [§10](#10-connecting-a-new-sql-database), where the whole integration is a declaration.

Registered names: `supported_source_types()`

## 2. Rule functions

So a business rule expression can call domain-specific predicates.

```python
from ontology_platform.semantic_kernel import register_rule_function

def days_between(start, end) -> int:
    ...

register_rule_function("days_between", days_between)
# rules may now write: days_between(sign_date, today) <= 15
```

**Constraints, and why each one exists:**

- The name must be a valid identifier and must not start with an underscore. The sandbox
  resolves `ast.Name` nodes, so a dotted name can never bind; an underscore prefix would
  collide with the sandbox's own internal names.
- **Registration grants the right to be called; it does not widen the AST allowlist.**
  Dunder attribute access, lambdas, comprehensions, conditional expressions and keyword
  arguments stay forbidden.
- **Your function must be pure and must not raise.** The rule engine is fail-closed
  ([ADR-0002](adr/0002-rule-engine-fail-closed.md)): a function that raises makes the rule
  count as *not passed*, which blocks **every instance** of the object it scopes.
- Registered functions take precedence over row data when the two are merged, so a column
  named `sum` cannot shadow the `sum` function.

Registered names: `allowed_rule_function_names()`

## 3. Route policies

**If your plugin adds API endpoints, you must register a policy for them.** Otherwise they
fall through to the "unregistered routes are admin-only" default, which looks to a
non-admin user like the endpoint does not exist.

```python
from ontology_platform.access_policy import register_route_policy
from ontology_platform.auth import CAP_READ, CAP_EXECUTE

register_route_policy(["GET"], r"/oracle/tables.*", CAP_READ, "Browse Oracle tables")
register_route_policy(["POST"], r"/oracle/sync", CAP_EXECUTE, "Trigger a sync")
```

Paths are regular expressions, anchored automatically. Plugin rules are matched **before**
the built-in table; anything they miss still falls through to the built-in table and
finally to the admin default — deny-by-default does not weaken because a plugin exists.

Capabilities: `platform:read`, `platform:write`, `governance:review`, `governance:publish`,
`automation:execute`, `platform:admin`. An unknown capability is rejected at registration
time rather than silently matching nothing.

Effective policies: `describe_policy()`, each row marked `builtin` or `plugin`.

## 4. Writeback executors

A writeback channel other than HTTP — a message queue, RPC, direct database write, a
stored procedure.

```python
from ontology_platform.automation import ExecutionRequest, register_executor

def publish_to_mq(request: ExecutionRequest) -> dict:
    # request.target / .plan / .timeout_seconds / .headers
    # The return value is written verbatim into the decision record's execution.remote,
    # so it should carry what an auditor will need.
    return {"published": True, "messageId": "..."}

register_executor("amqp", publish_to_mq)
```

Dispatch is by the scheme of the data source's `apiBaseUrl`. Because the return value
becomes part of the decision trail, it **has to be what an auditor needs** — not a debug
dump and not an empty `{}`.

Registered names: `supported_executor_schemes()`

---

## Packaging as a plugin (entry points)

```toml
# your plugin project's pyproject.toml
[project.entry-points."aletheia.adapters"]
oracle = "my_plugin.adapters:OracleAdapter"

[project.entry-points."aletheia.rule_functions"]
days_between = "my_plugin.rules:days_between"

[project.entry-points."aletheia.executors"]
amqp = "my_plugin.channels:publish_to_mq"

[project.entry-points."aletheia.access_policies"]
oracle = "my_plugin.policies:route_policies"
```

The target of `aletheia.access_policies` is a callable returning a sequence of
`(methods, path_regex, capability, description)` tuples.

Installing the package is enough; the platform discovers it at import time. **A plugin that
fails to load is logged and skipped, never fatal** — one broken plugin must not stop the
whole system from starting, and a platform that refuses to boot is harder to diagnose than
a feature that reports itself as unavailable.

| Entry point group | What you register |
|---|---|
| `aletheia.adapters` | data source adapter factory |
| `aletheia.rule_functions` | rule function |
| `aletheia.executors` | writeback executor |
| `aletheia.access_policies` | callable returning policy tuples |
| `aletheia.retrieval_backends` | retrieval backend |
| `aletheia.embedding_models` | embedding model |
| `aletheia.instance_resolvers` | instance resolver |

## 5. Retrieval backends and embedding models

The defaults are **zero-dependency** (BM25 + hashed n-grams) so a fresh clone runs. A
deployment that needs better recall registers its own.

```python
from ontology_platform.retrieval import (
    RetrievalHit, register_retrieval_backend, register_embedding_model,
)

def rank_with_pgvector(query: str, entries, limit: int) -> list[RetrievalHit]:
    # `entries` has already been narrowed by ontology anchoring. A backend may not widen the
    # candidate set past that anchoring -- it is the precondition for a citation being
    # attributable at all (ADR-0009).
    ...

register_retrieval_backend("pgvector", rank_with_pgvector)
register_embedding_model("bge-m3", lambda text: my_model.encode(text).tolist())
```

**The key constraint:** you receive an **already anchored** candidate set. Your job is to
order it. Widening it turns citations from "supported by" into "looks similar", which is the
distinction the whole product rests on.

Registered names: `supported_retrieval_backends()`, `supported_embedding_models()`

## 6. Multi-tenant context

An extension that reads platform data must go through the context rather than a hardcoded
path, or in a multi-tenant deployment it will read the wrong tenant's data.

```python
from ontology_platform.context import use_context
from ontology_platform.tenancy import tenant_context, require_tenant, scope_query

ctx = tenant_context(base_context, "acme")
with use_context(ctx):
    tenant = require_tenant()          # raises when the tenant cannot be determined
    query, params = scope_query("select * from data_source", ())
    with ctx.connect() as conn:
        rows = conn.execute(query, params).fetchall()
```

**`require_tenant()` is fail-closed.** If your extension must also run without a context,
handle `TenantError` explicitly — never degrade to "read every tenant".

## 7. Instance resolvers

Decides *which rows are instances of this business object*. Four ship in the box:
`single_table` (the default), `joined_tables`, `discriminated`, `custom_sql`.

```python
from ontology_platform.instance_resolver import (
    InstanceResolver, ResolverSpec, register_resolver,
)

class CrossSourceResolver(InstanceResolver):
    kind = "cross_source"

    def validate(self) -> None:
        ...  # check the configuration at construction, not when a verdict needs it

    def fetch(self, runtime, instance_id):
        ...  # a complete record, or None

    def list_ids(self, runtime, limit=50):
        ...  # tokens that fetch() must accept

    def columns(self, runtime):
        ...  # every name a rule may reference

register_resolver("cross_source", CrossSourceResolver)
```

**The part of the contract most often got wrong: `list_ids()` and `fetch()` must round-trip.**
Batch assessment depends on it — if `list_ids` returns an id your `fetch` refuses, the batch
reports "instance not found" instead of a verdict, while single-instance assessment looks
perfectly healthy. The contract checks every pair explicitly for that reason.

Verify: `aletheia verify instance_resolver` (see [§14](#14-verify-your-implementation-the-conformance-contract)).

### Identifiers must be validated, not merely quoted

Resolver configuration is supplied by an operator and ends up inside SQL text (join
clauses, discriminator columns). Use `validate_identifier()` — **a quoted-but-unvalidated
name in a join clause is still a hazard**.

### The trust boundary of `custom_sql`

`custom_sql` executes operator-supplied SQL **with the data source's own privileges**. The
platform imposes exactly three restrictions: it must begin with `select`/`with`, it must
contain no semicolon, and any identifier columns are validated. This is a **deliberate
trust decision** — use a read-only account when connecting a legacy system.

## 8. Units and dimensions

An attribute may declare a unit; comparison within a dimension converts automatically. The
built-in set covers currency scales, durations, mass, length and ratios — deliberately
small and domain-neutral, because a shipped industry-specific unit list is the same mistake
as a shipped industry vocabulary ([ADR-0003](adr/0003-no-builtin-domain-vocabulary.md)).

```python
from ontology_platform.derived_attributes import Unit, register_unit

register_unit(Unit(code="jin", name="斤", dimension="mass", to_canonical=500.0))
```

`to_canonical` is "how many canonical units of this dimension is one of mine". Conversion
always goes through the canonical unit rather than pairwise factors: N units need N factors
instead of N², and there is one place to check.

Overriding an existing unit requires an explicit `replace=True` — **silently redefining
"tonne" changes the meaning of every value already stored, and leaves no record of having
done so**.

A new dimension needs exactly one unit with `to_canonical == 1.0`; without it nothing in
that dimension can be converted.

### Cross-dimension conversion is refused

`convert(1, "day", "kilogram")` raises rather than returning 1. It almost always means the
model is wrong, and silently passing the number through would make every verdict derived
from it look entirely valid.

## 9. Tables: `SchemaBundle`

A plugin's own tables are declared through `SchemaBundle`, not by writing another
"pick the DDL by dialect and execute it" loop.

```python
from ontology_platform.schema import SchemaBundle

SCHEMA = SchemaBundle(
    name="my_plugin",
    tables=(
        {
            "sqlite": "create table if not exists my_table (id integer primary key, note text not null default '')",
            "postgresql": "create table if not exists my_table (id serial primary key, note text not null default '')",
            "mysql": "create table if not exists my_table (id integer primary key auto_increment, note text)",
        },
    ),
    indexes=(
        {
            "sqlite": "create index if not exists idx_my_table_note on my_table (note)",
            "postgresql": "create index if not exists idx_my_table_note on my_table (note)",
            # MySQL has no `create index if not exists`
            "mysql": "create index idx_my_table_note on my_table (note)",
        },
    ),
    table_names=("my_table",),
)
SCHEMA.verify_declared_names()   # checks the declaration against the DDL at import


def init_my_schema(conn):
    SCHEMA.apply(conn)
```

### Why tables and indexes are declared separately

They fail differently. `create table if not exists` is idempotent on all three dialects,
while MySQL has no `create index if not exists` and errors on a second run. Putting both in
one list forces every caller to sniff statement text to decide whether an error was
expected — and that sniffing is exactly the check that drifted between eight copies of this
code.

### Probe for a table; do not catch the exception

Where a feature's schema is optional, use `SCHEMA.has_tables(conn)` rather than
`try/except`. On PostgreSQL a failed statement aborts the entire transaction, so every
subsequent command on that connection fails with `InFailedSqlTransaction`
(see [ADR-0004](adr/0004-three-platform-dialects.md)).

`verify_declared_names()` guards a different mistake: changing the DDL and forgetting
`table_names` makes the probe report "not configured" for a table that exists, so **the
feature silently returns empty results instead of failing**.

## 10. Connecting a new SQL database

**You do not need to write an adapter.** `information_schema` is a standard and the scanner
is fully shared; the differences are six, and they are declared as a `SqlDialect`:

```python
from ontology_platform.generic_sql_adapter import DriverSpec, register_sql_source
from ontology_platform.sql_dialects import SqlDialect, get_dialect, register_dialect

register_dialect(SqlDialect(
    name="gaussdb",
    current_schema_expression="current_schema()",  # or database() / sys_context(...)
    quote_open='"', quote_close='"',
    paramstyle="format",                            # format(%s) / qmark(?) / numeric(:1)
    row_limit_style="limit_offset",                 # or fetch_first (Oracle / SQL Server / 达梦)
    catalog_uppercases_identifiers=False,           # True for Oracle / 达梦
    foreign_keys_via_referenced_columns=False,      # True for MySQL
))

register_sql_source(DriverSpec(
    source_type="gaussdb",
    dialect=get_dialect("gaussdb"),
    module="psycopg2",
    install_hint="Connecting GaussDB requires psycopg2.",
    passes_uri_positionally=True,   # the driver takes the whole URI as its first positional
))
```

That is the whole integration. Metadata scanning, column profiling, foreign key discovery,
instance resolution, every rule capability and runtime reads all follow from it.

### Three things that are easy to get wrong

**Getting `catalog_uppercases_identifiers` wrong fails silently.** Oracle and 达梦
upper-case unquoted identifiers in the catalog, so a lookup for `contracts` matches nothing
— the table then appears to have **no columns** rather than raising.

**Row limiting syntax.** A hardcoded `limit n` fails on Oracle, SQL Server and 达梦, and
column profiling swallows query errors — so every column profiles as empty instead of
raising.

**The connection-string parameter name differs per driver:** psycopg calls it `conninfo`,
oracledb calls it `dsn`, sqlite3 takes it positionally. Guessing wrong yields
`invalid connection option "dsn"`, which reads like a misconfiguration rather than a wrong
declaration. Hence `passes_uri_positionally`.

### Bundled declarations

Oracle, SQL Server, 达梦, KingbaseES and openGauss are declared in
`generic_sql_adapter.BUNDLED_SPECS`; `register_bundled_sql_sources()` activates them once
the driver is installed, and `aletheia doctor` lists each one's driver and install hint.

> ⚠️ These declarations are **not exercised in CI**: the drivers and client libraries cannot
> be installed there. The generic path itself is proven against a real PostgreSQL as "a
> database the platform has no dedicated adapter for".

## 11. Database writeback targets

The most dangerous extension point, so it carries the strictest constraints.

```python
from ontology_platform.db_executors import DatabaseTarget, SqlWriteback, register_database_target

register_database_target(DatabaseTarget(
    scheme="orders",
    connection_uri="postgresql://user:pass@host/orders",
    dialect_name="postgresql",
    driver_module="psycopg2",
    writebacks={
        "approve": SqlWriteback(
            name="approve", kind="update", table="contracts",
            columns=("status",), key_columns=("id",),
            dialect_name="postgresql",
        ),
    },
))
```

`orders://` is now an available writeback scheme, and the last segment of the operation path
selects the writeback by name.

### What the platform refuses

| Refused | Why |
|---|---|
| update/delete without `keyColumns` | a missing WHERE rewrites the whole table, and the decision record would not show that it did |
| a semicolon, or multiple statements | bypasses single-statement auditing |
| DDL and privilege statements (drop/alter/grant…) | automation advances business state; it does not change structure |
| delete without an explicit `allowDelete=True` | destroying data deserves its own authorisation decision |
| a missing parameter value | silently becoming NULL is how "the update cleared a column it should not have touched" happens |
| a connection string supplied by the request | that would let a caller point automation at any reachable database |

**The statement supplies identifiers, the request supplies values, and values are always
bound.** Building SQL from an operation payload creates an injection surface reachable from
an HTTP request body.

**Zero affected rows counts as failure by default**: an UPDATE matching nothing means the
target instance is absent or the condition is wrong. A genuinely idempotent writeback
declares `requireAffectedRows=False` explicitly.

## 12. Declaring a REST data source

A REST response has no discoverable schema, so fields must be declared — a schema sampled
from one response changes with the next, and a verdict citing it cannot be reproduced.

```python
from ontology_platform.rest_adapter import RestResource, RestSpec, register_rest_source

register_rest_source(RestSpec(
    source_type="crm",
    resources=(
        RestResource(
            name="customers",
            list_path="/api/customers",
            detail_path="/api/customers/{id}",
            primary_key="id",
            fields=("id", "name", "credit_status"),
            field_types={"id": "integer"},
            items_path="data.items",   # where the row list sits when the response is wrapped
        ),
    ),
))
```

With an existing OpenAPI document, use `register_openapi_source(source_type, document)` —
that is still a declaration, just one written by the API's owner.

**Undeclared fields are not exposed**: the declaration is the contract, and passing through
whatever the response happens to contain would make the names available to rules depend on
today's payload.

## 13. A consequence on CSV and REST sources

Neither source type infers foreign keys, so **a rule that references a related object
fails closed**. The contract-management blueprint ships

```
customer.credit_status != 'blacklist'
```

On a CSV source that evaluates to `name 'customer' is not defined` and is recorded as *not
passed*, rather than passing quietly.

**That is correct behaviour, not a defect.** The rule references an association that does not
exist here, and passing silently would be clearing data that was never checked
([ADR-0002](adr/0002-rule-engine-fail-closed.md)).

Three ways to deal with it, in order of preference:

1. Declare the real relationship — `describe_file_source()` proposes foreign key candidates
   for a modeller to confirm
2. Move the rule's scope to an object that does have the association
3. Give the rule a validity period, or use a `guard_expression`, so it participates only
   when its precondition holds

`aletheia assess` names the missing identifier in `evaluationError`, so this case is
discoverable rather than turning into an inexplicable verdict.

## 14. Verify your implementation: the conformance contract

**Run the contract before production.** It ships with the package — no clone, no pytest:

```bash
aletheia verify --list                                    # every contract and its extension point
aletheia verify data_source_adapter --source-type mydb --uri "mydb://host/db" --table contracts
aletheia verify retrieval_backend --name pgvector
aletheia verify embedding_model --name my-model
```

It exits non-zero on failure, so it works directly as a CI gate.

Contracts that need a live subject (instance resolvers, writeback executors) are called in
code:

```python
from ontology_platform.conformance import check_instance_resolver
from ontology_platform.adapters import get_adapter

with get_adapter("sqlite").runtime("/path/to/db.sqlite3") as runtime:
    report = check_instance_resolver(MyResolver(spec), runtime, subject="my_resolver")

print(report.summary())
report.raise_for_failures()   # raises ConformanceError (an AssertionError), usable in tests
```

### What the contracts actually check

**Only properties the kernel truly depends on.** Each one corresponds to a concrete wrong
outcome, and a failure states that outcome — an implementer should never have to guess why a
rule matters.

| Contract | Checks | The one most often got wrong |
|---|:--:|---|
| `instance_resolver` | 9 | tokens from `list_ids()` must be accepted by your own `fetch()` |
| `data_source_adapter` | 9 | keys from `fetch_primary_keys()` must be retrievable by `fetch_one()` |
| `retrieval_backend` | 6 | must not return entries outside the candidate set |
| `embedding_model` | 4 | the same input must produce the same vector |
| `writeback_executor` | 3 | the result must state what the writeback did |

### Required versus advisory

A `required` failure means **wrong results under normal operation**; `advisory` means it
works but is missing a capability (a non-tabular source cannot report `tables()`, so drift
detection does not cover it). The two are kept apart deliberately: mixing them produces a
report unusable for deciding whether to ship.

### The contract is not an API stability promise

The registries remain experimental
([ADR-0007](adr/0007-extension-registry-without-api-stability.md)). What is stable is the
**behaviour you are required to have**, not the signature that requires it.

> Every implementation inside the kernel (the four resolvers, the SQLite/CSV adapters, the
> BM25 and embedding retrieval backends, the database writeback executors) runs the same
> contracts in CI. A contract that only holds for its author's example drifts into
> demanding something the platform itself does not do — and then the first integrator to run
> it is failed by our own doing.

## 15. One object across two data sources

Customer master data in the CRM, contracts in the ERP, both with a "customer" but different
primary keys. Declare what makes them the same:

```python
from ontology_platform.entity_resolution import (
    CrossSourceLink, MatchKey, declare_cross_source_link,
)

declare_cross_source_link(platform_db, ontology_id, CrossSourceLink(
    name="crm_to_erp",
    primary_object_code="customer",          # primary source: identity comes from it
    secondary_data_source_id=2,              # secondary source
    secondary_table="clients",
    match_keys=(MatchKey(primary_column="tax_id", secondary_column="taxpayer_no"),),
    prefix="erp",                            # secondary columns appear as erp_credit_limit
))
```

Rules may now write `erp_credit_limit > 0` directly.

Cross-source aggregates work the same way, naming the target source on `AggregateSpec`:

```python
AggregateSpec(
    name="erp_order_total", function="sum",
    target_table="orders", target_column="client_taxpayer_no",
    group_column="tax_id", value_column="amount",
    target_data_source_id=2,        # 0 (the default) means this source
)
```

### Why matching keys must be declared

A cross-source verdict puts "these two rows are the same instance" into its decision chain.
**If that judgement cannot be interrogated, every conclusion resting on it is
unexplainable** — the answer to "why was this contract blocked" becomes "because we believe
these two rows are the same customer".

So the platform does **not** do similarity matching, edit distance or ML entity linking:
those make the verdict move with a threshold, and none of them can answer "why are these two
the same".

Normalisation covers only the deterministic part: trim, case-fold, and render as text (a
`varchar` in the CRM compared against a `bigint` in the ERP matches nothing if compared in
native types).

### Three refusals that will surprise you

| Situation | What the platform does | Why |
|---|---|---|
| the secondary matches several rows | **refuses** rather than taking the first | taking one applies the verdict to an arbitrarily chosen record, and the result looks normal |
| both sides have a same-named field with different values | **marks a conflict**; a rule referencing it fails closed | nobody can say which side is right |
| matching fails | **injects nothing** | injecting None makes `erp_x > 0` false, indistinguishable from a real violation |

Where taking any row is genuinely acceptable, declare `require_unique=False`; where one side
should win, declare `merge_strategy="prefer_primary"` / `"prefer_secondary"` — the choice is
recorded, because otherwise nobody can explain afterwards which value was used.

### No transitive inference

Declaring A↔B and B↔C does **not** produce A↔C. That would introduce a correspondence nobody
declared, and it would enter the decision chain just the same. Declare A↔C explicitly if you
need it.

Full reasoning in [ADR-0018](adr/0018-cross-source-entity-resolution.md).

## 16. Adding a column to a plugin's table

`create table if not exists` does **nothing** to a table that already exists, so a new field
applies only to fresh deployments — it works on the machine it was developed on, stops
working after an upgrade, and reports nothing.

Declare it with `ColumnAddition`:

```python
from ontology_platform.schema import ColumnAddition, SchemaBundle

SCHEMA = SchemaBundle(
    name="my_plugin",
    tables=(...),
    table_names=("my_table",),
    columns=(
        ColumnAddition(
            table="my_table", column="new_field",
            sqlite_type="integer not null default 0",
            postgresql_type="integer not null default 0",
            mysql_type="integer not null default 0",
        ),
    ),
)
```

**The default must equal the existing behaviour**, or the upgrade changes the meaning of
data already stored.

Adding a column probes the catalog first and then runs the DDL, so it is idempotent and does
not depend on a driver's error text — catching an exception to decide whether a column
exists aborts the whole transaction on PostgreSQL (as in ADR-0004).

## Extension points not yet open

The following are in the [ROADMAP](../ROADMAP.md) and have **no** extension mechanism:

- Cross-source *instance resolution* — see [§15](#15-one-object-across-two-data-sources),
  where the declaration-based form is available
- Authentication backends (SSO / LDAP)
- Event hooks
- Channel integrations
- Relation classification strategy (currently a fixed structural rule — see
  [ADR-0012](adr/0012-cross-object-aggregation-and-relation-semantics.md))
- Aggregate functions (`sum`/`count`/`min`/`max`/`avg`; use a `custom_sql` resolver when you
  need window functions)

> **Event hooks are withheld on purpose.** Events are a record, not a trigger: an event that
> triggers automation would make replaying history re-execute business actions. If you want
> event-driven action, go through `automation.py`'s writeback executors, driven by a decision
> ([ADR-0014](adr/0014-type-hierarchy-and-business-events.md)).

Their shape depends on a second real use case, and freezing it now would produce the wrong
API ([ADR-0001](adr/0001-three-repo-distribution.md) Consequences).
