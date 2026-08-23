"""Consolidate simulated sources and Word-native citations.

The active generation pipeline has no academic search provider yet. The
sources created here are explicit proposals for later validation, while their
citations remain connected to Word's Source Manager and bibliography.
"""

from __future__ import annotations

import re
import unicodedata
from copy import deepcopy
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Iterable

_REFERENCE_WARNING = (
    "Las siguientes referencias son propuestas academicas simuladas generadas sin acceso a internet. "
    "Deben ser validadas, corregidas o reemplazadas por el autor antes de la version final."
)
_REFERENCE_VALIDATION_NOTE = "Referencia propuesta simulada para validacion del autor."

_REFERENCE_AUTHOR_YEAR_RE = re.compile(r"^(.+?)\s+\(((?:19|20)\d{2})\)\.")
_REFERENCE_AUTHOR_RE = re.compile(
    r"(?<![A-Za-z0-9])([A-Za-zÁÉÍÓÚÜÑáéíóúüñ'-]+),\s*"
    r"[A-ZÁÉÍÓÚÜÑ](?:\.[A-ZÁÉÍÓÚÜÑ])?\."
)
_CITATION_MARKER_RE = re.compile(r"\[\[CITE:[A-Z0-9_-]+(?:;[A-Z0-9_-]+)*\]\]")
_ROMAN_PREFIX_RE = re.compile(r"^[\dIVXLCDM]+(?:[.\-]\d+)*[.)\s-]+")
_WORD_RE = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ][A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9]{2,}")

_NAME_TOKEN = r"(?:[A-ZÁÉÍÓÚÑÜŻŹĆŁŚŠŽČ][\w'’\-]+|[A-ZÁÉÍÓÚÑÜŻŹĆŁŚŠŽČ]{2,})"
_STANDARD_AUTHOR = (
    r"(?:MIL-STD-\d+[A-Z]?|"
    r"ISO(?:\s+[A-Z0-9][A-Z0-9.:/\-]*)?|"
    r"IEC(?:\s+[A-Z0-9][A-Z0-9.:/\-]*)?|"
    r"EN(?:\s+[A-Z0-9][A-Z0-9.:/\-]*)?|"
    r"SAE(?:\s+[A-Z0-9][A-Z0-9.:/\-]*)?|GMG)"
)
_NARRATIVE_AUTHOR = (
    rf"(?:{_STANDARD_AUTHOR}|{_NAME_TOKEN}"
    rf"(?:\s+(?:y|&|and)\s+{_NAME_TOKEN})?(?:\s+et\s+al\.)?)"
)
_NARRATIVE_CITATION_RE = re.compile(
    rf"(?<![\w])(?P<author>{_NARRATIVE_AUTHOR})\s*"
    rf"\((?P<year>(?:19|20)\d{{2}}[a-z]?)\)"
)
_CORPORATE_CITATION_RE = re.compile(
    r"[A-ZÁÉÍÓÚÑÜ][\w'’\-]+(?:\s+[A-ZÁÉÍÓÚÑÜ][\w'’\-]+){1,7}"
    r"\s+\[(?P<author>[A-Z]{2,})\]\s*"
    r"\((?P<year>(?:19|20)\d{2}[a-z]?)\)"
)
_PARENTHETICAL_RE = re.compile(r"\((?P<content>[^()]*)\)")
_PARENTHETICAL_PART_RE = re.compile(
    r"^\s*(?P<author>.+?),\s*(?P<year>(?:19|20)\d{2}[a-z]?)"
    r"(?:\s*[,.:]\s*.*)?$",
    flags=re.IGNORECASE,
)

_STOPWORDS = {
    "sobre", "desde", "hacia", "para", "entre", "segun", "tesis",
    "investigacion", "documento", "capitulo", "seccion", "estudio",
    "analisis", "marco", "teorico", "metodologia", "proyecto",
    "resultados", "discusion", "introduccion",
}

_CATEGORY_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("foundation", ("INTRODUCCION", "PLANTEAMIENTO", "PROBLEMA", "JUSTIFICACION")),
    ("theory", ("MARCO TEORICO", "BASES TEORICAS", "MARCO CONCEPTUAL", "ANTECEDENTES", "TERMINOS", "VARIABLE", "OPERACIONALIZACION")),
    ("methodology", ("METODOLOGIA", "METODO", "POBLACION", "MUESTRA", "INSTRUMENTOS", "PROCEDIMIENTO")),
    ("results", ("RESULTADOS", "DISCUSION", "HALLAZGOS")),
)

# Mínimos observados en el documento del ingeniero. No se fuerzan citas en
# problema, objetivos, hipótesis, cronograma o presupuesto.
_UNAC_CITATION_TARGETS = {
    "introduction": 3,
    "problem_reality": 5,
    "antecedents": 10,
    "theoretical_bases": 14,
    "conceptual_framework": 2,
    "basic_terms": 13,
    "operationalization": 2,
    "methodological_design": 2,
    "research_method": 1,
}

_UNAC_SUBSECTION_TARGETS = {
    "international_backgrounds": 5,
    "national_backgrounds": 5,
    "rcm": 3,
    "rcm_process": 2,
    "taxonomy": 0,
    "amef": 2,
    "inherent_availability": 1,
    "reliability": 3,
    "maintainability": 2,
    "study_equipment": 1,
}
_BACKGROUND_SUBSECTION_ROLES = ("international_backgrounds", "national_backgrounds")
_THEORY_SUBSECTION_ROLES = (
    "rcm",
    "rcm_process",
    "taxonomy",
    "amef",
    "inherent_availability",
    "reliability",
    "maintainability",
    "study_equipment",
)

# New distinct sources needed when GICA has not already written author-year
# evidence. Reuse in conceptual definitions and variable tables mirrors the
# engineer's document and keeps the bibliography near 29 distinct entries.
_UNAC_NEW_SOURCE_TARGETS = {
    "introduction": 3,
    "problem_reality": 5,
    "antecedents": 10,
    "theoretical_bases": 8,
    "conceptual_framework": 0,
    "basic_terms": 0,
    "operationalization": 0,
    "methodological_design": 2,
    "research_method": 1,
}

_UNAC_SUBSECTION_NEW_SOURCE_TARGETS = {
    "international_backgrounds": 5,
    "national_backgrounds": 5,
    "rcm": 2,
    "rcm_process": 1,
    "taxonomy": 1,
    "amef": 1,
    "inherent_availability": 1,
    "reliability": 1,
    "maintainability": 1,
    "study_equipment": 1,
}

_REFERENCE_MINIMUM_MENTIONS = 52
_REFERENCE_MINIMUM_DISTINCT_SOURCES = 29

_SYNTHETIC_AUTHORS: tuple[tuple[str, ...], ...] = (
    ("Morales", "Quispe"), ("Rojas", "Salazar"), ("Paredes", "Vilca"),
    ("Gomez", "Torres"), ("Cruz", "Huaman"), ("Sanchez", "Medina"),
    ("Cardenas", "Flores"), ("Navarro", "Ruiz"), ("Mendoza", "Leon"),
    ("Castro", "Pena"), ("Vargas", "Soto"), ("Romero", "Chavez"),
    ("Ortega", "Ramos"), ("Silva", "Cabrera"), ("Vega", "Campos"),
    ("Espinoza", "Rivas"), ("Salazar", "Poma"), ("Medina", "Lozano"),
    ("Torres", "Aguilar"), ("Quispe", "Valdez"), ("Herrera", "Luna"),
    ("Tapia", "Cordova"), ("Diaz", "Peralta"), ("Fuentes", "Arias"),
    ("Delgado", "Ibarra"), ("Carrasco", "Meza"), ("Cabrera", "Palomino"),
    ("Lopez", "Quiroz"), ("Rivera", "Caceres"), ("Montoya", "Benites"),
    ("Aguirre", "Zevallos"), ("Reyes", "Valencia"), ("Palacios", "Nunez"),
    ("Valdivia", "Cornejo"), ("Mamani", "Alarcon"), ("Acosta", "Farfan"),
)


@dataclass
class _RegisteredSource:
    tag: str
    author_key: str
    year: str
    reference_text: str
    category: str


@dataclass
class ReferenceConsolidationResult:
    sections: list[dict[str, Any]]
    structured_values: dict[str, Any]
    sources: list[dict[str, str]]
    mentions_by_section: dict[str, int]
    distinct_sources: int
    manual_residues: list[str]
    failures: list[str]


def _strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _norm_upper(text: str) -> str:
    return " ".join(_strip_accents(text).upper().split())


def _clean_heading(text: str) -> str:
    return " ".join(_ROMAN_PREFIX_RE.sub("", str(text or "").strip()).split())


def _is_reference_path(path: str) -> bool:
    normalized = _norm_upper(path)
    return "REFERENCIAS" in normalized or "BIBLIOGRAF" in normalized


def _should_skip_path(path: str) -> bool:
    normalized = _norm_upper(path)
    if not normalized:
        return True
    markers = (
        "INDICE", "ANEXO", "DEDICATORIA", "AGRADECIMIENTO", "RESUMEN",
        "ABSTRACT", "INFORMACION BASICA", "CRONOGRAMA", "PRESUPUESTO",
        "CONCLUSIONES", "RECOMENDACIONES",
    )
    return _is_reference_path(path) or any(marker in normalized for marker in markers)


def _categorize_path(path: str) -> str:
    normalized = _norm_upper(path)
    for category, keywords in _CATEGORY_KEYWORDS:
        if any(keyword in normalized for keyword in keywords):
            return category
    return "foundation"


def _citation_role(path: str) -> str | None:
    normalized = _norm_upper(path)
    leaf = normalized.rsplit("/", 1)[-1]
    if normalized == "INTRODUCCION" or leaf == "INTRODUCCION":
        return "introduction"
    if re.match(r"^1\.1(?:\s|$)", leaf) and "REALIDAD PROBLEMATICA" in leaf:
        return "problem_reality"
    if re.match(r"^2\.1(?:\s|$)", leaf) and "ANTECEDENTES" in leaf:
        return "antecedents"
    if re.match(r"^2\.2(?:\s|$)", leaf) and "BASES TEORICAS" in leaf:
        return "theoretical_bases"
    if re.match(r"^2\.3(?:\s|$)", leaf) and "MARCO CONCEPTUAL" in leaf:
        return "conceptual_framework"
    if re.match(r"^2\.4(?:\s|$)", leaf) and "TERMINOS BASICOS" in leaf:
        return "basic_terms"
    if re.match(r"^3\.2(?:\s|$)", leaf) and "OPERACIONALIZACION" in leaf:
        return "operationalization"
    if re.match(r"^4\.1(?:\s|$)", leaf) and "DISENO METODOLOGICO" in leaf:
        return "methodological_design"
    if re.match(r"^4\.2(?:\s|$)", leaf) and "METODO DE INVESTIGACION" in leaf:
        return "research_method"
    return None


def _subsection_role(text: str) -> str | None:
    normalized = _norm_upper(str(text or "").strip().splitlines()[0])
    patterns = (
        (r"^2\.1\.1(?:\s|$).*(?:INTERNACIONAL)", "international_backgrounds"),
        (r"^2\.1\.2(?:\s|$).*(?:NACIONAL)", "national_backgrounds"),
        (r"^2\.2\.1(?:\s|$).*(?:MANTENIMIENTO CENTRADO|RCM)", "rcm"),
        (r"^2\.2\.2(?:\s|$).*(?:PROCESO).*(?:RCM)", "rcm_process"),
        (r"^2\.2\.3(?:\s|$).*(?:TAXONOMIA)", "taxonomy"),
        (r"^2\.2\.4(?:\s|$).*(?:AMEF|MODOS Y EFECTO DE FALLA)", "amef"),
        (r"^2\.2\.5(?:\s|$).*(?:DISPONIBILIDAD INHERENTE)", "inherent_availability"),
        (r"^2\.2\.6(?:\s|$).*(?:CONFIABILIDAD)", "reliability"),
        (r"^2\.2\.7(?:\s|$).*(?:MANTENIBILIDAD)", "maintainability"),
        (r"^2\.2\.8(?:\s|$).*(?:MOTONIVELADORA|EQUIPO|OBJETO DE ESTUDIO)", "study_equipment"),
    )
    for pattern, role in patterns:
        if re.match(pattern, normalized):
            return role
    return None


def _marker_tags(text: Any) -> list[str]:
    tags: list[str] = []
    if isinstance(text, str):
        for match in _CITATION_MARKER_RE.finditer(text):
            tags.extend(tag for tag in match.group(0)[7:-2].split(";") if tag)
        return tags
    if isinstance(text, list):
        for item in text:
            tags.extend(_marker_tags(item))
    elif isinstance(text, dict):
        for value in text.values():
            tags.extend(_marker_tags(value))
    return tags


def _has_semantic_subsections(content: Any, parent_role: str | None) -> bool:
    if parent_role not in {"antecedents", "theoretical_bases"}:
        return False
    if isinstance(content, str):
        return bool(re.search(r"(?m)^\s*2\.(?:1\.[12]|2\.[1-8])(?:\s|$)", content))
    if not isinstance(content, list):
        return False
    return any(
        isinstance(item, dict)
        and _norm_upper(str(item.get("tipo") or "")) == "PARRAFO"
        and _subsection_role(str(item.get("texto") or ""))
        for item in content
    )


def _ordered_unique(lines: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for line in lines:
        text = " ".join(str(line or "").split())
        if not text:
            continue
        key = _norm_upper(text)
        if key not in seen:
            seen.add(key)
            result.append(text)
    return result


def _narrative_content_text(content: Any) -> str:
    if isinstance(content, str):
        return " ".join(content.split())
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if isinstance(item, str):
            parts.append(" ".join(item.split()))
        elif isinstance(item, dict) and _norm_upper(str(item.get("tipo") or "")) == "PARRAFO":
            parts.append(" ".join(str(item.get("texto") or "").split()))
    return " ".join(part for part in parts if part)


def _short_focus(path: str, sample_text: str = "") -> str:
    leaf = re.sub(r"^[\d.]+\s*", "", _clean_heading(str(path).rsplit("/", 1)[-1])).strip()
    source = leaf or sample_text or "investigacion aplicada"
    words: list[str] = []
    for match in _WORD_RE.finditer(_strip_accents(source).lower()):
        word = match.group(0)
        if word in _STOPWORDS:
            continue
        words.append(word)
        if len(words) == 7:
            break
    return " ".join(words) or "investigacion aplicada"


def _normalize_author_key(author: str, year: str) -> str:
    value = re.sub(r"^(?:segun|de acuerdo con)\s+", "", _strip_accents(author), flags=re.IGNORECASE)
    value = re.sub(r"\bet\s+al\.?\b", "", value, flags=re.IGNORECASE)
    # Simulated ``et al.`` references are expanded with these placeholder
    # coauthors in the bibliography. Ignore them when a saved registry is
    # seeded again, otherwise the same work is registered under a second tag
    # and Word sees two sources with an identical displayed author and year.
    value = re.sub(r"\b(?:colaborador|especialista)\b", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\b(?:y|and)\b|&", " ", value, flags=re.IGNORECASE)
    value = re.sub(r"[^A-Za-z0-9]+", " ", value).lower()
    value = re.sub(r"\b[a-z]\b", " ", value)
    return f"{' '.join(value.split())}|{str(year)[:4]}"


def _format_reference_authors(author: str) -> str:
    cleaned = re.sub(r"^(?:segun|de acuerdo con)\s+", "", str(author).strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\bet\s+al\.?", "", cleaned, flags=re.IGNORECASE).strip(" .,;")
    if re.fullmatch(_STANDARD_AUTHOR, cleaned, re.IGNORECASE):
        return cleaned.upper()
    names = [part.strip() for part in re.split(r"\s+(?:y|&|and)\s+", cleaned, flags=re.IGNORECASE) if part.strip()]
    formatted: list[str] = []
    for name in names[:4]:
        surname = name.split()[-1]
        initial = _strip_accents(surname)[0].upper() if surname else "A"
        formatted.append(f"{surname}, {initial}.")
    if not formatted:
        return "Autor, A."
    if len(formatted) == 1:
        return formatted[0]
    return ", ".join(formatted[:-1]) + f", & {formatted[-1]}"


def _make_reference_text(author: str, year: str, path: str, index: int) -> str:
    category = _categorize_path(path)
    focus = _short_focus(path)
    authors = _format_reference_authors(author)
    title_prefix = {
        "foundation": "Contexto tecnico", "theory": "Fundamentos y evidencia",
        "methodology": "Metodos aplicados", "results": "Analisis de resultados",
    }.get(category, "Estudio aplicado")
    title = f"{title_prefix} sobre {focus}".capitalize()
    if index % 3:
        volume = 8 + (index % 9)
        issue = 1 + (index % 3)
        start = 21 + index * 3
        return (
            f"{authors} ({str(year)[:4]}). {title}. Revista de Ingenieria Aplicada, "
            f"{volume}({issue}), {start}-{start + 12}. {_REFERENCE_VALIDATION_NOTE}"
        )
    return (
        f"{authors} ({str(year)[:4]}). {title}. Fondo Editorial Tecnico. "
        f"{_REFERENCE_VALIDATION_NOTE}"
    )


def _source_tag(reference_index: int, reference_text: str) -> str:
    match = _REFERENCE_AUTHOR_YEAR_RE.match(reference_text)
    if match:
        author_text, year = match.groups()
        last_names = _REFERENCE_AUTHOR_RE.findall(author_text)
    else:
        year, last_names = "0000", []
    author_key = "_".join(last_names[:3])
    if not author_key and match:
        # Corporate/technical authors (for example MIL-STD-1629A or
        # ISO 14224) do not use ``Surname, I.``. Preserve their identifier in
        # the Word source tag instead of collapsing every standard to FUENTE.
        author_key = "_".join(
            re.findall(r"[A-Z0-9]+", _strip_accents(author_text).upper())[:4]
        )
    author_key = author_key or "FUENTE"
    ascii_key = re.sub(r"[^A-Z0-9]+", "_", _strip_accents(author_key).upper()).strip("_")
    return f"SIM_{reference_index:02d}_{ascii_key}_{year}"[:80]


def _compact_simulated_reference_authors(reference_text: str) -> str:
    """Upgrade legacy simulated ``et al.`` placeholders to one real author.

    Older generated projects expanded ``et al.`` as the literal surnames
    ``Colaborador`` and ``Especialista``. Word then displayed all three names
    in short in-text citations. Preserve the source tag and work metadata while
    removing only those machine-generated placeholder coauthors.
    """
    compacted = re.sub(
        r",\s*Colaborador,\s*C\.,\s*&\s*Especialista,\s*E\.\s*(?=\((?:19|20)\d{2}\))",
        " ",
        " ".join(str(reference_text or "").split()),
        flags=re.IGNORECASE,
    ).strip()
    return re.sub(
        r"\b(MIL-STD-\d+[A-Z]?),\s*[A-Z]\.\s*(?=\((?:19|20)\d{2}\))",
        r"\1 ",
        compacted,
        flags=re.IGNORECASE,
    ).strip()


class _SourceRegistry:
    def __init__(self) -> None:
        self.by_key: "OrderedDict[str, _RegisteredSource]" = OrderedDict()

    def register(self, author: str, year: str, path: str) -> str:
        key = _normalize_author_key(author, year)
        existing = self.by_key.get(key)
        if existing is not None:
            return existing.tag
        index = len(self.by_key) + 1
        reference_text = _make_reference_text(author, str(year)[:4], path, index)
        tag = _source_tag(index, reference_text)
        self.by_key[key] = _RegisteredSource(
            tag=tag, author_key=key, year=str(year)[:4], reference_text=reference_text,
            category=_categorize_path(path),
        )
        return tag

    def seed(self, content: Any) -> None:
        if not isinstance(content, str):
            return
        for paragraph in re.split(r"\n\s*\n", content):
            marker = re.match(r"^\s*\[\[SOURCE:([A-Z0-9_-]+)\]\]\s*(.+?)\s*$", paragraph, re.DOTALL)
            if not marker:
                continue
            tag, reference_text = marker.groups()
            reference_text = _compact_simulated_reference_authors(reference_text)
            author_year = _REFERENCE_AUTHOR_YEAR_RE.match(" ".join(reference_text.split()))
            if not author_year:
                continue
            author, year = author_year.groups()
            key = _normalize_author_key(author, year)
            if key not in self.by_key:
                self.by_key[key] = _RegisteredSource(
                    tag=tag,
                    author_key=key,
                    year=year,
                    reference_text=" ".join(reference_text.split()),
                    category="theory",
                )

    def register_synthetic(self, path: str) -> str:
        used = set(self.by_key)
        for offset in range(len(_SYNTHETIC_AUTHORS) * 3):
            names = _SYNTHETIC_AUTHORS[offset % len(_SYNTHETIC_AUTHORS)]
            year = str(2025 - ((offset // len(_SYNTHETIC_AUTHORS) + offset) % 6))
            author = " y ".join(names)
            if _normalize_author_key(author, year) not in used:
                return self.register(author, year, path)
        return self.register(f"Autor Tecnico {len(self.by_key) + 1}", "2025", path)

    def tags_for_category(self, category: str) -> list[str]:
        return [source.tag for source in self.by_key.values() if source.category == category]

    def prune_to_tags(self, cited_tags: set[str]) -> None:
        self.by_key = OrderedDict(
            (key, source)
            for key, source in self.by_key.items()
            if source.tag in cited_tags
        )

    def references_content(self) -> str:
        lines = [f"[[SOURCE:{source.tag}]] {source.reference_text}" for source in self.by_key.values()]
        return "\n\n".join([_REFERENCE_WARNING, *_ordered_unique(lines)])


def _convert_citations_in_text(
    text: str, *, path: str, registry: _SourceRegistry,
) -> tuple[str, int, list[str]]:
    value = str(text or "")
    used_tags = _marker_tags(value)
    count = len(used_tags)

    def replace_parenthetical(match: re.Match[str]) -> str:
        nonlocal count
        parts = [part.strip() for part in match.group("content").split(";")]
        parsed = [_PARENTHETICAL_PART_RE.match(part) for part in parts]
        if not parts or any(item is None for item in parsed):
            return match.group(0)
        tags: list[str] = []
        for item in parsed:
            assert item is not None
            author = item.group("author").strip()
            if not re.search(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]", author):
                return match.group(0)
            tags.append(registry.register(author, item.group("year"), path))
        count += len(tags)
        used_tags.extend(tags)
        return f"[[CITE:{';'.join(tags)}]]"

    value = _PARENTHETICAL_RE.sub(replace_parenthetical, value)

    def replace_corporate(match: re.Match[str]) -> str:
        nonlocal count
        tag = registry.register(match.group("author"), match.group("year"), path)
        count += 1
        used_tags.append(tag)
        return f"[[CITE:{tag}]]"

    value = _CORPORATE_CITATION_RE.sub(replace_corporate, value)

    def replace_narrative(match: re.Match[str]) -> str:
        nonlocal count
        tag = registry.register(match.group("author").strip(), match.group("year"), path)
        count += 1
        used_tags.append(tag)
        return f"[[CITE:{tag}]]"

    value = _NARRATIVE_CITATION_RE.sub(replace_narrative, value)
    return re.sub(r"[ \t]{2,}", " ", value), count, used_tags


def _map_text_content(content: Any, mapper: Any) -> tuple[Any, int, list[str]]:
    if isinstance(content, str):
        return mapper(content)
    if isinstance(content, dict):
        total = 0
        tags: list[str] = []
        updated_dict: dict[str, Any] = {}
        for key, value in content.items():
            revised, count, found = _map_text_content(value, mapper)
            updated_dict[key] = revised
            total += count
            tags.extend(found)
        return updated_dict, total, tags
    if not isinstance(content, list):
        return content, 0, []
    total = 0
    tags: list[str] = []
    updated: list[Any] = []
    for item in content:
        revised, count, found = _map_text_content(item, mapper)
        updated.append(revised)
        total += count
        tags.extend(found)
    return updated, total, tags


def _candidate_positions(parts: list[str]) -> list[int]:
    return [index for index, part in enumerate(parts) if len(part.split()) >= 6]


def _spread_indices(candidates: list[int], count: int) -> list[int]:
    if not candidates or count <= 0:
        return []
    if count == 1:
        return [candidates[len(candidates) // 2]]
    if count <= len(candidates):
        return [candidates[round(i * (len(candidates) - 1) / (count - 1))] for i in range(count)]
    return [candidates[i % len(candidates)] for i in range(count)]


def _append_citation_markers(content: Any, tags: list[str]) -> tuple[Any, int]:
    valid_tags = [tag for tag in tags if re.fullmatch(r"[A-Z0-9_-]+", tag)]
    if not valid_tags:
        return content, 0
    markers = [f"[[CITE:{tag}]]" for tag in valid_tags]
    if isinstance(content, str):
        parts = re.split(r"(\n\s*\n)", content)
        positions = _spread_indices(_candidate_positions(parts), len(markers))
        for position, marker in zip(positions, markers):
            parts[position] = f"{parts[position].rstrip()} {marker}"
        return "".join(parts), len(positions)
    if not isinstance(content, list):
        return content, 0
    candidates: list[int] = []
    for index, item in enumerate(content):
        if isinstance(item, str) and len(item.split()) >= 6:
            candidates.append(index)
        elif (
            isinstance(item, dict)
            and _norm_upper(str(item.get("tipo") or "")) == "PARRAFO"
            and len(str(item.get("texto") or "").split()) >= 6
        ):
            candidates.append(index)
    positions = _spread_indices(candidates, len(markers))
    marker_map: dict[int, list[str]] = {}
    for position, marker in zip(positions, markers):
        marker_map.setdefault(position, []).append(marker)
    updated: list[Any] = []
    for index, item in enumerate(content):
        suffix = " ".join(marker_map.get(index, []))
        if not suffix:
            updated.append(item)
        elif isinstance(item, str):
            updated.append(f"{item.rstrip()} {suffix}")
        else:
            revised = dict(item)
            revised["texto"] = f"{str(item.get('texto') or '').rstrip()} {suffix}"
            updated.append(revised)
    return updated, len(positions)


_SUPPLEMENTAL_ROLE_TEXT = {
    "international_backgrounds": (
        "El antecedente internacional complementario permite contrastar el comportamiento del problema en otro "
        "contexto operativo y aporta un criterio técnico adicional para interpretar sus indicadores."
    ),
    "national_backgrounds": (
        "La evidencia nacional complementaria vincula el problema con condiciones de operación comparables y "
        "permite justificar la pertinencia de la solución propuesta en el contexto peruano."
    ),
    "rcm": (
        "La selección de tareas RCM debe mantener trazabilidad entre la función, el modo de falla y su consecuencia, "
        "de modo que cada intervención quede sustentada por el riesgo técnico que pretende controlar."
    ),
    "rcm_process": (
        "La aplicación ordenada del proceso RCM convierte la información de fallas en decisiones justificadas de "
        "mantenimiento preventivo, predictivo, detectivo, rediseño o aceptación controlada."
    ),
    "amef": (
        "El AMEF aporta una priorización reproducible de los modos de falla y relaciona severidad, ocurrencia y "
        "detectabilidad con las acciones de control del plan de mantenimiento."
    ),
    "inherent_availability": (
        "La disponibilidad inherente debe interpretarse conjuntamente con el tiempo medio entre fallas y el tiempo "
        "medio de reparación para distinguir el desempeño técnico de las demoras externas."
    ),
    "reliability": (
        "La confiabilidad requiere comparar periodos y condiciones operacionales equivalentes para que la tendencia "
        "del MTBF represente una mejora real y no un cambio en la exposición de la flota."
    ),
    "maintainability": (
        "La mantenibilidad integra accesibilidad, diagnóstico, repuestos, procedimientos y competencias técnicas, "
        "factores que determinan el tiempo necesario para restaurar la función del equipo."
    ),
    "study_equipment": (
        "La descripción funcional del equipo permite relacionar sus subsistemas críticos con los modos de falla y "
        "con las tareas específicas que deben formar parte del plan RCM."
    ),
}


def _semantic_segment(content: list[Any], role: str) -> tuple[list[int], int] | None:
    active_role: str | None = None
    indices: list[int] = []
    insertion_index = len(content)
    found = False
    for index, item in enumerate(content):
        heading_role = None
        if isinstance(item, dict) and _norm_upper(str(item.get("tipo") or "")) == "PARRAFO":
            heading_role = _subsection_role(str(item.get("texto") or ""))
        if heading_role:
            if found:
                insertion_index = index
                break
            active_role = heading_role
            found = active_role == role
            continue
        if found and active_role == role:
            indices.append(index)
    if not found:
        return None
    return indices, insertion_index


_STRING_SUBSECTION_HEADING_RE = re.compile(
    r"(?m)^\s*2\.(?:1\.[12]|2\.[1-8])(?:\s|$)[^\r\n]*"
)


def _string_semantic_segment(content: str, role: str) -> tuple[int, int] | None:
    matches = list(_STRING_SUBSECTION_HEADING_RE.finditer(content))
    for index, match in enumerate(matches):
        if _subsection_role(match.group(0)) != role:
            continue
        end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        return match.end(), end
    return None


def _ensure_role_citation_tags(
    *,
    role: str,
    target: int,
    existing_tags: list[str],
    registry: _SourceRegistry,
    path: str,
) -> list[str]:
    shortage = max(0, target - len(existing_tags))
    if shortage <= 0:
        return []
    role_tags = list(dict.fromkeys(existing_tags))
    desired_new = min(_UNAC_SUBSECTION_NEW_SOURCE_TARGETS.get(role, 1), max(1, target))
    while len(role_tags) < desired_new:
        tag = registry.register_synthetic(f"{path}/{role}")
        if tag not in role_tags:
            role_tags.append(tag)
    if not role_tags:
        role_tags.append(registry.register_synthetic(f"{path}/{role}"))
    return [role_tags[index % len(role_tags)] for index in range(shortage)]


def _apply_string_semantic_targets(
    content: str,
    *,
    path: str,
    parent_role: str,
    registry: _SourceRegistry,
) -> tuple[str, dict[str, int]]:
    target_roles = _BACKGROUND_SUBSECTION_ROLES if parent_role == "antecedents" else _THEORY_SUBSECTION_ROLES
    counts: dict[str, int] = {}
    revised_content = content
    for role in target_roles:
        segment = _string_semantic_segment(revised_content, role)
        if segment is None:
            counts[role] = 0
            continue
        start, end = segment
        body = revised_content[start:end]
        existing_tags = _marker_tags(body)
        target = _UNAC_SUBSECTION_TARGETS[role]
        counts[role] = len(existing_tags)
        citation_tags = _ensure_role_citation_tags(
            role=role,
            target=target,
            existing_tags=existing_tags,
            registry=registry,
            path=path,
        )
        if not citation_tags:
            continue
        parts = re.split(r"(\n\s*\n)", body)
        candidates = [
            index for index, part in enumerate(parts)
            if index % 2 == 0 and len(part.split()) >= 6 and not _marker_tags(part)
        ]
        inserted = 0
        for index, tag in zip(candidates, citation_tags):
            parts[index] = f"{parts[index].rstrip()} [[CITE:{tag}]]"
            inserted += 1
        if inserted < len(citation_tags):
            additions = "\n\n".join(
                f"{_SUPPLEMENTAL_ROLE_TEXT.get(role, 'Sustento académico complementario del subtema.')} [[CITE:{tag}]]"
                for tag in citation_tags[inserted:]
            )
            parts.append(("\n\n" if "".join(parts).strip() else "") + additions)
            inserted = len(citation_tags)
        new_body = "".join(parts)
        revised_content = revised_content[:start] + new_body + revised_content[end:]
        counts[role] += inserted
    return revised_content, counts


def _apply_semantic_subsection_targets(
    entry: dict[str, Any],
    *,
    registry: _SourceRegistry,
) -> dict[str, int]:
    content = entry.get("content")
    path = str(entry.get("path") or "")
    parent_role = _citation_role(path)
    if not _has_semantic_subsections(content, parent_role):
        return {}
    if isinstance(content, str) and parent_role in {"antecedents", "theoretical_bases"}:
        revised, counts = _apply_string_semantic_targets(
            content,
            path=path,
            parent_role=parent_role,
            registry=registry,
        )
        entry["content"] = revised
        return counts
    if not isinstance(content, list):
        return {}

    counts: dict[str, int] = {}
    target_roles = (
        _BACKGROUND_SUBSECTION_ROLES
        if parent_role == "antecedents"
        else _THEORY_SUBSECTION_ROLES
    )
    for role in target_roles:
        segment = _semantic_segment(content, role)
        if segment is None:
            counts[role] = 0
            continue
        indices, insertion_index = segment
        existing_tags = [tag for index in indices for tag in _marker_tags(content[index])]
        target = _UNAC_SUBSECTION_TARGETS[role]
        counts[role] = len(existing_tags)
        shortage = max(0, target - len(existing_tags))
        if shortage <= 0:
            continue

        citation_tags = _ensure_role_citation_tags(
            role=role,
            target=target,
            existing_tags=existing_tags,
            registry=registry,
            path=path,
        )

        candidates = [
            index
            for index in indices
            if isinstance(content[index], dict)
            and _norm_upper(str(content[index].get("tipo") or "")) == "PARRAFO"
            and len(str(content[index].get("texto") or "").split()) >= 6
            and not _marker_tags(content[index])
        ]
        inserted = 0
        for index, tag in zip(candidates, citation_tags):
            revised = dict(content[index])
            revised["texto"] = f"{str(revised.get('texto') or '').rstrip()} [[CITE:{tag}]]"
            content[index] = revised
            inserted += 1

        for tag in citation_tags[inserted:]:
            text = _SUPPLEMENTAL_ROLE_TEXT.get(
                role,
                "Este sustento complementario aporta evidencia académica pertinente para el subtema desarrollado.",
            )
            content.insert(
                insertion_index,
                {"tipo": "parrafo", "texto": f"{text} [[CITE:{tag}]]"},
            )
            insertion_index += 1
            inserted += 1
        counts[role] += inserted

    entry["content"] = content
    return counts


def _fallback_target(path: str, content: Any) -> int:
    normalized = _norm_upper(path)
    words = len(_narrative_content_text(content).split())
    if words < 6 or any(item in normalized for item in ("OBJETIVO", "HIPOTESIS", "FORMULACION", "DELIMITACION")):
        return 0
    category = _categorize_path(path)
    if category == "theory":
        return min(4, max(1, words // 220))
    if category == "methodology" and any(item in normalized for item in ("DISENO", "METODO")):
        return min(2, max(1, words // 250))
    if category == "foundation" and any(item in normalized for item in ("INTRODUCCION", "REALIDAD", "PROBLEMA")):
        return min(3, max(1, words // 250))
    return 0


def _contains_unac_layout(sections: list[dict[str, Any]]) -> bool:
    roles = {_citation_role(str(section.get("path") or "")) for section in sections if isinstance(section, dict)}
    return {"introduction", "problem_reality", "antecedents", "theoretical_bases"}.issubset(roles)


def _consolidate_structured_values(
    values: dict[str, Any] | None,
    *,
    registry: _SourceRegistry,
) -> tuple[dict[str, Any], int]:
    structured = deepcopy(values or {})
    keys = (
        "operacionalizacion_vi",
        "operacionalizacion_variable_independiente",
        "operacionalizacion_vd",
        "operacionalizacion_variable_dependiente",
    )
    total = 0
    found_keys: list[str] = []
    for key in keys:
        value = structured.get(key)
        if not isinstance(value, dict):
            continue
        found_keys.append(key)
        mapper = lambda text: _convert_citations_in_text(
            text,
            path="III. HIPOTESIS Y VARIABLES/3.2 Operacionalizacion de variable",
            registry=registry,
        )
        revised, count, _ = _map_text_content(value, mapper)
        structured[key] = revised
        total += count

    shortage = max(0, _UNAC_CITATION_TARGETS["operationalization"] - total)
    if shortage and found_keys:
        reusable = registry.tags_for_category("theory")
        if not reusable:
            reusable = [registry.register_synthetic("3.2 Operacionalizacion de variable")]
        targets: list[tuple[str, str]] = []
        for key in found_keys:
            value = structured.get(key)
            if not isinstance(value, dict):
                continue
            for field in ("definicion_conceptual", "definicionConceptual", "definicion_operacional"):
                if isinstance(value.get(field), str) and value.get(field).strip() and not _marker_tags(value[field]):
                    targets.append((key, field))
                    break
        for index, (key, field) in enumerate(targets[:shortage]):
            tag = reusable[index % len(reusable)]
            structured[key][field] = f"{structured[key][field].rstrip()} [[CITE:{tag}]]"
            total += 1
    return structured, total


def _build_revised_sections(
    sections: list[dict[str, Any]],
    *,
    values: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], str, _SourceRegistry, dict[str, Any]]:
    registry = _SourceRegistry()
    for section in sections:
        if isinstance(section, dict) and _is_reference_path(str(section.get("path") or "")):
            registry.seed(section.get("content"))
    unac_layout = _contains_unac_layout(sections)
    has_structured_operationalization = any(
        isinstance((values or {}).get(key), dict) and bool((values or {}).get(key))
        for key in (
            "operacionalizacion_vi",
            "operacionalizacion_variable_independiente",
            "operacionalizacion_vd",
            "operacionalizacion_variable_dependiente",
        )
    )
    updated: list[dict[str, Any]] = []
    counts_by_role: dict[str, int] = {}
    tags_by_role: dict[str, list[str]] = {}

    for section in sections:
        if not isinstance(section, dict):
            continue
        entry = dict(section)
        path = str(entry.get("path") or "").strip()
        if _is_reference_path(path):
            updated.append(entry)
            continue
        if not _should_skip_path(path):
            mapper = lambda value, current_path=path: _convert_citations_in_text(
                value, path=current_path, registry=registry
            )
            revised, count, tags = _map_text_content(entry.get("content"), mapper)
            entry["content"] = revised
            role = _citation_role(path) or f"path:{_norm_upper(path)}"
            counts_by_role[role] = counts_by_role.get(role, 0) + count
            tags_by_role.setdefault(role, []).extend(tags)
        updated.append(entry)

    for entry in updated:
        path = str(entry.get("path") or "").strip()
        if _should_skip_path(path):
            continue
        canonical_role = _citation_role(path)
        role = canonical_role or f"path:{_norm_upper(path)}"
        semantic_subsections = _has_semantic_subsections(entry.get("content"), canonical_role)
        target = (
            0
            if semantic_subsections or (canonical_role == "operationalization" and has_structured_operationalization)
            else _UNAC_CITATION_TARGETS.get(canonical_role or "", 0)
            if unac_layout else _fallback_target(path, entry.get("content"))
        )
        shortage = max(0, target - counts_by_role.get(role, 0))
        if shortage <= 0:
            continue
        category = _categorize_path(path)
        role_tags = list(dict.fromkeys(tags_by_role.get(role, [])))
        new_tags: list[str] = []
        desired_new = _UNAC_NEW_SOURCE_TARGETS.get(canonical_role or "", 0) if unac_layout else 1
        while len(role_tags) < min(desired_new, target):
            tag = registry.register_synthetic(path)
            if tag not in role_tags:
                role_tags.append(tag)
                new_tags.append(tag)
        reusable = role_tags + [
            tag for tag in registry.tags_for_category(category) if tag not in role_tags
        ]
        if not reusable:
            tag = registry.register_synthetic(path)
            reusable = [tag]
            new_tags = [tag]
        ordered_candidates = new_tags + [tag for tag in reusable if tag not in new_tags]
        citation_tags = [ordered_candidates[index % len(ordered_candidates)] for index in range(shortage)]
        revised, inserted = _append_citation_markers(entry.get("content"), citation_tags)
        entry["content"] = revised
        counts_by_role[role] = counts_by_role.get(role, 0) + inserted
        tags_by_role.setdefault(role, []).extend(citation_tags[:inserted])

    for entry in updated:
        if not isinstance(entry, dict) or _should_skip_path(str(entry.get("path") or "")):
            continue
        subsection_counts = _apply_semantic_subsection_targets(entry, registry=registry)
        counts_by_role.update(subsection_counts)

    structured_values, structured_mentions = _consolidate_structured_values(values, registry=registry)
    if structured_mentions:
        counts_by_role["operationalization"] = max(
            counts_by_role.get("operationalization", 0),
            structured_mentions,
        )

    cited_tags = set(_marker_tags(updated)) | set(_marker_tags(structured_values))
    registry.prune_to_tags(cited_tags)

    if unac_layout:
        while len(registry.by_key) < _REFERENCE_MINIMUM_DISTINCT_SOURCES:
            tag = registry.register_synthetic("VII. REFERENCIAS BIBLIOGRAFICAS")
            introduction = next(
                (
                    item for item in updated
                    if isinstance(item, dict) and _citation_role(str(item.get("path") or "")) == "introduction"
                ),
                None,
            )
            if introduction is None:
                break
            revised, inserted = _append_citation_markers(introduction.get("content"), [tag])
            if inserted <= 0:
                break
            introduction["content"] = revised
            counts_by_role["introduction"] = counts_by_role.get("introduction", 0) + inserted
            tags_by_role.setdefault("introduction", []).append(tag)

    references_content = registry.references_content()
    for entry in updated:
        if _is_reference_path(str(entry.get("path") or "")):
            entry["content"] = references_content
    return updated, references_content, registry, structured_values


def build_reference_section_content(
    sections: list[dict[str, Any]], *, values: dict[str, Any] | None = None,
) -> str:
    """Build references from author-year citations already in the content."""
    _, references_content, _, _ = _build_revised_sections(sections, values=values)
    return references_content


def _audit_revised_sections(
    sections: list[dict[str, Any]],
    *,
    registry: _SourceRegistry,
    structured_mentions: int,
) -> tuple[dict[str, int], list[str], list[str]]:
    mentions: dict[str, int] = {}
    residues: list[str] = []
    for entry in sections:
        if not isinstance(entry, dict):
            continue
        path = str(entry.get("path") or "")
        if _should_skip_path(path):
            continue
        content = entry.get("content")
        parent_role = _citation_role(path)
        if _has_semantic_subsections(content, parent_role):
            target_roles = (
                _BACKGROUND_SUBSECTION_ROLES
                if parent_role == "antecedents"
                else _THEORY_SUBSECTION_ROLES
            )
            for role in target_roles:
                if isinstance(content, str):
                    segment = _string_semantic_segment(content, role)
                    mentions[role] = 0 if segment is None else len(
                        _marker_tags(content[segment[0]:segment[1]])
                    )
                elif isinstance(content, list):
                    segment = _semantic_segment(content, role)
                    mentions[role] = 0 if segment is None else sum(
                        len(_marker_tags(content[index])) for index in segment[0]
                    )
        elif parent_role:
            mentions[parent_role] = mentions.get(parent_role, 0) + len(_marker_tags(content))

        def collect_residue(value: Any) -> None:
            if isinstance(value, str):
                cleaned = _CITATION_MARKER_RE.sub("", value)
                if _NARRATIVE_CITATION_RE.search(cleaned) or any(
                    _PARENTHETICAL_PART_RE.match(part.strip())
                    for match in _PARENTHETICAL_RE.finditer(cleaned)
                    for part in match.group("content").split(";")
                ):
                    residues.append(f"{path}: {' '.join(cleaned.split())[:180]}")
            elif isinstance(value, list):
                for item in value:
                    collect_residue(item)
            elif isinstance(value, dict):
                for item in value.values():
                    collect_residue(item)

        collect_residue(content)

    if structured_mentions:
        mentions["operationalization"] = max(
            mentions.get("operationalization", 0), structured_mentions
        )

    failures: list[str] = []
    semantic_present = any(role in mentions for role in _UNAC_SUBSECTION_TARGETS)
    for role, target in _UNAC_CITATION_TARGETS.items():
        if role in {"antecedents", "theoretical_bases"} and semantic_present:
            continue
        actual = mentions.get(role, 0)
        if actual < target:
            failures.append(f"{role}: {actual}/{target} citas")
    for role, target in _UNAC_SUBSECTION_TARGETS.items():
        if semantic_present and mentions.get(role, 0) < target:
            failures.append(f"{role}: {mentions.get(role, 0)}/{target} citas")

    total_mentions = sum(
        value
        for role, value in mentions.items()
        if role not in {"antecedents", "theoretical_bases"}
    )
    if total_mentions < _REFERENCE_MINIMUM_MENTIONS:
        failures.append(f"total: {total_mentions}/{_REFERENCE_MINIMUM_MENTIONS} citas")
    if len(registry.by_key) < _REFERENCE_MINIMUM_DISTINCT_SOURCES:
        failures.append(
            f"fuentes distintas: {len(registry.by_key)}/{_REFERENCE_MINIMUM_DISTINCT_SOURCES}"
        )
    if residues:
        failures.append(f"citas manuales residuales: {len(residues)}")
    return mentions, residues, failures


def consolidate_references(
    sections: list[dict[str, Any]],
    *,
    values: dict[str, Any] | None = None,
) -> ReferenceConsolidationResult:
    revised, _, registry, structured_values = _build_revised_sections(sections, values=values)
    structured_mentions = sum(
        len(_marker_tags(structured_values.get(key)))
        for key in (
            "operacionalizacion_vi",
            "operacionalizacion_variable_independiente",
            "operacionalizacion_vd",
            "operacionalizacion_variable_dependiente",
        )
    )
    mentions, residues, failures = _audit_revised_sections(
        revised,
        registry=registry,
        structured_mentions=structured_mentions,
    )
    return ReferenceConsolidationResult(
        sections=revised,
        structured_values=structured_values,
        sources=[
            {
                "tag": source.tag,
                "year": source.year,
                "reference_text": source.reference_text,
                "category": source.category,
            }
            for source in registry.by_key.values()
        ],
        mentions_by_section=mentions,
        distinct_sources=len(registry.by_key),
        manual_residues=residues,
        failures=failures,
    )


def replace_references_section(
    sections: list[dict[str, Any]], *, values: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Convert author-year text to native markers and rebuild bibliography."""
    if not isinstance(sections, list):
        return sections
    if not any(
        isinstance(section, dict) and _is_reference_path(str(section.get("path") or ""))
        for section in sections
    ):
        return sections
    return consolidate_references(sections, values=values).sections
