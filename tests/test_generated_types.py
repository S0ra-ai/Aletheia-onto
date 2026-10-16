"""The generated response types are current, and the generator does what it claims.

`frontend/src/types/index.ts` has been hand-mirrored since the beginning, and the reason given
for not generating it was correct: every endpoint returns `dict[str, object]`, so OpenAPI carries
no response schema and a generator reading OpenAPI would emit `unknown`. That reasoning is about
one route to the answer. `scripts/generate_types.py` takes the other one -- call the endpoint and
write down what came back -- and this file holds it to three claims.

**That the committed file is current.** Regenerating from an unchanged platform must produce a
byte-identical file, and this fails when it does not. That is what turns a backend field rename
into a diff on a generated file rather than into a table that quietly renders empty, which is how
seven blank-column defects arrived.

**That the generator can distinguish things.** The first version named every nested interface
after its key, so all twenty-one collapsed into one called `Items` holding the union of every
field in the API. It typechecked, and it would have told a reader that an audit entry has a
`confidence`. The unit tests below pin the naming and the empty-list case directly, because a
generator that produces plausible-looking wrong output is worse than none.

**That it sees fields the hand-written types do not list.** The generated file is only worth
having if it can disagree with what somebody wrote by hand.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "backend"))

GENERATED = ROOT / "frontend" / "src" / "types" / "generated.ts"


def test_the_generated_file_is_present_and_not_empty() -> None:
    assert GENERATED.exists(), "generated.ts 不在了。生成它：python scripts/generate_types.py"
    text = GENERATED.read_text(encoding="utf-8")
    assert text.count("export interface") >= 20, "生成文件里的接口太少，生成器多半没有取到数据"


def test_the_committed_file_matches_what_the_api_returns() -> None:
    """The whole point: a backend change shows up here rather than as an empty column.

    Regenerated in process rather than by shelling out, so a failure names the difference rather
    than reporting that a subprocess exited non-zero.
    """
    import generate_types

    expected = generate_types.generate()
    current = GENERATED.read_text(encoding="utf-8")
    if current == expected:
        return

    import difflib

    diff = "\n".join(
        difflib.unified_diff(current.splitlines(), expected.splitlines(), "committed", "regenerated", lineterm="", n=1)
    )
    pytest.fail(
        "generated.ts 与当前 API 返回的形状不一致。这**不是**生成器的问题，"
        "是接口变了——请看清下面每一处改动，确认是想要的，再运行 python scripts/generate_types.py：\n"
        f"{diff[:4000]}"
    )


# -- The generator's own behaviour --


def test_a_nested_interface_is_named_after_its_parent_not_its_key() -> None:
    """The defect that made the first version worthless and typecheck anyway.

    Every one of these endpoints carries an `items` list, so naming the nested interface after
    the key merged all of them into one called `Items` -- the union of every field the API has.
    Merged rather than rejected, which is what made it dangerous: it would have told a reader
    that an audit entry has a `confidence`.
    """
    import generate_types

    interfaces = generate_types.infer_types(
        {
            "First": {"items": [{"alpha": 1}]},
            "Second": {"items": [{"beta": "x"}]},
        }
    )
    assert "FirstItems" in interfaces and "SecondItems" in interfaces
    assert "Items" not in interfaces
    assert set(interfaces["FirstItems"]) == {"alpha"}
    assert set(interfaces["SecondItems"]) == {"beta"}


def test_an_empty_list_is_unknown_rather_than_null() -> None:
    """No evidence either way, and `null[]` would claim there is."""
    import generate_types

    assert generate_types._infer([]) == "unknown[]"


def test_a_field_missing_from_some_objects_is_optional() -> None:
    import generate_types

    interfaces = generate_types.infer_types({"Thing": [{"always": 1, "sometimes": "x"}, {"always": 2}]})
    assert interfaces["Thing"]["always"] == "number"
    assert interfaces["Thing"]["sometimes?"] == "string"


def test_two_types_for_one_field_become_unknown_rather_than_a_guess() -> None:
    """`unknown` is a prompt to look, which is the honest outcome of disagreement."""
    import generate_types

    interfaces = generate_types.infer_types({"Thing": [{"value": 1}, {"value": "x"}]})
    assert interfaces["Thing"]["value"] == "unknown"


def test_the_output_is_deterministic() -> None:
    """Without this, "the committed file is current" is not a testable claim.

    The set of interfaces depends on dict iteration order, which is insertion-ordered in Python
    and therefore stable within a run and not across them; the renderer sorts, and this is what
    holds it to that.
    """
    import generate_types

    payloads = {"Zeta": {"b": 1, "a": 2}, "Alpha": [{"y": 1, "x": 2}]}
    first = generate_types.render(generate_types.infer_types(payloads))
    second = generate_types.render(generate_types.infer_types(dict(reversed(list(payloads.items())))))
    assert first == second


def test_the_check_mode_reports_a_stale_file_rather_than_rewriting_it() -> None:
    """`--check` is what CI runs, so it has to fail rather than helpfully fix things."""
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "generate_types.py"), "--check", "--output", "/dev/null"],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 1
    assert "不符" in result.stderr


def test_the_screens_read_the_generated_declarations_where_they_can() -> None:
    """The step that makes the generated file *used* rather than merely present.

    `frontend/src/types/index.ts` still declares most of what the screens import, and that is
    correct where it does: for the endpoints the client normalises, the screen's type is the
    normalised shape rather than the wire one, and forcing it onto the generated declaration
    would mean deleting the normaliser that the blank-column defects were fixed by.

    What must not happen silently is the other direction -- a type that *can* be the generated
    one drifting back into a hand-written copy. This asserts that every alias present resolves,
    and that there is at least one, so the import cannot be dropped in a refactor and leave the
    generated file an orphan that nothing reads.

    `tsc` would catch a broken alias; it would not catch an orphan.
    """
    index = ROOT / "frontend" / "src" / "types" / "index.ts"
    source = index.read_text(encoding="utf-8")

    assert "from './generated'" in source, (
        "types/index.ts 不再引用生成文件了——生成物会变成没人读的孤儿，而它在 CI 里仍然每天被判为「最新」。"
    )

    aliases = re.findall(r"export type (\w+) = Generated\.(\w+);", source)
    assert aliases, "没有任何别名指向生成声明——这一层是空的"

    generated = GENERATED.read_text(encoding="utf-8")
    missing = [gen for _hand, gen in aliases if f"export interface {gen} " not in generated]
    assert not missing, (
        f"types/index.ts 指向了生成文件里没有的接口：{missing}。生成器改了命名或不再收录该端点，而界面仍在引用。"
    )
