"""Output validator for AI-generated content.

Validates and normalises the ``aiResult`` structure returned from the
Gemini generation pipeline, ensuring it conforms to the contract
expected by the rest of GicaGen.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import Any, Dict, List

from app.core.services.ai.completeness_validator import strip_placeholder_text
from app.core.services.content_sanitizer import sanitize_text_block
from app.core.services.toc_detector import is_toc_path as _shared_is_toc_path

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Raised when aiResult fails structural validation."""


class OutputValidator:
    """Validates the ``aiResult.sections`` contract."""

    # Minimum content length to emit a quality warning (not a hard error)
    MIN_CONTENT_LENGTH = 20
    _INDEX_TITLES = frozenset(
        {
            "indice",
            "indice de contenido",
            "indice de tablas",
            "indice de figuras",
            "indice de abreviaturas",
            "tabla de contenido",
        }
    )
    _FORBIDDEN_PHRASES = (
        "FIGURA DE EJEMPLO",
        "TABLA DE EJEMPLO",
        "TITULO DEL PROYECTO",
        "TÍTULO DEL PROYECTO",
        "LOREM IPSUM",
        "[PENDIENTE]",
    )
    _ABBREV_LINE_RE = re.compile(
        r"^\s*([A-ZÁÉÍÓÚÜÑ0-9]{2,})\s*(?:[:\-—])\s*(.+?)\s*$",
        re.IGNORECASE,
    )
    _ABBREV_PAREN_RE = re.compile(r"^\s*(.+?)\s*\(([\wÁÉÍÓÚÜÑ]{2,})\)\s*$", re.IGNORECASE)
    _SKIP_SECTION_TOKEN = "<<SKIP_SECTION>>"

    @staticmethod
    def _normalize_token(value: Any) -> str:
        text = str(value or "").strip().lower()
        if not text:
            return ""
        ascii_only = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
        return " ".join(ascii_only.split())

    @classmethod
    def _is_index_path(cls, path: str) -> bool:
        parts = [cls._normalize_token(part) for part in str(path or "").split("/")]
        for part in parts:
            if not part:
                continue
            if part in cls._INDEX_TITLES:
                return True
        return False

    @classmethod
    def _is_abbreviations_path(cls, path: str) -> bool:
        normalized = cls._normalize_token(path)
        return "abreviaturas" in normalized

    @classmethod
    def _line_has_forbidden_phrase(cls, line: str) -> bool:
        normalized = cls._normalize_token(line).upper()
        if not normalized:
            return False
        for phrase in cls._FORBIDDEN_PHRASES:
            if cls._normalize_token(phrase).upper() in normalized:
                return True
        return False

    @staticmethod
    def _collapse_blank_lines(lines: List[str]) -> List[str]:
        collapsed: List[str] = []
        previous_blank = False
        for line in lines:
            is_blank = not line
            if is_blank:
                if previous_blank:
                    continue
                collapsed.append("")
                previous_blank = True
                continue
            collapsed.append(line)
            previous_blank = False

        while collapsed and collapsed[0] == "":
            collapsed.pop(0)
        while collapsed and collapsed[-1] == "":
            collapsed.pop()
        return collapsed

    @classmethod
    def _normalize_abbreviations(cls, lines: List[str]) -> str:
        formatted: List[str] = []
        seen_siglas: set[str] = set()

        for line in lines:
            raw = line.strip()
            if not raw:
                continue

            sigla = ""
            meaning = ""

            if "\t" in raw:
                left, right = raw.split("\t", 1)
                sigla = left.strip().upper()
                meaning = right.strip()
            else:
                match = cls._ABBREV_LINE_RE.match(raw)
                if match:
                    sigla = match.group(1).strip().upper()
                    meaning = match.group(2).strip()
                else:
                    match = cls._ABBREV_PAREN_RE.match(raw)
                    if match:
                        meaning = match.group(1).strip()
                        sigla = match.group(2).strip().upper()

            if not sigla or not meaning:
                continue

            sigla = re.sub(r"\s+", "", sigla)
            meaning = re.sub(r"\s+", " ", meaning).strip()
            if len(sigla) < 2 or not meaning:
                continue
            if sigla in seen_siglas:
                continue

            seen_siglas.add(sigla)
            formatted.append(f"{sigla}\t{meaning}")

        return "\n".join(formatted)

    @classmethod
    def sanitize_content(cls, content: Any, *, path: str = "") -> str:
        """Normalize AI content for safe DOCX insertion."""
        raw = str(content or "")
        if not raw.strip():
            return ""
        if raw.strip() == cls._SKIP_SECTION_TOKEN:
            return ""

        if cls._is_index_path(path):
            return ""

        # Strip placeholder patterns (safety net)
        text = strip_placeholder_text(raw)

        # Remove code fences and common markdown formatting.
        text = re.sub(r"```[\s\S]*?```", " ", text)
        text = text.replace("```", " ")
        text = re.sub(r"^\s*#{1,6}\s*", "", text, flags=re.MULTILINE)
        text = text.replace("**", "").replace("__", "")
        text = text.replace("|", " ")

        cleaned_lines: List[str] = []
        for line in text.splitlines():
            line = re.sub(r"^\s*[-*+]\s+", "", line)
            line = re.sub(r"^\s*\d+[.)]\s+", "", line)
            line = re.sub(r"[ \t]+", " ", line).strip()
            if cls._line_has_forbidden_phrase(line):
                continue
            cleaned_lines.append(line)

        cleaned_lines = cls._collapse_blank_lines(cleaned_lines)
        if not cleaned_lines:
            return ""

        if cls._is_abbreviations_path(path):
            normalized_abbr = cls._normalize_abbreviations(cleaned_lines)
            if normalized_abbr:
                return normalized_abbr

        result = "\n".join(cleaned_lines)
        # Strip any surviving leader-dot + page-number artefacts.
        return sanitize_text_block(result)

    def validate(self, ai_result: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and return a normalised ``aiResult``.

        Raises :class:`ValidationError` if required structure is missing.
        Logs warnings for quality issues (short content) but does not
        reject them.
        """
        if not isinstance(ai_result, dict):
            raise ValidationError("aiResult must be a dict")

        sections = ai_result.get("sections")
        if not isinstance(sections, list) or not sections:
            raise ValidationError("aiResult.sections must be a non-empty list")

        validated: List[Dict[str, Any]] = []
        seen_ids: set = set()
        warnings: List[str] = []

        for idx, section in enumerate(sections):
            if not isinstance(section, dict):
                warnings.append(f"Section at index {idx} is not a dict, skipped")
                continue

            section_id = section.get("sectionId") or section.get("section_id", "")
            path = section.get("path", "")
            content = section.get("content", "")

            # --- TOC defence: drop the section entirely ----------------
            if _shared_is_toc_path(path):
                warnings.append(f"Dropped non-generative TOC section '{section_id}' (path='{path}')")
                continue
            # -----------------------------------------------------------

            content = self.sanitize_content(content, path=path)

            # sectionId is required
            if not section_id:
                section_id = f"sec-auto-{idx:04d}"
                warnings.append(f"Section at index {idx} missing sectionId, assigned '{section_id}'")

            # path is required
            if not path:
                warnings.append(f"Section '{section_id}' missing path")

            # content must not be empty
            if not content or not content.strip():
                warnings.append(f"Section '{section_id}' has empty content")
            elif len(content.strip()) < self.MIN_CONTENT_LENGTH:
                warnings.append(f"Section '{section_id}' content is very short ({len(content.strip())} chars)")

            # Unique sectionId check
            if section_id in seen_ids:
                section_id = f"{section_id}-dup-{idx}"
                warnings.append(f"Duplicate sectionId at index {idx}, renamed")
            seen_ids.add(section_id)

            validated.append(
                {
                    "sectionId": section_id,
                    "path": path,
                    "content": content,
                }
            )

        if warnings:
            for w in warnings:
                logger.warning("OutputValidator: %s", w)

        if not validated:
            raise ValidationError("No valid sections after validation")

        return {"sections": validated}

    def build_ai_result(
        self,
        sections: List[Dict[str, str]],
    ) -> Dict[str, Any]:
        """Build and validate an aiResult from a list of section dicts.

        Each dict should have ``sectionId``, ``path``, ``content``.
        """
        raw = {"sections": sections}
        return self.validate(raw)
