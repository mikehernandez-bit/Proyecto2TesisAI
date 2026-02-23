"""Semantics tests for provider status indicators consumed by the UI."""

from types import SimpleNamespace
from unittest.mock import patch

from app.core.services.ai.provider_metrics import ProviderMetricsService


def _settings(*, rate_limit_per_minute: int = 60, quota_limit_tokens_month: int = 0) -> SimpleNamespace:
    return SimpleNamespace(
        AI_LOCAL_RATE_LIMIT_PER_MINUTE=rate_limit_per_minute,
        AI_LOCAL_QUOTA_LIMIT_TOKENS_MONTH=quota_limit_tokens_month,
    )


def test_capacity_available_means_remaining_equals_limit_and_no_wait() -> None:
    metrics = ProviderMetricsService()

    with patch("app.core.services.ai.provider_metrics.settings", _settings(rate_limit_per_minute=60)):
        payload = metrics.payload_for_provider("gemini", model="gemini-2.0-flash", configured=True)

    assert payload["health"] == "OK"
    assert payload["rate_limit"]["remaining"] == 60
    assert payload["rate_limit"]["limit"] == 60
    assert payload["rate_limit"]["reset_seconds"] == 0
    assert payload["last_probe_status"] == "UNVERIFIED"


def test_rate_limited_and_exhausted_states_are_exposed_for_ui() -> None:
    metrics = ProviderMetricsService()

    with patch("app.core.services.ai.provider_metrics.settings", _settings(rate_limit_per_minute=60)):
        metrics.record_rate_limited("gemini", retry_after_s=57, message="Rate limited. Retry after 57 seconds.")
        limited_payload = metrics.payload_for_provider("gemini", model="gemini-2.0-flash", configured=True)
        assert limited_payload["health"] == "RATE_LIMITED"
        assert limited_payload["rate_limit"]["reset_seconds"] > 0

        metrics.record_exhausted("gemini", message="Quota exceeded. Check Gemini project quota/billing.")
        exhausted_payload = metrics.payload_for_provider("gemini", model="gemini-2.0-flash", configured=True)
        assert exhausted_payload["health"] == "EXHAUSTED"


def test_quota_unknown_returns_null_values_for_ui_no_disp_fallback() -> None:
    metrics = ProviderMetricsService()

    with patch("app.core.services.ai.provider_metrics.settings", _settings(quota_limit_tokens_month=0)):
        payload = metrics.payload_for_provider("mistral", model="mistral-medium-2505", configured=True)

    assert payload["quota"]["remaining"] is None
    assert payload["quota"]["limit"] is None
    assert payload["quota"]["note"] == "local_estimate"


def test_probe_metadata_is_persisted_for_ui_badges() -> None:
    metrics = ProviderMetricsService()

    metrics.record_probe(
        "mistral",
        status="RATE_LIMITED",
        detail="Retry after 9 seconds",
        retry_after_s=9,
    )
    payload = metrics.payload_for_provider("mistral", model="mistral-medium-2505", configured=True)
    assert payload["probe"]["status"] == "RATE_LIMITED"
    assert payload["last_probe_retry_after_s"] == 9
