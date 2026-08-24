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

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
PYPROJECT = ROOT / "pyproject.toml"
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
    """The endpoint count is a claim about the API's size, so it has to be a real number.

    Counted from the app itself rather than by grepping decorators. A source-text count
    only saw routes declared on `app`, so moving routes onto an `APIRouter` made the
    number drop without any endpoint disappearing -- the measurement tracked the file
    layout instead of the surface it claimed to describe.
    """
    import sys

    sys.path.insert(0, str(ROOT / "backend"))
    from ontology_platform.api import declared_routes

    routes = len(declared_routes())

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    claimed = {int(found) for found in re.findall(r"(\d+)\s*个端点", readme)}
    assert claimed, "README 未声明端点数量"
    assert routes in claimed, f"README 声明 {sorted(claimed)} 个端点，实际 {routes}"


def test_every_claimed_python_version_is_actually_tested() -> None:
    """The badge, the classifiers and the test matrix must agree.

    A version in the badge that no job runs is the worst kind of claim: Python keeps
    syntax compatible across releases but removes stdlib modules and changes defaults,
    and this platform reads schemas through `sqlite3` and enforces its rule sandbox
    through `ast` -- both of which move between versions. So "supports 3.13" can only be
    established by running it.

    The floor is checked in the other direction too. `requires-python` is what pip
    enforces, and a floor lower than the oldest tested version means pip cheerfully
    installs into an interpreter nobody has ever run the suite on.
    """
    pyproject = PYPROJECT.read_text(encoding="utf-8")
    workflow = WORKFLOW.read_text(encoding="utf-8")

    matrix = re.search(r"python-version: \[([^\]]+)\]", workflow)
    assert matrix, "CI 未声明 Python 版本矩阵"
    tested = {version.strip().strip('"') for version in matrix.group(1).split(",")}

    classifiers = set(re.findall(r"Programming Language :: Python :: (3\.\d+)", pyproject))
    assert classifiers == tested, f"classifiers 声明 {sorted(classifiers)}，CI 实际测试 {sorted(tested)}"

    floor = re.search(r'requires-python = ">=(3\.\d+)"', pyproject)
    assert floor, "pyproject 未声明 requires-python"

    def as_tuple(version: str) -> tuple[int, ...]:
        return tuple(int(part) for part in version.split("."))

    oldest_tested = min(tested, key=as_tuple)
    assert floor.group(1) == oldest_tested, (
        f"requires-python 为 {floor.group(1)}，但最旧的被测版本是 {oldest_tested}——pip 会安装到从未跑过测试的解释器上"
    )

    for filename, pattern in (("README.md", r"python-3\.(\d+)%2B"), ("README.en.md", r"python-3\.(\d+)%2B")):
        badge = re.search(pattern, (ROOT / filename).read_text(encoding="utf-8"))
        assert badge, f"{filename} 缺少 Python 版本徽章"
        assert f"3.{badge.group(1)}" == oldest_tested, (
            f"{filename} 徽章声明 3.{badge.group(1)}，实际底线 {oldest_tested}"
        )


def test_the_documented_signature_migration_count_is_current() -> None:
    """A debt number that drifts is a debt nobody can tell is shrinking.

    Three documents quote how many `platform_db: Path | str` signatures remain, and the
    number is the only evidence that the migration is progressing at all. Left to manual
    upkeep it goes stale in the wrong direction: the count grew from 172 to 186 while all
    three files still said 172, so the debt looked like it was being paid down while it
    was being added to.
    """
    import re as regex

    package = ROOT / "backend" / "ontology_platform"
    actual = sum(
        len(regex.findall(r"platform_db: Path \| str", path.read_text(encoding="utf-8")))
        for path in sorted(package.glob("*.py"))
    )

    for filename in ("README.md", "ROADMAP.md", "docs/architecture-debt.md"):
        text = (ROOT / filename).read_text(encoding="utf-8")
        claimed = {int(found) for found in regex.findall(r"(\d+) 处 `platform_db", text)}
        assert claimed, f"{filename} 未声明待迁移签名数量"
        assert actual in claimed, f"{filename} 声明 {sorted(claimed)} 处，实际 {actual} 处"


def test_the_documented_scale_is_current() -> None:
    """The "规模" line is the first thing a reader checks against reality.

    It had drifted badly -- 29 modules and 98 endpoints against an actual 71 and 149 --
    which is the kind of error that costs more than it looks: a reader who verifies one
    headline number and finds it less than half right stops trusting every other number in
    the document, including the ones that are correct.

    Counted with tolerance rather than exactly for the line total, since prose cannot
    reasonably track single-line edits. Module and endpoint counts are exact: those change
    only when something is added or removed.
    """
    import re as regex

    package = ROOT / "backend" / "ontology_platform"
    modules = sorted(path for path in package.rglob("*.py") if "__pycache__" not in str(path))
    lines = sum(len(path.read_text(encoding="utf-8").splitlines()) for path in modules)

    import sys

    sys.path.insert(0, str(ROOT / "backend"))
    from ontology_platform.api import declared_routes

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    claim = regex.search(r"(\d+) 个后端模块约 (\d+) 行，(\d+) 个 API 端点，(\d+) 张平台表", readme)
    assert claim, "README 规模一节格式已变，请同步本测试"
    stated_modules, stated_lines, stated_endpoints, stated_tables = (int(value) for value in claim.groups())

    assert stated_modules == len(modules), f"声明 {stated_modules} 个模块，实际 {len(modules)}"
    assert stated_endpoints == len(declared_routes()), f"声明 {stated_endpoints} 个端点，实际 {len(declared_routes())}"
    # Within 5%: close enough to be honest, loose enough not to fail on a comment edit.
    assert abs(stated_lines - lines) / lines < 0.05, f"声明约 {stated_lines} 行，实际 {lines}"

    tables = _platform_table_count()
    assert stated_tables == tables, f"声明 {stated_tables} 张平台表，实际 {tables}"


def _platform_table_count() -> int:
    """Tables a freshly initialised platform database contains.

    Counted by running `aletheia init` rather than by grepping DDL: feature modules own
    their own `SchemaBundle`, so a grep of `database.py` would miss every table added since
    the metamodel grew -- which is most of them. Driving the CLI also means the count is
    what a user actually gets, not what the internals could produce.
    """
    import contextlib
    import io
    import sqlite3
    import sys
    import tempfile
    from pathlib import Path as FsPath

    sys.path.insert(0, str(ROOT / "backend"))
    from ontology_platform.cli import main

    database = FsPath(tempfile.mkdtemp()) / "scale.sqlite3"
    with contextlib.redirect_stdout(io.StringIO()):
        assert main(["--platform-db", str(database), "init"]) == 0
    with sqlite3.connect(database) as raw:
        return int(
            raw.execute(
                "select count(*) from sqlite_master where type = 'table' and name not like 'sqlite_%'"
            ).fetchone()[0]
        )
