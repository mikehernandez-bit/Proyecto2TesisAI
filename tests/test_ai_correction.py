"""Tests for AI correction post-processing in AIService."""

import json

from app.core.services.ai.ai_service import AIService


def test_parse_corrected_json_merges_by_section_id_not_by_order():
    original = [
        {"sectionId": "sec-0001", "path": "A", "content": "orig-a"},
        {"sectionId": "sec-0002", "path": "B", "content": "orig-b"},
    ]
    raw = json.dumps(
        {
            "sections": [
                {"sectionId": "sec-0002", "path": "B", "content": "new-b"},
                {"sectionId": "sec-0001", "path": "A", "content": "new-a"},
            ]
        }
    )

    out = AIService._parse_corrected_json(raw, original, "proj-1")

    assert out == [
        {"sectionId": "sec-0001", "path": "A", "content": "new-a"},
        {"sectionId": "sec-0002", "path": "B", "content": "new-b"},
    ]


def test_parse_corrected_json_accepts_partial_sections_and_keeps_missing_original():
    original = [
        {"sectionId": "sec-0001", "path": "A", "content": "orig-a"},
        {"sectionId": "sec-0002", "path": "B", "content": "orig-b"},
    ]
    raw = json.dumps(
        {
            "sections": [
                {"sectionId": "sec-0002", "path": "B", "content": "new-b"},
            ]
        }
    )

    out = AIService._parse_corrected_json(raw, original, "proj-2")

    assert out == [
        {"sectionId": "sec-0001", "path": "A", "content": "orig-a"},
        {"sectionId": "sec-0002", "path": "B", "content": "new-b"},
    ]


def test_parse_corrected_json_ignores_invalid_content_type():
    original = [{"sectionId": "sec-0001", "path": "A", "content": "orig-a"}]
    raw = json.dumps({"sections": [{"sectionId": "sec-0001", "content": 12345}]})

    out = AIService._parse_corrected_json(raw, original, "proj-3")
    assert out == original


def test_parse_corrected_json_keeps_original_when_corrected_content_sanitizes_empty():
    original = [
        {
            "sectionId": "sec-0010",
            "path": "II. MARCO TEORICO/2.2 Bases teoricas",
            "content": "Texto teorico original suficientemente amplio para conservarse.",
        }
    ]
    raw = json.dumps(
        {
            "sections": [
                {
                    "sectionId": "sec-0010",
                    "content": (
                        "<<<FORMULA_JSON\n"
                        "{\"tipo\":\"formula\",\"texto\":\"NPR = S x O x D\"}\n"
                        "FORMULA_JSON>>>"
                    ),
                }
            ]
        }
    )

    out = AIService._parse_corrected_json(raw, original, "proj-4")
    assert out == original


def test_parse_corrected_json_keeps_dense_theoretical_bases_when_correction_collapses():
    original_text = " ".join(["fundamento"] * 420)
    original = [
        {
            "sectionId": "sec-0010",
            "path": "II. MARCO TEORICO/2.2 Bases teoricas",
            "content": original_text,
        }
    ]
    raw = json.dumps(
        {
            "sections": [
                {
                    "sectionId": "sec-0010",
                    "content": " ".join(["resumen"] * 40),
                }
            ]
        }
    )

    out = AIService._parse_corrected_json(raw, original, "proj-5")
    assert out == original


def test_parse_corrected_json_keeps_theoretical_bases_when_correction_removes_numbered_subtopics():
    original = [
        {
            "sectionId": "sec-0010",
            "path": "II. MARCO TEORICO/2.2 Bases teoricas",
            "content": (
                "2.2.1 Fundamento teorico\n\n"
                + " ".join(["teoria"] * 120)
                + "\n\n2.2.2 Modelo aplicado\n\n"
                + " ".join(["modelo"] * 120)
                + "\n\n2.2.3 Taxonomia tecnica\n\n"
                + " ".join(["taxonomia"] * 120)
                + "\n\n2.2.4 Herramienta especializada\n\n"
                + " ".join(["herramienta"] * 120)
                + "\n\n2.2.5 Indicadores del estudio\n\n"
                + " ".join(["indicador"] * 120)
            ),
        }
    ]
    raw = json.dumps(
        {
            "sections": [
                {
                    "sectionId": "sec-0010",
                    "content": " ".join(["resumen"] * 180),
                }
            ]
        }
    )

    out = AIService._parse_corrected_json(raw, original, "proj-6")
    assert out == original


def test_parse_corrected_json_keeps_theoretical_bases_when_correction_injects_figures():
    original = [
        {
            "sectionId": "sec-0010",
            "path": "II. MARCO TEORICO/2.2 Bases teoricas",
            "content": (
                "2.2.1 Fundamento teorico\n\n"
                + " ".join(["teoria"] * 100)
                + "\n\n2.2.2 Modelo aplicado\n\n"
                + " ".join(["modelo"] * 100)
                + "\n\n2.2.3 Taxonomia tecnica\n\n"
                + " ".join(["taxonomia"] * 100)
                + "\n\n2.2.4 Herramienta especializada\n\n"
                + " ".join(["herramienta"] * 100)
                + "\n\n2.2.5 Indicadores del estudio\n\n"
                + " ".join(["indicador"] * 100)
            ),
        }
    ]
    raw = json.dumps(
        {
            "sections": [
                {
                    "sectionId": "sec-0010",
                    "content": [
                        {"tipo": "parrafo", "texto": "2.2.1 Fundamento teorico"},
                        {"tipo": "figura", "caption": "Figura de ejemplo", "titulo": "Figura de ejemplo"},
                    ],
                }
            ]
        }
    )

    out = AIService._parse_corrected_json(raw, original, "proj-7")
    assert out == original


def test_build_correction_prompt_replaces_markers(tmp_path):
    prompt_template = (
        "FORMAT_JSON:\\n<<<FORMAT_JSON>>>\\n"
        "VALUES_JSON:\\n<<<VALUES_JSON>>>\\n"
        "AI_RESULT_JSON:\\n<<<AI_RESULT_JSON>>>\\n"
    )
    prompt_file = tmp_path / "correction_prompt.txt"
    prompt_file.write_text(prompt_template, encoding="utf-8")

    service = AIService()
    service._CORRECTION_PROMPT_PATH = prompt_file

    sections = [{"sectionId": "sec-0001", "path": "A", "content": "x"}]
    definition = {"cuerpo": [{"titulo": "Intro"}]}
    values = {"tema": "IA"}

    out = service._build_correction_prompt(sections, definition, values)

    assert "<<<FORMAT_JSON>>>" not in out
    assert "<<<VALUES_JSON>>>" not in out
    assert "<<<AI_RESULT_JSON>>>" not in out
    assert "\"sections\"" in out
    assert "\"tema\": \"IA\"" in out
