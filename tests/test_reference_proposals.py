"""Tests for simulated reference consolidation."""

from app.core.services.ai.reference_proposals import (
    build_reference_section_content,
    replace_references_section,
)


def test_build_reference_section_content_is_simulated_and_contextual() -> None:
    sections = [
        {
            "sectionId": "sec-0001",
            "path": "II. MARCO TEORICO/2.2 Bases teoricas",
            "content": "Desarrollo conceptual sobre mantenimiento predictivo y modelos de gestion.",
        },
        {
            "sectionId": "sec-0002",
            "path": "IV. METODOLOGIA/4.1 Diseno metodologico",
            "content": "Se describe el diseno metodologico, instrumentos y plan de analisis.",
        },
        {
            "sectionId": "sec-0003",
            "path": "IX. REFERENCIAS BIBLIOGRAFICAS",
            "content": "Contenido viejo",
        },
    ]

    content = build_reference_section_content(
        sections,
        values={"tema": "Mantenimiento predictivo en sistemas industriales"},
    )

    assert "sin acceso a internet" in content
    assert "Fundamentos teoricos de mantenimiento predictivo en sistemas industriales" in content
    assert "Metodologia de la investigacion aplicada a mantenimiento predictivo en sistemas industriales" in content
    assert "http" not in content.lower()
    assert "doi" not in content.lower()


def test_replace_references_section_overrides_final_reference_content() -> None:
    sections = [
        {
            "sectionId": "sec-0001",
            "path": "I. PLANTEAMIENTO DEL PROBLEMA",
            "content": "Contenido academico del problema.",
        },
        {
            "sectionId": "sec-0002",
            "path": "IX. REFERENCIAS BIBLIOGRAFICAS",
            "content": "Ejemplo viejo del formato",
        },
    ]

    updated = replace_references_section(
        sections,
        values={"tema": "Optimización logística con IA"},
    )

    final_section = next(item for item in updated if "REFERENCIAS" in item["path"].upper())
    assert "sin acceso a internet" in final_section["content"]
    assert "Ejemplo viejo del formato" not in final_section["content"]
