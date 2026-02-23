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
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response, StreamingResponse

from app.core.config import settings
from app.core.services.ai import AIService, QuotaExceededError
from app.core.services.ai.errors import GenerationCancelledError
from app.core.services.definition_compiler import compile_definition_to_section_index
from app.core.services.docx_builder import build_demo_docx
from app.core.services.format_service import FormatService
from app.core.services.gicatesis_status import gicatesis_status
from app.core.services.n8n_client import N8NClient
from app.core.services.n8n_integration_service import N8NIntegrationService
from app.core.services.project_service import ProjectService
from app.core.services.prompt_service import PromptService
from app.core.services.toc_detector import is_toc_path as _is_toc_path
from app.integrations.gicatesis.errors import (
    GicaTesisError,
    UpstreamTimeout,
    UpstreamUnavailable,
)
from app.modules.api.models import (
    N8NCallbackIn,
    ProjectDraftIn,
    ProjectGenerateIn,
    ProjectUpdateIn,
    PromptIn,
    ProviderSelectIn,
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
STARTED_AT = dt.datetime.now(dt.timezone.utc).isoformat()
TRACE_MAX_PREVIEW_CHARS = 520
TRACE_TERMINAL_STATUSES = {
    "completed",
    "failed",
    "blocked",
    "cancel_requested",
    "n8n_failed",
    "ai_failed",
    "generation_failed",
}
_API_KEY_RE = re.compile(r"AIza[0-9A-Za-z\-_]{20,}")
_BEARER_RE = re.compile(r"Bearer\s+[A-Za-z0-9\-\._~\+/]+=*", re.IGNORECASE)
_SECRET_FIELD_RE = re.compile(r"(?i)\b(api[_-]?key|authorization|token|secret)\b\s*[:=]\s*([^\s,;]+)")


def _utc_now_z() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _sanitize_text(value: Any) -> str:
    text = str(value or "")
    text = _API_KEY_RE.sub("[REDACTED_KEY]", text)
    text = _BEARER_RE.sub("Bearer [REDACTED]", text)
    text = _SECRET_FIELD_RE.sub(lambda m: f"{m.group(1)}=[REDACTED]", text)
    return " ".join(text.split())


def _clip_text(value: Any, max_chars: int = TRACE_MAX_PREVIEW_CHARS) -> str:
    sanitized = _sanitize_text(value)
    if len(sanitized) <= max_chars:
        return sanitized
    return f"{sanitized[: max_chars - 1]}â€¦"


def _sanitize_preview(preview: Optional[Dict[str, Any]]) -> Optional[Dict[str, str]]:
    if not isinstance(preview, dict):
        return None
    cleaned: Dict[str, str] = {}
    for key in ("prompt", "raw", "clean", "payload"):
        if key in preview and preview.get(key) is not None:
            cleaned[key] = _clip_text(preview.get(key))
    return cleaned or None


def _status_to_level(status: str) -> str:
    lowered = str(status or "").lower()
    if lowered in {"error", "failed"}:
        return "error"
    if lowered in {"warn", "warning"}:
        return "warn"
    if lowered == "done":
        return "info"
    return "info"


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
    safe_meta: Dict[str, Any] = {}
    if isinstance(meta, dict) and meta:
        for key, value in meta.items():
            if isinstance(value, (str, int, float, bool)) or value is None:
                safe_meta[key] = _clip_text(value, 140) if isinstance(value, str) else value

    def _as_int(value: Any) -> int:
        try:
            return int(value)
        except Exception:
            return 0

    provider = str(safe_meta.get("provider") or safe_meta.get("to") or safe_meta.get("targetProvider") or "")
    section_current = _as_int(safe_meta.get("sectionIndex") or safe_meta.get("sectionCurrent") or 0)
    section_total = _as_int(safe_meta.get("sectionTotal") or safe_meta.get("totalSections") or 0)
    section_path = str(safe_meta.get("sectionPath") or safe_meta.get("path") or "")

    message = _clip_text(
        f"{title}. {detail}" if detail else title,
        360,
    )
    event_stage = str(safe_meta.get("stage") or step)
    event: Dict[str, Any] = {
        "ts": _utc_now_z(),
        # New event contract (for project.events)
        "level": _status_to_level(status),
        "stage": event_stage,
        "message": message,
        "provider": provider,
        "sectionCurrent": section_current,
        "sectionTotal": section_total,
        "sectionPath": section_path,
        # Legacy trace fields (kept for compatibility)
        "step": step,
        "status": status,
        "title": _clip_text(title, 220),
    }
    if detail:
        event["detail"] = _clip_text(detail, 360)
    if safe_meta:
        event["meta"] = safe_meta
    safe_preview = _sanitize_preview(preview)
    if safe_preview:
        event["preview"] = safe_preview
    projects.append_event(project_id, event)


def _git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _extract_upstream_detail(response: httpx.Response, default_message: str) -> str:
    """Extract useful detail from an upstream HTTP response body."""
    try:
        payload = response.json()
    except Exception:
        payload = None

    if isinstance(payload, dict):
        detail = payload.get("detail")
        if isinstance(detail, str) and detail.strip():
            return detail.strip()

    raw = response.text.strip() if isinstance(response.text, str) else ""
    if raw:
        return raw[:500]
    return default_message


def _gicatesis_unavailable_detail(action: str) -> str:
    return (
        f"{action}: no se pudo conectar a GicaTesis en "
        f"{settings.GICATESIS_BASE_URL}. Levanta GicaTesis en :8000 o "
        "actualiza GICATESIS_BASE_URL. Para pruebas de catalogo sin upstream, "
        "puedes usar GICAGEN_DEMO_MODE=true."
    )


def _build_sim_sections(
    section_index: list[Dict[str, Any]],
) -> list[Dict[str, str]]:
    sections: list[Dict[str, str]] = []
    for idx, section in enumerate(section_index, start=1):
        path = str(section.get("path") or "").strip()
        if not path:
            continue
        section_id = str(section.get("sectionId") or f"sec-{idx:04d}")
        sections.append(
            {
                "sectionId": section_id,
                "path": path,
                "content": f"Contenido IA simulado para: {path}",
            }
        )
    if not sections:
        sections.append(
            {
                "sectionId": "sec-0001",
                "path": "Documento/Seccion principal",
                "content": "Contenido IA simulado para: Documento/Seccion principal",
            }
        )
    return sections


def _values_with_title(
    project: Dict[str, Any],
    source_values: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Ensure render/generation values include ``title`` fallback."""
    values: Dict[str, Any] = dict(source_values or {})
    title_value = values.get("title")
    if isinstance(title_value, str) and title_value.strip():
        return values

    project_title = str(project.get("title") or "").strip()
    if project_title:
        values["title"] = project_title
    return values


def _adapt_ai_result_for_gicatesis(ai_result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Normalize aiResult payload for GicaTesis render without path collisions.

    Important:
    - Keep only canonical paths emitted by the compiler.
    - Do not duplicate leaf paths, which can collide with TOC/index headings.
    """
    if not isinstance(ai_result, dict):
        return {"sections": []}

    raw_sections = ai_result.get("sections")
    if not isinstance(raw_sections, list):
        return {"sections": []}

    canonical_sections: list[Dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for section in raw_sections:
        if not isinstance(section, dict):
            continue

        content = section.get("content")
        if not isinstance(content, str) or not content.strip():
            continue

        section_id = section.get("sectionId")
        section_path = section.get("path")
        path = section_path.strip() if isinstance(section_path, str) else ""

        if not path:
            continue

        # Defence-in-depth: drop TOC/index sections that may have leaked.
        if _is_toc_path(path):
            continue

        canonical_id = section_id.strip() if isinstance(section_id, str) and section_id.strip() else ""
        dedupe_key = (canonical_id or path, path)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        entry: Dict[str, str] = {
            "path": path,
            "content": content,
        }
        if canonical_id:
            entry["sectionId"] = canonical_id
        canonical_sections.append(entry)

    # Avoid top-level heading collisions with TOC rows in upstream renderers:
    # when a level-1 section also has child sections, move its content to the
    # first child and omit the parent entry.
    by_path: Dict[str, Dict[str, str]] = {item["path"]: item for item in canonical_sections if item.get("path")}
    parent_paths_with_children: set[str] = set()
    for path in by_path.keys():
        if "/" in path:
            continue
        prefix = f"{path}/"
        if any(other_path.startswith(prefix) for other_path in by_path.keys()):
            parent_paths_with_children.add(path)

    paths_to_drop: set[str] = set()
    for parent_path in parent_paths_with_children:
        parent_entry = by_path.get(parent_path)
        if not parent_entry:
            continue
        parent_content = str(parent_entry.get("content") or "").strip()
        if not parent_content:
            paths_to_drop.add(parent_path)
            continue

        first_child: Optional[Dict[str, str]] = None
        child_prefix = f"{parent_path}/"
        for item in canonical_sections:
            item_path = item.get("path", "")
            if item_path.startswith(child_prefix):
                first_child = item
                break
        if first_child is not None:
            child_content = str(first_child.get("content") or "").strip()
            if child_content:
                first_child["content"] = f"{parent_content}\n\n{child_content}"
            else:
                first_child["content"] = parent_content
        paths_to_drop.add(parent_path)

    if paths_to_drop:
        canonical_sections = [item for item in canonical_sections if item.get("path") not in paths_to_drop]

    return {"sections": canonical_sections}


def _build_render_payload(
    *,
    format_id: str,
    values: Dict[str, Any],
    ai_result_raw: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build render payload for GicaTesis preserving canonical AI sections.

    Keep ``aiResult.sections`` as the source of truth. Do not replace it
    with an injected structured definition, otherwise generated content can
    be lost when upstream renderers ignore custom fields.
    """
    ai_result = _adapt_ai_result_for_gicatesis(ai_result_raw)
    return {
        "formatId": format_id,
        "values": values,
        "mode": "simulation",
        "aiResult": ai_result,
    }


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


@router.post("/prompts")
def create_prompt(payload: PromptIn):
    return prompts.create_prompt(payload.model_dump())


@router.put("/prompts/{prompt_id}")
def update_prompt(prompt_id: str, payload: PromptIn):
    updated = prompts.update_prompt(prompt_id, payload.model_dump())
    if not updated:
        raise HTTPException(status_code=404, detail="Prompt not found")
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

    project = projects.create_project(
        {
            "title": payload.title,
            "prompt_id": payload.prompt_id,
            "prompt_name": prompt.get("name") if prompt else None,
            "prompt_template": prompt.get("template") if prompt else None,
            "format_id": format_id,
            "format_name": payload.format_name or format_id,
            "format_version": payload.format_version,
            "variables": draft_values,
            "values": draft_values,
            "status": "draft",
        }
    )
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
    raw = payload.model_dump(exclude_unset=True)
    prompt_id = raw.get("prompt_id")
    prompt = prompts.get_prompt(prompt_id) if prompt_id else None
    variables = raw.get("variables") if "variables" in raw else None

    update_payload: Dict[str, Any] = {
        "title": raw.get("title"),
        "prompt_id": raw.get("prompt_id"),
        "prompt_name": prompt.get("name") if prompt else raw.get("prompt_name"),
        "prompt_template": prompt.get("template") if prompt else raw.get("prompt_template"),
        "format_id": raw.get("format_id"),
        "format_name": raw.get("format_name"),
        "format_version": raw.get("format_version"),
        "status": raw.get("status"),
    }
    if variables is not None:
        merged_values = dict(variables)
        raw_title = str(raw.get("title") or "").strip()
        if raw_title and not str(merged_values.get("title") or "").strip():
            merged_values["title"] = raw_title
        update_payload["variables"] = merged_values
        update_payload["values"] = merged_values

    updated = projects.update_project(
        project_id,
        update_payload,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Project not found")
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
    payload: Dict[str, Any] = _build_render_payload(
        format_id=format_id,
        values=values,
        ai_result_raw=ai_result_raw,
    )
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
    payload: Dict[str, Any] = _build_render_payload(
        format_id=format_id,
        values=values,
        ai_result_raw=ai_result_raw,
    )
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


async def _ai_generation_job(project_id: str, run_id: str):
    """Background task: generate content via IA and render artifacts."""

    project = projects.get_project(project_id)
    if not project:
        return

    provider_selection = (
        project.get("ai_selection")
        if isinstance(project.get("ai_selection"), dict)
        else ai_service.get_provider_selection()
    )
    previous_status = str(project.get("status") or "").lower().strip()
    previous_ai_result = project.get("ai_result") if isinstance(project.get("ai_result"), dict) else None
    has_previous_sections = bool((previous_ai_result or {}).get("sections"))
    resume_from_partial = previous_status in {
        "failed",
        "blocked",
        "cancel_requested",
        "generation_failed",
        "ai_failed",
    } and has_previous_sections
    if not isinstance(project.get("ai_selection"), dict):
        projects.update_project(project_id, {"ai_selection": provider_selection})
    provider_hint = str(
        project.get("progress", {}).get("provider")
        or provider_selection.get("provider")
        or settings.AI_PRIMARY_PROVIDER.lower()
    )
    projects.update_project(
        project_id,
        {
            "status": "generating",
            "run_id": run_id,
            "cancel_requested": False,
            "incidents": [],
            "warnings_count": 0,
        },
    )
    projects.update_progress(
        project_id,
        current=0,
        total=0,
        current_path="",
        provider=provider_hint,
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
            detail="Se reutilizaran secciones ya generadas en el intento anterior.",
            meta={"stage": "queued"},
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
    ) -> None:
        safe_total = total if total >= 0 else 0
        safe_current = current if current >= 0 else 0
        projects.update_progress(
            project_id,
            current=safe_current,
            total=safe_total if safe_total > 0 else None,
            current_path=path or "",
            provider=provider or "",
        )

        if stage == "provider_fallback":
            _emit_project_trace(
                project_id,
                step="ai.provider.fallback",
                status="warn",
                title=f"Fallback de proveedor -> {provider}",
                detail=f"Continuando en {provider} por cuota/error del proveedor primario.",
                meta={
                    "provider": provider,
                    "sectionCurrent": safe_current,
                    "sectionTotal": safe_total,
                    "sectionPath": path,
                    "stage": stage,
                },
            )
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

        last_path = str(partial_sections[-1].get("path") or "")
        projects.update_project(project_id, {"ai_result": partial_ai})
        projects.update_progress(
            project_id,
            current=len(partial_sections),
            total=len(compile_definition_to_section_index(format_detail_payload.get("definition", {})))
            if isinstance(format_detail_payload, dict)
            else None,
            current_path=last_path,
            provider=provider_hint,
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
        )
        provider = ai_service.get_last_used_provider() or provider_hint
        model = (
            ai_service.get_model_for_provider(
                provider,
                selection_override=provider_selection,
            )
            or "-"
        )
        projects.update_progress(project_id, provider=provider)

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
        ai_payload = _adapt_ai_result_for_gicatesis(ai_result)
        ai_sections = ai_payload.get("sections", [])
        sections_count = len(ai_sections)

        # Build a hierarchical payload by injecting AI content into the
        # format definition.  This ensures content lands ONLY in the
        # correct sections (desarrollo / texto) â€” indices, caratula, and
        # structural fields are never touched.
        payload_preview = {
            "formatId": latest_format_id,
            "valuesKeys": sorted(list(values.keys())),
            "sections": sections_count,
            "mode": "simulation",
        }

        _emit_project_trace(
            project_id,
            step="gicatesis.payload",
            status="running",
            title="Enviando payload a GicaTesis",
            detail=f"Secciones preparadas: {sections_count}.",
            meta={
                "formatId": latest_format_id,
                "sections": sections_count,
                "stage": "section_done",
            },
            preview={"payload": json.dumps(payload_preview, ensure_ascii=False)},
        )

        def _render_outputs_sync() -> tuple[Path, Path]:
            base_url = settings.GICATESIS_BASE_URL.rstrip("/")
            headers: Dict[str, str] = {}
            if settings.GICATESIS_API_KEY:
                headers["X-GICATESIS-KEY"] = settings.GICATESIS_API_KEY

            payload = _build_render_payload(
                format_id=latest_format_id,
                values=values,
                ai_result_raw=ai_result,
            )

            out_dir = Path("outputs")
            out_dir.mkdir(parents=True, exist_ok=True)
            docx_path = out_dir / f"{project_id}.docx"
            pdf_path = out_dir / f"{project_id}.pdf"

            with httpx.Client(timeout=240.0) as client:
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
                    _emit_project_trace(
                        project_id,
                        step="gicatesis.render.docx",
                        status="error",
                        title="Render DOCX fallido",
                        detail=detail,
                    )
                    raise RuntimeError(detail) from exc

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
                    _emit_project_trace(
                        project_id,
                        step="gicatesis.render.pdf",
                        status="error",
                        title="Render PDF fallido",
                        detail=detail,
                    )
                    raise RuntimeError(detail) from exc

            return docx_path, pdf_path

        docx_path, pdf_path = await asyncio.to_thread(_render_outputs_sync)

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

        projects.mark_completed(
            project_id,
            str(docx_path),
            pdf_file=str(pdf_path),
            artifacts=[
                {"type": "docx", "downloadUrl": f"/api/download/{project_id}"},
                {"type": "pdf", "downloadUrl": f"/api/download/{project_id}/pdf"},
            ],
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
    except GenerationCancelledError as exc:
        _persist_partial_resume_snapshot("Generacion cancelada por usuario")
        projects.mark_blocked(project_id, str(exc), keep_ai_result=True)
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
        _emit_project_trace(
            project_id,
            step="generation.job",
            status="error",
            title="Generacion detenida por error",
            detail=str(exc),
            meta={"runId": run_id, "stage": "failed"},
        )
        _logger.error("AI generation failed for project %s: %s", project_id, exc)


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
async def trigger_generation(projectId: str, background: BackgroundTasks):
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
    project_selection = project.get("ai_selection") if isinstance(project.get("ai_selection"), dict) else None
    if project_selection is None:
        project_selection = ai_service.get_provider_selection()
        projects.update_project(projectId, {"ai_selection": project_selection})

    if ai_service.is_configured(selection_override=project_selection):
        _logger.info("Starting AI generation for project %s", projectId)
        projects.clear_trace(projectId)
        projects.clear_incidents(projectId)
        selection = project_selection
        available = ai_service.available_providers(selection_override=selection)
        provider = (
            str(available[0]).lower().strip()
            if available
            else str(selection.get("provider") or settings.AI_PRIMARY_PROVIDER).lower().strip() or "gemini"
        )
        mode = str(selection.get("mode") or "auto").lower().strip()
        run_id = f"{provider}-{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d%H%M%S')}"
        projects.update_project(
            projectId,
            {
                "status": "generating",
                "cancel_requested": False,
                "run_id": run_id,
                "progress": {
                    "current": 0,
                    "total": 0,
                    "currentPath": "",
                    "provider": provider,
                    "updatedAt": _utc_now_z(),
                },
            },
        )

        _emit_project_trace(
            projectId,
            step="generation.request.received",
            status="running",
            title="Solicitud de generacion recibida",
            meta={"runId": run_id, "provider": provider, "mode": mode, "stage": "queued"},
        )
        _emit_project_trace(
            projectId,
            step="project.status.generating",
            status="running",
            title="Proyecto en estado Generando",
            meta={"runId": run_id, "provider": provider, "mode": mode, "stage": "queued"},
        )

        background.add_task(_ai_generation_job, projectId, run_id)
        return {
            "ok": True,
            "status": "generating",
            "projectId": projectId,
            "runId": run_id,
            "mode": "async",
            "provider": provider,
            "model": ai_service.get_model_for_provider(provider, selection_override=selection),
            "selectionMode": mode,
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
    payload: Dict[str, Any] = _build_render_payload(
        format_id=format_id,
        values=values,
        ai_result_raw=ai_result_raw,
    )
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
    payload: Dict[str, Any] = _build_render_payload(
        format_id=format_id,
        values=values,
        ai_result_raw=ai_result_raw,
    )
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
