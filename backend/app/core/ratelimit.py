"""In-memory sliding-window rate limiting.

OAK runs as a single process (ADR-0014), so an in-memory limiter sees every request. Limits
reset on restart; that is acceptable for login throttling and webhook flood protection.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_seconds: float, clock: Callable[[], float] = time.monotonic) -> None:
        self.limit = limit
        self.window = window_seconds
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> deque[float]:
        hits = self._hits.setdefault(key, deque())
        while hits and now - hits[0] >= self.window:
            hits.popleft()
        return hits

    def hit(self, key: str) -> int | None:
        """Record a hit. Returns ``None`` if allowed, else seconds until a slot frees up."""
        with self._lock:
            now = self._clock()
            hits = self._prune(key, now)
            if len(hits) >= self.limit:
                return max(1, int(self.window - (now - hits[0])) + 1)
            hits.append(now)
            if len(self._hits) > 10_000:
                self._hits = {k: v for k, v in self._hits.items() if v}
            return None

    def blocked(self, key: str) -> int | None:
        with self._lock:
            now = self._clock()
            hits = self._prune(key, now)
            if len(hits) >= self.limit:
                return max(1, int(self.window - (now - hits[0])) + 1)
            return None

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)
