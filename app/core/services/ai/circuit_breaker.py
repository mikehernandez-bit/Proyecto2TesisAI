"""Circuit breaker for provider resilience."""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict


@dataclass
class _CircuitState:
    state: str = "closed"  # closed | open | half_open
    failures: Deque[float] = field(default_factory=deque)
    opened_until: float = 0.0
    half_open_trials: int = 0
    last_reason: str = ""


class CircuitBreaker:
    """Thread-safe circuit breaker per provider."""

    def __init__(
        self,
        *,
        failures_threshold: int = 5,
        window_seconds: float = 60.0,
        open_seconds: float = 120.0,
        half_open_max_trials: int = 2,
        time_fn=time.monotonic,
    ) -> None:
        self._failures_threshold = max(1, int(failures_threshold))
        self._window_seconds = max(1.0, float(window_seconds))
        self._open_seconds = max(1.0, float(open_seconds))
        self._half_open_max_trials = max(1, int(half_open_max_trials))
        self._time_fn = time_fn
        self._lock = threading.RLock()
        self._states: Dict[str, _CircuitState] = {}

    def _state(self, provider: str) -> _CircuitState:
        return self._states.setdefault(str(provider), _CircuitState())

    def _trim_failures(self, state: _CircuitState, now: float) -> None:
        cutoff = now - self._window_seconds
        while state.failures and state.failures[0] < cutoff:
            state.failures.popleft()

    def before_call(self, provider: str) -> bool:
        """Return True if calls are allowed for this provider."""
        now = self._time_fn()
        with self._lock:
            state = self._state(provider)
            self._trim_failures(state, now)

            if state.state == "open":
                if now < state.opened_until:
                    return False
                # Transition to half-open when cooldown expires.
                state.state = "half_open"
                state.half_open_trials = 0

            if state.state == "half_open":
                if state.half_open_trials >= self._half_open_max_trials:
                    state.state = "open"
                    state.opened_until = now + self._open_seconds
                    return False
                state.half_open_trials += 1
                return True

            return True

    def on_success(self, provider: str) -> None:
        now = self._time_fn()
        with self._lock:
            state = self._state(provider)
            state.state = "closed"
            state.failures.clear()
            state.opened_until = 0.0
            state.half_open_trials = 0
            state.last_reason = ""
            self._trim_failures(state, now)

    def on_failure(self, provider: str, *, reason: str = "") -> None:
        now = self._time_fn()
        with self._lock:
            state = self._state(provider)
            state.last_reason = str(reason or "")[:160]

            if state.state == "half_open":
                state.state = "open"
                state.opened_until = now + self._open_seconds
                state.half_open_trials = 0
                state.failures.append(now)
                self._trim_failures(state, now)
                return

            state.failures.append(now)
            self._trim_failures(state, now)
            if len(state.failures) >= self._failures_threshold:
                state.state = "open"
                state.opened_until = now + self._open_seconds
                state.half_open_trials = 0

    def current_state(self, provider: str) -> str:
        now = self._time_fn()
        with self._lock:
            state = self._state(provider)
            self._trim_failures(state, now)
            if state.state == "open" and now >= state.opened_until:
                # auto transition visibility
                return "half_open"
            return state.state

    def seconds_until_closed(self, provider: str) -> float:
        now = self._time_fn()
        with self._lock:
            state = self._state(provider)
            if state.state != "open":
                return 0.0
            return max(0.0, state.opened_until - now)

    def snapshot(self) -> Dict[str, Dict[str, object]]:
        now = self._time_fn()
        with self._lock:
            payload: Dict[str, Dict[str, object]] = {}
            for provider, state in self._states.items():
                self._trim_failures(state, now)
                payload[provider] = {
                    "state": self.current_state(provider),
                    "open_seconds_remaining": self.seconds_until_closed(provider),
                    "recent_failures": len(state.failures),
                    "last_reason": state.last_reason or None,
                }
            return payload

