"""Shared TOC / index detection utilities.

This module provides a single source of truth for deciding whether a
section title or path refers to a Table of Contents entry (TOC, index,
list of tables/figures, etc.) that must **never** be sent to AI for
content generation.

Used by:
- ``definition_compiler`` (compile-time exclusion)
- ``output_validator`` (runtime defence)
- ``router._adapt_ai_result_for_gicatesis`` (payload defence)
"""

from __future__ import annotations

import unicodedata
from typing import Any

# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------


def normalize_title(value: Any) -> str:
    """Accent-, case- and whitespace-insensitive normalisation.

    ``"ÍNDICE DE TABLAS"`` → ``"indice de tablas"``
    """
    text = str(value or "").strip().lower()
    if not text:
        return ""
    ascii_only = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_only.split())


# ---------------------------------------------------------------------------
# Known TOC / index titles (normalised form)
# ---------------------------------------------------------------------------

TOC_TITLES: frozenset[str] = frozenset(
    {
        "indice",
        "indice de contenido",
        "indice de contenidos",
        "indice de tablas",
        "indice de figuras",
        "indice de abreviaturas",
        "tabla de contenido",
        "tabla de contenidos",
        "table of contents",
        "toc",
    }
)


# ---------------------------------------------------------------------------
# Public predicates
# ---------------------------------------------------------------------------


def is_toc_title(title: str) -> bool:
    """Return *True* when *title* is a known TOC / index heading.

    Handles accented characters (``ÍNDICE``), mixed case, and leading/
    trailing whitespace transparently.

    Does **not** match partial substrings: ``"contenido"`` alone returns
    *False* to avoid flagging real chapter titles.
    """
    normalized = normalize_title(title)
    if not normalized:
        return False
    return normalized in TOC_TITLES


def is_toc_path(path: str) -> bool:
    """Return *True* when **any** segment of a ``/``-separated path is a
    known TOC title.

    ``"ÍNDICE/I. PLANTEAMIENTO"`` → *True* (first segment matches).
    ``"I. PLANTEAMIENTO/1.1 Problema"`` → *False*.
    """
    for part in str(path or "").split("/"):
        if is_toc_title(part):
            return True
    return False
