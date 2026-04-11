"""Payload builders and data-adaptation helpers.

Extracted from router.py to separate data transformation from HTTP routing.
These functions build, adapt, and normalize payloads for GicaTesis rendering.
"""

from __future__ import annotations

from typing import Any
import json
import logging

import httpx

from app.core.config import settings
from app.core.services.ai.section_content_policy import (
    allows_structured_content,
)
from app.core.services.toc_detector import is_toc_path as _is_toc_path
from app.integrations.gicatesis.types import validate_render_payload
from app.core.services.maestria_payload_mapper import (
    is_maestria_format,
    map_maestria_values,
)

_logger = logging.getLogger(__name__)


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
        elif block_type in {"tabla", "figura"}:
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


def _strip_raw_structured_string(content: str) -> str:
    stripped = content.strip()
    if (
        stripped[:1] in "[{"
        and ("'tipo'" in stripped or '"tipo"' in stripped)
        and any(token in stripped for token in ("'parrafo'", '"parrafo"', "'tabla'", '"tabla"', "'figura'", '"figura"'))
    ):
        return ""

    kept_lines: list[str] = []
    for line in content.splitlines():
        raw = line.strip()
        if (
            raw[:1] in "[{"
            and ("'tipo'" in raw or '"tipo"' in raw)
            and any(token in raw for token in ("'parrafo'", '"parrafo"', "'tabla'", '"tabla"', "'figura'", '"figura"'))
        ):
            continue
        kept_lines.append(line)
    return "\n".join(kept_lines).strip()


def _apply_section_content_policy(path: str, content: Any) -> Any:
    if isinstance(content, str):
        return _strip_raw_structured_string(content)
    if not isinstance(content, list):
        return content
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

    # SPECIAL HANDLING FOR UNAC MAESTRÍA:
    if is_maestria_format(project):
        maestria_values = map_maestria_values(values)
        # Update only if not empty to prevent wiping existing good data
        for k, v in maestria_values.items():
            if v:
                values[k] = v

    # 3. Asegurar sincronización y prioridad del título
    # Priorizamos lo que hay en 'values' (que ya incluye vars) sobre el 'project.title' raíz
    title_from_values = str(values.get("titulo") or values.get("title") or values.get("tema") or "").strip()
    root_title = str(project.get("title") or "").strip()
    
    final_title = title_from_values or root_title
    
    if final_title:
        values["titulo"] = final_title
        values["title"] = final_title
        values["tema"] = final_title

    return values


def adapt_ai_result_for_gicatesis(ai_result: dict[str, Any] | None) -> dict[str, Any]:
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
        path = str(item.get("path") or "").strip()
        if not path:
            continue

        raw_content = item.get("content")
        canonical_id = item.get("sectionId")

        content = _apply_section_content_policy(path, raw_content)
        entry: dict[str, Any] = {
            "path": path,
            "content": content,
        }
        if canonical_id:
            entry["sectionId"] = canonical_id
        canonical_sections.append(entry)

    by_path: dict[str, dict[str, Any]] = {item["path"]: item for item in canonical_sections if item.get("path")}
    parent_paths_with_children: set[str] = set()
    for path in by_path:
        if "/" in path:
            continue
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


def build_render_payload(
    *,
    format_id: str,
    values: dict[str, Any],
    ai_result_raw: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build render payload for GicaTesis preserving canonical AI sections."""
    payload = {
        "formatId": format_id,
        "values": values,
        "mode": "simulation",
        "aiResult": ai_result_raw or {"sections": []},
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
            seed_sections.append({
                "path": path,
                "content": content
            })
    return seed_sections


def decide_resume_mode(
    project: dict[str, Any],
    requested_mode: str = "auto"
) -> tuple[bool, list[dict[str, Any]], str]:
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

    if requested_mode == "restart":
        return False, [], "restart"

    if requested_mode == "resume":
        return has_partial, existing_sections, "resume"

    # Auto mode: resume if we have partial sections and status warrants it
    status = str(project.get("status") or "").strip().lower()
    suspicious_statuses = {"failed", "blocked", "cancel_requested", "render_failed"}
    if has_partial and status in suspicious_statuses:
        return True, existing_sections, "resume"

    return False, [], "restart"
