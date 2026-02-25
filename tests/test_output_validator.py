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
