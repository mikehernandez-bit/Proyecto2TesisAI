from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse

from app.core.services.format_api import FormatService
from app.core.services.prompt_service import PromptService
from app.core.services.project_service import ProjectService
from app.core.services.docx_builder import build_demo_docx
from app.core.services.n8n_client import N8NClient
from app.modules.api.models import PromptIn, ProjectGenerateIn

router = APIRouter()

formats = FormatService()
prompts = PromptService()
projects = ProjectService()
n8n = N8NClient()

@router.get("/formats")
async def list_formats(university: Optional[str] = None, career: Optional[str] = None):
    return await formats.list_formats(university=university, career=career)

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
