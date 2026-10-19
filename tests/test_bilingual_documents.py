"""The two language versions of a page, held to describing the same platform.

Every page here has a Chinese and an English edition, and the promise the README makes is
that they are the same document. Nothing held them to it, and both directions had drifted:

* `docs/quickstart.md` never mentioned `aletheia new` -- scaffolding a project instead of
  forking -- nor `codegen`, nor the OWL/SHACL export, nor what `demo` prints. A reader who
  opened the English quick start was told the framework does less than it does.
* `docs/capabilities.zh-CN.md` had no row for the installable package or the CLI.
* The English capability matrix cited **19 fewer modules** than the Chinese one: no axioms, no
  instance resolvers, no SSO, no tenant quotas, no audit reports, no deployment preflight, no
  conformance contracts, no workbench, no graph. On the page that answers "what does this do",
  an English reader counted two thirds of the framework.
* `docs/capabilities.zh-CN.md` and `docs/testing.zh-CN.md` each ended a sentence with a colon
  and then simply stopped, where the other language had a command to run.

**What is compared, and what is deliberately not.** Prose cannot be compared and should not
be -- a translation is not a transformation. Headings cannot be compared either: the two
`design-decisions` pages carry the same twelve decisions, one as `## N. Title` and the other
as bold lead-ins, and a heading count would call that a gap while reporting nothing. What *can*
be compared is what is language-neutral:

* **Fenced code blocks, by count.** A command, a JSON payload, a Python snippet is content
  rather than prose; only the comments inside it get translated. A different count means one
  edition documents something the other does not.
* **The module names a capability matrix cites.** `` `axioms.py` `` is spelled the same in both.

Both are floors. Neither can tell a well-translated sentence from a badly translated one --
`tests/test_ui_messages.py` and `scripts/i18n_audit.py` own the interface's version of that
question, and prose quality remains a thing a person reads.

The drift is one-directional in practice: the Chinese pages are written first and the English
ones follow. That is why this file compares *sets* rather than counts of anything translated,
and why the failure messages name both sides.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"

FENCE = re.compile(r"^\s*```")
MODULE = re.compile(r"`([a-z_0-9]+\.py)`")


def _pairs() -> list[tuple[Path, Path]]:
    """Every `X.md` that has an `X.zh-CN.md` beside it, plus the two READMEs.

    Discovered rather than listed: a new page added in one language is then checked from the
    moment it exists, which is when the other edition is most likely to be forgotten.
    """
    pairs = [
        (path, path.with_name(path.name[: -len(".md")] + ".zh-CN.md"))
        for path in sorted(DOCS.glob("*.md"))
        if not path.name.endswith(".zh-CN.md")
    ]
    pairs = [(en, zh) for en, zh in pairs if zh.exists()]
    readmes = (ROOT / "README.md", ROOT / "README.zh-CN.md")
    return [*pairs, readmes]


def _fenced_blocks(path: Path) -> list[str]:
    """The blocks themselves, in order, with their bodies."""
    blocks: list[str] = []
    opening = False
    current: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if FENCE.match(line):
            if opening:
                blocks.append("\n".join(current))
                current = []
            opening = not opening
            continue
        if opening:
            current.append(line)
    return blocks


def _module_names(path: Path) -> set[str]:
    """Every `something.py` the page names in backticks."""
    return set(MODULE.findall(path.read_text(encoding="utf-8")))


@pytest.mark.parametrize(("english", "chinese"), _pairs(), ids=lambda path: Path(path).name)
def test_both_editions_show_the_same_number_of_code_blocks(english: Path, chinese: Path) -> None:
    """A command in one edition and not the other is a reader told the framework does less.

    The quick start is where this matters most: the English one skipped `aletheia new`, the
    command that scaffolds a project rather than making you fork the repository -- which is the
    headline answer to "can I build on this without forking it".
    """
    left, right = _fenced_blocks(english), _fenced_blocks(chinese)
    assert len(left) == len(right), (
        f"{english.name} 有 {len(left)} 个代码块，{chinese.name} 有 {len(right)} 个。"
        "命令、JSON、代码片段不是散文——只有里面的注释会翻译，块本身应当两边都有。"
    )


def test_no_code_block_is_in_one_edition_only() -> None:
    """The same check at the level of the command, so the failure names what is missing.

    A count catches the drift; a command list says which one. The comparison strips each block
    to the invocations in it, because everything else -- comments, sample output, a Chinese
    verdict -- is exactly what a translation is allowed to change.
    """
    missing: list[str] = []
    for english, chinese in _pairs():
        # `aletheia <verb>` and `python -m <module>`: the parts a reader types, and the parts
        # that have no translation.
        commands = re.compile(r"\b(aletheia [a-z][a-z-]*|python -m \w+)")
        en = {match for block in _fenced_blocks(english) for match in commands.findall(block)}
        zh = {match for block in _fenced_blocks(chinese) for match in commands.findall(block)}
        # `aletheia serve` legitimately appears as a comment in one edition's sample output and
        # as a command in the other's; a name appearing somewhere in one file is enough.
        for name in sorted(en - zh):
            missing.append(f"{english.name} 里的 `{name}` 在 {chinese.name} 里没有")
        for name in sorted(zh - en):
            missing.append(f"{chinese.name} 里的 `{name}` 在 {english.name} 里没有")
    assert not missing, "两个语言版本的命令不一致——有一边的读者读到的能力比另一边少：\n  " + "\n  ".join(missing)


def test_each_edition_is_written_in_the_language_its_filename_claims() -> None:
    """`model-endpoints.md` was Chinese, so the English README sent its reader to `# 接入自定义模型服务`.

    That is the mirror of the drift this file was written for, and the harder one to notice: the
    page *exists*, the link *resolves*, and `test_documentation_links.py` is satisfied. Only a
    reader who does not read Chinese finds out, and they find out by landing on it.

    Four pages were in that state -- `model-endpoints.md`, `operations.md`,
    `production-checklist.md` and `architecture-debt.md` -- all written in Chinese under a
    filename that says otherwise. Three now have a Chinese edition under `.zh-CN.md` and an
    English one under `.md`.

    **Only paired pages are checked.** `01-总体架构.md` and the other design documents are
    Chinese-only on purpose and make no claim about a second edition; requiring them to be
    English would be requiring a translation nobody asked for. `docs/README.md` holds both
    languages in one file by design and is not paired either.

    The threshold is wide because the question is only "which language is this page in": every
    Chinese edition sits above 80% CJK and every English one below 30%, so anything in between
    is a page that mixes them and deserves a person's attention rather than a guess.
    """
    problems: list[str] = []
    for english, chinese in _pairs():
        en_share, zh_share = _cjk_share(english), _cjk_share(chinese)
        if en_share > 0.30:
            problems.append(f"{english.name} 有 {en_share:.0%} 的汉字——英文文件名，中文内容")
        if zh_share < 0.50:
            problems.append(f"{chinese.name} 只有 {zh_share:.0%} 的汉字——中文文件名，却不是中文")

    assert not problems, (
        "成对文档里有一份不是它文件名所说的那种语言。读者不会先读文件名再判断——"
        "他们会点进去，然后用自己不会读的语言读一整页：\n  " + "\n  ".join(problems)
    )


def _cjk_share(path: Path) -> float:
    """The share of CJK characters among CJK characters plus Latin words, in prose only.

    Code blocks are excluded: a page of Chinese prose is mostly `bash` and JSON, and counting
    identifiers would pull every technical document toward the middle.
    """
    fence = False
    prose: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if FENCE.match(line):
            fence = not fence
            continue
        if not fence:
            prose.append(line)
    text = "\n".join(prose)
    cjk = len(re.findall(r"[一-鿿]", text))
    words = len(re.findall(r"\b[A-Za-z][A-Za-z'-]+\b", text))
    return cjk / max(1, cjk + words)


def test_the_english_index_says_which_pages_are_chinese() -> None:
    """An index row that promises a page in your language and delivers another is a small trap.

    Three pages were in exactly that state: `model-endpoints.md`, `operations.md` and
    `production-checklist.md` were Chinese under English filenames, listed in this index as
    English pages. They have English editions now. What remains Chinese-only is the ADR
    directory, `CHANGELOG.md`, `ROADMAP.md`, `SECURITY.md`, `CONTRIBUTING.md`, the `01`–`04`
    design documents and `architecture-debt.md` -- a deliberate, coherent choice for a
    Chinese-first project, and one a reader should be told about rather than discover.

    **A row may link a Chinese page as long as it says so.** The word "Chinese" in the row is
    the marker; the note under the table explains the rest. Scoped to the main table because
    the design-documents section carries its own note, and a section-level statement is the
    right size for four documents that share one reason.
    """
    text = (DOCS / "README.md").read_text(encoding="utf-8")
    main_table = text.split("## Design documents", 1)[0]

    problems: list[str] = []
    for line in main_table.splitlines():
        if not line.startswith("| "):
            continue
        for target in re.findall(r"\]\(([^)#\s]+\.md)\)", line):
            path = (DOCS / target).resolve()
            if not path.exists() or _cjk_share(path) <= 0.30:
                continue
            if "Chinese" not in line:
                problems.append(f"docs/{target} 是中文页，但英文索引的这一行没说")

    assert not problems, (
        "英文索引把中文页当成英文页列出来了。读者不会先读文件名再判断，他们会点进去：\n  " + "\n  ".join(problems)
    )


def test_every_page_is_reachable_from_somewhere() -> None:
    """A page nothing links to is a page nobody reads, and one was sitting in the repository.

    `docs/production-checklist.md` -- 79 lines of pre-production checks, the list an operator
    works through before going live -- was reachable from nowhere. Not from the README, not
    from the deployment page, not from operations. It had been written, committed, and then
    orphaned by whatever edit removed the last link to it.

    Nothing noticed, and nothing could: `tests/test_documentation_links.py` checks that the
    links a page *has* resolve, which says nothing about a page no link points at. The
    framework-readiness page has had its own version of this check since it was written --
    "an unlinked page is a page nobody evaluates against" -- and it was only ever applied to
    that one page.

    A page linked only by another orphan is still an orphan, so reachability is computed from
    the READMEs outward rather than by counting references.
    """
    readmes = [ROOT / "README.md", ROOT / "README.zh-CN.md"]
    pages = {path.name: path for path in DOCS.glob("*.md")}
    link = re.compile(r"\]\(([^)#\s]+\.md)")

    reachable: set[str] = set()
    frontier = readmes
    seen_files: set[Path] = set()
    while frontier:
        page = frontier.pop()
        if page in seen_files or not page.exists():
            continue
        seen_files.add(page)
        for target in link.findall(page.read_text(encoding="utf-8")):
            name = Path(target).name
            # Only pages in `docs/` are this test's subject; the READMEs link all over.
            if name in pages and name not in reachable:
                reachable.add(name)
                frontier.append(pages[name])

    orphaned = sorted(set(pages) - reachable)
    assert not orphaned, (
        "这些文档从 README 出发沿着链接走不到——没人链接的页面就是没人读的页面：\n  "
        + "\n  ".join(f"docs/{name}" for name in orphaned)
        + "\n把它链到读者会去找它的地方（通常是 README 的文档索引，或它所属的那条路径上）。"
    )


def test_the_two_capability_matrices_name_the_same_modules() -> None:
    """The page that answers "what does this do", counted the way a reader counts it.

    Nineteen modules were named in the Chinese matrix and in no English row: `axioms.py`,
    `instance_resolver.py`, `sso.py`, `quotas.py`, `audit_reports.py`, `deployment.py`,
    `conformance.py`, `workbench.py`, `graph_view.py` and more. Each is a capability the
    platform has and the English page did not claim -- one third of the matrix, on the page an
    evaluator reads to decide whether to build on this.

    Modules rather than capability names because a module name is the one part of a row that
    does not get translated, and it is what a reader follows to check the claim.
    """
    english, chinese = DOCS / "capabilities.md", DOCS / "capabilities.zh-CN.md"
    en, zh = _module_names(english), _module_names(chinese)

    only_chinese = sorted(zh - en)
    only_english = sorted(en - zh)
    assert not only_chinese and not only_english, (
        "两份能力矩阵点名的模块不一致：\n"
        f"  只在中文里有：{only_chinese}\n"
        f"  只在英文里有：{only_english}\n"
        "每个模块都是一项能力，缺的那一边读到的就是更小的框架。"
    )


def test_no_line_of_an_english_page_is_a_chinese_sentence() -> None:
    """A page can be 95% English and still have a paragraph in the other language.

    That is what `docs/deployment.md` had: two lines explaining that the backend serves the
    admin console, written in Chinese inside the English page -- while the Chinese page did not
    have the paragraph at all. The whole-page language check passed, because two lines out of a
    hundred do not move a ratio; the reader who cannot read Chinese hits them anyway.

    **Prose only**: code fences are excluded, and a line is only reported when its Chinese
    characters outnumber its Latin ones -- so 「达梦」 in a table of database names, or a link
    that names both READMEs, stays where it is. The reverse direction is not checked: technical
    Chinese prose is dense with identifiers, and every attempt to flag Latin-heavy lines there
    reported paths and commands instead of untranslated sentences.
    """
    problems: list[str] = []
    for english, _chinese in _pairs():
        fence = False
        for number, line in enumerate(english.read_text(encoding="utf-8").splitlines(), 1):
            if FENCE.match(line):
                fence = not fence
                continue
            if fence:
                continue
            cjk = len(re.findall(r"[一-鿿]", line))
            latin = len(re.findall(r"[A-Za-z]", line))
            if cjk >= 4 and cjk > latin:
                problems.append(f"{english.name}:{number}: {line.strip()[:80]}")

    assert not problems, "英文页里出现了整行的中文句子。英文读者会直接撞上它：\n  " + "\n  ".join(problems)
