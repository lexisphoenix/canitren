"""
In-memory cache with TTL.

Simple dict-based cache for the MVP. Swap for Redis later by implementing
the same interface.
"""

from __future__ import annotations

import time
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class MemoryCache:
    """Simple in-memory cache with TTL support."""

    def __init__(self, default_ttl: int = 900):
        self._store: dict[str, tuple[Any, float]] = {}  # key → (value, expires_at)
        self.default_ttl = default_ttl

    def get(self, key: str) -> Optional[Any]:
        """Get a cached value, or None if missing/expired."""
        if key in self._store:
            value, expires_at = self._store[key]
            if time.time() < expires_at:
                logger.debug("Cache HIT: %s", key)
                return value
            else:
                del self._store[key]
                logger.debug("Cache EXPIRED: %s", key)
        return None

    def set(self, key: str, value: Any, ttl: int | None = None):
        """Store a value with optional TTL (seconds)."""
        ttl = ttl or self.default_ttl
        expires_at = time.time() + ttl
        self._store[key] = (value, expires_at)
        logger.debug("Cache SET: %s (TTL=%ds)", key, ttl)

    def delete(self, key: str):
        """Remove a cached value."""
        self._store.pop(key, None)

    def clear(self):
        """Remove all cached values."""
        self._store.clear()

    def make_key(self, origin: str, destination: str, date: str) -> str:
        """Create a cache key for a search query."""
        return f"search:{origin}:{destination}:{date}"


# Global cache instance
cache = MemoryCache()
