[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "{{dist}}"
version = "0.1.0"
description = "基于 Aletheia 的业务语义内核部署"
requires-python = ">=3.11"

# 固定而非区间。规则引擎依赖的一次传递升级可以改变判定结论，
# 而判定是本平台要负责的东西。
dependencies = [
    "aletheia-onto[web]=={{version}}",
]

[project.scripts]
{{dist}} = "{{package}}.__main__:main"

[tool.setuptools.packages.find]
include = ["{{package}}*"]
