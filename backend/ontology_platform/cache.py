"""Simple in-memory cache for API responses.

Provides caching for frequently accessed data to reduce database load.
"""

from __future__ import annotations

import logging
import time
from collections import OrderedDict
from typing import Any, Optional

logger = logging.getLogger(__name__)


class SimpleCache:
    """Thread-safe LRU cache with TTL support."""

    def __init__(self, max_size: int = 1000, default_ttl: float = 300.0):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._cache: OrderedDict[str, tuple[float, Any]] = OrderedDict()

    def get(self, key: str) -> Optional[Any]:
        """Get a value from cache."""
        if key in self._cache:
            timestamp, value = self._cache[key]
            if time.time() - timestamp < self.default_ttl:
                # Move to end (most recently used)
                self._cache.move_to_end(key)
                return value
            else:
                del self._cache[key]
        return None

    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        """Set a value in cache."""
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = (time.time(), value)

        # Evict oldest if over capacity
        while len(self._cache) > self.max_size:
            self._cache.popitem(last=False)

    def delete(self, key: str) -> None:
        """Delete a value from cache."""
        self._cache.pop(key, None)

    def clear(self) -> None:
        """Clear all cached values."""
        self._cache.clear()

    def stats(self) -> dict[str, int]:
        """Get cache statistics."""
        return {
            "size": len(self._cache),
            "max_size": self.max_size,
        }


# Global cache instances
_ontology_cache = SimpleCache(max_size=500, default_ttl=60.0)
_rule_cache = SimpleCache(max_size=200, default_ttl=120.0)
_workbench_cache = SimpleCache(max_size=100, default_ttl=30.0)


def get_ontology_cache() -> SimpleCache:
    return _ontology_cache


def get_rule_cache() -> SimpleCache:
    return _rule_cache


def get_workbench_cache() -> SimpleCache:
    return _workbench_cache
