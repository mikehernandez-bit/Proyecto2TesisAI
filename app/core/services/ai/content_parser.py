"""Content parser for AI-generated structured blocks.

Extracts <<<TABLE_JSON ... TABLE_JSON>>> and <<<FIGURE_JSON ... FIGURE_JSON>>>
delimited blocks from AI text output and converts them into structured content
arrays compatible with GicaTesis normalizer.

If the AI output contains NO delimited blocks, it is returned as-is (plain string).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

_TABLE_BLOCK_RE = re.compile(
    r"<<<TABLE_JSON\s*\n(.*?)\nTABLE_JSON>>>",
    re.DOTALL,
)
_FIGURE_BLOCK_RE = re.compile(
    r"<<<FIGURE_JSON\s*\n(.*?)\nFIGURE_JSON>>>",
    re.DOTALL,
)

# Combined pattern to split text around any delimited block
_ANY_BLOCK_RE = re.compile(
    r"(<<<(?:TABLE_JSON|FIGURE_JSON)\s*\n.*?\n(?:TABLE_JSON|FIGURE_JSON)>>>)",
    re.DOTALL,
)


def _parse_json_block(raw: str, block_type: str) -> Optional[Dict[str, Any]]:
    """Try to parse a JSON block, returning None on failure."""
    try:
        obj = json.loads(raw.strip())
        if not isinstance(obj, dict):
            logger.warning("content_parser: %s block is not a dict, skipping", block_type)
            return None
        if "tipo" not in obj:
            obj["tipo"] = block_type
        return obj
    except json.JSONDecodeError as exc:
        logger.warning(
            "content_parser: failed to parse %s JSON block: %s",
            block_type,
            exc,
        )
        return None


def _determine_orientation(table: Dict[str, Any]) -> str:
    """Determine if a table needs landscape orientation.

    Returns ``"landscape"`` or ``"portrait"`` to match the values
    expected by the ``table`` renderer in GicaTesis.
    """
    explicit = (table.get("orientacion") or "auto").strip().lower()
    if explicit in ("horizontal", "landscape"):
        return "landscape"
    if explicit in ("vertical", "portrait"):
        return "portrait"
    # Auto-detect based on column count (encabezados is the canonical key)
    headers = table.get("encabezados") or table.get("columnas", [])
    if isinstance(headers, list) and len(headers) > 5:
        return "landscape"
    return "portrait"


def parse_ai_content(raw_content: str) -> Union[str, List[Dict[str, Any]]]:
    """Parse AI-generated text, extracting structured table/figure blocks.

    Returns:
        - ``str`` if the content has no delimited blocks (backward-compatible).
        - ``List[dict]`` if at least one block was found.  Each element is either
          ``{"tipo": "parrafo", "texto": "..."}`` or a table/figure dict.
    """
    if not isinstance(raw_content, str) or not raw_content.strip():
        return raw_content

    # Quick check: are there any delimited blocks at all?
    if "<<<TABLE_JSON" not in raw_content and "<<<FIGURE_JSON" not in raw_content:
        return raw_content  # plain text, return as-is

    parts = _ANY_BLOCK_RE.split(raw_content)
    result: List[Dict[str, Any]] = []

    for part in parts:
        part_stripped = part.strip()
        if not part_stripped:
            continue

        # Check if this part is a TABLE block
        table_match = _TABLE_BLOCK_RE.search(part)
        if table_match:
            obj = _parse_json_block(table_match.group(1), "tabla")
            if obj:
                obj["orientacion"] = _determine_orientation(obj)
                result.append(obj)
            continue

        # Check if this part is a FIGURE block
        figure_match = _FIGURE_BLOCK_RE.search(part)
        if figure_match:
            obj = _parse_json_block(figure_match.group(1), "figura")
            if obj:
                # Set placeholder path
                if "ruta_placeholder" not in obj:
                    obj["ruta_placeholder"] = "assets/placeholder_figura.png"
                result.append(obj)
            continue

        # Plain text paragraph(s)
        for paragraph in part_stripped.split("\n\n"):
            text = paragraph.strip()
            if text:
                result.append({"tipo": "parrafo", "texto": text})

    if not result:
        return raw_content

    logger.info(
        "content_parser: extracted %d structured blocks (%d tables, %d figures, %d paragraphs)",
        len(result),
        sum(1 for r in result if r.get("tipo") == "tabla"),
        sum(1 for r in result if r.get("tipo") == "figura"),
        sum(1 for r in result if r.get("tipo") == "parrafo"),
    )
    return result
