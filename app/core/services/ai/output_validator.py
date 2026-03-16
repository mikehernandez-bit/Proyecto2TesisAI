"""Output validator for AI-generated content.

Validates and normalizes the ``aiResult`` structure returned from the
generation pipeline, preserving valid structured blocks and preventing raw
dict/list representations from leaking into the final document.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import Any

from app.core.services.ai.completeness_validator import strip_placeholder_text
from app.core.services.content_sanitizer import sanitize_text_block
from app.core.services.toc_detector import is_toc_path as _shared_is_toc_path

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Raised when aiResult fails structural validation."""


class OutputValidator:
    """Validates the ``aiResult.sections`` contract."""

    MIN_CONTENT_LENGTH = 20
    MAX_TABLE_BLOCKS = 2
    MAX_FIGURE_BLOCKS = 1
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
        "LOREM IPSUM",
        "[PENDIENTE]",
    )
    _ABBREV_LINE_RE = re.compile(r"^\s*([A-Z0-9]{2,})\s*(?:[:\-])\s*(.+?)\s*$", re.IGNORECASE)
    _ABBREV_PAREN_RE = re.compile(r"^\s*(.+?)\s*\(([\w]{2,})\)\s*$", re.IGNORECASE)
    _FIGURE_PREFIX_RE = re.compile(r"^\s*figura\s*[\w.-]*\s*[:.)-]*\s*", re.IGNORECASE)
    _DELIMITED_BLOCK_RE = re.compile(
        r"<<<(?:TABLE_JSON|FIGURE_JSON)\s*[\s\S]*?(?:TABLE_JSON|FIGURE_JSON)>>>",
        re.IGNORECASE,
    )
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
        return any(part in cls._INDEX_TITLES for part in parts if part)

    @classmethod
    def _is_abbreviations_path(cls, path: str) -> bool:
        normalized = cls._normalize_token(path)
        return "abreviaturas" in normalized

    @classmethod
    def _line_has_forbidden_phrase(cls, line: str) -> bool:
        normalized = cls._normalize_token(line).upper()
        if not normalized:
            return False
        return any(cls._normalize_token(phrase).upper() in normalized for phrase in cls._FORBIDDEN_PHRASES)

    @classmethod
    def _strip_structured_artifacts_from_text(cls, text: str) -> str:
        """Drop leaked JSON/Python repr blocks from plain-text content."""
        cleaned = cls._DELIMITED_BLOCK_RE.sub(" ", text)
        kept_lines: list[str] = []
        for line in cleaned.splitlines():
            stripped = line.strip()
            if not stripped:
                kept_lines.append("")
                continue
            if stripped in {"<<<TABLE_JSON", "TABLE_JSON>>>", "<<<FIGURE_JSON", "FIGURE_JSON>>>"}:
                continue
            if (
                stripped[:1] in "[{"
                and ("'tipo'" in stripped or '"tipo"' in stripped)
                and any(
                    token in stripped
                    for token in ("'parrafo'", '"parrafo"', "'tabla'", '"tabla"', "'figura'", '"figura"')
                )
            ):
                continue
            kept_lines.append(line)
        return "\n".join(kept_lines)

    @staticmethod
    def _collapse_blank_lines(lines: list[str]) -> list[str]:
        collapsed: list[str] = []
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
    def _normalize_abbreviations(cls, lines: list[str]) -> str:
        formatted: list[str] = []
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
            if len(sigla) < 2 or not meaning or sigla in seen_siglas:
                continue

            seen_siglas.add(sigla)
            formatted.append(f"{sigla}\t{meaning}")

        return "\n".join(formatted)

    @classmethod
    def _sanitize_text_content(cls, content: Any, *, path: str = "") -> str:
        """Normalize plain-text content for safe DOCX insertion."""
        raw = str(content or "")
        if not raw.strip():
            return ""
        if raw.strip() == cls._SKIP_SECTION_TOKEN:
            return ""
        if cls._is_index_path(path):
            return ""

        text = cls._strip_structured_artifacts_from_text(raw)
        if not text.strip():
            return ""

        text = strip_placeholder_text(text)
        text = re.sub(r"```[\s\S]*?```", " ", text)
        text = text.replace("```", " ")
        text = re.sub(r"^\s*#{1,6}\s*", "", text, flags=re.MULTILINE)
        text = text.replace("**", "").replace("__", "")
        text = text.replace("|", " ")

        cleaned_lines: list[str] = []
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

        return sanitize_text_block("\n".join(cleaned_lines))

    @staticmethod
    def _sanitize_table_cell(value: Any) -> str:
        return re.sub(r"\s+", " ", str(value or "")).strip()[:300]

    @classmethod
    def _normalize_orientation(cls, table: dict[str, Any], header_count: int) -> str:
        explicit = str(table.get("orientacion") or "auto").strip().lower()
        if explicit in {"horizontal", "landscape"}:
            return "landscape"
        if explicit in {"vertical", "portrait"}:
            return "portrait"
        return "landscape" if header_count > 5 else "portrait"

    @classmethod
    def _normalize_table_row(cls, row: Any, source_headers: list[str], header_count: int) -> list[str]:
        if isinstance(row, dict):
            cells = [
                cls._sanitize_table_cell(row.get(header, row.get(cls._sanitize_table_cell(header), "")))
                for header in source_headers
            ]
        elif isinstance(row, (list, tuple)):
            cells = [cls._sanitize_table_cell(cell) for cell in row[:header_count]]
        else:
            return []

        if len(cells) < header_count:
            cells.extend([""] * (header_count - len(cells)))
        if not any(cells):
            return []
        return cells[:header_count]

    @classmethod
    def _normalize_table_block(cls, item: dict[str, Any]) -> dict[str, Any] | None:
        headers_raw = item.get("encabezados")
        if not isinstance(headers_raw, list):
            headers_raw = item.get("columnas")
        if not isinstance(headers_raw, list):
            return None

        header_pairs: list[tuple[str, str]] = []
        for header in headers_raw:
            raw_header = str(header or "").strip()
            clean_header = cls._sanitize_table_cell(raw_header)
            if clean_header:
                header_pairs.append((raw_header or clean_header, clean_header))
        source_headers = [raw for raw, _ in header_pairs]
        headers = [clean for _, clean in header_pairs]
        if not headers:
            return None

        rows_raw = item.get("filas")
        if not isinstance(rows_raw, list):
            return None

        rows: list[list[str]] = []
        for row in rows_raw:
            normalized_row = cls._normalize_table_row(row, source_headers, len(headers))
            if normalized_row:
                rows.append(normalized_row)
        if not rows:
            return None

        normalized: dict[str, Any] = {
            "tipo": "tabla",
            "encabezados": headers,
            "filas": rows,
            "orientacion": cls._normalize_orientation(item, len(headers)),
        }

        identifier = str(item.get("id") or "").strip()
        if identifier:
            normalized["id"] = identifier

        title = cls._sanitize_text_content(item.get("titulo"))
        if title:
            normalized["titulo"] = title

        footnote = cls._sanitize_text_content(item.get("nota_pie") or item.get("notaPie"))
        if footnote:
            normalized["nota_pie"] = footnote

        return normalized

    @classmethod
    def _normalize_figure_block(cls, item: dict[str, Any]) -> dict[str, Any] | None:
        caption = cls._sanitize_text_content(item.get("caption") or item.get("titulo"))
        if not caption:
            return None

        normalized: dict[str, Any] = {
            "tipo": "figura",
            "caption": caption,
            "ruta_placeholder": str(item.get("ruta_placeholder") or "assets/placeholder_figura.png").strip()
            or "assets/placeholder_figura.png",
        }

        identifier = str(item.get("id") or "").strip()
        if identifier:
            normalized["id"] = identifier

        title = cls._sanitize_text_content(item.get("titulo"))
        if not title:
            title = cls._FIGURE_PREFIX_RE.sub("", caption).strip()
        if title:
            normalized["titulo"] = title

        return normalized

    @classmethod
    def _normalize_structured_content(cls, content: list[Any], *, path: str = "") -> list[dict[str, Any]] | str:
        normalized: list[dict[str, Any]] = []
        table_count = 0
        figure_count = 0

        for item in content:
            if isinstance(item, str):
                text = cls._sanitize_text_content(item, path=path)
                if text:
                    normalized.append({"tipo": "parrafo", "texto": text})
                continue

            if not isinstance(item, dict):
                continue

            block_type = cls._normalize_token(item.get("tipo"))
            if block_type == "parrafo":
                text = cls._sanitize_text_content(item.get("texto"), path=path)
                if text:
                    normalized.append({"tipo": "parrafo", "texto": text})
                continue

            if block_type == "tabla":
                if table_count >= cls.MAX_TABLE_BLOCKS:
                    continue
                table_block = cls._normalize_table_block(item)
                if table_block is not None:
                    normalized.append(table_block)
                    table_count += 1
                continue

            if block_type == "figura":
                if figure_count >= cls.MAX_FIGURE_BLOCKS:
                    continue
                figure_block = cls._normalize_figure_block(item)
                if figure_block is not None:
                    normalized.append(figure_block)
                    figure_count += 1
                continue

            fallback_text = cls._sanitize_text_content(
                item.get("texto") or item.get("caption") or item.get("titulo"),
                path=path,
            )
            if fallback_text:
                normalized.append({"tipo": "parrafo", "texto": fallback_text})

        return normalized if normalized else ""

    @classmethod
    def _visible_content_text(cls, content: Any) -> str:
        if isinstance(content, str):
            return content.strip()
        if not isinstance(content, list):
            return ""

        visible_parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                text = item.strip()
                if text:
                    visible_parts.append(text)
                continue
            if not isinstance(item, dict):
                continue
            block_type = cls._normalize_token(item.get("tipo"))
            if block_type == "parrafo":
                text = str(item.get("texto") or "").strip()
                if text:
                    visible_parts.append(text)
            elif block_type == "figura":
                caption = str(item.get("caption") or "").strip()
                if caption:
                    visible_parts.append(caption)
            elif block_type == "tabla":
                title = str(item.get("titulo") or "").strip()
                footnote = str(item.get("nota_pie") or "").strip()
                if title:
                    visible_parts.append(title)
                if footnote:
                    visible_parts.append(footnote)
        return " ".join(visible_parts)

    @classmethod
    def sanitize_content(cls, content: Any, *, path: str = "") -> Any:
        """Normalize AI content while preserving valid structured blocks."""
        if isinstance(content, list):
            return cls._normalize_structured_content(content, path=path)
        if isinstance(content, dict):
            return cls._normalize_structured_content([content], path=path)
        return cls._sanitize_text_content(content, path=path)

    def validate(self, ai_result: dict[str, Any]) -> dict[str, Any]:
        """Validate and return a normalized ``aiResult``."""
        if not isinstance(ai_result, dict):
            raise ValidationError("aiResult must be a dict")

        sections = ai_result.get("sections")
        if not isinstance(sections, list) or not sections:
            raise ValidationError("aiResult.sections must be a non-empty list")

        validated: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        warnings: list[str] = []

        for idx, section in enumerate(sections):
            if not isinstance(section, dict):
                warnings.append(f"Section at index {idx} is not a dict, skipped")
                continue

            section_id = section.get("sectionId") or section.get("section_id", "")
            path = section.get("path", "")
            content = section.get("content", "")

            if _shared_is_toc_path(path):
                warnings.append(f"Dropped non-generative TOC section '{section_id}' (path='{path}')")
                continue

            content = self.sanitize_content(content, path=path)
            visible_content = self._visible_content_text(content)

            if not section_id:
                section_id = f"sec-auto-{idx:04d}"
                warnings.append(f"Section at index {idx} missing sectionId, assigned '{section_id}'")

            if not path:
                warnings.append(f"Section '{section_id}' missing path")

            if not visible_content:
                warnings.append(f"Section '{section_id}' has empty content")
            elif len(visible_content) < self.MIN_CONTENT_LENGTH:
                warnings.append(f"Section '{section_id}' content is very short ({len(visible_content)} chars)")

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

        for warning in warnings:
            logger.warning("OutputValidator: %s", warning)

        if not validated:
            raise ValidationError("No valid sections after validation")

        return {"sections": validated}

    def build_ai_result(self, sections: list[dict[str, Any]]) -> dict[str, Any]:
        """Build and validate an aiResult from a list of sections."""
        return self.validate({"sections": sections})
