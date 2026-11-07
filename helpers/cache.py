"""Bounded LRU cache with time-to-live (TTL) expiration using OrderedDict."""

from __future__ import annotations

import time
from collections import OrderedDict


class _CacheEntry[V]:
    """Internal container wrapping a cached value and its expiration timestamp."""

    __slots__ = ("expires_at", "value")

    def __init__(self, value: V, expires_at: float | None) -> None:
        self.value = value
        self.expires_at = expires_at

    def is_expired(self, current_time: float) -> bool:
        """Check if the entry has expired."""
        return self.expires_at is not None and current_time >= self.expires_at


class TTLCache[K, V]:
    """Bounded, thread-safe (single-thread asyncio) LRU cache with TTL eviction.

    Features:
        - O(1) retrieval and insertion via collections.OrderedDict.
        - Automatic least-recently-used (LRU) eviction upon reaching max_size.
        - Per-entry or default time-to-live (TTL) in seconds.
    """

    __slots__ = ("_data", "_default_ttl", "_max_size")

    def __init__(self, max_size: int = 1024, default_ttl: float | None = 300.0) -> None:
        if max_size <= 0:
            raise ValueError("max_size must be a positive integer.")
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._data: OrderedDict[K, _CacheEntry[V]] = OrderedDict()

    def get(self, key: K, default: V | None = None) -> V | None:
        """Retrieve a value by key, evicting it if expired."""
        entry = self._data.get(key)
        if entry is None:
            return default

        now = time.monotonic()
        if entry.is_expired(now):
            del self._data[key]
            return default

        # Move to end to mark as most recently used
        self._data.move_to_end(key)
        return entry.value

    def set(self, key: K, value: V, ttl: float | None = None) -> None:
        """Insert or update a key with an optional custom TTL."""
        effective_ttl = ttl if ttl is not None else self._default_ttl
        now = time.monotonic()
        expires_at = (now + effective_ttl) if effective_ttl is not None else None

        if key in self._data:
            del self._data[key]
        elif len(self._data) >= self._max_size:
            # Evict the oldest (least recently used) entry
            self._data.popitem(last=False)

        self._data[key] = _CacheEntry(value, expires_at)

    def delete(self, key: K) -> bool:
        """Remove a key from the cache. Returns True if deleted."""
        if key in self._data:
            del self._data[key]
            return True
        return False

    def clear(self) -> None:
        """Remove all entries from the cache."""
        self._data.clear()

    def prune_expired(self) -> int:
        """Actively purge all expired keys from the cache. Returns count of purged keys."""
        now = time.monotonic()
        expired_keys = [k for k, entry in self._data.items() if entry.is_expired(now)]
        for k in expired_keys:
            del self._data[k]
        return len(expired_keys)

    def __contains__(self, key: K) -> bool:
        return self.get(key) is not None

    def __len__(self) -> int:
        return len(self._data)
