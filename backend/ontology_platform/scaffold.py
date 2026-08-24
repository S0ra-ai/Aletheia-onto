"""Project scaffolding: a runnable starting point for someone else's deployment.

ROADMAP stage F named a separate `aletheia-scaffold` repository. A repository is the wrong
shape for the problem it was meant to solve, and the reason is the one that kept the
three-repo split deferred: a scaffold repository is a **fork**, so it stops receiving
improvements the moment it is used, and the first thing a user must do is delete the parts
that do not apply to them.

What a user actually lacks is narrower. The library is installable, the CLI runs the whole
loop, and `docs/extending.md` explains every extension point. What is missing is the answer
to "where do I put my own code" -- and that answer is small enough to generate.

So `aletheia new` writes a project, not a fork:

- a config module holding the platform database path and the sources to connect
- one registration module per extension point the project actually uses, each with a
  working skeleton and a comment saying when that seam is the right one
- a conformance script wired to the shipped contracts, so a wrong implementation fails
  locally rather than in production
- a `.env.example` with no usable defaults, and a `.gitignore` that excludes the real one

## Generated code depends on the installed version, never on a copy of it

No vendored platform code. That is what separates this from a fork: upgrading is
`pip install -U aletheia-onto`, and the generated files keep working because they only call
public entry points. A scaffold that copied platform internals would pin the user to the
version they generated from -- the same trap ADR-0001 was avoiding, reached from the other
direction.

## Nothing is generated unless it is asked for

Each extension point is opt-in. Generating all six by default produces a project where five
files are dead code, and dead example code is worse than none: a reader cannot tell which
parts the project relies on, so nobody dares delete them.

## Regenerating over existing work is refused

Generated code becomes the user's the moment they edit it. A scaffold that overwrites is one
that eventually destroys work, so this refuses and says to generate into a new directory and
diff -- which is recoverable.

Stability: experimental (ADR-0007).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

__all__ = [
    "EXTENSION_POINTS",
    "ScaffoldError",
    "create_project",
    "describe_extension_points",
]

# Extension points a generated project can wire up. Each carries a note on *when* it is the
# right seam, because "which extension point do I need" is what the docs answer least well.
EXTENSION_POINTS: dict[str, tuple[str, str]] = {
    "datasource": (
        "数据源适配器",
        "接入平台尚无内置声明的库。先看 sql_dialects：多数 SQL 库只需声明 4 行，不必写适配器。",
    ),
    "rule-function": (
        "规则函数",
        "让规则表达式能调用领域谓词。注册只授予调用权，不放宽沙箱 AST 白名单。",
    ),
    "writeback": (
        "写回执行器",
        "把判定结果写回传统系统。按 scheme 分发；无 WHERE 的语句会被拒绝。",
    ),
    "retrieval": (
        "检索后端",
        "替换默认 BM25。检索必须确定：同一问题两次给出不同引用，结论就不可复现。",
    ),
    "embedding": (
        "嵌入模型",
        "替换默认哈希 n-gram。必须确定且同维，否则相似度无意义。",
    ),
    "policy": (
        "路由权限策略",
        "为自己新增的端点声明所需能力。未登记的路由默认仅管理员可访问。",
    ),
}

PROJECT_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,39}$")


class ScaffoldError(ValueError):
    """Raised when a project cannot be generated, or would overwrite existing work."""


@dataclass(frozen=True)
class GeneratedFile:
    path: str
    content: str


def describe_extension_points() -> list[dict[str, str]]:
    return [{"point": point, "name": name, "when": when} for point, (name, when) in sorted(EXTENSION_POINTS.items())]


def create_project(
    target: Path | str,
    *,
    project_name: str,
    extensions: Sequence[str] = (),
    domain: str = "",
) -> dict[str, Any]:
    """Write a project skeleton, refusing to overwrite anything."""
    if not PROJECT_NAME_PATTERN.match(project_name):
        raise ScaffoldError(
            f"项目名 {project_name!r} 不合法：需为小写字母开头、2-40 位的小写字母／数字／下划线（它会成为 Python 包名）"
        )

    unknown = [item for item in extensions if item not in EXTENSION_POINTS]
    if unknown:
        raise ScaffoldError(f"未知扩展点 {chr(12289).join(unknown)}，可选: {chr(12289).join(sorted(EXTENSION_POINTS))}")

    root = Path(target)
    selected = tuple(dict.fromkeys(extensions))
    files = _plan(project_name, selected, domain)

    existing = [item.path for item in files if (root / item.path).exists()]
    if existing:
        raise ScaffoldError(
            f"以下文件已存在，未做任何修改: {chr(12289).join(existing)}。生成到新目录再对比合并——脚手架不覆盖既有代码。"
        )

    for item in files:
        destination = root / item.path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(item.content, encoding="utf-8")

    return {
        "project": project_name,
        "root": str(root.resolve()),
        "files": [item.path for item in files],
        "extensions": list(selected),
        "next": [
            f"cd {root}",
            "cp .env.example .env   # 填入真实值，.env 已在 .gitignore 中",
            "pip install -e .",
            f"python -m {project_name} init",
            f"python -m {project_name} serve",
        ],
    }


def _plan(package: str, extensions: tuple[str, ...], domain: str) -> list[GeneratedFile]:
    files = [
        GeneratedFile(f"{package}/__init__.py", _init_module(package, extensions)),
        GeneratedFile(f"{package}/__main__.py", _main_module(package)),
        GeneratedFile(f"{package}/config.py", _config_module(package, domain)),
        GeneratedFile("pyproject.toml", _pyproject(package)),
        GeneratedFile(".env.example", _env_example(package)),
        GeneratedFile(".gitignore", _gitignore()),
        GeneratedFile("README.md", _readme(package, extensions, domain)),
        GeneratedFile("verify.py", _verify_script(package, extensions)),
    ]
    if extensions:
        files.append(GeneratedFile(f"{package}/extensions/__init__.py", _extensions_init(extensions)))
        for point in extensions:
            files.append(GeneratedFile(f"{package}/extensions/{_module_name(point)}.py", _extension_module(point)))
    return files


def _module_name(point: str) -> str:
    return point.replace("-", "_")


# -- Rendering --
#
# Templates are real files under `scaffold_templates/`, not string constants in this module.
# Three reasons, and the third is the one that matters: they stay readable, `ruff` can lint
# the Python ones as files, and a template embedded as a Python string containing triple
# quotes and braces is a place where a subtle escaping mistake produces generated code that
# is *almost* valid -- which fails at the user's first run rather than in review.
#
# Substitution is `{{name}}` rather than `str.format`, because the generated Python and TOML
# legitimately contain braces (dict literals, f-strings) and every one of them would have to
# be doubled.

TEMPLATE_ROOT = Path(__file__).resolve().parent / "scaffold_templates"


def _render(template: str, **values: str) -> str:
    """Fill a template, refusing to leave a placeholder behind.

    An unresolved `{{name}}` reaching a generated file is worse than a crash: the project
    looks generated, and the placeholder surfaces as a NameError or a broken path at the
    user's first command.
    """
    source = (TEMPLATE_ROOT / template).read_text(encoding="utf-8")
    for key, value in values.items():
        source = source.replace("{{" + key + "}}", value)
    leftover = re.findall(r"\{\{(\w+)\}\}", source)
    if leftover:
        raise ScaffoldError(f"模板 {template} 存在未替换占位符: {'、'.join(sorted(set(leftover)))}")
    return source


def _platform_version() -> str:
    from . import __version__

    return __version__


def _init_module(package: str, extensions: tuple[str, ...]) -> str:
    if extensions:
        registration = "    from .extensions import register_all\n\n    register_all()"
    else:
        registration = "    # 尚未注册任何扩展点。可选项见 `aletheia new --list-extensions`。\n    return"
    return _render("__init___py.tpl", package=package, registration=registration)


def _main_module(package: str) -> str:
    return _render("__main___py.tpl", package=package)


def _config_module(package: str, domain: str) -> str:
    return _render(
        "config_py.tpl",
        package=package,
        UPPER=package.upper(),
        domain=domain or "合同管理",
    )


def _extensions_init(extensions: tuple[str, ...]) -> str:
    imports = "\n".join(f"from . import {_module_name(point)}" for point in extensions)
    calls = "\n".join(f"    {_module_name(point)}.register()" for point in extensions)
    return _render("extensions_init_py.tpl", imports=imports, calls=calls)


def _extension_module(point: str) -> str:
    return (TEMPLATE_ROOT / "extensions" / f"{_module_name(point)}.py.tpl").read_text(encoding="utf-8")


def _pyproject(package: str) -> str:
    return _render(
        "pyproject_toml.tpl",
        package=package,
        dist=package.replace("_", "-"),
        version=_platform_version(),
    )


def _env_example(package: str) -> str:
    return _render("env_example.tpl", package=package, UPPER=package.upper())


def _gitignore() -> str:
    return _render("gitignore.tpl")


def _verify_script(package: str, extensions: tuple[str, ...]) -> str:
    # Only these four have executable contracts. Rule functions and route policies are
    # covered by the platform's own tests, and saying so is better than implying a contract
    # exists -- a developer looking for one and not finding it assumes they missed something.
    contracts = {
        "datasource": "check_data_source_adapter",
        "retrieval": "check_retrieval_backend",
        "embedding": "check_embedding_model",
        "writeback": "check_writeback_executor",
    }
    covered = [point for point in extensions if point in contracts]
    if covered:
        lines = "\n".join(f"#   {point} -> conformance.{contracts[point]}" for point in covered)
    else:
        lines = (
            "#   （本项目注册的扩展暂无对应契约；规则函数与路由策略由平台自身测试覆盖。）\n"
            "#   新增数据源适配器、检索后端、嵌入模型或写回执行器后，在此补上对应检查。"
        )
    return _render("verify_py.tpl", package=package, covered=lines)


def _readme(package: str, extensions: tuple[str, ...], domain: str) -> str:
    if extensions:
        listed = "\n".join(
            f"- `{package}/extensions/{_module_name(point)}.py` —— {EXTENSION_POINTS[point][0]}"
            f"：{EXTENSION_POINTS[point][1]}"
            for point in extensions
        )
    else:
        listed = "（未生成任何扩展点。用 `aletheia new --list-extensions` 查看可选项。）"
    return _render(
        "readme_md.tpl",
        package=package,
        domain=domain or "合同管理",
        extension_list=listed,
    )
