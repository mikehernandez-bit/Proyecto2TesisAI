"""Unit tests for retry policy helpers."""

from random import Random

from app.core.services.ai.error_classifier import LLMErrorType
from app.core.services.ai.retry_policy import compute_backoff, should_retry


def test_compute_backoff_respects_retry_after_and_cap():
    wait = compute_backoff(
        attempt=0,
        retry_after=45.0,
        cap_seconds=30.0,
    )
    assert wait == 30.0


def test_compute_backoff_with_deterministic_jitter():
    rng = Random(7)
    wait = compute_backoff(
        attempt=1,  # base 5s
        retry_after=None,
        jitter=0.3,
        cap_seconds=30.0,
        rng=rng,
    )
    assert 3.5 <= wait <= 6.5


def test_should_retry_only_rate_limited_and_transient():
    assert should_retry(LLMErrorType.RATE_LIMITED, 0, max_rate_limited_retries=2) is True
    assert should_retry(LLMErrorType.RATE_LIMITED, 2, max_rate_limited_retries=2) is False
    assert should_retry(LLMErrorType.TRANSIENT, 0, max_transient_retries=1) is True
    assert should_retry(LLMErrorType.TRANSIENT, 1, max_transient_retries=1) is False
    assert should_retry(LLMErrorType.EXHAUSTED, 0) is False
    assert should_retry(LLMErrorType.AUTH_ERROR, 0) is False

