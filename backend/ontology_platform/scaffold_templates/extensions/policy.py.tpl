"""路由权限策略。

为本项目新增的端点声明所需能力。

**必须声明**：未登记的路由落到「仅管理员」兜底。那样失败是安全的，
但会把功能锁死在管理员手里，而缺失的条目对所有会发现它的人都不可见。
"""

from __future__ import annotations

from ontology_platform.access_policy import CAP_READ, register_route_policy

__all__ = ["register"]


def register() -> None:
    register_route_policy(["GET"], r"/example/.*", CAP_READ, "示例只读端点")
