"""Custom exceptions for AI generation flow."""

from __future__ import annotations

from typing import Optional


class AIServiceError(RuntimeError):
    """Base class for AI service errors."""


class QuotaExceededError(AIServiceError):
    """Raised when provider quota/rate limits block generation."""

    def __init__(
        self,
        message: str = "Quota exceeded for Gemini API.",
        *,
        provider: str = "ai",
        retry_after: Optional[float] = None,
        status_code: int = 429,
        error_type: str = "exhausted",
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.retry_after = retry_after
        self.status_code = status_code
        # Allowed values: exhausted, rate_limited.
        self.error_type = str(error_type or "exhausted").lower().strip()


class ProviderAuthError(AIServiceError):
    """Raised when provider credentials are invalid or unauthorized."""

    def __init__(
        self,
        message: str = "Provider authentication failed.",
        *,
        provider: str = "ai",
        status_code: int = 401,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.status_code = status_code


class ProviderTransientError(AIServiceError):
    """Raised for transient provider errors (timeouts/5xx)."""

    def __init__(
        self,
        message: str = "Transient provider error.",
        *,
        provider: str = "ai",
        status_code: Optional[int] = None,
        retry_after: Optional[float] = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.status_code = status_code
        self.retry_after = retry_after


class GenerationCancelledError(AIServiceError):
    """Raised when a generation run is cancelled by the user."""
