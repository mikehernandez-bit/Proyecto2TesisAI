"""Helpers for LLM token usage accounting during document generation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Mapping


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def estimate_tokens(text: str) -> int:
    normalized = str(text or "").strip()
    if not normalized:
        return 0
    return max(1, len(normalized) // 4)


def _to_int(value: Any) -> int:
    try:
        return max(0, int(value))
    except Exception:
        return 0


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "si"}
    return bool(value)


def _section_title_from_path(path: str) -> str:
    parts = [segment.strip() for segment in str(path or "").split("/") if segment.strip()]
    return parts[-1] if parts else ""


def _usage_key(section_id: str, section_path: str) -> str:
    section_id = str(section_id or "").strip()
    if section_id:
        return f"id:{section_id}"
    return f"path:{str(section_path or '').strip()}"


def empty_token_usage_summary() -> dict[str, Any]:
    return {
        "input_tokens_total": 0,
        "output_tokens_total": 0,
        "total_tokens": 0,
        "calls_total": 0,
        "reported_calls": 0,
        "estimated_calls": 0,
        "has_estimated_usage": False,
        "current_section": None,
        "last_call": None,
    }


def empty_token_usage_report() -> dict[str, Any]:
    report = empty_token_usage_summary()
    report.update(
        {
            "attempts": [],
            "sections": [],
            "providers": [],
        }
    )
    return report


def build_usage_entry(
    raw_usage: Mapping[str, Any] | None,
    *,
    prompt: str,
    response: str = "",
    provider: str,
    model: str,
    phase: str,
    section_id: str,
    section_path: str,
    attempt: int,
    success: bool,
    error: str = "",
    timestamp: str | None = None,
    duration_ms: int | None = None,
) -> dict[str, Any]:
    raw_usage = raw_usage if isinstance(raw_usage, Mapping) else {}
    prompt_tokens = _to_int(
        raw_usage.get("input_tokens")
        or raw_usage.get("prompt_tokens")
        or raw_usage.get("inputTokens")
        or raw_usage.get("promptTokenCount")
    )
    completion_tokens = _to_int(
        raw_usage.get("output_tokens")
        or raw_usage.get("completion_tokens")
        or raw_usage.get("outputTokens")
        or raw_usage.get("completionTokenCount")
        or raw_usage.get("candidates_token_count")
    )
    total_tokens = _to_int(
        raw_usage.get("total_tokens") or raw_usage.get("totalTokens") or raw_usage.get("total_token_count")
    )

    estimated = _to_bool(raw_usage.get("estimated"))
    if prompt_tokens <= 0:
        prompt_tokens = estimate_tokens(prompt)
        estimated = True
    if success:
        if completion_tokens <= 0 and response:
            completion_tokens = estimate_tokens(response)
            estimated = True
    else:
        completion_tokens = max(0, completion_tokens)

    if total_tokens <= 0:
        total_tokens = prompt_tokens + completion_tokens
        estimated = True

    source = str(raw_usage.get("source") or "").strip()
    if not source:
        source = "estimated" if estimated else "reported_by_provider"

    return {
        "input_tokens": prompt_tokens,
        "output_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "provider": str(provider or "").strip(),
        "model": str(model or "").strip(),
        "phase": str(phase or "").strip(),
        "section_id": str(section_id or "").strip(),
        "section_path": str(section_path or "").strip(),
        "section_title": _section_title_from_path(section_path),
        "attempt": max(1, _to_int(attempt)),
        "timestamp": str(timestamp or _utc_now_iso()),
        "duration_ms": _to_int(duration_ms),
        "estimated": estimated,
        "source": source,
        "success": bool(success),
        "error": str(error or "").strip()[:240],
    }


def summarize_token_usage(
    attempts: Iterable[Mapping[str, Any]],
    *,
    current_section_id: str = "",
    current_section_path: str = "",
) -> dict[str, Any]:
    report = empty_token_usage_report()
    normalized_attempts: list[dict[str, Any]] = []
    section_map: dict[str, dict[str, Any]] = {}
    provider_map: dict[str, dict[str, Any]] = {}
    current_key = _usage_key(current_section_id, current_section_path)

    for raw in attempts:
        if not isinstance(raw, Mapping):
            continue
        input_tokens = _to_int(raw.get("input_tokens"))
        output_tokens = _to_int(raw.get("output_tokens"))
        total_tokens = _to_int(raw.get("total_tokens"))
        provider = str(raw.get("provider") or "").strip()
        model = str(raw.get("model") or "").strip()
        phase = str(raw.get("phase") or "").strip()
        section_id = str(raw.get("section_id") or "").strip()
        section_path = str(raw.get("section_path") or "").strip()
        section_title = str(raw.get("section_title") or _section_title_from_path(section_path)).strip()
        attempt = max(1, _to_int(raw.get("attempt") or 1))
        timestamp = str(raw.get("timestamp") or _utc_now_iso())
        duration_ms = _to_int(raw.get("duration_ms"))
        estimated = _to_bool(raw.get("estimated"))
        source = str(raw.get("source") or ("estimated" if estimated else "reported_by_provider"))
        success = _to_bool(raw.get("success", True))
        error = str(raw.get("error") or "").strip()[:240]
        entry = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "provider": provider,
            "model": model,
            "phase": phase,
            "section_id": section_id,
            "section_path": section_path,
            "section_title": section_title,
            "attempt": attempt,
            "timestamp": timestamp,
            "duration_ms": duration_ms,
            "estimated": estimated,
            "source": source,
            "success": success,
            "error": error,
        }
        if total_tokens <= 0:
            total_tokens = input_tokens + output_tokens
            entry["total_tokens"] = total_tokens
        normalized_attempts.append(entry)

        report["input_tokens_total"] += input_tokens
        report["output_tokens_total"] += output_tokens
        report["total_tokens"] += total_tokens
        report["calls_total"] += 1
        if estimated:
            report["estimated_calls"] += 1
            report["has_estimated_usage"] = True
        else:
            report["reported_calls"] += 1

        section_key = _usage_key(section_id, section_path)
        section_bucket = section_map.setdefault(
            section_key,
            {
                "section_id": section_id,
                "section_path": section_path,
                "section_title": section_title,
                "input_tokens_total": 0,
                "output_tokens_total": 0,
                "total_tokens": 0,
                "calls_total": 0,
                "reported_calls": 0,
                "estimated_calls": 0,
                "has_estimated_usage": False,
                "last_provider": "",
                "last_model": "",
                "last_timestamp": "",
            },
        )
        section_bucket["input_tokens_total"] += input_tokens
        section_bucket["output_tokens_total"] += output_tokens
        section_bucket["total_tokens"] += total_tokens
        section_bucket["calls_total"] += 1
        section_bucket["last_provider"] = provider
        section_bucket["last_model"] = model
        section_bucket["last_timestamp"] = timestamp
        if estimated:
            section_bucket["estimated_calls"] += 1
            section_bucket["has_estimated_usage"] = True
        else:
            section_bucket["reported_calls"] += 1

        provider_key = f"{provider}|{model}"
        provider_bucket = provider_map.setdefault(
            provider_key,
            {
                "provider": provider,
                "model": model,
                "input_tokens_total": 0,
                "output_tokens_total": 0,
                "total_tokens": 0,
                "calls_total": 0,
                "reported_calls": 0,
                "estimated_calls": 0,
                "has_estimated_usage": False,
            },
        )
        provider_bucket["input_tokens_total"] += input_tokens
        provider_bucket["output_tokens_total"] += output_tokens
        provider_bucket["total_tokens"] += total_tokens
        provider_bucket["calls_total"] += 1
        if estimated:
            provider_bucket["estimated_calls"] += 1
            provider_bucket["has_estimated_usage"] = True
        else:
            provider_bucket["reported_calls"] += 1

    report["attempts"] = normalized_attempts
    report["sections"] = list(section_map.values())
    report["providers"] = list(provider_map.values())
    report["last_call"] = normalized_attempts[-1] if normalized_attempts else None

    if current_key and current_key in section_map:
        report["current_section"] = dict(section_map[current_key])
    elif normalized_attempts:
        last = normalized_attempts[-1]
        report["current_section"] = dict(section_map[_usage_key(last["section_id"], last["section_path"])])
    else:
        report["current_section"] = None
    return report


def merge_token_usage(
    current: Mapping[str, Any] | None,
    new_attempts: Iterable[Mapping[str, Any]],
    *,
    current_section_id: str = "",
    current_section_path: str = "",
) -> dict[str, Any]:
    existing_attempts = []
    if isinstance(current, Mapping):
        raw_attempts = current.get("attempts")
        if isinstance(raw_attempts, list):
            existing_attempts = [item for item in raw_attempts if isinstance(item, Mapping)]

    merged_attempts = [*existing_attempts, *[item for item in new_attempts if isinstance(item, Mapping)]]
    return summarize_token_usage(
        merged_attempts,
        current_section_id=current_section_id,
        current_section_path=current_section_path,
    )


def token_usage_snapshot(report: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(report, Mapping):
        return empty_token_usage_summary()
    return {
        "input_tokens_total": _to_int(report.get("input_tokens_total")),
        "output_tokens_total": _to_int(report.get("output_tokens_total")),
        "total_tokens": _to_int(report.get("total_tokens")),
        "calls_total": _to_int(report.get("calls_total")),
        "reported_calls": _to_int(report.get("reported_calls")),
        "estimated_calls": _to_int(report.get("estimated_calls")),
        "has_estimated_usage": _to_bool(report.get("has_estimated_usage")),
        "current_section": report.get("current_section")
        if isinstance(report.get("current_section"), Mapping)
        else None,
        "last_call": report.get("last_call") if isinstance(report.get("last_call"), Mapping) else None,
    }


def normalize_token_usage_report(raw: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        return empty_token_usage_report()
    attempts = raw.get("attempts")
    if not isinstance(attempts, list):
        return empty_token_usage_report()
    current_section = raw.get("current_section")
    if not isinstance(current_section, Mapping):
        current_section = {}
    return summarize_token_usage(
        attempts,
        current_section_id=str(current_section.get("section_id") or ""),
        current_section_path=str(current_section.get("section_path") or ""),
    )


def normalize_token_usage_snapshot(raw: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        return empty_token_usage_summary()
    report = empty_token_usage_summary()
    report["input_tokens_total"] = _to_int(raw.get("input_tokens_total"))
    report["output_tokens_total"] = _to_int(raw.get("output_tokens_total"))
    report["total_tokens"] = _to_int(raw.get("total_tokens"))
    report["calls_total"] = _to_int(raw.get("calls_total"))
    report["reported_calls"] = _to_int(raw.get("reported_calls"))
    report["estimated_calls"] = _to_int(raw.get("estimated_calls"))
    report["has_estimated_usage"] = _to_bool(raw.get("has_estimated_usage"))
    report["current_section"] = raw.get("current_section") if isinstance(raw.get("current_section"), Mapping) else None
    report["last_call"] = raw.get("last_call") if isinstance(raw.get("last_call"), Mapping) else None
    return report
