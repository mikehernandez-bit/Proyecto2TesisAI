from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Iterable, Mapping, Optional

from app.core.services.ai.token_usage import empty_token_usage_report, normalize_token_usage_report

_MICRO_TOKENS = Decimal("1000000")
_COST_QUANTIZE = Decimal("0.00000001")


def _optional_float(value: Any) -> Optional[float]:
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _round_cost(value: Decimal) -> float:
    return float(value.quantize(_COST_QUANTIZE, rounding=ROUND_HALF_UP))


def _decimal_or_zero(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0")


def _provider_label(provider: str) -> str:
    normalized = str(provider or "").strip().lower()
    labels = {
        "openai": "OpenAI",
        "gemini": "Google / Gemini",
        "google": "Google / Gemini",
        "mistral": "Mistral AI",
        "mistralai": "Mistral AI",
        "anthropic": "Anthropic",
        "x-ai": "xAI",
    }
    return labels.get(normalized, normalized.title() if normalized else "-")


def _normalize_provider_id(provider: str) -> str:
    normalized = str(provider or "").strip().lower()
    aliases = {
        "gemini": "google",
        "mistral": "mistralai",
    }
    return aliases.get(normalized, normalized)


def _usage_source_label(usage_report: Mapping[str, Any]) -> str:
    reported_calls = max(0, int(usage_report.get("reported_calls") or 0))
    estimated_calls = max(0, int(usage_report.get("estimated_calls") or 0))
    if reported_calls and estimated_calls:
        return "mixed"
    if estimated_calls:
        return "estimated"
    if reported_calls:
        return "reported_by_provider"
    return "unavailable"


def _build_project_origin(usage_report: Mapping[str, Any]) -> Dict[str, str]:
    providers = usage_report.get("providers")
    if not isinstance(providers, list):
        return {"provider": "", "model": ""}
    best = max(
        (item for item in providers if isinstance(item, dict)),
        key=lambda item: int(item.get("total_tokens") or 0),
        default=None,
    )
    if not isinstance(best, dict):
        return {"provider": "", "model": ""}
    return {
        "provider": _normalize_provider_id(str(best.get("provider") or "")),
        "model": str(best.get("model") or ""),
    }


def _normalize_budget_usage(raw_usage: Mapping[str, Any] | None) -> Dict[str, Any]:
    if not isinstance(raw_usage, Mapping):
        return empty_token_usage_report()
    if isinstance(raw_usage.get("attempts"), list):
        return normalize_token_usage_report(raw_usage)
    normalized = empty_token_usage_report()
    normalized.update(
        {
            "input_tokens_total": max(0, int(raw_usage.get("input_tokens_total") or 0)),
            "output_tokens_total": max(0, int(raw_usage.get("output_tokens_total") or 0)),
            "total_tokens": max(0, int(raw_usage.get("total_tokens") or 0)),
            "calls_total": max(0, int(raw_usage.get("calls_total") or 0)),
            "reported_calls": max(0, int(raw_usage.get("reported_calls") or 0)),
            "estimated_calls": max(0, int(raw_usage.get("estimated_calls") or 0)),
            "has_estimated_usage": bool(raw_usage.get("has_estimated_usage")),
            "sections": [item for item in raw_usage.get("sections", []) if isinstance(item, Mapping)],
            "providers": [item for item in raw_usage.get("providers", []) if isinstance(item, Mapping)],
        }
    )
    return normalized


def _group_catalog(records: Iterable[Mapping[str, Any]]) -> list[Dict[str, Any]]:
    grouped: dict[str, Dict[str, Any]] = {}
    for item in records:
        provider = _normalize_provider_id(str(item.get("provider") or "").strip().lower())
        if not provider:
            continue
        bucket = grouped.setdefault(
            provider,
            {
                "id": provider,
                "label": _provider_label(provider),
                "models": [],
            },
        )
        bucket["models"].append(
            {
                "provider": provider,
                "model": str(item.get("model") or ""),
                "canonical_model_id": str(item.get("canonical_model_id") or ""),
                "display_name": str(item.get("display_name") or item.get("model") or ""),
                "input_price_per_1m_tokens": _optional_float(item.get("input_price_per_1m_tokens")),
                "output_price_per_1m_tokens": _optional_float(item.get("output_price_per_1m_tokens")),
                "cached_input_price_per_1m_tokens": _optional_float(item.get("cached_input_price_per_1m_tokens")),
                "input_cache_write_price_per_1m_tokens": _optional_float(
                    item.get("input_cache_write_price_per_1m_tokens")
                ),
                "request_price": _optional_float(item.get("request_price")),
                "image_price": _optional_float(item.get("image_price")),
                "web_search_price": _optional_float(item.get("web_search_price")),
                "internal_reasoning_price_per_1m_tokens": _optional_float(
                    item.get("internal_reasoning_price_per_1m_tokens")
                ),
                "currency": str(item.get("currency") or "USD"),
                "pricing_mode": str(item.get("pricing_mode") or "standard"),
                "threshold_rule": str(item.get("threshold_rule") or ""),
                "modality": str(item.get("modality") or "text"),
                "source_url": str(item.get("source_url") or ""),
                "fetched_at": str(item.get("fetched_at") or ""),
                "pricing_source": str(item.get("pricing_source") or "cached"),
                "pricing_origin": str(item.get("pricing_origin") or ""),
                "endpoint_provider": str(item.get("endpoint_provider") or ""),
                "endpoint_tag": str(item.get("endpoint_tag") or ""),
                "is_cached_fallback": bool(item.get("is_cached_fallback")),
                "available": bool(item.get("available")),
            }
        )
    grouped_list = list(grouped.values())
    grouped_list.sort(key=lambda item: str(item.get("label") or item.get("id") or ""))
    for item in grouped_list:
        item["models"].sort(key=lambda model: str(model.get("display_name") or model.get("model") or ""))
    return grouped_list


def _select_provider_model(
    catalog_records: list[Dict[str, Any]],
    *,
    requested_provider: str = "",
    requested_model: str = "",
    origin_provider: str = "",
    origin_model: str = "",
) -> tuple[str, str]:
    available_pairs = [
        (_normalize_provider_id(str(item.get("provider") or "").strip().lower()), str(item.get("model") or "").strip())
        for item in catalog_records
        if bool(item.get("available"))
    ]
    for provider, model in [
        (_normalize_provider_id(str(requested_provider or "").strip().lower()), str(requested_model or "").strip()),
        (_normalize_provider_id(str(origin_provider or "").strip().lower()), str(origin_model or "").strip()),
    ]:
        if provider and model and (provider, model) in available_pairs:
            return provider, model
    if available_pairs:
        return available_pairs[0]
    return _normalize_provider_id(str(requested_provider or origin_provider or "").strip().lower()), str(
        requested_model or origin_model or ""
    ).strip()


def _build_cost_entry(
    *,
    input_tokens: int,
    output_tokens: int,
    pricing: Mapping[str, Any],
) -> Dict[str, Any]:
    input_price = _optional_float(pricing.get("input_price_per_1m_tokens"))
    output_price = _optional_float(pricing.get("output_price_per_1m_tokens"))
    available = input_price is not None and output_price is not None
    input_cost = Decimal("0")
    output_cost = Decimal("0")
    if available:
        input_cost = (Decimal(max(0, int(input_tokens or 0))) / _MICRO_TOKENS) * _decimal_or_zero(input_price)
        output_cost = (Decimal(max(0, int(output_tokens or 0))) / _MICRO_TOKENS) * _decimal_or_zero(output_price)
    return {
        "input_tokens": max(0, int(input_tokens or 0)),
        "output_tokens": max(0, int(output_tokens or 0)),
        "total_tokens": max(0, int(input_tokens or 0)) + max(0, int(output_tokens or 0)),
        "canonical_model_id": str(pricing.get("canonical_model_id") or ""),
        "display_name": str(pricing.get("display_name") or pricing.get("model") or ""),
        "input_price_per_1m_tokens": input_price,
        "output_price_per_1m_tokens": output_price,
        "cached_input_price_per_1m_tokens": _optional_float(pricing.get("cached_input_price_per_1m_tokens")),
        "input_cache_write_price_per_1m_tokens": _optional_float(pricing.get("input_cache_write_price_per_1m_tokens")),
        "request_price": _optional_float(pricing.get("request_price")),
        "image_price": _optional_float(pricing.get("image_price")),
        "web_search_price": _optional_float(pricing.get("web_search_price")),
        "internal_reasoning_price_per_1m_tokens": _optional_float(
            pricing.get("internal_reasoning_price_per_1m_tokens")
        ),
        "estimated_input_cost": _round_cost(input_cost),
        "estimated_output_cost": _round_cost(output_cost),
        "estimated_total_cost": _round_cost(input_cost + output_cost),
        "currency": str(pricing.get("currency") or "USD"),
        "pricing_mode": str(pricing.get("pricing_mode") or "unavailable"),
        "threshold_rule": str(pricing.get("threshold_rule") or ""),
        "modality": str(pricing.get("modality") or "text"),
        "source_url": str(pricing.get("source_url") or ""),
        "pricing_fetched_at": str(pricing.get("fetched_at") or ""),
        "pricing_source": str(pricing.get("pricing_source") or "unavailable"),
        "pricing_origin": str(pricing.get("pricing_origin") or "unavailable"),
        "endpoint_provider": str(pricing.get("endpoint_provider") or ""),
        "endpoint_tag": str(pricing.get("endpoint_tag") or ""),
        "is_cached_fallback": bool(pricing.get("is_cached_fallback")),
        "available": bool(available and pricing.get("available", True)),
    }


def build_project_budget_report(
    project: Mapping[str, Any] | None,
    *,
    pricing_service: Any,
    selected_provider: str = "",
    selected_model: str = "",
    refresh_pricing: bool = False,
) -> Dict[str, Any]:
    safe_project = project if isinstance(project, Mapping) else {}
    raw_usage = safe_project.get("token_usage")
    if not isinstance(raw_usage, Mapping):
        raw_usage = safe_project.get("ai_result", {}).get("tokenUsage") if isinstance(safe_project.get("ai_result"), Mapping) else {}
    usage_report = _normalize_budget_usage(raw_usage if isinstance(raw_usage, Mapping) else empty_token_usage_report())
    project_origin = _build_project_origin(usage_report)

    catalog_records = pricing_service.list_pricing_catalog(
        refresh=refresh_pricing,
        only_available=True,
        source_preference="openrouter",
    )
    provider, model = _select_provider_model(
        catalog_records,
        requested_provider=selected_provider,
        requested_model=selected_model,
        origin_provider=project_origin["provider"],
        origin_model=project_origin["model"],
    )
    pricing = pricing_service.get_pricing(provider, model) if provider and model else {}
    summary_cost = _build_cost_entry(
        input_tokens=max(0, int(usage_report.get("input_tokens_total") or 0)),
        output_tokens=max(0, int(usage_report.get("output_tokens_total") or 0)),
        pricing=pricing,
    )

    sections_payload: list[Dict[str, Any]] = []
    sections = usage_report.get("sections")
    if isinstance(sections, list):
        for item in sections:
            if not isinstance(item, Mapping):
                continue
            section_cost = _build_cost_entry(
                input_tokens=max(0, int(item.get("input_tokens_total") or 0)),
                output_tokens=max(0, int(item.get("output_tokens_total") or 0)),
                pricing=pricing,
            )
            sections_payload.append(
                {
                    "section_id": str(item.get("section_id") or ""),
                    "section_path": str(item.get("section_path") or ""),
                    "section_title": str(item.get("section_title") or ""),
                    **section_cost,
                }
            )

    comparisons = []
    for record in catalog_records:
        comparison = _build_cost_entry(
            input_tokens=max(0, int(usage_report.get("input_tokens_total") or 0)),
            output_tokens=max(0, int(usage_report.get("output_tokens_total") or 0)),
            pricing=record,
        )
        comparisons.append(
            {
                "provider": str(record.get("provider") or ""),
                "provider_label": _provider_label(str(record.get("provider") or "")),
                "model": str(record.get("model") or ""),
                "display_name": str(record.get("display_name") or record.get("model") or ""),
                "canonical_model_id": str(record.get("canonical_model_id") or ""),
                **comparison,
            }
        )
    comparisons.sort(
        key=lambda item: (
            not bool(item.get("available")),
            float(item.get("estimated_total_cost") or 0.0),
            str(item.get("provider") or ""),
            str(item.get("model") or ""),
        )
    )

    return {
        "project": {
            "id": str(safe_project.get("id") or ""),
            "title": str(safe_project.get("title") or "Proyecto sin titulo"),
            "format_name": str(safe_project.get("format_name") or safe_project.get("format_id") or ""),
            "status": str(safe_project.get("status") or ""),
            "original_provider": project_origin["provider"],
            "original_model": project_origin["model"],
        },
        "usage": {
            "input_tokens_total": max(0, int(usage_report.get("input_tokens_total") or 0)),
            "output_tokens_total": max(0, int(usage_report.get("output_tokens_total") or 0)),
            "total_tokens": max(0, int(usage_report.get("total_tokens") or 0)),
            "calls_total": max(0, int(usage_report.get("calls_total") or 0)),
            "reported_calls": max(0, int(usage_report.get("reported_calls") or 0)),
            "estimated_calls": max(0, int(usage_report.get("estimated_calls") or 0)),
            "usage_source": _usage_source_label(usage_report),
            "has_estimated_usage": bool(usage_report.get("has_estimated_usage")),
            "sections": sections_payload,
        },
        "catalog": {
            "providers": _group_catalog(catalog_records),
        },
        "selected_pricing": {
            "provider": provider,
            "provider_label": _provider_label(provider),
            "model": model,
            "canonical_model_id": str(pricing.get("canonical_model_id") or ""),
            "display_name": str(pricing.get("display_name") or pricing.get("model") or ""),
            "input_price_per_1m_tokens": _optional_float(pricing.get("input_price_per_1m_tokens")),
            "output_price_per_1m_tokens": _optional_float(pricing.get("output_price_per_1m_tokens")),
            "cached_input_price_per_1m_tokens": _optional_float(pricing.get("cached_input_price_per_1m_tokens")),
            "input_cache_write_price_per_1m_tokens": _optional_float(
                pricing.get("input_cache_write_price_per_1m_tokens")
            ),
            "request_price": _optional_float(pricing.get("request_price")),
            "image_price": _optional_float(pricing.get("image_price")),
            "web_search_price": _optional_float(pricing.get("web_search_price")),
            "internal_reasoning_price_per_1m_tokens": _optional_float(
                pricing.get("internal_reasoning_price_per_1m_tokens")
            ),
            "currency": str(pricing.get("currency") or "USD"),
            "pricing_mode": str(pricing.get("pricing_mode") or "unavailable"),
            "threshold_rule": str(pricing.get("threshold_rule") or ""),
            "modality": str(pricing.get("modality") or "text"),
            "source_url": str(pricing.get("source_url") or ""),
            "fetched_at": str(pricing.get("fetched_at") or ""),
            "pricing_source": str(pricing.get("pricing_source") or "unavailable"),
            "pricing_origin": str(pricing.get("pricing_origin") or "unavailable"),
            "endpoint_provider": str(pricing.get("endpoint_provider") or ""),
            "endpoint_tag": str(pricing.get("endpoint_tag") or ""),
            "is_cached_fallback": bool(pricing.get("is_cached_fallback")),
            "available": bool(pricing.get("available")),
        },
        "estimate": {
            "provider": provider,
            "provider_label": _provider_label(provider),
            "model": model,
            "display_name": str(pricing.get("display_name") or pricing.get("model") or model),
            **summary_cost,
            "sections": sections_payload,
        },
        "comparisons": comparisons,
    }
