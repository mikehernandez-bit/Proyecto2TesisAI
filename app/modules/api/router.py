"""
API Router - BFF endpoints for frontend consumption.

Frontend calls `/api/*` only. GicaGen handles:
- Formats BFF + cache
- Prompt CRUD
- Project drafts/history
- AI generation via configured providers (Gemini/Mistral)
- n8n integration contracts/callback (DEPRECATED)
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response, StreamingResponse

from app.core.config import settings
from app.core.services.ai import AIService, QuotaExceededError
from app.core.services.ai.errors import GenerationCancelledError
from app.core.services.ai.token_usage import (
    empty_token_usage_report,
    normalize_token_usage_report,
    token_usage_snapshot,
)
from app.core.services.definition_compiler import compile_definition_to_section_index
from app.core.services.format_service import FormatService
from app.core.services.pricing import (
    PricingService,
    build_generation_cost_report,
    build_project_budget_report,
    empty_generation_cost_report,
    generation_cost_snapshot,
    normalize_generation_cost_report,
    normalize_generation_cost_snapshot,
)
from app.core.services.project_service import ProjectService
from app.core.services.prompt_service import PromptService
from app.core.utils.docx_builder import build_demo_docx
from app.integrations.gicatesis.errors import (
    GicaTesisError,
    UpstreamTimeout,
    UpstreamUnavailable,
)
from app.integrations.gicatesis.status import gicatesis_status
from app.integrations.gicatesis.types import RenderPayloadValidationError
from app.integrations.n8n.client import N8NClient
from app.integrations.n8n.service import N8NIntegrationService
from app.modules.api.models import (
    N8NCallbackIn,
    ProjectDraftIn,
    ProjectGenerateIn,
    ProjectGenerateTriggerIn,
    ProjectUpdateIn,
    PromptIn,
    ProviderSelectIn,
)
from app.modules.api.payload_helpers import (
    adapt_ai_result_for_gicatesis as _adapt_ai_result_for_gicatesis,
)
from app.modules.api.payload_helpers import (
    build_render_payload as _build_render_payload,
)
from app.modules.api.payload_helpers import (
    build_sim_sections as _build_sim_sections,
)
from app.modules.api.payload_helpers import (
    decide_resume_mode as _decide_resume_mode,
)
from app.modules.api.payload_helpers import (
    extract_resume_seed_sections as _extract_resume_seed_sections,
)
from app.modules.api.payload_helpers import (
    extract_upstream_detail as _extract_upstream_detail,
)
from app.modules.api.payload_helpers import (
    gicatesis_unavailable_detail as _gicatesis_unavailable_detail,
)
from app.modules.api.payload_helpers import (
    values_with_title as _values_with_title,
)
from app.modules.api.trace_helpers import (
    emit_project_trace as _emit_project_trace_raw,
)
from app.modules.api.trace_helpers import (
    git_commit as _git_commit,
)
from app.modules.api.trace_helpers import (
    utc_now_z as _utc_now_z,
)

_logger = logging.getLogger(__name__)

router = APIRouter()

# Service instances
formats = FormatService()
prompts = PromptService()
projects = ProjectService()
n8n = N8NClient()
n8n_specs = N8NIntegrationService()
ai_service = AIService()
pricing_service = PricingService()
STARTED_AT = dt.datetime.now(dt.timezone.utc).isoformat()
TRACE_MAX_PREVIEW_CHARS = 520
TRACE_TERMINAL_STATUSES = {
    "completed",
    "failed",
    "render_failed",
    "blocked",
    "cancel_requested",
    "n8n_failed",
    "ai_failed",
    "generation_failed",
}


def _emit_project_trace(
    project_id: str,
    *,
    step: str,
    status: str,
    title: str,
    detail: str = "",
    meta: Optional[Dict[str, Any]] = None,
    preview: Optional[Dict[str, Any]] = None,
) -> None:
    """Wrapper local para inyectar la dependencia de 'projects' al helper de trace."""
    _emit_project_trace_raw(
        project_id,
        step=step,
        status=status,
        title=title,
        detail=detail,
        meta=meta,
        preview=preview,
        projects=projects,
    )


class RenderStageError(RuntimeError):
    """Raised when the render stage fails after AI content is already available."""

    def __init__(self, detail: Any, *, status_code: int = 500) -> None:
        self.detail_payload = detail
        self.status_code = int(status_code or 500)
        super().__init__(self.detail_text)

    @property
    def detail_text(self) -> str:
        detail = self.detail_payload
        if isinstance(detail, str):
            return detail
        try:
            return json.dumps(detail, ensure_ascii=False)
        except Exception:
            return str(detail)


def _build_payload_preview(format_id: str, values: dict[str, Any], sections_count: int) -> dict[str, Any]:
    return {
        "formatId": format_id,
        "valuesKeys": sorted(list(values.keys())),
        "sections": sections_count,
        "mode": "simulation",
    }


def _build_generation_snapshot(
    *,
    sections: list[Dict[str, Any]] | None,
    total_sections: int = 0,
    current_path: str = "",
    token_usage_snapshot_data: Optional[Dict[str, Any]] = None,
    cost_usage_snapshot_data: Optional[Dict[str, Any]] = None,
    run_id: str = "",
    status: str = "idle",
) -> Dict[str, Any]:
    completed_sections: list[Dict[str, str]] = []
    for item in sections or []:
        if not isinstance(item, dict):
            continue
        section_id = str(item.get("sectionId") or item.get("section_id") or "").strip()
        path = str(item.get("path") or item.get("section_path") or "").strip()
        if not section_id and not path:
            continue
        completed_sections.append({"sectionId": section_id, "path": path})

    snapshot_current_path = str(current_path or "").strip() or (
        str(completed_sections[-1]["path"]).strip() if completed_sections else ""
    )
    return {
        "saved_sections_count": len(completed_sections),
        "total_sections": max(0, int(total_sections or 0)),
        "current_path": snapshot_current_path,
        "completed_sections": completed_sections,
        "tokenUsage": token_usage_snapshot_data or token_usage_snapshot(empty_token_usage_report()),
        "costUsage": cost_usage_snapshot_data or generation_cost_snapshot(empty_generation_cost_report()),
        "source_run_id": str(run_id or "").strip(),
        "status": str(status or "idle").strip() or "idle",
        "updated_at": _utc_now_z(),
    }


_CONSTRUCTION_TASK_SPECS = (
    ("handoff", "Contenido IA validado"),
    ("payload", "Payload a GicaTesis"),
    ("render_docx", "Render DOCX"),
    ("render_pdf", "Render PDF"),
    ("final_validation", "Validacion final"),
)


def _empty_generation_phase(*, total_sections: int = 0) -> Dict[str, Any]:
    return {
        "status": "idle",
        "base_prompt": "",
        "current_section_id": "",
        "current_section_path": "",
        "total_sections": max(0, int(total_sections or 0)),
        "completed_sections": 0,
        "planned_sections": [],
        "sections": [],
        "cost_summary": generation_cost_snapshot(empty_generation_cost_report()),
        "started_at": "",
        "updated_at": "",
        "finished_at": "",
    }


def _default_construction_tasks() -> list[Dict[str, Any]]:
    return [
        {
            "id": task_id,
            "label": label,
            "status": "pending",
            "detail": "Pendiente",
            "updated_at": "",
        }
        for task_id, label in _CONSTRUCTION_TASK_SPECS
    ]


def _empty_construction_phase() -> Dict[str, Any]:
    return {
        "status": "idle",
        "current_task": "",
        "tasks": _default_construction_tasks(),
        "started_at": "",
        "updated_at": "",
        "finished_at": "",
    }


def _normalize_generation_phase_state(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return _empty_generation_phase()
    base = _empty_generation_phase(total_sections=int(raw.get("total_sections") or 0))
    base.update(
        {
            "status": str(raw.get("status") or "idle"),
            "base_prompt": str(raw.get("base_prompt") or ""),
            "current_section_id": str(raw.get("current_section_id") or ""),
            "current_section_path": str(raw.get("current_section_path") or ""),
            "total_sections": max(0, int(raw.get("total_sections") or 0)),
            "completed_sections": max(0, int(raw.get("completed_sections") or 0)),
            "cost_summary": normalize_generation_cost_snapshot(raw.get("cost_summary")),
            "started_at": str(raw.get("started_at") or ""),
            "updated_at": str(raw.get("updated_at") or ""),
            "finished_at": str(raw.get("finished_at") or ""),
        }
    )
    planned = raw.get("planned_sections")
    if isinstance(planned, list):
        base["planned_sections"] = [item for item in planned if isinstance(item, dict)]
    sections = raw.get("sections")
    if isinstance(sections, list):
        base["sections"] = [item for item in sections if isinstance(item, dict)]
    return base


def _normalize_construction_phase_state(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return _empty_construction_phase()
    base = _empty_construction_phase()
    base.update(
        {
            "status": str(raw.get("status") or "idle"),
            "current_task": str(raw.get("current_task") or ""),
            "started_at": str(raw.get("started_at") or ""),
            "updated_at": str(raw.get("updated_at") or ""),
            "finished_at": str(raw.get("finished_at") or ""),
        }
    )
    tasks_by_id = {task["id"]: dict(task) for task in _default_construction_tasks()}
    raw_tasks = raw.get("tasks")
    if isinstance(raw_tasks, list):
        for item in raw_tasks:
            if not isinstance(item, dict):
                continue
            task_id = str(item.get("id") or "").strip()
            if not task_id:
                continue
            current = tasks_by_id.get(task_id, {"id": task_id, "label": task_id, "status": "pending", "detail": ""})
            current.update(
                {
                    "label": str(item.get("label") or current.get("label") or task_id),
                    "status": str(item.get("status") or current.get("status") or "pending"),
                    "detail": str(item.get("detail") or current.get("detail") or ""),
                    "updated_at": str(item.get("updated_at") or current.get("updated_at") or ""),
                }
            )
            tasks_by_id[task_id] = current
    base["tasks"] = list(tasks_by_id.values())
    return base


def _section_title_from_path(path: str) -> str:
    parts = [part.strip() for part in str(path or "").split("/") if part.strip()]
    return parts[-1] if parts else ""


def _section_parent_path(path: str) -> str:
    parts = [part.strip() for part in str(path or "").split("/") if part.strip()]
    if len(parts) <= 1:
        return ""
    return "/".join(parts[:-1])


def _section_level_from_path(path: str) -> int:
    parts = [part.strip() for part in str(path or "").split("/") if part.strip()]
    return max(1, len(parts))


def _usage_source_label(attempts: list[Dict[str, Any]]) -> str:
    if not attempts:
        return ""
    estimated = sum(1 for item in attempts if bool(item.get("estimated")))
    reported = sum(1 for item in attempts if not bool(item.get("estimated")))
    if estimated and reported:
        return "mixed"
    if estimated:
        return "estimated"
    return "reported_by_provider"


def _aggregate_attempt_usage(attempts: list[Dict[str, Any]]) -> Dict[str, Any]:
    safe_attempts = [item for item in attempts if isinstance(item, dict)]
    return {
        "input_tokens": sum(int(item.get("input_tokens") or 0) for item in safe_attempts),
        "output_tokens": sum(int(item.get("output_tokens") or 0) for item in safe_attempts),
        "total_tokens": sum(int(item.get("total_tokens") or 0) for item in safe_attempts),
        "estimated": any(bool(item.get("estimated")) for item in safe_attempts),
        "source": _usage_source_label(safe_attempts),
        "attempt_count": len(safe_attempts),
        "provider": str((safe_attempts[-1].get("provider") if safe_attempts else "") or ""),
        "model": str((safe_attempts[-1].get("model") if safe_attempts else "") or ""),
    }


def _apply_generation_costs_to_phase(
    phase: Dict[str, Any],
    cost_report: Dict[str, Any],
) -> Dict[str, Any]:
    normalized = _normalize_generation_phase_state(phase)
    normalized["cost_summary"] = normalize_generation_cost_snapshot(cost_report)
    section_costs = (
        {
            (str(item.get("section_id") or "").strip() or str(item.get("section_path") or "").strip()): item
            for item in cost_report.get("sections", [])
            if isinstance(item, dict)
        }
        if isinstance(cost_report, dict)
        else {}
    )

    updated_sections: list[Dict[str, Any]] = []
    for item in normalized.get("sections") or []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("section_id") or "").strip() or str(item.get("section_path") or "").strip()
        cost_entry = section_costs.get(key, {})
        updated = dict(item)
        updated["estimated_cost_usd"] = float(
            cost_entry.get("estimated_cost_usd") or item.get("estimated_cost_usd") or 0.0
        )
        updated["pricing_source"] = str(cost_entry.get("pricing_source") or item.get("pricing_source") or "unavailable")
        updated["pricing_fetched_at"] = str(
            cost_entry.get("pricing_fetched_at") or item.get("pricing_fetched_at") or ""
        )
        updated["currency"] = str(cost_entry.get("currency") or item.get("currency") or "USD")
        updated["pricing_available"] = bool(
            cost_entry.get("available") if "available" in cost_entry else item.get("pricing_available")
        )
        updated_sections.append(updated)
    normalized["sections"] = updated_sections
    return normalized


def _upsert_generation_section(
    phase: Dict[str, Any],
    section_payload: Dict[str, Any],
) -> Dict[str, Any]:
    normalized = _normalize_generation_phase_state(phase)
    sections = list(normalized.get("sections") or [])
    section_id = str(section_payload.get("section_id") or "").strip()
    section_path = str(section_payload.get("section_path") or "").strip()
    key = section_id or section_path
    if not key:
        return normalized

    now = _utc_now_z()
    merged_payload = dict(section_payload)
    attempts = merged_payload.get("attempts")
    attempts = [item for item in attempts if isinstance(item, dict)] if isinstance(attempts, list) else []
    if attempts:
        aggregate = _aggregate_attempt_usage(attempts)
        merged_payload.setdefault("input_tokens", aggregate["input_tokens"])
        merged_payload.setdefault("output_tokens", aggregate["output_tokens"])
        merged_payload.setdefault("total_tokens", aggregate["total_tokens"])
        merged_payload.setdefault("estimated", aggregate["estimated"])
        merged_payload.setdefault("source", aggregate["source"])
        merged_payload.setdefault("attempt_count", aggregate["attempt_count"])
        merged_payload.setdefault("provider", aggregate["provider"])
        merged_payload.setdefault("model", aggregate["model"])

    idx = next(
        (
            index
            for index, item in enumerate(sections)
            if key == (str(item.get("section_id") or "").strip() or str(item.get("section_path") or "").strip())
        ),
        -1,
    )
    current = sections[idx] if idx >= 0 else {}
    started_at = str(current.get("started_at") or merged_payload.get("started_at") or now)
    completed_at = (
        now
        if str(merged_payload.get("status") or "").lower().strip() in {"ok", "error"}
        else str(current.get("completed_at") or "")
    )
    updated = {
        "section_id": section_id or str(current.get("section_id") or ""),
        "section_path": section_path or str(current.get("section_path") or ""),
        "section_title": str(
            merged_payload.get("section_title")
            or current.get("section_title")
            or _section_title_from_path(section_path or current.get("section_path") or "")
        ),
        "parent_section_path": str(
            merged_payload.get("parent_section_path")
            or current.get("parent_section_path")
            or _section_parent_path(section_path or current.get("section_path") or "")
        ),
        "section_level": int(
            merged_payload.get("section_level")
            or current.get("section_level")
            or _section_level_from_path(section_path or current.get("section_path") or "")
        ),
        "prompt_sent": str(merged_payload.get("prompt_sent") or current.get("prompt_sent") or ""),
        "ai_output": str(merged_payload.get("ai_output") or current.get("ai_output") or ""),
        "input_tokens": int(merged_payload.get("input_tokens") or current.get("input_tokens") or 0),
        "output_tokens": int(merged_payload.get("output_tokens") or current.get("output_tokens") or 0),
        "total_tokens": int(merged_payload.get("total_tokens") or current.get("total_tokens") or 0),
        "estimated_cost_usd": float(
            merged_payload.get("estimated_cost_usd") or current.get("estimated_cost_usd") or 0.0
        ),
        "pricing_source": str(merged_payload.get("pricing_source") or current.get("pricing_source") or "unavailable"),
        "pricing_fetched_at": str(merged_payload.get("pricing_fetched_at") or current.get("pricing_fetched_at") or ""),
        "currency": str(merged_payload.get("currency") or current.get("currency") or "USD"),
        "pricing_available": bool(
            merged_payload.get("pricing_available")
            if "pricing_available" in merged_payload
            else current.get("pricing_available")
        ),
        "model": str(merged_payload.get("model") or current.get("model") or ""),
        "provider": str(merged_payload.get("provider") or current.get("provider") or ""),
        "status": str(merged_payload.get("status") or current.get("status") or "pending"),
        "duration_ms": int(merged_payload.get("duration_ms") or current.get("duration_ms") or 0),
        "estimated": bool(
            merged_payload.get("estimated") if "estimated" in merged_payload else current.get("estimated")
        ),
        "source": str(merged_payload.get("source") or current.get("source") or ""),
        "attempt_count": int(merged_payload.get("attempt_count") or current.get("attempt_count") or len(attempts)),
        "attempts": attempts or list(current.get("attempts") or []),
        "error": str(merged_payload.get("error") or current.get("error") or ""),
        "started_at": started_at,
        "completed_at": completed_at,
        "updated_at": now,
    }
    if idx >= 0:
        sections[idx] = updated
    else:
        sections.append(updated)
    normalized["sections"] = sections
    normalized["current_section_id"] = updated["section_id"]
    normalized["current_section_path"] = updated["section_path"]
    normalized["completed_sections"] = sum(1 for item in sections if str(item.get("status") or "").lower() == "ok")
    normalized["updated_at"] = now
    if not normalized.get("started_at"):
        normalized["started_at"] = now
    if str(updated["status"]).lower() == "ok":
        normalized["status"] = "running"
    elif str(updated["status"]).lower() == "error":
        normalized["status"] = "failed"
    return normalized


def _update_generation_phase_for_event(project_id: str, event: Dict[str, Any]) -> None:
    project = projects.get_project(project_id)
    if not project:
        return
    phase = _normalize_generation_phase_state(project.get("generation_phase"))
    meta = event.get("meta") if isinstance(event.get("meta"), dict) else {}
    preview = event.get("preview") if isinstance(event.get("preview"), dict) else {}
    step = str(event.get("step") or "")
    status = str(event.get("status") or "")
    now = _utc_now_z()

    if step == "prompt.base":
        phase["base_prompt"] = str(preview.get("prompt") or phase.get("base_prompt") or "")
        phase["status"] = "running"
        phase["updated_at"] = now
        if not phase.get("started_at"):
            phase["started_at"] = now
    elif step == "format.section_index":
        phase["total_sections"] = max(0, int(meta.get("sectionTotal") or phase.get("total_sections") or 0))
        outline = meta.get("sectionOutline")
        if isinstance(outline, list):
            phase["planned_sections"] = [
                {
                    "section_id": str(item.get("sectionId") or ""),
                    "section_path": str(item.get("sectionPath") or ""),
                    "section_title": _section_title_from_path(str(item.get("sectionPath") or "")),
                    "parent_section_path": str(
                        item.get("sectionParentPath") or _section_parent_path(str(item.get("sectionPath") or ""))
                    ),
                    "section_level": int(
                        item.get("sectionLevel") or _section_level_from_path(str(item.get("sectionPath") or ""))
                    ),
                }
                for item in outline
                if isinstance(item, dict) and (item.get("sectionId") or item.get("sectionPath"))
            ]
        phase["updated_at"] = now
    elif step == "ai.generate.section":
        section_payload = {
            "section_id": str(meta.get("sectionId") or ""),
            "section_path": str(meta.get("sectionPath") or ""),
            "section_title": _section_title_from_path(str(meta.get("sectionPath") or "")),
            "parent_section_path": str(
                meta.get("sectionParentPath") or _section_parent_path(str(meta.get("sectionPath") or ""))
            ),
            "section_level": int(
                meta.get("sectionLevel") or _section_level_from_path(str(meta.get("sectionPath") or ""))
            ),
            "prompt_sent": str(preview.get("prompt") or ""),
            "ai_output": str(preview.get("raw") or ""),
            "model": str(meta.get("model") or ""),
            "provider": str(meta.get("provider") or ""),
            "duration_ms": int(meta.get("durationMs") or 0),
            "attempts": meta.get("usageAttempts") if isinstance(meta.get("usageAttempts"), list) else [],
            "error": str(event.get("detail") or ""),
            "status": "pending",
        }
        if status == "running":
            section_payload["status"] = "generating"
        elif status == "done":
            section_payload["status"] = "ok"
        elif status == "error":
            section_payload["status"] = "error"
        phase = _upsert_generation_section(phase, section_payload)
    elif step == "ai.generate.done":
        phase["status"] = "completed"
        phase["finished_at"] = now
        phase["updated_at"] = now
    elif step == "generation.job" and status == "error":
        phase["status"] = "failed"
        phase["updated_at"] = now
    elif step == "generation.job" and status == "warn":
        phase["status"] = "blocked"
        phase["updated_at"] = now

    projects.update_project(project_id, {"generation_phase": phase})


def _set_construction_task(
    project_id: str,
    task_id: str,
    *,
    status: str,
    detail: str = "",
    global_status: str = "",
    finish: bool = False,
) -> None:
    project = projects.get_project(project_id)
    if not project:
        return
    phase = _normalize_construction_phase_state(project.get("construction_phase"))
    now = _utc_now_z()
    tasks = []
    for task in phase.get("tasks") or []:
        if str(task.get("id") or "") == task_id:
            tasks.append(
                {
                    "id": task_id,
                    "label": str(task.get("label") or task_id),
                    "status": status,
                    "detail": detail or str(task.get("detail") or ""),
                    "updated_at": now,
                }
            )
        else:
            tasks.append(task)
    phase["tasks"] = tasks
    phase["current_task"] = task_id if status == "running" else phase.get("current_task") or ""
    phase["updated_at"] = now
    if not phase.get("started_at") and status in {"running", "done", "error"}:
        phase["started_at"] = now
    if global_status:
        phase["status"] = global_status
    elif status == "error":
        phase["status"] = "error"
    elif any(str(task.get("status") or "") == "running" for task in tasks):
        phase["status"] = "running"
    elif all(str(task.get("status") or "") == "done" for task in tasks):
        phase["status"] = "completed"
    elif any(str(task.get("status") or "") == "done" for task in tasks):
        phase["status"] = "running"
    if finish:
        phase["finished_at"] = now
        if phase["status"] == "running":
            phase["status"] = "completed"
    projects.update_project(project_id, {"construction_phase": phase})


def _render_project_outputs_sync(
    project_id: str,
    *,
    format_id: str,
    values: dict[str, Any],
    ai_result_raw: dict[str, Any],
) -> tuple[Path, Path]:
    _set_construction_task(
        project_id,
        "payload",
        status="running",
        detail="Preparando y validando payload antes de enviar a GicaTesis.",
        global_status="running",
    )
    ai_payload = _adapt_ai_result_for_gicatesis(ai_result_raw)
    ai_sections = ai_payload.get("sections", [])
    sections_count = len(ai_sections)
    payload_preview = _build_payload_preview(format_id, values, sections_count)

    _emit_project_trace(
        project_id,
        step="gicatesis.payload",
        status="running",
        title="Enviando payload a GicaTesis",
        detail=f"Secciones preparadas: {sections_count}.",
        meta={
            "formatId": format_id,
            "sections": sections_count,
            "stage": "section_done",
        },
        preview={"payload": json.dumps(payload_preview, ensure_ascii=False)},
    )

    try:
        payload = _build_render_payload(
            format_id=format_id,
            values=values,
            ai_result_raw=ai_result_raw,
        )
    except RenderPayloadValidationError as exc:
        _set_construction_task(
            project_id,
            "payload",
            status="error",
            detail="El payload no paso la validacion previa a GicaTesis.",
            global_status="error",
        )
        _emit_project_trace(
            project_id,
            step="gicatesis.payload",
            status="error",
            title="Payload invalido antes de enviar a GicaTesis",
            detail=json.dumps(exc.errors, ensure_ascii=False),
            meta={"stage": "failed", "statusCode": 422},
        )
        raise RenderStageError(exc.errors, status_code=422) from exc

    base_url = settings.GICATESIS_BASE_URL.rstrip("/")
    headers: Dict[str, str] = {}
    if settings.GICATESIS_API_KEY:
        headers["X-GICATESIS-KEY"] = settings.GICATESIS_API_KEY

    out_dir = Path("outputs")
    out_dir.mkdir(parents=True, exist_ok=True)
    docx_path = out_dir / f"{project_id}.docx"
    pdf_path = out_dir / f"{project_id}.pdf"

    with httpx.Client(timeout=240.0) as client:
        _set_construction_task(
            project_id,
            "payload",
            status="done",
            detail="Payload validado y enviado a GicaTesis.",
            global_status="running",
        )
        _set_construction_task(
            project_id,
            "render_docx",
            status="running",
            detail="Construyendo DOCX final.",
            global_status="running",
        )
        _emit_project_trace(
            project_id,
            step="gicatesis.render.docx",
            status="running",
            title="Render DOCX en proceso",
        )
        try:
            docx_response = client.post(f"{base_url}/render/docx", json=payload, headers=headers)
            docx_response.raise_for_status()
            docx_path.write_bytes(docx_response.content)
        except httpx.HTTPStatusError as exc:
            detail = _extract_upstream_detail(exc.response, "GicaTesis render/docx failed")
            _set_construction_task(
                project_id,
                "render_docx",
                status="error",
                detail=detail,
                global_status="error",
            )
            _emit_project_trace(
                project_id,
                step="gicatesis.render.docx",
                status="error",
                title="Render DOCX fallido",
                detail=detail,
            )
            raise RenderStageError(detail, status_code=exc.response.status_code) from exc

        _set_construction_task(
            project_id,
            "render_docx",
            status="done",
            detail=f"Archivo {docx_path.name} generado.",
            global_status="running",
        )
        _set_construction_task(
            project_id,
            "render_pdf",
            status="running",
            detail="Construyendo PDF final.",
            global_status="running",
        )
        _emit_project_trace(
            project_id,
            step="gicatesis.render.docx",
            status="done",
            title="DOCX listo",
            detail=f"Archivo: {docx_path.name}",
        )

        _emit_project_trace(
            project_id,
            step="gicatesis.render.pdf",
            status="running",
            title="Render PDF en proceso",
        )
        try:
            pdf_response = client.post(f"{base_url}/render/pdf", json=payload, headers=headers)
            pdf_response.raise_for_status()
            pdf_path.write_bytes(pdf_response.content)
        except httpx.HTTPStatusError as exc:
            detail = _extract_upstream_detail(exc.response, "GicaTesis render/pdf failed")
            _set_construction_task(
                project_id,
                "render_pdf",
                status="error",
                detail=detail,
                global_status="error",
            )
            _emit_project_trace(
                project_id,
                step="gicatesis.render.pdf",
                status="error",
                title="Render PDF fallido",
                detail=detail,
            )
            raise RenderStageError(detail, status_code=exc.response.status_code) from exc

    _set_construction_task(
        project_id,
        "render_pdf",
        status="done",
        detail=f"Archivo {pdf_path.name} generado.",
        global_status="running",
    )
    _emit_project_trace(
        project_id,
        step="gicatesis.payload",
        status="done",
        title="Payload procesado por GicaTesis",
    )
    _emit_project_trace(
        project_id,
        step="gicatesis.render.pdf",
        status="done",
        title="PDF listo",
        detail=f"Archivo: {pdf_path.name}",
    )
    return docx_path, pdf_path


# =============================================================================
# FORMATS BFF ENDPOINTS
# =============================================================================


@router.get("/formats/version")
async def get_formats_version():
    """Return catalog version status from GicaTesis with cache metadata."""
    try:
        return await formats.check_version()
    except UpstreamUnavailable:
        raise HTTPException(
            status_code=503,
            detail=_gicatesis_unavailable_detail("Version de formatos no disponible"),
        )
    except UpstreamTimeout:
        raise HTTPException(
            status_code=503,
            detail=_gicatesis_unavailable_detail("Timeout consultando version de formatos"),
        )
    except GicaTesisError as e:
        raise HTTPException(
            status_code=503,
            detail=_gicatesis_unavailable_detail(f"Error de GicaTesis: {e}"),
        )


@router.get("/formats")
async def list_formats(
    university: Optional[str] = None,
    category: Optional[str] = None,
    documentType: Optional[str] = None,
):
    """List formats via BFF, using cache+ETag and optional filters."""
    try:
        result = await formats.list_formats(
            university=university,
            category=category,
            document_type=documentType,
        )
    except UpstreamUnavailable:
        raise HTTPException(
            status_code=503,
            detail=_gicatesis_unavailable_detail("Catalogo no disponible (sin cache utilizable)"),
        )
    except GicaTesisError as e:
        raise HTTPException(
            status_code=503,
            detail=_gicatesis_unavailable_detail(f"Error de GicaTesis: {e}"),
        )

    is_stale = result.get("stale", False)
    source = result.get("source", "cache")
    upstream_online = gicatesis_status.online

    # Policy B (strict): reject stale cache when configured
    if is_stale and settings.GICAGEN_STRICT_GICATESIS:
        raise HTTPException(
            status_code=503,
            detail=_gicatesis_unavailable_detail("GicaTesis no disponible (modo estricto activado)"),
        )

    # Policy A (default): return 200 with metadata headers
    return Response(
        content=json.dumps(result, default=str, ensure_ascii=False),
        media_type="application/json",
        headers={
            "X-Data-Source": source,
            "X-Upstream-Online": str(upstream_online).lower(),
        },
    )


@router.get("/formats/{format_id}")
async def get_format_detail(format_id: str):
    """Get full format detail from BFF/cache."""
    try:
        detail = await formats.get_format_detail(format_id)
        if not detail:
            raise HTTPException(status_code=404, detail=f"Formato no encontrado: {format_id}")
        return detail
    except UpstreamUnavailable:
        raise HTTPException(
            status_code=503,
            detail=_gicatesis_unavailable_detail("Detalle de formato no disponible"),
        )
    except UpstreamTimeout:
        raise HTTPException(
            status_code=503,
            detail=_gicatesis_unavailable_detail("Timeout consultando detalle de formato"),
        )
    except GicaTesisError as e:
        raise HTTPException(
            status_code=503,
            detail=_gicatesis_unavailable_detail(f"Error de GicaTesis: {e}"),
        )


@router.get("/assets/{path:path}")
async def proxy_asset(path: str):
    """Proxy for GicaTesis assets (logos, images) to avoid direct frontend calls."""
    # Short-circuit when upstream is known offline â€” avoids timeout waste.
    if not gicatesis_status.online:
        raise HTTPException(
            status_code=503,
            detail="GicaTesis offline â€” asset no disponible.",
        )

    url = f"{settings.GICATESIS_BASE_URL}/assets/{path}"
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(url)
    except httpx.RequestError:
        gicatesis_status.record_failure("asset proxy connection error")
        raise HTTPException(
            status_code=503,
            detail="GicaTesis no disponible â€” no se pudo obtener el asset.",
        )

    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail="Asset not found")
    if resp.status_code >= 400:
        raise HTTPException(
            status_code=503,
            detail=f"GicaTesis respondiÃ³ {resp.status_code} para el asset solicitado.",
        )

    return Response(content=resp.content, media_type=resp.headers.get("content-type"))


@router.get("/_meta/build")
def build_info():
    """Expose runtime metadata to confirm active backend instance."""
    return {
        "service": "gicagen",
        "cwd": str(Path.cwd()),
        "started_at": STARTED_AT,
        "git_commit": _git_commit(),
    }


@router.get("/gicatesis/status")
def gicatesis_upstream_status():
    """Return GicaTesis upstream connectivity state."""
    return gicatesis_status.to_dict()


# =============================================================================
# AI / GENERATION
# =============================================================================


@router.get("/ai/health")
def ai_health():
    """Check AI generation configuration status."""
    return ai_service.health_payload()


@router.get("/ai/metrics")
def ai_metrics():
    """Lightweight resilience metrics snapshot (in-memory counters)."""
    return ai_service.resilience_metrics_payload()


@router.get("/providers/status")
def providers_status(projectId: Optional[str] = Query(None)):
    """Return provider/model selection plus runtime health metrics."""
    selection_override: Optional[Dict[str, Any]] = None
    if projectId:
        project = projects.get_project(projectId)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        project_selection = project.get("ai_selection")
        if isinstance(project_selection, dict):
            selection_override = project_selection

    payload = ai_service.providers_status_payload(selection_override=selection_override)
    if projectId:
        payload["projectId"] = projectId
    payload["gicatesis"] = gicatesis_status.to_dict()
    return payload


@router.post("/providers/probe")
def providers_probe(projectId: Optional[str] = Query(None)):
    """Run real provider probes (minimal requests) and return refreshed status."""
    selection_override: Optional[Dict[str, Any]] = None
    if projectId:
        project = projects.get_project(projectId)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        project_selection = project.get("ai_selection")
        if isinstance(project_selection, dict):
            selection_override = project_selection

    payload = ai_service.probe_providers(selection_override=selection_override)
    if projectId:
        payload["projectId"] = projectId
    return payload


@router.post("/providers/select")
def providers_select(payload: ProviderSelectIn, projectId: Optional[str] = Query(None)):
    """Persist provider/model selection used by AI generation."""
    raw = payload.model_dump(exclude_none=True)
    target_project_id = projectId or raw.pop("project_id", None)
    if target_project_id:
        project = projects.get_project(str(target_project_id))
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        selected = ai_service.normalize_provider_selection(raw)
        projects.update_project(str(target_project_id), {"ai_selection": selected})
        status_payload = ai_service.providers_status_payload(selection_override=selected)
        status_payload["projectId"] = str(target_project_id)
    else:
        selected = ai_service.set_provider_selection(raw)
        status_payload = ai_service.providers_status_payload()

    # Echo normalized selection explicitly in this endpoint response so UI/tests
    # can confirm what was saved, independent from runtime health filtering.
    status_payload["selected_provider"] = selected.get("provider") or status_payload.get("selected_provider", "")
    status_payload["selected_model"] = selected.get("model") or status_payload.get("selected_model", "")
    status_payload["fallback_provider"] = selected.get("fallback_provider") or ""
    status_payload["fallback_model"] = selected.get("fallback_model") or ""
    status_payload["mode"] = selected.get("mode") or status_payload.get("mode", "auto")
    status_payload["selection"] = selected
    return status_payload


# =============================================================================
# N8N INTEGRATION CONTRACTS (DEPRECATED â€” use Gemini via /ai/health)
# =============================================================================


@router.get("/integrations/n8n/health")
async def n8n_health():
    """DEPRECATED â€” Check n8n webhook connectivity."""
    return await n8n.ping()


@router.get("/integrations/n8n/spec")
async def get_n8n_spec(projectId: str):
    """
    Build integration guide/spec for wizard step 4.

    Returns summary, env checks, payload, headers, checklist and markdown export text.
    """
    project = projects.get_project(projectId)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    format_detail_payload: Optional[Dict[str, Any]] = None
    format_id = project.get("format_id")
    if format_id:
        detail = await formats.get_format_detail(format_id)
        if detail is not None:
            # Accept both pydantic model and plain dict objects.
            if hasattr(detail, "model_dump"):
                format_detail_payload = detail.model_dump()
            else:
                format_detail_payload = detail

    prompt = prompts.get_prompt(project.get("prompt_id")) if project.get("prompt_id") else None

    return n8n_specs.build_spec(
        project=project,
        format_detail=format_detail_payload,
        prompt=prompt,
    )


@router.post("/integrations/n8n/callback")
def n8n_callback_contract(
    payload: N8NCallbackIn,
    x_n8n_secret: Optional[str] = Header(None, alias="X-N8N-SECRET"),
):
    """
    Callback stub for n8n -> GicaGen.

    Validates shared secret and stores AI result in project state.
    """
    if settings.N8N_SHARED_SECRET and x_n8n_secret != settings.N8N_SHARED_SECRET:
        raise HTTPException(status_code=401, detail="Secret invalido")

    updated = projects.mark_ai_received(
        payload.projectId,
        payload.aiResult,
        run_id=payload.runId,
        artifacts=payload.artifacts,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Project not found")

    _emit_project_trace(
        payload.projectId,
        step="project.status.ai_received",
        status="done",
        title="Callback n8n recibido",
        meta={"runId": payload.runId},
    )

    return {
        "ok": True,
        "status": "ai_received",
        "projectId": payload.projectId,
        "project": updated,
    }


@router.post("/sim/n8n/run")
async def run_n8n_simulation(projectId: str = Query(..., description="Project id to simulate")):
    """
    Execute n8n simulation contract output (no local document generation).

    n8n simulated output only returns aiResult by path/sectionId.
    Artifact rendering remains proxied to GicaTesis at download time.
    """
    project = projects.get_project(projectId)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    format_id = project.get("format_id")
    if not format_id:
        raise HTTPException(status_code=400, detail="Project has no format_id")

    # Build section index from real format definition
    format_detail_payload: Optional[Dict[str, Any]] = None
    if format_id:
        detail = await formats.get_format_detail(format_id)
        if detail is not None:
            if hasattr(detail, "model_dump"):
                format_detail_payload = detail.model_dump()
            else:
                format_detail_payload = detail

    prompt = prompts.get_prompt(project.get("prompt_id")) if project.get("prompt_id") else None
    spec = n8n_specs.build_spec(
        project=project,
        format_detail=format_detail_payload,
        prompt=prompt,
    )

    section_index = spec.get("sectionIndex")
    if not isinstance(section_index, list):
        raw_definition = spec.get("formatDefinition")
        if isinstance(raw_definition, dict):
            section_index = compile_definition_to_section_index(raw_definition)
        else:
            section_index = []

    sim_sections = _build_sim_sections(
        section_index=section_index,
    )

    ai_result = {"sections": sim_sections}

    run_id = f"sim-{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d%H%M%S')}"
    updated = projects.mark_simulated(
        project_id=projectId,
        ai_result=ai_result,
        run_id=run_id,
        artifacts=[],
    )

    return {
        "ok": True,
        "mode": "simulation",
        "source": "n8n_contract",
        "projectId": projectId,
        "runId": run_id,
        "status": "simulated",
        "aiResult": ai_result,
        "project": updated,
    }


# =============================================================================
# PROMPTS ENDPOINTS
# =============================================================================


@router.get("/prompts")
def list_prompts():
    return prompts.list_prompts()


@router.post("/prompts", status_code=201)
def create_prompt(payload: PromptIn):
    # Convertimos el objeto a diccionario para que el servicio guarde TODO
    data = payload.model_dump()

    # Aseguramos compatibilidad: si no hay template, usamos system_instruction
    if not data.get("template") and data.get("system_instruction"):
        data["template"] = data["system_instruction"]

    return prompts.create_prompt(data)


@router.put("/prompts/{prompt_id}")
def update_prompt(prompt_id: str, payload: PromptIn):
    data = payload.model_dump()

    if not data.get("template") and data.get("system_instruction"):
        data["template"] = data["system_instruction"]

    updated = prompts.update_prompt(prompt_id, data)
    if not updated:
        raise HTTPException(status_code=404, detail="Prompt no encontrado")
    return updated


@router.delete("/prompts/{prompt_id}")
def delete_prompt(prompt_id: str):
    ok = prompts.delete_prompt(prompt_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return {"ok": True}


# =============================================================================
# PROJECTS ENDPOINTS
# =============================================================================


@router.get("/projects")
def list_projects():
    return projects.list_projects()


@router.post("/projects/draft", status_code=201)
def create_project_draft(payload: Optional[ProjectDraftIn] = None):
    """Persist wizard state before triggering external workflow."""
    payload = payload or ProjectDraftIn()
    prompt = prompts.get_prompt(payload.prompt_id) if payload.prompt_id else None
    format_id = payload.format_id or "draft-format"
    draft_values = dict(payload.variables or {})
    if payload.title and not str(draft_values.get("title") or "").strip():
        draft_values["title"] = str(payload.title).strip()

    # --- Guardamos las secciones y la instrucción maestra en el borrador ---
    project_data = {
        "title": payload.title,
        "prompt_id": payload.prompt_id,
        "prompt_name": prompt.get("name") if prompt else None,
        # Guardamos la estructura nueva para que el generador sepa qué hacer
        "system_instruction": prompt.get("system_instruction") if prompt else None,
        "sections": prompt.get("sections") if prompt else [],
        # Mantenemos compatibilidad con versiones viejas
        "prompt_template": prompt.get("template") if prompt else None,
        "format_id": format_id,
        "format_name": payload.format_name or format_id,
        "format_version": payload.format_version,
        "variables": draft_values,
        "values": draft_values,
        "status": "draft",
        "wizard_state": payload.wizard_state,
    }

    project = projects.create_project(project_data)

    return {
        **project,
        "id": project["id"],
        "projectId": project["id"],
        "status": project.get("status", "draft"),
    }


@router.get("/projects/{project_id}")
def get_project(project_id: str):
    p = projects.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return p


@router.get("/projects/{project_id}/budget")
def get_project_budget(
    project_id: str,
    provider: Optional[str] = Query(default=None),
    model: Optional[str] = Query(default=None),
    refresh_pricing: bool = Query(default=False, alias="refreshPricing"),
):
    project = projects.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return build_project_budget_report(
        project,
        pricing_service=pricing_service,
        selected_provider=str(provider or ""),
        selected_model=str(model or ""),
        refresh_pricing=bool(refresh_pricing),
    )


@router.delete("/projects/{project_id}")
def delete_project(project_id: str):
    ok = projects.delete_project(project_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"ok": True, "projectId": project_id}


@router.get("/projects/{project_id}/trace")
def get_project_trace(project_id: str):
    project = projects.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return {
        "projectId": project_id,
        "events": projects.list_trace(project_id),
    }


@router.get("/projects/{project_id}/trace/stream")
async def stream_project_trace(project_id: str, request: Request):
    project = projects.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    async def _event_stream():
        last_count = 0
        while True:
            if await request.is_disconnected():
                break

            current = projects.get_project(project_id)
            if current is None:
                break

            events = projects.list_trace(project_id)
            if len(events) > last_count:
                for event in events[last_count:]:
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                last_count = len(events)
            else:
                yield "event: ping\ndata: {}\n\n"

            if str(current.get("status") or "") in TRACE_TERMINAL_STATUSES:
                break
            await asyncio.sleep(1)

    return StreamingResponse(_event_stream(), media_type="text/event-stream")


@router.put("/projects/{project_id}")
def update_project(project_id: str, payload: ProjectUpdateIn):
    current_project = projects.get_project(project_id)
    if not current_project:
        raise HTTPException(status_code=404, detail="Project not found")

    raw = payload.model_dump(exclude_unset=True)
    prompt_id = raw.get("prompt_id")
    prompt = prompts.get_prompt(prompt_id) if prompt_id else None
    variables = raw.get("variables") if "variables" in raw else None
    reset_generated_state = bool(raw.get("reset_generated_state"))
    touch_project_timestamp = raw.get("touch_project_timestamp")
    if touch_project_timestamp is None:
        touch_project_timestamp = True

    # --- Actualizamos secciones si cambia el prompt ---
    update_payload: Dict[str, Any] = {
        "title": raw.get("title"),
        "prompt_id": raw.get("prompt_id"),
        "prompt_name": prompt.get("name") if prompt else raw.get("prompt_name"),
        # Si hay nuevo prompt, traemos sus secciones nuevas
        "system_instruction": prompt.get("system_instruction") if prompt else None,
        "sections": prompt.get("sections") if prompt else None,
        "prompt_template": prompt.get("template") if prompt else raw.get("prompt_template"),
        "format_id": raw.get("format_id"),
        "format_name": raw.get("format_name"),
        "format_version": raw.get("format_version"),
        "status": raw.get("status"),
        "wizard_state": raw.get("wizard_state"),
    }

    # Limpieza de valores nulos
    update_payload = {k: v for k, v in update_payload.items() if v is not None}

    if variables is not None:
        merged_values = dict(variables)
        raw_title = str(raw.get("title") or "").strip()
        if raw_title and not str(merged_values.get("title") or "").strip():
            merged_values["title"] = raw_title
        update_payload["variables"] = merged_values
        update_payload["values"] = merged_values

    if reset_generated_state:
        current_provider = ""
        progress = current_project.get("progress")
        if isinstance(progress, dict):
            current_provider = str(progress.get("provider") or "")
        update_payload.update(
            {
                "status": raw.get("status") or "draft",
                "ai_result": None,
                "artifacts": [],
                "output_file": None,
                "pdf_file": None,
                "error": None,
                "run_id": None,
                "cancel_requested": False,
                "token_usage": empty_token_usage_report(),
                "generation_cost": empty_generation_cost_report(),
                "progress": {
                    "current": 0,
                    "total": 0,
                    "currentPath": "",
                    "provider": current_provider,
                    "tokenUsage": token_usage_snapshot(empty_token_usage_report()),
                    "costUsage": generation_cost_snapshot(empty_generation_cost_report()),
                    "updatedAt": _utc_now_z(),
                },
                "generation_snapshot": _build_generation_snapshot(
                    sections=[],
                    total_sections=0,
                    current_path="",
                    token_usage_snapshot_data=token_usage_snapshot(empty_token_usage_report()),
                    cost_usage_snapshot_data=generation_cost_snapshot(empty_generation_cost_report()),
                    status="idle",
                ),
                "generation_phase": {
                    **_empty_generation_phase(),
                    "updated_at": _utc_now_z(),
                },
                "construction_phase": {
                    **_empty_construction_phase(),
                    "updated_at": _utc_now_z(),
                },
                "incidents": [],
                "warnings_count": 0,
                "resume": {
                    "eligible": False,
                    "saved_sections_count": 0,
                    "resume_from_index": 0,
                    "last_failed_section_path": "",
                    "format_version": str(raw.get("format_version") or current_project.get("format_version") or ""),
                    "base_run_id": "",
                    "retry_count": 0,
                    "reason": "",
                    "updated_at": _utc_now_z(),
                },
            }
        )

    updated = projects.update_project(
        project_id,
        update_payload,
        touch_updated_at=bool(touch_project_timestamp),
    )
    if reset_generated_state:
        projects.clear_trace(project_id)
    return updated


@router.post("/projects/{project_id}/cancel")
def cancel_project_generation(project_id: str):
    project = projects.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    updated = projects.request_cancel(project_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Project not found")

    _emit_project_trace(
        project_id,
        step="generation.cancel.requested",
        status="warn",
        title="Cancelacion solicitada",
        detail="Se detendra el proceso cuando finalice la operacion en curso.",
    )
    return {
        "ok": True,
        "projectId": project_id,
        "status": updated.get("status"),
        "cancelRequested": True,
    }


@router.get("/download/{project_id}")
def download(project_id: str):
    p = projects.get_project(project_id)
    if not p or not p.get("output_file"):
        raise HTTPException(status_code=404, detail="File not available")
    file_path = Path(p["output_file"])
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File missing on disk")
    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@router.get("/download/{project_id}/pdf")
def download_pdf(project_id: str):
    p = projects.get_project(project_id)
    pdf_path_raw = p.get("pdf_file") if isinstance(p, dict) else None
    if not p or not pdf_path_raw:
        raise HTTPException(status_code=404, detail="File not available")
    file_path = Path(str(pdf_path_raw))
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File missing on disk")
    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type="application/pdf",
    )


@router.get("/sim/download/docx")
async def sim_download_docx(projectId: str, runId: Optional[str] = None):
    """
    Download DOCX artifact.

    Always proxied to GicaTesis render/docx. GicaGen does not generate local docs.
    """
    project = projects.get_project(projectId)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    format_id = project.get("format_id")
    if not format_id:
        raise HTTPException(status_code=400, detail="Project has no format_id")

    project_values = project.get("values") if isinstance(project.get("values"), dict) else {}
    values = _values_with_title(project, project_values)
    ai_result_raw = project.get("ai_result") if isinstance(project.get("ai_result"), dict) else {"sections": []}
    ai_result = _adapt_ai_result_for_gicatesis(ai_result_raw)

    url = f"{settings.GICATESIS_BASE_URL.rstrip('/')}/render/docx"
    try:
        payload: Dict[str, Any] = _build_render_payload(
            format_id=format_id,
            values=values,
            ai_result_raw=ai_result_raw,
        )
    except RenderPayloadValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors)
    _emit_project_trace(
        projectId,
        step="gicatesis.payload",
        status="running",
        title="Enviando payload a GicaTesis (DOCX)",
        preview={
            "payload": json.dumps(
                {
                    "formatId": format_id,
                    "valuesKeys": sorted(list(values.keys())),
                    "sections": len(ai_result.get("sections", [])),
                },
                ensure_ascii=False,
            )
        },
    )
    _emit_project_trace(
        projectId,
        step="gicatesis.render.docx",
        status="running",
        title="Render DOCX en proceso",
    )

    async with httpx.AsyncClient(timeout=180.0) as client:
        try:
            response = await client.post(url, json=payload)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            upstream_detail = _extract_upstream_detail(exc.response, "GicaTesis render/docx failed")
            raise HTTPException(
                status_code=exc.response.status_code,
                detail=upstream_detail,
            )
        except Exception:
            _emit_project_trace(
                projectId,
                step="gicatesis.render.docx",
                status="error",
                title="Render DOCX fallido",
                detail=_gicatesis_unavailable_detail("Render DOCX no disponible"),
            )
            raise HTTPException(
                status_code=503,
                detail=_gicatesis_unavailable_detail("Render DOCX no disponible"),
            )

    projects.update_project(projectId, {"status": "completed"})
    _emit_project_trace(
        projectId,
        step="gicatesis.payload",
        status="done",
        title="Payload procesado por GicaTesis",
    )
    _emit_project_trace(
        projectId,
        step="gicatesis.render.docx",
        status="done",
        title="DOCX listo",
    )
    response_run_id = runId or str(project.get("run_id") or "")
    return Response(
        content=response.content,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f'attachment; filename="generated-{projectId}.docx"',
            "X-Generated-By": "gicatesis",
            "X-Simulation-RunId": response_run_id,
        },
    )


@router.get("/sim/download/pdf")
async def sim_download_pdf(projectId: str, runId: Optional[str] = None):
    """
    Download PDF artifact.

    Always proxied to GicaTesis render/pdf. GicaGen does not generate local docs.
    """
    project = projects.get_project(projectId)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    format_id = project.get("format_id")
    if not format_id:
        raise HTTPException(status_code=400, detail="Project has no format_id")

    project_values = project.get("values") if isinstance(project.get("values"), dict) else {}
    values = _values_with_title(project, project_values)
    ai_result_raw = project.get("ai_result") if isinstance(project.get("ai_result"), dict) else {"sections": []}
    ai_result = _adapt_ai_result_for_gicatesis(ai_result_raw)

    url = f"{settings.GICATESIS_BASE_URL.rstrip('/')}/render/pdf"
    try:
        payload: Dict[str, Any] = _build_render_payload(
            format_id=format_id,
            values=values,
            ai_result_raw=ai_result_raw,
        )
    except RenderPayloadValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors)
    _emit_project_trace(
        projectId,
        step="gicatesis.payload",
        status="running",
        title="Enviando payload a GicaTesis (PDF)",
        preview={
            "payload": json.dumps(
                {
                    "formatId": format_id,
                    "valuesKeys": sorted(list(values.keys())),
                    "sections": len(ai_result.get("sections", [])),
                },
                ensure_ascii=False,
            )
        },
    )
    _emit_project_trace(
        projectId,
        step="gicatesis.render.pdf",
        status="running",
        title="Render PDF en proceso",
    )

    async with httpx.AsyncClient(timeout=240.0) as client:
        try:
            response = await client.post(url, json=payload)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            upstream_detail = _extract_upstream_detail(exc.response, "GicaTesis render/pdf failed")
            raise HTTPException(
                status_code=exc.response.status_code,
                detail=upstream_detail,
            )
        except Exception:
            _emit_project_trace(
                projectId,
                step="gicatesis.render.pdf",
                status="error",
                title="Render PDF fallido",
                detail=_gicatesis_unavailable_detail("Render PDF no disponible"),
            )
            raise HTTPException(
                status_code=503,
                detail=_gicatesis_unavailable_detail("Render PDF no disponible"),
            )

    projects.update_project(projectId, {"status": "completed"})
    _emit_project_trace(
        projectId,
        step="gicatesis.payload",
        status="done",
        title="Payload procesado por GicaTesis",
    )
    _emit_project_trace(
        projectId,
        step="gicatesis.render.pdf",
        status="done",
        title="PDF listo",
    )
    response_run_id = runId or str(project.get("run_id") or "")
    return Response(
        content=response.content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="generated-{projectId}.pdf"',
            "X-Generated-By": "gicatesis",
            "X-Simulation-RunId": response_run_id,
        },
    )


async def _ai_generation_job(
    project_id: str,
    run_id: str,
    *,
    resume_from_partial: bool = False,
    resume_seed_sections: Optional[list[Dict[str, Any]]] = None,
):
    """Background task: generate content via IA and render artifacts."""

    project = projects.get_project(project_id)
    if not project:
        return

    provider_selection_raw = (
        project.get("ai_selection")
        if isinstance(project.get("ai_selection"), dict)
        else ai_service.get_provider_selection()
    )
    provider_selection = ai_service.normalize_provider_selection(provider_selection_raw)
    safe_seed_sections = _extract_resume_seed_sections({"sections": resume_seed_sections or []})
    if not safe_seed_sections and resume_from_partial:
        safe_seed_sections = _extract_resume_seed_sections(project.get("ai_result"))
    if not safe_seed_sections:
        resume_from_partial = False

    if project.get("ai_selection") != provider_selection:
        projects.update_project(project_id, {"ai_selection": provider_selection})
    provider_hint = str(
        project.get("progress", {}).get("provider")
        or provider_selection.get("provider")
        or settings.AI_PRIMARY_PROVIDER.lower()
    )
    initial_usage_report = (
        normalize_token_usage_report(project.get("ai_result", {}).get("tokenUsage"))
        if resume_from_partial and isinstance(project.get("ai_result"), dict)
        else empty_token_usage_report()
    )
    initial_total_sections = int(project.get("progress", {}).get("total") or 0)
    existing_generation_phase = _normalize_generation_phase_state(project.get("generation_phase"))
    initial_generation_phase = (
        {
            **existing_generation_phase,
            "status": "running",
            "current_section_id": (
                str(existing_generation_phase.get("sections", [])[-1].get("section_id") or "")
                if existing_generation_phase.get("sections")
                else ""
            ),
            "current_section_path": (
                str(existing_generation_phase.get("sections", [])[-1].get("section_path") or "")
                if existing_generation_phase.get("sections")
                else ""
            ),
            "updated_at": _utc_now_z(),
        }
        if resume_from_partial and existing_generation_phase.get("sections")
        else {
            **_empty_generation_phase(total_sections=initial_total_sections),
            "status": "running",
            "started_at": _utc_now_z(),
            "updated_at": _utc_now_z(),
        }
    )
    projects.update_project(
        project_id,
        {
            "status": "generating",
            "run_id": run_id,
            "cancel_requested": False,
            "incidents": [],
            "warnings_count": 0,
            "generation_snapshot": _build_generation_snapshot(
                sections=safe_seed_sections if resume_from_partial else [],
                total_sections=initial_total_sections,
                current_path=(
                    safe_seed_sections[-1].get("path") or "" if resume_from_partial and safe_seed_sections else ""
                ),
                token_usage_snapshot_data=token_usage_snapshot(initial_usage_report),
                run_id=run_id,
                status="running" if resume_from_partial and safe_seed_sections else "idle",
            ),
            "generation_phase": initial_generation_phase,
            "construction_phase": _empty_construction_phase(),
        },
    )
    projects.update_progress(
        project_id,
        current=len(safe_seed_sections) if resume_from_partial else 0,
        total=0,
        current_path=(safe_seed_sections[-1].get("path") or "") if resume_from_partial and safe_seed_sections else "",
        provider=provider_hint,
        token_usage_snapshot_data=token_usage_snapshot(initial_usage_report),
        token_usage_report_data=initial_usage_report,
    )
    _emit_project_trace(
        project_id,
        step="generation.job",
        status="running",
        title="Generacion en cola iniciada",
        meta={"runId": run_id, "provider": provider_hint, "stage": "queued"},
    )
    if resume_from_partial:
        _emit_project_trace(
            project_id,
            step="generation.resume",
            status="warn",
            title="Reanudando desde avance previo",
            detail=f"Se reutilizaran {len(safe_seed_sections)} secciones ya generadas en el intento anterior.",
            meta={"stage": "queued", "seededSections": len(safe_seed_sections)},
        )

    format_detail_payload: Optional[Dict[str, Any]] = None
    prompt = prompts.get_prompt(project.get("prompt_id")) if project.get("prompt_id") else None

    format_id = str(project.get("format_id") or "").strip()
    if format_id:
        try:
            detail = await formats.get_format_detail(format_id)
            if detail is not None:
                format_detail_payload = detail.model_dump() if hasattr(detail, "model_dump") else detail
                definition = format_detail_payload.get("definition")
                total_sections = (
                    len(compile_definition_to_section_index(definition)) if isinstance(definition, dict) else 0
                )
                projects.update_progress(project_id, total=total_sections)
                current_project_snapshot = projects.get_project(project_id) or {}
                snapshot_raw = (
                    current_project_snapshot.get("generation_snapshot")
                    if isinstance(current_project_snapshot.get("generation_snapshot"), dict)
                    else {}
                )
                completed_sections = snapshot_raw.get("completed_sections") if isinstance(snapshot_raw, dict) else []
                projects.update_project(
                    project_id,
                    {
                        "generation_snapshot": _build_generation_snapshot(
                            sections=completed_sections if isinstance(completed_sections, list) else [],
                            total_sections=total_sections,
                            current_path=str(snapshot_raw.get("current_path") or ""),
                            token_usage_snapshot_data=(
                                snapshot_raw.get("tokenUsage")
                                if isinstance(snapshot_raw.get("tokenUsage"), dict)
                                else token_usage_snapshot(ai_service.get_token_usage_report())
                            ),
                            run_id=run_id,
                            status="running" if resume_from_partial and safe_seed_sections else "idle",
                        ),
                        "generation_phase": {
                            **_normalize_generation_phase_state(
                                (projects.get_project(project_id) or {}).get("generation_phase")
                            ),
                            "total_sections": total_sections,
                            "updated_at": _utc_now_z(),
                        },
                    },
                )
                _emit_project_trace(
                    project_id,
                    step="format.loaded",
                    status="done",
                    title="Formato JSON cargado",
                    detail=f"Se detectaron {total_sections} secciones.",
                    meta={
                        "formatId": format_id,
                        "sectionTotal": total_sections,
                        "stage": "queued",
                    },
                )
        except Exception as exc:
            _logger.warning("Could not fetch format detail for %s: %s", project_id, exc)
            _emit_project_trace(
                project_id,
                step="format.loaded",
                status="warn",
                title="No se pudo cargar detalle completo del formato",
                detail=str(exc),
                meta={"formatId": format_id, "stage": "queued"},
            )
    else:
        _emit_project_trace(
            project_id,
            step="format.loaded",
            status="warn",
            title="Proyecto sin format_id",
            detail="La generacion intentara continuar con estructura minima.",
            meta={"stage": "queued"},
        )

    def _on_trace(event: Dict[str, Any]) -> None:
        _update_generation_phase_for_event(project_id, event)
        _emit_project_trace(
            project_id,
            step=str(event.get("step") or "ai.event"),
            status=str(event.get("status") or "running"),
            title=str(event.get("title") or "Evento de IA"),
            detail=str(event.get("detail") or ""),
            meta=event.get("meta") if isinstance(event.get("meta"), dict) else None,
            preview=event.get("preview") if isinstance(event.get("preview"), dict) else None,
        )

    def _on_progress(
        current: int,
        total: int,
        path: str,
        provider: str,
        *,
        stage: str = "section_start",
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        safe_total = total if total >= 0 else 0
        safe_current = current if current >= 0 else 0
        usage_report = ai_service.get_token_usage_report()
        usage_snapshot = ai_service.get_token_usage_snapshot()
        cost_report = build_generation_cost_report(usage_report, pricing_service=pricing_service)
        cost_snapshot = generation_cost_snapshot(cost_report)
        projects.update_progress(
            project_id,
            current=safe_current,
            total=safe_total if safe_total > 0 else None,
            current_path=path or "",
            provider=provider or "",
            token_usage_snapshot_data=usage_snapshot,
            token_usage_report_data=usage_report,
            cost_usage_snapshot_data=cost_snapshot,
            generation_cost_report_data=cost_report,
        )
        if isinstance(payload, dict) and payload.get("section_id"):
            current_project = projects.get_project(project_id) or {}
            generation_phase = _normalize_generation_phase_state(current_project.get("generation_phase"))
            generation_phase["total_sections"] = max(
                safe_total,
                int(generation_phase.get("total_sections") or 0),
            )
            generation_phase["status"] = "running"
            generation_phase["updated_at"] = _utc_now_z()
            generation_phase = _upsert_generation_section(generation_phase, payload)
            generation_phase = _apply_generation_costs_to_phase(generation_phase, cost_report)
            projects.update_project(project_id, {"generation_phase": generation_phase})

        if stage == "provider_fallback":
            _emit_project_trace(
                project_id,
                step="ai.provider.fallback",
                status="warn",
                title=f"Cambio automatico de proveedor -> {provider}",
                detail=f"Continuando en {provider} por cuota/error del proveedor principal.",
                meta={
                    "provider": provider,
                    "sectionCurrent": safe_current,
                    "sectionTotal": safe_total,
                    "sectionPath": path,
                    "stage": stage,
                },
            )
            return
        if stage == "cleanup_correction":
            return

        status = "running" if stage == "section_start" else "done"
        title = (
            f"IA: seccion {safe_current}/{safe_total} ({path})"
            if safe_total > 0
            else f"IA: seccion {safe_current} ({path})"
        )
        _emit_project_trace(
            project_id,
            step="ai.generate.section",
            status=status,
            title=title,
            meta={
                "provider": provider,
                "sectionIndex": safe_current,
                "sectionTotal": safe_total,
                "sectionPath": path,
                "stage": stage,
            },
        )

    # Ensure title variable exists before prompt rendering and downstream render.
    project_values = project.get("values") if isinstance(project.get("values"), dict) else {}
    enriched_values = _values_with_title(project, project_values)
    _emit_project_trace(
        project_id,
        step="project.variables.ready",
        status="done",
        title="Variables del proyecto preparadas",
        meta={
            "variables": len(enriched_values.keys()),
            "promptId": project.get("prompt_id"),
            "stage": "queued",
        },
    )
    if enriched_values != project_values:
        projects.update_project(
            project_id,
            {
                "values": enriched_values,
                "variables": enriched_values,
            },
        )
        project = projects.get_project(project_id) or project

    project_for_ai = dict(project)
    project_for_ai["values"] = enriched_values
    project_for_ai["variables"] = enriched_values

    def _persist_partial_resume_snapshot(reason: str) -> int:
        partial_ai = ai_service.get_partial_ai_result()
        partial_sections = partial_ai.get("sections") if isinstance(partial_ai, dict) else None
        if not isinstance(partial_sections, list) or not partial_sections:
            return 0

        usage_report = ai_service.get_token_usage_report()
        usage_snapshot = ai_service.get_token_usage_snapshot()
        cost_report = build_generation_cost_report(usage_report, pricing_service=pricing_service)
        cost_snapshot = generation_cost_snapshot(cost_report)
        last_path = str(partial_sections[-1].get("path") or "")
        partial_ai["tokenUsage"] = usage_report
        partial_ai["generationCost"] = cost_report
        latest_project = projects.get_project(project_id) or {}
        latest_progress = latest_project.get("progress") if isinstance(latest_project.get("progress"), dict) else {}
        total_sections = (
            len(compile_definition_to_section_index(format_detail_payload.get("definition", {})))
            if isinstance(format_detail_payload, dict)
            else int(latest_progress.get("total") or 0)
        )
        projects.update_project(
            project_id,
            {
                "ai_result": partial_ai,
                "token_usage": usage_report,
                "generation_cost": cost_report,
                "generation_snapshot": _build_generation_snapshot(
                    sections=partial_sections,
                    total_sections=total_sections,
                    current_path=last_path,
                    token_usage_snapshot_data=usage_snapshot,
                    cost_usage_snapshot_data=cost_snapshot,
                    run_id=run_id,
                    status="resume_ready",
                ),
            },
        )
        projects.mark_resume_checkpoint(
            project_id,
            saved_sections_count=len(partial_sections),
            last_failed_section_path=last_path,
            reason=reason,
            base_run_id=run_id,
        )
        projects.update_progress(
            project_id,
            current=len(partial_sections),
            total=total_sections or None,
            current_path=last_path,
            provider=provider_hint,
            token_usage_snapshot_data=usage_snapshot,
            token_usage_report_data=usage_report,
            cost_usage_snapshot_data=cost_snapshot,
            generation_cost_report_data=cost_report,
        )
        _emit_project_trace(
            project_id,
            step="generation.resume",
            status="warn",
            title="Avance parcial guardado para reintento",
            detail=f"{reason}. Se conservaron {len(partial_sections)} secciones.",
            meta={"stage": "failed", "sections": len(partial_sections)},
        )
        return len(partial_sections)

    try:
        ai_result = await asyncio.to_thread(
            ai_service.generate,
            project=project_for_ai,
            format_detail=format_detail_payload,
            prompt=prompt,
            trace_hook=_on_trace,
            cancel_check=lambda: projects.is_cancel_requested(project_id),
            progress_cb=_on_progress,
            selection_override=provider_selection,
            resume_from_partial=resume_from_partial,
            seed_sections_override=safe_seed_sections,
        )
        provider = ai_service.get_last_used_provider() or provider_hint
        model = (
            ai_service.get_model_for_provider(
                provider,
                selection_override=provider_selection,
            )
            or "-"
        )
        usage_report = ai_service.get_token_usage_report()
        usage_snapshot = ai_service.get_token_usage_snapshot()
        cost_report = build_generation_cost_report(usage_report, pricing_service=pricing_service)
        cost_snapshot = generation_cost_snapshot(cost_report)
        ai_result["generationCost"] = cost_report
        projects.update_progress(
            project_id,
            provider=provider,
            token_usage_snapshot_data=usage_snapshot,
            token_usage_report_data=usage_report,
            cost_usage_snapshot_data=cost_snapshot,
            generation_cost_report_data=cost_report,
        )

        run_incidents = ai_service.get_run_incidents()
        if run_incidents:
            for incident in run_incidents:
                projects.append_incident(project_id, incident)
            warning_count = sum(1 for item in run_incidents if str(item.get("severity") or "").lower() == "warning")
            _emit_project_trace(
                project_id,
                step="generation.incidents",
                status="warn",
                title="Generacion completada con incidencias de proveedor",
                detail=f"Incidencias registradas: {len(run_incidents)} (warnings: {warning_count}).",
                meta={"stage": "section_done", "warnings": warning_count},
            )

        projects.mark_ai_received(
            project_id,
            ai_result,
            run_id=run_id,
            artifacts=[
                {"type": "docx", "downloadUrl": f"/api/download/{project_id}"},
                {"type": "pdf", "downloadUrl": f"/api/download/{project_id}/pdf"},
            ],
        )
        current_project_after_ai = projects.get_project(project_id) or {}
        generation_phase = _normalize_generation_phase_state(current_project_after_ai.get("generation_phase"))
        generation_phase["status"] = "completed"
        generation_phase["finished_at"] = _utc_now_z()
        generation_phase["updated_at"] = _utc_now_z()
        generation_phase = _apply_generation_costs_to_phase(generation_phase, cost_report)
        projects.update_project(project_id, {"generation_phase": generation_phase})
        _set_construction_task(
            project_id,
            "handoff",
            status="done",
            detail="La generacion IA termino y el contenido validado quedo listo para construir el documento.",
            global_status="running",
        )
        _emit_project_trace(
            project_id,
            step="project.status.ai_received",
            status="done",
            title="Contenido IA recibido",
            detail=f"Proveedor: {provider} ({model}).",
            meta={
                "provider": provider,
                "model": model,
                "runId": run_id,
                "stage": "done",
            },
        )

        latest_project = projects.get_project(project_id)
        if not latest_project:
            return

        latest_format_id = str(latest_project.get("format_id") or "").strip()
        if not latest_format_id:
            projects.mark_failed(project_id, "No format_id available for GicaTesis render.")
            _emit_project_trace(
                project_id,
                step="project.status.failed",
                status="error",
                title="Generacion fallida",
                detail="El proyecto no tiene format_id configurado.",
                meta={"stage": "failed"},
            )
            return

        latest_values = latest_project.get("values") if isinstance(latest_project.get("values"), dict) else {}
        values = _values_with_title(latest_project, latest_values)
        if values != latest_values:
            projects.update_project(
                project_id,
                {
                    "values": values,
                    "variables": values,
                },
            )

        # correct sections (desarrollo / texto) â€” indices, caratula, and
        def _render_outputs_sync() -> tuple[Path, Path]:
            return _render_project_outputs_sync(
                project_id,
                format_id=latest_format_id,
                values=values,
                ai_result_raw=ai_result,
            )

        docx_path, pdf_path = await asyncio.to_thread(_render_outputs_sync)

        projects.mark_completed(
            project_id,
            str(docx_path),
            pdf_file=str(pdf_path),
            artifacts=[
                {"type": "docx", "downloadUrl": f"/api/download/{project_id}"},
                {"type": "pdf", "downloadUrl": f"/api/download/{project_id}/pdf"},
            ],
        )
        _set_construction_task(
            project_id,
            "final_validation",
            status="done",
            detail="DOCX y PDF generados y validados para descarga.",
            global_status="completed",
            finish=True,
        )
        finished_project = projects.get_project(project_id) or {}
        warnings_count = int(finished_project.get("warnings_count") or 0)
        has_incidents = warnings_count > 0
        _emit_project_trace(
            project_id,
            step="generation.job",
            status="done",
            title="Generacion finalizada",
            detail=(
                "IA y render completados con incidencias opcionales."
                if has_incidents
                else "IA y render completados correctamente."
            ),
            meta={
                "runId": run_id,
                "provider": provider,
                "stage": "done",
                "warnings": warnings_count,
            },
        )
        _logger.info("AI generation completed for project %s using %s", project_id, provider)
    except RenderStageError as exc:
        projects.mark_render_failed(project_id, exc.detail_text)
        _set_construction_task(
            project_id,
            "final_validation",
            status="error",
            detail="La construccion se detuvo por un error en render.",
            global_status="error",
        )
        _emit_project_trace(
            project_id,
            step="project.status.render_failed",
            status="error",
            title="Render fallido; contenido IA conservado",
            detail=exc.detail_text,
            meta={"runId": run_id, "stage": "failed", "statusCode": exc.status_code},
        )
        _emit_project_trace(
            project_id,
            step="generation.job",
            status="error",
            title="Generacion IA completada, pero el render fallo",
            detail="El proyecto conserva ai_result para reintentar solo render.",
            meta={"runId": run_id, "stage": "failed", "statusCode": exc.status_code},
        )
        _logger.error("Render stage failed for project %s: %s", project_id, exc.detail_text)
    except GenerationCancelledError as exc:
        _persist_partial_resume_snapshot("Generacion cancelada por usuario")
        projects.mark_blocked(project_id, str(exc), keep_ai_result=True)
        current_project = projects.get_project(project_id) or {}
        generation_phase = _normalize_generation_phase_state(current_project.get("generation_phase"))
        generation_phase["status"] = "blocked"
        generation_phase["updated_at"] = _utc_now_z()
        projects.update_project(project_id, {"generation_phase": generation_phase})
        _emit_project_trace(
            project_id,
            step="generation.job",
            status="warn",
            title="Generacion cancelada",
            detail=str(exc),
            meta={"runId": run_id, "stage": "failed"},
        )
        _logger.info("AI generation cancelled for project %s", project_id)
    except QuotaExceededError as exc:
        partial_count = _persist_partial_resume_snapshot("Error de cuota del proveedor IA")
        projects.mark_failed(project_id, str(exc), keep_ai_result=partial_count > 0)
        current_project = projects.get_project(project_id) or {}
        generation_phase = _normalize_generation_phase_state(current_project.get("generation_phase"))
        generation_phase["status"] = "failed"
        generation_phase["updated_at"] = _utc_now_z()
        projects.update_project(project_id, {"generation_phase": generation_phase})
        _emit_project_trace(
            project_id,
            step="generation.job",
            status="error",
            title="Generacion fallida por cuota",
            detail=str(exc),
            meta={
                "runId": run_id,
                "retryAfter": exc.retry_after,
                "provider": exc.provider,
                "stage": "failed",
            },
        )
        _logger.error("AI generation quota error for project %s: %s", project_id, exc)
    except Exception as exc:
        partial_count = _persist_partial_resume_snapshot("Error transitorio durante generacion IA")
        projects.mark_failed(project_id, str(exc), keep_ai_result=partial_count > 0)
        current_project = projects.get_project(project_id) or {}
        generation_phase = _normalize_generation_phase_state(current_project.get("generation_phase"))
        generation_phase["status"] = "failed"
        generation_phase["updated_at"] = _utc_now_z()
        projects.update_project(project_id, {"generation_phase": generation_phase})
        _emit_project_trace(
            project_id,
            step="generation.job",
            status="error",
            title="Generacion detenida por error",
            detail=str(exc),
            meta={"runId": run_id, "stage": "failed"},
        )
        _logger.error("AI generation failed for project %s: %s", project_id, exc)


async def _render_saved_ai_job(project_id: str, run_id: str) -> None:
    """Render artifacts from an already validated ai_result without re-running IA."""

    project = projects.get_project(project_id)
    if not project:
        return

    format_id = str(project.get("format_id") or "").strip()
    ai_result = project.get("ai_result") if isinstance(project.get("ai_result"), dict) else None
    if not format_id:
        projects.mark_render_failed(project_id, "No format_id available for GicaTesis render.")
        return
    if not isinstance(ai_result, dict) or not isinstance(ai_result.get("sections"), list) or not ai_result["sections"]:
        projects.mark_render_failed(project_id, "No ai_result available for render retry.")
        return

    values_source = project.get("values") if isinstance(project.get("values"), dict) else {}
    values = _values_with_title(project, values_source)
    if values != values_source:
        projects.update_project(
            project_id,
            {
                "values": values,
                "variables": values,
            },
        )

    provider = str(project.get("progress", {}).get("provider") or "")
    _set_construction_task(
        project_id,
        "handoff",
        status="done",
        detail="Se reutiliza el contenido IA guardado para reconstruir el documento.",
        global_status="running",
    )

    try:
        docx_path, pdf_path = await asyncio.to_thread(
            _render_project_outputs_sync,
            project_id,
            format_id=format_id,
            values=values,
            ai_result_raw=ai_result,
        )
        projects.mark_completed(
            project_id,
            str(docx_path),
            pdf_file=str(pdf_path),
            artifacts=[
                {"type": "docx", "downloadUrl": f"/api/download/{project_id}"},
                {"type": "pdf", "downloadUrl": f"/api/download/{project_id}/pdf"},
            ],
        )
        _set_construction_task(
            project_id,
            "final_validation",
            status="done",
            detail="Render reintentado con exito y artefactos listos.",
            global_status="completed",
            finish=True,
        )
        _emit_project_trace(
            project_id,
            step="generation.job",
            status="done",
            title="Render reintentado con exito",
            detail="Se reutilizo el ai_result guardado sin volver a llamar al proveedor IA.",
            meta={"runId": run_id, "provider": provider, "stage": "done"},
        )
    except RenderStageError as exc:
        projects.mark_render_failed(project_id, exc.detail_text)
        _set_construction_task(
            project_id,
            "final_validation",
            status="error",
            detail="El reintento de construccion termino con error.",
            global_status="error",
        )
        _emit_project_trace(
            project_id,
            step="project.status.render_failed",
            status="error",
            title="Render reintentado y fallido",
            detail=exc.detail_text,
            meta={"runId": run_id, "provider": provider, "stage": "failed", "statusCode": exc.status_code},
        )
        _logger.error("Render retry failed for project %s: %s", project_id, exc.detail_text)


async def _demo_generation_job(project_id: str, format_name: str, prompt_name: str, variables: Dict[str, Any]):
    """Background task: generate demo DOCX locally (fallback)."""
    _emit_project_trace(
        project_id,
        step="demo.generate.start",
        status="running",
        title="Modo demo: generando documento local",
    )
    out_path = Path("outputs") / f"{project_id}.docx"
    build_demo_docx(
        output_path=str(out_path),
        title=f"{prompt_name} - {format_name}",
        sections=["Capitulo 1", "Capitulo 2", "Capitulo 3", "Capitulo 4", "Referencias"],
        variables=variables,
    )
    await asyncio.sleep(0.8)
    projects.mark_completed(
        project_id,
        str(out_path),
        artifacts=[
            {"type": "docx", "downloadUrl": f"/api/download/{project_id}"},
            {"type": "pdf", "downloadUrl": f"/api/render/pdf?projectId={project_id}"},
        ],
    )
    _emit_project_trace(
        project_id,
        step="project.status.completed",
        status="done",
        title="Modo demo completado",
        detail=f"Archivo generado: {out_path.name}",
    )


@router.post("/projects/generate")
def generate(payload: ProjectGenerateIn, background: BackgroundTasks):
    """
    DEPRECATED -- Legacy endpoint kept for backward compatibility.

    Wizard v2 now uses:
    - POST /api/projects/draft
    - POST /api/projects/{id}/generate
    """
    prompt = prompts.get_prompt(payload.prompt_id)
    if not prompt:
        raise HTTPException(status_code=400, detail="Invalid prompt_id")

    format_name = payload.format_id
    legacy_values = dict(payload.variables or {})
    legacy_title = payload.title or legacy_values.get("tema")
    if legacy_title and not str(legacy_values.get("title") or "").strip():
        legacy_values["title"] = str(legacy_title).strip()

    project = projects.create_project(
        {
            "title": legacy_title,
            "prompt_id": payload.prompt_id,
            "prompt_name": prompt.get("name"),
            "prompt_template": prompt.get("template"),
            "format_id": payload.format_id,
            "format_name": format_name,
            "variables": legacy_values,
            "values": legacy_values,
            "status": "processing",
        }
    )

    background.add_task(
        _demo_generation_job,
        project["id"],
        format_name,
        prompt.get("name", "Prompt"),
        legacy_values,
    )
    return project


@router.post("/projects/{projectId}/generate", status_code=202)
async def trigger_generation(
    projectId: str,
    background: BackgroundTasks,
    payload: Optional[ProjectGenerateTriggerIn] = None,
):
    """
    Trigger generation for an existing project draft.

    Priority order:
    1. If any AI provider is configured: enqueue async AI generation (202).
    2. If N8N_WEBHOOK_URL is set (DEPRECATED): call webhook for ACK.
    3. Otherwise: fall back to local demo (background).
    """
    project = projects.get_project(projectId)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # ------------------------------------------------------------------
    # Path A: AI provider configured => generate via AI
    # ------------------------------------------------------------------
    project_selection_raw = project.get("ai_selection") if isinstance(project.get("ai_selection"), dict) else None
    if project_selection_raw is None:
        project_selection_raw = ai_service.get_provider_selection()
    project_selection = ai_service.normalize_provider_selection(project_selection_raw)
    if project.get("ai_selection") != project_selection:
        projects.update_project(projectId, {"ai_selection": project_selection})

    requested_resume_mode = payload.resume_mode if payload else "auto"
    stored_ai_result = project.get("ai_result") if isinstance(project.get("ai_result"), dict) else None
    stored_ai_sections = (
        stored_ai_result.get("sections")
        if isinstance(stored_ai_result, dict) and isinstance(stored_ai_result.get("sections"), list)
        else []
    )
    can_retry_render_only = (
        str(project.get("status") or "").strip().lower() == "render_failed"
        and requested_resume_mode != "restart"
        and bool(stored_ai_sections)
    )

    if can_retry_render_only:
        _logger.info("Retrying render-only for project %s using saved ai_result", projectId)
        projects.clear_trace(projectId)
        progress = project.get("progress") if isinstance(project.get("progress"), dict) else {}
        provider = (
            str(progress.get("provider") or project_selection.get("provider") or settings.AI_PRIMARY_PROVIDER)
            .lower()
            .strip()
            or "gemini"
        )
        mode = str(project_selection.get("mode") or "auto").lower().strip()
        run_id = f"render-{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d%H%M%S')}"
        stored_usage_report = normalize_token_usage_report(stored_ai_result.get("tokenUsage"))
        total_sections = int(progress.get("total") or len(stored_ai_sections))
        current_sections = int(progress.get("current") or total_sections or len(stored_ai_sections))
        current_path = (
            str(progress.get("currentPath") or "").strip()
            or str((stored_ai_sections[-1] or {}).get("path") or "").strip()
        )
        projects.update_project(
            projectId,
            {
                "status": "rendering",
                "cancel_requested": False,
                "run_id": run_id,
                "error": None,
                "progress": {
                    "current": current_sections,
                    "total": total_sections,
                    "currentPath": current_path,
                    "provider": provider,
                    "tokenUsage": token_usage_snapshot(stored_usage_report),
                    "updatedAt": _utc_now_z(),
                },
                "token_usage": stored_usage_report,
                "generation_snapshot": _build_generation_snapshot(
                    sections=stored_ai_sections,
                    total_sections=total_sections,
                    current_path=current_path,
                    token_usage_snapshot_data=token_usage_snapshot(stored_usage_report),
                    run_id=run_id,
                    status="rendering",
                ),
                "construction_phase": {
                    **_empty_construction_phase(),
                    "status": "running",
                    "started_at": _utc_now_z(),
                    "updated_at": _utc_now_z(),
                },
            },
        )
        _emit_project_trace(
            projectId,
            step="generation.request.received",
            status="running",
            title="Solicitud de reintento de render recibida",
            detail="Se reutilizara el contenido IA ya validado; no se llamara al proveedor.",
            meta={
                "runId": run_id,
                "provider": provider,
                "mode": mode,
                "stage": "queued",
                "resumeMode": requested_resume_mode,
                "savedSections": len(stored_ai_sections),
                "retryMode": "render_only",
            },
        )
        _emit_project_trace(
            projectId,
            step="project.status.rendering",
            status="running",
            title="Proyecto en estado Renderizando",
            detail="Reintentando solo DOCX/PDF con ai_result existente.",
            meta={
                "runId": run_id,
                "provider": provider,
                "mode": mode,
                "stage": "queued",
                "retryMode": "render_only",
            },
        )
        background.add_task(_render_saved_ai_job, projectId, run_id)
        return {
            "ok": True,
            "status": "rendering",
            "projectId": projectId,
            "runId": run_id,
            "mode": "render_only",
            "provider": provider,
            "model": ai_service.get_model_for_provider(provider, selection_override=project_selection),
            "selectionMode": mode,
            "resumeMode": requested_resume_mode,
            "savedSections": len(stored_ai_sections),
            "resumeFromSection": len(stored_ai_sections),
        }

    if ai_service.is_configured(selection_override=project_selection):
        _logger.info("Starting AI generation for project %s", projectId)
        resume_from_partial, resume_seed_sections, resolved_resume_mode = _decide_resume_mode(
            project,
            requested_mode=requested_resume_mode,
        )
        saved_sections = len(resume_seed_sections)
        resume_from_section = saved_sections + 1 if resume_from_partial else 1

        projects.clear_trace(projectId)
        projects.clear_incidents(projectId)
        if resolved_resume_mode == "restart":
            projects.update_project(projectId, {"ai_result": None})
            projects.clear_resume(projectId)
            projects.clear_generation_snapshot(projectId)
            projects.update_project(
                projectId,
                {
                    "generation_phase": {
                        **_empty_generation_phase(),
                        "updated_at": _utc_now_z(),
                    },
                    "construction_phase": {
                        **_empty_construction_phase(),
                        "updated_at": _utc_now_z(),
                    },
                },
            )
            resume_from_partial = False
            resume_seed_sections = []
            saved_sections = 0
            resume_from_section = 1

        selection = project_selection
        available = ai_service.available_providers(selection_override=selection)
        provider = (
            str(available[0]).lower().strip()
            if available
            else str(selection.get("provider") or settings.AI_PRIMARY_PROVIDER).lower().strip() or "gemini"
        )
        mode = str(selection.get("mode") or "auto").lower().strip()
        run_id = f"{provider}-{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d%H%M%S')}"
        initial_usage_report = (
            normalize_token_usage_report(stored_ai_result.get("tokenUsage"))
            if resume_from_partial and isinstance(stored_ai_result, dict)
            else empty_token_usage_report()
        )
        initial_cost_report = (
            normalize_generation_cost_report(stored_ai_result.get("generationCost"))
            if resume_from_partial and isinstance(stored_ai_result, dict)
            else empty_generation_cost_report()
        )
        if (
            resume_from_partial
            and isinstance(stored_ai_result, dict)
            and not initial_cost_report.get("priced_calls")
            and initial_usage_report.get("calls_total")
        ):
            initial_cost_report = build_generation_cost_report(initial_usage_report, pricing_service=pricing_service)
        initial_cost_snapshot = generation_cost_snapshot(initial_cost_report)
        existing_progress = project.get("progress") if isinstance(project.get("progress"), dict) else {}
        total_sections_hint = int(existing_progress.get("total") or 0)
        existing_generation_phase = _normalize_generation_phase_state(project.get("generation_phase"))
        if resume_from_partial:
            seeded_generation_phase = {
                **existing_generation_phase,
                "status": "running",
                "updated_at": _utc_now_z(),
            }
            if not seeded_generation_phase.get("sections") and resume_seed_sections:
                seeded_generation_phase["sections"] = [
                    {
                        "section_id": str(item.get("sectionId") or ""),
                        "section_path": str(item.get("path") or ""),
                        "section_title": _section_title_from_path(str(item.get("path") or "")),
                        "parent_section_path": _section_parent_path(str(item.get("path") or "")),
                        "section_level": _section_level_from_path(str(item.get("path") or "")),
                        "prompt_sent": "",
                        "ai_output": "",
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "total_tokens": 0,
                        "model": "",
                        "provider": provider,
                        "status": "ok",
                        "duration_ms": 0,
                        "estimated": False,
                        "source": "",
                        "attempt_count": 0,
                        "attempts": [],
                        "error": "",
                        "started_at": "",
                        "completed_at": "",
                        "updated_at": _utc_now_z(),
                    }
                    for item in resume_seed_sections
                    if isinstance(item, dict) and (item.get("sectionId") or item.get("path"))
                ]
                seeded_generation_phase["completed_sections"] = len(seeded_generation_phase["sections"])
                if seeded_generation_phase["sections"]:
                    seeded_generation_phase["current_section_id"] = str(
                        seeded_generation_phase["sections"][-1].get("section_id") or ""
                    )
                    seeded_generation_phase["current_section_path"] = str(
                        seeded_generation_phase["sections"][-1].get("section_path") or ""
                    )
            generation_phase_payload = seeded_generation_phase
        else:
            generation_phase_payload = {
                **_empty_generation_phase(total_sections=total_sections_hint),
                "status": "running",
                "started_at": _utc_now_z(),
                "updated_at": _utc_now_z(),
            }
        generation_phase_payload = _apply_generation_costs_to_phase(generation_phase_payload, initial_cost_report)
        projects.update_project(
            projectId,
            {
                "status": "generating",
                "cancel_requested": False,
                "run_id": run_id,
                "progress": {
                    "current": saved_sections if resume_from_partial else 0,
                    "total": 0,
                    "currentPath": (
                        str(resume_seed_sections[-1].get("path") or "")
                        if resume_from_partial and resume_seed_sections
                        else ""
                    ),
                    "provider": provider,
                    "tokenUsage": token_usage_snapshot(initial_usage_report),
                    "costUsage": initial_cost_snapshot,
                    "updatedAt": _utc_now_z(),
                },
                "token_usage": initial_usage_report,
                "generation_cost": initial_cost_report,
                "generation_snapshot": _build_generation_snapshot(
                    sections=resume_seed_sections if resume_from_partial else [],
                    total_sections=total_sections_hint,
                    current_path=(
                        str(resume_seed_sections[-1].get("path") or "")
                        if resume_from_partial and resume_seed_sections
                        else ""
                    ),
                    token_usage_snapshot_data=token_usage_snapshot(initial_usage_report),
                    cost_usage_snapshot_data=initial_cost_snapshot,
                    run_id=run_id,
                    status="running" if resume_from_partial and resume_seed_sections else "idle",
                ),
                "generation_phase": (generation_phase_payload),
                "construction_phase": {
                    **_empty_construction_phase(),
                    "updated_at": _utc_now_z(),
                },
            },
        )

        _emit_project_trace(
            projectId,
            step="generation.request.received",
            status="running",
            title="Solicitud de generacion recibida",
            meta={
                "runId": run_id,
                "provider": provider,
                "mode": mode,
                "stage": "queued",
                "resumeMode": resolved_resume_mode,
                "savedSections": saved_sections,
            },
        )
        _emit_project_trace(
            projectId,
            step="project.status.generating",
            status="running",
            title="Proyecto en estado Generando",
            meta={
                "runId": run_id,
                "provider": provider,
                "mode": mode,
                "stage": "queued",
                "resumeMode": resolved_resume_mode,
            },
        )
        if resume_from_partial and resume_seed_sections:
            _emit_project_trace(
                projectId,
                step="generation.resume",
                status="warn",
                title=f"Reanudando desde seccion {resume_from_section}",
                detail=f"Se reutilizaran {saved_sections} secciones guardadas del intento previo.",
                meta={
                    "runId": run_id,
                    "savedSections": saved_sections,
                    "resumeFromSection": resume_from_section,
                    "stage": "queued",
                },
            )

        background.add_task(
            _ai_generation_job,
            projectId,
            run_id,
            resume_from_partial=resume_from_partial,
            resume_seed_sections=resume_seed_sections,
        )
        return {
            "ok": True,
            "status": "generating",
            "projectId": projectId,
            "runId": run_id,
            "mode": "async",
            "provider": provider,
            "model": ai_service.get_model_for_provider(provider, selection_override=selection),
            "selectionMode": mode,
            "resumeMode": resolved_resume_mode,
            "savedSections": saved_sections,
            "resumeFromSection": resume_from_section,
        }

    # ------------------------------------------------------------------
    # Path B (DEPRECATED): n8n configured => synchronous ACK
    # ------------------------------------------------------------------
    if settings.N8N_WEBHOOK_URL:
        _logger.info("Using DEPRECATED n8n path for project %s", projectId)
        projects.clear_trace(projectId)
        projects.clear_incidents(projectId)
        n8n_values_source = (
            project.get("variables")
            if isinstance(project.get("variables"), dict)
            else project.get("values")
            if isinstance(project.get("values"), dict)
            else {}
        )
        n8n_values = _values_with_title(project, n8n_values_source)
        _emit_project_trace(
            projectId,
            step="generation.request.received",
            status="running",
            title="Solicitud recibida (ruta n8n legacy)",
        )
        callback_url = f"{settings.GICAGEN_BASE_URL.rstrip('/')}/api/integrations/n8n/callback"
        payload = {
            "projectId": projectId,
            "format": {
                "id": project.get("format_id"),
                "name": project.get("format_name"),
                "version": project.get("format_version"),
            },
            "prompt": {
                "id": project.get("prompt_id"),
                "name": project.get("prompt_name"),
            },
            "values": n8n_values,
            "callbackUrl": callback_url,
        }

        projects.update_project(projectId, {"status": "sending"})
        _emit_project_trace(
            projectId,
            step="project.status.sending",
            status="running",
            title="Enviando payload a n8n",
        )
        result = await n8n.trigger(payload)

        if result.get("ok"):
            run_id = result.get("data", {}).get("runId") or result.get("data", {}).get("run_id") or f"run_{projectId}"
            projects.update_project(
                projectId,
                {
                    "status": "n8n_ack",
                    "run_id": run_id,
                },
            )
            _emit_project_trace(
                projectId,
                step="project.status.n8n_ack",
                status="done",
                title="n8n confirmo la ejecucion",
                meta={"runId": run_id},
            )
            return {
                "ok": True,
                "status": "n8n_ack",
                "runId": run_id,
                "statusCode": result.get("statusCode"),
            }

        error_msg = result.get("error", "Error desconocido al llamar a n8n")
        projects.update_project(
            projectId,
            {
                "status": "n8n_failed",
                "error": error_msg,
            },
        )
        _emit_project_trace(
            projectId,
            step="project.status.n8n_failed",
            status="error",
            title="n8n devolvio error",
            detail=error_msg,
        )
        raise HTTPException(status_code=502, detail=error_msg)

    # ------------------------------------------------------------------
    # Path C: no Gemini, no n8n => local demo (background task)
    # ------------------------------------------------------------------
    projects.clear_trace(projectId)
    projects.clear_incidents(projectId)
    projects.update_project(projectId, {"status": "processing", "cancel_requested": False})
    _emit_project_trace(
        projectId,
        step="project.status.processing",
        status="running",
        title="Generacion local en modo demo",
    )
    background.add_task(
        _demo_generation_job,
        projectId,
        project.get("format_name", "Format"),
        project.get("prompt_name", "Prompt"),
        _values_with_title(
            project,
            project.get("variables") if isinstance(project.get("variables"), dict) else {},
        ),
    )
    return {"ok": True, "status": "processing", "mode": "demo"}


@router.post("/n8n/callback/{project_id}")
def legacy_n8n_callback(project_id: str, body: Dict[str, Any]):
    """Legacy callback endpoint kept for compatibility."""
    status = body.get("status")
    if status == "completed":
        file_path = body.get("file_path")
        if not file_path:
            raise HTTPException(status_code=400, detail="file_path required")
        updated = projects.mark_completed(project_id, file_path)
        if not updated:
            raise HTTPException(status_code=404, detail="Project not found")
        return {"ok": True, "project": updated}

    if status == "failed":
        updated = projects.mark_failed(project_id, body.get("error", "Unknown error"))
        if not updated:
            raise HTTPException(status_code=404, detail="Project not found")
        return {"ok": True, "project": updated}

    raise HTTPException(status_code=400, detail="Invalid status")


# =============================================================================
# RENDER PROXY ENDPOINTS - Forward to GicaTesis Real Generators
# =============================================================================
# These endpoints proxy to GicaTesis /api/v1/render/* which uses the REAL
# generator scripts. This ensures DOCX/PDF are VISUALLY IDENTICAL to those
# generated by GicaTesis UI (same logos, fonts, margins, styles).


@router.get("/render/docx")
@router.post("/render/docx")
async def render_docx(projectId: str = Query(..., description="Project ID")):
    """
    Render DOCX using GicaTesis REAL generator pipeline.

    This proxies to GicaTesis /api/v1/render/docx which calls the same
    generator scripts as the GicaTesis UI. The resulting DOCX is visually
    identical to downloading from GicaTesis directly.
    """
    project = projects.get_project(projectId)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    format_id = project.get("format_id")
    if not format_id:
        raise HTTPException(status_code=400, detail="Project has no format_id")

    source_values = project.get("values") if isinstance(project.get("values"), dict) else {}
    values = _values_with_title(project, source_values)
    ai_result_raw = project.get("ai_result") if isinstance(project.get("ai_result"), dict) else {"sections": []}

    # Proxy to GicaTesis render endpoint
    url = f"{settings.GICATESIS_BASE_URL}/render/docx"
    try:
        payload: Dict[str, Any] = _build_render_payload(
            format_id=format_id,
            values=values,
            ai_result_raw=ai_result_raw,
        )
    except RenderPayloadValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors)
    _emit_project_trace(
        projectId,
        step="gicatesis.payload",
        status="running",
        title="Enviando payload a GicaTesis (render/docx)",
    )
    _emit_project_trace(
        projectId,
        step="gicatesis.render.docx",
        status="running",
        title="Render DOCX en proceso",
    )

    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            headers = {}
            if settings.GICATESIS_API_KEY:
                headers["X-GICATESIS-KEY"] = settings.GICATESIS_API_KEY

            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            _emit_project_trace(
                projectId,
                step="gicatesis.payload",
                status="done",
                title="Payload procesado por GicaTesis",
            )
            _emit_project_trace(
                projectId,
                step="gicatesis.render.docx",
                status="done",
                title="DOCX listo",
            )

            # Stream the binary response back to client
            content_disposition = response.headers.get(
                "content-disposition", f'attachment; filename="gicatesis-{format_id}.docx"'
            )

            return Response(
                content=response.content,
                media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                headers={
                    "Content-Disposition": content_disposition,
                    "X-Rendered-By": "gicatesis-real-generator",
                    "X-Proxy-Source": "gicatesis",
                },
            )
        except httpx.HTTPStatusError as exc:
            upstream_detail = _extract_upstream_detail(exc.response, "GicaTesis render failed")
            _emit_project_trace(
                projectId,
                step="gicatesis.render.docx",
                status="error",
                title="Render DOCX fallido",
                detail=upstream_detail,
            )
            raise HTTPException(status_code=exc.response.status_code, detail=upstream_detail)
        except Exception:
            _emit_project_trace(
                projectId,
                step="gicatesis.render.docx",
                status="error",
                title="Render DOCX no disponible",
                detail=_gicatesis_unavailable_detail("Render DOCX no disponible"),
            )
            raise HTTPException(
                status_code=503,
                detail=_gicatesis_unavailable_detail("Render DOCX no disponible"),
            )


@router.get("/render/pdf")
@router.post("/render/pdf")
async def render_pdf(projectId: str = Query(..., description="Project ID")):
    """
    Render PDF using GicaTesis REAL generator pipeline.

    This proxies to GicaTesis /api/v1/render/pdf which:
    1. Generates DOCX using real generator scripts
    2. Converts to PDF using Word COM

    The resulting PDF is visually identical to GicaTesis UI output.
    """
    project = projects.get_project(projectId)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    format_id = project.get("format_id")
    if not format_id:
        raise HTTPException(status_code=400, detail="Project has no format_id")

    source_values = project.get("values") if isinstance(project.get("values"), dict) else {}
    values = _values_with_title(project, source_values)
    ai_result_raw = project.get("ai_result") if isinstance(project.get("ai_result"), dict) else {"sections": []}

    # Build structured definition with AI content injected into the
    # Proxy to GicaTesis render endpoint
    url = f"{settings.GICATESIS_BASE_URL}/render/pdf"
    try:
        payload: Dict[str, Any] = _build_render_payload(
            format_id=format_id,
            values=values,
            ai_result_raw=ai_result_raw,
        )
    except RenderPayloadValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors)
    _emit_project_trace(
        projectId,
        step="gicatesis.payload",
        status="running",
        title="Enviando payload a GicaTesis (render/pdf)",
    )
    _emit_project_trace(
        projectId,
        step="gicatesis.render.pdf",
        status="running",
        title="Render PDF en proceso",
    )

    async with httpx.AsyncClient(timeout=180.0) as client:
        try:
            headers = {}
            if settings.GICATESIS_API_KEY:
                headers["X-GICATESIS-KEY"] = settings.GICATESIS_API_KEY

            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            _emit_project_trace(
                projectId,
                step="gicatesis.payload",
                status="done",
                title="Payload procesado por GicaTesis",
            )
            _emit_project_trace(
                projectId,
                step="gicatesis.render.pdf",
                status="done",
                title="PDF listo",
            )

            content_disposition = response.headers.get(
                "content-disposition", f'attachment; filename="gicatesis-{format_id}.pdf"'
            )

            return Response(
                content=response.content,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": content_disposition,
                    "X-Rendered-By": "gicatesis-real-generator",
                    "X-Proxy-Source": "gicatesis",
                },
            )
        except httpx.HTTPStatusError as exc:
            upstream_detail = _extract_upstream_detail(exc.response, "GicaTesis render failed")
            _emit_project_trace(
                projectId,
                step="gicatesis.render.pdf",
                status="error",
                title="Render PDF fallido",
                detail=upstream_detail,
            )
            raise HTTPException(status_code=exc.response.status_code, detail=upstream_detail)
        except Exception:
            _emit_project_trace(
                projectId,
                step="gicatesis.render.pdf",
                status="error",
                title="Render PDF no disponible",
                detail=_gicatesis_unavailable_detail("Render PDF no disponible"),
            )
            raise HTTPException(
                status_code=503,
                detail=_gicatesis_unavailable_detail("Render PDF no disponible"),
            )
