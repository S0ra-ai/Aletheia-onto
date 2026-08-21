"""Credential redaction helpers.

Data source rows and model configuration hold production secrets. Everything
that leaves the platform through an API response or a log line goes through
here first, so the secret stays in the database and the operator still sees
enough to identify the target system.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit

REDACTION = "***"

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
