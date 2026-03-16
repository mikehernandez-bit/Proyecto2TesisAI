"""Shared section-level policy for structured AI content.

GicaGen owns these academic rules. They are reused by prompt construction,
payload adaptation, and tests so tables/figures are allowed or stripped
consistently across the pipeline.
"""

from __future__ import annotations

import re
import unicodedata

TEXT_ONLY_KEYWORDS: frozenset[str] = frozenset(
    {
        "INTRODUCCION",
        "OBJETIVOS",
        "OBJETIVO GENERAL",
        "OBJETIVOS GENERALES",
        "OBJETIVO ESPECIFICO",
        "OBJETIVOS ESPECIFICOS",
        "JUSTIFICACION",
        "CONCLUSIONES",
        "CONCLUSION",
        "RECOMENDACIONES",
        "RECOMENDACION",
        "DEDICATORIA",
        "AGRADECIMIENTO",
        "AGRADECIMIENTOS",
        "RESUMEN",
        "ABSTRACT",
    }
)

STRUCTURED_SECTION_KEYWORDS: frozenset[str] = frozenset(
    {
        "MARCO TEORICO",
        "BASES TEORICAS",
        "MARCO CONCEPTUAL",
        "METODOLOGIA",
        "METODOS",
        "PROCEDIMIENTO",
        "DISCUSION",
        "DISCUSION DE RESULTADOS",
        "OPERACIONALIZACION",
        "RESULTADOS",
        "CRONOGRAMA",
        "PRESUPUESTO",
        "MATRIZ",
        "MATRICES",
        "ANEXO",
        "ANEXOS",
    }
)

RECOMMENDED_FIGURE_KEYWORDS: frozenset[str] = frozenset(
    {
        "MARCO TEORICO",
        "BASES TEORICAS",
        "MARCO CONCEPTUAL",
        "METODOLOGIA",
        "DISENO METODOLOGICO",
        "PROCEDIMIENTO",
        "RESULTADOS",
        "DISCUSION",
        "DISCUSION DE RESULTADOS",
        "CRONOGRAMA",
        "FLUJO",
    }
)

_ROMAN_PREFIX_RE = re.compile(r"^[\dIVXLCDM]+(?:[.\-]\d+)*[.)\s-]+")


def strip_accents(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalized_path_segments(path: str) -> list[str]:
    segments: list[str] = []
    for raw_segment in str(path or "").split("/"):
        normalized = strip_accents(raw_segment).upper()
        normalized = _ROMAN_PREFIX_RE.sub("", normalized).strip()
        normalized = " ".join(normalized.split())
        if normalized:
            segments.append(normalized)
    return segments


def is_text_only_section(path: str) -> bool:
    """Return True if the section path matches a text-only academic section."""
    for segment in normalized_path_segments(path):
        if any(keyword in segment for keyword in TEXT_ONLY_KEYWORDS):
            return True
    return False


def allows_structured_content(path: str) -> bool:
    if is_text_only_section(path):
        return False
    return any(
        keyword in segment
        for segment in normalized_path_segments(path)
        for keyword in STRUCTURED_SECTION_KEYWORDS
    )


def allows_recommended_figure(path: str) -> bool:
    """Return True when the section path can carry a recommended figure."""
    if is_text_only_section(path):
        return False
    return any(
        keyword in segment
        for segment in normalized_path_segments(path)
        for keyword in RECOMMENDED_FIGURE_KEYWORDS
    )


def render_prompt_policy_rules() -> str:
    """Return the section policy rendered as prompt text."""
    return (
        "- NO sugieras tablas/figuras en Introduccion, Objetivos, Justificacion, "
        "Conclusiones ni Recomendaciones.\n"
        "- Considera tablas/figuras principalmente en Marco teorico/Bases teoricas, "
        "Marco conceptual, Metodologia, Resultados, Discusion, Cronograma, Presupuesto, Matriz/Matrices, "
        "Operacionalizacion y Anexos.\n"
    )
