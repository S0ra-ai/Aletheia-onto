"""数据源适配器。

接入平台尚无内置声明的库。**先确认是否真的需要它**：多数 SQL 库只需在
`sql_dialects` 里声明 4 行方言（见扩展指南「接一个新的 SQL 数据库」），
通用 DB-API 适配器会处理其余部分。只有协议不是 DB-API 时才需要写适配器。

用 `python verify.py` 跑一致性契约——它随包发布，不需要 clone 平台仓库。
"""

from __future__ import annotations

from typing import Any

from ontology_platform.adapters import register_adapter

__all__ = ["register"]


class ExampleAdapter:
    """占位适配器。替换为真实实现，或删掉本文件。"""

    def test_connection(self, connection_uri: str) -> dict[str, Any]:
        raise NotImplementedError("实现连通性探测：返回 sourceType/reachable/status/message")

    def scan(self, connection_uri: str) -> list[Any]:
        raise NotImplementedError("实现元数据扫描：返回 SourceTableInfo 列表（表、列、外键）")

    def runtime(self, connection_uri: str) -> Any:
        raise NotImplementedError("返回上下文管理器，yield 一个 RuntimeDatabase")


def register() -> None:
    # 传入工厂而非实例：适配器构造开销很小，每次调用视为独立对象。
    register_adapter("example", ExampleAdapter)
