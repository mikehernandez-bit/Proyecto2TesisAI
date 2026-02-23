"""Tests for GicaTesis AI-result adapter in API router."""

from app.modules.api.router import (
    _adapt_ai_result_for_gicatesis,
    _build_render_payload,
    _values_with_title,
)


def test_adapter_returns_empty_sections_for_invalid_payload():
    assert _adapt_ai_result_for_gicatesis(None) == {"sections": []}
    assert _adapt_ai_result_for_gicatesis({}) == {"sections": []}
    assert _adapt_ai_result_for_gicatesis({"sections": "x"}) == {"sections": []}


def test_adapter_keeps_only_canonical_paths():
    ai_result = {
        "sections": [
            {
                "sectionId": "sec-0001",
                "path": "Capitulo I/Introduccion",
                "content": "Texto IA",
            }
        ]
    }

    out = _adapt_ai_result_for_gicatesis(ai_result)
    sections = out["sections"]

    assert len(sections) == 1
    assert sections[0]["path"] == "Capitulo I/Introduccion"
    assert sections[0]["sectionId"] == "sec-0001"


def test_adapter_keeps_single_path_when_no_hierarchy():
    ai_result = {
        "sections": [
            {
                "sectionId": "sec-0002",
                "path": "Resumen",
                "content": "Contenido resumen",
            }
        ]
    }

    out = _adapt_ai_result_for_gicatesis(ai_result)
    assert len(out["sections"]) == 1
    assert out["sections"][0]["path"] == "Resumen"


def test_adapter_skips_empty_content():
    ai_result = {
        "sections": [
            {"path": "Capitulo I/Marco", "content": ""},
            {"path": "Capitulo I/Marco", "content": "  "},
            {"path": "Capitulo I/Marco", "content": "Valido"},
        ]
    }

    out = _adapt_ai_result_for_gicatesis(ai_result)
    assert len(out["sections"]) == 1
    assert all(s["content"].strip() for s in out["sections"])


def test_values_with_title_falls_back_to_project_title():
    project = {"title": "Titulo real de tesis"}
    values = {"tema": "IA aplicada"}
    enriched = _values_with_title(project, values)
    assert enriched["title"] == "Titulo real de tesis"
    assert enriched["tema"] == "IA aplicada"


def test_values_with_title_keeps_existing_title():
    project = {"title": "Titulo del proyecto"}
    values = {"title": "Titulo definido en values"}
    enriched = _values_with_title(project, values)
    assert enriched["title"] == "Titulo definido en values"


def test_adapter_drops_toc_sections():
    """Sections with TOC/index paths must be dropped even if content is nonempty."""
    ai_result = {
        "sections": [
            {
                "sectionId": "sec-0001",
                "path": "ÍNDICE",
                "content": "contenido que no debería estar",
            },
            {
                "sectionId": "sec-0002",
                "path": "ÍNDICE/I. PLANTEAMIENTO",
                "content": "contenido bajo índice",
            },
            {
                "sectionId": "sec-0003",
                "path": "ÍNDICE DE TABLAS",
                "content": "contenido tabla",
            },
            {
                "sectionId": "sec-0004",
                "path": "I. PLANTEAMIENTO/1.1 Problema",
                "content": "Contenido legit del capitulo",
            },
        ]
    }

    out = _adapt_ai_result_for_gicatesis(ai_result)
    assert len(out["sections"]) == 1
    assert out["sections"][0]["sectionId"] == "sec-0004"
    assert out["sections"][0]["path"] == "I. PLANTEAMIENTO/1.1 Problema"


def test_adapter_drops_accented_indice():
    """ÍNDICE with accent must also be dropped."""
    ai_result = {
        "sections": [
            {"sectionId": "s1", "path": "ÍNDICE DE FIGURAS", "content": "x"},
            {"sectionId": "s2", "path": "Introduccion", "content": "Texto real"},
        ]
    }
    out = _adapt_ai_result_for_gicatesis(ai_result)
    assert len(out["sections"]) == 1
    assert out["sections"][0]["sectionId"] == "s2"


def test_build_render_payload_preserves_ai_sections():
    payload = _build_render_payload(
        format_id="unac-proyecto-cual",
        values={"title": "Titulo"},
        ai_result_raw={
            "sections": [
                {
                    "sectionId": "sec-0001",
                    "path": "I. PLANTEAMIENTO/1.1 Problema",
                    "content": "Texto generado por IA.",
                }
            ]
        },
    )

    assert payload["formatId"] == "unac-proyecto-cual"
    assert payload["mode"] == "simulation"
    assert "definition" not in payload
    assert payload["aiResult"]["sections"][0]["content"] == "Texto generado por IA."


def test_adapter_moves_top_level_parent_content_into_first_child():
    ai_result = {
        "sections": [
            {
                "sectionId": "sec-0100",
                "path": "I. PLANTEAMIENTO DEL PROBLEMA",
                "content": "Contenido general del capitulo.",
            },
            {
                "sectionId": "sec-0101",
                "path": "I. PLANTEAMIENTO DEL PROBLEMA/1.1 Descripcion",
                "content": "Contenido especifico 1.1.",
            },
        ]
    }

    out = _adapt_ai_result_for_gicatesis(ai_result)
    sections = out["sections"]
    assert len(sections) == 1
    assert sections[0]["path"] == "I. PLANTEAMIENTO DEL PROBLEMA/1.1 Descripcion"
    assert "Contenido general del capitulo." in sections[0]["content"]
    assert "Contenido especifico 1.1." in sections[0]["content"]
