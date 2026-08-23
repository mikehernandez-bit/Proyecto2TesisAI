from app.core.services.ai.section_prompt_profiles import build_section_editorial_context


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
                "¿De que manera el plan RCM mejorara la disponibilidad "
                "inherente de la flota CAT 24M en 2025?"
            ),
            "objetivo_general": (
                "Determinar como el plan RCM mejorara la disponibilidad "
                "inherente de la flota CAT 24M en 2025."
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
    }


def test_formulacion_context_enforces_dimension_order():
    context = build_section_editorial_context(
        format_id="unac-proyecto-cuant",
        section_id="sec-formulacion",
        section_path="I. PLANTEAMIENTO DEL PROBLEMA/1.2 Formulacion del problema",
        values=_sample_values(),
    )

    assert "Rango de palabras aceptable: minimo obligatorio 89 palabras narrativas" in context
    assert "Orden obligatorio de dimensiones especificas: Confiabilidad; Mantenibilidad" in context
    assert "confiabilidad -> mantenibilidad" in context
    assert "No agregues ningun parrafo final despues de las preguntas." in context


def test_problem_detail_context_requires_professor_style_narrative_between_figures():
    context = build_section_editorial_context(
        format_id="unac-proyecto-cuant",
        section_id="sec-problem",
        section_path="I. PLANTEAMIENTO DEL PROBLEMA/1.1 Descripcion de la realidad problematica",
        values=_sample_values(),
    )

    assert "el ejemplo guia del profesor" in context
    assert "no redactes guias manuales" in context
    assert "Parrafo 7 (130 a 170 palabras): interpreta Figura 1.1" in context
    assert "Parrafo 13 (170 a 220 palabras): interpreta Figura 1.4 cuantitativamente" in context
    assert "No cuentes la guia azul como desarrollo academico" in context
    assert "Antes de cada figura debe existir un parrafo largo y especifico" in context


def test_objetivos_context_preserves_general_objective_and_order():
    context = build_section_editorial_context(
        format_id="unac-proyecto-cuant",
        section_id="sec-objetivos",
        section_path="I. PLANTEAMIENTO DEL PROBLEMA/1.3 Objetivos",
        values=_sample_values(),
    )

    assert "Replica exactamente el mismo orden de los problemas especificos" in context
    assert "Si el objetivo general ya coincide con la variable dependiente principal del proyecto" in context
    assert "No inviertas el orden de confiabilidad y mantenibilidad" in context


def test_justificacion_context_is_calibrated_to_rcm_case():
    context = build_section_editorial_context(
        format_id="unac-proyecto-cuant",
        section_id="sec-justificacion",
        section_path="I. PLANTEAMIENTO DEL PROBLEMA/1.4 Justificacion",
        values=_sample_values(),
    )

    assert "linea exacta '1.4.1 Justificacion normativa'" in context
    assert "subtitulos 1.4.1, 1.4.2, 1.4.3, 1.4.4, 1.4.5 y 1.4.6" in context
    assert "SAE JA1011 como eje tecnico del RCM" in context
    assert "ISO 14224:2016" in context
    assert "Moubray, seis patrones de falla, analisis funcional, AMEF, MTBF, MTTR" in context
    assert "CBM e inspeccion tecnica" in context
    assert "diseno preexperimental longitudinal con preprueba/posprueba" in context
    assert "OPEX, costos correctivos no programados" in context
    assert "ISO 2631" in context
    assert "No permitas que ISO 55000 desplace a SAE JA1011" in context


def test_delimitaciones_context_is_operational_not_generic():
    context = build_section_editorial_context(
        format_id="unac-proyecto-cuant",
        section_id="sec-delimitaciones",
        section_path="I. PLANTEAMIENTO DEL PROBLEMA/1.5 Delimitaciones de la investigacion",
        values=_sample_values(),
    )

    assert "linea exacta '1.5.2 Delimitacion temporal'" in context
    assert "subtitulos 1.5.1, 1.5.2 y 1.5.3" in context
    assert "temporada seca, temporada humeda y horas de operacion estadisticamente significativas" in context
    assert "TPM y Lean Maintenance" in context
    assert "No agregues exclusiones temporales no declaradas por el usuario" in context


def test_chapter_two_backgrounds_context_requires_five_dense_antecedents():
    context = build_section_editorial_context(
        format_id="unac-proyecto-cuant",
        section_id="sec-antecedentes",
        section_path="II. MARCO TEORICO/2.1 Antecedentes",
        values=_sample_values(),
    )

    assert "minimo obligatorio 3245 palabras narrativas" in context
    assert "Antecedentes internacionales: cinco antecedentes" in context
    assert "titulo exacto, problema abordado, pregunta o proposito, objetivo" in context
    assert "No insertes figuras, tablas, mapas conceptuales ni formulas" in context
    assert "Evita antecedentes vagos" in context
    assert "Cada antecedente debe cerrar con el aporte concreto al titulo" in context


def test_chapter_two_theoretical_bases_context_places_figures_and_formulas():
    context = build_section_editorial_context(
        format_id="unac-proyecto-cuant",
        section_id="sec-bases",
        section_path="II. MARCO TEORICO/2.2 Bases teoricas",
        values=_sample_values(),
    )

    assert "Subtema teorico principal de la variable independiente" in context
    assert "Cada subtitulo debe ir como linea independiente con patron 2.2.x" in context
    assert "No arrastres nombres, autores, normas, indicadores o equipos del ejemplo guia" in context
    assert "Figuras: usa 0 a 4 segun necesidad" in context
    assert "Formulas: usa FORMULA_JSON solo si el tema requiere indicadores" in context
    assert "No insertes matriz de consistencia ni matriz de operacionalizacion" in context
    assert "Las figuras nunca deben abrir la seccion ni un subtema" in context
    assert "Prohibido hardcodear elementos del ejemplo guia" in context
    assert "ocho subtitulos de tercer nivel en este orden exacto" in context
    assert "Figura 2.1 despues del subtema 2.2.2" in context
    assert "2.2.5 Disponibilidad inherente, 2.2.6 Confiabilidad y 2.2.7 Mantenibilidad" in context


def test_chapter_two_theoretical_bases_context_applies_to_literature_review_name():
    context = build_section_editorial_context(
        format_id="unac-proyecto-cual",
        section_id="sec-bases",
        section_path="II. REVISIÓN DE LITERATURA/2.2 Bases teóricas",
        values=_sample_values(),
    )

    assert "Subtema teorico principal de la variable independiente" in context
    assert "Figuras: usa 0 a 4 segun necesidad" in context
    assert "No generes TABLE_JSON, matriz de consistencia" in context


def test_chapter_two_conceptual_and_terms_are_text_only():
    conceptual = build_section_editorial_context(
        format_id="unac-proyecto-cuant",
        section_id="sec-conceptual",
        section_path="II. MARCO TEORICO/2.3 Marco conceptual",
        values=_sample_values(),
    )
    terms = build_section_editorial_context(
        format_id="unac-proyecto-cuant",
        section_id="sec-terms",
        section_path="II. MARCO TEORICO/2.4 Definicion de terminos basicos",
        values=_sample_values(),
    )

    assert "No generes tabla, figura, mapa conceptual ni formula en 2.3" in conceptual
    assert "Variable independiente: usar el nombre exacto registrado en el proyecto" in conceptual
    assert "Dimensiones de la variable dependiente" in conceptual
    assert "Lista textual con formato exacto 'Termino. Definicion...'" in terms
    assert "No insertes figura, tabla, formula ni cierre final en 2.4" in terms
    assert "Incluye 10 a 15 terminos derivados del area" in terms
    assert "No hardcodees terminos de mantenimiento" in terms


def test_chapter_three_hypotheses_context_preserves_dimension_order():
    context = build_section_editorial_context(
        format_id="unac-proyecto-cuant",
        section_id="sec-hipotesis",
        section_path="III. HIPOTESIS Y VARIABLES/3.1 Hipotesis",
        values=_sample_values(),
    )

    assert "Primera hipotesis especifica: mejora de la confiabilidad" in context
    assert "Segunda hipotesis especifica: mejora de la mantenibilidad" in context
    assert "confiabilidad -> mantenibilidad" in context
    assert "No agregues figuras, tablas ni explicacion adicional en 3.1" in context


def test_chapter_three_operationalization_context_is_bridge_only():
    context = build_section_editorial_context(
        format_id="unac-proyecto-cuant",
        section_id="sec-operacionalizacion",
        section_path="III. HIPOTESIS Y VARIABLES/3.2 Operacionalizacion de variable",
        values=_sample_values(),
    )

    assert "80 a 160 palabras de puente textual" in context
    assert "No generes TABLE_JSON, FIGURE_JSON ni FORMULA_JSON en 3.2" in context
    assert "No reconstruyas manualmente tablas 3.1/3.2" in context


def test_chapter_four_design_context_uses_textual_schema_without_visuals():
    context = build_section_editorial_context(
        format_id="unac-proyecto-cuant",
        section_id="sec-diseno",
        section_path="IV. METODOLOGIA DEL PROYECTO/4.1 Diseno metodologico",
        values=_sample_values(),
    )

    assert "tipo, nivel o alcance y diseno metodologico reales del proyecto" in context
    assert "Esquema textual opcional si el diseno lo requiere: M O\u2081 X O\u2082" in context
    assert "No generes Tabla 4.1, matriz metodologica, FIGURE_JSON ni figura numerada" in context
    assert "El esquema M O\u2081 X O\u2082 debe quedar como texto o FORMULA_JSON" in context
    assert "No hardcodees mantenimiento, mineria, unidad minera, fechas ni equipos" in context


def test_chapter_four_methodology_sections_block_tables_and_figures():
    method = build_section_editorial_context(
        format_id="unac-proyecto-cuant",
        section_id="sec-metodo",
        section_path="IV. METODOLOGIA DEL PROYECTO/4.2 Metodo de investigacion",
        values=_sample_values(),
    )
    population = build_section_editorial_context(
        format_id="unac-proyecto-cuant",
        section_id="sec-poblacion",
        section_path="IV. METODOLOGIA DEL PROYECTO/4.3 Poblacion y muestra",
        values=_sample_values(),
    )
    techniques = build_section_editorial_context(
        format_id="unac-proyecto-cuant",
        section_id="sec-tecnicas",
        section_path="IV. METODOLOGIA DEL PROYECTO/4.5 Tecnicas e instrumentos para la recoleccion de la informacion",
        values=_sample_values(),
    )
    processing = build_section_editorial_context(
        format_id="unac-proyecto-cuant",
        section_id="sec-procesamiento",
        section_path="IV. METODOLOGIA DEL PROYECTO/4.6 Analisis y procesamiento de datos",
        values=_sample_values(),
    )

    assert "enfoque de investigacion y tipo de informacion que se recolectara" in method
    assert "metodo o estrategia analitica" in method
    assert "No fuerces enfoque cuantitativo ni metodo hipotetico-deductivo" in method
    assert "No generes figuras, tablas ni cierres genericos en 4.2" in method
    assert "Un solo parrafo breve" in population
    assert "No agregues desarrollo extenso, estratificacion innecesaria, figuras ni tablas" in population
    assert "No hardcodees cantidades, equipos, aulas, pacientes, usuarios o instituciones" in population
    assert "No generes Tabla 4.2, figura, flujo metodologico ni frase de sintesis de tabla" in techniques
    assert "No hardcodees manuales, normas, historiales, software, indicadores o instrumentos" in techniques
    assert "No generes Tabla 4.3, flujo de procesamiento, figura ni placeholder tecnico" in processing
    assert "No fuerces Pareto, AMEF, NPR, indicadores de mantenimiento" in processing


def test_chapter_four_place_and_ethics_follow_guide():
    place = build_section_editorial_context(
        format_id="unac-proyecto-cuant",
        section_id="sec-lugar",
        section_path="IV. METODOLOGIA DEL PROYECTO/4.4 Lugar de estudio",
        values=_sample_values(),
    )
    ethics = build_section_editorial_context(
        format_id="unac-proyecto-cuant",
        section_id="sec-etica",
        section_path="IV. METODOLOGIA DEL PROYECTO/4.7 Aspectos eticos en Investigacion",
        values=_sample_values(),
    )

    assert "Ubicacion geografica, institucional, empresarial" in place
    assert "no agregues figura de ubicacion, tabla ni cierre adicional" in place
    assert "marco etico institucional, reglamento, comite, norma o codigo" in ethics
    assert "No hardcodees UNAC ni Resolucion N. 260-19-CU" in ethics
    assert "probidad, transparencia" in ethics
    assert "consentimiento informado, anonimato, participacion voluntaria" in ethics


def test_schedule_and_budget_context_require_valid_table_json_without_canonical_replacement():
    schedule = build_section_editorial_context(
        format_id="unac-proyecto-cuant",
        section_id="sec-cronograma",
        section_path="V. CRONOGRAMA DE ACTIVIDADES/Cronograma Detallado de Actividades",
        values=_sample_values(),
    )
    budget = build_section_editorial_context(
        format_id="unac-proyecto-cuant",
        section_id="sec-presupuesto",
        section_path="VI. PRESUPUESTO/Presupuesto del Proyecto",
        values=_sample_values(),
    )

    assert "TABLE_JSON valido" in schedule
    assert "tabla canonica del cronograma" not in schedule.lower()
    assert "TABLE_JSON valido" in budget
    assert "tabla canonica del presupuesto" not in budget.lower()
