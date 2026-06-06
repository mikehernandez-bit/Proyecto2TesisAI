"""Focused tests for dynamic schedule/budget table validation contract."""

import json

import pytest

from app.core.services.ai.content_parser import parse_ai_content
from app.core.services.ai.output_validator import OutputValidator, ValidationError


@pytest.fixture
def validator():
    return OutputValidator()


def _schedule_row(label: str, marked_months: list[int] | None = None) -> list[str]:
    row = [label] + [""] * 12
    for month in marked_months or []:
        row[month] = "●"
    return row


def _valid_schedule_table() -> dict[str, object]:
    phase_titles = [
        "1. Delimitacion y planificacion del estudio",
        "2. Levantamiento y organizacion de datos operacionales",
        "3. Depuracion y construccion de base analitica",
        "4. Linea base de confiabilidad y mantenibilidad",
        "5. Criticidad y priorizacion de modos de falla",
        "6. Diseno del plan RCM e implementacion piloto",
        "7. Validacion tecnica y contrastacion de resultados",
        "8. Cierre documental y preparacion de sustentacion",
    ]
    rows = [
        ["", "Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Set", "Oct", "Nov", "Dic"],
        _schedule_row(phase_titles[0]),
        _schedule_row("1.1. Delimitar alcance y unidad de analisis", [2]),
        _schedule_row("1.2. Definir protocolo de captura y control documental", [2, 3]),
        _schedule_row("1.3. Establecer criterios de consistencia del estudio", [3]),
        _schedule_row(phase_titles[1]),
        _schedule_row("2.1. Recopilar historiales de fallas y paradas", [2, 3]),
        _schedule_row("2.2. Levantar contexto operacional y condiciones de trabajo", [3, 4]),
        _schedule_row("2.3. Homologar taxonomia de sistemas y modos de falla", [4]),
        _schedule_row(phase_titles[2]),
        _schedule_row("3.1. Consolidar base estructurada para analisis", [4, 5]),
        _schedule_row("3.2. Depurar duplicados, faltantes y unidades", [5, 6]),
        _schedule_row("3.3. Validar consistencia interna con responsables", [6]),
        _schedule_row(phase_titles[3]),
        _schedule_row("4.1. Calcular indicadores base de MTBF, MTTR y disponibilidad", [6]),
        _schedule_row("4.2. Segmentar resultados por sistema y condicion", [6, 7]),
        _schedule_row("4.3. Emitir diagnostico inicial de comportamiento", [7]),
        _schedule_row(phase_titles[4]),
        _schedule_row("5.1. Ejecutar analisis de criticidad por subsistema", [7]),
        _schedule_row("5.2. Desarrollar AMEF de modos de falla dominantes", [7, 8]),
        _schedule_row("5.3. Priorizar componentes de mayor consecuencia operacional", [8]),
        _schedule_row(phase_titles[5]),
        _schedule_row("6.1. Disenar tareas RCM para funciones criticas", [7, 8]),
        _schedule_row("6.2. Definir frecuencias, recursos y puntos de control", [8, 9]),
        _schedule_row("6.3. Ajustar parametros de implementacion y seguimiento", [9, 10]),
        _schedule_row("6.4. Ejecutar piloto del plan en la flota objetivo", [7, 8, 9, 10]),
        _schedule_row(phase_titles[6]),
        _schedule_row("7.1. Validar tecnicamente el plan con especialistas", [8, 9]),
        _schedule_row("7.2. Contrastar resultados pre y post intervencion", [9, 10]),
        _schedule_row("7.3. Analizar sensibilidad de tiempos y tasas de falla", [10, 11]),
        _schedule_row(phase_titles[7]),
        _schedule_row("8.1. Redactar resultados, discusion y conclusiones", [10]),
        _schedule_row("8.2. Levantar observaciones del asesor", [10, 11]),
        _schedule_row("8.3. Ajustar anexos, tablas y formato final", [11, 12]),
        _schedule_row("8.4. Preparar presentacion y sustentacion final", [12]),
    ]
    return {
        "tipo": "tabla",
        "id": "tabla_5_1_cronograma_actividades",
        "titulo": "Tabla 5.1 Cronograma de actividades",
        "encabezados": ["FASES Y ACTIVIDADES", "2025", "", "", "", "", "", "", "", "", "", "", ""],
        "filas": rows,
        "orientacion": "landscape",
        "subtipo": "cronograma_actividades",
        "anio": "2025",
        "meses": ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Set", "Oct", "Nov", "Dic"],
        "filas_fase": [1, 5, 9, 13, 17, 21, 26, 30],
        "celdas_combinadas": [{"fila": -1, "col_inicio": 1, "col_fin": 12, "texto": "2025"}]
        + [{"fila": row, "col_inicio": 0, "col_fin": 12, "texto": title} for row, title in zip([1, 5, 9, 13, 17, 21, 26, 30], phase_titles)],
        "celdas_fusionadas": [
            {"fila": -1, "col": 0, "filas_span": 2, "cols_span": 1, "texto": "FASES Y ACTIVIDADES"},
            {"fila": -1, "col": 1, "filas_span": 1, "cols_span": 12, "texto": "2025"},
        ]
        + [{"fila": row, "col": 0, "filas_span": 1, "cols_span": 13, "texto": title} for row, title in zip([1, 5, 9, 13, 17, 21, 26, 30], phase_titles)],
    }


def _failed_sec_0025_schedule_raw_response() -> str:
    bad_table = _valid_schedule_table()
    bad_table["encabezados"] = ["FASES Y ACTIVIDADES", "Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Set", "Oct", "Nov", "Dic"]
    bad_table["filas"][0] = [""] * 14
    bad_table["celdas_combinadas"] = [
        {"fila_inicio": 0, "fila_fin": 0, "col_inicio": 0, "col_fin": 0, "texto": "FASES Y ACTIVIDADES"},
        {"fila_inicio": 0, "fila_fin": 0, "col_inicio": 1, "col_fin": 12, "texto": "2025"},
    ]
    bad_table["celdas_fusionadas"] = [
        {"fila": 1, "col_inicio": 0, "col_fin": 12, "texto": "1. Delimitacion y planificacion del estudio"},
    ]
    return f"```json\n<<<TABLE_JSON\n{json.dumps(bad_table, ensure_ascii=False)}\nTABLE_JSON>>>\n```"


def test_schedule_section_keeps_dynamic_structured_table(validator):
    ai_result = {
        "sections": [
            {
                "sectionId": "sec-cronograma",
                "path": "V. CRONOGRAMA DE ACTIVIDADES",
                "content": [_valid_schedule_table()],
            }
        ]
    }

    result = validator.validate(ai_result)
    content = result["sections"][0]["content"]
    table = content[0]

    assert isinstance(content, list)
    assert len(content) == 1
    assert table["tipo"] == "tabla"
    assert table["id"] == "tabla_5_1_cronograma_actividades"
    assert table["titulo"] == "Tabla 5.1 Cronograma de actividades"
    assert table["orientacion"] == "landscape"
    assert table["subtipo"] == "cronograma_actividades"
    assert len(table["encabezados"]) == 13
    assert len(table["filas"]) == 35


def test_schedule_section_rejects_non_contiguous_marks(validator):
    bad_table = _valid_schedule_table()
    bad_table["filas"][22] = _schedule_row("6.1. Disenar tareas RCM para funciones criticas", [7, 9])
    ai_result = {"sections": [{"sectionId": "sec-cronograma", "path": "V. CRONOGRAMA DE ACTIVIDADES", "content": [bad_table]}]}

    with pytest.raises(ValidationError, match="tabla estructurada valida de cronograma"):
        validator.validate(ai_result)


def test_schedule_section_rejects_marks_outside_phase_window(validator):
    bad_table = _valid_schedule_table()
    bad_table["filas"][18] = _schedule_row("5.1. Ejecutar analisis de criticidad por subsistema", [6])
    ai_result = {"sections": [{"sectionId": "sec-cronograma", "path": "V. CRONOGRAMA DE ACTIVIDADES", "content": [bad_table]}]}

    with pytest.raises(ValidationError, match="tabla estructurada valida de cronograma"):
        validator.validate(ai_result)


def test_schedule_section_rejects_placeholder_phase_and_activity_labels(validator):
    bad_table = _valid_schedule_table()
    bad_table["filas"][1][0] = "FASE 1"
    bad_table["filas"][2][0] = "ACTIVIDAD 1.1"
    ai_result = {"sections": [{"sectionId": "sec-cronograma", "path": "V. CRONOGRAMA DE ACTIVIDADES", "content": [bad_table]}]}

    with pytest.raises(ValidationError, match="tabla estructurada valida de cronograma"):
        validator.validate(ai_result)


def test_schedule_section_reports_specific_structural_errors_for_failed_sec_0025_shape(validator):
    parsed = parse_ai_content(_failed_sec_0025_schedule_raw_response())
    ai_result = {"sections": [{"sectionId": "sec-0025", "path": "V. CRONOGRAMA DE ACTIVIDADES", "content": parsed}]}

    result = validator.validate(ai_result)
    assert result["sections"][0]["path"] == "V. CRONOGRAMA DE ACTIVIDADES"


def test_schedule_section_without_structured_table_raises(validator):
    ai_result = {
        "sections": [
            {
                "sectionId": "sec-cronograma",
                "path": "V. CRONOGRAMA DE ACTIVIDADES",
                "content": "Cronograma narrativo sin tabla estructurada.",
            }
        ]
    }

    with pytest.raises(ValidationError, match="tabla estructurada valida de cronograma"):
        validator.validate(ai_result)


def test_budget_section_keeps_dynamic_structured_table(validator):
    ai_result = {
        "sections": [
            {
                "sectionId": "sec-presupuesto",
                "path": "VI. PRESUPUESTO",
                "content": [
                    {
                        "tipo": "tabla",
                        "id": "tabla_6_1_presupuesto_investigacion",
                        "titulo": "Tabla 6.1 Presupuesto de investigacion",
                        "encabezados": ["N°", "DESCRIPCION DEL GASTO", "CANTIDAD", "COSTO UNIT. (S/.)", "COSTO TOTAL (S/.)"],
                        "filas": [
                            ["1. RECURSOS HUMANOS", "", "", "", "2,000.00"],
                            ["1.1", "Investigador", "1", "2,000.00", "2,000.00"],
                            ["2. RECURSOS DE INVESTIGACION", "", "", "", "4,849.00"],
                            ["2.1", "Laptop", "1", "2,999.00", "2,999.00"],
                            ["2.2", "Internet", "12", "50.00", "600.00"],
                            ["2.3", "Movilidad", "4", "250.00", "1,000.00"],
                            ["2.4", "Software", "1", "250.00", "250.00"],
                            ["3. RECURSOS CONSUMIBLES", "", "", "", "560.00"],
                            ["3.1", "Escritorio", "1", "150.00", "150.00"],
                            ["3.2", "Impresiones", "1", "350.00", "350.00"],
                            ["3.3", "USB", "1", "60.00", "60.00"],
                            ["4. CONTINGENCIA / IMPREVISTOS", "", "", "", "370.00"],
                            ["4.1", "Imprevistos", "1", "370.00", "370.00"],
                            ["TOTAL GENERAL", "", "", "", "S/. 7,779.00"],
                        ],
                        "orientacion": "portrait",
                        "subtipo": "presupuesto_investigacion",
                        "filas_categoria": [0, 2, 7, 11],
                        "fila_total": 13,
                        "celdas_combinadas": [{"fila": 0, "col_inicio": 0, "col_fin": 3, "texto": "1. RECURSOS HUMANOS"}],
                        "celdas_fusionadas": [{"fila": 13, "col": 0, "filas_span": 1, "cols_span": 4, "texto": "TOTAL GENERAL"}],
                    }
                ],
            }
        ]
    }

    result = validator.validate(ai_result)
    content = result["sections"][0]["content"]
    table = content[0]

    assert isinstance(content, list)
    assert len(content) == 1
    assert table["tipo"] == "tabla"
    assert table["id"] == "tabla_6_1_presupuesto_investigacion"
    assert table["titulo"] == "Tabla 6.1 Presupuesto de investigacion"
    assert table["orientacion"] == "portrait"
    assert table["subtipo"] == "presupuesto_investigacion"
    assert len(table["encabezados"]) == 5
    assert len(table["filas"]) == 14


def test_budget_section_without_structured_table_raises(validator):
    ai_result = {
        "sections": [
            {
                "sectionId": "sec-presupuesto",
                "path": "VI. PRESUPUESTO",
                "content": [{"tipo": "tabla", "titulo": "Tabla incompleta", "encabezados": ["A"], "filas": []}],
            }
        ]
    }

    with pytest.raises(ValidationError, match="tabla estructurada valida de presupuesto"):
        validator.validate(ai_result)


def test_operationalization_section_keeps_only_bridge_text(validator):
    ai_result = {
        "sections": [
            {
                "sectionId": "sec-operacionalizacion",
                "path": "III. HIPÓTESIS Y VARIABLES/3.2 Operacionalización de variable",
                "content": [
                    {
                        "tipo": "parrafo",
                        "texto": "La operacionalizacion organiza variables, dimensiones e indicadores.",
                    },
                    {
                        "tipo": "tabla",
                        "id": "tab-3-1",
                        "titulo": "Tabla 3.1 Operacionalización de la variable independiente",
                        "encabezados": [
                            "VARIABLES",
                            "DEFINICIÓN CONCEPTUAL",
                            "DEFINICIÓN OPERACIONAL",
                            "DIMENSIONES",
                            "INDICADORES",
                            "ÍNDICE",
                            "MÉTODO Y TÉCNICA",
                        ],
                        "filas": [
                            ["VI", "Def. conceptual", "Def. operacional", "Dim 1", "Ind 1", "Idx 1", "Técnica 1"],
                        ],
                        "orientacion": "landscape",
                    },
                    {
                        "tipo": "tabla",
                        "id": "tab-3-2",
                        "titulo": "Tabla 3.2 Operacionalización de la variable dependiente",
                        "encabezados": [
                            "VARIABLES",
                            "DEFINICIÓN CONCEPTUAL",
                            "DEFINICIÓN OPERACIONAL",
                            "DIMENSIONES",
                            "INDICADORES",
                            "ÍNDICE",
                            "MÉTODO Y TÉCNICA",
                        ],
                        "filas": [
                            ["VD", "Def. conceptual", "Def. operacional", "Dim A", "Ind A", "Idx A", "Técnica A"],
                        ],
                        "orientacion": "landscape",
                    },
                    {
                        "tipo": "figura",
                        "caption": "Figura no permitida en 3.2",
                    },
                ],
            }
        ]
    }

    result = validator.validate(ai_result)
    content = result["sections"][0]["content"]
    assert isinstance(content, list)
    assert [item["tipo"] for item in content] == ["parrafo"]
    assert "operacionalizacion organiza variables" in content[0]["texto"].lower()
