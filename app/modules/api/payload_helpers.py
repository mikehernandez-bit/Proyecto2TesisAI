"""Payload builders and data-adaptation helpers.

Extracted from router.py to separate data transformation from HTTP routing.
These functions build, adapt, and normalize payloads for GicaTesis rendering.
"""

from __future__ import annotations

import logging
import unicodedata
from typing import Any

import httpx

from app.core.config import settings
from app.core.services.ai.content_parser import parse_ai_content
from app.core.services.ai.output_validator import OutputValidator
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
        return content
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
    ai_with_fallback = _build_generation_phase_fallback(ai_result_raw, generation_phase)
    adapted_ai_result = adapt_ai_result_for_gicatesis(ai_with_fallback, values=values)
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
            seed_sections.append({"path": path, "content": content})
    return seed_sections


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

    # Auto mode: resume if we have partial sections and status warrants it
    status = str(project.get("status") or "").strip().lower()
    suspicious_statuses = {"failed", "blocked", "cancel_requested", "render_failed"}
    if has_partial and status in suspicious_statuses:
        return True, existing_sections, "auto"

    return False, [], "auto"
