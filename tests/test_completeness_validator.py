"""Tests for the completeness validator.

Verifies that placeholder text is detected and autofill produces
real content for known section types.
"""

import pytest

from app.core.services.ai.completeness_validator import (
    CompletenessIssue,
    autofill_section,
    detect_placeholders,
    strip_placeholder_text,
)


# ---------------------------------------------------------------------------
# detect_placeholders
# ---------------------------------------------------------------------------


class TestDetectPlaceholders:
    def test_detects_escriba_placeholder(self):
        sections = [
            {"sectionId": "ded", "path": "DEDICATORIA", "content": "[Escriba aquí su dedicatoria…]"},
        ]
        issues = detect_placeholders(sections)
        assert len(issues) == 1
        assert issues[0].issue_type == "placeholder"
        assert issues[0].section_id == "ded"

    def test_detects_completar_placeholder(self):
        sections = [
            {"sectionId": "abbr", "path": "ABREVIATURAS", "content": "(Completar abreviaturas)"},
        ]
        issues = detect_placeholders(sections)
        assert len(issues) == 1
        assert issues[0].issue_type == "placeholder"

    def test_detects_template_vars(self):
        sections = [
            {"sectionId": "car", "path": "caratula", "content": "Titulo: {{titulo_tesis}}"},
        ]
        issues = detect_placeholders(sections)
        assert len(issues) == 1
        assert issues[0].issue_type == "template_var"

    def test_detects_empty_content(self):
        sections = [
            {"sectionId": "intro", "path": "INTRO", "content": "   "},
        ]
        issues = detect_placeholders(sections)
        assert len(issues) == 1
        assert issues[0].issue_type == "empty"

    def test_detects_instruction_text(self):
        sections = [
            {
                "sectionId": "res",
                "path": "RESUMEN",
                "content": "Escriba aquí el cuerpo del resumen.",
            },
        ]
        issues = detect_placeholders(sections)
        assert len(issues) == 1
        assert issues[0].issue_type == "instruction"

    def test_detects_placeholder_only_structured_table(self):
        sections = [
            {
                "sectionId": "disc",
                "path": "VI. DISCUSION DE RESULTADOS/6.1 Discusion",
                "content": [
                    {
                        "tipo": "tabla",
                        "titulo": "Tabla comparativa",
                        "encabezados": ["Autor", "Variable", "Resultado"],
                        "filas": [["[Autor 1]", "[Variable]", "[Resultado]"]],
                    }
                ],
            },
        ]
        issues = detect_placeholders(sections)
        assert len(issues) == 1
        assert issues[0].issue_type == "placeholder"

    def test_no_issues_for_real_content(self):
        sections = [
            {
                "sectionId": "intro",
                "path": "I. INTRODUCCION",
                "content": (
                    "La presente investigacion tiene como objetivo analizar el impacto "
                    "de las tecnologias emergentes en la educacion superior peruana. "
                    "Se emplea una metodologia cuantitativa con enfoque descriptivo."
                ),
            },
        ]
        issues = detect_placeholders(sections)
        assert len(issues) == 0

    def test_multiple_issues(self):
        sections = [
            {"sectionId": "ded", "path": "DEDICATORIA", "content": "[Escriba aquí su dedicatoria…]"},
            {"sectionId": "agr", "path": "AGRADECIMIENTO", "content": "[Escriba aquí su agradecimiento…]"},
            {"sectionId": "intro", "path": "INTRODUCCION", "content": "Contenido real aqui."},
        ]
        issues = detect_placeholders(sections)
        assert len(issues) == 2


# ---------------------------------------------------------------------------
# autofill_section
# ---------------------------------------------------------------------------


class TestAutofillSection:
    def test_autofill_dedicatoria(self):
        sec = {"sectionId": "ded", "path": "DEDICATORIA", "content": "[placeholder]"}
        result = autofill_section(sec, "placeholder")
        assert result is not None
        assert "Dedico" in result
        assert "[" not in result
        assert len(result) > 50

    def test_autofill_agradecimiento(self):
        sec = {"sectionId": "agr", "path": "AGRADECIMIENTO", "content": ""}
        result = autofill_section(sec, "empty")
        assert result is not None
        assert "Agradezco" in result
        assert len(result) > 50

    def test_autofill_abreviaturas(self):
        sec = {"sectionId": "abbr", "path": "INDICE DE ABREVIATURAS", "content": "(Completar)"}
        result = autofill_section(sec, "placeholder")
        assert result is not None
        assert "abreviaturas" in result.lower()
        assert "(Completar" not in result

    def test_autofill_unknown_section_returns_none(self):
        sec = {"sectionId": "intro", "path": "INTRODUCCION", "content": ""}
        result = autofill_section(sec, "empty")
        assert result is None

    def test_autofill_discusion_generates_required_fallback(self):
        sec = {"sectionId": "disc", "path": "VI. DISCUSION DE RESULTADOS/6.1 Discusion", "content": ""}
        result = autofill_section(
            sec,
            "empty",
            values={
                "tema": "mantenimiento predictivo en motores de combustion interna",
                "objetivo_general": "evaluar el impacto del analisis predictivo en la deteccion de fallas",
            },
            all_sections=[
                {
                    "sectionId": "res",
                    "path": "V. RESULTADOS/5.1 Resultados",
                    "content": (
                        "Los resultados evidenciaron una mejora en la deteccion temprana de fallas y una reduccion "
                        "de intervenciones no planificadas."
                    ),
                }
            ],
        )
        assert result is not None
        assert "mantenimiento predictivo" in result.lower()
        assert len(result) > 150

    def test_autofill_conclusiones_generates_required_fallback(self):
        sec = {"sectionId": "conc", "path": "VII. CONCLUSIONES/7.1 Conclusiones", "content": ""}
        result = autofill_section(
            sec,
            "empty",
            values={"tema": "optimizacion logistica con IA generativa"},
        )
        assert result is not None
        assert "concluye" in result.lower() or "conclus" in result.lower()
        assert len(result) > 150

    def test_autofill_recomendaciones_generates_required_fallback(self):
        sec = {"sectionId": "rec", "path": "VIII. RECOMENDACIONES/8.1 Recomendaciones", "content": ""}
        result = autofill_section(
            sec,
            "empty",
            values={"tema": "optimizacion logistica con IA generativa"},
        )
        assert result is not None
        assert "recomienda" in result.lower()
        assert len(result) > 150


# ---------------------------------------------------------------------------
# strip_placeholder_text
# ---------------------------------------------------------------------------


class TestStripPlaceholderText:
    def test_strips_escriba_pattern(self):
        text = "Hola [Escriba aquí su texto] mundo"
        result = strip_placeholder_text(text)
        assert "[Escriba" not in result
        assert "mundo" in result

    def test_strips_completar_pattern(self):
        text = "Antes (Completar abreviaturas) despues"
        result = strip_placeholder_text(text)
        assert "(Completar" not in result
        assert "Antes" in result

    def test_strips_template_vars(self):
        text = "Titulo: {{titulo_tesis}} por {{autor}}"
        result = strip_placeholder_text(text)
        assert "{{" not in result
        assert "}}" not in result

    def test_preserves_real_content(self):
        text = "La investigacion analiza el impacto de las TIC."
        result = strip_placeholder_text(text)
        assert result == text


# ---------------------------------------------------------------------------
# Integration: no placeholders survive the pipeline
# ---------------------------------------------------------------------------


class TestNoPlaceholdersSurvive:
    """Simulates sections going through detect -> autofill cycle."""

    def test_full_repair_cycle(self):
        sections = [
            {"sectionId": "ded", "path": "DEDICATORIA", "content": "[Escriba aquí su dedicatoria…]"},
            {"sectionId": "agr", "path": "AGRADECIMIENTO", "content": "[Escriba aquí su agradecimiento…]"},
            {"sectionId": "abbr", "path": "ABREVIATURAS", "content": "(Completar abreviaturas)"},
            {
                "sectionId": "intro",
                "path": "INTRODUCCION",
                "content": "Contenido real de la introduccion.",
            },
        ]

        # First pass: detect issues
        issues = detect_placeholders(sections)
        assert len(issues) == 3  # ded, agr, abbr

        # Repair
        for issue in issues:
            for sec in sections:
                if sec["sectionId"] == issue.section_id:
                    replacement = autofill_section(sec, issue.issue_type)
                    if replacement:
                        sec["content"] = replacement

        # Second pass: should be clean
        remaining = detect_placeholders(sections)
        assert len(remaining) == 0

        # Verify no forbidden patterns in any content
        forbidden = ["[Escriba", "(Completar", "{{"]
        for sec in sections:
            for pat in forbidden:
                assert pat not in sec["content"], f"Section {sec['sectionId']} still contains '{pat}'"
