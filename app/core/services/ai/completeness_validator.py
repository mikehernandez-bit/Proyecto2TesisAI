"""Completeness validator for AI-generated thesis sections.

Detects placeholder text (e.g. "[Escriba aqui su dedicatoria...]") and
empty/stub content that should not appear in the final document.  Provides
autofill fallbacks for known section types (dedicatoria, agradecimiento,
abreviaturas) so the pipeline can repair instead of rendering broken docs.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
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
_ABREVIATURAS_KEYS = frozenset({
    "abreviaturas", "abreviatura",
    "indice de abreviaturas", "lista de abreviaturas",
    "siglas", "acronimos", "acrónimos",
})


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

def detect_placeholders(
    sections: List[Dict[str, str]],
) -> List[CompletenessIssue]:
    """Scan all sections and return a list of completeness issues.

    Each issue describes a section whose content appears to be a placeholder,
    template variable, instruction text, or empty stub.
    """
    issues: List[CompletenessIssue] = []

    for sec in sections:
        sid = sec.get("sectionId", "")
        path = sec.get("path", "")
        content = str(sec.get("content", ""))
        stripped = content.strip()

        # 1) Empty / whitespace-only
        if not stripped:
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

def _classify_section(path: str) -> Optional[str]:
    """Return a section category based on its path, or None."""
    norm = path.strip().lower()
    # Remove numbering prefixes like "1. " or "I. "
    norm = re.sub(r"^[\dIVXivx]+[\.\)\-]\s*", "", norm).strip()

    if any(k in norm for k in _DEDICATORIA_KEYS):
        return "dedicatoria"
    if any(k in norm for k in _AGRADECIMIENTO_KEYS):
        return "agradecimiento"
    if any(k in norm for k in _ABREVIATURAS_KEYS):
        return "abreviaturas"
    return None


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
    "abreviaturas": (
        "No se identificaron abreviaturas relevantes en el presente documento."
    ),
}


def autofill_section(
    section: Dict[str, str],
    issue_type: str,
) -> Optional[str]:
    """Return replacement content for a known section type, or None.

    Returns ``None`` when the section type is unknown and re-generation
    via the AI should be attempted instead.
    """
    path = section.get("path", "")
    category = _classify_section(path)
    if category and category in _AUTOFILL:
        return _AUTOFILL[category]
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
