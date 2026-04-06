import json

from app.core.services.prompt_service import PromptService


def test_prompt_service_merges_legacy_blocks_into_format_sections(tmp_path):
    prompts_path = tmp_path / "prompts.json"
    prompts_path.write_text(
        json.dumps(
            [
                {
                    "id": "prompt_modern_unac_inf_cual",
                    "name": "Informe Cualitativo UNAC",
                    "docType": "tesis",
                    "template": "Tema: {{tema}}",
                    "variables": ["tema"],
                    "is_active": True,
                },
                {
                    "id_unico": "UNAC_INF_CUALI_CAPITULO_I",
                    "universidad": "UNAC",
                    "metodologia": "INF",
                    "categoria": "CUALI",
                    "prompts": [
                        {
                            "numero_prompt": 1,
                            "capitulo_nombre": "PLANTEAMIENTO DEL PROBLEMA",
                            "titulo_cabecera": "Realidad problematica",
                            "instrucciones_ia": "Profundiza en el problema tecnico.",
                            "variables_locales": ["variable_dependiente"],
                        }
                    ],
                },
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    definition = {
        "preliminares": {
            "resumen": {"titulo": "RESUMEN"},
            "introduccion": {"titulo": "INTRODUCCION"},
        },
        "cuerpo": [
            {
                "titulo": "I. PLANTEAMIENTO DEL PROBLEMA",
                "contenido": [
                    {"texto": "1.1 Realidad problematica"},
                ],
            }
        ],
    }

    service = PromptService(path=str(prompts_path))
    service.format_cache._data = {
        "catalogVersion": "test",
        "catalogEtag": None,
        "formats": [
            {
                "id": "unac-informe-cual",
                "title": "Informe de Tesis UNAC - Enfoque Cualitativo",
                "documentType": "tesis",
                "version": "v1",
            }
        ],
        "detailsById": {
            "unac-informe-cual": {
                "id": "unac-informe-cual",
                "title": "Informe de Tesis UNAC - Enfoque Cualitativo",
                "documentType": "tesis",
                "version": "v1",
                "definition": definition,
            }
        },
        "lastSyncAt": None,
    }

    prompts = service.list_prompts()

    assert len(prompts) == 1
    prompt = prompts[0]
    assert prompt["format_id"] == "unac-informe-cual"
    assert any(section["section_path"] == "RESUMEN" and section["default_selected"] is False for section in prompt["sections"])
    matching_section = next(
        section
        for section in prompt["sections"]
        if "Realidad problematica" in section["section_path"]
    )
    assert matching_section["blocks"][0]["instructions"] == "Profundiza en el problema tecnico."
    assert "variable_dependiente" in prompt["variables"]
