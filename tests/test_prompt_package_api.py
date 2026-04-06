from fastapi.testclient import TestClient

from app.core.services.institutional_section_service import InstitutionalSectionService
from app.main import app


def test_prompt_package_endpoint_returns_selected_sections_and_tree(monkeypatch):
    from app.modules.api import router as router_module

    definition = {
        "preliminares": {
            "resumen": {"titulo": "RESUMEN"},
            "introduccion": {"titulo": "INTRODUCCION"},
        },
        "cuerpo": [
            {
                "titulo": "I. PLANTEAMIENTO DEL PROBLEMA",
                "contenido": [{"texto": "1.1 Realidad problematica"}],
            }
        ],
    }

    section_service = InstitutionalSectionService()
    sections = section_service.extract_sections(definition)

    class FakeFormats:
        async def get_format_detail(self, format_id: str):
            return {
                "id": format_id,
                "title": "Informe de Tesis UNAC - Enfoque Cualitativo",
                "documentType": "tesis",
                "version": "v1",
                "definition": definition,
            }

    class FakePrompts:
        def get_prompt_by_format(self, format_id: str, *, format_detail=None):
            return {
                "id": "promptpkg_unac_informe_cual",
                "name": "Paquete Informe Cualitativo UNAC",
                "format_id": format_id,
                "format_name": "Informe de Tesis UNAC - Enfoque Cualitativo",
                "format_version": "v1",
                "doc_type": "tesis",
                "template": "Tema: {{tema}}",
                "variables": ["tema"],
                "sections": sections,
            }

    monkeypatch.setattr(router_module, "formats", FakeFormats())
    monkeypatch.setattr(router_module, "prompts", FakePrompts())

    with TestClient(app) as client:
        response = client.get("/api/formats/unac-informe-cual/prompt-package")

    assert response.status_code == 200
    payload = response.json()
    assert payload["format_id"] == "unac-informe-cual"
    assert any(item["section_path"] == "INTRODUCCION" for item in payload["selected_sections"])
    assert all(item["section_path"] != "RESUMEN" for item in payload["selected_sections"])
    assert isinstance(payload["section_tree"], list)
    assert payload["section_tree"][0]["section_path"] in {"INTRODUCCION", "RESUMEN", "I. PLANTEAMIENTO DEL PROBLEMA"}
