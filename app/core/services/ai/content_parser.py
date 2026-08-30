"""Content parser for AI-generated structured blocks.

Extracts <<<TABLE_JSON ... TABLE_JSON>>>, <<<FIGURE_JSON ... FIGURE_JSON>>>,
and <<<FORMULA_JSON ... FORMULA_JSON>>> delimited blocks from AI text output
and converts them into structured content arrays compatible with GicaTesis
normalizer.

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
_FORMULA_BLOCK_RE = re.compile(
    r"<<<FORMULA_JSON\s*\n(.*?)\nFORMULA_JSON>>>",
    re.DOTALL,
)

# Combined pattern to split text around any delimited block
_ANY_BLOCK_RE = re.compile(
    r"(<<<(?:TABLE_JSON|FIGURE_JSON|FORMULA_JSON)\s*\n.*?\n(?:TABLE_JSON|FIGURE_JSON|FORMULA_JSON)>>>)",
    re.DOTALL,
)
_FENCE_LINE_RE = re.compile(r"^\s*```[\w-]*\s*$", re.MULTILINE)
_MARKER_TOKENS = {"●", "•", "â—", "x", "X", "✔", "✓", "■"}


def _strip_external_fences(raw: str) -> str:
    """Remove standalone markdown fence lines around structured blocks."""
    return _FENCE_LINE_RE.sub("", raw).strip()


# Bare keyword marker, con o sin los delimitadores <<< >>> (parcial o
# totalmente ausentes). El modelo a veces emite solo "FORMULA_JSON" (o
# TABLE_JSON/FIGURE_JSON) pegado a un bloque "{...}" sin la envoltura
# <<<...>>> esperada. _TABLE_BLOCK_RE/_FIGURE_BLOCK_RE/_FORMULA_BLOCK_RE no
# matchean ese caso y el JSON crudo se queda como texto visible.
_BARE_STRUCTURED_KEYWORD_RE = re.compile(
    r"<{0,3}\s*(?:TABLE_JSON|FIGURE_JSON|FORMULA_JSON)\s*>{0,3}",
    re.IGNORECASE,
)


def _strip_bare_structured_json_blocks(text: str) -> str:
    """Remove TABLE_JSON/FIGURE_JSON/FORMULA_JSON leaks that arrive without
    (or with malformed) ``<<<...>>>`` delimiters.

    Scans for a bare keyword immediately followed by a balanced ``{...}``
    object and drops that whole span -- regardless of whether the JSON is
    well-formed or matches any expected schema -- so raw JSON never leaks
    into the final document as visible prose.
    """
    result: list[str] = []
    pos = 0
    for match in _BARE_STRUCTURED_KEYWORD_RE.finditer(text):
        if match.start() < pos:
            continue
        brace_start = text.find("{", match.end())
        between = text[match.end():brace_start] if brace_start != -1 else ""
        if brace_start == -1 or between.strip():
            # No JSON object glued right after the keyword: this is not a
            # leaked structured block, leave it untouched.
            continue

        depth = 0
        end = None
        for idx in range(brace_start, len(text)):
            ch = text[idx]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = idx + 1
                    break
        if end is None:
            # Unbalanced braces: drop from the keyword onward rather than
            # leak a half-open JSON blob to the reader.
            end = len(text)

        trailing = text[end : end + 40]
        trailing_match = _BARE_STRUCTURED_KEYWORD_RE.match(trailing.lstrip())
        if trailing_match:
            end += (len(trailing) - len(trailing.lstrip())) + trailing_match.end()

        result.append(text[pos : match.start()])
        pos = end

    result.append(text[pos:])
    return "".join(result)


def _normalize_marker_value(value: Any) -> Any:
    if isinstance(value, str) and value.strip() in _MARKER_TOKENS:
        return "●"
    if isinstance(value, list):
        return [_normalize_marker_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalize_marker_value(item) for key, item in value.items()}
    return value


def _parse_json_block(raw: str, block_type: str) -> Optional[Dict[str, Any]]:
    """Try to parse a JSON block, returning None on failure."""
    try:
        obj = json.loads(raw.strip())
        if not isinstance(obj, dict):
            logger.warning("content_parser: %s block is not a dict, skipping", block_type)
            return None
        if "tipo" not in obj:
            obj["tipo"] = block_type
        normalized = _normalize_marker_value(obj)
        if isinstance(normalized, dict):
            return normalized
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

    raw_content = _strip_external_fences(raw_content)

    # Quick check: are there any well-formed <<<...>>> delimited blocks at all?
    if (
        "<<<TABLE_JSON" not in raw_content
        and "<<<FIGURE_JSON" not in raw_content
        and "<<<FORMULA_JSON" not in raw_content
    ):
        # No well-formed block, but the model may still have left a bare
        # keyword (e.g. "FORMULA_JSON" with no <<<...>>> at all) glued to a
        # raw "{...}" blob. Strip that before returning plain text, so it
        # never leaks into the document as visible JSON.
        return _strip_bare_structured_json_blocks(raw_content).strip()

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
                result.append(obj)
            continue

        # Check if this part is a FORMULA block
        formula_match = _FORMULA_BLOCK_RE.search(part)
        if formula_match:
            obj = _parse_json_block(formula_match.group(1), "formula")
            if obj:
                obj.setdefault("alineacion", "center")
                result.append(obj)
            continue

        # Plain text paragraph(s). Strip any bare (non-delimited) keyword +
        # JSON leak that may still be glued to otherwise-normal prose in
        # this segment before splitting into paragraph blocks.
        part_stripped = _strip_bare_structured_json_blocks(part_stripped).strip()
        for paragraph in part_stripped.split("\n\n"):
            text = paragraph.strip()
            if _FENCE_LINE_RE.fullmatch(text):
                continue
            if text:
                result.append({"tipo": "parrafo", "texto": text})

    if not result:
        return raw_content

    logger.info(
        "content_parser: extracted %d structured blocks (%d tables, %d figures, %d formulas, %d paragraphs)",
        len(result),
        sum(1 for r in result if r.get("tipo") == "tabla"),
        sum(1 for r in result if r.get("tipo") == "figura"),
        sum(1 for r in result if r.get("tipo") == "formula"),
        sum(1 for r in result if r.get("tipo") == "parrafo"),
    )
    return result
