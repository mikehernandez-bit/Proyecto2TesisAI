"""Tests for app.core.services.ai.output_validator."""

import pytest

from app.core.services.ai.output_validator import OutputValidator, ValidationError


@pytest.fixture
def validator():
    return OutputValidator()


class TestValidate:
    def test_valid_ai_result(self, validator):
        ai_result = {
            "sections": [
                {
                    "sectionId": "sec-0001",
                    "path": "Introduccion",
                    "content": "Contenido de la introduccion con suficiente texto.",
                },
                {
                    "sectionId": "sec-0002",
                    "path": "Marco Teorico",
                    "content": "Contenido del marco teorico con suficiente texto.",
                },
            ]
        }
        result = validator.validate(ai_result)
        assert len(result["sections"]) == 2
        assert result["sections"][0]["sectionId"] == "sec-0001"

    def test_missing_sections_raises(self, validator):
        with pytest.raises(ValidationError, match="non-empty list"):
            validator.validate({"sections": []})

    def test_not_a_dict_raises(self, validator):
        with pytest.raises(ValidationError, match="must be a dict"):
            validator.validate("not a dict")

    def test_missing_section_id_auto_assigned(self, validator):
        ai_result = {
            "sections": [
                {"path": "Intro", "content": "Texto suficientemente largo para pasar."},
            ]
        }
        result = validator.validate(ai_result)
        assert result["sections"][0]["sectionId"].startswith("sec-auto-")

    def test_empty_content_warning(self, validator):
        ai_result = {
            "sections": [
                {"sectionId": "sec-0001", "path": "Intro", "content": ""},
            ]
        }
        result = validator.validate(ai_result)
        assert result["sections"][0]["content"] == ""

    def test_sanitizes_markdown_and_placeholders(self, validator):
        ai_result = {
            "sections": [
                {
                    "sectionId": "sec-0001",
                    "path": "I. PLANTEAMIENTO/1.1 Realidad",
                    "content": (
                        "### Titulo interno\n"
                        "**Texto** con  |  tabla markdown\n"
                        "- item con vineta\n\n"
                        "FIGURA DE EJEMPLO\n"
                        "TITULO DEL PROYECTO"
                    ),
                }
            ]
        }

        result = validator.validate(ai_result)
        content = result["sections"][0]["content"]
        assert "###" not in content
        assert "**" not in content
        assert "|" not in content
        assert "FIGURA DE EJEMPLO" not in content
        assert "TITULO DEL PROYECTO" not in content
        assert "item con vineta" in content

    def test_preserves_structured_content_lists(self, validator):
        ai_result = {
            "sections": [
                {
                    "sectionId": "sec-structured",
                    "path": "II. MARCO TEORICO/2.1 Bases teoricas",
                    "content": [
                        {"tipo": "parrafo", "texto": "Parrafo academico suficientemente largo para pasar validacion."},
                        {
                            "tipo": "tabla",
                            "titulo": "Tabla 1. Variables",
                            "encabezados": ["Variable", "Definicion", "Indicador"],
                            "filas": [["A", "[COMPLETAR]", "I1"]],
                        },
                        {
                            "tipo": "figura",
                            "titulo": "Figura 1. Modelo",
                            "caption": "Figura 1. Modelo conceptual propuesto.",
                        },
                    ],
                }
            ]
        }

        result = validator.validate(ai_result)
        content = result["sections"][0]["content"]
        assert isinstance(content, list)
        assert content[0]["tipo"] == "parrafo"
        assert content[1]["tipo"] == "tabla"
        assert content[1]["filas"][0][1] == "[COMPLETAR]"
        assert content[2]["tipo"] == "figura"
        assert content[2]["ruta_placeholder"] == "assets/placeholder_figura.png"

    def test_figure_title_is_derived_from_caption_when_missing(self, validator):
        ai_result = {
            "sections": [
                {
                    "sectionId": "sec-figure",
                    "path": "IV. METODOLOGIA/4.1 Diseno metodologico",
                    "content": [
                        {
                            "tipo": "figura",
                            "caption": "Figura 2. Flujo metodologico del estudio sobre mantenimiento predictivo.",
                        }
                    ],
                }
            ]
        }

        result = validator.validate(ai_result)
        figure = result["sections"][0]["content"][0]
        assert figure["titulo"] == "Flujo metodologico del estudio sobre mantenimiento predictivo."

    def test_reality_problem_preserves_four_figure_blocks(self, validator):
        figures = [
            {
                "tipo": "figura",
                "titulo": f"Figura {index}",
                "caption": f"Figura {index}. Guia tecnica.",
            }
            for index in range(1, 6)
        ]
        ai_result = {
            "sections": [
                {
                    "sectionId": "sec-problem",
                    "path": "I. PLANTEAMIENTO DEL PROBLEMA/1.1 Descripcion de la realidad problematica",
                    "content": figures,
                }
            ]
        }

        result = validator.validate(ai_result)
        content = result["sections"][0]["content"]
        assert isinstance(content, list)
        assert len([block for block in content if block["tipo"] == "figura"]) == 4

    def test_reality_problem_drops_table_blocks(self, validator):
        ai_result = {
            "sections": [
                {
                    "sectionId": "sec-problem",
                    "path": "I. PLANTEAMIENTO DEL PROBLEMA/1.1 Descripcion de la realidad problematica",
                    "content": [
                        {"tipo": "parrafo", "texto": "Diagnostico tecnico suficiente para el problema."},
                        {
                            "tipo": "tabla",
                            "titulo": "Tabla 1.1 Diagrama de Pareto",
                            "encabezados": ["Sistema", "Frecuencia"],
                            "filas": [["Tren de potencia", "42"]],
                        },
                    ],
                }
            ]
        }

        result = validator.validate(ai_result)
        content = result["sections"][0]["content"]
        assert isinstance(content, list)
        assert [block["tipo"] for block in content] == ["parrafo"]

    def test_strips_raw_structured_repr_from_plain_text(self, validator):
        ai_result = {
            "sections": [
                {
                    "sectionId": "sec-raw",
                    "path": "I. PLANTEAMIENTO/1.1 Problema",
                    "content": (
                        "Parrafo limpio antes.\n"
                        "[{'tipo': 'tabla', 'id': 'tab_001', 'titulo': 'Tabla rota'}]\n"
                        "{'tipo': 'figura', 'id': 'fig_001', 'caption': 'Figura rota'}\n"
                        "Parrafo limpio despues."
                    ),
                }
            ]
        }

        result = validator.validate(ai_result)
        content = result["sections"][0]["content"]
        assert "tipo" not in content
        assert "tab_001" not in content
        assert "fig_001" not in content
        assert "Parrafo limpio antes." in content
        assert "Parrafo limpio despues." in content

    def test_index_path_forces_empty_content(self, validator):
        """TOC sections are now DROPPED entirely, not just emptied."""
        ai_result = {
            "sections": [
                {
                    "sectionId": "sec-0001",
                    "path": "INDICE",
                    "content": "No debe aparecer en el indice",
                },
                {
                    "sectionId": "sec-0002",
                    "path": "I. PLANTEAMIENTO",
                    "content": "Contenido valido del capitulo",
                },
            ]
        }

        result = validator.validate(ai_result)
        # sec-0001 was dropped
        assert len(result["sections"]) == 1
        assert result["sections"][0]["sectionId"] == "sec-0002"

    def test_skip_section_token_is_normalized_to_empty(self, validator):
        ai_result = {
            "sections": [
                {
                    "sectionId": "sec-0001",
                    "path": "I. PLANTEAMIENTO/1.1 Realidad",
                    "content": "<<SKIP_SECTION>>",
                }
            ]
        }
        result = validator.validate(ai_result)
        assert result["sections"][0]["content"] == ""

    def test_abbreviations_are_normalized_to_tab_format(self, validator):
        ai_result = {
            "sections": [
                {
                    "sectionId": "sec-0001",
                    "path": "PRELIMINARES/ABREVIATURAS",
                    "content": (
                        "IA: Inteligencia Artificial\n"
                        "ERP - Planificacion de recursos empresariales\n"
                        "Organizacion Mundial de la Salud (OMS)"
                    ),
                }
            ]
        }

        result = validator.validate(ai_result)
        content = result["sections"][0]["content"]
        assert "IA\tInteligencia Artificial" in content
        assert "ERP\tPlanificacion de recursos empresariales" in content
        assert "OMS\tOrganizacion Mundial de la Salud" in content

    def test_index_of_abbreviations_forces_empty_content(self, validator):
        """ÍNDICE DE ABREVIATURAS is a TOC heading — dropped entirely."""
        ai_result = {
            "sections": [
                {
                    "sectionId": "sec-0001",
                    "path": "INDICE DE ABREVIATURAS",
                    "content": "IA: Inteligencia Artificial",
                },
                {
                    "sectionId": "sec-0002",
                    "path": "I. CAPITULO",
                    "content": "Contenido del capitulo real",
                },
            ]
        }

        result = validator.validate(ai_result)
        assert len(result["sections"]) == 1
        assert result["sections"][0]["sectionId"] == "sec-0002"


class TestBuildAiResult:
    def test_build_and_validate(self, validator):
        sections = [
            {"sectionId": "s1", "path": "Cap 1", "content": "Contenido capitulo uno largo."},
        ]
        result = validator.build_ai_result(sections)
        assert "sections" in result
        assert result["sections"][0]["sectionId"] == "s1"
