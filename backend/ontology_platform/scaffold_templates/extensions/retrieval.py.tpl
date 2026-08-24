"""检索后端。

替换默认 BM25（如 pgvector、Milvus）。

**必须确定**：同一问题两次返回不同引用，结论就不可复现。

候选集已由平台按本体与锚点收窄，且**已按调用者的对象权限过滤**——
不要重新去全库检索，那会绕过权限过滤，让答案里出现调用方不该看到的原文。
"""

from __future__ import annotations

from typing import Any, Sequence

from ontology_platform.retrieval import RetrievalHit, register_retrieval_backend

__all__ = ["register"]


def example_backend(question: str, entries: Sequence[dict[str, Any]], limit: int) -> list[RetrievalHit]:
    """示例检索后端。替换为真实实现，或删掉本文件。"""
    raise NotImplementedError("实现检索：对已过滤的候选集打分并返回 RetrievalHit 列表")


def register() -> None:
    register_retrieval_backend("example", example_backend)
