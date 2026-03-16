"""Derive recommended figure blocks from finalized AI section content.

The AI may return plain text for sections that academically justify a visual
aid. This module adds a single recommended figure placeholder with a specific
title when the section path and generated text make that recommendation useful.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from app.core.services.ai.section_content_policy import (
    allows_recommended_figure,
    normalized_path_segments,
)

_CANONICAL_PLACEHOLDER_PATH = "assets/placeholder_figura.png"
_FIGURE_ID_RE = re.compile(r"[^a-z0-9]+")
_BLANK_LINE_RE = re.compile(r"\n\s*\n")
_GENERIC_FIGURE_MARKERS = (
    "FIGURA DE EJEMPLO",
    "DIAGRAMA ILUSTRATIVO",
    "ARBOL DE PROBLEMAS",
    "ARQUETIPO GENERICO",
)
_FIGURE_TRIGGER_MARKERS = (
    "ARQUITECTURA",
    "FLUJO",
    "PROCESO",
    "MODELO",
    "MARCO CONCEPTUAL",
    "COMPONENTE",
    "ETAPA",
    "RESULTADO",
    "HALLAZGO",
    "CRONOGRAMA",
    "METODOLOGIA",
)


def _normalize_token(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    ascii_only = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_only.split())


def _paragraph_blocks_from_text(text: str) -> list[dict[str, str]]:
    paragraphs = [
        part.strip()
        for part in _BLANK_LINE_RE.split(text.replace("\r\n", "\n").replace("\r", "\n"))
        if part and part.strip()
    ]
    return [{"tipo": "parrafo", "texto": paragraph} for paragraph in paragraphs]


def _content_to_blocks(content: Any) -> list[dict[str, Any]]:
    if isinstance(content, str):
        return _paragraph_blocks_from_text(content)
    if not isinstance(content, list):
        return []

    blocks: list[dict[str, Any]] = []
    for item in content:
        if isinstance(item, str):
            blocks.extend(_paragraph_blocks_from_text(item))
            continue
        if isinstance(item, dict):
            blocks.append(dict(item))
    return blocks


def _visible_text(content: Any) -> str:
    parts: list[str] = []
    if isinstance(content, str):
        return re.sub(r"\s+", " ", content).strip()

    for block in _content_to_blocks(content):
        block_type = _normalize_token(block.get("tipo"))
        if block_type == "parrafo":
            text = str(block.get("texto") or "").strip()
            if text:
                parts.append(text)
        elif block_type == "figura":
            text = str(block.get("titulo") or block.get("caption") or "").strip()
            if text:
                parts.append(text)
        elif block_type == "tabla":
            text = str(block.get("titulo") or "").strip()
            if text:
                parts.append(text)
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


def _is_generic_figure(block: dict[str, Any]) -> bool:
    caption = _normalize_token(block.get("caption"))
    title = _normalize_token(block.get("titulo"))
    if not caption and not title:
        return True
    return any(marker.lower() in f"{caption} {title}" for marker in _GENERIC_FIGURE_MARKERS)


def _subject(values: dict[str, Any] | None) -> str:
    if not isinstance(values, dict):
        return "el estudio desarrollado"
    for key in ("tema", "title", "project_title", "projectTitle", "objetivo_general"):
        raw = values.get(key)
        text = str(raw or "").strip()
        if text:
            return text
    return "el estudio desarrollado"


def _slugify_figure_id(section_id: str, path: str) -> str:
    base = _normalize_token(section_id or path or "figura")
    slug = _FIGURE_ID_RE.sub("_", base).strip("_")
    return f"fig_{slug or 'sugerida'}"


def _text_has_figure_triggers(text: str) -> bool:
    normalized = _normalize_token(text).upper()
    return any(marker in normalized for marker in _FIGURE_TRIGGER_MARKERS)


def _path_requires_recommended_figure(path: str, content_text: str) -> bool:
    if not allows_recommended_figure(path):
        return False
    if len(content_text) < 80:
        return False

    joined = " / ".join(normalized_path_segments(path))
    strong_markers = (
        "MARCO CONCEPTUAL",
        "METODOLOGIA",
        "DISENO METODOLOGICO",
        "PROCEDIMIENTO",
        "RESULTADOS",
        "DISCUSION",
        "CRONOGRAMA",
        "FLUJO",
    )
    if any(marker in joined for marker in strong_markers):
        return True

    theoretical_markers = ("MARCO TEORICO", "BASES TEORICAS")
    return any(marker in joined for marker in theoretical_markers) and _text_has_figure_triggers(content_text)


def _figure_title(path: str, content_text: str, values: dict[str, Any] | None) -> str:
    joined = " / ".join(normalized_path_segments(path))
    subject = _subject(values)
    normalized_text = _normalize_token(content_text).upper()

    if "CRONOGRAMA" in joined:
        return f"Cronograma visual de actividades para {subject}"
    if any(marker in joined for marker in ("METODOLOGIA", "DISENO METODOLOGICO", "PROCEDIMIENTO", "FLUJO")):
        return f"Flujo metodologico del estudio sobre {subject}"
    if "MARCO CONCEPTUAL" in joined:
        return f"Mapa conceptual del estudio sobre {subject}"
    if any(marker in joined for marker in ("MARCO TEORICO", "BASES TEORICAS")):
        if "ARQUITECTURA" in normalized_text or "SISTEMA" in normalized_text:
            return f"Arquitectura conceptual aplicada a {subject}"
        return f"Modelo teorico de referencia para {subject}"
    if "RESULTADOS" in joined:
        return f"Visualizacion comparativa de resultados de {subject}"
    if "DISCUSION" in joined:
        return f"Relacion entre hallazgos y antecedentes sobre {subject}"
    return f"Esquema tecnico de {subject}"


def _build_recommended_figure(section_id: str, path: str, title: str) -> dict[str, Any]:
    return {
        "tipo": "figura",
        "id": _slugify_figure_id(section_id, path),
        "titulo": title,
        "caption": title,
        "ruta_placeholder": _CANONICAL_PLACEHOLDER_PATH,
        "fuente": "Placeholder tecnico controlado. Reemplazar por la figura validada por el autor.",
    }


def apply_figure_recommendations(
    sections: list[dict[str, Any]],
    *,
    values: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Inject or repair one recommended figure block in eligible sections."""
    for section in sections:
        if not isinstance(section, dict):
            continue

        path = str(section.get("path") or "").strip()
        if not path:
            continue

        current_content = section.get("content")
        content_text = _visible_text(current_content)
        blocks = _content_to_blocks(current_content)

        figure_indexes = [
            index for index, block in enumerate(blocks) if _normalize_token(block.get("tipo")) == "figura"
        ]

        if figure_indexes:
            title = _figure_title(path, content_text, values)
            replacement = _build_recommended_figure(
                str(section.get("sectionId") or ""),
                path,
                title,
            )
            generic_indexes = [index for index in figure_indexes if _is_generic_figure(blocks[index])]
            if generic_indexes:
                blocks[generic_indexes[0]] = replacement
                section["content"] = blocks
            continue

        if not _path_requires_recommended_figure(path, content_text):
            continue

        title = _figure_title(path, content_text, values)
        blocks.append(
            _build_recommended_figure(
                str(section.get("sectionId") or ""),
                path,
                title,
            )
        )
        section["content"] = blocks

    return sections
