"""Build simulated academic references for final bibliography sections.

The active Mistral pipeline does not have internet access, so these helpers
produce coherent reference proposals for later author validation instead of
pretending to cite verified online sources.
"""

from __future__ import annotations

import re
import unicodedata
from collections import OrderedDict
from typing import Any, Iterable

_REFERENCE_WARNING = (
    "Las siguientes referencias son propuestas academicas simuladas generadas sin acceso a internet. "
    "Deben ser validadas, corregidas o reemplazadas por el autor antes de la version final."
)

_ROMAN_PREFIX_RE = re.compile(r"^[\dIVXLCDM]+(?:[.\-]\d+)*[.)\s-]+")
_WORD_RE = re.compile(r"[A-Za-zA-Z][A-Za-zA-Z0-9]{3,}")
_STOPWORDS = {
    "sobre",
    "desde",
    "hacia",
    "para",
    "entre",
    "segun",
    "tesis",
    "investigacion",
    "documento",
    "capitulo",
    "seccion",
    "estudio",
    "analisis",
    "marco",
    "teorico",
    "metodologia",
    "resultados",
    "discusion",
    "conclusiones",
    "recomendaciones",
    "introduccion",
    "problema",
    "objetivos",
}
_CATEGORY_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("foundation", ("INTRODUCCION", "PLANTEAMIENTO", "PROBLEMA", "JUSTIFICACION", "OBJETIVOS", "HIPOTESIS")),
    ("theory", ("MARCO TEORICO", "BASES TEORICAS", "MARCO CONCEPTUAL", "ANTECEDENTES", "LITERATURA")),
    ("methodology", ("METODOLOGIA", "METODO", "POBLACION", "MUESTRA", "INSTRUMENTOS", "PROCEDIMIENTO", "RIGOR")),
    ("results", ("RESULTADOS", "DISCUSION", "HALLAZGOS")),
    ("closure", ("CONCLUSIONES", "RECOMENDACIONES")),
)
_AUTHOR_PAIRS: tuple[tuple[str, str], ...] = (
    ("Morales, J.", "Quispe, L."),
    ("Rojas, M.", "Salazar, P."),
    ("Paredes, A.", "Vilca, C."),
    ("Gomez, R.", "Torres, E."),
    ("Cruz, D.", "Huaman, S."),
    ("Sanchez, F.", "Medina, V."),
)
_CATEGORY_TEMPLATES: dict[str, tuple[str, ...]] = {
    "foundation": (
        "{a1}, & {a2} ({y1}). Contextualizacion del problema de {topic} en organizaciones contemporaneas. Revista Latinoamericana de Gestion Aplicada, 14(2), 45-62. Referencia propuesta simulada para validacion del autor.",
        "{a3} ({y2}). Formulacion de objetivos y delimitacion de estudios sobre {focus}. Editorial Academia Tecnica. Referencia propuesta simulada para validacion del autor.",
    ),
    "theory": (
        "{a1}, & {a2} ({y1}). Fundamentos teoricos de {topic}. Fondo Editorial Universitario. Referencia propuesta simulada para validacion del autor.",
        "{a3}, & {a4} ({y2}). Modelos conceptuales para el analisis de {focus}. Revista Iberoamericana de Estudios Aplicados, 11(1), 33-51. Referencia propuesta simulada para validacion del autor.",
    ),
    "methodology": (
        "{a1} ({y1}). Metodologia de la investigacion aplicada a {topic}. Editorial Metodo y Evidencia. Referencia propuesta simulada para validacion del autor.",
        "{a2}, & {a3} ({y2}). Diseno de instrumentos y tecnicas de recoleccion para {focus}. Revista de Metodos Aplicados, 9(3), 70-88. Referencia propuesta simulada para validacion del autor.",
    ),
    "results": (
        "{a1}, & {a2} ({y1}). Analisis e interpretacion de resultados en proyectos sobre {topic}. Revista de Analisis Aplicado, 17(2), 101-119. Referencia propuesta simulada para validacion del autor.",
        "{a3} ({y2}). Discusion de hallazgos y contraste teorico en estudios de {focus}. Cuadernos de Investigacion Profesional, 6(1), 25-39. Referencia propuesta simulada para validacion del autor.",
    ),
    "closure": (
        "{a1} ({y1}). Criterios para redactar conclusiones y recomendaciones en estudios de {topic}. Manual de Escritura Academica Avanzada. Referencia propuesta simulada para validacion del autor.",
    ),
}


def _strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _norm_upper(text: str) -> str:
    return " ".join(_strip_accents(text).upper().split())


def _clean_heading(text: str) -> str:
    cleaned = _ROMAN_PREFIX_RE.sub("", str(text or "").strip())
    return " ".join(cleaned.split())


def _is_reference_path(path: str) -> bool:
    normalized = _norm_upper(path)
    return "REFERENCIAS" in normalized or "BIBLIOGRAF" in normalized


def _should_skip_path(path: str) -> bool:
    normalized = _norm_upper(path)
    if not normalized:
        return True
    markers = ("INDICE", "ANEXO", "DEDICATORIA", "AGRADECIMIENTO", "RESUMEN", "ABSTRACT")
    return _is_reference_path(path) or any(marker in normalized for marker in markers)


def _visible_content_text(content: Any) -> str:
    if isinstance(content, str):
        return " ".join(content.split())
    if not isinstance(content, list):
        return ""

    parts: list[str] = []
    for item in content:
        if isinstance(item, str):
            text = " ".join(item.split())
            if text:
                parts.append(text)
            continue
        if not isinstance(item, dict):
            continue
        block_type = _norm_upper(item.get("tipo"))
        if block_type == "PARRAFO":
            text = " ".join(str(item.get("texto") or "").split())
            if text:
                parts.append(text)
        elif block_type == "FIGURA":
            caption = " ".join(str(item.get("caption") or "").split())
            if caption:
                parts.append(caption)
        elif block_type == "TABLA":
            title = " ".join(str(item.get("titulo") or "").split())
            if title:
                parts.append(title)
    return " ".join(parts)


def _extract_topic(values: dict[str, Any] | None) -> str:
    values = values or {}
    candidates = (
        values.get("tema"),
        values.get("title"),
        values.get("project_title"),
        values.get("projectTitle"),
    )
    for candidate in candidates:
        text = " ".join(str(candidate or "").split())
        if text:
            return text
    return "el tema central de la investigacion"


def _extract_focus(path: str, sample_text: str) -> str:
    leaf = _clean_heading(str(path or "").split("/")[-1])
    leaf = re.sub(r"^[\d.]+\s*", "", leaf).strip()
    if leaf:
        return leaf.lower()

    words: list[str] = []
    seen: set[str] = set()
    for match in _WORD_RE.finditer(_strip_accents(sample_text).lower()):
        word = match.group(0)
        if word in _STOPWORDS or word in seen:
            continue
        seen.add(word)
        words.append(word)
        if len(words) == 3:
            break
    if words:
        return " ".join(words)
    return "la investigacion desarrollada"


def _categorize_path(path: str) -> str:
    normalized = _norm_upper(path)
    for category, keywords in _CATEGORY_KEYWORDS:
        if any(keyword in normalized for keyword in keywords):
            return category
    return "foundation"


def _ordered_unique(lines: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for line in lines:
        text = " ".join(str(line or "").split())
        if not text:
            continue
        key = _norm_upper(text)
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def build_reference_section_content(
    sections: list[dict[str, Any]],
    *,
    values: dict[str, Any] | None = None,
) -> str:
    """Build a final references section from generated section content."""
    topic = _extract_topic(values)
    buckets: "OrderedDict[str, tuple[str, str]]" = OrderedDict()

    for section in sections:
        if not isinstance(section, dict):
            continue
        path = str(section.get("path") or "").strip()
        if _should_skip_path(path):
            continue
        top_level = str(path.split("/", 1)[0] or "").strip()
        if not top_level:
            continue
        visible = _visible_content_text(section.get("content"))
        bucket_key = _norm_upper(top_level)
        stored = buckets.get(bucket_key)
        if stored is None or len(visible) > len(stored[1]):
            buckets[bucket_key] = (path, visible)

    if not buckets:
        buckets[_norm_upper(topic)] = (topic, topic)

    references: list[str] = []
    for index, (path, sample) in enumerate(buckets.values()):
        category = _categorize_path(path)
        focus = _extract_focus(path, sample or topic)
        authors = _AUTHOR_PAIRS[index % len(_AUTHOR_PAIRS)]
        next_authors = _AUTHOR_PAIRS[(index + 1) % len(_AUTHOR_PAIRS)]
        years = (2025 - (index % 4), 2023 - (index % 3))
        for template in _CATEGORY_TEMPLATES[category]:
            references.append(
                template.format(
                    a1=authors[0],
                    a2=authors[1],
                    a3=next_authors[0],
                    a4=next_authors[1],
                    y1=years[0],
                    y2=years[1],
                    topic=topic.lower(),
                    focus=focus,
                )
            )

    ordered_refs = _ordered_unique(references)
    paragraphs = [_REFERENCE_WARNING]
    paragraphs.extend(ordered_refs)
    return "\n\n".join(paragraphs)


def replace_references_section(
    sections: list[dict[str, Any]],
    *,
    values: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Replace the final references section with simulated validated proposals."""
    if not isinstance(sections, list):
        return sections

    references_content = build_reference_section_content(sections, values=values)
    updated: list[dict[str, Any]] = []
    replaced = False

    for section in sections:
        if not isinstance(section, dict):
            continue
        entry = dict(section)
        path = str(entry.get("path") or "").strip()
        if _is_reference_path(path):
            entry["content"] = references_content
            replaced = True
        updated.append(entry)

    return updated
