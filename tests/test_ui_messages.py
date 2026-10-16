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


def test_the_workbench_action_items_speak_the_readers_language() -> None:
    """The workbench is the first screen, and its action list was the last Chinese on it.

    The server builds those sentences -- it is the half that knows the counts -- and sends
    them in Chinese beside a stable `code`. The console renders the sentence from its own
    dictionary when it knows the code, and keeps the server's when it does not. This asserts
    the two sides agree on the vocabulary, in both directions:

    - a code the backend can emit but the console cannot name is an English interface with one
      Chinese list in the middle of it, which is exactly what this fixes;
    - a code in the console that the backend cannot emit is a translation of a sentence nobody
      will ever see -- the failure mode `CONSISTENCY_STATUS`'s `inconsistent` already had once.
    """
    import sys

    sys.path.insert(0, str(ROOT / "backend"))
    from ontology_platform.workbench import ACTION_ITEM_CODES, _action_items

    source = (ROOT / "backend" / "ontology_platform" / "workbench.py").read_text(encoding="utf-8")
    emitted = set(re.findall(r'"code":\s*"([a-z_]+)"', source))
    assert emitted == set(ACTION_ITEM_CODES), (
        "workbench.py 里实际写出的 code 与 ACTION_ITEM_CODES 对不上；"
        f"仅代码有 {sorted(emitted - set(ACTION_ITEM_CODES))}，仅常量有 {sorted(set(ACTION_ITEM_CODES) - emitted)}"
    )

    # Walked through every item the builder can produce rather than trusting the tuple: a
    # branch that returns early would leave a code unreachable while still listed.
    built: set[str] = set()
    for data_sources in ({"total": 0, "scanned": 0, "unscanned": 0}, {"total": 2, "scanned": 1, "unscanned": 1}):
        for ontologies in (
            {"total": 0, "objects": 0, "unboundObjects": 0},
            {"total": 1, "objects": 6, "unboundObjects": 3},
        ):
            for governance in (
                {"pendingMappings": 0, "reviewableTransitions": 0},
                {"pendingMappings": 5, "reviewableTransitions": 2},
            ):
                for rules in ({"total": 0, "objectsWithoutRules": 0}, {"total": 4, "objectsWithoutRules": 1}):
                    # Three states, not two: `open_feedback` and `escalated_conversations`
                    # are branches of one `if/elif`, so a state with both set only ever
                    # produces the first -- and a matrix that stopped there would report the
                    # second code as unreachable when it is merely unreached.
                    for feedback in (
                        {"incorrect": 0, "escalated": 0, "openItems": 0},
                        {"incorrect": 2, "escalated": 1, "openItems": 3},
                        {"incorrect": 0, "escalated": 0, "openItems": 3},
                    ):
                        built.update(
                            item["code"]
                            for item in _action_items(data_sources, ontologies, governance, rules, feedback)
                        )
    assert built == set(ACTION_ITEM_CODES), (
        f"构造不出这些 code：{sorted(set(ACTION_ITEM_CODES) - built)}；多出来的是：{sorted(built - set(ACTION_ITEM_CODES))}"
    )

    declared = set(_entries())
    missing = [f"workbench.item.{code}.{field}" for code in ACTION_ITEM_CODES for field in ("title", "detail")]
    unknown = sorted(key for key in missing if key not in declared)
    assert not unknown, f"字典里缺少这些句子，英文界面上会露出服务端的中文：{unknown}"
