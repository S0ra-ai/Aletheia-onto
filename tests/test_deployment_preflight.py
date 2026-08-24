"""Pre-flight checks for a production deployment.

ROADMAP stage G. `aletheia doctor` answers "is this configured", which is a development
question. This answers "would this configuration be unsafe in production", and it answers
it before the service accepts a request.

Every check here corresponds to a way a real deployment goes wrong, and all of them are
silent -- the platform starts, serves traffic, and looks healthy. The one that matters most
is `ONTOLOGY_AUTH_DISABLED` left on: the entire API becomes reachable with no token,
including writeback to legacy systems.

`monkeypatch.delenv`/`setenv` is used throughout because the checks read the live
environment on purpose -- a config file that is correct while the environment overrides it
is exactly the failure this is meant to catch.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from ontology_platform.deployment import (
    CRITICAL,
    WARNING,
    PreflightReport,
    check_deployment,
    describe_checks,
)

_MANAGED = (
    "ONTOLOGY_AUTH_DISABLED",
    "ONTOLOGY_ALLOWED_ORIGINS",
    "ONTOLOGY_ADMIN_PASSWORD",
    "ONTOLOGY_PLATFORM_DB_TYPE",
    "ONTOLOGY_PLATFORM_DB_URI",
    "ONTOLOGY_SESSION_TTL_HOURS",
    "OPENROUTER_API_KEY",
    "ONTOLOGY_MODEL_API_KEY",
)


@pytest.fixture
def clean_env(monkeypatch):
    """A known-empty environment, so a developer's own settings cannot mask a finding."""
    for name in _MANAGED:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


@pytest.fixture
def secure_db(tmp_path: Path) -> Path:
    """A platform database file with tight permissions, so that check passes by default."""
    path = tmp_path / "platform.sqlite3"
    path.write_bytes(b"")
    path.chmod(0o600)
    return path


def _production(clean_env, secure_db: Path, **overrides) -> PreflightReport:
    """A configuration that should pass, with individual values overridden per test."""
    settings = {
        "ONTOLOGY_ADMIN_PASSWORD": "Xk8vQ2mNp7rT4wZa",
        "ONTOLOGY_ALLOWED_ORIGINS": "https://ontology.example.com",
        "ONTOLOGY_PLATFORM_DB_TYPE": "postgresql",
        "ONTOLOGY_PLATFORM_DB_URI": "postgresql://svc@db.internal/ontology",
        "ONTOLOGY_SESSION_TTL_HOURS": "12",
    }
    settings.update({key: value for key, value in overrides.items() if value is not None})
    for name, value in settings.items():
        clean_env.setenv(name, value)
    for name, value in overrides.items():
        if value is None:
            clean_env.delenv(name, raising=False)
    return check_deployment(platform_db=secure_db, worker_count=1)


def _failed(report: PreflightReport) -> set[str]:
    return {check.name for check in report.checks if not check.passed}


# -- The baseline --


def test_a_correctly_configured_deployment_passes(clean_env, secure_db: Path) -> None:
    """A check that nothing can satisfy gets disabled rather than fixed."""
    report = _production(clean_env, secure_db)
    assert report.ready, report.summary()
    assert not report.blockers


def test_the_report_states_how_many_checks_ran(clean_env, secure_db: Path) -> None:
    report = _production(clean_env, secure_db)
    assert report.as_dict()["checked"] == len(report.checks) > 5


# -- Authentication: the one that matters most --


def test_disabled_authentication_blocks_the_deployment(clean_env, secure_db: Path) -> None:
    """The entire API becomes reachable with no token, including writeback."""
    report = _production(clean_env, secure_db, ONTOLOGY_AUTH_DISABLED="1")
    assert not report.ready
    assert "认证已开启" in {check.name for check in report.blockers}


@pytest.mark.parametrize("value", ["1", "true", "yes", "on", "TRUE", "Yes"])
def test_every_truthy_spelling_of_the_auth_switch_is_caught(clean_env, secure_db: Path, value: str) -> None:
    """Recognising only `1` would let `ONTOLOGY_AUTH_DISABLED=true` disable auth while
    preflight reports the deployment as safe -- worse than having no check."""
    report = _production(clean_env, secure_db, ONTOLOGY_AUTH_DISABLED=value)
    assert "认证已开启" in {check.name for check in report.blockers}


def test_a_falsy_auth_switch_does_not_block(clean_env, secure_db: Path) -> None:
    report = _production(clean_env, secure_db, ONTOLOGY_AUTH_DISABLED="0")
    assert report.ready, report.summary()


def test_an_absurd_session_ttl_is_a_warning_not_a_blocker(clean_env, secure_db: Path) -> None:
    """It weakens the deployment without making it exploitable today, and blocking on it
    would train people to pass --skip-preflight."""
    report = _production(clean_env, secure_db, ONTOLOGY_SESSION_TTL_HOURS="100000")
    assert report.ready
    assert "会话有效期合理" in {check.name for check in report.warnings}


# -- CORS --


def test_a_wildcard_origin_blocks_the_deployment(clean_env, secure_db: Path) -> None:
    """Any site could drive the API carrying a user's credentials."""
    report = _production(clean_env, secure_db, ONTOLOGY_ALLOWED_ORIGINS="*")
    assert not report.ready
    assert "CORS 未使用通配" in {check.name for check in report.blockers}


def test_a_wildcard_among_real_origins_is_still_caught(clean_env, secure_db: Path) -> None:
    report = _production(clean_env, secure_db, ONTOLOGY_ALLOWED_ORIGINS="https://ontology.example.com,*")
    assert "CORS 未使用通配" in {check.name for check in report.blockers}


def test_localhost_only_origins_are_warned_about(clean_env, secure_db: Path) -> None:
    """It means the real frontend is blocked, and the next step someone takes is `*`."""
    report = _production(clean_env, secure_db, ONTOLOGY_ALLOWED_ORIGINS="http://localhost:3000")
    assert report.ready
    assert "CORS 已配置为真实前端来源" in {check.name for check in report.warnings}


def test_unset_origins_are_warned_about(clean_env, secure_db: Path) -> None:
    report = _production(clean_env, secure_db, ONTOLOGY_ALLOWED_ORIGINS=None)
    assert "CORS 已配置为真实前端来源" in {check.name for check in report.warnings}


def test_an_expected_origin_missing_from_the_allowlist_is_reported(clean_env, secure_db: Path) -> None:
    """So a deployment pipeline can assert the frontend it just deployed is actually
    permitted, instead of finding out from the browser console."""
    for name, value in {
        "ONTOLOGY_ADMIN_PASSWORD": "Xk8vQ2mNp7rT4wZa",
        "ONTOLOGY_ALLOWED_ORIGINS": "https://ontology.example.com",
        "ONTOLOGY_PLATFORM_DB_TYPE": "postgresql",
        "ONTOLOGY_PLATFORM_DB_URI": "postgresql://svc@db.internal/ontology",
    }.items():
        clean_env.setenv(name, value)
    report = check_deployment(platform_db=secure_db, expected_origins=("https://admin.example.com",), worker_count=1)
    assert "预期来源均已允许" in {check.name for check in report.warnings}


# -- Bootstrap admin --


def test_an_unset_admin_password_is_warned_about(clean_env, secure_db: Path) -> None:
    """A random one is printed once, and in a container that log line is usually gone."""
    report = _production(clean_env, secure_db, ONTOLOGY_ADMIN_PASSWORD=None)
    assert "引导管理员口令已显式设置" in {check.name for check in report.warnings}


@pytest.mark.parametrize("password", ["change-me-please", "changeme", "admin", "password", "123456"])
def test_a_placeholder_password_blocks_the_deployment(clean_env, secure_db: Path, password: str) -> None:
    """An explicit weak password is worse than a strong generated one: someone chose it and
    will assume it was changed later."""
    report = _production(clean_env, secure_db, ONTOLOGY_ADMIN_PASSWORD=password)
    assert not report.ready
    assert {"引导管理员口令不是占位值", "引导管理员口令强度足够"} & {check.name for check in report.blockers}


def test_a_short_password_blocks_the_deployment(clean_env, secure_db: Path) -> None:
    report = _production(clean_env, secure_db, ONTOLOGY_ADMIN_PASSWORD="Ab3!x")
    assert "引导管理员口令强度足够" in {check.name for check in report.blockers}


# -- Platform store --


def test_sqlite_with_several_workers_blocks_the_deployment(clean_env, secure_db: Path) -> None:
    """SQLite serialises writers. The symptom under load is intermittent timeouts, not an
    obvious configuration error, so it has to be caught before traffic arrives."""
    for name, value in {
        "ONTOLOGY_ADMIN_PASSWORD": "Xk8vQ2mNp7rT4wZa",
        "ONTOLOGY_ALLOWED_ORIGINS": "https://ontology.example.com",
        "ONTOLOGY_PLATFORM_DB_TYPE": "sqlite",
    }.items():
        clean_env.setenv(name, value)
    report = check_deployment(platform_db=secure_db, worker_count=4)
    assert not report.ready
    assert "多工作进程未搭配 SQLite" in {check.name for check in report.blockers}


def test_sqlite_with_one_worker_is_allowed(clean_env, secure_db: Path) -> None:
    """A single-node evaluation deployment on SQLite is legitimate; refusing it would push
    people to skip the check entirely."""
    for name, value in {
        "ONTOLOGY_ADMIN_PASSWORD": "Xk8vQ2mNp7rT4wZa",
        "ONTOLOGY_ALLOWED_ORIGINS": "https://ontology.example.com",
        "ONTOLOGY_PLATFORM_DB_TYPE": "sqlite",
    }.items():
        clean_env.setenv(name, value)
    report = check_deployment(platform_db=secure_db, worker_count=1)
    assert report.ready, report.summary()


def test_a_non_sqlite_type_without_a_uri_blocks(clean_env, secure_db: Path) -> None:
    report = _production(clean_env, secure_db, ONTOLOGY_PLATFORM_DB_URI=None)
    assert not report.ready
    assert "非 SQLite 平台库已提供连接串" in {check.name for check in report.blockers}


def test_an_unset_db_type_is_warned_about(clean_env, secure_db: Path) -> None:
    """Relying on the default means the deployment silently runs on SQLite."""
    for name, value in {
        "ONTOLOGY_ADMIN_PASSWORD": "Xk8vQ2mNp7rT4wZa",
        "ONTOLOGY_ALLOWED_ORIGINS": "https://ontology.example.com",
    }.items():
        clean_env.setenv(name, value)
    report = check_deployment(platform_db=secure_db, worker_count=1)
    assert "平台库类型明确声明" in {check.name for check in report.warnings}


# -- Credential exposure --


def test_an_inline_password_in_the_uri_is_warned_about(clean_env, secure_db: Path) -> None:
    """It appears in the process list, in container inspect output, and in crash logs."""
    report = _production(clean_env, secure_db, ONTOLOGY_PLATFORM_DB_URI="postgresql://svc:s3cret@db.internal/ontology")
    assert "平台库连接串未内联口令" in {check.name for check in report.warnings}


def test_a_world_readable_platform_database_blocks(clean_env, tmp_path: Path) -> None:
    """The platform database holds every data source's connection string, so the file mode
    is a credential-store question, not an ordinary data-file one."""
    loose = tmp_path / "platform.sqlite3"
    loose.write_bytes(b"")
    loose.chmod(0o644)
    for name, value in {
        "ONTOLOGY_ADMIN_PASSWORD": "Xk8vQ2mNp7rT4wZa",
        "ONTOLOGY_ALLOWED_ORIGINS": "https://ontology.example.com",
        "ONTOLOGY_PLATFORM_DB_TYPE": "sqlite",
    }.items():
        clean_env.setenv(name, value)
    report = check_deployment(platform_db=loose, worker_count=1)
    assert not report.ready
    assert "平台库文件权限已收紧" in {check.name for check in report.blockers}


def test_a_model_key_in_the_environment_is_reported_as_info(clean_env, secure_db: Path) -> None:
    """Not a blocker -- the platform works without a model at all -- but a key in the
    environment is a key in every crash dump."""
    report = _production(clean_env, secure_db, OPENROUTER_API_KEY="sk-test-value")
    assert report.ready
    names = {check.name for check in report.checks if not check.passed}
    assert any("OPENROUTER_API_KEY" in name for name in names)


# -- Report shape --


def test_warnings_do_not_block_but_blockers_do() -> None:
    """Mixing "exploitable" with "will be slow" makes the report useless for deciding
    whether to ship."""
    report = PreflightReport()
    report.add("警告项", False, severity=WARNING)
    assert report.ready is True
    report.add("阻断项", False, severity=CRITICAL)
    assert report.ready is False


def test_every_failing_check_says_what_to_set() -> None:
    """A check that reports a problem without a remedy is one people learn to ignore."""
    for check in describe_checks():
        assert check["remedy"], f"{check['name']} 缺少处理建议"


def test_describing_the_checks_does_not_mutate_the_environment() -> None:
    """A describe call that changed the process's configuration would be a trap."""
    before = {name: os.environ.get(name) for name in _MANAGED}
    describe_checks()
    assert {name: os.environ.get(name) for name in _MANAGED} == before


def test_the_summary_names_the_remedy_for_each_blocker(clean_env, secure_db: Path) -> None:
    report = _production(clean_env, secure_db, ONTOLOGY_AUTH_DISABLED="1")
    summary = report.summary()
    assert "ONTOLOGY_AUTH_DISABLED" in summary
    assert "处理:" in summary


# -- The deployment artefacts --


def test_the_container_image_runs_as_a_non_root_user() -> None:
    """The platform database is a credential store; running as root means one container
    escape hands over every data source's connection string."""
    dockerfile = (ROOT / "deploy" / "Dockerfile").read_text(encoding="utf-8")
    assert "useradd" in dockerfile
    assert "USER aletheia" in dockerfile


def test_the_container_image_builds_in_two_stages() -> None:
    """Not about image size: a runtime that can fetch and compile arbitrary packages is the
    shortest path from one code execution to a persistent backdoor."""
    dockerfile = (ROOT / "deploy" / "Dockerfile").read_text(encoding="utf-8")
    assert dockerfile.count("FROM ") >= 2
    assert "AS build" in dockerfile


def test_the_image_ships_no_credentials_or_seeded_database() -> None:
    """A bundled SQLite would make every deployment share one initial dataset -- and that
    dataset is where data source connection strings live."""
    dockerfile = (ROOT / "deploy" / "Dockerfile").read_text(encoding="utf-8")
    assert "ONTOLOGY_ADMIN_PASSWORD" not in dockerfile
    assert ".sqlite3" not in dockerfile.replace("ONTOLOGY_DATA_DIR", "")


def test_the_compose_file_requires_secrets_rather_than_defaulting_them() -> None:
    """`:?` makes compose fail on an unset value. A default password in a reference
    compose file is a password that reaches production."""
    compose = (ROOT / "deploy" / "docker-compose.yml").read_text(encoding="utf-8")
    for variable in ("POSTGRES_PASSWORD", "ONTOLOGY_ADMIN_PASSWORD", "ONTOLOGY_ALLOWED_ORIGINS"):
        assert f"${{{variable}:?" in compose, f"{variable} 应使用 :? 强制设置"


def test_the_compose_file_does_not_expose_the_database_port() -> None:
    """The platform reaches it over the compose network; publishing 5432 makes the
    credential store directly reachable."""
    compose = (ROOT / "deploy" / "docker-compose.yml").read_text(encoding="utf-8")
    assert "5432:5432" not in compose


def test_the_env_example_contains_no_usable_defaults() -> None:
    """An example file with working credentials eventually gets deployed as-is."""
    example = (ROOT / "deploy" / ".env.example").read_text(encoding="utf-8")
    for line in example.splitlines():
        if line.startswith("POSTGRES_PASSWORD") or line.startswith("ONTOLOGY_ADMIN_PASSWORD"):
            assert line.split("=", 1)[1].strip() == "", f"范例文件不应带可用值: {line}"


def test_the_real_env_file_is_not_tracked() -> None:
    """Otherwise the first person to fill it in commits their production credentials."""
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "deploy/.env" in ignored
