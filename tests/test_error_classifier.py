"""Tests for provider error classification."""

from app.core.services.ai.error_classifier import LLMErrorType, classify_error, extract_retry_after_seconds


def test_classify_rate_limited_by_status():
    exc = RuntimeError("limit")
    assert classify_error(exc, status_code=429) == LLMErrorType.RATE_LIMITED


def test_classify_exhausted_by_message():
    exc = RuntimeError("Quota exceeded for this project quota/billing")
    assert classify_error(exc) == LLMErrorType.EXHAUSTED


def test_classify_exhausted_by_402_status():
    exc = RuntimeError("Payment required")
    assert classify_error(exc, status_code=402) == LLMErrorType.EXHAUSTED


def test_classify_auth_error():
    exc = RuntimeError("401 unauthorized key invalid")
    assert classify_error(exc) == LLMErrorType.AUTH_ERROR


def test_classify_transient():
    exc = RuntimeError("Read timed out while connecting")
    assert classify_error(exc) == LLMErrorType.TRANSIENT


def test_classify_ssl_bad_record_mac_as_transient():
    exc = RuntimeError("SSLError: [SSL: SSLV3_ALERT_BAD_RECORD_MAC] sslv3 alert bad record mac")
    assert classify_error(exc) == LLMErrorType.TRANSIENT


def test_extract_retry_after_from_message():
    exc = RuntimeError("Rate limited. Retry after 12 seconds.")
    assert extract_retry_after_seconds(exc) == 12.0
