"""规则函数。

让规则表达式能调用领域谓词。注册只授予「表达式可以调用它」，
**不放宽沙箱的 AST 白名单**。
"""

from __future__ import annotations

from ontology_platform.rule_sandbox import register_rule_function

__all__ = ["register"]


def is_overdue(days: object) -> bool:
    """示例谓词：账期是否已逾期。替换为真实实现，或删掉本文件。

    规则函数必须是**纯函数且确定**：读数据库或读时钟的函数会让同一实例在两次
    判定中得到不同结论，而判定可复现是本平台的产品本身。

    无法求值时**让它抛出**，不要猜一个值：规则引擎 fail-closed，
    平台会把求值失败判为未通过并说明原因。在此返回 False 会把
    「算不出来」伪装成「不逾期」。
    """
    return int(days) > 0  # type: ignore[arg-type]


def register() -> None:
    register_rule_function("is_overdue", is_overdue)
