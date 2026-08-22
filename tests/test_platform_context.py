"""Platform context: the object that replaced the module-level singleton.

`database._platform_adapter` was a module-level global, so a process could hold
exactly one platform configuration. That blocked multi-tenancy (ADR-0006 needs a
connection bound to a tenant), and made it impossible to verify two dialects or
embed the kernel twice in one process.

These tests pin down the three properties that matter: instances are genuinely
independent, a thread-scoped binding does not leak, and every existing
`platform_db: Path | str` call site keeps working unchanged.
"""

from __future__ import annotations

import sqlite3
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from ontology_platform import database as database_module
from ontology_platform.context import (
    DEFAULT_TENANT,
    PlatformContext,
    configure_default_context,
    current_context,
    get_default_context,
    reset_default_context,
    resolve_context,
    use_context,
)
from ontology_platform.database import connect, get_platform_config, initialize_platform_db
from ontology_platform.metadata import list_data_sources, register_data_source


@pytest.fixture(autouse=True)
def _clean_default():
    """The default context is process-wide, so a test must not leak into the next."""
    reset_default_context()
    saved = database_module._platform_adapter
    database_module._platform_adapter = None
    yield
    reset_default_context()
    database_module._platform_adapter = saved


def _business_db(path: Path) -> str:
    sqlite3.connect(path).close()
    return str(path)


# -- Independence: the point of the change --


def test_two_contexts_in_one_process_are_isolated(tmp_path: Path) -> None:
    """Previously impossible: one global meant one configuration per process."""
    first = PlatformContext(connection_uri=str(tmp_path / "a.sqlite3"), tenant="acme")
    second = PlatformContext(connection_uri=str(tmp_path / "b.sqlite3"), tenant="globex")
    initialize_platform_db(first)
    initialize_platform_db(second)

    register_data_source(first, "acme 的源", "sqlite", _business_db(tmp_path / "biz-a.sqlite3"), domain="测试")
    register_data_source(second, "globex 的源", "sqlite", _business_db(tmp_path / "biz-b.sqlite3"), domain="测试")

    assert [item["name"] for item in list_data_sources(first)] == ["acme 的源"]
    assert [item["name"] for item in list_data_sources(second)] == ["globex 的源"]


def test_each_context_builds_its_own_adapter(tmp_path: Path) -> None:
    first = PlatformContext(connection_uri=str(tmp_path / "a.sqlite3"))
    second = PlatformContext(connection_uri=str(tmp_path / "b.sqlite3"))
    assert first.adapter is not second.adapter


def test_adapter_is_cached_per_context(tmp_path: Path) -> None:
    """Repeated connect() must not rebuild the adapter, matching the old global."""
    context = PlatformContext(connection_uri=str(tmp_path / "a.sqlite3"))
    assert context.adapter is context.adapter


def test_adapter_creation_is_thread_safe(tmp_path: Path) -> None:
    """FastAPI serves on a thread pool; two threads must not each build one."""
    context = PlatformContext(connection_uri=str(tmp_path / "a.sqlite3"))
    seen: list[object] = []
    barrier = threading.Barrier(8)

    def grab() -> None:
        barrier.wait()
        seen.append(context.adapter)

    threads = [threading.Thread(target=grab) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len({id(item) for item in seen}) == 1


def test_for_tenant_returns_a_sibling_without_mutating_the_original() -> None:
    """A request handler must not be able to re-tenant a context another is using."""
    context = PlatformContext(tenant="acme")
    derived = context.for_tenant("globex", schema="tenant_globex")
    assert derived.tenant == "globex"
    assert derived.schema == "tenant_globex"
    assert context.tenant == "acme"
    assert derived is not context


def test_default_tenant_is_applied_when_unset() -> None:
    assert PlatformContext().tenant == DEFAULT_TENANT
    assert PlatformContext(tenant="").for_tenant("").tenant == DEFAULT_TENANT


def test_describe_redacts_the_connection_uri() -> None:
    """The URI carries credentials, so diagnostics must not leak it."""
    context = PlatformContext(db_type="mysql", connection_uri="mysql://root:secret@db.internal:3306/platform")
    described = context.describe()
    assert "secret" not in str(described)
    assert described["tenant"] == DEFAULT_TENANT


# -- resolve_context: what keeps 156 old signatures working --


def test_a_context_resolves_to_itself() -> None:
    context = PlatformContext()
    assert resolve_context(context) is context


@pytest.mark.parametrize("source", ["", None])
def test_empty_input_falls_back_to_the_default(source, tmp_path: Path) -> None:
    default = configure_default_context("sqlite", str(tmp_path / "default.sqlite3"))
    assert resolve_context(source) is default


def test_a_path_resolves_to_a_sqlite_context(tmp_path: Path) -> None:
    """The old connect(path) meaning must be preserved exactly."""
    path = tmp_path / "explicit.sqlite3"
    context = resolve_context(path)
    assert context.db_type == "sqlite"
    assert context.connection_uri == str(path)


def test_an_explicit_path_wins_over_the_default(tmp_path: Path) -> None:
    """Otherwise a test passing tmp_path would silently hit the configured default."""
    configure_default_context("sqlite", str(tmp_path / "default.sqlite3"))
    resolved = resolve_context(tmp_path / "explicit.sqlite3")
    assert resolved.connection_uri.endswith("explicit.sqlite3")


def test_resolution_without_any_configuration_still_works() -> None:
    """A library-only import with no setup must not raise."""
    assert resolve_context().db_type == "sqlite"


# -- Thread-scoped binding --


def test_use_context_binds_only_the_current_thread(tmp_path: Path) -> None:
    """The old global would have let one request's binding affect another's."""
    default = configure_default_context("sqlite", str(tmp_path / "default.sqlite3"))
    other = PlatformContext(connection_uri=str(tmp_path / "other.sqlite3"), tenant="other")

    seen: dict[str, str] = {}

    def bound() -> None:
        with use_context(other):
            seen["bound"] = current_context().tenant

    def unbound() -> None:
        seen["unbound"] = current_context().tenant

    first = threading.Thread(target=bound)
    first.start()
    first.join()
    second = threading.Thread(target=unbound)
    second.start()
    second.join()

    assert seen["bound"] == "other"
    assert seen["unbound"] == default.tenant


def test_binding_is_restored_after_the_block(tmp_path: Path) -> None:
    configure_default_context("sqlite", str(tmp_path / "default.sqlite3"))
    other = PlatformContext(tenant="other")
    with use_context(other):
        assert current_context().tenant == "other"
    assert current_context().tenant == DEFAULT_TENANT


def test_binding_is_restored_even_when_the_block_raises(tmp_path: Path) -> None:
    configure_default_context("sqlite", str(tmp_path / "default.sqlite3"))
    with pytest.raises(RuntimeError):
        with use_context(PlatformContext(tenant="other")):
            raise RuntimeError("boom")
    assert current_context().tenant == DEFAULT_TENANT


def test_nested_bindings_unwind_in_order() -> None:
    outer = PlatformContext(tenant="outer")
    inner = PlatformContext(tenant="inner")
    with use_context(outer):
        with use_context(inner):
            assert current_context().tenant == "inner"
        assert current_context().tenant == "outer"


def test_bound_context_is_used_by_connect(tmp_path: Path) -> None:
    """The binding must actually reach the connection, not merely be readable."""
    bound = PlatformContext(connection_uri=str(tmp_path / "bound.sqlite3"))
    initialize_platform_db(bound)
    register_data_source(bound, "绑定源", "sqlite", _business_db(tmp_path / "biz.sqlite3"), domain="测试")
    with use_context(bound):
        with connect() as conn:
            rows = conn.execute("select name from data_source").fetchall()
    assert [row["name"] for row in rows] == ["绑定源"]


# -- Backwards compatibility --


def test_configure_platform_db_sets_the_default_context(tmp_path: Path) -> None:
    """Application startup already calls this; it must now populate a context."""
    database_module.configure_platform_db("sqlite", str(tmp_path / "configured.sqlite3"))
    default = get_default_context()
    assert default is not None
    assert default.connection_uri.endswith("configured.sqlite3")


def test_legacy_adapter_global_points_at_the_same_adapter(tmp_path: Path) -> None:
    """A caller reaching for the old global must not land on a different connection."""
    database_module.configure_platform_db("sqlite", str(tmp_path / "configured.sqlite3"))
    assert database_module._platform_adapter is get_default_context().adapter


def test_get_platform_config_reflects_the_bound_context(tmp_path: Path) -> None:
    database_module.configure_platform_db("sqlite", str(tmp_path / "configured.sqlite3"))
    other = PlatformContext(db_type="postgresql", connection_uri="postgresql://localhost:5432/x")
    with use_context(other):
        assert get_platform_config().db_type == "postgresql"
    assert get_platform_config().db_type == "sqlite"


def test_path_based_calls_behave_as_before(tmp_path: Path) -> None:
    """The whole point of resolve_context: existing call sites are untouched."""
    platform_db = tmp_path / "legacy.sqlite3"
    initialize_platform_db(platform_db)
    register_data_source(platform_db, "遗留调用", "sqlite", _business_db(tmp_path / "biz.sqlite3"), domain="测试")
    assert [item["name"] for item in list_data_sources(platform_db)] == ["遗留调用"]


def test_mixed_dialect_contexts_can_coexist(tmp_path: Path) -> None:
    """Verifying two dialects in one process was previously impossible."""
    sqlite_context = PlatformContext(connection_uri=str(tmp_path / "a.sqlite3"))
    postgres_context = PlatformContext(
        db_type="postgresql", connection_uri="postgresql://localhost:5432/ontology_platform"
    )
    assert sqlite_context.db_type == "sqlite"
    assert postgres_context.db_type == "postgresql"
    # Only the SQLite one is exercised; building the other must not disturb it.
    initialize_platform_db(sqlite_context)
    with connect(sqlite_context) as conn:
        assert conn.execute("select count(*) as c from data_source").fetchone()["c"] == 0
