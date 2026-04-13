"""
Excel Template Builder — Maestría UNAC

Generates a downloadable .xlsx template for the UNAC Master's thesis wizard step.
Users fill in the template and upload it back to GicaGen for extraction.

Layout:
  Column A: Field label (read-only guide)
  Column B: User value (to be filled)

Sheet name: "Datos Maestría"
"""

from __future__ import annotations

import io
from typing import Any

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


# ---------------------------------------------------------------------------
# Internal field spec
# ---------------------------------------------------------------------------

_SECTIONS: list[dict[str, Any]] = [
    {
        "title": "A. Datos Generales",
        "color": "1E40AF",  # blue-800
        "fields": [
            {
                "key": "titulo",
                "label": "Título del proyecto",
                "placeholder": "Ej: Implementación de un sistema para mejorar la atención de proyectos de investigación",
                "required": True,
            },
            {
                "key": "linea_investigacion",
                "label": "Línea de investigación",
                "placeholder": "Ej: Gestión y Optimización de Sistemas de Mantenimiento Industrial",
                "required": True,
            },
            {
                "key": "anio",
                "label": "Año",
                "placeholder": "Ej: 2025",
                "required": True,
            },
            {
                "key": "lugar_caratula",
                "label": "Lugar (carátula)",
                "placeholder": "Ej: Callao",
                "required": False,
            },
        ],
    },
    {
        "title": "B. Autor 1",
        "color": "065F46",  # green-800
        "fields": [
            {
                "key": "autor1_nombres",
                "label": "Apellidos y Nombres (Autor 1)",
                "placeholder": "Ej: QUISPE FLORES, Juan Carlos",
                "required": True,
            },
            {
                "key": "autor1_dni",
                "label": "DNI (Autor 1)",
                "placeholder": "Ej: 12345678",
                "required": False,
            },
            {
                "key": "autor1_orcid",
                "label": "ORCID (Autor 1)",
                "placeholder": "Ej: 0000-0001-2345-6789",
                "required": False,
            },
        ],
    },
    {
        "title": "C. Autor 2 (Opcional)",
        "color": "164E63",  # cyan-900
        "fields": [
            {
                "key": "autor2_nombres",
                "label": "Apellidos y Nombres (Autor 2)",
                "placeholder": "Dejar vacío si no hay segundo autor",
                "required": False,
            },
            {
                "key": "autor2_dni",
                "label": "DNI (Autor 2)",
                "placeholder": "Ej: 87654321",
                "required": False,
            },
            {
                "key": "autor2_orcid",
                "label": "ORCID (Autor 2)",
                "placeholder": "Ej: 0000-0002-3456-7890",
                "required": False,
            },
        ],
    },
    {
        "title": "D. Asesor",
        "color": "7C2D12",  # orange-900
        "fields": [
            {
                "key": "asesor_nombres",
                "label": "Apellidos y Nombres (Asesor)",
                "placeholder": "Ej: RAMÍREZ TORRES, Pedro Augusto",
                "required": True,
            },
            {
                "key": "asesor_dni",
                "label": "DNI (Asesor)",
                "placeholder": "Ej: 11223344",
                "required": False,
            },
            {
                "key": "asesor_orcid",
                "label": "ORCID (Asesor)",
                "placeholder": "Ej: 0000-0003-4567-8901",
                "required": False,
            },
        ],
    },
    {
        "title": "E. Datos de Investigación",
        "color": "4C1D95",  # violet-900
        "fields": [
            {
                "key": "lugar_ejecucion",
                "label": "Lugar de ejecución",
                "placeholder": "Ej: Planta Industrial XYZ, Callao",
                "required": True,
            },
            {
                "key": "unidad_analisis",
                "label": "Unidad de análisis",
                "placeholder": "Ej: Equipos de mantenimiento del área de producción",
                "required": True,
            },
            {
                "key": "tipo",
                "label": "Tipo de investigación",
                "placeholder": "Ej: Aplicada",
                "required": True,
            },
            {
                "key": "enfoque",
                "label": "Enfoque",
                "placeholder": "Cuantitativo / Cualitativo / Mixto",
                "required": True,
            },
            {
                "key": "diseno_investigacion",
                "label": "Diseño de investigación",
                "placeholder": "Ej: Preexperimental / No experimental / Descriptivo",
                "required": True,
            },
            {
                "key": "tema_ocde_1",
                "label": "Tema OCDE 1",
                "placeholder": "Ej: 2. Ingeniería y Tecnología",
                "required": True,
            },
            {
                "key": "tema_ocde_2",
                "label": "Tema OCDE 2",
                "placeholder": "Ej: 2.3 Ingeniería Mecánica",
                "required": False,
            },
            {
                "key": "tema_ocde_3",
                "label": "Tema OCDE 3",
                "placeholder": "Ej: 2.3.1 Mantenimiento industrial",
                "required": False,
            },
            {
                "key": "objeto_estudio",
                "label": "Objeto de estudio",
                "placeholder": "Ej: Flota de motoniveladoras CAT 24M",
                "required": True,
            },
            {
                "key": "variable_independiente",
                "label": "Variable independiente",
                "placeholder": "Ej: Plan de mantenimiento centrado en confiabilidad",
                "required": True,
            },
            {
                "key": "variable_dependiente",
                "label": "Variable dependiente",
                "placeholder": "Ej: Disponibilidad inherente",
                "required": True,
            },
            {
                "key": "poblacion",
                "label": "Población",
                "placeholder": "Ej: 15 motoniveladoras CAT 24M",
                "required": True,
            },
            {
                "key": "muestra",
                "label": "Muestra",
                "placeholder": "Ej: 15 motoniveladoras CAT 24M (censo)",
                "required": True,
            },
            {
                "key": "lugar",
                "label": "Lugar (para el título)",
                "placeholder": "Ej: Unidad Minera Cuprífera, Sierra Central",
                "required": True,
            },
            {
                "key": "temporal",
                "label": "Temporal (Año del título)",
                "placeholder": "Ej: 2025",
                "required": True,
            },
        ],
    },
]


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def build_excel_template() -> bytes:
    """
    Build and return the Excel template as bytes.

    Returns:
        bytes: The .xlsx file content ready to be sent as a response.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Datos Maestría"

    # Column widths
    ws.column_dimensions["A"].width = 38
    ws.column_dimensions["B"].width = 60
    ws.column_dimensions["C"].width = 32

    # Header row
    _write_header(ws)

    current_row = 3  # Start after header

    for section in _SECTIONS:
        current_row = _write_section(ws, section, current_row)
        current_row += 1  # blank row between sections

    # Instructions sheet
    _write_instructions_sheet(wb)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


def _write_header(ws: Any) -> None:
    """Write the main header row."""
    ws.row_dimensions[1].height = 30
    header_cell = ws["A1"]
    header_cell.value = "PLANTILLA DATOS — TESIS MAESTRÍA UNAC"
    header_cell.font = Font(name="Calibri", bold=True, size=14, color="FFFFFF")
    header_cell.fill = PatternFill("solid", fgColor="1E3A5F")
    header_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.merge_cells("A1:C1")

    ws.row_dimensions[2].height = 22
    ws["A2"].value = "Campo"
    ws["B2"].value = "Valor (completar aquí)"
    ws["C2"].value = "Ejemplo / Notas"
    for col in ("A", "B", "C"):
        cell = ws[f"{col}2"]
        cell.font = Font(name="Calibri", bold=True, size=10, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="374151")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def _write_section(ws: Any, section: dict[str, Any], start_row: int) -> int:
    """Write a section header + its fields. Returns the next available row."""
    color = section["color"]
    title = section["title"]

    # Section header
    ws.row_dimensions[start_row].height = 20
    section_cell = ws[f"A{start_row}"]
    section_cell.value = title
    section_cell.font = Font(name="Calibri", bold=True, size=11, color="FFFFFF")
    section_cell.fill = PatternFill("solid", fgColor=color)
    section_cell.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.merge_cells(f"A{start_row}:C{start_row}")
    current_row = start_row + 1

    for field in section["fields"]:
        ws.row_dimensions[current_row].height = 18
        label_cell = ws[f"A{current_row}"]
        label_text = field["label"]
        if field.get("required"):
            label_text += " *"
        label_cell.value = label_text
        label_cell.font = Font(name="Calibri", bold=field.get("required", False), size=10)
        label_cell.alignment = Alignment(vertical="center", indent=1, wrap_text=True)
        # Light fill for alternating rows
        bg = "EFF6FF" if (current_row % 2 == 0) else "F9FAFB"
        label_cell.fill = PatternFill("solid", fgColor=bg)

        value_cell = ws[f"B{current_row}"]
        value_cell.value = ""  # user fills this
        value_cell.font = Font(name="Calibri", size=10)
        value_cell.alignment = Alignment(vertical="center", wrap_text=True)
        value_cell.fill = PatternFill("solid", fgColor="FFFFFF")

        note_cell = ws[f"C{current_row}"]
        note_cell.value = field.get("placeholder", "")
        note_cell.font = Font(name="Calibri", size=9, italic=True, color="6B7280")
        note_cell.alignment = Alignment(vertical="center", wrap_text=True)
        note_cell.fill = PatternFill("solid", fgColor=bg)

        # Map the key to row for parsing later — stored as a comment in col A
        # We use a named range approach: store key in column D (hidden)
        key_cell = ws[f"D{current_row}"]
        key_cell.value = field["key"]
        ws.column_dimensions["D"].hidden = True

        current_row += 1

    return current_row


def _write_instructions_sheet(wb: Any) -> None:
    """Write a helper instructions sheet."""
    ws = wb.create_sheet(title="Instrucciones")
    ws.column_dimensions["A"].width = 80

    instructions = [
        ("CÓMO USAR ESTA PLANTILLA", True, 14, "1E3A5F", "FFFFFF"),
        ("", False, 11, None, None),
        ("1. Complete los campos en la columna B de la hoja 'Datos Maestría'.", False, 11, None, None),
        ("2. Los campos marcados con (*) son obligatorios.", False, 11, None, None),
        ("3. No modifique la columna A (etiquetas) ni la columna D.", False, 11, None, None),
        ("4. Guarde el archivo y súbalo en GicaGen (Paso 3 del wizard).", False, 11, None, None),
        ("5. El sistema extraerá los datos automáticamente.", False, 11, None, None),
        ("", False, 11, None, None),
        ("VALIDACIONES APLICADAS", True, 12, "374151", "FFFFFF"),
        ("• Título: obligatorio, texto no vacío.", False, 10, None, None),
        ("• Año: numérico entre 2000 y 2100.", False, 10, None, None),
        ("• DNI: solo dígitos (8 para Perú).", False, 10, None, None),
        ("• ORCID: formato 0000-0000-0000-0000.", False, 10, None, None),
        ("• Si completa datos de Autor 2, es recomendable completar todos sus campos.", False, 10, None, None),
        ("• Tema OCDE 1 es obligatorio; OCDE 2 y 3 son opcionales.", False, 10, None, None),
    ]
    for row_idx, (text, bold, size, bg_hex, fg_hex) in enumerate(instructions, start=1):
        cell = ws[f"A{row_idx}"]
        cell.value = text
        cell.font = Font(name="Calibri", bold=bold, size=size, color=fg_hex or "111827")
        cell.alignment = Alignment(wrap_text=True, vertical="center", indent=1)
        if bg_hex:
            cell.fill = PatternFill("solid", fgColor=bg_hex)
        ws.row_dimensions[row_idx].height = 20 if text else 10
