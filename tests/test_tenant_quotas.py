"""Tenant quotas: ROADMAP stage B's last open item.

Isolation was already done -- schema routing plus a `tenant_id` column, cross-tenant
access blocked. What was missing was a ceiling. On a shared deployment that is not a
billing question but an availability one: one tenant ingesting an unbounded document set
fills the platform database, and the tenant that then cannot write is a *different*
tenant, who has no way to discover why.

The properties that make a quota mean anything:

- **a tenant cannot raise its own limit** -- quotas live in the base database, not in the
  tenant's schema, so reaching them requires platform-level access
- **the check runs before the write** -- a quota discovered afterwards has to undo a
  partially ingested document, and the tenant is then unsure what landed
- **an undeclared quota is unlimited, not zero** -- the other default would stop every
  existing deployment from accepting writes the moment this shipped
- **usage is counted, not tracked** -- a stored counter drifts from the rows it counts,
  and a drifted counter either blocks a tenant under their limit or lets one past it
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from ontology_platform.context import PlatformContext
from ontology_platform.quotas import (
    QUOTA_RESOURCES,
    SCHEMA,
    QuotaExceeded,
    check_quota,
    describe_quota_resources,
    quota_usage,
    set_tenant_quota,
    tenant_quotas,
    verify_resources_are_tenant_scoped,
)
from ontology_platform.tenancy import (
    DEFAULT_TENANT,
    TENANT_SCOPED_TABLES,
    TenantError,
    provision_tenant,
)


@pytest.fixture
def base(tmp_path: Path) -> PlatformContext:
    context = PlatformContext(db_type="sqlite", connection_uri=str(tmp_path / "platform.sqlite3"))
    context.initialize()
    provision_tenant(context, DEFAULT_TENANT)
    return context


# -- The resource catalogue --


def test_every_limitable_resource_counts_a_tenant_scoped_table() -> None:
    """A resource pointing at a platform-global table would count every tenant's rows.

    One tenant's usage would then consume another's quota, and the tenant hitting the
    limit would have done nothing to cause it. Enforced at import as well as here.
    """
    verify_resources_are_tenant_scoped()
    for resource, (table, _) in QUOTA_RESOURCES.items():
        assert table in TENANT_SCOPED_TABLES, f"{resource} 指向非租户表 {table}"


def test_the_catalogue_says_which_table_each_resource_counts() -> None:
    """`ontologies` counts versions too. An operator who assumed otherwise would set a
    limit that a normal `derive` workflow exhausts."""
    described = describe_quota_resources()
    assert {item["resource"] for item in described} == set(QUOTA_RESOURCES)
    for item in described:
        assert item["table"], item
        assert item["description"], item


# -- Declaration --


def test_an_unknown_resource_is_refused(base) -> None:
    """Stored, it would be a quota that never applies to anything -- an operator would
    believe a limit is in force."""
    with pytest.raises(TenantError, match="未知配额资源"):
        set_tenant_quota(base, DEFAULT_TENANT, "gigabytes_of_ram", 10)


def test_a_negative_limit_is_refused(base) -> None:
    """Stored, it would read as "unlimited" or "blocked" depending on which comparison
    ran first."""
    with pytest.raises(TenantError, match="不能为负数"):
        set_tenant_quota(base, DEFAULT_TENANT, "data_sources", -1)


def test_an_invalid_tenant_identifier_is_refused(base) -> None:
    with pytest.raises(TenantError):
        set_tenant_quota(base, "Bad Tenant!", "data_sources", 5)


def test_setting_the_same_resource_twice_replaces_the_limit(base) -> None:
    """Two rows for one resource would both be checked, and the lower one would win by
    accident rather than by decision."""
    set_tenant_quota(base, DEFAULT_TENANT, "data_sources", 5)
    set_tenant_quota(base, DEFAULT_TENANT, "data_sources", 9)
    assert tenant_quotas(base, DEFAULT_TENANT) == {"data_sources": 9}


# -- An undeclared quota is unlimited --


def test_no_declared_quota_permits_the_write(base) -> None:
    """The one place this module is deliberately not fail-closed.

    Defaulting to zero would stop every existing deployment from accepting writes the
    moment quotas shipped -- a silent outage caused by adding a feature nobody opted
    into. And refusing writes for tenants nobody set a limit for protects no one, because
    the failure being prevented is resource exhaustion, not unauthorised access.
    """
    assert tenant_quotas(base, DEFAULT_TENANT) == {}
    check_quota(base, DEFAULT_TENANT, "data_sources", requested=10_000)


def test_usage_reports_none_rather_than_a_large_number_when_unlimited(base) -> None:
    """A caller cannot render "unlimited" as a misleading figure if there is no figure."""
    report = quota_usage(base, DEFAULT_TENANT)
    entry = report["resources"]["data_sources"]
    assert entry["limit"] is None
    assert entry["remaining"] is None
    assert entry["exceeded"] is False


def test_a_missing_quota_table_reads_as_no_limits(tmp_path: Path) -> None:
    """An installation that has not applied the migration must not start refusing writes.

    Raising here would make every write fail on upgrade, which is the failure mode that
    gets a feature reverted.
    """
    context = PlatformContext(db_type="sqlite", connection_uri=str(tmp_path / "bare.sqlite3"))
    context.initialize()
    assert tenant_quotas(context, DEFAULT_TENANT) == {}
    check_quota(context, DEFAULT_TENANT, "data_sources", requested=1)


# -- Enforcement --


def test_a_write_within_the_limit_is_permitted(base) -> None:
    set_tenant_quota(base, DEFAULT_TENANT, "data_sources", 3)
    check_quota(base, DEFAULT_TENANT, "data_sources", requested=3)


def test_a_write_past_the_limit_is_refused_with_the_numbers(base) -> None:
    """ "Quota exceeded" with no numbers is indistinguishable from a bug, and the caller's
    next action is to retry the identical request."""
    set_tenant_quota(base, DEFAULT_TENANT, "data_sources", 2)
    with pytest.raises(QuotaExceeded) as raised:
        check_quota(base, DEFAULT_TENANT, "data_sources", requested=3)

    error = raised.value
    assert error.limit == 2
    assert error.requested == 3
    assert error.current == 0
    message = str(error)
    assert "上限 2" in message
    assert "本次请求 3" in message
    # And what to do about it, since the caller cannot raise their own quota.
    assert "管理员" in message


def test_a_batch_is_measured_as_a_whole(base) -> None:
    """Otherwise a batch of 100 would pass a limit of 1 by checking one row at a time."""
    set_tenant_quota(base, DEFAULT_TENANT, "knowledge_entries", 10)
    check_quota(base, DEFAULT_TENANT, "knowledge_entries", requested=10)
    with pytest.raises(QuotaExceeded):
        check_quota(base, DEFAULT_TENANT, "knowledge_entries", requested=11)


def test_a_quota_exceeded_error_is_a_tenant_error(base) -> None:
    """So a caller that already handles tenant problems handles this one, while a caller
    that wants the numbers can catch it specifically."""
    set_tenant_quota(base, DEFAULT_TENANT, "data_sources", 0)
    with pytest.raises(TenantError):
        check_quota(base, DEFAULT_TENANT, "data_sources", requested=1)


def test_usage_counts_actual_rows_rather_than_a_counter(base) -> None:
    """A stored counter drifts from the rows it counts.

    A drifted counter either blocks a tenant who is under their limit or lets one past
    it -- both worse than a count that costs a query.
    """
    from ontology_platform.metadata import register_data_source
    from ontology_platform.tenancy import tenant_context

    set_tenant_quota(base, DEFAULT_TENANT, "data_sources", 2)
    before = quota_usage(base, DEFAULT_TENANT)["resources"]["data_sources"]
    assert before["current"] == 0
    assert before["remaining"] == 2

    # Written through the *tenant's* context, which is where its rows live -- on SQLite
    # each tenant is a separate file, so a write to the base database would not be the
    # tenant's data and counting it would be counting the wrong rows.
    scoped = tenant_context(base, DEFAULT_TENANT)
    register_data_source(scoped.connection_uri, "系统甲", "sqlite", str(scoped.connection_uri), domain="合同管理")

    after = quota_usage(base, DEFAULT_TENANT)["resources"]["data_sources"]
    assert after["current"] == 1, "用量未反映真实行数"
    assert after["remaining"] == 1

    # And the check now accounts for the row that exists.
    check_quota(base, DEFAULT_TENANT, "data_sources", requested=1)
    with pytest.raises(QuotaExceeded):
        check_quota(base, DEFAULT_TENANT, "data_sources", requested=2)


# -- Quotas are not reachable from the tenant's own database --


def test_quotas_are_stored_in_the_base_database_not_the_tenants(base, tmp_path: Path) -> None:
    """The design's load-bearing decision.

    A quota stored in the tenant's schema is a quota the tenant can edit: the same
    connection that writes their data would reach the row that limits it. This asserts
    the table is absent from a tenant context, because "the tenant cannot edit it" is
    only true while it is not there.
    """
    from ontology_platform.tenancy import tenant_context

    set_tenant_quota(base, "acme", "data_sources", 1)
    provision_tenant(base, "acme")
    scoped = tenant_context(base, "acme")

    with scoped.connect() as conn:
        assert not SCHEMA.has_tables(conn), "配额表出现在租户库中，租户可自行修改上限"

    # Still readable through the base context, which is where it belongs.
    assert tenant_quotas(base, "acme") == {"data_sources": 1}


def test_one_tenants_usage_does_not_consume_anothers_quota(base) -> None:
    """The failure the tenant-scoped-table guard exists to prevent."""
    from ontology_platform.metadata import register_data_source
    from ontology_platform.tenancy import tenant_context

    provision_tenant(base, "acme")
    provision_tenant(base, "globex")
    set_tenant_quota(base, "acme", "data_sources", 1)
    set_tenant_quota(base, "globex", "data_sources", 1)

    acme = tenant_context(base, "acme")
    register_data_source(acme.connection_uri, "甲系统", "sqlite", str(acme.connection_uri), domain="合同管理")

    assert quota_usage(base, "acme")["resources"]["data_sources"]["current"] == 1
    assert quota_usage(base, "globex")["resources"]["data_sources"]["current"] == 0
    # globex has written nothing, so its quota is untouched.
    check_quota(base, "globex", "data_sources", requested=1)
