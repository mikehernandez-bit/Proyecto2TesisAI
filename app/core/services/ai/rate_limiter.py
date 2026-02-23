"""Sliding-window RPM limiter."""

from __future__ import annotations

import asyncio
import threading
import time
from collections import deque
from typing import Callable, Deque


class SlidingWindowRateLimiter:
    """Rate limiter with a 60s sliding window."""

    def __init__(
        self,
        rpm: int,
        *,
        window_seconds: float = 60.0,
        time_fn: Callable[[], float] = time.monotonic,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self._rpm = max(1, int(rpm))
        self._window_seconds = max(1.0, float(window_seconds))
        self._time_fn = time_fn
        self._sleep_fn = sleep_fn
        self._events: Deque[float] = deque()
        self._lock = threading.RLock()

    def _trim(self, now: float) -> None:
        cutoff = now - self._window_seconds
        while self._events and self._events[0] < cutoff:
            self._events.popleft()

    def _next_wait(self, now: float) -> float:
        self._trim(now)
        if len(self._events) < self._rpm:
            return 0.0
        oldest = self._events[0]
        return max(0.0, self._window_seconds - (now - oldest))

    def acquire_sync(self) -> None:
        while True:
            with self._lock:
                now = self._time_fn()
                wait = self._next_wait(now)
                if wait <= 0:
                    self._events.append(now)
                    return
            self._sleep_fn(min(wait, 0.5))

    async def acquire(self) -> None:
        while True:
            with self._lock:
                now = self._time_fn()
                wait = self._next_wait(now)
                if wait <= 0:
                    self._events.append(now)
                    return
            await asyncio.sleep(min(wait, 0.5))

    def window_usage(self) -> int:
        with self._lock:
            self._trim(self._time_fn())
            return len(self._events)

