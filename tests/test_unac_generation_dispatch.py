from __future__ import annotations

from unittest.mock import MagicMock

from app.core.services.ai.ai_service import AIService
from app.core.services.ai.resilience_router import LLMResult
from app.core.services.ai.unac_quality_profile import (
    audit_unac_maintenance_sections,
    requirements_for_section_path,
)


def _values():
    return {
        "title": "PLAN DE MANTENIMIENTO CENTRADO EN CONFIABILIDAD PARA MEJORAR LA DISPONIBILIDAD",
        "variable_independiente": "Mantenimiento centrado en confiabilidad RCM",
        "variable_dependiente": "Disponibilidad inherente",
        "objeto_estudio": "Motoniveladoras CAT 24M",
        "problema_general": "¿Cómo mejora el plan RCM la disponibilidad inherente de las motoniveladoras CAT 24M?",
        "objetivo_general": "Determinar cómo mejora el plan RCM la disponibilidad inherente de las motoniveladoras CAT 24M.",
        "hipotesis_general": "El plan RCM mejora la disponibilidad inherente de las motoniveladoras CAT 24M.",
        "problemas_especificos": ["¿Cómo mejora la confiabilidad?", "¿Cómo mejora la mantenibilidad?"],
        "objetivos_especificos": ["Determinar la mejora de la confiabilidad.", "Determinar la mejora de la mantenibilidad."],
        "hipotesis_especificas": ["El plan mejora la confiabilidad.", "El plan mejora la mantenibilidad."],
    }


def test_single_v2_methodology_unit_uses_immediate_semantic_validation():
    service = AIService()
    controlled = MagicMock(
        return_value=LLMResult(
            content="La ubicación, la operación y el entorno delimitan el lugar de estudio.",
            provider="mistral",
            status="ok",
        )
    )
    service._generate_unac_semantic_units = controlled

    service._generate_sections(
        base_prompt="Contrato base",
        section_index=[{"sectionId": "method-4-4", "path": "IV. METODOLOGÍA/4.4 Lugar de estudio"}],
        project_id="project-dispatch",
        values=_values(),
        selection={"provider": "mistral", "mode": "fixed"},
        format_id="unac-proyecto-cuant",
    )

    assert controlled.call_count == 1
    assert controlled.call_args.kwargs["requirements"][0].key == "4.4"


def test_matrix_owned_sections_are_built_without_provider_calls():
    service = AIService()
    provider_call = MagicMock()
    service._generate_with_provider_fallback = provider_call

    sections = service._generate_sections(
        base_prompt="Contrato base",
        section_index=[
            {"sectionId": "titulo-info-basica", "path": "Título + Información Básica"},
            {"sectionId": "problem", "path": "I/1.2 Formulación del problema"},
            {"sectionId": "objective", "path": "I/1.3 Objetivos"},
            {"sectionId": "hypothesis", "path": "III/3.1 Hipótesis"},
            {"sectionId": "terms", "path": "II/2.4 Definición de términos básicos"},
            {"sectionId": "operationalization", "path": "III/3.2 Operacionalización de variable"},
            {"sectionId": "schedule", "path": "V. CRONOGRAMA DE ACTIVIDADES"},
            {"sectionId": "budget", "path": "VI. PRESUPUESTO"},
            {"sectionId": "references", "path": "VII. REFERENCIAS BIBLIOGRÁFICAS"},
            {"sectionId": "annexes", "path": "ANEXOS"},
        ],
        project_id="project-deterministic",
        values=_values(),
        selection={"provider": "mistral", "mode": "fixed"},
        format_id="unac-proyecto-cuant",
    )

    assert provider_call.call_count == 0
    by_path = {item["path"]: item["content"] for item in sections}
    assert by_path["I/1.2 Formulación del problema"][0]["texto"] == "Problema general"
    assert by_path["I/1.2 Formulación del problema"][2]["texto"] == "Problemas específicos"
    assert by_path["I/1.2 Formulación del problema"][3]["tipo"] == "lista"
    terms = by_path["II/2.4 Definición de términos básicos"]
    terms_audit = audit_unac_maintenance_sections(
        [{"path": "II/2.4 Definición de términos básicos", "content": terms}]
    )[0]
    assert len(terms) == 13
    assert terms_audit.items == 13
    assert 434 <= terms_audit.words <= 500
    assert not terms_audit.missing_topics
    assert "variable independiente" in by_path["III/3.2 Operacionalización de variable"][0]["texto"]
    assert "Tablas 3.1 y 3.2" in by_path["III/3.2 Operacionalización de variable"][0]["texto"]
    assert by_path["V. CRONOGRAMA DE ACTIVIDADES"][0]["subtipo"] == "cronograma_actividades"
    assert by_path["VI. PRESUPUESTO"][0]["subtipo"] == "presupuesto_investigacion"
    assert "registro de fuentes" in by_path["VII. REFERENCIAS BIBLIOGRÁFICAS"][0]["texto"]
    assert "plantilla institucional" in by_path["ANEXOS"][0]["texto"]


def test_terms_prompt_removes_legacy_conflicting_range():
    requirement = next(
        item
        for item in requirements_for_section_path("II/2.4 Definición de términos básicos")
        if item.key == "2.4"
    )
    prompt = AIService._normalize_managed_requirement_prompt(
        "Rango de palabras aceptable: 450 a 600 palabras. Incluye 10 a 15 terminos técnicos.",
        requirement,
    )
    assert "450 a 600" not in prompt
    assert "10 a 15" not in prompt
    assert "434 a 500" in prompt
    assert "exactamente trece" in prompt
