"""In-memory sliding-window rate limiting.

OAK runs as a single process (ADR-0014), so an in-memory limiter sees every request. Limits
reset on restart; that is acceptable for login throttling and webhook flood protection.

Memory stays bounded (audit F02 of 25 October):

* only :meth:`SlidingWindowLimiter.hit` stores anything; checking a key never creates one;
* once per window every key is pruned, and keys without recent hits are dropped;
* above ``max_keys`` the keys whose last hit is oldest go first. Those are the ones closest to
  expiring anyway.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable

MAX_KEYS = 10_000
# After evicting, keep this share of max_keys, so the next hits do not evict again right away.
EVICT_TO = 0.9


class SlidingWindowLimiter:
    def __init__(
        self,
        limit: int,
        window_seconds: float,
        clock: Callable[[], float] = time.monotonic,
        max_keys: int = MAX_KEYS,
    ) -> None:
        self.limit = limit
        self.window = window_seconds
        self.max_keys = max_keys
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()
        self._last_sweep = clock()

    def _prune(self, hits: deque[float], now: float) -> deque[float]:
        while hits and now - hits[0] >= self.window:
            hits.popleft()
        return hits

    def _retry_after(self, hits: deque[float], now: float) -> int | None:
        if len(hits) >= self.limit:
            return max(1, int(self.window - (now - hits[0])) + 1)
        return None

    def _sweep(self, now: float) -> None:
        self._hits = {k: v for k, v in self._hits.items() if self._prune(v, now)}
        self._last_sweep = now

    def _evict(self) -> None:
        keep = int(self.max_keys * EVICT_TO)
        newest = sorted(self._hits.items(), key=lambda item: item[1][-1], reverse=True)[:keep]
        self._hits = dict(newest)

    def hit(self, key: str) -> int | None:
        """Record a hit. Returns ``None`` if allowed, else seconds until a slot frees up."""
        with self._lock:
            now = self._clock()
            if now - self._last_sweep >= self.window:
                self._sweep(now)
            hits = self._hits.get(key)
            if hits is not None:
                retry = self._retry_after(self._prune(hits, now), now)
                if retry is not None:
                    return retry
            else:
                if len(self._hits) >= self.max_keys:
                    self._sweep(now)
                    if len(self._hits) >= self.max_keys:
                        self._evict()
                hits = self._hits[key] = deque()
            hits.append(now)
            return None

    def blocked(self, key: str) -> int | None:
        """Seconds until the key may try again, or ``None``. Stores nothing."""
        with self._lock:
            hits = self._hits.get(key)
            if hits is None:
                return None
            now = self._clock()
            return self._retry_after(self._prune(hits, now), now)

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)

    def __len__(self) -> int:
        with self._lock:
            return len(self._hits)
