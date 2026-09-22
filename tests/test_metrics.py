"""Tests for the metrics module."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from ontology_platform.metrics import (
    PROM_AVAILABLE,
    increment_decision,
    increment_request,
    increment_rule_evaluation,
    init_metrics,
)


class TestMetrics:
    """Test metric counters."""

    def test_increment_request(self) -> None:
        """Test request counter increment."""
        increment_request("GET", "/health", 200)
        # No exception means success

    def test_increment_decision(self) -> None:
        """Test decision counter increment."""
        increment_decision("contract", "approved")
        # No exception means success

    def test_increment_rule_evaluation(self) -> None:
        """Test rule evaluation counter increment."""
        increment_rule_evaluation("test_rule", True)
        increment_rule_evaluation("test_rule", False)
        # No exception means success


@pytest.mark.skipif(not PROM_AVAILABLE, reason="prometheus-client not installed")
class TestPrometheusMetrics:
    """Test Prometheus integration."""


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """A live app backed by an isolated database, without touching repository data."""
    platform_db = tmp_path / "platform.sqlite3"
    monkeypatch.setenv("ONTOLOGY_ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ONTOLOGY_ADMIN_PASSWORD", "admin-password-123")

    import ontology_platform.api as api_module
    import ontology_platform.database as database_module

    database_module._platform_adapter = None
    monkeypatch.setattr(database_module, "DEFAULT_PLATFORM_DB", platform_db)
    api_module = importlib.reload(api_module)
    monkeypatch.setattr(api_module, "DEFAULT_PLATFORM_DB", platform_db)

    with TestClient(api_module.app) as test_client:
        yield test_client

    database_module._platform_adapter = None


@pytest.mark.skipif(not PROM_AVAILABLE, reason="prometheus-client not installed")
class TestPrometheusEndpoint:
    """The metrics endpoint shares the process-wide registry safely."""

    def test_repeated_initialization_does_not_duplicate_metrics(self) -> None:
        """Embedded hosts and test clients can create several app instances."""
        init_metrics()
        init_metrics()

    def test_metrics_endpoint(self, client: object) -> None:
        """Test metrics endpoint is accessible."""
        from ontology_platform.api import app

        c = TestClient(app)
        r = c.get("/metrics")
        assert r.status_code == 200
        assert b"http_requests_total" in r.content
