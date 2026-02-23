"""Classification helpers for provider/API errors."""

from __future__ import annotations

import re
from enum import Enum
from typing import Optional

_RETRY_AFTER_RE = re.compile(
    r"(?:retry\s+after|retry\s+in)\s+([0-9]+(?:\.[0-9]+)?)",
    re.IGNORECASE,
)


class LLMErrorType(str, Enum):
    RATE_LIMITED = "RATE_LIMITED"
    TRANSIENT = "TRANSIENT"
    AUTH_ERROR = "AUTH_ERROR"
    EXHAUSTED = "EXHAUSTED"
    ERROR = "ERROR"


def classify_error(exc: Exception, status_code: Optional[int] = None) -> LLMErrorType:
    """Classify provider errors into retry/fallback policy buckets."""
    status = status_code
    if status is None:
        try:
            raw = getattr(exc, "status_code", None)
            if raw is not None:
                status = int(raw)
        except Exception:
            status = None

    message = f"{type(exc).__name__}: {exc}".lower()

    if status in {401, 403} or any(
        marker in message
        for marker in (
            "invalid api key",
            "api key not valid",
            "permission denied",
            "unauthorized",
            "forbidden",
        )
    ):
        return LLMErrorType.AUTH_ERROR

    if any(
        marker in message
        for marker in (
            "quota exceeded",
            "resource_exhausted",
            "insufficient_quota",
            "project quota/billing",
            "exceeded your current quota",
        )
    ):
        return LLMErrorType.EXHAUSTED

    if status == 429 or any(
        marker in message
        for marker in (
            "rate limit",
            "rate-limited",
            "retry after",
            "retry in",
            "429",
        )
    ):
        return LLMErrorType.RATE_LIMITED

    if status in {500, 502, 503, 504} or any(
        marker in message
        for marker in (
            "timeout",
            "timed out",
            "read timed out",
            "connection reset",
            "econnreset",
            "temporarily unavailable",
            "service unavailable",
            "ssl",
            "tls",
            "bad record mac",
            "sslv3_alert_bad_record_mac",
        )
    ):
        return LLMErrorType.TRANSIENT

    return LLMErrorType.ERROR


def extract_retry_after_seconds(exc: Exception) -> Optional[float]:
    """Best-effort retry-after extraction from exception attributes/text."""
    direct = getattr(exc, "retry_after", None)
    if isinstance(direct, (int, float)):
        try:
            value = float(direct)
            if value > 0:
                return value
        except Exception:
            pass

    message = str(exc)
    match = _RETRY_AFTER_RE.search(message)
    if match:
        try:
            value = float(match.group(1))
            if value > 0:
                return value
        except Exception:
            return None
    return None
