"""OpenRouter API client wrapper for GicaGen."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

import requests  # type: ignore[import-untyped]

from app.core.config import settings
from app.core.services.ai.errors import ProviderAuthError, ProviderTransientError, QuotaExceededError

logger = logging.getLogger(__name__)

_EXHAUSTED_MARKERS = (
    "quota exceeded",
    "insufficient_quota",
    "no credits",
    "payment required",
    "credit",
    "resource_exhausted",
)


class OpenRouterClient:
    """Synchronous OpenRouter client with lightweight probe support."""

    def __init__(self) -> None:
        self._session: Optional[requests.Session] = None

    def _build_headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {
            "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        }
        referer = str(getattr(settings, "OPENROUTER_HTTP_REFERER", "") or "").strip()
        if referer:
            headers["HTTP-Referer"] = referer
        title = str(getattr(settings, "OPENROUTER_APP_TITLE", "") or "").strip()
        if title:
            headers["X-Title"] = title
        return headers

    def _get_session(self) -> requests.Session:
        if self._session is None:
            self._session = requests.Session()
            self._session.headers.update(self._build_headers())
            logger.info("OpenRouterClient session created")
        return self._session

    def _close_session(self) -> None:
        if self._session is not None:
            try:
                self._session.close()
            except Exception:
                pass
            self._session = None

    def is_configured(self) -> bool:
        return bool(settings.OPENROUTER_API_KEY)

    def generate(self, prompt: str, *, timeout: int = 60, model: Optional[str] = None) -> str:
        if not self.is_configured():
            raise RuntimeError("OPENROUTER_API_KEY is not configured")

        selected_model = str(model or settings.OPENROUTER_MODEL).strip() or settings.OPENROUTER_MODEL
        url = f"{settings.OPENROUTER_BASE_URL.rstrip('/')}/chat/completions"
        payload = {
            "model": selected_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_completion_tokens": 1400,
            "stream": False,
        }
        request_timeout = timeout or int(getattr(settings, "OPENROUTER_TIMEOUT_SECONDS", 30))
        session = self._get_session()

        try:
            response = session.post(url, json=payload, timeout=request_timeout)
        except requests.Timeout as exc:
            self._close_session()
            raise ProviderTransientError(
                "Timeout conectando a OpenRouter.",
                provider="openrouter",
                status_code=None,
            ) from exc
        except requests.RequestException as exc:
            self._close_session()
            raise ProviderTransientError(
                f"OpenRouter request failed: {str(exc)[:200]}",
                provider="openrouter",
                status_code=None,
            ) from exc

        status_code = int(response.status_code)
        error_message = self._extract_error_message(response)

        if status_code in {401, 403}:
            raise ProviderAuthError(
                "OpenRouter authentication failed. Check OPENROUTER_API_KEY.",
                provider="openrouter",
                status_code=status_code,
            )

        if status_code == 402:
            raise QuotaExceededError(
                error_message or "OpenRouter credits exhausted or plan required.",
                provider="openrouter",
                retry_after=None,
                status_code=402,
                error_type="exhausted",
            )

        if status_code == 429:
            retry_after = self._extract_retry_after_seconds(response)
            if self._is_exhausted_message(error_message):
                raise QuotaExceededError(
                    error_message or "OpenRouter quota exhausted.",
                    provider="openrouter",
                    retry_after=None,
                    status_code=429,
                    error_type="exhausted",
                )
            message = "Rate limited by OpenRouter API."
            if retry_after is not None:
                message = f"{message} Retry after {int(round(retry_after))} seconds."
            raise QuotaExceededError(
                message,
                provider="openrouter",
                retry_after=retry_after,
                status_code=429,
                error_type="rate_limited",
            )

        if status_code >= 500:
            raise ProviderTransientError(
                error_message or f"OpenRouter upstream unavailable ({status_code}).",
                provider="openrouter",
                status_code=status_code,
            )

        if status_code >= 400:
            raise RuntimeError(error_message or f"OpenRouter API error {status_code}")

        response.raise_for_status()
        text = self._extract_text(response)
        if text.strip():
            return text
        raise RuntimeError("OpenRouter returned empty content")

    def probe(self, *, timeout: int = 8, model: Optional[str] = None) -> Dict[str, Any]:
        """Run a low-cost provider probe and expose health metadata."""
        if not self.is_configured():
            return {
                "provider": "openrouter",
                "status": "UNVERIFIED",
                "detail": "OPENROUTER_API_KEY no configurada.",
                "retry_after_s": None,
            }

        started = time.perf_counter()
        session = self._get_session()
        key_url = f"{settings.OPENROUTER_BASE_URL.rstrip('/')}/key"
        request_timeout = timeout or int(getattr(settings, "OPENROUTER_TIMEOUT_SECONDS", 30))

        try:
            response = session.get(key_url, timeout=request_timeout)
            if int(response.status_code) == 404:
                return self._probe_chat_completion(timeout=request_timeout, model=model)
            return self._probe_from_response(response, started)
        except requests.Timeout:
            self._close_session()
            return {
                "provider": "openrouter",
                "status": "ERROR",
                "detail": "Timeout conectando a OpenRouter.",
                "retry_after_s": None,
            }
        except requests.RequestException as exc:
            self._close_session()
            return {
                "provider": "openrouter",
                "status": "ERROR",
                "detail": str(exc)[:240],
                "retry_after_s": None,
            }

    def _probe_from_response(self, response: requests.Response, started: float) -> Dict[str, Any]:
        status_code = int(response.status_code)
        detail = self._extract_error_message(response)
        retry_after = self._extract_retry_after_seconds(response)
        payload = self._safe_json(response)

        if status_code in {401, 403}:
            return {
                "provider": "openrouter",
                "status": "AUTH_ERROR",
                "detail": detail or "Credenciales invalidas.",
                "retry_after_s": None,
            }

        if status_code == 402:
            return {
                "provider": "openrouter",
                "status": "EXHAUSTED",
                "detail": detail or "Sin creditos disponibles.",
                "retry_after_s": None,
            }

        if status_code == 429:
            if self._is_exhausted_message(detail):
                return {
                    "provider": "openrouter",
                    "status": "EXHAUSTED",
                    "detail": detail or "Sin creditos disponibles.",
                    "retry_after_s": None,
                }
            return {
                "provider": "openrouter",
                "status": "RATE_LIMITED",
                "detail": detail or "Rate limited.",
                "retry_after_s": int(round(retry_after)) if retry_after is not None else None,
            }

        if status_code >= 500:
            return {
                "provider": "openrouter",
                "status": "ERROR",
                "detail": detail or f"OpenRouter no disponible ({status_code}).",
                "retry_after_s": None,
            }

        if status_code >= 400:
            return {
                "provider": "openrouter",
                "status": "ERROR",
                "detail": detail or f"OpenRouter error {status_code}",
                "retry_after_s": None,
            }

        elapsed_ms = int(round((time.perf_counter() - started) * 1000))
        meta: Dict[str, Any] = {}
        if isinstance(payload, dict):
            flattened = payload.get("data") if isinstance(payload.get("data"), dict) else payload
            if isinstance(flattened, dict):
                meta = {
                    "limit_requests": flattened.get("limit_requests"),
                    "remaining_requests": flattened.get("remaining_requests"),
                    "credits": flattened.get("credits"),
                    "credits_remaining": flattened.get("credits_remaining"),
                }
                # Remove empty keys to keep payload concise.
                meta = {k: v for k, v in meta.items() if v is not None}

        return {
            "provider": "openrouter",
            "status": "OK",
            "detail": "Probe OK",
            "retry_after_s": None,
            "latency_ms": elapsed_ms,
            "meta": meta or None,
        }

    def _probe_chat_completion(self, *, timeout: int, model: Optional[str]) -> Dict[str, Any]:
        selected_model = str(model or settings.OPENROUTER_MODEL).strip() or settings.OPENROUTER_MODEL
        url = f"{settings.OPENROUTER_BASE_URL.rstrip('/')}/chat/completions"
        payload = {
            "model": selected_model,
            "messages": [{"role": "user", "content": "ping"}],
            "temperature": 0,
            "max_completion_tokens": 1,
            "stream": False,
        }
        started = time.perf_counter()
        session = self._get_session()
        response = session.post(url, json=payload, timeout=timeout)
        return self._probe_from_response(response, started)

    @staticmethod
    def _safe_json(response: requests.Response) -> Any:
        try:
            return response.json()
        except Exception:
            return None

    @staticmethod
    def _extract_text(response: requests.Response) -> str:
        payload = OpenRouterClient._safe_json(response)
        if not isinstance(payload, dict):
            return ""
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            return ""
        first = choices[0]
        if not isinstance(first, dict):
            return ""
        message = first.get("message")
        if not isinstance(message, dict):
            return ""
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            chunks: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str):
                        chunks.append(text)
            return "\n".join(part for part in chunks if part).strip()
        return ""

    @staticmethod
    def _extract_error_message(response: requests.Response) -> str:
        payload = OpenRouterClient._safe_json(response)
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                message = error.get("message")
                if isinstance(message, str) and message.strip():
                    return message.strip()[:240]
            for key in ("message", "detail", "error"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()[:240]
        text = str(getattr(response, "text", "") or "").strip()
        return text[:240]

    @staticmethod
    def _extract_retry_after_seconds(response: requests.Response) -> Optional[float]:
        header = response.headers.get("Retry-After")
        if header:
            try:
                value = float(header)
                if value > 0:
                    return value
            except Exception:
                pass

        message = OpenRouterClient._extract_error_message(response).lower()
        if "retry after" in message:
            tail = message.split("retry after", 1)[1].strip().split(" ", 1)[0]
            tail = tail.replace("seconds", "").replace("second", "").replace("s", "").strip()
            try:
                value = float(tail)
                if value > 0:
                    return value
            except Exception:
                return None
        return None

    @staticmethod
    def _is_exhausted_message(message: str) -> bool:
        lowered = str(message or "").lower()
        return any(marker in lowered for marker in _EXHAUSTED_MARKERS)
