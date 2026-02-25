"""AI generation orchestrator for GicaGen.

Coordinates the full generation pipeline:
  render prompt -> generate per section -> correct -> validate -> aiResult

Supports provider selection and quota fallback (Gemini <-> Mistral).
When the primary provider hits rate limits, the orchestrator waits for
the retry-after window and retries the same provider before falling back.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol, Set, Tuple

from app.core.config import settings
from app.core.services.ai.circuit_breaker import CircuitBreaker
from app.core.services.ai.errors import GenerationCancelledError
from app.core.services.ai.gemini_client import GeminiClient
from app.core.services.ai.limiter import LLMLimiter
from app.core.services.ai.mistral_client import MistralClient
from app.core.services.ai.openrouter_client import OpenRouterClient
from app.core.services.ai.completeness_validator import (
    detect_placeholders,
    autofill_section,
)
from app.core.services.ai.output_validator import OutputValidator, ValidationError
from app.core.services.ai.phase_policy import build_phase_policies
from app.core.services.ai.prompt_renderer import PromptRenderer
from app.core.services.ai.provider_metrics import ProviderMetricsService
from app.core.services.ai.provider_selection import ProviderSelectionService
from app.core.services.ai.resilience_router import LLMProviderRouter, LLMRequest, LLMResult
from app.core.services.definition_compiler import compile_definition_to_section_index

logger = logging.getLogger(__name__)

_PROVIDER_ORDER = ("gemini", "mistral", "openrouter")
_PROVIDER_SET = set(_PROVIDER_ORDER)

# Throttle between section calls to avoid bursting through rate limits.
_INTER_SECTION_DELAY_S = 2.0

# Retry policy by error type.
_RATE_LIMIT_RETRIES = 2
_TRANSIENT_RETRIES = 1
_RATE_LIMIT_WAIT_CAP_S = 30.0
_TRANSIENT_BACKOFF_S = 2.0
_EXHAUSTED_MARKERS = (
    "quota exceeded",
    "project quota/billing",
    "exceeded your current quota",
    "insufficient_quota",
    "resource_exhausted",
)
_RATE_LIMIT_MARKERS = (
    "rate-limited",
    "rate limited",
    "retry after",
    "429",
)
_AUTH_MARKERS = (
    "api key not valid",
    "invalid api key",
    "permission denied",
    "unauthorized",
    "forbidden",
    "401",
    "403",
)
_TIMEOUT_MARKERS = (
    "timed out",
    "timeout",
    "read timed out",
    "read timeout",
)
_TRANSIENT_MARKERS = (
    "connection reset",
    "temporarily unavailable",
    "service unavailable",
    "502",
    "503",
    "504",
    "500",
    "sslv3_alert_bad_record_mac",
    "bad record mac",
    "ssl:",
    "sslerror",
)


class _ProviderClient(Protocol):
    def is_configured(self) -> bool: ...

    def generate(
        self,
        prompt: str,
        *,
        timeout: int = 60,
        model: Optional[str] = None,
    ) -> str: ...

    def probe(self, *, timeout: int = 8, model: Optional[str] = None) -> Dict[str, Any]: ...


class AIService:
    """Orchestrates AI content generation with provider failover."""

    def __init__(self) -> None:
        self.renderer = PromptRenderer()
        self.validator = OutputValidator()
        self._clients: Dict[str, _ProviderClient] = {
            "gemini": GeminiClient(),
            "mistral": MistralClient(),
            "openrouter": OpenRouterClient(),
        }
        self._selection_store = ProviderSelectionService()
        self._selection = self._selection_store.get_selection()
        self._metrics = ProviderMetricsService()
        self._last_used_provider: Optional[str] = None
        self._trace_hook: Optional[Callable[[Dict[str, Any]], None]] = None
        self._cancel_check: Optional[Callable[[], bool]] = None
        self._progress_cb: Optional[Callable[..., None]] = None
        self._active_selection: Dict[str, Any] = {}
        self._run_incidents: List[Dict[str, Any]] = []
        self._last_call_result: Optional[LLMResult] = None
        self._partial_sections: List[Dict[str, str]] = []

        self._phase_policies = build_phase_policies()
        self._limiter = LLMLimiter(
            provider_concurrency={
                "mistral": int(getattr(settings, "MAX_INFLIGHT_MISTRAL", 3)),
                "gemini": int(getattr(settings, "MAX_INFLIGHT_GEMINI", 3)),
                "openrouter": int(getattr(settings, "MAX_INFLIGHT_OPENROUTER", 3)),
            },
            provider_rpm={
                "mistral": int(getattr(settings, "MISTRAL_RPM", 60)),
                "gemini": int(getattr(settings, "GEMINI_RPM", 60)),
                "openrouter": int(getattr(settings, "OPENROUTER_RPM", 60)),
            },
            max_inflight_per_tenant=int(getattr(settings, "MAX_INFLIGHT_PER_TENANT", 2)),
            default_concurrency=2,
            default_rpm=60,
        )
        self._breaker = CircuitBreaker(
            failures_threshold=int(getattr(settings, "CB_FAILURES", 5)),
            window_seconds=float(getattr(settings, "CB_WINDOW_SEC", 60)),
            open_seconds=float(getattr(settings, "CB_OPEN_SEC", 120)),
            half_open_max_trials=int(getattr(settings, "CB_HALF_OPEN_MAX_TRIALS", 2)),
        )
        self._resilience_router = LLMProviderRouter(
            providers=self._clients,
            get_model_for_provider=self._model_for_active_selection,
            phase_policies=self._phase_policies,
            limiter=self._limiter,
            breaker=self._breaker,
            provider_metrics=self._metrics,
            retry_jitter=float(getattr(settings, "RETRY_JITTER", 0.3)),
            retry_cap_seconds=float(getattr(settings, "RETRY_CAP_SECONDS", 30)),
            max_rate_limited_retries=_RATE_LIMIT_RETRIES,
            max_transient_retries=_TRANSIENT_RETRIES,
            sleep_fn=self._sleep_with_cancel,
        )

    def _model_for_active_selection(self, provider: str) -> Optional[str]:
        return self.get_model_for_provider(provider, selection_override=self._active_selection)

    @staticmethod
    def _default_model_for_provider(provider: str) -> str:
        if provider == "gemini":
            return str(getattr(settings, "GEMINI_MODEL", "gemini-2.0-flash"))
        if provider == "mistral":
            return str(getattr(settings, "MISTRAL_MODEL", "mistral-medium-2505"))
        return str(getattr(settings, "OPENROUTER_MODEL", "openai/gpt-oss-120b:free"))

    @staticmethod
    def _fallback_for(primary: str) -> str:
        for candidate in _PROVIDER_ORDER:
            if candidate != primary:
                return candidate
        return "gemini"

    @staticmethod
    def _provider_display_name(provider: str) -> str:
        labels = {
            "gemini": "Gemini",
            "mistral": "Mistral",
            "openrouter": "OpenRouter (GPT-OSS-120B Gratis)",
        }
        return labels.get(provider, provider.capitalize())

    @staticmethod
    def _model_matches_provider(provider: str, model: str) -> bool:
        normalized = str(model or "").strip().lower()
        if not normalized:
            return False
        if provider == "gemini":
            return "gemini" in normalized
        if provider == "mistral":
            return "mistral" in normalized
        if provider == "openrouter":
            return "gemini" not in normalized and "mistral" not in normalized
        return False

    def _refresh_selection(self) -> Dict[str, str]:
        self._selection = self._selection_store.get_selection()
        return dict(self._selection)

    def get_provider_selection(self) -> Dict[str, str]:
        return self._refresh_selection()

    def set_provider_selection(self, payload: Dict[str, Any]) -> Dict[str, str]:
        self._selection = self._selection_store.set_selection(payload)
        return dict(self._selection)

    def normalize_provider_selection(self, payload: Dict[str, Any]) -> Dict[str, str]:
        return self._selection_store.normalize(payload)

    def _resolve_selection(self, selection_override: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
        if isinstance(selection_override, dict):
            return self.normalize_provider_selection(selection_override)
        return self._refresh_selection()

    def _provider_usable_for_fallback(
        self,
        provider: str,
        *,
        selection_override: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Return True when provider can be used as fallback candidate."""
        client = self._clients.get(provider)
        if client is None or not client.is_configured():
            return False

        model = self.get_model_for_provider(provider, selection_override=selection_override)
        if not model:
            model = self._default_model_for_provider(provider)

        payload = self._metrics.payload_for_provider(provider, model=model, configured=True)
        health = str(payload.get("health") or "UNKNOWN").upper().strip()
        probe_status = str(
            payload.get("last_probe_status")
            or payload.get("probe", {}).get("status")
            or "UNVERIFIED"
        ).upper().strip()

        # Do not select providers with known hard-fail states as fallback.
        if probe_status in {"EXHAUSTED", "AUTH_ERROR"}:
            return False
        if health == "EXHAUSTED":
            return False
        return True

    def _effective_fallback_provider(
        self,
        primary: str,
        requested_fallback: str,
        *,
        selection_override: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Pick first usable fallback provider, preferring requested fallback."""
        candidates: List[str] = []
        if requested_fallback in _PROVIDER_SET and requested_fallback != primary:
            candidates.append(requested_fallback)
        for candidate in _PROVIDER_ORDER:
            if candidate == primary or candidate in candidates:
                continue
            candidates.append(candidate)

        for candidate in candidates:
            if self._provider_usable_for_fallback(
                candidate,
                selection_override=selection_override,
            ):
                return candidate
        return ""

    def _provider_order(self, selection_override: Optional[Dict[str, Any]] = None) -> List[str]:
        selection = self._resolve_selection(selection_override)
        primary = str(selection.get("provider") or "gemini").lower().strip()
        if primary not in _PROVIDER_SET:
            primary = _PROVIDER_ORDER[0]

        fallback = str(selection.get("fallback_provider") or "").lower().strip()
        if fallback not in _PROVIDER_SET or fallback == primary:
            fallback = self._fallback_for(primary)

        mode = str(selection.get("mode") or "auto").lower().strip()
        if mode == "fixed":
            return [primary]

        effective_fallback = self._effective_fallback_provider(
            primary,
            fallback,
            selection_override=selection,
        )
        if not effective_fallback:
            return [primary]
        return [primary, effective_fallback]

    def available_providers(self, selection_override: Optional[Dict[str, Any]] = None) -> List[str]:
        available: List[str] = []
        for provider in self._provider_order(selection_override):
            client = self._clients.get(provider)
            if client is not None and client.is_configured():
                available.append(provider)
        return available

    def is_configured(self, selection_override: Optional[Dict[str, Any]] = None) -> bool:
        return bool(self.available_providers(selection_override))

    def get_last_used_provider(self) -> Optional[str]:
        return self._last_used_provider

    def get_run_incidents(self) -> List[Dict[str, Any]]:
        return [dict(item) for item in self._run_incidents if isinstance(item, dict)]

    def get_run_warning_count(self) -> int:
        return sum(1 for item in self._run_incidents if str(item.get("severity") or "").lower() == "warning")

    def get_partial_ai_result(self) -> Dict[str, Any]:
        """Return the latest partial sections generated during current run."""
        return {"sections": [dict(section) for section in self._partial_sections]}

    def resilience_metrics_payload(self) -> Dict[str, Any]:
        return {
            "limiter": self._limiter.snapshot(),
            "circuit_breaker": self._breaker.snapshot(),
            "router": self._resilience_router.metrics_snapshot(),
        }

    def _append_incidents(self, incidents: List[Dict[str, Any]]) -> None:
        if not isinstance(incidents, list):
            return
        for incident in incidents:
            if not isinstance(incident, dict):
                continue
            item = dict(incident)
            self._run_incidents.append(item)
            # Emit warning to timeline for UI observability.
            severity = str(item.get("severity") or "").lower()
            if severity in {"warning", "error"}:
                provider = str(item.get("provider") or "")
                phase = str(item.get("phase") or "")
                message = str(item.get("message") or "")
                section_id = str(item.get("section_id") or "")
                section_path = str(item.get("section_path") or "")
                self._emit_trace(
                    step=f"ai.incident.{phase or 'unknown'}",
                    status="warn" if severity == "warning" else "error",
                    title=message[:180] or "Incidencia de proveedor",
                    meta={
                        "provider": provider,
                        "phase": phase,
                        "sectionId": section_id,
                        "sectionPath": section_path,
                    },
                )

    def get_model_for_provider(
        self,
        provider: Optional[str],
        *,
        selection_override: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        if provider not in _PROVIDER_SET:
            return None

        selection = self._resolve_selection(selection_override)
        if provider == selection.get("provider"):
            selected_model = str(selection.get("model") or "").strip()
            if selected_model:
                return selected_model

        if provider == selection.get("fallback_provider"):
            fallback_model = str(selection.get("fallback_model") or "").strip()
            if fallback_model:
                return fallback_model

        if provider == "gemini":
            return str(getattr(settings, "GEMINI_MODEL", "gemini-2.0-flash"))
        if provider == "mistral":
            return str(getattr(settings, "MISTRAL_MODEL", "mistral-medium-2505"))
        if provider == "openrouter":
            return str(getattr(settings, "OPENROUTER_MODEL", "openai/gpt-oss-120b:free"))
        return None

    @staticmethod
    def _contains_marker(message: str, markers: tuple[str, ...]) -> bool:
        lowered = str(message or "").lower()
        return any(marker in lowered for marker in markers)

    def _is_timeout_error(self, message: str) -> bool:
        return self._contains_marker(message, _TIMEOUT_MARKERS)

    def _is_exhausted_error(self, message: str) -> bool:
        return self._contains_marker(message, _EXHAUSTED_MARKERS)

    def _is_rate_limited_error(self, message: str) -> bool:
        return self._contains_marker(message, _RATE_LIMIT_MARKERS)

    def _is_auth_error(self, message: str) -> bool:
        return self._contains_marker(message, _AUTH_MARKERS)

    def _is_transient_error(self, message: str) -> bool:
        return self._is_timeout_error(message) or self._contains_marker(message, _TRANSIENT_MARKERS)

    def providers_status_payload(self, selection_override: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        selection = self._resolve_selection(selection_override)
        selected_provider = str(selection.get("provider") or _PROVIDER_ORDER[0]).lower().strip()
        if selected_provider not in _PROVIDER_SET:
            selected_provider = _PROVIDER_ORDER[0]
        requested_fallback = str(selection.get("fallback_provider") or "").lower().strip()
        if requested_fallback not in _PROVIDER_SET or requested_fallback == selected_provider:
            requested_fallback = self._fallback_for(selected_provider)
        selected_model = str(selection.get("model") or self._default_model_for_provider(selected_provider))
        if not self._model_matches_provider(selected_provider, selected_model):
            selected_model = self._default_model_for_provider(selected_provider)
        mode = str(selection.get("mode") or "auto")

        fallback_provider = ""
        if mode.lower().strip() == "auto":
            fallback_provider = self._effective_fallback_provider(
                selected_provider,
                requested_fallback,
                selection_override=selection,
            )
        fallback_model = ""
        if fallback_provider:
            requested_fallback_model = str(selection.get("fallback_model") or "").strip()
            if not self._model_matches_provider(fallback_provider, requested_fallback_model):
                requested_fallback_model = self._default_model_for_provider(fallback_provider)
            fallback_model = requested_fallback_model

        providers_payload: List[Dict[str, Any]] = []
        for provider in _PROVIDER_ORDER:
            client = self._clients.get(provider)
            configured = bool(client and client.is_configured())
            if provider == selected_provider:
                model = selected_model
            elif provider == fallback_provider:
                model = fallback_model
            else:
                model = self._default_model_for_provider(provider)
            provider_payload = self._metrics.payload_for_provider(
                provider,
                model=model,
                configured=configured,
            )
            provider_payload["display_name"] = self._provider_display_name(provider)
            probe_status = str(
                provider_payload.get("last_probe_status")
                or provider_payload.get("probe", {}).get("status")
                or "UNVERIFIED"
            ).upper()
            provider_payload["online"] = bool(configured and probe_status in {"OK", "RATE_LIMITED"})
            providers_payload.append(provider_payload)

        return {
            "selected_provider": selected_provider,
            "selected_model": selected_model,
            "fallback_provider": fallback_provider,
            "fallback_model": fallback_model,
            "mode": mode,
            "providers": providers_payload,
        }

    def probe_providers(
        self,
        *,
        selection_override: Optional[Dict[str, Any]] = None,
        timeout: int = 8,
    ) -> Dict[str, Any]:
        """Run real low-cost provider probes and return refreshed status payload."""
        selection = self._resolve_selection(selection_override)
        for provider in _PROVIDER_ORDER:
            client = self._clients.get(provider)
            if client is None:
                continue
            model = self.get_model_for_provider(
                provider,
                selection_override=selection,
            ) or self._default_model_for_provider(provider)

            if not client.is_configured():
                self._metrics.record_probe(
                    provider,
                    status="UNVERIFIED",
                    detail="Provider no configurado.",
                )
                continue

            probe_result: Dict[str, Any]
            try:
                probe_result = client.probe(timeout=timeout, model=model)
            except Exception as exc:
                probe_result = {
                    "status": "ERROR",
                    "detail": str(exc)[:240],
                    "retry_after_s": None,
                }

            probe_status = str(probe_result.get("status") or "ERROR").upper().strip() or "ERROR"
            probe_detail = str(probe_result.get("detail") or "").strip()
            retry_after = probe_result.get("retry_after_s")
            probe_meta = probe_result.get("meta") if isinstance(probe_result.get("meta"), dict) else None

            self._metrics.record_probe(
                provider,
                status=probe_status,
                detail=probe_detail,
                retry_after_s=retry_after if isinstance(retry_after, (int, float)) else None,
                meta=probe_meta,
            )

            if probe_status == "EXHAUSTED":
                self._metrics.record_exhausted(provider, message=probe_detail or f"{provider} exhausted")
            elif probe_status == "RATE_LIMITED":
                wait = retry_after if isinstance(retry_after, (int, float)) else 10
                self._metrics.record_rate_limited(
                    provider,
                    retry_after_s=wait,
                    message=probe_detail or f"{provider} rate-limited",
                )
            elif probe_status == "AUTH_ERROR":
                self._metrics.record_error(provider, message=probe_detail or "Auth error", kind="auth")

            if probe_status == "EXHAUSTED":
                self._metrics.record_exhausted(provider, message=probe_detail or f"{provider} exhausted")
            elif probe_status == "RATE_LIMITED":
                wait = retry_after if isinstance(retry_after, (int, float)) else 10
                self._metrics.record_rate_limited(
                    provider,
                    retry_after_s=wait,
                    message=probe_detail or f"{provider} rate-limited",
                )
            elif probe_status == "AUTH_ERROR":
                self._metrics.record_error(provider, message=probe_detail or "Auth error", kind="auth")
            elif probe_status == "ERROR":
                self._metrics.record_error(provider, message=probe_detail or "Probe error", kind="error")

        return self.providers_status_payload(selection_override=selection)

    @staticmethod
    def _clip_preview(text: str, max_chars: int = 480) -> str:
        normalized = " ".join(str(text or "").split())
        if len(normalized) <= max_chars:
            return normalized
        return f"{normalized[: max_chars - 3]}..."

    _SECRET_PATTERNS = (
        "Authorization", "Bearer ", "sk-", "OPENROUTER_API_KEY",
        "GEMINI_API_KEY", "MISTRAL_API_KEY", "api_key", "apiKey",
    )

    @staticmethod
    def _redact_secrets(text: str) -> str:
        """Remove API keys and tokens from text before emitting to clients."""
        result = str(text or "")
        for pattern in AIService._SECRET_PATTERNS:
            if pattern in result:
                result = result.replace(pattern, "[REDACTED]")
        # Redact Bearer tokens: Bearer XXXX...
        import re
        result = re.sub(r'Bearer\s+[A-Za-z0-9_\-\.]+', 'Bearer [REDACTED]', result)
        # Redact sk-... style keys
        result = re.sub(r'sk-[A-Za-z0-9]{8,}', '[REDACTED]', result)
        return result

    def _emit_trace(
        self,
        *,
        step: str,
        status: str,
        title: str,
        detail: str = "",
        meta: Optional[Dict[str, Any]] = None,
        preview: Optional[Dict[str, str]] = None,
    ) -> None:
        if self._trace_hook is None:
            return
        event: Dict[str, Any] = {
            "step": step,
            "status": status,
            "title": title,
        }
        if detail:
            event["detail"] = detail
        if meta:
            event["meta"] = meta
        if preview:
            event["preview"] = preview
        try:
            self._trace_hook(event)
        except Exception:
            logger.debug("AIService trace hook failed", exc_info=True)

    def _emit_progress(
        self,
        current: int,
        total: int,
        path: str,
        provider: str,
        *,
        stage: str,
    ) -> None:
        if self._progress_cb is None:
            return
        try:
            self._progress_cb(
                int(current),
                int(total),
                str(path or ""),
                str(provider or ""),
                stage=stage,
            )
        except Exception:
            logger.debug("AIService progress callback failed", exc_info=True)

    def _ensure_not_cancelled(self) -> None:
        if self._cancel_check is None:
            return
        try:
            if self._cancel_check():
                raise GenerationCancelledError("Generacion cancelada por el usuario.")
        except GenerationCancelledError:
            raise
        except Exception:
            logger.debug("AIService cancel check failed", exc_info=True)

    def _sleep_with_cancel(self, seconds: float) -> None:
        if seconds <= 0:
            return
        if self._cancel_check is None:
            time.sleep(seconds)
            return

        remaining = seconds
        while remaining > 0:
            self._ensure_not_cancelled()
            chunk = min(remaining, 0.5)
            time.sleep(chunk)
            remaining -= chunk

    def health_payload(self) -> Dict[str, Any]:
        selection = self._refresh_selection()
        available = self.available_providers(selection)
        fallback_on_quota = str(selection.get("mode") or "auto") == "auto" and bool(
            getattr(settings, "AI_FALLBACK_ON_QUOTA", True)
        )
        if not available:
            return {
                "configured": False,
                "engine": "simulation",
                "model": None,
                "reachable": False,
                "message": "No AI provider configured. Set GEMINI_API_KEY, MISTRAL_API_KEY or OPENROUTER_API_KEY.",
                "availableProviders": [],
                "fallbackOnQuota": fallback_on_quota,
            }

        primary = available[0]
        model = self.get_model_for_provider(primary, selection_override=selection)
        message = f"{primary.capitalize()} configurado (modelo: {model})"

        if fallback_on_quota and len(available) > 1:
            message = f"{message}. Respaldo automatico por cuota activo -> {available[1]}."

        return {
            "configured": True,
            "engine": primary,
            "model": model,
            "reachable": True,
            "message": message,
            "availableProviders": available,
            "fallbackOnQuota": fallback_on_quota,
        }

    def generate(
        self,
        project: Dict[str, Any],
        format_detail: Optional[Dict[str, Any]] = None,
        prompt: Optional[Dict[str, Any]] = None,
        *,
        trace_hook: Optional[Callable[[Dict[str, Any]], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
        progress_cb: Optional[Callable[..., None]] = None,
        selection_override: Optional[Dict[str, Any]] = None,
        resume_from_partial: bool = False,
        seed_sections_override: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """Run the full generation pipeline."""
        self._last_used_provider = None
        self._trace_hook = trace_hook
        self._cancel_check = cancel_check
        self._progress_cb = progress_cb
        active_selection = self._resolve_selection(selection_override)
        self._active_selection = dict(active_selection)
        self._run_incidents = []
        self._last_call_result = None
        self._partial_sections = []

        project_id = project.get("id", "unknown")
        logger.info("AIService.generate START projectId=%s", project_id)
        self._emit_trace(
            step="ai.generate.start",
            status="running",
            title="Generacion IA iniciada",
            detail="Preparando prompt y secciones del formato.",
        )
        self._ensure_not_cancelled()

        template_text = ""
        if prompt:
            template_text = prompt.get("template", "")
        values = project.get("variables") or project.get("values", {})
        base_prompt = self.renderer.render(
            template_text,
            values,
            trace_hook=self._trace_hook,
        )

        if not base_prompt.strip():
            base_prompt = (
                f"Genera contenido academico para un documento de tesis. Titulo: {project.get('title', 'Sin titulo')}."
            )
            logger.warning(
                "Empty prompt template, using fallback. projectId=%s",
                project_id,
            )
            self._emit_trace(
                step="prompt.render",
                status="warn",
                title="Prompt base vacio, usando respaldo",
                detail="Se aplico un prompt generico para continuar.",
                preview={"prompt": self._clip_preview(base_prompt)},
            )

        definition: Dict[str, Any] = {}
        if isinstance(format_detail, dict):
            raw = format_detail.get("definition", {})
            if isinstance(raw, dict):
                definition = raw

        self._ensure_not_cancelled()
        section_index = compile_definition_to_section_index(definition)
        if not section_index:
            section_index = [{"sectionId": "sec-0001", "path": "Contenido Principal"}]
            logger.warning(
                "No section index from definition, using generic section. projectId=%s",
                project_id,
            )
            self._emit_trace(
                step="format.section_index",
                status="warn",
                title="Formato sin secciones detectadas",
                detail="Se usara una seccion generica para evitar bloqueo.",
                meta={"sectionTotal": 1},
            )
        else:
            self._emit_trace(
                step="format.section_index",
                status="done",
                title=f"Formato parseado ({len(section_index)} secciones)",
                meta={"sectionTotal": len(section_index)},
            )

        # Merge project-level values for system prompt rendering
        project_values = dict(values)
        project_values.setdefault("title", project.get("title", ""))

        seeded_sections: List[Dict[str, str]] = []
        if resume_from_partial:
            if isinstance(seed_sections_override, list) and seed_sections_override:
                seeded_sections = self._extract_seed_sections(
                    {"sections": seed_sections_override},
                    section_index=section_index,
                )
            else:
                seeded_sections = self._extract_seed_sections(
                    project.get("ai_result"),
                    section_index=section_index,
                )
            if seeded_sections:
                self._partial_sections = [dict(item) for item in seeded_sections]
                self._emit_trace(
                    step="ai.resume",
                    status="warn",
                    title=f"Reanudando generacion desde seccion {len(seeded_sections) + 1}/{len(section_index)}",
                    detail=f"Se reutilizan {len(seeded_sections)} secciones ya generadas.",
                    meta={
                        "seededSections": len(seeded_sections),
                        "sectionTotal": len(section_index),
                    },
                )

        sections = self._generate_sections(
            base_prompt=base_prompt,
            section_index=section_index,
            project_id=project_id,
            values=project_values,
            selection=active_selection,
            seed_sections=seeded_sections,
        )

        # --- Post-processing correction pass ---
        if settings.AI_CORRECTION_ENABLED:
            self._emit_trace(
                step="ai.correction",
                status="running",
                title="Aplicando limpieza y correccion",
            )
            sections = self._correct_ai_result(
                sections=sections,
                definition=definition,
                values=project_values,
                project_id=project_id,
                selection=active_selection,
            )
            self._emit_trace(
                step="ai.correction",
                status="done",
                title="Limpieza y correccion completadas",
                meta={"sections": len(sections)},
            )

        # --- Completeness check: detect and repair placeholders ---
        sections = self._ensure_completeness(sections, project_id=project_id)

        try:
            ai_result = self.validator.build_ai_result(sections)
        except ValidationError as exc:
            logger.error("Validation failed for projectId=%s: %s", project_id, exc)
            self._emit_trace(
                step="ai.validation",
                status="error",
                title="Validacion de salida fallida",
                detail=str(exc),
            )
            raise RuntimeError(f"AI output validation failed: {exc}") from exc
        self._emit_trace(
            step="ai.validation",
            status="done",
            title="Salida IA validada",
            meta={"sections": len(ai_result.get("sections", []))},
        )

        logger.info(
            "AIService.generate DONE projectId=%s sections=%d provider=%s",
            project_id,
            len(ai_result.get("sections", [])),
            self._last_used_provider,
        )
        self._emit_trace(
            step="ai.generate.done",
            status="done",
            title="Generacion IA completada",
            detail=f"Proveedor final: {self._last_used_provider or 'desconocido'}.",
            meta={
                "provider": self._last_used_provider,
                "warnings": self.get_run_warning_count(),
                "incidents": len(self._run_incidents),
            },
        )
        self._trace_hook = None
        self._cancel_check = None
        self._progress_cb = None
        self._active_selection = {}
        return ai_result

    @staticmethod
    def _section_lookup_key(section_id: str, path: str) -> str:
        canonical_id = str(section_id or "").strip()
        if canonical_id:
            return f"id:{canonical_id}"
        return f"path:{str(path or '').strip()}"

    def _extract_seed_sections(
        self,
        ai_result: Any,
        *,
        section_index: List[Dict[str, Any]],
    ) -> List[Dict[str, str]]:
        if not isinstance(ai_result, dict):
            return []
        raw_sections = ai_result.get("sections")
        if not isinstance(raw_sections, list):
            return []

        seeded_map: Dict[str, str] = {}
        for section in raw_sections:
            if not isinstance(section, dict):
                continue
            content = section.get("content")
            if not isinstance(content, str) or not content.strip():
                continue
            section_id = str(section.get("sectionId") or "").strip()
            path = str(section.get("path") or "").strip()
            if not section_id and not path:
                continue
            key = self._section_lookup_key(section_id, path)
            if key not in seeded_map:
                seeded_map[key] = content

        ordered: List[Dict[str, str]] = []
        for idx, section in enumerate(section_index, 1):
            section_id = str(section.get("sectionId") or f"sec-{idx:04d}")
            path = str(section.get("path") or f"Section {idx}")
            key = self._section_lookup_key(section_id, path)
            seeded_content = seeded_map.get(key)
            if seeded_content is None:
                alt_key = self._section_lookup_key("", path)
                seeded_content = seeded_map.get(alt_key)
            if seeded_content is None:
                break
            ordered.append(
                {
                    "sectionId": section_id,
                    "path": path,
                    "content": seeded_content,
                }
            )
        return ordered

    def _generate_sections(
        self,
        base_prompt: str,
        section_index: List[Dict[str, Any]],
        project_id: str,
        values: Dict[str, Any] | None = None,
        selection: Optional[Dict[str, Any]] = None,
        seed_sections: Optional[List[Dict[str, str]]] = None,
    ) -> List[Dict[str, str]]:
        """Generate content for each section in the index.

        Includes an inter-section delay to stay within API rate limits
        when generating many sections (e.g. 74 for a full thesis format).
        """
        sections: List[Dict[str, str]] = []
        total = len(section_index)
        preferred_provider: Optional[str] = None
        disabled_providers: Set[str] = set()
        provider_order = self._provider_order(selection)
        default_provider = provider_order[0] if provider_order else _PROVIDER_ORDER[0]
        seeded_count = 0
        if seed_sections:
            for seeded in seed_sections:
                if not isinstance(seeded, dict):
                    continue
                seeded_content = seeded.get("content")
                if not isinstance(seeded_content, str) or not seeded_content.strip():
                    continue
                seeded_id = str(seeded.get("sectionId") or "").strip()
                seeded_path = str(seeded.get("path") or "").strip()
                if not seeded_id and not seeded_path:
                    continue
                sections.append(
                    {
                        "sectionId": seeded_id or f"sec-{len(sections) + 1:04d}",
                        "path": seeded_path or f"Section {len(sections) + 1}",
                        "content": seeded_content,
                    }
                )
            seeded_count = len(sections)
            if seeded_count > 0:
                self._partial_sections = [dict(item) for item in sections]

        for i, sec in enumerate(section_index[seeded_count:], seeded_count + 1):
            self._ensure_not_cancelled()
            section_id = str(sec.get("sectionId") or f"sec-{i:04d}")
            path = str(sec.get("path") or f"Section {i}")

            # Throttle between generated sections to avoid rate-limit bursts
            if sections and _INTER_SECTION_DELAY_S > 0:
                self._sleep_with_cancel(_INTER_SECTION_DELAY_S)

            logger.info(
                "Generating section %d/%d: %s (projectId=%s)",
                i,
                total,
                path,
                project_id,
            )
            self._emit_trace(
                step="ai.generate.section",
                status="running",
                title=f"IA: seccion {i}/{total} ({path})",
                meta={
                    "sectionIndex": i,
                    "sectionTotal": total,
                    "sectionId": section_id,
                    "sectionPath": path,
                },
            )
            self._emit_progress(
                i,
                total,
                path,
                preferred_provider or default_provider,
                stage="section_start",
            )

            section_prompt = self.renderer.build_section_prompt(
                base_prompt=base_prompt,
                section_path=path,
                section_id=section_id,
                extra_context=sec.get("hints", ""),
                values=values,
            )

            content, used_provider = self._generate_with_provider_fallback(
                section_prompt,
                preferred_provider=preferred_provider,
                section_current=i,
                section_total=total,
                section_path=path,
                section_id=section_id,
                phase="generate_section",
                context=sec.get("hints", ""),
                selection=selection,
                disabled_for_job=disabled_providers,
            )
            preferred_provider = used_provider
            self._last_used_provider = used_provider

            # Build enriched trace data for Inspector IA
            _model = self.get_model_for_provider(used_provider) or "-"
            _prompt_preview = self._redact_secrets(
                section_prompt[:2000] + ("..." if len(section_prompt) > 2000 else "")
            )
            _messages = [
                {"role": "system", "content": self._redact_secrets(section_prompt[:1500])},
            ]
            if sec.get("hints"):
                _messages.append({"role": "user", "content": self._redact_secrets(str(sec["hints"])[:500])})

            self._emit_trace(
                step="ai.generate.section",
                status="done",
                title=f"Seccion {i}/{total} completada ({path})",
                meta={
                    "sectionIndex": i,
                    "sectionTotal": total,
                    "sectionId": section_id,
                    "sectionPath": path,
                    "provider": used_provider,
                    "model": _model,
                    "messages": _messages,
                    "usage": {
                        "prompt_tokens": max(1, len(section_prompt) // 4),
                        "completion_tokens": max(1, len(content) // 4),
                    },
                },
                preview={
                    "raw": self._redact_secrets(self._clip_preview(content, max_chars=2000)),
                    "prompt": _prompt_preview,
                },
            )
            self._emit_progress(
                i,
                total,
                path,
                used_provider,
                stage="section_done",
            )

            sections.append(
                {
                    "sectionId": section_id,
                    "path": path,
                    "content": content,
                }
            )
            self._partial_sections = [dict(item) for item in sections]

        return sections

    def _generate_with_provider_fallback(
        self,
        prompt: str,
        *,
        preferred_provider: Optional[str] = None,
        section_current: int = 0,
        section_total: int = 0,
        section_path: str = "",
        section_id: str = "",
        phase: str = "generate_section",
        context: str = "",
        selection: Optional[Dict[str, Any]] = None,
        disabled_for_job: Optional[Set[str]] = None,
    ) -> Tuple[str, str]:
        """Call the resilient router and keep compatibility with existing call sites."""
        # Keep router references aligned with runtime overrides/mocks.
        self._resilience_router.set_providers(self._clients)
        self._resilience_router.set_sleep_fn(self._sleep_with_cancel)

        runtime_selection = self._resolve_selection(selection)
        providers = self._provider_order(runtime_selection)
        auto_mode = str(runtime_selection.get("mode") or "auto").lower().strip() == "auto"
        fallback_enabled = auto_mode and bool(getattr(settings, "AI_FALLBACK_ON_QUOTA", True))
        disabled = disabled_for_job if disabled_for_job is not None else set()

        if preferred_provider in providers and preferred_provider not in disabled:
            providers = [preferred_provider] + [p for p in providers if p != preferred_provider]

        if not fallback_enabled and providers:
            providers = providers[:1]

        request = LLMRequest(
            phase=phase,
            prompt=prompt,
            context=context,
            section_id=section_id,
            section_path=section_path,
            tenant_id=str(getattr(settings, "APP_ENV", "") or "global"),
            preferred_provider=preferred_provider,
            provider_candidates=providers,
            selection_mode="auto" if fallback_enabled else "fixed",
            metadata={
                "request_id": f"{phase}:{section_id or section_path}:{int(time.time())}",
                "section_current": section_current,
                "section_total": section_total,
            },
        )

        result = self._resilience_router.callLLMWithResilience(
            request,
            disabled_for_job=disabled,
        )
        self._last_call_result = result
        self._append_incidents(result.incidents)

        if result.status == "degraded":
            self._emit_trace(
                step="ai.provider.degraded",
                status="warn",
                title="Fase opcional en modo degradado",
                detail=f"Se omitio llamada remota para {phase}.",
                meta={
                    "phase": phase,
                    "provider": result.provider,
                    "sectionId": section_id,
                    "sectionPath": section_path,
                },
            )

        # When fallback happened, move progress provider to the effective provider.
        # Use providers[0] as the baseline when preferred_provider is None
        # (first section) to avoid a false-positive fallback notification.
        expected = preferred_provider or (providers[0] if providers else None)
        if result.provider and result.provider != expected and result.provider != "DEGRADED":
            self._emit_progress(
                section_current,
                section_total,
                section_path,
                result.provider,
                stage="provider_fallback",
            )

        return result.content, result.provider

    # ------------------------------------------------------------------
    # Post-processing correction
    # ------------------------------------------------------------------

    _CORRECTION_PROMPT_PATH = Path(__file__).resolve().parents[4] / "data" / "correction_prompt.txt"

    def _correct_ai_result(
        self,
        sections: List[Dict[str, str]],
        definition: Dict[str, Any],
        values: Dict[str, Any],
        project_id: str,
        selection: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, str]]:
        """Run a correction pass on the raw AI-generated sections.

        Sends the entire ai_result (all sections) plus the format definition
        and project values to the AI, asking it to clean up content following
        strict rules (no markdown, no placeholders, minimum word counts, etc.).

        If the correction fails for any reason (parse error, provider error),
        the original sections are returned unchanged — this step is best-effort
        and must never break the pipeline.
        """
        logger.info(
            "Correction pass START projectId=%s (%d sections)",
            project_id,
            len(sections),
        )

        try:
            correction_prompt = self._build_correction_prompt(
                sections=sections,
                definition=definition,
                values=values,
            )
        except FileNotFoundError:
            logger.warning(
                "Correction prompt file not found at %s, skipping correction.",
                self._CORRECTION_PROMPT_PATH,
            )
            self._emit_trace(
                step="ai.correction",
                status="warn",
                title="No se encontro prompt de correccion",
                detail="Se mantiene contenido original de la IA.",
            )
            return sections

        try:
            raw_response, provider = self._generate_with_provider_fallback(
                correction_prompt,
                preferred_provider=self._last_used_provider,
                phase="cleanup_correction",
                section_id="cleanup_correction",
                section_path="Limpieza/Correccion",
                context=json.dumps({"sections": sections}, ensure_ascii=False),
                selection=selection,
            )
            if self._last_call_result and self._last_call_result.status == "degraded":
                self._emit_trace(
                    step="ai.correction",
                    status="warn",
                    title="Limpieza opcional omitida (modo degradado)",
                    detail="Se mantiene contenido original y el documento continua.",
                )
                return sections
            if provider != "DEGRADED":
                self._last_used_provider = provider
        except Exception as exc:
            logger.warning(
                "Correction pass FAILED (provider error): %s. Returning uncorrected sections. projectId=%s",
                str(exc)[:200],
                project_id,
            )
            self._emit_trace(
                step="ai.correction",
                status="warn",
                title="Correccion omitida por error de proveedor",
                detail=str(exc)[:220],
            )
            return sections

        # Parse the JSON response
        corrected = self._parse_corrected_json(raw_response, sections, project_id)
        if corrected is sections:
            self._emit_trace(
                step="ai.correction",
                status="warn",
                title="No se pudo aplicar correccion estructurada",
                detail="Se conserva la salida original de IA.",
            )
        else:
            self._emit_trace(
                step="ai.correction",
                status="done",
                title="Correccion estructurada aplicada",
                preview={
                    "raw": self._clip_preview(raw_response),
                    "clean": self._clip_preview(corrected[0]["content"] if corrected else ""),
                },
            )
        return corrected

    # ------------------------------------------------------------------
    # Completeness check — detect and repair placeholders / empty stubs
    # ------------------------------------------------------------------

    def _ensure_completeness(
        self,
        sections: List[Dict[str, str]],
        *,
        project_id: str = "",
    ) -> List[Dict[str, str]]:
        """Detect placeholder content and auto-fill known section types.

        Runs after ``_correct_ai_result`` and before ``build_ai_result``.
        For known sections (dedicatoria, agradecimiento, abreviaturas),
        replaces placeholder text with formal generic content.
        Unknown sections with placeholders are logged as warnings.
        """
        issues = detect_placeholders(sections)
        if not issues:
            logger.info(
                "Completeness check PASSED — no placeholders (projectId=%s)",
                project_id,
            )
            self._emit_trace(
                step="ai.completeness",
                status="done",
                title="Validacion de completitud OK",
                meta={"issues": 0},
            )
            return sections

        logger.warning(
            "Completeness check found %d issue(s) in projectId=%s: %s",
            len(issues),
            project_id,
            ", ".join(f"{i.section_id}({i.issue_type})" for i in issues),
        )

        repaired = 0
        remaining_issues: List[str] = []

        for issue in issues:
            # Find the section in the list
            target = None
            for sec in sections:
                if sec.get("sectionId") == issue.section_id:
                    target = sec
                    break
            if target is None:
                continue

            replacement = autofill_section(target, issue.issue_type)
            if replacement:
                target["content"] = replacement
                repaired += 1
                logger.info(
                    "Autofilled section '%s' (path='%s', type=%s)",
                    issue.section_id,
                    issue.path,
                    issue.issue_type,
                )
            else:
                remaining_issues.append(
                    f"{issue.section_id}: {issue.issue_type} — {issue.sample[:80]}"
                )

        status = "done" if not remaining_issues else "warn"
        detail = ""
        if remaining_issues:
            detail = (
                f"Se repararon {repaired} secciones. "
                f"Quedan {len(remaining_issues)} con contenido dudoso."
            )
        else:
            detail = f"Se repararon {repaired} secciones con placeholders."

        self._emit_trace(
            step="ai.completeness",
            status=status,
            title="Validacion de completitud",
            detail=detail,
            meta={
                "issues_found": len(issues),
                "repaired": repaired,
                "remaining": len(remaining_issues),
            },
        )

        return sections

    def _build_correction_prompt(
        self,
        sections: List[Dict[str, str]],
        definition: Dict[str, Any],
        values: Dict[str, Any],
    ) -> str:
        """Build the correction prompt by substituting template markers."""
        template = self._CORRECTION_PROMPT_PATH.read_text(encoding="utf-8")

        ai_result_json = json.dumps({"sections": sections}, ensure_ascii=False)
        format_json = json.dumps(definition, ensure_ascii=False)
        values_json = json.dumps(values, ensure_ascii=False)

        prompt = template.replace("<<<FORMAT_JSON>>>", format_json)
        prompt = prompt.replace("<<<VALUES_JSON>>>", values_json)
        prompt = prompt.replace("<<<AI_RESULT_JSON>>>", ai_result_json)

        # Substitute alternative markers too
        prompt = prompt.replace("<<<PEGAR_AQUI_FORMAT_JSON>>>", format_json)
        prompt = prompt.replace("<<<PEGAR_AQUI_VALUES_JSON>>>", values_json)
        prompt = prompt.replace("<<<PEGAR_AQUI_AI_RESULT_JSON>>>", ai_result_json)

        return prompt

    @staticmethod
    def _parse_corrected_json(
        raw_response: str,
        original_sections: List[Dict[str, str]],
        project_id: str,
    ) -> List[Dict[str, str]]:
        """Parse the AI correction response as JSON.

        Attempts to extract a valid ``{"sections": [...]}`` structure from
        the response.  If parsing fails or the structure is invalid, returns
        the original uncorrected sections.
        """
        # Strip potential markdown code fences the AI might have added
        text = raw_response.strip()
        if text.startswith("```"):
            # Remove opening fence (```json or ```)
            first_newline = text.index("\n") if "\n" in text else 3
            text = text[first_newline + 1 :]
        if text.endswith("```"):
            text = text[:-3].rstrip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # Try to find JSON object in the response
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    data = json.loads(text[start:end])
                except json.JSONDecodeError:
                    logger.warning(
                        "Correction pass: could not parse JSON from AI response. "
                        "Returning uncorrected sections. projectId=%s",
                        project_id,
                    )
                    return original_sections
            else:
                logger.warning(
                    "Correction pass: no JSON found in AI response. Returning uncorrected sections. projectId=%s",
                    project_id,
                )
                return original_sections

        if not isinstance(data, dict) or "sections" not in data:
            logger.warning(
                "Correction pass: response missing 'sections' key. Returning uncorrected sections. projectId=%s",
                project_id,
            )
            return original_sections

        corrected_sections = data["sections"]
        if not isinstance(corrected_sections, list):
            logger.warning(
                "Correction pass: 'sections' is not a list. Returning uncorrected sections. projectId=%s",
                project_id,
            )
            return original_sections

        # Always merge by sectionId to avoid ordering issues.
        original_ids = {s["sectionId"] for s in original_sections}
        corrected_by_id: Dict[str, Dict[str, Any]] = {}
        for item in corrected_sections:
            if not isinstance(item, dict):
                continue
            sid = item.get("sectionId")
            if not isinstance(sid, str) or not sid.strip():
                continue
            corrected_by_id[sid] = item

        corrected_ids = set(corrected_by_id.keys())
        if original_ids != corrected_ids:
            logger.warning(
                "Correction pass: sectionId mismatch (original=%d, corrected=%d). "
                "Will merge partial corrected content by sectionId. projectId=%s",
                len(original_ids),
                len(corrected_ids),
                project_id,
            )

        result: List[Dict[str, str]] = []
        for orig in original_sections:
            sid = orig["sectionId"]
            corrected_item = corrected_by_id.get(sid)
            content = orig["content"]
            if isinstance(corrected_item, dict):
                corrected_content = corrected_item.get("content")
                if isinstance(corrected_content, str) and corrected_content.strip():
                    content = corrected_content
            result.append(
                {
                    "sectionId": sid,
                    "path": orig["path"],
                    "content": content,
                }
            )

        logger.info(
            "Correction pass DONE projectId=%s (%d sections corrected)",
            project_id,
            len(result),
        )
        return result
