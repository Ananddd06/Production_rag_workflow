"""
LRU Cache Manager with TTL expiration for the RAG pipeline.

Provides thread-safe caching with hit/miss tracking for monitoring.
"""

import threading
import time
from collections import OrderedDict
from typing import Any, Optional


class CacheManager:
    """Thread-safe LRU cache with TTL expiration and usage statistics."""

    def __init__(self, max_size: int = 1000, ttl: int = 3600) -> None:
        """
        Initialize the cache manager.

        Args:
            max_size: Maximum number of entries in the cache.
            ttl: Default time-to-live in seconds for cache entries.
        """
        self.max_size = max_size
        self.default_ttl = ttl
        self._cache: OrderedDict[str, dict] = OrderedDict()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Any]:
        """
        Retrieve a value from the cache.

        Returns None on cache miss or if the entry has expired.
        Moves accessed entries to the end for LRU ordering.

        Args:
            key: The cache key to look up.

        Returns:
            The cached value, or None if not found / expired.
        """
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None

            entry = self._cache[key]

            # Check TTL expiration
            if time.time() > entry["expires_at"]:
                del self._cache[key]
                self._misses += 1
                return None

            # Move to end (most recently used)
            self._cache.move_to_end(key)
            self._hits += 1
            return entry["value"]

    def set(self, key: str, value: Any, ttl: int = None) -> None:
        """
        Store a value in the cache.

        If the cache is at capacity, the least recently used entry is evicted.

        Args:
            key: The cache key.
            value: The value to cache.
            ttl: Optional TTL override in seconds. Uses default if not provided.
        """
        effective_ttl = ttl if ttl is not None else self.default_ttl

        with self._lock:
            # If key already exists, remove it first so reinsertion goes to the end
            if key in self._cache:
                del self._cache[key]

            # Evict LRU entry if at capacity
            while len(self._cache) >= self.max_size:
                self._cache.popitem(last=False)

            self._cache[key] = {
                "value": value,
                "expires_at": time.time() + effective_ttl,
                "created_at": time.time(),
            }

    def invalidate(self, key: str) -> None:
        """
        Remove a specific entry from the cache.

        Args:
            key: The cache key to remove.
        """
        with self._lock:
            self._cache.pop(key, None)

    def clear(self) -> None:
        """Remove all entries from the cache and reset statistics."""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0

    def get_stats(self) -> dict:
        """
        Return cache performance statistics.

        Returns:
            Dictionary with hits, misses, hit_rate, size, and max_size.
        """
        with self._lock:
            total = self._hits + self._misses
            hit_rate = self._hits / total if total > 0 else 0.0
            return {
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(hit_rate, 4),
                "size": len(self._cache),
                "max_size": self.max_size,
            }
