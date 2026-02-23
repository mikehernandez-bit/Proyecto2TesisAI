"""Tests for the shared TOC / index detector."""

import pytest

from app.core.services.toc_detector import is_toc_path, is_toc_title, normalize_title

# ---------------------------------------------------------------------------
# normalize_title
# ---------------------------------------------------------------------------


class TestNormalizeTitle:
    def test_strips_accents(self):
        assert normalize_title("ÍNDICE") == "indice"

    def test_lowercases(self):
        assert normalize_title("INDICE DE TABLAS") == "indice de tablas"

    def test_collapses_whitespace(self):
        assert normalize_title("  ÍNDICE   DE   TABLAS  ") == "indice de tablas"

    def test_empty_input(self):
        assert normalize_title("") == ""
        assert normalize_title(None) == ""

    def test_preserves_regular_text(self):
        assert normalize_title("I. PLANTEAMIENTO DEL PROBLEMA") == "i. planteamiento del problema"


# ---------------------------------------------------------------------------
# is_toc_title
# ---------------------------------------------------------------------------


class TestIsTocTitle:
    @pytest.mark.parametrize(
        "title",
        [
            "ÍNDICE",
            "Índice",
            "indice",
            "INDICE",
            "ÍNDICE DE TABLAS",
            "Indice de Tablas",
            "ÍNDICE DE FIGURAS",
            "ÍNDICE DE ABREVIATURAS",
            "ÍNDICE DE CONTENIDO",
            "ÍNDICE DE CONTENIDOS",
            "TABLA DE CONTENIDO",
            "TABLA DE CONTENIDOS",
            "Table of Contents",
            "TABLE OF CONTENTS",
            "TOC",
            "toc",
            "  ÍNDICE  ",
        ],
    )
    def test_known_toc_titles(self, title):
        assert is_toc_title(title) is True, f"Expected True for '{title}'"

    @pytest.mark.parametrize(
        "title",
        [
            "I. PLANTEAMIENTO DEL PROBLEMA",
            "INTRODUCCIÓN",
            "Introduccion",
            "MARCO TEÓRICO",
            "CONTENIDO",
            "contenido",
            "Capitulo I",
            "",
        ],
    )
    def test_non_toc_titles(self, title):
        assert is_toc_title(title) is False, f"Expected False for '{title}'"


# ---------------------------------------------------------------------------
# is_toc_path
# ---------------------------------------------------------------------------


class TestIsTocPath:
    def test_single_segment_toc(self):
        assert is_toc_path("ÍNDICE") is True

    def test_single_segment_non_toc(self):
        assert is_toc_path("INTRODUCCIÓN") is False

    def test_first_segment_toc(self):
        assert is_toc_path("ÍNDICE/I. PLANTEAMIENTO") is True

    def test_nested_toc_segment(self):
        assert is_toc_path("ÍNDICE/ÍNDICE DE TABLAS") is True

    def test_chapter_under_toc_parent(self):
        assert is_toc_path("ÍNDICE/II. MARCO TEÓRICO") is True

    def test_normal_chapter_path(self):
        assert is_toc_path("I. PLANTEAMIENTO/1.1 Problema") is False

    def test_empty_path(self):
        assert is_toc_path("") is False
        assert is_toc_path(None) is False

    def test_toc_in_middle_segment(self):
        assert is_toc_path("PRELIMINARES/ÍNDICE DE FIGURAS/Figura 1") is True

    def test_indice_de_tablas_standalone(self):
        assert is_toc_path("ÍNDICE DE TABLAS") is True

    def test_table_of_contents_english(self):
        assert is_toc_path("Table of Contents/Chapter I") is True
