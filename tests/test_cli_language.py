"""The CLI speaks two languages, and says which parts it does not.

The console has been bilingual for a while; `aletheia` has not, and it is the first thing an
adopter meets -- `aletheia --help`, `aletheia demo`, `aletheia new`. The division is the same one
the console draws: **what the tool says about itself** is translated; the JSON it prints is the
API's output, whose shape and vocabulary are the contract a pipeline parses, and that stays
Chinese exactly as the English console's fallback does.

What is checked here is that the step is complete in both directions -- every key the CLI asks
for exists, every key defined is asked for -- and that the *help text* is translated, which is
the one thing a flag parsed by the parser cannot reach on its own.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from ontology_platform import cli_messages

CLI = ROOT / "backend" / "ontology_platform" / "cli.py"


def _run(args: list[str], **env: str) -> subprocess.CompletedProcess[str]:
    import os

    environment = {**os.environ, "PYTHONPATH": str(ROOT / "backend"), **env}
    return subprocess.run(
        [sys.executable, "-m", "ontology_platform.cli", *args],
        capture_output=True,
        text=True,
        env=environment,
        timeout=60,
    )


def test_every_key_the_cli_asks_for_exists() -> None:
    """A missing key renders `⟦key⟧` in the terminal -- visible on purpose, and still a defect."""
    source = CLI.read_text(encoding="utf-8")
    used = set(re.findall(r"_t\(\s*['\"]([\w_]+)['\"]", source))
    assert used, "没有解析到任何 _t() 调用——扫描器多半失效了，而不是 CLI 改了写法"
    missing = sorted(used - set(cli_messages.MESSAGES))
    assert not missing, f"CLI 调用了字典里没有的键：{missing}"


def test_every_defined_key_is_asked_for() -> None:
    """A translation nothing reads is a sentence that looks like coverage.

    It also stops the table from accumulating entries for commands that were removed -- the two
    failure directions are the same defect as an orphaned dictionary key in the console, which is
    why `tests/test_ui_messages.py` checks it there too.
    """
    source = CLI.read_text(encoding="utf-8")
    used = set(re.findall(r"_t\(\s*['\"]([\w_]+)['\"]", source))
    # Two keys are reached through the doctor hint composer rather than a literal `_t("…")`.
    reached_by_code = {"driver_missing_installable", "driver_missing_vendor"}
    orphaned = sorted(set(cli_messages.MESSAGES) - used - reached_by_code)
    assert not orphaned, f"字典里这些键没有任何地方读：{orphaned}"


def test_both_languages_are_filled_in() -> None:
    empty = [key for key, (zh, en) in cli_messages.MESSAGES.items() if not zh.strip() or not en.strip()]
    assert not empty, f"这些键缺一种语言：{empty}"


def test_the_help_text_follows_the_flag() -> None:
    """The hard half: `--help` is produced by the parser, and `--lang` is parsed by it.

    Resolving the language after parsing would leave `--help` in Chinese for the reader who asked
    for English -- the one invocation where the language matters most, because it is what they
    read before running anything.
    """
    zh = _run(["--help"])
    en = _run(["--lang", "en", "--help"])
    assert zh.returncode == 0 and en.returncode == 0
    assert "为传统业务系统安装" in zh.stdout
    assert "install a verifiable semantic kernel" in en.stdout
    assert "为传统业务系统安装" not in en.stdout


def test_the_language_can_come_from_the_environment_too() -> None:
    """A deployment script should not have to repeat the flag on every invocation."""
    en = _run(["--help"], ONTOLOGY_LANG="en")
    assert "install a verifiable semantic kernel" in en.stdout


@pytest.mark.parametrize("value", ["fr", "", "ENGLISH", "zh-CN"])
def test_an_unusable_language_falls_back_rather_than_failing(value: str) -> None:
    """A tool that refused to start because of a locale would be a tool that ruined a deploy."""
    result = _run(["--help"], ONTOLOGY_LANG=value)
    assert result.returncode == 0
    assert "为传统业务系统安装" in result.stdout


def test_the_flag_beats_the_environment() -> None:
    result = _run(["--lang", "en", "--help"], ONTOLOGY_LANG="zh")
    assert "install a verifiable semantic kernel" in result.stdout


def test_the_cli_translates_what_it_says_about_itself_and_not_what_the_api_says() -> None:
    """The boundary, asserted rather than left to a docstring.

    An uninitialised platform makes the storage engine raise `no such table: data_source`; the
    CLI adds its own sentence about what to do, and that sentence is translated. The API's own
    sentences -- the ones inside the JSON -- stay Chinese, because that is the contract, and the
    console's English mode falls back to them for the same reason.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as folder:
        db = str(Path(folder) / "platform.sqlite3")
        zh = _run(["--platform-db", db, "publish", "1"])
        en = _run(["--platform-db", db, "publish", "1"], ONTOLOGY_LANG="en")

    assert zh.returncode != 0 and en.returncode != 0
    assert "平台库尚未初始化" in zh.stderr
    assert "not initialised yet" in en.stderr, en.stderr
    # The driver's own words pass through untranslated in both: they name an internal table, and
    # restating a storage engine's sentence is `errors.py`'s job rather than the CLI's.
    assert "no such table" in zh.stderr and "no such table" in en.stderr


def test_the_scaffolded_program_name_survives_translation() -> None:
    """A scaffolded project wraps this CLI, and its name appears *inside* a translated sentence.

    A message that hard-coded `aletheia` there would send the reader of that project to the one
    command its README says not to use -- and it would do so only in the language nobody on the
    project reads.
    """
    source = CLI.read_text(encoding="utf-8")
    assert "program=program_name()" in source or "program=PROGRAM" in source
