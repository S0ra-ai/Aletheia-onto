"""Route to capability policy.

Authorization lives in one table instead of being spread across 80+ endpoint
signatures, so the effective policy can be reviewed and tested as data. The
matcher is deny-by-default: an unlisted route requires admin, which means a new
endpoint cannot accidentally ship unprotected.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from .auth import (
    ALL_CAPABILITIES,
    CAP_ADMIN,
    CAP_EXECUTE,
    CAP_PUBLISH,
    CAP_READ,
    CAP_REVIEW,
    CAP_WRITE,
)
from .registry import load_entry_point_plugins


@dataclass(frozen=True)
class Rule:
    methods: frozenset[str]
    pattern: re.Pattern[str]
    capability: str
    description: str


def _rule(methods: Iterable[str], path_regex: str, capability: str, description: str) -> Rule:
    return Rule(
        methods=frozenset(method.upper() for method in methods),
        pattern=re.compile(f"^{path_regex}$"),
        capability=capability,
        description=description,
    )


# Endpoints reachable without a token.
PUBLIC_PATHS: frozenset[str] = frozenset(
    {
        "/health",
        "/auth/login",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/docs/oauth2-redirect",
    }
)

ANY_METHOD = ("GET", "POST", "PUT", "PATCH", "DELETE")

# Order matters: the first match wins, so specific rules precede generic ones.
RULES: tuple[Rule, ...] = (
    # -- Session --
    _rule(("POST",), r"/auth/logout", CAP_READ, "退出登录"),
    _rule(("GET",), r"/auth/me", CAP_READ, "查看当前身份"),
    _rule(("POST",), r"/auth/change-password", CAP_READ, "修改自己的密码"),
    # -- User administration --
    _rule(ANY_METHOD, r"/auth/users.*", CAP_ADMIN, "用户管理"),
    # -- Governance: review and publish are distinct capabilities --
    _rule(("POST",), r"/semantic-mappings/\d+/review", CAP_REVIEW, "审核语义映射"),
    _rule(("POST",), r"/ontologies/\d+/mappings/review", CAP_REVIEW, "批量审核语义映射"),
    _rule(("POST",), r"/ontologies/\d+/publish", CAP_PUBLISH, "发布本体版本"),
    _rule(("POST",), r"/ontologies/\d+/derive", CAP_PUBLISH, "派生本体版本"),
    _rule(("POST",), r"/tools/logs/\d+/review", CAP_REVIEW, "审核工具执行"),
    # -- Automation against legacy systems --
    _rule(("POST",), r"/automation/operations/[^/]+/preflight", CAP_READ, "操作语义预检"),
    _rule(("POST",), r"/automation/operations/[^/]+/execute", CAP_EXECUTE, "执行传统系统操作"),
    _rule(("POST",), r"/workflows/\d+/transitions/run", CAP_EXECUTE, "驱动工作流流转"),
    # -- Platform configuration --
    _rule(("POST", "DELETE"), r"/model/config", CAP_ADMIN, "模型层配置"),
    _rule(("GET",), r"/model/config(/test)?", CAP_ADMIN, "查看模型层配置"),
    _rule(ANY_METHOD, r"/permissions/roles.*", CAP_ADMIN, "角色管理"),
    _rule(("POST",), r"/permissions/policies", CAP_ADMIN, "权限策略管理"),
    _rule(("POST",), r"/tools", CAP_ADMIN, "注册智能体工具"),
    _rule(("POST",), r"/tools/authorize", CAP_ADMIN, "授权智能体工具"),
    _rule(("POST",), r"/demo/bootstrap.*", CAP_ADMIN, "初始化演示数据"),
    # -- Read-only assessment endpoints that use POST --
    _rule(("POST",), r"/semantic/objects/[^/]+/instances/[^/]+/assess", CAP_READ, "实例语义研判"),
    _rule(("POST",), r"/semantic/objects/[^/]+/consistency", CAP_READ, "批量一致性评估"),
    _rule(("POST",), r"/semantic/natural-language/query", CAP_READ, "自然语言问答"),
    _rule(("POST",), r"/agent/chat", CAP_READ, "智能体对话"),
    _rule(("POST",), r"/data-sources/(\d+/)?test-connection", CAP_READ, "测试数据源连接"),
    _rule(("POST",), r"/data-sources/\d+/test-api-gateway", CAP_READ, "测试业务网关"),
    _rule(("POST",), r"/permissions/check", CAP_READ, "权限自查"),
    _rule(("POST",), r"/tools/check-auth", CAP_READ, "工具授权自查"),
    _rule(("POST",), r"/ontologies/\d+/rules/validate-expression", CAP_READ, "校验规则表达式"),
    # -- Agent role administration --
    _rule(("POST", "DELETE"), r"/agent/roles(/.*)?", CAP_ADMIN, "自定义智能体角色"),
    # -- Modelling and metadata writes --
    _rule(("POST",), r"/ai/.*", CAP_WRITE, "AI 建模建议"),
    _rule(("POST", "PUT", "PATCH", "DELETE"), r"/data-sources.*", CAP_WRITE, "数据源与元数据写入"),
    _rule(("POST", "PUT", "PATCH", "DELETE"), r"/onboarding/.*", CAP_WRITE, "接入流水线"),
    _rule(("POST", "PUT", "PATCH", "DELETE"), r"/ontologies.*", CAP_WRITE, "本体与规则写入"),
    _rule(("POST", "PUT", "PATCH", "DELETE"), r"/industry-blueprints.*", CAP_WRITE, "行业蓝图写入"),
    _rule(("POST", "PUT", "PATCH", "DELETE"), r"/workflows.*", CAP_WRITE, "工作流定义写入"),
    # -- Everything readable --
    # Knowledge documents: ingesting is authoring (write), while confirming an
    # entry as judgement evidence is a governance review.
    _rule(("POST",), r"/ontologies/[0-9]+/knowledge/documents", CAP_WRITE, "上传知识文档"),
    _rule(("POST",), r"/knowledge/entries/[0-9]+/review", CAP_REVIEW, "审核知识条目"),
    # Submitting feedback is something any authenticated reader can do -- the
    # point of a feedback loop is that the person who saw the answer can report
    # it. Resolving feedback and escalating are governance actions.
    _rule(("POST",), r"/conversations/messages/[0-9]+/feedback", CAP_READ, "提交答案反馈"),
    _rule(("POST",), r"/conversations/[^/]+/escalate", CAP_REVIEW, "转人工"),
    _rule(("PATCH",), r"/conversations/[^/]+/status", CAP_REVIEW, "变更会话状态"),
    _rule(("POST",), r"/feedback/[0-9]+/resolve", CAP_REVIEW, "处理反馈"),
    # Provisioning a tenant creates schemas and tables, which is strictly an
    # administrative act.
    _rule(("POST",), r"/tenants", CAP_ADMIN, "开通租户"),
    # Changing how an object resolves its instances alters what every rule for
    # that object evaluates against, so it is a modelling write.
    _rule(("PUT",), r"/ontologies/[0-9]+/objects/[^/]+/resolver", CAP_WRITE, "配置实例解析器"),
    # An aggregate becomes part of what every rule for that object evaluates
    # against, so declaring one is a modelling write.
    _rule(("PUT",), r"/ontologies/[0-9]+/objects/[^/]+/aggregates", CAP_WRITE, "定义跨对象聚合"),
    # A derived attribute or a declared unit changes what every rule reading that
    # name evaluates against -- a unit change silently rescales a threshold -- so
    # both are modelling writes.
    _rule(("PUT",), r"/ontologies/[0-9]+/objects/[^/]+/derived-attributes", CAP_WRITE, "定义派生属性"),
    _rule(("PUT",), r"/ontologies/[0-9]+/objects/[^/]+/attributes/[^/]+/unit", CAP_WRITE, "声明属性单位"),
    _rule(("GET",), r"/.*", CAP_READ, "平台读取"),
)


# Rules contributed by plugins. Checked *before* the built-in table so an
# extension can protect its own routes; it cannot loosen a built-in rule,
# because anything it does not match still falls through to RULES and then to
# the admin default.
#
# Experimental: this signature may change before 1.0 (ADR-0007).
_PLUGIN_RULES: list[Rule] = []

POLICY_ENTRY_POINT_GROUP = "aletheia.access_policies"


def register_route_policy(
    methods: Iterable[str],
    path_regex: str,
    capability: str,
    description: str = "",
) -> Rule:
    """Declare the capability required by a plugin's routes.

    Plugins that add endpoints must register a policy, otherwise their routes
    inherit the admin-only default and appear broken to non-admin users.

    >>> register_route_policy(["GET"], r"/oracle/tables.*", CAP_READ, "Oracle 表浏览")  # doctest: +SKIP

    Registering a policy for a path already covered by a plugin rule replaces
    that rule, so re-importing a plugin is idempotent.
    """
    if capability not in ALL_CAPABILITIES:
        raise ValueError(f"未知能力: {capability}。可用: {'、'.join(sorted(ALL_CAPABILITIES))}")
    rule = _rule(methods, path_regex, capability, description)
    for index, existing in enumerate(_PLUGIN_RULES):
        if existing.pattern.pattern == rule.pattern.pattern and existing.methods == rule.methods:
            _PLUGIN_RULES[index] = rule
            return rule
    _PLUGIN_RULES.append(rule)
    return rule


def clear_route_policies() -> None:
    """Drop all plugin-registered rules. Intended for tests."""
    _PLUGIN_RULES.clear()


def load_policy_plugins() -> list[str]:
    """Let installed packages contribute route policies via entry points."""

    def _register(name: str, factory: Any) -> None:
        for spec in factory() or ():
            register_route_policy(*spec)

    return load_entry_point_plugins(POLICY_ENTRY_POINT_GROUP, _register)


def required_capability(method: str, path: str) -> str:
    """Return the capability needed for a request, defaulting to admin."""
    normalized_method = method.upper()
    normalized_path = path.rstrip("/") or "/"
    for rule in (*_PLUGIN_RULES, *RULES):
        if normalized_method in rule.methods and rule.pattern.match(normalized_path):
            return rule.capability
    return CAP_ADMIN


def is_public(path: str) -> bool:
    normalized = path.rstrip("/") or "/"
    return normalized in PUBLIC_PATHS or normalized.startswith("/docs")


def describe_policy() -> list[dict[str, str]]:
    """Expose the effective policy for review."""
    return [
        {
            "methods": ",".join(sorted(rule.methods)),
            "pattern": rule.pattern.pattern,
            "capability": rule.capability,
            "description": rule.description,
            "source": "plugin" if rule in _PLUGIN_RULES else "builtin",
        }
        for rule in (*_PLUGIN_RULES, *RULES)
    ]
