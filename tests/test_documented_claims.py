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

    **And a row with no `Covers` cell is the same failure with the number kept** -- which is
    what `docs/testing.md` had for `test_metadata_flow.py`, eighty tests described by nothing.
    """
    counts = _collected_counts()
    # The table moved out of the README when the entry point was shortened. Both language
    # versions carry it, and both are checked: a breakdown that is right in one language and
    # stale in the other is worse than one place being wrong, because the reader who checks
    # the stale copy has no reason to suspect the other exists.
    actual = {Path(path).name: count for path, count in counts.items()}
    problems: list[str] = []

    for name in ("testing.md", "testing.zh-CN.md"):
        documented = {
            row["name"]: (int(row["count"]), row["covers"].strip())
            for row in (
                re.match(r"^\| `(?P<name>test_\S+\.py)` \| (?P<count>\d+) \| (?P<covers>.*) \|$", line)
                for line in (ROOT / "docs" / name).read_text(encoding="utf-8").splitlines()
            )
            if row
        }
        for missing_name in sorted(set(actual) - set(documented)):
            problems.append(f"{name}: 缺少 {missing_name} 的行——这个测试套件读者找不到")
        for gone in sorted(set(documented) - set(actual)):
            problems.append(f"{name}: {gone} 这一行的测试文件不存在了——它描述的是已经不在的覆盖")
        for shared, (count, covers) in sorted(documented.items()):
            if shared in actual and actual[shared] != count:
                problems.append(f"{name}: {shared} 写着 {count}，实际 {actual[shared]}")
            if not covers:
                problems.append(f"{name}: {shared} 的「覆盖」一栏是空的——数字留下了，句子没有了")

    assert not problems, "两份分布表与实际测试文件不符：\n  " + "\n  ".join(problems)


def _sync_module():
    """Import `scripts/sync_test_counts.py` by path: it is a script, not a package module."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "sync_test_counts_under_test", ROOT / "scripts" / "sync_test_counts.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_the_sync_script_writes_exactly_what_the_checks_above_require() -> None:
    """One copy of the patterns, because two copies is how this chore came about.

    Adding a test used to mean editing six places by hand, and the checks above would fail until
    all six agreed. `scripts/sync_test_counts.py` does the six, which is the right home for a
    mechanical edit -- but only if the script and the checks cannot disagree. A script whose
    pattern stops matching a reworded badge would report "nothing to do" and exit 0, the next
    person would believe it, and the check would then fail on a file the script had just called
    current.

    So the script is the authority and this asserts against its own output: running it over the
    committed files must change nothing, and it must not report anything for a person either.
    The failure message names the command rather than the six edits.
    """
    module = _sync_module()
    per_file = _collected_counts()
    total = sum(per_file.values())
    problems: list[str] = []

    for filename in module.documents():
        current = (ROOT / filename).read_text(encoding="utf-8")
        wanted, unresolved = module.sync(current, filename, {Path(p).name: n for p, n in per_file.items()}, total)
        if wanted != current:
            problems.append(f"{filename}: 数量不是最新的")
        # `unresolved` is the half a script must not guess at: a test file with no row needs a
        # sentence, and a row for a file that is gone needs a decision about the document.
        problems.extend(unresolved)

    assert not problems, (
        "文档里的测试数量与 `scripts/sync_test_counts.py` 应当写出的不一致。"
        "这个脚本就是这件事的归口，所以先运行它，再回来看这里：\n"
        "    python scripts/sync_test_counts.py\n  " + "\n  ".join(problems)
    )


def test_the_sync_script_changes_a_stale_number_and_refuses_to_invent_prose() -> None:
    """The check above passes trivially if `sync` never changes anything.

    Same shape as the quote scanner in `tests/test_error_codes.py`: a text-rewriting function
    that has quietly stopped matching looks exactly like a file that is up to date. So it is run
    against a doctored count on both sides -- one that must move, and one that must be reported
    instead of written.
    """
    module = _sync_module()
    grown = {"test_alpha.py": 12, "test_beta.py": 5}

    # A whole-enough page: the total sentence *and* the table. Both are claims the script knows
    # how to update, and passing only the table would report the missing sentence -- correctly,
    # since a pattern that stops matching is what `--check` exists to catch.
    table = "**17 tests**, all passing.\n\n| File | Count | Covers |\n|---|--:|---|\n"
    table += "| `test_alpha.py` | 9 | 甲 |\n| `test_beta.py` | 5 | 乙 |\n"

    wanted, unresolved = module.sync(table, "docs/testing.md", grown, 17)
    assert "| `test_alpha.py` | 12 | 甲 |" in wanted, wanted
    assert "| `test_beta.py` | 5 | 乙 |" in wanted, wanted
    assert not unresolved, unresolved

    # A new file: the number is mechanical, the sentence is not, and a script that wrote one
    # would be writing documentation nobody read.
    wanted, unresolved = module.sync(table, "docs/testing.md", {**grown, "test_gamma.py": 3}, 20)
    assert "test_gamma" not in wanted
    assert any("test_gamma.py" in note for note in unresolved), unresolved

    # A row for a file that is gone: reported, not deleted -- removing it is a judgement about
    # the document rather than a number to fill in.
    wanted, unresolved = module.sync(table, "docs/testing.md", {"test_beta.py": 5}, 5)
    assert "test_alpha.py" in wanted
    assert any("test_alpha.py" in note for note in unresolved), unresolved

    # And a reworded badge is reported rather than silently skipped -- the whole point of
    # `--check`, since a pattern that stops matching looks exactly like a current file.
    _wanted, unresolved = module.sync("no badge here\n", "README.md", grown, 17)
    assert len(unresolved) == 2, unresolved  # the badge and the prose sentence


def test_each_distribution_table_has_a_sentence_in_its_own_language() -> None:
    """The Chinese table held forty-five rows of English, and every check on it passed.

    A count is a number, so the counters above catch a stale one -- but a row whose number is
    right and whose *sentence* is in the wrong language reads as a correct row to everything
    that looks at it. `docs/testing.zh-CN.md` is the page a Chinese reader is sent to, and it
    was, for forty-four of its rows, the English page again: the same reading, in the language
    they did not open it for. Two more rows said nothing at all -- an empty `Covers` cell --
    and an empty cell is the same failure with the number kept.

    `test_ui_messages.py` holds the *interface* to this standard. Nothing held the documents to
    it, on the reasoning that prose cannot be checked -- which is true of whether a translation
    is any good and false of whether it is there.

    A floor, not a ceiling: a Chinese row may carry identifiers (`SchemaBundle`, `tenant_id`,
    `--platform-db`, `OWL/RDFS/SHACL`), because those are the names of things. What it may not
    be is *only* those.
    """
    problems: list[str] = []
    for name in ("testing.md", "testing.zh-CN.md"):
        chinese = name.endswith("zh-CN.md")
        for number, line in enumerate((ROOT / "docs" / name).read_text(encoding="utf-8").splitlines(), 1):
            if not line.startswith("| `test_"):
                continue
            cells = [cell.strip() for cell in line.split("|")[1:-1]]
            if len(cells) < 3:
                continue
            covers = cells[2]
            if not covers:
                problems.append(f"{name}:{number} {cells[0]} 的「覆盖」一栏是空的")
            elif chinese and not re.search(r"[一-鿿]", covers):
                problems.append(f"{name}:{number} {cells[0]} 一栏是英文：{covers[:60]}")
            elif not chinese and re.search(r"[一-鿿]", covers):
                problems.append(f"{name}:{number} {cells[0]} 一栏是中文：{covers[:60]}")
    assert not problems, "下面这些行不是本页语言，或者什么都没写：\n  " + "\n  ".join(problems)


def test_the_changelog_states_each_change_type_once_per_release() -> None:
    """One `### Added` per release. The file had eleven.

    Appending by hand means appending a heading, because that is what the previous round
    left at the top of the block -- so `[Unreleased]` accumulated twenty headings, eleven
    of them `Added`, and a reader skimming for what changed this cycle read the same
    heading eleven times. Keep a Changelog allows one section per change type per release,
    and nothing checked it: unlike a wrong number, a duplicated heading is not a false
    claim, so no reader reports it and no counter catches it.

    Checked per release rather than over the file, so the released sections cannot drift
    the same way -- a heading repeated inside `[0.4.0]` is the same editing mistake.
    """
    seen: dict[str, list[str]] = {}
    release = "(文件开头)"
    for line in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            release = line[3:].strip()
        elif line.startswith("### "):
            seen.setdefault(release, []).append(line[4:].strip())

    repeated = {name: [t for t in types if types.count(t) > 1] for name, types in seen.items()}
    repeated = {name: sorted(set(types)) for name, types in repeated.items() if types}
    assert not repeated, (
        f"CHANGELOG 的同一版本下重复出现同名小节（Keep a Changelog 只允许每个版本每种类型一节）：{repeated}"
    )


def test_the_documented_endpoint_count_matches_the_http_layer() -> None:
    """The endpoint count is a claim about the API's size, so it has to be a real number.

    Counted from the app itself rather than by grepping decorators. A source-text count
    only saw routes declared on `app`, so moving routes onto an `APIRouter` made the
    number drop without any endpoint disappearing -- the measurement tracked the file
    layout instead of the surface it claimed to describe.

    **Both numbers, in both languages, and that is the fix rather than the ceremony.** The
    sentence used to read "156 endpoints, of which **31 are still declared in `api.py`** -- the
    app shell, `/health`, `/files`, `/metrics`, backups, and the demo bootstrap". All three
    parts had drifted and the check saw none of them, because it read one number out of one
    language: there are four app-level routes rather than 31, `/health`, `/files`, `/metrics`
    and the demo bootstrap all live in `routers/` now, and the 156 was never *of which* anything
    -- `declared_routes()` does not include the app's own routes at all. A number that is
    right and a sentence around it that is wrong is the harder failure to see, because the
    thing a counter checks is correct.
    """
    sys.path.insert(0, str(ROOT / "backend"))
    from fastapi.routing import APIRoute
    from ontology_platform.api import app, declared_routes

    routed = len(declared_routes())
    # What the app declares for itself: the single-page shell, and nothing else. Counted from
    # the app rather than from a list here, so a route added to `api.py` moves the number.
    shell = len([route for route in app.routes if isinstance(route, APIRoute)])

    problems: list[str] = []
    for name, routed_pattern, shell_pattern in (
        ("docs/limitations.md", r"has (\d+) endpoints", r"Four more are declared on the app itself"),
        ("docs/limitations.zh-CN.md", r"共 (\d+) 个端点", r"另有 (\d+) 个直接声明在 app 上"),
    ):
        text = (ROOT / name).read_text(encoding="utf-8")
        match = re.search(routed_pattern, text)
        if not match:
            problems.append(f"{name}: 找不到端点总数的句子（{routed_pattern}）")
        elif int(match.group(1)) != routed:
            problems.append(f"{name}: 声明 {match.group(1)} 个端点，实际 {routed}")

        # The shell count is stated in the same sentence; the Chinese side names it, the English
        # side says "Four" in words. Asserted as text on the English side so a change from 4 to
        # 5 fails here rather than passing on the word "Four" still being present.
        if name.endswith("zh-CN.md"):
            match = re.search(shell_pattern, text)
            if not match:
                problems.append(f"{name}: 找不到直接声明在 app 上的端点数量（{shell_pattern}）")
            elif int(match.group(1)) != shell:
                problems.append(f"{name}: 声明 {match.group(1)} 个直接路由，实际 {shell}")
        else:
            assert shell_pattern in text, f"{name}: 找不到直接声明在 app 上的端点的描述"
            assert "Four more are declared" in text and shell == 4, (
                f"英文页用文字写的「Four」与实际 {shell} 个直接路由不符——请同时改句子的措辞和这里"
            )

    assert not problems, "端点数量的描述与实际 HTTP 层不符：\n  " + "\n  ".join(problems)


def test_the_component_coverage_number_matches_the_component_tests() -> None:
    """The framework-readiness gap row counts tables, so the count has to come from the file.

    It read "component tests cover five tables" while the file covered seven -- and grew to
    thirteen in one round. A number in a **gap list** is trusted more than one in a feature list,
    because the page has already shown it is willing to admit to shortfalls.

    Counted by the convention the file follows: a case that reads a whole table is named
    `renders a value in every cell of ...`. That convention is the contract -- a case that reads
    a table without saying so would be invisible here, which is why the transitions case was
    renamed to follow it rather than exempted.
    """
    source = (ROOT / "frontend" / "src" / "components" / "TableColumns.test.tsx").read_text(encoding="utf-8")
    tables = len(re.findall(r"it\('renders a value in every cell of ", source))

    claimed = re.search(
        # Hyphenated number words included: the count reached "twenty-one", and `\w+` stops at
        # the hyphen, matching "twenty" and then failing to find " tables across".
        r"cover ([\w-]+) tables across ([\w-]+) screens",
        (ROOT / "docs" / "framework-readiness.md").read_text(encoding="utf-8"),
    )
    assert claimed, "框架成熟度页面上的组件测试那一行改写了，这里要跟着改"
    words = {
        "five": 5,
        "seven": 7,
        "thirteen": 13,
        "fourteen": 14,
        "fifteen": 15,
        "sixteen": 16,
        "seventeen": 17,
        "eighteen": 18,
        "nineteen": 19,
        "twenty": 20,
        "twenty-one": 21,
        "twenty-two": 22,
        "twenty-three": 23,
        "twenty-four": 24,
        "twenty-five": 25,
        "twenty-six": 26,
        "twenty-seven": 27,
        "twenty-eight": 28,
        "twenty-nine": 29,
        "thirty": 30,
        "thirty-one": 31,
        "thirty-two": 32,
        "thirty-three": 33,
        "thirty-four": 34,
        "thirty-five": 35,
        "thirty-six": 36,
        "thirty-seven": 37,
        "thirty-eight": 38,
        "thirty-nine": 39,
        "forty": 40,
        "forty-one": 41,
        "forty-two": 42,
        "forty-three": 43,
        "forty-four": 44,
    }
    asserted = words.get(claimed.group(1))
    assert asserted is not None, (
        f"这一行用了一个这里认不出的数词：「{claimed.group(1)}」——数字会漂，所以它必须能被数出来。"
    )
    assert asserted == tables, (
        f"框架成熟度页面说组件测试覆盖 {claimed.group(1)}（{asserted}）张表，"
        f"而 TableColumns.test.tsx 里有 {tables} 个「每格都有内容」的用例。"
    )


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
    from ontology_platform import (
        adapters,
        automation,
        conversations,
        decisions,
        events,
        governance,
        onboarding,
        relations,
        semantic_kernel,
    )

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
        "CONSISTENCY_STATUS": set(semantic_kernel.CONSISTENCY_STATUSES),
        "NEXT_ACTION": set(automation.NEXT_ACTIONS),
        "RULE_STATUS": set(governance.VALID_RULE_STATUSES),
        "EXECUTION_STATUS": set(automation.EXECUTION_STATUSES),
        "CONVERSATION_STATUS": set(conversations.CONVERSATION_STATUSES),
        "FEEDBACK_STATUS": set(conversations.FEEDBACK_STATUSES),
        "CONNECTION_STATUS": set(adapters.CONNECTION_STATUSES),
        "ONBOARDING_STEP_STATUS": set(onboarding.ONBOARDING_STEP_STATUSES),
        # Added with the sweep that fixed eleven columns rendering their enum raw: a map is
        # only half the fix, and a map that does not know a value the backend produces puts
        # the raw identifier back on the screen in both languages.
        "MAPPING_TYPE": set(relations.MAPPING_TYPES),
        "DECISION_TYPE": set(decisions.DECISION_TYPES),
        "DECISION_STATUS": set(semantic_kernel.DECISION_STATUSES),
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


# Modules with no test file that names them, and why that is fine. Each is exercised through
# the module that imports it; naming that here is the point -- an allowance with a reason is
# a statement somebody can check, and a missing entry is a module nobody has tried.
COVERED_TRANSITIVELY = {
    # Imported by `api.py` and driven through the app by `test_frontend_serving.py`, which
    # asks for the SPA routes rather than for these two functions.
    "frontend_runtime",
}


def test_every_module_is_named_somewhere_in_the_suite() -> None:
    """Which modules have no test is a question the repository can answer.

    I have twice written down what was "not covered" from memory and been wrong both times --
    once claiming the export, codegen and extension-combination paths had no check, when they
    have twenty-two tests between them. A claim about coverage that nobody verified is the
    same defect as a claim about a test count that nobody counted, and this file exists for
    that shape.

    The assertion is weak on purpose: a module *named* in a test file is not a module that is
    tested well. What it catches is the module that arrives with nothing at all, which is how
    a feature module with no test gets merged.
    """
    import re as regex

    tested_text = "\n".join(path.read_text(encoding="utf-8") for path in TESTS.glob("test_*.py"))
    modules = sorted(
        path.stem for path in (ROOT / "backend" / "ontology_platform").glob("*.py") if path.stem != "__init__"
    )
    assert len(modules) > 50, f"只枚举到 {len(modules)} 个模块"

    unnamed = {name for name in modules if not regex.search(rf"\b{regex.escape(name)}\b", tested_text)}
    unexpected = sorted(unnamed - COVERED_TRANSITIVELY)
    assert not unexpected, (
        "以下模块没有任何测试文件提到过——要么给它一个测试，"
        f"要么在 COVERED_TRANSITIVELY 里写明它经由谁被覆盖：{unexpected}"
    )


def test_every_documented_cli_flag_exists() -> None:
    """Documentation names commands and flags; renaming one leaves the other behind.

    A flag in a copied command is worse than a wrong number: the reader pastes it, gets
    `unrecognized arguments`, and now doubts the document rather than the flag. The
    per-file table in `docs/testing.md` cannot see this -- it counts tests, not commands.

    Scan rather than list, so a command added to a guide is checked the moment it is
    written. `docs/` and both READMEs, in `bash` blocks, for invocations of the CLI.
    """
    import re as regex

    sys.path.insert(0, str(ROOT / "backend"))
    from ontology_platform.cli import build_parser

    parser = build_parser()
    subcommands = next(action for action in parser._actions if getattr(action, "choices", None))
    flags = {
        name: {option for action in command._actions for option in action.option_strings}
        for name, command in subcommands.choices.items()
    }

    documents = list((ROOT / "docs").glob("*.md"))
    documents += [ROOT / "README.md", ROOT / "README.zh-CN.md"]

    # `python -m ontology_platform.cli` and the installed `aletheia` are the same program.
    invocation = regex.compile(
        r"(?:\.venv/bin/python -m ontology_platform\.cli|python -m ontology_platform\.cli|aletheia)\s+([a-z-]+)(.*)"
    )

    checked = 0
    unknown: list[str] = []
    for document in documents:
        text = document.read_text(encoding="utf-8")
        for block in regex.findall(r"```(?:bash|shell|sh)\n(.*?)```", text, regex.DOTALL):
            for line in block.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                match = invocation.match(line)
                if match is None or match.group(1) not in flags:
                    continue
                checked += 1
                used = set(regex.findall(r"(?<!\w)(--[a-z][a-z-]*)", match.group(2)))
                for flag in sorted(used - flags[match.group(1)]):
                    unknown.append(f"{document.name}: aletheia {match.group(1)} {flag}")

    assert checked > 20, f"只在文档里找到 {checked} 条命令示例，扫描方式或已失效"
    assert not unknown, "文档里的命令用了不存在的选项：\n  " + "\n  ".join(unknown)


def test_every_design_document_says_it_is_one() -> None:
    """`01`–`04` are the project's earliest writing, and nothing inside them said so.

    `docs/README.md` lists them with a "gap vs implementation" column, but a reader who
    arrives at one of the files directly -- a link, a search result, a directory listing --
    sees a specification that reads as current. `04` stated 「当前支持 SQLite，并提供
    PostgreSQL、MySQL 适配入口」, which stopped being true the moment the other two dialects
    became real and CI started running both as service containers.

    Asserted rather than remembered: the set is a glob, so a fifth design document cannot
    join it without carrying the same note and the two documents that are checked against
    the code.
    """
    design_docs = sorted((ROOT / "docs").glob("0*.md"))
    assert len(design_docs) >= 4, f"没有找到立项阶段的设计稿：{design_docs}"
    index = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    for path in design_docs:
        text = path.read_text(encoding="utf-8")
        assert "这是立项阶段的设计稿" in text, f"{path.name} 没有说明自己是历史文档"
        for target in ("capabilities.md", "limitations.md"):
            assert target in text, f"{path.name} 没有指向 {target}，而判断现状要看那一份"
        assert path.name in index, f"{path.name} 没在 docs/README.md 的设计文档表里"
