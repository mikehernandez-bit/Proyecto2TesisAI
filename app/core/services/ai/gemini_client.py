"""Gemini API client wrapper for GicaGen.

Provides a thin wrapper around the ``google.generativeai`` SDK with
retry logic, exponential backoff, and safe logging (never logs API keys).
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Dict, Optional

from app.core.config import settings
from app.core.services.ai.errors import ProviderAuthError, QuotaExceededError

logger = logging.getLogger(__name__)

_RETRY_IN_TEXT_RE = re.compile(r"retry in\s+([0-9]+(?:\.[0-9]+)?)s", re.IGNORECASE)
_RETRY_DELAY_BLOCK_RE = re.compile(r"retry_delay\s*\{\s*seconds:\s*(\d+)", re.IGNORECASE)


class GeminiClient:
    """Synchronous Gemini API client with retry support.

    Uses the ``google.generativeai`` SDK. The client is designed to be
    called inside ``BackgroundTasks`` (threadpool), so synchronous calls
    are acceptable here.
    """

    def __init__(self) -> None:
        self._models: Dict[str, Any] = {}
        self._model = None

    def is_configured(self) -> bool:
        """Return True when a Gemini API key is available."""
        return bool(settings.GEMINI_API_KEY)

    def _get_model(self, model_name: Optional[str] = None):
        """Lazy-initialise the generative model on first call."""
        if model_name is None and self._model is not None:
            return self._model

        target_model = str(model_name or settings.GEMINI_MODEL).strip() or settings.GEMINI_MODEL

        # Backward-compatible shortcut used in existing tests.
        if target_model == settings.GEMINI_MODEL and self._model is not None:
            return self._model
        if target_model in self._models:
            return self._models[target_model]

        try:
            import google.generativeai as genai
        except ImportError as exc:
            raise RuntimeError("google-generativeai is not installed. Run: pip install google-generativeai") from exc

        genai.configure(api_key=settings.GEMINI_API_KEY)
        model = genai.GenerativeModel(
            model_name=target_model,
            generation_config={
                "temperature": settings.GEMINI_TEMPERATURE,
                "top_p": settings.GEMINI_TOP_P,
                "max_output_tokens": settings.GEMINI_MAX_OUTPUT_TOKENS,
            },
        )
        self._models[target_model] = model
        if target_model == settings.GEMINI_MODEL:
            self._model = model
        logger.info(
            "GeminiClient initialised (model=%s, temp=%.1f)",
            target_model,
            settings.GEMINI_TEMPERATURE,
        )
        return model

    def generate(self, prompt: str, *, timeout: int = 60, model: Optional[str] = None) -> str:
        """Generate content from a prompt with retries."""
        if not self.is_configured():
            raise RuntimeError("GEMINI_API_KEY is not configured")

        model_client = self._get_model(model)
        last_error: Optional[Exception] = None

        for attempt in range(settings.GEMINI_RETRY_MAX):
            try:
                response = model_client.generate_content(
                    prompt,
                    request_options={"timeout": timeout},
                )
                text = response.text or ""
                if not text.strip():
                    logger.warning(
                        "Gemini returned empty content (attempt %d/%d)",
                        attempt + 1,
                        settings.GEMINI_RETRY_MAX,
                    )
                    last_error = RuntimeError("Gemini returned empty content")
                else:
                    return text

            except Exception as exc:
                if self._is_auth_error(exc):
                    raise ProviderAuthError(
                        "Gemini authentication failed. Check GEMINI_API_KEY.",
                        provider="gemini",
                        status_code=401,
                    ) from exc

                if self._is_exhausted_error(exc):
                    raise QuotaExceededError(
                        "Quota exceeded. Check Gemini project quota/billing.",
                        provider="gemini",
                        retry_after=None,
                        error_type="exhausted",
                    ) from exc

                if self._is_rate_limited_error(exc):
                    retry_after = self._extract_retry_after_seconds(exc)
                    message = "Rate limited by Gemini API."
                    if retry_after is not None:
                        message = f"{message} Retry after {int(round(retry_after))} seconds."
                    raise QuotaExceededError(
                        message,
                        provider="gemini",
                        retry_after=retry_after,
                        error_type="rate_limited",
                    ) from exc

                last_error = exc
                logger.warning(
                    "Gemini API error (attempt %d/%d): %s",
                    attempt + 1,
                    settings.GEMINI_RETRY_MAX,
                    str(exc),
                )

            # Exponential backoff before next retry
            if attempt < settings.GEMINI_RETRY_MAX - 1:
                wait = settings.GEMINI_RETRY_BACKOFF**attempt
                logger.info("Retrying in %.1fs...", wait)
                time.sleep(wait)

        raise RuntimeError(
            f"Gemini generation failed after {settings.GEMINI_RETRY_MAX} attempts. Last error: {last_error}"
        )

    def probe(self, *, timeout: int = 8, model: Optional[str] = None) -> Dict[str, Any]:
        """Run a low-cost real request to validate provider availability."""
        if not self.is_configured():
            return {
                "provider": "gemini",
                "status": "UNVERIFIED",
                "detail": "GEMINI_API_KEY no configurada.",
                "retry_after_s": None,
            }

        started = time.perf_counter()
        target_model = str(model or settings.GEMINI_MODEL).strip() or settings.GEMINI_MODEL
        try:
            model_client = self._get_model(target_model)
            model_client.generate_content(
                "ping",
                generation_config={
                    "temperature": 0,
                    "top_p": 1,
                    "max_output_tokens": 1,
                },
                request_options={"timeout": timeout},
            )
            elapsed_ms = int(round((time.perf_counter() - started) * 1000))
            return {
                "provider": "gemini",
                "status": "OK",
                "detail": "Probe OK",
                "retry_after_s": None,
                "latency_ms": elapsed_ms,
            }
        except Exception as exc:
            retry_after = self._extract_retry_after_seconds(exc)
            if self._is_auth_error(exc):
                status = "AUTH_ERROR"
                retry_after = None
            elif self._is_exhausted_error(exc):
                status = "EXHAUSTED"
                retry_after = None
            elif self._is_rate_limited_error(exc):
                status = "RATE_LIMITED"
            else:
                status = "ERROR"

            return {
                "provider": "gemini",
                "status": status,
                "detail": str(exc)[:240],
                "retry_after_s": int(round(retry_after)) if retry_after is not None else None,
            }

    @staticmethod
    def _is_auth_error(exc: Exception) -> bool:
        status_candidates = [
            getattr(exc, "status_code", None),
            getattr(exc, "code", None),
        ]
        for status in status_candidates:
            if status is None:
                continue
            try:
                if int(status) in {401, 403}:
                    return True
            except Exception:
                pass

        text = str(exc).lower()
        markers = (
            "api key not valid",
            "invalid api key",
            "permission denied",
            "unauthorized",
            "forbidden",
            "401",
            "403",
        )
        return any(marker in text for marker in markers)

    @staticmethod
    def _is_exhausted_error(exc: Exception) -> bool:
        """Detect hard quota exhaustion conditions."""
        text = str(exc).lower()
        markers = (
            "quota exceeded",
            "project quota/billing",
            "exceeded your current quota",
            "insufficient_quota",
            "resource_exhausted",
        )
        return any(marker in text for marker in markers)

    @staticmethod
    def _is_rate_limited_error(exc: Exception) -> bool:
        """Detect temporary rate-limit conditions."""
        status_candidates = [
            getattr(exc, "status_code", None),
            getattr(exc, "code", None),
        ]
        for status in status_candidates:
            if status is None:
                continue
            try:
                if int(status) == 429:
                    return True
            except Exception:
                pass

        text = str(exc).lower()
        markers = (
            "429",
            "rate limit",
            "rate-limited",
            "retry after",
        )
        return any(marker in text for marker in markers)

    @staticmethod
    def _extract_retry_after_seconds(exc: Exception) -> Optional[float]:
        """Extract retry hint from provider message when available."""
        text = str(exc)

        m = _RETRY_IN_TEXT_RE.search(text)
        if m:
            try:
                return float(m.group(1))
            except Exception:
                return None

        m = _RETRY_DELAY_BLOCK_RE.search(text)
        if m:
            try:
                return float(m.group(1))
            except Exception:
                return None

        return None
