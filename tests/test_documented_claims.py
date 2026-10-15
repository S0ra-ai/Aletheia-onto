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
# Where each language states the test total. Both READMEs carry it as a badge; the testing
# pages carry it in prose. Checked in every place it appears, because one stale copy is
# enough to teach a reader that the numbers here cannot be trusted.
TEST_TOTAL_SOURCES = {
    "README.md": r"tests-(\d+)%20passing",
    "README.zh-CN.md": r"tests-(\d+)%20passing",
    "docs/testing.md": r"\*\*(\d+) tests\*\*",
    "docs/testing.zh-CN.md": r"\*\*(\d+) 个测试\*\*",
}

# The same total, in the sentence a reader actually reads. The badge is a URL fragment that
# happens to contain a number; the prose is the claim. They are separate copies, and only
# the badge was checked -- so the prose sat at a stale `1379` while the badge, the testing
# pages and CI were all green, which is precisely the drift this file exists to prevent.
#
# Matched loosely (`<number> tests`) rather than against a fixed sentence, and asserted to
# be *the only* such number rather than merely present: a file carrying both the right
# number and a stale one has the same problem as carrying only the stale one.
PROSE_TOTAL_SOURCES = {
    "README.md": r"(\d{3,5}) tests\b",
    "README.zh-CN.md": r"(\d{3,5}) 个测试",
}


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

    for filename, pattern in TEST_TOTAL_SOURCES.items():
        claimed = {int(found) for found in re.findall(pattern, (ROOT / filename).read_text(encoding="utf-8"))}
        assert claimed, f"{filename} 未声明测试总数"
        assert total in claimed, f"{filename} 声明 {sorted(claimed)}，实际收集到 {total}"


def test_the_prose_test_total_matches_the_badge() -> None:
    """The sentence a reader reads, not just the URL fragment beside it.

    The badge is checked above and always was; the prose stating the same number was not,
    so it sat at a stale `1379` while the badge, both testing pages and CI were green. That
    is the exact failure this module exists to prevent -- a number a reader can check, wrong
    in one of the two places they might check it.

    Asserted to be the *only* such number in the file rather than merely present: a file
    carrying both the current number and a stale one is no better than carrying only the
    stale one, and `in` would accept it.
    """
    total = sum(_collected_counts().values())
    for filename, pattern in PROSE_TOTAL_SOURCES.items():
        found = {int(number) for number in re.findall(pattern, (ROOT / filename).read_text(encoding="utf-8"))}
        assert found, f"{filename} 未在正文中声明测试总数"
        assert found == {total}, f"{filename} 正文声明 {sorted(found)}，实际收集到 {total}"


def test_the_per_file_breakdown_covers_every_test_file() -> None:
    """A distribution table missing a row is a test suite nobody knows exists.

    Both directions matter. A row for a deleted file describes coverage that is gone; a
    file with no row is coverage the reader cannot find, which is how a suite ends up
    with two modules testing the same thing.
    """
    counts = _collected_counts()
    # The table moved out of the README when the entry point was shortened. Both language
    # versions carry it, and both are checked: a breakdown that is right in one language and
    # stale in the other is worse than one place being wrong, because the reader who checks
    # the stale copy has no reason to suspect the other exists.
    testing = "\n".join(
        (ROOT / "docs" / name).read_text(encoding="utf-8") for name in ("testing.zh-CN.md", "testing.md")
    )
    documented = {
        name: int(count) for name, count in re.findall(r"^\| `(test_\S+\.py)` \| (\d+) \|", testing, re.MULTILINE)
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

    limitations = (ROOT / "docs" / "limitations.zh-CN.md").read_text(encoding="utf-8")
    claimed = {int(found) for found in re.findall(r"(\d+)\s*个端点", limitations)}
    assert claimed, "docs/limitations.zh-CN.md 未声明端点数量"
    assert routes in claimed, f"文档声明 {sorted(claimed)} 个端点，实际 {routes}"


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

    for filename, pattern in (("README.md", r"python-3\.(\d+)%2B"), ("README.zh-CN.md", r"python-3\.(\d+)%2B")):
        badge = re.search(pattern, (ROOT / filename).read_text(encoding="utf-8"))
        assert badge, f"{filename} 缺少 Python 版本徽章"
        assert f"3.{badge.group(1)}" == oldest_tested, (
            f"{filename} 徽章声明 3.{badge.group(1)}，实际底线 {oldest_tested}"
        )


def test_no_signature_narrows_back_to_a_path() -> None:
    """`platform_db` must stay widened to `PlatformDb`, in every module.

    This replaces a test that tracked how many `Path | str` signatures remained. That count
    existed because the migration was in progress, and it drifted in the worst direction --
    172 became 186 while all three documents still said 172, so the debt read as shrinking
    while it was being added to.

    The migration is done, so the useful invariant is different: no new function may narrow
    the annotation back. Narrowing does not break anything at runtime -- every one of these
    resolves through `resolve_context()` -- which is exactly why it would go unnoticed. It
    would simply make a type checker reject a supported call, and the caller who hits it
    cannot tell whether the platform means to support contexts or not.
    """
    import re as regex

    package = ROOT / "backend" / "ontology_platform"
    offenders = {}
    for path in sorted(package.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        # Signatures only. `context.py` discusses the old annotation in prose, and a docstring
        # mentioning it is not a signature declaring it.
        found = regex.findall(r"^\s*platform_db: Path \| str", source, regex.MULTILINE)
        if found:
            offenders[path.name] = len(found)

    assert not offenders, (
        f"以下模块把 platform_db 标注收窄回 Path | str: {offenders}。"
        "运行时仍可用，但类型检查器会拒绝传入 PlatformContext——"
        "而多租户与嵌入正是靠传 context 实现的。"
    )


def test_the_screenshot_docs_state_how_many_screenshots_there_are() -> None:
    """Both screenshot docs must claim the number of screenshots they actually contain.

    They said "Ten screenshots" while holding twelve, and "十张截图" in the Chinese copy.
    No test noticed because the count is prose: `test_documentation_links.py` checks that
    `![alt](images/NN-name.png)` resolves, and every one of them did. The claim that had
    gone stale was the one a reader uses to decide whether they have seen everything.

    The number is asserted rather than removed because it is a real promise -- it tells a
    reader the page is finite and they have reached the end of it.
    """
    import re as regex

    for name, pattern in (
        ("docs/screenshots.md", r"^> (\d+) screenshots?,"),
        ("docs/screenshots.zh-CN.md", r"^> (\d+) 张截图"),
    ):
        document = (ROOT / name).read_text(encoding="utf-8")
        claim = regex.search(pattern, document, regex.MULTILINE)
        assert claim, f"{name} 的截图数量引言格式已变，请同步本测试"

        # Count sections that actually carry an image, not every `##` heading: the Chinese
        # page has an extra section explaining the tenant-isolation ADR, which is prose
        # about a decision rather than a screenshot of a screen.
        sections = [chunk for chunk in document.split("\n## ")[1:] if "](images/" in chunk]

        assert int(claim.group(1)) == len(sections), f"{name} 声明 {claim.group(1)} 张，实际 {len(sections)}"


def test_the_frontend_label_maps_cover_the_backend_vocabulary() -> None:
    """`frontend/src/i18n/labels.ts` claims to know what the backend can emit.

    `label()` falls back to the raw value when a map has not learned it, so an incomplete
    map does not break anything -- it prints `blocked` in the middle of a Chinese console and
    looks like a rendering detail rather than a gap. That is how `blocked` was missing from
    `READINESS_STATUS` while three endpoints emit it, and how the ontology detail page came
    to show a raw enum beside a translated one.

    Only the vocabularies the backend declares as constants are checked. The rest are
    literals scattered through the modules that return them, and a test that guessed at them
    would be asserting its own guess.
    """
    import re as regex

    sys.path.insert(0, str(ROOT / "backend"))
    from ontology_platform import events, governance, relations

    source = (ROOT / "frontend" / "src" / "i18n" / "labels.ts").read_text(encoding="utf-8")

    def entries(name: str) -> set[str]:
        match = regex.search(rf"export const {name}\b[^=]*= \{{(.*?)\n\}};", source, regex.DOTALL)
        assert match, f"labels.ts 中找不到 {name}，请同步本测试"
        return set(regex.findall(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:", match.group(1), regex.MULTILINE))

    expected: dict[str, set[str]] = {
        "ONTOLOGY_STATUS": set(governance.VALID_ONTOLOGY_STATUSES),
        "MAPPING_STATUS": set(governance.VALID_MAPPING_STATUSES),
        "RULE_TYPE": set(governance.VALID_RULE_TYPES),
        "RULE_SEVERITY": set(governance.VALID_RULE_SEVERITIES),
        "RELATION_KIND": set(relations.RELATION_KINDS),
        "EVENT_CATEGORY": set(events.EVENT_CATEGORIES),
    }
    for name, vocabulary in expected.items():
        missing = vocabulary - entries(name)
        assert not missing, f"labels.ts 的 {name} 缺少后端会产出的值：{sorted(missing)}"


def test_the_documented_scale_is_current() -> None:
    """The "规模" line is the first thing a reader checks against reality.

    It had drifted badly -- 29 modules and 98 endpoints against an actual 71 and 149 --
    which is the kind of error that costs more than it looks: a reader who verifies one
    headline number and finds it less than half right stops trusting every other number in
    the document, including the ones that are correct.

    Counted with tolerance rather than exactly for the line total, since prose cannot
    reasonably track single-line edits. Module and endpoint counts are exact: those change
    only when something is added or removed.

    Both languages are read. Reading only the Chinese copy is what this file's own module
    docstring warns about -- the English README fell two releases behind while CI stayed
    green -- and the same bug was sitting here: `docs/testing.md` said "87 backend modules,
    roughly 34,100 lines" against an actual 85 and ~35,500, while the Chinese copy beside it
    was correct and asserted. Two documents disagreeing about the same fact is worse than
    one of them being stale, because the reader has to decide which one lied.
    """
    import re as regex

    package = ROOT / "backend" / "ontology_platform"
    modules = sorted(path for path in package.rglob("*.py") if "__pycache__" not in str(path))
    lines = sum(len(path.read_text(encoding="utf-8").splitlines()) for path in modules)

    import sys

    sys.path.insert(0, str(ROOT / "backend"))
    from ontology_platform.api import declared_routes

    zh = (ROOT / "docs" / "testing.zh-CN.md").read_text(encoding="utf-8")
    en = (ROOT / "docs" / "testing.md").read_text(encoding="utf-8")

    claim = regex.search(r"(\d+) 个后端模块约 (\d+) 行，(\d+) 个 API 端点，(\d+) 张平台表", zh)
    assert claim, "docs/testing.zh-CN.md 规模一节格式已变，请同步本测试"
    stated_modules, stated_lines, stated_endpoints, stated_tables = (int(value) for value in claim.groups())

    english = regex.search(r"(\d+) backend modules, roughly ([\d,]+) lines, (\d+) API endpoints", en)
    assert english, "docs/testing.md 规模一节格式已变，请同步本测试"
    en_modules, en_lines, en_endpoints = (
        int(english.group(1)),
        int(english.group(2).replace(",", "")),
        int(english.group(3)),
    )

    assert stated_modules == len(modules), f"声明 {stated_modules} 个模块，实际 {len(modules)}"
    assert stated_endpoints == len(declared_routes()), f"声明 {stated_endpoints} 个端点，实际 {len(declared_routes())}"
    # Within 5%: close enough to be honest, loose enough not to fail on a comment edit.
    assert abs(stated_lines - lines) / lines < 0.05, f"声明约 {stated_lines} 行，实际 {lines}"

    assert en_modules == len(modules), f"docs/testing.md 声明 {en_modules} 个模块，实际 {len(modules)}"
    assert en_endpoints == len(declared_routes()), f"docs/testing.md 声明 {en_endpoints} 个端点"
    assert abs(en_lines - lines) / lines < 0.05, f"docs/testing.md 声明约 {en_lines} 行，实际 {lines}"

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


def test_every_location_the_capability_matrix_names_exists() -> None:
    """`docs/capabilities.zh-CN.md` says where each capability is implemented.

    Nothing checked it. A row whose实现位置 points at a file that was renamed or removed
    still reads as "implemented, and here it is" -- which is the most useful kind of wrong:
    the reader follows the pointer and finds nothing, and has no way to tell whether the
    capability moved or never existed.

    Only the paths are asserted, not the status column. Whether a ✅ row is *correctly* ✅
    is a question for the tests named beside it; whether the file it points at exists is a
    question a machine can answer.
    """
    import re as regex

    package_files = {path.name for path in (ROOT / "backend" / "ontology_platform").rglob("*.py")}
    test_files = {path.name for path in TESTS.glob("*.py")}

    # Both languages. The English matrix exists and is linked from the English README, so
    # checking only the Chinese one is the mistake this file's own module docstring warns
    # about -- a claim verified in one language and assumed in the other.
    for name in ("capabilities.zh-CN.md", "capabilities.md"):
        document = (ROOT / "docs" / name).read_text(encoding="utf-8")
        checked = 0
        missing: list[str] = []
        for line in document.splitlines():
            if not line.startswith("|") or "✅" not in line:
                continue
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if len(cells) < 3:
                continue
            for reference in regex.findall(r"`([A-Za-z0-9_./]+\.py)`", cells[2]):
                checked += 1
                base = reference.rsplit("/", 1)[-1]
                if base not in package_files and base not in test_files:
                    missing.append(f"{cells[0][:40]} -> {reference}")

        assert checked > 50, f"{name} 里只解析到 {checked} 个实现位置，格式或已改变"
        assert not missing, f"{name} 指向了不存在的文件：{missing}"
