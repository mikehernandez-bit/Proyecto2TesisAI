"""Integration test: full pipeline excludes TOC from AI generation.

Uses a minimal format definition and a fake AI provider to verify that:
1. The compiler never emits TOC sections.
2. The AI is never called for TOC paths.
3. The validator drops any TOC sections that somehow leak in.
4. The final adapted payload contains only real chapter content.
"""

from app.core.services.ai.output_validator import OutputValidator
from app.core.services.definition_compiler import compile_definition_to_section_index
from app.modules.api.router import _adapt_ai_result_for_gicatesis

# A minimal format that mirrors the problematic unac-proyecto-cual structure.
MINIMAL_FORMAT = {
    "preliminares": {
        "indices": [
            {
                "titulo": "ÍNDICE",
                "items": [
                    {"texto": "ÍNDICE", "pag": 1},
                    {"texto": "ÍNDICE DE TABLAS", "pag": 2},
                    {"texto": "ÍNDICE DE FIGURAS", "pag": 3},
                    {"texto": "INTRODUCCIÓN", "pag": 5},
                    {"texto": "I. PLANTEAMIENTO DEL PROBLEMA", "pag": 6},
                    {"texto": "II. MARCO TEÓRICO", "pag": 10},
                ],
            },
            {
                "titulo": "ÍNDICE DE TABLAS",
                "items": [{"texto": "Tabla 1.1 Ejemplo", "pag": 8}],
            },
            {
                "titulo": "ÍNDICE DE FIGURAS",
                "items": [{"texto": "Figura 1.1 Ejemplo", "pag": 7}],
            },
            {
                "titulo": "ÍNDICE DE ABREVIATURAS",
                "items": [{"texto": "OMS", "pag": 6}],
            },
        ],
        "introduccion": {
            "titulo": "INTRODUCCIÓN",
            "texto": "Guía: escriba aquí...",
        },
    },
    "cuerpo": [
        {
            "titulo": "I. PLANTEAMIENTO DEL PROBLEMA",
            "nota_capitulo": "Nota interna",
            "contenido": [
                {
                    "texto": "1.1 Descripción de la realidad problemática",
                    "nota": "Nota interna",
                    "instruccion_detallada": "Instrucción larga...",
                },
                {
                    "texto": "1.2 Formulación del problema",
                },
            ],
        },
        {
            "titulo": "II. MARCO TEÓRICO",
            "contenido": [
                {"texto": "2.1 Antecedentes"},
            ],
        },
    ],
}


def test_compiler_never_emits_toc():
    """compile_definition_to_section_index produces ZERO TOC paths."""
    section_index = compile_definition_to_section_index(MINIMAL_FORMAT)
    paths = [s["path"] for s in section_index]

    for path in paths:
        assert "ÍNDICE" not in path, f"TOC leaked: {path}"
        assert "INDICE" not in path.upper(), f"TOC leaked: {path}"

    # Real sections ARE present
    assert any("INTRODUCCIÓN" in p for p in paths)
    assert any("I. PLANTEAMIENTO DEL PROBLEMA" in p for p in paths)
    assert any("1.1" in p for p in paths)
    assert any("1.2" in p for p in paths)
    assert any("II. MARCO TEÓRICO" in p for p in paths)
    assert any("2.1" in p for p in paths)


def test_fake_provider_never_called_for_toc():
    """Simulate the AI loop and verify no TOC section is dispatched."""
    section_index = compile_definition_to_section_index(MINIMAL_FORMAT)

    called_paths = []

    def fake_provider(path: str, section_id: str) -> str:
        called_paths.append(path)
        return f"Generated content for {path}"

    # Simulate the AI loop (mirrors ai_service._generate_sections)
    ai_sections = []
    for sec in section_index:
        content = fake_provider(sec["path"], sec["sectionId"])
        ai_sections.append(
            {
                "sectionId": sec["sectionId"],
                "path": sec["path"],
                "content": content,
            }
        )

    # No TOC path was called
    for path in called_paths:
        assert "INDICE" not in path.upper(), f"Provider was called for TOC: {path}"


def test_validator_drops_injected_toc_sections():
    """If TOC sections somehow leak into aiResult, the validator drops them."""
    validator = OutputValidator()

    raw_sections = [
        # ToC sections (should be dropped)
        {"sectionId": "sec-0001", "path": "ÍNDICE", "content": "Fake TOC"},
        {"sectionId": "sec-0002", "path": "ÍNDICE/ÍNDICE", "content": "Fake"},
        {"sectionId": "sec-0003", "path": "ÍNDICE/I. PLANTEAMIENTO", "content": "Fake"},
        {"sectionId": "sec-0004", "path": "ÍNDICE DE TABLAS", "content": "Fake"},
        {"sectionId": "sec-0005", "path": "ÍNDICE DE FIGURAS", "content": "Fake"},
        {"sectionId": "sec-0006", "path": "ÍNDICE DE ABREVIATURAS", "content": "Fake"},
        # Real sections (should be kept)
        {"sectionId": "sec-0007", "path": "INTRODUCCIÓN", "content": "Real introduction"},
        {"sectionId": "sec-0008", "path": "I. PLANTEAMIENTO/1.1 Problema", "content": "Real chapter"},
    ]

    result = validator.build_ai_result(raw_sections)
    section_ids = [s["sectionId"] for s in result["sections"]]

    # All TOC sections dropped
    assert "sec-0001" not in section_ids
    assert "sec-0002" not in section_ids
    assert "sec-0003" not in section_ids
    assert "sec-0004" not in section_ids
    assert "sec-0005" not in section_ids
    assert "sec-0006" not in section_ids

    # Real sections kept
    assert "sec-0007" in section_ids
    assert "sec-0008" in section_ids


def test_adapter_filters_toc_from_old_project_data():
    """Old projects with contaminated aiResult are cleaned by the adapter."""
    ai_result = {
        "sections": [
            {"sectionId": "sec-0001", "path": "ÍNDICE", "content": '""'},
            {"sectionId": "sec-0002", "path": "ÍNDICE/ÍNDICE", "content": '""'},
            {"sectionId": "sec-0003", "path": "ÍNDICE/INTRODUCCIÓN", "content": "Real content"},
            {"sectionId": "sec-0004", "path": "ÍNDICE/I. PLANTEAMIENTO", "content": "Real content"},
            {"sectionId": "sec-0005", "path": "INTRODUCCIÓN", "content": "Clean content"},
            {"sectionId": "sec-0006", "path": "I. PLANTEAMIENTO/1.1 Problema", "content": "Clean content"},
        ]
    }

    adapted = _adapt_ai_result_for_gicatesis(ai_result)
    adapted_paths = [s["path"] for s in adapted["sections"]]

    # All ÍNDICE/* paths removed
    assert all("ÍNDICE" not in p and "INDICE" not in p.upper() for p in adapted_paths)
    # Clean sections kept
    assert "INTRODUCCIÓN" in adapted_paths
    assert "I. PLANTEAMIENTO/1.1 Problema" in adapted_paths


def test_end_to_end_pipeline():
    """Full pipeline: compile → generate → validate → adapt."""
    # Step 1: Compile
    section_index = compile_definition_to_section_index(MINIMAL_FORMAT)

    # Step 2: Simulate generation
    ai_sections = [
        {
            "sectionId": sec["sectionId"],
            "path": sec["path"],
            "content": f"Generated academic content for '{sec['path']}' "
            f"with sufficient length to pass validation checks.",
        }
        for sec in section_index
    ]

    # Step 3: Validate
    validator = OutputValidator()
    validated = validator.build_ai_result(ai_sections)

    # Step 4: Adapt for GicaTesis
    adapted = _adapt_ai_result_for_gicatesis(validated)

    # Verify: no TOC in final payload
    for sec in adapted["sections"]:
        assert "INDICE" not in sec["path"].upper(), f"TOC in final payload: {sec['path']}"

    # Verify: real sections present
    paths = [s["path"] for s in adapted["sections"]]
    assert any("INTRODUCCIÓN" in p for p in paths)
    assert any("I. PLANTEAMIENTO" in p for p in paths)
    assert any("1.1" in p for p in paths)
    assert len(adapted["sections"]) >= 6  # At least intro + chapters + subcapítulos
