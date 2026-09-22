"""In-process public request controls complementing Cloudflare edge limits."""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable
from functools import lru_cache


class SessionRateLimiter:
    """Bound requests by session without storing questions or credentials."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._recent: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self, requests_per_minute: int) -> bool:
        if requests_per_minute < 1:
            raise ValueError("O limite de requisições deve ser positivo.")
        now = self._clock()
        with self._lock:
            while self._recent and self._recent[0] <= now - 60:
                self._recent.popleft()
            if len(self._recent) >= requests_per_minute:
                return False
            self._recent.append(now)
            return True


@lru_cache(maxsize=32)
def global_concurrency_gate(limit: int) -> threading.BoundedSemaphore:
    """Share one gate across all Streamlit sessions in this app process."""
    if limit < 1:
        raise ValueError("O limite de concorrência deve ser positivo.")
    return threading.BoundedSemaphore(limit)
