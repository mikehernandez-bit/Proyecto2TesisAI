"""
API Router - BFF Endpoints

Exposes internal API endpoints for the frontend.
Frontend calls these endpoints, NOT GicaTesis directly.

Includes:
- /api/formats/* - BFF for GicaTesis Formats API
- /api/prompts/* - Prompt CRUD
- /api/projects/* - Project CRUD and generation
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse

from app.core.services.format_service import FormatService
from app.core.services.prompt_service import PromptService
from app.core.services.project_service import ProjectService
from app.core.services.docx_builder import build_demo_docx
from app.core.services.n8n_client import N8NClient
from app.modules.api.models import PromptIn, ProjectGenerateIn
from app.integrations.gicatesis.errors import (
    GicaTesisError,
    UpstreamUnavailable,
    UpstreamTimeout
)

router = APIRouter()

# Service instances
formats = FormatService()
prompts = PromptService()
projects = ProjectService()
n8n = N8NClient()


# =============================================================================
# FORMATS BFF ENDPOINTS (proxies to GicaTesis via FormatService)
# =============================================================================

@router.get("/formats/version")
async def get_formats_version():
    """
    BFF: Check catalog version.
    
    Proxies to GicaTesis /api/v1/formats/version
    Returns version hash and whether catalog changed.
    """
    try:
        return await formats.check_version()
    except UpstreamUnavailable:
        raise HTTPException(
            status_code=502,
            detail="GicaTesis no disponible"
        )
    except UpstreamTimeout:
        raise HTTPException(
            status_code=504,
            detail="GicaTesis timeout"
        )
    except GicaTesisError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Error de GicaTesis: {e}"
        )


@router.get("/formats")
async def list_formats(
    university: Optional[str] = None,
    category: Optional[str] = None,
    documentType: Optional[str] = None
):
    """
    BFF: List formats with optional filters.
    
    Proxies to GicaTesis /api/v1/formats with caching.
    Uses ETag/304 for efficient sync.
    Falls back to cache if GicaTesis unavailable.
    
    Query params:
    - university: Filter by university code (e.g., "unac")
    - category: Filter by category (e.g., "informe")
    - documentType: Filter by document type (e.g., "cual")
    
    Returns:
    - formats: List of FormatSummary
    - stale: True if using stale cache
    - cachedAt: Last sync timestamp
    """
    try:
        return await formats.list_formats(
            university=university,
            category=category,
            document_type=documentType
        )
    except UpstreamUnavailable:
        raise HTTPException(
            status_code=502,
            detail="GicaTesis no disponible y no hay cache"
        )
    except GicaTesisError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Error de GicaTesis: {e}"
        )


@router.get("/formats/{format_id}")
async def get_format_detail(format_id: str):
    """
    BFF: Get full format detail.
    
    Proxies to GicaTesis /api/v1/formats/{id}
    Caches detail for future requests.
    
    Returns FormatDetail with fields for wizard.
    """
    try:
        detail = await formats.get_format_detail(format_id)
        if not detail:
            raise HTTPException(
                status_code=404,
                detail=f"Formato no encontrado: {format_id}"
            )
        return detail
    except UpstreamUnavailable:
        raise HTTPException(
            status_code=502,
            detail="GicaTesis no disponible"
        )
    except UpstreamTimeout:
        raise HTTPException(
            status_code=504,
            detail="GicaTesis timeout"
        )
    except GicaTesisError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Error de GicaTesis: {e}"
        )


@router.get("/assets/{path:path}")
async def proxy_asset(path: str):
    """
    BFF: Proxy for GicaTesis assets (logos, images).
    
    Serves images from GicaTesis avoiding CORS issues.
    Example: /api/assets/logos/unac.png
    """
    import httpx
    from fastapi import Response
    from app.core.config import settings

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

    return Response(
        content=resp.content,
        media_type=resp.headers.get("content-type"),
    )


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


@router.get("/projects/{project_id}")
def get_project(project_id: str):
    p = projects.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return p


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


async def _generation_job(project_id: str, format_name: str, prompt_name: str, variables: Dict[str, Any]):
    # Try n8n (real mode)
    try:
        payload = {"project_id": project_id, "format_name": format_name, "prompt_name": prompt_name, "variables": variables}
        r = await n8n.trigger(payload)
        if r.get("ok"):
            # Real mode expects callback later: /api/n8n/callback/{project_id}
            return
    except Exception:
        pass

    # Demo mode: generate locally
    out_path = Path("outputs") / f"{project_id}.docx"
    build_demo_docx(
        output_path=str(out_path),
        title=f"{prompt_name} - {format_name}",
        sections=["Capítulo 1", "Capítulo 2", "Capítulo 3", "Capítulo 4", "Referencias"],
        variables=variables,
    )
    await asyncio.sleep(0.8)
    projects.mark_completed(project_id, str(out_path))


@router.post("/projects/generate")
def generate(payload: ProjectGenerateIn, background: BackgroundTasks):
    prompt = prompts.get_prompt(payload.prompt_id)
    if not prompt:
        raise HTTPException(status_code=400, detail="Invalid prompt_id")

    format_name = payload.format_id  # TODO: if you have formats DB, map id->name

    project = projects.create_project({
        "title": payload.title or payload.variables.get("tema"),
        "prompt_id": payload.prompt_id,
        "prompt_name": prompt.get("name"),
        "format_id": payload.format_id,
        "format_name": format_name,
    })

    background.add_task(_generation_job, project["id"], format_name, prompt.get("name", "Prompt"), payload.variables or {})
    return project


@router.post("/n8n/callback/{project_id}")
def n8n_callback(project_id: str, body: Dict[str, Any]):
    """Callback endpoint for n8n to finalize a project.

    Suggested body:
      { "status": "completed", "file_path": "outputs/proj_xxx.docx" }
      { "status": "failed", "error": "..." }

    TODO (DEV): if n8n returns URL/bytes, download/save into /outputs then mark_completed.
    """
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
