"""Phase-specific policy for resilient provider routing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List

from app.core.config import settings


@dataclass(frozen=True)
class PhasePolicy:
    critical: bool
    fallback_chain: List[str]
    max_input_tokens: int
    max_output_tokens: int
    allow_degraded: bool


def _parse_chain(raw: str, defaults: Iterable[str]) -> List[str]:
    parts = [item.strip() for item in str(raw or "").split(",") if item.strip()]
    if not parts:
        parts = [str(item).strip() for item in defaults if str(item).strip()]
    deduped: List[str] = []
    for entry in parts:
        normalized = entry
        if normalized.upper() == "DEGRADED":
            normalized = "DEGRADED"
        else:
            normalized = normalized.lower()
        if normalized not in deduped:
            deduped.append(normalized)
    return deduped


def build_phase_policies() -> Dict[str, PhasePolicy]:
    """Build runtime policies from settings/env vars."""
    generate_chain = _parse_chain(
        getattr(settings, "FALLBACK_CHAIN_GENERATE", "mistral,provider_b,provider_c"),
        defaults=("mistral", "provider_b", "provider_c"),
    )
    cleanup_chain = _parse_chain(
        getattr(settings, "FALLBACK_CHAIN_CLEANUP", "mistral,cheap_model,DEGRADED"),
        defaults=("mistral", "cheap_model", "DEGRADED"),
    )

    return {
        "generate_section": PhasePolicy(
            critical=True,
            fallback_chain=generate_chain,
            max_input_tokens=max(500, int(getattr(settings, "LLM_MAX_INPUT_TOKENS_GENERATE", 6000))),
            max_output_tokens=max(100, int(getattr(settings, "LLM_MAX_OUTPUT_TOKENS_GENERATE", 1400))),
            allow_degraded=False,
        ),
        "cleanup_correction": PhasePolicy(
            critical=False,
            fallback_chain=cleanup_chain,
            max_input_tokens=max(500, int(getattr(settings, "LLM_MAX_INPUT_TOKENS_CLEANUP", 3500))),
            max_output_tokens=max(100, int(getattr(settings, "LLM_MAX_OUTPUT_TOKENS_CLEANUP", 900))),
            allow_degraded=True,
        ),
    }
