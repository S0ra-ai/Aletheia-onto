"""Tests for the rate limiter module."""

from __future__ import annotations

from ontology_platform.rate_limiter import RateLimiter


class TestRateLimiter:
    """Test rate limiting functionality."""

    def test_allows_within_limit(self) -> None:
        """Test requests within limit are allowed."""
        limiter = RateLimiter(max_requests=5, window_seconds=60)

        for i in range(5):
            assert limiter.is_allowed(f"test_{i}") is True

    def test_blocks_over_limit(self) -> None:
        """Test requests over limit are blocked."""
        limiter = RateLimiter(max_requests=3, window_seconds=60)

        assert limiter.is_allowed("test") is True
        assert limiter.is_allowed("test") is True
        assert limiter.is_allowed("test") is True
        assert limiter.is_allowed("test") is False

    def test_remaining_count(self) -> None:
        """Test remaining requests count."""
        limiter = RateLimiter(max_requests=10, window_seconds=60)

        limiter.is_allowed("test")
        limiter.is_allowed("test")

        assert limiter.get_remaining("test") == 8
