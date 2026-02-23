"""Retry policy for resilient LLM calls."""

from __future__ import annotations

import random
from typing import Optional

from app.core.services.ai.error_classifier import LLMErrorType

_BACKOFF_SECONDS = (2.0, 5.0, 12.0)


def should_retry(
    err_type: LLMErrorType,
    attempt: int,
    *,
    max_rate_limited_retries: int = 2,
    max_transient_retries: int = 1,
) -> bool:
    """Return whether a call should be retried for the given error type."""
    safe_attempt = max(0, int(attempt))
    if err_type == LLMErrorType.RATE_LIMITED:
        return safe_attempt < max(0, int(max_rate_limited_retries))
    if err_type == LLMErrorType.TRANSIENT:
        return safe_attempt < max(0, int(max_transient_retries))
    return False


def compute_backoff(
    attempt: int,
    retry_after: Optional[float] = None,
    *,
    jitter: float = 0.3,
    cap_seconds: float = 30.0,
    rng: Optional[random.Random] = None,
) -> float:
    """Compute exponential backoff with jitter, honoring Retry-After when present."""
    cap = max(0.1, float(cap_seconds))
    if retry_after is not None:
        try:
            wait = float(retry_after)
            if wait > 0:
                return min(cap, wait)
        except Exception:
            pass

    idx = min(max(0, int(attempt)), len(_BACKOFF_SECONDS) - 1)
    base = _BACKOFF_SECONDS[idx]
    jitter_ratio = max(0.0, float(jitter))
    randomizer = rng.uniform if rng is not None else random.uniform
    factor = randomizer(1.0 - jitter_ratio, 1.0 + jitter_ratio)
    wait_with_jitter = base * factor
    return min(cap, max(0.1, wait_with_jitter))

