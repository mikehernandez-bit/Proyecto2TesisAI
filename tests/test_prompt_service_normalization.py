import json

from app.core.services.prompt_service import PromptService
from app.modules.api.models import PromptBlock


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
    assert any(
        section["section_path"] == "RESUMEN" and section["default_selected"] is False for section in prompt["sections"]
    )
    matching_section = next(
        section for section in prompt["sections"] if "Realidad problematica" in section["section_path"]
    )
    assert matching_section["blocks"][0]["header"] == "Realidad problemática"
    assert matching_section["blocks"][0]["cabecera"] == "Realidad problemática"
    assert matching_section["blocks"][0]["label"] == "Diagnóstico de la realidad problemática"
    assert matching_section["blocks"][0]["instructions"] == (
        "Presenta la situación problemática con datos observables, contexto del estudio, "
        "evidencia local y una propuesta preliminar de solución."
    )
    assert "variable_dependiente" in prompt["variables"]


def test_prompt_block_accepts_header_cabecera_and_titulo_cabecera_aliases():
    from_header = PromptBlock.model_validate({"header": "Contexto", "label": "Prompt"})
    from_cabecera = PromptBlock.model_validate({"cabecera": "Cabecera publica"})
    from_legacy = PromptBlock.model_validate({"titulo_cabecera": "Legacy"})

    assert from_header.header == "Contexto"
    assert from_header.cabecera == "Contexto"
    assert from_cabecera.header == "Cabecera publica"
    assert from_cabecera.cabecera == "Cabecera publica"
    assert from_legacy.header == "Legacy"
    assert from_legacy.cabecera == "Legacy"


def test_prompt_service_repairs_mojibake_and_injects_required_variables_for_realidad_problematica(tmp_path):
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
                    "sections": [
                        {
                            "section_id": "sec-1",
                            "section_path": (
                                "I. PLANTEAMIENTO DEL PROBLEMA/1.1 DescripciÃƒÂ³n de la realidad problemÃƒÂ¡tica"
                            ),
                            "section_title": "1.1 DescripciÃƒÂ³n de la realidad problemÃƒÂ¡tica",
                            "parent_section_path": "I. PLANTEAMIENTO DEL PROBLEMA",
                            "section_level": 2,
                            "blocks": [],
                            "source_hints": "Contexto institucional/local: Describe la realidad especÃƒÂ­fica.",
                        }
                    ],
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
                            "titulo_cabecera": "XD",
                            "instrucciones_ia": "XD",
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
        "cuerpo": [
            {
                "titulo": "I. PLANTEAMIENTO DEL PROBLEMA",
                "contenido": [
                    {"texto": "1.1 DescripciÃ³n de la realidad problemÃ¡tica"},
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

    prompt = service.get_prompt_by_format("unac-informe-cual")

    assert prompt is not None
    matching_section = next(
        section
        for section in prompt["sections"]
        if "Descripción de la realidad problemática" in section["section_path"]
    )
    assert matching_section["section_title"] == "1.1 Descripción de la realidad problemática"
    assert matching_section["blocks"][0]["header"] == "Realidad problemática"
    assert matching_section["blocks"][0]["label"] == "Diagnóstico de la realidad problemática"
    assert matching_section["blocks"][0]["instructions"]
    assert matching_section["blocks"][0]["required_variables"] == [
        "variable_dependiente",
        "contexto_organizacion",
        "problema_observable",
        "sustento_local",
        "propuesta_solucion_preliminar",
        "contexto_internacional",
        "contexto_nacional",
        "sustento_ingenieril",
        "periodo_analisis",
    ]


def test_prompt_service_excludes_persisted_annex_example_children(tmp_path):
    prompts_path = tmp_path / "prompts.json"
    prompts_path.write_text(
        json.dumps(
            [
                {
                    "id": "prompt_modern_unac_inf_cual",
                    "name": "Informe Cualitativo UNAC",
                    "docType": "tesis",
                    "template": "",
                    "variables": [],
                    "is_active": True,
                    "format_id": "unac-informe-cual",
                    "sections": [
                        {
                            "section_id": "sec-anexos",
                            "section_path": "ANEXOS",
                            "section_title": "ANEXOS",
                            "parent_section_path": "",
                            "section_level": 1,
                            "section_order": 10,
                            "optional": True,
                            "default_selected": False,
                            "blocks": [],
                        },
                        {
                            "section_id": "sec-anexo-1",
                            "section_path": "ANEXOS/Anexo 1: Matriz de consistencia",
                            "section_title": "Anexo 1: Matriz de consistencia",
                            "parent_section_path": "ANEXOS",
                            "section_level": 2,
                            "section_order": 11,
                            "optional": True,
                            "default_selected": False,
                            "blocks": [],
                        },
                    ],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    definition = {
        "cuerpo": [
            {
                "titulo": "ANEXOS",
                "contenido": [
                    {"texto": "Anexo 1: Matriz de consistencia"},
                    {"texto": "Anexo 2: Instrumento de recoleccion de datos"},
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

    prompt = service.get_prompt("prompt_modern_unac_inf_cual")

    assert prompt is not None
    section_paths = [section["section_path"] for section in prompt["sections"]]
    assert "ANEXOS" in section_paths
    assert "ANEXOS/Anexo 1: Matriz de consistencia" not in section_paths
