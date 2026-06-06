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
        "REALIDAD PROBLEMATICA",
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
        "REALIDAD PROBLEMATICA",
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
    if (
        is_chapter_two_text_only_section(path)
        or is_chapter_three_hypotheses_section(path)
        or is_chapter_three_operationalization_section(path)
        or is_chapter_four_text_only_section(path)
    ):
        return True
    for segment in normalized_path_segments(path):
        if any(keyword in segment for keyword in TEXT_ONLY_KEYWORDS):
            return True
    return False


def is_chapter_two_text_only_section(path: str) -> bool:
    segments = normalized_path_segments(path)
    joined = " / ".join(segments)
    if "MARCO TEORICO" not in joined:
        return False
    text_only_markers = (
        "ANTECEDENTES",
        "MARCO CONCEPTUAL",
        "DEFINICION DE TERMINOS BASICOS",
        "DEFINICION DE TERMINOS",
    )
    return any(marker in joined for marker in text_only_markers)


def is_chapter_three_hypotheses_section(path: str) -> bool:
    segments = normalized_path_segments(path)
    joined = " / ".join(segments)
    return "HIPOTESIS Y VARIABLES" in joined and "HIPOTESIS" in joined and "OPERACIONALIZACION" not in joined


def is_chapter_three_operationalization_section(path: str) -> bool:
    segments = normalized_path_segments(path)
    joined = " / ".join(segments)
    if "OPERACIONALIZACION" not in joined:
        return False
    if "HIPOTESIS Y VARIABLES" in joined:
        return True
    normalized = " ".join(strip_accents(str(path or "")).upper().split())
    return bool(re.search(r"\b3\.2\b", normalized))


def is_chapter_four_design_section(path: str) -> bool:
    joined = " / ".join(normalized_path_segments(path))
    return "METODOLOGIA" in joined and "DISENO METODOLOGICO" in joined


def is_chapter_four_text_only_section(path: str) -> bool:
    joined = " / ".join(normalized_path_segments(path))
    if "METODOLOGIA" not in joined:
        return False
    text_only_markers = (
        "METODO DE INVESTIGACION",
        "POBLACION Y MUESTRA",
        "LUGAR DE ESTUDIO",
        "TECNICAS E INSTRUMENTOS",
        "ANALISIS Y PROCESAMIENTO DE DATOS",
        "ASPECTOS ETICOS",
    )
    return any(marker in joined for marker in text_only_markers)


def allows_structured_content(path: str) -> bool:
    if is_chapter_four_design_section(path):
        return True
    if is_text_only_section(path):
        return False
    return any(
        keyword in segment for segment in normalized_path_segments(path) for keyword in STRUCTURED_SECTION_KEYWORDS
    )


def allows_recommended_figure(path: str) -> bool:
    """Return True when the section path can carry a recommended figure."""
    if is_text_only_section(path):
        return False
    segments = normalized_path_segments(path)
    joined = " / ".join(segments)
    if joined == "MARCO TEORICO" or is_chapter_four_design_section(path):
        return False
    if "METODOLOGIA" in joined and (is_chapter_four_design_section(path) or is_chapter_four_text_only_section(path)):
        return False
    return any(
        keyword in segment for segment in normalized_path_segments(path) for keyword in RECOMMENDED_FIGURE_KEYWORDS
    )


def render_prompt_policy_rules() -> str:
    """Return the section policy rendered as prompt text."""
    return (
        "- NO sugieras tablas/figuras en Introduccion, Objetivos, Justificacion, "
        "Conclusiones ni Recomendaciones.\n"
        "- Considera tablas/figuras principalmente en Marco teorico/Bases teoricas, "
        "Metodologia, Resultados, Discusion, Cronograma, Presupuesto, Matriz/Matrices, "
        "Operacionalizacion, Anexos y la descripcion de la realidad problematica cuando el formato lo exige.\n"
        "- En Capitulo II Marco teorico: no uses tablas ni figuras en Antecedentes, "
        "Marco conceptual ni Definicion de terminos basicos; en Bases teoricas usa solo las figuras "
        "controladas por subtema y las formulas tecnicas autorizadas. No inicies Bases teoricas con figuras, "
        "no coloques figuras consecutivas sin texto teorico y no muestres placeholders tecnicos al lector.\n"
        "- En Capitulo III: 3.1 no lleva tablas ni figuras; 3.2 solo lleva texto puente "
        "(sin TABLE_JSON, FIGURE_JSON ni FORMULA_JSON) porque las tablas 3.1/3.2 se "
        "renderizan desde los datos estructurados del proyecto.\n"
        "- En Capitulo IV: no uses figuras ni tablas en 4.1 a 4.7; 4.1 solo puede incluir "
        "el esquema textual M O1 X O2 con su leyenda.\n"
        "- En Cronograma de actividades: genera solo tabla estructurada del proyecto actual; sin parrafos narrativos, "
        "sin listas y sin texto posterior.\n"
        "- En Presupuesto: genera solo tabla estructurada del proyecto actual; "
        "sin parrafos narrativos, sin listas y sin texto posterior.\n"
    )
