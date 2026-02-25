"""Unit tests for fallback/degraded behavior in resilient router."""

from __future__ import annotations

import pytest

from app.core.services.ai.circuit_breaker import CircuitBreaker
from app.core.services.ai.limiter import LLMLimiter
from app.core.services.ai.phase_policy import PhasePolicy
from app.core.services.ai.resilience_router import LLMProviderRouter, LLMRequest


class _StubProvider:
    def __init__(self, *, result: str = "", exc: Exception | None = None, configured: bool = True) -> None:
        self._result = result
        self._exc = exc
        self._configured = configured
        self.calls = 0

    def is_configured(self) -> bool:
        return self._configured

    def generate(self, _prompt: str, *, model: str | None = None) -> str:  # noqa: ARG002
        self.calls += 1
        if self._exc is not None:
            raise self._exc
        return self._result


def _build_router(providers: dict[str, object]) -> LLMProviderRouter:
    limiter = LLMLimiter(
        provider_concurrency={"mistral": 1, "gemini": 1},
        provider_rpm={"mistral": 120, "gemini": 120},
        max_inflight_per_tenant=0,
    )
    breaker = CircuitBreaker(
        failures_threshold=10,
        window_seconds=60,
        open_seconds=10,
        half_open_max_trials=1,
    )
    policies = {
        "generate_section": PhasePolicy(
            critical=True,
            fallback_chain=["mistral", "gemini"],
            max_input_tokens=6000,
            max_output_tokens=1200,
            allow_degraded=False,
        ),
        "cleanup_correction": PhasePolicy(
            critical=False,
            fallback_chain=["mistral", "gemini", "DEGRADED"],
            max_input_tokens=3000,
            max_output_tokens=800,
            allow_degraded=True,
        ),
    }
    return LLMProviderRouter(
        providers=providers,
        get_model_for_provider=lambda provider: f"{provider}-model",
        phase_policies=policies,
        limiter=limiter,
        breaker=breaker,
        retry_jitter=0.0,
        retry_cap_seconds=1.0,
        max_rate_limited_retries=0,
        max_transient_retries=0,
        sleep_fn=lambda _seconds: None,
    )


def test_optional_phase_returns_degraded_when_all_providers_fail() -> None:
    providers = {
        "mistral": _StubProvider(exc=RuntimeError("Read timed out")),
        "gemini": _StubProvider(exc=RuntimeError("Read timed out")),
    }
    router = _build_router(providers)

    result = router.callLLMWithResilience(
        LLMRequest(
            phase="cleanup_correction",
            prompt="clean this",
            context="texto **markdown** con FIGURA DE EJEMPLO",
            section_id="cleanup",
            section_path="Limpieza/Correccion",
            provider_candidates=["mistral", "gemini"],
            selection_mode="auto",
        )
    )

    assert result.status == "degraded"
    assert result.provider == "DEGRADED"
    assert any(item.get("kind") == "degraded" for item in result.incidents)
    assert "FIGURA DE EJEMPLO" not in result.content.upper()


def test_critical_phase_raises_when_all_providers_fail() -> None:
    providers = {
        "mistral": _StubProvider(exc=RuntimeError("Read timed out")),
        "gemini": _StubProvider(exc=RuntimeError("Read timed out")),
    }
    router = _build_router(providers)

    with pytest.raises(RuntimeError, match="Read timed out"):
        router.callLLMWithResilience(
            LLMRequest(
                phase="generate_section",
                prompt="generate",
                section_id="sec-1",
                section_path="Introduccion",
                provider_candidates=["mistral", "gemini"],
                selection_mode="auto",
            )
        )

    assert providers["mistral"].calls == 1
    assert providers["gemini"].calls == 1
