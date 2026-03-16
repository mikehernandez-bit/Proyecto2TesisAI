"""Completeness validator for AI-generated thesis sections.

Detects placeholder text (e.g. "[Escriba aqui su dedicatoria...]") and
empty/stub content that should not appear in the final document.  Provides
autofill fallbacks for known section types (dedicatoria, agradecimiento,
abreviaturas) so the pipeline can repair instead of rendering broken docs.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Detection patterns
# ---------------------------------------------------------------------------

# Regex patterns that match common placeholder text in Spanish formats.
_PLACEHOLDER_RE = re.compile(
    r"\[.*?(?:escriba|complete|llene|inserte|coloque|ingrese|agregue).*?\]",
    re.IGNORECASE | re.DOTALL,
)

_COMPLETAR_RE = re.compile(
    r"\((?:Completar|Llenar|Insertar|Agregar)\b.*?\)",
    re.IGNORECASE,
)

_TEMPLATE_VAR_RE = re.compile(r"\{\{.*?\}\}")

# Short generic instructions that are clearly not real content.
_INSTRUCTION_PATTERNS: List[re.Pattern] = [
    re.compile(r"escriba\s+aqu[ií]", re.IGNORECASE),
    re.compile(r"complete\s+esta\s+secci[oó]n", re.IGNORECASE),
    re.compile(r"inserte\s+(?:aqu[ií]|su|el|la)", re.IGNORECASE),
    re.compile(r"coloque\s+(?:aqu[ií]|su|el|la)", re.IGNORECASE),
    re.compile(r"ejemplo\s+de\s+(?:dedicatoria|agradecimiento)", re.IGNORECASE),
    re.compile(r"reemplace\s+este\s+texto", re.IGNORECASE),
    re.compile(r"(?:no\s+exceder|debe\s+contener)\s+.*palabras", re.IGNORECASE),
]

# Section-path keywords for classification
_DEDICATORIA_KEYS = frozenset({"dedicatoria"})
_AGRADECIMIENTO_KEYS = frozenset({"agradecimiento", "agradecimientos"})
_ABREVIATURAS_KEYS = frozenset(
    {
        "abreviaturas",
        "abreviatura",
        "indice de abreviaturas",
        "lista de abreviaturas",
        "siglas",
        "acronimos",
        "acrónimos",
    }
)
_DISCUSION_KEYS = frozenset({"discusion", "discusion de resultados"})
_CONCLUSIONES_KEYS = frozenset({"conclusion", "conclusiones"})
_RECOMENDACIONES_KEYS = frozenset({"recomendacion", "recomendaciones"})


# ---------------------------------------------------------------------------
# Issue dataclass
# ---------------------------------------------------------------------------


@dataclass
class CompletenessIssue:
    """Describes a placeholder or empty-content problem in a section."""

    section_id: str
    path: str
    issue_type: str  # "placeholder" | "template_var" | "empty" | "instruction"
    sample: str = ""


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


def _looks_like_placeholder_table_cell(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    normalized = _normalize_label(text)
    if text.startswith("[") and text.endswith("]"):
        return True
    markers = (
        "completar",
        "autor 1",
        "autor 2",
        "variable",
        "resultado",
        "si/no",
        "nombre",
        "indicador",
    )
    return any(marker in normalized for marker in markers)


def _structured_content_looks_placeholder_only(content: list[Any]) -> str:
    for item in content:
        if not isinstance(item, dict):
            continue
        block_type = str(item.get("tipo") or "").strip().lower()
        if block_type == "tabla":
            rows = item.get("filas") or item.get("rows") or []
            visible_cells: List[str] = []
            for row in rows if isinstance(rows, list) else []:
                if not isinstance(row, (list, tuple)):
                    continue
                for cell in row:
                    text = str(cell or "").strip()
                    if text:
                        visible_cells.append(text)
            if visible_cells and all(_looks_like_placeholder_table_cell(cell) for cell in visible_cells):
                return visible_cells[0][:120]
        if block_type == "figura":
            caption = str(item.get("caption") or item.get("titulo") or "").strip()
            normalized = _normalize_label(caption)
            if normalized and any(
                marker in normalized for marker in ("figura de ejemplo", "diagrama ilustrativo", "arbol de problemas")
            ):
                return caption[:120]
    return ""


def detect_placeholders(
    sections: List[Dict[str, Any]],
) -> List[CompletenessIssue]:
    """Scan all sections and return a list of completeness issues.

    Each issue describes a section whose content appears to be a placeholder,
    template variable, instruction text, or empty stub.
    """
    issues: List[CompletenessIssue] = []

    for sec in sections:
        sid = sec.get("sectionId", "")
        path = sec.get("path", "")
        raw_content = sec.get("content", "")
        if isinstance(raw_content, list):
            paragraph_parts: List[str] = []
            has_structured_blocks = False
            structured_placeholder_sample = _structured_content_looks_placeholder_only(raw_content)
            for item in raw_content:
                if isinstance(item, str):
                    text = item.strip()
                    if text:
                        paragraph_parts.append(text)
                    continue
                if not isinstance(item, dict):
                    continue
                block_type = str(item.get("tipo") or "").strip().lower()
                if block_type in {"tabla", "figura"}:
                    has_structured_blocks = True
                    continue
                if block_type == "parrafo":
                    text = str(item.get("texto") or "").strip()
                    if text:
                        paragraph_parts.append(text)
            content = "\n\n".join(paragraph_parts)
        else:
            content = str(raw_content or "")
            has_structured_blocks = False
            structured_placeholder_sample = ""
        stripped = content.strip()

        if structured_placeholder_sample and not stripped:
            issues.append(
                CompletenessIssue(
                    sid,
                    path,
                    "placeholder",
                    structured_placeholder_sample,
                )
            )
            continue

        # 1) Empty / whitespace-only
        if not stripped:
            if has_structured_blocks:
                continue
            issues.append(CompletenessIssue(sid, path, "empty"))
            continue

        # 2) Placeholder brackets: [Escriba aquí ...]
        m = _PLACEHOLDER_RE.search(content)
        if m:
            issues.append(CompletenessIssue(sid, path, "placeholder", m.group()[:120]))
            continue

        # 3) (Completar ...) patterns
        m2 = _COMPLETAR_RE.search(content)
        if m2:
            issues.append(CompletenessIssue(sid, path, "placeholder", m2.group()[:120]))
            continue

        # 4) {{template}} variables
        m3 = _TEMPLATE_VAR_RE.search(content)
        if m3:
            issues.append(CompletenessIssue(sid, path, "template_var", m3.group()[:120]))
            continue

        # 5) Instruction-like text (the whole content is basically an instruction)
        if len(stripped) < 300:
            for pat in _INSTRUCTION_PATTERNS:
                if pat.search(stripped):
                    issues.append(CompletenessIssue(sid, path, "instruction", stripped[:120]))
                    break

    return issues


# ---------------------------------------------------------------------------
# Autofill
# ---------------------------------------------------------------------------


def _normalize_label(text: str) -> str:
    lowered = str(text or "").strip().lower()
    if not lowered:
        return ""
    ascii_only = unicodedata.normalize("NFKD", lowered).encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_only.split())


def _classify_section(path: str) -> Optional[str]:
    """Return a section category based on its path, or None."""
    norm = _normalize_label(path)
    norm = re.sub(r"^[\dIVXivx]+[\.\)\-]\s*", "", norm).strip()

    if any(k in norm for k in _DEDICATORIA_KEYS):
        return "dedicatoria"
    if any(k in norm for k in _AGRADECIMIENTO_KEYS):
        return "agradecimiento"
    if any(k in norm for k in _ABREVIATURAS_KEYS):
        return "abreviaturas"
    if any(k in norm for k in _DISCUSION_KEYS):
        return "discusion"
    if any(k in norm for k in _CONCLUSIONES_KEYS):
        return "conclusiones"
    if any(k in norm for k in _RECOMENDACIONES_KEYS):
        return "recomendaciones"
    return None


def _first_nonempty(values: Dict[str, Any] | None, keys: tuple[str, ...]) -> str:
    if not isinstance(values, dict):
        return ""
    for key in keys:
        raw = values.get(key)
        if raw is None:
            continue
        text = str(raw).strip()
        if text:
            return text
    return ""


def _visible_content_text(content: Any) -> str:
    if isinstance(content, str):
        return re.sub(r"\s+", " ", content).strip()
    if not isinstance(content, list):
        return ""

    parts: List[str] = []
    for item in content:
        if isinstance(item, str):
            text = item.strip()
            if text:
                parts.append(text)
            continue
        if not isinstance(item, dict):
            continue
        block_type = str(item.get("tipo") or "").strip().lower()
        if block_type == "parrafo":
            text = str(item.get("texto") or "").strip()
            if text:
                parts.append(text)
        elif block_type == "figura":
            caption = str(item.get("caption") or item.get("titulo") or "").strip()
            if caption:
                parts.append(caption)
        elif block_type == "tabla":
            title = str(item.get("titulo") or "").strip()
            if title:
                parts.append(title)

    return re.sub(r"\s+", " ", " ".join(parts)).strip()


def _supporting_excerpt(
    sections: List[Dict[str, Any]] | None,
    *,
    include_keywords: frozenset[str],
    exclude_path: str = "",
) -> str:
    if not sections:
        return ""

    excluded = _normalize_label(exclude_path)
    for section in sections:
        if not isinstance(section, dict):
            continue
        path = _normalize_label(section.get("path", ""))
        if not path or path == excluded:
            continue
        if not any(keyword in path for keyword in include_keywords):
            continue
        text = _visible_content_text(section.get("content"))
        if len(text) >= 60:
            return text[:320].rstrip(" .")
    return ""


def _academic_subject(values: Dict[str, Any] | None) -> str:
    return (
        _first_nonempty(values, ("tema", "title", "project_title", "projectTitle")) or "el objeto de estudio planteado"
    )


def _general_objective(values: Dict[str, Any] | None) -> str:
    return _first_nonempty(values, ("objetivo_general", "general_objective"))


def _build_discussion_fallback(
    values: Dict[str, Any] | None,
    sections: List[Dict[str, Any]] | None,
    path: str,
) -> str:
    subject = _academic_subject(values)
    objective = _general_objective(values)
    results_excerpt = _supporting_excerpt(
        sections,
        include_keywords=frozenset({"resultado", "resultados", "hallazgo", "hallazgos", "analisis"}),
        exclude_path=path,
    )
    antecedent_excerpt = _supporting_excerpt(
        sections,
        include_keywords=frozenset({"antecedente", "marco teorico", "bases teoricas", "literatura"}),
        exclude_path=path,
    )

    first = (
        f"La discusion de resultados del presente estudio interpreta los hallazgos vinculados con {subject}. "
        "En relacion con el objetivo general de "
        f"{objective or 'desarrollar un analisis consistente del problema investigado'}, "
        "la evidencia reunida permite sostener que los resultados no deben entenderse "
        "como datos aislados, sino como indicadores que muestran tendencias tecnicas, "
        "operativas o metodologicas coherentes con el problema inicialmente formulado. "
    )
    if results_excerpt:
        first += (
            "En los apartados previos se identificaron hallazgos relevantes, entre ellos "
            f"{results_excerpt}. Esta informacion sirve como base para interpretar el alcance real del estudio, "
            "valorar sus implicancias y reconocer los factores que explican el comportamiento observado."
        )
    else:
        first += (
            "La lectura integrada de los resultados permite reconocer patrones, relaciones "
            "y puntos criticos que fortalecen la "
            "comprension del fenomeno estudiado y orientan la toma de decisiones derivada del trabajo academico."
        )

    second = (
        "Asimismo, la discusion exige contrastar dichos hallazgos con los antecedentes "
        "y fundamentos teoricos revisados, con el fin "
        "de determinar coincidencias, diferencias y aportes del estudio. "
    )
    if antecedent_excerpt:
        second += (
            "En ese sentido, la literatura considerada destaca que "
            f"{antecedent_excerpt}, lo cual ofrece un marco util para explicar "
            "por que los resultados del proyecto mantienen coherencia con enfoques previos "
            "y, al mismo tiempo, aportan una mirada contextualizada al escenario analizado. "
            "En conjunto, esta contrastacion respalda la validez academica de la discusion y "
            "permite formular conclusiones y recomendaciones directamente relacionadas "
            "con el problema de investigacion."
        )
    else:
        second += (
            "Aunque la profundidad de la contrastacion depende de la validacion final del autor, "
            "el analisis realizado permite sostener que los resultados guardan correspondencia "
            "con el marco conceptual del estudio y ofrecen una base suficiente para derivar "
            "conclusiones tecnicas, metodologicas y practicas con sentido academico."
        )

    return f"{first}\n\n{second}"


def _build_conclusions_fallback(values: Dict[str, Any] | None) -> str:
    subject = _academic_subject(values)
    objective = _general_objective(values) or "analizar el problema de investigacion con un enfoque academico riguroso"
    return (
        "En sintesis, el estudio permitio establecer hallazgos consistentes respecto de "
        f"{subject}, en correspondencia directa con el objetivo general de {objective}. "
        "A partir del analisis desarrollado, se concluye que la informacion obtenida "
        "ofrece una base suficiente para comprender el fenomeno estudiado, identificar "
        "sus factores mas relevantes y sustentar tecnicamente la respuesta "
        "al problema planteado.\n\n"
        "Asimismo, se concluye que la articulacion entre el marco teorico, la metodologia "
        "aplicada y los resultados obtenidos fortalece la coherencia interna del trabajo. "
        "Esta relacion permite interpretar los hallazgos con mayor consistencia, delimitar su alcance "
        "real y reconocer tanto los aportes del estudio como sus restricciones metodologicas.\n\n"
        "Finalmente, las conclusiones del documento confirman que el proceso de investigacion "
        "desarrollado produce conocimiento util para el contexto evaluado y deja criterios "
        "claros para la toma de decisiones, la mejora del objeto de estudio y la continuidad de "
        "nuevas investigaciones relacionadas."
    )


def _build_recommendations_fallback(values: Dict[str, Any] | None) -> str:
    subject = _academic_subject(values)
    return (
        "Se recomienda que las decisiones y acciones derivadas del estudio sobre "
        f"{subject} se implementen de manera progresiva, con seguimiento tecnico y "
        "criterios de evaluacion definidos, a fin de verificar su impacto real y ajustar oportunamente los "
        "procedimientos involucrados.\n\n"
        "Tambien se recomienda fortalecer la recoleccion y sistematizacion de informacion "
        "en futuras etapas del trabajo, de modo que sea posible ampliar la comparacion entre "
        "periodos, escenarios o unidades de analisis y obtener evidencia aun mas robusta para la "
        "toma de decisiones academicas o institucionales.\n\n"
        "Finalmente, resulta pertinente que futuras investigaciones profundicen en variables "
        "complementarias, instrumentos adicionales y estrategias metodologicas comparables, "
        "con el proposito de validar los hallazgos alcanzados y ampliar el valor aplicado del "
        "estudio en contextos similares."
    )


# Pre-built autofill texts (generic, formal, no proper names).
_AUTOFILL: Dict[str, str] = {
    "dedicatoria": (
        "Dedico este trabajo a mi familia, quienes con su apoyo incondicional "
        "hicieron posible la culminacion de esta etapa academica. "
        "A mis docentes, por su orientacion constante y su compromiso con la "
        "excelencia educativa. Y a todos aquellos que, de una u otra forma, "
        "contribuyeron a la realizacion de esta investigacion."
    ),
    "agradecimiento": (
        "Agradezco a Dios por haberme permitido llegar hasta este punto. "
        "A mi familia, por su paciencia y comprension durante todo el proceso. "
        "A mi asesor de tesis, por su guia academica y profesional. "
        "A la Universidad Nacional del Callao, por brindarme las herramientas "
        "y el entorno necesarios para mi formacion. "
        "A mis companeros y amigos, por su apoyo y motivacion constante."
    ),
    "abreviaturas": ("No se identificaron abreviaturas relevantes en el presente documento."),
}


def autofill_section(
    section: Dict[str, str],
    issue_type: str,
    *,
    values: Dict[str, Any] | None = None,
    all_sections: List[Dict[str, Any]] | None = None,
) -> Optional[str]:
    """Return replacement content for a known section type, or None.

    Returns ``None`` when the section type is unknown and re-generation
    via the AI should be attempted instead.
    """
    path = section.get("path", "")
    category = _classify_section(path)
    if category and category in _AUTOFILL:
        return _AUTOFILL[category]
    if category == "discusion":
        return _build_discussion_fallback(values, all_sections, path)
    if category == "conclusiones":
        return _build_conclusions_fallback(values)
    if category == "recomendaciones":
        return _build_recommendations_fallback(values)
    return None


# ---------------------------------------------------------------------------
# Strip placeholders from arbitrary text (used by sanitize_content)
# ---------------------------------------------------------------------------


def strip_placeholder_text(text: str) -> str:
    """Remove known placeholder patterns from text, returning cleaned text.

    This is a lighter-weight function intended for use inside
    ``OutputValidator.sanitize_content`` as a safety net.
    """
    result = _PLACEHOLDER_RE.sub("", text)
    result = _COMPLETAR_RE.sub("", result)
    result = _TEMPLATE_VAR_RE.sub("", result)
    return result
