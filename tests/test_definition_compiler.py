"""Tests for section-index compilation rules."""

from app.core.services.definition_compiler import compile_definition_to_section_index


def test_section_index_excludes_preliminaries_indexes_and_keeps_body():
    definition = {
        "preliminares": {
            "indices": [
                {
                    "titulo": "INDICE",
                    "items": [
                        {"texto": "I. PLANTEAMIENTO DEL PROBLEMA"},
                        {"texto": "II. MARCO TEORICO"},
                    ],
                },
                {
                    "titulo": "INDICE DE TABLAS",
                    "items": [{"texto": "Tabla 1.1 Matriz de consistencia"}],
                },
            ],
            "abreviaturas": {
                "titulo": "INDICE DE ABREVIATURAS",
                "nota": "Lista limpia de siglas.",
            },
            "introduccion": {"titulo": "INTRODUCCION"},
        },
        "cuerpo": [
            {
                "titulo": "I. PLANTEAMIENTO DEL PROBLEMA",
                "contenido": [
                    {"texto": "1.1 Descripcion de la realidad problematica"},
                ],
            }
        ],
        "finales": {
            "anexos": {
                "titulo_seccion": "ANEXOS",
                "lista": [{"titulo": "Anexo 1: Matriz de consistencia"}],
            }
        },
    }

    section_index = compile_definition_to_section_index(definition)
    paths = [item["path"] for item in section_index]

    assert all(not path.startswith("INDICE/") for path in paths)
    assert "INDICE" not in paths
    assert "INDICE DE TABLAS" not in paths
    assert "INDICE DE FIGURAS" not in paths
    assert "INDICE DE ABREVIATURAS" not in paths
    assert "I. PLANTEAMIENTO DEL PROBLEMA" in paths
    assert any(path.startswith("I. PLANTEAMIENTO DEL PROBLEMA/1.1") for path in paths)
    assert "ANEXOS" in paths


def test_section_index_skips_figure_and_table_placeholder_nodes():
    definition = {
        "cuerpo": [
            {
                "titulo": "I. CAPITULO DE PRUEBA",
                "contenido": [
                    {
                        "texto": "1.1 Seccion principal",
                        "imagenes": [{"titulo": "Figura 1.1 Ejemplo"}],
                        "tablas": [{"titulo": "Tabla 1.1 Ejemplo"}],
                    }
                ],
            }
        ]
    }

    section_index = compile_definition_to_section_index(definition)
    paths = [item["path"] for item in section_index]

    assert "I. CAPITULO DE PRUEBA" in paths
    assert any(path.endswith("1.1 Seccion principal") for path in paths)
    assert all("Figura 1.1" not in path for path in paths)
    assert all("Tabla 1.1" not in path for path in paths)


def test_section_index_excludes_accented_indices():
    """ÍNDICE (with accent) must be excluded just like INDICE."""
    definition = {
        "preliminares": {
            "indices": [
                {
                    "titulo": "ÍNDICE",
                    "items": [
                        {"texto": "ÍNDICE", "pag": 1},
                        {"texto": "I. PLANTEAMIENTO DEL PROBLEMA", "pag": 6},
                    ],
                },
                {
                    "titulo": "ÍNDICE DE TABLAS",
                    "items": [{"texto": "Tabla 1.1 Ejemplo", "pag": 8}],
                },
            ],
            "introduccion": {"titulo": "INTRODUCCIÓN"},
        },
        "cuerpo": [
            {
                "titulo": "I. PLANTEAMIENTO DEL PROBLEMA",
                "contenido": [
                    {"texto": "1.1 Descripción de la realidad problemática"},
                ],
            }
        ],
    }

    section_index = compile_definition_to_section_index(definition)
    paths = [item["path"] for item in section_index]

    # No TOC paths leaked
    assert all("ÍNDICE" not in p and "INDICE" not in p.upper() for p in paths)
    # Real sections are present
    assert any("INTRODUCCIÓN" in p for p in paths)
    assert any("1.1" in p for p in paths)


def test_section_index_excludes_dict_style_indices():
    """Handles the dict-style indices (pre-array format variant)."""
    definition = {
        "preliminares": {
            "indices": {
                "contenido": "ÍNDICE DE CONTENIDO",
                "tablas": "ÍNDICE DE TABLAS",
                "figuras": "ÍNDICE DE FIGURAS",
                "placeholder": "(Generarlo)",
            },
            "introduccion": {"titulo": "INTRODUCCIÓN"},
        },
        "cuerpo": [
            {"titulo": "I. CAPITULO", "contenido": [{"texto": "1.1 Seccion"}]}
        ],
    }

    section_index = compile_definition_to_section_index(definition)
    paths = [item["path"] for item in section_index]

    assert all("INDICE" not in p.upper() for p in paths)
    assert any("INTRODUCCIÓN" in p for p in paths)
    assert any("1.1" in p for p in paths)


def test_introduccion_and_all_chapters_are_generative():
    """Verify INTRODUCCIÓN + all cuerpo chapters are emitted."""
    definition = {
        "preliminares": {
            "indices": [{"titulo": "ÍNDICE", "items": []}],
            "introduccion": {"titulo": "INTRODUCCIÓN"},
        },
        "cuerpo": [
            {
                "titulo": "I. PLANTEAMIENTO DEL PROBLEMA",
                "contenido": [
                    {"texto": "1.1 Realidad problemática"},
                    {"texto": "1.2 Formulación del problema"},
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

    section_index = compile_definition_to_section_index(definition)
    paths = [item["path"] for item in section_index]

    assert any("INTRODUCCIÓN" in p for p in paths)
    assert any("I. PLANTEAMIENTO DEL PROBLEMA" in p for p in paths)
    assert any("1.1" in p for p in paths)
    assert any("1.2" in p for p in paths)
    assert any("II. MARCO TEÓRICO" in p for p in paths)
    assert any("2.1" in p for p in paths)
    # sectionId is stable and sequential
    ids = [item["sectionId"] for item in section_index]
    assert ids[0] == "sec-0001"
    assert all(sid.startswith("sec-") for sid in ids)
