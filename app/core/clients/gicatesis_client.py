"""
GicaTesis Client - HTTP client for calling GicaTesis Generation API.

This client handles:
1. POST /api/v1/generate - Request document generation
2. Streaming artifact downloads from /api/v1/artifacts/{runId}/*
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# Timeout for generation requests (may take time for PDF conversion)
GENERATION_TIMEOUT = 120.0


class GenerationArtifact:
    """Info about a generated artifact."""
    def __init__(self, type: str, download_url: str):
        self.type = type
        self.download_url = download_url


class GenerationResponse:
    """Response from generation endpoint."""
    def __init__(
        self,
        project_id: str,
        run_id: str,
        status: str,
        artifacts: List[GenerationArtifact],
        error: Optional[str] = None,
    ):
        self.project_id = project_id
        self.run_id = run_id
        self.status = status
        self.artifacts = artifacts
        self.error = error


class GicaTesisClient:
    """HTTP client for GicaTesis Generation API."""

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = (base_url or settings.GICATESIS_BASE_URL).rstrip("/")

    async def generate(
        self,
        project_id: str,
        format_id: str,
        values: Optional[Dict[str, Any]] = None,
        ai_result: Optional[Dict[str, Any]] = None,
        mode: str = "simulation",
    ) -> GenerationResponse:
        """
        Request document generation from GicaTesis.
        
        Args:
            project_id: Project identifier
            format_id: Format to generate
            values: User values for placeholders
            ai_result: AI-generated content
            mode: Generation mode ('simulation' or 'production')
        
        Returns:
            GenerationResponse with artifact URLs
        """
        url = f"{self.base_url}/generate"
        
        payload = {
            "projectId": project_id,
            "formatId": format_id,
            "mode": mode,
            "values": values or {},
        }
        
        if ai_result:
            payload["aiResult"] = ai_result

        logger.info("Calling GicaTesis generate: %s", url)

        headers = {}
        if settings.GICATESIS_API_KEY:
            headers["X-GICATESIS-KEY"] = settings.GICATESIS_API_KEY

        async with httpx.AsyncClient(timeout=GENERATION_TIMEOUT) as client:
            try:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
                
                artifacts = [
                    GenerationArtifact(
                        type=a.get("type", ""),
                        download_url=a.get("downloadUrl", ""),
                    )
                    for a in data.get("artifacts", [])
                ]
                
                return GenerationResponse(
                    project_id=data.get("projectId", project_id),
                    run_id=data.get("runId", ""),
                    status=data.get("status", "error"),
                    artifacts=artifacts,
                    error=data.get("error"),
                )
            except httpx.HTTPStatusError as exc:
                logger.error("GicaTesis generate failed: %s", exc)
                error_detail = "Generation failed"
                try:
                    error_detail = exc.response.json().get("detail", error_detail)
                except Exception:
                    pass
                return GenerationResponse(
                    project_id=project_id,
                    run_id="",
                    status="error",
                    artifacts=[],
                    error=error_detail,
                )
            except Exception as exc:
                logger.error("GicaTesis generate error: %s", exc)
                return GenerationResponse(
                    project_id=project_id,
                    run_id="",
                    status="error",
                    artifacts=[],
                    error=str(exc),
                )
