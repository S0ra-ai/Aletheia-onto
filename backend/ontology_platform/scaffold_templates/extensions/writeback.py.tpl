"""写回执行器。

把判定结果写回传统系统。按 scheme 分发。

三条安全约束由平台强制，不要绕过：语句需声明、值必须绑定、
无 WHERE 的 UPDATE／DELETE 会被拒绝。**影响 0 行按失败处理**——
「写了但没命中」与「写成功」在审计上是完全不同的事。
"""

from __future__ import annotations

from typing import Any

from ontology_platform.automation import register_executor

__all__ = ["register"]


def example_executor(request: Any) -> dict[str, Any]:
    """示例写回执行器。替换为真实实现，或删掉本文件。"""
    raise NotImplementedError("实现写回：返回 {'success', 'affected', 'detail'}")


def register() -> None:
    register_executor("example", example_executor)
