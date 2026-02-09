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
from app.core.services.definition_compiler import compile_definition_to_section_index
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

    ai_result = {
        "sections": sim_sections
    }

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

    values = project.get("values") if isinstance(project.get("values"), dict) else {}
    ai_result = project.get("ai_result") if isinstance(project.get("ai_result"), dict) else {"sections": []}

    url = f"{settings.GICATESIS_BASE_URL.rstrip('/')}/render/docx"
    payload = {
        "formatId": format_id,
        "values": values,
        "mode": "simulation",
        "aiResult": ai_result,
    }

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
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Failed to reach GicaTesis: {exc}")

    projects.update_project(projectId, {"status": "completed"})
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

    values = project.get("values") if isinstance(project.get("values"), dict) else {}
    ai_result = project.get("ai_result") if isinstance(project.get("ai_result"), dict) else {"sections": []}

    url = f"{settings.GICATESIS_BASE_URL.rstrip('/')}/render/pdf"
    payload = {
        "formatId": format_id,
        "values": values,
        "mode": "simulation",
        "aiResult": ai_result,
    }

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
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Failed to reach GicaTesis: {exc}")

    projects.update_project(projectId, {"status": "completed"})
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


# =============================================================================
# RENDER PROXY ENDPOINTS - Forward to GicaTesis Real Generators
# =============================================================================
# These endpoints proxy to GicaTesis /api/v1/render/* which uses the REAL
# generator scripts. This ensures DOCX/PDF are VISUALLY IDENTICAL to those
# generated by GicaTesis UI (same logos, fonts, margins, styles).

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
    
    values = project.get("values", {})
    ai_result = project.get("ai_result") if isinstance(project.get("ai_result"), dict) else {"sections": []}
    
    # Proxy to GicaTesis render endpoint
    url = f"{settings.GICATESIS_BASE_URL}/render/docx"
    payload = {
        "formatId": format_id,
        "values": values,
        "mode": "simulation",
        "aiResult": ai_result,
    }
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            
            # Stream the binary response back to client
            content_disposition = response.headers.get(
                "content-disposition", 
                f'attachment; filename="gicatesis-{format_id}.docx"'
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
            raise HTTPException(status_code=exc.response.status_code, detail=upstream_detail)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Failed to reach GicaTesis: {exc}")


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
    
    values = project.get("values", {})
    ai_result = project.get("ai_result") if isinstance(project.get("ai_result"), dict) else {"sections": []}
    
    # Proxy to GicaTesis render endpoint
    url = f"{settings.GICATESIS_BASE_URL}/render/pdf"
    payload = {
        "formatId": format_id,
        "values": values,
        "mode": "simulation",
        "aiResult": ai_result,
    }
    
    async with httpx.AsyncClient(timeout=180.0) as client:
        try:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            
            content_disposition = response.headers.get(
                "content-disposition",
                f'attachment; filename="gicatesis-{format_id}.pdf"'
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
            raise HTTPException(status_code=exc.response.status_code, detail=upstream_detail)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Failed to reach GicaTesis: {exc}")
