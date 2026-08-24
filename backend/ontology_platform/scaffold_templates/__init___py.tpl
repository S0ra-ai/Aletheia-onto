"""{{package}}: 基于 Aletheia 的业务语义内核部署。

本包只调用 `aletheia-onto` 的公开入口，不复制平台代码——升级即
`pip install -U aletheia-onto`，本包无需改动。
"""

from __future__ import annotations

__all__ = ["setup"]


def setup() -> None:
    """注册本项目的扩展。在使用平台任何功能之前调用一次。

    显式调用而非 import 期副作用：import 期注册会让「导入这个包」与「改变平台行为」
    成为同一件事，于是一次为了读常量的导入也会静默改变判定结果。
    """
{{registration}}
