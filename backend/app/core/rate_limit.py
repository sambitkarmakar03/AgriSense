from collections import deque
from math import ceil
from threading import Lock
from time import monotonic

from fastapi import HTTPException


class UploadRateLimiter:
    """Small process-local sliding-window limiter for authenticated uploads."""

    def __init__(self, max_requests: int, window_seconds: float) -> None:
        if max_requests < 1 or window_seconds <= 0:
            raise ValueError("Rate-limit capacity and window must be positive.")
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = {}
        self._lock = Lock()

    def check(self, key: str) -> None:
        now = monotonic()
        with self._lock:
            events = self._events.setdefault(key, deque())
            cutoff = now - self.window_seconds
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= self.max_requests:
                retry_after = max(1, ceil(self.window_seconds - (now - events[0])))
                raise HTTPException(
                    status_code=429,
                    detail="Upload rate limit exceeded. Try again later.",
                    headers={"Retry-After": str(retry_after)},
                )
            events.append(now)
