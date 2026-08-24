"""`--platform-db` must mean the same database in every command, including `serve`.

Found by using the platform rather than by testing it: `aletheia init --platform-db X`
followed by `aletheia serve --platform-db X` served a *different* database. `uvicorn.run`
imports the app in a fresh context that resolves the platform database from the environment,
and nothing carried `X` across.

The failure mode is what makes this worth a dedicated test. Nothing errored. The API returned
an empty ontology list, which reads as "my data did not save" -- so the investigation starts
by re-running `model`, re-checking the scan, and doubting the writes. The one thing it does
not look like is a path mismatch.

Two properties are pinned here:

- **the flag reaches the served process**, so every command agrees on the database
- **the path is announced on startup**, because a silent correct default and a silent wrong
  default are indistinguishable from outside, and this is the variable that decides whether
  a deployment sees its own data
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def _env(**overrides: str) -> dict[str, str]:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT / "backend")
    # Cleared so the test observes the resolution rules rather than the developer's shell.
    for name in ("ONTOLOGY_PLATFORM_DB_FILE", "ONTOLOGY_DATA_DIR"):
        environment.pop(name, None)
    environment.update(overrides)
    return environment


def _resolved_platform_db(environment: dict[str, str]) -> str:
    """The path a freshly imported process would use.

    A subprocess because the value is resolved at import time: reading it in-process would
    report whatever the first import happened to see.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from ontology_platform.database import DEFAULT_PLATFORM_DB; print(DEFAULT_PLATFORM_DB)",
        ],
        capture_output=True,
        text=True,
        env=environment,
        check=True,
    )
    return result.stdout.strip()


# -- The file-level override --


def test_the_file_variable_names_the_database_directly(tmp_path: Path) -> None:
    """`ONTOLOGY_DATA_DIR` cannot express this.

    The directory variable requires the file to be called `platform.sqlite3`, so pointing a
    process at `/srv/aletheia/prod.sqlite3` was impossible without renaming it.
    """
    target = tmp_path / "prod.sqlite3"
    assert _resolved_platform_db(_env(ONTOLOGY_PLATFORM_DB_FILE=str(target))) == str(target)


def test_the_file_variable_wins_over_the_directory(tmp_path: Path) -> None:
    """The more specific setting wins, so a deployment can point one process at one database
    without disturbing the directory layout everything else uses."""
    directory = tmp_path / "data"
    target = tmp_path / "explicit.sqlite3"
    resolved = _resolved_platform_db(_env(ONTOLOGY_DATA_DIR=str(directory), ONTOLOGY_PLATFORM_DB_FILE=str(target)))
    assert resolved == str(target)


def test_the_directory_variable_still_works_alone(tmp_path: Path) -> None:
    """Existing deployments configure the directory, and this must not change for them."""
    directory = tmp_path / "data"
    resolved = _resolved_platform_db(_env(ONTOLOGY_DATA_DIR=str(directory)))
    assert resolved == str(directory / "platform.sqlite3")


# -- `serve` carries the flag across the process boundary --


def test_serve_passes_the_flag_to_the_served_process(tmp_path: Path, monkeypatch) -> None:
    """The defect this file exists for.

    `serve --platform-db X` runs the server in a child process, because
    `database.DEFAULT_PLATFORM_DB` is resolved at import time and `cli` has already imported
    `database` by then -- setting the variable in-process changes a constant that was fixed
    long before. Only a fresh interpreter can observe it.

    Asserted by intercepting the spawn rather than by starting a server and querying it: a
    real server would add a port, several seconds and a class of failures that have nothing
    to do with the path under test.
    """
    from ontology_platform import cli
    from ontology_platform.database import PLATFORM_DB_FILE_ENV

    target = tmp_path / "mine.sqlite3"
    observed: dict[str, object] = {}

    def _fake_call(command, env=None, **kwargs):
        observed["command"] = command
        observed["platformDb"] = (env or {}).get(PLATFORM_DB_FILE_ENV)
        return 0

    monkeypatch.setattr(cli.subprocess, "call", _fake_call)
    monkeypatch.setitem(sys.modules, "uvicorn", object())

    parser = cli.build_parser()
    args = parser.parse_args(["--platform-db", str(target), "serve", "--host", "127.0.0.1"])
    assert cli.cmd_serve(args) == 0

    assert observed["platformDb"] == str(target.expanduser().resolve()), (
        "serve 未把 --platform-db 传给被服务的进程：它会读另一个库，"
        "而症状是本体列表为空、管理员口令被拒——读起来像「数据没保存」"
    )
    command = observed["command"]
    assert "ontology_platform.api:app" in command
    assert "--host" in command and "127.0.0.1" in command


def test_serve_without_the_flag_runs_in_process_and_keeps_the_environment(tmp_path: Path, monkeypatch) -> None:
    """No flag means no child process and no environment change.

    A deployment that configured `ONTOLOGY_PLATFORM_DB_FILE` and did not pass the flag must
    keep its setting -- substituting one silent mismatch for another would be no improvement.
    Running in-process also keeps the common case free of a second interpreter.
    """
    from ontology_platform import cli
    from ontology_platform.database import PLATFORM_DB_FILE_ENV

    configured = str(tmp_path / "configured.sqlite3")
    monkeypatch.setenv(PLATFORM_DB_FILE_ENV, configured)

    spawned: list[object] = []
    monkeypatch.setattr(cli.subprocess, "call", lambda *a, **k: spawned.append(a) or 0)

    in_process: dict[str, object] = {}

    class _Recorder:
        @staticmethod
        def run(app: str, **kwargs: object) -> None:
            in_process["app"] = app

    monkeypatch.setitem(sys.modules, "uvicorn", _Recorder())

    parser = cli.build_parser()
    assert cli.cmd_serve(parser.parse_args(["serve", "--host", "127.0.0.1"])) == 0

    assert in_process["app"] == "ontology_platform.api:app", "未传 --platform-db 时应在本进程内启动"
    assert not spawned, "未传 --platform-db 时不应另起进程"
    assert os.environ[PLATFORM_DB_FILE_ENV] == configured, "不应改写已配置的环境变量"


def test_serve_announces_the_database_it_will_use(tmp_path: Path, monkeypatch, capsys) -> None:
    """A silent correct default and a silent wrong default look identical from outside.

    This is the value that decides whether a deployment sees its own data, so it is printed
    rather than left to be inferred from an empty result.
    """
    from ontology_platform import cli

    target = tmp_path / "announced.sqlite3"
    monkeypatch.setattr(cli.subprocess, "call", lambda *a, **k: 0)
    monkeypatch.setitem(sys.modules, "uvicorn", object())

    parser = cli.build_parser()
    cli.cmd_serve(parser.parse_args(["--platform-db", str(target), "serve", "--host", "127.0.0.1"]))

    assert str(target.resolve()) in capsys.readouterr().err, "serve 未告知实际使用的平台库"


# -- The documented variable list stays honest --


def test_the_new_variable_is_documented() -> None:
    """A resolution rule nobody can find is a rule that gets rediscovered by debugging."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "ONTOLOGY_PLATFORM_DB_FILE" in readme, "README 未记录该环境变量"
