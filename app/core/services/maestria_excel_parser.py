"""
Maestría UNAC — Excel Parser

Parses the filled Excel template uploaded by the user in Wizard Step 3.
Returns a normalized, validated result with extracted fields, missing fields,
warnings, and validation errors.

This module is intentionally isolated from HTTP concerns — it only handles
file parsing and business validation. The router calls it and wraps the result
in HTTP responses.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from typing import Any

import openpyxl

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SHEET_NAME = "Datos Maestría"
_KEY_COLUMN = "D"  # Hidden column that maps rows to field keys
_VALUE_COLUMN = "B"

_REQUIRED_FIELDS = {
    "titulo",
    "anio",
    "autor1_nombres",
    "asesor_nombres",
    "lugar_ejecucion",
    "unidad_analisis",
    "tipo",
    "enfoque",
    "diseno_investigacion",
    "tema_ocde_1",
}

_ORCID_PATTERN = re.compile(r"^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$")
_DNI_PERU_PATTERN = re.compile(r"^\d{8}$")

_YEAR_MIN = 2000
_YEAR_MAX = 2100

# Valid controlled values (case-insensitive matching)
_VALID_ENFOQUE = {"cuantitativo", "cualitativo", "mixto"}
_VALID_TIPO = {"aplicada", "básica", "basica", "experimental", "descriptiva"}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class AutorData:
    nombres: str = ""
    dni: str = ""
    orcid: str = ""

    def is_empty(self) -> bool:
        return not any([self.nombres, self.dni, self.orcid])


@dataclass
class InvestigacionData:
    lugar_ejecucion: str = ""
    unidad_analisis: str = ""
    tipo: str = ""
    enfoque: str = ""
    diseno_investigacion: str = ""
    nivel_investigacion: str = ""
    tema_ocde: list[str] = field(default_factory=list)
    vi: str = ""
    vd: str = ""
    variable_independiente: str = ""
    variable_dependiente: str = ""
    objeto_estudio: str = ""
    poblacion: str = ""
    muestra: str = ""
    lugar: str = ""
    temporal: str = ""


@dataclass
class MaestriaExcelResult:
    # Main fields
    titulo: str | None = None
    linea_investigacion: str | None = None
    anio: str | None = None
    lugar_caratula: str | None = None
    autor1: AutorData = field(default_factory=AutorData)
    autor2: AutorData = field(default_factory=AutorData)
    asesor: AutorData = field(default_factory=AutorData)
    coasesor: AutorData = field(default_factory=AutorData)
    investigacion: InvestigacionData = field(default_factory=InvestigacionData)
    # Metadata
    extracted_fields: list[str] = field(default_factory=list)
    missing_required: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    validation_errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "titulo": self.titulo,
            "linea_investigacion": self.linea_investigacion,
            "anio": self.anio,
            "lugar_caratula": self.lugar_caratula,
            "autor1": {
                "nombres": self.autor1.nombres,
                "dni": self.autor1.dni,
                "orcid": self.autor1.orcid,
            },
            "autor2": {
                "nombres": self.autor2.nombres,
                "dni": self.autor2.dni,
                "orcid": self.autor2.orcid,
            },
            "asesor": {
                "nombres": self.asesor.nombres,
                "dni": self.asesor.dni,
                "orcid": self.asesor.orcid,
            },
            "coasesor": {
                "nombres": self.coasesor.nombres,
                "dni": self.coasesor.dni,
                "orcid": self.coasesor.orcid,
            },
            "investigacion": {
                "lugar_ejecucion": self.investigacion.lugar_ejecucion,
                "unidad_analisis": self.investigacion.unidad_analisis,
                "tipo": self.investigacion.tipo,
                "enfoque": self.investigacion.enfoque,
                "diseno_investigacion": self.investigacion.diseno_investigacion,
                "nivel_investigacion": self.investigacion.nivel_investigacion,
                "tema_ocde": self.investigacion.tema_ocde,
                "vi": self.investigacion.variable_independiente,
                "vd": self.investigacion.variable_dependiente,
                "variable_independiente": self.investigacion.variable_independiente,
                "variable_dependiente": self.investigacion.variable_dependiente,
                "objeto_estudio": self.investigacion.objeto_estudio,
                "poblacion": self.investigacion.poblacion,
                "muestra": self.investigacion.muestra,
                "lugar": self.investigacion.lugar,
                "temporal": self.investigacion.temporal,
            },
            "extracted_fields": self.extracted_fields,
            "missing_required": self.missing_required,
            "warnings": self.warnings,
            "validation_errors": self.validation_errors,
        }

    def to_flat_dict(self) -> dict[str, Any]:
        """
        Returns a flat dict suitable for merging into project values / wizard store.
        This is what gets written into projectValues for the payload builder.
        """
        tema_ocde = (self.investigacion.tema_ocde or []) + ["", "", ""]
        return {
            "titulo": self.titulo or "",
            "title": self.titulo or "",
            "tema": self.titulo or "",
            "linea_investigacion": self.linea_investigacion or "",
            "anio": self.anio or "",
            "lugar_caratula": self.lugar_caratula or "",
            "autor1_nombres": self.autor1.nombres,
            "autor1_dni": self.autor1.dni,
            "autor1_orcid": self.autor1.orcid,
            "autor2_nombres": self.autor2.nombres,
            "autor2_dni": self.autor2.dni,
            "autor2_orcid": self.autor2.orcid,
            "asesor_nombres": self.asesor.nombres,
            "asesor_dni": self.asesor.dni,
            "asesor_orcid": self.asesor.orcid,
            "coasesor_nombres": self.coasesor.nombres,
            "coasesor_dni": self.coasesor.dni,
            "coasesor_orcid": self.coasesor.orcid,
            "lugar_ejecucion": self.investigacion.lugar_ejecucion,
            "unidad_analisis": self.investigacion.unidad_analisis,
            "tipo": self.investigacion.tipo,
            "enfoque": self.investigacion.enfoque,
            "diseno_investigacion": self.investigacion.diseno_investigacion,
            "nivel_investigacion": self.investigacion.nivel_investigacion,
            "variable_independiente": self.investigacion.variable_independiente,
            "variable_dependiente": self.investigacion.variable_dependiente,
            "objeto_estudio": self.investigacion.objeto_estudio,
            "poblacion": self.investigacion.poblacion,
            "muestra": self.investigacion.muestra,
            "lugar": self.investigacion.lugar,
            "temporal": self.investigacion.temporal,
            "tema_ocde_1": tema_ocde[0],
            "tema_ocde_2": tema_ocde[1],
            "tema_ocde_3": tema_ocde[2],
        }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_excel_bytes(data: bytes) -> MaestriaExcelResult:
    """
    Parse Excel bytes from an uploaded file.

    Args:
        data: Raw .xlsx file bytes.

    Returns:
        MaestriaExcelResult with all extracted data and validation metadata.

    Raises:
        ValueError: If the file is not a valid Excel file or missing the expected sheet.
    """
    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
    except Exception as exc:
        raise ValueError(f"No se pudo leer el archivo Excel: {exc}") from exc

    if SHEET_NAME not in wb.sheetnames:
        available = ", ".join(wb.sheetnames)
        raise ValueError(
            f"No se encontró la hoja '{SHEET_NAME}' en el archivo. "
            f"Hojas disponibles: {available}. "
            "Usa la plantilla oficial descargada desde GicaGen."
        )

    ws = wb[SHEET_NAME]
    raw_values = _extract_raw_values(ws)
    result = _build_result(raw_values)
    _run_validations(result)
    return result


# ---------------------------------------------------------------------------
# Internal extraction
# ---------------------------------------------------------------------------


def _normalize_cell(value: Any) -> str:
    """Normalize a cell value to a clean string or empty string."""
    if value is None:
        return ""
    text = str(value).strip()
    # Collapse multiple spaces
    text = re.sub(r"  +", " ", text)
    # Remove line break variants
    text = text.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
    return text.strip()


def _extract_raw_values(ws: Any) -> dict[str, str]:
    """
    Walk the worksheet and extract key→value pairs using column D as key map.

    Column D holds the internal field key (hidden), column B holds the user value.
    Skips MergedCell objects that do not have a column_letter attribute.
    """
    raw: dict[str, str] = {}
    for row in ws.iter_rows():
        key_cell = None
        value_cell = None
        for cell in row:
            # Skip MergedCell placeholders (they lack column_letter / value attrs)
            if not hasattr(cell, "column_letter"):
                continue
            if cell.column_letter == "D":
                key_cell = cell
            elif cell.column_letter == "B":
                value_cell = cell
        if key_cell is None or value_cell is None:
            continue
        key = _normalize_cell(key_cell.value)
        if not key:
            continue
        value = _normalize_cell(value_cell.value)
        raw[key] = value
    return raw


def _get(raw: dict[str, str], key: str) -> str | None:
    """Return None for empty strings, otherwise the value."""
    value = raw.get(key, "").strip()
    return value if value else None


def _build_result(raw: dict[str, str]) -> MaestriaExcelResult:
    """Populate a MaestriaExcelResult from the raw key→value dict."""
    result = MaestriaExcelResult()
    extracted: list[str] = []

    def assign(key: str, setter_fn: Any) -> None:
        value = _get(raw, key)
        if value is not None:
            setter_fn(value)
            extracted.append(key)

    # Datos generales
    def set_titulo(v: str) -> None:
        result.titulo = v

    def set_linea(v: str) -> None:
        result.linea_investigacion = v

    def set_anio(v: str) -> None:
        result.anio = v

    def set_lugar(v: str) -> None:
        result.lugar_caratula = v

    assign("titulo", set_titulo)
    assign("linea_investigacion", set_linea)
    assign("anio", set_anio)
    assign("lugar_caratula", set_lugar)

    # Autor 1
    _fill_autor(raw, result.autor1, "autor1", extracted)
    # Autor 2
    _fill_autor(raw, result.autor2, "autor2", extracted)
    # Asesor
    _fill_autor(raw, result.asesor, "asesor", extracted)
    # Co-asesor
    _fill_autor(raw, result.coasesor, "coasesor", extracted)

    # Investigación
    inv = result.investigacion

    def set_lugar_ej(v: str) -> None:
        inv.lugar_ejecucion = v

    def set_unidad(v: str) -> None:
        inv.unidad_analisis = v

    def set_tipo(v: str) -> None:
        inv.tipo = v

    def set_enfoque(v: str) -> None:
        inv.enfoque = v

    def set_diseno(v: str) -> None:
        inv.diseno_investigacion = v

    def set_nivel(v: str) -> None:
        inv.nivel_investigacion = v

    def set_vi(v: str) -> None:
        inv.variable_independiente = v
        inv.vi = v

    def set_vd(v: str) -> None:
        inv.variable_dependiente = v
        inv.vd = v

    def set_objeto(v: str) -> None:
        inv.objeto_estudio = v

    def set_poblacion(v: str) -> None:
        inv.poblacion = v

    def set_muestra(v: str) -> None:
        inv.muestra = v

    def set_lugar(v: str) -> None:
        inv.lugar = v

    def set_temporal(v: str) -> None:
        inv.temporal = v

    assign("lugar_ejecucion", set_lugar_ej)
    assign("unidad_analisis", set_unidad)
    assign("tipo", set_tipo)
    assign("enfoque", set_enfoque)
    assign("diseno_investigacion", set_diseno)
    assign("nivel_investigacion", set_nivel)
    assign("variable_independiente", set_vi)
    assign("variable_dependiente", set_vd)
    assign("objeto_estudio", set_objeto)
    assign("poblacion", set_poblacion)
    assign("muestra", set_muestra)
    assign("lugar", set_lugar)
    assign("temporal", set_temporal)
    # Compatibilidad con llaves cortas de versiones anteriores si existen
    if not inv.variable_independiente: assign("vi", set_vi)
    if not inv.variable_dependiente: assign("vd", set_vd)

    temas: list[str] = []
    for key in ("tema_ocde_1", "tema_ocde_2", "tema_ocde_3"):
        v = _get(raw, key)
        if v:
            temas.append(v)
            extracted.append(key)
    inv.tema_ocde = temas

    result.extracted_fields = extracted
    return result


def _fill_autor(raw: dict[str, str], autor: AutorData, prefix: str, extracted: list[str]) -> None:
    for suffix, attr in (("_nombres", "nombres"), ("_dni", "dni"), ("_orcid", "orcid")):
        key = f"{prefix}{suffix}"
        value = _get(raw, key)
        if value is not None:
            setattr(autor, attr, value)
            extracted.append(key)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _run_validations(result: MaestriaExcelResult) -> None:
    """Populate missing_required, warnings, and validation_errors."""
    missing: list[str] = []
    warnings: list[str] = []
    errors: list[str] = []

    # Required fields check:
    # We compare against the CANONICAL source fields, not the reordered flat dict.
    # For tema_ocde, we check tema_ocde_1 specifically by whether it was extracted.
    extracted_set = set(result.extracted_fields)
    direct_required_checks: dict[str, bool] = {
        "titulo": bool(str(result.titulo or "").strip()),
        "linea_investigacion": bool(str(result.linea_investigacion or "").strip()),
        "anio": bool(str(result.anio or "").strip()),
        "autor1_nombres": bool(str(result.autor1.nombres or "").strip()),
        "asesor_nombres": bool(str(result.asesor.nombres or "").strip()),
        "lugar_ejecucion": bool(str(result.investigacion.lugar_ejecucion or "").strip()),
        "unidad_analisis": bool(str(result.investigacion.unidad_analisis or "").strip()),
        "objeto_estudio": bool(str(result.investigacion.objeto_estudio or "").strip()),
        "variable_independiente": bool(str(result.investigacion.variable_independiente or "").strip()),
        "variable_dependiente": bool(str(result.investigacion.variable_dependiente or "").strip()),
        "temporal": bool(str(result.investigacion.temporal or "").strip()),
        "tipo": bool(str(result.investigacion.tipo or "").strip()),
        "enfoque": bool(str(result.investigacion.enfoque or "").strip()),
        "diseno_investigacion": bool(str(result.investigacion.diseno_investigacion or "").strip()),
        # tema_ocde_1 must be explicitly present in extracted_fields AND non-empty
        "tema_ocde_1": "tema_ocde_1" in extracted_set and len(result.investigacion.tema_ocde) > 0,
    }
    for field_key in sorted(_REQUIRED_FIELDS):
        if not direct_required_checks.get(field_key, False):
            missing.append(field_key)

    # Year validation
    if result.anio:
        if not re.fullmatch(r"\d{4}", result.anio):
            errors.append("El año debe contener exactamente 4 dígitos.")
        else:
            year = int(result.anio)
            if year < _YEAR_MIN or year > _YEAR_MAX:
                errors.append(f"El año debe estar dentro del rango {_YEAR_MIN}-{_YEAR_MAX}.")

    # ORCID validations
    for label, orcid_val in [
        ("Autor 1", result.autor1.orcid),
        ("Autor 2", result.autor2.orcid),
        ("Asesor", result.asesor.orcid),
    ]:
        if orcid_val and not _ORCID_PATTERN.match(orcid_val):
            warnings.append(
                f"ORCID de {label} '{orcid_val}' no tiene el formato esperado "
                "(0000-0000-0000-0000)."
            )

    # DNI validations (Perú: 8 digits)
    for label, dni_val in [
        ("Autor 1", result.autor1.dni),
        ("Autor 2", result.autor2.dni),
        ("Asesor", result.asesor.dni),
    ]:
        if dni_val and not _DNI_PERU_PATTERN.match(dni_val):
            warnings.append(
                f"DNI de {label} '{dni_val}' no parece un DNI peruano válido (8 dígitos)."
            )

    # Enfoque validation
    if result.investigacion.enfoque:
        if result.investigacion.enfoque.lower() not in _VALID_ENFOQUE:
            warnings.append(
                f"Enfoque '{result.investigacion.enfoque}' no es uno de los valores "
                f"esperados: {', '.join(sorted(_VALID_ENFOQUE))}."
            )

    # Autor 2 coherence
    autor2 = result.autor2
    autor2_fields = [autor2.nombres, autor2.dni, autor2.orcid]
    non_empty = [f for f in autor2_fields if f]
    if 0 < len(non_empty) < 2:
        warnings.append(
            "Autor 2: si va a incluir un segundo autor, se recomienda completar "
            "al menos nombres y DNI."
        )

    result.missing_required = missing
    result.warnings = warnings
    result.validation_errors = errors
