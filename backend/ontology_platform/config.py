"""Platform tunables.

Values that were previously scattered as literals across modules live here so
they can be reviewed in one place and overridden per deployment. Nothing in
this module encodes business-domain vocabulary; domain terms are resolved from
the ontology at runtime (see `vocabulary.py`).
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _float_env(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _str_env(name: str, default: str) -> str:
    return os.environ.get(name, "").strip() or default


@dataclass(frozen=True)
class MappingConfidence:
    """Confidence attached to generated semantic mapping candidates.

    These are heuristic priors, not measurements: a blueprint hit is stronger
    evidence than a name-shape guess. They are surfaced as configuration
    because the right values depend on how curated the blueprints are.
    """

    blueprint_match: float = _float_env("ONTOLOGY_CONFIDENCE_BLUEPRINT", 0.92)
    structural_match: float = _float_env("ONTOLOGY_CONFIDENCE_STRUCTURAL", 0.85)
    lexicon_match: float = _float_env("ONTOLOGY_CONFIDENCE_LEXICON", 0.90)
    weak_match: float = _float_env("ONTOLOGY_CONFIDENCE_WEAK", 0.70)


@dataclass(frozen=True)
class QueryLimits:
    """Upper bounds for row and instance reads."""

    default_page_size: int = _int_env("ONTOLOGY_DEFAULT_PAGE_SIZE", 50)
    max_page_size: int = _int_env("ONTOLOGY_MAX_PAGE_SIZE", 200)
    max_consistency_sample: int = _int_env("ONTOLOGY_MAX_CONSISTENCY_SAMPLE", 200)
    enum_max_distinct: int = _int_env("ONTOLOGY_ENUM_MAX_DISTINCT", 20)
    enum_min_distinct: int = _int_env("ONTOLOGY_ENUM_MIN_DISTINCT", 3)


@dataclass(frozen=True)
class AnswerConfidence:
    """Confidence reported for locally generated (non-model) answers."""

    grounded: float = _float_env("ONTOLOGY_ANSWER_CONFIDENCE_GROUNDED", 0.85)
    ungrounded: float = _float_env("ONTOLOGY_ANSWER_CONFIDENCE_UNGROUNDED", 0.30)
    neutral: float = _float_env("ONTOLOGY_ANSWER_CONFIDENCE_NEUTRAL", 0.50)


@dataclass(frozen=True)
class ResolutionConfidence:
    """How confident the router is that it understood a question.

    Confidence accumulates as more of the target is pinned down: knowing the
    object, the instance and the ontology version each add evidence.
    """

    unknown_intent: float = _float_env("ONTOLOGY_RESOLUTION_UNKNOWN", 0.20)
    base: float = _float_env("ONTOLOGY_RESOLUTION_BASE", 0.62)
    object_bonus: float = _float_env("ONTOLOGY_RESOLUTION_OBJECT_BONUS", 0.12)
    instance_bonus: float = _float_env("ONTOLOGY_RESOLUTION_INSTANCE_BONUS", 0.14)
    ontology_bonus: float = _float_env("ONTOLOGY_RESOLUTION_ONTOLOGY_BONUS", 0.08)
    ceiling: float = _float_env("ONTOLOGY_RESOLUTION_CEILING", 0.96)


@dataclass(frozen=True)
class SemanticAssetNaming:
    """Base IRIs for exported semantic assets.

    Deployments publishing ontologies externally must set their own namespace;
    the default is a clearly non-routable placeholder.
    """

    vocabulary_base: str = _str_env(
        "ONTOLOGY_VOCABULARY_BASE_IRI", "https://ontology-platform.local/vocab#"
    )
    ontology_base: str = _str_env(
        "ONTOLOGY_ASSET_BASE_IRI", "https://ontology-platform.local/ontology"
    )


@dataclass(frozen=True)
class ModelProviderDefaults:
    """Defaults for the OpenAI-compatible model provider.

    A vendor endpoint, not a business assumption: overridable by environment
    variable and by the persisted model configuration.
    """

    base_url: str = _str_env("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    model: str = _str_env("OPENROUTER_MODEL", "~openai/gpt-latest")
    app_title: str = _str_env("OPENROUTER_APP_TITLE", "Ontology Transformation Platform")
    service_tier: str = _str_env("OPENROUTER_SERVICE_TIER", "auto")
    timeout_seconds: float = _float_env("OPENROUTER_TIMEOUT_SECONDS", 30)


MAPPING_CONFIDENCE = MappingConfidence()
QUERY_LIMITS = QueryLimits()
ANSWER_CONFIDENCE = AnswerConfidence()
RESOLUTION_CONFIDENCE = ResolutionConfidence()
SEMANTIC_ASSET_NAMING = SemanticAssetNaming()
MODEL_PROVIDER_DEFAULTS = ModelProviderDefaults()


def clamp_page_size(value: int | None) -> int:
    """Clamp a caller supplied page size into the configured range."""
    if value is None:
        return QUERY_LIMITS.default_page_size
    try:
        resolved = int(value)
    except (TypeError, ValueError):
        return QUERY_LIMITS.default_page_size
    return max(1, min(resolved, QUERY_LIMITS.max_page_size))


def clamp_sample_size(value: int | None) -> int:
    """Clamp a consistency-assessment sample size."""
    if value is None:
        return QUERY_LIMITS.default_page_size
    try:
        resolved = int(value)
    except (TypeError, ValueError):
        return QUERY_LIMITS.default_page_size
    return max(1, min(resolved, QUERY_LIMITS.max_consistency_sample))
