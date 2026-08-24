"""本项目注册的扩展点。

逐个列出而非扫描目录：扫描会让「哪些扩展生效」取决于哪些文件恰好可导入，
而一个静默没注册上的扩展表现为平台缺少某个能力，很难定位。
"""

from __future__ import annotations

{{imports}}

__all__ = ["register_all"]


def register_all() -> None:
{{calls}}
