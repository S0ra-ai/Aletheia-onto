"""The normalisers and the types the screens read, held to each other.

`api/index.ts` translates the endpoints whose wire spelling differs from the console's
(`can_read` -> `canRead`). Eleven normalisers do it, and the shape each one produces is declared
by hand in `types/index.ts` -- the maturity page calls this "the split is by hand", and it is.

What the compiler already covers, and what it does not:

* **A key the normaliser drops** is a type error. The return is annotated, so an object literal
  missing a required field does not compile.
* **A key the normaliser invents** is a type error too -- excess-property checking on a literal.
* **An optional field the normaliser never produces** is *not* an error. `createdAt?: string` is
  satisfied by never writing `createdAt`, and the screen then reads `undefined`. That is the one
  hole in the split, and it is the same shape as every blank-column defect in this repository:
  the type says a field is there, the data never carries it, and nothing fails.

The last check is what this file is for. The others are cheap enough to state anyway -- they
document the contract, and they fail loudly if someone replaces an annotated literal with a cast.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NORMALISE = ROOT / "frontend" / "src" / "api" / "normalise.ts"
INDEX_TYPES = ROOT / "frontend" / "src" / "types" / "index.ts"
GENERATED_TYPES = ROOT / "frontend" / "src" / "types" / "generated.ts"
NORMALISED_TS = ROOT / "frontend" / "src" / "types" / "normalised.ts"

SIGNATURE = re.compile(r"export const (?P<name>normalize\w+) = \(item: any\): (?P<type>\w+) => \(\{")
FIELD = re.compile(r"^\s{2}(?P<key>\w+):", re.MULTILINE)


def _normalisers() -> list[tuple[str, str, list[str], bool]]:
    """`(function, declared type, literal keys, spreads the wire row)` for each normaliser.

    Keys are read only at one level of indentation -- the body of every one of these is a flat
    object literal, and a nested object would otherwise contribute its own keys. A body that
    stops being flat should fail here rather than be silently mis-read, which is why the regex is
    anchored on exactly two spaces.
    """
    text = NORMALISE.read_text(encoding="utf-8")
    found: list[tuple[str, str, list[str], bool]] = []
    for match in SIGNATURE.finditer(text):
        body_start = match.end()
        depth = 1
        index = body_start
        while index < len(text) and depth > 0:
            if text[index] == "{":
                depth += 1
            elif text[index] == "}":
                depth -= 1
            index += 1
        body = text[body_start : index - 1]
        found.append((match.group("name"), match.group("type"), FIELD.findall(body), "...item" in body))
    return found


def _fields(type_name: str) -> list[str]:
    """The field names of an interface or object type, from either types file.

    `index.ts` first: for the normalised endpoints that is where the shape lives, and a same-named
    interface in `generated.ts` describes the *wire* row instead. Reading the wrong one would
    compare a normaliser against the thing it translates.

    **An alias is resolved, not skipped.** `export type PermissionRole = Generated.PermissionRoleRoles;`
    is how the seven migrated row types are declared, and `generated.ts` also contains an interface
    called `PermissionRole` -- the *response wrapper*, whose only field is `roles`. Falling through
    to that one compared the normaliser against the wrong declaration and reported two fields it
    was right to produce. The wrapper's name collides with the row's on purpose-ish; the alias
    says which one is meant.
    """
    index = INDEX_TYPES.read_text(encoding="utf-8")
    match = re.search(rf"export (?:interface|type) {type_name}\b[^{{=;]*\{{(.*?)\n\}}", index, re.S)
    if match:
        return re.findall(r"^\s*(\w+)\??:", match.group(1), re.MULTILINE)

    alias = re.search(rf"export type {type_name} = Generated\.(\w+);", index)
    target = alias.group(1) if alias else type_name
    generated = GENERATED_TYPES.read_text(encoding="utf-8")
    match = re.search(rf"export interface {target} \{{(.*?)\n\}}", generated, re.S)
    return re.findall(r"^\s*(\w+)\??:", match.group(1), re.MULTILINE) if match else []


def test_every_normaliser_names_a_type_that_exists() -> None:
    missing = [f"{name} -> {type_name}" for name, type_name, _keys, _spread in _normalisers() if not _fields(type_name)]
    assert not missing, "以下归一化函数声明的返回类型找不到定义：\n  " + "\n  ".join(missing)


def test_a_closed_normaliser_produces_exactly_the_fields_its_type_declares() -> None:
    """The normalisers whose body lists every field, rather than spreading the wire row.

    Those five are the ones where the type and the function are supposed to be the same list.
    Optional fields count: a type that declares `createdAt?` and a function that never writes it
    are not equal, and the compiler will not say so.
    """
    problems: list[str] = []
    for name, type_name, keys, spread in _normalisers():
        if spread:
            continue
        fields = _fields(type_name)
        for only_function in sorted(set(keys) - set(fields)):
            problems.append(f"{name}: 写出了 {only_function}，{type_name} 没有声明")
        for only_type in sorted(set(fields) - set(keys)):
            problems.append(f"{type_name}: 声明了 {only_type}，{name} 从不产出它")

    assert not problems, (
        "归一化函数与它声明的类型不是同一份清单——声明成可选字段的那种漂移编译器看不见：\n  " + "\n  ".join(problems)
    )


def test_a_spreading_normaliser_never_invents_a_field() -> None:
    """The other six spread `...item`, so their key set is open -- but nothing they *write* may
    be absent from the type. An invented key here is a field the screen can read and the
    declaration denies."""
    problems: list[str] = []
    for name, type_name, keys, spread in _normalisers():
        if not spread:
            continue
        fields = _fields(type_name)
        for key in sorted(set(keys) - set(fields)):
            problems.append(f"{name}: 写出了 {key}，{type_name} 没有声明")

    assert not problems, "以下归一化函数写出了类型里没有的字段：\n  " + "\n  ".join(problems)


def test_the_check_reads_both_sides() -> None:
    """A parser that finds nothing passes every assertion above.

    The same lesson as the quote scanner and the sync script: a text-matching check that has
    quietly stopped matching looks exactly like a codebase with no problems. So the parsed
    shapes are asserted to be plausible -- eleven normalisers, at least one of each kind, and at
    least one type with a field -- before the comparisons are trusted.
    """
    normalisers = _normalisers()
    assert len(normalisers) >= 11, f"只解析到 {len(normalisers)} 个归一化函数——解析器失效了"
    assert any(spread for _n, _t, _k, spread in normalisers), "没有找到任何带 ...item 的函数"
    assert any(not spread for _n, _t, _k, spread in normalisers), "没有找到任何闭合的函数"
    assert all(keys for _n, _t, keys, _spread in normalisers), "有函数解析出 0 个字段"
    assert _fields("PermissionPolicy"), "从 types/index.ts 里读不出 PermissionPolicy 的字段"


def test_the_generated_key_lists_are_current() -> None:
    """`normalised.ts` is generated from `normalise.ts`; regenerate it rather than editing it.

    Same contract as `generated.ts`: the committed file is a description of the code, so a
    change to a normaliser shows up as a diff here rather than as a type that quietly disagrees
    with the function that produces the data.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "generate_normalised_keys", ROOT / "scripts" / "generate_normalised_keys.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    wanted = module.generate()
    current = NORMALISED_TS.read_text(encoding="utf-8")
    assert current == wanted, (
        "frontend/src/types/normalised.ts 与 normalise.ts 不一致。"
        "运行 `python scripts/generate_normalised_keys.py` 重新生成——这一步不是可选的，"
        "因为 index.ts 里的编译期断言读的正是这个文件。"
    )


def test_the_compile_time_assertions_are_still_wired() -> None:
    """The generated file is useless if nothing compares it to the types.

    `NormalisedTypeChecks` in `types/index.ts` is a tuple of `Expect<...>` assertions: the
    compiler evaluates them, and a mismatch fails `npm run build`. This checks that the tuple
    and the import are still there, because deleting them is a one-line change that leaves every
    other test in this file passing -- the Python comparison above would still run, and the
    build would stop checking anything.
    """
    index = INDEX_TYPES.read_text(encoding="utf-8")
    assert "from './normalised'" in index, "types/index.ts 不再引用生成文件——它成了没人读的孤儿"
    assert "NormalisedTypeChecks" in index, "编译期断言被删掉了；tsc 不再比较类型与归一化函数的键"
    assert "NORMALISED_FIELDS" in index and "NORMALISED_OVERRIDES" in index, (
        "断言没有引用生成的两张表——它们还在，但没有任何东西读"
    )
