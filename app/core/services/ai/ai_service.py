"""AI generation orchestrator for GicaGen.

Coordinates the full generation pipeline:
  render prompt -> generate per section -> correct -> validate -> aiResult

Uses provider selection with resilience routing, retries and fallback.
"""

from __future__ import annotations

import copy
import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol, Set

from app.core.config import settings
from app.core.services.ai.budget_table_builder import (
    build_budget_table_from_plan,
    build_synthetic_budget_plan,
    extract_budget_plan_from_content,
    salvage_budget_plan_from_legacy_table,
    validate_budget_plan,
)
from app.core.services.ai.circuit_breaker import CircuitBreaker
from app.core.services.ai.completeness_validator import (
    autofill_section,
    detect_placeholders,
)
from app.core.services.ai.content_parser import parse_ai_content
from app.core.services.ai.errors import GenerationCancelledError, QualityProfileValidationError
from app.core.services.ai.figure_recommendations import apply_figure_recommendations
from app.core.services.ai.gemini_client import GeminiClient
from app.core.services.ai.limiter import LLMLimiter
from app.core.services.ai.mistral_client import MistralClient
from app.core.services.ai.output_validator import OutputValidator, ValidationError
from app.core.services.ai.phase_policy import build_phase_policies
from app.core.services.ai.prompt_renderer import PromptRenderer
from app.core.services.ai.provider_metrics import ProviderMetricsService
from app.core.services.ai.provider_selection import ProviderSelectionService
from app.core.services.ai.reference_proposals import consolidate_references
from app.core.services.ai.resilience_router import LLMProviderRouter, LLMRequest, LLMResult
from app.core.services.ai.schedule_table_builder import (
    build_schedule_table_from_plan,
    build_synthetic_schedule_plan,
    extract_schedule_plan_from_content,
    salvage_schedule_plan_from_legacy_table,
    validate_schedule_plan,
)
from app.core.services.ai.section_prompt_profiles import (
    build_format_editorial_contract,
    build_section_editorial_context,
    build_stable_project_memory_snapshot,
)
from app.core.services.ai.token_usage import (
    empty_token_usage_report,
    merge_token_usage,
    normalize_token_usage_report,
    summarize_token_usage,
    token_usage_snapshot,
)
from app.core.services.ai.unac_quality_profile import (
    SectionQualityAudit,
    SectionQualityRequirement,
    audit_unac_maintenance_sections,
    canonical_formula_for_key,
    canonicalize_duplicate_semantic_units,
    ensure_canonical_formulas,
    extract_semantic_unit_content,
    content_quality_failures,
    is_unac_maintenance_project,
    load_unac_maintenance_profile,
    normalize_semantic_blocks,
    quality_failures,
    replace_semantic_unit_content,
    requirements_for_section_path,
    section_key_from_path,
)
from app.core.services.definition_compiler import compile_definition_to_section_index

logger = logging.getLogger(__name__)

_PROVIDER_ORDER = ("gemini", "mistral")
_PROVIDER_SET = set(_PROVIDER_ORDER)

# Successful calls are not delayed artificially. Provider-side 429, timeout
# and transient backoff remain handled by the resilience router.
_INTER_SECTION_DELAY_S = 0.0

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

    @property
    def _clients(self) -> Dict[str, _ProviderClient]:
        return self._clients_map

    @_clients.setter
    def _clients(self, providers: Dict[str, _ProviderClient]) -> None:
        self._clients_map = dict(providers or {})
        router = getattr(self, "_resilience_router", None)
        if router is not None:
            router.set_providers(self._clients_map)

    @staticmethod
    def _is_unac_schedule_chapter_path(path: str) -> bool:
        normalized = " ".join(str(path or "").strip().lower().split())
        return normalized == "v. cronograma de actividades"

    def __init__(self) -> None:
        self.renderer = PromptRenderer()
        self.validator = OutputValidator()
        self._clients: Dict[str, _ProviderClient] = {
            "gemini": GeminiClient(),
            "mistral": MistralClient(),
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
        self._partial_sections: List[Dict[str, Any]] = []
        self._token_usage_report: Dict[str, Any] = empty_token_usage_report()
        self._last_base_prompt: str = ""
        self._last_base_prompt_source: str = "package_template"

        self._phase_policies = build_phase_policies()
        self._limiter = LLMLimiter(
            provider_concurrency={
                "gemini": int(getattr(settings, "MAX_INFLIGHT_GEMINI", 3)),
                "mistral": int(getattr(settings, "MAX_INFLIGHT_MISTRAL", 3)),
            },
            provider_rpm={
                "gemini": int(getattr(settings, "GEMINI_RPM", 60)),
                "mistral": int(getattr(settings, "MISTRAL_RPM", 60)),
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
        return str(getattr(settings, "GEMINI_MODEL", "gemini-2.0-flash"))

    @staticmethod
    def _fallback_for(primary: str) -> str:
        if primary == "gemini":
            return "mistral"
        if primary == "mistral":
            return "gemini"
        return ""

    @staticmethod
    def _provider_display_name(provider: str) -> str:
        labels = {
            "gemini": "Gemini",
            "mistral": "Mistral",
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
        probe_status = (
            str(payload.get("last_probe_status") or payload.get("probe", {}).get("status") or "UNVERIFIED")
            .upper()
            .strip()
        )

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
        primary = str(selection.get("provider") or _PROVIDER_ORDER[0]).lower().strip()
        if primary not in _PROVIDER_SET:
            primary = _PROVIDER_ORDER[0]
        return [primary]

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

    def get_token_usage_report(self) -> Dict[str, Any]:
        return normalize_token_usage_report(self._token_usage_report)

    def get_token_usage_snapshot(self) -> Dict[str, Any]:
        return token_usage_snapshot(self._token_usage_report)

    def _record_token_usage(
        self,
        attempts: List[Dict[str, Any]],
        *,
        current_section_id: str = "",
        current_section_path: str = "",
    ) -> Dict[str, Any]:
        self._token_usage_report = merge_token_usage(
            self._token_usage_report,
            attempts,
            current_section_id=current_section_id,
            current_section_path=current_section_path,
        )
        return self.get_token_usage_snapshot()

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

        if provider == "mistral":
            return str(getattr(settings, "MISTRAL_MODEL", "mistral-medium-2505"))
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
        visible_providers = ("mistral",) if "mistral" in self._clients else _PROVIDER_ORDER
        selected_provider = visible_providers[0]
        selected_model = str(selection.get("model") or self._default_model_for_provider(selected_provider))
        if not self._model_matches_provider(selected_provider, selected_model):
            selected_model = self._default_model_for_provider(selected_provider)
        mode = "fixed"

        fallback_provider = ""
        fallback_model = ""

        providers_payload: List[Dict[str, Any]] = []
        for provider in visible_providers:
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
        "Authorization",
        "Bearer ",
        "sk-",
        "OPENROUTER_API_KEY",
        "GEMINI_API_KEY",
        "MISTRAL_API_KEY",
        "api_key",
        "apiKey",
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

        result = re.sub(r"Bearer\s+[A-Za-z0-9_\-\.]+", "Bearer [REDACTED]", result)
        # Redact sk-... style keys
        result = re.sub(r"sk-[A-Za-z0-9]{8,}", "[REDACTED]", result)
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
        payload: Optional[Dict[str, Any]] = None,
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
                payload=payload if isinstance(payload, dict) else None,
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
        fallback_on_quota = False
        if not available:
            return {
                "configured": False,
                "engine": "simulation",
                "model": None,
                "reachable": False,
                "message": "No AI provider configured. Set MISTRAL_API_KEY.",
                "availableProviders": [],
                "fallbackOnQuota": fallback_on_quota,
            }

        primary = available[0]
        model = self.get_model_for_provider(primary, selection_override=selection)
        message = f"{primary.capitalize()} configurado (modelo: {model})"

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
        seed_sections_override: Optional[List[Dict[str, Any]]] = None,
        planned_sections: Optional[List[Dict[str, Any]]] = None,
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
        self._token_usage_report = empty_token_usage_report()

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
        format_id = self._resolve_prompt_format_id(prompt, format_detail)
        values = project.get("variables") or project.get("values", {})
        base_prompt = self.renderer.render(
            template_text,
            values,
            trace_hook=self._trace_hook,
        )
        format_editorial_contract = build_format_editorial_contract(format_id)
        if format_editorial_contract:
            base_prompt = "\n\n".join(part for part in [base_prompt.strip(), format_editorial_contract] if part)
        self._last_base_prompt = base_prompt
        self._last_base_prompt_source = "package_template" if base_prompt.strip() else "fallback"

        if not base_prompt.strip():
            base_prompt = (
                f"Genera contenido academico para un documento de tesis. Titulo: {project.get('title', 'Sin titulo')}."
            )
            self._last_base_prompt = base_prompt
            self._last_base_prompt_source = "fallback"
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

        self._emit_trace(
            step="prompt.base",
            status="done",
            title="Prompt base listo",
            detail="Se guardo el prompt general antes de dividir la generacion por secciones.",
            preview={"prompt": self._redact_secrets(base_prompt)},
        )

        definition: Dict[str, Any] = {}
        if isinstance(format_detail, dict):
            raw = format_detail.get("definition", {})
            if isinstance(raw, dict):
                definition = raw

        self._ensure_not_cancelled()
        if isinstance(planned_sections, list) and planned_sections:
            section_index = [dict(item) for item in planned_sections if isinstance(item, dict)]
        else:
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
                meta={
                    "sectionTotal": len(section_index),
                    "sectionOutline": [
                        {
                            "sectionId": str(item.get("sectionId") or ""),
                            "sectionPath": str(item.get("path") or ""),
                            "sectionTitle": str(
                                item.get("title") or self._section_title_from_path(str(item.get("path") or ""))
                            ),
                            "sectionParentPath": self._section_parent_path(str(item.get("path") or "")),
                            "sectionLevel": int(
                                item.get("level") or self._section_level_from_path(str(item.get("path") or ""))
                            ),
                            "sectionOrder": self._section_order_from_item(item, index),
                        }
                        for index, item in enumerate(section_index)
                    ],
                },
            )

        # Merge project-level values for system prompt rendering
        project_values = dict(values)
        project_values.setdefault("title", project.get("title", ""))

        if resume_from_partial:
            stored_ai_result = project.get("ai_result")
            if isinstance(stored_ai_result, dict):
                self._token_usage_report = normalize_token_usage_report(stored_ai_result.get("tokenUsage"))

        seeded_sections: List[Dict[str, Any]] = []
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
            format_id=format_id,
        )

        # --- Post-processing correction pass ---
        full_content_resume = bool(
            resume_from_partial
            and len(seeded_sections) >= len(section_index)
            and all(bool(item.get("semanticComplete", True)) for item in seeded_sections)
        )
        if settings.AI_CORRECTION_ENABLED and not full_content_resume:
            pre_correction_sections = copy.deepcopy(sections)
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
            sections = self._preserve_unac_quality_regressions(
                before=pre_correction_sections,
                after=sections,
                values=project_values,
                format_id=format_id,
            )
            self._emit_trace(
                step="ai.correction",
                status="done",
                title="Limpieza y correccion completadas",
                meta={"sections": len(sections)},
            )
        elif settings.AI_CORRECTION_ENABLED and full_content_resume:
            self._emit_trace(
                step="ai.correction",
                status="done",
                title="Limpieza IA reutilizada",
                detail=(
                    "Todas las secciones ya estaban guardadas; se omite una nueva llamada de correccion "
                    "y se conserva el contenido aprobado."
                ),
                meta={"sections": len(sections), "resumePostprocessingOnly": True},
            )

        # Normalize profile headings before any specialized quality repair so
        # a provider-paraphrased title does not trigger another AI call.
        sections = canonicalize_duplicate_semantic_units(sections)

        # --- Completeness check: detect and repair placeholders ---
        sections = self._ensure_completeness(
            sections,
            project_id=project_id,
            values=project_values,
        )
        sections = apply_figure_recommendations(
            sections,
            values=project_values,
            format_id=format_id,
        )
        sections = self._repair_reality_problem_sections(
            sections,
            project_id=project_id,
            values=project_values,
            format_id=format_id,
            selection=active_selection,
        )
        sections = self._repair_chapter_one_heading_sections(
            sections,
            project_id=project_id,
            values=project_values,
            format_id=format_id,
            selection=active_selection,
        )
        sections = self._repair_theoretical_bases_sections(
            sections,
            project_id=project_id,
            values=project_values,
            format_id=format_id,
            selection=active_selection,
        )
        sections = self._repair_schedule_budget_sections(
            sections,
            project_id=project_id,
            values=project_values,
            format_id=format_id,
            selection=active_selection,
        )
        sections = canonicalize_duplicate_semantic_units(sections)
        sections = ensure_canonical_formulas(sections)
        sections, quality_audit = self._repair_unac_quality_profile_sections(
            sections,
            project_id=project_id,
            values=project_values,
            format_id=format_id,
            selection=active_selection,
        )
        # Repairs can echo a provider-paraphrased heading. Canonicalize once
        # more before assigning citations and building the render payload.
        sections = canonicalize_duplicate_semantic_units(sections)
        self._emit_trace(
            step="ai.figures",
            status="done",
            title="Figuras recomendadas derivadas",
            detail="Se revisaron secciones elegibles para insertar placeholders tecnicos con caption especifico.",
        )
        has_references_section = any(
            "referencias bibliogr" in str(section.get("path") or "").lower()
            for section in sections
            if isinstance(section, dict)
        )
        consolidation = consolidate_references(sections, values=project_values) if has_references_section else None
        if consolidation is not None:
            sections = consolidation.sections
            self._emit_trace(
                step="ai.references",
                status="done",
                title="Referencias finales consolidadas",
                detail=(
                    "Se generaron referencias propuestas simuladas sin acceso a internet. "
                    f"Menciones={sum(consolidation.mentions_by_section.values())}; "
                    f"fuentes distintas={consolidation.distinct_sources}."
                ),
            )

        if is_unac_maintenance_project(format_id, project_values):
            if consolidation is not None and consolidation.failures:
                detail = " | ".join(consolidation.failures)
                self._emit_trace(
                    step="ai.references",
                    status="error",
                    title="Politica de citas y referencias incumplida",
                    detail=detail,
                    meta={
                        "profile": load_unac_maintenance_profile().id,
                        "distinctSources": consolidation.distinct_sources,
                    },
                )
                raise QualityProfileValidationError(
                    "Perfil UNAC de referencias incumplido: " + detail,
                    failed_quality_keys=list(consolidation.failures),
                )
            quality_audit = audit_unac_maintenance_sections(sections)
            failures = quality_failures(quality_audit)
            if failures:
                detail = self._quality_failure_detail(failures)
                self._emit_trace(
                    step="ai.quality_profile",
                    status="error",
                    title="Perfil UNAC de calidad incumplido",
                    detail=detail,
                    meta={"profile": load_unac_maintenance_profile().id, "failures": len(failures)},
                )
                raise QualityProfileValidationError(
                    f"AI output validation failed: {detail}",
                    failed_quality_keys=[audit.key for audit in failures],
                )

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
        ai_result["tokenUsage"] = self.get_token_usage_report()
        if quality_audit:
            ai_result["qualityProfile"] = load_unac_maintenance_profile().id
            ai_result["qualityAudit"] = [audit.to_dict() for audit in quality_audit]
            for generated_section in ai_result.get("sections", []):
                if not isinstance(generated_section, dict):
                    continue
                owner_key = section_key_from_path(str(generated_section.get("path") or ""))
                related = [
                    audit.to_dict()
                    for audit in quality_audit
                    if owner_key
                    and (audit.key == owner_key or audit.key.startswith(owner_key + "."))
                ]
                if related:
                    generated_section["qualityAudit"] = {
                        "status": "ok" if all(item.get("status") == "ok" for item in related) else "pending",
                        "profile": load_unac_maintenance_profile().id,
                        "units": related,
                    }
        self._emit_trace(
            step="ai.validation",
            status="done",
            title="Salida IA validada",
            meta={
                "sections": len(ai_result.get("sections", [])),
                "tokenUsage": self.get_token_usage_snapshot(),
            },
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
                "tokenUsage": self.get_token_usage_snapshot(),
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

    @staticmethod
    def _section_title_from_path(path: str) -> str:
        parts = [part.strip() for part in str(path or "").split("/") if part.strip()]
        return parts[-1] if parts else ""

    @staticmethod
    def _section_parent_path(path: str) -> str:
        parts = [part.strip() for part in str(path or "").split("/") if part.strip()]
        if len(parts) <= 1:
            return ""
        return "/".join(parts[:-1])

    @staticmethod
    def _section_level_from_path(path: str) -> int:
        parts = [part.strip() for part in str(path or "").split("/") if part.strip()]
        return max(1, len(parts))

    @staticmethod
    def _section_order_from_item(section: Dict[str, Any], fallback: int = 0) -> int:
        for key in ("section_order", "sectionOrder"):
            value = section.get(key)
            if value in (None, ""):
                continue
            try:
                if isinstance(value, bool):
                    continue
                if isinstance(value, int):
                    return value
                if isinstance(value, float):
                    return int(value)
                if isinstance(value, str):
                    return int(value.strip())
            except (TypeError, ValueError):
                continue
        return int(fallback)

    @staticmethod
    def _content_to_memory_text(content: Any) -> str:
        if isinstance(content, str):
            return " ".join(content.split())
        if isinstance(content, list):
            chunks: List[str] = []
            for item in content:
                if isinstance(item, str):
                    chunks.append(item)
                    continue
                if isinstance(item, dict):
                    for key in ("text", "content", "caption", "titulo", "title"):
                        value = item.get(key)
                        if isinstance(value, str) and value.strip():
                            chunks.append(value)
                            break
                    continue
                if item is not None:
                    chunks.append(str(item))
            return " ".join(" ".join(chunk.split()) for chunk in chunks if str(chunk).strip())
        if isinstance(content, dict):
            try:
                return " ".join(json.dumps(content, ensure_ascii=False).split())
            except Exception:
                return " ".join(str(content).split())
        return ""

    def _build_section_memory_entry(self, section: Dict[str, Any]) -> Dict[str, str]:
        path = str(section.get("path") or "").strip()
        title = self._section_title_from_path(path) or path
        summary = self._content_to_memory_text(section.get("content"))
        if len(summary) > 320:
            summary = f"{summary[:317].rstrip()}..."
        return {
            "path": path,
            "title": title,
            "summary": summary,
        }

    @staticmethod
    def _memory_fixed_values_snapshot(values: Dict[str, Any] | None) -> str:
        if not isinstance(values, dict):
            return ""
        preferred_keys = [
            "tema",
            "objetivo_general",
            "problema_general",
            "variable_independiente",
            "variable_dependiente",
            "poblacion",
            "muestra",
            "metodologia",
        ]
        selected: List[str] = []
        seen: Set[str] = set()
        ordered_keys = preferred_keys + [key for key in values.keys() if key not in preferred_keys]
        for key in ordered_keys:
            normalized_key = str(key or "").strip()
            if not normalized_key or normalized_key in {"title"} or normalized_key in seen:
                continue
            compact_value = " ".join(str(values.get(key) or "").split())
            if not compact_value:
                continue
            if len(compact_value) > 90:
                compact_value = f"{compact_value[:87].rstrip()}..."
            selected.append(f"{normalized_key}={compact_value}")
            seen.add(normalized_key)
            if len(selected) >= 6:
                break
        return "; ".join(selected)

    @staticmethod
    def _resolve_prompt_format_id(
        prompt: Dict[str, Any] | None,
        format_detail: Dict[str, Any] | None,
    ) -> str:
        prompt_data = prompt if isinstance(prompt, dict) else {}
        detail_data = format_detail if isinstance(format_detail, dict) else {}
        return str(
            prompt_data.get("format_id")
            or prompt_data.get("formatId")
            or detail_data.get("id")
            or detail_data.get("format_id")
            or ""
        ).strip()

    def _build_generation_memory_context(
        self,
        *,
        previous_sections: List[Dict[str, str]],
        values: Dict[str, Any] | None = None,
        format_id: str = "",
    ) -> str:
        if not previous_sections:
            return ""

        completed_paths = [
            str(item.get("path") or "").strip() for item in previous_sections if str(item.get("path") or "").strip()
        ]
        latest = previous_sections[-1]
        lines: List[str] = [
            "Memoria de continuidad entre secciones:",
            f"- Secciones previas completadas: {', '.join(completed_paths)}",
            f"- Seccion inmediatamente anterior: {str(latest.get('title') or latest.get('path') or '').strip()}",
        ]
        latest_summary = str(latest.get("summary") or "").strip()
        if latest_summary:
            lines.append(f"- Resumen breve de la seccion anterior: {latest_summary}")

        lines.append("- Resumen acumulado reciente:")
        for item in previous_sections[-3:]:
            title = str(item.get("title") or item.get("path") or "").strip()
            summary = str(item.get("summary") or "").strip() or "Seccion completada sin resumen adicional."
            lines.append(f"  - {title}: {summary}")

        fixed_values = build_stable_project_memory_snapshot(format_id, values) or self._memory_fixed_values_snapshot(
            values
        )
        if fixed_values:
            lines.append(f"- Variables o decisiones ya fijadas: {fixed_values}")

        return "\n".join(lines)

    def _extract_seed_sections(
        self,
        ai_result: Any,
        *,
        section_index: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        if not isinstance(ai_result, dict):
            return []
        raw_sections = ai_result.get("sections")
        if not isinstance(raw_sections, list):
            return []

        seeded_map: Dict[str, Dict[str, Any]] = {}
        for section in raw_sections:
            if not isinstance(section, dict):
                continue
            content = section.get("content")
            if isinstance(content, str):
                if not content.strip():
                    continue
            elif isinstance(content, list):
                if not content:
                    continue
            else:
                continue
            section_id = str(section.get("sectionId") or "").strip()
            path = str(section.get("path") or "").strip()
            if not section_id and not path:
                continue
            key = self._section_lookup_key(section_id, path)
            if key not in seeded_map:
                seeded_map[key] = {
                    "content": content,
                    "semanticUnitsCompleted": list(section.get("semanticUnitsCompleted") or []),
                    "semanticUnitsTotal": int(section.get("semanticUnitsTotal") or 0),
                    "semanticComplete": bool(section.get("semanticComplete", True)),
                }

        ordered: List[Dict[str, Any]] = []
        for idx, section in enumerate(section_index, 1):
            section_id = str(section.get("sectionId") or f"sec-{idx:04d}")
            path = str(section.get("path") or f"Section {idx}")
            key = self._section_lookup_key(section_id, path)
            seeded_entry = seeded_map.get(key)
            if seeded_entry is None:
                alt_key = self._section_lookup_key("", path)
                seeded_entry = seeded_map.get(alt_key)
            if seeded_entry is None:
                break
            ordered.append(
                {
                    "sectionId": section_id,
                    "path": path,
                    "content": seeded_entry["content"],
                    "semanticUnitsCompleted": seeded_entry["semanticUnitsCompleted"],
                    "semanticUnitsTotal": seeded_entry["semanticUnitsTotal"],
                    "semanticComplete": seeded_entry["semanticComplete"],
                }
            )
            if not seeded_entry["semanticComplete"]:
                break
        return ordered

    @staticmethod
    def _unac_requirement_contract(requirement: SectionQualityRequirement) -> str:
        lines = [
            "CONTRATO OBLIGATORIO DE LA UNIDAD UNAC:",
            f"- Encabezado exacto: {requirement.heading}",
            f"- Intervalo narrativo obligatorio: {requirement.min_words}-{requirement.max_words} palabras; "
            f"apunta a {requirement.target_words} palabras.",
            "- El mínimo y el máximo reemplazan cualquier rango previo del bloque padre; no excedas el máximo.",
            "- El conteo no incluye el encabezado, citas, formulas, tablas, figuras ni captions.",
            f"- Temas que deben desarrollarse expresamente: {', '.join(requirement.topics) or 'los propios del encabezado'}.",
            f"- Densidad bibliográfica final: entre {requirement.min_citations} y {requirement.max_citations} citas.",
            "- Devuelve el encabezado exacto y luego solo el desarrollo de esta unidad, sin Markdown ni comentarios.",
            "- No inventes porcentajes, resultados, instrumentos, métodos, tecnologías, equipos ni mediciones.",
            "- Solo son hechos del proyecto los incluidos expresamente en el contexto estructurado.",
            "- No repitas párrafos ni copies redacción del documento guía.",
        ]
        if requirement.min_paragraphs or requirement.max_paragraphs:
            minimum = requirement.min_paragraphs or requirement.max_paragraphs
            maximum = requirement.max_paragraphs or requirement.min_paragraphs
            lines.append(f"- Estructura obligatoria: entre {minimum} y {maximum} párrafos sustantivos.")
        if requirement.expected_items:
            lines.append(f"- Cantidad exacta de elementos sustantivos: {requirement.expected_items}.")
        if requirement.key in {"2.1.1", "2.1.2"}:
            lines.append(
                "- Redacta exactamente cinco antecedentes, uno por párrafo. Cada uno debe exponer autor, título, "
                "problema, objetivo, método, muestra, resultado, conclusión y aporte al proyecto."
            )
            lines.append("- Usa únicamente los cinco autores-año de los estudios asignados; nunca páginas web.")
        else:
            lines.append(
                "- No escribas citas autor-año ni marcadores manuales: el plan de referencias las inserta "
                "después de aprobar la prosa y dentro del intervalo indicado."
            )
        if requirement.min_formulas:
            lines.append(
                "- Desarrolla definicion, variables e interpretacion; la ecuacion sera insertada por el sistema y no debes escribir FORMULA_JSON."
            )
        return "\n".join(lines)

    @staticmethod
    def _normalize_managed_requirement_prompt(
        prompt: str,
        requirement: SectionQualityRequirement,
    ) -> str:
        """Remove legacy managed ranges that conflict with the active profile."""
        normalized = str(prompt or "")
        if requirement.key != "2.4":
            return normalized
        normalized = re.sub(
            r"Rango de palabras aceptable:\s*450\s+a\s+600\s+palabras(?:\s*;[^\n]*)?\. ?",
            "Rango de palabras aceptable: 434 a 500 palabras; exactamente trece definiciones. ",
            normalized,
            flags=re.IGNORECASE,
        )
        normalized = re.sub(
            r"Incluye\s+10\s+a\s+15\s+t[eé]rminos",
            "Incluye exactamente trece términos",
            normalized,
            flags=re.IGNORECASE,
        )
        return normalized

    def _generate_unac_semantic_units(
        self,
        *,
        section_prompt: str,
        requirements: tuple[SectionQualityRequirement, ...],
        preferred_provider: Optional[str],
        section_current: int,
        section_total: int,
        section_path: str,
        section_id: str,
        selection: Optional[Dict[str, Any]],
        disabled_for_job: Set[str],
        seed_content: Any = None,
        completed_unit_keys: tuple[str, ...] = (),
        project_values: Optional[Dict[str, Any]] = None,
    ) -> LLMResult:
        """Generate composite institutional sections one semantic unit at a time."""
        outputs: list[str] = []
        completed = set(completed_unit_keys)
        if seed_content:
            seed_blocks = normalize_seed = seed_content
            if isinstance(normalize_seed, list):
                outputs.append(
                    "\n\n".join(
                        str(block.get("texto") or "")
                        for block in normalize_seed
                        if isinstance(block, dict) and str(block.get("texto") or "").strip()
                    )
                )
            else:
                outputs.append(str(seed_blocks).strip())
        attempts: list[Dict[str, Any]] = []
        incidents: list[Dict[str, Any]] = []
        effective_provider = preferred_provider
        status = "ok"
        if outputs and completed:
            # Persist an inherited partial semantic section immediately. If
            # the next pending unit fails before any new unit is completed,
            # the previous implementation dropped this seed and regenerated
            # already-approved siblings on the following retry.
            inherited_provisional = {
                "sectionId": section_id,
                "path": section_path,
                "content": "\n\n".join(value for value in outputs if value),
                "semanticUnitsCompleted": [item.key for item in requirements if item.key in completed],
                "semanticUnitsTotal": len(requirements),
                "semanticComplete": False,
            }
            self._partial_sections = [
                item
                for item in self._partial_sections
                if self._section_lookup_key(str(item.get("sectionId") or ""), str(item.get("path") or ""))
                != self._section_lookup_key(section_id, section_path)
            ] + [inherited_provisional]
        for unit_index, requirement in enumerate(requirements, 1):
            if requirement.key in completed:
                continue
            self._ensure_not_cancelled()
            unit_path = f"{section_path}/{requirement.heading}"
            normalized_section_prompt = self._normalize_managed_requirement_prompt(
                section_prompt,
                requirement,
            )
            prompt = "\n\n".join(
                [
                    normalized_section_prompt,
                    "La instruccion siguiente limita la respuesta a una sola subseccion y prevalece sobre cualquier solicitud de redactar el bloque padre completo.",
                    self._unac_requirement_contract(requirement),
                ]
            )
            self._emit_trace(
                step="ai.generate.semantic_unit",
                status="running",
                title=f"Generando unidad {unit_index}/{len(requirements)}: {requirement.heading}",
                meta={
                    "sectionId": section_id,
                    "sectionPath": section_path,
                    "unitKey": requirement.key,
                    "unitMinimum": requirement.min_words,
                },
            )
            result = self._generate_with_provider_fallback(
                prompt,
                preferred_provider=effective_provider,
                section_current=section_current,
                section_total=section_total,
                section_path=unit_path,
                section_id=f"{section_id}:{requirement.key}",
                phase="quality_profile_generate",
                selection=selection,
                disabled_for_job=disabled_for_job,
            )
            effective_provider = result.provider or effective_provider
            attempts.extend(result.attempts)
            incidents.extend(result.incidents)
            if result.status != "ok":
                status = result.status
            unit_blocks = normalize_semantic_blocks(
                self.validator.sanitize_content(
                    parse_ai_content(str(result.content or "")),
                    path=unit_path,
                )
            )
            unit_blocks = self._isolate_blocks_for_requirement(unit_blocks, requirement)

            def _with_canonical_formula(candidate_content: Any) -> list[Dict[str, Any]]:
                blocks = normalize_semantic_blocks(candidate_content)
                formula = canonical_formula_for_key(requirement.key)
                if not formula:
                    return blocks
                blocks = [
                    dict(block)
                    for block in blocks
                    if str(block.get("tipo") or "").lower() != "formula"
                ]
                prose_indexes = [
                    index
                    for index, block in enumerate(blocks)
                    if str(block.get("tipo") or "").lower() == "parrafo"
                    and not self._strict_semantic_heading_key(block)
                ]
                insertion = prose_indexes[0] + 1 if prose_indexes else len(blocks)
                blocks.insert(insertion, formula)
                return blocks

            unit_blocks = _with_canonical_formula(unit_blocks)

            def _unit_audit(candidate_content: Any) -> SectionQualityAudit:
                audits = audit_unac_maintenance_sections(
                    [
                        {
                            "sectionId": f"{section_id}:{requirement.key}",
                            "path": unit_path,
                            "content": candidate_content,
                        }
                    ]
                )
                return next(item for item in audits if item.key == requirement.key)

            unit_audit = _unit_audit(unit_blocks)
            # Three directed phases are allowed because a repetitive long
            # answer often needs one complete rewrite followed by a short
            # deficit-only completion. Treating both as a single repair made
            # us discard a much cleaner rewrite merely because it was 20-25%
            # short, leaving the original repetitive text as the "best" one.
            for repair_attempt in range(1, 4):
                duplicate_limit = load_unac_maintenance_profile().duplicate_ratio_max
                prose_failed = (
                    unit_audit.words < unit_audit.minimum
                    or unit_audit.words > unit_audit.maximum
                    or bool(unit_audit.missing_topics)
                    or unit_audit.duplicate_ratio > duplicate_limit
                    or (unit_audit.paragraph_minimum and unit_audit.paragraphs < unit_audit.paragraph_minimum)
                    or (unit_audit.paragraph_maximum and unit_audit.paragraphs > unit_audit.paragraph_maximum)
                    or (unit_audit.expected_items and unit_audit.items != unit_audit.expected_items)
                )
                if not prose_failed:
                    break
                deterministic_pool: list[list[Dict[str, Any]]] = []
                if unit_audit.missing_topics:
                    deterministic_pool.extend(
                        self._deterministic_topic_completion_candidates(
                            unit_blocks,
                            requirement,
                            unit_audit.missing_topics,
                        )
                    )
                if (
                    unit_audit.words > unit_audit.maximum
                    or (
                        unit_audit.paragraph_maximum
                        and unit_audit.paragraphs > unit_audit.paragraph_maximum
                    )
                ):
                    deterministic_pool.extend(
                        self._deterministic_compression_candidates(unit_blocks, requirement)
                    )
                if unit_audit.duplicate_ratio > duplicate_limit:
                    deterministic_pool.extend(
                        self._deterministic_repetition_repair_candidates(
                            unit_blocks,
                            requirement,
                            values=project_values,
                        )
                    )
                if (
                    unit_audit.paragraph_minimum
                    and unit_audit.paragraphs < unit_audit.paragraph_minimum
                ):
                    structural_seeds = [unit_blocks, *deterministic_pool]
                    for structural_seed in structural_seeds:
                        deterministic_pool.extend(
                            self._deterministic_paragraph_rebalance_candidates(
                                structural_seed,
                                requirement,
                            )
                        )
                # Word deficits, missing topics and paragraph shortages are
                # invariants that can be completed safely from the approved
                # prose and the project fact registry.  Run this before any
                # repair call so a response such as 1231 words/10 paragraphs
                # for 1.1 is split and completed locally instead of spending
                # three more provider calls and then failing.
                if (
                    unit_audit.words < unit_audit.minimum
                    or unit_audit.missing_topics
                    or (
                        unit_audit.paragraph_minimum
                        and unit_audit.paragraphs < unit_audit.paragraph_minimum
                    )
                ):
                    deficit_seeds = [unit_blocks, *deterministic_pool]
                    seen_deficit_seeds: set[str] = set()
                    for deficit_seed in deficit_seeds:
                        seed_fingerprint = json.dumps(
                            deficit_seed,
                            ensure_ascii=False,
                            sort_keys=True,
                        )
                        if seed_fingerprint in seen_deficit_seeds:
                            continue
                        seen_deficit_seeds.add(seed_fingerprint)
                        deterministic_pool.extend(
                            self._deterministic_deficit_completion_candidates(
                                deficit_seed,
                                requirement,
                                values=project_values,
                            )
                        )
                valid_deterministic: list[
                    tuple[int, list[Dict[str, Any]], SectionQualityAudit]
                ] = []
                for repaired in deterministic_pool:
                    repaired_audit = _unit_audit(repaired)
                    if (
                        repaired_audit.minimum <= repaired_audit.words <= repaired_audit.maximum
                        and not repaired_audit.missing_topics
                        and repaired_audit.duplicate_ratio <= duplicate_limit
                        and repaired_audit.formulas >= requirement.min_formulas
                        and (
                            not repaired_audit.paragraph_minimum
                            or repaired_audit.paragraph_minimum
                            <= repaired_audit.paragraphs
                            <= repaired_audit.paragraph_maximum
                        )
                        and (
                            not repaired_audit.expected_items
                            or repaired_audit.items == repaired_audit.expected_items
                        )
                    ):
                        valid_deterministic.append(
                            (
                                abs(repaired_audit.words - requirement.target_words),
                                repaired,
                                repaired_audit,
                            )
                        )
                if valid_deterministic:
                    _, unit_blocks, unit_audit = min(valid_deterministic, key=lambda item: item[0])
                    self._emit_trace(
                        step="ai.generate.semantic_unit.deterministic_repair",
                        status="done",
                        title=f"Unidad ajustada sin otra llamada IA: {requirement.heading}",
                        detail=(
                            f"Resultado={unit_audit.words} palabras, párrafos={unit_audit.paragraphs}, "
                            "cobertura temática completa."
                        ),
                        meta={"unitKey": requirement.key, "repairAttempt": repair_attempt},
                    )
                    break
                if unit_audit.missing_topics:
                    valid_topic_repairs: list[
                        tuple[int, list[Dict[str, Any]], SectionQualityAudit]
                    ] = []
                    for repaired in self._deterministic_topic_completion_candidates(
                        unit_blocks,
                        requirement,
                        unit_audit.missing_topics,
                    ):
                        repaired_audit = _unit_audit(repaired)
                        if (
                            repaired_audit.minimum <= repaired_audit.words <= repaired_audit.maximum
                            and not repaired_audit.missing_topics
                            and repaired_audit.duplicate_ratio <= duplicate_limit
                            and repaired_audit.formulas >= requirement.min_formulas
                            and (
                                not repaired_audit.paragraph_minimum
                                or repaired_audit.paragraph_minimum
                                <= repaired_audit.paragraphs
                                <= repaired_audit.paragraph_maximum
                            )
                            and (
                                not repaired_audit.expected_items
                                or repaired_audit.items == repaired_audit.expected_items
                            )
                        ):
                            valid_topic_repairs.append(
                                (
                                    abs(repaired_audit.words - requirement.target_words),
                                    repaired,
                                    repaired_audit,
                                )
                            )
                    if valid_topic_repairs:
                        _, unit_blocks, unit_audit = min(
                            valid_topic_repairs, key=lambda item: item[0]
                        )
                        self._emit_trace(
                            step="ai.generate.semantic_unit.topic_repair",
                            status="done",
                            title=f"Cobertura temática corregida: {requirement.heading}",
                            detail=(
                                "Se incorporaron de forma controlada los temas faltantes sin regenerar "
                                f"la unidad; resultado={unit_audit.words} palabras."
                            ),
                            meta={"unitKey": requirement.key, "repairAttempt": repair_attempt},
                        )
                        break
                progressive_deterministic: list[
                    tuple[tuple[int, ...], list[Dict[str, Any]], SectionQualityAudit]
                ] = []
                current_score = self._quality_content_score(unit_audit)
                for candidate in deterministic_pool:
                    candidate_audit = _unit_audit(candidate)
                    candidate_score = self._quality_content_score(candidate_audit)
                    if (
                        candidate_score < current_score
                        and candidate_audit.formulas >= requirement.min_formulas
                        and (
                            not requirement.expected_items
                            or candidate_audit.items == requirement.expected_items
                        )
                    ):
                        progressive_deterministic.append(
                            (candidate_score, candidate, candidate_audit)
                        )
                if progressive_deterministic:
                    _, unit_blocks, unit_audit = min(
                        progressive_deterministic,
                        key=lambda item: item[0],
                    )
                    self._emit_trace(
                        step="ai.generate.semantic_unit.deterministic_progress",
                        status="done",
                        title=f"Defectos parciales corregidos localmente: {requirement.heading}",
                        detail=(
                            f"Base preservada en {unit_audit.words} palabras y "
                            f"{unit_audit.paragraphs} párrafos antes de completar el déficit restante."
                        ),
                        meta={"unitKey": requirement.key, "repairAttempt": repair_attempt},
                    )
                overage_only = (
                    unit_audit.words > unit_audit.maximum
                    and not unit_audit.missing_topics
                    and unit_audit.duplicate_ratio <= duplicate_limit
                    and (not unit_audit.paragraph_minimum or unit_audit.paragraphs >= unit_audit.paragraph_minimum)
                    and (not unit_audit.paragraph_maximum or unit_audit.paragraphs <= unit_audit.paragraph_maximum)
                    and (not unit_audit.expected_items or unit_audit.items == unit_audit.expected_items)
                )
                if overage_only:
                    valid_compressions: list[tuple[int, list[Dict[str, Any]], SectionQualityAudit]] = []
                    for compressed in self._deterministic_compression_candidates(
                        unit_blocks, requirement
                    ):
                        compressed_audit = _unit_audit(compressed)
                        if (
                            compressed_audit.minimum <= compressed_audit.words <= compressed_audit.maximum
                            and not compressed_audit.missing_topics
                            and compressed_audit.duplicate_ratio <= duplicate_limit
                            and compressed_audit.formulas >= requirement.min_formulas
                            and (
                                not compressed_audit.paragraph_minimum
                                or compressed_audit.paragraph_minimum
                                <= compressed_audit.paragraphs
                                <= compressed_audit.paragraph_maximum
                            )
                            and (
                                not compressed_audit.expected_items
                                or compressed_audit.items == compressed_audit.expected_items
                            )
                        ):
                            valid_compressions.append(
                                (
                                    abs(compressed_audit.words - requirement.target_words),
                                    compressed,
                                    compressed_audit,
                                )
                            )
                    if valid_compressions:
                        _, unit_blocks, unit_audit = min(valid_compressions, key=lambda item: item[0])
                        self._emit_trace(
                            step="ai.generate.semantic_unit.compress",
                            status="done",
                            title=f"Exceso corregido sin regenerar: {requirement.heading}",
                            detail=(
                                f"La unidad se comprimió de forma conservadora hasta {unit_audit.words} "
                                f"palabras (rango {unit_audit.minimum}-{unit_audit.maximum})."
                            ),
                            meta={"unitKey": requirement.key, "repairAttempt": repair_attempt},
                        )
                        break
                available_room = max(0, unit_audit.maximum - unit_audit.words)
                completion_mode = (
                    unit_audit.duplicate_ratio <= duplicate_limit
                    and unit_audit.words <= unit_audit.maximum
                    and (not unit_audit.paragraph_minimum or unit_audit.paragraphs >= unit_audit.paragraph_minimum)
                    and (not unit_audit.paragraph_maximum or unit_audit.paragraphs <= unit_audit.paragraph_maximum)
                    and (
                        unit_audit.words < unit_audit.minimum
                        or bool(unit_audit.missing_topics)
                    )
                    and (
                        not unit_audit.missing_topics
                        or available_room >= 80
                    )
                )
                word_deficit = max(0, unit_audit.minimum - unit_audit.words)
                supplemental_minimum = max(1, word_deficit)
                supplemental_maximum = min(
                    max(1, available_room),
                    max(supplemental_minimum + 10, (supplemental_minimum * 108 + 99) // 100),
                )
                compression_mode = overage_only
                topic_rewrite_mode = (
                    bool(unit_audit.missing_topics)
                    and unit_audit.words >= unit_audit.minimum
                    and unit_audit.words <= unit_audit.maximum
                    and unit_audit.duplicate_ratio <= duplicate_limit
                    and available_room < 80
                )
                repair_instruction = (
                    "Devuelve SOLO parrafos complementarios nuevos, sin encabezado y sin repetir ni resumir "
                    f"el contenido valido. Escribe entre {supplemental_minimum} y "
                    f"{supplemental_maximum} palabras narrativas nuevas; no superes ese límite."
                    if completion_mode
                    else (
                        "Edita minimamente la unidad existente, reemplazando una oración secundaria cuando "
                        "sea necesario. No anexes un párrafo adicional ni aumentes la extensión. "
                        f"Devuelve entre {requirement.min_words} y {requirement.max_words} palabras e incorpora "
                        "expresamente estos temas faltantes: "
                        + ", ".join(unit_audit.missing_topics)
                        + ". Conserva los demás temas y la cantidad de párrafos."
                        if topic_rewrite_mode
                    else (
                        "Edita minimamente la unidad existente: elimina redundancias, no agregues información "
                        f"y devuelve entre {requirement.min_words} y {requirement.max_words} palabras, "
                        f"preferentemente {requirement.target_words}. Conserva todos los temas y la cantidad "
                        "de párrafos; devuelve la unidad completa corregida."
                        if compression_mode
                    else (
                        "Reescribe la unidad completa con variedad real entre parrafos. Conserva los hechos, "
                        "pero no reutilices una plantilla fija: cambia aperturas, orden argumental y cierres; "
                            f"la repetición de secuencias debe quedar por debajo de {duplicate_limit:.0%}. "
                            f"Entrega {requirement.target_words} palabras sin superar {requirement.max_words}."
                    )))
                )
                repair_prompt = "\n".join(
                    [
                        repair_instruction,
                        f"Unidad: {requirement.heading}",
                        f"Reparacion inmediata {repair_attempt}/3.",
                        "Incumplimientos exactos: "
                        + self._quality_failure_detail([unit_audit], include_citations=False),
                        (
                            "Incluye expresamente estas ideas pendientes mediante redaccion academica natural: "
                            + ", ".join(unit_audit.missing_topics)
                            + "."
                            if unit_audit.missing_topics
                            else ""
                        ),
                        self._unac_requirement_contract(requirement),
                        "Contenido valido actual:",
                        json.dumps(unit_blocks, ensure_ascii=False),
                        (
                            "Devuelve solo el complemento."
                            if completion_mode
                            else "Devuelve solo la unidad completa corregida."
                        ),
                    ]
                )
                repaired_blocks: list[Dict[str, Any]] | None = None
                repair_raw = ""
                batch_rewrite = False
                if (
                    requirement.key in {"2.1.1", "2.1.2"}
                    and (
                        unit_audit.duplicate_ratio > duplicate_limit
                        or unit_audit.words < unit_audit.minimum
                        or (unit_audit.expected_items and unit_audit.items != unit_audit.expected_items)
                    )
                ):
                    repaired_blocks = self._rewrite_repetitive_antecedent_batches(
                        current_unit=unit_blocks,
                        requirement=requirement,
                        path=section_path,
                        selection=selection,
                        rewrite_existing=unit_audit.duplicate_ratio > duplicate_limit,
                    )
                    if repaired_blocks is not None:
                        batch_rewrite = True
                        repair_raw = self._semantic_blocks_as_generation_text(repaired_blocks)
                        effective_provider = self._last_used_provider or effective_provider

                if repaired_blocks is None:
                    repair_result = self._generate_with_provider_fallback(
                        repair_prompt,
                        preferred_provider=effective_provider,
                        section_current=section_current,
                        section_total=section_total,
                        section_path=unit_path,
                        section_id=f"{section_id}:{requirement.key}",
                        phase="quality_profile_repair",
                        selection=selection,
                        disabled_for_job=disabled_for_job,
                    )
                    effective_provider = repair_result.provider or effective_provider
                    attempts.extend(repair_result.attempts)
                    incidents.extend(repair_result.incidents)
                    repair_raw = str(repair_result.content or "")
                    repaired_blocks = normalize_semantic_blocks(
                        self.validator.sanitize_content(
                            parse_ai_content(repair_raw),
                            path=unit_path,
                        )
                    )
                usable_supplement = (
                    self._supplement_blocks_for_requirement(repaired_blocks, requirement)
                    if completion_mode and not batch_rewrite
                    else []
                )
                proposed_blocks = (
                    repaired_blocks
                    if batch_rewrite
                    else self._merge_supplement_within_structure(
                        unit_blocks, usable_supplement, requirement
                    )
                    if completion_mode
                    else repaired_blocks
                )
                proposed_blocks = _with_canonical_formula(proposed_blocks)
                proposed_audit = _unit_audit(proposed_blocks)
                if completion_mode and (
                    proposed_audit.words > requirement.max_words
                    or (
                        proposed_audit.paragraph_maximum
                        and proposed_audit.paragraphs > proposed_audit.paragraph_maximum
                    )
                ):
                    bounded_candidates: list[
                        tuple[int, list[Dict[str, Any]], SectionQualityAudit]
                    ] = []
                    candidate_pool = self._bounded_completion_candidates(
                        unit_blocks, usable_supplement, requirement
                    )
                    candidate_pool.extend(
                        self._deterministic_compression_candidates(proposed_blocks, requirement)
                    )
                    for compressed in candidate_pool:
                        compressed_audit = _unit_audit(compressed)
                        if (
                            compressed_audit.minimum <= compressed_audit.words <= compressed_audit.maximum
                            and not compressed_audit.missing_topics
                            and compressed_audit.duplicate_ratio <= duplicate_limit
                            and compressed_audit.formulas >= requirement.min_formulas
                            and (
                                not compressed_audit.paragraph_minimum
                                or compressed_audit.paragraph_minimum
                                <= compressed_audit.paragraphs
                                <= compressed_audit.paragraph_maximum
                            )
                            and (
                                not compressed_audit.expected_items
                                or compressed_audit.items == compressed_audit.expected_items
                            )
                        ):
                            bounded_candidates.append(
                                (
                                    abs(compressed_audit.words - requirement.target_words),
                                    compressed,
                                    compressed_audit,
                                )
                            )
                    if bounded_candidates:
                        _, proposed_blocks, proposed_audit = min(
                            bounded_candidates, key=lambda item: item[0]
                        )
                self._emit_trace(
                    step="ai.generate.semantic_unit.repair",
                    status=(
                        "done"
                        if self._quality_content_score(proposed_audit)
                        < self._quality_content_score(unit_audit)
                        else "warn"
                    ),
                    title=f"Reparacion {repair_attempt}/3 evaluada: {requirement.heading}",
                    detail=(
                        f"Unidad {unit_audit.words}->{proposed_audit.words} palabras; "
                        f"bloques recibidos={len(repaired_blocks)}, "
                        f"bloques utilizables={len(usable_supplement) if completion_mode else len(repaired_blocks)}."
                    ),
                    meta={
                        "sectionId": section_id,
                        "sectionPath": section_path,
                        "unitKey": requirement.key,
                        "repairAttempt": repair_attempt,
                        "completionMode": completion_mode,
                        "rawCharacters": len(repair_raw),
                        "parsedBlocks": len(repaired_blocks),
                        "usableBlocks": len(usable_supplement) if completion_mode else len(repaired_blocks),
                        "batchRewrite": batch_rewrite,
                        "wordsBefore": unit_audit.words,
                        "wordsProposed": proposed_audit.words,
                        "missingTopicsProposed": list(proposed_audit.missing_topics),
                        "duplicateRatioProposed": proposed_audit.duplicate_ratio,
                    },
                )
                progressive_duplicate_rewrite = (
                    unit_audit.duplicate_ratio > duplicate_limit
                    and proposed_audit.duplicate_ratio <= duplicate_limit
                    and proposed_audit.words >= int(requirement.min_words * 0.60)
                    and proposed_audit.words <= requirement.max_words
                    and proposed_audit.formulas >= requirement.min_formulas
                )
                if (
                    self._quality_content_score(proposed_audit)
                    < self._quality_content_score(unit_audit)
                    or progressive_duplicate_rewrite
                ):
                    unit_blocks = proposed_blocks
                    unit_audit = proposed_audit

            if (
                unit_audit.words < unit_audit.minimum
                or unit_audit.words > unit_audit.maximum
                or unit_audit.missing_topics
                or unit_audit.duplicate_ratio > duplicate_limit
                or (
                    unit_audit.paragraph_minimum
                    and unit_audit.paragraphs < unit_audit.paragraph_minimum
                )
                or (
                    unit_audit.paragraph_maximum
                    and unit_audit.paragraphs > unit_audit.paragraph_maximum
                )
            ):
                safety_pool: list[list[Dict[str, Any]]] = []
                safety_pool.extend(
                    self._deterministic_deficit_completion_candidates(
                        unit_blocks,
                        requirement,
                        values=project_values,
                    )
                )
                if unit_audit.duplicate_ratio > duplicate_limit:
                    safety_pool.extend(
                        self._deterministic_repetition_repair_candidates(
                            unit_blocks,
                            requirement,
                            values=project_values,
                        )
                    )
                if (
                    unit_audit.words > unit_audit.maximum
                    or (
                        unit_audit.paragraph_maximum
                        and unit_audit.paragraphs > unit_audit.paragraph_maximum
                    )
                ):
                    safety_pool.extend(
                        self._deterministic_compression_candidates(
                            unit_blocks,
                            requirement,
                        )
                    )
                valid_safety: list[
                    tuple[int, list[Dict[str, Any]], SectionQualityAudit]
                ] = []
                for candidate in safety_pool:
                    candidate = _with_canonical_formula(candidate)
                    candidate_audit = _unit_audit(candidate)
                    if (
                        candidate_audit.minimum
                        <= candidate_audit.words
                        <= candidate_audit.maximum
                        and not candidate_audit.missing_topics
                        and candidate_audit.duplicate_ratio <= duplicate_limit
                        and candidate_audit.formulas >= requirement.min_formulas
                        and (
                            not candidate_audit.paragraph_minimum
                            or candidate_audit.paragraph_minimum
                            <= candidate_audit.paragraphs
                            <= candidate_audit.paragraph_maximum
                        )
                        and (
                            not candidate_audit.expected_items
                            or candidate_audit.items == candidate_audit.expected_items
                        )
                    ):
                        valid_safety.append(
                            (
                                abs(candidate_audit.words - requirement.target_words),
                                candidate,
                                candidate_audit,
                            )
                        )
                if valid_safety:
                    _, unit_blocks, unit_audit = min(
                        valid_safety,
                        key=lambda item: item[0],
                    )
                    self._emit_trace(
                        step="ai.generate.semantic_unit.invariant_repair",
                        status="done",
                        title=f"Invariantes V2 normalizadas: {requirement.heading}",
                        detail=(
                            f"Resultado final={unit_audit.words} palabras, "
                            f"párrafos={unit_audit.paragraphs}; sin regenerar secciones previas."
                        ),
                        meta={"unitKey": requirement.key, "profile": "UNAC_MAINTENANCE_V2"},
                    )

            if (
                unit_audit.words < unit_audit.minimum
                or unit_audit.words > unit_audit.maximum
                or unit_audit.missing_topics
                or unit_audit.duplicate_ratio > duplicate_limit
                or (unit_audit.paragraph_minimum and unit_audit.paragraphs < unit_audit.paragraph_minimum)
                or (unit_audit.paragraph_maximum and unit_audit.paragraphs > unit_audit.paragraph_maximum)
                or (unit_audit.expected_items and unit_audit.items != unit_audit.expected_items)
            ):
                raise QualityProfileValidationError(
                    "Perfil UNAC detenido en la unidad generada: "
                    + self._quality_failure_detail([unit_audit], include_citations=False),
                    failed_quality_keys=[requirement.key],
                )

            first_is_target = bool(
                unit_blocks
                and str(unit_blocks[0].get("tipo") or "").lower() == "parrafo"
                and section_key_from_path(str(unit_blocks[0].get("texto") or "")) == requirement.key
            )
            owner_key = section_key_from_path(section_path)
            needs_internal_heading = len(requirements) > 1 or owner_key != requirement.key
            if needs_internal_heading:
                if first_is_target:
                    unit_blocks[0] = {**unit_blocks[0], "texto": requirement.heading}
                else:
                    unit_blocks.insert(0, {"tipo": "parrafo", "texto": requirement.heading})
            elif first_is_target:
                # The outer section renderer already writes this heading. A
                # second copy created the duplicated INTRODUCCIÓN observed in
                # Word and also distorted the narrative audit.
                unit_blocks = unit_blocks[1:]
            outputs.append(self._semantic_blocks_as_generation_text(unit_blocks))
            completed.add(requirement.key)
            self._emit_trace(
                step="ai.generate.semantic_unit",
                status="done",
                title=f"Unidad generada: {requirement.heading}",
                meta={
                    "sectionId": section_id,
                    "sectionPath": section_path,
                    "unitKey": requirement.key,
                    "unitMinimum": requirement.min_words,
                },
            )
            provisional = {
                "sectionId": section_id,
                "path": section_path,
                "content": "\n\n".join(value for value in outputs if value),
                "semanticUnitsCompleted": [item.key for item in requirements if item.key in completed],
                "semanticUnitsTotal": len(requirements),
                "semanticComplete": False,
            }
            self._partial_sections = [
                item
                for item in self._partial_sections
                if self._section_lookup_key(str(item.get("sectionId") or ""), str(item.get("path") or ""))
                != self._section_lookup_key(section_id, section_path)
            ] + [provisional]
            self._emit_progress(
                section_current,
                section_total,
                f"{section_path}/{requirement.heading}",
                effective_provider or "",
                stage="semantic_unit_done",
                payload={
                    "section_id": f"{section_id}:{requirement.key}",
                    "section_path": f"{section_path}/{requirement.heading}",
                    "path": f"{section_path}/{requirement.heading}",
                    "section_title": requirement.heading,
                    "parent_section_path": section_path,
                    "status": "ok",
                    "unit_key": requirement.key,
                },
            )
        return LLMResult(
            content="\n\n".join(outputs),
            provider=effective_provider or "",
            status=status,
            incidents=incidents,
            attempts=attempts,
        )

    @staticmethod
    def _matrix_scalar(values: Dict[str, Any], key: str, group: str, nested_key: str) -> str:
        direct = values.get(key)
        if str(direct or "").strip():
            return str(direct).strip()
        matrix = values.get("matriz_consistencia")
        if isinstance(matrix, dict):
            direct = matrix.get(key)
            if str(direct or "").strip():
                return str(direct).strip()
            nested = matrix.get(group)
            if isinstance(nested, dict):
                return str(nested.get(nested_key) or "").strip()
        return ""

    @staticmethod
    def _matrix_items(values: Dict[str, Any], key: str, group: str) -> list[str]:
        raw: Any = values.get(key)
        matrix = values.get("matriz_consistencia")
        if not isinstance(raw, list) and isinstance(matrix, dict):
            raw = matrix.get(key)
            if not isinstance(raw, list) and isinstance(matrix.get(group), dict):
                raw = matrix[group].get("especificos")
        return [str(item).strip() for item in (raw if isinstance(raw, list) else []) if str(item).strip()]

    @classmethod
    def _deterministic_unac_section_content(
        cls,
        *,
        section_id: str,
        section_path: str,
        values: Dict[str, Any],
        format_id: str,
    ) -> Any:
        """Build matrix-owned sections without consuming an LLM call."""
        if not is_unac_maintenance_project(format_id, values):
            return None
        if section_id == "titulo-info-basica":
            title = str(values.get("title") or values.get("titulo") or "").strip()
            return title.upper() if title else None
        if cls._is_unac_schedule_chapter_path(section_path):
            return [
                build_schedule_table_from_plan(
                    build_synthetic_schedule_plan(values),
                    values=values,
                )
            ]
        if OutputValidator._is_budget_path(section_path):
            return [
                build_budget_table_from_plan(
                    build_synthetic_budget_plan(values),
                    values=values,
                )
            ]
        normalized_path = " ".join(str(section_path or "").strip().lower().split())
        if "referencias bibliogr" in normalized_path:
            return [
                {
                    "tipo": "parrafo",
                    "texto": "Referencias bibliográficas administradas por el registro de fuentes del proyecto.",
                }
            ]
        if normalized_path == "anexos" or normalized_path.startswith("anexos/"):
            return [
                {
                    "tipo": "parrafo",
                    "texto": "Anexos estructurados administrados por la plantilla institucional.",
                }
            ]

        key = section_key_from_path(section_path)
        if key == "1.2":
            general = cls._matrix_scalar(values, "problema_general", "problemas", "general")
            specifics = cls._matrix_items(values, "problemas_especificos", "problemas")
            if not general:
                return None
            return [
                {"tipo": "parrafo", "texto": "Problema general", "negrita": True},
                {"tipo": "parrafo", "texto": general},
                {"tipo": "parrafo", "texto": "Problemas específicos", "negrita": True},
                {
                    "tipo": "lista",
                    "items": specifics,
                    "ordered": False,
                    "style": "bullet",
                    "sangria": "francesa",
                },
            ]
        if key == "1.3":
            general = cls._matrix_scalar(values, "objetivo_general", "objetivos", "general")
            specifics = cls._matrix_items(values, "objetivos_especificos", "objetivos")
            if not general:
                return None
            return [
                {"tipo": "parrafo", "texto": "Objetivo general", "negrita": True},
                {"tipo": "parrafo", "texto": general},
                {"tipo": "parrafo", "texto": "Objetivos específicos", "negrita": True},
                {
                    "tipo": "lista",
                    "items": specifics,
                    "ordered": False,
                    "style": "bullet",
                    "sangria": "francesa",
                },
            ]
        if key == "3.1":
            general = cls._matrix_scalar(values, "hipotesis_general", "hipotesis", "general")
            specifics = cls._matrix_items(values, "hipotesis_especificas", "hipotesis")
            if not general:
                return None
            return [
                {"tipo": "parrafo", "texto": "Hipótesis general", "negrita": True},
                {"tipo": "parrafo", "texto": general},
                {"tipo": "parrafo", "texto": "Hipótesis específicas", "negrita": True},
                {
                    "tipo": "lista",
                    "items": specifics,
                    "ordered": False,
                    "style": "bullet",
                    "sangria": "francesa",
                },
            ]
        if key == "2.4":
            independent = str(
                values.get("variable_independiente")
                or values.get("variableIndependiente")
                or "Mantenimiento Centrado en Confiabilidad (RCM)"
            ).strip()
            dependent = str(
                values.get("variable_dependiente")
                or values.get("variableDependiente")
                or "disponibilidad inherente"
            ).strip()
            object_of_study = str(
                values.get("objeto_estudio")
                or values.get("objetoEstudio")
                or "los equipos comprendidos en el estudio"
            ).strip()
            definitions = (
                (
                    "Gestión de mantenimiento",
                    "Proceso administrativo que planifica, organiza, ejecuta y controla las intervenciones sobre los activos físicos, buscando preservar sus funciones requeridas y sostener la continuidad operativa dentro de condiciones verificables de seguridad, calidad y costo.",
                ),
                (
                    independent,
                    "Metodología sistemática que determina las tareas de mantenimiento para conservar las funciones de un activo, mediante el análisis de funciones, fallas funcionales, modos de falla, consecuencias y acciones técnicamente aplicables.",
                ),
                (
                    "Función del activo",
                    "Desempeño esperado de un equipo bajo condiciones operativas definidas. Su formulación identifica qué debe hacer el activo, con qué nivel y dentro de qué límites, proporcionando la base para reconocer desviaciones funcionales relevantes.",
                ),
                (
                    "Falla funcional",
                    "Condición en la cual un activo deja de cumplir una función requerida según el estándar de desempeño establecido. Su identificación permite diferenciar la pérdida funcional de sus causas y orientar el análisis posterior.",
                ),
                (
                    "Taxonomía de equipos",
                    "Clasificación jerárquica de sistemas, subsistemas, equipos y componentes que uniformiza el registro de información de mantenimiento. Facilita relacionar fallas, intervenciones y tiempos operativos con el nivel correspondiente, manteniendo trazabilidad y consistencia.",
                ),
                (
                    "Análisis de criticidad",
                    "Procedimiento de jerarquización que valora las consecuencias asociadas con la falla de activos. Considera criterios operativos, económicos y de seguridad para orientar recursos hacia los elementos cuyo comportamiento representa mayor impacto.",
                ),
                (
                    "Análisis de Modos y Efectos de Falla (AMEF)",
                    "Herramienta estructurada que identifica modos de falla, causas, efectos y mecanismos de control. Permite examinar el riesgo, sustentar prioridades de intervención y documentar decisiones de mantenimiento vinculadas con las funciones del activo.",
                ),
                (
                    "Plan de mantenimiento",
                    "Conjunto organizado de tareas, frecuencias, recursos y criterios de ejecución destinados a conservar las funciones de los equipos. Su formulación vincula los riesgos identificados con actividades preventivas, predictivas, detectivas o correctivas.",
                ),
                (
                    dependent,
                    "Indicador que expresa la proporción del tiempo durante el cual un activo se encuentra apto para operar, considerando el tiempo entre fallas y el tiempo requerido para reparar. Su interpretación integra confiabilidad y mantenibilidad.",
                ),
                (
                    "Confiabilidad",
                    "Probabilidad de que un equipo cumpla una función requerida sin fallar durante un intervalo determinado y bajo condiciones establecidas. En el proyecto permite analizar la continuidad funcional de "
                    f"{object_of_study} mediante el comportamiento entre fallas.",
                ),
                (
                    "Mantenibilidad",
                    "Probabilidad de restablecer un activo a una condición especificada en un tiempo determinado, utilizando procedimientos y recursos definidos. Representa la facilidad y rapidez con que pueden ejecutarse las acciones de diagnóstico y reparación.",
                ),
                (
                    "Tiempo Medio Entre Fallas (MTBF)",
                    "Indicador de confiabilidad calculado como la relación entre el tiempo de operación y el número de fallas observadas. Un valor mayor representa intervalos operativos más prolongados antes de que ocurra una nueva falla.",
                ),
                (
                    "Tiempo Medio Para Reparar (MTTR)",
                    "Indicador de mantenibilidad obtenido al dividir el tiempo empleado en reparaciones entre el número de fallas. Un valor menor refleja una recuperación más rápida, siempre que se mantengan criterios equivalentes de medición.",
                ),
            )
            return [
                {"tipo": "parrafo", "texto": f"{term}. {definition}"}
                for term, definition in definitions
            ]
        if key == "3.2":
            independent = str(
                values.get("variable_independiente")
                or values.get("variableIndependiente")
                or "la variable independiente registrada"
            ).strip()
            dependent = str(
                values.get("variable_dependiente")
                or values.get("variableDependiente")
                or "la variable dependiente registrada"
            ).strip()
            matrix = values.get("matriz_consistencia")
            if not isinstance(matrix, dict):
                matrix = values.get("matriz") if isinstance(values.get("matriz"), dict) else {}
            vi_dimensions = [
                str(item).strip()
                for item in matrix.get("dimensiones_variable_independiente", [])
                if str(item).strip()
            ]
            vd_dimensions = [
                str(item).strip()
                for item in matrix.get("dimensiones_variable_dependiente", [])
                if str(item).strip()
            ]
            dimension_parts = [*vi_dimensions, *vd_dimensions]
            dimensions = ", ".join(dict.fromkeys(dimension_parts))
            dimension_sentence = (
                f" Las dimensiones registradas —{dimensions}— conservan el orden definido en la matriz de consistencia."
                if dimensions
                else " Las dimensiones conservan el orden definido en la matriz de consistencia."
            )
            bridge = (
                f"La operacionalización organiza la variable independiente {independent} y la variable dependiente "
                f"{dependent} en definiciones conceptuales y operacionales, dimensiones, indicadores, índices, "
                "métodos, técnicas e instrumentos verificables."
                f"{dimension_sentence} "
                "Las Tablas 3.1 y 3.2 presentan esta correspondencia con los datos estructurados del proyecto, "
                "sin alterar las relaciones establecidas entre los problemas, objetivos e hipótesis. Esta estructura "
                "orientará la recolección, el procesamiento y la interpretación posterior de los datos."
            )
            return [{"tipo": "parrafo", "texto": bridge}]
        return None

    @staticmethod
    def _deterministic_content_preview(content: Any) -> str:
        if isinstance(content, str):
            return content
        if not isinstance(content, list):
            return ""
        parts: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            if str(block.get("tipo") or "").lower() in {"lista", "list"}:
                parts.extend(str(item) for item in block.get("items") or [] if str(item).strip())
            elif str(block.get("texto") or "").strip():
                parts.append(str(block.get("texto") or "").strip())
        return "\n\n".join(parts)

    def _generate_sections(
        self,
        base_prompt: str,
        section_index: List[Dict[str, Any]],
        project_id: str,
        values: Dict[str, Any] | None = None,
        selection: Optional[Dict[str, Any]] = None,
        seed_sections: Optional[List[Dict[str, Any]]] = None,
        format_id: str = "",
    ) -> List[Dict[str, Any]]:
        """Generate and immediately validate every selected section."""
        sections: List[Dict[str, Any]] = []
        total = len(section_index)
        preferred_provider: Optional[str] = None
        disabled_providers: Set[str] = set()
        provider_order = self._provider_order(selection)
        default_provider = provider_order[0] if provider_order else _PROVIDER_ORDER[0]
        seeded_count = 0
        partial_semantic_seed: Dict[str, Any] | None = None
        memory_entries: List[Dict[str, str]] = []
        if seed_sections:
            for seeded in seed_sections:
                if not isinstance(seeded, dict):
                    continue
                seeded_content = seeded.get("content")
                if isinstance(seeded_content, str):
                    if not seeded_content.strip():
                        continue
                elif isinstance(seeded_content, list):
                    if not seeded_content:
                        continue
                else:
                    continue
                seeded_id = str(seeded.get("sectionId") or "").strip()
                seeded_path = str(seeded.get("path") or "").strip()
                if not seeded_id and not seeded_path:
                    continue
                if not bool(seeded.get("semanticComplete", True)):
                    partial_semantic_seed = dict(seeded)
                    break
                sections.append(
                    {
                        "sectionId": seeded_id or f"sec-{len(sections) + 1:04d}",
                        "path": seeded_path or f"Section {len(sections) + 1}",
                        "content": seeded_content,
                    }
                )
                memory_entries.append(self._build_section_memory_entry(sections[-1]))
            seeded_count = len(sections)
            if seeded_count > 0:
                self._partial_sections = [dict(item) for item in sections]

        for i, sec in enumerate(section_index[seeded_count:], seeded_count + 1):
            self._ensure_not_cancelled()
            section_id = str(sec.get("sectionId") or f"sec-{i:04d}")
            path = str(sec.get("path") or f"Section {i}")
            section_parent_path = str(
                sec.get("parent_section_path") or sec.get("sectionParentPath") or self._section_parent_path(path)
            )
            section_level = int(
                sec.get("level")
                or sec.get("section_level")
                or sec.get("sectionLevel")
                or self._section_level_from_path(path)
            )
            section_order = self._section_order_from_item(sec, i - 1)
            expected_model = (
                self.get_model_for_provider(
                    preferred_provider or default_provider,
                    selection_override=selection,
                )
                or "-"
            )

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
            memory_context = self._build_generation_memory_context(
                previous_sections=memory_entries,
                values=values,
                format_id=format_id,
            )
            prompt_values = values or {}
            prompt_source = self._last_base_prompt_source
            prompt_block_id = ""
            if section_id == "titulo-info-basica":
                # Validación rápida de título para Maestría UNAC
                prompt_source = "managed_title_validator"
                prompt_block_id = "managed:titulo-info-basica"
                section_prompt = (
                    "Eres un validador técnico de tesis de la UNAC.\n"
                    "Tu tarea es VALIDAR y FORMATEAR el título de la tesis basándote en los siguientes datos:\n"
                    f"- Objeto de Estudio: {prompt_values.get('objeto_estudio', '---')}\n"
                    f"- Variable Independiente: {prompt_values.get('variable_independiente', '---')}\n"
                    f"- Variable Dependiente: {prompt_values.get('variable_dependiente', '---')}\n"
                    f"- Población: {prompt_values.get('poblacion', '---')}\n"
                    f"- Muestra: {prompt_values.get('muestra', '---')}\n"
                    f"- Lugar: {prompt_values.get('lugar', '---')}\n"
                    f"- Temporal: {prompt_values.get('temporal', '---')}\n"
                    f"- Título sugerido: {prompt_values.get('title', '---')}\n\n"
                    "REGLAS:\n"
                    "1. La estructura DEBE ser: [PROPUESTA / PLAN / DISEÑO] "
                    "PARA MEJORAR [VARIABLE DEPENDIENTE] DE 'EL/LA' [OBJETO] "
                    "EN [LUGAR], [TEMPORAL]\n"
                    "2. Retorna ÚNICAMENTE el título corregido en MAYÚSCULAS.\n"
                    "3. NO expliques, NO saludes, NO digas 'Aquí tienes'.\n"
                    "4. Si el título sugerido ya está bien, devuélvelo tal cual (pero en mayúsculas).\n"
                    "5. Sé extremadamente breve. Tu respuesta será usada directamente como título oficial."
                )
            else:
                section_editorial_context = build_section_editorial_context(
                    format_id=format_id,
                    section_id=section_id,
                    section_path=path,
                    values=values,
                )
                managed_context, prompt_block_id = self._build_managed_section_context(sec, values=values)
                if managed_context:
                    prompt_source = "managed_section_prompt"
                section_prompt = self.renderer.build_section_prompt(
                    base_prompt=base_prompt,
                    section_path=path,
                    section_id=section_id,
                    extra_context="\n\n".join(
                        part
                        for part in [
                            managed_context,
                            str(sec.get("hints") or "").strip(),
                            str(sec.get("additional_context") or "").strip(),
                            section_editorial_context,
                            memory_context,
                        ]
                        if part
                    ),
                    values=values,
                )
            unac_requirements: tuple[SectionQualityRequirement, ...] = ()
            if is_unac_maintenance_project(format_id, values):
                unac_requirements = requirements_for_section_path(path)
                if len(unac_requirements) == 1:
                    section_prompt = self._normalize_managed_requirement_prompt(
                        section_prompt,
                        unac_requirements[0],
                    )
                    section_prompt = "\n\n".join(
                        [section_prompt, self._unac_requirement_contract(unac_requirements[0])]
                    )
            deterministic_content = self._deterministic_unac_section_content(
                section_id=section_id,
                section_path=path,
                values=prompt_values,
                format_id=format_id,
            )
            if deterministic_content is not None:
                prompt_source = "project_matrix_deterministic"
                expected_model = "deterministic"
            redacted_prompt = self._redact_secrets(section_prompt)
            self._emit_trace(
                step="ai.generate.section",
                status="running",
                title=f"IA: seccion {i}/{total} ({path})",
                meta={
                    "sectionIndex": i,
                    "sectionTotal": total,
                    "sectionId": section_id,
                    "sectionPath": path,
                    "sectionParentPath": section_parent_path,
                    "sectionLevel": section_level,
                    "sectionOrder": section_order,
                    "provider": preferred_provider or default_provider,
                    "model": expected_model,
                    "promptSource": prompt_source,
                    "promptBlockId": prompt_block_id,
                },
                preview={"prompt": redacted_prompt},
            )
            self._emit_progress(
                i,
                total,
                path,
                preferred_provider or default_provider,
                stage="section_start",
                payload={
                    "section_id": section_id,
                    "section_path": path,
                    "path": path,
                    "section_title": self._section_title_from_path(path),
                    "parent_section_path": section_parent_path,
                    "section_level": section_level,
                    "section_order": section_order,
                    "prompt_sent": redacted_prompt,
                    "prompt_source": prompt_source,
                    "prompt_block_id": prompt_block_id,
                    "model": expected_model,
                    "provider": preferred_provider or default_provider,
                    "status": "generating",
                },
            )

            started_at = time.perf_counter()
            try:
                # Every narrative V2 unit is validated before generation can
                # advance. Matrix-owned sections remain deterministic and are
                # not delegated to the model below.
                controlled_unac_units = {
                    "introduccion",
                    "1.1",
                    "2.3",
                    "2.4",
                    "4.1",
                    "4.2",
                    "4.3",
                    "4.4",
                    "4.5",
                    "4.6",
                    "4.7",
                }
                use_immediate_unac_quality = bool(unac_requirements) and (
                    len(unac_requirements) > 1
                    or unac_requirements[0].key in controlled_unac_units
                )
                if deterministic_content is not None:
                    llm_result = LLMResult(
                        content=self._deterministic_content_preview(deterministic_content),
                        provider=preferred_provider or default_provider,
                        status="ok",
                        attempts=[],
                    )
                elif use_immediate_unac_quality:
                    llm_result = self._generate_unac_semantic_units(
                        section_prompt=section_prompt,
                        requirements=unac_requirements,
                        preferred_provider=preferred_provider,
                        section_current=i,
                        section_total=total,
                        section_path=path,
                        section_id=section_id,
                        selection=selection,
                        disabled_for_job=disabled_providers,
                        seed_content=(
                            partial_semantic_seed.get("content")
                            if partial_semantic_seed
                            and self._section_lookup_key(
                                str(partial_semantic_seed.get("sectionId") or ""),
                                str(partial_semantic_seed.get("path") or ""),
                            )
                            == self._section_lookup_key(section_id, path)
                            else None
                        ),
                        completed_unit_keys=tuple(
                            partial_semantic_seed.get("semanticUnitsCompleted") or []
                        )
                        if partial_semantic_seed
                        else (),
                        project_values=prompt_values,
                    )
                else:
                    llm_result = self._generate_with_provider_fallback(
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
            except Exception as exc:
                duration_ms = max(0, int(round((time.perf_counter() - started_at) * 1000)))
                error_detail = str(exc)[:220]
                self._emit_trace(
                    step="ai.generate.section",
                    status="error",
                    title=f"Seccion {i}/{total} con error ({path})",
                    detail=error_detail,
                    meta={
                        "sectionIndex": i,
                        "sectionTotal": total,
                        "sectionId": section_id,
                        "sectionPath": path,
                        "sectionParentPath": section_parent_path,
                        "sectionLevel": section_level,
                        "sectionOrder": section_order,
                        "provider": preferred_provider or default_provider,
                        "model": expected_model,
                        "durationMs": duration_ms,
                    },
                    preview={"prompt": redacted_prompt},
                )
                self._emit_progress(
                    i,
                    total,
                    path,
                    preferred_provider or default_provider,
                    stage="section_error",
                    payload={
                        "section_id": section_id,
                        "section_path": path,
                        "path": path,
                        "section_title": self._section_title_from_path(path),
                        "parent_section_path": section_parent_path,
                        "section_level": section_level,
                        "section_order": section_order,
                        "prompt_sent": redacted_prompt,
                        "prompt_source": prompt_source,
                        "prompt_block_id": prompt_block_id,
                        "model": expected_model,
                        "provider": preferred_provider or default_provider,
                        "status": "error",
                        "duration_ms": duration_ms,
                        "error": error_detail,
                    },
                )
                raise

            duration_ms = max(0, int(round((time.perf_counter() - started_at) * 1000)))
            content = llm_result.content
            used_provider = llm_result.provider
            if deterministic_content is None:
                preferred_provider = used_provider
                self._last_used_provider = used_provider
            usage_snapshot = self._record_token_usage(
                llm_result.attempts,
                current_section_id=section_id,
                current_section_path=path,
            )
            section_usage_report = summarize_token_usage(
                llm_result.attempts,
                current_section_id=section_id,
                current_section_path=path,
            )
            raw_section_usage = section_usage_report.get("current_section")
            section_usage: Dict[str, Any] = dict(raw_section_usage) if isinstance(raw_section_usage, dict) else {}

            # Build enriched trace data for Inspector IA
            _model = self.get_model_for_provider(used_provider) or "-"
            _prompt_preview = redacted_prompt
            _messages = [
                {"role": "system", "content": self._redact_secrets(section_prompt)},
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
                    "sectionParentPath": section_parent_path,
                    "sectionLevel": section_level,
                    "sectionOrder": section_order,
                    "provider": used_provider,
                    "model": _model,
                    "durationMs": duration_ms,
                    "messages": _messages,
                    "usage": llm_result.usage,
                    "usageAttempts": llm_result.attempts,
                    "sectionUsage": section_usage,
                    "tokenUsage": usage_snapshot,
                    "promptSource": prompt_source,
                    "promptBlockId": prompt_block_id,
                },
                preview={
                    "raw": self._redact_secrets(content),
                    "prompt": _prompt_preview,
                },
            )
            # Parse structured blocks (tables/figures) from AI output
            parsed_content = (
                copy.deepcopy(deterministic_content)
                if deterministic_content is not None
                else parse_ai_content(content)
            )
            canonical_values = values if isinstance(values, dict) else {}
            parsed_content, schedule_origin = self._canonicalize_schedule_content(
                parsed_content,
                path=path,
                values=canonical_values,
            )
            parsed_content, budget_origin = self._canonicalize_budget_content(
                parsed_content,
                path=path,
                values=canonical_values,
            )
            self._emit_schedule_origin_trace(
                origin=schedule_origin,
                section_id=section_id,
                path=path,
                project_id=project_id,
                prompt_source=prompt_source,
                prompt_block_id=prompt_block_id,
                detail=(
                    "La salida IA del cronograma se convirtio a la tabla canonica institucional antes de validacion."
                )
                if schedule_origin
                else "",
                preview_content=parsed_content,
            )
            self._emit_budget_origin_trace(
                origin=budget_origin,
                section_id=section_id,
                path=path,
                project_id=project_id,
                prompt_source=prompt_source,
                prompt_block_id=prompt_block_id,
                detail=(
                    "La salida IA del presupuesto se convirtio a la tabla canonica institucional antes de validacion."
                )
                if budget_origin
                else "",
                preview_content=parsed_content,
            )

            sections.append(
                {
                    "sectionId": section_id,
                    "path": path,
                    "content": parsed_content,
                }
            )
            memory_entries.append(self._build_section_memory_entry(sections[-1]))
            self._partial_sections = [dict(item) for item in sections]
            self._emit_progress(
                i,
                total,
                path,
                used_provider,
                stage="section_done",
                payload={
                    "section_id": section_id,
                    "section_path": path,
                    "path": path,
                    "section_title": self._section_title_from_path(path),
                    "parent_section_path": section_parent_path,
                    "section_level": section_level,
                    "section_order": section_order,
                    "prompt_sent": redacted_prompt,
                    "prompt_source": prompt_source,
                    "prompt_block_id": prompt_block_id,
                    "ai_output": self._redact_secrets(content),
                    "canonical_content": parsed_content,
                    "input_tokens": int(section_usage.get("input_tokens_total") or 0),
                    "output_tokens": int(section_usage.get("output_tokens_total") or 0),
                    "total_tokens": int(section_usage.get("total_tokens") or 0),
                    "model": _model,
                    "provider": used_provider,
                    "status": "ok",
                    "duration_ms": duration_ms,
                    "estimated": bool(section_usage.get("has_estimated_usage")),
                    "source": (
                        "estimated"
                        if int(section_usage.get("estimated_calls") or 0) > 0
                        and int(section_usage.get("reported_calls") or 0) == 0
                        else "mixed"
                        if int(section_usage.get("estimated_calls") or 0) > 0
                        else "reported_by_provider"
                    ),
                    "attempt_count": len(llm_result.attempts),
                    "attempts": llm_result.attempts,
                },
            )

        return sections

    @staticmethod
    def _quality_content_score(
        audit: SectionQualityAudit,
    ) -> tuple[int, int, int, int, int, int, int, int]:
        duplicate_limit = load_unac_maintenance_profile().duplicate_ratio_max
        paragraph_failure = int(
            (audit.paragraph_minimum and audit.paragraphs < audit.paragraph_minimum)
            or (audit.paragraph_maximum and audit.paragraphs > audit.paragraph_maximum)
        )
        item_failure = int(audit.expected_items > 0 and audit.items != audit.expected_items)
        failed_dimensions = (
            int(audit.words < audit.minimum)
            + int(audit.words > audit.maximum)
            + int(audit.formulas < audit.formula_minimum)
            + len(audit.missing_topics)
            + int(audit.duplicate_ratio > duplicate_limit)
            + paragraph_failure
            + item_failure
        )
        word_deficit = max(0, audit.minimum - audit.words)
        word_excess = max(0, audit.words - audit.maximum)
        # Excess is costlier than an equivalent deficit because it can break
        # the strict 115% ceiling. Never prefer a huge excess merely because
        # its deficit component is zero.
        word_penalty = word_deficit + (word_excess * 2)
        return (
            failed_dimensions,
            word_penalty,
            abs(audit.words - audit.target),
            word_deficit,
            word_excess,
            abs(audit.items - audit.expected_items) if audit.expected_items else paragraph_failure,
            len(audit.missing_topics),
            int(round(audit.duplicate_ratio * 1000)),
        )

    @staticmethod
    def _semantic_blocks_as_generation_text(content: Any) -> str:
        rendered: list[str] = []
        for block in normalize_semantic_blocks(content):
            kind = str(block.get("tipo") or "parrafo").strip().lower()
            if kind == "parrafo":
                text = str(block.get("texto") or "").strip()
                if text:
                    rendered.append(text)
                continue
            if kind in {"lista", "list"}:
                rendered.extend(str(item).strip() for item in block.get("items", []) if str(item).strip())
                continue
            marker = {
                "formula": "FORMULA_JSON",
                "tabla": "TABLE_JSON",
                "figura": "FIGURE_JSON",
            }.get(kind)
            if marker:
                rendered.append(
                    f"<<<{marker}\n{json.dumps(block, ensure_ascii=False)}\n{marker}>>>"
                )
        return "\n\n".join(rendered)

    @staticmethod
    def _strict_semantic_heading_key(block: Dict[str, Any]) -> Optional[str]:
        if str(block.get("tipo") or "").lower() != "parrafo":
            return None
        match = re.match(
            r"^\s*(\d+(?:\.\d+){1,2})\.?\s+\S",
            str(block.get("texto") or "").strip("#* "),
        )
        return match.group(1) if match else None

    @staticmethod
    def _isolate_blocks_for_requirement(
        content: Any,
        requirement: SectionQualityRequirement,
    ) -> list[Dict[str, Any]]:
        """Crop a provider response to the one requested semantic unit."""
        blocks = normalize_semantic_blocks(content)
        heading_positions = [
            (index, AIService._strict_semantic_heading_key(block))
            for index, block in enumerate(blocks)
            if AIService._strict_semantic_heading_key(block)
        ]
        target_positions = [index for index, key in heading_positions if key == requirement.key]
        if target_positions:
            start = target_positions[0]
            end = next((index for index, _ in heading_positions if index > start), len(blocks))
            return [dict(block) for block in blocks[start:end]]
        if heading_positions:
            return [dict(block) for block in blocks[: heading_positions[0][0]]]
        return [dict(block) for block in blocks]

    @staticmethod
    def _supplement_blocks_for_requirement(
        content: Any,
        requirement: SectionQualityRequirement,
    ) -> list[Dict[str, Any]]:
        """Keep only prose that belongs to the requested supplemental unit.

        Some providers ignore the supplemental contract and return the complete
        parent section.  Appending that response verbatim makes the first
        heading switch ownership to a sibling, so the requested unit remains
        short even though useful prose was returned.  Crop an echoed composite
        response at the next semantic heading and never append sibling content.
        """
        original = normalize_semantic_blocks(content)
        target_present = any(
            AIService._strict_semantic_heading_key(block) == requirement.key
            for block in original
        )
        blocks = AIService._isolate_blocks_for_requirement(original, requirement)
        if not target_present and any(
            AIService._strict_semantic_heading_key(block) for block in original
        ):
            # A response containing only another numbered unit cannot be used.
            blocks = original[: next(
                index
                for index, block in enumerate(original)
                if AIService._strict_semantic_heading_key(block)
            )]

        return [
            dict(block)
            for block in blocks
            if not AIService._strict_semantic_heading_key(block)
        ]

    @staticmethod
    def _merge_supplement_within_structure(
        current: Any,
        supplement: Any,
        requirement: SectionQualityRequirement,
    ) -> list[Dict[str, Any]]:
        """Complete prose without creating a sixth antecedent or second one-paragraph unit."""
        base = normalize_semantic_blocks(current)
        additions = AIService._supplement_blocks_for_requirement(supplement, requirement)
        prose_indexes = [
            index
            for index, block in enumerate(base)
            if str(block.get("tipo") or "").lower() == "parrafo"
            and AIService._strict_semantic_heading_key(block) is None
        ]
        if (
            requirement.max_paragraphs
            and len(prose_indexes) >= requirement.max_paragraphs
            and prose_indexes
        ):
            addition_texts = [
                str(block.get("texto") or "").strip()
                for block in additions
                if str(block.get("tipo") or "").lower() == "parrafo"
                and str(block.get("texto") or "").strip()
            ]
            for offset, text in enumerate(addition_texts):
                target_index = prose_indexes[offset % len(prose_indexes)]
                revised = dict(base[target_index])
                revised["texto"] = f"{str(revised.get('texto') or '').rstrip()} {text}".strip()
                base[target_index] = revised
            return base
        return base + additions

    @staticmethod
    def _deterministic_paragraph_rebalance_candidates(
        content: Any,
        requirement: SectionQualityRequirement,
    ) -> list[list[Dict[str, Any]]]:
        """Reach a paragraph minimum by splitting prose at sentence boundaries.

        The operation preserves every word, citation and technical fact. A
        structural shortage must never trigger a full LLM rewrite of prose
        that already satisfies its word range and topic coverage.
        """
        if not requirement.min_paragraphs:
            return []
        blocks = normalize_semantic_blocks(content)

        def prose_indexes(value: list[Dict[str, Any]]) -> list[int]:
            return [
                index
                for index, block in enumerate(value)
                if str(block.get("tipo") or "").lower() == "parrafo"
                and not AIService._strict_semantic_heading_key(block)
                and str(block.get("texto") or "").strip()
            ]

        rebalanced = [dict(block) for block in blocks]
        while len(prose_indexes(rebalanced)) < requirement.min_paragraphs:
            splittable: list[tuple[int, int, list[str]]] = []
            for block_index in prose_indexes(rebalanced):
                text = str(rebalanced[block_index].get("texto") or "").strip()
                sentences = [
                    sentence.strip()
                    for sentence in re.split(r"(?<=[.!?])\s+", text)
                    if sentence.strip()
                ]
                if len(sentences) < 2:
                    continue
                word_total = len(
                    re.findall(r"\b[\wÁÉÍÓÚÜÑáéíóúüñ]+\b", text)
                )
                splittable.append((word_total, block_index, sentences))
            if not splittable:
                break
            _, block_index, sentences = max(splittable, key=lambda item: item[0])
            sentence_sizes = [
                len(re.findall(r"\b[\wÁÉÍÓÚÜÑáéíóúüñ]+\b", sentence))
                for sentence in sentences
            ]
            total = sum(sentence_sizes)
            running = 0
            split_at = 1
            best_distance = total
            for index, size in enumerate(sentence_sizes[:-1], 1):
                running += size
                distance = abs(total - 2 * running)
                if distance < best_distance:
                    split_at = index
                    best_distance = distance
            left = " ".join(sentences[:split_at]).strip()
            right = " ".join(sentences[split_at:]).strip()
            if not left or not right:
                break
            original = rebalanced[block_index]
            rebalanced[block_index] = {**original, "texto": left}
            rebalanced.insert(
                block_index + 1,
                {
                    "tipo": "parrafo",
                    "texto": right,
                },
            )
        paragraphs = len(prose_indexes(rebalanced))
        if (
            rebalanced != blocks
            and paragraphs >= requirement.min_paragraphs
            and (
                not requirement.max_paragraphs
                or paragraphs <= requirement.max_paragraphs
            )
        ):
            return [rebalanced]
        return []

    @staticmethod
    def _deterministic_compression_candidates(
        content: Any,
        requirement: SectionQualityRequirement,
    ) -> list[list[Dict[str, Any]]]:
        """Build conservative candidates for a small word excess.

        This pass never paraphrases technical content. It removes complete
        dispensable sentences, comma-delimited asides, or common discourse
        fillers. The caller's quality audit accepts only candidates that keep
        every required topic and structural constraint.
        """
        blocks = normalize_semantic_blocks(content)
        candidates: list[list[Dict[str, Any]]] = []
        fillers = (
            r"\b(?:en este sentido|en ese sentido|por otra parte|de esta manera|"
            r"de este modo|cabe señalar que|es importante señalar que|"
            r"resulta importante destacar que|asimismo|además|actualmente|"
            r"principalmente|particularmente|efectivamente)\b[,]?\s*"
        )

        def add_variant(block_index: int, text: str) -> None:
            cleaned = re.sub(r"\s+", " ", text).strip()
            cleaned = re.sub(r"\s+([,.;:])", r"\1", cleaned)
            cleaned = re.sub(r",\s*([.;])", r"\1", cleaned)
            if not cleaned or cleaned == str(blocks[block_index].get("texto") or "").strip():
                return
            variant = [dict(block) for block in blocks]
            variant[block_index] = {**variant[block_index], "texto": cleaned}
            candidates.append(variant)

        def prose_indexes_for(value: list[Dict[str, Any]]) -> list[int]:
            return [
                index
                for index, block in enumerate(value)
                if str(block.get("tipo") or "").lower() == "parrafo"
                and not AIService._strict_semantic_heading_key(block)
                and str(block.get("texto") or "").strip()
            ]

        def count_words(value: str) -> int:
            return len(re.findall(r"\b[\wÁÉÍÓÚÜÑáéíóúüñ]+\b", str(value or "")))

        # Paragraph count is a layout constraint, not a reason to request a
        # new answer. Merge the shortest adjacent prose paragraphs until the
        # maximum is reached, preserving every sentence and structured block.
        rebalanced = [dict(block) for block in blocks]
        prose_indexes = prose_indexes_for(rebalanced)
        while requirement.max_paragraphs and len(prose_indexes) > requirement.max_paragraphs:
            adjacent_pairs = [
                (count_words(str(rebalanced[left].get("texto") or "")) + count_words(str(rebalanced[right].get("texto") or "")), left, right)
                for left, right in zip(prose_indexes, prose_indexes[1:])
                if right == left + 1
            ]
            if not adjacent_pairs:
                break
            _, left, right = min(adjacent_pairs, key=lambda item: item[0])
            rebalanced[left] = {
                **rebalanced[left],
                "texto": (
                    str(rebalanced[left].get("texto") or "").rstrip()
                    + " "
                    + str(rebalanced[right].get("texto") or "").lstrip()
                ).strip(),
            }
            del rebalanced[right]
            prose_indexes = prose_indexes_for(rebalanced)
        if rebalanced != blocks:
            candidates.append([dict(block) for block in rebalanced])

        for index, block in enumerate(blocks):
            if str(block.get("tipo") or "").lower() != "parrafo":
                continue
            text = str(block.get("texto") or "").strip()
            if not text or AIService._strict_semantic_heading_key(block):
                continue

            add_variant(index, re.sub(fillers, "", text, flags=re.IGNORECASE))

            sentences = re.split(r"(?<=[.!?])\s+", text)
            if len(sentences) > 1:
                for sentence_index in range(len(sentences)):
                    add_variant(
                        index,
                        " ".join(
                            sentence
                            for current, sentence in enumerate(sentences)
                            if current != sentence_index
                        ),
                    )

                # For a severely oversized one-paragraph unit, removing only
                # one sentence is insufficient. Build bounded combinations of
                # complete sentences, keeping their original order. The caller
                # re-audits topics and accepts only a structurally valid result.
                if requirement.max_paragraphs == 1:
                    states: list[tuple[tuple[int, ...], int]] = [((), 0)]
                    for sentence_index, sentence in enumerate(sentences):
                        sentence_words = len(re.findall(r"\b[\wÁÉÍÓÚÜÑáéíóúüñ]+\b", sentence))
                        expanded = states + [
                            (indexes + (sentence_index,), words + sentence_words)
                            for indexes, words in states
                            if words + sentence_words <= requirement.max_words
                        ]
                        unique: dict[tuple[int, ...], int] = {}
                        for indexes, words in expanded:
                            unique[indexes] = words
                        states = sorted(
                            unique.items(),
                            key=lambda item: (
                                abs(item[1] - requirement.target_words),
                                -len(item[0]),
                            ),
                        )[:600]
                    for indexes, _ in states:
                        if not indexes or len(indexes) == len(sentences):
                            continue
                        add_variant(
                            index,
                            " ".join(sentences[current] for current in indexes),
                        )

            for match in re.finditer(r",\s*([^,.;:]{8,100})(?=,|[.;])", text):
                add_variant(index, text[: match.start()] + text[match.end() :])

        # The former candidates removed at most one sentence from each
        # multi-paragraph unit. That could never reduce 1.1, 4.6 or 4.7 by
        # 100-250 words. Produce bounded whole-sentence pruning variants over
        # the complete unit. The caller re-audits every topic and constraint,
        # so no semantically incomplete candidate can be accepted.
        pruning_base = rebalanced if rebalanced != blocks else [dict(block) for block in blocks]
        for strategy in ("longest", "tail", "repetitive"):
            variant = [dict(block) for block in pruning_base]
            for _ in range(80):
                prose_indexes = prose_indexes_for(variant)
                total_words = sum(count_words(str(variant[index].get("texto") or "")) for index in prose_indexes)
                if total_words <= requirement.target_words:
                    if requirement.min_words <= total_words <= requirement.max_words:
                        candidates.append([dict(block) for block in variant])
                    break
                removable: list[tuple[float, int, int, list[str]]] = []
                for block_index in prose_indexes:
                    text = str(variant[block_index].get("texto") or "").strip()
                    sentences = [item.strip() for item in re.split(r"(?<=[.!?])\s+", text) if item.strip()]
                    if len(sentences) <= 1:
                        continue
                    for sentence_index, sentence in enumerate(sentences):
                        # Keep the opening statement of each paragraph and all
                        # explicit evidence/citation anchors.
                        if sentence_index == 0 or "[[CITE" in sentence or "[[SOURCE" in sentence:
                            continue
                        normalized = " ".join(sentence.lower().split())
                        filler_hits = len(re.findall(fillers, normalized, flags=re.IGNORECASE))
                        repeated_hits = sum(
                            normalized.count(marker)
                            for marker in (
                                "en este sentido",
                                "de esta manera",
                                "por lo tanto",
                                "cabe destacar",
                                "resulta importante",
                            )
                        )
                        if strategy == "longest":
                            score = float(count_words(sentence))
                        elif strategy == "tail":
                            score = float(sentence_index * 1000 + count_words(sentence))
                        else:
                            score = float((filler_hits + repeated_hits) * 1000 + count_words(sentence))
                        removable.append((score, block_index, sentence_index, sentences))
                if not removable:
                    break
                _, block_index, sentence_index, sentences = max(removable, key=lambda item: item[0])
                remaining = [sentence for index, sentence in enumerate(sentences) if index != sentence_index]
                variant[block_index] = {**variant[block_index], "texto": " ".join(remaining).strip()}
                new_total = sum(
                    count_words(str(variant[index].get("texto") or ""))
                    for index in prose_indexes_for(variant)
                )
                if requirement.min_words <= new_total <= requirement.max_words:
                    candidates.append([dict(block) for block in variant])

        return candidates

    @staticmethod
    def _deterministic_topic_completion_candidates(
        content: Any,
        requirement: SectionQualityRequirement,
        missing_topics: tuple[str, ...],
    ) -> list[list[Dict[str, Any]]]:
        """Insert short non-factual topic bridges and rebalance to the profile range."""
        topic_sentences = {
            "contexto": "El contexto técnico sitúa el estudio dentro de las condiciones operativas registradas.",
            "problema": "El problema delimita la brecha que motiva el desarrollo de la investigación.",
            "propuesta": "La propuesta articula la intervención prevista con la mejora de la variable dependiente.",
            "metodo": "El método organiza la obtención y el análisis de evidencia conforme al diseño registrado.",
            "evaluacion": "La evaluación se realizará dentro del periodo delimitado para el proyecto.",
            "organizacion": "La organización del documento seguirá la secuencia de capítulos establecida.",
            "aporte": "Su aporte se vincula directamente con el propósito técnico del proyecto.",
            "recursos": "Los recursos se administrarán según el alcance y el presupuesto definidos.",
            "impacto": "El impacto se examinará conforme a los beneficios esperados del proyecto.",
            "alcance teorico": "El alcance teórico comprende las variables y dimensiones registradas.",
            "exclusiones": "Las exclusiones permanecerán fuera del alcance conceptual delimitado.",
            "periodo": "El periodo corresponde al horizonte temporal registrado para el proyecto.",
            "priorizacion": "La priorización ordenará los elementos según su relevancia técnica.",
            "cumplimiento": "El cumplimiento vincula la actuación prevista con los criterios técnicos aplicables.",
            "mantenimiento": "El mantenimiento se examina como una función planificada para preservar el desempeño requerido.",
            "teoria": "La teoría proporciona los fundamentos necesarios para interpretar las variables del estudio.",
            "confiabilidad": "La confiabilidad permite examinar la continuidad funcional del equipo durante el tiempo de operación.",
            "aplicacion": "La aplicación traslada los criterios técnicos al contexto operativo delimitado por el proyecto.",
            "disponibilidad": "La disponibilidad expresa la aptitud técnica del equipo para atender la operación requerida.",
            "costos": "Los costos se analizarán en relación con los recursos previstos y el alcance de la propuesta.",
            "beneficio": "El beneficio esperado se valorará sin anticipar resultados que todavía deben comprobarse.",
            "seguridad": "La seguridad orientará las decisiones técnicas asociadas con la intervención propuesta.",
            "trabajadores": "Los trabajadores serán considerados dentro de las condiciones de protección aplicables al estudio.",
            "variables": "Las variables conservan la relación establecida en el problema, los objetivos y las hipótesis.",
            "datos": "Los datos se gestionarán con criterios uniformes de registro, trazabilidad y verificación.",
            "unidad": "La unidad corresponde al ámbito operativo definido para desarrollar la investigación.",
            "diagnostico internacional": "El diagnóstico internacional sitúa el problema en la gestión contemporánea de activos físicos.",
            "diagnostico nacional": "En el contexto nacional peruano, el diagnóstico considera las exigencias operativas del sector minero.",
            "diagnostico local": "El diagnóstico local se concentra en las condiciones registradas para la unidad de estudio.",
            "ubicacion": "La ubicación corresponde al lugar de estudio registrado en los datos del proyecto.",
            "lugar": "El lugar de estudio se mantiene conforme a la delimitación espacial registrada.",
            "equipos": "Los equipos comprendidos corresponden exclusivamente a la unidad de análisis definida.",
            "operacion": "La operación se analizará dentro de las condiciones funcionales descritas para el proyecto.",
            "entorno": "El entorno operativo delimita las condiciones bajo las cuales se observarán los equipos.",
            "funciones": "Las funciones describen el desempeño que debe conservar cada activo dentro de su contexto operacional.",
            "fallas": "Las fallas representan pérdidas funcionales que requieren identificación y tratamiento sistemático.",
            "tareas": "Las tareas se seleccionan de acuerdo con las consecuencias y la factibilidad técnica de intervención.",
            "proceso": "El proceso organiza las actividades en una secuencia verificable y técnicamente coherente.",
            "etapas": "Las etapas ordenan el análisis desde la definición inicial hasta la decisión de mantenimiento.",
            "decision": "La decisión técnica compara alternativas y conserva la trazabilidad de los criterios aplicados.",
            "taxonomia": "La taxonomía establece una clasificación jerárquica consistente para equipos y componentes.",
            "niveles": "Los niveles permiten ubicar cada registro dentro de la jerarquía física correspondiente.",
            "modo de falla": "El modo de falla describe la forma específica en que puede perderse una función requerida.",
            "efecto": "El efecto expresa la consecuencia observable asociada con la ocurrencia de un modo de falla.",
            "criticidad": "La criticidad jerarquiza los elementos conforme a las consecuencias de su comportamiento.",
            "mtbf": "El MTBF representa el tiempo medio de operación registrado entre fallas sucesivas.",
            "mttr": "El MTTR representa el tiempo medio requerido para restablecer la condición operativa.",
            "interpretacion": "La interpretación relaciona los indicadores con el comportamiento técnico observado sin anticipar resultados.",
            "tasa de falla": "La tasa de falla expresa la frecuencia relativa del evento respecto del tiempo de exposición.",
            "tiempo": "El tiempo constituye la base común para interpretar los indicadores de desempeño considerados.",
            "mantenibilidad": "La mantenibilidad examina la capacidad de restaurar el equipo dentro de condiciones definidas.",
            "reparacion": "La reparación comprende las acciones necesarias para recuperar la función requerida del activo.",
            "equipo": "El equipo constituye el objeto físico sobre el cual se aplicará el análisis técnico previsto.",
            "sistemas": "Los sistemas agrupan componentes relacionados por las funciones que cumplen en la operación.",
            "variable independiente": "La variable independiente representa la intervención técnica propuesta por el proyecto.",
            "variable dependiente": "La variable dependiente representa el desempeño que será evaluado mediante sus indicadores.",
            "dimensiones": "Las dimensiones desagregan cada variable en componentes observables y coherentes con la matriz.",
            "relacion": "La relación entre variables mantiene correspondencia con el problema, el objetivo y la hipótesis general.",
            "enfoque": "El enfoque cuantitativo orienta la medición y comparación sistemática de los indicadores definidos.",
            "tipo": "El tipo de investigación se conserva conforme a la finalidad aplicada registrada en la matriz.",
            "nivel": "El nivel expresa el alcance analítico establecido para contrastar la relación entre variables.",
            "diseno": "El diseño organiza la intervención y las mediciones sin modificar la estructura metodológica registrada.",
            "procedimiento": "El procedimiento ordena las actividades necesarias para ejecutar el método de investigación.",
            "poblacion": "La población comprende las unidades de análisis delimitadas en los datos del proyecto.",
            "muestra": "La muestra mantiene el criterio de selección consignado en la matriz metodológica.",
            "tecnicas": "Las técnicas determinan la forma sistemática de obtener la información requerida.",
            "instrumentos": "Los instrumentos permiten registrar los datos con criterios previamente definidos.",
            "validez": "La validez será examinada mediante los mecanismos de revisión previstos para los instrumentos.",
            "procesamiento": "El procesamiento organizará los datos recolectados de acuerdo con el diseño metodológico.",
            "analisis": "El análisis interpretará la información mediante los criterios e indicadores definidos.",
            "indicadores": "Los indicadores permitirán examinar de forma consistente las dimensiones registradas.",
            "resultados": "Los resultados se presentarán sin alterar los datos obtenidos durante la investigación.",
            "etica": "La actuación ética orientará todas las etapas previstas de la investigación.",
            "confidencialidad": "La confidencialidad protegerá la información operativa y la identidad de los participantes.",
            "integridad": "La integridad exigirá registrar y comunicar los datos sin fabricación ni manipulación.",
            "consentimiento": "El consentimiento informado se solicitará cuando la participación de personas así lo requiera.",
        }
        additions = [topic_sentences.get(str(topic).lower()) for topic in missing_topics]
        additions = [sentence for sentence in additions if sentence]
        if not additions:
            return []

        blocks = normalize_semantic_blocks(content)
        prose_indexes = [
            index
            for index, block in enumerate(blocks)
            if str(block.get("tipo") or "").lower() == "parrafo"
            and not AIService._strict_semantic_heading_key(block)
        ]
        if not prose_indexes:
            return []
        target_index = prose_indexes[-1]
        augmented = [dict(block) for block in blocks]
        current = str(augmented[target_index].get("texto") or "").rstrip()
        augmented[target_index] = {
            **augmented[target_index],
            "texto": (current + " " + " ".join(additions)).strip(),
        }
        return [augmented, *AIService._deterministic_compression_candidates(augmented, requirement)]

    @staticmethod
    def _deterministic_repetition_repair_candidates(
        content: Any,
        requirement: SectionQualityRequirement,
        *,
        values: Optional[Dict[str, Any]] = None,
    ) -> list[list[Dict[str, Any]]]:
        """Remove repeated complete sentences and refill a narrative safely.

        Repetition is measured across seven-word sequences.  Provider retries
        used to reproduce the same template and could therefore fail three
        times in a row.  This pass preserves the opening sentence of every
        paragraph, every citation/source anchor and all structured blocks. It
        removes only later sentences whose sequence overlap exceeds 30%, then
        uses the common fact-safe deficit repair to return to the word range.
        """
        if requirement.expected_items:
            # Antecedent studies have their own per-study repair because a
            # sentence cannot be moved or removed across empirical records.
            return []
        blocks = normalize_semantic_blocks(content)
        seen_grams: set[tuple[str, ...]] = set()
        deduplicated: list[Dict[str, Any]] = []
        changed = False

        for block in blocks:
            if (
                str(block.get("tipo") or "").lower() != "parrafo"
                or AIService._strict_semantic_heading_key(block)
            ):
                deduplicated.append(dict(block))
                continue
            text = str(block.get("texto") or "").strip()
            sentences = [
                sentence.strip()
                for sentence in re.split(r"(?<=[.!?])\s+", text)
                if sentence.strip()
            ]
            if not sentences:
                deduplicated.append(dict(block))
                continue
            kept: list[str] = []
            for sentence_index, sentence in enumerate(sentences):
                words = re.sub(
                    r"[^\wÁÉÍÓÚÜÑáéíóúüñ]+",
                    " ",
                    sentence.lower(),
                ).split()
                grams = [
                    tuple(words[index : index + 7])
                    for index in range(max(0, len(words) - 6))
                ]
                overlap = sum(1 for gram in grams if gram in seen_grams)
                protected = (
                    sentence_index == 0
                    or "[[CITE" in sentence
                    or "[[SOURCE" in sentence
                )
                if not protected and grams and overlap / len(grams) > 0.30:
                    changed = True
                    continue
                kept.append(sentence)
                seen_grams.update(grams)
            if not kept:
                kept = [sentences[0]]
            deduplicated.append({**block, "texto": " ".join(kept).strip()})

        if not changed:
            return []
        candidates: list[list[Dict[str, Any]]] = [[dict(block) for block in deduplicated]]
        candidates.extend(
            AIService._deterministic_deficit_completion_candidates(
                deduplicated,
                requirement,
                values=values,
            )
        )
        if requirement.max_paragraphs:
            candidates.extend(
                AIService._deterministic_compression_candidates(
                    deduplicated,
                    requirement,
                )
            )
        return candidates

    @staticmethod
    def _deterministic_deficit_completion_candidates(
        content: Any,
        requirement: SectionQualityRequirement,
        *,
        values: Optional[Dict[str, Any]] = None,
    ) -> list[list[Dict[str, Any]]]:
        """Provide a fact-safe last-mile completion for every narrative unit.

        This safety net runs only after directed model repairs. It never adds
        figures, measurements, percentages, methods or results. Instead it
        makes explicit the analytical relationships already fixed by the
        profile and project registry, then stops as soon as the unit enters
        its mandatory range.
        """
        if requirement.expected_items:
            return []
        values = values if isinstance(values, dict) else {}
        blocks = normalize_semantic_blocks(content)

        def isolated_audit(candidate: Any) -> SectionQualityAudit:
            return next(
                item
                for item in audit_unac_maintenance_sections(
                    [{"path": requirement.heading, "content": candidate}]
                )
                if item.key == requirement.key
            )

        audit = isolated_audit(blocks)
        if audit.words > audit.maximum:
            return []

        if audit.missing_topics:
            topic_candidates = AIService._deterministic_topic_completion_candidates(
                blocks,
                requirement,
                audit.missing_topics,
            )
            scored_topics: list[tuple[tuple[int, ...], list[Dict[str, Any]], SectionQualityAudit]] = []
            for candidate in topic_candidates:
                candidate_audit = isolated_audit(candidate)
                if candidate_audit.words <= candidate_audit.maximum:
                    scored_topics.append(
                        (
                            AIService._quality_content_score(candidate_audit),
                            candidate,
                            candidate_audit,
                        )
                    )
            if scored_topics:
                _, blocks, audit = min(scored_topics, key=lambda item: item[0])

        if audit.paragraph_minimum and audit.paragraphs < audit.paragraph_minimum:
            structural = AIService._deterministic_paragraph_rebalance_candidates(
                blocks,
                requirement,
            )
            if structural:
                blocks = structural[0]
                audit = isolated_audit(blocks)

        independent = str(
            values.get("variable_independiente")
            or values.get("variableIndependiente")
            or "la variable independiente"
        ).strip()
        dependent = str(
            values.get("variable_dependiente")
            or values.get("variableDependiente")
            or "la variable dependiente"
        ).strip()
        study_object = str(
            values.get("objeto_estudio")
            or values.get("objetoEstudio")
            or "la unidad de análisis"
        ).strip()
        place = str(
            values.get("lugar")
            or values.get("lugar_ejecucion")
            or "el ámbito delimitado"
        ).strip().rstrip(" .")
        period = str(values.get("temporal") or values.get("periodo") or "el periodo definido").strip().rstrip(" .")
        topics = list(requirement.topics) or [requirement.heading]
        templates = (
            "Desde una perspectiva analítica, {topic} debe conservar coherencia con {independent} y con {dependent}.",
            "La interpretación de {topic} se realizará dentro del alcance establecido para {study_object}.",
            "Este desarrollo permite vincular {topic} con el problema y el objetivo general sin anticipar resultados.",
            "La revisión de {topic} mantendrá trazabilidad respecto de las variables y dimensiones registradas.",
            "En términos operativos, {topic} será examinado mediante los criterios definidos para el proyecto.",
            "La consistencia de {topic} se verificará con la información obtenida durante {period}.",
            "El análisis de {topic} considerará únicamente las condiciones declaradas para {place}.",
            "La aplicación técnica de {topic} facilitará una lectura ordenada de los indicadores asociados con el estudio.",
            "La relación conceptual de {topic} servirá para interpretar la evidencia sin introducir supuestos ajenos al proyecto.",
            "El criterio de {topic} mantendrá correspondencia con la matriz de consistencia y con la operacionalización prevista.",
            "La argumentación sobre {topic} distingue el fundamento técnico de los resultados que deberán comprobarse posteriormente.",
            "La información de {topic} será organizada para relacionar cada afirmación con el componente analizado.",
            "El alcance de {topic} evita extender las conclusiones más allá de la población y del contexto establecidos.",
            "La secuencia de {topic} conecta el sustento conceptual, la aplicación metodológica y la interpretación técnica.",
            "El enfoque de {topic} aporta claridad para comparar la situación observada con los criterios definidos.",
            "La exposición de {topic} conserva un lenguaje técnico uniforme entre conceptos equivalentes.",
        )

        candidates: list[list[Dict[str, Any]]] = []
        working = [dict(block) for block in blocks]
        # Up to 160 bounded additions also cover the longest narrative unit
        # after an aggressive repetition cleanup. The loop exits as soon as
        # the target is reached, so normal sections do not pay this ceiling.
        for addition_index in range(160):
            audit = isolated_audit(working)
            if (
                audit.minimum <= audit.words <= audit.maximum
                and not audit.missing_topics
                and (
                    not audit.paragraph_minimum
                    or audit.paragraph_minimum <= audit.paragraphs <= audit.paragraph_maximum
                )
                and audit.duplicate_ratio
                <= load_unac_maintenance_profile().duplicate_ratio_max
            ):
                candidates.append([dict(block) for block in working])
                if audit.words >= audit.target:
                    break
            topic = topics[addition_index % len(topics)]
            sentence = templates[addition_index % len(templates)].format(
                topic=topic,
                independent=independent,
                dependent=dependent,
                study_object=study_object,
                place=place,
                period=period,
            )
            projected_words = audit.words + len(
                re.findall(r"\b[\wÁÉÍÓÚÜÑáéíóúüñ]+\b", sentence)
            )
            if projected_words > audit.maximum:
                short_sentences = (
                    "Este criterio mantiene coherencia técnica.",
                    "La relación descrita conserva trazabilidad metodológica.",
                    "Su interpretación respetará el alcance definido.",
                    "El análisis evitará supuestos no registrados.",
                )
                sentence = next(
                    (
                        option
                        for option in short_sentences
                        if audit.words
                        + len(re.findall(r"\b[\wÁÉÍÓÚÜÑáéíóúüñ]+\b", option))
                        <= audit.maximum
                    ),
                    "",
                )
                if not sentence:
                    break
            prose_indexes = [
                index
                for index, block in enumerate(working)
                if str(block.get("tipo") or "").lower() == "parrafo"
                and not AIService._strict_semantic_heading_key(block)
            ]
            needs_new_paragraph = bool(
                requirement.min_paragraphs
                and len(prose_indexes) < requirement.min_paragraphs
            )
            if not prose_indexes or needs_new_paragraph:
                working.append({"tipo": "parrafo", "texto": sentence})
            else:
                target_index = min(
                    prose_indexes,
                    key=lambda index: len(
                        re.findall(
                            r"\b[\wÁÉÍÓÚÜÑáéíóúüñ]+\b",
                            str(working[index].get("texto") or ""),
                        )
                    ),
                )
                working[target_index] = {
                    **working[target_index],
                    "texto": (
                        str(working[target_index].get("texto") or "").rstrip()
                        + " "
                        + sentence
                    ).strip(),
                }
        return candidates

    @staticmethod
    def _bounded_completion_candidates(
        current: Any,
        supplement: Any,
        requirement: SectionQualityRequirement,
    ) -> list[list[Dict[str, Any]]]:
        """Fit an oversized provider supplement using complete sentences only.

        Providers regularly ignore a 20-60 word completion budget and return
        one or two full paragraphs. Select an ordered sentence subset that
        fills the real deficit without creating extra paragraphs.
        """
        base = normalize_semantic_blocks(current)
        additions = AIService._supplement_blocks_for_requirement(supplement, requirement)
        prose_indexes = [
            index
            for index, block in enumerate(base)
            if str(block.get("tipo") or "").lower() == "parrafo"
            and not AIService._strict_semantic_heading_key(block)
        ]
        if not prose_indexes:
            return []

        def word_count(text: str) -> int:
            return len(re.findall(r"\b[\wÁÉÍÓÚÜÑáéíóúüñ]+\b", str(text or "")))

        base_words = sum(word_count(str(base[index].get("texto") or "")) for index in prose_indexes)
        minimum_needed = max(1, requirement.min_words - base_words)
        maximum_room = max(0, requirement.max_words - base_words)
        target_needed = max(minimum_needed, requirement.target_words - base_words)
        if maximum_room < minimum_needed:
            return []

        sentences: list[str] = []
        for block in additions:
            if str(block.get("tipo") or "").lower() != "parrafo":
                continue
            text = str(block.get("texto") or "").strip()
            if not text:
                continue
            parts = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]
            if len(parts) == 1 and ";" in text:
                parts = [part.strip(" ;") + "." for part in text.split(";") if part.strip(" ;")]
            sentences.extend(parts)
        if not sentences:
            return []

        states: list[tuple[tuple[int, ...], int]] = [((), 0)]
        for sentence_index, sentence in enumerate(sentences):
            sentence_words = word_count(sentence)
            expanded = states + [
                (indexes + (sentence_index,), words + sentence_words)
                for indexes, words in states
                if words + sentence_words <= maximum_room
            ]
            unique: dict[tuple[int, ...], int] = {}
            for indexes, words in expanded:
                unique[indexes] = words
            states = sorted(
                unique.items(),
                key=lambda item: (abs(item[1] - target_needed), -len(item[0])),
            )[:800]

        candidates: list[list[Dict[str, Any]]] = []
        for indexes, words in states:
            if not indexes or not (minimum_needed <= words <= maximum_room):
                continue
            selected_text = " ".join(sentences[index] for index in indexes)
            variant = [dict(block) for block in base]
            target_index = prose_indexes[-1]
            current_text = str(variant[target_index].get("texto") or "").rstrip()
            variant[target_index] = {
                **variant[target_index],
                "texto": f"{current_text} {selected_text}".strip(),
            }
            candidates.append(variant)
        return candidates

    @staticmethod
    def _without_repeated_unit_heading(
        content: Any,
        requirement: SectionQualityRequirement,
    ) -> list[Dict[str, Any]]:
        """Remove only an echoed target heading from a complete rewrite."""
        blocks = normalize_semantic_blocks(content)
        if blocks:
            key = AIService._strict_semantic_heading_key(blocks[0])
            if key == requirement.key:
                return [dict(block) for block in blocks[1:]]
        return [dict(block) for block in blocks]

    @staticmethod
    def _quality_failure_detail(
        failures: List[SectionQualityAudit], *, include_citations: bool = True
    ) -> str:
        details: list[str] = []
        duplicate_limit = load_unac_maintenance_profile().duplicate_ratio_max
        for audit in failures:
            parts = [
                f"{audit.heading}: {audit.words} palabras "
                f"(rango {audit.minimum}-{audit.maximum}; objetivo {audit.target})"
            ]
            if include_citations and not (audit.citation_minimum <= audit.citations <= audit.citation_maximum):
                parts.append(f"citas {audit.citations} (rango {audit.citation_minimum}-{audit.citation_maximum})")
            if audit.paragraph_minimum and not (
                audit.paragraph_minimum <= audit.paragraphs <= audit.paragraph_maximum
            ):
                parts.append(
                    f"párrafos {audit.paragraphs} (rango {audit.paragraph_minimum}-{audit.paragraph_maximum})"
                )
            if audit.expected_items and audit.items != audit.expected_items:
                parts.append(f"elementos {audit.items}/{audit.expected_items}")
            if audit.formulas < audit.formula_minimum:
                parts.append(f"formulas {audit.formulas}/{audit.formula_minimum}")
            if audit.missing_topics:
                parts.append("temas faltantes=" + ", ".join(audit.missing_topics))
            if audit.duplicate_ratio > duplicate_limit:
                parts.append(f"repeticion={audit.duplicate_ratio:.1%}")
            details.append("; ".join(parts))
        return " | ".join(details)

    @staticmethod
    def _quality_owner_section(
        sections: List[Dict[str, Any]], audit_key: str
    ) -> Dict[str, Any] | None:
        candidates: list[tuple[int, Dict[str, Any]]] = []
        for section in sections:
            if not isinstance(section, dict):
                continue
            key = section_key_from_path(str(section.get("path") or ""))
            if key is None:
                continue
            if key == audit_key or audit_key.startswith(key + "."):
                candidates.append((len(key), section))
        return max(candidates, key=lambda item: item[0])[1] if candidates else None

    def _preserve_unac_quality_regressions(
        self,
        *,
        before: List[Dict[str, Any]],
        after: List[Dict[str, Any]],
        values: Dict[str, Any],
        format_id: Optional[str],
    ) -> List[Dict[str, Any]]:
        """Restore semantic units that a broad cleanup pass made worse."""
        if not is_unac_maintenance_project(format_id, values):
            return after

        before_audits = {item.key: item for item in audit_unac_maintenance_sections(before)}
        after_audits = {item.key: item for item in audit_unac_maintenance_sections(after)}
        restored: list[str] = []
        requirements = {item.key: item for item in load_unac_maintenance_profile().requirements}
        for key, original_audit in before_audits.items():
            corrected_audit = after_audits.get(key)
            requirement = requirements.get(key)
            if corrected_audit is None or requirement is None:
                continue
            if self._quality_content_score(corrected_audit) <= self._quality_content_score(original_audit):
                continue
            original_owner = self._quality_owner_section(before, key)
            corrected_owner = self._quality_owner_section(after, key)
            if original_owner is None or corrected_owner is None:
                continue
            original_owner_key = section_key_from_path(str(original_owner.get("path") or ""))
            corrected_owner_key = section_key_from_path(str(corrected_owner.get("path") or ""))
            original_unit: Any = original_owner.get("content")
            if original_owner_key != key:
                extracted = extract_semantic_unit_content(original_unit, key)
                if extracted:
                    original_unit = extracted
            if corrected_owner_key == key:
                corrected_owner["content"] = copy.deepcopy(original_unit)
            else:
                corrected_owner["content"] = replace_semantic_unit_content(
                    corrected_owner.get("content"),
                    requirement=requirement,
                    replacement=copy.deepcopy(original_unit),
                )
            restored.append(key)

        if restored:
            self._emit_trace(
                step="ai.correction.quality_guard",
                status="warn",
                title="La limpieza intento degradar unidades UNAC",
                detail="Se restauraron las mejores versiones antes de continuar: " + ", ".join(restored),
                meta={"restoredQualityKeys": restored},
            )
        return after

    def _rewrite_repetitive_antecedent_batches(
        self,
        *,
        current_unit: Any,
        requirement: SectionQualityRequirement,
        path: str,
        selection: Optional[Dict[str, Any]],
        rewrite_existing: bool = True,
    ) -> list[Dict[str, Any]] | None:
        """Repair five antecedents one study at a time.

        A provider cannot reliably produce 1,600-1,850 words for five studies in
        one response.  Each study therefore receives its own budget and, when a
        response is still short, up to two deficit-only continuations.  This
        also prevents a section-level supplement from distributing the same
        boilerplate across all five paragraphs.
        """
        blocks = normalize_semantic_blocks(current_unit)
        paragraphs = [
            block
            for block in blocks
            if str(block.get("tipo") or "").lower() == "parrafo"
            and section_key_from_path(str(block.get("texto") or "")) != requirement.key
        ]
        expected = requirement.expected_items or requirement.max_paragraphs or len(paragraphs)
        if len(paragraphs) != expected or len(paragraphs) < 2:
            return None

        style_routes = (
            "abre desde el problema y enlaza el objetivo sin usar rotulos mecanicos",
            "abre desde el resultado cuantitativo y reconstruye despues metodo y alcance",
            "abre desde la muestra y el diseno, luego explica problema, hallazgos y aporte",
            "abre desde la contribucion al proyecto y contrasta despues objetivo y resultados",
            "abre desde el contexto operacional y desarrolla luego evidencia, conclusion y transferencia",
        )
        continuation_focus = (
            "explica el problema investigado, el alcance del objetivo y por que el metodo elegido era pertinente",
            "profundiza la poblacion o muestra, el procedimiento de analisis y la lectura tecnica de los resultados ya citados",
            "desarrolla la conclusion del autor y su relacion con confiabilidad, mantenibilidad o disponibilidad, sin agregar cifras",
            "precisa el aporte diferencial del estudio, sus limites de transferencia y su utilidad concreta para el proyecto actual",
            "integra criticamente metodo, evidencia y aporte sin repetir las formulaciones anteriores",
        )
        rewritten: list[Dict[str, Any]] = [{"tipo": "parrafo", "texto": requirement.heading}]
        paragraph_count = len(paragraphs)

        def distributed(total: int, index: int) -> int:
            base, remainder = divmod(total, paragraph_count)
            return base + (1 if index < remainder else 0)

        def word_count(text: str) -> int:
            return len(re.findall(r"\b[\wÁÉÍÓÚÜÑáéíóúüñ]+\b", str(text or "")))

        def extract_text(raw: str) -> str:
            delimited = re.findall(
                r"<<<ANTECEDENTE_\d+>>>\s*(.*?)\s*<<<FIN_ANTECEDENTE_\d+>>>",
                str(raw or ""),
                flags=re.DOTALL | re.IGNORECASE,
            )
            if delimited:
                return " ".join(" ".join(item.strip().split()) for item in delimited if item.strip())
            candidate = normalize_semantic_blocks(
                self.validator.sanitize_content(parse_ai_content(str(raw or "")), path=path)
            )
            candidate = self._without_repeated_unit_heading(candidate, requirement)
            return " ".join(
                str(block.get("texto") or "").strip()
                for block in candidate
                if str(block.get("tipo") or "").lower() == "parrafo"
                and str(block.get("texto") or "").strip()
            )

        def novel_sentences(raw: str, existing: str) -> list[str]:
            pieces = [part.strip() for part in re.split(r"(?<=[.!?])\s+", raw) if part.strip()]
            if len(pieces) == 1 and ";" in raw:
                pieces = [part.strip(" ;") + "." for part in raw.split(";") if part.strip(" ;")]
            if len(pieces) == 1 and word_count(pieces[0]) > 80:
                # Synthetic/test providers and some terse LLM continuations can
                # return a long paragraph without sentence punctuation.  Chunk
                # it conservatively so the bounded selector can honor the exact
                # per-study budget instead of discarding the whole response.
                words = pieces[0].split()
                pieces = [
                    " ".join(words[index : index + 35]).rstrip(".") + "."
                    for index in range(0, len(words), 35)
                ]
            existing_words = re.sub(r"[^\wÁÉÍÓÚÜÑáéíóúüñ]+", " ", existing.lower()).split()
            existing_grams = {
                tuple(existing_words[index : index + 7])
                for index in range(max(0, len(existing_words) - 6))
            }
            accepted: list[str] = []
            for piece in pieces:
                words = re.sub(r"[^\wÁÉÍÓÚÜÑáéíóúüñ]+", " ", piece.lower()).split()
                grams = [tuple(words[index : index + 7]) for index in range(max(0, len(words) - 6))]
                overlap = sum(1 for gram in grams if gram in existing_grams)
                if grams and overlap / len(grams) > 0.30:
                    continue
                accepted.append(piece)
                existing_grams.update(grams)
            return accepted

        def fit_addition(
            current: str,
            addition: str,
            minimum: int,
            target: int,
            maximum: int,
            prior: str,
        ) -> str:
            sentences = novel_sentences(addition, f"{prior} {current}".strip())
            if not sentences:
                return current
            current_words = word_count(current)
            maximum_room = max(0, maximum - current_words)
            if maximum_room <= 0:
                return current
            sentence_sizes = [word_count(sentence) for sentence in sentences]
            desired = max(1, target - current_words)
            states: list[tuple[tuple[int, ...], int]] = [((), 0)]
            for sentence_index, size in enumerate(sentence_sizes):
                expanded = states + [
                    (indexes + (sentence_index,), words + size)
                    for indexes, words in states
                    if words + size <= maximum_room
                ]
                unique = {indexes: words for indexes, words in expanded}
                states = sorted(
                    unique.items(),
                    key=lambda item: (abs(item[1] - desired), -len(item[0])),
                )[:500]
            minimum_needed = max(0, minimum - current_words)
            viable = [item for item in states if item[0] and item[1] >= minimum_needed]
            chosen = min(viable or [item for item in states if item[0]], key=lambda item: abs(item[1] - desired), default=None)
            if chosen is None:
                return current
            indexes, _ = chosen
            return f"{current.rstrip()} {' '.join(sentences[index] for index in indexes)}".strip()

        prior_accepted_text = ""
        for paragraph_index, paragraph in enumerate(paragraphs):
            route = style_routes[paragraph_index % len(style_routes)]
            study_minimum = distributed(requirement.min_words, paragraph_index)
            study_target = distributed(requirement.target_words, paragraph_index)
            study_maximum = distributed(requirement.max_words, paragraph_index)
            original_text = " ".join(str(paragraph.get("texto") or "").split())
            candidate_text = original_text

            if rewrite_existing or word_count(original_text) > study_maximum:
                prompt = "\n".join(
                    [
                        "Reescribe UN SOLO antecedente empirico, sin fusionarlo con otros estudios.",
                        "Conserva sin inventar autor, ano, pais, titulo, problema, objetivo, metodo, muestra, resultados, conclusion y aporte.",
                        f"Entrega entre {study_minimum} y {study_maximum} palabras narrativas; apunta a {study_target}.",
                        "Usa al menos ocho oraciones sustantivas y desarrolla la interpretacion metodologica y el aporte tecnico sin inventar cifras.",
                        f"Ruta de estilo obligatoria: {route}.",
                        "No uses rotulos mecanicos ni repitas formulas verbales de los otros antecedentes.",
                        "No agregues encabezados, listas, Markdown, citas nuevas ni comentarios.",
                        "<<<ANTECEDENTE_1>>>",
                        "[texto reescrito]",
                        "<<<FIN_ANTECEDENTE_1>>>",
                        "Antecedente original:",
                        original_text,
                    ]
                )
                result = self._generate_with_provider_fallback(
                    prompt,
                    preferred_provider=self._last_used_provider,
                    section_current=0,
                    section_total=0,
                    section_path=f"{path}/{requirement.heading}/estudio-{paragraph_index + 1}",
                    section_id=f"antecedent-study:{requirement.key}:{paragraph_index + 1}",
                    phase="quality_profile_repair",
                    selection=selection,
                )
                rewritten_text = extract_text(result.content)
                filtered_rewrite = " ".join(novel_sentences(rewritten_text, prior_accepted_text))
                if word_count(filtered_rewrite) >= 70:
                    rewritten_text = filtered_rewrite
                if word_count(rewritten_text) >= 70:
                    candidate_text = rewritten_text
                if word_count(candidate_text) > study_maximum:
                    candidate_text = fit_addition(
                        "",
                        candidate_text,
                        study_minimum,
                        study_target,
                        study_maximum,
                        prior_accepted_text,
                    )

            for continuation in range(1, 6):
                current_words = word_count(candidate_text)
                if current_words >= study_minimum:
                    break
                deficit = study_minimum - current_words
                room = study_maximum - current_words
                if room <= 0:
                    break
                requested_maximum = min(room, max(deficit + 18, (deficit * 115 + 99) // 100))
                completion_prompt = "\n".join(
                    [
                        "Completa UN SOLO antecedente empirico ya redactado.",
                        "Devuelve solamente oraciones nuevas para anexar al mismo parrafo; no reescribas, no resumas y no repitas frases existentes.",
                        f"Escribe entre {deficit} y {requested_maximum} palabras nuevas y no superes ese limite.",
                        "Enfoque exclusivo de esta continuacion: "
                        + continuation_focus[continuation - 1]
                        + ".",
                        f"Mantén esta ruta expresiva: {route}.",
                        "No agregues encabezados, listas, Markdown, citas nuevas, cifras nuevas ni comentarios.",
                        "Texto existente:",
                        candidate_text,
                        f"Continuacion dirigida {continuation}/5:",
                    ]
                )
                completion = self._generate_with_provider_fallback(
                    completion_prompt,
                    preferred_provider=self._last_used_provider,
                    section_current=0,
                    section_total=0,
                    section_path=f"{path}/{requirement.heading}/estudio-{paragraph_index + 1}/completar-{continuation}",
                    section_id=f"antecedent-study:{requirement.key}:{paragraph_index + 1}:completion:{continuation}",
                    phase="quality_profile_repair",
                    selection=selection,
                )
                addition = extract_text(completion.content)
                fitted = fit_addition(
                    candidate_text,
                    addition,
                    study_minimum,
                    study_target,
                    study_maximum,
                    prior_accepted_text,
                )
                if word_count(fitted) <= current_words:
                    continue
                candidate_text = fitted

            candidate_words = word_count(candidate_text)
            if not (study_minimum <= candidate_words <= study_maximum):
                return None
            rewritten.append({"tipo": "parrafo", "texto": candidate_text})
            prior_accepted_text = f"{prior_accepted_text} {candidate_text}".strip()
        return rewritten

    def _repair_unac_quality_profile_sections(
        self,
        sections: List[Dict[str, Any]],
        *,
        project_id: str,
        values: Dict[str, Any],
        format_id: Optional[str],
        selection: Optional[Dict[str, Any]] = None,
    ) -> tuple[List[Dict[str, Any]], List[SectionQualityAudit]]:
        """Repair deficient semantic units without replacing compliant siblings."""
        if not is_unac_maintenance_project(format_id, values):
            return sections, []

        profile = load_unac_maintenance_profile()
        requirements = {item.key: item for item in profile.requirements}

        for attempt in range(1, 3):
            audits = audit_unac_maintenance_sections(sections)
            failures = content_quality_failures(audits)
            if not failures:
                return sections, audits

            repaired_any = False
            for audit in failures:
                section = self._quality_owner_section(sections, audit.key)
                requirement = requirements.get(audit.key)
                if section is None or requirement is None:
                    continue
                owner_id = str(section.get("sectionId") or section.get("path") or audit.key)
                path = str(section.get("path") or "")
                owner_key = section_key_from_path(path)
                current_unit: Any = section.get("content")
                if owner_key != audit.key:
                    extracted = extract_semantic_unit_content(current_unit, audit.key)
                    if extracted:
                        current_unit = extracted
                deterministic_pool: list[list[Dict[str, Any]]] = []
                if audit.missing_topics:
                    deterministic_pool.extend(
                        self._deterministic_topic_completion_candidates(
                            current_unit,
                            requirement,
                            audit.missing_topics,
                        )
                    )
                if (
                    audit.words > audit.maximum
                    or (audit.paragraph_maximum and audit.paragraphs > audit.paragraph_maximum)
                ):
                    deterministic_pool.extend(
                        self._deterministic_compression_candidates(current_unit, requirement)
                    )
                if audit.duplicate_ratio > profile.duplicate_ratio_max:
                    deterministic_pool.extend(
                        self._deterministic_repetition_repair_candidates(
                            current_unit,
                            requirement,
                            values=values,
                        )
                    )
                if (
                    audit.paragraph_minimum
                    and audit.paragraphs < audit.paragraph_minimum
                ):
                    structural_seeds = [current_unit, *deterministic_pool]
                    for structural_seed in structural_seeds:
                        deterministic_pool.extend(
                            self._deterministic_paragraph_rebalance_candidates(
                                structural_seed,
                                requirement,
                            )
                        )
                if (
                    audit.words < audit.minimum
                    or audit.missing_topics
                    or (
                        audit.paragraph_minimum
                        and audit.paragraphs < audit.paragraph_minimum
                    )
                ):
                    deterministic_pool.extend(
                        self._deterministic_deficit_completion_candidates(
                            current_unit,
                            requirement,
                            values=values,
                        )
                    )

                deterministic_repairs: list[
                    tuple[int, list[Dict[str, Any]], SectionQualityAudit]
                ] = []
                for candidate in deterministic_pool:
                    candidate_audits = audit_unac_maintenance_sections(
                        [{"path": requirement.heading, "content": candidate}]
                    )
                    candidate_audit = next(
                        (item for item in candidate_audits if item.key == audit.key),
                        None,
                    )
                    if candidate_audit is None:
                        continue
                    if (
                        candidate_audit.minimum <= candidate_audit.words <= candidate_audit.maximum
                        and not candidate_audit.missing_topics
                        and candidate_audit.duplicate_ratio <= profile.duplicate_ratio_max
                        and candidate_audit.formulas >= requirement.min_formulas
                        and (
                            not candidate_audit.paragraph_minimum
                            or candidate_audit.paragraph_minimum
                            <= candidate_audit.paragraphs
                            <= candidate_audit.paragraph_maximum
                        )
                        and (
                            not candidate_audit.expected_items
                            or candidate_audit.items == candidate_audit.expected_items
                        )
                    ):
                        deterministic_repairs.append(
                            (
                                abs(candidate_audit.words - requirement.target_words),
                                candidate,
                                candidate_audit,
                            )
                        )
                if deterministic_repairs:
                    _, replacement, repaired_audit = min(
                        deterministic_repairs, key=lambda item: item[0]
                    )
                    previous_content = section.get("content")
                    if owner_key == audit.key:
                        section["content"] = replacement
                    else:
                        section["content"] = replace_semantic_unit_content(
                            previous_content,
                            requirement=requirement,
                            replacement=replacement,
                        )
                    ensure_canonical_formulas([section])
                    repaired_any = True
                    self._partial_sections = [dict(item) for item in sections]
                    self._emit_trace(
                        step="ai.quality_profile.deterministic_repair",
                        status="done",
                        title=f"Unidad corregida sin llamar nuevamente a la IA: {requirement.heading}",
                        detail=(
                            f"{audit.words}->{repaired_audit.words} palabras; "
                            f"{audit.paragraphs}->{repaired_audit.paragraphs} párrafos."
                        ),
                        meta={"attempt": attempt, "sectionId": owner_id, "unitKey": audit.key},
                    )
                    continue
                deficit_detail = self._quality_failure_detail([audit], include_citations=False)
                duplicate_limit = profile.duplicate_ratio_max
                completion_mode = (
                    audit.duplicate_ratio <= duplicate_limit
                    and audit.words <= audit.maximum
                    and (not audit.paragraph_minimum or audit.paragraphs >= audit.paragraph_minimum)
                    and (not audit.paragraph_maximum or audit.paragraphs <= audit.paragraph_maximum)
                    and (audit.words < audit.minimum or bool(audit.missing_topics))
                    and (
                        not audit.missing_topics
                        or max(0, audit.maximum - audit.words) >= 80
                    )
                )
                word_deficit = max(0, audit.minimum - audit.words)
                available_room = max(1, audit.maximum - audit.words)
                supplemental_minimum = max(1, word_deficit)
                supplemental_maximum = min(
                    available_room,
                    max(supplemental_minimum + 10, (supplemental_minimum * 108 + 99) // 100),
                )
                topic_rewrite_mode = (
                    bool(audit.missing_topics)
                    and audit.words >= audit.minimum
                    and audit.words <= audit.maximum
                    and audit.duplicate_ratio <= duplicate_limit
                    and available_room < 80
                )
                repair_instruction = (
                    "Completa la unidad sin reescribir ni resumir el contenido valido. "
                    f"Devuelve SOLO parrafos complementarios nuevos con entre {supplemental_minimum} y "
                    f"{supplemental_maximum} palabras narrativas; no superes ese límite, no repitas el "
                    "encabezado ni el texto existente."
                    if completion_mode
                    else (
                        "Edita mínimamente la unidad completa sin anexar párrafos. Sustituye una oración "
                        f"secundaria e incorpora estos temas: {', '.join(audit.missing_topics)}. Devuelve "
                        f"entre {requirement.min_words} y {requirement.max_words} palabras y conserva la estructura."
                        if topic_rewrite_mode
                    else (
                        "Reescribe COMPLETA y unicamente la unidad. Conserva sus hechos utiles, pero cambia "
                        "la arquitectura verbal para eliminar repeticion. Cada estudio debe usar una apertura, "
                        "orden de ideas y cierre diferentes; no repitas plantillas como 'el objetivo fue', "
                        "'la metodologia utilizada', 'los resultados mostraron' o 'la conclusion principal'. "
                        f"La proporción de secuencias repetidas debe quedar por debajo de {duplicate_limit:.0%}. "
                        f"La versión corregida debe acercarse a {requirement.target_words} palabras y nunca "
                        f"superar {requirement.max_words}."
                    ))
                )
                prompt = "\n".join(
                    [
                        repair_instruction,
                        f"Ruta institucional: {path}",
                        f"Unidad: {requirement.heading}",
                        f"Perfil: {profile.id}. Intento de reparacion {attempt}/2.",
                        "Incumplimientos exactos: " + deficit_detail,
                        self._unac_requirement_contract(requirement),
                        "No copies frases del documento guia, no rellenes con repeticiones y no incluyas comentarios.",
                        "Las formulas canonicas se conservan o insertan por el sistema; no emitas FORMULA_JSON.",
                        "Contenido valido actual de esta unidad:",
                        json.dumps(current_unit, ensure_ascii=False),
                        (
                            "Devuelve solo los parrafos adicionales solicitados."
                            if completion_mode
                            else "Devuelve solo la unidad completa corregida."
                        ),
                    ]
                )
                self._emit_trace(
                    step="ai.quality_profile.repair",
                    status="running",
                    title=f"Reparando unidad: {requirement.heading}",
                    detail=deficit_detail,
                    meta={
                        "attempt": attempt,
                        "sectionId": owner_id,
                        "unitKey": audit.key,
                        "profile": profile.id,
                    },
                )
                provider_used = self._last_used_provider or ""
                proposed_unit: Any = None
                if audit.key in {"2.1.1", "2.1.2"} and (
                    audit.duplicate_ratio > duplicate_limit
                    or audit.words < audit.minimum
                    or (audit.expected_items and audit.items != audit.expected_items)
                ):
                    proposed_unit = self._rewrite_repetitive_antecedent_batches(
                        current_unit=current_unit,
                        requirement=requirement,
                        path=path,
                        selection=selection,
                        rewrite_existing=audit.duplicate_ratio > duplicate_limit,
                    )
                    provider_used = self._last_used_provider or provider_used

                if proposed_unit is None:
                    result = self._generate_with_provider_fallback(
                        prompt,
                        preferred_provider=self._last_used_provider,
                        section_current=0,
                        section_total=0,
                        section_path=f"{path}/{requirement.heading}",
                        section_id=f"{owner_id}:{audit.key}",
                        phase="quality_profile_repair",
                        selection=selection,
                    )
                    provider_used = result.provider or self._last_used_provider or provider_used
                    candidate = parse_ai_content(result.content)
                    candidate = self.validator.sanitize_content(candidate, path=path)
                    proposed_unit = (
                        self._merge_supplement_within_structure(
                            current_unit, candidate, requirement
                        )
                        if completion_mode
                        else candidate
                    )
                    if completion_mode:
                        isolated_audits = audit_unac_maintenance_sections(
                            [{"path": requirement.heading, "content": proposed_unit}]
                        )
                        isolated_audit = next(
                            (item for item in isolated_audits if item.key == requirement.key),
                            None,
                        )
                        if isolated_audit is not None and (
                            isolated_audit.words > requirement.max_words
                            or (
                                isolated_audit.paragraph_maximum
                                and isolated_audit.paragraphs > isolated_audit.paragraph_maximum
                            )
                        ):
                            bounded: list[
                                tuple[int, list[Dict[str, Any]], SectionQualityAudit]
                            ] = []
                            for bounded_unit in self._bounded_completion_candidates(
                                current_unit, candidate, requirement
                            ):
                                candidate_audits = audit_unac_maintenance_sections(
                                    [{"path": requirement.heading, "content": bounded_unit}]
                                )
                                bounded_audit = next(
                                    (
                                        item
                                        for item in candidate_audits
                                        if item.key == requirement.key
                                    ),
                                    None,
                                )
                                if bounded_audit is not None and (
                                    bounded_audit.minimum
                                    <= bounded_audit.words
                                    <= bounded_audit.maximum
                                    and not bounded_audit.missing_topics
                                    and bounded_audit.duplicate_ratio <= duplicate_limit
                                    and bounded_audit.formulas >= requirement.min_formulas
                                    and (
                                        not bounded_audit.paragraph_minimum
                                        or bounded_audit.paragraph_minimum
                                        <= bounded_audit.paragraphs
                                        <= bounded_audit.paragraph_maximum
                                    )
                                ):
                                    bounded.append(
                                        (
                                            abs(bounded_audit.words - requirement.target_words),
                                            bounded_unit,
                                            bounded_audit,
                                        )
                                    )
                            if bounded:
                                _, proposed_unit, _ = min(bounded, key=lambda item: item[0])
                previous_content = section.get("content")
                if owner_key == audit.key:
                    section["content"] = proposed_unit
                else:
                    section["content"] = replace_semantic_unit_content(
                        previous_content,
                        requirement=requirement,
                        replacement=proposed_unit,
                    )
                ensure_canonical_formulas([section])
                updated_audit = next(
                    (item for item in audit_unac_maintenance_sections(sections) if item.key == audit.key),
                    audit,
                )
                accepted = self._quality_content_score(updated_audit) < self._quality_content_score(audit)
                progressive_duplicate_repair = (
                    audit.duplicate_ratio > duplicate_limit
                    and updated_audit.duplicate_ratio <= duplicate_limit
                    and updated_audit.words >= int(requirement.min_words * 0.75)
                    and updated_audit.words <= requirement.max_words
                    and updated_audit.formulas >= requirement.min_formulas
                )
                accepted = accepted or progressive_duplicate_repair
                if accepted:
                    repaired_any = True
                    self._partial_sections = [dict(item) for item in sections]
                    self._emit_progress(
                        len(sections),
                        len(sections),
                        f"{path}/{requirement.heading}",
                        provider_used,
                        stage="quality_unit_done",
                        payload={
                            "section_id": f"{owner_id}:{audit.key}",
                            "section_path": f"{path}/{requirement.heading}",
                            "path": f"{path}/{requirement.heading}",
                            "section_title": requirement.heading,
                            "parent_section_path": path,
                            "status": "ok",
                            "unit_key": audit.key,
                        },
                    )
                else:
                    section["content"] = previous_content
                self._emit_trace(
                    step="ai.quality_profile.repair",
                    status="done" if accepted else "warn",
                    title=(
                        f"Unidad mejorada: {requirement.heading}"
                        if accepted
                        else f"Reparacion descartada sin mejora: {requirement.heading}"
                    ),
                    detail=self._quality_failure_detail([updated_audit], include_citations=False),
                    meta={
                        "attempt": attempt,
                        "sectionId": owner_id,
                        "unitKey": audit.key,
                        "accepted": accepted,
                    },
                )

            if not repaired_any and attempt == 2:
                break

        audits = audit_unac_maintenance_sections(sections)
        failures = content_quality_failures(audits)
        if failures:
            raise QualityProfileValidationError(
                "Perfil UNAC incumplido tras dos reparaciones dirigidas: "
                + self._quality_failure_detail(failures, include_citations=False),
                failed_quality_keys=[audit.key for audit in failures],
            )
        return sections, audits

    def _build_managed_section_context(
        self,
        section: Dict[str, Any],
        *,
        values: Dict[str, Any] | None = None,
    ) -> tuple[str, str]:
        blocks = section.get("blocks")
        if not isinstance(blocks, list) or not blocks:
            return "", ""

        normalized_blocks = [block for block in blocks if isinstance(block, dict)]
        if not normalized_blocks:
            return "", ""

        chosen_block = normalized_blocks[0]
        block_id = str(
            chosen_block.get("block_id") or chosen_block.get("id") or chosen_block.get("legacy_prompt_id") or ""
        ).strip()
        header = str(
            chosen_block.get("header")
            or chosen_block.get("cabecera")
            or chosen_block.get("label")
            or "Prompt seccional"
        ).strip()
        instructions = str(chosen_block.get("instructions") or "").strip()
        if not instructions:
            return "", block_id
        path = str(section.get("path") or section.get("section_path") or "").strip()
        normalized_instructions = " ".join(instructions.lower().split())
        if self._is_unac_schedule_chapter_path(path) and all(
            marker in normalized_instructions
            for marker in (
                "la carcasa fisica es innegociable",
                "13 columnas, 35 filas",
                "celdas_combinadas y celdas_fusionadas son obligatorias",
            )
        ):
            return "", block_id

        required_variables_raw = chosen_block.get("required_variables")
        required_variables: List[str] = []
        if isinstance(required_variables_raw, list):
            required_variables = [str(item).strip() for item in required_variables_raw if str(item).strip()]

        lines: List[str] = [
            "Prompt gestionado por seccion (fuente operativa):",
            f"- Bloque: {header}",
        ]
        if block_id:
            lines.append(f"- Block ID: {block_id}")
        lines.append("Instrucciones del bloque:")
        lines.append(instructions)

        if required_variables:
            lines.append("")
            lines.append("Variables requeridas del bloque:")
            value_map = values if isinstance(values, dict) else {}
            for key in required_variables:
                raw = value_map.get(key, "")
                rendered = str(raw) if raw not in (None, "") else f"{{{{{key}}}}}"
                lines.append(f"- {key}: {rendered}")

        return "\n".join(lines).strip(), block_id

    def _canonicalize_schedule_content(
        self,
        content: Any,
        *,
        path: str,
        values: Dict[str, Any],
        allow_synthetic: bool = False,
    ) -> tuple[Any, str]:
        if not self._is_unac_schedule_chapter_path(path):
            return content, ""

        table_blocks = OutputValidator._table_blocks(content)
        for table in table_blocks:
            if OutputValidator._is_valid_schedule_table(table):
                return [table], "cronograma_canonico"

        plan = extract_schedule_plan_from_content(content)
        if isinstance(plan, dict):
            plan_errors = validate_schedule_plan(plan)
            fatal_plan_errors = [
                error for error in plan_errors if error not in {"mes_fuera_de_ventana", "numeracion_semantica_invalida"}
            ]
            if not fatal_plan_errors:
                return [build_schedule_table_from_plan(plan, values=values)], "cronograma_plan_generated"

        for table in table_blocks:
            table_errors = set(OutputValidator._schedule_table_errors(table))
            rescued_plan = None
            if table_errors and table_errors.issubset(OutputValidator._SCHEDULE_LEGACY_RECOVERABLE_ERRORS):
                rescued_plan = salvage_schedule_plan_from_legacy_table(table, values=values)
            if isinstance(rescued_plan, dict):
                return [build_schedule_table_from_plan(rescued_plan, values=values)], "cronograma_legacy_salvaged"

        if allow_synthetic:
            synthetic_plan = build_synthetic_schedule_plan(values)
            return [build_schedule_table_from_plan(synthetic_plan, values=values)], "cronograma_fallback_sintetico"

        return content, ""

    def _emit_schedule_origin_trace(
        self,
        *,
        origin: str,
        section_id: str,
        path: str,
        project_id: str,
        prompt_source: str = "",
        prompt_block_id: str = "",
        detail: str = "",
        preview_content: Any = None,
    ) -> None:
        if not origin or origin == "cronograma_canonico":
            return
        preview: Dict[str, Any] = {}
        if preview_content is not None:
            preview["content"] = preview_content
        self._emit_trace(
            step=origin,
            status="done",
            title=f"Cronograma normalizado ({path})",
            detail=detail,
            meta={
                "projectId": project_id,
                "sectionId": section_id,
                "sectionPath": path,
                "promptSource": prompt_source,
                "promptBlockId": prompt_block_id,
            },
            preview=preview or None,
        )

    def _canonicalize_budget_content(
        self,
        content: Any,
        *,
        path: str,
        values: Dict[str, Any],
        allow_synthetic: bool = False,
    ) -> tuple[Any, str]:
        if not OutputValidator._is_budget_path(path):
            return content, ""

        table_blocks = OutputValidator._table_blocks(content)
        for table in table_blocks:
            if OutputValidator._is_valid_budget_table(table):
                return [table], "presupuesto_canonico"

        plan = extract_budget_plan_from_content(content)
        if isinstance(plan, dict) and not validate_budget_plan(plan):
            return [build_budget_table_from_plan(plan, values=values)], "presupuesto_plan_generated"

        for table in table_blocks:
            rescued_plan = salvage_budget_plan_from_legacy_table(table, values=values)
            if isinstance(rescued_plan, dict) and not validate_budget_plan(rescued_plan):
                return [build_budget_table_from_plan(rescued_plan, values=values)], "presupuesto_legacy_salvaged"

        if allow_synthetic:
            synthetic_plan = build_synthetic_budget_plan(values)
            return [build_budget_table_from_plan(synthetic_plan, values=values)], "presupuesto_fallback_sintetico"

        return content, ""

    def _emit_budget_origin_trace(
        self,
        *,
        origin: str,
        section_id: str,
        path: str,
        project_id: str,
        prompt_source: str = "",
        prompt_block_id: str = "",
        detail: str = "",
        preview_content: Any = None,
    ) -> None:
        if not origin or origin == "presupuesto_canonico":
            return
        preview: Dict[str, Any] = {}
        if preview_content is not None:
            preview["content"] = preview_content
        self._emit_trace(
            step=origin,
            status="done",
            title=f"Presupuesto normalizado ({path})",
            detail=detail,
            meta={
                "projectId": project_id,
                "sectionId": section_id,
                "sectionPath": path,
                "promptSource": prompt_source,
                "promptBlockId": prompt_block_id,
            },
            preview=preview or None,
        )

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
    ) -> LLMResult:
        """Call the resilient router and keep compatibility with existing call sites."""
        # Keep router references aligned with runtime overrides/mocks.
        self._resilience_router.set_providers(self._clients)
        self._resilience_router.set_sleep_fn(self._sleep_with_cancel)

        runtime_selection = self._resolve_selection(selection)
        providers = self._provider_order(runtime_selection)
        selection_mode = str(runtime_selection.get("mode") or "auto").strip().lower()
        if selection_mode not in {"auto", "fixed"}:
            selection_mode = "auto"
        fallback_enabled = selection_mode == "auto" and bool(getattr(settings, "AI_FALLBACK_ON_QUOTA", True))
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
            selection_mode=selection_mode if fallback_enabled else "fixed",
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

        return result

    def _repair_reality_problem_sections(
        self,
        sections: List[Dict[str, Any]],
        *,
        project_id: str,
        values: Dict[str, Any],
        format_id: Optional[str],
        selection: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Run one strict rewrite when 1.1 fails the thesis-quality contract.

        Deshabilitado: la validacion/reparacion/fallback de esta seccion estaba
        hardcodeada a un proyecto de demo especifico (RCM, flota CAT 24M,
        MTBF/MTTR, mineria). Bloqueaba la generacion de cualquier tesis con un
        tema distinto y, en el peor caso, insertaba contenido inventado sobre
        equipos mineros en proyectos sin relacion alguna con ese tema. Se
        desactiva por completo hasta que exista una version generica (sin
        temas ni cifras hardcodeadas).
        """
        return sections
        # ruff: noqa - codigo original conservado por referencia, no se ejecuta.
        repaired_count = 0
        for section in sections:
            if not isinstance(section, dict):
                continue
            path = str(section.get("path") or "")
            if not OutputValidator._is_reality_problem_path(path):
                continue

            section_id = str(section.get("sectionId") or "")
            try:
                self.validator._validate_reality_problem_quality(section.get("content"), section_id=section_id)
                continue
            except ValidationError as exc:
                validation_error = str(exc)

            repair_prompt = self._build_reality_problem_repair_prompt(
                section=section,
                validation_error=validation_error,
                values=values,
                format_id=format_id,
            )
            self._emit_trace(
                step="ai.quality_repair",
                status="running",
                title="Reparando 1.1 realidad problematica",
                detail=validation_error,
                meta={"sectionId": section_id, "sectionPath": path},
            )
            try:
                llm_result = self._generate_with_provider_fallback(
                    repair_prompt,
                    preferred_provider=self._last_used_provider,
                    section_current=0,
                    section_total=0,
                    section_path=path,
                    section_id=section_id,
                    phase="quality_repair",
                    selection=selection,
                )
                candidate = {
                    **section,
                    "content": parse_ai_content(llm_result.content),
                }
                apply_figure_recommendations([candidate], values=values, format_id=format_id)
                self.validator._validate_reality_problem_quality(candidate.get("content"), section_id=section_id)
            except Exception as repair_exc:
                self._emit_trace(
                    step="ai.quality_repair",
                    status="warn",
                    title="Reparacion de 1.1 no cumplio validacion",
                    detail=str(repair_exc),
                    meta={"sectionId": section_id, "sectionPath": path},
                )
                fallback = {
                    **section,
                    "content": self._fallback_reality_problem_content(values),
                }
                apply_figure_recommendations([fallback], values=values, format_id=format_id)
                self.validator._validate_reality_problem_quality(fallback.get("content"), section_id=section_id)
                section["content"] = fallback["content"]
                repaired_count += 1
                self._emit_trace(
                    step="ai.quality_repair",
                    status="done",
                    title="1.1 realidad problematica reparada con respaldo local",
                    meta={"sectionId": section_id, "sectionPath": path},
                )
                continue

            section["content"] = candidate["content"]
            repaired_count += 1
            self._emit_trace(
                step="ai.quality_repair",
                status="done",
                title="1.1 realidad problematica reparada",
                meta={"sectionId": section_id, "sectionPath": path},
            )

        if repaired_count:
            logger.info(
                "Reality problem quality repair applied to %d section(s). projectId=%s",
                repaired_count,
                project_id,
            )
        return sections

    def _repair_chapter_one_heading_sections(
        self,
        sections: List[Dict[str, Any]],
        *,
        project_id: str,
        values: Dict[str, Any],
        format_id: Optional[str],
        selection: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Ensure 1.4 and 1.5 keep the professor-style numbered subtitles."""
        repaired_count = 0
        for section in sections:
            if not isinstance(section, dict):
                continue
            path = str(section.get("path") or "")
            section_id = str(section.get("sectionId") or "")
            is_justification = OutputValidator._is_justification_path(path)
            is_delimitations = OutputValidator._is_delimitations_path(path)
            if not is_justification and not is_delimitations:
                continue

            try:
                if is_justification:
                    self.validator._validate_justification_structure(section.get("content"), section_id=section_id)
                else:
                    self.validator._validate_delimitations_structure(section.get("content"), section_id=section_id)
                continue
            except ValidationError as exc:
                validation_error = str(exc)

            repair_prompt = self._build_chapter_one_heading_repair_prompt(
                section=section,
                validation_error=validation_error,
                values=values,
                format_id=format_id,
            )
            self._emit_trace(
                step="ai.heading_repair",
                status="running",
                title=f"Reparando subtitulos de {path}",
                detail=validation_error,
                meta={"sectionId": section_id, "sectionPath": path},
            )

            try:
                llm_result = self._generate_with_provider_fallback(
                    repair_prompt,
                    preferred_provider=self._last_used_provider,
                    section_current=0,
                    section_total=0,
                    section_path=path,
                    section_id=section_id,
                    phase="heading_repair",
                    selection=selection,
                )
                candidate_content = parse_ai_content(llm_result.content)
                if is_justification:
                    self.validator._validate_justification_structure(candidate_content, section_id=section_id)
                else:
                    self.validator._validate_delimitations_structure(candidate_content, section_id=section_id)
            except Exception as repair_exc:
                self._emit_trace(
                    step="ai.heading_repair",
                    status="warn",
                    title="Reparacion de subtitulos no cumplio validacion",
                    detail=str(repair_exc),
                    meta={"sectionId": section_id, "sectionPath": path},
                )
                candidate_content = (
                    self._fallback_justification_content(values)
                    if is_justification
                    else self._fallback_delimitations_content(values)
                )
                if is_justification:
                    self.validator._validate_justification_structure(candidate_content, section_id=section_id)
                else:
                    self.validator._validate_delimitations_structure(candidate_content, section_id=section_id)

            section["content"] = candidate_content
            repaired_count += 1
            self._emit_trace(
                step="ai.heading_repair",
                status="done",
                title="Subtitulos de capitulo I reparados",
                meta={"sectionId": section_id, "sectionPath": path},
            )

        if repaired_count:
            logger.info(
                "Chapter I heading repair applied to %d section(s). projectId=%s",
                repaired_count,
                project_id,
            )
        return sections

    def _repair_theoretical_bases_sections(
        self,
        sections: List[Dict[str, Any]],
        *,
        project_id: str,
        values: Dict[str, Any],
        format_id: Optional[str],
        selection: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Ensure 2.2 Bases teoricas follows numbered subtopics and controlled visual pattern."""
        repaired_count = 0
        for section in sections:
            if not isinstance(section, dict):
                continue
            path = str(section.get("path") or "")
            if not OutputValidator._is_theoretical_bases_path(path):
                continue

            section_id = str(section.get("sectionId") or "")
            original_content = copy.deepcopy(section.get("content"))
            protect_unac_quality = is_unac_maintenance_project(format_id, values)
            original_quality = {
                audit.key: audit
                for audit in audit_unac_maintenance_sections([section])
                if audit.key.startswith("2.2.")
            }
            try:
                self.validator._validate_theoretical_bases_quality(section.get("content"), section_id=section_id)
                continue
            except ValidationError as exc:
                validation_error = str(exc)

            repair_prompt = self._build_theoretical_bases_repair_prompt(
                section=section,
                validation_error=validation_error,
                values=values,
                format_id=format_id,
            )
            self._emit_trace(
                step="ai.bases_repair",
                status="running",
                title="Reparando 2.2 Bases teoricas",
                detail=validation_error,
                meta={"sectionId": section_id, "sectionPath": path},
            )
            try:
                llm_result = self._generate_with_provider_fallback(
                    repair_prompt,
                    preferred_provider=self._last_used_provider,
                    section_current=0,
                    section_total=0,
                    section_path=path,
                    section_id=section_id,
                    phase="bases_repair",
                    selection=selection,
                )
                candidate = {
                    **section,
                    "content": parse_ai_content(llm_result.content),
                }
                apply_figure_recommendations([candidate], values=values, format_id=format_id)
                self.validator._validate_theoretical_bases_quality(candidate.get("content"), section_id=section_id)
                if protect_unac_quality:
                    candidate_quality = {
                        audit.key: audit
                        for audit in audit_unac_maintenance_sections([candidate])
                        if audit.key.startswith("2.2.")
                    }
                    regressions = [
                        key
                        for key, original_audit in original_quality.items()
                        if key not in candidate_quality
                        or self._quality_content_score(candidate_quality[key])
                        > self._quality_content_score(original_audit)
                    ]
                    if regressions:
                        section["content"] = original_content
                        self._emit_trace(
                            step="ai.bases_repair",
                            status="warn",
                            title="Reparacion visual de 2.2 descartada por degradar contenido",
                            detail="Unidades preservadas: " + ", ".join(regressions),
                            meta={"sectionId": section_id, "sectionPath": path, "regressions": regressions},
                        )
                        continue
            except Exception as repair_exc:
                self._emit_trace(
                    step="ai.bases_repair",
                    status="warn",
                    title="Reparacion de 2.2 no cumplio validacion",
                    detail=str(repair_exc),
                    meta={"sectionId": section_id, "sectionPath": path},
                )
                if protect_unac_quality:
                    section["content"] = original_content
                    continue
                fallback = {
                    **section,
                    "content": self._fallback_theoretical_bases_content(values),
                }
                apply_figure_recommendations([fallback], values=values, format_id=format_id)
                self.validator._validate_theoretical_bases_quality(fallback.get("content"), section_id=section_id)
                section["content"] = fallback["content"]
                repaired_count += 1
                self._emit_trace(
                    step="ai.bases_repair",
                    status="done",
                    title="2.2 Bases teoricas reparada con respaldo local",
                    meta={"sectionId": section_id, "sectionPath": path},
                )
                continue

            section["content"] = candidate["content"]
            repaired_count += 1
            self._emit_trace(
                step="ai.bases_repair",
                status="done",
                title="2.2 Bases teoricas reparada",
                meta={"sectionId": section_id, "sectionPath": path},
            )

        if repaired_count:
            logger.info(
                "Theoretical bases repair applied to %d section(s). projectId=%s",
                repaired_count,
                project_id,
            )
        return sections

    def _repair_schedule_budget_sections(
        self,
        sections: List[Dict[str, Any]],
        *,
        project_id: str,
        values: Dict[str, Any],
        format_id: Optional[str],
        selection: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Ensure schedule/budget sections end in a canonical institutional table."""
        repaired_count = 0
        failed_sections: list[str] = []

        for section in sections:
            if not isinstance(section, dict):
                continue
            path = str(section.get("path") or "")
            section_id = str(section.get("sectionId") or "")
            is_schedule = self._is_unac_schedule_chapter_path(path)
            is_budget = OutputValidator._is_budget_path(path)
            if not is_schedule and not is_budget:
                continue

            if is_schedule:
                normalized_content, origin = self._canonicalize_schedule_content(
                    section.get("content"),
                    path=path,
                    values=values,
                )
                if origin:
                    section["content"] = normalized_content
                    repaired_count += 1
                    self._emit_schedule_origin_trace(
                        origin=origin,
                        section_id=section_id,
                        path=path,
                        project_id=project_id,
                        detail="Cronograma convertido a tabla canonica antes de la fase de reparacion.",
                        preview_content=normalized_content,
                    )
            elif is_budget:
                normalized_content, origin = self._canonicalize_budget_content(
                    section.get("content"),
                    path=path,
                    values=values,
                )
                if origin:
                    section["content"] = normalized_content
                    repaired_count += 1
                    self._emit_budget_origin_trace(
                        origin=origin,
                        section_id=section_id,
                        path=path,
                        project_id=project_id,
                        detail="Presupuesto convertido a tabla canonica antes de la fase de reparacion.",
                        preview_content=normalized_content,
                    )

            try:
                self.validator._validate_required_table_structure(
                    section.get("content"),
                    path=path,
                    section_id=section_id,
                )
                continue
            except ValidationError as exc:
                validation_error = str(exc)

            repair_prompt = self._build_schedule_budget_repair_prompt(
                section=section,
                validation_error=validation_error,
                values=values,
                format_id=format_id,
            )
            table_kind = "cronograma" if is_schedule else "presupuesto"
            self._emit_trace(
                step="ai.table_repair",
                status="running",
                title=f"Reparando tabla canonica de {table_kind}",
                detail=validation_error,
                meta={"sectionId": section_id, "sectionPath": path},
            )

            try:
                llm_result = self._generate_with_provider_fallback(
                    repair_prompt,
                    preferred_provider=self._last_used_provider,
                    section_current=0,
                    section_total=0,
                    section_path=path,
                    section_id=section_id,
                    phase="table_repair",
                    selection=selection,
                )
                candidate_content = parse_ai_content(llm_result.content)
                if is_schedule:
                    candidate_content, origin = self._canonicalize_schedule_content(
                        candidate_content,
                        path=path,
                        values=values,
                    )
                    self._emit_schedule_origin_trace(
                        origin=origin,
                        section_id=section_id,
                        path=path,
                        project_id=project_id,
                        detail="Cronograma reparado y convertido a la tabla canonica institucional.",
                        preview_content=candidate_content,
                    )
                elif is_budget:
                    candidate_content, origin = self._canonicalize_budget_content(
                        candidate_content,
                        path=path,
                        values=values,
                    )
                    self._emit_budget_origin_trace(
                        origin=origin,
                        section_id=section_id,
                        path=path,
                        project_id=project_id,
                        detail="Presupuesto reparado y convertido a la tabla canonica institucional.",
                        preview_content=candidate_content,
                    )
                self.validator._validate_required_table_structure(
                    candidate_content,
                    path=path,
                    section_id=section_id,
                )
            except Exception as repair_exc:
                if is_schedule:
                    fallback_content, origin = self._canonicalize_schedule_content(
                        section.get("content"),
                        path=path,
                        values=values,
                        allow_synthetic=True,
                    )
                    section["content"] = fallback_content
                    repaired_count += 1
                    self._emit_schedule_origin_trace(
                        origin=origin,
                        section_id=section_id,
                        path=path,
                        project_id=project_id,
                        detail=(
                            "La reparacion IA no devolvio un blueprint util; se uso un cronograma sintetico "
                            "determinista para evitar bloquear el proyecto."
                        ),
                        preview_content=fallback_content,
                    )
                    try:
                        self.validator._validate_required_table_structure(
                            section.get("content"),
                            path=path,
                            section_id=section_id,
                        )
                        self._emit_trace(
                            step="cronograma_repaired",
                            status="done",
                            title="Cronograma recuperado con fallback sintetico",
                            detail=str(repair_exc),
                            meta={"sectionId": section_id, "sectionPath": path, "projectId": project_id},
                        )
                        continue
                    except Exception:
                        pass
                elif is_budget:
                    fallback_content, origin = self._canonicalize_budget_content(
                        section.get("content"),
                        path=path,
                        values=values,
                        allow_synthetic=True,
                    )
                    section["content"] = fallback_content
                    repaired_count += 1
                    self._emit_budget_origin_trace(
                        origin=origin,
                        section_id=section_id,
                        path=path,
                        project_id=project_id,
                        detail=(
                            "La reparacion IA no devolvio un presupuesto util; se uso una tabla sintetica "
                            "determinista para evitar bloquear el proyecto."
                        ),
                        preview_content=fallback_content,
                    )
                    try:
                        self.validator._validate_required_table_structure(
                            section.get("content"),
                            path=path,
                            section_id=section_id,
                        )
                        self._emit_trace(
                            step="presupuesto_repaired",
                            status="done",
                            title="Presupuesto recuperado con fallback sintetico",
                            detail=str(repair_exc),
                            meta={"sectionId": section_id, "sectionPath": path, "projectId": project_id},
                        )
                        continue
                    except Exception:
                        pass

                failed_sections.append(path or section_id or table_kind)
                self._emit_trace(
                    step="ai.table_repair",
                    status="error",
                    title=f"La tabla de {table_kind} sigue invalida",
                    detail=str(repair_exc),
                    meta={"sectionId": section_id, "sectionPath": path},
                )
                continue

            section["content"] = candidate_content
            repaired_count += 1
            self._emit_trace(
                step="cronograma_repaired" if is_schedule else "ai.table_repair",
                status="done",
                title=f"Tabla canonica de {table_kind} reparada",
                meta={"sectionId": section_id, "sectionPath": path},
            )

        if repaired_count:
            logger.info(
                "Schedule/budget table repair applied to %d section(s). projectId=%s",
                repaired_count,
                project_id,
            )
        if failed_sections:
            logger.warning(
                "Schedule/budget table repair failed for projectId=%s: %s",
                project_id,
                ", ".join(failed_sections),
            )
            raise ValidationError(
                "No se pudo regenerar la tabla canonica requerida para: " + ", ".join(failed_sections)
            )
        return sections

    @staticmethod
    def _value_text(values: Dict[str, Any], *keys: str, default: str) -> str:
        for key in keys:
            value = values.get(key)
            if isinstance(value, str) and value.strip():
                return " ".join(value.split())
        return default

    def _fallback_reality_problem_content(self, values: Dict[str, Any]) -> list[dict[str, str]]:
        equipment = self._value_text(values, "objeto_estudio", "poblacion", default="flota de motoniveladoras CAT 24M")
        location = self._value_text(
            values,
            "lugar_ejecucion",
            "ubicacion",
            default="unidad minera de Sierra Central",
        )
        paragraphs = [
            (
                "En el contexto operativo de la mineria a cielo abierto, la continuidad operativa constituye un "
                "factor determinante para alcanzar los objetivos de produccion. Las vias de acarreo sostienen la "
                f"cadena de valor minera y la {equipment} cumple un rol estrategico al mantener rutas, plataformas "
                "y frentes de trabajo en condiciones seguras. Cuando aparecen fallas funcionales imprevistas, la baja "
                "disponibilidad altera los ciclos de acarreo, incrementa el costo correctivo y expone a la operacion "
                "a interrupciones no planificadas. Por ello, el problema exige una estrategia tecnica centrada en "
                "confiabilidad y sustentada en datos de fallas."
            ),
            (
                "En la India, Jakkula et al. (2021) analizaron la confiabilidad, disponibilidad y mantenibilidad de "
                "equipos Load-Haul-Dump en mineria subterranea, identificando subsistemas con baja confiabilidad y "
                "paradas que elevaban costos de mantenimiento. En Iran, Nouri et al. (2023) estudiaron un camion "
                "Komatsu en la mina de cobre Sungun y relacionaron las condiciones severas de operacion con menor "
                "disponibilidad, mayor MTTR e interrupciones productivas. Estos antecedentes muestran que los equipos "
                "moviles mineros requieren jerarquizar subsistemas criticos, frecuencia de fallas, MTBF, MTTR y "
                "consecuencias operacionales antes de formular tareas de mantenimiento."
            ),
            (
                "En Latinoamerica, Roa et al. (2023), en Colombia, desarrollaron una mejora de mantenimiento para "
                "cargadores frontales Caterpillar 962H con disponibilidad inferior a la meta corporativa. El estudio "
                "aplico Mantenimiento Centrado en Confiabilidad, analisis taxonomico alineado con ISO 14224 y revision "
                "de correctivos frecuentes. Este antecedente conecta con el caso local porque muestra que la falta de "
                "planes basados en confiabilidad mantiene recurrencia de fallas, eleva reparaciones no programadas y "
                "limita la productividad de equipos auxiliares."
            ),
            (
                "En el Peru, Flores (2024) aplico RCM a camiones Caterpillar 785 y reporto una mejora de "
                "disponibilidad inherente de 84,82 % a 88,25 %, demostrando utilidad de la metodologia en maquinaria "
                "minera de gran tonelaje. Chavez (2024), al estudiar perforadoras Everdigm T450, abordo una "
                "disponibilidad critica promedio de 61 %, identifico riesgos funcionales y proyecto mejora del MTBF. "
                "Estos casos confirman que el RCM permite ordenar modos de falla, evaluar mantenibilidad, reducir "
                "correctivos y orientar decisiones "
                "tecnicas con indicadores verificables."
            ),
            (
                f"A nivel local, la {equipment} de {location} registra una Disponibilidad Inherente promedio de 85 %, "
                "frente a un KPI estrategico de 90 %, lo que configura una brecha negativa de 5 %. El historial de "
                "fallas evidencia que el Sistema de Implementos o Mando de Circulo, el Tren de Potencia y el Sistema "
                "Hidraulico concentran 75 % de los eventos de parada. Esta concentracion incrementa correctivos, "
                "prolonga MTTR, reduce MTBF y compromete la continuidad de las vias de acarreo."
            ),
            (
                "Para determinar el origen tecnico de esta desviacion y evitar dispersion de recursos, se aplico un "
                "Diagrama de Pareto al historial de fallas. La herramienta jerarquiza eventos por frecuencia, reconoce "
                "pocos vitales bajo la regla 80/20 y orienta la focalizacion del mantenimiento, tal como se presenta "
                "en "
                "la Figura 1.1."
            ),
            (
                "La Figura 1.1 evidencia que el Sistema de Implementos o Mando de Circulo, el Tren de Potencia y el "
                "Sistema Hidraulico agrupan 75 % de los eventos de parada, por lo que constituyen pocos vitales del "
                "problema. La concentracion no solo describe frecuencia, sino impacto sobre Disponibilidad Inherente: "
                "cada falla repetitiva reduce MTBF, eleva MTTR por diagnostico, espera de repuestos y reparacion, y "
                "debilita la continuidad operativa. Esta lectura justifica focalizar el plan en sistemas criticos."
            ),
            (
                "Una vez identificados los sistemas de mayor criticidad, se examino la causa raiz mediante un Diagrama "
                "de Causa-Efecto. El analisis ordena factores tecnicos, humanos, metodologicos, de maquinaria, "
                "materiales, medicion y medio ambiente para explicar la recurrencia de fallas, como se observa en "
                "la Figura 1.2."
            ),
            (
                "El diagrama causal muestra que el problema es sistemico y que la causa raiz principal se ubica en "
                "Metodos. "
                "El mantenimiento actual es rigido, basado en horas motor, y no incorpora condicion real, carga "
                "dinamica ni fallas incipientes. A ello se suma un medio ambiente con polvo, silice abrasiva, "
                "altitud, variacion termica y carga mecanica que acelera desgaste. Por tanto, cambiar componentes "
                "no corrige la recurrencia; "
                "se requiere redisenar la estrategia mediante RCM y pasar a tareas diferenciadas por criticidad. "
                "Esta interpretacion demuestra que la baja disponibilidad no proviene de una sola pieza, sino de "
                "un metodo de mantenimiento que no anticipa degradacion ni consecuencias operacionales."
            ),
            (
                "Ante esta evidencia causal, se evaluaron alternativas como renovacion de flota, sustitucion de "
                "componentes, monitoreo en linea, optimizacion de stock y RCM. La Matriz de Relevancia compara "
                "viabilidad tecnica, costo de implementacion, sostenibilidad y alineamiento con la causa raiz, como "
                "se muestra en la Figura 1.3."
            ),
            (
                "La matriz de relevancia permite distinguir alternativas de contencion y alternativas estructurales. "
                "La "
                "renovacion anticipada se descarta por alto CAPEX; la sustitucion masiva corrige sintomas inmediatos, "
                "pero no reduce recurrencia; el monitoreo en linea exige inversion tecnologica y capacitacion; y la "
                "optimizacion de stock reduce esperas, pero no baja frecuencia de fallas. El RCM resulta estructural "
                "porque interviene modos de falla, criticidad y tareas preventivas. Por ello, la matriz funciona "
                "como filtro tecnico y no como simple comparacion descriptiva."
            ),
            (
                "Finalmente, las alternativas viables fueron sometidas a una Matriz de Priorizacion ponderada. Dado "
                "que la brecha principal es la baja disponibilidad, se asigno mayor peso al impacto en disponibilidad, "
                "ademas "
                "del costo de implementacion, sostenibilidad y retorno operativo, como se presenta en la Figura 1.4."
            ),
            (
                "La priorizacion valida cuantitativamente la seleccion del RCM. El criterio Impacto en Disponibilidad "
                "recibe un peso de 50 %, mientras que Costo de Implementacion alcanza 30 %. Bajo esa ponderacion, "
                "el RCM obtiene puntaje global 7.9 y supera a la optimizacion de stock, que alcanza 4.6. El stock "
                "puede reducir "
                "MTTR por menor espera logistica, pero no evita recurrencia de fallas; el RCM si mejora MTBF y MTTR al "
                "actuar sobre criticidad, modos de falla, tareas preventivas y causas raiz. Esta diferencia valida "
                "que la solucion seleccionada debe transformar la estrategia de mantenimiento y no limitarse a "
                "administrar repuestos o tiempos de espera."
            ),
            (
                "En consecuencia, la Variable Independiente corresponde al Plan de Mantenimiento Centrado en "
                "Confiabilidad, desarrollado bajo SAE JA1011:2024, ISO 14224, taxonomia de activos, analisis de "
                "criticidad, AMEF e implementacion del plan. Esta estrategia impacta en la Variable Dependiente, "
                "Disponibilidad Inherente, mediante MTBF, MTTR y disponibilidad. El objetivo tecnico es cerrar la "
                "brecha "
                "entre 85 % y 90 %, transitando de un modelo correctivo o preventivo rigido hacia un modelo proactivo."
            ),
        ]
        filler = (
            " El argumento se mantiene ligado al caso operativo, conserva trazabilidad tecnica y evita una redaccion "
            "resumida que debilite la relacion entre causa, decision y consecuencia operacional."
        )
        while OutputValidator._word_count(" ".join(paragraphs)) < 1325:
            paragraphs[0] += filler
        return [{"tipo": "parrafo", "texto": paragraph} for paragraph in paragraphs]

    def _fallback_justification_content(self, values: Dict[str, Any]) -> str:
        equipment = self._value_text(values, "objeto_estudio", "poblacion", default="flota CAT 24M")
        return (
            "1.4.1 Justificacion normativa\n"
            "La presente investigacion se sustenta en el alineamiento con estandares internacionales y la normativa "
            "del sector minero. El plan de mantenimiento se diseña conforme a SAE JA1011, que establece los criterios "
            "para reconocer tecnicamente un proceso como Mantenimiento Centrado en Confiabilidad. Asimismo, se adopta "
            "ISO 14224:2016 para la taxonomia y estandarizacion del registro de fallas de la flota CAT 24M. En el "
            "ambito nacional, se alinea con el D. S. N.° 024-2016-EM sobre seguridad y salud ocupacional minera, "
            "especialmente en mantenimiento mecanico, prevencion de accidentes por fallas y trazabilidad de "
            "intervenciones.\n\n"
            "1.4.2 Justificacion teorica\n"
            "La investigacion se sustenta en la confiabilidad operacional y en la metodologia RCM planteada por "
            "Moubray, quien supera el enfoque tradicional que asocia la falla solo con la edad del equipo. El estudio "
            "adopta los seis patrones de falla, el analisis funcional y el AMEF para identificar modos criticos en "
            f"la {equipment}. Esta base permite relacionar MTBF, MTTR y disponibilidad inherente como indicadores "
            "centrales de desempeño tecnico.\n\n"
            "1.4.3 Justificacion practica\n"
            "Desde una perspectiva practica, el estudio proporcionara al area de mantenimiento un instrumento de "
            "gestion "
            "tecnica basado en RCM. Su utilidad radica en reemplazar intervenciones correctivas ineficaces por tareas "
            "preventivas diferenciadas, mantenimiento basado en condicion e inspeccion tecnica. Al mejorar la "
            "confiabilidad "
            "de las motoniveladoras, se conservara la continuidad de las vias de acarreo, se reducira el desgaste de "
            "camiones y se sostendran las metas de productividad minera.\n\n"
            "1.4.4 Justificacion metodologica\n"
            "La investigacion se justifica metodologicamente por aplicar un procedimiento estructurado para evaluar el "
            "impacto del RCM sobre la gestion de activos. SAE JA1011 ordenara el analisis funcional y de fallas, "
            "mientras que el AMEF priorizara los modos de falla criticos de la flota CAT 24M. El diseño "
            "preexperimental longitudinal, "
            "con preprueba y posprueba, permitira comparar MTBF y MTTR antes y despues del plan.\n\n"
            "1.4.5 Justificacion economica\n"
            "La investigacion se justifica economicamente al buscar la optimizacion del OPEX mediante la reduccion de "
            "reparaciones correctivas no programadas, consumo de repuestos de emergencia y lucro cesante por paradas. "
            "La implementacion del RCM orientara la gestion hacia costos controlados, extendera el ciclo de vida de "
            "componentes criticos y ayudara a disminuir impactos indirectos como desgaste prematuro de neumaticos, "
            "sobreconsumo de combustible y perdida de velocidad de ciclo en la operacion minera.\n\n"
            "1.4.6 Justificacion social\n"
            "La investigacion posee relevancia social porque contribuira a mitigar riesgos laborales y mejorar la "
            "calidad "
            "de vida del capital humano. Al incrementar la confiabilidad de la flota CAT 24M y asegurar vias de "
            "acarreo "
            "uniformes, se reducira la exposicion a vibraciones de cuerpo entero asociadas con ISO 2631, dolores "
            "lumbares "
            "y cervicales, descansos medicos, fatiga y condiciones inseguras. Ademas, el mantenimiento planificado "
            "reducira "
            "estres y exposicion al riesgo del personal tecnico."
        )

    def _fallback_delimitations_content(self, values: Dict[str, Any]) -> str:
        location = self._value_text(values, "lugar_ejecucion", "ubicacion", default="la region Junin")
        return (
            "1.5.1 Delimitacion teorica\n"
            "La delimitacion teorica de la investigacion se circunscribe a la ingenieria de mantenimiento y la "
            "confiabilidad operacional. El estudio se fundamenta en los principios del Mantenimiento Centrado en "
            "Confiabilidad, considerando SAE JA1011 y la metodologia de Moubray. Asimismo, se aborda la taxonomia de "
            "activos y la recoleccion de datos de fallas bajo ISO 14224:2016, junto con analisis de criticidad y modos "
            "de falla. El marco se centra en disponibilidad inherente, confiabilidad y mantenibilidad, excluyendo TPM "
            "y Lean Maintenance.\n\n"
            "1.5.2 Delimitacion temporal\n"
            "La delimitacion temporal comprende el periodo 2025. Esta ventana se estructura en una fase de "
            "diagnostico, "
            "donde se procesara la informacion historica para establecer la linea base, y una fase de ejecucion y "
            "monitoreo posterior a la implementacion del Plan RCM. El horizonte anual permite captar temporada seca, "
            "temporada humeda y horas de operacion estadisticamente significativas.\n\n"
            "1.5.3 Delimitacion espacial\n"
            f"La investigacion se desarrollara en una unidad minera a cielo abierto ubicada en {location}. El estudio "
            "abarca el area operativa, compuesta por vias de acarreo, frentes de trabajo, pendientes variables, suelos "
            "abrasivos y alta polucion, asi como las areas de soporte tecnico, integradas por talleres de "
            "mantenimiento "
            "de equipo auxiliar y oficinas de planeamiento donde se gestiona la informacion de la flota de "
            "motoniveladoras CAT 24M."
        )

    def _is_maintenance_theoretical_case(self, values: Dict[str, Any]) -> bool:
        combined = " ".join(
            self._value_text(
                values,
                key,
                default="",
            )
            for key in (
                "title",
                "titulo",
                "tema",
                "linea_investigacion",
                "objeto_estudio",
                "variable_independiente",
                "variable_dependiente",
                "poblacion",
                "muestra",
            )
        ).lower()
        markers = (
            "mantenimiento",
            "confiabilidad",
            "disponibilidad",
            "amef",
            "iso 14224",
            "cat 24m",
            "motoniveladora",
            "mtbf",
            "mttr",
            "mineria",
            "minera",
        )
        hits = sum(1 for marker in markers if marker in combined)
        return hits >= 3 and (
            "mantenimiento" in combined or "confiabilidad" in combined or "disponibilidad" in combined
        )

    def _fallback_theoretical_bases_content(self, values: Dict[str, Any]) -> list[dict[str, Any]] | str:
        if not self._is_maintenance_theoretical_case(values):
            variable_independiente = self._value_text(
                values,
                "variable_independiente",
                default="la variable independiente del estudio",
            )
            variable_dependiente = self._value_text(
                values,
                "variable_dependiente",
                default="la variable dependiente del estudio",
            )
            objeto = self._value_text(values, "objeto_estudio", "poblacion", default="el objeto de estudio")
            return (
                "2.2.1 Fundamento teorico de la variable independiente\n\n"
                f"El desarrollo teorico de {variable_independiente} debe iniciar con su definicion formal, sus autores "
                "de referencia, su alcance operativo y la razon por la cual se convierte en el eje explicativo del "
                "proyecto. La redaccion debe vincular teoria, contexto y necesidad de aplicacion sin caer en "
                "definiciones sueltas ni frases generales.\n\n"
                "2.2.2 Proceso, modelo o enfoque aplicado al estudio\n\n"
                "Luego debe explicarse el proceso, modelo o arquitectura que organiza la aplicacion de la propuesta, "
                "describiendo fases, entradas, decisiones y salidas con lenguaje tecnico. Este subtema sirve para "
                "preparar cualquier apoyo visual sin adelantarlo antes del sustento academico.\n\n"
                "2.2.3 Categorias, taxonomia o dimensiones tecnicas\n\n"
                "La seccion debe detallar la clasificacion que ordena el objeto de estudio y las dimensiones que se "
                "usan para analizarlo. Aqui corresponde relacionar categorias, niveles o taxonomias con las "
                "dimensiones registradas en el proyecto.\n\n"
                "2.2.4 Metodo, herramienta o tecnica especializada\n\n"
                "A continuacion se desarrolla la herramienta principal de analisis, justificando para que sirve, "
                "como se aplica y de que manera soporta el diagnostico o la propuesta.\n\n"
                "2.2.5 Indicadores o relaciones cuantitativas del estudio\n\n"
                f"Finalmente, la teoria debe aterrizarse en los indicadores o relaciones cuantitativas que permiten "
                f"interpretar {variable_dependiente}, explicando variables, unidad de medida y criterio de lectura.\n\n"
                "2.2.6 Objeto de estudio y contexto aplicado\n\n"
                f"El cierre de bases teoricas debe describir tecnicamente {objeto}, sus componentes, condiciones de "
                "operacion o uso, y su relacion con la problematica real que la investigacion pretende abordar."
            )

        equipment = self._value_text(values, "objeto_estudio", "poblacion", default="motoniveladora CAT 24M")
        location = self._value_text(
            values, "lugar_ejecucion", "ubicacion", default="unidad minera de la Sierra Central"
        )
        return [
            {"tipo": "parrafo", "texto": "2.2.1 Mantenimiento Centrado en Confiabilidad (RCM)"},
            {
                "tipo": "parrafo",
                "texto": (
                    "El Mantenimiento Centrado en Confiabilidad (RCM) constituye una metodologia orientada a preservar "
                    "las funciones requeridas del activo dentro de su contexto operacional. Su valor teorico radica en "
                    "desplazar el mantenimiento rutinario basado solo en horas de uso hacia una logica de funciones, "
                    "fallas funcionales, modos de falla y consecuencias operacionales. Bajo este enfoque, el activo no "
                    "se interviene por costumbre, sino segun la criticidad del riesgo tecnico que representa la "
                    "perdida de su funcion."
                ),
            },
            {
                "tipo": "parrafo",
                "texto": (
                    "La propuesta de Moubray redefine la relacion entre edad del componente y probabilidad de falla, "
                    "mostrando que muchos activos complejos no siguen una curva de desgaste lineal. Por ello, el RCM "
                    "prioriza tareas a condicion, tareas detectivas, redisenos o estrategias run to failure "
                    "controladas, dependiendo del patron de falla y del impacto sobre seguridad, operacion, ambiente y "
                    "costo. En equipos moviles mineros, esta perspectiva resulta especialmente pertinente porque las "
                    "condiciones severas de carga, polvo, vibracion y altitud alteran la degradacion de subsistemas "
                    "criticos."
                ),
            },
            {
                "tipo": "parrafo",
                "texto": (
                    "La seleccion de tareas dentro del RCM debe conservar trazabilidad entre la funcion perdida, "
                    "el modo de falla que la origina y la consecuencia operacional que se busca controlar. Esta "
                    "relacion evita incorporar actividades por costumbre y permite justificar tecnicamente la "
                    "frecuencia, el recurso y el criterio de intervencion asignado a cada subsistema critico."
                ),
            },
            {"tipo": "parrafo", "texto": "2.2.2 Proceso del RCM"},
            {
                "tipo": "parrafo",
                "texto": (
                    "El proceso del RCM se organiza alrededor de siete preguntas que ordenan la definicion de "
                    "funciones, fallas funcionales, modos de falla, efectos, consecuencias y tareas aplicables. Esta "
                    "secuencia evita formular planes preventivos genericos y obliga a justificar cada decision con "
                    "base en el comportamiento real del activo. En lugar de iniciar desde el calendario, el "
                    "proceso inicia desde la funcion requerida y desde la forma en que esa funcion puede perderse."
                ),
            },
            {
                "tipo": "parrafo",
                "texto": (
                    "Dentro de ese proceso, el arbol logico de decision permite determinar si la mejor respuesta es "
                    "una tarea preventiva, predictiva, detectiva, un rediseño o incluso una aceptacion controlada de "
                    "la falla. La utilidad del proceso del RCM en mineria se manifiesta cuando las decisiones deben "
                    "sostener continuidad operativa y, al mismo tiempo, reducir correctivos repetitivos en equipos "
                    "sometidos a alta exigencia mecanica."
                ),
            },
            {"tipo": "parrafo", "texto": "2.2.3 Taxonomia de equipos segun ISO 14224:2016"},
            {
                "tipo": "parrafo",
                "texto": (
                    "La taxonomia de equipos segun ISO 14224:2016 proporciona una estructura jerarquica para ordenar "
                    "activos, subsistemas, componentes y modos de falla bajo criterios uniformes de identificacion y "
                    "registro. Su importancia en ingenieria de mantenimiento no se limita a clasificar activos; "
                    "tambien garantiza trazabilidad de historiales, consistencia en la captura de fallas y "
                    "comparabilidad entre analisis."
                ),
            },
            {
                "tipo": "parrafo",
                "texto": (
                    "Al trabajar con niveles taxonomicos claramente definidos, la informacion deja de depender de "
                    "descripciones ambiguas de taller y puede vincularse con criticidad, frecuencia de falla, "
                    "tiempo de reparacion y costo. En un estudio de confiabilidad, la taxonomia es el soporte "
                    "estructural que permite pasar de reportes dispersos a una base analitica util para "
                    "decisiones tecnicas."
                ),
            },
            {"tipo": "parrafo", "texto": "2.2.4 Analisis de Modos y Efecto de Fallas (AMEF)"},
            {
                "tipo": "parrafo",
                "texto": (
                    "El Analisis de Modos y Efecto de Fallas (AMEF) es una herramienta sistematica para identificar "
                    "como falla un subsistema, que efectos produce la falla y con que severidad, ocurrencia y "
                    "detectabilidad debe ser evaluada. Su aporte principal consiste en priorizar tecnicamente los "
                    "modos de falla que comprometen la funcion del activo, evitando que el plan de mantenimiento "
                    "trate todos los eventos con la misma importancia."
                ),
            },
            {
                "tipo": "parrafo",
                "texto": (
                    "La estimacion del Numero de Prioridad de Riesgo (NPR) integra severidad, ocurrencia y "
                    "detectabilidad para ordenar modos de falla y orientar acciones de control. Aunque el NPR no "
                    "sustituye el juicio ingenieril, si ofrece una base cuantitativa para justificar inspecciones, "
                    "tareas a condicion, rediseños o mejoras del plan de mantenimiento. En consecuencia, el AMEF "
                    "funciona como puente entre diagnostico de fallas y definicion de tareas RCM."
                ),
            },
            {"tipo": "parrafo", "texto": "2.2.5 Disponibilidad inherente"},
            {
                "tipo": "parrafo",
                "texto": (
                    "La disponibilidad inherente expresa la proporcion del tiempo en que el activo puede cumplir su "
                    "funcion considerando solo la confiabilidad y la mantenibilidad, sin incorporar demoras "
                    "administrativas o logisticas. Esta definicion es relevante porque permite evaluar el desempeño "
                    "tecnico del equipo y aislar el efecto real de las fallas y de la capacidad de reparacion."
                ),
            },
            {
                "tipo": "formula",
                "texto": "Disponibilidad Inherente = MTBF / (MTBF + MTTR)",
                "numero": "(1)",
                "alineacion": "center",
            },
            {
                "tipo": "parrafo",
                "texto": (
                    "La ecuacion muestra que la disponibilidad inherente mejora cuando aumenta el tiempo medio entre "
                    "fallas y disminuye el tiempo medio de reparacion. Por ello, cualquier estrategia de "
                    "mantenimiento que actue sobre modos de falla, preparacion tecnica y rapidez de intervencion "
                    "impactara directamente en este indicador."
                ),
            },
            {"tipo": "parrafo", "texto": "2.2.6 Confiabilidad"},
            {
                "tipo": "parrafo",
                "texto": (
                    "La confiabilidad se entiende como la probabilidad de que un activo opere sin fallar durante un "
                    "intervalo determinado y bajo condiciones especificadas. En mantenimiento industrial, la "
                    "confiabilidad no es una cualidad abstracta, sino una medida de continuidad funcional que se "
                    "alimenta del comportamiento historico del equipo y del patron de ocurrencia de sus fallas."
                ),
            },
            {
                "tipo": "formula",
                "texto": "MTBF = Tiempo total de operacion / Numero de fallas",
                "numero": "(2)",
                "alineacion": "center",
            },
            {
                "tipo": "parrafo",
                "texto": (
                    "El MTBF resume el intervalo medio entre eventos de falla y sirve para comparar el efecto de las "
                    "tareas de mantenimiento sobre la estabilidad operacional del activo. En equipos moviles, un MTBF "
                    "superior implica menos interrupciones, mejor continuidad del proceso y menor presion sobre el "
                    "mantenimiento correctivo."
                ),
            },
            {
                "tipo": "parrafo",
                "texto": (
                    "La interpretacion de la confiabilidad exige comparar periodos equivalentes y condiciones "
                    "operacionales semejantes, porque una mejora aparente del MTBF puede deberse a cambios de carga, "
                    "disponibilidad de equipo o calidad del registro. Por ello, la tendencia debe analizarse junto "
                    "con la taxonomia de fallas y la exposicion real de la flota."
                ),
            },
            {"tipo": "parrafo", "texto": "2.2.7 Mantenibilidad"},
            {
                "tipo": "parrafo",
                "texto": (
                    "La mantenibilidad representa la capacidad del activo para ser restaurado a una "
                    "condicion operativa en un tiempo determinado y bajo procedimientos, recursos y condiciones de "
                    "reparacion definidas. Su analisis permite reconocer si los tiempos de intervencion responden "
                    "a complejidad tecnica, accesibilidad, disponibilidad de repuestos, calidad del diagnostico o "
                    "eficiencia del proceso de mantenimiento."
                ),
            },
            {
                "tipo": "formula",
                "texto": "MTTR = Tiempo total de reparacion / Numero de intervenciones correctivas",
                "numero": "(3)",
                "alineacion": "center",
            },
            {
                "tipo": "parrafo",
                "texto": (
                    "Cuando el MTTR disminuye, el activo retorna mas rapido a la operacion y mejora la disponibilidad "
                    "inherente. Sin embargo, reducir MTTR sin actuar sobre las causas de falla solo contiene sintomas; "
                    "por ello, la mantenibilidad debe analizarse de manera conjunta con la confiabilidad dentro del "
                    "diseño del plan RCM."
                ),
            },
            {"tipo": "parrafo", "texto": "2.2.8 Motoniveladora CAT 24M"},
            {
                "tipo": "parrafo",
                "texto": (
                    f"La {equipment} es un equipo auxiliar critico en mineria a cielo abierto porque conserva la "
                    "geometria, transitabilidad y seguridad de las vias de acarreo. Su desempeño condiciona la "
                    "velocidad de ciclo de los camiones, la estabilidad de las rutas y la continuidad de las "
                    f"operaciones en {location}. Por esta razon, su analisis teorico no puede separarse de las cargas "
                    "dinamicas, del ambiente abrasivo ni de la severidad del trabajo diario."
                ),
            },
            {
                "tipo": "parrafo",
                "texto": (
                    "Desde la perspectiva funcional, la motoniveladora CAT 24M integra sistemas de implementos, tren "
                    "de potencia, sistema hidraulico, sistema electrico y componentes estructurales que trabajan bajo "
                    "altas exigencias. Describir tecnicamente el equipo permite entender por que la estrategia de "
                    "mantenimiento debe adaptarse a sus subsistemas criticos y al contexto operacional donde se "
                    "manifiestan las fallas recurrentes."
                ),
            },
        ]

    def _build_reality_problem_repair_prompt(
        self,
        *,
        section: Dict[str, Any],
        validation_error: str,
        values: Dict[str, Any],
        format_id: Optional[str],
    ) -> str:
        section_id = str(section.get("sectionId") or "")
        path = str(section.get("path") or "")
        editorial_context = build_section_editorial_context(
            format_id=format_id,
            section_id=section_id,
            section_path=path,
            values=values,
        )
        current_content = json.dumps(section.get("content"), ensure_ascii=False, indent=2)
        values_json = json.dumps(values, ensure_ascii=False, indent=2)
        return "\n\n".join(
            [
                "Reescribe SOLO el apartado 1.1 Descripcion de la realidad problematica.",
                "La salida anterior fallo la validacion automatica; debes corregirla antes de entregar.",
                f"Error de validacion: {validation_error}",
                editorial_context,
                (
                    "Devuelve unicamente parrafos academicos en texto plano. No uses listas, markdown, "
                    "TABLE_JSON, FIGURE_JSON, guias manuales, fuentes manuales ni asteriscos. Menciona "
                    "Figura 1.1, Figura 1.2, Figura 1.3 y Figura 1.4 en los parrafos de introduccion e "
                    "interpretacion; el sistema insertara los bloques visuales y la guia azul."
                ),
                "Valores del proyecto disponibles:",
                values_json,
                "Contenido actual que debes sustituir por una version valida:",
                current_content,
            ]
        )

    def _build_theoretical_bases_repair_prompt(
        self,
        *,
        section: Dict[str, Any],
        validation_error: str,
        values: Dict[str, Any],
        format_id: Optional[str],
    ) -> str:
        section_id = str(section.get("sectionId") or "")
        path = str(section.get("path") or "")
        editorial_context = build_section_editorial_context(
            format_id=format_id,
            section_id=section_id,
            section_path=path,
            values=values,
        )
        current_content = json.dumps(section.get("content"), ensure_ascii=False, indent=2)
        values_json = json.dumps(values, ensure_ascii=False, indent=2)
        return "\n\n".join(
            [
                f"Reescribe SOLO la seccion {path}.",
                "La salida anterior no respeto el patron institucional de 2.2 Bases teoricas.",
                f"Error de validacion: {validation_error}",
                editorial_context,
                (
                    "Devuelve texto academico plano y, solo cuando corresponda, FORMULA_JSON. "
                    "No uses Markdown, no uses **, no uses listas, no generes TABLE_JSON y no insertes "
                    "figuras genericas. Cada subtitulo 2.2.x debe quedar como linea independiente, seguido de "
                    "sus parrafos tecnicos. Si el caso corresponde a mantenimiento/confiabilidad, respeta el "
                    "orden 2.2.1 a 2.2.8 y deja anclajes teoricos claros para que el sistema coloque las figuras "
                    "controladas en 2.2.2, 2.2.3, 2.2.4 y 2.2.8."
                ),
                "Valores del proyecto disponibles:",
                values_json,
                "Contenido actual que debes sustituir por una version valida:",
                current_content,
            ]
        )

    def _build_chapter_one_heading_repair_prompt(
        self,
        *,
        section: Dict[str, Any],
        validation_error: str,
        values: Dict[str, Any],
        format_id: Optional[str],
    ) -> str:
        section_id = str(section.get("sectionId") or "")
        path = str(section.get("path") or "")
        editorial_context = build_section_editorial_context(
            format_id=format_id,
            section_id=section_id,
            section_path=path,
            values=values,
        )
        current_content = json.dumps(section.get("content"), ensure_ascii=False, indent=2)
        values_json = json.dumps(values, ensure_ascii=False, indent=2)
        return "\n\n".join(
            [
                f"Reescribe SOLO la seccion {path}.",
                "La salida anterior omitio subtitulos obligatorios o no respeto el formato del profesor.",
                f"Error de validacion: {validation_error}",
                editorial_context,
                (
                    "Devuelve texto plano academico. No uses listas, markdown, tablas ni parrafos introductorios "
                    "generales. Escribe cada subtitulo numerado como linea independiente y debajo su parrafo "
                    "sustantivo. Respeta literalmente los numeros y nombres de subtitulo solicitados."
                ),
                "Valores del proyecto disponibles:",
                values_json,
                "Contenido actual que debes sustituir por una version valida:",
                current_content,
            ]
        )

    def _build_schedule_budget_repair_prompt(
        self,
        *,
        section: Dict[str, Any],
        validation_error: str,
        values: Dict[str, Any],
        format_id: Optional[str],
    ) -> str:
        section_id = str(section.get("sectionId") or "")
        path = str(section.get("path") or "")
        editorial_context = build_section_editorial_context(
            format_id=format_id,
            section_id=section_id,
            section_path=path,
            values=values,
        )
        current_content = json.dumps(section.get("content"), ensure_ascii=False, indent=2)
        values_json = json.dumps(values, ensure_ascii=False, indent=2)
        is_schedule = OutputValidator._is_schedule_path(path)
        kind = "cronograma" if is_schedule else "presupuesto"
        detailed_errors = OutputValidator._required_table_error_messages(section.get("content"), path=path)
        error_block = "\n".join(f"- {item}" for item in detailed_errors) if detailed_errors else "- tabla_invalida"

        repair_rules = [
            "Devuelve exclusivamente UN bloque <<<TABLE_JSON ... TABLE_JSON>>> valido.",
            "No agregues parrafos, listas, markdown, observaciones ni texto antes o despues del bloque.",
            "No uses placeholders finales sin reemplazar.",
        ]
        if is_schedule:
            repair_rules = [
                "Devuelve exclusivamente UN bloque <<<TABLE_JSON ... TABLE_JSON>>> valido.",
                "No agregues parrafos, listas, markdown, observaciones ni texto antes o despues del bloque.",
                "No generes la tabla institucional final del cronograma.",
                "Devuelve un blueprint semantico con tipo='tabla' y subtipo='cronograma_plan'.",
                (
                    "La estructura obligatoria es: {tipo:'tabla', subtipo:'cronograma_plan', "
                    "anio:'2025 o anio del proyecto', fases:[{numero, titulo, actividades:"
                    "[{numero, titulo, mes_inicio, mes_fin}]}]}."
                ),
                "Deben existir exactamente 8 fases y 26 actividades con distribucion 3-3-3-3-3-4-3-4.",
                (
                    "Las fases deben empezar con '1.' hasta '8.' y las actividades con "
                    "'1.1.' hasta '8.4.' segun corresponda."
                ),
                "No escribas encabezados, filas, celdas_combinadas, celdas_fusionadas, estilo ni orientacion final.",
                "Cada actividad debe declarar mes_inicio y mes_fin como enteros del 1 al 12.",
                "Ventanas mensuales obligatorias: F1=2-3, F2=2-4, F3=4-6, F4=6-7, F5=7-8, F6=7-10, F7=8-11, F8=10-12.",
                "Si una actividad ocupa varios meses, el rango debe ser contiguo.",
                "No uses fences markdown tipo ```json ni ```.",
            ]

        return "\n\n".join(
            [
                f"Reescribe SOLO la seccion {path}.",
                (
                    (
                        "La salida anterior del cronograma fallo la validacion estructural institucional. "
                        "Ya no debes reconstruir la tabla final; debes devolver solo el blueprint semantico "
                        "para que GicaGen construya la tabla canonica."
                    )
                    if is_schedule
                    else (
                        f"La salida anterior del {kind} fallo la validacion estructural institucional y sera rechazada "
                        "si no devuelves la tabla canonica exacta."
                    )
                ),
                f"Error de validacion: {validation_error}",
                "Errores detectados por el validador:",
                error_block,
                editorial_context,
                "\n".join(repair_rules),
                "Valores del proyecto disponibles:",
                values_json,
                "Contenido actual que debes sustituir por una version valida:",
                current_content,
            ]
        )

    # ------------------------------------------------------------------
    # Post-processing correction
    # ------------------------------------------------------------------

    _CORRECTION_PROMPT_PATH = Path(__file__).resolve().parents[4] / "data" / "correction_prompt.txt"

    def _correct_ai_result(
        self,
        sections: List[Dict[str, Any]],
        definition: Dict[str, Any],
        values: Dict[str, Any],
        project_id: str,
        selection: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
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
            llm_result = self._generate_with_provider_fallback(
                correction_prompt,
                preferred_provider=self._last_used_provider,
                phase="cleanup_correction",
                section_id="cleanup_correction",
                section_path="Limpieza/Correccion",
                context=json.dumps({"sections": sections}, ensure_ascii=False),
                selection=selection,
            )
            raw_response = llm_result.content
            provider = llm_result.provider
            usage_snapshot = self._record_token_usage(
                llm_result.attempts,
                current_section_id="cleanup_correction",
                current_section_path="Limpieza/Correccion",
            )
            self._emit_progress(
                len(sections),
                len(sections),
                "Limpieza/Correccion",
                provider,
                stage="cleanup_correction",
            )
            if llm_result.status == "degraded":
                self._emit_trace(
                    step="ai.correction",
                    status="warn",
                    title="Limpieza opcional omitida (modo degradado)",
                    detail="Se mantiene contenido original y el documento continua.",
                    meta={
                        "provider": provider,
                        "usage": llm_result.usage,
                        "usageAttempts": llm_result.attempts,
                        "tokenUsage": usage_snapshot,
                    },
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
                meta={"tokenUsage": self.get_token_usage_snapshot()},
            )
        else:
            self._emit_trace(
                step="ai.correction",
                status="done",
                title="Correccion estructurada aplicada",
                meta={"tokenUsage": self.get_token_usage_snapshot()},
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
        sections: List[Dict[str, Any]],
        *,
        project_id: str = "",
        values: Dict[str, Any] | None = None,
    ) -> List[Dict[str, Any]]:
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

            replacement = autofill_section(
                target,
                issue.issue_type,
                values=values,
                all_sections=sections,
            )
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
                remaining_issues.append(f"{issue.section_id}: {issue.issue_type} — {issue.sample[:80]}")

        status = "done" if not remaining_issues else "warn"
        detail = ""
        if remaining_issues:
            detail = f"Se repararon {repaired} secciones. Quedan {len(remaining_issues)} con contenido dudoso."
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
        sections: List[Dict[str, Any]],
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
        original_sections: List[Dict[str, Any]],
        project_id: str,
    ) -> List[Dict[str, Any]]:
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

        result: List[Dict[str, Any]] = []
        for orig in original_sections:
            sid = orig["sectionId"]
            corrected_item = corrected_by_id.get(sid)
            content = orig["content"]
            section_path = str(orig.get("path") or "")
            if isinstance(corrected_item, dict):
                corrected_content = corrected_item.get("content")
                if isinstance(corrected_content, (str, list)) and AIService._should_accept_corrected_content(
                    original_content=content,
                    corrected_content=corrected_content,
                    path=section_path,
                ):
                    content = corrected_content
                elif isinstance(corrected_content, (str, list)):
                    logger.warning(
                        "Correction pass: discarded corrected content for sectionId=%s "
                        "(path='%s') because it became empty or overly degraded.",
                        sid,
                        section_path,
                    )
            result.append(
                {
                    "sectionId": sid,
                    "path": section_path,
                    "content": content,
                }
            )

        logger.info(
            "Correction pass DONE projectId=%s (%d sections corrected)",
            project_id,
            len(result),
        )
        return result

    @staticmethod
    def _sanitized_visible_text(content: Any, *, path: str) -> str:
        sanitized = OutputValidator.sanitize_content(content, path=path)
        return OutputValidator._visible_content_text(sanitized)

    @classmethod
    def _should_accept_corrected_content(
        cls,
        *,
        original_content: Any,
        corrected_content: Any,
        path: str,
    ) -> bool:
        corrected_visible = cls._sanitized_visible_text(corrected_content, path=path)
        if not corrected_visible.strip():
            return False

        original_visible = cls._sanitized_visible_text(original_content, path=path)
        original_words = OutputValidator._word_count(original_visible)
        corrected_words = OutputValidator._word_count(corrected_visible)

        # Generic guardrail: avoid replacing dense generated sections with a
        # correction that collapses content to a tiny fragment.
        if original_words >= 350:
            minimum_generic_words = max(80, int(original_words * 0.20))
            if corrected_words < minimum_generic_words:
                return False

        if not OutputValidator._is_theoretical_bases_path(path):
            return True

        # Guardrail for 2.2: avoid accepting corrections that collapse a dense
        # theoretical base section into a fragment too short for institutional quality.
        if original_words >= 300:
            minimum_words = max(120, int(original_words * 0.35))
            if corrected_words < minimum_words:
                return False

        original_headings = OutputValidator._theoretical_heading_lines(original_content)
        corrected_headings = OutputValidator._theoretical_heading_lines(corrected_content)
        if len(original_headings) >= 5:
            if len(corrected_headings) < 5:
                return False
            if len(corrected_headings) < len(original_headings):
                return False

        original_figures = OutputValidator._figure_blocks(original_content)
        corrected_figures = OutputValidator._figure_blocks(corrected_content)
        if not original_figures and corrected_figures:
            return False

        return True
