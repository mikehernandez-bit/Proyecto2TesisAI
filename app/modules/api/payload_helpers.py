"""Payload builders and data-adaptation helpers.

Extracted from router.py to separate data transformation from HTTP routing.
These functions build, adapt, and normalize payloads for GicaTesis rendering.
"""

from __future__ import annotations

import logging
import unicodedata
import hashlib
import json
import re
from typing import Any

import httpx

from app.core.config import settings
from app.core.services.ai.content_parser import parse_ai_content
from app.core.services.ai.figure_recommendations import apply_figure_recommendations
from app.core.services.ai.output_validator import OutputValidator
from app.core.services.ai.reference_proposals import consolidate_references
from app.core.services.ai.unac_quality_profile import (
    canonicalize_duplicate_semantic_units,
    ensure_canonical_formulas,
)
from app.core.services.ai.budget_table_builder import (
    build_budget_table_from_plan,
    build_synthetic_budget_plan,
    extract_budget_plan_from_content,
    salvage_budget_plan_from_legacy_table,
    validate_budget_plan,
)
from app.core.services.ai.schedule_table_builder import (
    build_schedule_table_from_plan,
    extract_schedule_plan_from_content,
    salvage_schedule_plan_from_legacy_table,
    validate_schedule_plan,
)
from app.core.services.ai.section_content_policy import (
    allows_structured_content,
    is_chapter_three_operationalization_section,
    is_chapter_four_design_section,
)
from app.core.services.maestria_payload_mapper import (
    is_maestria_format,
    map_maestria_values,
    normalize_maestria_details,
)
from app.core.services.toc_detector import is_toc_path as _is_toc_path
from app.integrations.gicatesis.types import RenderPayloadValidationError, validate_render_payload

_logger = logging.getLogger(__name__)
_OPERATIONALIZATION_BRIDGE_TEXT = (
    "La operacionalizacion de variables se desarrolla con los datos estructurados del proyecto "
    "y se presenta en las Tablas 3.1 y 3.2 del formato institucional."
)


def _methodology_truth(values: dict[str, Any]) -> dict[str, Any]:
    matrix = values.get("matriz_consistencia")
    if not isinstance(matrix, dict):
        matrix = values.get("matriz")
    methodology = matrix.get("metodologia") if isinstance(matrix, dict) else None
    return methodology if isinstance(methodology, dict) else {}


def _canonical_preexperimental_paragraph(values: dict[str, Any], original: str = "") -> str:
    """Build the design paragraph from project truth, never from LLM assumptions."""
    methodology = _methodology_truth(values)
    population = str(methodology.get("poblacion") or values.get("poblacion") or "").strip()
    if not population:
        population_match = re.search(
            r"poblaci[oó]n\s+(?:est[aá]\s+(?:conformada|constituida)\s+por|corresponde\s+a)\s+"
            r"(.+?)(?=,|\s+y\s+la\s+recolecci[oó]n|\.|$)",
            original,
            flags=re.IGNORECASE,
        )
        population = population_match.group(1).strip() if population_match else "la población registrada"
    sample = str(methodology.get("muestra") or values.get("muestra") or "").strip().rstrip(" .;")
    place = str(values.get("lugar_ejecucion") or values.get("lugar") or "el lugar de estudio registrado").strip().rstrip(" .;")
    period = str(values.get("temporal") or values.get("anio") or "el periodo definido").strip().rstrip(" .;")
    citation_markers = " ".join(dict.fromkeys(re.findall(r"\[\[CITE:[^\]]+\]\]", original)))
    paragraph = (
        "El diseño metodológico es preexperimental con preprueba y posprueba. "
        "Primero se realizará una medición inicial de los indicadores de la variable dependiente; "
        "después se aplicará la intervención definida por la variable independiente y, finalmente, "
        "se efectuará una medición posterior bajo criterios equivalentes. "
        f"La población está constituida por {population}. "
    )
    if sample:
        if _normalize_token(sample).startswith("muestreo"):
            paragraph += f"La muestra se determinó mediante {sample[0].lower() + sample[1:]}. "
        else:
            paragraph += f"La muestra corresponde a {sample}. "
    paragraph += (
        f"El estudio se ejecutará en {place} durante {period}. "
        "La comparación de las mediciones antes y después de la intervención permitirá estimar su efecto "
        "sobre la variable dependiente y contrastar la hipótesis, manteniendo control documental sobre "
        "las condiciones de medición y la trazabilidad de los indicadores."
    )
    if citation_markers:
        paragraph += f" {citation_markers}"
    return paragraph


def _replace_contradictory_design_paragraphs(text: str, *, values: dict[str, Any]) -> str:
    parts = re.split(r"(\n\s*\n)", text)
    contradiction_markers = (
        "no experimental",
        "transversal",
        "sin manipulacion",
        "sin intervencion experimental",
        "sin intervencion deliberada",
        "contexto natural",
        "un unico momento",
        "un solo momento",
        "un solo periodo",
    )
    for index in range(0, len(parts), 2):
        paragraph = parts[index]
        normalized = _normalize_token(paragraph)
        declares_design = "diseno metodologico" in normalized or "diseno de investigacion" in normalized
        if declares_design and any(marker in normalized for marker in contradiction_markers):
            design_match = re.search(
                r"\b(?:el\s+)?dise[nñ]o\s+(?:metodol[oó]gico|de\s+investigaci[oó]n)",
                paragraph,
                flags=re.IGNORECASE,
            )
            prefix = paragraph[: design_match.start()] if design_match else ""
            contradictory_design = paragraph[design_match.start() :] if design_match else paragraph
            parts[index] = prefix + _canonical_preexperimental_paragraph(values, contradictory_design)
    return "".join(parts)


def _reconcile_unac_methodology(
    sections: list[dict[str, Any]],
    *,
    values: dict[str, Any],
) -> list[dict[str, Any]]:
    """Make 4.1 obey the structured matrix before rendering.

    The LLM occasionally emits a correlational/non-experimental design even
    when the matrix explicitly defines an explanatory pretest/posttest design.
    Safe, known contradictions are corrected deterministically; any remaining
    contradiction is rejected instead of reaching Word silently.
    """
    methodology = _methodology_truth(values)
    expected_level = _normalize_token(methodology.get("nivel") or values.get("nivel_investigacion"))
    expected_design = _normalize_token(
        methodology.get("diseno")
        or methodology.get("diseño")
        or values.get("diseno_investigacion")
    )
    expects_preexperimental = "pre experimental" in expected_design or "preexperimental" in expected_design
    expects_explanatory = "explicativ" in expected_level
    if not expects_preexperimental and not expects_explanatory:
        return sections

    residual_failures: list[str] = []
    for section in sections:
        if not isinstance(section, dict) or "4.1" not in _normalize_token(section.get("path")):
            continue
        content = section.get("content")
        if isinstance(content, str):
            text = content
            if expects_explanatory:
                # Generated prose varies considerably (for example,
                # "descriptivo-correlacional" instead of the older exact
                # phrase "enfoque correlacional").  Reconcile the declared
                # level first and then remove statements which would still
                # describe an association-only study.
                text = re.sub(
                    r"\b(?:nivel|alcance)\s+(?:de\s+la\s+investigaci[oó]n\s+es\s+)?"
                    r"(?:descriptiv[oa](?:\s*[-–/]\s*|\s+y\s+)?correlacional|correlacional)\b",
                    "nivel de la investigación es explicativo",
                    text,
                    flags=re.IGNORECASE,
                )
                text = re.sub(
                    r"\bdescriptiv[oa]\s*[-–/]\s*correlacional\b",
                    "explicativo",
                    text,
                    flags=re.IGNORECASE,
                )
                text = re.sub(r"\benfoque\s+correlacional\b", "nivel explicativo", text, flags=re.IGNORECASE)
                text = re.sub(
                    r"identificar\s+el\s+grado\s+de\s+asociaci[oó]n\s+entre\s+ambas\s+variables\s+sin\s+manipulaci[oó]n\s+experimental",
                    "explicar el efecto de la variable independiente sobre la variable dependiente mediante una intervención controlada",
                    text,
                    flags=re.IGNORECASE,
                )
                text = re.sub(
                    r"permite\s+identificar\s+patrones\s+y\s+asociaciones\s+entre\s+las\s+variables\s+sin\s+manipularlas\s+directamente",
                    "permite explicar el efecto de la intervención sobre la variable dependiente mediante mediciones antes y después",
                    text,
                    flags=re.IGNORECASE,
                )
            if expects_preexperimental:
                # Prefer a canonical paragraph whenever the generated design
                # contradicts the matrix. This covers arbitrary wording such
                # as "de tipo transversal" instead of chasing every phrase.
                text = _replace_contradictory_design_paragraphs(text, values=values)
                text = re.sub(
                    r"\bno\s+experimental\s+de\s+corte\s+transversal\b",
                    "preexperimental con preprueba y posprueba",
                    text,
                    flags=re.IGNORECASE,
                )
                text = re.sub(
                    r"corresponde\s+a\s+un\s+estudio\s+no\s+experimental\s+de\s+corte\s+transversal,\s*"
                    r"donde\s+las\s+variables\s+se\s+analizan\s+en\s+un\s+momento\s+espec[ií]fico\s*"
                    r"\(([^)]+)\)\s+sin\s+intervenci[oó]n\s+directa\s+sobre\s+las\s+unidades\s+de\s+estudio",
                    r"corresponde a un estudio preexperimental con preprueba y posprueba, en el que los indicadores se miden antes y después de implementar el plan durante \1",
                    text,
                    flags=re.IGNORECASE,
                )
                text = re.sub(
                    r"sin\s+intervenci[oó]n\s+deliberada\s+sobre\s+(?:ellas|las\s+variables)",
                    "con intervención deliberada mediante la aplicación del plan de mantenimiento",
                    text,
                    flags=re.IGNORECASE,
                )
                text = re.sub(
                    r"evaluar\s+la\s+relaci[oó]n\s+entre\s+las\s+variables\s+en\s+su\s+contexto\s+natural",
                    "evaluar el efecto de la intervención sobre la disponibilidad inherente",
                    text,
                    flags=re.IGNORECASE,
                )
                text = re.sub(
                    r"(?:en\s+)?un\s+solo\s+per[ií]odo\s+temporal",
                    "en dos momentos, antes y después de la intervención",
                    text,
                    flags=re.IGNORECASE,
                )
                text = re.sub(
                    r"\benfoque\s+transversal\b",
                    "diseño preexperimental con preprueba y posprueba",
                    text,
                    flags=re.IGNORECASE,
                )
            section["content"] = text
            normalized_content = _normalize_token(text)
        else:
            normalized_content = _normalize_token(json.dumps(content, ensure_ascii=False))

        if expects_preexperimental and any(
            marker in normalized_content
            for marker in (
                "no experimental",
                "corte transversal",
                "enfoque transversal",
                "sin intervencion deliberada",
                "sin manipulacion deliberada",
                "sin intervencion experimental",
                "sin manipularlas directamente",
            )
        ):
            residual_failures.append("4.1 contradice el diseño preexperimental de la matriz")
        if expects_explanatory and any(
            marker in normalized_content
            for marker in ("correlacional", "alcance descriptivo", "nivel descriptivo")
        ):
            residual_failures.append("4.1 contradice el nivel explicativo de la matriz")

    if residual_failures:
        raise RenderPayloadValidationError(
            [
                {
                    "loc": ["body", "aiResult", "methodology", "4.1"],
                    "msg": " | ".join(dict.fromkeys(residual_failures)),
                    "type": "value_error.unac_methodology_alignment",
                }
            ]
        )
    return sections


def _strip_redundant_introduction_heading(
    sections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    for section in sections:
        if not isinstance(section, dict):
            continue
        path = _normalize_token(section.get("path"))
        if path.split("/")[-1].strip() != "introduccion":
            continue
        content = section.get("content")
        if isinstance(content, str):
            lines = content.replace("\r\n", "\n").replace("\r", "\n").split("\n")
            if lines and _normalize_token(lines[0]) == "introduccion":
                section["content"] = "\n".join(lines[1:]).lstrip()
        elif isinstance(content, list) and content:
            first = content[0]
            if (
                isinstance(first, dict)
                and _normalize_token(first.get("texto") or first.get("text")) == "introduccion"
            ):
                section["content"] = content[1:]
    return sections


def _normalize_token(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    ascii_only = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_only.split())


def _is_schedule_or_budget_chapter_name(label: str) -> bool:
    normalized = _normalize_token(label)
    if not normalized:
        return False
    if "cronograma de actividades" in normalized:
        return True
    return "presupuesto" in normalized


def _canonicalize_schedule_budget_section_path(path: Any) -> str:
    raw = str(path or "").strip()
    if not raw:
        return ""
    parts = [part.strip() for part in raw.split("/") if part.strip()]
    if len(parts) <= 1:
        return raw
    if _is_schedule_or_budget_chapter_name(parts[0]):
        return parts[0]
    return raw


def _is_excluded_static_section_path(path: str) -> bool:
    normalized = _normalize_token(path)
    if not normalized:
        return False
    if "cronograma resumido de actividades" in normalized:
        return True
    if "matriz de consistencia de implementaci" in normalized:
        return True
    return "matriz de operacionalizaci" in normalized and (
        "diseno" in normalized or "bases te" in normalized
    )


def _is_template_owned_project_section_path(path: str) -> bool:
    """Sections still owned by template-level rendering and not by free-form AI output."""
    normalized = _normalize_token(path)
    if not normalized:
        return False
    return normalized == "anexos" or normalized.startswith("anexos/")


def _is_valid_schedule_table_payload(table: dict[str, Any]) -> bool:
    return OutputValidator._is_valid_schedule_table(table)


def _is_unac_schedule_chapter_path(path: Any) -> bool:
    return _canonicalize_schedule_budget_section_path(path) == "V. CRONOGRAMA DE ACTIVIDADES"


def _canonicalize_schedule_blocks(content: Any, values: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    blocks = _content_to_blocks(content)
    table_blocks = [
        block
        for block in blocks
        if isinstance(block, dict) and _normalize_token(block.get("tipo")) == "tabla"
    ]
    for table in table_blocks:
        if _is_valid_schedule_table_payload(table):
            return [table]

    plan = extract_schedule_plan_from_content(blocks)
    if isinstance(plan, dict):
        plan_errors = validate_schedule_plan(plan)
        fatal_plan_errors = [
            error
            for error in plan_errors
            if error not in {"mes_fuera_de_ventana", "numeracion_semantica_invalida"}
        ]
        if not fatal_plan_errors:
            return [build_schedule_table_from_plan(plan, values=values or {})]

    for table in table_blocks:
        table_errors = set(OutputValidator._schedule_table_errors(table))
        rescued_plan = None
        if table_errors and table_errors.issubset(OutputValidator._SCHEDULE_LEGACY_RECOVERABLE_ERRORS):
            rescued_plan = salvage_schedule_plan_from_legacy_table(table, values=values or {})
        if isinstance(rescued_plan, dict):
            return [build_schedule_table_from_plan(rescued_plan, values=values or {})]

    return []


def _is_valid_budget_table_payload(table: dict[str, Any]) -> bool:
    headers = table.get("encabezados")
    rows = table.get("filas")
    normalized_headers = [_normalize_token(item) for item in headers] if isinstance(headers, list) else []
    if _normalize_token(table.get("subtipo")) != "presupuesto_investigacion":
        return False
    if _normalize_token(table.get("orientacion")) != "portrait":
        return False
    if len(normalized_headers) != 5:
        return False
    if normalized_headers[0] not in {"n", "n?", "n°"} and not normalized_headers[0].startswith("n"):
        return False
    if normalized_headers[1:] != [
        "descripcion del gasto",
        "cantidad",
        "costo unit. (s/.)",
        "costo total (s/.)",
    ]:
        return False
    if not isinstance(rows, list) or len(rows) != 14:
        return False
    if table.get("filas_categoria") != [0, 2, 7, 11]:
        return False
    if table.get("fila_total") != 13:
        return False
    return bool(table.get("celdas_combinadas")) and bool(table.get("celdas_fusionadas"))


def _canonicalize_budget_blocks(content: Any, values: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    blocks = _content_to_blocks(content)
    table_blocks = [
        block
        for block in blocks
        if isinstance(block, dict) and _normalize_token(block.get("tipo")) == "tabla"
    ]
    for table in table_blocks:
        if _is_valid_budget_table_payload(table):
            return [table]

    plan = extract_budget_plan_from_content(blocks)
    if isinstance(plan, dict):
        if not validate_budget_plan(plan):
            return [build_budget_table_from_plan(plan, values=values or {})]

    for table in table_blocks:
        rescued_plan = salvage_budget_plan_from_legacy_table(table, values=values or {})
        if isinstance(rescued_plan, dict) and not validate_budget_plan(rescued_plan):
            return [build_budget_table_from_plan(rescued_plan, values=values or {})]

    return []


def _has_valid_structured_table(content: Any, *, path: str) -> bool:
    if _is_unac_schedule_chapter_path(path):
        canonical_blocks = _canonicalize_schedule_blocks(content)
        return bool(canonical_blocks and _is_valid_schedule_table_payload(canonical_blocks[0]))
    if _is_schedule_or_budget_chapter_name(path) and "presupuesto" in _normalize_token(path):
        canonical_blocks = _canonicalize_budget_blocks(content)
        return bool(canonical_blocks and _is_valid_budget_table_payload(canonical_blocks[0]))

    for block in _content_to_blocks(content):
        if str(block.get("tipo") or "").strip().lower() != "tabla":
            continue
        if _is_schedule_or_budget_chapter_name(path):
            if _is_valid_budget_table_payload(block):
                return True
            continue
        headers = block.get("encabezados")
        rows = block.get("filas")
        if isinstance(headers, list) and headers and isinstance(rows, list) and rows:
            return True
    return False


def _required_schedule_budget_paths(
    normalized_selected_sections: list[dict[str, Any]],
    ai_result_raw: dict[str, Any] | None,
) -> set[str]:
    required: set[str] = set()
    for item in normalized_selected_sections:
        path = _canonicalize_schedule_budget_section_path(item.get("section_path") or item.get("path") or "")
        if _is_schedule_or_budget_chapter_name(path):
            required.add(path)

    raw_sections = ai_result_raw.get("sections") if isinstance(ai_result_raw, dict) else None
    if isinstance(raw_sections, list):
        for item in raw_sections:
            if not isinstance(item, dict):
                continue
            path = _canonicalize_schedule_budget_section_path(item.get("path") or "")
            if _is_schedule_or_budget_chapter_name(path):
                required.add(path)
    return required


def _validate_required_schedule_budget_tables(
    ai_result: dict[str, Any],
    *,
    required_paths: set[str],
) -> None:
    if not required_paths:
        return

    sections = ai_result.get("sections")
    if not isinstance(sections, list):
        raise RenderPayloadValidationError(
            [
                {
                    "loc": ["body", "aiResult", "sections"],
                    "msg": "Selected schedule/budget chapters require validated AI table sections.",
                    "type": "value_error.missing_schedule_budget_sections",
                }
            ]
        )

    errors: list[dict[str, Any]] = []
    for path in sorted(required_paths):
        matched = next(
            (
                section
                for section in sections
                if _canonicalize_schedule_budget_section_path(section.get("path") or "") == path
            ),
            None,
        )
        if matched is None:
            errors.append(
                {
                    "loc": ["body", "aiResult", "sections", path],
                    "msg": (
                        f"Selected chapter '{path}' requires a validated AI table and it is missing from the payload."
                    ),
                    "type": "value_error.missing_schedule_budget_table",
                }
            )
            continue
        if not _has_valid_structured_table(matched.get("content"), path=path):
            errors.append(
                {
                    "loc": ["body", "aiResult", "sections", path],
                    "msg": (
                        f"Selected chapter '{path}' must contain a validated structured AI table with non-empty "
                        "encabezados and filas."
                    ),
                    "type": "value_error.invalid_schedule_budget_table",
                }
            )

    if errors:
        raise RenderPayloadValidationError(errors)


def _flatten_structured_to_text(content: list[dict[str, Any]]) -> str:
    """Extract only paragraph text from a structured content list."""
    parts: list[str] = []
    for item in content:
        if isinstance(item, str):
            text = item.strip()
            if text:
                parts.append(text)
        elif isinstance(item, dict) and item.get("tipo") == "parrafo":
            text = str(item.get("texto") or "").strip()
            if text:
                parts.append(text)
    return "\n\n".join(parts)


def _content_to_blocks(content: Any) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    if isinstance(content, str):
        text = content.strip()
        if text:
            blocks.append({"tipo": "parrafo", "texto": text})
        return blocks

    if not isinstance(content, list):
        return blocks

    for item in content:
        if isinstance(item, str):
            text = item.strip()
            if text:
                blocks.append({"tipo": "parrafo", "texto": text})
            continue
        if not isinstance(item, dict):
            continue
        block_type = str(item.get("tipo") or "").strip().lower()
        if block_type == "parrafo":
            text = str(item.get("texto") or "").strip()
            if text:
                blocks.append({"tipo": "parrafo", "texto": text})
        elif block_type in {"tabla", "figura", "formula"}:
            blocks.append(dict(item))
    return blocks


def _has_visible_content(content: Any) -> bool:
    if isinstance(content, str):
        return bool(content.strip())
    return bool(_content_to_blocks(content))


def _merge_content(parent_content: Any, child_content: Any) -> Any:
    if isinstance(parent_content, str) and isinstance(child_content, str):
        parent_text = parent_content.strip()
        child_text = child_content.strip()
        if parent_text and child_text:
            return f"{parent_text}\n\n{child_text}"
        return parent_text or child_text

    merged_blocks = _content_to_blocks(parent_content) + _content_to_blocks(child_content)
    if not merged_blocks:
        return ""
    if all(str(block.get("tipo") or "").strip().lower() == "parrafo" for block in merged_blocks):
        return _flatten_structured_to_text(merged_blocks)
    return merged_blocks


def _normalize_selected_sections_for_render(
    selected_sections: list[dict[str, Any]] | list[str] | None,
) -> list[dict[str, Any]]:
    if not isinstance(selected_sections, list):
        return []

    def _to_int(value: Any, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    normalized: list[dict[str, Any]] = []
    by_path: dict[str, dict[str, Any]] = {}
    for item in selected_sections:
        if isinstance(item, str):
            key = _canonicalize_schedule_budget_section_path(item)
            if not key:
                continue
            entry = {"section_id": key, "section_path": key, "path": key}
            if key not in by_path:
                by_path[key] = entry
                normalized.append(entry)
            continue
        if not isinstance(item, dict):
            continue

        section_id = str(
            item.get("section_id") or item.get("sectionId") or item.get("id") or ""
        ).strip()
        raw_section_path = str(
            item.get("section_path")
            or item.get("sectionPath")
            or item.get("path")
            or ""
        ).strip()
        section_path = _canonicalize_schedule_budget_section_path(raw_section_path)
        if not section_id and not section_path:
            continue
        parent_path = str(item.get("parent_section_path") or item.get("parentSectionPath") or "").strip()
        section_title = str(item.get("section_title") or item.get("sectionTitle") or item.get("title") or "").strip()
        if section_path and raw_section_path and section_path != raw_section_path:
            parent_path = ""
            if not section_title:
                section_title = section_path.split("/")[-1]
        entry = {
            "section_id": section_id,
            "section_path": section_path,
            "path": section_path or section_id,
            "section_title": section_title,
            "parent_section_path": parent_path,
            "section_level": _to_int(item.get("section_level") or item.get("sectionLevel"), 1),
            "section_order": _to_int(item.get("section_order") or item.get("sectionOrder"), 0),
            "optional": bool(item.get("optional")),
            "default_selected": bool(item.get("default_selected", True)),
        }
        dedupe_key = str(entry.get("section_path") or entry.get("section_id") or "").strip()
        if not dedupe_key:
            continue
        existing = by_path.get(dedupe_key)
        if existing is None:
            by_path[dedupe_key] = entry
            normalized.append(entry)
            continue
        existing["default_selected"] = bool(existing.get("default_selected", True)) or bool(
            entry.get("default_selected", True)
        )
        existing["optional"] = bool(existing.get("optional")) and bool(entry.get("optional"))
        existing["section_order"] = min(
            _to_int(existing.get("section_order"), 0),
            _to_int(entry.get("section_order"), 0),
        )
        if not str(existing.get("section_title") or "").strip():
            existing["section_title"] = section_title
    return normalized


def _strip_raw_structured_string(content: str) -> str:
    stripped = content.strip()
    if (
        stripped[:1] in "[{"
        and ("'tipo'" in stripped or '"tipo"' in stripped)
        and any(
            token in stripped
            for token in (
                "'parrafo'",
                '"parrafo"',
                "'tabla'",
                '"tabla"',
                "'figura'",
                '"figura"',
                "'formula'",
                '"formula"',
            )
        )
    ):
        return ""

    kept_lines: list[str] = []
    for line in content.splitlines():
        raw = line.strip()
        if (
            raw[:1] in "[{"
            and ("'tipo'" in raw or '"tipo"' in raw)
            and any(
                token in raw
                for token in (
                    "'parrafo'",
                    '"parrafo"',
                    "'tabla'",
                    '"tabla"',
                    "'figura'",
                    '"figura"',
                    "'formula'",
                    '"formula"',
                )
            )
        ):
            continue
        kept_lines.append(line)
    return "\n".join(kept_lines).strip()


def _drop_nonrenderable_figures(path: str, content: list[Any]) -> list[Any]:
    """Remove provider-only captions while preserving all other saved blocks."""
    theoretical_bases = "2.2" in _normalize_token(path) and "bases teoricas" in _normalize_token(path)
    figure_limit = OutputValidator.MAX_THEORETICAL_BASES_FIGURE_BLOCKS if theoretical_bases else None
    figure_count = 0
    cleaned: list[Any] = []
    for item in content:
        if not isinstance(item, dict) or _normalize_token(item.get("tipo")) != "figura":
            cleaned.append(item)
            continue
        image_path = str(
            item.get("ruta")
            or item.get("ruta_placeholder")
            or item.get("image_path")
            or ""
        ).strip()
        diagram_type = str(item.get("diagram_type") or "").strip()
        if not image_path and not diagram_type:
            continue
        if figure_limit is not None and figure_count >= figure_limit:
            continue
        cleaned.append(item)
        figure_count += 1
    return cleaned


def _apply_section_content_policy(path: str, content: Any) -> Any:
    if isinstance(content, str):
        return _strip_raw_structured_string(content)
    if not isinstance(content, list):
        return content
    if is_chapter_three_operationalization_section(path):
        return _flatten_structured_to_text(content)
    if is_chapter_four_design_section(path):
        kept_blocks = [
            item
            for item in _content_to_blocks(content)
            if str(item.get("tipo") or "").strip().lower() in {"parrafo", "formula"}
        ]
        if not kept_blocks:
            return ""
        if all(str(block.get("tipo") or "").strip().lower() == "parrafo" for block in kept_blocks):
            return _flatten_structured_to_text(kept_blocks)
        return kept_blocks
    if allows_structured_content(path):
        # Recheck the one render-critical invariant on every render attempt.
        # Avoid a full sanitation pass here because formulas and tables have
        # already been approved and must not be degraded on retry.
        return _drop_nonrenderable_figures(path, content)
    return _flatten_structured_to_text(content)


def extract_upstream_detail(response: httpx.Response, default_message: str) -> str:
    """Extract useful detail from an upstream HTTP response body."""
    try:
        payload = response.json()
    except Exception:
        payload = None

    if isinstance(payload, dict):
        detail = payload.get("detail")
        if isinstance(detail, str) and detail.strip():
            return detail.strip()

    raw = response.text.strip() if isinstance(response.text, str) else ""
    if raw:
        return raw[:500]
    return default_message


def gicatesis_unavailable_detail(action: str) -> str:
    return (
        f"{action}: no se pudo conectar a GicaTesis en "
        f"{settings.GICATESIS_BASE_URL}. Levanta GicaTesis en :8000 o "
        "actualiza GICATESIS_BASE_URL. Para pruebas de catalogo sin upstream, "
        "puedes usar GICAGEN_DEMO_MODE=true."
    )


def build_sim_sections(section_index: list[dict[str, Any]]) -> list[dict[str, str]]:
    sections: list[dict[str, str]] = []
    for idx, section in enumerate(section_index, start=1):
        path = str(section.get("path") or "").strip()
        if not path:
            continue
        section_id = str(section.get("sectionId") or f"sec-{idx:04d}")
        sections.append(
            {
                "sectionId": section_id,
                "path": path,
                "content": f"Contenido IA simulado para: {path}",
            }
        )
    if not sections:
        sections.append(
            {
                "sectionId": "sec-0001",
                "path": "Documento/Seccion principal",
                "content": "Contenido IA simulado para: Documento/Seccion principal",
            }
        )
    return sections


def values_with_title(
    project: dict[str, Any],
    source_values: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Ensure render/generation values include ``title`` fallback.

    Merges source values with priority:
      1. project["values"] (Legacy/lowest)
      2. project["variables"] (Wizard/Excel data)
      3. source_values (Override/highest)
    """
    # 1. Start with legacy values
    vals = project.get("values") if isinstance(project.get("values"), dict) else {}
    # 2. Merge wizard variables (these are more reliable as they come from Excel/UI)
    vars = project.get("variables") if isinstance(project.get("variables"), dict) else {}

    # Combined base
    values: dict[str, Any] = {**vals, **vars, **(source_values or {})}

    def _is_unac_project_format(project_data: dict[str, Any]) -> bool:
        category = str(project_data.get("category") or "").lower()
        format_id = str(
            project_data.get("format_id") or project_data.get("formatId") or project_data.get("id") or ""
        ).lower()
        university = str(project_data.get("university") or "").lower()
        return ("unac-proyecto" in format_id) or (university == "unac" and "proyecto" in category)

    # SPECIAL HANDLING FOR UNAC MAESTRÍA / UNAC PROYECTO:
    if is_maestria_format(project):
        maestria_details = project.get("maestria_details")
        maestria_source = maestria_details if isinstance(maestria_details, dict) else values
        maestria_values = map_maestria_values(normalize_maestria_details(maestria_source))
        # Update only if not empty to prevent wiping existing good data
        for k, v in maestria_values.items():
            if v:
                values[k] = v
        if _is_unac_project_format(project):
            values["tipo_documento"] = "PROYECTO DE INVESTIGACIÓN"
            values["frase_grado"] = "PARA OPTAR EL GRADO ACADÉMICO DE MAESTRO EN GERENCIA DE MANTENIMIENTO"
            values["facultad"] = "ESCUELA DE POSGRADO"
            values["escuela"] = "UNIDAD DE POSGRADO DE LA FACULTAD DE INGENIERÍA MECÁNICA Y DE ENERGÍA"

    # 3. Asegurar sincronización y prioridad del título
    # Priorizamos lo que hay en 'values' (que ya incluye vars) sobre el 'project.title' raíz
    explicit_title = str(values.get("titulo") or values.get("title") or "").strip()
    root_title = str(project.get("title") or "").strip()
    current_theme = str(values.get("tema") or "").strip()

    final_title = explicit_title or root_title or current_theme

    if final_title:
        values["title"] = final_title
        values.setdefault("titulo", final_title)
        values.setdefault("tema", final_title)

    return values


def adapt_ai_result_for_gicatesis(
    ai_result: dict[str, Any] | None,
    *,
    values: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Adapt the stored ai_result into the sections-only list GicaTesis expects."""
    if not ai_result or not isinstance(ai_result, dict):
        return {"sections": []}

    raw_sections = ai_result.get("sections")
    if not isinstance(raw_sections, list):
        return {"sections": []}

    canonical_sections: list[dict[str, Any]] = []
    for item in raw_sections:
        if not isinstance(item, dict):
            continue
        path = _canonicalize_schedule_budget_section_path(item.get("path") or "")
        if not path or _is_toc_path(path):
            continue
        if _is_excluded_static_section_path(path):
            continue
        if _is_template_owned_project_section_path(path):
            continue

        raw_content = item.get("content")
        canonical_id = item.get("sectionId")

        content = _apply_section_content_policy(path, raw_content)
        if _is_unac_schedule_chapter_path(path):
            content = _canonicalize_schedule_blocks(content, values=values or {})
        elif _is_schedule_or_budget_chapter_name(path) and "presupuesto" in _normalize_token(path):
            content = _canonicalize_budget_blocks(content, values=values or {})
        if is_chapter_three_operationalization_section(path) and not _has_visible_content(content):
            content = _OPERATIONALIZATION_BRIDGE_TEXT
        if not _has_visible_content(content):
            continue
        entry: dict[str, Any] = {
            "path": path,
            "content": content,
        }
        if canonical_id:
            entry["sectionId"] = canonical_id
        existing = next(
            (section for section in canonical_sections if str(section.get("path") or "") == path),
            None,
        )
        if existing is None:
            canonical_sections.append(entry)
            continue
        existing["content"] = _merge_content(existing.get("content"), content)
        if canonical_id and not existing.get("sectionId"):
            existing["sectionId"] = canonical_id

    by_path: dict[str, dict[str, Any]] = {item["path"]: item for item in canonical_sections if item.get("path")}
    parent_paths_with_children: set[str] = set()
    for path in by_path:
        prefix = f"{path}/"
        if any(other_path.startswith(prefix) for other_path in by_path):
            parent_paths_with_children.add(path)

    paths_to_drop: set[str] = set()
    for parent_path in parent_paths_with_children:
        parent_entry = by_path.get(parent_path)
        if not parent_entry:
            continue
        parent_content = parent_entry.get("content")
        if not _has_visible_content(parent_content):
            paths_to_drop.add(parent_path)
            continue

        first_child: dict[str, Any] | None = None
        child_prefix = f"{parent_path}/"
        for item in canonical_sections:
            item_path = item.get("path", "")
            if item_path.startswith(child_prefix):
                first_child = item
                break
        if first_child is not None:
            first_child["content"] = _merge_content(parent_content, first_child.get("content"))
        paths_to_drop.add(parent_path)

    if paths_to_drop:
        canonical_sections = [item for item in canonical_sections if item.get("path") not in paths_to_drop]

    return {"sections": canonical_sections}


def _section_identity_keys(section: dict[str, Any]) -> tuple[str, str]:
    section_id = str(section.get("sectionId") or section.get("section_id") or "").strip()
    section_path = str(section.get("path") or section.get("section_path") or "").strip()
    return section_id, section_path


def _build_generation_phase_fallback(
    ai_result: dict[str, Any] | None,
    generation_phase: dict[str, Any] | None,
) -> dict[str, Any]:
    """Restore missing or empty ai_result sections from generation trace output."""
    base_ai_result = ai_result if isinstance(ai_result, dict) else {"sections": []}
    raw_sections = base_ai_result.get("sections")
    merged_sections: list[dict[str, Any]] = (
        [dict(item) for item in raw_sections if isinstance(item, dict)]
        if isinstance(raw_sections, list)
        else []
    )

    if not isinstance(generation_phase, dict):
        return {"sections": merged_sections}

    generation_sections = generation_phase.get("sections")
    if not isinstance(generation_sections, list):
        return {"sections": merged_sections}

    id_to_index: dict[str, int] = {}
    path_to_index: dict[str, int] = {}
    for index, section in enumerate(merged_sections):
        section_id, section_path = _section_identity_keys(section)
        if section_id:
            id_to_index[section_id] = index
        normalized_path = _normalize_token(section_path)
        if normalized_path:
            path_to_index[normalized_path] = index

    for trace in generation_sections:
        if not isinstance(trace, dict):
            continue
        trace_id = str(trace.get("section_id") or trace.get("sectionId") or "").strip()
        trace_path = str(trace.get("section_path") or trace.get("path") or "").strip()
        normalized_trace_path = _normalize_token(trace_path)
        raw_output = str(trace.get("ai_output") or "").strip()
        if not raw_output:
            continue

        parsed_content = parse_ai_content(raw_output)
        if _is_unac_schedule_chapter_path(trace_path):
            parsed_content = _canonicalize_schedule_blocks(parsed_content)
        elif _is_schedule_or_budget_chapter_name(trace_path) and "presupuesto" in _normalize_token(trace_path):
            parsed_content = _canonicalize_budget_blocks(parsed_content)
        if not _has_visible_content(parsed_content):
            continue

        target_index = -1
        if trace_id and trace_id in id_to_index:
            target_index = id_to_index[trace_id]
        elif normalized_trace_path and normalized_trace_path in path_to_index:
            target_index = path_to_index[normalized_trace_path]

        if target_index >= 0:
            current_content = merged_sections[target_index].get("content")
            if _has_visible_content(current_content):
                continue
            merged_sections[target_index]["content"] = parsed_content
            if trace_id and not merged_sections[target_index].get("sectionId"):
                merged_sections[target_index]["sectionId"] = trace_id
            if trace_path and not merged_sections[target_index].get("path"):
                merged_sections[target_index]["path"] = trace_path
            continue

        if not trace_path:
            continue
        fallback_section: dict[str, Any] = {"path": trace_path, "content": parsed_content}
        if trace_id:
            fallback_section["sectionId"] = trace_id
        merged_sections.append(fallback_section)
        new_index = len(merged_sections) - 1
        if trace_id:
            id_to_index[trace_id] = new_index
        if normalized_trace_path:
            path_to_index[normalized_trace_path] = new_index

    return {"sections": merged_sections}


def build_render_payload(
    *,
    format_id: str,
    values: dict[str, Any],
    ai_result_raw: dict[str, Any] | None,
    generation_phase: dict[str, Any] | None = None,
    selected_sections: list[dict[str, Any]] | list[str] | None = None,
) -> dict[str, Any]:
    """Build render payload for GicaTesis preserving canonical AI sections."""
    render_values = dict(values or {})
    if is_maestria_format({"id": format_id}):
        maestria_values = map_maestria_values(normalize_maestria_details(render_values))
        for key, value in maestria_values.items():
            if value not in ("", None, [], {}):
                render_values[key] = value
    _validate_unac_matrix_alignment(format_id, render_values)
    ai_with_fallback = _build_generation_phase_fallback(ai_result_raw, generation_phase)
    adapted_ai_result = adapt_ai_result_for_gicatesis(ai_with_fallback, values=values)
    sections = adapted_ai_result.get("sections")
    if isinstance(sections, list):
        sections = canonicalize_duplicate_semantic_units(sections)
        sections = _strip_redundant_introduction_heading(sections)
        format_token = _normalize_token(format_id)
        domain_text = _normalize_token(
            " ".join(
                str(render_values.get(key) or "")
                for key in (
                    "title",
                    "titulo",
                    "tema",
                    "variable_independiente",
                    "variable_dependiente",
                    "objeto_estudio",
                    "poblacion",
                )
            )
        )
        strict_unac_maintenance = format_token.startswith("unac-proyecto") and any(
            marker in domain_text
            for marker in ("mantenimiento", "confiabilidad", "disponibilidad", "rcm", "motoniveladora")
        )
        if strict_unac_maintenance:
            # This final, idempotent pass also upgrades saved projects created
            # before the figure-guide contract was fixed. A render retry can
            # therefore restore captions and blue authoring prompts without
            # calling the AI provider again.
            sections = apply_figure_recommendations(
                sections,
                values=render_values,
                format_id=format_id,
            )
            sections = _reconcile_unac_methodology(sections, values=render_values)
            sections = ensure_canonical_formulas(sections)
        adapted_ai_result = {**adapted_ai_result, "sections": sections}
    has_reference_section = isinstance(sections, list) and any(
        isinstance(section, dict)
        and ("referencias" in _normalize_token(section.get("path")) or "bibliograf" in _normalize_token(section.get("path")))
        for section in sections
    )
    if isinstance(sections, list) and has_reference_section:
        consolidation = consolidate_references(sections, values=render_values)
        adapted_ai_result = {**adapted_ai_result, "sections": consolidation.sections}
        render_values = consolidation.structured_values

        strict_unac_references = strict_unac_maintenance
        if strict_unac_references and consolidation.failures:
            raise RenderPayloadValidationError(
                [
                    {
                        "loc": ["body", "aiResult", "references"],
                        "msg": "Incumplimiento de citas UNAC: " + " | ".join(consolidation.failures),
                        "type": "value_error.unac_reference_policy",
                    }
                ]
            )
    normalized_selected_sections = _normalize_selected_sections_for_render(selected_sections)
    _validate_required_schedule_budget_tables(
        adapted_ai_result,
        required_paths=_required_schedule_budget_paths(normalized_selected_sections, ai_with_fallback),
    )
    payload = {
        "formatId": format_id,
        "values": render_values,
        "mode": "simulation",
        "aiResult": adapted_ai_result,
        "selectedSections": normalized_selected_sections,
    }
    return validate_render_payload(payload)


def _matrix_scalar(values: dict[str, Any], key: str, group: str, nested_key: str) -> str:
    direct = values.get(key)
    if str(direct or "").strip():
        return str(direct).strip()
    matrix = values.get("matriz_consistencia")
    if isinstance(matrix, dict):
        direct = matrix.get(key)
        if str(direct or "").strip():
            return str(direct).strip()
        nested = matrix.get(group)
        if isinstance(nested, dict):
            return str(nested.get(nested_key) or "").strip()
    return ""


def _matrix_items(values: dict[str, Any], key: str, group: str) -> list[str]:
    raw: Any = values.get(key)
    matrix = values.get("matriz_consistencia")
    if not isinstance(raw, list) and isinstance(matrix, dict):
        raw = matrix.get(key)
        if not isinstance(raw, list) and isinstance(matrix.get(group), dict):
            raw = matrix[group].get("especificos")
    return [str(item).strip() for item in (raw if isinstance(raw, list) else []) if str(item).strip()]


def _validate_unac_matrix_alignment(format_id: str, values: dict[str, Any]) -> None:
    """Reject a render whose problem/objective/hypothesis matrix is misaligned."""
    token = _normalize_token(format_id)
    domain = _normalize_token(
        " ".join(
            str(values.get(key) or "")
            for key in ("title", "titulo", "tema", "variable_independiente", "variable_dependiente")
        )
    )
    if not token.startswith("unac-proyecto") or not any(
        marker in domain for marker in ("mantenimiento", "confiabilidad", "disponibilidad", "rcm")
    ):
        return

    problem_general = _matrix_scalar(values, "problema_general", "problemas", "general")
    objective_general = _matrix_scalar(values, "objetivo_general", "objetivos", "general")
    problems = _matrix_items(values, "problemas_especificos", "problemas")
    objectives = _matrix_items(values, "objetivos_especificos", "objetivos")
    hypotheses = _matrix_items(values, "hipotesis_especificas", "hipotesis")
    errors: list[str] = []
    if problem_general and not (problem_general.startswith("¿") and problem_general.endswith("?")):
        errors.append("el problema general debe conservar signos de interrogacion")
    for index, problem in enumerate(problems, start=1):
        if not (problem.startswith("¿") and problem.endswith("?")):
            errors.append(f"el problema especifico {index} debe conservar signos de interrogacion")
    for label, objective in [("general", objective_general), *[(str(i), item) for i, item in enumerate(objectives, 1)]]:
        first_word = re.sub(r"[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", "", objective.split(maxsplit=1)[0]) if objective else ""
        if objective and not _normalize_token(first_word).endswith(("ar", "er", "ir")):
            errors.append(f"el objetivo {label} debe iniciar con verbo en infinitivo")
    if (problem_general or objective_general) and (len(problems) < 2 or len(objectives) < 2):
        errors.append("se requieren al menos dos problemas y objetivos especificos")
    if problems or objectives:
        if len(problems) != len(objectives):
            errors.append("problemas y objetivos especificos no tienen correspondencia uno a uno")
        if hypotheses and len(hypotheses) != len(problems):
            errors.append("hipotesis y problemas especificos no tienen correspondencia uno a uno")
    if errors:
        raise RenderPayloadValidationError(
            [
                {
                    "loc": ["body", "values", "matriz_consistencia"],
                    "msg": "Matriz UNAC invalida: " + " | ".join(errors),
                    "type": "value_error.unac_matrix_alignment",
                }
            ]
        )


def extract_resume_seed_sections(ai_result_raw: Any) -> list[dict[str, Any]]:
    """Extract already generated sections from stored ai_result.

    Used to provide context for resuming a partially completed generation.
    Returns a list of dicts with 'path' and 'content' keys.
    """
    if not ai_result_raw or not isinstance(ai_result_raw, dict):
        return []

    raw_sections = ai_result_raw.get("sections")
    if not isinstance(raw_sections, list):
        return []

    seed_sections: list[dict[str, Any]] = []
    for item in raw_sections:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip()
        content = item.get("content")

        # We only take sections that have some content
        if path and content:
            seed_sections.append(
                {
                    "sectionId": str(item.get("sectionId") or ""),
                    "path": path,
                    "content": content,
                    "semanticUnitsCompleted": list(item.get("semanticUnitsCompleted") or []),
                    "semanticUnitsTotal": int(item.get("semanticUnitsTotal") or 0),
                    "semanticComplete": bool(item.get("semanticComplete", True)),
                }
            )
    return seed_sections


def project_input_fingerprint(project: dict[str, Any]) -> str:
    """Stable identity of inputs that affect generated content.

    Provider/model selection is intentionally excluded so a retry can switch
    provider while preserving already approved sections.
    """
    payload = {
        "format_id": project.get("format_id") or project.get("formatId") or "",
        "format_version": project.get("format_version") or project.get("formatVersion") or "",
        "prompt_id": project.get("prompt_id") or project.get("promptId") or "",
        "prompt_snapshot": project.get("prompt_snapshot") or project.get("promptSnapshot") or {},
        "title": project.get("title") or "",
        "values": project.get("values") or {},
        "variables": project.get("variables") or {},
        "maestria_details": project.get("maestria_details") or project.get("maestriaDetails") or {},
        "selected_sections": project.get("selected_sections") or project.get("selectedSections") or [],
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def decide_resume_mode(project: dict[str, Any], requested_mode: str = "auto") -> tuple[bool, list[dict[str, Any]], str]:
    """Decide if we should resume from partial results or restart.

    Args:
        project: The project dict.
        requested_mode: 'auto', 'resume', or 'restart'.

    Returns:
        (resume_from_partial, resume_seed_sections, resolved_resume_mode)
    """
    ai_result_raw = project.get("ai_result")
    existing_sections = extract_resume_seed_sections(ai_result_raw)
    has_partial = bool(existing_sections)

    requested_mode = str(requested_mode or "auto").strip().lower()

    if requested_mode == "restart":
        return False, [], "restart"

    if requested_mode == "resume":
        return has_partial, existing_sections, "resume"

    # Auto mode: inspect durable phase/checkpoint state. This also recovers
    # legacy projects accidentally reset to ``draft`` by the old frontend.
    status = str(project.get("status") or "").strip().lower()
    suspicious_statuses = {"failed", "blocked", "cancel_requested", "render_failed"}
    generation_phase = project.get("generation_phase") if isinstance(project.get("generation_phase"), dict) else {}
    generation_status = str(generation_phase.get("status") or "").strip().lower()
    resume = project.get("resume") if isinstance(project.get("resume"), dict) else {}
    resume_ready = bool(resume.get("eligible")) or str(resume.get("checkpoint_status") or "") in {
        "checkpoint_ready",
        "resume_ready",
    }
    if has_partial and (
        status in suspicious_statuses
        or generation_status in {"failed", "blocked", "resume_ready", "interrupted"}
        or resume_ready
        or (status == "draft" and generation_status not in {"idle", "completed", "done"})
    ):
        return True, existing_sections, "auto"

    return False, [], "auto"
