"""Tests for app.core.services.ai.ai_service provider routing and fallback."""
# ruff: noqa: E501

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.core.services.ai.ai_service import AIService
from app.core.services.ai.errors import ProviderAuthError, QuotaExceededError
from app.core.services.ai.resilience_router import LLMResult
from app.core.services.ai.unac_quality_profile import requirements_for_section_path


def _settings(
    primary: str = "gemini",
    fallback: bool = True,
    *,
    force_transient_fallback: bool = True,
) -> SimpleNamespace:
    return SimpleNamespace(
        AI_PRIMARY_PROVIDER=primary,
        AI_FALLBACK_ON_QUOTA=fallback,
        AI_FORCE_FALLBACK_ON_TRANSIENT=force_transient_fallback,
        AI_CORRECTION_ENABLED=False,
        GEMINI_MODEL="gemini-2.0-flash",
        MISTRAL_MODEL="mistral-medium-2505",
    )


class _InMemorySelectionStore:
    def __init__(self, provider: str = "gemini", mode: str = "auto") -> None:
        fallback = "mistral" if provider == "gemini" else "gemini"
        self._selection = {
            "provider": provider,
            "model": "gemini-2.0-flash" if provider == "gemini" else "mistral-medium-2505",
            "fallback_provider": fallback,
            "fallback_model": "mistral-medium-2505" if fallback == "mistral" else "gemini-2.0-flash",
            "mode": mode,
        }

    def get_selection(self):
        return dict(self._selection)

    def normalize(self, payload):
        merged = dict(self._selection)
        merged.update(payload or {})
        return dict(merged)

    def set_selection(self, payload):
        self._selection.update(payload or {})
        return dict(self._selection)


def _set_selection(svc: AIService, provider: str, *, mode: str = "auto") -> None:
    fallback = "mistral" if provider == "gemini" else "gemini"
    svc.set_provider_selection(
        {
            "provider": provider,
            "model": "gemini-2.0-flash" if provider == "gemini" else "mistral-medium-2505",
            "fallback_provider": fallback,
            "fallback_model": "mistral-medium-2505" if fallback == "mistral" else "gemini-2.0-flash",
            "mode": mode,
        }
    )


@pytest.fixture
def ai_svc():
    svc = AIService()
    svc._selection_store = _InMemorySelectionStore()
    svc._selection = svc._selection_store.get_selection()
    gemini = MagicMock()
    mistral = MagicMock()
    svc._clients = {"gemini": gemini, "mistral": mistral}
    return svc, gemini, mistral


class _UsageProvider:
    def __init__(self, *, content: str | list[str], usage: dict[str, int] | None = None) -> None:
        self._contents = list(content) if isinstance(content, list) else None
        self._content = content if isinstance(content, str) else ""
        self._usage = dict(usage or {})
        self._calls = 0

    def is_configured(self) -> bool:
        return True

    def generate_with_usage(self, prompt: str, *, timeout: int = 60, model: str | None = None):
        if self._contents is not None:
            index = min(self._calls, len(self._contents) - 1)
            self._calls += 1
            return self._contents[index], dict(self._usage)
        return self._content, dict(self._usage)


class _EstimateOnlyProvider:
    def __init__(self, *, content: str) -> None:
        self._content = content

    def is_configured(self) -> bool:
        return True

    def generate(self, prompt: str, *, timeout: int = 60, model: str | None = None) -> str:
        return self._content


def _figure_json_block(title: str) -> str:
    payload = {
        "tipo": "figura",
        "titulo": title,
        "caption": title,
        "ruta_placeholder": "assets/placeholder_figura.png",
        "fuente": "Elaboracion propia.",
    }
    return f"<<<FIGURE_JSON\n{json.dumps(payload, ensure_ascii=False)}\nFIGURE_JSON>>>"


def test_unac_composite_section_is_generated_by_semantic_unit() -> None:
    svc = AIService()
    svc._generate_with_provider_fallback = MagicMock(
        side_effect=[
            LLMResult(content="2.1.1 Antecedentes internacionales\n\nDesarrollo internacional.", provider="mistral", status="ok"),
            LLMResult(content="2.1.2 Antecedentes nacionales\n\nDesarrollo nacional.", provider="mistral", status="ok"),
        ]
    )
    requirements = requirements_for_section_path("II. MARCO TEÓRICO/2.1 Antecedentes")

    result = svc._generate_unac_semantic_units(
        section_prompt="Redacta antecedentes.",
        requirements=requirements,
        preferred_provider="mistral",
        section_current=9,
        section_total=25,
        section_path="II. MARCO TEÓRICO/2.1 Antecedentes",
        section_id="sec-0009",
        selection={"provider": "mistral", "mode": "fixed"},
        disabled_for_job=set(),
    )

    assert svc._generate_with_provider_fallback.call_count == 2
    first_prompt = svc._generate_with_provider_fallback.call_args_list[0].args[0]
    second_prompt = svc._generate_with_provider_fallback.call_args_list[1].args[0]
    assert "1611 palabras" in first_prompt
    assert "1634 palabras" in second_prompt
    assert "2.1.1 Antecedentes internacionales" in result.content
    assert "2.1.2 Antecedentes nacionales" in result.content


def _valid_reality_problem_raw_response() -> str:
    paragraphs = [
        (
            "En el contexto operativo de la mineria a cielo abierto, la continuidad operativa constituye un "
            "factor determinante para alcanzar los objetivos de produccion. Las vias de acarreo sostienen la "
            "cadena de valor minera porque permiten el desplazamiento continuo de camiones y equipos auxiliares, "
            "mientras que las motoniveladoras CAT 24M conservan la geometria de esas rutas. Cuando aparecen fallas "
            "funcionales imprevistas, la baja disponibilidad afecta ciclos de acarreo, seguridad y costo correctivo. "
            "Por ello, el problema exige una estrategia tecnica centrada en confiabilidad, articulada con datos de "
            "fallas y no con decisiones reactivas aisladas."
        ),
        (
            "En la India, Jakkula et al. (2021) analizaron la confiabilidad, disponibilidad y mantenibilidad de "
            "equipos Load-Haul-Dump en mineria subterranea, identificando subsistemas con confiabilidad reducida "
            "y paradas que incrementaban costos de mantenimiento. En Iran, Nouri et al. (2023) estudiaron un camion "
            "Komatsu en la mina de cobre Sungun y relacionaron las condiciones severas de operacion con menor "
            "disponibilidad, mayor MTTR e interrupciones productivas. Ambos antecedentes evidencian que los equipos "
            "moviles mineros requieren jerarquizar subsistemas criticos, frecuencia de fallas, MTBF, MTTR y "
            "consecuencias operacionales antes de formular tareas de mantenimiento."
        ),
        (
            "En Latinoamerica, Roa et al. (2023), en Colombia, desarrollaron una mejora de mantenimiento para "
            "cargadores frontales Caterpillar 962H con disponibilidad inferior a la meta corporativa. El estudio "
            "aplico Mantenimiento Centrado en Confiabilidad, analisis taxonomico alineado con ISO 14224 y revision "
            "de correctivos frecuentes. Este antecedente conecta con el caso local porque muestra que la falta de "
            "planes basados en confiabilidad mantiene recurrencia de fallas, eleva reparaciones no programadas y "
            "limita la productividad de equipos auxiliares."
        ),
        (
            "En el Peru, Flores (2024) aplico RCM a camiones Caterpillar 785 y reporto una mejora de disponibilidad "
            "inherente de 84,82 % a 88,25 %, demostrando utilidad de la metodologia en maquinaria minera de gran "
            "tonelaje. Chavez (2024), al estudiar perforadoras Everdigm T450, abordo una disponibilidad critica "
            "promedio de 61 %, identifico riesgos funcionales y proyecto mejora del MTBF. Estos casos confirman que "
            "el RCM permite ordenar modos de falla, evaluar mantenibilidad, reducir correctivos y orientar decisiones "
            "tecnicas con indicadores verificables."
        ),
        (
            "A nivel local, la flota de motoniveladoras CAT 24M de Sierra Central registra una Disponibilidad "
            "Inherente promedio de 85 %, frente a un KPI estrategico de 90 %, lo que configura una brecha negativa "
            "de 5 %. El historial de fallas evidencia que el Sistema de Implementos o Mando de Circulo, el Tren de "
            "Potencia y el Sistema Hidraulico concentran 75 % de los eventos de parada. Esta concentracion incrementa "
            "correctivos, prolonga MTTR, reduce MTBF y compromete la continuidad de las vias de acarreo."
        ),
        (
            "Para determinar el origen tecnico de esta desviacion y evitar dispersion de recursos, se aplico un "
            "Diagrama de Pareto al historial de fallas. La herramienta jerarquiza eventos por frecuencia, reconoce "
            "pocos vitales bajo la regla 80/20 y orienta la focalizacion del mantenimiento, tal como se presenta en "
            "la Figura 1.1."
        ),
        (
            "La Figura 1.1 evidencia que el Sistema de Implementos o Mando de Circulo, el Tren de Potencia y el "
            "Sistema Hidraulico agrupan 75 % de los eventos de parada, por lo que constituyen pocos vitales del "
            "problema. La concentracion no solo describe frecuencia, sino impacto sobre Disponibilidad Inherente: "
            "cada falla repetitiva reduce MTBF, eleva MTTR por diagnostico, espera de repuestos y reparacion, y "
            "debilita la continuidad operativa de la flota. Esta lectura justifica focalizar el plan en sistemas "
            "criticos antes de formular cualquier tarea de mantenimiento."
        ),
        (
            "Una vez identificados los sistemas de mayor criticidad, se examino la causa raiz mediante un Diagrama "
            "de Causa-Efecto. El analisis ordena factores tecnicos, humanos, metodologicos, de maquinaria, materiales, "
            "medicion y medio ambiente para explicar la recurrencia de fallas, como se observa en la Figura 1.2."
        ),
        (
            "La Figura 1.2 muestra que el problema es sistemico y que la causa raiz principal se ubica en Metodos. "
            "El mantenimiento actual es rigido, basado en horas motor, y no incorpora condicion real, carga dinamica "
            "ni fallas incipientes. A ello se suma un medio ambiente con polvo, silice abrasiva, altitud, variacion "
            "termica y carga mecanica que acelera desgaste. Por tanto, cambiar componentes no corrige la recurrencia; "
            "se requiere redisenar la estrategia mediante RCM. La lectura causal obliga a pasar de tareas uniformes "
            "a tareas diferenciadas por criticidad, consecuencia operacional y condicion observable del activo."
        ),
        (
            "Ante esta evidencia causal, se evaluaron alternativas como renovacion de flota, sustitucion de "
            "componentes, monitoreo en linea, optimizacion de stock y RCM. La Matriz de Relevancia compara "
            "viabilidad tecnica, "
            "costo de implementacion, sostenibilidad y alineamiento con la causa raiz metodologica, como se muestra "
            "en la Figura 1.3."
        ),
        (
            "La Figura 1.3 permite distinguir alternativas de contencion y alternativas estructurales. La renovacion "
            "anticipada se descarta por alto CAPEX; la sustitucion masiva corrige sintomas inmediatos, pero no reduce "
            "recurrencia; el monitoreo en linea exige inversion tecnologica y capacitacion; y la optimizacion de stock "
            "reduce esperas, pero no baja frecuencia de fallas. El RCM resulta estructural porque interviene modos de "
            "falla, criticidad y tareas preventivas, por lo que justifica pasar a la priorizacion final."
        ),
        (
            "Finalmente, las alternativas viables fueron sometidas a una Matriz de Priorizacion ponderada. Dado que "
            "la brecha principal es la baja disponibilidad, se asigno mayor peso al impacto en disponibilidad, ademas "
            "del costo de implementacion, sostenibilidad y retorno operativo, como se presenta en la Figura 1.4."
        ),
        (
            "La Figura 1.4 valida cuantitativamente la seleccion del RCM. El criterio Impacto en Disponibilidad "
            "recibe un peso de 50 %, mientras que Costo de Implementacion alcanza 30 %. Bajo esa ponderacion, el RCM "
            "obtiene puntaje global 7.9 y supera a la optimizacion de stock, que alcanza 4.6. El stock puede reducir "
            "MTTR por menor espera logistica, pero no evita recurrencia de fallas; el RCM si mejora MTBF y MTTR al "
            "actuar sobre criticidad, modos de falla, tareas preventivas y causas raiz. Por ello, la decision no se "
            "basa solo en disponibilidad inmediata, sino en sostenibilidad tecnica del control de fallas."
        ),
        (
            "En consecuencia, la Variable Independiente corresponde al Plan de Mantenimiento Centrado en "
            "Confiabilidad, desarrollado bajo SAE JA1011:2024, ISO 14224, taxonomia de activos, analisis de "
            "criticidad, AMEF e implementacion del plan. Esta estrategia impacta en la Variable Dependiente, "
            "Disponibilidad Inherente, mediante los indicadores MTBF, MTTR y disponibilidad. El objetivo tecnico es "
            "cerrar la brecha entre 85 % y 90 %, transitando de un modelo correctivo o preventivo rigido hacia un "
            "modelo proactivo basado en criticidad, modos de falla y consecuencias operacionales."
        ),
    ]
    filler = (
        " El desarrollo mantiene coherencia academica, incorpora evidencia tecnica y evita una redaccion resumida "
        "que oculte la relacion entre causa, decision y consecuencia operacional."
    )
    while len(" ".join(paragraphs).split()) < 1325:
        paragraphs[0] += filler
    blocks = [
        paragraphs[0],
        paragraphs[1],
        paragraphs[2],
        paragraphs[3],
        paragraphs[4],
        paragraphs[5],
        _figure_json_block("Diagrama de Pareto de modos de falla en flota CAT 24M"),
        paragraphs[6],
        paragraphs[7],
        _figure_json_block("Analisis de Causa-Efecto de Baja Disponibilidad (Ishikawa)"),
        paragraphs[8],
        paragraphs[9],
        _figure_json_block("Matriz de Relevancia para el filtrado de alternativas de solucion"),
        paragraphs[10],
        paragraphs[11],
        _figure_json_block("Matriz de Priorizacion de soluciones factibles"),
        paragraphs[12],
        paragraphs[13],
    ]
    return "\n\n".join(blocks)


def _project_quant_values() -> dict[str, object]:
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


def _generic_schedule_raw_response() -> str:
    return (
        "<<<TABLE_JSON\n"
        '{"tipo":"tabla","id":"tabla_invalida","titulo":"Cronograma","encabezados":["Actividad","Mes 1","Mes 2"],'
        '"filas":[["Revision","X",""],["Validacion","","X"]]}\n'
        "TABLE_JSON>>>"
    )


def _schedule_blueprint_raw_response() -> str:
    payload = {
        "tipo": "tabla",
        "subtipo": "cronograma_plan",
        "anio": "2025",
        "fases": [
            {
                "numero": index,
                "titulo": title,
                "actividades": [
                    {
                        "numero": f"{index}.{activity_index}",
                        "titulo": activity_title,
                        "mes_inicio": month_start,
                        "mes_fin": month_end,
                    }
                    for activity_index, (activity_title, month_start, month_end) in enumerate(activities, start=1)
                ],
            }
            for index, title, activities in [
                (
                    1,
                    "Planificacion y delimitacion tecnica del estudio",
                    [
                        ("Delimitar alcance y unidad de analisis", 2, 2),
                        ("Definir protocolo de datos", 2, 3),
                        ("Alinear criterios metodologicos", 3, 3),
                    ],
                ),
                (
                    2,
                    "Levantamiento y organizacion de datos operacionales",
                    [
                        ("Recopilar historiales de fallas y paradas", 2, 3),
                        ("Caracterizar condiciones operativas", 3, 4),
                        ("Homologar taxonomia de eventos", 4, 4),
                    ],
                ),
                (
                    3,
                    "Depuracion y construccion de base analitica",
                    [
                        ("Consolidar base estructurada", 4, 5),
                        ("Depurar duplicados y faltantes", 5, 6),
                        ("Validar consistencia interna", 6, 6),
                    ],
                ),
                (
                    4,
                    "Linea base de confiabilidad y mantenibilidad",
                    [
                        ("Calcular indicadores base", 6, 6),
                        ("Segmentar resultados por sistema", 6, 7),
                        ("Emitir diagnostico inicial", 7, 7),
                    ],
                ),
                (
                    5,
                    "Criticidad y priorizacion de modos de falla",
                    [
                        ("Ejecutar analisis de criticidad", 7, 7),
                        ("Desarrollar AMEF de modos de falla", 7, 8),
                        ("Priorizar componentes criticos", 8, 8),
                    ],
                ),
                (
                    6,
                    "Diseno del plan RCM e implementacion piloto",
                    [
                        ("Disenar tareas RCM", 7, 8),
                        ("Definir frecuencias y recursos", 8, 9),
                        ("Ajustar parametros del piloto", 9, 10),
                        ("Ejecutar piloto de implementacion", 7, 10),
                    ],
                ),
                (
                    7,
                    "Validacion tecnica y contrastacion de resultados",
                    [
                        ("Validar tecnicamente el plan", 8, 9),
                        ("Contrastar resultados pre y post", 9, 10),
                        ("Analizar sensibilidad de tiempos y tasas", 10, 11),
                    ],
                ),
                (
                    8,
                    "Cierre documental y preparacion de sustentacion",
                    [
                        ("Redactar resultados y conclusiones", 10, 10),
                        ("Levantar observaciones del asesor", 10, 11),
                        ("Ajustar anexos y formato final", 11, 12),
                        ("Preparar sustentacion final", 12, 12),
                    ],
                ),
            ]
        ],
    }
    return f"<<<TABLE_JSON\n{json.dumps(payload, ensure_ascii=False)}\nTABLE_JSON>>>"


def _failed_sec_0025_schedule_raw_response() -> str:
    phase_titles = [
        "1. Diagnostico inicial de la flota de motoniveladoras CAT 24M",
        "2. Diseno del marco teorico-conceptual",
        "3. Desarrollo del plan de mantenimiento centrado en confiabilidad",
        "4. Validacion tecnica del plan RCM",
        "5. Implementacion del plan en la flota seleccionada",
        "6. Monitoreo y evaluacion de resultados",
        "7. Analisis de resultados y conclusiones",
        "8. Presentacion y defensa del proyecto",
    ]
    rows = [
        [""] * 14,
        [phase_titles[0]] + [""] * 13,
        ["1.1. Revision documental de historiales de mantenimiento", "", "â—", "â—"] + [""] * 10,
        ["1.2. Inspeccion tecnica de componentes criticos", "", "â—", "â—"] + [""] * 10,
        ["1.3. Evaluacion de disponibilidad inherente actual", "", "â—", "â—"] + [""] * 10,
        [phase_titles[1]] + [""] * 13,
        ["2.1. Revision bibliografica de RCM aplicado a maquinaria minera", "", "â—", "â—", "â—"] + [""] * 9,
        ["2.2. Definicion de indicadores de confiabilidad", "", "â—", "â—", "â—"] + [""] * 9,
        ["2.3. Establecimiento de criterios de disponibilidad", "", "â—", "â—", "â—"] + [""] * 9,
        [phase_titles[2]] + [""] * 13,
        ["3.1. Identificacion de modos de falla criticos", "", "", "â—", "â—", "â—"] + [""] * 8,
        ["3.2. Diseno de estrategias de mantenimiento preventivo", "", "", "â—", "â—", "â—"] + [""] * 8,
        ["3.3. Protocolos de inspeccion predictiva", "", "", "â—", "â—", "â—"] + [""] * 8,
        [phase_titles[3]] + [""] * 13,
        ["4.1. Simulacion de escenarios de mantenimiento", "", "", "", "", "â—", "â—", "â—"] + [""] * 6,
        ["4.2. Pruebas piloto en condiciones operativas reales", "", "", "", "", "â—", "â—", "â—"] + [""] * 6,
        ["4.3. Ajustes tecnicos basados en resultados", "", "", "", "", "â—", "â—", "â—"] + [""] * 6,
        [phase_titles[4]] + [""] * 13,
        ["5.1. Capacitacion del personal tecnico", "", "", "", "", "", "", "â—", "â—"] + [""] * 5,
        ["5.2. Instalacion de sistemas de monitoreo", "", "", "", "", "", "", "â—", "â—"] + [""] * 5,
        ["5.3. Ejecucion de mantenimientos programados", "", "", "", "", "", "", "â—", "â—"] + [""] * 5,
        [phase_titles[5]] + [""] * 13,
        ["6.1. Recoleccion de datos de disponibilidad", "", "", "", "", "", "", "", "â—", "â—", "â—", "â—"] + [""] * 2,
        ["6.2. Analisis de indicadores de confiabilidad", "", "", "", "", "", "", "", "â—", "â—", "â—", "â—"]
        + [""] * 2,
        ["6.3. Comparacion con estandares de la industria", "", "", "", "", "", "", "", "â—", "â—", "â—", "â—"]
        + [""] * 2,
        ["6.4. Evaluacion de impacto economico-operativo", "", "", "", "", "", "", "", "â—", "â—", "â—", "â—"]
        + [""] * 2,
        [phase_titles[6]] + [""] * 13,
        ["7.1. Procesamiento estadistico de datos", "", "", "", "", "", "", "", "", "â—", "â—", "â—"] + [""] * 3,
        ["7.2. Elaboracion de informe tecnico", "", "", "", "", "", "", "", "", "â—", "â—", "â—"] + [""] * 3,
        ["7.3. Redaccion de conclusiones y recomendaciones", "", "", "", "", "", "", "", "", "â—", "â—", "â—"]
        + [""] * 3,
        [phase_titles[7]] + [""] * 13,
        ["8.1. Preparacion de material de defensa", "", "", "", "", "", "", "", "", "", "", "â—", "â—", "â—"],
        ["8.2. Elaboracion de informe final", "", "", "", "", "", "", "", "", "", "", "â—", "â—", "â—"],
        ["8.3. Presentacion ante comite evaluador", "", "", "", "", "", "", "", "", "", "", "â—", "â—", "â—"],
        ["8.4. Sustentacion publica del proyecto", "", "", "", "", "", "", "", "", "", "", "â—", "â—", "â—"],
    ]
    payload = {
        "tipo": "tabla",
        "id": "tabla_5_1_cronograma_actividades",
        "titulo": "Tabla 5.1 Cronograma de actividades",
        "orientacion": "landscape",
        "subtipo": "cronograma_actividades",
        "encabezados": [
            "FASES Y ACTIVIDADES",
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
        ],
        "filas": rows,
        "anio": "2025",
        "meses": ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Set", "Oct", "Nov", "Dic"],
        "simbolo_marca": "â—",
        "filas_fase": [1, 5, 9, 13, 17, 21, 26, 30],
        "celdas_combinadas": [
            {"fila_inicio": 0, "fila_fin": 0, "col_inicio": 0, "col_fin": 0, "texto": "FASES Y ACTIVIDADES"},
            {"fila_inicio": 0, "fila_fin": 0, "col_inicio": 1, "col_fin": 12, "texto": "2025"},
        ],
        "celdas_fusionadas": [
            {"fila": 1, "col_inicio": 0, "col_fin": 12, "texto": phase_titles[0]},
            {"fila": 5, "col_inicio": 0, "col_fin": 12, "texto": phase_titles[1]},
        ],
        "estilo": {
            "modelo_referencia": "cronograma_actividades.docx",
            "titulo_capitulo": "V. CRONOGRAMA DE ACTIVIDADES",
            "titulo_exacto": True,
            "orientacion_pagina": "landscape",
            "margenes_reducidos": True,
        },
    }
    return f"```json\n<<<TABLE_JSON\n{json.dumps(payload, ensure_ascii=False)}\nTABLE_JSON>>>\n```"


def _schedule_row(label: str, marked_months: list[int] | None = None) -> list[str]:
    row = [label] + [""] * 12
    for month in marked_months or []:
        row[month] = "●"
    return row


def _canonical_schedule_raw_response() -> str:
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
    payload = {
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
        + [
            {"fila": row, "col_inicio": 0, "col_fin": 12, "texto": title}
            for row, title in zip([1, 5, 9, 13, 17, 21, 26, 30], phase_titles)
        ],
        "celdas_fusionadas": [
            {"fila": -1, "col": 0, "filas_span": 2, "cols_span": 1, "texto": "FASES Y ACTIVIDADES"},
            {"fila": -1, "col": 1, "filas_span": 1, "cols_span": 12, "texto": "2025"},
        ]
        + [
            {"fila": row, "col": 0, "filas_span": 1, "cols_span": 13, "texto": title}
            for row, title in zip([1, 5, 9, 13, 17, 21, 26, 30], phase_titles)
        ],
    }
    return f"<<<TABLE_JSON\n{json.dumps(payload, ensure_ascii=False)}\nTABLE_JSON>>>"


def _generic_budget_raw_response() -> str:
    return (
        "<<<TABLE_JSON\n"
        '{"tipo":"tabla","id":"tabla_invalida","titulo":"Presupuesto","encabezados":["Rubro","Cantidad","Costo"],'
        '"filas":[["Laptop","1","2999.00"],["Internet","12","600.00"]]}\n'
        "TABLE_JSON>>>"
    )


def _canonical_budget_raw_response() -> str:
    payload = {
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
    return f"<<<TABLE_JSON\n{json.dumps(payload, ensure_ascii=False)}\nTABLE_JSON>>>"


class TestIsConfigured:
    def test_not_configured_when_no_provider_has_key(self, ai_svc):
        svc, gemini, mistral = ai_svc
        _set_selection(svc, "gemini", mode="auto")
        gemini.is_configured.return_value = False
        mistral.is_configured.return_value = False

        with patch("app.core.services.ai.ai_service.settings", _settings()):
            assert svc.is_configured() is False

    def test_configured_when_any_provider_is_available(self, ai_svc):
        svc, gemini, mistral = ai_svc
        _set_selection(svc, "mistral", mode="fixed")
        gemini.is_configured.return_value = False
        mistral.is_configured.return_value = True

        with patch("app.core.services.ai.ai_service.settings", _settings(primary="mistral")):
            assert svc.is_configured() is True
            assert svc.available_providers() == ["mistral"]


class TestGenerate:
    def test_generate_records_token_usage_per_section_and_total(self, ai_svc):
        svc, _, _ = ai_svc
        _set_selection(svc, "gemini", mode="fixed")
        svc._clients = {
            "gemini": _UsageProvider(
                content="Contenido generado por Gemini para la seccion.",
                usage={"input_tokens": 120, "output_tokens": 45, "total_tokens": 165},
            ),
            "mistral": MagicMock(is_configured=MagicMock(return_value=False)),
        }

        project = {
            "id": "proj-token-usage-001",
            "title": "Token Usage",
            "variables": {"tema": "IA aplicada"},
            "values": {"tema": "IA aplicada"},
        }
        format_detail = {
            "definition": {
                "cuerpo": {
                    "capitulos": [
                        {"titulo": "Introduccion"},
                        {"titulo": "Marco teorico"},
                    ]
                }
            }
        }

        with (
            patch("app.core.services.ai.ai_service.settings", _settings(primary="gemini", fallback=False)),
            patch("app.core.services.ai.ai_service.is_unac_maintenance_project", return_value=False),
        ):
            result = svc.generate(project, format_detail, None)

        usage = result["tokenUsage"]
        assert usage["calls_total"] == 2
        assert usage["reported_calls"] == 2
        assert usage["estimated_calls"] == 0
        assert usage["input_tokens_total"] == 240
        assert usage["output_tokens_total"] == 90
        assert usage["total_tokens"] == 330
        assert len(usage["sections"]) == 2

    def test_generate_marks_estimated_usage_when_provider_does_not_report_usage(self, ai_svc):
        svc, _, _ = ai_svc
        _set_selection(svc, "gemini", mode="fixed")
        svc._clients = {
            "gemini": _EstimateOnlyProvider(content="Contenido estimado para la seccion."),
            "mistral": MagicMock(is_configured=MagicMock(return_value=False)),
        }

        project = {"id": "proj-token-estimate-001", "title": "Estimate", "variables": {"tema": "ML"}}
        format_detail = {"definition": {"cuerpo": {"capitulos": [{"titulo": "Capitulo 1"}]}}}

        with patch("app.core.services.ai.ai_service.settings", _settings(primary="gemini", fallback=False)):
            result = svc.generate(project, format_detail, None)

        usage = result["tokenUsage"]
        assert usage["calls_total"] == 1
        assert usage["reported_calls"] == 0
        assert usage["estimated_calls"] == 1
        assert usage["has_estimated_usage"] is True
        assert usage["total_tokens"] > 0

    def test_generate_accumulates_retry_and_fallback_usage_attempts(self, ai_svc):
        svc, gemini, _ = ai_svc
        _set_selection(svc, "gemini", mode="auto")
        gemini.is_configured.return_value = True
        gemini.generate.side_effect = QuotaExceededError(
            "Quota exceeded. Check Gemini project quota/billing.",
            provider="gemini",
            error_type="exhausted",
        )
        svc._clients = {
            "gemini": gemini,
            "mistral": _UsageProvider(
                content="Contenido generado por Mistral tras fallback.",
                usage={"input_tokens": 80, "output_tokens": 20, "total_tokens": 100},
            ),
        }

        project = {"id": "proj-token-fallback-001", "title": "Fallback", "variables": {"tema": "Fallback"}}
        format_detail = {"definition": {"cuerpo": {"capitulos": [{"titulo": "Capitulo 1"}]}}}

        with (
            patch("app.core.services.ai.ai_service.settings", _settings(primary="gemini", fallback=True)),
            patch("app.core.services.ai.ai_service.time.sleep"),
        ):
            result = svc.generate(project, format_detail, None)

        usage = result["tokenUsage"]
        assert usage["calls_total"] == 2
        assert usage["reported_calls"] == 1
        assert usage["estimated_calls"] == 1
        assert usage["total_tokens"] >= 100
        assert len(usage["attempts"]) == 2
        assert usage["attempts"][0]["provider"] == "gemini"
        assert usage["attempts"][1]["provider"] == "mistral"

    def test_full_flow_with_primary_provider(self, ai_svc):
        svc, gemini, mistral = ai_svc
        _set_selection(svc, "gemini", mode="auto")
        gemini.is_configured.return_value = True
        mistral.is_configured.return_value = False
        gemini.generate.return_value = "Contenido generado por Gemini."

        project = {
            "id": "proj-test-001",
            "title": "Test Project",
            "variables": {"tema": "IA", "objetivo_general": "mejorar"},
            "values": {"tema": "IA", "objetivo_general": "mejorar"},
        }
        prompt = {"template": "Escribe sobre {{tema}} con objetivo {{objetivo_general}}."}
        format_detail = {
            "definition": {
                "cuerpo": {
                    "capitulos": [
                        {"titulo": "Introduccion"},
                        {"titulo": "Marco teorico"},
                    ]
                }
            }
        }

        with patch("app.core.services.ai.ai_service.settings", _settings(primary="gemini", fallback=True)):
            result = svc.generate(project, format_detail, prompt)

        assert "sections" in result
        assert len(result["sections"]) == 2
        assert svc.get_last_used_provider() == "gemini"
        assert gemini.generate.call_count == 2
        mistral.generate.assert_not_called()

    def test_fallback_to_secondary_provider_on_quota(self, ai_svc):
        svc, gemini, mistral = ai_svc
        _set_selection(svc, "gemini", mode="auto")
        gemini.is_configured.return_value = True
        mistral.is_configured.return_value = True
        gemini.generate.side_effect = QuotaExceededError(
            "Quota exceeded. Check Gemini project quota/billing.",
            provider="gemini",
            error_type="exhausted",
        )
        mistral.generate.return_value = "Contenido generado por Mistral."

        project = {"id": "proj-fallback-001", "title": "Fallback", "variables": {"tema": "Fallback"}}
        format_detail = {"definition": {"cuerpo": {"capitulos": [{"titulo": "Capitulo 1"}]}}}

        with (
            patch("app.core.services.ai.ai_service.settings", _settings(primary="gemini", fallback=True)),
            patch("app.core.services.ai.ai_service.time.sleep"),
        ):
            result = svc.generate(project, format_detail, None)

        assert result["sections"][0]["content"] == "Contenido generado por Mistral."
        assert svc.get_last_used_provider() == "mistral"
        assert gemini.generate.call_count == 1
        mistral.generate.assert_called_once()

    def test_fail_fast_when_quota_and_fallback_disabled(self, ai_svc):
        svc, gemini, mistral = ai_svc
        _set_selection(svc, "gemini", mode="auto")
        gemini.is_configured.return_value = True
        mistral.is_configured.return_value = True
        gemini.generate.side_effect = QuotaExceededError(
            "Quota exceeded. Check Gemini project quota/billing.",
            provider="gemini",
            error_type="exhausted",
        )

        project = {"id": "proj-fail-001", "title": "Fail Fast", "variables": {"tema": "Test"}}
        format_detail = {"definition": {"cuerpo": {"capitulos": [{"titulo": "Capitulo 1"}]}}}

        with (
            patch("app.core.services.ai.ai_service.settings", _settings(primary="gemini", fallback=False)),
            patch("app.core.services.ai.ai_service.time.sleep"),
        ):
            with pytest.raises(QuotaExceededError):
                svc.generate(project, format_detail, None)

        assert gemini.generate.call_count == 1
        mistral.generate.assert_not_called()

    def test_auth_error_without_retry_falls_back_immediately(self, ai_svc):
        svc, gemini, mistral = ai_svc
        _set_selection(svc, "gemini", mode="auto")
        gemini.is_configured.return_value = True
        mistral.is_configured.return_value = True
        gemini.generate.side_effect = ProviderAuthError(
            "Gemini authentication failed.",
            provider="gemini",
            status_code=401,
        )
        mistral.generate.return_value = "Contenido por fallback auth."

        project = {"id": "proj-auth-fallback", "title": "Auth", "variables": {"tema": "x"}}
        format_detail = {"definition": {"cuerpo": {"capitulos": [{"titulo": "Capitulo 1"}]}}}

        with patch("app.core.services.ai.ai_service.settings", _settings(primary="gemini", fallback=True)):
            result = svc.generate(project, format_detail, None)

        assert result["sections"][0]["content"] == "Contenido por fallback auth."
        assert gemini.generate.call_count == 1
        assert mistral.generate.call_count == 1

    def test_transient_error_retries_once_then_fallback(self, ai_svc):
        svc, gemini, mistral = ai_svc
        _set_selection(svc, "gemini", mode="auto")
        gemini.is_configured.return_value = True
        mistral.is_configured.return_value = True
        gemini.generate.side_effect = [RuntimeError("Read timed out"), RuntimeError("Read timed out")]
        mistral.generate.return_value = "Contenido por fallback transient."

        project = {"id": "proj-transient-fallback", "title": "Transient", "variables": {"tema": "x"}}
        format_detail = {"definition": {"cuerpo": {"capitulos": [{"titulo": "Capitulo 1"}]}}}

        with (
            patch("app.core.services.ai.ai_service.settings", _settings(primary="gemini", fallback=True)),
            patch.object(svc, "_sleep_with_cancel", return_value=None),
        ):
            result = svc.generate(project, format_detail, None)

        assert result["sections"][0]["content"] == "Contenido por fallback transient."
        assert gemini.generate.call_count == 2
        assert mistral.generate.call_count == 1

    def test_exhausted_provider_is_disabled_for_rest_of_job(self, ai_svc):
        svc, gemini, mistral = ai_svc
        _set_selection(svc, "gemini", mode="auto")
        gemini.is_configured.return_value = True
        mistral.is_configured.return_value = True
        gemini.generate.side_effect = QuotaExceededError(
            "Quota exceeded. Check Gemini project quota/billing.",
            provider="gemini",
            error_type="exhausted",
        )
        mistral.generate.return_value = "Contenido de fallback por seccion."

        project = {"id": "proj-disabled-provider", "title": "Circuit", "variables": {"tema": "x"}}
        format_detail = {
            "definition": {
                "cuerpo": {
                    "capitulos": [
                        {"titulo": "Capitulo 1"},
                        {"titulo": "Capitulo 2"},
                    ]
                }
            }
        }

        with patch("app.core.services.ai.ai_service.settings", _settings(primary="gemini", fallback=True)):
            result = svc.generate(project, format_detail, None)

        assert len(result["sections"]) == 2
        assert gemini.generate.call_count == 1
        assert mistral.generate.call_count == 2

    def test_empty_prompt_uses_fallback_prompt(self, ai_svc):
        svc, gemini, mistral = ai_svc
        _set_selection(svc, "gemini", mode="auto")
        gemini.is_configured.return_value = True
        mistral.is_configured.return_value = False
        gemini.generate.return_value = "Contenido."

        project = {
            "id": "proj-noprompt",
            "title": "Sin Prompt",
            "variables": {},
        }

        with patch("app.core.services.ai.ai_service.settings", _settings()):
            result = svc.generate(project, None, None)

        assert "sections" in result
        called_prompt = gemini.generate.call_args[0][0]
        assert "Sin Prompt" in called_prompt

    def test_generate_uses_project_selection_override(self, ai_svc):
        svc, gemini, mistral = ai_svc
        _set_selection(svc, "gemini", mode="auto")
        gemini.is_configured.return_value = True
        mistral.is_configured.return_value = True
        mistral.generate.return_value = "Contenido con seleccion por proyecto."

        project = {
            "id": "proj-selection-override",
            "title": "Seleccion",
            "variables": {"tema": "Seleccion"},
        }
        format_detail = {"definition": {"cuerpo": {"capitulos": [{"titulo": "Capitulo 1"}]}}}
        selection_override = {
            "provider": "mistral",
            "model": "mistral-medium-2505",
            "fallback_provider": "gemini",
            "fallback_model": "gemini-2.0-flash",
            "mode": "fixed",
        }

        with patch("app.core.services.ai.ai_service.settings", _settings(primary="gemini", fallback=True)):
            result = svc.generate(project, format_detail, None, selection_override=selection_override)

        assert result["sections"][0]["content"] == "Contenido con seleccion por proyecto."
        mistral.generate.assert_called_once()
        gemini.generate.assert_not_called()

    def test_generate_skips_index_branches_from_definition(self, ai_svc):
        svc, gemini, mistral = ai_svc
        _set_selection(svc, "gemini", mode="auto")
        gemini.is_configured.return_value = True
        mistral.is_configured.return_value = False
        gemini.generate.side_effect = lambda prompt, **_: (
            _valid_reality_problem_raw_response()
            if "realidad problematica" in str(prompt).lower()
            else "Contenido academico de prueba para la seccion."
        )

        project = {
            "id": "proj-index-skip",
            "title": "Proyecto con indice",
            "variables": {"tema": "Optimizacion"},
        }
        format_detail = {
            "definition": {
                "preliminares": {
                    "indices": [
                        {
                            "titulo": "INDICE",
                            "items": [{"texto": "I. PLANTEAMIENTO DEL PROBLEMA"}],
                        },
                        {"titulo": "INDICE DE TABLAS", "items": [{"texto": "Tabla 1.1"}]},
                    ],
                    "introduccion": {"titulo": "INTRODUCCION"},
                },
                "cuerpo": [
                    {
                        "titulo": "I. PLANTEAMIENTO DEL PROBLEMA",
                        "contenido": [{"texto": "1.1 Realidad problematica"}],
                    }
                ],
            }
        }

        with patch("app.core.services.ai.ai_service.settings", _settings(primary="gemini", fallback=False)):
            result = svc.generate(project, format_detail, None)

        paths = [section["path"] for section in result["sections"]]
        assert "I. PLANTEAMIENTO DEL PROBLEMA" in paths
        assert any(path.endswith("1.1 Realidad problematica") for path in paths)
        assert all(not path.startswith("INDICE") for path in paths)
        assert all("INDICE DE TABLAS" not in path for path in paths)

    def test_generate_resumes_from_partial_ai_result(self, ai_svc):
        svc, gemini, mistral = ai_svc
        _set_selection(svc, "gemini", mode="auto")
        gemini.is_configured.return_value = True
        mistral.is_configured.return_value = False
        gemini.generate.return_value = "Contenido nuevo para segunda seccion."

        project = {
            "id": "proj-resume-001",
            "title": "Resume",
            "variables": {"tema": "Reintento"},
            "ai_result": {
                "sections": [
                    {
                        "sectionId": "sec-0001",
                        "path": "Capitulo 1",
                        "content": "Contenido previo guardado.",
                    }
                ]
            },
        }
        format_detail = {
            "definition": {
                "cuerpo": {
                    "capitulos": [
                        {"titulo": "Capitulo 1"},
                        {"titulo": "Capitulo 2"},
                    ]
                }
            }
        }

        with patch("app.core.services.ai.ai_service.settings", _settings(primary="gemini", fallback=True)):
            result = svc.generate(project, format_detail, None, resume_from_partial=True)

        assert len(result["sections"]) == 2
        assert result["sections"][0]["content"] == "Contenido previo guardado."
        assert result["sections"][1]["content"] == "Contenido nuevo para segunda seccion."
        assert gemini.generate.call_count == 1

    def test_generate_resumes_from_seed_override(self, ai_svc):
        svc, gemini, mistral = ai_svc
        _set_selection(svc, "gemini", mode="auto")
        gemini.is_configured.return_value = True
        mistral.is_configured.return_value = False
        gemini.generate.return_value = "Contenido generado desde el punto de reanudacion."

        project = {
            "id": "proj-seed-override-001",
            "title": "Resume override",
            "variables": {"tema": "Reintento"},
        }
        format_detail = {
            "definition": {
                "cuerpo": {
                    "capitulos": [
                        {"titulo": "Capitulo 1"},
                        {"titulo": "Capitulo 2"},
                    ]
                }
            }
        }
        seed_sections = [
            {
                "sectionId": "sec-0001",
                "path": "Capitulo 1",
                "content": "Contenido parcial externo",
            }
        ]

        with patch("app.core.services.ai.ai_service.settings", _settings(primary="gemini", fallback=True)):
            result = svc.generate(
                project,
                format_detail,
                None,
                resume_from_partial=True,
                seed_sections_override=seed_sections,
            )

        assert len(result["sections"]) == 2
        assert result["sections"][0]["content"] == "Contenido parcial externo"
        assert result["sections"][1]["content"] == "Contenido generado desde el punto de reanudacion."
        assert gemini.generate.call_count == 1

    def test_generate_consolidates_simulated_references_section(self, ai_svc):
        svc, gemini, mistral = ai_svc
        _set_selection(svc, "gemini", mode="auto")
        gemini.is_configured.return_value = True
        mistral.is_configured.return_value = False
        gemini.generate.return_value = "Contenido academico generado para la seccion."

        project = {
            "id": "proj-references-001",
            "title": "Mantenimiento predictivo",
            "variables": {"tema": "Mantenimiento predictivo"},
        }
        format_detail = {
            "definition": {
                "cuerpo": {
                    "capitulos": [
                        {"titulo": "II. MARCO TEORICO"},
                    ]
                },
                "finales": {
                    "referencias": {"titulo": "IX. REFERENCIAS BIBLIOGRAFICAS"},
                },
            }
        }

        with patch("app.core.services.ai.ai_service.settings", _settings(primary="gemini", fallback=False)):
            result = svc.generate(project, format_detail, None)

        references = next(section for section in result["sections"] if "REFERENCIAS" in section["path"].upper())
        body = next(section for section in result["sections"] if "MARCO TEORICO" in section["path"].upper())

        assert body["content"].startswith("Contenido academico generado para la seccion.")
        assert "[[CITE:SIM_" in body["content"]
        assert "sin acceso a internet" in references["content"]
        assert "[[SOURCE:SIM_" in references["content"]
        assert "Fundamentos y evidencia sobre investigacion aplicada" in references["content"]

    def test_resume_does_not_replay_seeded_sections_in_progress(self, ai_svc):
        svc, gemini, mistral = ai_svc
        _set_selection(svc, "gemini", mode="auto")
        gemini.is_configured.return_value = True
        mistral.is_configured.return_value = False
        gemini.generate.return_value = "Contenido generado nuevo."

        project = {
            "id": "proj-seed-progress-001",
            "title": "Resume progress",
            "variables": {"tema": "Reintento"},
        }
        format_detail = {
            "definition": {
                "cuerpo": {
                    "capitulos": [
                        {"titulo": "Capitulo 1"},
                        {"titulo": "Capitulo 2"},
                    ]
                }
            }
        }
        seed_sections = [
            {
                "sectionId": "sec-0001",
                "path": "Capitulo 1",
                "content": "Contenido parcial externo",
            }
        ]
        progress_events = []

        def _progress_cb(current, total, path, provider, *, stage="section_start", payload=None):
            progress_events.append((int(current), str(stage), str(path)))

        with patch("app.core.services.ai.ai_service.settings", _settings(primary="gemini", fallback=True)):
            svc.generate(
                project,
                format_detail,
                None,
                resume_from_partial=True,
                seed_sections_override=seed_sections,
                progress_cb=_progress_cb,
            )

        assert any(event[0] == 2 and event[1] == "section_start" for event in progress_events)
        assert not any(event[0] == 1 for event in progress_events)

    def test_fixed_mode_does_not_fallback_even_on_transient_ssl(self, ai_svc):
        svc, gemini, mistral = ai_svc
        _set_selection(svc, "mistral", mode="fixed")
        gemini.is_configured.return_value = True
        mistral.is_configured.return_value = True
        mistral.generate.side_effect = RuntimeError(
            "HTTPSConnectionPool: SSLError(SSLError(1, '[SSL: SSLV3_ALERT_BAD_RECORD_MAC] bad record mac'))"
        )

        project = {"id": "proj-fixed-ssl", "title": "SSL", "variables": {"tema": "TLS"}}
        format_detail = {"definition": {"cuerpo": {"capitulos": [{"titulo": "Capitulo 1"}]}}}

        with (
            patch("app.core.services.ai.ai_service.settings", _settings(primary="mistral", fallback=False)),
            patch.object(svc, "_sleep_with_cancel", return_value=None),
        ):
            with pytest.raises(RuntimeError, match="bad record mac"):
                svc.generate(project, format_detail, None)

        assert mistral.generate.call_count == 2  # 1 intento + 1 retry transitorio
        gemini.generate.assert_not_called()

    def test_fixed_mode_does_not_emit_preemptive_contingency_warning(self, ai_svc):
        svc, gemini, mistral = ai_svc
        _set_selection(svc, "mistral", mode="fixed")
        gemini.is_configured.return_value = True
        mistral.is_configured.return_value = True
        mistral.generate.return_value = "Contenido primario en modo fijo."

        project = {"id": "proj-fixed-clean", "title": "Fixed", "variables": {"tema": "TLS"}}
        format_detail = {"definition": {"cuerpo": {"capitulos": [{"titulo": "Capitulo 1"}]}}}
        trace_events = []

        with patch("app.core.services.ai.ai_service.settings", _settings(primary="mistral", fallback=False)):
            result = svc.generate(project, format_detail, None, trace_hook=trace_events.append)

        assert result["sections"][0]["content"] == "Contenido primario en modo fijo."
        assert not any(
            "fallback de contingencia habilitado" in str(evt.get("title", "")).lower() for evt in trace_events
        )

    def test_generate_emits_prompt_base_and_section_audit_traces(self, ai_svc):
        svc, _, _ = ai_svc
        _set_selection(svc, "gemini", mode="fixed")
        svc._clients = {
            "gemini": _UsageProvider(
                content="Respuesta detallada para la seccion de introduccion.",
                usage={"input_tokens": 90, "output_tokens": 30, "total_tokens": 120},
            ),
            "mistral": MagicMock(is_configured=MagicMock(return_value=False)),
        }
        project = {
            "id": "proj-trace-audit-001",
            "title": "Trace",
            "variables": {"tema": "Mantenimiento predictivo", "title": "Trace"},
            "values": {"tema": "Mantenimiento predictivo", "title": "Trace"},
        }
        prompt = {"template": "Contexto general: {{tema}}"}
        format_detail = {"definition": {"cuerpo": {"capitulos": [{"titulo": "Introduccion"}]}}}
        trace_events = []

        with patch("app.core.services.ai.ai_service.settings", _settings(primary="gemini", fallback=False)):
            svc.generate(project, format_detail, prompt, trace_hook=trace_events.append)

        base_prompt_event = next(evt for evt in trace_events if evt.get("step") == "prompt.base")
        assert "Contexto general: Mantenimiento predictivo" in str(base_prompt_event.get("preview", {}).get("prompt"))

        section_done = next(
            evt for evt in trace_events if evt.get("step") == "ai.generate.section" and evt.get("status") == "done"
        )
        assert "Introduccion" in str(section_done.get("preview", {}).get("prompt"))
        assert "Respuesta detallada para la seccion de introduccion." in str(section_done.get("preview", {}).get("raw"))
        assert section_done.get("meta", {}).get("sectionUsage", {}).get("total_tokens") == 120

    def test_generate_emits_distinct_prompts_for_sibling_subsections(self, ai_svc):
        svc, _, _ = ai_svc
        _set_selection(svc, "gemini", mode="fixed")
        svc._clients = {
            "gemini": _UsageProvider(
                content=[
                    "Contenido del capitulo.",
                    _valid_reality_problem_raw_response(),
                    "Contenido por subseccion.",
                ],
                usage={"input_tokens": 90, "output_tokens": 30, "total_tokens": 120},
            ),
            "mistral": MagicMock(is_configured=MagicMock(return_value=False)),
        }
        project = {
            "id": "proj-trace-hierarchy-001",
            "title": "Trace hierarchy",
            "variables": {"tema": "Mantenimiento predictivo", "title": "Trace hierarchy"},
            "values": {"tema": "Mantenimiento predictivo", "title": "Trace hierarchy"},
        }
        prompt = {"template": "Contexto general: {{tema}}"}
        format_detail = {
            "definition": {
                "cuerpo": {
                    "capitulos": [
                        {
                            "titulo": "I. Planteamiento del problema",
                            "subsecciones": [
                                {"titulo": "1.1 Descripcion de la realidad problematica"},
                                {"titulo": "1.2 Formulacion del problema"},
                            ],
                        }
                    ]
                }
            }
        }
        trace_events = []

        with patch("app.core.services.ai.ai_service.settings", _settings(primary="gemini", fallback=False)):
            svc.generate(project, format_detail, prompt, trace_hook=trace_events.append)

        section_done_events = [
            evt for evt in trace_events if evt.get("step") == "ai.generate.section" and evt.get("status") == "done"
        ]
        sibling_events = [
            evt
            for evt in section_done_events
            if evt.get("meta", {}).get("sectionPath")
            in {
                "I. Planteamiento del problema/1.1 Descripcion de la realidad problematica",
                "I. Planteamiento del problema/1.2 Formulacion del problema",
            }
        ]
        assert len(sibling_events) == 2
        first_prompt = str(sibling_events[0].get("preview", {}).get("prompt"))
        second_prompt = str(sibling_events[1].get("preview", {}).get("prompt"))

        assert "I. Planteamiento del problema/1.1 Descripcion de la realidad problematica" in first_prompt
        assert "I. Planteamiento del problema/1.2 Formulacion del problema" in second_prompt
        assert first_prompt != second_prompt

    def test_generate_injects_editorial_contract_and_word_ranges_for_project_quant(self, ai_svc):
        svc, _, _ = ai_svc
        _set_selection(svc, "gemini", mode="fixed")
        svc._clients = {
            "gemini": _UsageProvider(
                content=[
                    "Contenido generado para proyecto cuantitativo.",
                    _valid_reality_problem_raw_response(),
                ],
                usage={"input_tokens": 90, "output_tokens": 30, "total_tokens": 120},
            ),
            "mistral": MagicMock(is_configured=MagicMock(return_value=False)),
        }
        values = _project_quant_values()
        project = {
            "id": "proj-project-quant-editorial-001",
            "title": str(values["title"]),
            "variables": values,
            "values": values,
        }
        prompt = {
            "template": "Contexto general del proyecto: {{title}}",
            "format_id": "unac-proyecto-cuant",
        }
        planned_sections = [
            {
                "sectionId": "sec-0001",
                "path": "INTRODUCCIÓN",
                "title": "INTRODUCCIÓN",
                "hints": "",
                "additional_context": "",
            },
            {
                "sectionId": "sec-0003",
                "path": "I. PLANTEAMIENTO DEL PROBLEMA/1.1 Descripción de la realidad problemática",
                "title": "1.1 Descripción de la realidad problemática",
                "hints": "",
                "additional_context": "",
            },
        ]
        trace_events = []

        with (
            patch("app.core.services.ai.ai_service.settings", _settings(primary="gemini", fallback=False)),
            patch("app.core.services.ai.ai_service.is_unac_maintenance_project", return_value=False),
        ):
            svc.generate(
                project,
                {"id": "unac-proyecto-cuant", "definition": {}},
                prompt,
                trace_hook=trace_events.append,
                planned_sections=planned_sections,
            )

        base_prompt_event = next(evt for evt in trace_events if evt.get("step") == "prompt.base")
        base_prompt_preview = str(base_prompt_event.get("preview", {}).get("prompt"))
        assert "Contrato editorial global del formato" in base_prompt_preview
        assert "no una tesis ya concluida" in base_prompt_preview

        section_done_events = [
            evt for evt in trace_events if evt.get("step") == "ai.generate.section" and evt.get("status") == "done"
        ]
        intro_prompt = str(section_done_events[0].get("preview", {}).get("prompt"))
        problem_prompt = str(section_done_events[1].get("preview", {}).get("prompt"))

        assert "minimo obligatorio 643 palabras narrativas" in intro_prompt
        assert "minimo obligatorio 1276 palabras narrativas" in problem_prompt
        assert "Hechos estructurados relevantes del proyecto:" in problem_prompt
        assert "Problema general:" in problem_prompt
        assert "Variables o decisiones ya fijadas:" in problem_prompt
        assert "Figura 1.1 Diagrama de Pareto" in problem_prompt

    def test_generate_emits_section_order_metadata_in_trace_and_progress(self, ai_svc):
        svc, _, _ = ai_svc
        _set_selection(svc, "gemini", mode="fixed")
        svc._clients = {
            "gemini": _UsageProvider(
                content="Contenido generado para validar orden institucional.",
                usage={"input_tokens": 40, "output_tokens": 20, "total_tokens": 60},
            ),
            "mistral": MagicMock(is_configured=MagicMock(return_value=False)),
        }
        project = {
            "id": "proj-section-order-metadata-001",
            "title": "Orden institucional",
            "variables": {"tema": "Orden institucional", "title": "Orden institucional"},
            "values": {"tema": "Orden institucional", "title": "Orden institucional"},
        }
        prompt = {"template": "Base {{title}}", "format_id": "unac-proyecto-cuant"}
        planned_sections = [
            {
                "sectionId": "titulo-info-basica",
                "path": "Título + Información Básica",
                "title": "Título + Información Básica",
                "parent_section_path": "",
                "level": 1,
                "section_order": -100,
                "hints": "",
                "additional_context": "",
            },
            {
                "sectionId": "intro",
                "path": "INTRODUCCIÓN",
                "title": "INTRODUCCIÓN",
                "parent_section_path": "",
                "level": 1,
                "section_order": 1,
                "hints": "",
                "additional_context": "",
            },
            {
                "sectionId": "chapter-1",
                "path": "I. PLANTEAMIENTO DEL PROBLEMA",
                "title": "I. PLANTEAMIENTO DEL PROBLEMA",
                "parent_section_path": "",
                "level": 1,
                "section_order": 2,
                "hints": "",
                "additional_context": "",
            },
        ]
        trace_events = []
        progress_events = []

        def _progress_cb(current, total, path, provider, *, stage="section_start", payload=None):
            progress_events.append(
                {
                    "current": int(current),
                    "total": int(total),
                    "path": str(path),
                    "provider": str(provider),
                    "stage": str(stage),
                    "payload": dict(payload or {}),
                }
            )

        with patch("app.core.services.ai.ai_service.settings", _settings(primary="gemini", fallback=False)):
            svc.generate(
                project,
                {"id": "unac-proyecto-cuant", "definition": {}},
                prompt,
                trace_hook=trace_events.append,
                progress_cb=_progress_cb,
                planned_sections=planned_sections,
            )

        section_index_event = next(evt for evt in trace_events if evt.get("step") == "format.section_index")
        outline = section_index_event.get("meta", {}).get("sectionOutline", [])
        assert [item["sectionOrder"] for item in outline] == [-100, 1, 2]
        assert outline[0]["sectionPath"] == "Título + Información Básica"
        assert outline[1]["sectionPath"] == "INTRODUCCIÓN"

        section_done_events = [
            evt for evt in trace_events if evt.get("step") == "ai.generate.section" and evt.get("status") == "done"
        ]
        assert section_done_events[0]["meta"]["sectionOrder"] == -100
        assert section_done_events[1]["meta"]["sectionOrder"] == 1
        assert section_done_events[2]["meta"]["sectionOrder"] == 2

        progress_done = [evt for evt in progress_events if evt.get("stage") == "section_done"]
        assert progress_done[0]["payload"]["section_order"] == -100
        assert progress_done[0]["payload"]["path"] == "Título + Información Básica"
        assert progress_done[1]["payload"]["section_order"] == 1
        assert progress_done[2]["payload"]["section_order"] == 2


class TestProviderStatus:
    def test_provider_status_exposes_selection_and_health(self, ai_svc):
        svc, gemini, mistral = ai_svc
        _set_selection(svc, "gemini", mode="auto")
        gemini.is_configured.return_value = True
        mistral.is_configured.return_value = True

        status = svc.providers_status_payload()
        assert status["selected_provider"] == "mistral"
        assert status["mode"] == "fixed"
        providers = {item["id"]: item for item in status["providers"]}
        assert set(providers) == {"mistral"}
        assert providers["mistral"]["health"] in {"OK", "UNKNOWN", "DEGRADED", "RATE_LIMITED", "EXHAUSTED"}

    def test_rate_limited_health_with_reset_seconds(self, ai_svc):
        svc, gemini, mistral = ai_svc
        _set_selection(svc, "mistral", mode="fixed")
        mistral.is_configured.return_value = True
        svc._metrics.record_rate_limited(
            "mistral",
            retry_after_s=57,
            message="Rate limited. Retry after 57 seconds.",
        )

        status = svc.providers_status_payload()
        mistral_status = next(item for item in status["providers"] if item["id"] == "mistral")
        assert mistral_status["health"] == "RATE_LIMITED"
        assert mistral_status["rate_limit"]["reset_seconds"] > 0

    def test_exhausted_health_when_quota_exceeded(self, ai_svc):
        svc, gemini, mistral = ai_svc
        _set_selection(svc, "mistral", mode="fixed")
        gemini.is_configured.return_value = False
        mistral.is_configured.return_value = True
        mistral.generate.side_effect = QuotaExceededError(
            "Rate limited. Retry after 57 seconds.",
            provider="mistral",
            retry_after=57,
            error_type="rate_limited",
        )
        mistral.generate.side_effect = QuotaExceededError(
            "Quota exceeded. Check Mistral project quota/billing.",
            provider="mistral",
            error_type="exhausted",
        )

        project = {"id": "proj-exhausted", "title": "Quota", "variables": {"tema": "x"}}
        format_detail = {"definition": {"cuerpo": {"capitulos": [{"titulo": "Capitulo 1"}]}}}

        with (
            patch("app.core.services.ai.ai_service.settings", _settings(primary="mistral", fallback=False)),
            patch.object(svc, "_sleep_with_cancel", return_value=None),
        ):
            with pytest.raises(QuotaExceededError):
                svc.generate(project, format_detail, None)

        status = svc.providers_status_payload()
        mistral_status = next(item for item in status["providers"] if item["id"] == "mistral")
        assert mistral_status["health"] == "EXHAUSTED"

    def test_degraded_health_after_repeated_timeouts(self, ai_svc):
        svc, gemini, mistral = ai_svc
        _set_selection(svc, "mistral", mode="fixed")
        gemini.is_configured.return_value = False
        mistral.is_configured.return_value = True
        mistral.generate.side_effect = RuntimeError("Read timed out")

        project = {"id": "proj-timeout", "title": "Timeout", "variables": {"tema": "x"}}
        format_detail = {"definition": {"cuerpo": {"capitulos": [{"titulo": "Capitulo 1"}]}}}

        with (
            patch("app.core.services.ai.ai_service.settings", _settings(primary="mistral", fallback=False)),
            patch.object(svc, "_sleep_with_cancel", return_value=None),
        ):
            for _ in range(3):
                with pytest.raises(RuntimeError):
                    svc.generate(project, format_detail, None)

        status = svc.providers_status_payload()
        mistral_status = next(item for item in status["providers"] if item["id"] == "mistral")
        assert mistral_status["health"] == "DEGRADED"
        assert mistral_status["stats"]["errors_last_15m"] >= 3

    def test_fixed_mode_status_has_no_fallback_provider(self, ai_svc):
        svc, gemini, mistral = ai_svc
        svc.set_provider_selection(
            {
                "provider": "mistral",
                "model": "mistral-medium-2505",
                "fallback_provider": "gemini",
                "fallback_model": "gemini-2.0-flash",
                "mode": "auto",
            }
        )
        gemini.is_configured.return_value = True
        mistral.is_configured.return_value = True

        status = svc.providers_status_payload()

        assert status["selected_provider"] == "mistral"
        assert status["mode"] == "fixed"
        assert status["fallback_provider"] == ""
        assert status["fallback_model"] == ""

    def test_fixed_mode_generation_does_not_use_removed_providers(self, ai_svc):
        svc, gemini, mistral = ai_svc
        openrouter = MagicMock()
        openrouter.is_configured.return_value = True
        openrouter.generate.return_value = "Contenido por OpenRouter."
        svc._clients["openrouter"] = openrouter
        svc.set_provider_selection(
            {
                "provider": "mistral",
                "model": "mistral-medium-2505",
                "fallback_provider": "gemini",
                "fallback_model": "gemini-2.0-flash",
                "mode": "auto",
            }
        )
        gemini.is_configured.return_value = True
        mistral.is_configured.return_value = True
        mistral.generate.return_value = "Contenido por Mistral."
        gemini.generate.return_value = "No debe usarse"

        project = {"id": "proj-skip-exhausted-fallback", "title": "Fallback", "variables": {"tema": "x"}}
        format_detail = {"definition": {"cuerpo": {"capitulos": [{"titulo": "Capitulo 1"}]}}}

        with (
            patch("app.core.services.ai.ai_service.settings", _settings(primary="mistral", fallback=True)),
            patch.object(svc, "_sleep_with_cancel", return_value=None),
        ):
            result = svc.generate(project, format_detail, None)

        assert result["sections"][0]["content"] == "Contenido por Mistral."
        assert mistral.generate.call_count == 1
        gemini.generate.assert_not_called()
        openrouter.generate.assert_not_called()

    def test_generate_preserves_structured_blocks_in_allowed_sections(self, ai_svc):
        svc, gemini, mistral = ai_svc
        _set_selection(svc, "mistral", mode="fixed")
        gemini.is_configured.return_value = False
        mistral.is_configured.return_value = True
        mistral.generate.return_value = (
            "Texto previo del cronograma.\n\n"
            "<<<TABLE_JSON\n"
            '{"tipo":"tabla","id":"tab_001","titulo":"Cronograma","encabezados":["Actividad","Mes 1","Mes 2"],'
            '"filas":[["Revision","X",""],["Validacion","","X"]]}\n'
            "TABLE_JSON>>>\n\n"
            "Texto posterior del cronograma."
        )

        project = {
            "id": "proj-structured-001",
            "title": "Structured",
            "variables": {"tema": "Planificacion"},
            "values": {"tema": "Planificacion"},
        }
        prompt = {"template": "Genera contenido sobre {{tema}}."}
        format_detail = {
            "definition": {
                "cuerpo": {
                    "capitulos": [
                        {"titulo": "Cronograma"},
                    ]
                }
            }
        }

        with patch("app.core.services.ai.ai_service.settings", _settings(primary="mistral", fallback=False)):
            result = svc.generate(project, format_detail, prompt)

        content = result["sections"][0]["content"]
        assert isinstance(content, list)
        assert content[0]["tipo"] == "parrafo"
        assert content[1]["tipo"] == "tabla"
        assert content[2]["tipo"] == "parrafo"

    def test_generate_repairs_schedule_and_budget_tables_to_canonical_table_json(self, ai_svc):
        svc, gemini, mistral = ai_svc
        _set_selection(svc, "mistral", mode="fixed")
        gemini.is_configured.return_value = False
        mistral.is_configured.return_value = True
        mistral.generate.side_effect = [
            _generic_schedule_raw_response(),
            _generic_budget_raw_response(),
            _schedule_blueprint_raw_response(),
            _canonical_budget_raw_response(),
        ]

        project = {
            "id": "proj-table-repair-001",
            "title": "Tablas canonicas",
            "variables": _project_quant_values(),
            "values": _project_quant_values(),
        }
        prompt = {"template": "Genera contenido sobre {{title}}.", "format_id": "unac-proyecto-cuant"}
        planned_sections = [
            {
                "sectionId": "sec-crono",
                "path": "V. CRONOGRAMA DE ACTIVIDADES",
                "title": "V. CRONOGRAMA DE ACTIVIDADES",
                "hints": "",
                "additional_context": "",
            },
            {
                "sectionId": "sec-pres",
                "path": "VI. PRESUPUESTO",
                "title": "VI. PRESUPUESTO",
                "hints": "",
                "additional_context": "",
            },
        ]

        with (
            patch("app.core.services.ai.ai_service.settings", _settings(primary="mistral", fallback=False)),
            patch.object(svc, "_sleep_with_cancel", return_value=None),
        ):
            result = svc.generate(
                project,
                {"id": "unac-proyecto-cuant", "definition": {}},
                prompt,
                planned_sections=planned_sections,
            )

        sections = {item["path"]: item["content"] for item in result["sections"]}
        cronograma = sections["V. CRONOGRAMA DE ACTIVIDADES"][0]
        presupuesto = sections["VI. PRESUPUESTO"][0]

        assert cronograma["subtipo"] == "cronograma_actividades"
        assert cronograma["orientacion"] == "landscape"
        assert len(cronograma["encabezados"]) == 13
        assert len(cronograma["filas"]) == 35

        assert presupuesto["subtipo"] == "presupuesto_investigacion"
        assert presupuesto["orientacion"] == "portrait"
        assert len(presupuesto["encabezados"]) == 5
        assert len(presupuesto["filas"]) == 14
        assert mistral.generate.call_count == 3

    def test_schedule_repair_prompt_requests_semantic_blueprint(self, ai_svc):
        svc, gemini, mistral = ai_svc
        _set_selection(svc, "mistral", mode="fixed")
        gemini.is_configured.return_value = False
        mistral.is_configured.return_value = True
        mistral.generate.side_effect = [
            _generic_schedule_raw_response(),
            _schedule_blueprint_raw_response(),
        ]

        project = {
            "id": "proj-table-repair-sec-0025",
            "title": "Cronograma canonico",
            "variables": _project_quant_values(),
            "values": _project_quant_values(),
        }
        prompt = {"template": "Genera contenido sobre {{title}}.", "format_id": "unac-proyecto-cuant"}
        planned_sections = [
            {
                "sectionId": "sec-0025",
                "path": "V. CRONOGRAMA DE ACTIVIDADES",
                "title": "V. CRONOGRAMA DE ACTIVIDADES",
                "hints": "",
                "additional_context": "",
            }
        ]

        with (
            patch("app.core.services.ai.ai_service.settings", _settings(primary="mistral", fallback=False)),
            patch.object(svc, "_sleep_with_cancel", return_value=None),
        ):
            result = svc.generate(
                project,
                {"id": "unac-proyecto-cuant", "definition": {}},
                prompt,
                planned_sections=planned_sections,
            )

        repair_prompt = mistral.generate.call_args_list[1].args[0]
        assert "Errores detectados por el validador:" in repair_prompt
        assert "- encabezados_invalidos" in repair_prompt
        assert "- fila_0_invalida" in repair_prompt
        assert "- fila_con_longitud_invalida" in repair_prompt
        assert "Devuelve un blueprint semantico con tipo='tabla' y subtipo='cronograma_plan'." in repair_prompt
        assert "No generes la tabla institucional final del cronograma." in repair_prompt
        assert "No uses fences markdown tipo ```json ni ```." in repair_prompt
        assert result["sections"][0]["content"][0]["subtipo"] == "cronograma_actividades"

    def test_schedule_repair_uses_synthetic_fallback_when_second_pass_remains_invalid(self, ai_svc):
        svc, gemini, mistral = ai_svc
        _set_selection(svc, "mistral", mode="fixed")
        gemini.is_configured.return_value = False
        mistral.is_configured.return_value = True
        mistral.generate.side_effect = [
            _failed_sec_0025_schedule_raw_response(),
            _generic_schedule_raw_response(),
        ]

        project = {
            "id": "proj-table-repair-fails",
            "title": "Cronograma invalido",
            "variables": _project_quant_values(),
            "values": _project_quant_values(),
        }
        prompt = {"template": "Genera contenido sobre {{title}}.", "format_id": "unac-proyecto-cuant"}
        planned_sections = [
            {
                "sectionId": "sec-0025",
                "path": "V. CRONOGRAMA DE ACTIVIDADES",
                "title": "V. CRONOGRAMA DE ACTIVIDADES",
                "hints": "",
                "additional_context": "",
            }
        ]

        with (
            patch("app.core.services.ai.ai_service.settings", _settings(primary="mistral", fallback=False)),
            patch.object(svc, "_sleep_with_cancel", return_value=None),
        ):
            result = svc.generate(
                project,
                {"id": "unac-proyecto-cuant", "definition": {}},
                prompt,
                planned_sections=planned_sections,
            )

        cronograma = result["sections"][0]["content"][0]
        assert cronograma["subtipo"] == "cronograma_actividades"
        assert len(cronograma["filas"]) == 35

    def test_budget_repair_uses_synthetic_fallback_when_second_pass_remains_invalid(self, ai_svc):
        svc, gemini, mistral = ai_svc
        _set_selection(svc, "mistral", mode="fixed")
        gemini.is_configured.return_value = False
        mistral.is_configured.return_value = True
        mistral.generate.side_effect = [
            _generic_budget_raw_response(),
            _generic_budget_raw_response(),
        ]

        project = {
            "id": "proj-budget-repair-fails",
            "title": "Presupuesto invalido",
            "variables": _project_quant_values(),
            "values": _project_quant_values(),
        }
        prompt = {"template": "Genera contenido sobre {{title}}.", "format_id": "unac-proyecto-cuant"}
        planned_sections = [
            {
                "sectionId": "sec-pres",
                "path": "VI. PRESUPUESTO",
                "title": "VI. PRESUPUESTO",
                "hints": "",
                "additional_context": "",
            }
        ]

        with (
            patch("app.core.services.ai.ai_service.settings", _settings(primary="mistral", fallback=False)),
            patch.object(svc, "_sleep_with_cancel", return_value=None),
        ):
            result = svc.generate(
                project,
                {"id": "unac-proyecto-cuant", "definition": {}},
                prompt,
                planned_sections=planned_sections,
            )

        presupuesto = result["sections"][0]["content"][0]
        assert presupuesto["subtipo"] == "presupuesto_investigacion"
        assert presupuesto["orientacion"] == "portrait"
        assert len(presupuesto["encabezados"]) == 5
        assert len(presupuesto["filas"]) == 14
