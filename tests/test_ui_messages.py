"""The bilingual interface: what a machine can check about a translation.

A translation is a claim about another language, and a test cannot read English. What it can
read is the *shape*: that every key exists in both languages, that a key is defined once, and
that a sentence with a placeholder has the same placeholders in both -- a `{count}` dropped in
translation is a message that renders a literal brace to a user, and nothing else would notice.

This is deliberately not a spell-check or a fluency check. Those need a reader, which is why
the interface keeps both languages written in their own script: whoever reads it can see.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MESSAGES = ROOT / "frontend" / "src" / "i18n" / "messages"

# `'key': { zh: '...', en: '...' },` -- the dictionary files are TypeScript, and this reads
# them as text: importing them would need a JavaScript runtime in the test suite. The values
# are single-quoted by convention, and `_declared_keys` below counts what the files *declare*
# so an entry this regex cannot read fails the check instead of quietly escaping it.
ENTRY = re.compile(
    r"'(?P<key>[\w.]+)':\s*\{\s*zh:\s*'(?P<zh>(?:[^'\\]|\\.)*)'\s*,\s*en:\s*'(?P<en>(?:[^'\\]|\\.)*)'",
    re.DOTALL,
)
DECLARED = re.compile(r"^\s*'(?P<key>[\w.]+)':\s*\{", re.MULTILINE)
PLACEHOLDER = re.compile(r"\{(\w+)\}")


def _entries() -> dict[str, dict[str, str]]:
    found: dict[str, dict[str, str]] = {}
    files = sorted(path for path in MESSAGES.glob("*.ts") if path.name != "index.ts")
    assert files, f"没有找到消息文件：{MESSAGES}"
    for path in files:
        text = path.read_text(encoding="utf-8")
        declared = DECLARED.findall(text)
        parsed = list(ENTRY.finditer(text))
        assert len(declared) == len(parsed), (
            f"{path.name} 声明了 {len(declared)} 条、只读到 {len(parsed)} 条——"
            "有写法这个检查读不出来（值的引号必须成对且不带反引号），请改成 'key': { zh: '…', en: '…' }"
        )
        for match in parsed:
            key = f"{path.stem}.{match.group('key')}"
            assert key not in found, f"{key} 在 {path.name} 与别处重复定义"
            found[key] = {"zh": match.group("zh"), "en": match.group("en")}
    return found


def test_every_message_exists_in_both_languages() -> None:
    entries = _entries()
    # A floor, not a count: the per-file check above is what catches a parser that reads
    # nothing, and a message count that had to be updated every time would be noise.
    assert len(entries) >= 40, f"只找到 {len(entries)} 条消息，字典像是没被读到"
    missing = [key for key, value in entries.items() if not value["zh"].strip() or not value["en"].strip()]
    assert not missing, f"这些键缺一种语言：{sorted(missing)}"


def test_a_sentence_keeps_its_placeholders_in_both_languages() -> None:
    """`{count} 项` translated without `{count}` renders a literal brace, and the value is lost."""
    wrong = {
        key: (sorted(PLACEHOLDER.findall(value["zh"])), sorted(PLACEHOLDER.findall(value["en"])))
        for key, value in _entries().items()
        if sorted(PLACEHOLDER.findall(value["zh"])) != sorted(PLACEHOLDER.findall(value["en"]))
    }
    assert not wrong, f"占位符在两种语言里对不上：{wrong}"


def test_no_message_is_a_key_that_resolves_to_nothing() -> None:
    """`t()` renders ⟦key⟧ for an unknown key, on purpose, so it is visible in the interface.

    That makes an unfilled dictionary loud rather than blank — but only where somebody looks.
    This asserts that the keys a screen asks for exist at all.
    """
    declared = set(_entries())
    asked: set[str] = set()
    for path in (ROOT / "frontend" / "src").rglob("*.ts*"):
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"\bt\(\s*'([\w.]+)'", text):
            asked.add(match.group(1))
    # Namespaced keys in the dictionary are `<file>.<key>`; a call site writes the same string.
    unknown = sorted(key for key in asked if key not in declared and key != "shell")
    assert not unknown, f"界面里调用了字典里没有的键：{unknown}"
