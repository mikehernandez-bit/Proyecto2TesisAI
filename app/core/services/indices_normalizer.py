"""Indices Normalizer — migrates legacy index declarations to TOC directives.

Legacy format definitions declare indices in two incompatible shapes:

**Variant A (dict):**
    ``{"contenido": "ÍNDICE DE CONTENIDO", "tablas": "...", "placeholder": "..."}``

**Variant B (array):**
    ``[{"titulo": "ÍNDICE", "items": [{"texto": "...", "pag": 8}, ...]}]``

Both are replaced by a list of **TOC directive blocks**::

    [
        {"type": "toc", "title": "ÍNDICE", "levels": "1-3",
         "page_break_after": true, "update_fields_on_open": true},
        {"type": "toc_tables", "title": "ÍNDICE DE TABLAS",
         "page_break_after": true, "update_fields_on_open": true},
        {"type": "toc_figures", "title": "ÍNDICE DE FIGURAS",
         "page_break_after": true, "update_fields_on_open": true},
    ]

The normalizer runs **before** the definition compiler so every downstream
consumer only sees the canonical directive format.
"""

from __future__ import annotations

import copy
import logging
from typing import Any, Dict, List, Optional

from app.core.services.toc_detector import normalize_title

logger = logging.getLogger(__name__)

# Canonical directive type mapping based on normalised title fragments.
_TITLE_TO_TYPE: List[tuple[str, str]] = [
    ("tabla", "toc_tables"),
    ("figuras", "toc_figures"),
    ("abreviaturas", "toc_abbreviations"),
]


def _infer_directive_type(title: str) -> str:
    """Map a TOC/index title to a canonical directive ``type``."""
    norm = normalize_title(title)
    for fragment, dtype in _TITLE_TO_TYPE:
        if fragment in norm:
            return dtype
    return "toc"


def _make_directive(
    title: str,
    *,
    levels: str = "1-3",
    page_break_after: bool = True,
    update_fields_on_open: bool = True,
) -> Dict[str, Any]:
    """Build a single TOC directive block."""
    return {
        "type": _infer_directive_type(title),
        "title": title,
        "levels": levels,
        "page_break_after": page_break_after,
        "update_fields_on_open": update_fields_on_open,
    }


# ------------------------------------------------------------------
# Variant A: dict  (keys like contenido, tablas, figuras, ...)
# ------------------------------------------------------------------

_DICT_KEY_PRIORITY = [
    "contenido",
    "tablas",
    "figuras",
    "abreviaturas",
]


def _normalize_dict_indices(indices: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Convert dict-style indices to directive blocks."""
    directives: List[Dict[str, Any]] = []
    seen_keys: set[str] = set()

    for key in _DICT_KEY_PRIORITY:
        title = indices.get(key)
        if isinstance(title, str) and title.strip():
            directives.append(_make_directive(title.strip()))
            seen_keys.add(key)

    # Pick up any extra keys not in our priority list (future-proof).
    for key, title in indices.items():
        if key in seen_keys or key in ("placeholder", "nota"):
            continue
        if isinstance(title, str) and title.strip():
            directives.append(_make_directive(title.strip()))

    return directives


# ------------------------------------------------------------------
# Variant B: list of {"titulo": "...", "items": [...]}
# ------------------------------------------------------------------


def _normalize_array_indices(indices: List[Any]) -> List[Dict[str, Any]]:
    """Convert array-style indices (with ``items``/``pag``) to directive blocks.

    The ``items`` arrays with ``pag`` fields are **discarded** — page numbers
    are auto-calculated by Word.
    """
    directives: List[Dict[str, Any]] = []
    for entry in indices:
        if not isinstance(entry, dict):
            continue
        title = entry.get("titulo") or entry.get("title") or ""
        if isinstance(title, str) and title.strip():
            directives.append(_make_directive(title.strip()))
    return directives


# ------------------------------------------------------------------
# Already normalised check
# ------------------------------------------------------------------


def _is_already_normalised(indices: Any) -> bool:
    """Return True if ``indices`` is already a list of directive blocks."""
    if not isinstance(indices, list):
        return False
    if not indices:
        return False
    first = indices[0]
    return isinstance(first, dict) and "type" in first


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------


def normalize_indices(indices: Any) -> Optional[List[Dict[str, Any]]]:
    """Normalise a legacy ``indices`` value into a list of TOC directives.

    Returns ``None`` if the input is unrecognised (not dict, not list,
    empty, etc.) — the caller should treat this as "no indices".
    """
    if indices is None:
        return None

    if _is_already_normalised(indices):
        return indices  # type: ignore[return-value]

    if isinstance(indices, dict):
        result = _normalize_dict_indices(indices)
        if result:
            logger.info("Normalised dict-style indices → %d TOC directive(s)", len(result))
            return result
        return None

    if isinstance(indices, list):
        result = _normalize_array_indices(indices)
        if result:
            logger.info("Normalised array-style indices → %d TOC directive(s)", len(result))
            return result
        return None

    return None


def normalize_definition(definition: Dict[str, Any]) -> Dict[str, Any]:
    """Return a **copy** of *definition* with ``preliminares.indices``
    normalised to TOC directive blocks.

    The original dict is never mutated.
    """
    if not isinstance(definition, dict):
        return definition

    preliminares = definition.get("preliminares")
    if not isinstance(preliminares, dict):
        return definition

    raw_indices = preliminares.get("indices")
    if raw_indices is None:
        return definition

    normalised = normalize_indices(raw_indices)
    if normalised is None:
        return definition

    # Already in canonical form — nothing to do.
    if normalised is raw_indices:
        return definition

    result = copy.deepcopy(definition)
    result["preliminares"]["indices"] = normalised
    return result
