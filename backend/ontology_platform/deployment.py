"""Pre-flight checks for a production deployment.

ROADMAP stage G. `aletheia doctor` answers "is this configured", which is a development
question. This answers a different one: **would this configuration be unsafe in
production**, and it answers it before the service accepts a request rather than after.

The checks exist because each corresponds to a way a real deployment goes wrong, and every
one of them is silent — the platform starts, serves traffic, and looks healthy:

| Misconfiguration | What actually happens |
|---|---|
| `ONTOLOGY_AUTH_DISABLED=1` left on | the entire API is reachable with no token, including writeback |
| CORS left at `*` or localhost | either any origin can drive the API, or the real frontend cannot |
| bootstrap admin password unset | a random one is printed to the log once, then nobody can log in |
| SQLite as the platform store with several workers | writes serialise and time out under load |
| credentials in the connection URI with a world-readable DB file | the file is the credential store |
| platform DB and business DB the same database | a platform bug can write to the business system |

## Why this refuses rather than warns

A warning in a startup log is read once, by whoever set the service up, and never again.
`aletheia preflight` exits non-zero so a deployment pipeline stops — which is the only
point at which "authentication is disabled" is still cheap to fix.

Severities are separated for the same reason as the conformance suites (ADR-0016): mixing
"this is exploitable" with "this will be slow" makes the report unusable for deciding
whether to ship.

## What it deliberately does not do

It does not reach into the network, scan for open ports, or test whether the database is
backed up. Those are infrastructure concerns with existing tools, and a half-implemented
version here would invite someone to trust it as complete.

Stability: experimental (ADR-0007).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# `critical` means an attacker or an accident can cause harm today. `warning` means the
# deployment works but will disappoint under load or during an incident.
CRITICAL = "critical"
WARNING = "warning"
INFO = "info"


@dataclass(frozen=True)
class Check:
    """One preflight finding.

    `remedy` is required in spirit: a check that reports a problem without saying what to
    set is a check people learn to ignore.
    """

    name: str
    passed: bool
    severity: str
    detail: str = ""
    remedy: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "severity": self.severity,
            "detail": self.detail,
            "remedy": self.remedy,
        }


@dataclass
class PreflightReport:
    """The result of checking one deployment's configuration."""

    checks: list[Check] = field(default_factory=list)
    environment: str = "production"

    def add(
        self,
        name: str,
        passed: bool,
        *,
        severity: str = CRITICAL,
        detail: str = "",
        remedy: str = "",
    ) -> None:
        self.checks.append(Check(name=name, passed=passed, severity=severity, detail=detail, remedy=remedy))

    @property
    def blockers(self) -> list[Check]:
        return [check for check in self.checks if not check.passed and check.severity == CRITICAL]

    @property
    def warnings(self) -> list[Check]:
        return [check for check in self.checks if not check.passed and check.severity == WARNING]

    @property
    def ready(self) -> bool:
        """Whether the deployment is safe to serve traffic.

        Warnings do not block: a single-node evaluation deployment on SQLite is a legitimate
        thing to run, and refusing it would push people to skip the check entirely.
        """
        return not self.blockers

    def as_dict(self) -> dict[str, Any]:
        return {
            "environment": self.environment,
            "ready": self.ready,
            "checked": len(self.checks),
            "blockers": [check.as_dict() for check in self.blockers],
            "warnings": [check.as_dict() for check in self.warnings],
            "checks": [check.as_dict() for check in self.checks],
        }

    def summary(self) -> str:
        if self.ready:
            tail = f"，{len(self.warnings)} 项警告" if self.warnings else ""
            return f"✓ 部署前自检通过（{len(self.checks)} 项检查{tail}）"
        lines = [f"✗ 部署前自检未通过，{len(self.blockers)} 项阻断:"]
        for check in self.blockers:
            lines.append(f"  - {check.name}: {check.detail}")
            if check.remedy:
                lines.append(f"    处理: {check.remedy}")
        for check in self.warnings:
            lines.append(f"  ! {check.name}: {check.detail}")
        return "\n".join(lines)


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def _truthy(value: str) -> bool:
    return value.lower() in {"1", "true", "yes", "on"}


def check_deployment(
    *,
    environment: str = "production",
    platform_db: Optional[Any] = None,
    expected_origins: tuple[str, ...] = (),
    worker_count: int = 1,
) -> PreflightReport:
    """Check the current environment for production-unsafe configuration.

    Reads the live environment rather than a config file, because the environment is what
    the process will actually use — a config file that is correct while the environment
    overrides it is the exact failure this is meant to catch.
    """
    report = PreflightReport(environment=environment)
    _check_authentication(report)
    _check_cors(report, expected_origins)
    _check_bootstrap_admin(report)
    _check_platform_store(report, platform_db, worker_count)
    _check_credential_exposure(report, platform_db)
    _check_model_configuration(report)
    return report


def _check_authentication(report: PreflightReport) -> None:
    disabled = _truthy(_env("ONTOLOGY_AUTH_DISABLED"))
    report.add(
        "认证已开启",
        not disabled,
        detail=("ONTOLOGY_AUTH_DISABLED 为真：全部端点无需令牌即可访问，包括对遗留系统的写回。" if disabled else ""),
        remedy="移除 ONTOLOGY_AUTH_DISABLED（该开关仅供本地开发）",
    )

    ttl = _env("ONTOLOGY_SESSION_TTL_HOURS")
    try:
        hours = int(ttl) if ttl else 12
    except ValueError:
        hours = -1
    report.add(
        "会话有效期合理",
        0 < hours <= 24 * 7,
        severity=WARNING,
        detail=(f"ONTOLOGY_SESSION_TTL_HOURS={ttl!r} 不是 1..168 之间的整数" if not 0 < hours <= 24 * 7 else ""),
        remedy="设为业务可接受的最短时长；令牌泄露后的暴露窗口就是这个值",
    )


def _check_cors(report: PreflightReport, expected_origins: tuple[str, ...]) -> None:
    raw = _env("ONTOLOGY_ALLOWED_ORIGINS")
    origins = [item.strip() for item in raw.split(",") if item.strip()]

    report.add(
        "CORS 未使用通配",
        "*" not in origins,
        detail="ONTOLOGY_ALLOWED_ORIGINS 含 `*`：任意站点都能携带用户凭据驱动本 API。" if "*" in origins else "",
        remedy="改为逐个列出前端来源",
    )

    # Unset means the default, which is localhost — correct for development and wrong for a
    # deployment, where it means the real frontend is blocked and someone will "fix" it
    # with `*`.
    localhost_only = bool(origins) and all(
        urlparse(origin).hostname in {"127.0.0.1", "localhost", "::1"} for origin in origins
    )
    report.add(
        "CORS 已配置为真实前端来源",
        bool(origins) and not localhost_only,
        severity=WARNING,
        detail=(
            "未设置 ONTOLOGY_ALLOWED_ORIGINS，将回落到 localhost 默认值"
            if not origins
            else "仅允许 localhost 来源"
            if localhost_only
            else ""
        ),
        remedy="设为前端实际域名；否则前端被拦，随后有人会用 `*` 绕过",
    )

    if expected_origins:
        missing = sorted(set(expected_origins) - set(origins))
        report.add(
            "预期来源均已允许",
            not missing,
            severity=WARNING,
            detail=f"以下来源未在允许列表中: {missing}" if missing else "",
            remedy="补入 ONTOLOGY_ALLOWED_ORIGINS",
        )


def _check_bootstrap_admin(report: PreflightReport) -> None:
    password = _env("ONTOLOGY_ADMIN_PASSWORD")
    report.add(
        "引导管理员口令已显式设置",
        bool(password),
        severity=WARNING,
        detail=(
            "未设置 ONTOLOGY_ADMIN_PASSWORD：首次启动会生成随机口令并只打印一次，容器化部署中该日志通常已经丢失。"
            if not password
            else ""
        ),
        remedy="通过密钥管理注入 ONTOLOGY_ADMIN_PASSWORD",
    )
    # A weak explicit password is worse than a strong generated one, so length is checked
    # rather than only presence.
    if password:
        report.add(
            "引导管理员口令强度足够",
            len(password) >= 12,
            detail=f"口令长度为 {len(password)}，少于 12 位" if len(password) < 12 else "",
            remedy="使用至少 12 位的随机口令",
        )
        report.add(
            "引导管理员口令不是占位值",
            password.lower() not in _PLACEHOLDER_PASSWORDS,
            detail=f"口令为常见占位值 {password!r}" if password.lower() in _PLACEHOLDER_PASSWORDS else "",
            remedy="替换为真实随机口令",
        )


_PLACEHOLDER_PASSWORDS = {
    "change-me-please",
    "changeme",
    "password",
    "admin",
    "admin123",
    "123456",
    "secret",
    "aletheia",
}


def _check_platform_store(report: PreflightReport, platform_db: Optional[Any], worker_count: int) -> None:
    db_type = (_env("ONTOLOGY_PLATFORM_DB_TYPE") or "sqlite").lower()
    report.add(
        "平台库类型明确声明",
        bool(_env("ONTOLOGY_PLATFORM_DB_TYPE")),
        severity=WARNING,
        detail="未设置 ONTOLOGY_PLATFORM_DB_TYPE，将默认使用 SQLite" if not _env("ONTOLOGY_PLATFORM_DB_TYPE") else "",
        remedy="显式设为 postgresql / mysql / sqlite，避免依赖默认值",
    )

    # SQLite serialises writers. One worker is fine; several will time out under load, and
    # the symptom is intermittent 500s rather than an obvious configuration error.
    report.add(
        "多工作进程未搭配 SQLite",
        not (db_type == "sqlite" and worker_count > 1),
        detail=(
            f"平台库为 SQLite 而工作进程数为 {worker_count}：SQLite 串行化写入，"
            "高并发下表现为间歇性超时，而不是明显的配置错误。"
            if db_type == "sqlite" and worker_count > 1
            else ""
        ),
        remedy="改用 PostgreSQL 或 MySQL，或将工作进程数设为 1",
    )

    if db_type != "sqlite":
        uri = _env("ONTOLOGY_PLATFORM_DB_URI")
        report.add(
            "非 SQLite 平台库已提供连接串",
            bool(uri),
            detail="ONTOLOGY_PLATFORM_DB_TYPE 非 sqlite 但未提供 ONTOLOGY_PLATFORM_DB_URI" if not uri else "",
            remedy="设置 ONTOLOGY_PLATFORM_DB_URI",
        )


def _check_credential_exposure(report: PreflightReport, platform_db: Optional[Any]) -> None:
    uri = _env("ONTOLOGY_PLATFORM_DB_URI")
    has_inline_password = bool(uri) and bool(urlparse(uri).password)
    report.add(
        "平台库连接串未内联口令",
        not has_inline_password,
        severity=WARNING,
        detail=(
            "ONTOLOGY_PLATFORM_DB_URI 内联了口令：它会出现在进程列表、容器 inspect 与崩溃日志里。"
            if has_inline_password
            else ""
        ),
        remedy="改用 .pgpass、IAM 认证或密钥挂载",
    )

    # A SQLite platform database *is* the credential store: it holds every data source's
    # connection string. File mode matters more here than for an ordinary data file.
    path = _sqlite_path(platform_db, uri)
    if path is not None and path.exists():
        mode = path.stat().st_mode & 0o777
        report.add(
            "平台库文件权限已收紧",
            mode & 0o077 == 0,
            detail=(f"{path} 权限为 {oct(mode)}：平台库保存所有数据源连接串，等同凭据存储。" if mode & 0o077 else ""),
            remedy=f"chmod 600 {path}",
        )


def _sqlite_path(platform_db: Optional[Any], uri: str) -> Optional[Path]:
    """The on-disk path of a SQLite platform database, when that is what is configured."""
    candidate = str(platform_db) if platform_db else uri
    if not candidate:
        from .database import DEFAULT_PLATFORM_DB

        candidate = str(DEFAULT_PLATFORM_DB)
    if "://" in candidate:
        parsed = urlparse(candidate)
        if parsed.scheme not in {"sqlite", "file"}:
            return None
        candidate = parsed.path
    return Path(candidate) if candidate.endswith((".sqlite3", ".sqlite", ".db")) else None


def _check_model_configuration(report: PreflightReport) -> None:
    """Model keys are optional, so this only checks that a key is not left in plain env.

    Not critical: the platform works without a model, and the local heuristic path produces
    verdicts on its own. But a key in the environment is a key in every crash dump.
    """
    for name in ("OPENROUTER_API_KEY", "ONTOLOGY_MODEL_API_KEY"):
        value = _env(name)
        if value:
            report.add(
                f"{name} 未以明文环境变量提供",
                False,
                severity=INFO,
                detail=f"{name} 存在于环境变量中：它会进入崩溃转储与容器 inspect。",
                remedy="改用密钥挂载，或通过平台的模型配置接口存储（会被脱敏）",
            )


def describe_checks() -> list[dict[str, str]]:
    """What preflight verifies, for the docs and for `preflight --list`.

    Derived from the checks the current environment actually produces, rather than from a
    hand-maintained list that would drift. Mutating the environment to get a canonical set
    was the alternative and is worse: a describe call must not change what the running
    process is configured with.
    """
    report = check_deployment(environment="describe")
    return [{"name": check.name, "severity": check.severity, "remedy": check.remedy} for check in report.checks]
