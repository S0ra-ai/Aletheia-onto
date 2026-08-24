"""Documented numbers match the code they describe.

The README makes countable promises -- how many tests exist, how many each file
contributes, how many endpoints the HTTP layer exposes. Prose drifts from code
silently, and a number that is wrong is worse than one that is absent: a reader who
checks one claim and finds it stale stops trusting the ones they cannot check.

Asserted here rather than in a workflow step, for two reasons. A check that only exists
in CI cannot be run before pushing, so it reports drift after review has started. And
the workflow's version read only the Chinese README, which let the English one fall two
releases behind while CI stayed green -- an English-speaking reader had no way to know
the file they were reading was the unverified copy.

What is deliberately *not* asserted: prose describing behaviour. That belongs to the
tests for that behaviour. These are only the claims a machine can count, which are
exactly the ones a human reviewer skims past.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
READMES = {"README.md": "(\\d+)\\s*个测试", "README.en.md": r"\*\*(\d+) tests\*\*"}


def _collected_counts() -> dict[str, int]:
    """Test file -> number of collected tests, per pytest itself.

    Collection rather than a passed count: skips depend on which service containers are
    reachable, so a passed count would make the README's number correct in one
    environment and wrong in every other.
    """
    out = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", str(TESTS)],
        capture_output=True,
        text=True,
        check=True,
        cwd=ROOT,
    ).stdout
    return {name: int(count) for name, count in re.findall(r"^(tests/\S+\.py): (\d+)$", out, re.MULTILINE)}


def test_both_readmes_state_the_real_test_total() -> None:
    """A stale total is the one number every reader checks first."""
    counts = _collected_counts()
    assert counts, "未能从 pytest 解析每个文件的收集数量"
    total = sum(counts.values())

    for filename, pattern in READMES.items():
        claimed = {int(found) for found in re.findall(pattern, (ROOT / filename).read_text(encoding="utf-8"))}
        assert claimed, f"{filename} 未声明测试总数"
        assert total in claimed, f"{filename} 声明 {sorted(claimed)}，实际收集到 {total}"


def test_the_per_file_breakdown_covers_every_test_file() -> None:
    """A distribution table missing a row is a test suite nobody knows exists.

    Both directions matter. A row for a deleted file describes coverage that is gone; a
    file with no row is coverage the reader cannot find, which is how a suite ends up
    with two modules testing the same thing.
    """
    counts = _collected_counts()
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    documented = {
        name: int(count) for name, count in re.findall(r"^\| `(test_\S+\.py)` \| (\d+) \|", readme, re.MULTILINE)
    }

    actual = {Path(path).name: count for path, count in counts.items()}

    assert set(documented) == set(actual), (
        f"README 分布表与实际测试文件不一致；仅文档有: {sorted(set(documented) - set(actual))}；"
        f"仅代码有: {sorted(set(actual) - set(documented))}"
    )

    wrong = {name: (count, actual[name]) for name, count in documented.items() if actual[name] != count}
    assert not wrong, f"README 分布表数量过期（文档, 实际）: {wrong}"


def test_the_documented_endpoint_count_matches_the_http_layer() -> None:
    """`api.py` 的端点数是拆分 APIRouter 的进度指标，因此必须是实数而非约数。"""
    tree = ast.parse((ROOT / "backend" / "ontology_platform" / "api.py").read_text(encoding="utf-8"))
    routes = 0
    for node in ast.walk(tree):
        for decorator in getattr(node, "decorator_list", []):
            func = decorator.func if isinstance(decorator, ast.Call) else decorator
            if (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "app"
                and func.attr in {"get", "post", "put", "patch", "delete"}
            ):
                routes += 1

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    claimed = {int(found) for found in re.findall(r"(\d+)\s*个端点", readme)}
    assert claimed, "README 未声明端点数量"
    assert routes in claimed, f"README 声明 {sorted(claimed)} 个端点，实际 {routes}"
