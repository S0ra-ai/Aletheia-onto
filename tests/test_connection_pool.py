"""Reusing platform-database connections without ever handing one to the wrong caller.

`docs/limitations.md` said "no connection pooling" and gave a reason that was correct and did
not scale down to a design: connections here are tenant-scoped, so a shared pool would hand a
caller another tenant's data. The premise is right -- and the conclusion is not "do not pool",
it is "key the pool by everything the connection's session state depends on".

That key is `(db type, connection URI, schema)`, which is exactly the set of things each adapter
configures when it opens a connection: PostgreSQL points `search_path` at the tenant's schema,
MySQL fixes the session time zone. Two contexts that differ in any of the three would be
*pointed at different data* by the same connection, so borrowing for one misses the entry the
other left.

What is checked here is the safety, not the speed. A pool that is fast and leaks across tenants
is worse than no pool, and the leak would show up as somebody else's data in a query result --
the one failure this platform exists to make impossible.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from ontology_platform.connection_pool import ConnectionPool


class _FakeConnection:
    """A driver connection, in the three respects the pool actually touches."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.closed = False
        self.rollbacks = 0
        self.rollback_fails = False

    def rollback(self) -> None:
        self.rollbacks += 1
        if self.rollback_fails:
            raise RuntimeError("rollback failed")

    def close(self) -> None:
        self.closed = True

    def __repr__(self) -> str:  # pragma: no cover - failure messages only
        return f"<conn {self.name}>"


def _factory(counter: list[int], prefix: str = "conn"):
    def make() -> _FakeConnection:
        counter[0] += 1
        return _FakeConnection(f"{prefix}-{counter[0]}")

    return make


def test_an_idle_connection_is_reused_for_the_same_key() -> None:
    pool = ConnectionPool(size=4)
    opened: list[int] = [0]
    key = ("postgresql", "postgresql://h/db", "acme")

    first = pool.acquire(key, _factory(opened))
    pool.release(key, first)
    second = pool.acquire(key, _factory(opened))

    assert second is first, "同一个 key 应该拿回同一条连接"
    assert opened[0] == 1
    assert pool.reused == 1


def test_connections_are_never_shared_across_keys() -> None:
    """The property the whole design turns on.

    A connection opened for one schema has that schema's `search_path` set on it. Handing it to
    a caller who asked for another schema is not a performance mistake -- it is a cross-tenant
    read, and it would come back as somebody else's rows with nothing to indicate it.
    """
    pool = ConnectionPool(size=4)
    opened: list[int] = [0]
    acme = ("postgresql", "postgresql://h/db", "acme")
    globex = ("postgresql", "postgresql://h/db", "globex")

    a = pool.acquire(acme, _factory(opened, "acme"))
    pool.release(acme, a)
    b = pool.acquire(globex, _factory(opened, "globex"))

    assert b is not a
    assert b.name.startswith("globex")


def test_the_key_includes_the_uri_not_only_the_schema() -> None:
    """Two databases can carry the same schema name, and a pool keyed on the name alone would
    hand one's connection to the other -- the same leak, one level out."""
    pool = ConnectionPool(size=4)
    opened: list[int] = [0]
    first = ("postgresql", "postgresql://a/db", "public")
    second = ("postgresql", "postgresql://b/db", "public")

    a = pool.acquire(first, _factory(opened, "a"))
    pool.release(first, a)
    b = pool.acquire(second, _factory(opened, "b"))

    assert b is not a


def test_a_returned_connection_has_no_open_transaction() -> None:
    """`__exit__` settles the transaction, and this is the belt to that pair of braces.

    A caller that never entered the `with` block can still leave one open, and the next borrower
    inheriting it would see a defect surface in somebody else's request -- uncommitted rows that
    appear or vanish depending on what ran before.
    """
    pool = ConnectionPool(size=4)
    opened: list[int] = [0]
    key = ("postgresql", "postgresql://h/db", "")

    connection = pool.acquire(key, _factory(opened))
    pool.release(key, connection)

    assert connection.rollbacks == 1, "归还前必须回滚，否则下一个借用者会继承未结束的事务"


def test_a_connection_that_cannot_be_rolled_back_is_closed_rather_than_returned() -> None:
    """A failed rollback leaves the connection in an unknown state.

    Returning it would mean the next borrower's first query runs against whatever the previous
    one left behind. Closing it costs a handshake and cannot be wrong.
    """
    pool = ConnectionPool(size=4)
    opened: list[int] = [0]
    key = ("postgresql", "postgresql://h/db", "")

    connection = pool.acquire(key, _factory(opened))
    connection.rollback_fails = True
    pool.release(key, connection)

    assert connection.closed is True
    assert pool.acquire(key, _factory(opened)) is not connection


def test_the_idle_pool_is_bounded_per_key() -> None:
    """Otherwise a burst of concurrency leaves every connection it ever opened parked forever."""
    pool = ConnectionPool(size=64)
    opened: list[int] = [0]
    key = ("postgresql", "postgresql://h/db", "")

    handed_out = [pool.acquire(key, _factory(opened)) for _ in range(20)]
    for connection in handed_out:
        pool.release(key, connection)

    # The oldest ones are closed as the cap is reached; the recent ones are still reusable.
    assert sum(1 for connection in handed_out if connection.closed) >= 12
    assert pool.acquire(key, _factory(opened)) in handed_out


def test_pooling_off_opens_a_connection_every_time() -> None:
    """The default. Every deployment before this opened one per `connect()`, and a framework
    that quietly changed how many connections a deployment holds would be trading an operator's
    capacity planning for a latency win they did not ask for."""
    pool = ConnectionPool(size=0)
    opened: list[int] = [0]
    key = ("postgresql", "postgresql://h/db", "")

    first = pool.acquire(key, _factory(opened))
    pool.release(key, first)
    second = pool.acquire(key, _factory(opened))

    assert second is not first
    assert pool.enabled is False


def test_release_does_nothing_when_pooling_is_off() -> None:
    """A connection handed out while the pool was off must not be closed by the release path --
    its owner closes it, and closing it twice is driver-specific."""
    pool = ConnectionPool(size=0)
    connection = _FakeConnection("x")
    pool.release(("sqlite", "/tmp/x.db", ""), connection)
    assert connection.closed is False


def test_sqlite_is_not_pooled_even_when_pooling_is_on() -> None:
    """A correctness boundary, not a preference.

    `sqlite3.connect` binds a connection to the thread that opened it (`check_same_thread`), so
    a pooled one handed to another thread raises inside whichever query happens to run first.
    The platform database is SQLite in most deployments, which makes this the common case.
    """
    from ontology_platform import connection_pool
    from ontology_platform.context import PlatformContext
    from ontology_platform.database import PlatformConnection

    pool = connection_pool._reset_pool(4)
    context = PlatformContext(db_type="sqlite", connection_uri=":memory:")
    try:
        with context.connect() as connection:
            assert isinstance(connection, PlatformConnection)
            # Handed straight through: not routed via the pool, so nothing was acquired.
            assert connection._pool is None
        assert pool.reused == 0
    finally:
        connection_pool._reset_pool(0)


def test_a_context_with_the_same_schema_and_uri_produces_the_same_key() -> None:
    """The key has to be *stable across calls*, or the pool holds entries nothing looks up and
    every request pays the handshake it was built to avoid."""
    from ontology_platform.context import PlatformContext

    one = PlatformContext(db_type="postgresql", connection_uri="postgresql://h/db", schema="acme")
    two = PlatformContext(db_type="postgresql", connection_uri="postgresql://h/db", schema="acme")
    other = PlatformContext(db_type="postgresql", connection_uri="postgresql://h/db", schema="globex")

    assert one.pool_key() == two.pool_key()
    assert one.pool_key() != other.pool_key()


def test_the_pool_key_covers_all_three_of_its_parts() -> None:
    """Each part changes what a borrowed connection points at, so each part has to be in it."""
    from ontology_platform.context import PlatformContext

    base = PlatformContext(db_type="postgresql", connection_uri="postgresql://h/db", schema="s")
    variants = [
        PlatformContext(db_type="mysql", connection_uri="postgresql://h/db", schema="s"),
        PlatformContext(db_type="postgresql", connection_uri="postgresql://h/other", schema="s"),
        PlatformContext(db_type="postgresql", connection_uri="postgresql://h/db", schema="other"),
    ]
    for variant in variants:
        assert variant.pool_key() != base.pool_key()


@pytest.mark.parametrize("size", [-5, 0])
def test_a_nonsensical_size_is_clamped_rather_than_trusted(size: int) -> None:
    """The size comes from an environment variable, and a negative one would make `enabled`
    false by accident rather than by intent."""
    pool = ConnectionPool(size=size)
    assert pool.size >= 0
    assert pool.enabled is False


def test_the_default_is_on_for_network_databases_and_irrelevant_for_sqlite() -> None:
    """Why a non-zero default is safe here, asserted rather than argued.

    A feature nobody turns on is a feature that does not exist, and the reason for leaving this
    off -- "it changes how many connections a deployment holds open" -- does not survive the
    SQLite exception: SQLite is never pooled whatever the setting, and most deployments run
    SQLite. So the default only ever affects PostgreSQL and MySQL, which are the deployments that
    gain from it.
    """
    from ontology_platform.config import CONNECTION_POOL

    assert CONNECTION_POOL.size > 0, (
        "默认值被改回 0 了。那会让这个特性只存在于文档里——请连同这一段一起改，而不是只改配置。"
    )

    # And the exception the argument rests on, restated where the default lives.
    from ontology_platform import connection_pool
    from ontology_platform.context import PlatformContext

    pool = connection_pool._reset_pool(CONNECTION_POOL.size)
    try:
        context = PlatformContext(db_type="sqlite", connection_uri=":memory:")
        with context.connect() as connection:
            assert connection._pool is None, "SQLite 不应被池化，无论默认值是多少"
        assert pool.reused == 0
    finally:
        connection_pool._reset_pool(0)
