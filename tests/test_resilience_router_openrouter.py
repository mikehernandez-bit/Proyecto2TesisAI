"""OpenRouter-specific resilience behavior tests."""

from __future__ import annotations

from app.core.services.ai.circuit_breaker import CircuitBreaker
from app.core.services.ai.errors import QuotaExceededError
from app.core.services.ai.limiter import LLMLimiter
from app.core.services.ai.phase_policy import PhasePolicy
from app.core.services.ai.resilience_router import LLMProviderRouter, LLMRequest


class _SequenceProvider:
    def __init__(self, sequence):
        self._sequence = list(sequence)
        self.calls = 0

    def is_configured(self) -> bool:
        return True

    def generate(self, _prompt: str, *, model: str | None = None) -> str:  # noqa: ARG002
        current = self._sequence[self.calls]
        self.calls += 1
        if isinstance(current, Exception):
            raise current
        return str(current)


def _build_router(provider: object, sleeps: list[float]) -> LLMProviderRouter:
    limiter = LLMLimiter(
        provider_concurrency={"openrouter": 1},
        provider_rpm={"openrouter": 60},
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
            fallback_chain=["openrouter"],
            max_input_tokens=6000,
            max_output_tokens=1200,
            allow_degraded=False,
        )
    }
    return LLMProviderRouter(
        providers={"openrouter": provider},
        get_model_for_provider=lambda provider_id: f"{provider_id}-model",
        phase_policies=policies,
        limiter=limiter,
        breaker=breaker,
        retry_jitter=0.0,
        retry_cap_seconds=45.0,
        max_rate_limited_retries=2,
        max_transient_retries=0,
        sleep_fn=lambda seconds: sleeps.append(float(seconds)),
    )


def test_openrouter_rate_limit_uses_conservative_waits_when_retry_after_missing() -> None:
    rate_exc = QuotaExceededError(
        "Rate limited by OpenRouter API.",
        provider="openrouter",
        retry_after=None,
        error_type="rate_limited",
    )
    provider = _SequenceProvider([rate_exc, rate_exc, "ok"])
    waits: list[float] = []
    router = _build_router(provider, waits)

    result = router.callLLMWithResilience(
        LLMRequest(
            phase="generate_section",
            prompt="Genera introduccion",
            section_id="sec-1",
            section_path="Introduccion",
            provider_candidates=["openrouter"],
            selection_mode="auto",
        )
    )

    assert result.status == "ok"
    assert result.provider == "openrouter"
    assert provider.calls == 3
    assert waits == [10.0, 20.0]
