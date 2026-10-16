"""Credential redaction helpers.

Data source rows and model configuration hold production secrets. Everything
that leaves the platform through an API response or a log line goes through
here first, so the secret stays in the database and the operator still sees
enough to identify the target system.

## The other direction: keeping the secret out of the database

Redaction is what happens on the way *out*. `resolve_secret` is the way in, and it exists because
"the platform database is the credential store" was a limitation with an obvious mitigation that
the documentation recommended and nothing implemented: an operator who would rather not store a
production password can write a reference instead.

    connection_uri = "env:CONTRACTS_DSN"      # read at connect time
    api_key        = "file:/run/secrets/azure-openai-key"

It is deliberately not encryption. A per-row encryption layer needs a crypto dependency the
zero-dependency kernel does not carry, and an encryption layer whose key is stored beside the
ciphertext is worse than none because it looks like protection. This is the other option:
**not storing the secret at all**, which needs nothing and removes the row rather than obscuring
it.

A reference that resolves to nothing is an error rather than an empty string. An empty password
fails to authenticate and reads as "the credentials are wrong"; the reader has to work out that
the platform never had them.
"""

from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit

REDACTION = "***"

# `env:NAME` or `file:/path`. Case-sensitive and lower-case on purpose: a connection URI always
# contains `://`, so `env:` cannot collide with a scheme, and refusing to accept `ENV:` means a
# typo lands in the "not a reference" branch rather than being half-recognised.
_REFERENCE = re.compile(r"^(env|file):(.+)$")


class UnresolvedSecret(RuntimeError):
    """A secret reference that does not point at anything."""


def resolve_secret(value: str | None, *, what: str = "凭据") -> str:
    """A stored value, with an `env:` or `file:` reference read at the point of use.

    Anything that is not a reference is returned unchanged, so this is safe on the many values
    that are ordinary strings -- a SQLite path, a URL, an empty password.

    Called at connect time and never on a display path. That separation is the point: the
    redaction helpers above must keep working on the *reference*, because showing the
    environment variable's name is exactly what an operator needs in order to know which secret
    a data source is using.
    """
    text = (value or "").strip()
    match = _REFERENCE.match(text)
    if not match:
        return text
    kind, target = match.group(1), match.group(2).strip()
    if kind == "env":
        resolved = os.environ.get(target)
        if resolved is None:
            raise UnresolvedSecret(
                f"{what}引用了环境变量 {target}，但它没有设置。"
                "平台不会用空值继续连接——那会失败在「凭据不对」，而不是「没有凭据」。"
            )
        return resolved
    try:
        with open(target, encoding="utf-8") as handle:
            # A trailing newline is how every tool that writes a secret file writes it, and a
            # password with one silently fails to authenticate against most systems.
            return handle.read().strip()
    except OSError as error:
        raise UnresolvedSecret(f"{what}引用了文件 {target}，但读不到它: {error}") from error


def is_reference(value: str | None) -> bool:
    """Whether a stored value is a reference rather than the secret itself.

    For the surfaces that describe a credential: an operator reading "env:CONTRACTS_DSN" learns
    which secret a source uses, where "***" would tell them only that there is one.
    """
    return bool(_REFERENCE.match((value or "").strip()))


_SENSITIVE_HEADER_PATTERN = re.compile(
    r"(authorization|api[-_]?key|token|secret|password|cookie)",
    re.IGNORECASE,
)


def redact_connection_uri(connection_uri: str | None) -> str:
    """Remove the password from a database connection string.

    `mysql://root:s3cret@10.0.0.5:3306/contracts`
    -> `mysql://root:***@10.0.0.5:3306/contracts`

    Local file paths (SQLite) carry no credential and are returned unchanged so
    operators can still see which file is attached.
    """
    value = (connection_uri or "").strip()
    if not value or "://" not in value:
        return value
    try:
        parts = urlsplit(value)
    except ValueError:
        return value
    if not parts.password:
        return value
    host = parts.hostname or ""
    if parts.port:
        host = f"{host}:{parts.port}"
    userinfo = f"{parts.username or ''}:{REDACTION}"
    return urlunsplit((parts.scheme, f"{userinfo}@{host}", parts.path, parts.query, parts.fragment))


def mask_secret(secret: str | None, keep_prefix: int = 6, keep_suffix: int = 4) -> str:
    """Mask a token while keeping enough characters to tell keys apart."""
    value = secret or ""
    if not value:
        return ""
    if len(value) <= keep_prefix + keep_suffix:
        return REDACTION
    return f"{value[:keep_prefix]}...{value[-keep_suffix:]}"


def redact_headers(headers: dict[str, Any] | None) -> dict[str, str]:
    """Redact values of headers that carry credentials."""
    result: dict[str, str] = {}
    for key, value in (headers or {}).items():
        text = "" if value is None else str(value)
        result[str(key)] = REDACTION if _SENSITIVE_HEADER_PATTERN.search(str(key)) else text
    return result
