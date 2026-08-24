"""SSO: an external identity provider proves who, the platform decides what.

ROADMAP stage G's last open item. The platform authenticated users against its own
`platform_user` table, which is workable for a pilot and wrong for a deployment: an
enterprise already has an identity provider, and a second password store means a second
offboarding process. When someone leaves, the account that still works is the one nobody
remembered to disable.

## The provider asserts identity, never authority

This is the decision everything else follows from. An OIDC token can carry any claim the
provider chooses to put in it, including `role: admin`. Trusting that claim would move
the platform's authorization boundary into someone else's configuration -- and the group
memberships in a corporate directory were not designed as a permission model for this
platform.

So a claim never becomes a capability directly. An administrator declares a mapping from
provider group to platform role, and an identity carrying no mapped group gets **no
access at all** rather than a default role. The alternative -- defaulting to the lowest
role -- sounds safe and is not: it silently grants every employee read access to every
business object the platform can reach, which is exactly what object permissions exist to
prevent.

## Local accounts are not replaced

Both paths coexist deliberately. A deployment that turns SSO on still needs a way in when
the provider is unreachable, and "the IdP is down so nobody can fix the IdP integration"
is a real outage shape. The bootstrap admin therefore keeps its password.

What is refused is the dangerous middle: an SSO identity cannot be used to *set* a
password, and a local account cannot be silently upgraded into an SSO one. Either would
let one authentication path be used to weaken the other.

## Tokens are verified, not decoded

The signature check is the whole point of accepting an external token, so a deployment
must configure a verification key. Absent one, SSO refuses to start rather than falling
back to decoding claims without checking them -- an unverified token is a token the
caller wrote themselves.

Verification is deliberately narrow: signature, issuer, audience, expiry, and nothing
else. No discovery, no dynamic key rotation, no nested assertion parsing. Those need a
real deployment to shape them, and each one is a place where a subtle mistake accepts a
forged token.

Stability: experimental (ADR-0007).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Optional

from .auth import (
    ROLE_CAPABILITIES,
    TOKEN_BYTES,
    AuthenticationError,
    Principal,
    format_moment,
    hash_token,
    utc_now,
)
from .context import PlatformDb
from .database import connect
from .schema import SchemaBundle

logger = logging.getLogger(__name__)

__all__ = [
    "SCHEMA",
    "SsoConfig",
    "SsoError",
    "declare_group_mapping",
    "describe_sso",
    "init_sso_schema",
    "list_group_mappings",
    "login_with_assertion",
    "remove_group_mapping",
    "verify_assertion",
]

# Supported signature algorithms. HMAC only, and that is a deliberate limit rather than an
# oversight: RS256 needs an asymmetric crypto library, and the kernel is dependency-free.
# A deployment needing RS256 registers its own verifier through the same seam.
SUPPORTED_ALGORITHMS = ("HS256", "HS384", "HS512")

_DIGEST_BY_ALGORITHM = {"HS256": hashlib.sha256, "HS384": hashlib.sha384, "HS512": hashlib.sha512}

SCHEMA = SchemaBundle(
    name="sso",
    tables=[
        {
            "sqlite": (
                "create table if not exists sso_group_mapping ("
                "id integer primary key autoincrement,"
                " provider_group text not null,"
                " role_code text not null,"
                " note text not null default '',"
                " unique(provider_group))"
            ),
            "postgresql": (
                "create table if not exists sso_group_mapping ("
                "id serial primary key,"
                " provider_group text not null,"
                " role_code text not null,"
                " note text not null default '',"
                " unique(provider_group))"
            ),
            "mysql": (
                "create table if not exists sso_group_mapping ("
                "id integer primary key auto_increment,"
                " provider_group varchar(255) not null,"
                " role_code varchar(64) not null,"
                " note text not null,"
                " unique(provider_group))"
            ),
        }
    ],
    table_names=["sso_group_mapping"],
)


class SsoError(AuthenticationError):
    """Raised when an assertion cannot be trusted, or SSO is misconfigured.

    A subclass of `AuthenticationError` so the middleware's existing 401 handling applies:
    an untrusted assertion and a wrong password are the same answer to the caller.
    """


@dataclass(frozen=True)
class SsoConfig:
    """What is needed to trust an assertion. All from the environment.

    Environment rather than the database on purpose: the verification key is a credential,
    and a credential in the platform database is a credential in every backup of it.
    """

    issuer: str = ""
    audience: str = ""
    secret: str = ""
    algorithm: str = "HS256"
    group_claim: str = "groups"
    username_claim: str = "sub"
    display_name_claim: str = "name"

    @classmethod
    def from_env(cls) -> "SsoConfig":
        return cls(
            issuer=os.environ.get("ONTOLOGY_SSO_ISSUER", "").strip(),
            audience=os.environ.get("ONTOLOGY_SSO_AUDIENCE", "").strip(),
            secret=os.environ.get("ONTOLOGY_SSO_SECRET", "").strip(),
            algorithm=(os.environ.get("ONTOLOGY_SSO_ALGORITHM", "") or "HS256").strip().upper(),
            group_claim=(os.environ.get("ONTOLOGY_SSO_GROUP_CLAIM", "") or "groups").strip(),
            username_claim=(os.environ.get("ONTOLOGY_SSO_USERNAME_CLAIM", "") or "sub").strip(),
            display_name_claim=(os.environ.get("ONTOLOGY_SSO_NAME_CLAIM", "") or "name").strip(),
        )

    @property
    def enabled(self) -> bool:
        """SSO is on only when it can actually verify something.

        Requiring all three means a half-configured deployment behaves as "SSO off" rather
        than as "SSO on and accepting anything", which is the direction that matters.
        """
        return bool(self.issuer and self.audience and self.secret)

    def require(self) -> "SsoConfig":
        if not self.enabled:
            missing = [
                name
                for name, value in (
                    ("ONTOLOGY_SSO_ISSUER", self.issuer),
                    ("ONTOLOGY_SSO_AUDIENCE", self.audience),
                    ("ONTOLOGY_SSO_SECRET", self.secret),
                )
                if not value
            ]
            raise SsoError(f"SSO 未启用，缺少配置: {'、'.join(missing)}")
        if self.algorithm not in SUPPORTED_ALGORITHMS:
            raise SsoError(f"不支持的签名算法 {self.algorithm}，可选: {'、'.join(SUPPORTED_ALGORITHMS)}")
        return self


def init_sso_schema(conn: Any) -> None:
    SCHEMA.apply(conn)


def describe_sso(platform_db: PlatformDb, config: Optional[SsoConfig] = None) -> dict[str, Any]:
    """Whether SSO is usable, and what it would grant. Never the secret.

    Reports the *effective* state including whether any group is mapped, because SSO that
    verifies correctly and maps nothing rejects every login -- and "configured but nobody
    can log in" is otherwise indistinguishable from a signature problem.
    """
    resolved = config or SsoConfig.from_env()
    mappings = list_group_mappings(platform_db)
    return {
        "enabled": resolved.enabled,
        "issuer": resolved.issuer,
        "audience": resolved.audience,
        "algorithm": resolved.algorithm,
        "groupClaim": resolved.group_claim,
        "usernameClaim": resolved.username_claim,
        "mappedGroups": len(mappings),
        "mappings": mappings,
        "note": ("身份由提供方断言，权限由平台决定：未映射到任何角色的身份将被拒绝，而不是给一个默认角色。"),
    }


# -- Group to role mapping --


def declare_group_mapping(
    platform_db: PlatformDb,
    provider_group: str,
    role_code: str,
    *,
    note: str = "",
    actor: str = "system",
) -> dict[str, Any]:
    """Map one provider group to one platform role.

    The role must already exist in `ROLE_CAPABILITIES`. A mapping to an unknown role would
    produce a principal whose capabilities resolve to nothing -- the user would
    authenticate successfully and then be refused by every endpoint, which reads as a
    platform fault rather than a configuration one.
    """
    group = (provider_group or "").strip()
    role = (role_code or "").strip()
    if not group:
        raise SsoError("提供方组名不能为空")
    if role not in ROLE_CAPABILITIES:
        raise SsoError(f"未知平台角色 {role}，可选: {'、'.join(sorted(ROLE_CAPABILITIES))}")

    with connect(platform_db) as conn:
        init_sso_schema(conn)
        conn.execute("delete from sso_group_mapping where provider_group = ?", (group,))
        conn.execute(
            "insert into sso_group_mapping (provider_group, role_code, note) values (?, ?, ?)",
            (group, role, note),
        )
        conn.execute(
            "insert into audit_log (actor, action, target_type, target_id, detail) values (?, ?, ?, ?, ?)",
            (
                actor,
                "declare_sso_mapping",
                "sso_group_mapping",
                group,
                json.dumps({"roleCode": role}, ensure_ascii=False),
            ),
        )
    return {"providerGroup": group, "roleCode": role, "note": note}


def remove_group_mapping(platform_db: PlatformDb, provider_group: str, *, actor: str = "system") -> dict[str, Any]:
    group = (provider_group or "").strip()
    with connect(platform_db) as conn:
        init_sso_schema(conn)
        cursor = conn.execute("delete from sso_group_mapping where provider_group = ?", (group,))
        removed = getattr(cursor, "rowcount", 0) or 0
        if removed:
            conn.execute(
                "insert into audit_log (actor, action, target_type, target_id, detail) values (?, ?, ?, ?, '{}')",
                (actor, "remove_sso_mapping", "sso_group_mapping", group),
            )
    if not removed:
        raise SsoError(f"组映射不存在: {group}")
    return {"removed": group}


def list_group_mappings(platform_db: PlatformDb) -> list[dict[str, Any]]:
    with connect(platform_db) as conn:
        if not SCHEMA.has_tables(conn):
            return []
        rows = conn.execute(
            "select provider_group, role_code, note from sso_group_mapping order by provider_group"
        ).fetchall()
    return [{"providerGroup": row["provider_group"], "roleCode": row["role_code"], "note": row["note"]} for row in rows]


# -- Assertion verification --


def _b64url_decode(segment: str) -> bytes:
    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + padding)


def verify_assertion(assertion: str, config: Optional[SsoConfig] = None) -> dict[str, Any]:
    """Verify a JWT and return its claims, or raise.

    Signature first, then registered claims. Order matters: parsing claims from an
    unverified token and validating them afterwards means the validation ran on data the
    caller controls, and a mistake anywhere in it accepts a forged token.

    `alg` is taken from the configuration, never from the token header. A token that names
    its own algorithm can name `none` -- the classic JWT bypass -- and this refuses to look
    at the header's claim at all rather than checking it against a list.
    """
    resolved = (config or SsoConfig.from_env()).require()

    parts = (assertion or "").strip().split(".")
    if len(parts) != 3:
        raise SsoError("断言格式无效：应为三段 JWT")
    header_segment, payload_segment, signature_segment = parts

    digest = _DIGEST_BY_ALGORITHM[resolved.algorithm]
    expected = hmac.new(
        resolved.secret.encode("utf-8"),
        f"{header_segment}.{payload_segment}".encode("ascii"),
        digest,
    ).digest()
    try:
        provided = _b64url_decode(signature_segment)
    except Exception as error:
        raise SsoError("断言签名无法解码") from error
    # Constant time: a length or content leak here is a signature-forgery oracle.
    if not hmac.compare_digest(expected, provided):
        raise SsoError("断言签名校验失败")

    try:
        claims = json.loads(_b64url_decode(payload_segment))
    except Exception as error:
        raise SsoError("断言载荷无法解析") from error
    if not isinstance(claims, dict):
        raise SsoError("断言载荷不是对象")

    if claims.get("iss") != resolved.issuer:
        raise SsoError(f"签发方不匹配: {claims.get('iss')!r}")

    audience = claims.get("aud")
    audiences = audience if isinstance(audience, list) else [audience]
    if resolved.audience not in audiences:
        raise SsoError(f"受众不匹配: {audience!r}")

    expiry = claims.get("exp")
    if expiry is None:
        # A token that never expires is a permanent credential, and revoking it requires
        # rotating the signing key for everyone.
        raise SsoError("断言缺少 exp，不接受永不过期的凭据")
    try:
        expires_at = float(expiry)
    except (TypeError, ValueError) as error:
        raise SsoError(f"exp 不是时间戳: {expiry!r}") from error
    if expires_at <= utc_now().timestamp():
        raise SsoError("断言已过期")

    return claims


def _mapped_role(platform_db: PlatformDb, groups: Any) -> Optional[str]:
    """The platform role for these provider groups, or None.

    When an identity carries several mapped groups, the **most capable** role wins. The
    alternative -- refusing ambiguity -- reads as safer and is not: a user in both
    `analysts` and `approvers` is legitimately both, and refusing their login pushes the
    administrator toward one over-broad group instead of two precise ones.
    """
    if isinstance(groups, str):
        candidates = [groups]
    elif isinstance(groups, (list, tuple)):
        candidates = [str(item) for item in groups]
    else:
        return None

    mappings = {item["providerGroup"]: item["roleCode"] for item in list_group_mappings(platform_db)}
    roles = {mappings[name] for name in candidates if name in mappings}
    if not roles:
        return None
    return max(roles, key=lambda role: len(ROLE_CAPABILITIES.get(role, ())))


def login_with_assertion(
    platform_db: PlatformDb,
    assertion: str,
    *,
    config: Optional[SsoConfig] = None,
    ttl_hours: float | None = None,
) -> dict[str, Any]:
    """Exchange a verified assertion for a platform session.

    The provider decides *who*; the mapping decides *what*. An identity whose groups map to
    nothing is refused outright rather than given a default role: a default would silently
    grant every employee read access to every business object the platform reaches, which
    is what object permissions exist to prevent.

    The local account is created or updated on first login, so `platform_user` remains the
    single place a session resolves from -- the middleware, audit trail and object
    permissions all read a principal, and giving SSO its own parallel identity path would
    mean two places where "who is this" is answered.
    """
    resolved = (config or SsoConfig.from_env()).require()
    claims = verify_assertion(assertion, resolved)

    username = str(claims.get(resolved.username_claim) or "").strip().lower()
    if not username:
        raise SsoError(f"断言缺少用户标识声明 {resolved.username_claim}")

    role_code = _mapped_role(platform_db, claims.get(resolved.group_claim))
    if role_code is None:
        raise SsoError(
            f"身份 {username} 的组未映射到任何平台角色，已拒绝。"
            "请由平台管理员声明组到角色的映射——未映射即无权限，不会给默认角色。"
        )

    display_name = str(claims.get(resolved.display_name_claim) or username).strip()

    with connect(platform_db) as conn:
        init_sso_schema(conn)
        row = conn.execute(
            "select id, status from platform_user where username = ?",
            (username,),
        ).fetchone()

        if row is None:
            conn.execute(
                # `identity_source` is declared rather than inferred from an empty hash.
                # The empty hash still blocks a password login, but that protection was a
                # side effect of `verify_password`'s guard clause; this makes it a property
                # of the record, which is what `login` can then check deliberately.
                "insert into platform_user (username, display_name, role_code, password_hash,"
                " password_salt, iterations, identity_source, status)"
                " values (?, ?, ?, '', '', 0, 'sso', 'active')",
                (username, display_name, role_code),
            )
            user_id = int(conn.execute("select id from platform_user where username = ?", (username,)).fetchone()["id"])
            action = "sso_provision"
        else:
            if row["status"] != "active":
                # A disabled local account overrides the provider. Offboarding must be
                # effective from either side, and the platform's own switch is the one an
                # operator can reach during an incident.
                raise SsoError("用户已被禁用")
            user_id = int(row["id"])
            # The role is re-derived on every login, so removing someone from a group takes
            # effect at their next sign-in rather than whenever someone remembers.
            conn.execute(
                "update platform_user set display_name = ?, role_code = ?, updated_at = ? where id = ?",
                (display_name, role_code, format_moment(utc_now()), user_id),
            )
            action = "sso_login"

        token = secrets.token_urlsafe(TOKEN_BYTES)
        ttl = float(ttl_hours or os.environ.get("ONTOLOGY_SESSION_TTL_HOURS") or 12)
        expires_at = utc_now() + timedelta(hours=ttl)
        conn.execute(
            "insert into user_session (token_hash, user_id, expires_at, last_seen_at) values (?, ?, ?, ?)",
            (hash_token(token), user_id, format_moment(expires_at), format_moment(utc_now())),
        )
        conn.execute(
            "update platform_user set last_login_at = ? where id = ?",
            (format_moment(utc_now()), user_id),
        )
        conn.execute(
            "insert into audit_log (actor, action, target_type, target_id, detail) values (?, ?, ?, ?, ?)",
            (
                username,
                action,
                "platform_user",
                username,
                # The issuer and mapped role are recorded because "why did this person have
                # this role" is the question an audit asks about federated access.
                json.dumps(
                    {"issuer": resolved.issuer, "roleCode": role_code, "ttlHours": ttl},
                    ensure_ascii=False,
                ),
            ),
        )

        principal = Principal(
            user_id=user_id,
            username=username,
            display_name=display_name,
            role_code=role_code,
        )

    return {
        "token": token,
        "tokenType": "Bearer",
        "expiresAt": format_moment(expires_at),
        "user": principal.public_dict(),
        "identitySource": "sso",
    }
