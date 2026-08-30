"""Output validator for AI-generated content.

Validates and normalizes the ``aiResult`` structure returned from the
generation pipeline, preserving valid structured blocks and preventing raw
dict/list representations from leaking into the final document.
"""

from __future__ import annotations

import logging
import re
import unicodedata
import hashlib
from typing import Any, cast

from app.core.services.ai.budget_table_builder import (
    extract_budget_plan_from_content,
    salvage_budget_plan_from_legacy_table,
    validate_budget_plan,
)
from app.core.services.ai.completeness_validator import strip_placeholder_text
from app.core.services.ai.schedule_table_builder import (
    extract_schedule_plan_from_content,
    salvage_schedule_plan_from_legacy_table,
    validate_schedule_plan,
)
from app.core.services.content_sanitizer import sanitize_text_block
from app.core.services.toc_detector import is_toc_path as _shared_is_toc_path

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Raised when aiResult fails structural validation."""


class OutputValidator:
    """Validates the ``aiResult.sections`` contract."""

    MIN_CONTENT_LENGTH = 20
    MAX_TABLE_BLOCKS = 2
    MAX_REALITY_PROBLEM_TABLE_BLOCKS = 0
    MAX_THEORETICAL_BASES_TABLE_BLOCKS = 0
    MAX_FIGURE_BLOCKS = 1
    MAX_PROBLEM_FIGURE_BLOCKS = 4
    MAX_THEORETICAL_BASES_FIGURE_BLOCKS = 4
    MAX_FORMULA_BLOCKS = 0
    MAX_THEORETICAL_BASES_FORMULA_BLOCKS = 4
    MAX_METHODOLOGICAL_DESIGN_FORMULA_BLOCKS = 1
    MIN_REALITY_PROBLEM_NARRATIVE_WORDS = 1300
    MAX_REALITY_PROBLEM_NARRATIVE_WORDS = 1450
    MIN_THEORETICAL_FIGURE_PREVIOUS_WORDS = 40
    MIN_THEORETICAL_FORMULA_PREVIOUS_WORDS = 20
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
        "PLACEHOLDER TECNICO CONTROLADO",
        "REEMPLAZAR POR LA FIGURA VALIDADA POR EL AUTOR",
        "ARQUITECTURA CONCEPTUAL APLICADA",
        "MAPA CONCEPTUAL DEL ESTUDIO",
        "PLACEHOLDER TECNICO",
        "FIGURA PENDIENTE DE ELABORACION PROPIA",
        "FLUJO METODOLOGICO DEL ESTUDIO SOBRE",
        "ETAPAS DEL METODO DE INVESTIGACION",
        "UBICACION GEOGRAFICA DE LA UNIDAD MINERA",
        "MATRIZ DE CONSISTENCIA METODOLOGICA",
        "TECNICAS E INSTRUMENTOS DE RECOLECCION DE DATOS",
        "FLUJO DE PROCESAMIENTO DE DATOS",
        "FIGURA 4.1",
        "FIGURA 4.2",
        "FIGURA 4.3",
        "FIGURA 4.4",
        "FIGURA 4.5",
        "FIGURA 4.6",
        "FIGURA 4.7",
        "TABLA 4.1",
        "TABLA 4.2",
        "TABLA 4.3",
    )
    _ABBREV_LINE_RE = re.compile(r"^\s*([A-Z0-9]{2,})\s*(?:[:\-])\s*(.+?)\s*$", re.IGNORECASE)
    _ABBREV_PAREN_RE = re.compile(r"^\s*(.+?)\s*\(([\w]{2,})\)\s*$", re.IGNORECASE)
    _FIGURE_PREFIX_RE = re.compile(r"^\s*figura\s*[\w.-]*\s*[:.)-]*\s*", re.IGNORECASE)
    _DELIMITED_BLOCK_RE = re.compile(
        r"<<<(?:TABLE_JSON|FIGURE_JSON|FORMULA_JSON)\s*[\s\S]*?"
        r"(?:TABLE_JSON|FIGURE_JSON|FORMULA_JSON)>>>",
        re.IGNORECASE,
    )
    # Bare keyword marker, con o sin los delimitadores <<< >>> (parcial o
    # totalmente ausentes). Usado como ancla para localizar y eliminar
    # bloques JSON que el modelo dejo sin envolver correctamente.
    _BARE_STRUCTURED_KEYWORD_RE = re.compile(
        r"<{0,3}\s*(?:TABLE_JSON|FIGURE_JSON|FORMULA_JSON)\s*>{0,3}",
        re.IGNORECASE,
    )
    _SKIP_SECTION_TOKEN = "<<SKIP_SECTION>>"
    _REALITY_PROBLEM_REQUIRED_PATTERNS = (
        ("85 %", re.compile(r"\b85\s*%", re.IGNORECASE)),
        ("90 %", re.compile(r"\b90\s*%", re.IGNORECASE)),
        ("5 %", re.compile(r"\b5\s*%", re.IGNORECASE)),
        ("75 %", re.compile(r"\b75\s*%", re.IGNORECASE)),
        ("Figura 1.1", re.compile(r"\bfigura\s*1\.1\b", re.IGNORECASE)),
        ("Figura 1.2", re.compile(r"\bfigura\s*1\.2\b", re.IGNORECASE)),
        ("Figura 1.3", re.compile(r"\bfigura\s*1\.3\b", re.IGNORECASE)),
        ("Figura 1.4", re.compile(r"\bfigura\s*1\.4\b", re.IGNORECASE)),
        ("SAE JA1011:2024", re.compile(r"\bSAE\s+JA1011\s*:?\s*2024\b", re.IGNORECASE)),
        ("ISO 14224", re.compile(r"\bISO\s+14224\b", re.IGNORECASE)),
        ("AMEF", re.compile(r"\bAMEF\b", re.IGNORECASE)),
        ("MTBF", re.compile(r"\bMTBF\b", re.IGNORECASE)),
        ("MTTR", re.compile(r"\bMTTR\b", re.IGNORECASE)),
        ("7.9", re.compile(r"\b7[\.,]9\b")),
        ("4.6", re.compile(r"\b4[\.,]6\b")),
    )
    _REALITY_PROBLEM_REQUIRED_NORMALIZED_TERMS = (
        "disponibilidad inherente",
        "plan de mantenimiento centrado en confiabilidad",
    )
    _REALITY_PROBLEM_REQUIRED_FIGURE_TITLES = (
        "Diagrama de Pareto de modos de falla en flota CAT 24M",
        "Analisis de Causa-Efecto de Baja Disponibilidad (Ishikawa)",
        "Matriz de Relevancia para el filtrado de alternativas de solucion",
        "Matriz de Priorizacion de soluciones factibles",
    )
    _REALITY_PROBLEM_GENERIC_PHRASES = (
        "estudios internacionales han demostrado",
        "diversos estudios han demostrado",
        "se ha demostrado que",
    )
    _CHAPTER_TWO_BACKGROUND_GENERIC_PHRASES = (
        "en chile, un estudio",
        "un estudio realizado por",
        "una investigacion publicada",
        "un proyecto desarrollado por",
        "una universidad analizo",
        "diversos estudios",
        "varias investigaciones",
    )
    _CHAPTER_FOUR_WORD_RANGES = (
        ("diseno metodologico", 250, 450),
        ("metodo de investigacion", 200, 380),
        ("poblacion y muestra", 0, 130),
        ("lugar de estudio", 0, 220),
        ("tecnicas e instrumentos", 200, 380),
        ("analisis y procesamiento de datos", 220, 380),
        ("aspectos eticos", 220, 420),
    )
    _JUSTIFICATION_REQUIRED_HEADINGS = (
        "1.4.1 Justificacion normativa",
        "1.4.2 Justificacion teorica",
        "1.4.3 Justificacion practica",
        "1.4.4 Justificacion metodologica",
        "1.4.5 Justificacion economica",
        "1.4.6 Justificacion social",
    )
    _DELIMITATIONS_REQUIRED_HEADINGS = (
        "1.5.1 Delimitacion teorica",
        "1.5.2 Delimitacion temporal",
        "1.5.3 Delimitacion espacial",
    )
    _WORD_RE = re.compile(r"\b[\wÁÉÍÓÚÜÑáéíóúüñ]+(?:[-'][\wÁÉÍÓÚÜÑáéíóúüñ]+)?\b", re.UNICODE)
    # Detects bare mathematical equations written as plain text (e.g. "MTBF = X / Y").
    # These are promoted to formula blocks so GicaTesis does not render them as
    # Heading 3 paragraphs and include them in the table of contents.
    _INLINE_FORMULA_RE = re.compile(r"^[A-ZÁÉÍÓÚ][A-Za-záéíóúñÑ\s]+=\s*[\w\s/()+\-*.áéíóúñ]+$")
    _SCHEDULE_PHASE_ROWS = [1, 5, 9, 13, 17, 21, 26, 30]
    _SCHEDULE_ACTIVITY_COUNTS = (3, 3, 3, 3, 3, 4, 3, 4)
    _SCHEDULE_LEGACY_RECOVERABLE_ERRORS = {
        "encabezados_invalidos",
        "anio_inconsistente",
        "fila_con_14_celdas",
        "fila_con_longitud_invalida",
        "numero_filas_invalido",
        "fila_0_invalida",
        "celdas_combinadas_invalidas",
        "celdas_fusionadas_invalidas",
        "filas_fase_invalidas",
        "meses_invalidos",
    }
    _SCHEDULE_ALLOWED_MONTH_WINDOWS = {
        1: (2, 3),
        2: (2, 4),
        3: (4, 6),
        4: (6, 7),
        5: (7, 8),
        6: (7, 10),
        7: (8, 11),
        8: (10, 12),
    }
    _SCHEDULE_PLACEHOLDER_TOKENS = (
        "fase x",
        "actividad x",
        "<anio>",
        "[fase",
        "[actividad",
        "nombre de fase",
        "nombre de actividad",
        "fase 1",
        "fase 2",
        "fase 3",
        "fase 4",
        "fase 5",
        "fase 6",
        "fase 7",
        "fase 8",
    )
    _COMMON_ACADEMIC_FORMAT_REPLACEMENTS = (
        (re.compile(r"\bFuente:\s*Nota\.\s*", re.IGNORECASE), "Nota. "),
        (re.compile(r"\btaxonomicos\b", re.IGNORECASE), "taxonómicos"),
        (re.compile(r"\btaxonomia\b", re.IGNORECASE), "taxonomía"),
        (re.compile(r"\banalisis\b", re.IGNORECASE), "análisis"),
        (re.compile(r"\bfisicos\b", re.IGNORECASE), "físicos"),
        (re.compile(r"\bingenieria\b", re.IGNORECASE), "ingeniería"),
    )

    @staticmethod
    def _normalize_token(value: Any) -> str:
        text = str(value or "").strip().lower()
        if not text:
            return ""
        ascii_only = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
        return " ".join(ascii_only.split())

    @staticmethod
    def _match_case(value: str, template: str) -> str:
        if not value:
            return template
        if value.isupper():
            return template.upper()
        if value[0].isupper():
            return template[:1].upper() + template[1:]
        return template

    @classmethod
    def _fix_common_academic_formatting(cls, text: str) -> str:
        fixed = text
        for pattern, replacement in cls._COMMON_ACADEMIC_FORMAT_REPLACEMENTS:
            fixed = pattern.sub(lambda match: cls._match_case(match.group(0), replacement), fixed)
        return fixed

    @classmethod
    def _is_index_path(cls, path: str) -> bool:
        parts = [cls._normalize_token(part) for part in str(path or "").split("/")]
        return any(part in cls._INDEX_TITLES for part in parts if part)

    @classmethod
    def _is_abbreviations_path(cls, path: str) -> bool:
        normalized = cls._normalize_token(path)
        return "abreviaturas" in normalized

    @classmethod
    def _is_chapter_two_path(cls, path: str) -> bool:
        normalized = cls._normalize_token(path)
        return "marco teorico" in normalized

    @classmethod
    def _is_theoretical_bases_path(cls, path: str) -> bool:
        normalized = cls._normalize_token(path)
        return "marco teorico" in normalized and "bases teoricas" in normalized

    @classmethod
    def _is_backgrounds_path(cls, path: str) -> bool:
        normalized = cls._normalize_token(path)
        return "marco teorico" in normalized and "antecedentes" in normalized

    @classmethod
    def _is_basic_terms_path(cls, path: str) -> bool:
        normalized = cls._normalize_token(path)
        return "marco teorico" in normalized and "definicion de terminos" in normalized

    @classmethod
    def _is_chapter_two_text_only_path(cls, path: str) -> bool:
        normalized = cls._normalize_token(path)
        if "marco teorico" not in normalized:
            return False
        text_only_markers = (
            "antecedentes",
            "marco conceptual",
            "definicion de terminos basicos",
            "definicion de terminos",
        )
        return any(marker in normalized for marker in text_only_markers)

    @classmethod
    def _is_chapter_three_hypotheses_path(cls, path: str) -> bool:
        normalized = cls._normalize_token(path)
        return "hipotesis y variables" in normalized and "3.1 hipotesis" in normalized

    @classmethod
    def _is_operationalization_path(cls, path: str) -> bool:
        normalized = cls._normalize_token(path)
        if "operacionalizacion" not in normalized:
            return False
        if "hipotesis y variables" in normalized:
            return True
        return bool(re.search(r"\b3\.2\b", normalized))

    @classmethod
    def _is_chapter_four_section_path(cls, path: str) -> bool:
        normalized = cls._normalize_token(path)
        if "metodologia" not in normalized:
            return False
        markers = (
            "diseno metodologico",
            "metodo de investigacion",
            "poblacion y muestra",
            "lugar de estudio",
            "tecnicas e instrumentos",
            "analisis y procesamiento de datos",
            "aspectos eticos",
        )
        return any(marker in normalized for marker in markers)

    @classmethod
    def _is_schedule_path(cls, path: str) -> bool:
        normalized = cls._normalize_token(path)
        return "cronograma de actividades" in normalized

    @classmethod
    def _is_budget_path(cls, path: str) -> bool:
        normalized = cls._normalize_token(path)
        return "presupuesto" in normalized

    @classmethod
    def _is_chapter_four_design_path(cls, path: str) -> bool:
        normalized = cls._normalize_token(path)
        return "metodologia" in normalized and "diseno metodologico" in normalized

    @classmethod
    def _chapter_four_word_range_for_path(cls, path: str) -> tuple[int, int] | None:
        if not cls._is_chapter_four_section_path(path):
            return None
        normalized = cls._normalize_token(path)
        for marker, min_words, max_words in cls._CHAPTER_FOUR_WORD_RANGES:
            if marker in normalized:
                return min_words, max_words
        return None

    @classmethod
    def _is_reality_problem_path(cls, path: str) -> bool:
        normalized = cls._normalize_token(path)
        return "planteamiento del problema" in normalized and "realidad problematica" in normalized

    @classmethod
    def _is_justification_path(cls, path: str) -> bool:
        normalized = cls._normalize_token(path)
        return "planteamiento del problema" in normalized and "justificacion" in normalized

    @classmethod
    def _is_delimitations_path(cls, path: str) -> bool:
        normalized = cls._normalize_token(path)
        return "planteamiento del problema" in normalized and "delimitaciones" in normalized

    @classmethod
    def _max_figure_blocks_for_path(cls, path: str) -> int:
        if cls._is_schedule_path(path) or cls._is_budget_path(path):
            return 0
        if cls._is_operationalization_path(path):
            return 0
        if (
            cls._is_chapter_two_text_only_path(path)
            or cls._is_chapter_three_hypotheses_path(path)
            or cls._is_chapter_four_section_path(path)
        ):
            return 0
        if cls._is_theoretical_bases_path(path):
            return cls.MAX_THEORETICAL_BASES_FIGURE_BLOCKS
        if cls._is_reality_problem_path(path):
            return cls.MAX_PROBLEM_FIGURE_BLOCKS
        return cls.MAX_FIGURE_BLOCKS

    @classmethod
    def _max_table_blocks_for_path(cls, path: str) -> int:
        if cls._is_schedule_path(path):
            return 1
        if cls._is_budget_path(path):
            return 1
        if cls._is_operationalization_path(path):
            return 0
        if cls._is_chapter_three_hypotheses_path(path):
            return 0
        if cls._is_chapter_four_section_path(path):
            return 0
        if cls._is_chapter_two_path(path):
            return cls.MAX_THEORETICAL_BASES_TABLE_BLOCKS
        if cls._is_reality_problem_path(path):
            return cls.MAX_REALITY_PROBLEM_TABLE_BLOCKS
        return cls.MAX_TABLE_BLOCKS

    @classmethod
    def _max_formula_blocks_for_path(cls, path: str) -> int:
        if cls._is_schedule_path(path) or cls._is_budget_path(path):
            return 0
        if cls._is_operationalization_path(path):
            return 0
        if cls._is_theoretical_bases_path(path):
            return cls.MAX_THEORETICAL_BASES_FORMULA_BLOCKS
        if cls._is_chapter_four_design_path(path):
            return cls.MAX_METHODOLOGICAL_DESIGN_FORMULA_BLOCKS
        return cls.MAX_FORMULA_BLOCKS

    @classmethod
    def _line_has_forbidden_phrase(cls, line: str) -> bool:
        normalized = cls._normalize_token(line).upper()
        if not normalized:
            return False
        return any(cls._normalize_token(phrase).upper() in normalized for phrase in cls._FORBIDDEN_PHRASES)

    @classmethod
    def _strip_bare_structured_json_blocks(cls, text: str) -> str:
        """Remove TABLE_JSON/FIGURE_JSON/FORMULA_JSON leaks that reach the
        visible text without well-formed ``<<<...>>>`` delimiters.

        ``_DELIMITED_BLOCK_RE`` only matches a complete ``<<<KEYWORD ...
        KEYWORD>>>`` pair. When the model drops the delimiters (emits just
        the bare keyword, e.g. "FORMULA_JSON" followed directly by "{...}")
        that regex never fires and the raw JSON leaks straight into the
        document as prose. This scans for a bare keyword immediately
        followed by a balanced ``{...}`` object -- regardless of whether it
        parses as valid JSON or contains a "tipo" key -- and drops that
        whole span.
        """
        result: list[str] = []
        pos = 0
        for match in cls._BARE_STRUCTURED_KEYWORD_RE.finditer(text):
            if match.start() < pos:
                continue
            brace_start = text.find("{", match.end())
            between = text[match.end():brace_start] if brace_start != -1 else ""
            if brace_start == -1 or between.strip():
                # No JSON object glued right after the keyword: leave this
                # occurrence untouched, it is not a leaked structured block.
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
                # Unbalanced braces: still drop from the keyword onward
                # rather than leak a half-open JSON blob to the reader.
                end = len(text)

            trailing = text[end : end + 40]
            trailing_match = cls._BARE_STRUCTURED_KEYWORD_RE.match(trailing.lstrip())
            if trailing_match:
                end += (len(trailing) - len(trailing.lstrip())) + trailing_match.end()

            result.append(text[pos : match.start()])
            pos = end

        result.append(text[pos:])
        return "".join(result)

    @classmethod
    def _strip_structured_artifacts_from_text(cls, text: str) -> str:
        """Drop leaked JSON/Python repr blocks from plain-text content."""
        cleaned = cls._DELIMITED_BLOCK_RE.sub(" ", text)
        cleaned = cls._strip_bare_structured_json_blocks(cleaned)
        kept_lines: list[str] = []
        for line in cleaned.splitlines():
            stripped = line.strip()
            if not stripped:
                kept_lines.append("")
                continue
            if stripped in {
                "<<<TABLE_JSON",
                "TABLE_JSON>>>",
                "<<<FIGURE_JSON",
                "FIGURE_JSON>>>",
                "<<<FORMULA_JSON",
                "FORMULA_JSON>>>",
            }:
                continue
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
    def _strip_section_generic_closures(cls, lines: list[str], *, path: str) -> list[str]:
        normalized_path = cls._normalize_token(path)
        closure_markers: tuple[str, ...] = ()
        if cls._is_chapter_two_path(path) and "antecedentes" in normalized_path:
            closure_markers = (
                "los antecedentes revisados confirman",
                "en sintesis, los antecedentes",
                "en conjunto, los antecedentes",
                "a continuacion, se presentan los estudios",
            )
        elif cls._is_chapter_two_path(path) and "definicion de terminos" in normalized_path:
            closure_markers = (
                "estos terminos proporcionan",
                "estos terminos constituyen",
                "en conjunto, estos terminos",
                "en conjunto, estas definiciones",
                "este glosario proporciona",
                "los terminos definidos permiten",
                "los terminos anteriores permiten",
            )
        elif cls._is_chapter_four_section_path(path):
            closure_markers = (
                "la combinacion de estos elementos asegura",
                "la combinacion de estos elementos metodologicos asegura",
                "el metodo seleccionado asegura",
                "este enfoque garantiza",
                "este enfoque garantiza la fiabilidad",
                "la combinacion de estas tecnicas e instrumentos asegura",
                "la tabla presentada sintetiza",
                "de esta manera se garantiza",
                "de esta manera, se garantiza",
            )

        if not closure_markers:
            return lines

        kept: list[str] = []
        for line in lines:
            normalized_line = cls._normalize_token(line)
            if any(marker in normalized_line for marker in closure_markers):
                continue
            kept.append(line)
        return kept

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
        text = cls._fix_common_academic_formatting(text)
        text = re.sub(r"```[\s\S]*?```", " ", text)
        text = text.replace("```", " ")
        text = re.sub(r"^\s*#{1,6}\s*", "", text, flags=re.MULTILINE)
        text = text.replace("**", "").replace("__", "").replace("*", "")
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
        cleaned_lines = cls._strip_section_generic_closures(cleaned_lines, path=path)
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
    def _normalize_orientation(cls, table: dict[str, Any], header_count: int, *, path: str = "") -> str:
        # Keep operationalization tables in portrait to avoid forced page/section
        # breaks between Tabla 3.1 and 3.2 in project renders.
        if cls._is_operationalization_path(path) or cls._is_operationalization_table(table):
            return "portrait"
        explicit = str(table.get("orientacion") or "auto").strip().lower()
        if explicit in {"horizontal", "landscape"}:
            return "landscape"
        if explicit in {"vertical", "portrait"}:
            return "portrait"
        return "landscape" if header_count > 5 else "portrait"

    @classmethod
    def _is_operationalization_table(cls, table: dict[str, Any]) -> bool:
        title_tokens = " ".join(
            cls._normalize_token(value)
            for value in (
                table.get("titulo"),
                table.get("caption"),
                table.get("id"),
            )
            if value not in (None, "")
        )
        if "operacionalizacion" in title_tokens:
            return True
        if "tabla 3.1" in title_tokens or "tabla 3.2" in title_tokens:
            return True
        return False

    @classmethod
    def _normalize_table_row(
        cls,
        row: Any,
        source_headers: list[str],
        header_count: int,
        *,
        preserve_schedule_shape: bool = False,
    ) -> list[str]:
        if isinstance(row, dict):
            cells = [
                cls._sanitize_table_cell(row.get(header, row.get(cls._sanitize_table_cell(header), "")))
                for header in source_headers
            ]
        elif isinstance(row, (list, tuple)):
            if preserve_schedule_shape:
                cells = [cls._sanitize_table_cell(cell) for cell in row]
            else:
                cells = [cls._sanitize_table_cell(cell) for cell in row[:header_count]]
        else:
            return []

        if len(cells) < header_count:
            cells.extend([""] * (header_count - len(cells)))
        if not any(cells) and not preserve_schedule_shape:
            return []
        return cells if preserve_schedule_shape else cells[:header_count]

    @classmethod
    def _normalize_table_block(cls, item: dict[str, Any], *, path: str = "") -> dict[str, Any] | None:
        headers_raw = item.get("encabezados")
        if not isinstance(headers_raw, list):
            headers_raw = item.get("columnas")
        if not isinstance(headers_raw, list):
            return None

        preserve_sparse_headers = cls._is_schedule_path(path) or (
            cls._normalize_token(item.get("subtipo")) == "cronograma_actividades"
        )

        if preserve_sparse_headers:
            source_headers = [str(header or "").strip() for header in headers_raw]
            headers = [cls._sanitize_table_cell(header) for header in source_headers]
            if not any(headers):
                return None
        else:
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
            normalized_row = cls._normalize_table_row(
                row,
                source_headers,
                len(headers),
                preserve_schedule_shape=preserve_sparse_headers,
            )
            if normalized_row:
                rows.append(normalized_row)
        if not rows:
            return None

        normalized: dict[str, Any] = {
            "tipo": "tabla",
            "encabezados": headers,
            "filas": rows,
            "orientacion": cls._normalize_orientation(item, len(headers), path=path),
        }

        identifier = str(item.get("id") or "").strip()
        if identifier:
            normalized["id"] = identifier

        title = cls._sanitize_text_content(item.get("titulo"), path=path)
        if title:
            normalized["titulo"] = title

        footnote = cls._sanitize_text_content(item.get("nota_pie") or item.get("notaPie"), path=path)
        if footnote:
            normalized["nota_pie"] = footnote

        for extra_key in (
            "subtipo",
            "anio",
            "meses",
            "titulo_proyecto",
            "simbolo_marca",
            "filas_fase",
            "filas_categoria",
            "fila_total",
            "celdas_combinadas",
            "celdas_fusionadas",
            "estilos",
            "estilo",
        ):
            extra_value = item.get(extra_key)
            if extra_value not in (None, "", [], {}):
                normalized[extra_key] = extra_value

        return normalized

    @classmethod
    def _normalize_figure_block(cls, item: dict[str, Any], *, path: str = "") -> dict[str, Any] | None:
        caption = cls._sanitize_text_content(item.get("caption") or item.get("titulo"), path=path)
        if not caption:
            return None

        normalized: dict[str, Any] = {
            "tipo": "figura",
            "caption": caption,
        }
        image_path = str(item.get("ruta_placeholder") or item.get("image_path") or "").strip()
        if image_path:
            normalized["ruta_placeholder"] = image_path
        diagram_type = str(item.get("diagram_type") or "").strip()
        if diagram_type:
            normalized["diagram_type"] = diagram_type
            normalized["diagram_data"] = item.get("diagram_data") if isinstance(item.get("diagram_data"), dict) else {}
            normalized["numbered"] = bool(item.get("numbered", True))
            if "show_caption" in item:
                normalized["show_caption"] = bool(item.get("show_caption"))
            if "include_in_index" in item:
                normalized["include_in_index"] = bool(item.get("include_in_index"))
        if not image_path and not diagram_type:
            # A caption alone is not a renderable figure. Provider repairs can
            # echo figure prose as a block; keeping it here only postpones the
            # failure until GicaTesis validates the payload.
            return None

        identifier = str(item.get("id") or "").strip()
        if identifier:
            normalized["id"] = identifier

        title = cls._sanitize_text_content(item.get("titulo"), path=path)
        if not title:
            title = cls._FIGURE_PREFIX_RE.sub("", caption).strip()
        if title:
            normalized["titulo"] = title

        note = cls._sanitize_text_content(item.get("nota") or item.get("note"), path=path)
        if note:
            normalized["nota"] = note
            note_color = str(item.get("nota_color") or item.get("note_color") or "").strip()
            if note_color:
                normalized["nota_color"] = note_color

        source = cls._sanitize_text_content(item.get("fuente") or item.get("source"), path=path)
        if source:
            normalized["fuente"] = source

        placeholder_text = cls._sanitize_text_content(
            item.get("placeholder_text") or item.get("texto_placeholder"),
            path=path,
        )
        if placeholder_text:
            normalized["placeholder_text"] = placeholder_text

        return normalized

    @classmethod
    def _canonical_formula_latex(cls, text: str, latex: str) -> str:
        if latex:
            return latex
        normalized = cls._normalize_token(text)
        if normalized.startswith("disponibilidad inherente =") or normalized.startswith("ai ="):
            return r"A_i = \frac{MTBF}{MTBF + MTTR}"
        if normalized.startswith("disponibilidad ="):
            return r"Disponibilidad = \frac{TO}{TO + TIM}"
        if normalized.startswith("mtbf ="):
            return r"MTBF = \frac{T_o}{N_f}"
        if normalized.startswith("mttr ="):
            return r"MTTR = \frac{T_r}{N_i}"
        if normalized.startswith("r(t) =") and ("lambda" in normalized or "λ" in text):
            return r"R(t) = e^{-\lambda t}"
        if normalized.startswith("lambda =") or normalized.startswith("λ ="):
            return r"\lambda = \frac{1}{MTBF}"
        if normalized.startswith("m(t) =") and ("mu" in normalized or "μ" in text):
            return r"M(t) = 1 - e^{-\mu t}"
        if normalized == "m o1 x o2":
            return r"M O_1 X O_2"
        return ""

    @classmethod
    def _normalize_formula_block(cls, item: dict[str, Any], *, path: str = "") -> dict[str, Any] | None:
        text = cls._sanitize_text_content(item.get("texto") or item.get("text"), path=path)
        latex = cls._sanitize_text_content(item.get("latex"), path=path)
        if not text and not latex:
            return None
        latex = cls._canonical_formula_latex(text, latex)
        if not latex:
            raise ValidationError(f"Formula ambigua o no convertible en '{path}': {text[:100]}")

        normalized: dict[str, Any] = {
            "tipo": "formula",
            "alineacion": str(item.get("alineacion") or item.get("alignment") or "center").strip().lower() or "center",
        }
        if text:
            normalized["texto"] = text
        normalized["latex"] = latex

        number = cls._sanitize_text_content(item.get("numero") or item.get("number"), path=path)
        if number:
            normalized["numero"] = number

        identifier = str(item.get("id") or "").strip()
        normalized["id"] = identifier or "formula-" + hashlib.sha1(latex.encode("utf-8")).hexdigest()[:12]

        if normalized["alineacion"] not in {"center", "left", "right"}:
            normalized["alineacion"] = "center"
        return normalized

    @classmethod
    def _previous_kept_paragraph_word_count(cls, normalized: list[dict[str, Any]]) -> int:
        if not normalized:
            return 0
        previous = normalized[-1]
        if cls._normalize_token(previous.get("tipo")) != "parrafo":
            return 0
        return cls._word_count(str(previous.get("texto") or ""))

    @classmethod
    def _can_keep_theoretical_figure(cls, normalized: list[dict[str, Any]], *, path: str) -> bool:
        if not cls._is_theoretical_bases_path(path):
            return True
        return cls._previous_kept_paragraph_word_count(normalized) >= cls.MIN_THEORETICAL_FIGURE_PREVIOUS_WORDS

    @classmethod
    def _can_keep_theoretical_formula(cls, normalized: list[dict[str, Any]], *, path: str) -> bool:
        if not cls._is_theoretical_bases_path(path):
            return True
        return cls._previous_kept_paragraph_word_count(normalized) >= cls.MIN_THEORETICAL_FORMULA_PREVIOUS_WORDS

    @classmethod
    def _normalize_structured_content(cls, content: list[Any], *, path: str = "") -> list[dict[str, Any]] | str:
        normalized: list[dict[str, Any]] = []
        table_count = 0
        figure_count = 0
        formula_count = 0
        max_table_blocks = cls._max_table_blocks_for_path(path)
        max_figure_blocks = cls._max_figure_blocks_for_path(path)
        max_formula_blocks = cls._max_formula_blocks_for_path(path)

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
                    # Fallback guard: if this paragraph looks like a bare inline
                    # formula (single line, "X = Y / Z" pattern) in a theoretical
                    # bases section, promote it to a formula block so GicaTesis
                    # does not render it as Heading 3 / include it in the TOC.
                    single_line = "\n" not in text
                    is_theoretical = cls._is_theoretical_bases_path(path)
                    if (
                        single_line
                        and is_theoretical
                        and cls._INLINE_FORMULA_RE.match(text.strip())
                        and formula_count < max_formula_blocks
                    ):
                        promoted = {"tipo": "formula", "texto": text.strip(), "alineacion": "center"}
                        if cls._can_keep_theoretical_formula(normalized, path=path):
                            normalized.append(promoted)
                            formula_count += 1
                            logger.debug(
                                "output_validator: promoted inline formula to formula block in '%s': %r",
                                path,
                                text[:80],
                            )
                    else:
                        normalized.append({"tipo": "parrafo", "texto": text})
                continue

            if block_type == "tabla":
                if table_count >= max_table_blocks:
                    continue
                table_block = cls._normalize_table_block(item, path=path)
                if table_block is not None:
                    normalized.append(table_block)
                    table_count += 1
                continue

            if block_type == "figura":
                if figure_count >= max_figure_blocks:
                    continue
                figure_block = cls._normalize_figure_block(item, path=path)
                if figure_block is not None:
                    if not cls._can_keep_theoretical_figure(normalized, path=path):
                        continue
                    normalized.append(figure_block)
                    figure_count += 1
                continue

            if block_type == "formula":
                if formula_count >= max_formula_blocks:
                    continue
                formula_block = cls._normalize_formula_block(item, path=path)
                if formula_block is not None:
                    if not cls._can_keep_theoretical_formula(normalized, path=path):
                        continue
                    normalized.append(formula_block)
                    formula_count += 1
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
            elif block_type == "formula":
                formula_text = str(item.get("texto") or item.get("latex") or "").strip()
                number = str(item.get("numero") or "").strip()
                if formula_text:
                    visible_parts.append(formula_text)
                if number:
                    visible_parts.append(number)
        return " ".join(visible_parts)

    @classmethod
    def _paragraph_blocks(cls, content: Any) -> list[dict[str, Any]]:
        if isinstance(content, str):
            text = content.strip()
            return [{"tipo": "parrafo", "texto": text}] if text else []
        if not isinstance(content, list):
            return []
        return [
            item
            for item in content
            if isinstance(item, dict)
            and cls._normalize_token(item.get("tipo")) == "parrafo"
            and str(item.get("texto") or "").strip()
        ]

    @classmethod
    def _narrative_text(cls, content: Any) -> str:
        return "\n".join(str(block.get("texto") or "").strip() for block in cls._paragraph_blocks(content))

    @classmethod
    def _word_count(cls, text: str) -> int:
        return len(cls._WORD_RE.findall(text))

    @classmethod
    def _figure_blocks(cls, content: Any) -> list[dict[str, Any]]:
        if not isinstance(content, list):
            return []
        return [
            item for item in content if isinstance(item, dict) and cls._normalize_token(item.get("tipo")) == "figura"
        ]

    @classmethod
    def _table_blocks(cls, content: Any) -> list[dict[str, Any]]:
        if not isinstance(content, list):
            return []
        return [
            item for item in content if isinstance(item, dict) and cls._normalize_token(item.get("tipo")) == "tabla"
        ]

    @classmethod
    def _schedule_row_text(cls, row: Any) -> str:
        if not isinstance(row, list) or not row:
            return ""
        return str(row[0] or "").strip()

    @classmethod
    def _schedule_mark_positions(cls, row: Any) -> list[int]:
        if not isinstance(row, list):
            return []
        marks: list[int] = []
        for month_index, cell in enumerate(row[1:13], start=1):
            if str(cell or "").strip():
                marks.append(month_index)
        return marks

    @classmethod
    def _schedule_has_placeholder(cls, text: str) -> bool:
        normalized = cls._normalize_token(text)
        if not normalized:
            return False
        return any(token in normalized for token in cls._SCHEDULE_PLACEHOLDER_TOKENS)

    @classmethod
    def _schedule_expected_month_row(cls) -> list[str]:
        return ["", "Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Set", "Oct", "Nov", "Dic"]

    @classmethod
    def _schedule_header_errors(cls, table: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        headers = table.get("encabezados")
        if not isinstance(headers, list) or len(headers) != 13:
            return ["encabezados_invalidos"]

        if cls._normalize_token(headers[0]) != "fases y actividades":
            errors.append("encabezados_invalidos")

        header_year = str(headers[1] or "").strip()
        if not re.fullmatch(r"\d{4}", header_year):
            errors.append("encabezados_invalidos")

        if any(str(value or "").strip() for value in headers[2:]):
            errors.append("encabezados_invalidos")

        declared_year = str(table.get("anio") or "").strip()
        if declared_year and declared_year != header_year:
            errors.append("anio_inconsistente")
        elif not declared_year:
            errors.append("anio_inconsistente")

        return list(dict.fromkeys(errors))

    @classmethod
    def _schedule_row_length_errors(cls, rows: Any) -> list[str]:
        if not isinstance(rows, list):
            return ["filas_no_list"]
        length_errors: list[str] = []
        for row in rows:
            if not isinstance(row, list):
                length_errors.append("fila_con_longitud_invalida")
                continue
            if len(row) == 14:
                length_errors.append("fila_con_14_celdas")
            elif len(row) != 13:
                length_errors.append("fila_con_longitud_invalida")
        return list(dict.fromkeys(length_errors))

    @classmethod
    def _schedule_merge_errors(cls, table: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        year_value = str(table.get("anio") or "").strip()
        combined_raw = table.get("celdas_combinadas")
        fused_raw = table.get("celdas_fusionadas")
        if not isinstance(combined_raw, list) or not combined_raw:
            errors.append("celdas_combinadas_invalidas")
        if not isinstance(fused_raw, list) or not fused_raw:
            errors.append("celdas_fusionadas_invalidas")
        if errors:
            return errors
        combined = cast(list[Any], combined_raw)
        fused = cast(list[Any], fused_raw)

        has_year_combined = any(
            isinstance(item, dict)
            and item.get("fila") == -1
            and item.get("col_inicio") == 1
            and item.get("col_fin") == 12
            and str(item.get("texto") or "").strip() == year_value
            for item in combined
        )
        if not has_year_combined:
            errors.append("celdas_combinadas_invalidas")

        has_left_header_fusion = any(
            isinstance(item, dict)
            and item.get("fila") == -1
            and item.get("col") == 0
            and item.get("filas_span") == 2
            and item.get("cols_span") == 1
            and cls._normalize_token(item.get("texto")) == "fases y actividades"
            for item in fused
        )
        if not has_left_header_fusion:
            errors.append("celdas_fusionadas_invalidas")

        has_year_fusion = any(
            isinstance(item, dict)
            and item.get("fila") == -1
            and item.get("col") == 1
            and item.get("filas_span") == 1
            and item.get("cols_span") == 12
            and str(item.get("texto") or "").strip() == year_value
            for item in fused
        )
        if not has_year_fusion:
            errors.append("celdas_fusionadas_invalidas")

        rows = table.get("filas")
        if isinstance(rows, list) and len(rows) == 35 and not cls._schedule_row_length_errors(rows):
            for phase_row in cls._SCHEDULE_PHASE_ROWS:
                phase_text = cls._schedule_row_text(rows[phase_row])
                has_phase_fusion = any(
                    isinstance(item, dict)
                    and item.get("fila") == phase_row
                    and item.get("col") == 0
                    and item.get("filas_span") == 1
                    and item.get("cols_span") == 13
                    and str(item.get("texto") or "").strip() == phase_text
                    for item in fused
                )
                if not has_phase_fusion:
                    errors.append("celdas_fusionadas_invalidas")
                    break

        return list(dict.fromkeys(errors))

    @classmethod
    def _schedule_semantic_errors(cls, table: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        rows = table.get("filas")
        if not isinstance(rows, list):
            return ["filas_no_list"]
        if len(rows) != 35:
            return []
        if cls._schedule_row_length_errors(rows):
            return []

        if rows[0] != cls._schedule_expected_month_row():
            errors.append("fila_0_invalida")

        for phase_number, phase_row_index in enumerate(cls._SCHEDULE_PHASE_ROWS, start=1):
            phase_text = cls._schedule_row_text(rows[phase_row_index])
            if not phase_text:
                errors.append(f"fase_{phase_number}_vacia")
            elif cls._schedule_has_placeholder(phase_text):
                errors.append("placeholder_detectado")
            elif not re.match(rf"^{phase_number}\.\s*\S+", phase_text):
                errors.append("numeracion_invalida")

            activity_count = cls._SCHEDULE_ACTIVITY_COUNTS[phase_number - 1]
            month_start, month_end = cls._SCHEDULE_ALLOWED_MONTH_WINDOWS[phase_number]
            allowed_months = set(range(month_start, month_end + 1))
            first_activity_row = phase_row_index + 1
            for activity_number in range(1, activity_count + 1):
                row_index = first_activity_row + activity_number - 1
                activity_text = cls._schedule_row_text(rows[row_index])
                if not activity_text:
                    errors.append(f"actividad_{phase_number}_{activity_number}_vacia")
                    continue
                if cls._schedule_has_placeholder(activity_text):
                    errors.append("placeholder_detectado")
                if not re.match(rf"^{phase_number}\.{activity_number}(?:\.|\b)\s*\S+", activity_text):
                    errors.append("numeracion_invalida")

                marks = cls._schedule_mark_positions(rows[row_index])
                if not marks:
                    errors.append(f"actividad_{phase_number}_{activity_number}_sin_marcas")
                    continue
                if any(mark not in allowed_months for mark in marks):
                    errors.append("marcas_fuera_de_ventana")
                if marks[-1] - marks[0] + 1 != len(marks):
                    errors.append("marcas_no_contiguas")

        return list(dict.fromkeys(errors))

    @classmethod
    def _schedule_table_errors(cls, table: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        if cls._normalize_token(table.get("subtipo")) != "cronograma_actividades":
            errors.append("subtipo_invalido")
        if cls._normalize_token(table.get("orientacion")) != "landscape":
            errors.append("orientacion_invalida")
        errors.extend(cls._schedule_header_errors(table))
        rows = table.get("filas")
        errors.extend(cls._schedule_row_length_errors(rows))
        if isinstance(rows, list) and len(rows) != 35:
            errors.append("numero_filas_invalido")
        if isinstance(rows, list):
            if not rows or rows[0] != cls._schedule_expected_month_row():
                errors.append("fila_0_invalida")
        if table.get("filas_fase") != cls._SCHEDULE_PHASE_ROWS:
            errors.append("filas_fase_invalidas")
        if table.get("meses") != cls._schedule_expected_month_row()[1:]:
            errors.append("meses_invalidos")
        errors.extend(cls._schedule_merge_errors(table))
        errors.extend(cls._schedule_semantic_errors(table))
        return list(dict.fromkeys(errors))

    @classmethod
    def _schedule_error_message(cls, error_code: str) -> str:
        messages = {
            "subtipo_invalido": "subtipo_invalido",
            "orientacion_invalida": "orientacion_invalida",
            "encabezados_invalidos": "encabezados_invalidos",
            "anio_inconsistente": "anio_inconsistente",
            "filas_no_list": "filas_no_list",
            "fila_con_14_celdas": "fila_con_14_celdas",
            "fila_con_longitud_invalida": "fila_con_longitud_invalida",
            "numero_filas_invalido": "numero_filas_invalido",
            "fila_0_invalida": "fila_0_invalida",
            "filas_fase_invalidas": "filas_fase_invalidas",
            "meses_invalidos": "meses_invalidos",
            "celdas_combinadas_invalidas": "celdas_combinadas_invalidas",
            "celdas_fusionadas_invalidas": "celdas_fusionadas_invalidas",
            "numeracion_invalida": "numeracion_invalida",
            "placeholder_detectado": "placeholder_detectado",
            "marcas_fuera_de_ventana": "marcas_fuera_de_ventana",
            "marcas_no_contiguas": "marcas_no_contiguas",
        }
        return messages.get(error_code, error_code)

    @classmethod
    def _required_table_error_messages(cls, content: Any, *, path: str) -> list[str]:
        table_blocks = cls._table_blocks(content)
        if cls._is_schedule_path(path):
            plan = extract_schedule_plan_from_content(content)
            if isinstance(plan, dict):
                plan_errors = validate_schedule_plan(plan)
                fatal_plan_errors = [
                    error
                    for error in plan_errors
                    if error not in {"mes_fuera_de_ventana", "numeracion_semantica_invalida"}
                ]
                if not fatal_plan_errors:
                    return []
            for table in table_blocks:
                table_errors = set(cls._schedule_table_errors(table))
                if (
                    table_errors
                    and table_errors.issubset(cls._SCHEDULE_LEGACY_RECOVERABLE_ERRORS)
                    and salvage_schedule_plan_from_legacy_table(table)
                ):
                    return []
            if not table_blocks:
                return ["sin_table_json_canonico"]
            if any(cls._is_valid_schedule_table(table) for table in table_blocks):
                return []
            errors: list[str] = []
            for table in table_blocks:
                errors.extend(cls._schedule_error_message(code) for code in cls._schedule_table_errors(table))
            return list(dict.fromkeys(errors or ["tabla_cronograma_invalida"]))
        if cls._is_budget_path(path):
            plan = extract_budget_plan_from_content(content)
            if isinstance(plan, dict) and not validate_budget_plan(plan):
                return []
            if not table_blocks:
                return ["sin_table_json_canonico"]
            if any(cls._is_valid_budget_table(table) for table in table_blocks):
                return []
            for table in table_blocks:
                rescued_plan = salvage_budget_plan_from_legacy_table(table)
                if isinstance(rescued_plan, dict) and not validate_budget_plan(rescued_plan):
                    return []
            return ["tabla_presupuesto_invalida"]
        return []

    @classmethod
    def _is_valid_schedule_table(cls, table: dict[str, Any]) -> bool:
        return not cls._schedule_table_errors(table)

    @classmethod
    def _is_valid_budget_table(cls, table: dict[str, Any]) -> bool:
        headers = table.get("encabezados")
        rows = table.get("filas")
        normalized_headers = [cls._normalize_token(item) for item in headers] if isinstance(headers, list) else []
        if cls._normalize_token(table.get("subtipo")) != "presupuesto_investigacion":
            return False
        if cls._normalize_token(table.get("orientacion")) != "portrait":
            return False
        if normalized_headers != [
            "n°",
            "descripcion del gasto",
            "cantidad",
            "costo unit. (s/.)",
            "costo total (s/.)",
        ] and normalized_headers != [
            "n",
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

    @classmethod
    def _validate_required_table_structure(cls, content: Any, *, path: str, section_id: str) -> None:
        is_schedule = cls._is_schedule_path(path)
        is_budget = cls._is_budget_path(path)
        if not is_schedule and not is_budget:
            return

        error_messages = cls._required_table_error_messages(content, path=path)
        if not error_messages:
            return

        section_kind = "cronograma" if is_schedule else "presupuesto"
        logger.warning(
            "OutputValidator: tabla institucional invalida sectionId=%s path=%s errores=%s",
            section_id,
            path,
            ", ".join(error_messages),
        )
        raise ValidationError(
            f"Seccion {section_id} requiere una tabla estructurada valida de {section_kind}; "
            + "; ".join(error_messages)
            + (
                ". Regenera la seccion en formato TABLE_JSON canonico con subtipo, "
                "encabezados, filas y metadatos institucionales completos."
            )
        )

    @classmethod
    def _previous_paragraph_index(cls, content: list[dict[str, Any]], index: int) -> int:
        return index - 1 if index > 0 and cls._normalize_token(content[index - 1].get("tipo")) == "parrafo" else -1

    @classmethod
    def _next_paragraph_index(cls, content: list[dict[str, Any]], index: int) -> int:
        next_index = index + 1
        if next_index < len(content) and cls._normalize_token(content[next_index].get("tipo")) == "parrafo":
            return next_index
        return -1

    @classmethod
    def _validate_reality_problem_quality(cls, content: Any, *, section_id: str) -> None:
        narrative = cls._narrative_text(content)
        normalized_narrative = cls._normalize_token(narrative)
        errors: list[str] = []

        word_count = cls._word_count(narrative)
        if word_count < cls.MIN_REALITY_PROBLEM_NARRATIVE_WORDS:
            errors.append(
                f"1.1 tiene {word_count} palabras narrativas; minimo {cls.MIN_REALITY_PROBLEM_NARRATIVE_WORDS}"
            )
        if word_count > cls.MAX_REALITY_PROBLEM_NARRATIVE_WORDS:
            errors.append(
                f"1.1 tiene {word_count} palabras narrativas; maximo {cls.MAX_REALITY_PROBLEM_NARRATIVE_WORDS}"
            )

        missing = [label for label, pattern in cls._REALITY_PROBLEM_REQUIRED_PATTERNS if not pattern.search(narrative)]
        missing.extend(
            term for term in cls._REALITY_PROBLEM_REQUIRED_NORMALIZED_TERMS if term not in normalized_narrative
        )
        if missing:
            errors.append("1.1 omite contenido obligatorio: " + ", ".join(missing))

        generic_hits = [phrase for phrase in cls._REALITY_PROBLEM_GENERIC_PHRASES if phrase in normalized_narrative]
        if generic_hits:
            errors.append("1.1 conserva frases genericas sin sustento: " + ", ".join(generic_hits))

        if not isinstance(content, list):
            errors.append("1.1 debe llegar como bloques estructurados para controlar figuras e interpretaciones")
        else:
            figures = cls._figure_blocks(content)
            figure_titles = [cls._normalize_token(figure.get("titulo") or figure.get("caption")) for figure in figures]
            expected_titles = [cls._normalize_token(title) for title in cls._REALITY_PROBLEM_REQUIRED_FIGURE_TITLES]
            if figure_titles != expected_titles:
                errors.append(
                    "1.1 no conserva el orden obligatorio de figuras 1.1 Pareto, 1.2 Ishikawa, "
                    "1.3 Relevancia, 1.4 Priorizacion"
                )

            figure_positions = [
                index
                for index, block in enumerate(content)
                if isinstance(block, dict) and cls._normalize_token(block.get("tipo")) == "figura"
            ]
            if len(figure_positions) != 4:
                errors.append("1.1 debe contener exactamente cuatro figuras controladas")
            else:
                for figure_number, position in enumerate(figure_positions, start=1):
                    previous_index = cls._previous_paragraph_index(content, position)
                    next_index = cls._next_paragraph_index(content, position)
                    if previous_index < 0:
                        errors.append(f"Figura 1.{figure_number} no tiene introduccion previa inmediata")
                    else:
                        previous_words = cls._word_count(str(content[previous_index].get("texto") or ""))
                        if previous_words < 35:
                            errors.append(
                                f"Figura 1.{figure_number} tiene introduccion previa demasiado breve "
                                f"({previous_words} palabras)"
                            )
                    if next_index < 0:
                        errors.append(f"Figura 1.{figure_number} no tiene interpretacion posterior inmediata")
                    else:
                        next_words = cls._word_count(str(content[next_index].get("texto") or ""))
                        min_next_words = 70 if figure_number in {1, 3} else 90
                        if next_words < min_next_words:
                            errors.append(
                                f"Figura 1.{figure_number} tiene interpretacion posterior insuficiente "
                                f"({next_words} palabras)"
                            )
                if figure_positions[-1] < len(content) - 1:
                    after_last_paragraphs = [
                        block
                        for block in content[figure_positions[-1] + 1 :]
                        if isinstance(block, dict) and cls._normalize_token(block.get("tipo")) == "parrafo"
                    ]
                    if len(after_last_paragraphs) < 2:
                        errors.append(
                            "Figura 1.4 debe tener interpretacion cuantitativa y cierre metodologico posterior"
                        )

        if errors:
            raise ValidationError(f"Calidad insuficiente en seccion {section_id}: " + " | ".join(errors))

    @classmethod
    def _validate_chapter_two_backgrounds_quality(cls, content: Any, *, section_id: str) -> None:
        visible = cls._visible_content_text(content)
        normalized_visible = cls._normalize_token(visible)
        errors: list[str] = []

        generic_hits = [
            phrase for phrase in cls._CHAPTER_TWO_BACKGROUND_GENERIC_PHRASES if phrase in normalized_visible
        ]
        if generic_hits:
            errors.append("2.1 conserva antecedentes vagos: " + ", ".join(generic_hits))

        # Enforce numbered Heading 3 headings for backgrounds:
        # "2.1.1 Antecedentes internacionales" and "2.1.2 Antecedentes nacionales"
        if not re.search(r"2\.1\.1\.?\s+antecedentes\s+internacionales", normalized_visible):
            errors.append("2.1 no contiene el subtitulo numerado '2.1.1 Antecedentes internacionales'")
        if not re.search(r"2\.1\.2\.?\s+antecedentes\s+nacionales", normalized_visible):
            errors.append("2.1 no contiene el subtitulo numerado '2.1.2 Antecedentes nacionales'")

        narrative_words = cls._word_count(cls._narrative_text(content))
        if narrative_words and narrative_words < 1200:
            errors.append(f"2.1 parece demasiado breve para antecedentes densos ({narrative_words} palabras)")

        if errors:
            raise ValidationError(f"Calidad insuficiente en seccion {section_id}: " + " | ".join(errors))

    @classmethod
    def _theoretical_heading_lines(cls, content: Any) -> list[str]:
        if not isinstance(content, list):
            return []
        headings = []
        for block in content:
            if isinstance(block, dict) and cls._normalize_token(block.get("tipo")) == "parrafo":
                text = str(block.get("texto") or "").strip()
                if text:
                    first_line = text.splitlines()[0].strip()
                    if re.match(r"^\s*2\.2\.\d+", first_line):
                        headings.append(first_line)
        return headings

    @classmethod
    def _validate_theoretical_bases_quality(cls, content: Any, *, section_id: str) -> None:
        if not isinstance(content, list):
            return

        errors: list[str] = []
        # Check for numbered headings (2.2.x)
        headings = cls._theoretical_heading_lines(content)
        if not headings:
            errors.append("2.2 no contiene subtitulos numerados (2.2.x)")

        visible = cls._normalize_token(cls._visible_content_text(content))
        maintenance_markers = (
            "mantenimiento centrado en confiabilidad",
            "rcm",
            "iso 14224",
            "amef",
            "disponibilidad inherente",
            "mtbf",
            "mttr",
            "motoniveladora",
        )
        maintenance_case = sum(marker in visible for marker in maintenance_markers) >= 3
        if maintenance_case:
            required_headings = (
                "2.2.1 mantenimiento centrado en confiabilidad",
                "2.2.2 proceso del rcm",
                "2.2.3 taxonomia de equipos",
                "2.2.4 analisis de modos y efecto de fallas",
                "2.2.5 disponibilidad inherente",
                "2.2.6 confiabilidad",
                "2.2.7 mantenibilidad",
                "2.2.8 motoniveladora",
            )
            normalized_headings = [cls._normalize_token(heading) for heading in headings]
            missing = [
                heading
                for heading in required_headings
                if not any(candidate.startswith(heading) for candidate in normalized_headings)
            ]
            if missing:
                errors.append(
                    "2.2 de mantenimiento no respeta los ocho subtitulos canonicos: "
                    + ", ".join(missing)
                )

        figure_positions = [
            index
            for index, block in enumerate(content)
            if isinstance(block, dict) and cls._normalize_token(block.get("tipo")) == "figura"
        ]
        formula_positions = [
            index
            for index, block in enumerate(content)
            if isinstance(block, dict) and cls._normalize_token(block.get("tipo")) == "formula"
        ]

        narrative_words = cls._word_count(cls._narrative_text(content))
        if figure_positions and narrative_words < 300:
            errors.append("2.2 contiene figuras, pero el desarrollo teorico previo/posterior es insuficiente")

        for position in figure_positions:
            previous_index = cls._previous_paragraph_index(content, position)
            if previous_index < 0:
                errors.append("2.2 contiene una figura sin parrafo teorico inmediato previo")
                continue
            previous_words = cls._word_count(str(content[previous_index].get("texto") or ""))
            if previous_words < cls.MIN_THEORETICAL_FIGURE_PREVIOUS_WORDS:
                errors.append(
                    f"2.2 contiene una figura precedida por texto demasiado breve ({previous_words} palabras)"
                )

        for position in formula_positions:
            previous_index = cls._previous_paragraph_index(content, position)
            if previous_index < 0:
                errors.append("2.2 contiene una formula sin definicion previa inmediata")
                continue
            previous_words = cls._word_count(str(content[previous_index].get("texto") or ""))
            if previous_words < cls.MIN_THEORETICAL_FORMULA_PREVIOUS_WORDS:
                errors.append(
                    f"2.2 contiene una formula precedida por texto demasiado breve ({previous_words} palabras)"
                )
            if cls._next_paragraph_index(content, position) < 0:
                errors.append("2.2 contiene una formula sin interpretacion posterior inmediata")

        if errors:
            raise ValidationError(f"Calidad insuficiente en seccion {section_id}: " + " | ".join(errors))

    @classmethod
    def _validate_required_headings(
        cls,
        content: Any,
        *,
        section_id: str,
        required_headings: tuple[str, ...],
    ) -> None:
        visible = cls._visible_content_text(content)
        normalized_visible = cls._normalize_token(visible)
        missing = [heading for heading in required_headings if cls._normalize_token(heading) not in normalized_visible]
        if missing:
            raise ValidationError(
                f"Calidad insuficiente en seccion {section_id}: faltan subtitulos obligatorios: " + ", ".join(missing)
            )

    @classmethod
    def _validate_justification_structure(cls, content: Any, *, section_id: str) -> None:
        cls._validate_required_headings(
            content,
            section_id=section_id,
            required_headings=cls._JUSTIFICATION_REQUIRED_HEADINGS,
        )

    @classmethod
    def _validate_delimitations_structure(cls, content: Any, *, section_id: str) -> None:
        cls._validate_required_headings(
            content,
            section_id=section_id,
            required_headings=cls._DELIMITATIONS_REQUIRED_HEADINGS,
        )

    @classmethod
    def _validate_chapter_four_methodology_length(cls, content: Any, *, path: str, section_id: str) -> None:
        word_range = cls._chapter_four_word_range_for_path(path)
        if word_range is None:
            return
        min_words, max_words = word_range
        narrative_words = cls._word_count(cls._narrative_text(content))
        if narrative_words == 0:
            return

        errors: list[str] = []
        if min_words and narrative_words < min_words:
            errors.append(f"Capitulo IV fuera de extension: {narrative_words} palabras; minimo {min_words}")
        if max_words and narrative_words > max_words:
            errors.append(f"Capitulo IV fuera de extension: {narrative_words} palabras; maximo {max_words}")
        if errors:
            raise ValidationError(f"Calidad insuficiente en seccion {section_id}: " + " | ".join(errors))

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

            self._validate_required_table_structure(
                content,
                path=path,
                section_id=str(section_id or f"sec-auto-{idx:04d}"),
            )

            if not path:
                warnings.append(f"Section '{section_id}' missing path")

            if not visible_content:
                warnings.append(f"Section '{section_id}' has empty content")
            elif len(visible_content) < self.MIN_CONTENT_LENGTH:
                warnings.append(f"Section '{section_id}' content is very short ({len(visible_content)} chars)")

            if self._is_reality_problem_path(path):
                try:
                    self._validate_reality_problem_quality(
                        content,
                        section_id=str(section_id or f"sec-auto-{idx:04d}"),
                    )
                except ValidationError as exc:
                    warnings.append(str(exc))
            if self._is_backgrounds_path(path):
                try:
                    self._validate_chapter_two_backgrounds_quality(
                        content,
                        section_id=str(section_id or f"sec-auto-{idx:04d}"),
                    )
                except ValidationError as exc:
                    warnings.append(str(exc))
            if self._is_theoretical_bases_path(path):
                try:
                    self._validate_theoretical_bases_quality(
                        content,
                        section_id=str(section_id or f"sec-auto-{idx:04d}"),
                    )
                except ValidationError as exc:
                    warnings.append(str(exc))
            if self._is_justification_path(path):
                try:
                    self._validate_justification_structure(
                        content,
                        section_id=str(section_id or f"sec-auto-{idx:04d}"),
                    )
                except ValidationError as exc:
                    warnings.append(str(exc))
            if self._is_delimitations_path(path):
                try:
                    self._validate_delimitations_structure(
                        content,
                        section_id=str(section_id or f"sec-auto-{idx:04d}"),
                    )
                except ValidationError as exc:
                    warnings.append(str(exc))
            if self._is_chapter_four_section_path(path):
                try:
                    self._validate_chapter_four_methodology_length(
                        content,
                        path=path,
                        section_id=str(section_id or f"sec-auto-{idx:04d}"),
                    )
                except ValidationError as exc:
                    warnings.append(str(exc))

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
