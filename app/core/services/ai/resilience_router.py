"""Resilient provider router for LLM calls."""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Set

from app.core.services.ai.circuit_breaker import CircuitBreaker
from app.core.services.ai.error_classifier import LLMErrorType, classify_error, extract_retry_after_seconds
from app.core.services.ai.limiter import LLMLimiter
from app.core.services.ai.phase_policy import PhasePolicy
from app.core.services.ai.retry_policy import compute_backoff, should_retry

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _estimate_tokens(text: str) -> int:
    normalized = str(text or "").strip()
    if not normalized:
        return 0
    return max(1, len(normalized) // 4)


@dataclass
class LLMRequest:
    phase: str
    prompt: str
    context: str = ""
    section_id: str = ""
    section_path: str = ""
    tenant_id: Optional[str] = None
    preferred_provider: Optional[str] = None
    provider_candidates: Sequence[str] = field(default_factory=list)
    selection_mode: str = "auto"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResult:
    content: str
    provider: str
    status: str  # ok | degraded
    incidents: List[Dict[str, Any]] = field(default_factory=list)
    retry_count: int = 0


class LLMProviderRouter:
    """Provider routing with queueing, retries, breaker, fallback and degraded mode."""

    def __init__(
        self,
        *,
        providers: Dict[str, Any],
        get_model_for_provider: Callable[[str], Optional[str]],
        phase_policies: Dict[str, PhasePolicy],
        limiter: LLMLimiter,
        breaker: CircuitBreaker,
        provider_metrics: Optional[Any] = None,
        retry_jitter: float = 0.3,
        retry_cap_seconds: float = 30.0,
        max_rate_limited_retries: int = 2,
        max_transient_retries: int = 1,
        sleep_fn: Callable[[float], None] = time.sleep,
        time_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self._providers = providers
        self._get_model_for_provider = get_model_for_provider
        self._phase_policies = dict(phase_policies or {})
        self._limiter = limiter
        self._breaker = breaker
        self._provider_metrics = provider_metrics
        self._retry_jitter = max(0.0, float(retry_jitter))
        self._retry_cap_seconds = max(0.1, float(retry_cap_seconds))
        self._max_rate_limited_retries = max(0, int(max_rate_limited_retries))
        self._max_transient_retries = max(0, int(max_transient_retries))
        self._sleep_fn = sleep_fn
        self._time_fn = time_fn
        self._metrics_lock = threading.RLock()
        self._metrics: Dict[str, int] = {}

    def _metric_inc(self, key: str) -> None:
        with self._metrics_lock:
            self._metrics[key] = int(self._metrics.get(key, 0)) + 1

    def set_providers(self, providers: Dict[str, Any]) -> None:
        """Update runtime provider map (used by tests and dynamic wiring)."""
        self._providers = dict(providers or {})

    def set_sleep_fn(self, sleep_fn: Callable[[float], None]) -> None:
        """Update sleep callback (supports patched sleeps in tests)."""
        self._sleep_fn = sleep_fn

    def metrics_snapshot(self) -> Dict[str, int]:
        with self._metrics_lock:
            return dict(self._metrics)

    def _policy_for(self, phase: str) -> PhasePolicy:
        return self._phase_policies.get(phase) or self._phase_policies["generate_section"]

    @staticmethod
    def _incident(
        *,
        severity: str,
        phase: str,
        provider: str,
        message: str,
        section_id: str,
        section_path: str,
        kind: str = "provider",
    ) -> Dict[str, Any]:
        return {
            "ts": _utc_now_iso(),
            "severity": severity,
            "phase": phase,
            "provider": provider,
            "message": str(message or "").strip()[:360],
            "section_id": section_id,
            "section_path": section_path,
            "kind": kind,
        }

    @staticmethod
    def _chain(
        *,
        preferred_provider: Optional[str],
        provider_candidates: Sequence[str],
        policy_chain: Sequence[str],
        allow_degraded: bool,
        selection_mode: str,
    ) -> List[str]:
        merged: List[str] = []
        base_values: List[Optional[str]] = [preferred_provider, *provider_candidates]
        if str(selection_mode or "").lower().strip() != "fixed":
            base_values.extend(policy_chain)
        for value in base_values:
            if not value:
                continue
            text = str(value).strip()
            if not text:
                continue
            item = "DEGRADED" if text.upper() == "DEGRADED" else text.lower()
            if item not in merged:
                merged.append(item)
        if allow_degraded and "DEGRADED" not in merged:
            merged.append("DEGRADED")
        return merged

    @staticmethod
    def _budget_text(prompt: str, context: str, *, max_input_tokens: int, max_output_tokens: int) -> str:
        input_budget = max(200, int(max_input_tokens) - int(max_output_tokens))
        joined = f"{str(prompt or '').strip()}\n\n{str(context or '').strip()}".strip()
        if _estimate_tokens(joined) <= input_budget:
            return joined
        keep_chars = max(400, input_budget * 4)
        return joined[:keep_chars]

    @staticmethod
    def _degraded_cleanup_text(context: str) -> str:
        raw = str(context or "")
        cleaned = raw.replace("**", "").replace("__", "").replace("```", "").replace("|", " ")
        lines = []
        for line in cleaned.splitlines():
            normalized = " ".join(line.split())
            if not normalized:
                continue
            upper = normalized.upper()
            if "FIGURA DE EJEMPLO" in upper or "[INSERTAR" in upper:
                continue
            lines.append(normalized)
        return "\n".join(lines).strip()

    def _log_structured(self, payload: Dict[str, Any]) -> None:
        try:
            logger.info("llm_call %s", json.dumps(payload, ensure_ascii=False))
        except Exception:
            logger.info("llm_call %s", payload)

    def callLLMWithResilience(
        self,
        req: LLMRequest,
        *,
        disabled_for_job: Optional[Set[str]] = None,
    ) -> LLMResult:
        """Execute one LLM call with full resilience policy."""
        disabled = disabled_for_job if disabled_for_job is not None else set()
        policy = self._policy_for(req.phase)
        chain = self._chain(
            preferred_provider=req.preferred_provider,
            provider_candidates=req.provider_candidates,
            policy_chain=policy.fallback_chain,
            allow_degraded=policy.allow_degraded,
            selection_mode=req.selection_mode,
        )

        incidents: List[Dict[str, Any]] = []
        total_retries = 0
        last_error: Optional[Exception] = None

        for provider_index, provider in enumerate(chain):
            provider_last_error_type: Optional[LLMErrorType] = None
            if provider == "DEGRADED":
                if policy.allow_degraded and not policy.critical:
                    incidents.append(
                        self._incident(
                            severity="warning",
                            phase=req.phase,
                            provider="DEGRADED",
                            message="Se activo modo degradado local para continuar.",
                            section_id=req.section_id,
                            section_path=req.section_path,
                            kind="degraded",
                        )
                    )
                    content = self._degraded_cleanup_text(req.context)
                    return LLMResult(
                        content=content,
                        provider="DEGRADED",
                        status="degraded",
                        incidents=incidents,
                        retry_count=total_retries,
                    )
                continue

            if provider in disabled:
                continue

            client = self._providers.get(provider)
            if client is None:
                continue
            if not bool(getattr(client, "is_configured", lambda: False)()):
                continue

            if not self._breaker.before_call(provider):
                wait = self._breaker.seconds_until_closed(provider)
                incidents.append(
                    self._incident(
                        severity="warning",
                        phase=req.phase,
                        provider=provider,
                        message=f"Circuit breaker abierto ({int(round(wait))}s restantes), saltando provider.",
                        section_id=req.section_id,
                        section_path=req.section_path,
                        kind="circuit_open",
                    )
                )
                self._metric_inc(f"circuit_open:{provider}")
                continue

            attempt = 0
            while True:
                started = self._time_fn()
                model = self._get_model_for_provider(provider) or "-"
                bounded_prompt = self._budget_text(
                    req.prompt,
                    req.context,
                    max_input_tokens=policy.max_input_tokens,
                    max_output_tokens=policy.max_output_tokens,
                )
                tokens_in = _estimate_tokens(bounded_prompt)
                try:
                    with self._limiter.acquire_sync(provider, tenant_id=req.tenant_id):
                        content = client.generate(
                            bounded_prompt,
                            model=model if model and model != "-" else None,
                        )
                    latency_ms = int(round((self._time_fn() - started) * 1000))
                    self._breaker.on_success(provider)
                    tokens_out = _estimate_tokens(content)
                    if self._provider_metrics is not None:
                        self._provider_metrics.record_success(
                            provider,
                            latency_ms=latency_ms,
                            prompt=bounded_prompt,
                            response=content,
                        )
                    self._metric_inc(f"success:{provider}:{req.phase}")
                    self._log_structured(
                        {
                            "request_id": req.metadata.get("request_id"),
                            "provider": provider,
                            "model": model,
                            "phase": req.phase,
                            "section_id": req.section_id,
                            "status_code": 200,
                            "latency_ms": latency_ms,
                            "tokens_in": tokens_in,
                            "tokens_out": tokens_out,
                            "retry_count": attempt,
                            "tenant_id": req.tenant_id,
                        }
                    )
                    return LLMResult(
                        content=content,
                        provider=provider,
                        status="ok",
                        incidents=incidents,
                        retry_count=total_retries,
                    )
                except Exception as exc:
                    last_error = exc
                    status_code = getattr(exc, "status_code", None)
                    err_type = classify_error(exc, status_code=status_code)
                    provider_last_error_type = err_type
                    retry_after = extract_retry_after_seconds(exc)
                    latency_ms = int(round((self._time_fn() - started) * 1000))
                    reason = err_type.value
                    self._breaker.on_failure(provider, reason=reason)

                    if self._provider_metrics is not None:
                        if err_type == LLMErrorType.RATE_LIMITED:
                            self._provider_metrics.record_rate_limited(
                                provider,
                                retry_after_s=retry_after or 10,
                                message=str(exc),
                            )
                        elif err_type == LLMErrorType.EXHAUSTED:
                            self._provider_metrics.record_exhausted(provider, message=str(exc))
                        else:
                            kind = "timeout" if err_type == LLMErrorType.TRANSIENT else "error"
                            if err_type == LLMErrorType.AUTH_ERROR:
                                kind = "auth"
                            self._provider_metrics.record_error(
                                provider,
                                message=str(exc),
                                latency_ms=latency_ms,
                                kind=kind,
                            )

                    self._metric_inc(f"error:{provider}:{req.phase}:{reason}")
                    self._log_structured(
                        {
                            "request_id": req.metadata.get("request_id"),
                            "provider": provider,
                            "model": model,
                            "phase": req.phase,
                            "section_id": req.section_id,
                            "status_code": status_code,
                            "latency_ms": latency_ms,
                            "tokens_in": tokens_in,
                            "tokens_out": 0,
                            "retry_count": attempt,
                            "tenant_id": req.tenant_id,
                            "error_type": reason,
                            "error": str(exc)[:220],
                        }
                    )

                    incidents.append(
                        self._incident(
                            severity="warning" if not policy.critical else "error",
                            phase=req.phase,
                            provider=provider,
                            message=f"{reason}: {str(exc)[:200]}",
                            section_id=req.section_id,
                            section_path=req.section_path,
                        )
                    )

                    if err_type in {LLMErrorType.EXHAUSTED, LLMErrorType.AUTH_ERROR}:
                        disabled.add(provider)
                        break

                    if should_retry(
                        err_type,
                        attempt,
                        max_rate_limited_retries=self._max_rate_limited_retries,
                        max_transient_retries=self._max_transient_retries,
                    ):
                        wait_seconds = compute_backoff(
                            attempt,
                            retry_after=retry_after,
                            jitter=self._retry_jitter,
                            cap_seconds=self._retry_cap_seconds,
                        )
                        total_retries += 1
                        retry_limit = (
                            self._max_rate_limited_retries
                            if err_type == LLMErrorType.RATE_LIMITED
                            else self._max_transient_retries
                        )
                        wait_label = int(round(wait_seconds))
                        incidents.append(
                            self._incident(
                                severity="warning",
                                phase=req.phase,
                                provider=provider,
                                message=(
                                    f"{reason}: reintento {attempt + 1}/"
                                    f"{retry_limit}; espera {wait_label}s."
                                ),
                                section_id=req.section_id,
                                section_path=req.section_path,
                                kind="retry",
                            )
                        )
                        self._metric_inc(f"retry:{provider}:{req.phase}")
                        self._sleep_fn(wait_seconds)
                        attempt += 1
                        continue
                    break

            # Fixed mode keeps the selected provider by default; only permit
            # contingency fallback on transient/rate-limited failures.
            if (
                str(req.selection_mode or "").lower().strip() == "fixed"
                and provider_index == 0
                and provider_last_error_type is not None
            ):
                if provider_last_error_type not in {LLMErrorType.TRANSIENT, LLMErrorType.RATE_LIMITED}:
                    break
                incidents.append(
                    self._incident(
                        severity="warning",
                        phase=req.phase,
                        provider=provider,
                        message=(
                            "Modo fijo: se habilita fallback de contingencia por "
                            f"error {provider_last_error_type.value}."
                        ),
                        section_id=req.section_id,
                        section_path=req.section_path,
                        kind="fixed_mode_fallback",
                    )
                )

        if policy.allow_degraded and not policy.critical:
            incidents.append(
                self._incident(
                    severity="warning",
                    phase=req.phase,
                    provider="DEGRADED",
                    message="Todos los proveedores fallaron en fase opcional; se omitio automaticamente.",
                    section_id=req.section_id,
                    section_path=req.section_path,
                    kind="degraded",
                )
            )
            return LLMResult(
                content=self._degraded_cleanup_text(req.context),
                provider="DEGRADED",
                status="degraded",
                incidents=incidents,
                retry_count=total_retries,
            )

        if last_error is not None:
            raise last_error
        raise RuntimeError(
            f"Sin proveedores disponibles para fase critica '{req.phase}'. "
            "No hubo proveedor configurado/disponible."
        )
