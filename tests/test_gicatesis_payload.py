"""Tests for build_gicatesis_payload hierarchical assembly."""

from app.core.services.gicatesis_payload import build_gicatesis_payload

SAMPLE_FORMAT = {
    "preliminares": {
        "indices": [
            {
                "titulo": "ÍNDICE",
                "items": [{"texto": "ÍNDICE", "pag": 1}],
            }
        ],
        "introduccion": {
            "titulo": "INTRODUCCIÓN",
            "texto": "Guía original: escriba aquí su introducción.",
        },
    },
    "cuerpo": [
        {
            "titulo": "I. PLANTEAMIENTO DEL PROBLEMA",
            "nota_capitulo": "Nota interna del capítulo.",
            "contenido": [
                {
                    "texto": "1.1 Descripción de la realidad problemática",
                    "nota": "Nota interna",
                    "instruccion_detallada": "Instrucción larga para la IA.",
                },
                {
                    "texto": "1.2 Formulación del problema",
                },
            ],
        },
    ],
}


def test_injects_introduccion_desarrollo():
    ai_sections = [
        {"sectionId": "sec-0001", "path": "INTRODUCCIÓN", "content": "Contenido generado."},
    ]

    result = build_gicatesis_payload(SAMPLE_FORMAT, ai_sections)

    intro = result["preliminares"]["introduccion"]
    # AI content goes into "desarrollo" (body text), NOT "texto" (heading).
    # Placing content in "texto" would make it appear in the ÍNDICE (Word TOC).
    assert intro["desarrollo"] == "Contenido generado."
    # Original "texto" is preserved as-is (it's the section placeholder/title).
    assert intro["texto"] == "Guía original: escriba aquí su introducción."


def test_injects_desarrollo_into_cuerpo():
    ai_sections = [
        {
            "sectionId": "sec-0002",
            "path": "I. PLANTEAMIENTO DEL PROBLEMA/1.1 Descripción de la realidad problemática",
            "content": "Contenido generado para el subcapítulo.",
        },
    ]

    result = build_gicatesis_payload(SAMPLE_FORMAT, ai_sections)

    item = result["cuerpo"][0]["contenido"][0]
    # texto is preserved as title
    assert item["texto"] == "1.1 Descripción de la realidad problemática"
    # desarrollo contains the generated content
    assert item["desarrollo"] == "Contenido generado para el subcapítulo."


def test_moves_guidance_to_meta():
    ai_sections = []
    result = build_gicatesis_payload(SAMPLE_FORMAT, ai_sections)

    item = result["cuerpo"][0]["contenido"][0]
    # nota and instruccion_detallada are in _meta, not at top level
    assert "nota" not in item
    assert "instruccion_detallada" not in item
    assert item["_meta"]["nota"] == "Nota interna"
    assert item["_meta"]["instruccion_detallada"] == "Instrucción larga para la IA."

    # nota_capitulo at chapter level
    chapter = result["cuerpo"][0]
    assert "nota_capitulo" not in chapter
    assert chapter["_meta"]["nota_capitulo"] == "Nota interna del capítulo."


def test_indices_preserved_structurally():
    ai_sections = [
        {"sectionId": "x", "path": "ÍNDICE", "content": "Should be ignored"},
    ]

    result = build_gicatesis_payload(SAMPLE_FORMAT, ai_sections)

    # indices structure is preserved (not modified)
    assert "indices" in result["preliminares"]
    indices = result["preliminares"]["indices"]
    assert isinstance(indices, list)
    assert indices[0]["titulo"] == "ÍNDICE"
    # No "desarrollo" or "content" injected into indices
    assert "desarrollo" not in indices[0]


def test_does_not_mutate_original():
    ai_sections = [
        {"sectionId": "sec-0001", "path": "INTRODUCCIÓN", "content": "Generado."},
    ]

    import copy

    original = copy.deepcopy(SAMPLE_FORMAT)
    build_gicatesis_payload(SAMPLE_FORMAT, ai_sections)

    # Original format untouched
    assert SAMPLE_FORMAT == original
