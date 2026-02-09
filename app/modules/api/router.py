"""
API Router - BFF endpoints for frontend consumption.

Frontend calls `/api/*` only. GicaGen handles:
- Formats BFF + cache
- Prompt CRUD
- Project drafts/history
- n8n integration contracts/callback
"""
from __future__ import annotations

import asyncio
import datetime as dt
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query
from fastapi.responses import FileResponse, Response

from app.core.config import settings
from app.core.services.docx_builder import build_demo_docx
from app.core.services.format_service import FormatService
from app.core.services.n8n_client import N8NClient
from app.core.services.n8n_integration_service import N8NIntegrationService
from app.core.services.project_service import ProjectService
from app.core.services.prompt_service import PromptService
from app.core.services.simulation_artifact_service import (
    build_simulated_docx,
    build_simulated_pdf,
)
from app.integrations.gicatesis.errors import (
    GicaTesisError,
    UpstreamUnavailable,
    UpstreamTimeout,
)
from app.modules.api.models import N8NCallbackIn, ProjectDraftIn, ProjectGenerateIn, PromptIn
from app.modules.api.models import ProjectUpdateIn

router = APIRouter()

# Service instances
formats = FormatService()
prompts = PromptService()
projects = ProjectService()
n8n = N8NClient()
n8n_specs = N8NIntegrationService()
STARTED_AT = dt.datetime.now(dt.timezone.utc).isoformat()


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


def _build_sim_sections(
    values: Dict[str, Any],
    prompt_text: str,
    format_definition: Dict[str, Any],
) -> list[Dict[str, str]]:
    sections: list[Dict[str, str]] = []

    topic = str(values.get("tema") or values.get("titulo") or values.get("title") or "Proyecto")
    sections.append(
        {
            "title": "Resumen ejecutivo",
            "content": f"Simulacion de salida para {topic}. Prompt base: {prompt_text[:140]}",
        }
    )

    if values:
        details = ", ".join(f"{k}={v}" for k, v in list(values.items())[:5])
        sections.append(
            {
                "title": "Variables de entrada",
                "content": f"Valores aplicados en la ejecucion simulada: {details}",
            }
        )

    if format_definition:
        keys = ", ".join(list(format_definition.keys())[:8])
        sections.append(
            {
                "title": "Cobertura del formato",
                "content": f"La simulacion contempla la estructura definida en: {keys}",
            }
        )

    sections.append(
        {
            "title": "Plan de redaccion",
            "content": "Generar cada seccion conforme al formato institucional y validar coherencia antes del callback.",
        }
    )
    return sections


# =============================================================================
# FORMATS BFF ENDPOINTS
# =============================================================================

@router.get("/formats/version")
async def get_formats_version():
    """Return catalog version status from GicaTesis with cache metadata."""
    try:
        return await formats.check_version()
    except UpstreamUnavailable:
        raise HTTPException(status_code=502, detail="GicaTesis no disponible")
    except UpstreamTimeout:
        raise HTTPException(status_code=504, detail="GicaTesis timeout")
    except GicaTesisError as e:
        raise HTTPException(status_code=502, detail=f"Error de GicaTesis: {e}")


@router.get("/formats")
async def list_formats(
    university: Optional[str] = None,
    category: Optional[str] = None,
    documentType: Optional[str] = None,
):
    """List formats via BFF, using cache+ETag and optional filters."""
    try:
        return await formats.list_formats(
            university=university,
            category=category,
            document_type=documentType,
        )
    except UpstreamUnavailable:
        raise HTTPException(status_code=502, detail="GicaTesis no disponible y no hay cache")
    except GicaTesisError as e:
        raise HTTPException(status_code=502, detail=f"Error de GicaTesis: {e}")


@router.get("/formats/{format_id}")
async def get_format_detail(format_id: str):
    """Get full format detail from BFF/cache."""
    try:
        detail = await formats.get_format_detail(format_id)
        if not detail:
            raise HTTPException(status_code=404, detail=f"Formato no encontrado: {format_id}")
        return detail
    except UpstreamUnavailable:
        raise HTTPException(status_code=502, detail="GicaTesis no disponible")
    except UpstreamTimeout:
        raise HTTPException(status_code=504, detail="GicaTesis timeout")
    except GicaTesisError as e:
        raise HTTPException(status_code=502, detail=f"Error de GicaTesis: {e}")


@router.get("/assets/{path:path}")
async def proxy_asset(path: str):
    """Proxy for GicaTesis assets (logos, images) to avoid direct frontend calls."""
    url = f"{settings.GICATESIS_BASE_URL}/assets/{path}"
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(url)
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail="Failed to fetch asset") from e

    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail="Asset not found")
    if resp.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Upstream error {resp.status_code}")

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


# =============================================================================
# N8N INTEGRATION CONTRACTS
# =============================================================================

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

    return {
        "ok": True,
        "status": "ai_received",
        "projectId": payload.projectId,
        "project": updated,
    }


@router.post("/sim/n8n/run")
async def run_n8n_simulation(projectId: str = Query(..., description="Project id to simulate")):
    """Execute local n8n simulation and persist ai_result/artifacts."""
    project = projects.get_project(projectId)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    format_detail_payload: Optional[Dict[str, Any]] = None
    format_id = project.get("format_id")
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

    run_id = f"sim-{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d%H%M%S')}"
    output = n8n_specs.build_simulated_output(project_id=projectId, run_id=run_id)
    payload_values = spec.get("request", {}).get("payload", {}).get("values", {})
    prompt_text = spec.get("promptDetail", {}).get("text", "")
    format_definition = spec.get("formatDefinition", {})
    output["aiResult"]["sections"] = _build_sim_sections(
        values=payload_values if isinstance(payload_values, dict) else {},
        prompt_text=str(prompt_text or ""),
        format_definition=format_definition if isinstance(format_definition, dict) else {},
    )

    updated = projects.mark_simulated(
        project_id=projectId,
        ai_result=output["aiResult"],
        run_id=run_id,
        artifacts=output["artifacts"],
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Project not found")

    return {
        "ok": True,
        "mode": "simulation",
        "projectId": projectId,
        "runId": run_id,
        "status": "simulated",
        "aiResult": output["aiResult"],
        "artifacts": output["artifacts"],
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

    project = projects.create_project(
        {
            "title": payload.title,
            "prompt_id": payload.prompt_id,
            "prompt_name": prompt.get("name") if prompt else None,
            "prompt_template": prompt.get("template") if prompt else None,
            "format_id": format_id,
            "format_name": payload.format_name or format_id,
            "format_version": payload.format_version,
            "variables": payload.variables or {},
            "values": payload.variables or {},
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
        update_payload["variables"] = variables
        update_payload["values"] = variables

    updated = projects.update_project(
        project_id,
        update_payload,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Project not found")
    return updated


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


@router.get("/sim/download/docx")
def sim_download_docx(projectId: str, runId: Optional[str] = None):
    project = projects.get_project(projectId)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    file_path = build_simulated_docx(project, run_id=runId)
    projects.update_project(projectId, {"status": "completed"})
    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@router.get("/sim/download/pdf")
def sim_download_pdf(projectId: str, runId: Optional[str] = None):
    project = projects.get_project(projectId)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    file_path = build_simulated_pdf(project, run_id=runId)
    projects.update_project(projectId, {"status": "completed"})
    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type="application/pdf",
    )


async def _generation_job(project_id: str, format_name: str, prompt_name: str, variables: Dict[str, Any]):
    # Try n8n (real mode)
    try:
        callback_url = f"{settings.GICAGEN_BASE_URL.rstrip('/')}/api/integrations/n8n/callback"
        payload = {
            "project_id": project_id,
            "format_name": format_name,
            "prompt_name": prompt_name,
            "variables": variables,
            "callback_url": callback_url,
        }
        r = await n8n.trigger(payload)
        if r.get("ok"):
            # Real mode expects callback later.
            return
    except Exception:
        pass

    # Demo mode: generate locally
    out_path = Path("outputs") / f"{project_id}.docx"
    build_demo_docx(
        output_path=str(out_path),
        title=f"{prompt_name} - {format_name}",
        sections=["Capitulo 1", "Capitulo 2", "Capitulo 3", "Capitulo 4", "Referencias"],
        variables=variables,
    )
    await asyncio.sleep(0.8)
    projects.mark_completed(project_id, str(out_path))


@router.post("/projects/generate")
def generate(payload: ProjectGenerateIn, background: BackgroundTasks):
    """
    Legacy endpoint kept for backward compatibility.

    Wizard v2 now uses:
    - POST /api/projects/draft
    - GET /api/integrations/n8n/spec
    """
    prompt = prompts.get_prompt(payload.prompt_id)
    if not prompt:
        raise HTTPException(status_code=400, detail="Invalid prompt_id")

    format_name = payload.format_id
    project = projects.create_project(
        {
            "title": payload.title or payload.variables.get("tema"),
            "prompt_id": payload.prompt_id,
            "prompt_name": prompt.get("name"),
            "prompt_template": prompt.get("template"),
            "format_id": payload.format_id,
            "format_name": format_name,
            "variables": payload.variables or {},
            "values": payload.variables or {},
            "status": "processing",
        }
    )

    background.add_task(
        _generation_job,
        project["id"],
        format_name,
        prompt.get("name", "Prompt"),
        payload.variables or {},
    )
    return project


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
