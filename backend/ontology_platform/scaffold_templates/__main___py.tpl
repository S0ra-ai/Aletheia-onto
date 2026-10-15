"""命令行入口：先注册本项目扩展，再交给平台 CLI。

包装平台 CLI 而非复制它：`init`／`connect`／`model`／`assess`／`serve`／`preflight`／
`audit`／`export` 全部可用，且随 `aletheia-onto` 升级自动获得新命令。

直接用 `aletheia` 命令则**不会**加载本项目的扩展——那正是这个入口存在的原因。
"""

from __future__ import annotations

import os
import sys

from ontology_platform.cli import main as platform_main

# 平台在提示与错误里用这个名字自称。不声明的话它会说 `aletheia model 1`——
# 而上面刚写清楚：直接用 `aletheia` 不会加载本项目的扩展。
os.environ.setdefault("ONTOLOGY_PROGRAM_NAME", "python -m {{package}}")

from . import setup
from .config import PLATFORM_DB


def main(argv: list[str] | None = None) -> int:
    setup()
    args = list(sys.argv[1:] if argv is None else argv)
    # 默认指向本项目配置的平台库，除非调用方显式覆盖。
    if "--platform-db" not in args:
        args = ["--platform-db", str(PLATFORM_DB), *args]
    return platform_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
