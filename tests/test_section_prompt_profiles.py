from app.core.services.ai.section_prompt_profiles import (
    build_format_editorial_contract,
    build_section_editorial_context,
    build_stable_project_memory_snapshot,
)


def _sample_values() -> dict:
    return {
        "title": "PLAN DE MANTENIMIENTO CENTRADO EN CONFIABILIDAD PARA MEJORAR LA DISPONIBILIDAD INHERENTE",
        "titulo": "PLAN DE MANTENIMIENTO CENTRADO EN CONFIABILIDAD PARA MEJORAR LA DISPONIBILIDAD INHERENTE",
        "tema": "PLAN DE MANTENIMIENTO CENTRADO EN CONFIABILIDAD PARA MEJORAR LA DISPONIBILIDAD INHERENTE",
        "linea_investigacion": "Gerencia de mantenimiento",
        "objeto_estudio": "flota de motoniveladoras CAT 24M",
        "variable_independiente": "Mantenimiento centrado en la confiabilidad",
        "variable_dependiente": "Disponibilidad inherente",
        "tipo": "Aplicada",
        "enfoque": "Cuantitativo",
        "diseno_investigacion": "Preexperimental",
        "nivel_investigacion": "Explicativo",
        "poblacion": "05 motoniveladoras CAT 24M",
        "muestra": "Muestra censal (n=5)",
        "lugar_ejecucion": "Unidad minera en Junin",
        "unidad_analisis": "Equipos de mantenimiento",
        "temporal": "2025",
        "matriz_consistencia": {
            "problema_general": (
                "¿De que manera el plan RCM mejorara la disponibilidad inherente de la flota CAT 24M en 2025?"
            ),
            "objetivo_general": (
                "Determinar como el plan RCM mejorara la disponibilidad inherente de la flota CAT 24M en 2025."
            ),
            "hipotesis_general": "El plan RCM mejorara la disponibilidad inherente de la flota CAT 24M en 2025.",
            "problemas_especificos": [
                "¿De que manera el plan RCM mejorara la confiabilidad de la flota CAT 24M?",
                "¿De que manera el plan RCM mejorara la mantenibilidad de la flota CAT 24M?",
            ],
            "objetivos_especificos": [
                "Determinar como el plan RCM mejorara la confiabilidad de la flota CAT 24M.",
                "Determinar como el plan RCM mejorara la mantenibilidad de la flota CAT 24M.",
            ],
            "hipotesis_especificas": [
                "El plan RCM mejorara la confiabilidad de la flota CAT 24M.",
                "El plan RCM mejorara la mantenibilidad de la flota CAT 24M.",
            ],
            "dimensiones_variable_independiente": [
                "Taxonomia de equipos",
                "Analisis de criticidad",
                "AMEF",
                "Plan de mantenimiento",
            ],
            "dimensiones_variable_dependiente": [
                "Confiabilidad",
                "Mantenibilidad",
            ],
            "tecnicas": "Analisis documental y observacion directa",
            "instrumentos": "Fichas ISO 14224 y hojas AMEF",
            "procesamiento_datos": "Analisis estadistico de KPI y distribucion Weibull",
        },
        "operacionalizacion_vi": {
            "variable": "Mantenimiento centrado en la confiabilidad",
            "definicion_conceptual": "Metodologia para preservar funciones del activo.",
            "definicion_operacional": "Se operacionaliza mediante taxonomia, criticidad, AMEF y plan de mantenimiento.",
            "filas": [
                {
                    "dimension": "Taxonomia de equipos",
                    "indicador": "Nivel de jerarquia taxonomica",
                    "indice": "Ordinal",
                    "tecnica_instrumentos": "Tecnica: Analisis documental | Instrumento: Fichas ISO 14224",
                },
                {
                    "dimension": "Analisis de criticidad",
                    "indicador": "Nivel de criticidad",
                    "indice": "Ordinal",
                    "tecnica_instrumentos": "Tecnica: Juicio de expertos | Instrumento: Matriz de criticidad",
                },
            ],
        },
        "operacionalizacion_vd": {
            "variable": "Disponibilidad inherente",
            "definicion_conceptual": "Tiempo durante el cual el equipo esta disponible para operar.",
            "definicion_operacional": "Se operacionaliza mediante MTBF y MTTR.",
            "filas": [
                {
                    "dimension": "Confiabilidad",
                    "indicador": "MTBF",
                    "indice": "Razon",
                    "metodo_tecnica": "Tecnica: Analisis de datos",
                },
                {
                    "dimension": "Mantenibilidad",
                    "indicador": "MTTR",
                    "indice": "Razon",
                    "metodo_tecnica": "Tecnica: Analisis de datos",
                },
            ],
        },
    }


def test_build_format_editorial_contract_for_project_quant():
    contract = build_format_editorial_contract("unac-proyecto-cuant")
    assert "Contrato editorial global del formato" in contract
    assert "no una tesis ya concluida" in contract
    assert "sin copiar frases ni parrafos literales" in contract


def test_build_section_editorial_context_for_problem_detail():
    context = build_section_editorial_context(
        format_id="unac-proyecto-cuant",
        section_id="sec-0003",
        section_path="I. PLANTEAMIENTO DEL PROBLEMA/1.1 Descripción de la realidad problemática",
        values=_sample_values(),
    )
    assert "mínimo obligatorio 1276, objetivo 1378 y máximo estricto 1468 palabras narrativas" in context
    assert "Párrafo 1: contexto operativo internacional" in context
    assert "Párrafo 4: contexto local" in context
    assert "No inventes porcentajes de mejora, resultados, Monte Carlo, sensores IoT" in context
    assert "No escribas FIGURE_JSON" in context
    assert "Hechos estructurados relevantes del proyecto:" in context
    assert "Problema general:" in context
    assert "Dimensiones VI:" in context
    assert "Horizonte temporal:" in context
    assert "Problemas especificos:" in context
    assert "cuatro apoyos visuales no numerados" in context
    assert "Pareto cualitativo, Ishikawa, matriz de relevancia y matriz de priorización" in context
    assert "No redactes títulos, fuentes, instrucciones de dibujo ni valores" in context


def test_build_section_editorial_context_for_problem_detail_in_maestria_quant():
    context = build_section_editorial_context(
        format_id="unac-maestria-cuant",
        section_id="sec-0003",
        section_path="I. PLANTEAMIENTO DEL PROBLEMA/1.1 Descripción de la realidad problemática",
        values=_sample_values(),
    )
    assert "Contrato editorial especifico de esta seccion:" in context
    assert "cuatro apoyos visuales no numerados" in context


def test_build_stable_project_memory_snapshot_for_project_quant():
    snapshot = build_stable_project_memory_snapshot("unac-proyecto-cuant", _sample_values())
    assert "titulo=PLAN DE MANTENIMIENTO CENTRADO EN CONFIABILIDAD" in snapshot
    assert "variable_independiente=Mantenimiento centrado en la confiabilidad" in snapshot
    assert "variable_dependiente=Disponibilidad inherente" in snapshot
    assert "problema_general=" in snapshot


def test_build_section_editorial_context_for_delimitaciones_aliases():
    canonical = build_section_editorial_context(
        format_id="unac-proyecto-cuant",
        section_id="sec-delimitaciones",
        section_path="I. PLANTEAMIENTO DEL PROBLEMA/1.5 Delimitaciones de la investigación",
        values=_sample_values(),
    )
    legacy = build_section_editorial_context(
        format_id="unac-proyecto-cuant",
        section_id="sec-delimitantes",
        section_path="I. PLANTEAMIENTO DEL PROBLEMA/1.5 Delimitantes de la investigación",
        values=_sample_values(),
    )

    assert "linea exacta '1.5.1 Delimitacion teorica'" in canonical
    assert "linea exacta '1.5.1 Delimitacion teorica'" in legacy
