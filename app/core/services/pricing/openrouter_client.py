from __future__ import annotations

from typing import Any, Dict, Optional

import httpx

from app.core.config import settings


class OpenRouterPricingClient:
    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        http_referer: Optional[str] = None,
        app_title: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
    ) -> None:
        self._base_url = str(base_url or settings.OPENROUTER_BASE_URL).rstrip("/")
        self._api_key = str(api_key or settings.OPENROUTER_API_KEY).strip()
        self._http_referer = str(http_referer or settings.OPENROUTER_HTTP_REFERER).strip()
        self._app_title = str(app_title or settings.OPENROUTER_APP_TITLE).strip()
        self._timeout = max(5, int(timeout_seconds or settings.OPENROUTER_TIMEOUT_SECONDS))

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (compatible; GicaGenPricingBot/1.0)",
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        if self._http_referer:
            headers["HTTP-Referer"] = self._http_referer
        if self._app_title:
            headers["X-Title"] = self._app_title
        return headers

    def _get_json(self, path: str, *, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{self._base_url}/{path.lstrip('/')}"
        response = httpx.get(
            url,
            params=params,
            headers=self._headers(),
            timeout=self._timeout,
            follow_redirects=True,
        )
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    def fetch_models(
        self,
        *,
        output_modalities: str = "text",
        supported_parameters: str = "",
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {}
        if output_modalities:
            params["output_modalities"] = output_modalities
        if supported_parameters:
            params["supported_parameters"] = supported_parameters
        return self._get_json("models", params=params or None)

    def fetch_model_endpoints(self, author: str, slug: str) -> Dict[str, Any]:
        safe_author = str(author or "").strip()
        safe_slug = str(slug or "").strip()
        if not safe_author or not safe_slug:
            return {}
        return self._get_json(f"models/{safe_author}/{safe_slug}/endpoints")
