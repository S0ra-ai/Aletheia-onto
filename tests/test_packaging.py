"""Packaging: the project is installable, and the install is usable.

ROADMAP stage E. A framework nobody can `pip install` is a repository, not a
framework -- so these assert the properties that make the difference:

- **The kernel has no third-party dependencies.** The ontology, rule engine and
  decision records must work without a web server, or the library cannot be embedded
  in someone else's application.
- **The default database path does not depend on the working directory.** A relative
  `data/` is right in a checkout and wrong once installed: the same command would find
  a different database depending on where it ran, and that failure is silent.
- **Type annotations ship.** Without a `py.typed` marker a consumer's type checker
  ignores our annotations entirely (PEP 561), so a wrong call site looks fine until
  runtime.
"""

from __future__ import annotations

import importlib
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

PACKAGE = ROOT / "backend" / "ontology_platform"
PYPROJECT = (ROOT / "pyproject.toml").read_text()


def _section(name: str) -> str:
    """The raw text of one pyproject section.

    Text rather than parsed TOML: `tomllib` arrived in 3.11 and this project supports
    3.9, so parsing would need a dependency the test suite does not otherwise have.
    These assertions are about presence and shape, which text matching answers.
    """
    match = re.search(rf"^\[{re.escape(name)}\]$(.*?)(?=^\[|\Z)", PYPROJECT, re.MULTILINE | re.DOTALL)
    assert match, f"pyproject 缺少 [{name}] 段"
    return match.group(1)


# -- Distribution metadata --


def test_the_project_declares_build_metadata() -> None:
    project = _section("project")
    for field in ("name", "version", "requires-python", "description"):
        assert f"{field} =" in project, f"[project] 缺少 {field}"
    assert "[build-system]" in PYPROJECT


def test_the_declared_version_matches_the_package() -> None:
    """Two version numbers that can disagree will disagree."""
    from ontology_platform import __version__

    match = re.search(r'^version = "([^"]+)"', _section("project"), re.MULTILINE)
    assert match and match.group(1) == __version__, (
        f"pyproject 版本 {match.group(1) if match else '?'} 与 __init__ 的 {__version__} 不一致"
    )


def test_the_kernel_has_no_third_party_dependencies() -> None:
    """A library that drags in a web server cannot be embedded in someone else's app."""
    project = _section("project")
    match = re.search(r"^dependencies = \[(.*?)\]", project, re.MULTILINE | re.DOTALL)
    assert match, "[project] 缺少 dependencies"
    entries = [line.strip() for line in match.group(1).split("\n") if line.strip() and not line.strip().startswith("#")]
    assert not entries, f"内核不应有第三方依赖，却声明了: {entries}"


def test_optional_extras_cover_every_optional_import() -> None:
    """An optional dependency with no extra is unreachable: a user cannot install it."""
    extras = _section("project.optional-dependencies")
    for extra in ("web", "postgresql", "mysql", "documents", "dev", "all"):
        assert f"{extra} = [" in extras, f"缺少 {extra} extra"


def test_dependencies_are_pinned_not_ranged() -> None:
    """A range on a rule-engine dependency means a transitive upgrade can change a
    verdict, and a verdict is what this platform is accountable for."""
    extras = _section("project.optional-dependencies")
    loose = re.findall(r'"([A-Za-z][^"]*(?:>=|~=|\^|>)[^"]*)"', extras)
    # Self-referential extras in `all` carry no version and are fine.
    loose = [item for item in loose if not item.startswith("aletheia-onto[")]
    assert not loose, f"以下依赖未固定版本: {loose}"


def test_the_cli_entry_point_is_declared_and_importable() -> None:
    assert "aletheia = " in _section("project.scripts")
    module = importlib.import_module("ontology_platform.cli")
    assert callable(module.main)


# -- PEP 561 --


def test_the_type_marker_exists_and_is_packaged() -> None:
    """Without it a consumer's type checker silently ignores our annotations."""
    assert (PACKAGE / "py.typed").exists(), "缺少 py.typed 标记"
    assert "py.typed" in _section("tool.setuptools.package-data")


def test_the_package_facade_declares_its_surface() -> None:
    import ontology_platform

    assert ontology_platform.__all__
    missing = [name for name in ontology_platform.__all__ if not hasattr(ontology_platform, name)]
    assert not missing, f"__all__ 中的名称无法解析: {missing}"


def test_importing_the_facade_does_not_pull_in_optional_dependencies() -> None:
    """Lazy resolution is the point: someone who only validates a rule expression
    should not pay for psycopg and python-docx."""
    code = (
        "import sys; sys.path.insert(0, %r);"
        "import ontology_platform;"
        "print(','.join(sorted(m for m in sys.modules if m in ('psycopg', 'pymysql', 'docx', 'fastapi'))))"
        % str(ROOT / "backend")
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert result.stdout.strip() == "", f"导入门面时加载了可选依赖: {result.stdout.strip()}"


# -- The default data location --


def test_the_default_path_is_absolute() -> None:
    """A relative default means the same command finds a different database depending
    on the working directory, and that failure is silent."""
    from ontology_platform.database import DEFAULT_PLATFORM_DB

    assert Path(DEFAULT_PLATFORM_DB).is_absolute(), DEFAULT_PLATFORM_DB


def test_a_checkout_keeps_its_database_beside_the_code() -> None:
    """Development databases should not accumulate in the user's home directory."""
    from ontology_platform.database import DEFAULT_PLATFORM_DB

    assert Path(DEFAULT_PLATFORM_DB).parent == ROOT / "data"


def test_the_data_directory_can_be_overridden(monkeypatch, tmp_path) -> None:
    """A deployment has its own opinion about where state lives."""
    monkeypatch.setenv("ONTOLOGY_DATA_DIR", str(tmp_path / "custom"))
    import ontology_platform.database as database

    importlib.reload(database)
    try:
        assert Path(database.DEFAULT_PLATFORM_DB).parent == tmp_path / "custom"
    finally:
        # Reload again without the override so the rest of the suite sees the real
        # default; a leaked module-level path would fail unrelated tests confusingly.
        monkeypatch.delenv("ONTOLOGY_DATA_DIR")
        importlib.reload(database)


@pytest.mark.skipif(os.environ.get("CI") is None, reason="构建 wheel 较慢，只在 CI 上执行")
def test_the_wheel_builds_and_installs_standalone(tmp_path) -> None:
    """The end-to-end claim: a fresh environment can install and run the CLI.

    Every other test here checks a declaration; this one checks the artefact. Slow, so
    it is CI-only rather than skipped silently on a developer's machine.
    """
    dist = tmp_path / "dist"
    subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(dist)],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    wheels = list(dist.glob("*.whl"))
    assert wheels, "未生成 wheel"

    venv = tmp_path / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True, capture_output=True)
    binaries = venv / ("Scripts" if os.name == "nt" else "bin")
    subprocess.run([str(binaries / "pip"), "install", "--quiet", str(wheels[0])], check=True, capture_output=True)
    # `demo` exercises the whole loop with no extras installed, which is the strongest
    # single check that the kernel really is dependency-free.
    result = subprocess.run(
        [
            str(binaries / "aletheia"),
            "--platform-db",
            str(tmp_path / "platform.sqlite3"),
            "demo",
            "--sample-db",
            str(tmp_path / "sample.sqlite3"),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert '"decision"' in result.stdout, result.stdout
