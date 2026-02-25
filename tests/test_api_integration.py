"""Integration tests for API endpoints using FastAPI TestClient."""

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    """Provide a TestClient instance for the FastAPI app."""
    return TestClient(app)


# =============================================================================
# HEALTH ENDPOINTS
# =============================================================================


class TestHealthEndpoints:
    def test_healthz(self, client):
        r = client.get("/healthz")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert "app" in data
        assert "env" in data

    def test_ai_health(self, client):
        r = client.get("/api/ai/health")
        assert r.status_code == 200
        data = r.json()
        assert "configured" in data
        assert "engine" in data
        assert "availableProviders" in data
        if data["configured"]:
            assert data["engine"] in ("gemini", "mistral", "openrouter")
            assert "model" in data

    def test_providers_status(self, client):
        r = client.get("/api/providers/status")
        assert r.status_code == 200
        data = r.json()
        assert "selected_provider" in data
        assert "selected_model" in data
        assert "fallback_provider" in data
        assert "fallback_model" in data
        assert "mode" in data
        assert isinstance(data.get("providers"), list)
        if data.get("providers"):
            provider_ids = {item.get("id") for item in data["providers"] if isinstance(item, dict)}
            assert "gemini" in provider_ids
            assert "mistral" in provider_ids
            assert "openrouter" in provider_ids
            first = data["providers"][0]
            assert "last_probe_status" in first
            assert "last_probe_checked_at" in first

    def test_providers_probe(self, client):
        probe_payload = {
            "selected_provider": "gemini",
            "selected_model": "gemini-2.0-flash",
            "fallback_provider": "mistral",
            "fallback_model": "mistral-medium-2505",
            "mode": "auto",
            "providers": [
                {
                    "id": "gemini",
                    "health": "RATE_LIMITED",
                    "last_probe_status": "RATE_LIMITED",
                    "last_probe_checked_at": "2026-02-19T12:00:00Z",
                    "last_probe_detail": "retry after 10s",
                    "last_probe_retry_after_s": 10,
                    "rate_limit": {"remaining": 0, "limit": 60, "reset_seconds": 10},
                    "quota": {"remaining": None, "limit": None},
                    "stats": {"avg_latency_ms": 0, "errors_last_15m": 1, "last_error": "rate"},
                }
            ],
        }
        with patch(
            "app.modules.api.router.ai_service.probe_providers",
            return_value=probe_payload,
        ):
            r = client.post("/api/providers/probe")

        assert r.status_code == 200
        data = r.json()
        assert data["providers"][0]["last_probe_status"] == "RATE_LIMITED"

    def test_providers_status_openrouter_offline_without_key(self, client):
        from app.modules.api import router as router_module

        with patch.object(router_module.ai_service._clients["openrouter"], "is_configured", return_value=False):
            r = client.get("/api/providers/status")

        assert r.status_code == 200
        payload = r.json()
        openrouter = next(item for item in payload["providers"] if item.get("id") == "openrouter")
        assert openrouter["configured"] is False
        assert openrouter["online"] is False

    def test_providers_select(self, client):
        selection_result = {
            "provider": "gemini",
            "model": "gemini-2.0-flash",
            "fallback_provider": "mistral",
            "fallback_model": "mistral-medium-2505",
            "mode": "auto",
        }
        status_result = {
            "selected_provider": "gemini",
            "selected_model": "gemini-2.0-flash",
            "fallback_provider": "mistral",
            "fallback_model": "mistral-medium-2505",
            "mode": "auto",
            "providers": [],
        }
        with (
            patch(
                "app.modules.api.router.ai_service.set_provider_selection",
                return_value=selection_result,
            ),
            patch(
                "app.modules.api.router.ai_service.providers_status_payload",
                return_value=dict(status_result),
            ),
        ):
            r = client.post(
                "/api/providers/select",
                json={
                    "provider": "gemini",
                    "model": "gemini-2.0-flash",
                    "fallback_provider": "mistral",
                    "fallback_model": "mistral-medium-2505",
                    "mode": "auto",
                },
            )

        assert r.status_code == 200
        payload = r.json()
        assert payload["selected_provider"] == "gemini"
        assert payload["mode"] == "auto"
        assert "selection" in payload

    def test_providers_select_persists_selection_in_project(self, client):
        draft = client.post(
            "/api/projects/draft",
            json={
                "title": "Project Provider Selection",
                "formatId": "demo-format",
                "promptId": "prompt_tesis_estandar",
                "values": {"tema": "Provider"},
            },
        )
        project_id = draft.json()["id"]

        r = client.post(
            f"/api/providers/select?projectId={project_id}",
            json={
                "provider": "mistral",
                "model": "mistral-medium-2505",
                "fallback_provider": "gemini",
                "fallback_model": "gemini-2.0-flash",
                "mode": "auto",
            },
        )
        assert r.status_code == 200
        payload = r.json()
        assert payload["selected_provider"] == "mistral"
        assert payload["projectId"] == project_id

        project = client.get(f"/api/projects/{project_id}").json()
        assert project["ai_selection"]["provider"] == "mistral"
        assert project["ai_selection"]["mode"] == "auto"

        status = client.get(f"/api/providers/status?projectId={project_id}")
        assert status.status_code == 200
        status_payload = status.json()
        assert status_payload["selected_provider"] == "mistral"
        assert status_payload["projectId"] == project_id

    def test_providers_select_normalizes_model_provider_mismatch(self, client):
        draft = client.post(
            "/api/projects/draft",
            json={
                "title": "Project Provider Normalization",
                "formatId": "demo-format",
                "promptId": "prompt_tesis_estandar",
                "values": {"tema": "Provider"},
            },
        )
        project_id = draft.json()["id"]

        response = client.post(
            f"/api/providers/select?projectId={project_id}",
            json={
                "provider": "mistral",
                "model": "mistral-medium-2505",
                "fallback_provider": "gemini",
                # Intentional mismatch to verify backend normalization.
                "fallback_model": "mistral-medium-2505",
                "mode": "fixed",
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["selected_provider"] == "mistral"
        assert payload["fallback_provider"] == "gemini"
        assert payload["fallback_model"] == "gemini-2.0-flash"

        project = client.get(f"/api/projects/{project_id}").json()
        assert project["ai_selection"]["provider"] == "mistral"
        assert project["ai_selection"]["fallback_provider"] == "gemini"
        assert project["ai_selection"]["fallback_model"] == "gemini-2.0-flash"

    def test_providers_select_normalizes_primary_model_provider_mismatch(self, client):
        draft = client.post(
            "/api/projects/draft",
            json={
                "title": "Project Primary Model Normalization",
                "formatId": "demo-format",
                "promptId": "prompt_tesis_estandar",
                "values": {"tema": "Provider"},
            },
        )
        project_id = draft.json()["id"]

        response = client.post(
            f"/api/providers/select?projectId={project_id}",
            json={
                "provider": "gemini",
                # Intentional mismatch to verify backend normalization.
                "model": "mistral-medium-2505",
                "fallback_provider": "mistral",
                "fallback_model": "mistral-medium-2505",
                "mode": "fixed",
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["selected_provider"] == "gemini"
        assert payload["selected_model"] == "gemini-2.0-flash"

        project = client.get(f"/api/projects/{project_id}").json()
        assert project["ai_selection"]["provider"] == "gemini"
        assert project["ai_selection"]["model"] == "gemini-2.0-flash"

    def test_n8n_health_deprecated(self, client):
        r = client.get("/api/integrations/n8n/health")
        assert r.status_code == 200
        data = r.json()
        assert "configured" in data

    def test_build_info(self, client):
        r = client.get("/api/_meta/build")
        assert r.status_code == 200
        data = r.json()
        assert "service" in data
        assert "started_at" in data


# =============================================================================
# PROMPTS ENDPOINTS
# =============================================================================


class TestPromptsEndpoints:
    def test_list_prompts(self, client):
        r = client.get("/api/prompts")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)

    def test_create_and_delete_prompt(self, client):
        payload = {
            "name": "Test Prompt QA",
            "docType": "tesis",
            "template": "Escribe sobre {{tema}}.",
            "variables": ["tema"],
            "active": True,
        }
        r = client.post("/api/prompts", json=payload)
        assert r.status_code == 200
        created = r.json()
        assert "id" in created
        prompt_id = created["id"]

        r = client.get("/api/prompts")
        assert r.status_code == 200
        ids = [p["id"] for p in r.json()]
        assert prompt_id in ids

        r = client.delete(f"/api/prompts/{prompt_id}")
        assert r.status_code == 200

        r = client.get("/api/prompts")
        ids = [p["id"] for p in r.json()]
        assert prompt_id not in ids

    def test_update_prompt(self, client):
        payload = {
            "name": "Update Test",
            "docType": "informe",
            "template": "Original {{var}}.",
            "variables": ["var"],
            "active": True,
        }
        r = client.post("/api/prompts", json=payload)
        created = r.json()
        prompt_id = created["id"]

        updated_payload = {
            "name": "Updated Name",
            "docType": "informe",
            "template": "Updated {{var}}.",
            "variables": ["var"],
            "active": False,
        }
        r = client.put(f"/api/prompts/{prompt_id}", json=updated_payload)
        assert r.status_code == 200

        r = client.get("/api/prompts")
        prompt = next((p for p in r.json() if p["id"] == prompt_id), None)
        assert prompt is not None
        assert prompt["name"] == "Updated Name"

        client.delete(f"/api/prompts/{prompt_id}")


# =============================================================================
# PROJECTS ENDPOINTS
# =============================================================================


class TestProjectsEndpoints:
    def test_list_projects(self, client):
        r = client.get("/api/projects")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_create_draft(self, client):
        payload = {
            "title": "QA Test Draft",
            "formatId": "demo-format",
            "formatName": "Demo",
            "formatVersion": "1.0",
            "promptId": "prompt_tesis_estandar",
            "values": {"tema": "Testing"},
        }
        r = client.post("/api/projects/draft", json=payload)
        assert r.status_code == 201
        data = r.json()
        assert "id" in data
        assert data["status"] == "draft"

    def test_get_project_not_found(self, client):
        r = client.get("/api/projects/nonexistent-id-12345")
        assert r.status_code == 404

    def test_create_and_get_project(self, client):
        payload = {
            "title": "Get Test",
            "formatId": "demo",
            "promptId": "prompt_tesis_estandar",
            "values": {},
        }
        r = client.post("/api/projects/draft", json=payload)
        project_id = r.json()["id"]

        r = client.get(f"/api/projects/{project_id}")
        assert r.status_code == 200
        assert r.json()["id"] == project_id
        assert r.json()["title"] == "Get Test"


# =============================================================================
# GENERATION ENDPOINT
# =============================================================================


class TestGenerationEndpoint:
    def test_generate_nonexistent_project(self, client):
        r = client.post("/api/projects/nonexistent-id-99999/generate")
        assert r.status_code == 404

    def test_generate_returns_mode(self, client):
        payload = {
            "title": "Gen Test",
            "formatId": "demo",
            "promptId": "prompt_tesis_estandar",
            "values": {"tema": "Test"},
        }
        r = client.post("/api/projects/draft", json=payload)
        project_id = r.json()["id"]

        with patch("app.modules.api.router.ai_service.is_configured", return_value=True):
            with patch(
                "app.modules.api.router.formats.get_format_detail",
                new=AsyncMock(return_value={"definition": {}}),
            ):
                with patch("app.modules.api.router._ai_generation_job", return_value=None):
                    r = client.post(f"/api/projects/{project_id}/generate")

        assert r.status_code == 202
        data = r.json()
        assert data["ok"] is True
        assert data["status"] == "generating"
        assert "mode" in data

    def test_generate_trace_endpoint(self, client):
        payload = {
            "title": "Gen Trace Test",
            "formatId": "demo",
            "promptId": "prompt_tesis_estandar",
            "values": {"tema": "Trace"},
        }
        r = client.post("/api/projects/draft", json=payload)
        project_id = r.json()["id"]

        async def _fake_background_job(proj_id, run_id, **kwargs):
            from app.modules.api import router as router_module

            router_module._emit_project_trace(
                proj_id,
                step="ai.generate.section",
                status="running",
                title="IA: seccion 1/1 (Introduccion)",
                meta={"sectionIndex": 1, "sectionTotal": 1, "sectionPath": "Introduccion"},
            )
            router_module._emit_project_trace(
                proj_id,
                step="gicatesis.payload",
                status="running",
                title="Enviando payload a GicaTesis",
            )
            router_module._emit_project_trace(
                proj_id,
                step="gicatesis.render.docx",
                status="done",
                title="DOCX listo",
            )
            router_module._emit_project_trace(
                proj_id,
                step="gicatesis.render.pdf",
                status="done",
                title="PDF listo",
            )

        with patch("app.modules.api.router.ai_service.is_configured", return_value=True):
            with patch(
                "app.modules.api.router.formats.get_format_detail",
                new=AsyncMock(return_value={"definition": {}}),
            ):
                with patch(
                    "app.modules.api.router._ai_generation_job",
                    side_effect=_fake_background_job,
                ):
                    rr = client.post(f"/api/projects/{project_id}/generate")

        assert rr.status_code == 202

        trace_response = client.get(f"/api/projects/{project_id}/trace")
        assert trace_response.status_code == 200
        events = trace_response.json()["events"]
        steps = {evt.get("step") for evt in events}

        assert "generation.request.received" in steps
        assert "project.status.generating" in steps
        assert "ai.generate.section" in steps
        assert "gicatesis.payload" in steps
        assert "gicatesis.render.docx" in steps
        assert "gicatesis.render.pdf" in steps

    def test_generate_auto_resume_uses_saved_progress(self, client):
        from app.modules.api import router as router_module

        payload = {
            "title": "Resume Trigger Test",
            "formatId": "demo",
            "promptId": "prompt_tesis_estandar",
            "values": {"tema": "Resume"},
        }
        r = client.post("/api/projects/draft", json=payload)
        project_id = r.json()["id"]
        router_module.projects.update_project(
            project_id,
            {
                "status": "failed",
                "ai_result": {
                    "sections": [
                        {
                            "sectionId": "sec-0001",
                            "path": "Introduccion",
                            "content": "Contenido parcial",
                        }
                    ]
                },
                "resume": {
                    "eligible": True,
                    "saved_sections_count": 1,
                    "resume_from_index": 1,
                    "last_failed_section_path": "Introduccion",
                    "retry_count": 1,
                    "reason": "Error transitorio",
                    "updated_at": "2026-02-24T10:00:00",
                },
            },
        )

        with (
            patch("app.modules.api.router.ai_service.is_configured", return_value=True),
            patch(
                "app.modules.api.router._ai_generation_job",
                new=AsyncMock(return_value=None),
            ) as background_mock,
        ):
            response = client.post(f"/api/projects/{project_id}/generate", json={})

        assert response.status_code == 202
        data = response.json()
        assert data["resumeMode"] == "auto"
        assert data["savedSections"] == 1
        assert data["resumeFromSection"] == 2
        assert background_mock.call_args.kwargs["resume_from_partial"] is True
        assert len(background_mock.call_args.kwargs["resume_seed_sections"]) == 1

    def test_generate_restart_mode_ignores_saved_progress(self, client):
        from app.modules.api import router as router_module

        payload = {
            "title": "Restart Trigger Test",
            "formatId": "demo",
            "promptId": "prompt_tesis_estandar",
            "values": {"tema": "Restart"},
        }
        r = client.post("/api/projects/draft", json=payload)
        project_id = r.json()["id"]
        router_module.projects.update_project(
            project_id,
            {
                "status": "failed",
                "ai_result": {
                    "sections": [
                        {
                            "sectionId": "sec-0001",
                            "path": "Introduccion",
                            "content": "Contenido parcial",
                        }
                    ]
                },
                "resume": {
                    "eligible": True,
                    "saved_sections_count": 1,
                    "resume_from_index": 1,
                    "last_failed_section_path": "Introduccion",
                    "retry_count": 1,
                },
            },
        )

        with (
            patch("app.modules.api.router.ai_service.is_configured", return_value=True),
            patch(
                "app.modules.api.router._ai_generation_job",
                new=AsyncMock(return_value=None),
            ) as background_mock,
        ):
            response = client.post(
                f"/api/projects/{project_id}/generate",
                json={"resumeMode": "restart"},
            )

        assert response.status_code == 202
        data = response.json()
        assert data["resumeMode"] == "restart"
        assert data["savedSections"] == 0
        assert data["resumeFromSection"] == 1
        assert background_mock.call_args.kwargs["resume_from_partial"] is False
        assert background_mock.call_args.kwargs["resume_seed_sections"] == []

    def test_generate_returns_accepted_quickly(self, client):
        payload = {
            "title": "Gen Async Test",
            "formatId": "demo",
            "promptId": "prompt_tesis_estandar",
            "values": {"tema": "Async"},
        }
        r = client.post("/api/projects/draft", json=payload)
        project_id = r.json()["id"]

        with (
            patch("app.modules.api.router.ai_service.is_configured", return_value=True),
            patch(
                "app.modules.api.router._ai_generation_job",
                new=AsyncMock(return_value=None),
            ),
        ):
            start = time.perf_counter()
            response = client.post(f"/api/projects/{project_id}/generate")
            elapsed = time.perf_counter() - start

        assert response.status_code == 202
        # CI/local variance on Windows can be high due background task scheduling
        # and JSON store I/O; endpoint must still return quickly (non-blocking).
        assert elapsed < 5.0

    def test_background_job_updates_progress(self, client):
        from app.modules.api import router as router_module

        payload = {
            "title": "Progress Test",
            "formatId": "demo",
            "promptId": "prompt_tesis_estandar",
            "values": {"tema": "Progress"},
        }
        r = client.post("/api/projects/draft", json=payload)
        project_id = r.json()["id"]

        def _fake_generate(project, format_detail, prompt, **kwargs):
            progress_cb = kwargs.get("progress_cb")
            if callable(progress_cb):
                progress_cb(1, 3, "Introduccion", "gemini", stage="section_start")
            raise RuntimeError("forced failure")

        with (
            patch(
                "app.modules.api.router.formats.get_format_detail",
                new=AsyncMock(return_value={"definition": {"cuerpo": {"capitulos": [{"titulo": "Uno"}]}}}),
            ),
            patch("app.modules.api.router.ai_service.generate", side_effect=_fake_generate),
        ):
            asyncio.run(router_module._ai_generation_job(project_id, "gemini-test-run"))

        project = client.get(f"/api/projects/{project_id}").json()
        assert project["status"] == "failed"
        assert project["progress"]["current"] > 0
        assert project["progress"]["total"] > 0
        assert project["progress"]["currentPath"] == "Introduccion"

    def test_fallback_event_recorded_on_quota_error(self, client):
        from app.core.services.ai.errors import QuotaExceededError
        from app.modules.api import router as router_module

        payload = {
            "title": "Fallback Event Test",
            "formatId": "demo",
            "promptId": "prompt_tesis_estandar",
            "values": {"tema": "Fallback"},
        }
        r = client.post("/api/projects/draft", json=payload)
        project_id = r.json()["id"]

        def _fake_generate(project, format_detail, prompt, **kwargs):
            progress_cb = kwargs.get("progress_cb")
            if callable(progress_cb):
                progress_cb(2, 10, "Marco teorico", "mistral", stage="provider_fallback")
            raise QuotaExceededError(
                "Quota exceeded. Check Gemini project quota/billing.",
                provider="gemini",
                retry_after=15,
            )

        with (
            patch(
                "app.modules.api.router.formats.get_format_detail",
                new=AsyncMock(return_value={"definition": {"cuerpo": {"capitulos": [{"titulo": "Uno"}]}}}),
            ),
            patch("app.modules.api.router.ai_service.generate", side_effect=_fake_generate),
        ):
            asyncio.run(router_module._ai_generation_job(project_id, "gemini-quota-run"))

        trace_response = client.get(f"/api/projects/{project_id}/trace")
        assert trace_response.status_code == 200
        events = trace_response.json()["events"]
        assert any(
            evt.get("stage") == "provider_fallback" or evt.get("step") == "ai.provider.fallback" for evt in events
        )


# =============================================================================
# INVALID INPUTS (4xx)
# =============================================================================


class TestInvalidInputs:
    def test_create_draft_empty_body(self, client):
        r = client.post("/api/projects/draft", json={})
        assert r.status_code in (200, 201, 422)

    def test_delete_nonexistent_prompt(self, client):
        r = client.delete("/api/prompts/nonexistent-id-xyz")
        assert r.status_code in (200, 404)

    def test_update_nonexistent_prompt(self, client):
        payload = {
            "name": "Ghost",
            "docType": "tesis",
            "template": "{{x}}",
            "variables": ["x"],
            "active": True,
        }
        r = client.put("/api/prompts/nonexistent-id-xyz", json=payload)
        assert r.status_code in (200, 404)

    def test_download_nonexistent_project(self, client):
        r = client.get("/api/download/nonexistent-id-999")
        assert r.status_code >= 400
