from __future__ import annotations

import datetime as dt
import html
import logging
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence

import httpx

from app.core.config import settings
from app.core.services.pricing.openrouter_client import OpenRouterPricingClient
from app.core.storage.json_store import JsonStore

logger = logging.getLogger(__name__)

_GEMINI_MODEL_LINE = re.compile(r"^gemini-[a-z0-9.\-]+$", re.IGNORECASE)
_OPENAI_PRICE_PATTERN = re.compile(
    r"&quot;(?P<model>[^&]+?)&quot;\],\[0,(?P<input>[0-9.]+|null)\],\[0,(?P<cached>[0-9.]+|null)\],\[0,(?P<output>[0-9.]+|null)\]"
)
_PRICE_NUMBER_PATTERN = re.compile(r"(?:USD|\$)\s*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)
_OPENAI_MODEL_LINE = re.compile(r"^(?:gpt|o[1-9]|o3|o4|codex)[a-z0-9.\- ]+$", re.IGNORECASE)
_OPENROUTER_GENERIC_MODELS = {"audio", "image", "text", "embeddings"}
_PROVIDER_ALIASES = {
    "gemini": "google",
    "google": "google",
    "openai": "openai",
    "mistral": "mistralai",
    "mistralai": "mistralai",
    "anthropic": "anthropic",
    "xai": "x-ai",
}
_OFFICIAL_FALLBACK_PROVIDERS = {
    "openai": "openai",
    "google": "gemini",
    "gemini": "gemini",
}


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _clean_line(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _normalize_numeric(value: Any) -> Optional[float]:
    if value in {None, "", "null"}:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _price_per_token_to_per_million(value: Any) -> Optional[float]:
    numeric = _normalize_numeric(value)
    if numeric is None:
        return None
    return round(numeric * 1_000_000, 12)


def _normalize_provider_alias(value: str) -> str:
    normalized = str(value or "").strip().lower()
    return _PROVIDER_ALIASES.get(normalized, normalized)


def _normalize_match_text(value: str) -> str:
    normalized = str(value or "").strip().lower()
    replacements = {
        "é": "e",
        "á": "a",
        "í": "i",
        "ó": "o",
        "ú": "u",
        "Ã©": "e",
        "Ã¡": "a",
        "Ã­": "i",
        "Ã³": "o",
        "Ãº": "u",
    }
    for source, target in replacements.items():
        normalized = normalized.replace(source, target)
    return normalized


def _infer_pricing_origin(raw: Dict[str, Any]) -> str:
    source_url = str(raw.get("source_url") or "").strip().lower()
    if str(raw.get("pricing_origin") or "").strip():
        return str(raw.get("pricing_origin") or "").strip()
    if "openrouter.ai/api/v1/models" in source_url:
        return "openrouter_api"
    if "openai.com" in source_url or "developers.openai.com" in source_url:
        return "official_openai"
    if "google.dev" in source_url or "ai.google.dev" in source_url:
        return "official_gemini"
    return "unknown"


def _build_pricing_mode(
    *,
    cached_input_price_per_1m_tokens: Optional[float],
    request_price: Optional[float],
    image_price: Optional[float],
) -> str:
    mode_parts: list[str] = []
    if cached_input_price_per_1m_tokens is not None:
        mode_parts.append("cached_input_supported")
    if request_price not in {None, 0.0}:
        mode_parts.append("request_priced")
    if image_price not in {None, 0.0}:
        mode_parts.append("image_priced")
    if not mode_parts:
        return "standard"
    return "+".join(mode_parts)


def _empty_pricing_record(provider: str, model: str) -> Dict[str, Any]:
    canonical_provider = _normalize_provider_alias(provider)
    return {
        "provider": canonical_provider,
        "model": str(model or "").strip(),
        "canonical_model_id": (
            f"{canonical_provider}/{str(model or '').strip()}".strip("/")
            if canonical_provider and str(model or "").strip()
            else ""
        ),
        "display_name": str(model or "").strip(),
        "input_price_per_1m_tokens": None,
        "output_price_per_1m_tokens": None,
        "cached_input_price_per_1m_tokens": None,
        "input_cache_write_price_per_1m_tokens": None,
        "request_price": None,
        "image_price": None,
        "web_search_price": None,
        "internal_reasoning_price_per_1m_tokens": None,
        "currency": "USD",
        "pricing_mode": "unavailable",
        "threshold_rule": "",
        "modality": "text",
        "source_url": "",
        "fetched_at": "",
        "pricing_source": "unavailable",
        "pricing_origin": "unavailable",
        "endpoint_provider": "",
        "endpoint_tag": "",
        "is_cached_fallback": False,
        "available": False,
    }


def _normalize_pricing_record(raw: Any) -> Dict[str, Any]:
    base = _empty_pricing_record(
        str(raw.get("provider") or "") if isinstance(raw, dict) else "",
        str(raw.get("model") or "") if isinstance(raw, dict) else "",
    )
    if not isinstance(raw, dict):
        return base
    base.update(
        {
            "provider": _normalize_provider_alias(str(raw.get("provider") or "")),
            "model": str(raw.get("model") or "").strip(),
            "canonical_model_id": str(raw.get("canonical_model_id") or "").strip(),
            "display_name": str(raw.get("display_name") or raw.get("model") or "").strip(),
            "input_price_per_1m_tokens": _normalize_numeric(raw.get("input_price_per_1m_tokens")),
            "output_price_per_1m_tokens": _normalize_numeric(raw.get("output_price_per_1m_tokens")),
            "cached_input_price_per_1m_tokens": _normalize_numeric(raw.get("cached_input_price_per_1m_tokens")),
            "input_cache_write_price_per_1m_tokens": _normalize_numeric(
                raw.get("input_cache_write_price_per_1m_tokens")
            ),
            "request_price": _normalize_numeric(raw.get("request_price")),
            "image_price": _normalize_numeric(raw.get("image_price")),
            "web_search_price": _normalize_numeric(raw.get("web_search_price")),
            "internal_reasoning_price_per_1m_tokens": _normalize_numeric(
                raw.get("internal_reasoning_price_per_1m_tokens")
            ),
            "currency": str(raw.get("currency") or "USD").strip() or "USD",
            "pricing_mode": str(raw.get("pricing_mode") or "unavailable").strip() or "unavailable",
            "threshold_rule": str(raw.get("threshold_rule") or "").strip(),
            "modality": str(raw.get("modality") or "text").strip() or "text",
            "source_url": str(raw.get("source_url") or "").strip(),
            "fetched_at": str(raw.get("fetched_at") or "").strip(),
            "pricing_source": str(raw.get("pricing_source") or "cached").strip() or "cached",
            "pricing_origin": _infer_pricing_origin(raw),
            "endpoint_provider": str(raw.get("endpoint_provider") or "").strip(),
            "endpoint_tag": str(raw.get("endpoint_tag") or "").strip(),
            "is_cached_fallback": bool(raw.get("is_cached_fallback")),
            "available": bool(raw.get("available")),
        }
    )
    if not base["canonical_model_id"] and base["provider"] and base["model"]:
        base["canonical_model_id"] = f"{base['provider']}/{base['model']}"
    if not base["display_name"]:
        base["display_name"] = base["model"]
    if base["input_price_per_1m_tokens"] is not None and base["output_price_per_1m_tokens"] is not None:
        base["available"] = True
    if base["pricing_mode"] == "unavailable" and base["available"]:
        base["pricing_mode"] = _build_pricing_mode(
            cached_input_price_per_1m_tokens=base["cached_input_price_per_1m_tokens"],
            request_price=base["request_price"],
            image_price=base["image_price"],
        )
    return base


class PricingService:
    def __init__(self, path: Optional[str] = None) -> None:
        self._store = JsonStore(path or settings.PRICING_STORE_PATH)
        self._ttl_seconds = max(300, int(settings.PRICING_CACHE_TTL_SECONDS))
        self._timeout = max(5, int(settings.PRICING_HTTP_TIMEOUT_SECONDS))
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._openrouter = OpenRouterPricingClient()
        self._bootstrap_cache()

    @staticmethod
    def _cache_key(provider: str, model: str) -> str:
        return f"{_normalize_provider_alias(provider)}::{str(model or '').strip().lower()}"

    def _bootstrap_cache(self) -> None:
        for item in self._store.read_list():
            record = _normalize_pricing_record(item)
            key = self._cache_key(record["provider"], record["model"])
            if not key.strip(":"):
                continue
            existing = self._cache.get(key)
            if existing is None or str(record.get("fetched_at") or "") >= str(existing.get("fetched_at") or ""):
                self._cache[key] = record

    def _persist_records(self, records: Iterable[Dict[str, Any]]) -> None:
        merged = {self._cache_key(item["provider"], item["model"]): dict(item) for item in self._cache.values()}
        for item in records:
            record = _normalize_pricing_record(item)
            key = self._cache_key(record["provider"], record["model"])
            if not key.strip(":"):
                continue
            merged[key] = record
            self._cache[key] = record
        self._store.write_list(sorted(merged.values(), key=lambda item: (item["provider"], item["model"])))

    def _is_fresh(self, record: Dict[str, Any]) -> bool:
        fetched_at = str(record.get("fetched_at") or "").strip()
        if not fetched_at:
            return False
        try:
            fetched = dt.datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
        except ValueError:
            return False
        age = dt.datetime.now(dt.timezone.utc) - fetched
        return age.total_seconds() <= self._ttl_seconds

    @classmethod
    def _lookup_candidates(cls, provider: str, model: str) -> list[tuple[str, str]]:
        raw_provider = _normalize_provider_alias(provider)
        raw_model = str(model or "").strip()
        if not raw_model:
            return []

        candidates: list[tuple[str, str]] = []

        def _push(candidate_provider: str, candidate_model: str) -> None:
            normalized_provider = _normalize_provider_alias(candidate_provider)
            normalized_model = str(candidate_model or "").strip()
            if not normalized_provider or not normalized_model:
                return
            pair = (normalized_provider, normalized_model)
            if pair not in candidates:
                candidates.append(pair)

        if "/" in raw_model:
            vendor, model_slug = raw_model.split("/", 1)
            _push(vendor, model_slug)
            if ":" in model_slug:
                _push(vendor, model_slug.split(":", 1)[0])

        if raw_provider and raw_provider != "openrouter":
            _push(raw_provider, raw_model)
            if ":" in raw_model:
                _push(raw_provider, raw_model.split(":", 1)[0])

        if raw_provider == "openrouter" and "/" in raw_model:
            vendor, model_slug = raw_model.split("/", 1)
            _push(vendor, model_slug)

        return candidates

    def _collect_candidates(self, provider: str, model: str) -> list[Dict[str, Any]]:
        candidates: list[Dict[str, Any]] = []
        for candidate_provider, candidate_model in self._lookup_candidates(provider, model):
            cached = self._cache.get(self._cache_key(candidate_provider, candidate_model))
            if cached:
                candidates.append(cached)
        return candidates

    def _pick_best_candidate(self, records: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not records:
            return None
        ranked = sorted(
            (_normalize_pricing_record(item) for item in records),
            key=lambda item: (
                item.get("pricing_origin") != "openrouter_api",
                not self._is_fresh(item),
                not bool(item.get("available")),
                str(item.get("fetched_at") or ""),
            ),
        )
        return ranked[0] if ranked else None

    def get_pricing(self, provider: str, model: str) -> Dict[str, Any]:
        if not str(provider or "").strip() or not str(model or "").strip():
            return _empty_pricing_record(provider, model)

        preferred = self._pick_best_candidate(self._collect_candidates(provider, model))
        if preferred and self._is_fresh(preferred):
            cached = dict(preferred)
            cached["pricing_source"] = "cached"
            cached["is_cached_fallback"] = False
            if cached.get("pricing_origin") == "openrouter_api":
                return self._enrich_openrouter_record(cached)
            return cached

        self._refresh_provider("openrouter")
        refreshed = self._pick_best_candidate(self._collect_candidates(provider, model))
        if refreshed and self._is_fresh(refreshed):
            latest = dict(refreshed)
            latest["pricing_source"] = "updated"
            latest["is_cached_fallback"] = False
            if latest.get("pricing_origin") == "openrouter_api":
                latest = self._enrich_openrouter_record(latest)
                latest["pricing_source"] = "updated"
                latest["is_cached_fallback"] = False
            return latest

        fallback_provider = self._official_fallback_provider(provider)
        if fallback_provider:
            self._refresh_provider(fallback_provider)
            official = self._pick_best_candidate(self._collect_candidates(provider, model))
            if official and self._is_fresh(official):
                official_record = dict(official)
                official_record["pricing_source"] = "updated"
                official_record["is_cached_fallback"] = False
                return official_record

        if preferred:
            fallback = dict(preferred)
            fallback["pricing_source"] = "cached"
            fallback["is_cached_fallback"] = True
            return fallback

        unavailable = _empty_pricing_record(provider, model)
        unavailable["source_url"] = self._source_url_for_provider(provider)
        unavailable["fetched_at"] = _utc_now()
        unavailable["pricing_source"] = "unavailable"
        self._persist_records([unavailable])
        return unavailable

    def list_pricing_catalog(
        self,
        *,
        providers: Optional[Iterable[str]] = None,
        refresh: bool = False,
        only_available: bool = False,
        source_preference: str = "openrouter",
    ) -> List[Dict[str, Any]]:
        provider_filters = [
            _normalize_provider_alias(str(item or "").strip())
            for item in (providers if providers is not None else [])
            if str(item or "").strip()
        ]
        source_mode = str(source_preference or "openrouter").strip().lower()

        if source_mode == "openrouter":
            if refresh or not self._has_fresh_records(origin="openrouter_api", providers=provider_filters or None):
                self._refresh_provider("openrouter")

        records = self._collect_catalog_records(
            providers=provider_filters or None,
            only_available=only_available,
            origin="openrouter_api" if source_mode == "openrouter" else None,
        )
        if records:
            return records

        if source_mode == "openrouter":
            fallback_refresh_targets = provider_filters or ["openai", "google"]
            for provider in fallback_refresh_targets:
                official_provider = self._official_fallback_provider(provider)
                if official_provider:
                    self._refresh_provider(official_provider)
            fallback_records = self._collect_catalog_records(
                providers=provider_filters or None,
                only_available=only_available,
                origin=None,
            )
            if fallback_records:
                return fallback_records

        return []

    def _collect_catalog_records(
        self,
        *,
        providers: Optional[Sequence[str]],
        only_available: bool,
        origin: Optional[str],
    ) -> List[Dict[str, Any]]:
        records: List[Dict[str, Any]] = []
        for record in self._cache.values():
            normalized = _normalize_pricing_record(record)
            provider = str(normalized.get("provider") or "").strip().lower()
            if providers and provider not in providers:
                continue
            if origin and str(normalized.get("pricing_origin") or "") != origin:
                continue
            if only_available and not normalized.get("available"):
                continue
            if not self._is_catalog_record_coherent(normalized):
                continue
            records.append(normalized)

        records.sort(key=lambda item: (str(item.get("provider") or ""), str(item.get("model") or "")))
        return records

    def _has_fresh_records(self, *, origin: Optional[str], providers: Optional[Sequence[str]]) -> bool:
        for record in self._cache.values():
            normalized = _normalize_pricing_record(record)
            provider = str(normalized.get("provider") or "").strip().lower()
            if providers and provider not in providers:
                continue
            if origin and str(normalized.get("pricing_origin") or "") != origin:
                continue
            if not self._is_catalog_record_coherent(normalized):
                continue
            if self._is_fresh(normalized):
                return True
        return False

    @staticmethod
    def _official_fallback_provider(provider: str) -> str:
        normalized = _normalize_provider_alias(provider)
        return _OFFICIAL_FALLBACK_PROVIDERS.get(normalized, "")

    @staticmethod
    def _is_catalog_record_coherent(record: Dict[str, Any]) -> bool:
        model = str(record.get("model") or "").strip()
        if not model:
            return False
        if model.lower() in _OPENROUTER_GENERIC_MODELS:
            return False
        if " " in model and str(record.get("pricing_origin") or "") == "openrouter_api":
            return False
        modality = str(record.get("modality") or "").strip().lower()
        return "text" in modality or modality in {"", "text"}

    def _refresh_provider(self, provider: str) -> bool:
        fetchers = {
            "openrouter": self._fetch_openrouter_catalog,
            "openai": self._fetch_openai_catalog,
            "gemini": self._fetch_gemini_catalog,
        }
        fetcher = fetchers.get(str(provider or "").strip().lower())
        if fetcher is None:
            return False
        try:
            records = fetcher()
        except Exception as exc:
            logger.warning("Pricing refresh failed for %s: %s", provider, exc)
            return False
        if not records:
            return False
        self._persist_records(records)
        return True

    @staticmethod
    def _source_url_for_provider(provider: str) -> str:
        provider_key = _normalize_provider_alias(provider)
        if provider_key == "openai":
            return settings.PRICING_OPENAI_URL
        if provider_key in {"google", "gemini"}:
            return settings.PRICING_GEMINI_URL
        return f"{settings.OPENROUTER_BASE_URL.rstrip('/')}/models"

    def _fetch_text(self, url: str) -> str:
        response = httpx.get(
            url,
            follow_redirects=True,
            timeout=self._timeout,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; GicaGenPricingBot/1.0)",
                "Accept-Language": "es-419,es;q=0.9,en;q=0.8",
            },
        )
        response.raise_for_status()
        return response.text

    def _fetch_openrouter_catalog(self) -> List[Dict[str, Any]]:
        payload = self._openrouter.fetch_models(output_modalities="text")
        fetched_at = _utc_now()
        records: List[Dict[str, Any]] = []
        for item in payload.get("data", []):
            if not isinstance(item, dict):
                continue
            model_id = str(item.get("id") or "").strip()
            if "/" not in model_id:
                continue
            provider, model = model_id.split("/", 1)
            if not provider or not model:
                continue
            architecture = item.get("architecture") if isinstance(item.get("architecture"), dict) else {}
            output_modalities = [str(value or "").strip().lower() for value in architecture.get("output_modalities", [])]
            if output_modalities and "text" not in output_modalities:
                continue
            pricing = item.get("pricing") if isinstance(item.get("pricing"), dict) else {}
            input_price = _price_per_token_to_per_million(pricing.get("prompt"))
            output_price = _price_per_token_to_per_million(pricing.get("completion"))
            cached_input_price = _price_per_token_to_per_million(pricing.get("input_cache_read"))
            input_cache_write = _price_per_token_to_per_million(pricing.get("input_cache_write"))
            request_price = _normalize_numeric(pricing.get("request"))
            image_price = _normalize_numeric(pricing.get("image"))
            web_search_price = _normalize_numeric(pricing.get("web_search"))
            internal_reasoning_price = _price_per_token_to_per_million(pricing.get("internal_reasoning"))
            record = {
                "provider": provider,
                "model": model,
                "canonical_model_id": model_id,
                "display_name": str(item.get("name") or model_id),
                "input_price_per_1m_tokens": input_price,
                "output_price_per_1m_tokens": output_price,
                "cached_input_price_per_1m_tokens": cached_input_price,
                "input_cache_write_price_per_1m_tokens": input_cache_write,
                "request_price": request_price,
                "image_price": image_price,
                "web_search_price": web_search_price,
                "internal_reasoning_price_per_1m_tokens": internal_reasoning_price,
                "currency": "USD",
                "pricing_mode": _build_pricing_mode(
                    cached_input_price_per_1m_tokens=cached_input_price,
                    request_price=request_price,
                    image_price=image_price,
                ),
                "threshold_rule": "",
                "modality": str(architecture.get("modality") or "text"),
                "source_url": f"{settings.OPENROUTER_BASE_URL.rstrip('/')}/models",
                "fetched_at": fetched_at,
                "pricing_source": "updated",
                "pricing_origin": "openrouter_api",
                "endpoint_provider": "",
                "endpoint_tag": "",
                "available": input_price is not None and output_price is not None,
            }
            if self._is_catalog_record_coherent(record):
                records.append(record)
        return records

    def _enrich_openrouter_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        normalized = _normalize_pricing_record(record)
        if normalized.get("pricing_origin") != "openrouter_api":
            return normalized
        if normalized.get("endpoint_provider") and self._is_fresh(normalized):
            return normalized

        canonical_model_id = str(normalized.get("canonical_model_id") or "").strip()
        if not canonical_model_id or "/" not in canonical_model_id:
            return normalized
        author, slug = canonical_model_id.split("/", 1)
        try:
            payload = self._openrouter.fetch_model_endpoints(author, slug)
        except Exception as exc:
            logger.warning("OpenRouter endpoint pricing fetch failed for %s: %s", canonical_model_id, exc)
            return normalized

        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        endpoints = data.get("endpoints") if isinstance(data.get("endpoints"), list) else []
        best_endpoint = self._pick_best_endpoint(endpoints)
        if not best_endpoint:
            return normalized

        endpoint_pricing = best_endpoint.get("pricing") if isinstance(best_endpoint.get("pricing"), dict) else {}
        input_price = _price_per_token_to_per_million(endpoint_pricing.get("prompt"))
        output_price = _price_per_token_to_per_million(endpoint_pricing.get("completion"))
        cached_input_price = _price_per_token_to_per_million(endpoint_pricing.get("input_cache_read"))
        input_cache_write = _price_per_token_to_per_million(endpoint_pricing.get("input_cache_write"))
        request_price = _normalize_numeric(endpoint_pricing.get("request"))
        image_price = _normalize_numeric(endpoint_pricing.get("image"))
        web_search_price = _normalize_numeric(endpoint_pricing.get("web_search"))
        internal_reasoning_price = _price_per_token_to_per_million(endpoint_pricing.get("internal_reasoning"))

        enriched = dict(normalized)
        if input_price is not None:
            enriched["input_price_per_1m_tokens"] = input_price
        if output_price is not None:
            enriched["output_price_per_1m_tokens"] = output_price
        enriched["cached_input_price_per_1m_tokens"] = cached_input_price
        enriched["input_cache_write_price_per_1m_tokens"] = input_cache_write
        enriched["request_price"] = request_price
        enriched["image_price"] = image_price
        enriched["web_search_price"] = web_search_price
        enriched["internal_reasoning_price_per_1m_tokens"] = internal_reasoning_price
        enriched["endpoint_provider"] = str(best_endpoint.get("provider_name") or "")
        enriched["endpoint_tag"] = str(best_endpoint.get("tag") or "")
        enriched["source_url"] = f"{settings.OPENROUTER_BASE_URL.rstrip('/')}/models/{author}/{slug}/endpoints"
        enriched["pricing_mode"] = _build_pricing_mode(
            cached_input_price_per_1m_tokens=enriched.get("cached_input_price_per_1m_tokens"),
            request_price=request_price,
            image_price=image_price,
        )
        enriched["available"] = (
            enriched.get("input_price_per_1m_tokens") is not None
            and enriched.get("output_price_per_1m_tokens") is not None
        )
        self._persist_records([enriched])
        persisted = self._cache.get(self._cache_key(enriched["provider"], enriched["model"]))
        return _normalize_pricing_record(persisted or enriched)

    @staticmethod
    def _pick_best_endpoint(endpoints: list[Any]) -> Optional[Dict[str, Any]]:
        priced_candidates: list[tuple[float, Dict[str, Any]]] = []
        for item in endpoints:
            if not isinstance(item, dict):
                continue
            pricing = item.get("pricing") if isinstance(item.get("pricing"), dict) else {}
            prompt = _normalize_numeric(pricing.get("prompt"))
            completion = _normalize_numeric(pricing.get("completion"))
            if prompt is None or completion is None:
                continue
            priced_candidates.append((prompt + completion, item))
        if not priced_candidates:
            return None
        priced_candidates.sort(key=lambda entry: entry[0])
        return priced_candidates[0][1]

    def _fetch_openai_catalog(self) -> List[Dict[str, Any]]:
        source_candidates = [
            settings.PRICING_OPENAI_URL,
            settings.PRICING_OPENAI_FALLBACK_URL,
        ]
        for source_url in source_candidates:
            if not str(source_url or "").strip():
                continue
            try:
                html_text = self._fetch_text(source_url)
            except Exception as exc:
                logger.warning("OpenAI pricing fetch failed for %s: %s", source_url, exc)
                continue
            fetched_at = _utc_now()
            records = self._parse_openai_embedded_catalog(html_text, source_url=source_url, fetched_at=fetched_at)
            if records:
                return records
            records = self._parse_openai_marketing_catalog(html_text, source_url=source_url, fetched_at=fetched_at)
            if records:
                return records
        return []

    def _parse_openai_embedded_catalog(
        self,
        html_text: str,
        *,
        source_url: str,
        fetched_at: str,
    ) -> List[Dict[str, Any]]:
        records: List[Dict[str, Any]] = []
        for match in _OPENAI_PRICE_PATTERN.finditer(html_text):
            model = match.group("model")
            input_price = _normalize_numeric(match.group("input"))
            cached_input_price = _normalize_numeric(match.group("cached"))
            output_price = _normalize_numeric(match.group("output"))
            records.append(
                {
                    "provider": "openai",
                    "model": model,
                    "canonical_model_id": f"openai/{model}",
                    "display_name": model,
                    "input_price_per_1m_tokens": input_price,
                    "output_price_per_1m_tokens": output_price,
                    "cached_input_price_per_1m_tokens": cached_input_price,
                    "currency": "USD",
                    "pricing_mode": _build_pricing_mode(
                        cached_input_price_per_1m_tokens=cached_input_price,
                        request_price=None,
                        image_price=None,
                    ),
                    "threshold_rule": "",
                    "modality": "text",
                    "source_url": source_url,
                    "fetched_at": fetched_at,
                    "pricing_source": "updated",
                    "pricing_origin": "official_openai",
                    "available": input_price is not None and output_price is not None,
                }
            )
        return records

    def _parse_openai_marketing_catalog(
        self,
        html_text: str,
        *,
        source_url: str,
        fetched_at: str,
    ) -> List[Dict[str, Any]]:
        text = html.unescape(re.sub(r"<[^>]+>", "\n", html_text))
        lines = [_clean_line(line).replace("â€‘", "-").replace("â€“", "-") for line in text.splitlines()]
        lines = [line for line in lines if line]
        records: List[Dict[str, Any]] = []
        seen_models: set[str] = set()

        for index, line in enumerate(lines):
            if not _OPENAI_MODEL_LINE.fullmatch(line):
                continue
            window = lines[index : min(index + 18, len(lines))]
            parsed = self._parse_openai_window(window)
            if not parsed:
                continue
            model_name = self._normalize_openai_model_name(line)
            if not model_name or model_name in seen_models:
                continue
            seen_models.add(model_name)
            records.append(
                {
                    "provider": "openai",
                    "model": model_name,
                    "canonical_model_id": f"openai/{model_name}",
                    "display_name": line,
                    "input_price_per_1m_tokens": parsed["input_price_per_1m_tokens"],
                    "output_price_per_1m_tokens": parsed["output_price_per_1m_tokens"],
                    "cached_input_price_per_1m_tokens": parsed["cached_input_price_per_1m_tokens"],
                    "currency": "USD",
                    "pricing_mode": _build_pricing_mode(
                        cached_input_price_per_1m_tokens=parsed["cached_input_price_per_1m_tokens"],
                        request_price=None,
                        image_price=None,
                    ),
                    "threshold_rule": "",
                    "modality": "text",
                    "source_url": source_url,
                    "fetched_at": fetched_at,
                    "pricing_source": "updated",
                    "pricing_origin": "official_openai",
                    "available": parsed["input_price_per_1m_tokens"] is not None
                    and parsed["output_price_per_1m_tokens"] is not None,
                }
            )
        return records

    @staticmethod
    def _normalize_openai_model_name(raw: str) -> str:
        normalized = _clean_line(raw).lower().replace("â€‘", "-").replace("â€“", "-")
        normalized = re.sub(r"\s+", "-", normalized)
        normalized = re.sub(r"-{2,}", "-", normalized)
        return normalized.strip("-")

    @classmethod
    def _parse_openai_window(cls, window: List[str]) -> Optional[Dict[str, Any]]:
        def _extract_amount(label: str) -> Optional[float]:
            lowered_label = _normalize_match_text(label)
            for index, line in enumerate(window):
                lowered = _normalize_match_text(line)
                if lowered.startswith(lowered_label):
                    for candidate in window[index : min(index + 4, len(window))]:
                        match = _PRICE_NUMBER_PATTERN.search(candidate)
                        if match:
                            return _normalize_numeric(match.group(1))
            return None

        input_price = _extract_amount("entrada")
        output_price = _extract_amount("salida")
        cached_input_price = _extract_amount("entrada en cache")
        if input_price is None or output_price is None:
            return None
        return {
            "input_price_per_1m_tokens": input_price,
            "output_price_per_1m_tokens": output_price,
            "cached_input_price_per_1m_tokens": cached_input_price,
        }

    def _fetch_gemini_catalog(self) -> List[Dict[str, Any]]:
        raw_html = self._fetch_text(settings.PRICING_GEMINI_URL)
        fetched_at = _utc_now()
        text = html.unescape(re.sub(r"<[^>]+>", "\n", raw_html))
        lines = [_clean_line(line) for line in text.splitlines()]
        lines = [line for line in lines if line]
        records: List[Dict[str, Any]] = []
        total_lines = len(lines)
        for index, line in enumerate(lines):
            if not _GEMINI_MODEL_LINE.fullmatch(line):
                continue
            window = lines[index : min(index + 40, total_lines)]
            if "Precio de entrada" not in window:
                continue
            parsed = self._parse_gemini_window(window)
            if not parsed:
                continue
            records.append(
                {
                    "provider": "google",
                    "model": line,
                    "canonical_model_id": f"google/{line}",
                    "display_name": line,
                    "input_price_per_1m_tokens": parsed["input_price_per_1m_tokens"],
                    "output_price_per_1m_tokens": parsed["output_price_per_1m_tokens"],
                    "cached_input_price_per_1m_tokens": parsed["cached_input_price_per_1m_tokens"],
                    "currency": "USD",
                    "pricing_mode": parsed["pricing_mode"],
                    "threshold_rule": parsed["threshold_rule"],
                    "modality": "text",
                    "source_url": settings.PRICING_GEMINI_URL,
                    "fetched_at": fetched_at,
                    "pricing_source": "updated",
                    "pricing_origin": "official_gemini",
                    "available": parsed["input_price_per_1m_tokens"] is not None
                    and parsed["output_price_per_1m_tokens"] is not None,
                }
            )
        return records

    @staticmethod
    def _price_candidates(lines: List[str]) -> List[Dict[str, Any]]:
        candidates: List[Dict[str, Any]] = []
        for line in lines:
            lowered = line.lower()
            if "sin costo" in lowered or "no disponible" in lowered:
                continue
            match = _PRICE_NUMBER_PATTERN.search(line)
            if not match:
                continue
            descriptor = _clean_line(line[match.end() :].strip(" ,.;:-"))
            candidates.append(
                {
                    "amount": _normalize_numeric(match.group(1)),
                    "descriptor": descriptor,
                    "raw": line,
                }
            )
        return candidates

    @classmethod
    def _pick_text_candidate(cls, candidates: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not candidates:
            return None
        text_first = [item for item in candidates if "audio" not in str(item.get("descriptor") or "").lower()]
        return text_first[0] if text_first else candidates[0]

    @classmethod
    def _parse_gemini_window(cls, window: List[str]) -> Optional[Dict[str, Any]]:
        markers = {
            "input": "Precio de entrada",
            "output": "Precio de salida",
            "cache": "Precio del almacenamiento de contexto en cache",
        }
        sections: Dict[str, List[str]] = {"input": [], "output": [], "cache": []}
        current_key = ""
        for line in window:
            normalized_line = _normalize_match_text(line)
            normalized_markers = {key: _normalize_match_text(value) for key, value in markers.items()}
            if normalized_line in normalized_markers.values():
                current_key = next(key for key, value in normalized_markers.items() if value == normalized_line)
                continue
            if current_key and _normalize_match_text(line).startswith("precio de "):
                current_key = ""
            if current_key:
                sections[current_key].append(line)

        input_candidates = cls._price_candidates(sections["input"])
        output_candidates = cls._price_candidates(sections["output"])
        cache_candidates = cls._price_candidates(sections["cache"])
        selected_input = cls._pick_text_candidate(input_candidates)
        selected_output = cls._pick_text_candidate(output_candidates)
        selected_cache = cls._pick_text_candidate(cache_candidates)
        if not selected_input or not selected_output:
            return None

        threshold_descriptors = [
            item["descriptor"]
            for item in input_candidates + output_candidates
            if str(item.get("descriptor") or "").strip()
        ]
        threshold_descriptors = list(dict.fromkeys(threshold_descriptors))
        pricing_mode = "tiered" if len(input_candidates) > 1 or len(output_candidates) > 1 else "standard"
        return {
            "input_price_per_1m_tokens": selected_input.get("amount"),
            "output_price_per_1m_tokens": selected_output.get("amount"),
            "cached_input_price_per_1m_tokens": selected_cache.get("amount") if selected_cache else None,
            "pricing_mode": pricing_mode,
            "threshold_rule": " | ".join(threshold_descriptors),
        }
