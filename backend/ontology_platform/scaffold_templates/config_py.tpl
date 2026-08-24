"""本项目的配置。取自环境变量，带可安全提交的默认值。

凭据一律不写入本文件：连接串带口令，而提交进版本库的口令等于每份克隆里的口令。
连接串放 `.env`（已在 .gitignore 中），本文件只读它。
"""

from __future__ import annotations

import os
from pathlib import Path

# 平台库位置。解析为绝对路径：相对路径会让同一条命令在不同工作目录下找到不同的库，
# 而这种失败是静默的。
PLATFORM_DB = Path(
    os.environ.get("{{UPPER}}_PLATFORM_DB") or Path.home() / ".{{package}}" / "platform.sqlite3"
).expanduser()

# 要接入的传统业务系统。留空表示「先用 CLI 手工接一个」。
#
# 每项为 (名称, 类型, 连接串环境变量名, 业务域)。存**环境变量名**而非连接串本身——
# 这样本文件可以提交，而凭据不会。
DATA_SOURCES: tuple[tuple[str, str, str, str], ...] = (
    # ("合同系统", "postgresql", "{{UPPER}}_CONTRACT_URI", "{{domain}}"),
)


def resolved_sources() -> list[dict[str, str]]:
    """已配置且凭据存在的数据源。

    缺失环境变量的项被跳过而非报错：本地开发通常只接其中一两个，
    而「少接一个源」应该表现为少一个源，不是启动失败。
    """
    resolved = []
    for name, source_type, env_name, domain in DATA_SOURCES:
        uri = os.environ.get(env_name, "").strip()
        if uri:
            resolved.append(
                {"name": name, "sourceType": source_type, "connectionUri": uri, "domain": domain}
            )
    return resolved
