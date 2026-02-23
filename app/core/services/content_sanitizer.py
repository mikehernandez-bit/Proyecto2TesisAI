"""Content Sanitizer — strips leader-dot + page-number patterns from text.

When AI models (or legacy JSON definitions) produce text like::

    ``ÍNDICE DE TABLAS ..... 28``
    ``I. PLANTEAMIENTO DEL PROBLEMA .............. 6``
    ``Tabla 1.1. Frecuencia de fallas ......... pag 8``

these artefacts must be removed because page numbering is handled
exclusively by Word fields (TOC ``\\o "1-3"``).

This module provides:

- :func:`strip_leader_page` — removes dot-leaders and trailing page numbers
  from a single line.
- :func:`has_leader_page_pattern` — predicate to detect the pattern.
- :func:`sanitize_text_block` — cleans an entire multi-line block.
"""

from __future__ import annotations

import re

# Matches patterns like:
#   "TÍTULO ..... 28"
#   "TÍTULO ............ pag 8"
#   "TÍTULO … pag. 12"
#   "TÍTULO          24"  (many spaces then a number)
#   "TÍTULO ... pag X"    (literal "pag X")
_LEADER_PAGE_RE = re.compile(
    r"(?:"
    r"[.\u2026]{3,}"        # 3+ dots or ellipsis chars
    r"|[ \t]{4,}"           # OR 4+ spaces/tabs (right-aligned page number)
    r")"
    r"\s*"
    r"(?:pag\.?\s*)?"       # optional "pag" / "pag."
    r"(?:\d+|X)"            # page number or literal "X"
    r"\s*$",
    re.IGNORECASE,
)

# Simpler pattern: just "pag X" or "pag 12" at the end of a line
_PAG_SUFFIX_RE = re.compile(
    r"\s+pag\.?\s+(?:\d+|X)\s*$",
    re.IGNORECASE,
)


def has_leader_page_pattern(text: str) -> bool:
    """Return ``True`` if *text* contains a leader-dot + page-number pattern."""
    if not text:
        return False
    for line in text.splitlines():
        if _LEADER_PAGE_RE.search(line) or _PAG_SUFFIX_RE.search(line):
            return True
    return False


def strip_leader_page(line: str) -> str:
    """Remove trailing leader-dots and page numbers from a single line.

    Returns the cleaned line.  If the entire line is just a page-number
    pattern (nothing left after stripping), returns an empty string.
    """
    cleaned = _LEADER_PAGE_RE.sub("", line)
    cleaned = _PAG_SUFFIX_RE.sub("", cleaned)
    return cleaned.rstrip()


def sanitize_text_block(text: str) -> str:
    """Clean an entire multi-line block, stripping leader+page patterns.

    Empty lines resulting from stripping are collapsed.
    """
    if not text:
        return ""

    cleaned_lines: list[str] = []
    for line in text.splitlines():
        cleaned = strip_leader_page(line)
        cleaned_lines.append(cleaned)

    # Collapse consecutive blank lines.
    result_lines: list[str] = []
    prev_blank = False
    for line in cleaned_lines:
        is_blank = not line.strip()
        if is_blank:
            if prev_blank:
                continue
            prev_blank = True
        else:
            prev_blank = False
        result_lines.append(line)

    # Strip leading/trailing blank lines.
    while result_lines and not result_lines[0].strip():
        result_lines.pop(0)
    while result_lines and not result_lines[-1].strip():
        result_lines.pop()

    return "\n".join(result_lines)
