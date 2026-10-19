"""The workflow GitHub runs is the workflow the file describes.

Both failures below were written by hand into `ci.yml`, both passed every local check and
both only appeared once GitHub had the file:

- **A `run:` continued with a shell backslash.** A YAML *plain* scalar folds a line break
  into a space, so `cmd \\` on one line and an indented continuation on the next reach the
  shell as a single line -- where the backslash escapes that space instead of the newline.
  The script was handed `" --base-url"`: one word, with a leading space. argparse reported
  `unrecognized arguments` about an argument it had recognized. Reading the file does not
  show this, because the file reads exactly like the shell form it is imitating, and a YAML
  parse agrees with the runner -- the fold happened before either of them looked.

- **Duplicate keys.** `packaging`, `frontend` and `ui-smoke` each appeared twice after a
  hand repair. `yaml.safe_load` returns the last copy without complaint, so a local parse
  said the file was fine; GitHub refuses a file with duplicate job keys outright, which
  means no job runs at all and the run dies in zero seconds with a parse error rather than
  a red test.

Both are the same class: a local reading of the file that is not the runner's reading.
The checks here go through `yaml.compose`, which keeps the source style and every key pair
-- including the duplicates `safe_load` discards -- so they see what the runner sees.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.y*ml"))


def _workflows() -> list[Path]:
    assert WORKFLOWS, "没有找到任何 workflow 文件"
    return WORKFLOWS


def _mappings(node: yaml.Node, path: str, seen: set[int]) -> Iterator[tuple[str, yaml.MappingNode]]:
    """Every mapping in the document, with its path, each visited once.

    `seen` is by identity because `compose` resolves an alias to the same node object:
    without it an alias pointing at an ancestor would recurse forever.
    """
    if id(node) in seen:
        return
    seen.add(id(node))
    if isinstance(node, yaml.MappingNode):
        yield path, node
        for key_node, value_node in node.value:
            yield from _mappings(value_node, f"{path}.{_key(key_node)}", seen)
    elif isinstance(node, yaml.SequenceNode):
        for index, item in enumerate(node.value):
            yield from _mappings(item, f"{path}[{index}]", seen)


def _key(key_node: yaml.Node) -> str:
    return key_node.value if isinstance(key_node, yaml.ScalarNode) else "?"


def _entries(node: yaml.Node, path: str, seen: set[int]) -> Iterator[tuple[str, str, yaml.Node]]:
    """Every `key: value` pair, with the path of the mapping it sits in."""
    if id(node) in seen:
        return
    seen.add(id(node))
    if isinstance(node, yaml.MappingNode):
        for key_node, value_node in node.value:
            name = _key(key_node)
            yield path, name, value_node
            yield from _entries(value_node, f"{path}.{name}", seen)
    elif isinstance(node, yaml.SequenceNode):
        for index, item in enumerate(node.value):
            yield from _entries(item, f"{path}[{index}]", seen)


def _compose(path: Path) -> yaml.Node:
    try:
        return yaml.compose(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        # A syntax error is a workflow GitHub will not start, so it belongs in the failure.
        pytest.fail(f"{path.name} 不是合法的 YAML：{error}")


def test_no_run_command_is_folded_by_yaml() -> None:
    """A `run:` spanning more than one source line must use block-scalar syntax.

    Asserted on the node rather than on its text: once folded, `\\ ` and an intended
    escaped space are the same string, so only the source style distinguishes a mistake
    from a deliberate one. A plain scalar spanning lines is always the mistake here --
    a block scalar (`run: |`) is how a multi-line command is written on purpose.
    """
    found: list[str] = []
    for path in _workflows():
        root = _compose(path)
        for where, key, value in _entries(root, path.name, set()):
            if key != "run" or not isinstance(value, yaml.ScalarNode):
                continue
            if value.style is None and value.end_mark.line > value.start_mark.line:
                found.append(
                    f"{where}（第 {value.start_mark.line + 1} 行起）：YAML 会把换行折叠成空格，"
                    f"命令里的 `\\` 于是转到空格上——shell 收到的是 {value.value!r}，里面有一个以空格开头的参数。"
                    f"多行命令请写成 `run: |`。"
                )
    assert not found, "以下 run 命令被 YAML 折行：\n  " + "\n  ".join(found)


def test_no_key_is_declared_twice() -> None:
    """GitHub refuses a workflow file with a duplicate job key, and runs nothing.

    Checked on every mapping, not just `jobs`: the duplicate that got through was at the
    job level, but `steps` twice inside one job is the same silent-last-wins shape.
    """
    found: list[str] = []
    for path in _workflows():
        root = _compose(path)
        for where, mapping in _mappings(root, path.name, set()):
            seen: dict[str, int] = {}
            for key_node, _value in mapping.value:
                if not isinstance(key_node, yaml.ScalarNode):
                    continue
                name = key_node.value
                if name in seen:
                    found.append(
                        f"{where}.{name}：第 {seen[name] + 1} 行与第 {key_node.start_mark.line + 1} 行重复"
                        f"（GitHub 会因此拒绝整个文件，一个 job 都不会跑）"
                    )
                seen.setdefault(name, key_node.start_mark.line)
    assert not found, "以下键重复声明：\n  " + "\n  ".join(found)


def test_the_render_job_passes_its_token_with_an_equals_sign() -> None:
    """About 1 in 64 tokens begins with `-`, and a space-separated value is then read as an
    option: `argument --token: expected one argument`, for an argument that is right there.

    It cost two red runs, both reported as an argparse message that names neither the token
    nor the login. Asserted as text because the alternative is another red run every few
    weeks -- `--token=...` attaches the value whatever it looks like.
    """
    text = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "--token=" in text and "--user=" in text, "CI 又用空格分隔的方式传令牌了"
    assert '--token "$TOKEN"' not in text, "CI 里仍有会被当成选项的写法"


def _jobs() -> dict[str, dict]:
    return yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))["jobs"]


def test_no_job_runs_python_without_having_installed_it() -> None:
    """A step that ran `python` in a job with no Python setup, and had never once passed.

    The generated-types check was moved into the `frontend` job -- whose own comment said it
    "runs in the backend job's interpreter" -- and that job sets up Node and nothing else. Every
    push since has failed there with `No module named pytest`, while the rest of the job was
    green: a check that was never running, plus a red job, from one misplaced step. It surfaced
    only because the work was finally pushed; locally there was nowhere for it to fail.

    The rule is the narrow one that would have caught it: **a job that invokes `python` must set
    up Python**, and if it runs the test suite it must install the dependencies too. Set-up
    alone is not enough -- the runner ships a `python` with no `pytest` in it, which is exactly
    the state that produced the failure.
    """
    problems: list[str] = []
    for name, job in _jobs().items():
        steps = job.get("steps") or []
        if not any("python " in (step.get("run") or "") or "python -m" in (step.get("run") or "") for step in steps):
            continue
        uses = " ".join(step.get("uses") or "" for step in steps)
        runs = "\n".join(step.get("run") or "" for step in steps)
        if "actions/setup-python" not in uses:
            problems.append(f"{name}: 跑了 python，但没有 actions/setup-python")
        elif "pytest" in runs and "pip install" not in runs:
            problems.append(f"{name}: 跑了 pytest，但没有安装依赖（runner 自带的 python 里没有 pytest）")

    assert not problems, "以下 job 会在一个没有相应环境的 runner 上执行 Python：\n  " + "\n  ".join(problems)
