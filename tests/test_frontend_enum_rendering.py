"""An enum rendered raw is an untranslated word, and no other check notices.

`labels.ts` maps a backend value to a phrase per language, and `label()` falls back to the
value itself -- deliberately, so an extension's own vocabulary still shows something. That
fallback is what makes a missing `label()` call invisible: `column_to_attribute` in a table
cell looks like data, not like a bug, and it looks the same in both languages. The dictionary
test cannot see it (the map may be perfect), the type test cannot see it (both are strings),
and the render sweep cannot see it (the cell is not empty).

Eleven columns were doing this. The mapping review queue's first column -- what kind of claim
you are about to confirm -- read `column_to_attribute`. The governance screen printed
`instance_assessment` and `success`. The workbench printed `approved`.

Two directions, and both are needed:

- **here**: a column whose `dataIndex` is an enum field must call `label()`.
- **in `test_documented_claims.py`**: the maps must know every value the backend produces.
  A map with a hole puts the raw identifier back on screen just as surely.

`dataType` is not in the list, and that is not an oversight: `integer` and `decimal` are the
names of types, they are what the source database calls them, and renaming them for display
would make the column disagree with the schema a reader is comparing it against.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "frontend" / "src"

# Fields whose values a label map translates, and therefore must never be printed directly.
# Listed by hand because the frontend's types declare them as `string` -- an enum is a
# vocabulary, and nothing in TypeScript says a `status` is one.
ENUM_FIELDS = frozenset(
    {
        "mappingType",
        "relationType",
        "relationKind",
        "decisionType",
        "decision",
        "status",
        "severity",
        "ruleType",
        "driftStatus",
        "category",
        "eventCategory",
        "kind",
    }
)

DATA_INDEX = re.compile(r"dataIndex:\s*'([A-Za-z_][A-Za-z0-9_]*)'")


def _object_spans(source: str) -> list[tuple[int, int]]:
    """Every `{...}` span in the file, innermost-last, with strings and comments ignored.

    Columns are object literals in an array, and the properties are in no fixed order -- a
    `render:` may precede its `dataIndex`. So the unit to judge is the enclosing literal, not
    the text after the match.

    Comments have to be skipped as well as strings, and that is not a detail: the first
    version of this skipped only quotes, and a comment containing a `"` -- 「加载…失败"」, in
    `DataSourceDetail.tsx` -- opened a string that never closed, swallowing every brace after
    it. The scan then found no enclosing object for six columns that were in fact fine, which
    is the shape of failure this whole file exists to catch: a checker that reports a defect
    because it cannot read.
    """
    spans: list[tuple[int, int]] = []
    stack: list[int] = []
    index = 0
    quote = ""
    while index < len(source):
        char = source[index]
        if quote:
            if char == "\\":
                index += 2
                continue
            if char == quote:
                quote = ""
        elif char == "/" and source[index : index + 2] == "//":
            while index < len(source) and source[index] != "\n":
                index += 1
            continue
        elif char == "/" and source[index : index + 2] == "/*":
            end = source.find("*/", index + 2)
            index = len(source) if end == -1 else end + 2
            continue
        elif char in "'\"`":
            quote = char
        elif char == "{":
            stack.append(index)
        elif char == "}" and stack:
            spans.append((stack.pop(), index))
        index += 1
    return spans


def _enclosing_object(source: str, position: int, spans: list[tuple[int, int]]) -> str:
    """The smallest object literal containing `position`, or "" when there is none."""
    containing = [(start, end) for start, end in spans if start < position < end]
    if not containing:
        return ""
    start, end = min(containing, key=lambda span: span[1] - span[0])
    return source[start : end + 1]


def _raw_enum_columns() -> list[str]:
    """Every `file:line  field` where an enum field is rendered without `label()`."""
    raw: list[str] = []
    for path in sorted(SRC.rglob("*.tsx")):
        source = path.read_text(encoding="utf-8")
        spans = _object_spans(source)
        for match in DATA_INDEX.finditer(source):
            field = match.group(1)
            if field not in ENUM_FIELDS:
                continue
            column = _enclosing_object(source, match.start(), spans)
            if "render:" in column and "label(" in column:
                continue
            line = source[: match.start()].count("\n") + 1
            raw.append(f"{path.relative_to(ROOT)}:{line}  dataIndex: '{field}'")
    return raw


def test_the_scan_is_looking_at_the_columns_it_claims_to() -> None:
    """A scanner that silently matches nothing passes for the same reason the bug was invisible.

    The floor is not the count today: it is the evidence that the regex still finds columns
    and that the enclosing-object walk still resolves them. A file list that came back empty
    -- a bad glob, a moved directory -- would report a clean sweep of nothing.
    """
    columns = 0
    for path in sorted(SRC.rglob("*.tsx")):
        source = path.read_text(encoding="utf-8")
        spans = _object_spans(source)
        for match in DATA_INDEX.finditer(source):
            if match.group(1) in ENUM_FIELDS:
                assert _enclosing_object(source, match.start(), spans), (
                    f"{path.relative_to(ROOT)} 的 dataIndex 落在一个找不到的对象字面量里，扫描器的括号匹配已经失效"
                )
                columns += 1
    assert columns >= 20, f"只找到 {columns} 个枚举列，扫描器没有在看这些页面"


def test_no_column_prints_an_enum_value_itself() -> None:
    """The eleven columns this found, and the next one somebody adds.

    The fix is not always `label()`: the workflow list's `status` column was removed, because
    `workflow_definition.status` is always `active` and nothing ever changes it -- a column
    whose every cell says the same word is not a column. A raw enum can mean "translate this"
    or "this should not be here", and both of them are better than printing it.
    """
    raw = _raw_enum_columns()
    assert not raw, (
        "这些表格列把枚举原样打了出来，没有走 labels.ts：\n  "
        + "\n  ".join(raw)
        + "\n（用 label(MAP, value)；若这个字段其实不会变化，考虑删掉这一列。）"
    )
