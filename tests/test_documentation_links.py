"""Documentation links resolve, and the entry points a newcomer needs exist.

Broken links are how documentation rots without anyone noticing: nothing fails, and the
reader who follows one concludes the project is unmaintained rather than that one line is
stale. Renaming a section silently breaks every link to it, and that rename looks harmless
in review.

Checked here rather than by a link-checking service because it must run before the push, and
because an internal anchor cannot be verified from outside the repository at all.

What is deliberately *not* checked: external URLs. A network call in the test suite makes the
build depend on someone else's uptime, and a suite that fails for unrelated reasons gets its
failures ignored.
"""

from __future__ import annotations

import re
import urllib.parse
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Every Markdown file that is part of the delivered documentation. `examples/` is excluded:
# it ships as sample material and its README describes a mock legacy system rather than this
# project's surface.
DOCUMENTS = sorted(path for path in [*ROOT.glob("*.md"), *ROOT.glob("docs/**/*.md")] if "node_modules" not in str(path))


def _anchors(text: str) -> set[str]:
    """Heading anchors as GitHub generates them.

    Approximated rather than exact: lowercase, strip inline markup and punctuation, spaces to
    hyphens. Close enough that a real broken link is caught, and loose enough that a heading
    containing an unusual character does not produce a false failure -- which is what would
    get this test deleted.
    """

    def slug(title: str) -> str:
        cleaned = re.sub(r"[`*]", "", title.strip().lower())
        cleaned = re.sub(r"[^\w\u4e00-\u9fff\- ]", "", cleaned)
        return cleaned.replace(" ", "-")

    return {slug(match.group(2)) for match in re.finditer(r"^(#{1,6})\s+(.+)$", text, re.MULTILINE)}


@pytest.mark.parametrize("document", DOCUMENTS, ids=lambda path: str(path.relative_to(ROOT)))
def test_internal_anchors_resolve(document: Path) -> None:
    """A link to a renamed section is silently dead.

    This is the failure that made the check worth writing: `README.md` is over a thousand
    lines with sixty-odd headings, and its own table of contents links into them.
    """
    text = document.read_text(encoding="utf-8")
    anchors = _anchors(text)

    broken = []
    for match in re.finditer(r"\[([^\]]+)\]\(#([^)]+)\)", text):
        target = urllib.parse.unquote(match.group(2))
        if target not in anchors:
            broken.append(f"[{match.group(1)}](#{target})")

    assert not broken, f"{document.relative_to(ROOT)} 中的内部锚点失效: {broken}"


@pytest.mark.parametrize("document", DOCUMENTS, ids=lambda path: str(path.relative_to(ROOT)))
def test_relative_file_links_exist(document: Path) -> None:
    """A link to a moved file is worse than no link: it implies the material exists."""
    text = document.read_text(encoding="utf-8")

    missing = []
    for match in re.finditer(r"\[([^\]]+)\]\((?!#|https?:|mailto:)([^)]+)\)", text):
        raw = urllib.parse.unquote(match.group(2).split("#")[0]).strip()
        if not raw:
            continue
        candidate = (document.parent / raw).resolve()
        if not candidate.exists():
            missing.append(raw)

    assert not missing, f"{document.relative_to(ROOT)} 链接到不存在的文件: {sorted(set(missing))}"


def test_readme_has_no_empty_sections() -> None:
    """An empty heading is a section someone started and abandoned.

    `README.md` ended with a bare `## 配置` that duplicated a real section 250 lines earlier --
    a leftover that renders as an empty chapter and tells the reader the document is unfinished.

    A heading immediately followed by a *sub*heading is not empty: that is normal structure,
    and counting it would flag every well-organised document. What is flagged is a heading with
    nothing at all after it -- no prose and no subsection.
    """
    for document in DOCUMENTS:
        text = document.read_text(encoding="utf-8")
        lines = text.splitlines()
        empty = []
        for index, line in enumerate(lines):
            heading = re.match(r"^(#{2,6})\s+\S", line)
            if not heading:
                continue
            level = len(heading.group(1))
            has_content = False
            for item in lines[index + 1 :]:
                stripped = item.strip()
                next_heading = re.match(r"^(#{1,6})\s+\S", stripped)
                if next_heading:
                    # A deeper heading is this section's content; a sibling or shallower one
                    # ends it.
                    if len(next_heading.group(1)) > level:
                        has_content = True
                    break
                if stripped:
                    has_content = True
                    break
            if not has_content:
                empty.append(line.strip())
        assert not empty, f"{document.relative_to(ROOT)} 存在空章节: {empty}"


def test_the_readme_answers_where_to_start_before_it_explains_itself() -> None:
    """A newcomer must reach a runnable command early.

    This README is long on purpose -- it records trade-offs, not just usage -- but that made
    the first install command land past line 180, after the naming rationale and a product
    comparison. Someone evaluating the project in two minutes never got there.
    """
    for filename, nav_heading in (("README.md", "## Where to go"), ("README.zh-CN.md", "## 我想做什么")):
        text = ROOT.joinpath(filename).read_text(encoding="utf-8")
        lines = text.splitlines()

        install = next(
            (index for index, line in enumerate(lines) if "pip install aletheia-onto" in line),
            None,
        )
        assert install is not None, f"{filename} 未包含安装命令"
        assert install < 60, f"{filename} 首个安装命令在第 {install + 1} 行，太靠后——评估者读不到那里"

        # And a map, so a reader with a specific goal does not have to read linearly.
        assert nav_heading in text, f"{filename} 缺少按目的导航的入口表"


def test_both_readmes_stay_short_enough_to_read() -> None:
    """The entry point is not the manual.

    A reader deciding whether to try the project needs a different document from one
    implementing against it, and a single file cannot be both without failing the first. The
    Chinese README was 1139 lines before its nine long sections moved into `docs/`.

    The limit is generous rather than tight: the point is to catch a section quietly growing
    back, not to police paragraph counts.
    """
    for filename in ("README.md", "README.zh-CN.md"):
        length = len(ROOT.joinpath(filename).read_text(encoding="utf-8").splitlines())
        assert length < 260, f"{filename} 已 {length} 行——深度内容应移入 docs/ 并留链接"


def test_each_readme_links_to_the_other() -> None:
    """English-first, with the Chinese version one click away rather than lost in the tree."""
    english = ROOT.joinpath("README.md").read_text(encoding="utf-8")
    chinese = ROOT.joinpath("README.zh-CN.md").read_text(encoding="utf-8")
    assert "README.zh-CN.md" in english, "英文 README 未链接中文版"
    assert "README.md" in chinese, "中文 README 未链接英文版"


def test_every_screenshot_is_referenced_by_a_document() -> None:
    """An unreferenced image is one nobody will notice has gone stale.

    Screenshots were all re-captured against the current UI; the risk now is a page being
    renamed and its image quietly orphaned, so the file lingers while the claim it supported
    disappears.
    """
    images = sorted(path.name for path in ROOT.joinpath("docs", "images").glob("*.png"))
    assert images, "docs/images 下没有截图"

    corpus = "\n".join(path.read_text(encoding="utf-8") for path in DOCUMENTS)
    orphaned = [name for name in images if name not in corpus]
    assert not orphaned, f"以下截图未被任何文档引用: {orphaned}"


def test_the_docs_index_does_not_claim_shipped_features_are_missing() -> None:
    """Stale "not implemented" notes cost more than stale "implemented" ones.

    `docs/README.md` warned for a long time that `02-核心元模型设计` drew Event and State with
    no tables behind them. That was true when written and stopped being true when `events.py`
    shipped -- and a document telling a reader a feature is missing makes them build around its
    absence, or reject the project for lacking it. Nobody re-reads an index to check whether its
    warnings still apply.

    Asserted against the modules rather than against prose, so the check cannot drift with the
    text it guards.
    """
    index = ROOT.joinpath("docs", "README.md").read_text(encoding="utf-8")
    package = ROOT / "backend" / "ontology_platform"

    # Each claim the index used to make, paired with the module that refutes it.
    refuted = {
        "Event／State 无对应表": package / "events.py",
        "关系无基数": package / "relations.py",
        "无类型层级": package / "type_hierarchy.py",
    }
    for claim, module in refuted.items():
        if module.exists():
            assert claim not in index, (
                f"docs/README.md 仍声称「{claim}」，但 {module.name} 已实现它。"
                "声称某能力缺失会让读者绕开它，或据此否决整个项目。"
            )
