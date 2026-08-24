"""One place that brings a platform database up to date.

The HTTP startup and the CLI's `init` each enumerated every feature schema, in two lists
that had to stay in step. They did not have to disagree loudly to cause damage: a schema
missing from one list produces a database where a feature returns empty results rather
than an error, and "the knowledge base has no entries" reads as a data problem for a long
time before anyone suspects a missing table.

So the sequence is declared once here, and both entry points call it.

## Order is part of the contract

Base tables, then feature tables, then migrations. Migrations run **last** because they
alter what the earlier steps created -- a backfill against a column that the current boot
is adding must see the column already there.

`seed_*` runs after migrations for the same reason in reverse: seeded rows must land in
the final shape, not in a shape a migration is about to change.

Stability: internal.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from .agent_roles import init_agent_role_schema
from .aggregation import init_aggregate_schema
from .auth import init_auth_schema
from .axioms import init_axiom_schema
from .conversations import init_conversation_schema
from .entity_resolution import init_entity_resolution_schema
from .events import init_event_schema
from .knowledge_documents import init_knowledge_schema
from .migrations import apply_migrations, init_migration_schema
from .quotas import init_quota_schema
from .sso import init_sso_schema
from .temporal import init_temporal_schema
from .workflow_permission import init_workflow_and_permission_schema

logger = logging.getLogger(__name__)

__all__ = ["FEATURE_SCHEMAS", "prepare_database"]

# Every feature schema, in dependency order. Enumerated rather than discovered: a plugin
# scanner would make "which tables should exist" depend on what happens to be importable,
# and a feature whose schema silently did not run returns empty results rather than
# failing.
FEATURE_SCHEMAS: tuple[Callable[[Any], None], ...] = (
    init_workflow_and_permission_schema,
    init_auth_schema,
    init_agent_role_schema,
    init_knowledge_schema,
    init_aggregate_schema,
    init_conversation_schema,
    init_event_schema,
    init_temporal_schema,
    init_entity_resolution_schema,
    init_axiom_schema,
    init_quota_schema,
    init_sso_schema,
    init_migration_schema,
)


def prepare_database(conn: Any) -> list[dict[str, Any]]:
    """Create every feature schema, then apply pending migrations.

    Returns what the migrations did, so a caller can log or report it. Schema creation is
    idempotent and reports nothing -- there is no useful distinction between "created" and
    "already there" on a boot.

    Failures are not swallowed: a missing table becomes a confusing 500 on first use rather
    than a clear startup failure, which is the trade this platform already refuses
    elsewhere.
    """
    for initialise in FEATURE_SCHEMAS:
        initialise(conn)
    return apply_migrations(conn)
