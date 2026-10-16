"""The framework-readiness page, held to the repository it describes.

Every other document here says what the platform does. `docs/framework-readiness.md` answers a
different question -- *can I build on this without forking it* -- and a page like that is where
claims go to live unexamined. Each row names the artifact that provides a capability and the
check that holds it, so the page cannot describe code that has moved or a test that has been
deleted.

What this checks is the citations, not the judgement. Whether "multi-tenant isolation" is a
framework-grade capability is an argument the page makes in prose; whether
`tenancy.py` and `test_multi_tenancy.py` still exist is a fact, and a page of dead references is
how a gap becomes invisible.

The `Not there yet` table is checked too, in the opposite direction: it must be non-empty. A
project that deletes its own gap list to look finished has stopped being honest about the one
thing a new adopter most needs to know.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "docs" / "framework-readiness.md"

# A row's third column names a test module, optionally with `::test_name`.
CITATION = re.compile(r"`(tests/[A-Za-z0-9_/]+\.py)(?:::([A-Za-z0-9_]+))?`")
ARTIFACT = re.compile(r"`((?:backend|frontend|deploy)/[A-Za-z0-9_./-]+)`")


def _rows() -> list[tuple[str, str]]:
    """`(capability, whole row text)` for every table row on the page."""
    rows = []
    for line in PAGE.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| ") or line.startswith("| Capability") or line.startswith("|---"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) >= 3:
            rows.append((cells[0], line))
    return rows


def test_the_page_exists_and_is_not_a_stub() -> None:
    assert PAGE.exists(), "docs/framework-readiness.md 不见了——这正是它要防止的那种消失"
    rows = _rows()
    assert len(rows) >= 25, f"只解析到 {len(rows)} 行，页面像是被截断了"


def test_every_cited_artifact_still_exists() -> None:
    """A capability row pointing at a moved file describes nothing.

    Checked against the filesystem rather than by reading the page: the failure this catches is
    a rename or a deletion, and reading the page would only confirm that it says what it says.
    """
    missing: list[str] = []
    for capability, row in _rows():
        for path in ARTIFACT.findall(row):
            if not (ROOT / path).exists():
                missing.append(f"{capability} → {path}")
    assert not missing, "以下能力行指向的文件已经不存在——要么路径错了，要么它真的没了：\n  " + "\n  ".join(missing)


def test_every_cited_check_still_exists() -> None:
    """And a row pointing at a deleted test is a capability nobody verifies any more.

    `::test_name` is resolved inside the file rather than trusted: a renamed test would otherwise
    leave the citation matching a module that no longer holds it, which reads as covered.
    """
    missing: list[str] = []
    for capability, row in _rows():
        for module, function in CITATION.findall(row):
            path = ROOT / module
            if not path.exists():
                missing.append(f"{capability} → {module}（文件不存在）")
                continue
            if function and f"def {function}(" not in path.read_text(encoding="utf-8"):
                missing.append(f"{capability} → {module}::{function}（函数不存在）")
    assert not missing, "以下能力行引用的检查已经不存在：\n  " + "\n  ".join(missing)


def test_every_row_says_where_the_capability_lives_and_what_holds_it() -> None:
    """A row with an empty third column is a capability that was never verified.

    The page's own argument is that a capability nobody checks is a claim rather than a
    capability, so a row that cites nothing is the page contradicting itself.
    """
    bare = [capability for capability, row in _rows() if not CITATION.search(row)]
    assert not bare, "以下能力行没有引用任何检查——它们就是本页所说的「主张」：\n  " + "\n  ".join(bare)


def test_the_gap_section_is_present_and_every_gap_states_its_cost() -> None:
    """The section a project deletes first when it wants to look finished.

    Its absence would not fail anything else: the capability tables above would still parse, the
    citations would still resolve, and the page would read as a framework with no caveats. That
    is the failure this asserts against.

    **What it deliberately does not assert is that there *are* gaps.** The first version required
    at least five rows, which made this file a reason for the project to stay unfinished --
    closing a gap would have failed a test, and the way out would have been to invent one. A
    check that forbids the state it is measuring has the sign backwards.

    What it holds instead is the shape of whatever is there: a gap names what it costs the
    reader, because "not done" without a consequence is a note rather than an answer. And the
    day there are none, the section has to say that in a line rather than being deleted, so that
    the emptiness is a statement somebody made rather than a section that went missing.
    """
    text = PAGE.read_text(encoding="utf-8")
    assert "## Not there yet" in text, "缺口一节被删掉了——那不是页面变好了"

    gaps = text.split("## Not there yet", 1)[1]
    rows = [line for line in gaps.splitlines() if line.startswith("| **")]

    if not rows:
        assert re.search(r"nothing (is )?(outstanding|left|to report)", gaps, re.IGNORECASE), (
            "缺口一节空了，但没有用一句话说明它为什么是空的。一节空白与一节被删掉，读者分不出区别。"
        )
        return

    # Each row is `| **what is missing** | what it costs |`. A row that names the gap and not
    # the consequence leaves the evaluator to guess, which is the same problem as no row.
    costless = [row for row in rows if len([cell for cell in row.strip("|").split("|") if cell.strip()]) < 2]
    assert not costless, "以下缺口没有说明它对使用者意味着什么：\n  " + "\n  ".join(costless)


@pytest.mark.parametrize(
    "capability",
    ["Install from a package index", "Multi-tenant isolation", "A preflight that **refuses**"],
)
def test_the_page_covers_the_questions_a_framework_is_judged_on(capability: str) -> None:
    """Adopt, govern, operate -- the three an evaluator asks about in that order.

    A floor rather than a checklist: the point is that deleting a whole section to shorten the
    page fails here, while adding rows does not.
    """
    assert capability in PAGE.read_text(encoding="utf-8")


def test_the_page_is_reachable_from_the_README() -> None:
    """An unlinked page is a page nobody evaluates against.

    `tests/test_documentation_links.py` checks that links resolve; this checks that the one
    link that matters for this page was not simply left out.
    """
    for name in ("README.md", "README.zh-CN.md"):
        readme = (ROOT / name).read_text(encoding="utf-8")
        assert "framework-readiness.md" in readme, (
            f"{name} 没有指向框架成熟度这一页——读者不会找到它。两份 README 都要有：只在一份里就等于只对一半读者可见。"
        )
