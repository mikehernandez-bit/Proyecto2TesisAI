"""Versioned narrative-quality profile for UNAC maintenance projects."""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable


_PROFILE_PATH = Path(__file__).with_name("profiles") / "unac_maintenance_v1.json"
_WORD_RE = re.compile(r"\b[\wÁÉÍÓÚÜÑáéíóúüñ]+(?:[-'][\wÁÉÍÓÚÜÑáéíóúüñ]+)?\b", re.UNICODE)
_HEADING_RE = re.compile(r"^\s*(\d+(?:\.\d+){0,2})\.?\s+(.+?)\s*$")
_CITATION_RE = re.compile(r"\[\[CITE:([A-Z0-9_-]+(?:;[A-Z0-9_-]+)*)\]\]")
_SOURCE_RE = re.compile(r"\[\[SOURCE:[\s\S]*?\]\]")
_LABELS = {
    "problema general",
    "problemas especificos",
    "objetivo general",
    "objetivos especificos",
    "hipotesis general",
    "hipotesis especificas",
}

_TOPIC_ALIASES: dict[str, tuple[str, ...]] = {
    "normativa": (
        "justificacion normativa",
        "marco normativo",
        "cumplimiento normativo",
        "sustento normativo",
        "regulacion aplicable",
        "reglamentacion",
        "disposiciones legales",
        "obligaciones legales",
        "estandares tecnicos",
        "sae ja1011",
        "iso 14224",
        "decreto supremo 024-2016-em",
        "d. s. n. 024-2016-em",
    ),
    "organizacion": ("organizacion", "estructura del documento", "estructura del proyecto", "capitulos"),
    "aporte": (
        "aporte",
        "aporta",
        "aportan",
        "contribucion",
        "contribuye",
        "relevancia para el presente",
        "valor teorico",
    ),
    "dimensiones": (
        "dimension",
        "dimensiones",
        "componentes de la variable",
        "indicadores de la variable",
        "mtbf",
        "mttr",
    ),
    "recursos": ("recursos", "presupuesto", "inversion", "financiamiento"),
    "impacto": ("impacto", "beneficio social", "repercusion", "efecto social"),
    "alcance teorico": ("alcance teorico", "alcance conceptual", "comprende teoricamente"),
    "exclusiones": ("exclusiones", "excluye", "fuera del alcance", "no comprende"),
    "periodo": ("periodo", "ano 2025", "durante 2025", "intervalo temporal"),
    "lugar": ("lugar", "ubicacion", "ubicada", "ubicado", "localizada", "localizado", "emplazamiento"),
    "equipos": ("equipos", "motoniveladoras", "flota", "unidades"),
    "ubicacion": ("ubicacion", "ubicada", "ubicado", "localizada", "localizado", "emplazamiento"),
    "definicion": ("definicion", "se define", "se entiende", "concepto"),
    "definiciones": ("definiciones", "se define", "se entiende", "concepto"),
    "terminos tecnicos": ("terminos tecnicos", "glosario", "conceptos tecnicos", "se define", ":"),
    "unidad de analisis": (
        "unidad de analisis",
        "unidades de analisis",
        "equipos estudiados",
        "equipos evaluados",
        "flota evaluada",
        "flota de equipos",
        "motoniveladoras",
        "n =",
    ),
    "priorizacion": ("priorizacion", "priorizar", "jerarquizacion", "orden de criticidad"),
    "diagnostico internacional": ("diagnostico internacional", "contexto internacional", "ambito internacional"),
    "diagnostico nacional": ("diagnostico nacional", "contexto nacional", "ambito nacional", "en el peru"),
    "diagnostico local": ("diagnostico local", "contexto local", "unidad minera", "sierra central"),
}

_CANONICAL_FORMULAS: dict[str, dict[str, str]] = {
    "2.2.5": {
        "tipo": "formula",
        "latex": r"A_i = \frac{MTBF}{MTBF + MTTR}",
        "texto": "A_i = MTBF / (MTBF + MTTR)",
        "alineacion": "center",
        "numero": "(1)",
        "id": "disponibilidad-inherente-ai",
    },
    "2.2.6": {
        "tipo": "formula",
        "latex": r"R(t) = e^{-\lambda t}",
        "texto": "R(t) = e^(-lambda t)",
        "alineacion": "center",
        "numero": "(2)",
        "id": "confiabilidad-rt",
    },
    "2.2.7": {
        "tipo": "formula",
        "latex": r"M(t) = 1 - e^{-\mu t}",
        "texto": "M(t) = 1 - e^(-mu t)",
        "alineacion": "center",
        "numero": "(3)",
        "id": "mantenibilidad-mt",
    },
}


@dataclass(frozen=True)
class SectionQualityRequirement:
    key: str
    heading: str
    min_words: int
    min_citations: int = 0
    min_formulas: int = 0
    topics: tuple[str, ...] = ()


@dataclass(frozen=True)
class UnacQualityProfile:
    id: str
    source_sha256: str
    generation_buffer_percent: int
    global_citation_mentions_min: int
    distinct_sources_min: int
    requirements: tuple[SectionQualityRequirement, ...]


@dataclass(frozen=True)
class SectionQualityAudit:
    key: str
    heading: str
    words: int
    minimum: int
    difference: int
    citations: int
    citation_minimum: int
    formulas: int
    formula_minimum: int
    missing_topics: tuple[str, ...]
    duplicate_ratio: float
    status: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


@lru_cache(maxsize=1)
def load_unac_maintenance_profile() -> UnacQualityProfile:
    raw = json.loads(_PROFILE_PATH.read_text(encoding="utf-8"))
    requirements = tuple(
        SectionQualityRequirement(
            key=str(item["key"]),
            heading=str(item["heading"]),
            min_words=int(item["min_words"]),
            min_citations=int(item.get("min_citations") or 0),
            min_formulas=int(item.get("min_formulas") or 0),
            topics=tuple(str(topic) for topic in item.get("topics", [])),
        )
        for item in raw["requirements"]
    )
    return UnacQualityProfile(
        id=str(raw["id"]),
        source_sha256=str(raw["source_sha256"]),
        generation_buffer_percent=int(raw["generation_buffer_percent"]),
        global_citation_mentions_min=int(raw["global_citation_mentions_min"]),
        distinct_sources_min=int(raw["distinct_sources_min"]),
        requirements=requirements,
    )


def is_unac_maintenance_project(format_id: str | None, values: dict[str, Any] | None) -> bool:
    if not str(format_id or "").lower().startswith("unac"):
        return False
    values = values if isinstance(values, dict) else {}
    selected: list[str] = []
    for key in (
        "title",
        "titulo",
        "tema",
        "problema_general",
        "objetivo_general",
        "variable_independiente",
        "variable_dependiente",
        "objeto_estudio",
    ):
        value = values.get(key)
        if isinstance(value, str):
            selected.append(value)
    matrix = values.get("matriz_consistencia")
    if isinstance(matrix, dict):
        selected.append(json.dumps(matrix, ensure_ascii=False))
    combined = _norm(" ".join(selected))
    markers = ("mantenimiento", "confiabilidad", "disponibilidad", "mtbf", "mttr", "rcm")
    return sum(marker in combined for marker in markers) >= 2


def _paragraph_texts(content: Any) -> Iterable[str]:
    if isinstance(content, str):
        yield content
        return
    if not isinstance(content, list):
        return
    for block in content:
        if not isinstance(block, dict):
            continue
        kind = _norm(block.get("tipo"))
        if kind == "parrafo":
            text = str(block.get("texto") or "").strip()
            if text:
                yield text
        elif kind in {"lista", "list"}:
            for item in block.get("items", []):
                if str(item).strip():
                    yield str(item).strip()


def _section_key_from_path(path: str) -> str | None:
    normalized = _norm(path)
    if normalized.endswith("introduccion") or normalized == "introduccion":
        return "introduccion"
    matches = re.findall(r"(?<!\d)(\d+(?:\.\d+){0,2})(?!\d)", str(path or ""))
    return matches[-1] if matches else None


def section_key_from_path(path: str) -> str | None:
    return _section_key_from_path(path)


def requirements_for_section_path(section_path: str) -> tuple[SectionQualityRequirement, ...]:
    """Return exact or child semantic requirements in institutional order."""
    key = _section_key_from_path(section_path)
    if key is None:
        return ()
    requirements = load_unac_maintenance_profile().requirements
    children = tuple(item for item in requirements if item.key.startswith(key + "."))
    if children:
        return children
    return tuple(item for item in requirements if item.key == key)


def canonical_formula_for_key(key: str) -> dict[str, str] | None:
    formula = _CANONICAL_FORMULAS.get(str(key or "").strip())
    return dict(formula) if formula else None


def _split_paragraph_text(text: str) -> list[dict[str, str]]:
    """Turn mixed multiline prose into stable paragraph/heading blocks."""
    blocks: list[dict[str, str]] = []
    buffer: list[str] = []

    def flush() -> None:
        value = " ".join(part.strip() for part in buffer if part.strip()).strip()
        buffer.clear()
        if value:
            blocks.append({"tipo": "parrafo", "texto": value})

    for line in str(text or "").replace("\r", "\n").split("\n"):
        cleaned = line.strip()
        if not cleaned:
            flush()
            continue
        if _HEADING_RE.match(cleaned.strip("#* ")):
            flush()
            blocks.append({"tipo": "parrafo", "texto": cleaned.strip("#* ")})
            continue
        buffer.append(cleaned)
    flush()
    return blocks


def normalize_semantic_blocks(content: Any) -> list[dict[str, Any]]:
    """Normalize prose boundaries while preserving structured non-prose blocks."""
    if isinstance(content, str):
        return _split_paragraph_text(content)
    if not isinstance(content, list):
        return []
    normalized: list[dict[str, Any]] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if _norm(block.get("tipo")) == "parrafo":
            normalized.extend(_split_paragraph_text(str(block.get("texto") or "")))
        else:
            normalized.append(dict(block))
    return normalized


def canonicalize_duplicate_semantic_units(
    sections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Keep one best occurrence of every profile unit in composite sections.

    Repair providers can occasionally return the whole parent section instead
    of the requested child.  Repeated headings must never be allowed to inflate
    the quality audit or the Word table of contents.
    """
    profile = load_unac_maintenance_profile()
    for section in sections:
        if not isinstance(section, dict):
            continue
        owner_key = _section_key_from_path(str(section.get("path") or ""))
        if not owner_key:
            continue
        requirements = [
            item for item in profile.requirements if item.key.startswith(owner_key + ".")
        ]
        if not requirements:
            continue
        blocks = normalize_semantic_blocks(section.get("content"))
        requirement_by_key = {item.key: item for item in requirements}
        # Normalize every recognized profile heading even when no duplicate is
        # present.  The number is the semantic identity; the visible title must
        # remain the exact institutional caption from the versioned profile.
        recognized_profile_heading = False
        for block in blocks:
            key = _block_heading_key(block)
            requirement = requirement_by_key.get(key or "")
            if requirement is not None:
                recognized_profile_heading = True
                block["texto"] = requirement.heading
        starts: list[tuple[int, str]] = []
        for index, block in enumerate(blocks):
            key = _block_heading_key(block)
            if key in requirement_by_key:
                starts.append((index, key))
        counts = Counter(key for _, key in starts)
        if not any(count > 1 for count in counts.values()):
            if recognized_profile_heading:
                section["content"] = blocks
            continue

        candidates: dict[str, list[tuple[int, list[dict[str, Any]]]]] = {
            item.key: [] for item in requirements
        }
        for occurrence, (start, key) in enumerate(starts):
            end = starts[occurrence + 1][0] if occurrence + 1 < len(starts) else len(blocks)
            candidates[key].append((start, [dict(block) for block in blocks[start:end]]))

        canonical = [dict(block) for block in blocks[: starts[0][0]]]
        for requirement in requirements:
            choices = candidates.get(requirement.key) or []
            if not choices:
                continue

            def content_score(content: list[dict[str, Any]], start: int) -> tuple[float, ...]:
                audit = audit_unac_maintenance_sections(
                    [{"path": requirement.heading, "content": content}]
                )[0]
                hard_penalty = (
                    len(audit.missing_topics) * 10000
                    + max(0, requirement.min_formulas - audit.formulas) * 10000
                    + max(0, requirement.min_words - audit.words)
                    + max(0.0, audit.duplicate_ratio - 0.22) * 10000
                )
                return (
                    hard_penalty,
                    audit.duplicate_ratio,
                    -min(audit.words, requirement.min_words * 2),
                    -start,
                )

            def score(choice: tuple[int, list[dict[str, Any]]]) -> tuple[float, ...]:
                return content_score(choice[1], choice[0])

            best_start, best = min(choices, key=score)
            selected = [dict(block) for block in best]
            selected_score = content_score(selected, best_start)
            seen_text = {
                _norm(block.get("texto"))
                for block in selected
                if _norm(block.get("tipo")) == "parrafo" and _norm(block.get("texto"))
            }
            for alternative_start, alternative in sorted(choices, key=score):
                if alternative_start == best_start:
                    continue
                for block in alternative[1:]:
                    kind = _norm(block.get("tipo"))
                    if kind not in {"parrafo", "lista", "list", "formula"}:
                        continue
                    text_token = _norm(block.get("texto")) if kind == "parrafo" else ""
                    if text_token and text_token in seen_text:
                        continue
                    proposed = [*selected, dict(block)]
                    proposed_score = content_score(proposed, best_start)
                    if proposed_score < selected_score:
                        selected = proposed
                        selected_score = proposed_score
                        if text_token:
                            seen_text.add(text_token)
                    if selected_score[0] <= 0:
                        break
                if selected_score[0] <= 0:
                    break
            canonical.extend(selected)
        section["content"] = canonical
    return sections


def _block_heading_key(block: dict[str, Any]) -> str | None:
    if _norm(block.get("tipo")) != "parrafo":
        return None
    text = str(block.get("texto") or "").strip().strip("#* ")
    match = _HEADING_RE.match(text)
    return match.group(1) if match else None


def _semantic_bounds(blocks: list[dict[str, Any]], key: str) -> tuple[int, int] | None:
    start = next((index for index, block in enumerate(blocks) if _block_heading_key(block) == key), None)
    if start is None:
        return None
    depth = key.count(".")
    end = len(blocks)
    for index in range(start + 1, len(blocks)):
        candidate = _block_heading_key(blocks[index])
        if candidate and candidate.count(".") <= depth:
            end = index
            break
    return start, end


def extract_semantic_unit_content(content: Any, key: str) -> list[dict[str, Any]]:
    blocks = normalize_semantic_blocks(content)
    bounds = _semantic_bounds(blocks, key)
    if bounds is None:
        return []
    return [dict(block) for block in blocks[bounds[0] : bounds[1]]]


def replace_semantic_unit_content(
    content: Any,
    *,
    requirement: SectionQualityRequirement,
    replacement: Any,
) -> list[dict[str, Any]]:
    """Replace exactly one numbered unit and preserve every sibling block."""
    owner_blocks = normalize_semantic_blocks(content)
    replacement_blocks = normalize_semantic_blocks(replacement)
    replacement_bounds = _semantic_bounds(replacement_blocks, requirement.key)
    if replacement_bounds is not None:
        replacement_blocks = replacement_blocks[replacement_bounds[0] : replacement_bounds[1]]
    elif not replacement_blocks or _block_heading_key(replacement_blocks[0]) != requirement.key:
        replacement_blocks.insert(0, {"tipo": "parrafo", "texto": requirement.heading})

    owner_bounds = _semantic_bounds(owner_blocks, requirement.key)
    if owner_bounds is None:
        if owner_blocks and owner_blocks[-1].get("texto"):
            owner_blocks.append({"tipo": "parrafo", "texto": requirement.heading})
            owner_blocks.extend(replacement_blocks[1:])
        else:
            owner_blocks.extend(replacement_blocks)
        return owner_blocks
    return owner_blocks[: owner_bounds[0]] + replacement_blocks + owner_blocks[owner_bounds[1] :]


def ensure_canonical_formulas(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Guarantee the three maintenance formulas independently of LLM syntax."""
    for section in sections:
        if not isinstance(section, dict):
            continue
        section_key = _section_key_from_path(str(section.get("path") or ""))
        relevant = [
            key
            for key in _CANONICAL_FORMULAS
            if section_key == key or (section_key == "2.2" and key.startswith("2.2."))
        ]
        if not relevant:
            continue
        blocks = normalize_semantic_blocks(section.get("content"))
        # Remove common malformed formula-only fragments before inserting the canonical block.
        blocks = [
            block
            for block in blocks
            if not (
                _norm(block.get("tipo")) == "parrafo"
                and (
                    _norm(block.get("texto")).startswith("formula json")
                    or '"latex"' in str(block.get("texto") or "")
                    or "'latex'" in str(block.get("texto") or "")
                )
            )
        ]
        for key in sorted(relevant, reverse=True):
            bounds = _semantic_bounds(blocks, key)
            if bounds is None:
                continue
            start, end = bounds
            formula_indexes = [
                index
                for index in range(start, end)
                if _norm(blocks[index].get("tipo")) == "formula"
            ]
            insertion = formula_indexes[0] if formula_indexes else min(start + 2, end)
            for index in reversed(formula_indexes):
                blocks.pop(index)
            blocks.insert(insertion, canonical_formula_for_key(key) or {})
        section["content"] = blocks
    return sections


def _topic_is_covered(topic: str, normalized: str) -> bool:
    aliases = _TOPIC_ALIASES.get(_norm(topic), (topic,))
    return any(_norm(alias) in normalized for alias in aliases if _norm(alias))


def _split_units(sections: list[dict[str, Any]]) -> tuple[dict[str, list[str]], Counter[str], Counter[str]]:
    units: dict[str, list[str]] = {}
    citations: Counter[str] = Counter()
    formulas: Counter[str] = Counter()
    known_headings = {_norm(item.heading) for item in load_unac_maintenance_profile().requirements}
    for section in sections:
        if not isinstance(section, dict):
            continue
        current_key = _section_key_from_path(str(section.get("path") or ""))
        if current_key:
            units.setdefault(current_key, [])
        content = section.get("content")
        blocks = content if isinstance(content, list) else []
        if isinstance(content, str):
            blocks = [{"tipo": "parrafo", "texto": content}]
        for block in blocks:
            if not isinstance(block, dict):
                continue
            kind = _norm(block.get("tipo"))
            if kind == "formula":
                if current_key:
                    formulas[current_key] += 1
                continue
            if kind in {"figura", "tabla", "bibliography", "bibliografia"}:
                continue
            texts = [str(block.get("texto") or "")] if kind == "parrafo" else [str(x) for x in block.get("items", [])] if kind in {"lista", "list"} else []
            for raw in texts:
                lines = [line.strip() for line in raw.replace("\r", "\n").split("\n") if line.strip()]
                for line in lines:
                    clean_heading = line.strip("#* ")
                    heading_match = _HEADING_RE.match(clean_heading)
                    if heading_match:
                        current_key = heading_match.group(1)
                        units.setdefault(current_key, [])
                        remainder = ""
                    else:
                        remainder = line
                    if not current_key or not remainder:
                        continue
                    for marker in _CITATION_RE.findall(remainder):
                        citations[current_key] += len(marker.split(";"))
                    remainder = _CITATION_RE.sub(" ", remainder)
                    remainder = _SOURCE_RE.sub(" ", remainder)
                    if _norm(remainder) in _LABELS or _norm(remainder) in known_headings:
                        continue
                    units.setdefault(current_key, []).append(remainder)
    return units, citations, formulas


def _duplicate_ratio(paragraphs: list[str]) -> float:
    tokens = [_norm(item).split() for item in paragraphs]
    grams: list[tuple[str, ...]] = []
    for words in tokens:
        grams.extend(tuple(words[index : index + 7]) for index in range(max(0, len(words) - 6)))
    if not grams:
        return 0.0
    counts = Counter(grams)
    repeated = sum(count - 1 for count in counts.values() if count > 1)
    return round(repeated / len(grams), 3)


def audit_unac_maintenance_sections(sections: list[dict[str, Any]]) -> list[SectionQualityAudit]:
    profile = load_unac_maintenance_profile()
    units, citations, formulas = _split_units(sections)
    audits: list[SectionQualityAudit] = []
    selected_roots = set(units)
    active_requirements = []
    for requirement in profile.requirements:
        parent = requirement.key.rsplit(".", 1)[0] if requirement.key.count(".") >= 2 else requirement.key
        if requirement.key in selected_roots or parent in selected_roots:
            active_requirements.append(requirement)

    for requirement in active_requirements:
        paragraphs = units.get(requirement.key, [])
        narrative = " ".join(paragraphs)
        words = len(_WORD_RE.findall(narrative))
        normalized = _norm(narrative)
        if requirement.key == "2.4":
            explicit_definition_signals = sum(
                1
                for paragraph in paragraphs
                if ":" in paragraph or any(signal in _norm(paragraph) for signal in ("se define", "se entiende", "concepto"))
            )
            # Mistral suele devolver el glosario como ``**Termino.** Definicion``.
            # Es una definicion sustantiva aunque no contenga dos puntos ni la
            # frase literal "se define". Contamos cada entrada, no las palabras
            # genericas del encabezado, para evitar falsos positivos.
            term_definition_signals = sum(
                1
                for paragraph in paragraphs
                if re.match(
                    r"^\s*(?:\*\*)?[^\n.]{2,100}\.\*{0,2}\s+\S+",
                    paragraph,
                )
            )
            definition_signals = max(explicit_definition_signals, term_definition_signals)
            missing_topics = () if definition_signals >= 8 else tuple(requirement.topics)
        else:
            missing_topics = tuple(topic for topic in requirement.topics if not _topic_is_covered(topic, normalized))
        duplicate_ratio = _duplicate_ratio(paragraphs)
        ok = (
            words >= requirement.min_words
            and citations[requirement.key] >= requirement.min_citations
            and formulas[requirement.key] >= requirement.min_formulas
            and not missing_topics
            and duplicate_ratio <= 0.22
        )
        audits.append(
            SectionQualityAudit(
                key=requirement.key,
                heading=requirement.heading,
                words=words,
                minimum=requirement.min_words,
                difference=words - requirement.min_words,
                citations=citations[requirement.key],
                citation_minimum=requirement.min_citations,
                formulas=formulas[requirement.key],
                formula_minimum=requirement.min_formulas,
                missing_topics=missing_topics,
                duplicate_ratio=duplicate_ratio,
                status="ok" if ok else "error",
            )
        )
    return audits


def quality_failures(audits: Iterable[SectionQualityAudit]) -> list[SectionQualityAudit]:
    return [audit for audit in audits if audit.status != "ok"]


def content_quality_failures(audits: Iterable[SectionQualityAudit]) -> list[SectionQualityAudit]:
    """Failures that require rewriting prose before citation consolidation."""
    return [
        audit
        for audit in audits
        if audit.words < audit.minimum
        or audit.formulas < audit.formula_minimum
        or audit.missing_topics
        or audit.duplicate_ratio > 0.22
    ]


def minimum_for_section_path(section_path: str) -> int | None:
    """Return the profile floor for a selected section, aggregating children."""
    key = _section_key_from_path(section_path)
    if key is None:
        return None
    requirements = load_unac_maintenance_profile().requirements
    exact = [item for item in requirements if item.key == key]
    children = [item for item in requirements if item.key.startswith(key + ".")]
    selected = children or exact
    return sum(item.min_words for item in selected) if selected else None
