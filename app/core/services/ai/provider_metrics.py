"""Provider runtime metrics and health state for AI backends.

Tracks lightweight in-memory telemetry per provider so the UI can render:
- current health (OK, RATE_LIMITED, EXHAUSTED, DEGRADED, UNKNOWN)
- rate-limit window estimates
- quota estimates (local counters when provider quota APIs are unavailable)
- rolling error counters and latency.
"""

from __future__ import annotations

import collections
import datetime as dt
import math
import threading
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, Optional

from app.core.config import settings

_WINDOW_15M_SECONDS = 15 * 60
_RATE_WINDOW_SECONDS = 60
_TIMEOUT_DEGRADED_THRESHOLD = 3


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _month_key(now: Optional[dt.datetime] = None) -> str:
    current = now or _utc_now()
    return current.strftime("%Y-%m")


def _contains_timeout(text: str) -> bool:
    lowered = str(text or "").lower()
    markers = (
        "timed out",
        "timeout",
        "read timeout",
        "read timed out",
    )
    return any(marker in lowered for marker in markers)


def _contains_exhausted(text: str) -> bool:
    lowered = str(text or "").lower()
    markers = (
        "quota exceeded",
        "project quota/billing",
        "exceeded your current quota",
        "insufficient_quota",
    )
    return any(marker in lowered for marker in markers)


def _contains_rate_limited(text: str) -> bool:
    lowered = str(text or "").lower()
    markers = (
        "rate-limited",
        "rate limited",
        "429",
        "retry after",
    )
    return any(marker in lowered for marker in markers)


@dataclass
class _ProviderRuntime:
    requests_1m: Deque[dt.datetime] = field(default_factory=collections.deque)
    errors_15m: Deque[tuple[dt.datetime, str, str]] = field(default_factory=collections.deque)
    latency_ema_ms: Optional[float] = None
    last_error: str = ""
    rate_limited_until: Optional[dt.datetime] = None
    last_retry_after_s: Optional[int] = None
    exhausted: bool = False
    quota_period: str = field(default_factory=_month_key)
    quota_tokens_used: int = 0
    quota_requests_used: int = 0
    last_probe_status: str = "UNVERIFIED"
    last_probe_checked_at: Optional[str] = None
    last_probe_detail: str = ""
    last_probe_retry_after_s: Optional[int] = None

    def trim(self, now: dt.datetime) -> None:
        window_1m_cutoff = now - dt.timedelta(seconds=_RATE_WINDOW_SECONDS)
        while self.requests_1m and self.requests_1m[0] < window_1m_cutoff:
            self.requests_1m.popleft()

        window_15m_cutoff = now - dt.timedelta(seconds=_WINDOW_15M_SECONDS)
        while self.errors_15m and self.errors_15m[0][0] < window_15m_cutoff:
            self.errors_15m.popleft()

        if self.rate_limited_until and self.rate_limited_until <= now:
            self.rate_limited_until = None
            self.last_retry_after_s = None

        key = _month_key(now)
        if self.quota_period != key:
            self.quota_period = key
            self.quota_tokens_used = 0
            self.quota_requests_used = 0


class ProviderMetricsService:
    """In-memory metrics for provider health/status endpoints."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._runtime: Dict[str, _ProviderRuntime] = {
            "gemini": _ProviderRuntime(),
            "mistral": _ProviderRuntime(),
        }

    @staticmethod
    def estimate_tokens(text: str) -> int:
        normalized = str(text or "").strip()
        if not normalized:
            return 0
        # Lightweight approximation: ~4 chars/token.
        return max(1, math.ceil(len(normalized) / 4))

    @staticmethod
    def _rate_limit_per_minute() -> int:
        try:
            value = int(getattr(settings, "AI_LOCAL_RATE_LIMIT_PER_MINUTE", 60) or 60)
        except Exception:
            value = 60
        return max(1, value)

    @staticmethod
    def _quota_limit_tokens_month() -> Optional[int]:
        try:
            value = int(getattr(settings, "AI_LOCAL_QUOTA_LIMIT_TOKENS_MONTH", 0) or 0)
        except Exception:
            value = 0
        return value if value > 0 else None

    @staticmethod
    def _error_kind_from_message(message: str) -> str:
        if _contains_timeout(message):
            return "timeout"
        if _contains_exhausted(message):
            return "exhausted"
        if _contains_rate_limited(message):
            return "rate_limit"
        return "error"

    def _state(self, provider: str) -> _ProviderRuntime:
        return self._runtime.setdefault(provider, _ProviderRuntime())

    def record_success(
        self,
        provider: str,
        *,
        latency_ms: float,
        prompt: str = "",
        response: str = "",
    ) -> None:
        now = _utc_now()
        with self._lock:
            state = self._state(provider)
            state.trim(now)
            state.requests_1m.append(now)
            if state.latency_ema_ms is None:
                state.latency_ema_ms = float(latency_ms)
            else:
                # EMA keeps recent performance while smoothing spikes.
                state.latency_ema_ms = (0.7 * state.latency_ema_ms) + (0.3 * float(latency_ms))

            prompt_tokens = self.estimate_tokens(prompt)
            response_tokens = self.estimate_tokens(response)
            state.quota_requests_used += 1
            state.quota_tokens_used += prompt_tokens + response_tokens

            # Successful calls clear temporary health degradations.
            state.exhausted = False
            if state.rate_limited_until and state.rate_limited_until <= now:
                state.rate_limited_until = None
                state.last_retry_after_s = None

    def record_error(
        self,
        provider: str,
        *,
        message: str,
        latency_ms: Optional[float] = None,
        kind: Optional[str] = None,
    ) -> None:
        now = _utc_now()
        with self._lock:
            state = self._state(provider)
            state.trim(now)
            if latency_ms is not None:
                if state.latency_ema_ms is None:
                    state.latency_ema_ms = float(latency_ms)
                else:
                    state.latency_ema_ms = (0.8 * state.latency_ema_ms) + (0.2 * float(latency_ms))
            normalized_message = str(message or "").strip()[:240]
            state.last_error = normalized_message
            event_kind = kind or self._error_kind_from_message(normalized_message)
            state.errors_15m.append((now, normalized_message, event_kind))

            if event_kind == "exhausted":
                state.exhausted = True
            if event_kind == "rate_limit":
                # If no explicit retry_after is known yet, keep a short marker.
                state.rate_limited_until = now + dt.timedelta(seconds=10)
                state.last_retry_after_s = 10

    def record_rate_limited(
        self,
        provider: str,
        *,
        retry_after_s: Optional[float],
        message: str,
    ) -> None:
        now = _utc_now()
        wait_seconds = int(round(float(retry_after_s or 0)))
        wait_seconds = max(1, wait_seconds)
        with self._lock:
            state = self._state(provider)
            state.trim(now)
            state.last_error = str(message or "").strip()[:240]
            state.errors_15m.append((now, state.last_error, "rate_limit"))
            state.rate_limited_until = now + dt.timedelta(seconds=wait_seconds)
            state.last_retry_after_s = wait_seconds

    def record_exhausted(self, provider: str, *, message: str) -> None:
        now = _utc_now()
        with self._lock:
            state = self._state(provider)
            state.trim(now)
            state.last_error = str(message or "").strip()[:240]
            state.errors_15m.append((now, state.last_error, "exhausted"))
            state.exhausted = True

    def record_probe(
        self,
        provider: str,
        *,
        status: str,
        detail: str = "",
        retry_after_s: Optional[float] = None,
    ) -> None:
        """Store latest probe snapshot and align runtime health markers."""
        now = _utc_now()
        normalized_status = str(status or "UNVERIFIED").upper().strip() or "UNVERIFIED"
        clipped_detail = str(detail or "").strip()[:240]
        wait_seconds: Optional[int] = None
        if retry_after_s is not None:
            try:
                wait_seconds = max(0, int(round(float(retry_after_s))))
            except Exception:
                wait_seconds = None

        with self._lock:
            state = self._state(provider)
            state.trim(now)
            state.last_probe_status = normalized_status
            state.last_probe_checked_at = now.isoformat().replace("+00:00", "Z")
            state.last_probe_detail = clipped_detail
            state.last_probe_retry_after_s = wait_seconds

            if normalized_status == "OK":
                state.exhausted = False
                state.rate_limited_until = None
                state.last_retry_after_s = None
                return

            state.last_error = clipped_detail or state.last_error
            if normalized_status == "RATE_LIMITED":
                effective_wait = max(1, wait_seconds or 10)
                state.errors_15m.append((now, state.last_error, "rate_limit"))
                state.rate_limited_until = now + dt.timedelta(seconds=effective_wait)
                state.last_retry_after_s = effective_wait
                return

            if normalized_status == "EXHAUSTED":
                state.errors_15m.append((now, state.last_error, "exhausted"))
                state.exhausted = True
                return

            if normalized_status == "AUTH_ERROR":
                state.errors_15m.append((now, state.last_error or "authentication failed", "auth"))
                return

            if normalized_status == "ERROR":
                state.errors_15m.append((now, state.last_error or "probe failed", "error"))

    @staticmethod
    def _derive_health(state: _ProviderRuntime, *, now: dt.datetime, configured: bool) -> str:
        if not configured:
            return "UNKNOWN"
        if state.exhausted:
            return "EXHAUSTED"
        if state.rate_limited_until and state.rate_limited_until > now:
            return "RATE_LIMITED"
        timeout_errors = sum(1 for _, _, kind in state.errors_15m if kind == "timeout")
        if timeout_errors >= _TIMEOUT_DEGRADED_THRESHOLD:
            return "DEGRADED"
        return "OK"

    def payload_for_provider(self, provider: str, *, model: str, configured: bool) -> Dict[str, Any]:
        now = _utc_now()
        with self._lock:
            state = self._state(provider)
            state.trim(now)

            health = self._derive_health(state, now=now, configured=configured)
            rate_limit_limit = self._rate_limit_per_minute()
            used_1m = len(state.requests_1m)
            remaining_1m = max(0, rate_limit_limit - used_1m)

            reset_seconds = 0
            if state.rate_limited_until and state.rate_limited_until > now:
                reset_seconds = int(math.ceil((state.rate_limited_until - now).total_seconds()))
            elif used_1m >= rate_limit_limit and state.requests_1m:
                reset_seconds = max(
                    0,
                    int(math.ceil(_RATE_WINDOW_SECONDS - (now - state.requests_1m[0]).total_seconds())),
                )

            quota_limit_tokens = self._quota_limit_tokens_month()
            quota_remaining = (
                max(0, quota_limit_tokens - state.quota_tokens_used) if quota_limit_tokens is not None else None
            )

            errors_last_15m = len(state.errors_15m)
            avg_latency_ms = int(round(state.latency_ema_ms or 0))

            return {
                "id": provider,
                "display_name": provider.capitalize(),
                "model": model,
                "health": health,
                "configured": configured,
                "probe": {
                    "status": state.last_probe_status,
                    "checked_at": state.last_probe_checked_at,
                    "detail": state.last_probe_detail or None,
                    "retry_after_s": state.last_probe_retry_after_s,
                },
                "last_probe_status": state.last_probe_status,
                "last_probe_checked_at": state.last_probe_checked_at,
                "last_probe_detail": state.last_probe_detail or None,
                "last_probe_retry_after_s": state.last_probe_retry_after_s,
                "rate_limit": {
                    "remaining": remaining_1m,
                    "limit": rate_limit_limit,
                    "reset_seconds": reset_seconds,
                },
                "quota": {
                    "remaining": quota_remaining,
                    "limit": quota_limit_tokens,
                    "remaining_tokens": quota_remaining,
                    "limit_tokens": quota_limit_tokens,
                    "period": "month",
                    "note": "local_estimate",
                },
                "stats": {
                    "avg_latency_ms": avg_latency_ms,
                    "errors_last_15m": errors_last_15m,
                    "last_error": state.last_error or None,
                },
            }
