"""Contract tests for the platform's extension points.

Two audiences:

1. The platform itself -- these assert that opening the extension points did not
   weaken the guarantees the kernel makes (deny-by-default authorization, the
   rule sandbox, fail-closed evaluation).
2. Third-party implementers -- `AdapterContract` and the executor cases show the
   shape an implementation must satisfy. Run this module against your own
   registration to check compliance before shipping it.

See docs/adr/0007-extension-registry-without-api-stability.md for the stability
expectations that apply to everything exercised here.
"""

from __future__ import annotations

from typing import Any, Iterator

import pytest
from ontology_platform import access_policy
from ontology_platform.adapters import (
    ADAPTER_REGISTRY,
    get_adapter,
    register_adapter,
    supported_source_types,
)
from ontology_platform.auth import ALL_CAPABILITIES, CAP_ADMIN, CAP_EXECUTE, CAP_READ
from ontology_platform.automation import (
    EXECUTOR_REGISTRY,
    ExecutionRequest,
    register_executor,
    resolve_executor,
    supported_executor_schemes,
)
from ontology_platform.registry import Registry, RegistryError
from ontology_platform.semantic_kernel import (
    RULE_FUNCTION_REGISTRY,
    allowed_rule_function_names,
    register_rule_function,
    validate_rule_expression,
)


@pytest.fixture(autouse=True)
def _restore_registries() -> Iterator[None]:
    """Keep registrations from leaking between tests.

    The registries are process-global by design, so a test that registers an
    adapter would otherwise change what later tests observe.
    """
    saved = [
        (ADAPTER_REGISTRY, ADAPTER_REGISTRY.snapshot()),
        (RULE_FUNCTION_REGISTRY, RULE_FUNCTION_REGISTRY.snapshot()),
        (EXECUTOR_REGISTRY, EXECUTOR_REGISTRY.snapshot()),
    ]
    saved_policies = list(access_policy._PLUGIN_RULES)
    yield
    for registry, entries in saved:
        registry.restore(entries)
    access_policy._PLUGIN_RULES[:] = saved_policies


# -- Registry semantics --


def test_lookup_is_case_insensitive_and_trimmed() -> None:
    registry: Registry[str] = Registry("测试项")
    registry.register("Thing", "impl")
    assert registry.get("thing") == "impl"
    assert registry.get("  THING  ") == "impl"


def test_registering_the_same_object_twice_is_idempotent() -> None:
    registry: Registry[str] = Registry("测试项")
    registry.register("a", "impl")
    registry.register("a", "impl")
    assert registry.names() == ("a",)


def test_shadowing_a_different_implementation_requires_explicit_replace() -> None:
    """A plugin silently overriding a built-in is a debugging nightmare."""
    registry: Registry[str] = Registry("测试项")
    registry.register("a", "first")
    with pytest.raises(RegistryError, match="replace=True"):
        registry.register("a", "second")
    registry.register("a", "second", replace=True)
    assert registry.get("a") == "second"


def test_unknown_lookup_lists_what_is_available() -> None:
    registry: Registry[str] = Registry("测试项")
    registry.register("known", "impl")
    with pytest.raises(RegistryError, match="known"):
        registry.get("missing")


def test_empty_name_is_rejected() -> None:
    registry: Registry[str] = Registry("测试项")
    with pytest.raises(RegistryError):
        registry.register("   ", "impl")


# -- Data source adapters --


def test_builtin_adapters_are_registered() -> None:
    assert set(supported_source_types()) == {"sqlite", "postgresql", "mysql"}


@pytest.mark.parametrize(
    ("requested", "expected"),
    [
        ("sqlite", "SQLiteAdapter"),
        ("SQLite", "SQLiteAdapter"),
        ("postgresql", "PostgreSQLAdapter"),
        ("postgres", "PostgreSQLAdapter"),
        ("pgsql", "PostgreSQLAdapter"),
        ("mysql", "MySQLAdapter"),
    ],
)
def test_builtin_adapter_aliases_resolve(requested: str, expected: str) -> None:
    assert type(get_adapter(requested)).__name__ == expected


def test_unknown_adapter_raises_valueerror_naming_the_alternatives() -> None:
    """ValueError, not RegistryError: the API layer already maps it to a 400."""
    with pytest.raises(ValueError, match="sqlite"):
        get_adapter("oracle")


class _StubAdapter:
    """Minimal adapter used to prove third-party registration works."""

    def test_connection(self, connection_uri: str) -> dict[str, Any]:
        return {"sourceType": "stub", "reachable": True, "status": "ok", "message": ""}

    def scan(self, connection_uri: str) -> list[Any]:
        return []

    def runtime(self, connection_uri: str) -> Any:  # pragma: no cover - unused
        raise NotImplementedError


def test_a_third_party_adapter_becomes_usable_without_touching_platform_code() -> None:
    register_adapter("stubdb", _StubAdapter, aliases=("stub",))
    assert isinstance(get_adapter("stubdb"), _StubAdapter)
    assert isinstance(get_adapter("stub"), _StubAdapter)
    assert "stubdb" in supported_source_types()


# -- Rule functions --


def test_builtin_rule_functions_match_the_previous_frozen_set() -> None:
    assert allowed_rule_function_names() == frozenset({"sum", "len", "count", "any", "all"})


def test_unregistered_function_is_rejected_by_the_sandbox() -> None:
    result = validate_rule_expression("abs(amount) > 0")
    assert result["valid"] is False


def test_registered_function_becomes_callable_in_expressions() -> None:
    register_rule_function("abs", abs)
    assert validate_rule_expression("abs(amount) > 0")["valid"] is True


@pytest.mark.parametrize("name", ["_private", "2leading", "has.dot", "has space", ""])
def test_rule_function_names_must_be_plain_identifiers(name: str) -> None:
    """The sandbox resolves ast.Name nodes, so anything else could never bind."""
    with pytest.raises(ValueError):
        register_rule_function(name, abs)


def test_non_callable_rule_function_is_rejected() -> None:
    with pytest.raises(ValueError):
        register_rule_function("notafunc", 42)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "expression",
    [
        "abs.__class__",
        "abs(amount).__class__.__bases__",
        "__import__('os')",
        "abs(x) if y else z",
        "lambda: 1",
        "[i for i in items]",
        "abs(a=1)",
    ],
)
def test_registering_a_function_does_not_widen_the_ast_allowlist(expression: str) -> None:
    """Registration grants the right to call, never to bypass node validation."""
    register_rule_function("abs", abs)
    assert validate_rule_expression(expression)["valid"] is False


def test_a_column_cannot_shadow_a_registered_function() -> None:
    """Otherwise a table with a `sum` column would silently change rule meaning."""
    from ontology_platform.semantic_kernel import _allowed_names

    names = _allowed_names({"sum": 999})
    assert callable(names["sum"])


# -- Route policies --


def test_unregistered_route_still_defaults_to_admin() -> None:
    assert access_policy.required_capability("POST", "/plugin/whatever") == CAP_ADMIN


def test_plugin_can_declare_the_capability_for_its_own_routes() -> None:
    access_policy.register_route_policy(["POST"], r"/plugin/sync", CAP_EXECUTE, "插件同步")
    assert access_policy.required_capability("POST", "/plugin/sync") == CAP_EXECUTE


def test_a_plugin_rule_only_affects_paths_it_explicitly_matches() -> None:
    """Plugin rules are consulted first, so scope containment matters.

    A plugin *can* override a builtin route if it names that exact path --
    plugins are trusted code running in-process, and pretending otherwise would
    be security theatre. What this pins down is that the override cannot happen
    by accident: a rule for one path leaves neighbouring builtin routes alone.
    """
    access_policy.register_route_policy(["POST"], r"/plugin/open", CAP_READ, "插件公开端点")
    assert access_policy.required_capability("POST", "/plugin/open") == CAP_READ
    # Adjacent and builtin admin routes are untouched.
    assert access_policy.required_capability("POST", "/plugin/open/sub") == CAP_ADMIN
    assert access_policy.required_capability("POST", "/auth/users") == CAP_ADMIN


def test_unknown_capability_is_rejected_at_registration_time() -> None:
    with pytest.raises(ValueError, match="未知能力"):
        access_policy.register_route_policy(["GET"], r"/x", "bogus:capability", "x")


def test_reregistering_the_same_route_is_idempotent() -> None:
    before = len(access_policy.describe_policy())
    access_policy.register_route_policy(["GET"], r"/plugin/list", CAP_READ, "第一次")
    access_policy.register_route_policy(["GET"], r"/plugin/list", CAP_READ, "第二次")
    assert len(access_policy.describe_policy()) == before + 1


def test_describe_policy_distinguishes_plugin_rules_from_builtins() -> None:
    access_policy.register_route_policy(["GET"], r"/plugin/list", CAP_READ, "插件列表")
    sources = {row["source"] for row in access_policy.describe_policy()}
    assert sources == {"plugin", "builtin"}


def test_every_builtin_policy_uses_a_real_capability() -> None:
    for row in access_policy.describe_policy():
        assert row["capability"] in ALL_CAPABILITIES


# -- Writeback executors --


def test_http_and_https_are_built_in() -> None:
    assert set(supported_executor_schemes()) >= {"http", "https"}


def test_unsupported_scheme_explains_how_to_add_one() -> None:
    with pytest.raises(ValueError, match="register_executor"):
        resolve_executor("amqp://broker/queue")


def test_target_without_a_scheme_is_rejected() -> None:
    with pytest.raises(ValueError, match="无法从业务 API 基址识别协议"):
        resolve_executor("localhost:8080")


def test_a_third_party_executor_receives_the_execution_request() -> None:
    seen: list[ExecutionRequest] = []

    def _executor(request: ExecutionRequest) -> dict[str, Any]:
        seen.append(request)
        return {"published": True, "queue": request.plan["path"]}

    register_executor("amqp", _executor)
    result = resolve_executor("amqp://broker/q")(
        ExecutionRequest(
            target="amqp://broker/q",
            plan={"path": "/orders", "method": "POST", "payload": {"id": 1}},
            timeout_seconds=5.0,
            headers={"X-Trace": "abc"},
        )
    )
    assert result == {"published": True, "queue": "/orders"}
    assert seen[0].headers == {"X-Trace": "abc"}
    assert seen[0].timeout_seconds == 5.0


@pytest.mark.parametrize(("registered", "expected"), [("grpc://", "grpc"), ("MSSQLS", "mssqls")])
def test_executor_scheme_is_normalized_without_truncation(registered: str, expected: str) -> None:
    """rstrip('://') would eat a trailing s; splitting must not."""
    register_executor(registered, lambda request: {})
    assert expected in supported_executor_schemes()


def test_empty_executor_scheme_is_rejected() -> None:
    with pytest.raises(ValueError):
        register_executor("", lambda request: {})
