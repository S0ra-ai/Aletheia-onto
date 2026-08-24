"""Retrieval and embedding, as replaceable backends.

The default implementations are deliberately dependency-free: BM25 ranking over
term frequencies, and a hashed character-n-gram embedding. Neither is
state-of-the-art. That is an accepted trade, because "clone it and it runs" is a
promise the quick start makes, and requiring pgvector or a model service to see
any citation at all would break it.

Deployments that need better recall register a real backend
(`register_retrieval_backend` / `register_embedding_model`) and no longer touch
the defaults -- see docs/extending.md. Retrieval quality is explicitly *not* a
differentiator for this project (ROADMAP Non-Goals); verifiable citation is.

Tokenization note: Chinese has no word delimiters, so the default tokenizer emits
character bigrams for CJK runs alongside whole ASCII words. Bigrams are a crude
but effective stand-in for segmentation, and they avoid pulling in a segmenter
dependency for the default path.

Stability: experimental (ADR-0007).
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
from dataclasses import dataclass
from typing import Any, Callable, Sequence

from .registry import Registry, load_entry_point_plugins

logger = logging.getLogger(__name__)

_CJK = r"\u4e00-\u9fff"
_WORD_RE = re.compile(rf"[a-zA-Z0-9_]+|[{_CJK}]+")

# BM25 parameters. Defaults from the literature; k1 controls term-frequency
# saturation, b controls length normalisation.
BM25_K1 = 1.5
BM25_B = 0.75

EMBEDDING_DIMENSIONS = 256


def tokenize(text: str) -> list[str]:
    """Split text into comparable terms.

    ASCII words are kept whole and lowercased. CJK runs are emitted as character
    bigrams, plus single characters when a run is one character long, so that
    「退款」 matches a passage containing 「退款条件」.
    """
    tokens: list[str] = []
    for match in _WORD_RE.finditer(text or ""):
        chunk = match.group(0)
        if re.fullmatch(rf"[{_CJK}]+", chunk):
            if len(chunk) == 1:
                tokens.append(chunk)
                continue
            tokens.extend(chunk[i : i + 2] for i in range(len(chunk) - 1))
        else:
            tokens.append(chunk.lower())
    return tokens


@dataclass(frozen=True)
class RetrievalHit:
    """One retrieved knowledge entry with its score and provenance."""

    entry_id: int
    score: float
    citation: str
    content: str
    document_title: str
    object_code: str
    rule_code: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "entryId": self.entry_id,
            "score": round(self.score, 4),
            "citation": self.citation,
            "content": self.content,
            "documentTitle": self.document_title,
            "objectCode": self.object_code,
            "ruleCode": self.rule_code,
        }


def bm25_rank(
    query: str,
    entries: Sequence[dict[str, Any]],
    *,
    limit: int = 3,
    min_score: float = 0.0,
) -> list[RetrievalHit]:
    """Rank pre-narrowed entries by BM25.

    `entries` is already anchor-filtered by the caller; this only orders them.
    Entries carry `tokenSummary` computed at ingest time, so no re-tokenisation
    happens per query.
    """
    query_tokens = tokenize(query)
    if not query_tokens or not entries:
        return []

    summaries: list[dict[str, int]] = []
    for entry in entries:
        summary = entry.get("tokenSummary") or {}
        if not summary:
            # Older rows may predate token_summary; recover rather than skip.
            counts: dict[str, int] = {}
            for token in tokenize(entry.get("content", "")):
                counts[token] = counts.get(token, 0) + 1
            summary = counts
        summaries.append(summary)

    lengths = [sum(summary.values()) or 1 for summary in summaries]
    average_length = sum(lengths) / len(lengths)
    total_docs = len(summaries)

    document_frequency: dict[str, int] = {}
    for token in set(query_tokens):
        document_frequency[token] = sum(1 for summary in summaries if token in summary)

    hits: list[RetrievalHit] = []
    # strict: the three sequences are derived from `entries` one-to-one. If they ever
    # diverge, zipping to the shortest would drop entries from the candidate set
    # without saying so -- a citation missing from an answer is indistinguishable from
    # a citation that did not match.
    for entry, summary, length in zip(entries, summaries, lengths, strict=True):
        score = 0.0
        for token in query_tokens:
            frequency = summary.get(token, 0)
            if not frequency:
                continue
            appearances = document_frequency.get(token, 0) or 1
            # Standard BM25 IDF with the +0.5 smoothing that keeps the value
            # positive when a term appears in every document.
            idf = math.log(1 + (total_docs - appearances + 0.5) / (appearances + 0.5))
            denominator = frequency + BM25_K1 * (1 - BM25_B + BM25_B * length / average_length)
            score += idf * (frequency * (BM25_K1 + 1)) / denominator
        if score > min_score:
            hits.append(
                RetrievalHit(
                    entry_id=int(entry["id"]),
                    score=score,
                    citation=entry.get("citation", ""),
                    content=entry.get("content", ""),
                    document_title=entry.get("documentTitle", ""),
                    object_code=entry.get("objectCode", ""),
                    rule_code=entry.get("ruleCode", ""),
                )
            )
    hits.sort(key=lambda hit: (-hit.score, hit.entry_id))
    return hits[: max(1, limit)]


def hashed_embedding(text: str, dimensions: int = EMBEDDING_DIMENSIONS) -> list[float]:
    """Deterministic bag-of-n-grams embedding, no model service required.

    Used by the default retrieval path only as a similarity fallback; the primary
    ranking is BM25. Deterministic so the same text always yields the same vector,
    which keeps tests and screenshots reproducible.
    """
    vector = [0.0] * dimensions
    for token in tokenize(text):
        # Python's hash() is salted per process, so derive a stable bucket from a
        # digest of the whole token. Truncating the raw UTF-8 bytes instead would
        # collide badly for CJK, where the first bytes of different characters
        # frequently coincide.
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(digest, "big") % dimensions
        vector[bucket] += 1.0
    norm = math.sqrt(sum(value * value for value in vector))
    if norm:
        vector = [value / norm for value in vector]
    return vector


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    # Lengths are already checked above, where mismatch returns 0.0 rather than raising:
    # two embeddings of different width mean the vectors came from different models, and
    # a similarity search must degrade to "no match" instead of failing the whole answer.
    return sum(a * b for a, b in zip(left, right, strict=True))


# -- Extension points --

RetrievalBackend = Callable[[str, Sequence[dict[str, Any]], int], list[RetrievalHit]]
EmbeddingModel = Callable[[str], list[float]]

RETRIEVAL_REGISTRY: Registry[RetrievalBackend] = Registry("检索后端")
EMBEDDING_REGISTRY: Registry[EmbeddingModel] = Registry("嵌入模型")

RETRIEVAL_ENTRY_POINT_GROUP = "aletheia.retrieval_backends"
EMBEDDING_ENTRY_POINT_GROUP = "aletheia.embedding_models"

DEFAULT_BACKEND = "bm25"
DEFAULT_EMBEDDING = "hashed-ngram"


def register_retrieval_backend(name: str, backend: RetrievalBackend, *, replace: bool = False) -> RetrievalBackend:
    """Register a ranking backend.

    The backend receives the *already anchor-filtered* candidate entries, which is
    what keeps citations attributable: a backend cannot widen the candidate set
    beyond what the ontology anchors permit.

    >>> register_retrieval_backend("pgvector", rank_with_pgvector)  # doctest: +SKIP
    """
    RETRIEVAL_REGISTRY.register(name, backend, replace=replace)
    return backend


def register_embedding_model(name: str, model: EmbeddingModel, *, replace: bool = False) -> EmbeddingModel:
    """Register an embedding function used for similarity scoring."""
    EMBEDDING_REGISTRY.register(name, model, replace=replace)
    return model


def get_retrieval_backend(name: str = "") -> RetrievalBackend:
    return RETRIEVAL_REGISTRY.get(name or DEFAULT_BACKEND)


def get_embedding_model(name: str = "") -> EmbeddingModel:
    return EMBEDDING_REGISTRY.get(name or DEFAULT_EMBEDDING)


def supported_retrieval_backends() -> tuple[str, ...]:
    return RETRIEVAL_REGISTRY.names()


def supported_embedding_models() -> tuple[str, ...]:
    return EMBEDDING_REGISTRY.names()


def load_retrieval_plugins() -> list[str]:
    return load_entry_point_plugins(
        RETRIEVAL_ENTRY_POINT_GROUP,
        lambda name, backend: RETRIEVAL_REGISTRY.register(name, backend),
    )


def load_embedding_plugins() -> list[str]:
    return load_entry_point_plugins(
        EMBEDDING_ENTRY_POINT_GROUP,
        lambda name, model: EMBEDDING_REGISTRY.register(name, model),
    )


def _bm25_backend(query: str, entries: Sequence[dict[str, Any]], limit: int) -> list[RetrievalHit]:
    return bm25_rank(query, entries, limit=limit)


def _embedding_backend(query: str, entries: Sequence[dict[str, Any]], limit: int) -> list[RetrievalHit]:
    """Cosine similarity over the registered embedding model."""
    model = get_embedding_model()
    query_vector = model(query)
    hits = []
    for entry in entries:
        score = cosine_similarity(query_vector, model(entry.get("content", "")))
        if score > 0:
            hits.append(
                RetrievalHit(
                    entry_id=int(entry["id"]),
                    score=score,
                    citation=entry.get("citation", ""),
                    content=entry.get("content", ""),
                    document_title=entry.get("documentTitle", ""),
                    object_code=entry.get("objectCode", ""),
                    rule_code=entry.get("ruleCode", ""),
                )
            )
    hits.sort(key=lambda hit: (-hit.score, hit.entry_id))
    return hits[: max(1, limit)]


def retrieve(
    query: str,
    entries: Sequence[dict[str, Any]],
    *,
    limit: int = 3,
    backend: str = "",
) -> list[RetrievalHit]:
    """Rank anchor-filtered candidates using the selected backend."""
    return get_retrieval_backend(backend)(query, entries, limit)


def filter_entries_for_role(
    platform_db: Any,
    entries: Sequence[dict[str, Any]],
    *,
    role_code: str,
    ontology_id: int,
) -> list[dict[str, Any]]:
    """Drop entries whose anchor object the role may not read.

    Anchoring makes a citation *attributable*; it does not make it *permitted*. An entry
    anchored to an object the caller cannot read is still an object they cannot read, and
    surfacing its text in an answer discloses exactly what the object permission was
    protecting. Retrieval-time filtering is the last place to stop that -- once the text is
    in the answer, it has been disclosed.

    Applied here rather than in `load_confirmed_entries` because storage should not need to
    know the permission model; that coupling is what makes a policy change require a
    schema change.

    Fails closed: an entry whose permission cannot be evaluated is dropped. Losing a
    citation degrades an answer, whereas including one leaks a document -- the two failures
    are not symmetric (ADR-0002).
    """
    if not role_code:
        # No identity means no basis for disclosure. Callers that legitimately have no role
        # -- an internal maintenance task -- pass the entries straight to `retrieve`.
        logger.warning("检索期未提供角色，按 fail-closed 丢弃全部候选条目")
        return []

    from .workflow_permission import check_permission

    permitted: list[dict[str, Any]] = []
    # One decision per distinct anchor rather than per entry: a document can contribute
    # dozens of chunks, and re-deciding for each would multiply the policy reads.
    verdicts: dict[str, bool] = {}
    for entry in entries:
        anchor = str(entry.get("objectCode") or "")
        if not anchor:
            # An entry with no object anchor is ontology-level text. It is reachable by
            # anyone who can read the ontology, which they demonstrably can -- they got a
            # verdict for it.
            permitted.append(entry)
            continue
        if anchor not in verdicts:
            try:
                decision = check_permission(platform_db, role_code, anchor, "read", ontology_id=ontology_id)
                verdicts[anchor] = bool(decision.get("allowed"))
            except Exception as error:
                logger.warning("检索期权限判定失败，按拒绝处理 (%s): %s", anchor, error)
                verdicts[anchor] = False
        if verdicts[anchor]:
            permitted.append(entry)
    dropped = len(entries) - len(permitted)
    if dropped:
        logger.info("检索期权限过滤丢弃了 %s 条候选条目", dropped)
    return permitted


# Built-in implementations, registered at import so the defaults always exist.
register_retrieval_backend(DEFAULT_BACKEND, _bm25_backend)
register_retrieval_backend("embedding", _embedding_backend)
register_embedding_model(DEFAULT_EMBEDDING, hashed_embedding)

load_retrieval_plugins()
load_embedding_plugins()
