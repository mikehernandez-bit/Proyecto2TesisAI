"""Tests for GicaTesis AI-result adapter in API router."""

import pytest

from app.integrations.gicatesis.types import RenderPayloadValidationError
from app.modules.api.router import (
    _adapt_ai_result_for_gicatesis,
    _build_render_payload,
    _extract_resume_seed_sections,
    _values_with_title,
)


def _schedule_row(label: str, marked_months: list[int] | None = None) -> list[str]:
    row = [label] + [""] * 12
    for month in marked_months or []:
        row[month] = "●"
    return row


def _canonical_schedule_table() -> dict[str, object]:
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


def test_adapter_returns_empty_sections_for_invalid_payload():
    assert _adapt_ai_result_for_gicatesis(None) == {"sections": []}
    assert _adapt_ai_result_for_gicatesis({}) == {"sections": []}
    assert _adapt_ai_result_for_gicatesis({"sections": "x"}) == {"sections": []}


def test_adapter_keeps_only_canonical_paths():
    ai_result = {
        "sections": [
            {
                "sectionId": "sec-0001",
                "path": "Capitulo I/Introduccion",
                "content": "Texto IA",
            }
        ]
    }

    out = _adapt_ai_result_for_gicatesis(ai_result)
    sections = out["sections"]

    assert len(sections) == 1
    assert sections[0]["path"] == "Capitulo I/Introduccion"
    assert sections[0]["sectionId"] == "sec-0001"


def test_adapter_keeps_single_path_when_no_hierarchy():
    ai_result = {
        "sections": [
            {
                "sectionId": "sec-0002",
                "path": "Resumen",
                "content": "Contenido resumen",
            }
        ]
    }

    out = _adapt_ai_result_for_gicatesis(ai_result)
    assert len(out["sections"]) == 1
    assert out["sections"][0]["path"] == "Resumen"


def test_adapter_skips_empty_content():
    ai_result = {
        "sections": [
            {"path": "Capitulo I/Marco", "content": ""},
            {"path": "Capitulo I/Marco", "content": "  "},
            {"path": "Capitulo I/Marco", "content": "Valido"},
        ]
    }

    out = _adapt_ai_result_for_gicatesis(ai_result)
    assert len(out["sections"]) == 1
    assert all(s["content"].strip() for s in out["sections"])


def test_values_with_title_falls_back_to_project_title():
    project = {"title": "Titulo real de tesis"}
    values = {"tema": "IA aplicada"}
    enriched = _values_with_title(project, values)
    assert enriched["title"] == "Titulo real de tesis"
    assert enriched["tema"] == "IA aplicada"


def test_values_with_title_keeps_existing_title():
    project = {"title": "Titulo del proyecto"}
    values = {"title": "Titulo definido en values"}
    enriched = _values_with_title(project, values)
    assert enriched["title"] == "Titulo definido en values"


def test_values_with_title_forces_unac_project_cover_labels():
    project = {
        "title": "Titulo del proyecto",
        "formatId": "unac-proyecto-cuant",
        "university": "unac",
        "category": "Proyecto de Tesis",
        "variables": {"titulo": "Titulo del proyecto"},
    }
    values = {"tipo_documento": "Tesis de Maestría"}

    enriched = _values_with_title(project, values)

    assert enriched["tipo_documento"] == "PROYECTO DE INVESTIGACIÓN"
    assert enriched["facultad"] == "ESCUELA DE POSGRADO"
    assert enriched["escuela"] == "UNIDAD DE POSGRADO DE LA FACULTAD DE INGENIERÍA MECÁNICA Y DE ENERGÍA"


def test_adapter_drops_toc_sections():
    """Sections with TOC/index paths must be dropped even if content is nonempty."""
    ai_result = {
        "sections": [
            {
                "sectionId": "sec-0001",
                "path": "ÍNDICE",
                "content": "contenido que no debería estar",
            },
            {
                "sectionId": "sec-0002",
                "path": "ÍNDICE/I. PLANTEAMIENTO",
                "content": "contenido bajo índice",
            },
            {
                "sectionId": "sec-0003",
                "path": "ÍNDICE DE TABLAS",
                "content": "contenido tabla",
            },
            {
                "sectionId": "sec-0004",
                "path": "I. PLANTEAMIENTO/1.1 Problema",
                "content": "Contenido legit del capitulo",
            },
        ]
    }

    out = _adapt_ai_result_for_gicatesis(ai_result)
    assert len(out["sections"]) == 1
    assert out["sections"][0]["sectionId"] == "sec-0004"
    assert out["sections"][0]["path"] == "I. PLANTEAMIENTO/1.1 Problema"


def test_adapter_drops_accented_indice():
    """ÍNDICE with accent must also be dropped."""
    ai_result = {
        "sections": [
            {"sectionId": "s1", "path": "ÍNDICE DE FIGURAS", "content": "x"},
            {"sectionId": "s2", "path": "Introduccion", "content": "Texto real"},
        ]
    }
    out = _adapt_ai_result_for_gicatesis(ai_result)
    assert len(out["sections"]) == 1
    assert out["sections"][0]["sectionId"] == "s2"


def test_adapter_keeps_schedule_budget_tables_and_drops_template_owned_annex():
    ai_result = {
        "sections": [
            {
                "sectionId": "sec-crono-resumen",
                "path": "IV. METODOLOGÍA DEL PROYECTO/Cronograma Resumido de Actividades",
                "content": [
                    {
                        "tipo": "tabla",
                        "titulo": "Tabla 4.1 Cronograma Resumido de Actividades",
                        "encabezados": ["Actividad", "Mes 1", "Mes 2"],
                        "filas": [["Revision", "X", ""]],
                    }
                ],
            },
            {
                "sectionId": "sec-crono-5",
                "path": "V. CRONOGRAMA DE ACTIVIDADES",
                "content": [_canonical_schedule_table()],
            },
            {
                "sectionId": "sec-budget",
                "path": "VI. PRESUPUESTO/Presupuesto del Proyecto",
                "content": [
                    {
                        "tipo": "tabla",
                        "titulo": "Presupuesto IA defectuoso",
                        "encabezados": ["Rubro", "Costo"],
                        "filas": [["Sensores", "18000"]],
                    }
                ],
            },
            {
                "sectionId": "sec-annex",
                "path": "ANEXOS/Anexo 1: Matriz de consistencia",
                "content": [
                    {
                        "tipo": "tabla",
                        "titulo": "Matriz IA defectuosa",
                        "encabezados": ["Variable"],
                        "filas": [["Contenido mal ubicado"]],
                    }
                ],
            },
            {
                "sectionId": "sec-bases",
                "path": "II. REVISIÓN DE LITERATURA/2.2 Bases teóricas",
                "content": [
                    {"tipo": "parrafo", "texto": "Contenido válido de bases teóricas."},
                ],
            },
        ]
    }

    out = _adapt_ai_result_for_gicatesis(ai_result)
    paths = [item["path"] for item in out["sections"]]
    assert "IV. METODOLOGÍA DEL PROYECTO/Cronograma Resumido de Actividades" not in paths
    assert "V. CRONOGRAMA DE ACTIVIDADES" in paths
    assert "VI. PRESUPUESTO" in paths
    assert "ANEXOS/Anexo 1: Matriz de consistencia" not in paths
    assert "II. REVISIÓN DE LITERATURA/2.2 Bases teóricas" in paths


def test_build_render_payload_accepts_canonical_schedule_and_budget_tables():
    payload = _build_render_payload(
        format_id="unac-proyecto-cuant",
        values={"title": "Titulo"},
        ai_result_raw={
            "sections": [
                {
                    "sectionId": "sec-crono",
                    "path": "V. CRONOGRAMA DE ACTIVIDADES",
                    "content": [_canonical_schedule_table()],
                },
                {
                    "sectionId": "sec-pres",
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
                        },
                    ],
                },
            ]
        },
        selected_sections=[
            {"section_path": "V. CRONOGRAMA DE ACTIVIDADES"},
            {"section_path": "VI. PRESUPUESTO"},
        ],
    )

    paths = [item["path"] for item in payload["aiResult"]["sections"]]
    assert "V. CRONOGRAMA DE ACTIVIDADES" in paths
    assert "VI. PRESUPUESTO" in paths


def test_adapter_drops_static_bases_matrices_with_accents():
    ai_result = {
        "sections": [
            {
                "sectionId": "sec-matrix-1",
                "path": "II. MARCO TEÓRICO/2.2 Bases teóricas/Matriz de Consistencia de Implementación",
                "content": "No debe aparecer.",
            },
            {
                "sectionId": "sec-matrix-2",
                "path": "II. MARCO TEÓRICO/2.2 Bases teóricas/Matriz de Operacionalización de Diseño",
                "content": "No debe aparecer.",
            },
            {
                "sectionId": "sec-ok",
                "path": "II. MARCO TEÓRICO/2.2 Bases teóricas",
                "content": "Contenido válido de bases teóricas.",
            },
        ]
    }

    out = _adapt_ai_result_for_gicatesis(ai_result)
    paths = [item["path"] for item in out["sections"]]
    assert "II. MARCO TEÓRICO/2.2 Bases teóricas" in paths
    assert all("Matriz de Consistencia de Implementación" not in path for path in paths)
    assert all("Matriz de Operacionalización de Diseño" not in path for path in paths)


def test_build_render_payload_preserves_ai_sections():
    payload = _build_render_payload(
        format_id="unac-proyecto-cual",
        values={"title": "Titulo"},
        ai_result_raw={
            "sections": [
                {
                    "sectionId": "sec-0001",
                    "path": "I. PLANTEAMIENTO/1.1 Problema",
                    "content": "Texto generado por IA.",
                }
            ]
        },
    )

    assert payload["formatId"] == "unac-proyecto-cual"
    assert payload["mode"] == "simulation"
    assert "definition" not in payload
    assert payload["aiResult"]["sections"][0]["content"] == "Texto generado por IA."


def test_build_render_payload_restores_empty_section_from_generation_phase():
    payload = _build_render_payload(
        format_id="unac-proyecto-cual",
        values={"title": "Titulo"},
        ai_result_raw={
            "sections": [
                {
                    "sectionId": "sec-0010",
                    "path": "II. MARCO TEORICO/2.2 Bases teoricas",
                    "content": "",
                }
            ]
        },
        generation_phase={
            "sections": [
                {
                    "section_id": "sec-0010",
                    "section_path": "II. MARCO TEORICO/2.2 Bases teoricas",
                    "ai_output": "Bases teoricas recuperadas desde el rastro de generacion.",
                }
            ]
        },
    )

    sections = payload["aiResult"]["sections"]
    assert len(sections) == 1
    assert sections[0]["path"] == "II. MARCO TEORICO/2.2 Bases teoricas"
    assert sections[0]["content"] == "Bases teoricas recuperadas desde el rastro de generacion."


def test_build_render_payload_recovers_structured_formula_from_generation_phase():
    payload = _build_render_payload(
        format_id="unac-proyecto-cual",
        values={"title": "Titulo"},
        ai_result_raw={"sections": []},
        generation_phase={
            "sections": [
                {
                    "section_id": "sec-0010",
                    "section_path": "II. MARCO TEORICO/2.2 Bases teoricas",
                    "ai_output": (
                        "El indicador se define antes de la ecuacion.\n\n"
                        "<<<FORMULA_JSON\n"
                        "{\"tipo\":\"formula\",\"texto\":\"MTBF = sum(t_z) / n\",\"numero\":\"(3)\"}\n"
                        "FORMULA_JSON>>>"
                    ),
                }
            ]
        },
    )

    content = payload["aiResult"]["sections"][0]["content"]
    assert isinstance(content, list)
    assert [item["tipo"] for item in content] == ["parrafo", "formula"]


def test_build_render_payload_includes_selected_sections_for_render_pruning():
    payload = _build_render_payload(
        format_id="unac-proyecto-cuant",
        values={"title": "Titulo"},
        ai_result_raw={
            "sections": [
                {
                    "sectionId": "sec-0014",
                    "path": "III. HIPOTESIS Y VARIABLES/3.1 Hipotesis",
                    "content": "Hipotesis generada.",
                }
            ]
        },
        selected_sections=[
            {"section_path": "Título + Información Básica"},
            {"section_path": "III. HIPOTESIS Y VARIABLES/3.1 Hipotesis"},
        ],
    )

    selected = payload["selectedSections"]
    assert len(selected) == 2
    assert selected[0]["section_path"] == "Título + Información Básica"
    assert selected[1]["section_path"] == "III. HIPOTESIS Y VARIABLES/3.1 Hipotesis"


def test_build_render_payload_preserves_normalized_matriz_consistencia():
    payload = _build_render_payload(
        format_id="unac-proyecto-cuant",
        values={
            "titulo": "Titulo del proyecto de tesis",
            "variable_independiente": "Sistema de mantenimiento",
            "variable_dependiente": "Disponibilidad operativa",
            "tipo": "Aplicada",
            "nivel_investigacion": "Explicativo",
            "enfoque": "Cuantitativo",
            "diseno_investigacion": "Preexperimental",
            "poblacion": "Equipos criticos",
            "muestra": "12 equipos",
            "matriz_consistencia": {
                "problema_general": "PG",
                "objetivo_general": "OG",
                "hipotesis_general": "HG",
                "problemas_especificos": ["PE1", "PE2", "PE3"],
                "objetivos_especificos": ["OE1", "OE2", "OE3"],
                "hipotesis_especificas": ["HE1", "HE2", "HE3"],
                "dimensiones_variable_independiente": ["Planificacion", "Ejecucion"],
                "dimensiones_variable_dependiente": ["Confiabilidad", "Mantenibilidad"],
                "tecnicas": "Observacion directa",
                "instrumentos": "Ficha de registro",
                "procesamiento_datos": "Analisis estadistico",
            },
        },
        ai_result_raw={"sections": []},
    )

    values = payload["values"]
    matrix = values["matriz_consistencia"]
    assert values["titulo"] == "Titulo del proyecto de tesis"
    assert matrix["problema_general"] == "PG"
    assert matrix["problemas_especificos"] == ["PE1", "PE2", "PE3"]
    assert matrix["objetivos_especificos"] == ["OE1", "OE2", "OE3"]
    assert matrix["hipotesis_especificas"] == ["HE1", "HE2", "HE3"]
    assert matrix["variable_independiente"] == "Sistema de mantenimiento"
    assert matrix["variable_dependiente"] == "Disponibilidad operativa"
    assert matrix["tipo_investigacion"] == "Aplicada"
    assert matrix["nivel_investigacion"] == "Explicativo"
    assert matrix["enfoque_investigacion"] == "Cuantitativo"
    assert matrix["diseno"] == "Preexperimental"
    assert matrix["problemas"]["general"] == "PG"
    assert matrix["problemas"]["especificos"] == ["PE1", "PE2", "PE3"]
    assert matrix["objetivos"]["especificos"] == ["OE1", "OE2", "OE3"]
    assert matrix["hipotesis"]["especificos"] == ["HE1", "HE2", "HE3"]
    assert matrix["variables"]["independiente"]["nombre"] == "Sistema de mantenimiento"
    assert matrix["variables"]["independiente"]["dimensiones"] == ["Planificacion", "Ejecucion"]
    assert matrix["variables"]["dependiente"]["nombre"] == "Disponibilidad operativa"
    assert matrix["metodologia"]["tipo"] == "Aplicada"
    assert matrix["metodologia"]["diseno"] == "Preexperimental"
    assert "matriz_consistencia_tabla" not in values

    sections = payload["aiResult"]["sections"]
    assert all("Matriz de consistencia" not in section["path"] for section in sections)
    assert all(section["path"] != "V. CRONOGRAMA DE ACTIVIDADES" for section in sections)
    assert all(section["path"] != "VI. PRESUPUESTO" for section in sections)

def test_build_render_payload_preserves_dynamic_schedule_and_budget_tables():
    payload = _build_render_payload(
        format_id="unac-proyecto-cuant",
        values={"title": "Titulo del proyecto"},
        ai_result_raw={
            "sections": [
                {
                    "sectionId": "sec-cronograma",
                    "path": "V. CRONOGRAMA DE ACTIVIDADES",
                    "content": [_canonical_schedule_table()],
                },
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
                },
            ]
        },
    )

    sections = payload["aiResult"]["sections"]
    schedule_section = next(section for section in sections if section["path"] == "V. CRONOGRAMA DE ACTIVIDADES")
    budget_section = next(section for section in sections if section["path"] == "VI. PRESUPUESTO")
    assert schedule_section["content"][0]["id"] == "tabla_5_1_cronograma_actividades"
    assert len(schedule_section["content"][0]["encabezados"]) == 13
    assert schedule_section["content"][0]["encabezados"][1] == "2025"
    assert schedule_section["content"][0]["encabezados"][2:] == [""] * 11
    assert len(schedule_section["content"][0]["filas"][0]) == 13
    assert schedule_section["content"][0]["filas"][0][1:] == [
        "Ene",
        "Feb",
        "Mar",
        "Abr",
        "May",
        "Jun",
        "Jul",
        "Ago",
        "Set",
        "Oct",
        "Nov",
        "Dic",
    ]
    assert len(schedule_section["content"][0]["filas"]) == 35
    assert budget_section["content"][0]["id"] == "tabla_6_1_presupuesto_investigacion"
    assert len(budget_section["content"][0]["filas"]) == 14


def test_build_render_payload_raises_when_selected_schedule_budget_lack_valid_ai_tables():
    with pytest.raises(RenderPayloadValidationError):
        _build_render_payload(
            format_id="unac-proyecto-cuant",
            values={"title": "Titulo del proyecto"},
            ai_result_raw={"sections": []},
            selected_sections=[
                {"section_path": "V. CRONOGRAMA DE ACTIVIDADES"},
                {"section_path": "VI. PRESUPUESTO"},
            ],
        )


def test_build_render_payload_rescues_legacy_schedule_shape_even_if_section_exists():
    invalid_schedule = _canonical_schedule_table()
    invalid_schedule["encabezados"] = ["FASES Y ACTIVIDADES", "Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Set", "Oct", "Nov", "Dic"]
    invalid_schedule["filas"][0] = [""] * 14

    payload = _build_render_payload(
        format_id="unac-proyecto-cuant",
        values={"title": "Titulo del proyecto"},
        ai_result_raw={
            "sections": [
                {
                    "sectionId": "sec-cronograma",
                    "path": "V. CRONOGRAMA DE ACTIVIDADES",
                    "content": [invalid_schedule],
                }
            ]
        },
        selected_sections=[{"section_path": "V. CRONOGRAMA DE ACTIVIDADES"}],
    )
    schedule_section = next(section for section in payload["aiResult"]["sections"] if section["path"] == "V. CRONOGRAMA DE ACTIVIDADES")
    assert schedule_section["content"][0]["subtipo"] == "cronograma_actividades"
    assert len(schedule_section["content"][0]["filas"]) == 35


def test_build_render_payload_rescues_legacy_budget_shape_even_if_section_exists():
    invalid_budget = {
        "tipo": "tabla",
        "id": "tabla_invalida",
        "titulo": "Presupuesto",
        "encabezados": ["Rubro", "Descripción", "Costo estimado (S/.)", "Fuente de financiamiento"],
        "filas": [
            ["Materiales y equipos", "Laptop y software de análisis", "8,500.00", "Recursos propios"],
            ["Servicios", "Internet y movilidad", "1,600.00", "Recursos propios"],
            ["Contingencia", "Reserva operativa", "370.00", "Recursos propios"],
        ],
    }

    payload = _build_render_payload(
        format_id="unac-proyecto-cuant",
        values={"title": "Titulo del proyecto"},
        ai_result_raw={
            "sections": [
                {
                    "sectionId": "sec-presupuesto",
                    "path": "VI. PRESUPUESTO",
                    "content": [invalid_budget],
                }
            ]
        },
        selected_sections=[{"section_path": "VI. PRESUPUESTO"}],
    )

    budget_section = next(section for section in payload["aiResult"]["sections"] if section["path"] == "VI. PRESUPUESTO")
    budget_table = budget_section["content"][0]
    assert budget_table["subtipo"] == "presupuesto_investigacion"
    assert budget_table["orientacion"] == "portrait"
    assert len(budget_table["encabezados"]) == 5
    assert len(budget_table["filas"]) == 14


def test_build_render_payload_canonicalizes_figure_placeholder():
    payload = _build_render_payload(
        format_id="unac-proyecto-cual",
        values={"title": "Titulo"},
        ai_result_raw={
            "sections": [
                {
                    "sectionId": "sec-0002",
                    "path": "II. MARCO TEORICO/2.1 Bases teoricas",
                    "content": [
                        {
                            "tipo": "figura",
                            "caption": "Figura 1. Modelo conceptual.",
                            "ruta_placeholder": "placeholder",
                            "fuente": "Elaboración propia.",
                            "nota": "Guía para elaborar la figura: Debe mostrarse debajo de la fuente.",
                            "nota_color": "0000FF",
                        }
                    ],
                }
            ]
        },
    )

    content = payload["aiResult"]["sections"][0]["content"]
    assert isinstance(content, list)
    assert content[0]["ruta_placeholder"] == "assets/placeholder_figura.png"
    assert content[0]["fuente"] == "Elaboración propia."
    assert content[0]["nota"] == "Guía para elaborar la figura: Debe mostrarse debajo de la fuente."
    assert content[0]["nota_color"] == "0000FF"


def test_build_render_payload_accepts_formula_blocks():
    payload = _build_render_payload(
        format_id="unac-proyecto-cuant",
        values={"title": "Titulo"},
        ai_result_raw={
            "sections": [
                {
                    "sectionId": "sec-bases",
                    "path": "II. MARCO TEORICO/2.2 Bases teoricas",
                    "content": [
                        {
                            "tipo": "formula",
                            "id": "eq_2_1_npr",
                            "texto": "NPR = S x O x D",
                            "latex": "NPR = S \\\\times O \\\\times D",
                            "numero": "(1)",
                            "alineacion": "center",
                        }
                    ],
                }
            ]
        },
    )

    content = payload["aiResult"]["sections"][0]["content"]
    assert isinstance(content, list)
    assert content[0]["tipo"] == "formula"
    assert content[0]["numero"] == "(1)"


def test_adapter_preserves_reality_problem_figures():
    ai_result = {
        "sections": [
            {
                "sectionId": "sec-problem",
                "path": "I. PLANTEAMIENTO DEL PROBLEMA/1.1 Descripcion de la realidad problematica",
                "content": [
                    {"tipo": "parrafo", "texto": "Diagnostico tecnico suficiente."},
                    {
                        "tipo": "figura",
                        "titulo": "Diagrama de Pareto de modos de falla en flota CAT 24M",
                        "caption": "Diagrama de Pareto de modos de falla en flota CAT 24M",
                        "ruta_placeholder": "assets/placeholder_figura.png",
                    },
                ],
            }
        ]
    }

    out = _adapt_ai_result_for_gicatesis(ai_result)
    content = out["sections"][0]["content"]
    assert isinstance(content, list)
    assert content[1]["tipo"] == "figura"


def test_build_render_payload_raises_for_invalid_structured_block():
    with pytest.raises(RenderPayloadValidationError):
        _build_render_payload(
            format_id="unac-proyecto-cual",
            values={"title": "Titulo"},
            ai_result_raw={
                "sections": [
                    {
                        "sectionId": "sec-0003",
                        "path": "V. RESULTADOS/5.1 Tabla de resultados",
                        "content": [
                            {
                                "tipo": "tabla",
                                "encabezados": [],
                                "filas": [],
                            }
                        ],
                    }
                ]
            },
        )


def test_adapter_moves_top_level_parent_content_into_first_child():
    ai_result = {
        "sections": [
            {
                "sectionId": "sec-0100",
                "path": "I. PLANTEAMIENTO DEL PROBLEMA",
                "content": "Contenido general del capitulo.",
            },
            {
                "sectionId": "sec-0101",
                "path": "I. PLANTEAMIENTO DEL PROBLEMA/1.1 Descripcion",
                "content": "Contenido especifico 1.1.",
            },
        ]
    }

    out = _adapt_ai_result_for_gicatesis(ai_result)
    sections = out["sections"]
    assert len(sections) == 1
    assert sections[0]["path"] == "I. PLANTEAMIENTO DEL PROBLEMA/1.1 Descripcion"
    assert "Contenido general del capitulo." in sections[0]["content"]
    assert "Contenido especifico 1.1." in sections[0]["content"]


def test_adapter_flattens_structured_content_for_text_only_sections():
    ai_result = {
        "sections": [
            {
                "sectionId": "sec-intro",
                "path": "Introduccion",
                "content": [
                    {"tipo": "parrafo", "texto": "Texto introductorio limpio."},
                    {
                        "tipo": "tabla",
                        "titulo": "Tabla que no debe salir",
                        "encabezados": ["A", "B"],
                        "filas": [["1", "2"]],
                    },
                    {"tipo": "figura", "caption": "Figura que no debe salir"},
                ],
            }
        ]
    }

    out = _adapt_ai_result_for_gicatesis(ai_result)
    content = out["sections"][0]["content"]
    assert isinstance(content, str)
    assert content == "Texto introductorio limpio."


def test_adapter_flattens_structured_content_for_non_allowed_sections():
    ai_result = {
        "sections": [
            {
                "sectionId": "sec-problema",
                "path": "I. PLANTEAMIENTO DEL PROBLEMA/1.1 Descripcion",
                "content": [
                    {"tipo": "parrafo", "texto": "Texto del problema."},
                    {"tipo": "figura", "caption": "Figura que no corresponde."},
                ],
            }
        ]
    }

    out = _adapt_ai_result_for_gicatesis(ai_result)
    assert out["sections"][0]["content"] == "Texto del problema."


def test_adapter_operationalization_keeps_only_bridge_text():
    ai_result = {
        "sections": [
            {
                "sectionId": "sec-op",
                "path": "III. HIPOTESIS Y VARIABLES/3.2 Operacionalizacion de variable",
                "content": [
                    {"tipo": "parrafo", "texto": "Puente breve de operacionalizacion."},
                    {
                        "tipo": "tabla",
                        "titulo": "Tabla 3.1 Operacionalizacion de la variable independiente",
                        "encabezados": ["A"],
                        "filas": [["1"]],
                    },
                ],
            }
        ]
    }

    out = _adapt_ai_result_for_gicatesis(ai_result)
    content = out["sections"][0]["content"]
    assert isinstance(content, str)
    assert content == "Puente breve de operacionalizacion."


def test_adapter_operationalization_injects_bridge_when_only_tables_arrive():
    ai_result = {
        "sections": [
            {
                "sectionId": "sec-op2",
                "path": "III. HIPOTESIS Y VARIABLES/3.2 Operacionalizacion de variable",
                "content": [
                    {
                        "tipo": "tabla",
                        "titulo": "Tabla 3.1 Operacionalizacion de la variable independiente",
                        "encabezados": ["A"],
                        "filas": [["1"]],
                    }
                ],
            }
        ]
    }

    out = _adapt_ai_result_for_gicatesis(ai_result)
    content = out["sections"][0]["content"]
    assert isinstance(content, str)
    assert "Tablas 3.1 y 3.2" in content


def test_adapter_keeps_structured_content_for_allowed_sections():
    ai_result = {
        "sections": [
            {
                "sectionId": "sec-marco",
                "path": "II. MARCO TEORICO/2.1 Bases teoricas",
                "content": [
                    {
                        "tipo": "parrafo",
                        "texto": (
                            "El desarrollo teorico explica primero el modelo, sus componentes, su relacion con "
                            "las variables del estudio y la razon academica por la que el esquema visual aparece "
                            "despues del concepto."
                        ),
                    },
                    {"tipo": "figura", "caption": "Figura 1. Modelo conceptual."},
                ],
            }
        ]
    }

    out = _adapt_ai_result_for_gicatesis(ai_result)
    content = out["sections"][0]["content"]
    assert isinstance(content, list)
    assert [item["tipo"] for item in content] == ["parrafo", "figura"]


def test_adapter_keeps_formula_content_for_chapter_two_bases():
    ai_result = {
        "sections": [
            {
                "sectionId": "sec-bases",
                "path": "II. MARCO TEORICO/2.2 Bases teoricas",
                "content": [
                    {
                        "tipo": "parrafo",
                        "texto": (
                            "El indicador se define antes de presentar la formula, precisando sus variables, "
                            "la unidad de analisis, el sentido de interpretacion y la utilidad para comparar "
                            "el comportamiento del objeto de estudio."
                        ),
                    },
                    {"tipo": "formula", "texto": "MTBF = sum(t_z) / n", "numero": "(3)"},
                ],
            }
        ]
    }

    out = _adapt_ai_result_for_gicatesis(ai_result)
    content = out["sections"][0]["content"]
    assert isinstance(content, list)
    assert [item["tipo"] for item in content] == ["parrafo", "formula"]


def test_adapter_keeps_only_schema_formula_for_chapter_four_design():
    ai_result = {
        "sections": [
            {
                "sectionId": "sec-diseno",
                "path": "IV. METODOLOGIA DEL PROYECTO/4.1 Diseno metodologico",
                "content": [
                    {"tipo": "parrafo", "texto": "El esquema del diseno se representa de la siguiente manera."},
                    {"tipo": "formula", "texto": "M O1 X O2", "alineacion": "center"},
                    {"tipo": "figura", "caption": "Figura 4.1 Esquema del diseno preexperimental"},
                    {
                        "tipo": "tabla",
                        "titulo": "Tabla 4.1 Matriz de consistencia metodologica",
                        "encabezados": ["Elemento"],
                        "filas": [["Diseno"]],
                    },
                ],
            }
        ]
    }

    out = _adapt_ai_result_for_gicatesis(ai_result)
    content = out["sections"][0]["content"]
    assert isinstance(content, list)
    assert [item["tipo"] for item in content] == ["parrafo", "formula"]


def test_adapter_flattens_chapter_four_text_sections():
    ai_result = {
        "sections": [
            {
                "sectionId": "sec-tecnicas",
                "path": "IV. METODOLOGIA DEL PROYECTO/4.5 Tecnicas e instrumentos",
                "content": [
                    {"tipo": "parrafo", "texto": "Texto denso de tecnicas e instrumentos."},
                    {"tipo": "figura", "caption": "Flujo metodologico del estudio sobre el titulo."},
                    {
                        "tipo": "tabla",
                        "titulo": "Tabla 4.2 Tecnicas e instrumentos de recoleccion de datos",
                        "encabezados": ["Tecnica"],
                        "filas": [["Analisis documental"]],
                    },
                ],
            }
        ]
    }

    out = _adapt_ai_result_for_gicatesis(ai_result)
    assert out["sections"][0]["content"] == "Texto denso de tecnicas e instrumentos."


def test_adapter_flattens_structured_content_for_chapter_two_conceptual_frame():
    ai_result = {
        "sections": [
            {
                "sectionId": "sec-conceptual",
                "path": "II. MARCO TEORICO/2.3 Marco conceptual",
                "content": [
                    {"tipo": "parrafo", "texto": "Variable independiente: RCM."},
                    {"tipo": "figura", "caption": "Mapa conceptual del estudio."},
                    {"tipo": "formula", "texto": "MTBF = sum(t_z) / n"},
                ],
            }
        ]
    }

    out = _adapt_ai_result_for_gicatesis(ai_result)
    assert out["sections"][0]["content"] == "Variable independiente: RCM."


def test_adapter_keeps_structured_content_for_discussion_sections():
    ai_result = {
        "sections": [
            {
                "sectionId": "sec-disc",
                "path": "VI. DISCUSION DE RESULTADOS/6.1 Discusion",
                "content": [
                    {"tipo": "parrafo", "texto": "La discusion contrasta hallazgos con antecedentes relevantes."},
                    {"tipo": "figura", "caption": "Relacion entre hallazgos y antecedentes."},
                ],
            }
        ]
    }

    out = _adapt_ai_result_for_gicatesis(ai_result)
    content = out["sections"][0]["content"]
    assert isinstance(content, list)
    assert [item["tipo"] for item in content] == ["parrafo", "figura"]


def test_adapter_merges_parent_structured_content_into_first_child():
    ai_result = {
        "sections": [
            {
                "sectionId": "sec-met-parent",
                "path": "III. METODOLOGIA",
                "content": [
                    {"tipo": "parrafo", "texto": "Contexto metodologico."},
                    {
                        "tipo": "tabla",
                        "titulo": "Tabla 1. Variables",
                        "encabezados": ["Variable", "Indicador"],
                        "filas": [["A", "I1"]],
                    },
                ],
            },
            {
                "sectionId": "sec-met-child",
                "path": "III. METODOLOGIA/3.1 Diseno",
                "content": "Texto especifico del diseno.",
            },
        ]
    }

    out = _adapt_ai_result_for_gicatesis(ai_result)
    assert len(out["sections"]) == 1
    content = out["sections"][0]["content"]
    assert isinstance(content, list)
    assert content[0]["tipo"] == "parrafo"
    assert content[1]["tipo"] == "tabla"
    assert content[2]["tipo"] == "parrafo"


def test_adapter_drops_old_raw_structured_string_payloads():
    ai_result = {
        "sections": [
            {
                "sectionId": "sec-bad",
                "path": "II. MARCO TEORICO/2.1 Bases teoricas",
                "content": "[{'tipo': 'tabla', 'titulo': 'Tabla rota'}]",
            },
            {
                "sectionId": "sec-good",
                "path": "II. MARCO TEORICO/2.2 Antecedentes",
                "content": "Texto valido.",
            },
        ]
    }

    out = _adapt_ai_result_for_gicatesis(ai_result)
    assert len(out["sections"]) == 1
    assert out["sections"][0]["sectionId"] == "sec-good"


def test_adapter_strips_raw_structured_lines_from_old_mixed_strings():
    ai_result = {
        "sections": [
            {
                "sectionId": "sec-mixed",
                "path": "II. MARCO TEORICO/2.1 Bases teoricas",
                "content": ("Texto valido antes.\n{'tipo': 'figura', 'caption': 'Figura rota'}\nTexto valido despues."),
            }
        ]
    }

    out = _adapt_ai_result_for_gicatesis(ai_result)
    content = out["sections"][0]["content"]
    assert isinstance(content, str)
    assert "tipo" not in content
    assert "Texto valido antes." in content
    assert "Texto valido despues." in content


def test_extract_resume_seed_sections_preserves_structured_content():
    seeds = _extract_resume_seed_sections(
        {
            "sections": [
                {
                    "sectionId": "sec-1",
                    "path": "Cronograma",
                    "content": [
                        {"tipo": "parrafo", "texto": "Texto previo."},
                        {
                            "tipo": "tabla",
                            "titulo": "Cronograma",
                            "encabezados": ["Actividad", "Mes 1"],
                            "filas": [["Revision", "X"]],
                        },
                    ],
                }
            ]
        }
    )

    assert len(seeds) == 1
    assert isinstance(seeds[0]["content"], list)

def test_build_render_payload_canonicalizes_schedule_and_budget_child_selections():
    payload = _build_render_payload(
        format_id="unac-proyecto-cuant",
        values={"title": "Titulo"},
        ai_result_raw={
            "sections": [
                {
                    "sectionId": "sec-cronograma",
                    "path": "V. CRONOGRAMA DE ACTIVIDADES/Cronograma Detallado de Actividades",
                    "content": [_canonical_schedule_table()],
                },
                {
                    "sectionId": "sec-presupuesto",
                    "path": "VI. PRESUPUESTO/Presupuesto del Proyecto",
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
                },
            ]
        },
        selected_sections=[
            {"section_path": "V. CRONOGRAMA DE ACTIVIDADES/Cronograma de ejecucion"},
            {"section_path": "V. CRONOGRAMA DE ACTIVIDADES/Cronograma Detallado de Actividades"},
            {"section_path": "VI. PRESUPUESTO/Recursos y Presupuesto"},
            {"section_path": "VI. PRESUPUESTO/Presupuesto del Proyecto"},
        ],
    )

    selected_paths = [str(item.get("section_path") or "") for item in payload["selectedSections"]]
    assert "V. CRONOGRAMA DE ACTIVIDADES" in selected_paths
    assert "VI. PRESUPUESTO" in selected_paths
    assert all(not path.startswith("V. CRONOGRAMA DE ACTIVIDADES/") for path in selected_paths)
    assert all(not path.startswith("VI. PRESUPUESTO/") for path in selected_paths)
