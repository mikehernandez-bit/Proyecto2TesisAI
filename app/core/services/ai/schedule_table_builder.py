"""Deterministic builder for UNAC project schedule tables.

This module converts a small semantic blueprint into the canonical
``cronograma_actividades`` table required by GicaTesis. It also provides
best-effort rescue for legacy malformed tables produced by the model.
"""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

MONTHS = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Set", "Oct", "Nov", "Dic"]
PHASE_ROWS = [1, 5, 9, 13, 17, 21, 26, 30]
ACTIVITY_COUNTS = (3, 3, 3, 3, 3, 4, 3, 4)
ALLOWED_MONTH_WINDOWS = {
    1: (2, 3),
    2: (2, 4),
    3: (4, 6),
    4: (6, 7),
    5: (7, 8),
    6: (7, 10),
    7: (8, 11),
    8: (10, 12),
}
DEFAULT_YEAR = "2025"
MARKER = "●"
CANONICAL_TABLE_ID = "tabla_5_1_cronograma_actividades"
CANONICAL_TABLE_TITLE = "Tabla 5.1 Cronograma de actividades"
CANONICAL_CHAPTER_TITLE = "V. CRONOGRAMA DE ACTIVIDADES"

_YEAR_RE = re.compile(r"\b(20\d{2})\b")
_LEADING_NUMBER_RE = re.compile(r"^\s*\d+(?:\.\d+)?\.?\s*")
_MONTH_NAME_TO_INDEX = {name.lower(): index for index, name in enumerate(MONTHS, start=1)}
_BLUEPRINT_SUBTYPES = {"cronograma_plan", "schedule_plan"}


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _strip_leading_number(text: str) -> str:
    stripped = _LEADING_NUMBER_RE.sub("", _normalize_text(text))
    return stripped or _normalize_text(text)


def _coerce_int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    text = _normalize_text(value)
    if not text:
        return None
    if text.isdigit():
        return int(text)
    month_index = _MONTH_NAME_TO_INDEX.get(text.lower())
    if month_index is not None:
        return month_index
    return None


def _discover_year(values: Optional[Dict[str, Any]] = None, candidates: Iterable[Any] = ()) -> str:
    search_values: List[Any] = list(candidates)
    if isinstance(values, dict):
        for key in (
            "anio",
            "año",
            "year",
            "periodo",
            "titulo",
            "title",
            "tema",
            "tema_investigacion",
        ):
            search_values.append(values.get(key))

    for candidate in search_values:
        text = _normalize_text(candidate)
        if not text:
            continue
        match = _YEAR_RE.search(text)
        if match:
            return match.group(1)
    return DEFAULT_YEAR


def _activity_row_indexes() -> List[Tuple[int, int, int]]:
    mapping: List[Tuple[int, int, int]] = []
    row_index = 2
    for phase_number, count in enumerate(ACTIVITY_COUNTS, start=1):
        for activity_number in range(1, count + 1):
            mapping.append((phase_number, activity_number, row_index))
            row_index += 1
        if phase_number < len(ACTIVITY_COUNTS):
            row_index += 1
    return mapping


ACTIVITY_ROW_INDEXES = _activity_row_indexes()


def extract_schedule_plan_from_content(content: Any) -> Optional[Dict[str, Any]]:
    """Return the first schedule blueprint block found in content."""
    blocks: Sequence[Any]
    if isinstance(content, list):
        blocks = content
    else:
        blocks = [content]

    for block in blocks:
        if not isinstance(block, dict):
            continue
        block_type = _normalize_text(block.get("tipo")).lower()
        block_subtype = _normalize_text(block.get("subtipo")).lower()
        if block_type == "cronograma_plan" or block_subtype in _BLUEPRINT_SUBTYPES:
            return deepcopy(block)
    return None


def validate_schedule_plan(plan: Dict[str, Any]) -> List[str]:
    """Validate semantic schedule blueprint shape."""
    errors: List[str] = []
    if not isinstance(plan, dict):
        return ["cronograma_plan_invalido"]

    phases = plan.get("fases")
    if not isinstance(phases, list):
        return ["faltan_fases"]
    if len(phases) != len(ACTIVITY_COUNTS):
        errors.append("faltan_fases")
        return errors

    for phase_number, (phase, expected_activities) in enumerate(zip(phases, ACTIVITY_COUNTS), start=1):
        if not isinstance(phase, dict):
            errors.append("fase_invalida")
            continue
        title = _normalize_text(phase.get("titulo") or phase.get("nombre"))
        if not title:
            errors.append("fase_sin_titulo")

        phase_declared = _coerce_int(phase.get("numero"))
        if phase_declared is not None and phase_declared != phase_number:
            errors.append("numeracion_semantica_invalida")

        activities = phase.get("actividades")
        if not isinstance(activities, list) or len(activities) != expected_activities:
            errors.append("faltan_actividades")
            continue

        allowed_start, allowed_end = ALLOWED_MONTH_WINDOWS[phase_number]
        for activity_number, activity in enumerate(activities, start=1):
            if not isinstance(activity, dict):
                errors.append("actividad_invalida")
                continue
            activity_title = _normalize_text(activity.get("titulo") or activity.get("nombre"))
            if not activity_title:
                errors.append("actividad_sin_titulo")
            declared_number = _normalize_text(activity.get("numero"))
            if declared_number and not declared_number.startswith(f"{phase_number}.{activity_number}"):
                errors.append("numeracion_semantica_invalida")

            month_start = _coerce_int(activity.get("mes_inicio"))
            month_end = _coerce_int(activity.get("mes_fin"))
            if month_start is None or month_end is None:
                errors.append("actividad_sin_rango_mensual")
                continue
            if month_start > month_end:
                month_start, month_end = month_end, month_start
            if month_start < allowed_start or month_end > allowed_end:
                errors.append("mes_fuera_de_ventana")

    return list(dict.fromkeys(errors))


def _normalize_plan(
    plan: Dict[str, Any],
    *,
    values: Optional[Dict[str, Any]] = None,
    clamp_to_window: bool = True,
) -> Dict[str, Any]:
    errors = validate_schedule_plan(plan)
    fatal_errors = [error for error in errors if error not in {"mes_fuera_de_ventana", "numeracion_semantica_invalida"}]
    if fatal_errors:
        raise ValueError(", ".join(fatal_errors))

    phases = plan.get("fases") or []
    year = _discover_year(values, candidates=[plan.get("anio"), plan.get("year")])
    normalized_phases: List[Dict[str, Any]] = []

    for phase_number, (phase, expected_activities) in enumerate(zip(phases, ACTIVITY_COUNTS), start=1):
        title_body = _strip_leading_number(phase.get("titulo") or phase.get("nombre"))
        phase_title = f"{phase_number}. {title_body}"
        activities = []
        allowed_start, allowed_end = ALLOWED_MONTH_WINDOWS[phase_number]
        for activity_number, activity in enumerate((phase.get("actividades") or [])[:expected_activities], start=1):
            title_body = _strip_leading_number(activity.get("titulo") or activity.get("nombre"))
            activity_title = f"{phase_number}.{activity_number}. {title_body}"
            month_start = _coerce_int(activity.get("mes_inicio"))
            month_end = _coerce_int(activity.get("mes_fin"))
            if month_start is None or month_end is None:
                raise ValueError("actividad_sin_rango_mensual")
            if month_start > month_end:
                month_start, month_end = month_end, month_start
            if clamp_to_window:
                month_start = min(max(month_start, allowed_start), allowed_end)
                month_end = min(max(month_end, allowed_start), allowed_end)
                if month_start > month_end:
                    month_start = month_end = allowed_start
            elif month_start < allowed_start or month_end > allowed_end:
                raise ValueError("mes_fuera_de_ventana")

            activities.append(
                {
                    "numero": f"{phase_number}.{activity_number}",
                    "titulo": activity_title,
                    "mes_inicio": month_start,
                    "mes_fin": month_end,
                }
            )
        normalized_phases.append(
            {
                "numero": phase_number,
                "titulo": phase_title,
                "actividades": activities,
            }
        )

    return {
        "tipo": "cronograma_plan",
        "anio": year,
        "fases": normalized_phases,
    }


def build_schedule_table_from_plan(
    plan: Dict[str, Any],
    *,
    values: Optional[Dict[str, Any]] = None,
    clamp_to_window: bool = True,
) -> Dict[str, Any]:
    """Materialize canonical UNAC schedule table from a semantic blueprint."""
    normalized = _normalize_plan(plan, values=values, clamp_to_window=clamp_to_window)
    year = normalized["anio"]
    rows: List[List[str]] = [["", *MONTHS]]
    phase_titles: List[str] = []

    for phase in normalized["fases"]:
        phase_title = phase["titulo"]
        phase_titles.append(phase_title)
        rows.append([phase_title] + [""] * 12)
        for activity in phase["actividades"]:
            row = [activity["titulo"]] + [""] * 12
            for month in range(activity["mes_inicio"], activity["mes_fin"] + 1):
                row[month] = MARKER
            rows.append(row)

    canonical = {
        "tipo": "tabla",
        "id": CANONICAL_TABLE_ID,
        "titulo": CANONICAL_TABLE_TITLE,
        "encabezados": ["FASES Y ACTIVIDADES", year, "", "", "", "", "", "", "", "", "", "", ""],
        "filas": rows,
        "orientacion": "landscape",
        "subtipo": "cronograma_actividades",
        "anio": year,
        "meses": list(MONTHS),
        "simbolo_marca": MARKER,
        "filas_fase": list(PHASE_ROWS),
        "celdas_combinadas": [
            {"fila": -1, "fila_fin": 0, "col_inicio": 0, "col_fin": 0, "texto": "FASES Y ACTIVIDADES"},
            {"fila": -1, "col_inicio": 1, "col_fin": 12, "texto": year},
        ]
        + [
            {"fila": row, "col_inicio": 0, "col_fin": 12, "texto": title}
            for row, title in zip(PHASE_ROWS, phase_titles)
        ],
        "celdas_fusionadas": [
            {
                "fila": -1,
                "col": 0,
                "filas_span": 2,
                "cols_span": 1,
                "texto": "FASES Y ACTIVIDADES",
                "bold": True,
                "alignment": "center",
            },
            {
                "fila": -1,
                "col": 1,
                "filas_span": 1,
                "cols_span": 12,
                "texto": year,
                "bold": True,
                "alignment": "center",
            },
        ]
        + [
            {
                "fila": row,
                "col": 0,
                "filas_span": 1,
                "cols_span": 13,
                "texto": title,
                "bold": True,
                "alignment": "center",
            }
            for row, title in zip(PHASE_ROWS, phase_titles)
        ],
        "estilo": {
            "modelo_referencia": "cronograma_actividades.docx",
            "titulo_capitulo": CANONICAL_CHAPTER_TITLE,
            "titulo_exacto": True,
            "titulo_tamano_pt": 9.5,
            "titulo_space_after_pt": 6,
            "ancho_tabla": "100%",
            "ancho_columnas": [8.91] + [1.59] * 12,
            "alineacion_actividades": "left",
            "alineacion_meses": "center",
            "encabezados_negrita": True,
            "fases_negrita": True,
            "fases_centradas": True,
            "bordes": "grid",
            "fuente_tamano_pt": 8,
            "fuente_meses_pt": 8,
            "fuente_actividades_pt": 8,
            "fuente_fases_pt": 8,
            "fuente_marcas_pt": 10,
            "compactar_cronograma": False,
            "orientacion_pagina": "landscape",
            "margenes_reducidos": True,
        },
    }
    return canonical


def salvage_schedule_plan_from_legacy_table(
    table: Dict[str, Any],
    *,
    values: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Rescue a malformed legacy table into a semantic blueprint."""
    if not isinstance(table, dict):
        return None
    rows = table.get("filas")
    if not isinstance(rows, list) or len(rows) < 35:
        return None

    phases: List[Dict[str, Any]] = []
    year = _discover_year(values, candidates=[table.get("anio"), table.get("encabezados")])
    for phase_number, (phase_row, expected_activities) in enumerate(zip(PHASE_ROWS, ACTIVITY_COUNTS), start=1):
        raw_phase_row = rows[phase_row]
        if not isinstance(raw_phase_row, list):
            return None
        phase_title = _normalize_text(raw_phase_row[0] if raw_phase_row else "")
        if not phase_title:
            return None
        activities: List[Dict[str, Any]] = []
        for offset in range(expected_activities):
            row_index = phase_row + 1 + offset
            raw_activity_row = rows[row_index]
            if not isinstance(raw_activity_row, list):
                return None
            activity_title = _normalize_text(raw_activity_row[0] if raw_activity_row else "")
            if not activity_title:
                return None
            month_cells = list(raw_activity_row[1:13])
            marks = [index for index, cell in enumerate(month_cells, start=1) if _normalize_text(cell)]
            if not marks:
                return None
            activities.append(
                {
                    "numero": f"{phase_number}.{offset + 1}",
                    "titulo": _strip_leading_number(activity_title),
                    "mes_inicio": min(marks),
                    "mes_fin": max(marks),
                }
            )
        phases.append(
            {
                "numero": phase_number,
                "titulo": _strip_leading_number(phase_title),
                "actividades": activities,
            }
        )

    return {
        "tipo": "cronograma_plan",
        "subtipo": "cronograma_plan",
        "anio": year,
        "fases": phases,
    }


def _topic_from_values(values: Optional[Dict[str, Any]]) -> str:
    if not isinstance(values, dict):
        return "el proyecto de investigacion"
    for key in (
        "tema",
        "tema_investigacion",
        "titulo",
        "title",
        "problema_general",
    ):
        text = _normalize_text(values.get(key))
        if text:
            return text
    return "el proyecto de investigacion"


def build_synthetic_schedule_plan(values: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Fallback semantic plan when the model fails twice."""
    topic = _topic_from_values(values)
    objective = _normalize_text((values or {}).get("objetivo_general"))
    variable_i = _normalize_text((values or {}).get("variable_independiente")) or "variable independiente"
    variable_d = _normalize_text((values or {}).get("variable_dependiente")) or "variable dependiente"
    location = _normalize_text((values or {}).get("lugar") or (values or {}).get("ubicacion")) or "la unidad de estudio"

    phase_titles = [
        f"Planificacion y delimitacion tecnica del estudio sobre {topic}",
        "Levantamiento y organizacion de informacion operativa",
        "Depuracion y estructuracion de la base analitica",
        "Construccion de la linea base de analisis",
        "Analisis de criticidad y priorizacion tecnica",
        f"Diseno e integracion de la propuesta sobre {variable_i}",
        f"Validacion tecnica del impacto en {variable_d}",
        "Cierre documental y preparacion de sustentacion",
    ]
    activity_templates = [
        [
            f"Delimitar alcance, unidad de analisis y contexto de {location}",
            "Definir protocolo de trabajo, fuentes y criterios de control",
            f"Alinear objetivo general y supuestos de {topic}" if objective else f"Alinear problema y finalidad de {topic}",
        ],
        [
            "Recopilar historiales, registros y documentos tecnicos",
            "Caracterizar condiciones operativas y restricciones del entorno",
            "Homologar taxonomia, variables y codificacion de eventos",
        ],
        [
            "Consolidar la base estructurada para el tratamiento analitico",
            "Depurar duplicados, faltantes, unidades y consistencia temporal",
            "Validar integridad interna con responsables del proceso",
        ],
        [
            "Calcular indicadores base y metricas de comparacion",
            "Segmentar resultados por sistema, condicion o muestra",
            "Emitir diagnostico inicial para la linea base del estudio",
        ],
        [
            "Ejecutar analisis de criticidad por componentes o categorias",
            "Priorizar causas, riesgos o modos de falla relevantes",
            "Seleccionar focos de intervencion para la fase propositiva",
        ],
        [
            f"Disenar acciones y tareas asociadas a {variable_i}",
            "Definir frecuencias, recursos y criterios de implementacion",
            "Modelar escenarios de aplicacion y control operativo",
            "Consolidar propuesta tecnica y plan piloto de ejecucion",
        ],
        [
            f"Validar la propuesta frente a {variable_d}",
            "Contrastar resultados esperados con criterios tecnicos",
            "Ajustar sensibilidad, supuestos y trazabilidad del modelo",
        ],
        [
            "Redactar resultados, discusion y conclusiones finales",
            "Levantar observaciones y ajustar anexos, tablas y figuras",
            "Preparar version final del documento academico",
            "Organizar presentacion y sustentacion del proyecto",
        ],
    ]
    month_patterns = {
        1: [(2, 2), (2, 3), (3, 3)],
        2: [(2, 3), (3, 4), (4, 4)],
        3: [(4, 5), (5, 6), (6, 6)],
        4: [(6, 6), (6, 7), (7, 7)],
        5: [(7, 7), (7, 8), (8, 8)],
        6: [(7, 8), (7, 9), (9, 10), (10, 10)],
        7: [(8, 9), (9, 10), (11, 11)],
        8: [(10, 10), (10, 11), (11, 12), (12, 12)],
    }
    phases: List[Dict[str, Any]] = []
    for phase_number, titles in enumerate(activity_templates, start=1):
        activities = []
        for activity_number, title in enumerate(titles, start=1):
            month_start, month_end = month_patterns[phase_number][activity_number - 1]
            activities.append(
                {
                    "numero": f"{phase_number}.{activity_number}",
                    "titulo": title,
                    "mes_inicio": month_start,
                    "mes_fin": month_end,
                }
            )
        phases.append(
            {
                "numero": phase_number,
                "titulo": phase_titles[phase_number - 1],
                "actividades": activities,
            }
        )

    return {
        "tipo": "cronograma_plan",
        "subtipo": "cronograma_plan",
        "anio": _discover_year(values),
        "fases": phases,
    }

