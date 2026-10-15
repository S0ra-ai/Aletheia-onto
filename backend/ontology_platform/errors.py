"""Describing failures that arrive as operating-system or driver text.

Every message here exists because the alternative was `str(error)`, and the result was that
the platform's users read:

    unable to open database file
    <urlopen error [Errno 61] Connection refused>
    file is not a database
    Expecting value: line 1 column 1 (char 0)
    no such table: contract

Each of those is true and none of them is usable. They name a symptom in the vocabulary of
whichever component noticed it, in English, in a product whose interface is Chinese — and
the person holding the problem is an engineer who needs to know which of "the file is
wrong", "the service is down" and "the credentials are rejected" they are looking at.

**Why classification is by message and not only by type.** Typing precisely means importing
every driver: sqlite3 is always available, but psycopg, pymysql, oracledb and the rest are
optional by design — the kernel has no third-party dependencies, so it cannot `isinstance`
against an exception class it may not be able to import. The forms below are therefore
matched on text, narrowly, and the original is preserved for the log and for the caller's
`status`/`code` field, which machine consumers read. A restatement that loses the original
would trade one unusable message for another.
"""

from __future__ import annotations

import errno
import json
import socket
import sqlite3
from urllib.error import HTTPError, URLError

# How much of an unexpected error's own text to append. Long enough to be useful in a bug
# report, short enough not to push the actual sentence out of view in a one-line toast.
_DETAIL_LIMIT = 200


def _detail(error: Exception) -> str:
    text = " ".join(str(error).split())
    if len(text) > _DETAIL_LIMIT:
        text = text[: _DETAIL_LIMIT - 1] + "…"
    return text


def describe_data_source_failure(error: Exception) -> str:
    """A data source failure described for the person who configured it.

    Ordered from most specific to least, because several of these arrive as the same
    exception type with different text — `sqlite3.OperationalError` covers both "unable to
    open database file" and "no such table", which call for entirely different actions.

    An exception raised by this package is passed through untouched: its message was written
    for the user when it was raised, and restating it here produced
    `数据源操作失败（FileSourceError）：目录不存在: /x` — the curated sentence wrapped in
    framework wording and an internal class name. This function exists to translate text the
    platform did *not* write: drivers, the standard library, the operating system.
    """
    if type(error).__module__.split(".")[0] == "ontology_platform":
        return str(error)

    text = str(error)
    lowered = text.lower()

    # -- JSON, before anything else: a JSONDecodeError is a ValueError, so a later branch
    # would swallow it into a generic clause.
    if isinstance(error, json.JSONDecodeError):
        return (
            f"返回的内容不是合法 JSON（第 {error.lineno} 行第 {error.colno} 列），"
            "请确认地址指向的是接口而非网页或错误页。"
        )

    # -- Network -------------------------------------------------------------
    if isinstance(error, HTTPError):
        return f"请求被拒绝：HTTP {error.code}。请确认地址、鉴权方式与访问权限。"
    if _is_network_failure(error):
        return _describe_network_failure(error)

    # -- Authentication and authorisation -------------------------------------
    if any(
        phrase in lowered
        for phrase in (
            "password authentication failed",
            "access denied for user",
            "authentication failed",
            "invalid password",
            "login failed",
            "not authorized",
        )
    ):
        return "认证失败：账号或口令被拒绝。请确认凭据，并确认该账号被允许从本机登录。"

    if any(phrase in lowered for phrase in ("permission denied", "read-only file system", "operation not permitted")):
        return "没有读取权限。请确认运行平台的账号对该路径或该资源有访问权限。"

    # -- The path or the file itself ------------------------------------------
    if any(
        phrase in lowered
        for phrase in (
            "unable to open database file",
            "no such file or directory",
            "cannot open",
        )
    ):
        return "数据源文件不存在或无法打开。请确认路径正确、文件已上传，且运行平台的账号能读到它。"

    if "file is not a database" in lowered or "file is encrypted" in lowered:
        return "该文件不是有效的数据库文件（格式不符或已加密）。请确认导出格式与所选的数据源类型一致。"

    if any(phrase in lowered for phrase in ("does not exist", "unknown database", "invalid catalog name")):
        return "目标数据库不存在。请确认库名，以及该账号是否有权看到它。"

    if "no such table" in lowered or ("doesn't exist" in lowered and "table" in lowered):
        # The table name is in the driver's text, and it is the one detail worth keeping:
        # the user mistyped it or scanned a different schema.
        return f"表不存在（{_detail(error)}）。请确认表名，或重新扫描数据源以刷新结构。"

    if isinstance(error, sqlite3.Error):
        return f"数据库操作失败：{_detail(error)}"
    if isinstance(error, OSError):
        return f"读取失败：{_detail(error)}"

    # -- Anything else is a defect rather than a configuration problem --------
    return f"数据源操作失败（{type(error).__name__}）：{_detail(error)}"


def describe_model_failure(error: Exception) -> str:
    """A model call failure described for the person who configured the endpoint.

    The reason is worth showing here — an admin diagnosing a gateway needs "401" or
    "unknown model" — but it is the model service's own wording, so it is presented as a
    quoted reason rather than as this platform's sentence.
    """
    if isinstance(error, HTTPError):
        return f"模型服务返回 HTTP {error.code}。请对照「接入自定义模型服务」检查鉴权方式与模型名。"
    if isinstance(error, json.JSONDecodeError):
        return "模型服务的响应不是合法 JSON，请确认地址指向 OpenAI 兼容的 chat/completions 接口。"
    if _is_network_failure(error):
        return "无法连接模型服务（连接被拒绝、超时或域名不可解析）。请确认地址可达，必要时增大超时。"
    return f"模型调用失败（{type(error).__name__}）：{_detail(error)}"


def _is_network_failure(error: Exception) -> bool:
    """Whether this is a transport failure rather than an application-level one.

    Spelled out as one predicate because the exceptions involved form a small lattice:
    `URLError` wraps a `socket.gaierror` in `.reason`, `socket.timeout` is a subclass of
    `OSError` since 3.10, and a bare `gaierror` can arrive without a `URLError` around it.
    """
    if isinstance(error, (URLError, socket.gaierror, socket.timeout, TimeoutError)):
        return True
    if isinstance(error, OSError):
        return getattr(error, "errno", None) in (errno.ETIMEDOUT, errno.EHOSTUNREACH, errno.ENETUNREACH)
    return False


def _describe_network_failure(error: Exception) -> str:
    if isinstance(error, socket.gaierror) or isinstance(getattr(error, "reason", None), socket.gaierror):
        return "域名无法解析，请检查地址拼写与 DNS 配置。"
    if isinstance(error, (socket.timeout, TimeoutError)) or getattr(error, "errno", None) == errno.ETIMEDOUT:
        return "连接超时，请确认服务可达且网络未被拦截。"
    return "无法连接到该地址（连接被拒绝或不可达），请确认服务已启动、端口正确、防火墙放行。"
