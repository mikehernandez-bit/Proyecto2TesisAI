from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Iterable, Optional

_MICRO_TOKENS = Decimal("1000000")
_COST_QUANTIZE = Decimal("0.00000001")


def _decimal_or_zero(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0")


def _optional_float(value: Any) -> Optional[float]:
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _round_cost(value: Decimal) -> float:
    return float(value.quantize(_COST_QUANTIZE, rounding=ROUND_HALF_UP))


def _pricing_source_label(values: Iterable[str]) -> str:
    normalized = {str(item or "").strip().lower() for item in values if str(item or "").strip()}
    if not normalized:
        return "unavailable"
    if len(normalized) == 1:
        return normalized.pop()
    return "mixed"


def empty_generation_cost_snapshot() -> Dict[str, Any]:
    return {
        "currency": "USD",
        "input_cost_total_usd": 0.0,
        "output_cost_total_usd": 0.0,
        "total_cost_usd": 0.0,
        "priced_calls": 0,
        "unpriced_calls": 0,
        "has_unpriced_calls": False,
        "pricing_source": "unavailable",
        "pricing_fetched_at": "",
        "current_section": {
            "section_id": "",
            "section_path": "",
            "section_title": "",
            "estimated_cost_usd": 0.0,
            "pricing_source": "unavailable",
        },
    }


def empty_generation_cost_report() -> Dict[str, Any]:
    return {
        **empty_generation_cost_snapshot(),
        "calls": [],
        "sections": [],
        "models": [],
    }


def normalize_generation_cost_snapshot(raw: Any) -> Dict[str, Any]:
    base = empty_generation_cost_snapshot()
    if not isinstance(raw, dict):
        return base
    current_section_raw = raw.get("current_section")
    current_section = (
        {
            "section_id": str(current_section_raw.get("section_id") or ""),
            "section_path": str(current_section_raw.get("section_path") or ""),
            "section_title": str(current_section_raw.get("section_title") or ""),
            "estimated_cost_usd": _optional_float(current_section_raw.get("estimated_cost_usd")) or 0.0,
            "pricing_source": str(current_section_raw.get("pricing_source") or "unavailable"),
        }
        if isinstance(current_section_raw, dict)
        else dict(base["current_section"])
    )
    base.update(
        {
            "currency": str(raw.get("currency") or "USD"),
            "input_cost_total_usd": _optional_float(raw.get("input_cost_total_usd")) or 0.0,
            "output_cost_total_usd": _optional_float(raw.get("output_cost_total_usd")) or 0.0,
            "total_cost_usd": _optional_float(raw.get("total_cost_usd")) or 0.0,
            "priced_calls": max(0, int(raw.get("priced_calls") or 0)),
            "unpriced_calls": max(0, int(raw.get("unpriced_calls") or 0)),
            "has_unpriced_calls": bool(raw.get("has_unpriced_calls")),
            "pricing_source": str(raw.get("pricing_source") or "unavailable"),
            "pricing_fetched_at": str(raw.get("pricing_fetched_at") or ""),
            "current_section": current_section,
        }
    )
    return base


def normalize_generation_cost_report(raw: Any) -> Dict[str, Any]:
    base = empty_generation_cost_report()
    if not isinstance(raw, dict):
        return base
    base.update(normalize_generation_cost_snapshot(raw))

    calls: list[Dict[str, Any]] = []
    if isinstance(raw.get("calls"), list):
        for item in raw["calls"]:
            if not isinstance(item, dict):
                continue
            calls.append(
                {
                    "provider": str(item.get("provider") or ""),
                    "model": str(item.get("model") or ""),
                    "section_id": str(item.get("section_id") or ""),
                    "section_path": str(item.get("section_path") or ""),
                    "section_title": str(item.get("section_title") or ""),
                    "attempt": max(0, int(item.get("attempt") or 0)),
                    "input_tokens": max(0, int(item.get("input_tokens") or 0)),
                    "output_tokens": max(0, int(item.get("output_tokens") or 0)),
                    "total_tokens": max(0, int(item.get("total_tokens") or 0)),
                    "input_cost_usd": _optional_float(item.get("input_cost_usd")) or 0.0,
                    "output_cost_usd": _optional_float(item.get("output_cost_usd")) or 0.0,
                    "estimated_cost_usd": _optional_float(item.get("estimated_cost_usd")) or 0.0,
                    "pricing_source": str(item.get("pricing_source") or "unavailable"),
                    "pricing_fetched_at": str(item.get("pricing_fetched_at") or ""),
                    "currency": str(item.get("currency") or "USD"),
                    "estimated": bool(item.get("estimated")),
                    "usage_source": str(item.get("usage_source") or ""),
                    "available": bool(item.get("available")),
                }
            )

    sections: list[Dict[str, Any]] = []
    if isinstance(raw.get("sections"), list):
        for item in raw["sections"]:
            if not isinstance(item, dict):
                continue
            sections.append(
                {
                    "section_id": str(item.get("section_id") or ""),
                    "section_path": str(item.get("section_path") or ""),
                    "section_title": str(item.get("section_title") or ""),
                    "provider": str(item.get("provider") or ""),
                    "model": str(item.get("model") or ""),
                    "input_tokens": max(0, int(item.get("input_tokens") or 0)),
                    "output_tokens": max(0, int(item.get("output_tokens") or 0)),
                    "total_tokens": max(0, int(item.get("total_tokens") or 0)),
                    "input_cost_usd": _optional_float(item.get("input_cost_usd")) or 0.0,
                    "output_cost_usd": _optional_float(item.get("output_cost_usd")) or 0.0,
                    "estimated_cost_usd": _optional_float(item.get("estimated_cost_usd")) or 0.0,
                    "attempt_count": max(0, int(item.get("attempt_count") or 0)),
                    "pricing_source": str(item.get("pricing_source") or "unavailable"),
                    "pricing_fetched_at": str(item.get("pricing_fetched_at") or ""),
                    "currency": str(item.get("currency") or "USD"),
                    "available": bool(item.get("available")),
                }
            )

    models: list[Dict[str, Any]] = []
    if isinstance(raw.get("models"), list):
        for item in raw["models"]:
            if not isinstance(item, dict):
                continue
            models.append(
                {
                    "provider": str(item.get("provider") or ""),
                    "model": str(item.get("model") or ""),
                    "input_tokens_total": max(0, int(item.get("input_tokens_total") or 0)),
                    "output_tokens_total": max(0, int(item.get("output_tokens_total") or 0)),
                    "total_tokens": max(0, int(item.get("total_tokens") or 0)),
                    "estimated_cost_usd": _optional_float(item.get("estimated_cost_usd")) or 0.0,
                    "priced_calls": max(0, int(item.get("priced_calls") or 0)),
                    "unpriced_calls": max(0, int(item.get("unpriced_calls") or 0)),
                    "pricing_source": str(item.get("pricing_source") or "unavailable"),
                    "pricing_fetched_at": str(item.get("pricing_fetched_at") or ""),
                    "currency": str(item.get("currency") or "USD"),
                    "available": bool(item.get("available")),
                }
            )

    base["calls"] = calls
    base["sections"] = sections
    base["models"] = models
    return base


def generation_cost_snapshot(report: Any) -> Dict[str, Any]:
    normalized = normalize_generation_cost_report(report)
    return normalize_generation_cost_snapshot(normalized)


def build_generation_cost_report(
    usage_report: Any,
    *,
    pricing_service: Any,
) -> Dict[str, Any]:
    usage = usage_report if isinstance(usage_report, dict) else {}
    attempts = usage.get("attempts")
    attempts = [item for item in attempts if isinstance(item, dict)] if isinstance(attempts, list) else []
    if not attempts:
        return empty_generation_cost_report()

    report = empty_generation_cost_report()
    call_entries: list[Dict[str, Any]] = []
    section_map: dict[str, Dict[str, Any]] = {}
    model_map: dict[str, Dict[str, Any]] = {}
    pricing_sources: list[str] = []
    pricing_fetched_candidates: list[str] = []
    input_total = Decimal("0")
    output_total = Decimal("0")

    for attempt in attempts:
        provider = str(attempt.get("provider") or "").strip()
        model = str(attempt.get("model") or "").strip()
        section_id = str(attempt.get("section_id") or "").strip()
        section_path = str(attempt.get("section_path") or "").strip()
        section_title = str(attempt.get("section_title") or section_path.split("/")[-1] if section_path else "").strip()
        input_tokens = max(0, int(attempt.get("input_tokens") or 0))
        output_tokens = max(0, int(attempt.get("output_tokens") or 0))
        total_tokens = max(0, int(attempt.get("total_tokens") or 0))

        pricing = pricing_service.get_pricing(provider, model)
        input_price = _optional_float(pricing.get("input_price_per_1m_tokens"))
        output_price = _optional_float(pricing.get("output_price_per_1m_tokens"))
        input_cost = Decimal("0")
        output_cost = Decimal("0")
        available = input_price is not None and output_price is not None
        if available:
            input_cost = (Decimal(input_tokens) / _MICRO_TOKENS) * _decimal_or_zero(input_price)
            output_cost = (Decimal(output_tokens) / _MICRO_TOKENS) * _decimal_or_zero(output_price)
            pricing_sources.append(str(pricing.get("pricing_source") or "cached"))
            fetched_at = str(pricing.get("fetched_at") or "")
            if fetched_at:
                pricing_fetched_candidates.append(fetched_at)
        else:
            pricing_sources.append("unavailable")

        total_cost = input_cost + output_cost
        input_total += input_cost
        output_total += output_cost
        if available:
            report["priced_calls"] += 1
        else:
            report["unpriced_calls"] += 1

        call_entry = {
            "provider": provider,
            "model": model,
            "section_id": section_id,
            "section_path": section_path,
            "section_title": section_title,
            "attempt": max(0, int(attempt.get("attempt") or 0)),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "input_cost_usd": _round_cost(input_cost),
            "output_cost_usd": _round_cost(output_cost),
            "estimated_cost_usd": _round_cost(total_cost),
            "pricing_source": str(pricing.get("pricing_source") or "unavailable"),
            "pricing_fetched_at": str(pricing.get("fetched_at") or ""),
            "currency": str(pricing.get("currency") or "USD"),
            "estimated": bool(attempt.get("estimated")),
            "usage_source": str(attempt.get("source") or ""),
            "available": available,
        }
        call_entries.append(call_entry)

        section_key = section_id or section_path or f"section:{len(section_map)}"
        section_entry = section_map.setdefault(
            section_key,
            {
                "section_id": section_id,
                "section_path": section_path,
                "section_title": section_title,
                "provider": provider,
                "model": model,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "input_cost_usd": 0.0,
                "output_cost_usd": 0.0,
                "estimated_cost_usd": 0.0,
                "attempt_count": 0,
                "pricing_source": "unavailable",
                "pricing_fetched_at": "",
                "currency": str(pricing.get("currency") or "USD"),
                "available": False,
            },
        )
        section_entry["provider"] = provider or section_entry["provider"]
        section_entry["model"] = model or section_entry["model"]
        section_entry["input_tokens"] += input_tokens
        section_entry["output_tokens"] += output_tokens
        section_entry["total_tokens"] += total_tokens
        section_entry["input_cost_usd"] = _round_cost(_decimal_or_zero(section_entry["input_cost_usd"]) + input_cost)
        section_entry["output_cost_usd"] = _round_cost(_decimal_or_zero(section_entry["output_cost_usd"]) + output_cost)
        section_entry["estimated_cost_usd"] = _round_cost(
            _decimal_or_zero(section_entry["estimated_cost_usd"]) + total_cost
        )
        section_entry["attempt_count"] += 1
        section_entry["pricing_source"] = _pricing_source_label(
            [section_entry["pricing_source"], call_entry["pricing_source"]]
        )
        section_entry["pricing_fetched_at"] = max(
            section_entry.get("pricing_fetched_at") or "",
            call_entry["pricing_fetched_at"],
        )
        section_entry["available"] = bool(section_entry["available"] or available)

        model_key = f"{provider}:{model}"
        model_entry = model_map.setdefault(
            model_key,
            {
                "provider": provider,
                "model": model,
                "input_tokens_total": 0,
                "output_tokens_total": 0,
                "total_tokens": 0,
                "estimated_cost_usd": 0.0,
                "priced_calls": 0,
                "unpriced_calls": 0,
                "pricing_source": "unavailable",
                "pricing_fetched_at": "",
                "currency": str(pricing.get("currency") or "USD"),
                "available": False,
            },
        )
        model_entry["input_tokens_total"] += input_tokens
        model_entry["output_tokens_total"] += output_tokens
        model_entry["total_tokens"] += total_tokens
        model_entry["estimated_cost_usd"] = _round_cost(
            _decimal_or_zero(model_entry["estimated_cost_usd"]) + total_cost
        )
        if available:
            model_entry["priced_calls"] += 1
        else:
            model_entry["unpriced_calls"] += 1
        model_entry["pricing_source"] = _pricing_source_label(
            [model_entry["pricing_source"], call_entry["pricing_source"]]
        )
        model_entry["pricing_fetched_at"] = max(
            model_entry.get("pricing_fetched_at") or "",
            call_entry["pricing_fetched_at"],
        )
        model_entry["available"] = bool(model_entry["available"] or available)

    current_section_raw = usage.get("current_section")
    current_section_id = str(current_section_raw.get("section_id") or "") if isinstance(current_section_raw, dict) else ""
    current_section_path = str(current_section_raw.get("section_path") or "") if isinstance(current_section_raw, dict) else ""
    current_section_key = current_section_id or current_section_path
    current_section = section_map.get(current_section_key) or (list(section_map.values())[-1] if section_map else {})

    report["input_cost_total_usd"] = _round_cost(input_total)
    report["output_cost_total_usd"] = _round_cost(output_total)
    report["total_cost_usd"] = _round_cost(input_total + output_total)
    report["has_unpriced_calls"] = report["unpriced_calls"] > 0
    report["pricing_source"] = _pricing_source_label(pricing_sources)
    report["pricing_fetched_at"] = max(pricing_fetched_candidates) if pricing_fetched_candidates else ""
    report["current_section"] = {
        "section_id": str(current_section.get("section_id") or ""),
        "section_path": str(current_section.get("section_path") or ""),
        "section_title": str(current_section.get("section_title") or ""),
        "estimated_cost_usd": _optional_float(current_section.get("estimated_cost_usd")) or 0.0,
        "pricing_source": str(current_section.get("pricing_source") or "unavailable"),
    }
    report["calls"] = call_entries
    report["sections"] = sorted(
        section_map.values(),
        key=lambda item: str(item.get("section_path") or item.get("section_id") or ""),
    )
    report["models"] = sorted(
        model_map.values(),
        key=lambda item: (str(item.get("provider") or ""), str(item.get("model") or "")),
    )
    return normalize_generation_cost_report(report)
