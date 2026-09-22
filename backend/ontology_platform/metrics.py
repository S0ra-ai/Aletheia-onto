"""Prometheus metrics for the ontology platform.

Provides HTTP request counters, decision tracking, and performance metrics
that can be scraped by Prometheus for monitoring and alerting.
"""

from __future__ import annotations

import logging

try:
    from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest

    PROM_AVAILABLE = True
except ImportError:
    PROM_AVAILABLE = False

logger = logging.getLogger(__name__)

# Metrics registry
_registry: CollectorRegistry | None = None

# Request metrics
_request_counter: Counter | None = None
_request_duration: Histogram | None = None

# Business metrics
_decision_counter: Counter | None = None
_rule_evaluation_counter: Counter | None = None

# System metrics
_active_sessions: Gauge | None = None


def get_registry() -> CollectorRegistry:
    """Get or create the Prometheus metrics registry."""
    global _registry
    if _registry is None:
        _registry = CollectorRegistry()
    return _registry


def init_metrics() -> None:
    """Initialize all Prometheus metrics."""
    global _request_counter, _request_duration, _decision_counter
    global _rule_evaluation_counter, _active_sessions

    if not PROM_AVAILABLE:
        logger.warning("Prometheus client not installed, metrics disabled")
        return

    # ASGI applications can be created repeatedly in embedded deployments and tests.
    # Metrics are process-wide and already live in the process registry, so a second
    # application instance must reuse them instead of attempting duplicate registration.
    if _request_counter is not None and _request_duration is not None:
        return

    registry = get_registry()

    _request_counter = Counter(
        "http_requests_total",
        "Total HTTP requests",
        ["method", "endpoint", "status"],
        registry=registry,
    )

    _request_duration = Histogram(
        "http_request_duration_seconds",
        "HTTP request duration in seconds",
        ["method", "endpoint"],
        registry=registry,
    )

    _decision_counter = Counter(
        "decisions_total",
        "Total decisions made",
        ["object_code", "decision"],
        registry=registry,
    )

    _rule_evaluation_counter = Counter(
        "rule_evaluations_total",
        "Total rule evaluations",
        ["rule_code", "result"],
        registry=registry,
    )

    _active_sessions = Gauge(
        "active_sessions",
        "Number of active user sessions",
        registry=registry,
    )

    logger.info("Prometheus metrics initialized")


def expose_metrics() -> bytes:
    """Expose metrics in Prometheus text format."""
    if not PROM_AVAILABLE or _registry is None:
        return b""
    return generate_latest(_registry)


def increment_request(method: str, endpoint: str, status: int) -> None:
    """Increment request counter."""
    if _request_counter is not None:
        _request_counter.labels(method=method, endpoint=endpoint, status=str(status)).inc()


def observe_request_duration(method: str, endpoint: str, duration: float) -> None:
    """Record request duration."""
    if _request_duration is not None:
        _request_duration.labels(method=method, endpoint=endpoint).observe(duration)


def increment_decision(object_code: str, decision: str) -> None:
    """Increment decision counter."""
    if _decision_counter is not None:
        _decision_counter.labels(object_code=object_code, decision=decision).inc()


def increment_rule_evaluation(rule_code: str, passed: bool) -> None:
    """Increment rule evaluation counter."""
    if _rule_evaluation_counter is not None:
        result = "passed" if passed else "failed"
        _rule_evaluation_counter.labels(rule_code=rule_code, result=result).inc()
