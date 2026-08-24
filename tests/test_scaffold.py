"""Project scaffolding: generated code must actually run.

ROADMAP stage F named a separate `aletheia-scaffold` repository. A repository is a fork: it
stops receiving improvements the moment it is used, and the first thing a user does is
delete the parts that do not apply. `aletheia new` generates a project that depends on the
*installed* platform instead, so upgrading is `pip install -U aletheia-onto`.

The property these tests exist for, above all others: **generated code is executed here,
not just compared to an expected string.**

That is not a stylistic preference. The first version of `verify.py` imported
`conformance.list_suites`, which does not exist -- and a snapshot test would have passed
happily, because the snapshot would have contained the same wrong name. The failure surfaced
only when the generated project was actually run. Every template that produces Python is
therefore imported and, where it has an entry point, called.

A scaffold whose output has never been run is a scaffold that fails on someone else's first
command, which is the worst possible moment: they cannot tell whether they misconfigured
something or the tool is broken.
"""

from __future__ import annotations

import compileall
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from ontology_platform.scaffold import (
    EXTENSION_POINTS,
    ScaffoldError,
    create_project,
    describe_extension_points,
)

ALL_POINTS = tuple(sorted(EXTENSION_POINTS))


# -- Validation --


def test_an_invalid_project_name_is_refused(tmp_path: Path) -> None:
    """The name becomes a Python package name, so an invalid one produces a project that
    cannot be imported -- discovered at the user's first command rather than here."""
    for name in ("Mycorp", "9lives", "my-corp", "x", "with space", ""):
        with pytest.raises(ScaffoldError, match="不合法"):
            create_project(tmp_path / "out", project_name=name)


def test_an_unknown_extension_point_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ScaffoldError, match="未知扩展点"):
        create_project(tmp_path / "out", project_name="mycorp", extensions=["telepathy"])


def test_generating_over_existing_files_is_refused(tmp_path: Path) -> None:
    """Generated code becomes the user's the moment they edit it.

    A scaffold that overwrites is one that eventually destroys work, so this refuses and
    says to generate into a new directory and diff -- which is recoverable.
    """
    target = tmp_path / "out"
    create_project(target, project_name="mycorp")
    marker = target / "mycorp" / "config.py"
    marker.write_text("# 用户改过的内容\n", encoding="utf-8")

    with pytest.raises(ScaffoldError, match="已存在"):
        create_project(target, project_name="mycorp")
    assert marker.read_text(encoding="utf-8") == "# 用户改过的内容\n", "拒绝时不得修改任何文件"


def test_every_extension_point_says_when_it_is_the_right_seam() -> None:
    """ "Which extension point do I need" is what the docs answer least well, so the
    catalogue answers it rather than only naming them."""
    described = describe_extension_points()
    assert {item["point"] for item in described} == set(ALL_POINTS)
    for item in described:
        assert len(item["when"]) > 20, item


# -- Generated Python is valid, and imports resolve --


def test_generated_python_compiles(tmp_path: Path) -> None:
    """A template escaping mistake produces code that is *almost* valid."""
    target = tmp_path / "out"
    create_project(target, project_name="mycorp", extensions=ALL_POINTS)
    assert compileall.compile_dir(str(target), quiet=2, force=True), "生成的 Python 无法编译"


def test_no_placeholder_survives_into_generated_files(tmp_path: Path) -> None:
    """An unresolved placeholder is worse than a crash: the project looks generated, and
    the placeholder surfaces as a NameError or a broken path at the first command."""
    target = tmp_path / "out"
    create_project(target, project_name="mycorp", extensions=ALL_POINTS, domain="设备管理")
    for path in sorted(target.rglob("*")):
        if path.is_file():
            assert "{{" not in path.read_text(encoding="utf-8"), f"{path} 残留未替换占位符"


@pytest.mark.parametrize("point", ALL_POINTS)
def test_every_generated_extension_module_imports_and_registers(tmp_path: Path, point) -> None:
    """The check a snapshot test cannot make.

    Each generated module is imported in a subprocess and its `register()` is called against
    the real platform registries. An extension referring to a function the platform does not
    export -- which is exactly the defect this suite found in `verify.py` -- fails here
    rather than in someone else's deployment.

    A subprocess because registration mutates process-global registries: doing it in-process
    would leak an `example` adapter into every later test.
    """
    target = tmp_path / "out"
    create_project(target, project_name="mycorp", extensions=[point])

    script = "import mycorp\nmycorp.setup()\nprint('registered')\n"
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=target,
        capture_output=True,
        text=True,
        env=_env_with_backend(),
    )
    assert result.returncode == 0, f"{point} 注册失败:\n{result.stderr}"
    assert "registered" in result.stdout


def test_the_generated_verify_script_runs(tmp_path: Path) -> None:
    """The script that shipped broken.

    It imported `conformance.list_suites`, which does not exist. A snapshot test would have
    passed -- the snapshot would have contained the same wrong name -- so the only check
    that catches it is running the thing.
    """
    target = tmp_path / "out"
    create_project(target, project_name="mycorp", extensions=["embedding"])

    result = subprocess.run(
        [sys.executable, "verify.py"],
        cwd=target,
        capture_output=True,
        text=True,
        env=_env_with_backend(),
    )
    assert result.returncode == 0, f"verify.py 执行失败:\n{result.stderr}"
    assert "契约" in result.stdout


def test_the_generated_entry_point_reaches_the_platform_cli(tmp_path: Path) -> None:
    """`python -m project --help` must list the platform's commands.

    The entry point wraps the CLI rather than copying it, so a user gets new commands by
    upgrading. If the wrapper broke, the project would still install and then be unable to
    do anything.
    """
    target = tmp_path / "out"
    create_project(target, project_name="mycorp")

    result = subprocess.run(
        [sys.executable, "-m", "mycorp", "--help"],
        cwd=target,
        capture_output=True,
        text=True,
        env=_env_with_backend(),
    )
    assert result.returncode == 0, result.stderr
    for command in ("init", "connect", "model", "assess", "preflight", "audit", "export"):
        assert command in result.stdout, f"生成项目的入口未暴露平台命令 {command}"


def test_the_generated_project_initialises_a_database(tmp_path: Path) -> None:
    """The end-to-end claim: a generated project can actually create its platform database.

    Everything else here checks that code loads. This checks that it *works*, which is the
    only evidence that the scaffold produces a usable starting point rather than a plausible
    looking one.
    """
    target = tmp_path / "out"
    create_project(target, project_name="mycorp")

    environment = _env_with_backend()
    environment["MYCORP_PLATFORM_DB"] = str(tmp_path / "platform.sqlite3")
    environment["ONTOLOGY_ADMIN_PASSWORD"] = "scaffold-test-passphrase"

    result = subprocess.run(
        [sys.executable, "-m", "mycorp", "init"],
        cwd=target,
        capture_output=True,
        text=True,
        env=environment,
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "platform.sqlite3").exists(), "生成项目的 init 未创建平台库"
    # And it honoured the project's own configured location rather than the platform default.
    assert str(tmp_path / "platform.sqlite3") in result.stdout


# -- What the generated project must not contain --


def test_nothing_is_generated_for_an_unrequested_extension(tmp_path: Path) -> None:
    """Dead example code is worse than none: a reader cannot tell which parts the project
    relies on, so nobody dares delete them."""
    target = tmp_path / "out"
    create_project(target, project_name="mycorp", extensions=["policy"])

    generated = {path.name for path in target.rglob("*.py")}
    assert "policy.py" in generated
    for point in ALL_POINTS:
        if point != "policy":
            assert f"{point.replace('-', '_')}.py" not in generated


def test_no_platform_source_is_vendored(tmp_path: Path) -> None:
    """What separates this from a fork.

    A scaffold that copied platform internals would pin the user to the version they
    generated from, and upgrading would mean re-forking.
    """
    target = tmp_path / "out"
    create_project(target, project_name="mycorp", extensions=ALL_POINTS)

    for path in target.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        # Importing the platform is the point; copying its private internals is not.
        assert "ontology_platform._" not in source, f"{path} 引用了平台私有名"


def test_the_env_example_carries_no_usable_default(tmp_path: Path) -> None:
    """A working example password is a password that gets used in production."""
    target = tmp_path / "out"
    create_project(target, project_name="mycorp")

    example = (target / ".env.example").read_text(encoding="utf-8")
    for line in example.splitlines():
        if line.startswith("ONTOLOGY_ADMIN_PASSWORD") or line.startswith("ONTOLOGY_SSO_SECRET"):
            assert line.split("=", 1)[1] == "", f"示例文件带了可用默认值: {line}"
    # And the real file must not be committable.
    assert ".env" in (target / ".gitignore").read_text(encoding="utf-8")


def test_the_generated_pyproject_pins_the_installed_platform_version(tmp_path: Path) -> None:
    """A range on a rule-engine dependency means a transitive upgrade can change a verdict.

    Pinned to the version that generated it, so the project starts from a combination that
    was actually observed to work.
    """
    from ontology_platform import __version__

    target = tmp_path / "out"
    create_project(target, project_name="mycorp")
    assert f"aletheia-onto[web]=={__version__}" in (target / "pyproject.toml").read_text(encoding="utf-8")


def _env_with_backend() -> dict[str, str]:
    """Environment where the generated project can import both itself and the platform.

    `PYTHONPATH` rather than an install, so the test runs against the working tree -- an
    installed wheel would test whatever was last built rather than what is being changed.
    """
    import os

    environment = dict(os.environ)
    existing = environment.get("PYTHONPATH", "")
    backend = str(ROOT / "backend")
    environment["PYTHONPATH"] = f"{backend}{os.pathsep}{existing}" if existing else backend
    return environment
