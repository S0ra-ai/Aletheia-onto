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
