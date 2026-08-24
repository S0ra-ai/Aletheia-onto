"""Authentication, sessions and capability authorization.

The platform mutates business ontologies, publishes governed versions and
triggers operations against legacy systems, so every request needs a known
principal. This module owns three things:

1. Credential storage (PBKDF2-SHA256, per-user salt).
2. Opaque bearer tokens, stored only as digests.
3. The mapping from role to capability, used to authorize each route.

The audit trail records the authenticated principal rather than a name supplied
by the client, so `actor` can no longer be spoofed.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from .database import connect
from .schema import ColumnAddition, SchemaBundle

logger = logging.getLogger(__name__)

PBKDF2_ITERATIONS = 240_000
PBKDF2_ALGORITHM = "sha256"
TOKEN_BYTES = 32
DEFAULT_SESSION_TTL_HOURS = 12


# -- Capabilities --

CAP_READ = "platform:read"
CAP_WRITE = "platform:write"
CAP_REVIEW = "governance:review"
CAP_PUBLISH = "governance:publish"
CAP_EXECUTE = "automation:execute"
CAP_ADMIN = "platform:admin"

ALL_CAPABILITIES = (CAP_READ, CAP_WRITE, CAP_REVIEW, CAP_PUBLISH, CAP_EXECUTE, CAP_ADMIN)

# Roles reuse the vocabulary already seeded in permission_role so the object
# level policies and the API level capabilities describe the same actors.
ROLE_CAPABILITIES: dict[str, frozenset[str]] = {
    "admin": frozenset(ALL_CAPABILITIES),
    "ontology_engineer": frozenset({CAP_READ, CAP_WRITE, CAP_PUBLISH}),
    "business_expert": frozenset({CAP_READ, CAP_WRITE, CAP_REVIEW}),
    "operator": frozenset({CAP_READ, CAP_EXECUTE}),
    "analyst": frozenset({CAP_READ}),
    "ai_agent": frozenset({CAP_READ}),
}

DEFAULT_ROLE = "analyst"


SCHEMA_SQL: tuple[dict[str, str], ...] = (
    {
        "sqlite": """
        create table if not exists platform_user (
            id integer primary key autoincrement,
            username text not null unique,
            display_name text not null default '',
            role_code text not null default 'analyst',
            password_hash text not null,
            password_salt text not null,
            iterations integer not null default 240000,
            identity_source text not null default 'local',
            status text not null default 'active',
            created_at text not null default current_timestamp,
            updated_at text not null default current_timestamp,
            last_login_at text
        )""",
        "postgresql": """
        create table if not exists platform_user (
            id serial primary key,
            username text not null unique,
            display_name text not null default '',
            role_code text not null default 'analyst',
            password_hash text not null,
            password_salt text not null,
            iterations integer not null default 240000,
            identity_source text not null default 'local',
            status text not null default 'active',
            created_at timestamp not null default current_timestamp,
            updated_at timestamp not null default current_timestamp,
            last_login_at timestamp
        )""",
        "mysql": """
        create table if not exists platform_user (
            id integer primary key auto_increment,
            username varchar(191) not null unique,
            display_name varchar(255) not null default '',
            role_code varchar(100) not null default 'analyst',
            password_hash varchar(255) not null,
            password_salt varchar(255) not null,
            iterations integer not null default 240000,
            identity_source varchar(32) not null default 'local',
            status varchar(50) not null default 'active',
            created_at datetime not null default current_timestamp,
            updated_at datetime not null default current_timestamp,
            last_login_at datetime
        )""",
    },
    {
        "sqlite": """
        create table if not exists user_session (
            id integer primary key autoincrement,
            token_hash text not null unique,
            user_id integer not null references platform_user(id),
            created_at text not null default current_timestamp,
            expires_at text not null,
            last_seen_at text,
            revoked integer not null default 0
        )""",
        "postgresql": """
        create table if not exists user_session (
            id serial primary key,
            token_hash text not null unique,
            user_id integer not null references platform_user(id),
            created_at timestamp not null default current_timestamp,
            expires_at timestamp not null,
            last_seen_at timestamp,
            revoked integer not null default 0
        )""",
        "mysql": """
        create table if not exists user_session (
            id integer primary key auto_increment,
            token_hash varchar(191) not null unique,
            user_id integer not null references platform_user(id),
            created_at datetime not null default current_timestamp,
            expires_at datetime not null,
            last_seen_at datetime,
            revoked tinyint not null default 0
        )""",
    },
)


@dataclass(frozen=True)
class Principal:
    """An authenticated caller."""

    user_id: int
    username: str
    display_name: str
    role_code: str

    @property
    def capabilities(self) -> frozenset[str]:
        return ROLE_CAPABILITIES.get(self.role_code, frozenset({CAP_READ}))

    def can(self, capability: str) -> bool:
        return capability in self.capabilities

    @property
    def actor(self) -> str:
        """The identity written to audit and decision records."""
        return self.username

    def public_dict(self) -> dict[str, Any]:
        return {
            "userId": self.user_id,
            "username": self.username,
            "displayName": self.display_name or self.username,
            "roleCode": self.role_code,
            "capabilities": sorted(self.capabilities),
        }


class AuthenticationError(Exception):
    """Credentials or token missing, invalid or expired."""


class AuthorizationError(Exception):
    """Authenticated, but the role lacks the required capability."""


# Tables this module owns. Declared as a bundle rather than applied by a hand-written
# dispatch loop: the loop was duplicated in six modules and had to reach into
# `database` for private helpers, which is technical debt items 3 and 5.
SCHEMA = SchemaBundle(
    name="auth",
    tables=SCHEMA_SQL,
    table_names=["platform_user", "user_session"],
    # Added after `platform_user` shipped, so `create table if not exists` would not reach
    # an existing deployment. The default is `local` because that is what every account
    # predating SSO is; migration 0001 then reclassifies the ones SSO created.
    columns=[
        ColumnAddition(
            table="platform_user",
            column="identity_source",
            sqlite_type="text not null default 'local'",
            postgresql_type="text not null default 'local'",
            mysql_type="varchar(32) not null default 'local'",
        )
    ],
)


def init_auth_schema(conn: Any) -> None:
    SCHEMA.apply(conn)


# -- Password handling --


def hash_password(password: str, salt: str | None = None, iterations: int = PBKDF2_ITERATIONS) -> tuple[str, str, int]:
    if not password or len(password) < 8:
        raise ValueError("密码长度至少 8 位")
    resolved_salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        PBKDF2_ALGORITHM,
        password.encode("utf-8"),
        resolved_salt.encode("utf-8"),
        iterations,
    )
    return digest.hex(), resolved_salt, iterations


def verify_password(password: str, password_hash: str, salt: str, iterations: int = PBKDF2_ITERATIONS) -> bool:
    if not password or not password_hash or not salt:
        return False
    candidate = hashlib.pbkdf2_hmac(
        PBKDF2_ALGORITHM,
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    ).hex()
    return hmac.compare_digest(candidate, password_hash)


def hash_token(token: str) -> str:
    """The stored form of a bearer token.

    Public because SSO issues sessions too, and both paths must derive the digest
    identically -- a second implementation would produce tokens that authenticate on one
    path and not the other, which reads as a random logout.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def format_moment(moment: datetime) -> str:
    """The timestamp format every session and audit row uses.

    Public for the same reason as `hash_token`: two login paths writing two formats into
    one column means expiry comparisons work for one of them.
    """
    return moment.strftime("%Y-%m-%d %H:%M:%S")


def _parse(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    for pattern in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, pattern).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


# -- User management --


def create_user(
    platform_db: Path | str,
    username: str,
    password: str,
    role_code: str = DEFAULT_ROLE,
    display_name: str = "",
    actor: str = "system",
) -> dict[str, Any]:
    normalized = (username or "").strip().lower()
    if not normalized:
        raise ValueError("用户名不能为空")
    if role_code not in ROLE_CAPABILITIES:
        raise ValueError(f"不支持的角色: {role_code}。可用角色: {', '.join(sorted(ROLE_CAPABILITIES))}")
    password_hash, salt, iterations = hash_password(password)
    with connect(platform_db) as conn:
        existing = conn.execute("select id from platform_user where username = ?", (normalized,)).fetchone()
        if existing is not None:
            raise ValueError(f"用户已存在: {normalized}")
        conn.execute(
            """
            insert into platform_user (username, display_name, role_code, password_hash, password_salt, iterations)
            values (?, ?, ?, ?, ?, ?)
            """,
            (normalized, display_name or normalized, role_code, password_hash, salt, iterations),
        )
        conn.execute(
            "insert into audit_log (actor, action, target_type, target_id, detail) values (?, ?, ?, ?, ?)",
            (
                actor,
                "create_user",
                "platform_user",
                normalized,
                json.dumps({"roleCode": role_code}, ensure_ascii=False),
            ),
        )
        row = conn.execute(
            "select id, username, display_name, role_code, status, created_at from platform_user where username = ?",
            (normalized,),
        ).fetchone()
        return _user_dict(row)


def list_users(platform_db: Path | str) -> list[dict[str, Any]]:
    with connect(platform_db) as conn:
        rows = conn.execute(
            "select id, username, display_name, role_code, status, created_at, last_login_at from platform_user order by id"
        ).fetchall()
        return [_user_dict(row) for row in rows]


def set_user_status(platform_db: Path | str, username: str, status: str, actor: str = "system") -> dict[str, Any]:
    if status not in {"active", "disabled"}:
        raise ValueError("用户状态只能是 active 或 disabled")
    normalized = (username or "").strip().lower()
    with connect(platform_db) as conn:
        row = conn.execute("select id from platform_user where username = ?", (normalized,)).fetchone()
        if row is None:
            raise ValueError(f"用户不存在: {normalized}")
        conn.execute(
            "update platform_user set status = ?, updated_at = ? where id = ?",
            (status, format_moment(utc_now()), int(row["id"])),
        )
        if status == "disabled":
            conn.execute("update user_session set revoked = 1 where user_id = ?", (int(row["id"]),))
        conn.execute(
            "insert into audit_log (actor, action, target_type, target_id, detail) values (?, ?, ?, ?, ?)",
            (actor, "set_user_status", "platform_user", normalized, json.dumps({"status": status}, ensure_ascii=False)),
        )
        updated = conn.execute(
            "select id, username, display_name, role_code, status, created_at from platform_user where id = ?",
            (int(row["id"]),),
        ).fetchone()
        return _user_dict(updated)


def change_password(platform_db: Path | str, username: str, current_password: str, new_password: str) -> dict[str, Any]:
    normalized = (username or "").strip().lower()
    with connect(platform_db) as conn:
        row = conn.execute(
            "select id, password_hash, password_salt, iterations from platform_user where username = ?",
            (normalized,),
        ).fetchone()
        if row is None:
            raise AuthenticationError("用户名或密码不正确")
        if not verify_password(current_password, row["password_hash"], row["password_salt"], int(row["iterations"])):
            raise AuthenticationError("当前密码不正确")
        password_hash, salt, iterations = hash_password(new_password)
        conn.execute(
            "update platform_user set password_hash = ?, password_salt = ?, iterations = ?, updated_at = ? where id = ?",
            (password_hash, salt, iterations, format_moment(utc_now()), int(row["id"])),
        )
        # Changing a password invalidates existing sessions.
        conn.execute("update user_session set revoked = 1 where user_id = ?", (int(row["id"]),))
        conn.execute(
            "insert into audit_log (actor, action, target_type, target_id, detail) values (?, ?, ?, ?, ?)",
            (normalized, "change_password", "platform_user", normalized, "{}"),
        )
    return {"success": True, "message": "密码已更新，请重新登录。"}


# -- Sessions --


def login(
    platform_db: Path | str,
    username: str,
    password: str,
    ttl_hours: float | None = None,
) -> dict[str, Any]:
    normalized = (username or "").strip().lower()
    with connect(platform_db) as conn:
        row = conn.execute(
            """
            select id, username, display_name, role_code, status, password_hash, password_salt,
                   iterations, identity_source
            from platform_user where username = ?
            """,
            (normalized,),
        ).fetchone()
        # Always run the KDF so a missing user and a wrong password cost the same.
        stored_hash = row["password_hash"] if row is not None else "0" * 64
        stored_salt = row["password_salt"] if row is not None else "0" * 32
        iterations = int(row["iterations"]) if row is not None else PBKDF2_ITERATIONS
        valid = verify_password(password, stored_hash, stored_salt, iterations)
        # An SSO account is refused explicitly, and the KDF still ran above so the refusal
        # costs the same as a wrong password -- otherwise the response time would reveal
        # which accounts are federated.
        #
        # An empty hash already made `verify_password` return False, so this changes no
        # outcome today. It changes what the code *relies on*: the protection was a side
        # effect of a guard clause in another function, and anyone loosening that clause
        # would have opened password login on every SSO account without touching this file.
        federated = row is not None and (row["identity_source"] or "local") != "local"
        if row is None or not valid or federated:
            raise AuthenticationError("用户名或密码不正确")
        if row["status"] != "active":
            raise AuthenticationError("用户已被禁用")

        token = secrets.token_urlsafe(TOKEN_BYTES)
        ttl = float(ttl_hours or os.environ.get("ONTOLOGY_SESSION_TTL_HOURS") or DEFAULT_SESSION_TTL_HOURS)
        expires_at = utc_now() + timedelta(hours=ttl)
        conn.execute(
            "insert into user_session (token_hash, user_id, expires_at, last_seen_at) values (?, ?, ?, ?)",
            (hash_token(token), int(row["id"]), format_moment(expires_at), format_moment(utc_now())),
        )
        conn.execute(
            "update platform_user set last_login_at = ? where id = ?",
            (format_moment(utc_now()), int(row["id"])),
        )
        conn.execute(
            "insert into audit_log (actor, action, target_type, target_id, detail) values (?, ?, ?, ?, ?)",
            (normalized, "login", "platform_user", normalized, json.dumps({"ttlHours": ttl}, ensure_ascii=False)),
        )
        principal = Principal(
            user_id=int(row["id"]),
            username=row["username"],
            display_name=row["display_name"],
            role_code=row["role_code"],
        )
    return {
        "token": token,
        "tokenType": "Bearer",
        "expiresAt": format_moment(expires_at),
        "user": principal.public_dict(),
    }


def logout(platform_db: Path | str, token: str) -> dict[str, Any]:
    with connect(platform_db) as conn:
        conn.execute("update user_session set revoked = 1 where token_hash = ?", (hash_token(token),))
    return {"success": True, "message": "已退出登录。"}


def resolve_principal(platform_db: Path | str, token: str) -> Principal:
    if not token:
        raise AuthenticationError("缺少访问令牌")
    with connect(platform_db) as conn:
        row = conn.execute(
            """
            select s.id as session_id, s.expires_at, s.revoked,
                   u.id as user_id, u.username, u.display_name, u.role_code, u.status
            from user_session s
            join platform_user u on u.id = s.user_id
            where s.token_hash = ?
            """,
            (hash_token(token),),
        ).fetchone()
        if row is None:
            raise AuthenticationError("访问令牌无效")
        if int(row["revoked"]):
            raise AuthenticationError("访问令牌已失效，请重新登录")
        expires_at = _parse(row["expires_at"])
        if expires_at is not None and expires_at < utc_now():
            raise AuthenticationError("访问令牌已过期，请重新登录")
        if row["status"] != "active":
            raise AuthenticationError("用户已被禁用")
        conn.execute(
            "update user_session set last_seen_at = ? where id = ?",
            (format_moment(utc_now()), int(row["session_id"])),
        )
        return Principal(
            user_id=int(row["user_id"]),
            username=row["username"],
            display_name=row["display_name"],
            role_code=row["role_code"],
        )


def authorize(principal: Principal, capability: str) -> None:
    if not principal.can(capability):
        raise AuthorizationError(f"角色 {principal.role_code} 缺少所需权限 {capability}")


def purge_expired_sessions(platform_db: Path | str) -> int:
    with connect(platform_db) as conn:
        cursor = conn.execute("delete from user_session where expires_at < ?", (format_moment(utc_now()),))
        return int(getattr(cursor, "rowcount", 0) or 0)


def ensure_bootstrap_admin(platform_db: Path | str) -> Optional[dict[str, Any]]:
    """Create the first admin so a fresh deployment is reachable.

    Password comes from ONTOLOGY_ADMIN_PASSWORD. When it is unset a random one
    is generated and logged once; it is never written to the database in clear.
    """
    with connect(platform_db) as conn:
        total = conn.execute("select count(*) as total from platform_user").fetchone()["total"]
    if int(total) > 0:
        return None

    username = os.environ.get("ONTOLOGY_ADMIN_USERNAME", "admin").strip().lower()
    password = os.environ.get("ONTOLOGY_ADMIN_PASSWORD", "")
    generated = False
    if not password:
        password = secrets.token_urlsafe(18)
        generated = True
    created = create_user(platform_db, username, password, "admin", "平台管理员", actor="bootstrap")
    if generated:
        logger.warning(
            "已创建初始管理员账号 %s，随机密码: %s （仅本次显示，请立即登录并修改密码）",
            username,
            password,
        )
    return {**created, "generatedPassword": password if generated else None}


def _user_dict(row: Any) -> dict[str, Any]:
    keys = row.keys() if hasattr(row, "keys") else []
    return {
        "id": row["id"],
        "username": row["username"],
        "displayName": row["display_name"],
        "roleCode": row["role_code"],
        "capabilities": sorted(ROLE_CAPABILITIES.get(row["role_code"], frozenset({CAP_READ}))),
        "status": row["status"],
        "createdAt": row["created_at"] if "created_at" in keys else None,
        "lastLoginAt": row["last_login_at"] if "last_login_at" in keys else None,
    }
