"""Structured table builder for the Maestria consistency matrix annex."""

from __future__ import annotations

from typing import Any

from app.core.services.maestria_payload_mapper import normalize_maestria_details

_BLANK_HEADER = "\u200b"


def _clean_text(value: Any) -> str:
    if value is None or isinstance(value, (list, dict)):
        return ""
    return str(value).strip()


def _clean_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [text for item in value if (text := _clean_text(item))]
    if isinstance(value, str):
        return [text for part in value.replace("\r", "\n").split("\n") if (text := part.strip())]
    return []


def _label_lines(items: list[tuple[str, Any]]) -> str:
    lines: list[str] = []
    for label, value in items:
        text = _clean_text(value)
        if text:
            lines.append(f"{label}: {text}")
    return "\n".join(lines)


def _dimensions_block(title: str, variable: str, dimensions: list[str]) -> str:
    lines = [f"{title}:", variable or "Pendiente"]
    if dimensions:
        lines.extend(["", "Dimensiones:"])
        lines.extend(f"- {dimension}" for dimension in dimensions)
    return "\n".join(lines)


def build_matriz_consistencia_table(values: dict[str, Any] | None) -> dict[str, Any]:
    """Build the annex matrix exactly from the values captured in Details."""
    details = normalize_maestria_details(values or {})
    matrix = details["matriz_consistencia"]
    title = details.get("titulo") or "Titulo pendiente"

    problems = _clean_list(matrix.get("problemas_especificos"))
    objectives = _clean_list(matrix.get("objetivos_especificos"))
    hypotheses = _clean_list(matrix.get("hipotesis_especificas"))
    specific_count = max(len(problems), len(objectives), len(hypotheses), 1)

    vi = matrix.get("variable_independiente") or details.get("variable_independiente") or ""
    vd = matrix.get("variable_dependiente") or details.get("variable_dependiente") or ""
    vi_dimensions = _clean_list(matrix.get("dimensiones_variable_independiente"))
    vd_dimensions = _clean_list(matrix.get("dimensiones_variable_dependiente"))
    variables_text = "\n\n".join(
        [
            _dimensions_block("VARIABLE INDEPENDIENTE", vi, vi_dimensions),
            _dimensions_block("VARIABLE DEPENDIENTE", vd, vd_dimensions),
        ]
    ).strip()

    methodology_text = _label_lines(
        [
            ("Tipo", matrix.get("tipo_investigacion")),
            ("Nivel", matrix.get("nivel_investigacion")),
            ("Enfoque", matrix.get("enfoque_investigacion")),
            ("Diseño", matrix.get("diseno")),
            ("Población", matrix.get("poblacion")),
            ("Muestra", matrix.get("muestra")),
            ("Técnicas", matrix.get("tecnicas")),
            ("Instrumentos", matrix.get("instrumentos")),
            ("Procesamiento de datos", matrix.get("procesamiento_datos")),
        ]
    )

    rows: list[list[str]] = [
        ["PROBLEMA", "OBJETIVOS", "HIPÓTESIS", "VARIABLES", "METODOLOGÍA"],
        ["PROBLEMA GENERAL", "OBJETIVO GENERAL", "HIPÓTESIS GENERAL", variables_text, methodology_text],
        [
            _clean_text(matrix.get("problema_general")),
            _clean_text(matrix.get("objetivo_general")),
            _clean_text(matrix.get("hipotesis_general")),
            "",
            "",
        ],
        ["PROBLEMAS ESPECÍFICOS", "OBJETIVOS ESPECÍFICOS", "HIPÓTESIS ESPECÍFICAS", "", ""],
    ]

    for index in range(specific_count):
        rows.append(
            [
                problems[index] if index < len(problems) else "",
                objectives[index] if index < len(objectives) else "",
                hypotheses[index] if index < len(hypotheses) else "",
                "",
                "",
            ]
        )

    last_body_row = len(rows) - 1
    body_span = max(1, last_body_row)
    return {
        "tipo": "tabla",
        "id": "anexo_1_matriz_consistencia",
        "titulo": "Anexo 1: Matriz de consistencia",
        "encabezados": [title, *[_BLANK_HEADER for _ in range(4)]],
        "filas": rows,
        "orientacion": "landscape",
        "subtipo": "matriz_consistencia",
        "titulo_proyecto": title,
        "celdas_combinadas": [
            {"fila": -1, "col_inicio": 0, "col_fin": 4, "texto": title},
            {
                "fila_inicio": 1,
                "fila_fin": last_body_row,
                "col": 3,
                "texto": variables_text,
            },
            {
                "fila_inicio": 1,
                "fila_fin": last_body_row,
                "col": 4,
                "texto": methodology_text,
            },
        ],
        "celdas_fusionadas": [
            {
                "fila": -1,
                "col": 0,
                "filas_span": 1,
                "cols_span": 5,
                "texto": title,
                "bold": True,
                "alignment": "center",
            },
            {
                "fila": 1,
                "col": 3,
                "filas_span": body_span,
                "cols_span": 1,
                "texto": variables_text,
                "alignment": "left",
            },
            {
                "fila": 1,
                "col": 4,
                "filas_span": body_span,
                "cols_span": 1,
                "texto": methodology_text,
                "alignment": "left",
            },
        ],
        "estilos": {
            "ocupar_ancho_pagina": True,
            "columnas": 5,
            "ancho_columnas": ["20%", "20%", "20%", "20%", "20%"],
            "encabezado_negrita": True,
            "titulo_combinado": True,
            "variables_metodologia_combinadas_verticalmente": True,
        },
    }
