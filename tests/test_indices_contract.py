"""Tests for the indices normalizer, content sanitizer, and updated compiler."""

from __future__ import annotations

import copy

from app.core.services.content_sanitizer import (
    has_leader_page_pattern,
    sanitize_text_block,
    strip_leader_page,
)
from app.core.services.definition_compiler import (
    IRNodeType,
    compile_definition_to_ir,
    compile_definition_to_section_index,
)
from app.core.services.indices_normalizer import (
    normalize_definition,
    normalize_indices,
)

# -----------------------------------------------------------------------
# Indices Normalizer
# -----------------------------------------------------------------------


class TestNormalizeIndicesDict:
    """Dict-style indices (Variant A)."""

    def test_dict_to_directives(self):
        raw: dict = {
            "contenido": "ÍNDICE DE CONTENIDO",
            "tablas": "ÍNDICE DE TABLAS",
            "figuras": "ÍNDICE DE FIGURAS",
            "abreviaturas": "ÍNDICE DE ABREVIATURAS",
            "placeholder": "(Generarlo)",
        }
        result = normalize_indices(raw)
        assert result is not None
        assert len(result) == 4
        assert result[0]["type"] == "toc"
        assert result[0]["title"] == "ÍNDICE DE CONTENIDO"
        assert result[0]["page_break_after"] is True
        assert result[0]["update_fields_on_open"] is True
        assert result[1]["type"] == "toc_tables"
        assert result[2]["type"] == "toc_figures"
        assert result[3]["type"] == "toc_abbreviations"

    def test_placeholder_key_is_ignored(self):
        raw = {"contenido": "ÍNDICE", "placeholder": "(Generarlo)"}
        result = normalize_indices(raw)
        assert result is not None
        assert len(result) == 1
        assert all(d.get("placeholder") is None for d in result)


class TestNormalizeIndicesArray:
    """Array-style indices (Variant B) — the problematic format."""

    ARRAY_INPUT = [
        {
            "titulo": "ÍNDICE",
            "items": [
                {"texto": "ÍNDICE", "pag": 1},
                {"texto": "I. PLANTEAMIENTO DEL PROBLEMA", "pag": 6, "bold": True},
            ],
        },
        {
            "titulo": "ÍNDICE DE TABLAS",
            "items": [{"texto": "Tabla 1.1...", "pag": 8}],
        },
        {
            "titulo": "ÍNDICE DE FIGURAS",
            "items": [{"texto": "Figura 1...", "pag": 7}],
        },
        {
            "titulo": "ÍNDICE DE ABREVIATURAS",
            "items": [{"texto": "OMS", "pag": 6}],
            "nota": "...",
        },
    ]

    def test_array_to_directives(self):
        result = normalize_indices(self.ARRAY_INPUT)
        assert result is not None
        assert len(result) == 4
        assert result[0]["type"] == "toc"
        assert result[0]["title"] == "ÍNDICE"
        # items with pag numbers must be discarded
        assert "items" not in result[0]
        # No raw "pag" keys from the original items survive
        for d in result:
            assert "pag" not in d, f"raw 'pag' key found in directive: {d}"
        assert result[1]["type"] == "toc_tables"
        assert result[2]["type"] == "toc_figures"
        assert result[3]["type"] == "toc_abbreviations"

    def test_page_numbers_stripped(self):
        """No ``pag`` field survives normalisation."""
        result = normalize_indices(self.ARRAY_INPUT)
        for d in result:
            assert "pag" not in d
            assert "items" not in d


class TestNormalizeIndicesAlreadyNormalised:
    """Already-normalised input should pass through unchanged."""

    def test_passthrough(self):
        directives = [
            {
                "type": "toc",
                "title": "ÍNDICE",
                "levels": "1-3",
                "page_break_after": True,
                "update_fields_on_open": True,
            }
        ]
        result = normalize_indices(directives)
        assert result is directives  # same object, not a copy

    def test_none_returns_none(self):
        assert normalize_indices(None) is None

    def test_empty_list_returns_none(self):
        assert normalize_indices([]) is None


class TestNormalizeDefinition:
    """Full definition normalisation."""

    def test_dict_indices_in_definition(self):
        definition = {
            "preliminares": {
                "indices": {
                    "contenido": "ÍNDICE DE CONTENIDO",
                    "tablas": "ÍNDICE DE TABLAS",
                },
                "introduccion": {"titulo": "INTRODUCCIÓN"},
            },
            "cuerpo": [{"titulo": "I. PLANTEAMIENTO"}],
        }
        original = copy.deepcopy(definition)
        result = normalize_definition(definition)

        # Original must NOT be mutated
        assert definition == original
        # Result has normalised indices
        indices = result["preliminares"]["indices"]
        assert isinstance(indices, list)
        assert indices[0]["type"] == "toc"
        assert indices[1]["type"] == "toc_tables"

    def test_no_indices_passes_through(self):
        definition = {"cuerpo": [{"titulo": "Test"}]}
        result = normalize_definition(definition)
        assert result is definition  # no copy needed


# -----------------------------------------------------------------------
# Content Sanitizer
# -----------------------------------------------------------------------


class TestHasLeaderPagePattern:
    def test_with_dots(self):
        assert has_leader_page_pattern("I. PLANTEAMIENTO ..... 6")

    def test_with_many_dots(self):
        assert has_leader_page_pattern("ÍNDICE DE TABLAS .............. 28")

    def test_with_pag_x(self):
        assert has_leader_page_pattern("Tabla 1.1. Datos ......... pag X")

    def test_with_spaces_and_number(self):
        assert has_leader_page_pattern("INTRODUCCIÓN          5")

    def test_clean_text(self):
        assert not has_leader_page_pattern("El planteamiento del problema se refiere a")

    def test_empty(self):
        assert not has_leader_page_pattern("")

    def test_short_dots_not_matched(self):
        """Two dots (like abbreviation) should NOT match."""
        assert not has_leader_page_pattern("Dr.. Smith")


class TestStripLeaderPage:
    def test_strip_dots_and_number(self):
        assert strip_leader_page("MARCO TEÓRICO ..... 10") == "MARCO TEÓRICO"

    def test_strip_pag_x(self):
        assert strip_leader_page("Tabla 1.1. Datos ... pag X") == "Tabla 1.1. Datos"

    def test_clean_line_unchanged(self):
        line = "Este es un párrafo normal."
        assert strip_leader_page(line) == line


class TestSanitizeTextBlock:
    def test_multiline(self):
        text = "ÍNDICE ..... 1\nINTRODUCCIÓN ..... 5\nActual content here"
        result = sanitize_text_block(text)
        assert "....." not in result
        assert "Actual content here" in result

    def test_empty(self):
        assert sanitize_text_block("") == ""

    def test_all_patterns_removed(self):
        text = "Heading .............. 28\nAnother ..... pag 12"
        result = sanitize_text_block(text)
        assert "28" not in result
        assert "pag" not in result.lower()
        assert "Heading" in result
        assert "Another" in result


# -----------------------------------------------------------------------
# Compiler with normalised indices
# -----------------------------------------------------------------------


class TestCompilerWithTocDirectives:
    """compile_definition_to_ir should emit TOC/list nodes from directives."""

    def test_dict_indices_produce_toc_node(self):
        definition = {
            "preliminares": {
                "indices": {
                    "contenido": "ÍNDICE DE CONTENIDO",
                    "tablas": "ÍNDICE DE TABLAS",
                    "figuras": "ÍNDICE DE FIGURAS",
                    "abreviaturas": "ÍNDICE DE ABREVIATURAS",
                    "placeholder": "(Generarlo)",
                }
            },
            "cuerpo": [{"titulo": "I. PLANTEAMIENTO"}],
        }
        ir = compile_definition_to_ir(definition)
        node_types = [n.node_type for n in ir.nodes]
        assert IRNodeType.TOC_PLACEHOLDER in node_types
        assert IRNodeType.LIST_TABLES in node_types
        assert IRNodeType.LIST_FIGURES in node_types
        assert IRNodeType.LIST_ABBREVIATIONS in node_types

    def test_array_indices_produce_toc_node(self):
        definition = {
            "preliminares": {
                "indices": [
                    {
                        "titulo": "ÍNDICE",
                        "items": [
                            {"texto": "I. PLANTEAMIENTO", "pag": 6},
                        ],
                    },
                    {
                        "titulo": "ÍNDICE DE TABLAS",
                        "items": [{"texto": "Tabla 1", "pag": 8}],
                    },
                ]
            },
            "cuerpo": [{"titulo": "I. PLANTEAMIENTO"}],
        }
        ir = compile_definition_to_ir(definition)
        toc_nodes = [n for n in ir.nodes if n.node_type == IRNodeType.TOC_PLACEHOLDER]
        assert len(toc_nodes) >= 1
        assert toc_nodes[0].text == "ÍNDICE"
        list_nodes = [n for n in ir.nodes if n.node_type == IRNodeType.LIST_TABLES]
        assert len(list_nodes) >= 1

    def test_no_indices_emits_default_toc(self):
        definition = {"cuerpo": [{"titulo": "Test"}]}
        ir = compile_definition_to_ir(definition)
        toc_nodes = [n for n in ir.nodes if n.node_type == IRNodeType.TOC_PLACEHOLDER]
        assert len(toc_nodes) == 1
        assert toc_nodes[0].text == "TABLA DE CONTENIDO"

    def test_already_normalised_indices_work(self):
        definition = {
            "preliminares": {
                "indices": [
                    {
                        "type": "toc",
                        "title": "MI ÍNDICE",
                        "levels": "1-3",
                        "page_break_after": True,
                        "update_fields_on_open": True,
                    }
                ]
            },
            "cuerpo": [{"titulo": "Cap 1"}],
        }
        ir = compile_definition_to_ir(definition)
        toc = [n for n in ir.nodes if n.node_type == IRNodeType.TOC_PLACEHOLDER]
        assert len(toc) == 1
        assert toc[0].text == "MI ÍNDICE"

    def test_no_pag_numbers_in_ir_text(self):
        """Page numbers from array indices must not leak into IR node text."""
        definition = {
            "preliminares": {
                "indices": [
                    {
                        "titulo": "ÍNDICE",
                        "items": [
                            {"texto": "PLANTEAMIENTO", "pag": 6},
                            {"texto": "MARCO TEÓRICO", "pag": 10},
                        ],
                    }
                ]
            },
            "cuerpo": [{"titulo": "PLANTEAMIENTO"}],
        }
        ir = compile_definition_to_ir(definition)
        for node in ir.nodes:
            assert "pag" not in node.text.lower()
            # No stray numbers that look like page numbers
            if node.node_type == IRNodeType.TOC_PLACEHOLDER:
                assert node.text == "ÍNDICE"


class TestCompilerSectionIndexNormalised:
    """compile_definition_to_section_index must also normalise first."""

    def test_array_indices_not_in_section_index(self):
        """Array-style indices items must NOT appear as generative sections."""
        definition = {
            "preliminares": {
                "indices": [
                    {
                        "titulo": "ÍNDICE",
                        "items": [
                            {"texto": "I. PLANTEAMIENTO", "pag": 6},
                        ],
                    }
                ],
                "introduccion": {"titulo": "INTRODUCCIÓN"},
            },
            "cuerpo": [{"titulo": "I. PLANTEAMIENTO"}],
        }
        sections = compile_definition_to_section_index(definition)
        paths = [s["path"] for s in sections]
        # "ÍNDICE" paths must not appear in the section index
        for path in paths:
            assert "ÍNDICE" not in path.upper(), f"TOC path leaked into section index: {path}"
