"""Tests for GicaTesis AI-result adapter in API router."""

import pytest

from app.integrations.gicatesis.types import RenderPayloadValidationError
from app.modules.api.router import (
    _adapt_ai_result_for_gicatesis,
    _build_render_payload,
    _extract_resume_seed_sections,
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


def test_build_render_payload_canonicalizes_figure_placeholder():
    payload = _build_render_payload(
        format_id="unac-proyecto-cual",
        values={"title": "Titulo"},
        ai_result_raw={
            "sections": [
                {
                    "sectionId": "sec-0002",
                    "path": "II. MARCO TEORICO/2.1 Bases teoricas",
                    "content": [
                        {
                            "tipo": "figura",
                            "caption": "Figura 1. Modelo conceptual.",
                            "ruta_placeholder": "placeholder",
                        }
                    ],
                }
            ]
        },
    )

    content = payload["aiResult"]["sections"][0]["content"]
    assert isinstance(content, list)
    assert content[0]["ruta_placeholder"] == "assets/placeholder_figura.png"


def test_build_render_payload_raises_for_invalid_structured_block():
    with pytest.raises(RenderPayloadValidationError):
        _build_render_payload(
            format_id="unac-proyecto-cual",
            values={"title": "Titulo"},
            ai_result_raw={
                "sections": [
                    {
                        "sectionId": "sec-0003",
                        "path": "Cronograma",
                        "content": [
                            {
                                "tipo": "tabla",
                                "encabezados": [],
                                "filas": [],
                            }
                        ],
                    }
                ]
            },
        )


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


def test_adapter_flattens_structured_content_for_text_only_sections():
    ai_result = {
        "sections": [
            {
                "sectionId": "sec-intro",
                "path": "Introduccion",
                "content": [
                    {"tipo": "parrafo", "texto": "Texto introductorio limpio."},
                    {
                        "tipo": "tabla",
                        "titulo": "Tabla que no debe salir",
                        "encabezados": ["A", "B"],
                        "filas": [["1", "2"]],
                    },
                    {"tipo": "figura", "caption": "Figura que no debe salir"},
                ],
            }
        ]
    }

    out = _adapt_ai_result_for_gicatesis(ai_result)
    content = out["sections"][0]["content"]
    assert isinstance(content, str)
    assert content == "Texto introductorio limpio."


def test_adapter_flattens_structured_content_for_non_allowed_sections():
    ai_result = {
        "sections": [
            {
                "sectionId": "sec-problema",
                "path": "I. PLANTEAMIENTO DEL PROBLEMA/1.1 Descripcion",
                "content": [
                    {"tipo": "parrafo", "texto": "Texto del problema."},
                    {"tipo": "figura", "caption": "Figura que no corresponde."},
                ],
            }
        ]
    }

    out = _adapt_ai_result_for_gicatesis(ai_result)
    assert out["sections"][0]["content"] == "Texto del problema."


def test_adapter_keeps_structured_content_for_allowed_sections():
    ai_result = {
        "sections": [
            {
                "sectionId": "sec-marco",
                "path": "II. MARCO TEORICO/2.1 Bases teoricas",
                "content": [
                    {"tipo": "parrafo", "texto": "Texto del marco."},
                    {"tipo": "figura", "caption": "Figura 1. Modelo conceptual."},
                ],
            }
        ]
    }

    out = _adapt_ai_result_for_gicatesis(ai_result)
    content = out["sections"][0]["content"]
    assert isinstance(content, list)
    assert [item["tipo"] for item in content] == ["parrafo", "figura"]


def test_adapter_keeps_structured_content_for_discussion_sections():
    ai_result = {
        "sections": [
            {
                "sectionId": "sec-disc",
                "path": "VI. DISCUSION DE RESULTADOS/6.1 Discusion",
                "content": [
                    {"tipo": "parrafo", "texto": "La discusion contrasta hallazgos con antecedentes relevantes."},
                    {"tipo": "figura", "caption": "Relacion entre hallazgos y antecedentes."},
                ],
            }
        ]
    }

    out = _adapt_ai_result_for_gicatesis(ai_result)
    content = out["sections"][0]["content"]
    assert isinstance(content, list)
    assert [item["tipo"] for item in content] == ["parrafo", "figura"]


def test_adapter_merges_parent_structured_content_into_first_child():
    ai_result = {
        "sections": [
            {
                "sectionId": "sec-met-parent",
                "path": "III. METODOLOGIA",
                "content": [
                    {"tipo": "parrafo", "texto": "Contexto metodologico."},
                    {
                        "tipo": "tabla",
                        "titulo": "Tabla 1. Variables",
                        "encabezados": ["Variable", "Indicador"],
                        "filas": [["A", "I1"]],
                    },
                ],
            },
            {
                "sectionId": "sec-met-child",
                "path": "III. METODOLOGIA/3.1 Diseno",
                "content": "Texto especifico del diseno.",
            },
        ]
    }

    out = _adapt_ai_result_for_gicatesis(ai_result)
    assert len(out["sections"]) == 1
    content = out["sections"][0]["content"]
    assert isinstance(content, list)
    assert content[0]["tipo"] == "parrafo"
    assert content[1]["tipo"] == "tabla"
    assert content[2]["tipo"] == "parrafo"


def test_adapter_drops_old_raw_structured_string_payloads():
    ai_result = {
        "sections": [
            {
                "sectionId": "sec-bad",
                "path": "II. MARCO TEORICO/2.1 Bases teoricas",
                "content": "[{'tipo': 'tabla', 'titulo': 'Tabla rota'}]",
            },
            {
                "sectionId": "sec-good",
                "path": "II. MARCO TEORICO/2.2 Antecedentes",
                "content": "Texto valido.",
            },
        ]
    }

    out = _adapt_ai_result_for_gicatesis(ai_result)
    assert len(out["sections"]) == 1
    assert out["sections"][0]["sectionId"] == "sec-good"


def test_adapter_strips_raw_structured_lines_from_old_mixed_strings():
    ai_result = {
        "sections": [
            {
                "sectionId": "sec-mixed",
                "path": "II. MARCO TEORICO/2.1 Bases teoricas",
                "content": ("Texto valido antes.\n{'tipo': 'figura', 'caption': 'Figura rota'}\nTexto valido despues."),
            }
        ]
    }

    out = _adapt_ai_result_for_gicatesis(ai_result)
    content = out["sections"][0]["content"]
    assert isinstance(content, str)
    assert "tipo" not in content
    assert "Texto valido antes." in content
    assert "Texto valido despues." in content


def test_extract_resume_seed_sections_preserves_structured_content():
    seeds = _extract_resume_seed_sections(
        {
            "sections": [
                {
                    "sectionId": "sec-1",
                    "path": "Cronograma",
                    "content": [
                        {"tipo": "parrafo", "texto": "Texto previo."},
                        {
                            "tipo": "tabla",
                            "titulo": "Cronograma",
                            "encabezados": ["Actividad", "Mes 1"],
                            "filas": [["Revision", "X"]],
                        },
                    ],
                }
            ]
        }
    )

    assert len(seeds) == 1
    assert isinstance(seeds[0]["content"], list)
