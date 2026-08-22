"""Module boundaries: no import cycles, and no reaching into private names.

These are the two properties that turn "runs" into "can be packaged". Both were
recorded as technical debt items 3 and 4, and both are the kind of thing that decays
silently -- one convenient function-local import at a time -- so they are asserted
rather than documented.

Why it matters concretely: at packaging time (ROADMAP stage E) a cycle that crosses a
distribution boundary cannot be papered over with a function-local import. Finding
that out during the split means unpicking it under pressure; finding it out here means
a failing test on the commit that introduced it.
"""

from __future__ import annotations

import ast
import collections
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "backend" / "ontology_platform"
sys.path.insert(0, str(ROOT / "backend"))

# `context` and `database` genuinely depend on each other: a context owns an adapter
# that only `database` can build, and `database`'s public entry points resolve through
# a context. They are the single allowed pair, and they will land in the same
# distribution, so the cycle cannot cross a package boundary.
#
# Anything else appearing here is a regression, not a new exception.
ALLOWED_CYCLE_PAIRS = {frozenset({"context", "database"})}


def _relative_imports() -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """(top-level, function-local) intra-package import graphs."""
    top: dict[str, set[str]] = collections.defaultdict(set)
    local: dict[str, set[str]] = collections.defaultdict(set)
    for path in sorted(PACKAGE.glob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not (isinstance(node, ast.ImportFrom) and node.level == 1 and node.module):
                continue
            target = node.module.split(".")[0]
            # Column 0 means module scope; anything indented is inside a function.
            (top if node.col_offset == 0 else local)[path.stem].add(target)
    return dict(top), dict(local)


def _reaches(graph: dict[str, set[str]], start: str, goal: str) -> bool:
    stack, seen = [start], set()
    while stack:
        current = stack.pop()
        if current == goal:
            return True
        if current in seen:
            continue
        seen.add(current)
        stack.extend(graph.get(current, ()))
    return False


def test_no_top_level_import_cycles() -> None:
    """A top-level cycle would fail outright once the package is split."""
    top, _ = _relative_imports()
    cycles = {
        frozenset({module, target})
        for module, targets in top.items()
        for target in targets
        if _reaches(top, target, module)
    }
    assert not cycles, f"存在顶层循环依赖: {[sorted(pair) for pair in cycles]}"


def test_function_local_imports_do_not_hide_new_cycles() -> None:
    """A function-local import that would be a cycle if hoisted is a hidden cycle.

    Hoisting every intra-package import and re-checking is the honest test: a
    function-local import that only works because it is deferred is still a cycle, and
    packaging will surface it.
    """
    top, local = _relative_imports()
    combined: dict[str, set[str]] = {module: set(targets) for module, targets in top.items()}
    for module, targets in local.items():
        combined.setdefault(module, set()).update(targets)

    cycles = {
        frozenset({module, target})
        for module, targets in combined.items()
        for target in targets
        if module != target and _reaches(combined, target, module)
    }
    unexpected = cycles - ALLOWED_CYCLE_PAIRS
    assert not unexpected, (
        "函数内 import 掩盖了新的循环依赖: "
        f"{[sorted(pair) for pair in unexpected]}。"
        "请调整依赖方向，或注入依赖（参见 derived_attributes.bind_sandbox）。"
    )


def test_the_allowed_cycle_is_still_a_real_one() -> None:
    """Keeps the allowlist from outliving the problem it describes.

    If `context` and `database` stop depending on each other, this exception should be
    deleted rather than left as permission for a future cycle.
    """
    top, local = _relative_imports()
    combined: dict[str, set[str]] = {module: set(targets) for module, targets in top.items()}
    for module, targets in local.items():
        combined.setdefault(module, set()).update(targets)
    for pair in ALLOWED_CYCLE_PAIRS:
        left, right = sorted(pair)
        assert _reaches(combined, left, right) and _reaches(combined, right, left), (
            f"{left} 与 {right} 已不再相互依赖，请从 ALLOWED_CYCLE_PAIRS 中删除该例外"
        )


# -- Private-name boundaries --


def _cross_module_private_imports() -> list[tuple[str, str, str]]:
    """(importer, source module, private name) for underscore-prefixed imports."""
    findings = []
    for path in sorted(PACKAGE.glob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not (isinstance(node, ast.ImportFrom) and node.level == 1 and node.module):
                continue
            for alias in node.names:
                if alias.name.startswith("_"):
                    findings.append((path.stem, node.module.split(".")[0], alias.name))
    return findings


def test_no_module_imports_another_modules_private_names() -> None:
    """A private name imported across modules is an API nobody agreed to keep.

    Six modules used to import `database._sqlite_ddl` and friends; the shared behaviour
    they actually needed now lives in `schema`. A third party depending on a name we
    never meant to stabilise is the failure this prevents.
    """
    findings = _cross_module_private_imports()
    assert not findings, (
        "跨模块导入了私有名称: "
        + "、".join(f"{importer} ← {source}.{name}" for importer, source, name in findings)
        + "。请将共享行为提升为公开 API，或下沉到共享模块。"
    )


def test_the_public_surface_is_declared_where_it_matters() -> None:
    """The modules a third party is most likely to import must state their surface.

    Without `__all__`, every helper that happens to be defined at module scope reads as
    public, and we cannot rename one without risking a downstream break.
    """
    for module in ("rule_sandbox", "semantic_kernel"):
        tree = ast.parse((PACKAGE / f"{module}.py").read_text())
        declared = [
            node
            for node in tree.body
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets)
        ]
        assert declared, f"{module} 未声明 __all__，公开边界不明确"


def test_declared_exports_actually_exist() -> None:
    """An `__all__` naming something absent breaks `from module import *` at runtime."""
    import importlib

    for module in ("rule_sandbox", "semantic_kernel"):
        imported = importlib.import_module(f"ontology_platform.{module}")
        missing = [name for name in getattr(imported, "__all__", []) if not hasattr(imported, name)]
        assert not missing, f"{module}.__all__ 中的名称不存在: {missing}"
