"""嵌入模型。

替换默认哈希 n-gram。

**必须确定且同维**：随机或变长的向量会让相似度失去意义，
而同一问题两次引用不同文档意味着判定不可复现。
"""

from __future__ import annotations

from ontology_platform.retrieval import register_embedding_model

__all__ = ["register"]


def example_embedding(text: str) -> list[float]:
    """示例嵌入模型。替换为真实实现，或删掉本文件。"""
    raise NotImplementedError("实现嵌入：对同一文本必须返回同一定长向量")


def register() -> None:
    register_embedding_model("example", example_embedding)
