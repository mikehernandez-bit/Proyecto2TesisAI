"""Integration tests for API endpoints using FastAPI TestClient."""

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.services.pricing import PricingService
from app.core.services.project_service import ProjectService
from app.main import app


@pytest.fixture
def client(tmp_path):
    """Provide a TestClient instance for the FastAPI app."""
    from app.modules.api import router as router_module

    original_projects = router_module.projects
    original_pricing = router_module.pricing_service
    router_module.projects = ProjectService(str(tmp_path / "projects.json"))
    router_module.pricing_service = PricingService(path=str(tmp_path / "model_pricing.json"))
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        router_module.projects = original_projects
        router_module.pricing_service = original_pricing


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
        assert r.status_code == 201
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

    def test_project_budget_uses_historical_tokens_and_selected_model(self, client):
        from app.modules.api import router as router_module

        payload = {
            "title": "Proyecto presupuesto",
            "formatId": "demo",
            "promptId": "prompt_tesis_estandar",
            "values": {"tema": "Costo historico"},
        }
        response = client.post("/api/projects/draft", json=payload)
        project_id = response.json()["id"]

        router_module.projects.update_project(
            project_id,
            {
                "status": "completed",
                "token_usage": {
                    "attempts": [
                        {
                            "provider": "mistral",
                            "model": "mistral-medium-2505",
                            "section_id": "sec-1",
                            "section_path": "Introduccion",
                            "section_title": "Introduccion",
                            "input_tokens": 1000,
                            "output_tokens": 350,
                            "total_tokens": 1350,
                            "attempt": 1,
                            "timestamp": "2026-03-20T10:00:00Z",
                            "estimated": False,
                            "source": "reported_by_provider",
                            "success": True,
                        },
                        {
                            "provider": "mistral",
                            "model": "mistral-medium-2505",
                            "section_id": "sec-2",
                            "section_path": "Marco teorico",
                            "section_title": "Marco teorico",
                            "input_tokens": 1400,
                            "output_tokens": 550,
                            "total_tokens": 1950,
                            "attempt": 1,
                            "timestamp": "2026-03-20T10:01:00Z",
                            "estimated": False,
                            "source": "reported_by_provider",
                            "success": True,
                        },
                    ],
                    "current_section": {
                        "section_id": "sec-2",
                        "section_path": "Marco teorico",
                        "section_title": "Marco teorico",
                    },
                    "input_tokens_total": 2400,
                    "output_tokens_total": 900,
                    "total_tokens": 3300,
                    "calls_total": 2,
                    "reported_calls": 2,
                    "estimated_calls": 0,
                    "has_estimated_usage": False,
                    "sections": [
                        {
                            "section_id": "sec-1",
                            "section_path": "Introduccion",
                            "section_title": "Introduccion",
                            "input_tokens_total": 1000,
                            "output_tokens_total": 350,
                            "total_tokens": 1350,
                        }
                    ],
                    "providers": [
                        {
                            "provider": "mistral",
                            "model": "mistral-medium-2505",
                            "input_tokens_total": 2400,
                            "output_tokens_total": 900,
                            "total_tokens": 3300,
                        }
                    ],
                },
            },
        )

        with (
            patch.object(
                router_module.pricing_service,
                "list_pricing_catalog",
                return_value=[
                    {
                        "provider": "openai",
                        "model": "gpt-5.4-mini",
                        "input_price_per_1m_tokens": 0.4,
                        "output_price_per_1m_tokens": 3.2,
                        "cached_input_price_per_1m_tokens": 0.04,
                        "currency": "USD",
                        "pricing_mode": "cached_input_supported",
                        "threshold_rule": "",
                        "modality": "text",
                        "source_url": "https://openai.com/es-419/api/pricing/",
                        "fetched_at": "2026-03-20T10:00:00Z",
                        "pricing_source": "updated",
                        "is_cached_fallback": False,
                        "available": True,
                    },
                    {
                        "provider": "google",
                        "model": "gemini-2.0-flash",
                        "canonical_model_id": "google/gemini-2.0-flash",
                        "display_name": "Google: Gemini 2.0 Flash",
                        "input_price_per_1m_tokens": 0.1,
                        "output_price_per_1m_tokens": 0.4,
                        "cached_input_price_per_1m_tokens": 0.025,
                        "currency": "USD",
                        "pricing_mode": "tiered",
                        "threshold_rule": "texto <= 200000 tokens",
                        "modality": "text",
                        "source_url": "https://openrouter.ai/api/v1/models",
                        "fetched_at": "2026-03-20T10:00:00Z",
                        "pricing_source": "updated",
                        "pricing_origin": "openrouter_api",
                        "is_cached_fallback": False,
                        "available": True,
                    },
                ],
            ),
            patch.object(
                router_module.pricing_service,
                "get_pricing",
                return_value={
                    "provider": "google",
                    "model": "gemini-2.0-flash",
                    "canonical_model_id": "google/gemini-2.0-flash",
                    "display_name": "Google: Gemini 2.0 Flash",
                    "input_price_per_1m_tokens": 0.1,
                    "output_price_per_1m_tokens": 0.4,
                    "cached_input_price_per_1m_tokens": 0.025,
                    "currency": "USD",
                    "pricing_mode": "tiered",
                    "threshold_rule": "texto <= 200000 tokens",
                    "modality": "text",
                    "source_url": "https://openrouter.ai/api/v1/models",
                    "fetched_at": "2026-03-20T10:00:00Z",
                    "pricing_source": "updated",
                    "pricing_origin": "openrouter_api",
                    "is_cached_fallback": False,
                    "available": True,
                },
            ),
        ):
            budget_response = client.get(f"/api/projects/{project_id}/budget?provider=gemini&model=gemini-2.0-flash")

        assert budget_response.status_code == 200
        budget = budget_response.json()
        assert budget["project"]["id"] == project_id
        assert budget["usage"]["input_tokens_total"] == 2400
        assert budget["usage"]["output_tokens_total"] == 900
        assert budget["selected_pricing"]["provider"] == "google"
        assert budget["selected_pricing"]["model"] == "gemini-2.0-flash"
        assert budget["selected_pricing"]["pricing_origin"] == "openrouter_api"
        assert budget["estimate"]["estimated_total_cost"] == pytest.approx(0.0006)
        assert budget["comparisons"][0]["provider"] == "google"
        assert budget["comparisons"][0]["estimated_total_cost"] == pytest.approx(0.0006)
        assert budget["usage"]["sections"][0]["section_path"] == "Introduccion"

    def test_update_project_can_reset_generated_state_and_keep_wizard_state(self, client):
        from app.modules.api import router as router_module

        payload = {
            "title": "Reset project",
            "formatId": "demo",
            "promptId": "prompt_tesis_estandar",
            "values": {"tema": "Original"},
        }
        response = client.post("/api/projects/draft", json=payload)
        project_id = response.json()["id"]

        router_module.projects.update_project(
            project_id,
            {
                "status": "completed",
                "ai_result": {"sections": [{"sectionId": "sec-1", "path": "Introduccion", "content": "Texto"}]},
                "output_file": "outputs/reset.docx",
                "pdf_file": "outputs/reset.pdf",
                "generation_phase": {
                    "status": "completed",
                    "sections": [{"section_id": "sec-1", "section_path": "Introduccion"}],
                    "completed_sections": 1,
                    "total_sections": 1,
                },
            },
        )
        router_module.projects.append_event(
            project_id,
            {"ts": "2026-03-18T10:00:00Z", "stage": "ai.generate.section", "message": "done"},
        )

        update_response = client.put(
            f"/api/projects/{project_id}",
            json={
                "title": "Reset project actualizado",
                "values": {"tema": "Cambiado"},
                "wizardState": {
                    "currentStep": 3,
                    "lastCompletedStep": 4,
                    "lastOpenMode": "edit-details",
                },
                "resetGeneratedState": True,
            },
        )

        assert update_response.status_code == 200
        updated = update_response.json()
        assert updated["status"] == "draft"
        assert updated["title"] == "Reset project actualizado"
        assert updated["values"]["tema"] == "Cambiado"
        assert updated["ai_result"] is None
        assert updated["output_file"] is None
        assert updated["pdf_file"] is None
        assert updated["generation_phase"]["status"] == "idle"
        assert updated["construction_phase"]["status"] == "idle"
        assert updated["generation_snapshot"]["saved_sections_count"] == 0
        assert updated["wizard_state"]["current_step"] == 3
        assert updated["wizard_state"]["last_completed_step"] == 4
        trace = client.get(f"/api/projects/{project_id}/trace").json()
        assert trace["events"] == []

    def test_review_navigation_does_not_touch_project_updated_at(self, client):
        from app.modules.api import router as router_module

        payload = {
            "title": "Proyecto navegable",
            "formatId": "demo",
            "promptId": "prompt_tesis_estandar",
            "values": {"tema": "Sin cambios"},
        }
        response = client.post("/api/projects/draft", json=payload)
        project_id = response.json()["id"]

        items = router_module.projects.store.read_list()
        for item in items:
            if item["id"] == project_id:
                item["updated_at"] = "2026-03-18T10:00:00"
        router_module.projects.store.write_list(items)

        update_response = client.put(
            f"/api/projects/{project_id}",
            json={
                "wizardState": {
                    "currentStep": 5,
                    "lastCompletedStep": 5,
                    "lastOpenMode": "review",
                    "updatedAt": "2026-03-19T08:00:00",
                },
                "touchProjectTimestamp": False,
            },
        )

        assert update_response.status_code == 200
        updated = update_response.json()
        assert updated["updated_at"] == "2026-03-18T10:00:00"
        assert updated["wizard_state"]["current_step"] == 5
        assert updated["wizard_state"]["last_open_mode"] == "review"

    def test_download_project_does_not_touch_updated_at(self, client, tmp_path):
        from app.modules.api import router as router_module

        payload = {
            "title": "Proyecto descargable",
            "formatId": "demo",
            "promptId": "prompt_tesis_estandar",
            "values": {"tema": "Documento final"},
        }
        response = client.post("/api/projects/draft", json=payload)
        project_id = response.json()["id"]

        output_path = tmp_path / "sample.docx"
        output_path.write_bytes(b"docx")
        router_module.projects.update_project(
            project_id,
            {"status": "completed", "output_file": str(output_path)},
        )

        items = router_module.projects.store.read_list()
        for item in items:
            if item["id"] == project_id:
                item["updated_at"] = "2026-03-18T09:30:00"
        router_module.projects.store.write_list(items)

        download_response = client.get(f"/api/download/{project_id}")

        assert download_response.status_code == 200
        project = client.get(f"/api/projects/{project_id}").json()
        assert project["updated_at"] == "2026-03-18T09:30:00"

    def test_delete_project_removes_row_from_listing(self, client):
        payload = {
            "title": "Proyecto eliminable",
            "formatId": "demo",
            "promptId": "prompt_tesis_estandar",
            "values": {"tema": "Eliminar"},
        }
        response = client.post("/api/projects/draft", json=payload)
        project_id = response.json()["id"]

        delete_response = client.delete(f"/api/projects/{project_id}")

        assert delete_response.status_code == 200
        assert delete_response.json()["ok"] is True
        missing = client.get(f"/api/projects/{project_id}")
        assert missing.status_code == 404

    def test_home_includes_dashboard_resume_controls(self, client):
        response = client.get("/")
        assert response.status_code == 200
        html = response.text
        assert "/static/js/app.js?v=" in html
        assert "no-store" in response.headers.get("cache-control", "")
        assert 'id="dashboard-latest-card"' in html
        assert 'id="dashboard-latest-actions"' in html
        assert 'id="wizard-context-panel"' in html
        assert 'data-wizard-jump="1"' in html
        assert 'data-wizard-jump="4"' in html


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
                    ],
                    "tokenUsage": {
                        "attempts": [
                            {
                                "input_tokens": 50,
                                "output_tokens": 20,
                                "total_tokens": 70,
                                "provider": "gemini",
                                "model": "gemini-2.0-flash",
                                "phase": "generate_section",
                                "section_id": "sec-0001",
                                "section_path": "Introduccion",
                                "section_title": "Introduccion",
                                "attempt": 1,
                                "timestamp": "2026-03-17T10:00:00Z",
                                "estimated": False,
                                "source": "reported_by_provider",
                                "success": True,
                                "error": "",
                            }
                        ]
                    },
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
        project = client.get(f"/api/projects/{project_id}").json()
        assert project["generation_snapshot"]["saved_sections_count"] == 1
        assert project["generation_snapshot"]["completed_sections"][0]["path"] == "Introduccion"
        assert project["progress"]["tokenUsage"]["total_tokens"] == 70

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
        project = client.get(f"/api/projects/{project_id}").json()
        assert project["generation_snapshot"]["saved_sections_count"] == 0
        assert project["generation_snapshot"]["completed_sections"] == []

    def test_generate_render_failed_retries_render_only_without_ai(self, client):
        from app.modules.api import router as router_module

        payload = {
            "title": "Render Retry Test",
            "formatId": "demo",
            "promptId": "prompt_tesis_estandar",
            "values": {"tema": "Render retry"},
        }
        r = client.post("/api/projects/draft", json=payload)
        project_id = r.json()["id"]
        router_module.projects.update_project(
            project_id,
            {
                "status": "render_failed",
                "ai_result": {
                    "sections": [
                        {
                            "sectionId": "sec-0001",
                            "path": "Cronograma",
                            "content": "Contenido IA ya disponible.",
                        }
                    ]
                },
                "progress": {
                    "current": 1,
                    "total": 1,
                    "currentPath": "Cronograma",
                    "provider": "mistral",
                },
            },
        )

        with (
            patch("app.modules.api.router.ai_service.is_configured", return_value=False),
            patch(
                "app.modules.api.router._render_saved_ai_job",
                new=AsyncMock(return_value=None),
            ) as render_mock,
            patch(
                "app.modules.api.router._ai_generation_job",
                new=AsyncMock(return_value=None),
            ) as ai_mock,
        ):
            response = client.post(f"/api/projects/{project_id}/generate", json={})

        assert response.status_code == 202
        data = response.json()
        assert data["mode"] == "render_only"
        assert data["status"] == "rendering"
        assert render_mock.call_args.args[0] == project_id
        assert ai_mock.call_count == 0

        project = client.get(f"/api/projects/{project_id}").json()
        assert project["status"] == "rendering"

    def test_generate_render_failed_restart_forces_new_ai_run(self, client):
        from app.modules.api import router as router_module

        payload = {
            "title": "Render Restart Test",
            "formatId": "demo",
            "promptId": "prompt_tesis_estandar",
            "values": {"tema": "Restart from render"},
        }
        r = client.post("/api/projects/draft", json=payload)
        project_id = r.json()["id"]
        router_module.projects.update_project(
            project_id,
            {
                "status": "render_failed",
                "ai_result": {
                    "sections": [
                        {
                            "sectionId": "sec-0001",
                            "path": "Introduccion",
                            "content": "Contenido previo",
                        }
                    ]
                },
            },
        )

        with (
            patch("app.modules.api.router.ai_service.is_configured", return_value=True),
            patch(
                "app.modules.api.router._render_saved_ai_job",
                new=AsyncMock(return_value=None),
            ) as render_mock,
            patch(
                "app.modules.api.router._ai_generation_job",
                new=AsyncMock(return_value=None),
            ) as ai_mock,
        ):
            response = client.post(
                f"/api/projects/{project_id}/generate",
                json={"resumeMode": "restart"},
            )

        assert response.status_code == 202
        data = response.json()
        assert data["mode"] == "async"
        assert data["status"] == "generating"
        assert data["resumeMode"] == "restart"
        assert render_mock.call_count == 0
        assert ai_mock.call_count == 1

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
        assert elapsed < 8.0

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

    def test_background_job_persists_token_usage_for_step5(self, client):
        from app.modules.api import router as router_module

        payload = {
            "title": "Token Progress Test",
            "formatId": "demo",
            "promptId": "prompt_tesis_estandar",
            "values": {"tema": "Tokens"},
        }
        response = client.post("/api/projects/draft", json=payload)
        project_id = response.json()["id"]

        usage_snapshot = {
            "input_tokens_total": 120,
            "output_tokens_total": 45,
            "total_tokens": 165,
            "calls_total": 1,
            "reported_calls": 1,
            "estimated_calls": 0,
            "has_estimated_usage": False,
            "current_section": {
                "section_id": "sec-0001",
                "section_path": "Introduccion",
                "section_title": "Introduccion",
            },
            "last_call": {
                "provider": "gemini",
                "model": "gemini-2.0-flash",
            },
        }
        usage_report = {
            **usage_snapshot,
            "attempts": [
                {
                    "input_tokens": 120,
                    "output_tokens": 45,
                    "total_tokens": 165,
                    "provider": "gemini",
                    "model": "gemini-2.0-flash",
                    "phase": "generate_section",
                    "section_id": "sec-0001",
                    "section_path": "Introduccion",
                    "section_title": "Introduccion",
                    "attempt": 1,
                    "timestamp": "2026-03-17T10:00:00Z",
                    "estimated": False,
                    "source": "reported_by_provider",
                    "success": True,
                    "error": "",
                }
            ],
            "sections": [
                {
                    "section_id": "sec-0001",
                    "section_path": "Introduccion",
                    "section_title": "Introduccion",
                    "input_tokens_total": 120,
                    "output_tokens_total": 45,
                    "total_tokens": 165,
                    "calls_total": 1,
                    "reported_calls": 1,
                    "estimated_calls": 0,
                    "has_estimated_usage": False,
                    "last_provider": "gemini",
                    "last_model": "gemini-2.0-flash",
                    "last_timestamp": "2026-03-17T10:00:00Z",
                }
            ],
            "providers": [
                {
                    "provider": "gemini",
                    "model": "gemini-2.0-flash",
                    "input_tokens_total": 120,
                    "output_tokens_total": 45,
                    "total_tokens": 165,
                    "calls_total": 1,
                    "reported_calls": 1,
                    "estimated_calls": 0,
                    "has_estimated_usage": False,
                }
            ],
        }

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
            patch.object(router_module.ai_service, "get_token_usage_snapshot", return_value=usage_snapshot),
            patch.object(router_module.ai_service, "get_token_usage_report", return_value=usage_report),
        ):
            asyncio.run(router_module._ai_generation_job(project_id, "gemini-token-run"))

        project = client.get(f"/api/projects/{project_id}").json()
        assert project["progress"]["tokenUsage"]["total_tokens"] == 165
        assert project["progress"]["tokenUsage"]["reported_calls"] == 1
        assert project["token_usage"]["total_tokens"] == 165
        assert project["token_usage"]["attempts"][0]["provider"] == "gemini"

    def test_background_job_persists_generation_snapshot_on_partial_failure(self, client):
        from app.modules.api import router as router_module

        payload = {
            "title": "Resume Snapshot Test",
            "formatId": "demo",
            "promptId": "prompt_tesis_estandar",
            "values": {"tema": "Snapshot"},
        }
        response = client.post("/api/projects/draft", json=payload)
        project_id = response.json()["id"]

        usage_snapshot = {
            "input_tokens_total": 120,
            "output_tokens_total": 45,
            "total_tokens": 165,
            "calls_total": 1,
            "reported_calls": 1,
            "estimated_calls": 0,
            "has_estimated_usage": False,
            "current_section": {
                "section_id": "sec-0001",
                "section_path": "Introduccion",
                "section_title": "Introduccion",
            },
            "last_call": {"provider": "gemini", "model": "gemini-2.0-flash"},
        }
        usage_report = {
            **usage_snapshot,
            "attempts": [
                {
                    "input_tokens": 120,
                    "output_tokens": 45,
                    "total_tokens": 165,
                    "provider": "gemini",
                    "model": "gemini-2.0-flash",
                    "phase": "generate_section",
                    "section_id": "sec-0001",
                    "section_path": "Introduccion",
                    "section_title": "Introduccion",
                    "attempt": 1,
                    "timestamp": "2026-03-17T10:00:00Z",
                    "estimated": False,
                    "source": "reported_by_provider",
                    "success": True,
                    "error": "",
                }
            ],
            "sections": [],
            "providers": [],
        }

        def _fake_generate(project, format_detail, prompt, **kwargs):
            raise RuntimeError("forced failure")

        with (
            patch(
                "app.modules.api.router.formats.get_format_detail",
                new=AsyncMock(
                    return_value={
                        "definition": {
                            "cuerpo": {"capitulos": [{"titulo": "Introduccion"}, {"titulo": "Marco teorico"}]}
                        }
                    }
                ),
            ),
            patch("app.modules.api.router.ai_service.generate", side_effect=_fake_generate),
            patch.object(
                router_module.ai_service,
                "get_partial_ai_result",
                return_value={
                    "sections": [
                        {
                            "sectionId": "sec-0001",
                            "path": "Introduccion",
                            "content": "Contenido parcial",
                        }
                    ]
                },
            ),
            patch.object(router_module.ai_service, "get_token_usage_snapshot", return_value=usage_snapshot),
            patch.object(router_module.ai_service, "get_token_usage_report", return_value=usage_report),
        ):
            asyncio.run(router_module._ai_generation_job(project_id, "gemini-resume-run"))

        project = client.get(f"/api/projects/{project_id}").json()
        assert project["generation_snapshot"]["saved_sections_count"] == 1
        assert project["generation_snapshot"]["completed_sections"][0]["path"] == "Introduccion"
        assert project["generation_snapshot"]["status"] == "resume_ready"
        assert project["generation_snapshot"]["tokenUsage"]["total_tokens"] == 165

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

    def test_home_includes_step5_token_panel(self, client):
        response = client.get("/")
        assert response.status_code == 200
        html = response.text
        assert 'id="modal-project-budget"' in html
        assert 'id="budget-project-select"' in html
        assert 'id="budget-provider-select"' in html
        assert 'id="budget-model-select"' in html
        assert 'id="budget-calculate-button"' in html
        assert 'id="budget-estimate-pending"' in html
        assert 'id="budget-estimate-results"' in html
        assert 'id="budget-cost-total-pen"' in html
        assert 'id="budget-pen-rate"' in html
        assert 'id="stat-total-tokens"' in html
        assert 'id="gen-token-input-total"' in html
        assert 'id="gen-token-output-total"' in html
        assert 'id="gen-token-total"' in html
        assert 'id="gen-token-source"' in html
        assert 'id="sidebar-budget-total"' not in html
        assert 'id="gen-cost-total"' not in html
        assert 'id="gen-ai-detail-cost"' not in html
        assert 'id="gen-ai-detail-pricing"' not in html
        assert 'id="gen-ai-section-list"' in html
        assert 'id="construct-task-list"' in html
        assert 'id="step-7-content"' in html
        assert "Generación IA" in html
        assert "Construcción" in html

    def test_background_job_exposes_generation_and_construction_phases(self, client, tmp_path):
        from app.modules.api import router as router_module

        payload = {
            "title": "Phase Split Test",
            "formatId": "demo",
            "promptId": "prompt_tesis_estandar",
            "values": {"tema": "Phase split"},
        }
        response = client.post("/api/projects/draft", json=payload)
        project_id = response.json()["id"]

        usage_report = {
            "input_tokens_total": 210,
            "output_tokens_total": 75,
            "total_tokens": 285,
            "calls_total": 1,
            "reported_calls": 1,
            "estimated_calls": 0,
            "has_estimated_usage": False,
            "current_section": {
                "section_id": "sec-0001",
                "section_path": "Introduccion",
                "section_title": "Introduccion",
            },
            "last_call": {
                "provider": "mistral",
                "model": "mistral-medium-2505",
            },
            "attempts": [
                {
                    "input_tokens": 210,
                    "output_tokens": 75,
                    "total_tokens": 285,
                    "provider": "mistral",
                    "model": "mistral-medium-2505",
                    "phase": "generate_section",
                    "section_id": "sec-0001",
                    "section_path": "Introduccion",
                    "section_title": "Introduccion",
                    "attempt": 1,
                    "timestamp": "2026-03-18T10:00:00Z",
                    "duration_ms": 840,
                    "estimated": False,
                    "source": "reported_by_provider",
                    "success": True,
                    "error": "",
                }
            ],
            "sections": [],
            "providers": [],
        }

        def _fake_generate(project, format_detail, prompt, **kwargs):
            trace_hook = kwargs.get("trace_hook")
            progress_cb = kwargs.get("progress_cb")
            if callable(trace_hook):
                trace_hook(
                    {
                        "step": "prompt.base",
                        "status": "done",
                        "title": "Prompt base listo",
                        "preview": {"prompt": "PROMPT BASE DEL PROYECTO"},
                    }
                )
                trace_hook(
                    {
                        "step": "format.section_index",
                        "status": "done",
                        "title": "Formato parseado",
                        "meta": {
                            "sectionTotal": 1,
                            "sectionOutline": [
                                {
                                    "sectionId": "sec-0001",
                                    "sectionPath": (
                                        "I. PLANTEAMIENTO DEL PROBLEMA/1.1 Descripcion de la realidad problematica"
                                    ),
                                },
                            ],
                        },
                    }
                )
                trace_hook(
                    {
                        "step": "ai.generate.section",
                        "status": "done",
                        "title": "Seccion 1/1 completada",
                        "meta": {
                            "sectionIndex": 1,
                            "sectionTotal": 1,
                            "sectionId": "sec-0001",
                            "sectionPath": "I. PLANTEAMIENTO DEL PROBLEMA/1.1 Descripcion de la realidad problematica",
                            "provider": "mistral",
                            "model": "mistral-medium-2505",
                            "durationMs": 840,
                            "usageAttempts": usage_report["attempts"],
                        },
                        "preview": {
                            "prompt": "PROMPT SECCION INTRODUCCION",
                            "raw": "Salida IA para introduccion.",
                        },
                    }
                )
                trace_hook(
                    {
                        "step": "ai.generate.done",
                        "status": "done",
                        "title": "Generacion IA completada",
                    }
                )
            if callable(progress_cb):
                progress_cb(
                    1,
                    1,
                    "I. PLANTEAMIENTO DEL PROBLEMA/1.1 Descripcion de la realidad problematica",
                    "mistral",
                    stage="section_done",
                    payload={
                        "section_id": "sec-0001",
                        "section_path": "I. PLANTEAMIENTO DEL PROBLEMA/1.1 Descripcion de la realidad problematica",
                        "section_title": "1.1 Descripcion de la realidad problematica",
                        "parent_section_path": "I. PLANTEAMIENTO DEL PROBLEMA",
                        "section_level": 2,
                        "prompt_sent": "PROMPT SECCION INTRODUCCION",
                        "ai_output": "Salida IA para introduccion.",
                        "input_tokens": 210,
                        "output_tokens": 75,
                        "total_tokens": 285,
                        "model": "mistral-medium-2505",
                        "provider": "mistral",
                        "status": "ok",
                        "duration_ms": 840,
                        "estimated": False,
                        "source": "reported_by_provider",
                        "attempt_count": 1,
                        "attempts": usage_report["attempts"],
                    },
                )
            return {
                "sections": [
                    {
                        "sectionId": "sec-0001",
                        "path": "I. PLANTEAMIENTO DEL PROBLEMA/1.1 Descripcion de la realidad problematica",
                        "content": "Salida IA para introduccion.",
                    }
                ],
                "tokenUsage": usage_report,
            }

        def _fake_render(project_id_arg, **kwargs):
            router_module._set_construction_task(
                project_id_arg,
                "payload",
                status="done",
                detail="Payload validado.",
                global_status="running",
            )
            router_module._set_construction_task(
                project_id_arg,
                "render_docx",
                status="done",
                detail="DOCX listo.",
                global_status="running",
            )
            router_module._set_construction_task(
                project_id_arg,
                "render_pdf",
                status="done",
                detail="PDF listo.",
                global_status="running",
            )
            docx_path = tmp_path / "split.docx"
            pdf_path = tmp_path / "split.pdf"
            docx_path.write_bytes(b"docx")
            pdf_path.write_bytes(b"pdf")
            return docx_path, pdf_path

        with (
            patch(
                "app.modules.api.router.formats.get_format_detail",
                new=AsyncMock(return_value={"definition": {"cuerpo": {"capitulos": [{"titulo": "Introduccion"}]}}}),
            ),
            patch("app.modules.api.router.ai_service.generate", side_effect=_fake_generate),
            patch.object(router_module.ai_service, "get_token_usage_snapshot", return_value=usage_report),
            patch.object(router_module.ai_service, "get_token_usage_report", return_value=usage_report),
            patch.object(
                router_module.pricing_service,
                "get_pricing",
                return_value={
                    "provider": "mistral",
                    "model": "mistral-medium-2505",
                    "input_price_per_1m_tokens": 2.0,
                    "output_price_per_1m_tokens": 6.0,
                    "cached_input_price_per_1m_tokens": None,
                    "currency": "USD",
                    "pricing_mode": "standard",
                    "threshold_rule": "",
                    "modality": "text",
                    "source_url": "https://example.com/pricing",
                    "fetched_at": "2026-03-18T10:00:00Z",
                    "pricing_source": "cached",
                    "is_cached_fallback": False,
                    "available": True,
                },
            ),
            patch("app.modules.api.router._render_project_outputs_sync", side_effect=_fake_render),
        ):
            asyncio.run(router_module._ai_generation_job(project_id, "split-run-001"))

        project = client.get(f"/api/projects/{project_id}").json()
        assert project["generation_phase"]["status"] == "completed"
        assert project["generation_phase"]["base_prompt"] == "PROMPT BASE DEL PROYECTO"
        assert project["generation_phase"]["sections"][0]["prompt_sent"] == "PROMPT SECCION INTRODUCCION"
        assert project["generation_phase"]["sections"][0]["ai_output"] == "Salida IA para introduccion."
        assert project["generation_phase"]["sections"][0]["parent_section_path"] == "I. PLANTEAMIENTO DEL PROBLEMA"
        assert project["generation_phase"]["sections"][0]["section_level"] == 2
        assert (
            project["generation_phase"]["planned_sections"][0]["parent_section_path"] == "I. PLANTEAMIENTO DEL PROBLEMA"
        )
        assert project["generation_phase"]["sections"][0]["total_tokens"] == 285
        assert project["generation_phase"]["sections"][0]["estimated_cost_usd"] == pytest.approx(0.00087)
        assert project["generation_phase"]["cost_summary"]["total_cost_usd"] == pytest.approx(0.00087)
        assert project["generation_cost"]["total_cost_usd"] == pytest.approx(0.00087)
        assert project["progress"]["costUsage"]["total_cost_usd"] == pytest.approx(0.00087)
        assert project["construction_phase"]["status"] == "completed"
        tasks = {item["id"]: item for item in project["construction_phase"]["tasks"]}
        assert tasks["payload"]["status"] == "done"
        assert tasks["render_docx"]["status"] == "done"
        assert tasks["render_pdf"]["status"] == "done"
        assert tasks["final_validation"]["status"] == "done"

    def test_render_saved_ai_job_marks_render_failed_on_local_payload_validation(self, client):
        from app.modules.api import router as router_module

        payload = {
            "title": "Render Validation Test",
            "formatId": "demo",
            "promptId": "prompt_tesis_estandar",
            "values": {"tema": "Render validation"},
        }
        r = client.post("/api/projects/draft", json=payload)
        project_id = r.json()["id"]
        router_module.projects.update_project(
            project_id,
            {
                "status": "render_failed",
                "ai_result": {
                    "sections": [
                        {
                            "sectionId": "sec-0001",
                            "path": "Cronograma",
                            "content": [
                                {
                                    "tipo": "tabla",
                                    "encabezados": [],
                                    "filas": [],
                                }
                            ],
                        }
                    ]
                },
            },
        )

        asyncio.run(router_module._render_saved_ai_job(project_id, "render-test-001"))

        project = client.get(f"/api/projects/{project_id}").json()
        assert project["status"] == "render_failed"
        assert project["ai_result"] is not None
        assert "encabezados" in str(project["error"]) or "Render payload" in str(project["error"])


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
