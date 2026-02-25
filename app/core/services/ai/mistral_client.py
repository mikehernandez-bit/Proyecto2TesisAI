"""Mistral API client wrapper for GicaGen.

Uses the Mistral REST API through the ``requests`` library (urllib3 backend)
and returns plain generated text.

NOTE: we switched from ``httpx`` to ``requests`` because urllib3 handles some
Windows corporate TLS interception setups better than httpx defaults.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

import requests  # type: ignore[import-untyped]
import urllib3

from app.core.config import settings
from app.core.services.ai.errors import ProviderAuthError, QuotaExceededError

# Suppress InsecureRequestWarning since we intentionally use verify=False.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

_EXHAUSTED_MARKERS = (
    "quota exceeded",
    "project quota/billing",
    "insufficient_quota",
    "exceeded your current quota",
    "resource_exhausted",
)


class MistralClient:
    """Synchronous Mistral client with persistent session and retry support."""

    def __init__(self) -> None:
        self._session: Optional[requests.Session] = None

    def _get_session(self) -> requests.Session:
        """Return a reusable requests session (created lazily)."""
        if self._session is None:
            self._session = requests.Session()
            self._session.verify = False
            self._session.headers.update(
                {
                    "Authorization": f"Bearer {settings.MISTRAL_API_KEY}",
                    "Content-Type": "application/json",
                }
            )
            logger.info("MistralClient: persistent session created (urllib3, verify=off)")
        return self._session

    def is_configured(self) -> bool:
        return bool(settings.MISTRAL_API_KEY)

    def generate(self, prompt: str, *, timeout: int = 60, model: Optional[str] = None) -> str:
        if not self.is_configured():
            raise RuntimeError("MISTRAL_API_KEY is not configured")

        base_url = settings.MISTRAL_BASE_URL.rstrip("/")
        url = f"{base_url}/chat/completions"

        selected_model = str(model or settings.MISTRAL_MODEL).strip() or settings.MISTRAL_MODEL
        payload = {
            "model": selected_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": settings.MISTRAL_TEMPERATURE,
            "max_tokens": settings.MISTRAL_MAX_TOKENS,
        }

        last_error: Optional[Exception] = None

        for attempt in range(settings.MISTRAL_RETRY_MAX):
            try:
                session = self._get_session()
                response = session.post(url, json=payload, timeout=timeout)
                status_code = int(response.status_code)

                if status_code in {401, 403}:
                    raise ProviderAuthError(
                        "Mistral authentication failed. Check MISTRAL_API_KEY.",
                        provider="mistral",
                        status_code=status_code,
                    )

                if status_code == 429:
                    retry_after = self._extract_retry_after_seconds(response)
                    error_message = self._extract_error_message(response)
                    if self._is_exhausted_message(error_message):
                        raise QuotaExceededError(
                            "Quota exceeded. Check Mistral project quota/billing.",
                            provider="mistral",
                            retry_after=None,
                            error_type="exhausted",
                        )
                    message = "Rate limited by Mistral API."
                    if retry_after is not None:
                        message = f"{message} Retry after {int(round(retry_after))} seconds."
                    raise QuotaExceededError(
                        message,
                        provider="mistral",
                        retry_after=retry_after,
                        error_type="rate_limited",
                    )

                response.raise_for_status()
                text = self._extract_text(response)
                if text.strip():
                    return text

                last_error = RuntimeError("Mistral returned empty content")
                logger.warning(
                    "Mistral returned empty content (attempt %d/%d)",
                    attempt + 1,
                    settings.MISTRAL_RETRY_MAX,
                )

            except (QuotaExceededError, ProviderAuthError):
                raise
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Mistral API error (attempt %d/%d): %s",
                    attempt + 1,
                    settings.MISTRAL_RETRY_MAX,
                    str(exc),
                )
                # Destroy session on connection errors so a fresh one is created.
                self._close_session()

            if attempt < settings.MISTRAL_RETRY_MAX - 1:
                wait = settings.MISTRAL_RETRY_BACKOFF**attempt
                time.sleep(wait)

        raise RuntimeError(
            f"Mistral generation failed after {settings.MISTRAL_RETRY_MAX} attempts. Last error: {last_error}"
        )

    def probe(self, *, timeout: int = 8, model: Optional[str] = None) -> dict[str, Any]:
        """Run a minimal real request to validate provider availability."""
        if not self.is_configured():
            return {
                "provider": "mistral",
                "status": "UNVERIFIED",
                "detail": "MISTRAL_API_KEY no configurada.",
                "retry_after_s": None,
            }

        base_url = settings.MISTRAL_BASE_URL.rstrip("/")
        url = f"{base_url}/chat/completions"
        selected_model = str(model or settings.MISTRAL_MODEL).strip() or settings.MISTRAL_MODEL
        payload = {
            "model": selected_model,
            "messages": [{"role": "user", "content": "ping"}],
            "temperature": 0,
            "max_tokens": 1,
        }

        started = time.perf_counter()
        try:
            session = self._get_session()
            response = session.post(url, json=payload, timeout=timeout)
            status_code = int(response.status_code)

            if status_code in {401, 403}:
                return {
                    "provider": "mistral",
                    "status": "AUTH_ERROR",
                    "detail": self._extract_error_message(response) or "Credenciales invalidas.",
                    "retry_after_s": None,
                }

            if status_code == 429:
                retry_after = self._extract_retry_after_seconds(response)
                error_message = self._extract_error_message(response)
                if self._is_exhausted_message(error_message):
                    return {
                        "provider": "mistral",
                        "status": "EXHAUSTED",
                        "detail": error_message or "Quota exceeded.",
                        "retry_after_s": None,
                    }
                return {
                    "provider": "mistral",
                    "status": "RATE_LIMITED",
                    "detail": error_message or "Rate limited.",
                    "retry_after_s": int(round(retry_after)) if retry_after is not None else None,
                }

            response.raise_for_status()
            elapsed_ms = int(round((time.perf_counter() - started) * 1000))
            return {
                "provider": "mistral",
                "status": "OK",
                "detail": "Probe OK",
                "retry_after_s": None,
                "latency_ms": elapsed_ms,
            }
        except Exception as exc:
            self._close_session()
            return {
                "provider": "mistral",
                "status": "ERROR",
                "detail": str(exc)[:240],
                "retry_after_s": None,
            }

    def _close_session(self) -> None:
        """Safely close the current session."""
        if self._session is not None:
            try:
                self._session.close()
            except Exception:
                pass
            self._session = None

    @staticmethod
    def _extract_text(response: requests.Response) -> str:
        data = response.json()
        choices = data.get("choices") if isinstance(data, dict) else None
        if not isinstance(choices, list) or not choices:
            return ""
        first = choices[0]
        if not isinstance(first, dict):
            return ""
        message = first.get("message")
        if not isinstance(message, dict):
            return ""
        content = message.get("content", "")
        return content if isinstance(content, str) else ""

    @staticmethod
    def _extract_retry_after_seconds(response: requests.Response) -> Optional[float]:
        header = response.headers.get("Retry-After")
        if header:
            try:
                return float(header)
            except Exception:
                pass

        try:
            payload = response.json()
        except Exception:
            payload = None

        if isinstance(payload, dict):
            message = payload.get("message") or ""
            if isinstance(message, str):
                lower = message.lower()
                marker = "retry after"
                if marker in lower:
                    tail = lower.split(marker, 1)[1].strip().split(" ", 1)[0]
                    tail = tail.replace("seconds.", "").replace("second.", "").strip()
                    try:
                        return float(tail)
                    except Exception:
                        return None
        return None

    @staticmethod
    def _extract_error_message(response: requests.Response) -> str:
        try:
            payload = response.json()
        except Exception:
            payload = None
        if isinstance(payload, dict):
            detail = payload.get("message") or payload.get("detail") or payload.get("error")
            if isinstance(detail, str) and detail.strip():
                return detail.strip()[:240]
        text = str(getattr(response, "text", "") or "").strip()
        return text[:240]

    @staticmethod
    def _is_exhausted_message(message: str) -> bool:
        lowered = str(message or "").lower()
        return any(marker in lowered for marker in _EXHAUSTED_MARKERS)
