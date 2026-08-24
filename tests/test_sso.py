"""SSO: the provider proves who, the platform decides what.

ROADMAP stage G's last open item. An enterprise already has an identity provider, and a
second password store means a second offboarding process -- when someone leaves, the
account that still works is the one nobody remembered to disable.

The properties that make federated access safe here:

- **a claim never becomes a capability directly.** An OIDC token can carry `role: admin`;
  trusting it would move the authorization boundary into someone else's configuration.
- **an unmapped identity is refused, not defaulted.** A default role sounds safe and is
  not: it silently grants every employee read access to every business object the platform
  reaches, which is what object permissions exist to prevent.
- **`alg` comes from configuration, never from the token.** A token that names its own
  algorithm can name `none`, which is the classic JWT bypass.
- **the platform's own disable switch wins.** Offboarding must work from either side, and
  the platform's switch is the one an operator can reach during an incident.

Every one of those has a counter-example test. A signature check that has never been shown
to reject anything is indistinguishable from no signature check.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from ontology_platform.auth import init_auth_schema, resolve_principal, set_user_status
from ontology_platform.database import connect, initialize_platform_db
from ontology_platform.sso import (
    SsoConfig,
    SsoError,
    declare_group_mapping,
    describe_sso,
    init_sso_schema,
    list_group_mappings,
    login_with_assertion,
    remove_group_mapping,
    verify_assertion,
)

SECRET = "test-signing-secret-do-not-reuse"
CONFIG = SsoConfig(issuer="https://idp.example.com", audience="aletheia", secret=SECRET)


@pytest.fixture
def platform_db(tmp_path: Path) -> Path:
    database = tmp_path / "platform.sqlite3"
    initialize_platform_db(database)
    with connect(database) as conn:
        init_auth_schema(conn)
        init_sso_schema(conn)
        # Idempotent: startup runs this on every boot.
        init_sso_schema(conn)
    return database


def _b64(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")


def _assertion(
    claims: dict,
    *,
    secret: str = SECRET,
    algorithm: str = "HS256",
    header: dict | None = None,
) -> str:
    """Mint a JWT. Separate knobs for header and secret so a forgery can be constructed."""
    header_segment = _b64(json.dumps(header or {"alg": algorithm, "typ": "JWT"}).encode())
    payload_segment = _b64(json.dumps(claims).encode())
    digest = {"HS256": hashlib.sha256, "HS384": hashlib.sha384, "HS512": hashlib.sha512}[algorithm]
    signature = hmac.new(secret.encode(), f"{header_segment}.{payload_segment}".encode("ascii"), digest).digest()
    return f"{header_segment}.{payload_segment}.{_b64(signature)}"


def _claims(**overrides) -> dict:
    base = {
        "iss": CONFIG.issuer,
        "aud": CONFIG.audience,
        "sub": "zhang.san",
        "name": "张三",
        "groups": ["contract-analysts"],
        "exp": time.time() + 600,
    }
    base.update(overrides)
    return base


# -- Configuration --


def test_sso_is_off_until_it_can_verify_something(platform_db) -> None:
    """A half-configured deployment must behave as "SSO off", never as "SSO on and
    accepting anything"."""
    assert SsoConfig().enabled is False
    assert SsoConfig(issuer="i", audience="a").enabled is False
    assert SsoConfig(issuer="i", audience="a", secret="s").enabled is True


def test_using_sso_without_configuration_refuses_rather_than_trusting_claims(platform_db) -> None:
    """The dangerous fallback would be decoding claims without checking them -- an
    unverified token is a token the caller wrote themselves."""
    with pytest.raises(SsoError, match="SSO 未启用"):
        login_with_assertion(platform_db, _assertion(_claims()), config=SsoConfig())


def test_an_unsupported_algorithm_is_refused(platform_db) -> None:
    with pytest.raises(SsoError, match="不支持的签名算法"):
        verify_assertion(
            _assertion(_claims()),
            SsoConfig(issuer=CONFIG.issuer, audience=CONFIG.audience, secret=SECRET, algorithm="RS256"),
        )


def test_the_status_report_never_includes_the_secret(platform_db) -> None:
    """It would then appear in every screenshot and browser cache of the settings page."""
    report = describe_sso(platform_db, CONFIG)
    assert report["enabled"] is True
    assert SECRET not in json.dumps(report, ensure_ascii=False)


def test_the_status_report_says_how_many_groups_are_mapped(platform_db) -> None:
    """SSO that verifies correctly and maps nothing rejects every login, which is otherwise
    indistinguishable from a signature problem."""
    assert describe_sso(platform_db, CONFIG)["mappedGroups"] == 0
    declare_group_mapping(platform_db, "contract-analysts", "analyst")
    assert describe_sso(platform_db, CONFIG)["mappedGroups"] == 1


# -- Signature verification --


def test_a_valid_assertion_verifies(platform_db) -> None:
    claims = verify_assertion(_assertion(_claims()), CONFIG)
    assert claims["sub"] == "zhang.san"


def test_a_forged_signature_is_rejected(platform_db) -> None:
    """The counter-example that makes every other test here mean something."""
    with pytest.raises(SsoError, match="签名校验失败"):
        verify_assertion(_assertion(_claims(), secret="attacker-secret"), CONFIG)


def test_a_tampered_payload_is_rejected(platform_db) -> None:
    """Escalating a role by editing the payload must invalidate the signature."""
    valid = _assertion(_claims())
    header, _, signature = valid.split(".")
    forged_payload = _b64(json.dumps(_claims(groups=["platform-admins"])).encode())
    with pytest.raises(SsoError, match="签名校验失败"):
        verify_assertion(f"{header}.{forged_payload}.{signature}", CONFIG)


def test_the_algorithm_is_not_taken_from_the_token_header(platform_db) -> None:
    """The classic JWT bypass: a token naming `alg: none` and carrying no signature.

    Refused because the algorithm comes from configuration and the header's claim is never
    read -- checking it against a list would still be trusting the token to describe itself.
    """
    header = _b64(json.dumps({"alg": "none", "typ": "JWT"}).encode())
    payload = _b64(json.dumps(_claims(groups=["platform-admins"])).encode())
    with pytest.raises(SsoError, match="签名校验失败"):
        verify_assertion(f"{header}.{payload}.", CONFIG)


def test_a_malformed_assertion_is_rejected(platform_db) -> None:
    for bad in ("", "not-a-jwt", "only.two"):
        with pytest.raises(SsoError):
            verify_assertion(bad, CONFIG)


# -- Registered claims --


def test_a_different_issuer_is_rejected(platform_db) -> None:
    """A correctly signed token from another tenant of the same provider is still not for
    this deployment."""
    with pytest.raises(SsoError, match="签发方不匹配"):
        verify_assertion(_assertion(_claims(iss="https://evil.example.com")), CONFIG)


def test_a_different_audience_is_rejected(platform_db) -> None:
    """Otherwise a token minted for another application is accepted here -- token reuse
    across services is exactly what `aud` prevents."""
    with pytest.raises(SsoError, match="受众不匹配"):
        verify_assertion(_assertion(_claims(aud="some-other-app")), CONFIG)


def test_an_audience_list_containing_ours_is_accepted(platform_db) -> None:
    """`aud` is legitimately a list when a token is issued for several services."""
    claims = verify_assertion(_assertion(_claims(aud=["other-app", CONFIG.audience])), CONFIG)
    assert claims["sub"] == "zhang.san"


def test_an_expired_assertion_is_rejected(platform_db) -> None:
    with pytest.raises(SsoError, match="已过期"):
        verify_assertion(_assertion(_claims(exp=time.time() - 1)), CONFIG)


def test_an_assertion_without_expiry_is_rejected(platform_db) -> None:
    """A token that never expires is a permanent credential, and revoking it would require
    rotating the signing key for everyone."""
    claims = _claims()
    del claims["exp"]
    with pytest.raises(SsoError, match="缺少 exp"):
        verify_assertion(_assertion(claims), CONFIG)


# -- Group to role mapping is where authority is decided --


def test_an_unmapped_identity_is_refused_rather_than_given_a_default_role(platform_db) -> None:
    """The decision the whole design rests on.

    A default role would silently grant every employee in the directory read access to
    every business object the platform reaches.
    """
    with pytest.raises(SsoError, match="未映射到任何平台角色"):
        login_with_assertion(platform_db, _assertion(_claims()), config=CONFIG)

    with connect(platform_db) as conn:
        assert conn.execute("select count(*) as c from platform_user").fetchone()["c"] == 0, (
            "被拒绝的登录不应留下用户记录"
        )


def test_a_role_claim_in_the_token_grants_nothing(platform_db) -> None:
    """A provider can put any claim in a token. Authority comes from the mapping only."""
    declare_group_mapping(platform_db, "contract-analysts", "analyst")
    session = login_with_assertion(
        platform_db,
        _assertion(_claims(role="admin", roleCode="admin", capabilities=["platform:admin"])),
        config=CONFIG,
    )
    assert session["user"]["roleCode"] == "analyst", "令牌里的角色声明不应影响平台角色"


def test_a_mapping_to_an_unknown_role_is_refused(platform_db) -> None:
    """It would produce a principal whose capabilities resolve to nothing: the user
    authenticates and is then refused by every endpoint, which reads as a platform fault."""
    with pytest.raises(SsoError, match="未知平台角色"):
        declare_group_mapping(platform_db, "some-group", "wizard")


def test_the_most_capable_mapped_role_wins(platform_db) -> None:
    """Refusing ambiguity reads as safer and is not: a user in both `analysts` and
    `approvers` is legitimately both, and refusing their login pushes the administrator
    toward one over-broad group instead of two precise ones."""
    declare_group_mapping(platform_db, "analysts", "analyst")
    declare_group_mapping(platform_db, "admins", "admin")
    session = login_with_assertion(platform_db, _assertion(_claims(groups=["analysts", "admins"])), config=CONFIG)
    assert session["user"]["roleCode"] == "admin"


def test_removing_a_mapping_revokes_future_logins(platform_db) -> None:
    declare_group_mapping(platform_db, "contract-analysts", "analyst")
    login_with_assertion(platform_db, _assertion(_claims()), config=CONFIG)

    remove_group_mapping(platform_db, "contract-analysts")
    with pytest.raises(SsoError, match="未映射到任何平台角色"):
        login_with_assertion(platform_db, _assertion(_claims()), config=CONFIG)


def test_removing_a_nonexistent_mapping_reports_rather_than_silently_succeeding(platform_db) -> None:
    with pytest.raises(SsoError, match="映射不存在"):
        remove_group_mapping(platform_db, "never-declared")


def test_a_mapping_is_replaced_rather_than_duplicated(platform_db) -> None:
    declare_group_mapping(platform_db, "analysts", "analyst")
    declare_group_mapping(platform_db, "analysts", "admin")
    assert list_group_mappings(platform_db) == [{"providerGroup": "analysts", "roleCode": "admin", "note": ""}]


# -- Sessions and provisioning --


def test_a_successful_login_issues_a_usable_platform_session(platform_db) -> None:
    """The session must resolve through the same path as a password login, or the
    middleware, audit trail and object permissions would each need a second answer to
    "who is this"."""
    declare_group_mapping(platform_db, "contract-analysts", "analyst")
    session = login_with_assertion(platform_db, _assertion(_claims()), config=CONFIG)

    assert session["identitySource"] == "sso"
    principal = resolve_principal(platform_db, session["token"])
    assert principal.username == "zhang.san"
    assert principal.role_code == "analyst"


def test_the_role_is_re_derived_on_every_login(platform_db) -> None:
    """So removing someone from a group takes effect at their next sign-in, rather than
    whenever an administrator remembers to edit the local account."""
    declare_group_mapping(platform_db, "analysts", "analyst")
    declare_group_mapping(platform_db, "admins", "admin")

    first = login_with_assertion(platform_db, _assertion(_claims(groups=["admins"])), config=CONFIG)
    assert first["user"]["roleCode"] == "admin"

    second = login_with_assertion(platform_db, _assertion(_claims(groups=["analysts"])), config=CONFIG)
    assert second["user"]["roleCode"] == "analyst", "降级后的组应立即生效"


def test_a_disabled_local_account_overrides_the_provider(platform_db) -> None:
    """Offboarding must be effective from either side, and the platform's own switch is the
    one an operator can reach during an incident."""
    declare_group_mapping(platform_db, "contract-analysts", "analyst")
    login_with_assertion(platform_db, _assertion(_claims()), config=CONFIG)

    set_user_status(platform_db, "zhang.san", "disabled")
    with pytest.raises(SsoError, match="已被禁用"):
        login_with_assertion(platform_db, _assertion(_claims()), config=CONFIG)


def test_an_sso_account_has_no_usable_password(platform_db) -> None:
    """An SSO identity must not be usable to obtain a password login: that would let one
    authentication path weaken the other."""
    from ontology_platform.auth import AuthenticationError, login

    declare_group_mapping(platform_db, "contract-analysts", "analyst")
    login_with_assertion(platform_db, _assertion(_claims()), config=CONFIG)

    for attempt in ("", "password", "zhang.san"):
        with pytest.raises(AuthenticationError):
            login(platform_db, "zhang.san", attempt)


def test_the_login_is_audited_with_the_issuer_and_mapped_role(platform_db) -> None:
    """ "Why did this person have this role" is the question an audit asks about federated
    access, and it is unanswerable from a username alone."""
    declare_group_mapping(platform_db, "contract-analysts", "analyst")
    login_with_assertion(platform_db, _assertion(_claims()), config=CONFIG)

    with connect(platform_db) as conn:
        row = conn.execute(
            "select action, detail from audit_log where target_id = 'zhang.san' order by id desc"
        ).fetchone()
    assert row["action"] in ("sso_provision", "sso_login")
    detail = json.loads(row["detail"])
    assert detail["issuer"] == CONFIG.issuer
    assert detail["roleCode"] == "analyst"


def test_a_missing_username_claim_is_refused(platform_db) -> None:
    """An identity with no stable identifier cannot be audited, and the audit trail is the
    product."""
    declare_group_mapping(platform_db, "contract-analysts", "analyst")
    claims = _claims()
    del claims["sub"]
    with pytest.raises(SsoError, match="缺少用户标识声明"):
        login_with_assertion(platform_db, _assertion(claims), config=CONFIG)


def test_listing_mappings_without_the_table_returns_empty(tmp_path: Path) -> None:
    """An installation that has not applied the migration must read as "no mappings"
    rather than failing every request that reports SSO state."""
    database = tmp_path / "bare.sqlite3"
    initialize_platform_db(database)
    assert list_group_mappings(database) == []


# -- Preflight --


def test_preflight_blocks_sso_enabled_with_no_mappings(platform_db, monkeypatch) -> None:
    """The failure shape worth catching before requests arrive.

    A deployment switches to federated login, restarts, and nobody can sign in -- while the
    platform reports healthy, because verification is working exactly as configured. From
    the outside that is indistinguishable from a signature problem, and the two have
    opposite fixes.
    """
    from ontology_platform.deployment import check_deployment

    for name, value in (
        ("ONTOLOGY_SSO_ISSUER", CONFIG.issuer),
        ("ONTOLOGY_SSO_AUDIENCE", CONFIG.audience),
        ("ONTOLOGY_SSO_SECRET", SECRET),
    ):
        monkeypatch.setenv(name, value)

    report = check_deployment(platform_db=platform_db, environment="production")
    failing = {check.name for check in report.checks if not check.passed}
    assert "SSO 组角色映射已声明" in failing, [check.name for check in report.checks]

    declare_group_mapping(platform_db, "contract-analysts", "analyst")
    report = check_deployment(platform_db=platform_db, environment="production")
    passing = {check.name for check in report.checks if check.passed}
    assert "SSO 组角色映射已声明" in passing


def test_preflight_reports_a_half_configured_sso(platform_db, monkeypatch) -> None:
    """Half-configured is the case where the operator believes SSO is on and it silently
    is not."""
    from ontology_platform.deployment import check_deployment

    monkeypatch.setenv("ONTOLOGY_SSO_ISSUER", CONFIG.issuer)
    monkeypatch.delenv("ONTOLOGY_SSO_AUDIENCE", raising=False)
    monkeypatch.delenv("ONTOLOGY_SSO_SECRET", raising=False)

    report = check_deployment(platform_db=platform_db, environment="production")
    failing = {check.name for check in report.checks if not check.passed}
    assert "SSO 配置完整" in failing


def test_preflight_says_nothing_about_sso_when_it_is_off(platform_db, monkeypatch) -> None:
    """A deployment using password login must not be told it has an SSO problem."""
    from ontology_platform.deployment import check_deployment

    for name in ("ONTOLOGY_SSO_ISSUER", "ONTOLOGY_SSO_AUDIENCE", "ONTOLOGY_SSO_SECRET"):
        monkeypatch.delenv(name, raising=False)

    report = check_deployment(platform_db=platform_db, environment="production")
    assert not [check for check in report.checks if check.name.startswith("SSO")]
