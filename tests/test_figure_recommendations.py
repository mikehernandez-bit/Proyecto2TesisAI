from app.core.services.ai.ai_service import AIService
from app.core.services.ai.figure_recommendations import apply_figure_recommendations
from app.core.services.ai.output_validator import OutputValidator


def test_does_not_add_recommended_figure_to_chapter_four_design_section() -> None:
    sections = [
        {
            "sectionId": "sec-met",
            "path": "IV. METODOLOGIA/4.1 Diseno metodologico",
            "content": (
                "La metodologia del estudio organiza las etapas de diagnostico, recoleccion de datos, "
                "procesamiento tecnico y evaluacion de resultados para el sistema de mantenimiento predictivo."
            ),
        }
    ]

    updated = apply_figure_recommendations(
        sections,
        values={"title": "mantenimiento predictivo en motores de combustion interna"},
    )

    content = updated[0]["content"]
    assert isinstance(content, str)
    assert "Flujo metodologico" not in content


def test_replaces_generic_figure_caption_with_specific_title() -> None:
    sections = [
        {
            "sectionId": "sec-res",
            "path": "V. RESULTADOS/5.1 Presentacion de resultados",
            "content": [
                {"tipo": "parrafo", "texto": "Los resultados comparan el comportamiento de los indicadores clave."},
                {
                    "tipo": "figura",
                    "titulo": "Diagrama ilustrativo",
                    "caption": "Figura de ejemplo",
                    "ruta_placeholder": "assets/placeholder_figura.png",
                },
            ],
        }
    ]

    updated = apply_figure_recommendations(
        sections,
        values={"tema": "analisis predictivo de fallas en motores industriales"},
    )

    figure = updated[0]["content"][1]
    assert figure["tipo"] == "figura"
    assert figure["titulo"] == (
        "Visualizacion comparativa de resultados de analisis predictivo de fallas en motores industriales"
    )
    assert figure["caption"] == figure["titulo"]


def test_does_not_insert_figure_in_text_only_sections() -> None:
    sections = [
        {
            "sectionId": "sec-conc",
            "path": "VII. CONCLUSIONES/7.1 Conclusiones",
            "content": "Las conclusiones sintetizan los hallazgos finales del estudio.",
        }
    ]

    updated = apply_figure_recommendations(
        sections,
        values={"title": "sistema de monitoreo basado en IA"},
    )

    assert isinstance(updated[0]["content"], str)


def test_project_reality_problem_gets_four_required_figures() -> None:
    sections = [
        {
            "sectionId": "sec-problem",
            "path": "I. PLANTEAMIENTO DEL PROBLEMA/1.1 Descripcion de la realidad problematica",
            "content": "Diagnostico tecnico de la baja disponibilidad de la flota CAT 24M.",
        }
    ]

    updated = apply_figure_recommendations(
        sections,
        values={"title": "Plan RCM para flota CAT 24M"},
        format_id="unac-proyecto-cuant",
    )

    content = updated[0]["content"]
    figures = [block for block in content if block.get("tipo") == "figura"]
    assert len(figures) == 4
    assert figures[0]["titulo"] == "Diagrama de Pareto de modos de falla en flota CAT 24M"
    assert figures[1]["titulo"] == "Análisis de Causa-Efecto de Baja Disponibilidad (Ishikawa)"
    assert figures[2]["titulo"] == "Matriz de Relevancia para el filtrado de alternativas de solución"
    assert figures[3]["titulo"] == "Matriz de Priorización de soluciones factibles"
    assert all("ruta_placeholder" not in figure for figure in figures)
    assert all(figure["numbered"] is False and figure["diagram_type"] for figure in figures)
    assert all("placeholder_text" not in figure for figure in figures)
    assert all(figure["fuente"] == "Elaboración propia." for figure in figures)
    assert all("nota" not in figure and "nota_color" not in figure for figure in figures)
    assert all(figure["diagram_data"]["qualitative"] is True for figure in figures)


def test_project_reality_problem_short_text_does_not_group_figures_at_end() -> None:
    sections = [
        {
            "sectionId": "sec-problem",
            "path": "I. PLANTEAMIENTO DEL PROBLEMA/1.1 Descripcion de la realidad problematica",
            "content": "Diagnostico tecnico de baja disponibilidad en la flota CAT 24M.",
        }
    ]

    updated = apply_figure_recommendations(
        sections,
        values={"title": "Plan RCM para flota CAT 24M"},
        format_id="unac-proyecto-cuant",
    )

    content = updated[0]["content"]
    figure_positions = [index for index, block in enumerate(content) if block.get("tipo") == "figura"]
    assert len(figure_positions) == 4
    assert all(content[position - 1]["tipo"] == "parrafo" for position in figure_positions)
    assert not any(
        content[index].get("tipo") == "figura" and content[index + 1].get("tipo") == "figura"
        for index in range(len(content) - 1)
    )
    assert all("diagram_type" in content[position] and "fuente" in content[position] for position in figure_positions)
    assert all("placeholder_text" not in content[position] for position in figure_positions)


def test_project_reality_problem_removes_stale_placeholder_paragraphs() -> None:
    sections = [
        {
            "sectionId": "sec-problem",
            "path": "I. PLANTEAMIENTO DEL PROBLEMA/1.1 Descripcion de la realidad problematica",
            "content": [
                {"tipo": "parrafo", "texto": "El diagnostico inicial se ordena mediante Pareto."},
                {"tipo": "parrafo", "texto": "Figura 1.1 Diagrama de Pareto de modos de falla en flota CAT 24M"},
                {"tipo": "parrafo", "texto": "Figura pendiente de elaboración propia"},
                {"tipo": "parrafo", "texto": "Fuente: Elaboración propia"},
                {
                    "tipo": "parrafo",
                    "texto": "Nota técnica: La Figura 1.1 debe construirse a partir de datos preliminares.",
                },
            ],
        }
    ]

    updated = apply_figure_recommendations(
        sections,
        values={"title": "Plan RCM para flota CAT 24M"},
        format_id="unac-proyecto-cuant",
    )

    visible_text = " ".join(str(block.get("texto") or "") for block in updated[0]["content"])
    figures = [block for block in updated[0]["content"] if block.get("tipo") == "figura"]

    assert "Figura pendiente de elaboración propia" not in visible_text
    assert "Figura 1.1 Diagrama de Pareto" not in visible_text
    assert "La Figura 1.1 debe construirse" not in visible_text
    assert figures[0]["fuente"] == "Elaboración propia."
    assert figures[0]["numbered"] is False
    assert figures[0]["diagram_type"] == "pareto_qualitative"


def test_project_reality_problem_removes_old_markdown_figure_blocks_inside_text() -> None:
    sections = [
        {
            "sectionId": "sec-problem",
            "path": "I. PLANTEAMIENTO DEL PROBLEMA/1.1 Descripcion de la realidad problematica",
            "content": (
                "La concentración de fallas exige analizar causas raíz.\n"
                "Figura 1.2\n"
                "Diagrama de Ishikawa para fallas en sistema hidráulico de motoniveladoras CAT 24M\n"
                "*Fuente: Elaboración propia.*\n"
                "*Guía técnica: El diagrama debe estructurarse con seis ramas principales.\n"
                "Cada rama debe descomponerse en subcausas específicas.*\n"
                "Entre las alternativas de solución evaluadas, el RCM emerge como estrategia viable.\n"
                "Figura 1.3\n"
                "Matriz de Relevancia para alternativas de mejora de disponibilidad\n"
                "*Fuente: Elaboración propia.*\n"
                "*Guía técnica: La matriz debe incluir criterios como impacto, costo y tiempo.\n"
                "El RCM debe destacar por su equilibrio entre efectividad y viabilidad.*"
            ),
        }
    ]

    updated = apply_figure_recommendations(
        sections,
        values={"title": "Plan RCM para flota CAT 24M"},
        format_id="unac-proyecto-cuant",
    )

    paragraphs = "\n".join(str(block.get("texto") or "") for block in updated[0]["content"])
    figures = [block for block in updated[0]["content"] if block.get("tipo") == "figura"]

    assert len(figures) == 4
    assert "*Fuente:" not in paragraphs
    assert "*Guía técnica:" not in paragraphs
    assert "Diagrama de Ishikawa para fallas en sistema hidráulico" not in paragraphs
    assert "Matriz de Relevancia para alternativas de mejora de disponibilidad" not in paragraphs
    assert all("nota" not in figure for figure in figures)


def test_project_reality_problem_removes_loose_guide_blocks_without_asterisks() -> None:
    sections = [
        {
            "sectionId": "sec-problem",
            "path": "I. PLANTEAMIENTO DEL PROBLEMA/1.1 Descripcion de la realidad problematica",
            "content": (
                "El diagnostico local revela concentracion de fallas en tres sistemas principales.\n"
                "Diagrama de Pareto de fallas por sistema en motoniveladoras CAT 24M, 2023-2024.\n"
                "Guia tecnica: Para elaborar este diagrama, se requiere recopilar datos historicos.\n"
                "Luego, se calcula la frecuencia absoluta y acumulada de cada categoria.\n"
                "El eje vertical izquierdo representa la frecuencia de fallas.\n"
                "El analisis causal mediante Ishikawa explica metodos y medio ambiente.\n"
                "Matriz de Relevancia de alternativas de solucion para mejorar la disponibilidad.\n"
                "Guia tecnica: La matriz se elabora asignando pesos a cada criterio.\n"
                "El RCM obtiene 4.5 en el criterio tecnico.\n"
                "Finalmente, la matriz de priorizacion ponderada valida la alternativa seleccionada."
            ),
        }
    ]

    updated = apply_figure_recommendations(
        sections,
        values={"title": "Plan RCM para flota CAT 24M"},
        format_id="unac-proyecto-cuant",
    )

    paragraphs = "\n".join(str(block.get("texto") or "") for block in updated[0]["content"])

    assert "Diagrama de Pareto de fallas por sistema" not in paragraphs
    assert "Guia tecnica:" not in paragraphs
    assert "Luego, se calcula" not in paragraphs
    assert "Matriz de Relevancia de alternativas" not in paragraphs
    assert "El RCM obtiene 4.5" not in paragraphs


def test_project_reality_problem_interleaves_figures_after_references() -> None:
    sections = [
            {
                "sectionId": "sec-problem",
                "path": "I. PLANTEAMIENTO DEL PROBLEMA/1.1 Descripcion de la realidad problematica",
                "content": (
                    "El diagnostico inicial requiere ordenar los modos de falla por Pareto. "
                    "La Figura 1.1 muestra el punto donde debe colocarse el diagrama.\n\n"
                    "El analisis causa-efecto se organiza con Ishikawa y ramas 6M. "
                    "La Figura 1.2 muestra el punto donde debe colocarse el diagrama.\n\n"
                    "La matriz de relevancia compara alternativas de solucion por viabilidad tecnica. "
                    "La Figura 1.3 muestra el punto donde debe colocarse la matriz.\n\n"
                    "La matriz de priorizacion usa criterios ponderados y puntaje ponderado. "
                    "La Figura 1.4 muestra el punto donde debe colocarse la matriz."
                ),
            }
        ]

    updated = apply_figure_recommendations(
        sections,
        values={"title": "Plan RCM para flota CAT 24M"},
        format_id="unac-proyecto-cuant",
    )

    content = updated[0]["content"]
    figure_positions = [index for index, block in enumerate(content) if block.get("tipo") == "figura"]
    assert len(figure_positions) == 4
    assert all(content[position - 1]["tipo"] == "parrafo" for position in figure_positions)
    assert not any(
        content[index].get("tipo") == "figura" and content[index + 1].get("tipo") == "figura"
        for index in range(len(content) - 1)
    )
    assert all(content[figure_positions[index] + 1]["tipo"] == "parrafo" for index in range(len(figure_positions) - 1))


def test_project_reality_problem_keeps_figures_ordered_when_later_matrix_is_mentioned_first() -> None:
    sections = [
        {
            "sectionId": "sec-problem",
            "path": "I. PLANTEAMIENTO DEL PROBLEMA/1.1 Descripcion de la realidad problematica",
            "content": (
                "La mineria a cielo abierto requiere continuidad operativa de la flota CAT 24M.\n\n"
                "Finalmente, las alternativas factibles se ordenan con una matriz de priorizacion para justificar "
                "la seleccion de la solucion desarrollada.\n\n"
                "El diagnostico local revela que las fallas registradas se concentran en tres sistemas principales "
                "y confirman la existencia de pocos vitales.\n\n"
                "Esta concentracion exige analizar la causa raiz mediante metodos, medio ambiente y maquinaria.\n\n"
                "Ante esta evidencia causal, se comparan alternativas de solucion segun viabilidad tecnica y "
                "viabilidad economica.\n\n"
                "La priorizacion ponderada diferencia entre reducir MTTR y evitar recurrencia de fallas."
            ),
        }
    ]

    updated = apply_figure_recommendations(
        sections,
        values={"title": "Plan RCM para flota CAT 24M"},
        format_id="unac-proyecto-cuant",
    )

    figures = [block for block in updated[0]["content"] if block.get("tipo") == "figura"]

    assert [figure["titulo"] for figure in figures] == [
        "Diagrama de Pareto de modos de falla en flota CAT 24M",
        "Análisis de Causa-Efecto de Baja Disponibilidad (Ishikawa)",
        "Matriz de Relevancia para el filtrado de alternativas de solución",
        "Matriz de Priorización de soluciones factibles",
    ]


def test_project_reality_problem_places_figure_after_best_long_preceding_analysis() -> None:
    long_pareto_paragraph = (
        "A nivel local, el diagnostico operativo realizado a la flota de motoniveladoras CAT 24M revela una "
        "brecha de disponibilidad frente al target corporativo. Para determinar el origen tecnico de esta "
        "desviacion, el historial de fallas se somete a una jerarquizacion mediante Pareto, evidenciando que "
        "la frecuencia de fallas no es uniforme y que los pocos vitales concentran la mayor parte de eventos "
        "de parada, tal como se aprecia en la Figura 1.1."
    )
    sections = [
        {
            "sectionId": "sec-problem",
            "path": "I. PLANTEAMIENTO DEL PROBLEMA/1.1 Descripcion de la realidad problematica",
            "content": [
                {"tipo": "parrafo", "texto": "El diagnostico tecnico revela fallas en tres sistemas criticos."},
                {"tipo": "parrafo", "texto": long_pareto_paragraph},
                {
                    "tipo": "parrafo",
                    "texto": (
                        "Una vez segregados los sistemas vitales, se examina su causa raiz mediante Ishikawa, "
                        "identificando que los metodos de mantenimiento y el medio ambiente operacional explican "
                        "la baja disponibilidad, tal como se observa en la Figura 1.2."
                    ),
                },
            ],
        }
    ]

    updated = apply_figure_recommendations(
        sections,
        values={"title": "Plan RCM para flota CAT 24M"},
        format_id="unac-proyecto-cuant",
    )

    content = updated[0]["content"]
    pareto_index = next(
        index
        for index, block in enumerate(content)
        if block.get("tipo") == "figura"
        and block.get("titulo") == "Diagrama de Pareto de modos de falla en flota CAT 24M"
    )

    assert content[pareto_index - 1]["texto"] == long_pareto_paragraph


def test_project_reality_problem_drops_non_controlled_existing_figures() -> None:
    sections = [
        {
            "sectionId": "sec-problem",
            "path": "I. PLANTEAMIENTO DEL PROBLEMA/1.1 Descripcion de la realidad problematica",
            "content": [
                {"tipo": "parrafo", "texto": "El diagnostico local revela fallas registradas y pocos vitales."},
                {
                    "tipo": "figura",
                    "titulo": "Distribución de fallas por sistema en motoniveladoras CAT 24M",
                    "caption": "Figura 1.4 Distribución de fallas por sistema en motoniveladoras CAT 24M",
                },
            ],
        }
    ]

    updated = apply_figure_recommendations(
        sections,
        values={"title": "Plan RCM para flota CAT 24M"},
        format_id="unac-proyecto-cuant",
    )

    figures = [block for block in updated[0]["content"] if block.get("tipo") == "figura"]

    assert len(figures) == 4
    assert all("Distribución de fallas" not in str(figure.get("titulo") or "") for figure in figures)


def test_chapter_two_text_only_sections_drop_existing_figures() -> None:
    sections = [
        {
            "sectionId": "sec-ant",
            "path": "II. MARCO TEORICO/2.1 Antecedentes",
            "content": [
                {"tipo": "parrafo", "texto": "Antecedente internacional con resultados numericos."},
                {"tipo": "figura", "caption": "Arquitectura conceptual aplicada al titulo completo."},
            ],
        }
    ]

    updated = apply_figure_recommendations(
        sections,
        values={"title": "Plan RCM para flota CAT 24M"},
        format_id="unac-proyecto-cuant",
    )

    content = updated[0]["content"]
    assert isinstance(content, list)
    assert [block["tipo"] for block in content] == ["parrafo"]


def test_chapter_two_bases_gets_four_formal_figures_from_canonical_headings() -> None:
    """Bases teóricas con subtítulos 2.2.x detectados dinámicamente reciben una
    figura por cada subtítulo, con el título extraído del heading real.
    No depende de marcadores hardcodeados de mantenimiento.
    """
    sections = [
        {
            "sectionId": "sec-bases",
            "path": "II. MARCO TEORICO/2.2 Bases teoricas",
            "content": (
                "2.2.1 Mantenimiento Centrado en Confiabilidad (RCM)\n\nTexto tecnico del RCM.\n\n"
                "2.2.2 Proceso del RCM\n\nLas siete preguntas ordenan funciones, fallas y tareas.\n\n"
                "2.2.3 Taxonomia de equipos segun ISO 14224\n\nLos niveles taxonomicos ordenan activos.\n\n"
                "2.2.4 Analisis de Modos y Efecto de Fallas (AMEF)\n\nEl NPR prioriza modos de falla.\n\n"
                "2.2.5 Disponibilidad inherente\n\nRelaciona MTBF y MTTR.\n\n"
                "2.2.6 Confiabilidad\n\nDescribe la tasa de falla.\n\n"
                "2.2.7 Mantenibilidad\n\nDescribe el tiempo de reparacion.\n\n"
                "2.2.8 Equipo u objeto de estudio\n\nLa motoniveladora integra sistemas mantenibles."
            ),
        }
    ]

    updated = apply_figure_recommendations(
        sections,
        values={"title": "Plan RCM para flota CAT 24M"},
        format_id="unac-proyecto-cuant",
    )

    content = updated[0]["content"]
    figures = [block for block in content if block.get("tipo") == "figura"]
    figure_positions = [index for index, block in enumerate(content) if block.get("tipo") == "figura"]

    assert len(figures) == 4
    assert [figure["titulo"] for figure in figures] == [
        "Proceso del RCM", "Niveles taxonomicos",
        "Analisis de Modo y Efecto de Falla", "Motoniveladora CAT 24M",
    ]
    assert all(figure["numbered"] is True and figure["diagram_type"] for figure in figures)
    assert all("ruta_placeholder" not in figure and "nota" not in figure for figure in figures)
    assert figure_positions == sorted(figure_positions)


def test_chapter_two_captions_are_brief_and_do_not_repeat_project_title() -> None:
    project_title = (
        "PLAN DE MANTENIMIENTO CENTRADO EN CONFIABILIDAD PARA MEJORAR LA DISPONIBILIDAD "
        "INHERENTE DE LA FLOTA DE MOTONIVELADORAS CAT 24M"
    )
    sections = [
        {
            "sectionId": "sec-bases-short-caption",
            "path": "II. MARCO TEORICO/2.2 Bases teoricas",
            "content": "2.2.2 PROCESO DEL RCM\n\nTexto técnico de mantenimiento, confiabilidad y disponibilidad del proceso RCM.",
        }
    ]

    updated = apply_figure_recommendations(
        sections,
        values={"title": project_title},
        format_id="unac-proyecto-cuant",
    )

    figure = next(block for block in updated[0]["content"] if block.get("tipo") == "figura")
    assert figure["titulo"] == "Proceso del RCM"
    assert project_title not in figure["titulo"]
    assert "aplicado a" not in figure["titulo"].lower()
    assert len(figure["titulo"]) <= 120


def test_chapter_two_bases_keeps_paragraphs_and_passes_validator() -> None:
    service = AIService()
    validator = OutputValidator()
    section = {
        "sectionId": "sec-0010",
        "path": "II. MARCO TEORICO/2.2 Bases teoricas",
        "content": service._fallback_theoretical_bases_content(
            {
                "tema": (
                    "Plan de mantenimiento centrado en confiabilidad para mejorar la disponibilidad "
                    "inherente de la flota de motoniveladoras CAT 24M"
                ),
                "objeto_estudio": "motoniveladora CAT 24M",
                "lugar_ejecucion": "unidad minera de la Sierra Central",
                "variable_independiente": "Plan de mantenimiento centrado en confiabilidad",
                "variable_dependiente": "Disponibilidad inherente",
            }
        ),
    }

    updated = apply_figure_recommendations(
        [section],
        values={
            "tema": (
                "Plan de mantenimiento centrado en confiabilidad para mejorar la disponibilidad "
                "inherente de la flota de motoniveladoras CAT 24M"
            )
        },
        format_id="unac-proyecto-cuant",
    )

    content = updated[0]["content"]
    assert isinstance(content, list)
    assert sum(1 for block in content if block.get("tipo") == "parrafo") >= 16
    # Ahora se generan figuras dinámicamente según los subtítulos 2.2.x detectados.
    # El fallback de mantenimiento genera 8 subtítulos (2.2.1 al 2.2.8).
    figures = [block for block in content if block.get("tipo") == "figura"]
    assert len(figures) >= 4, f"Esperaba al menos 4 figuras dinámicas, se obtuvieron: {len(figures)}"
    assert all(f["numbered"] is True and f["diagram_type"] for f in figures)
    assert all("nota" not in f and "ruta_placeholder" not in f for f in figures)

    validator._validate_theoretical_bases_quality(content, section_id="sec-0010")


def test_chapter_two_bases_injects_dynamic_figures_for_any_domain() -> None:
    """Bases teóricas con subtítulos 2.2.x reciben figuras dinámicas para CUALQUIER
    dominio, no solo mantenimiento. Las figuras usan los títulos reales del heading.
    """
    sections = [
        {
            "sectionId": "sec-bases-soft",
            "path": "II. REVISION DE LITERATURA/2.2 Bases teoricas",
            "content": (
                "2.2.1 Arquitectura de software. El sistema distribuye responsabilidades en capas.\n\n"
                "2.2.2 Modelo cliente servidor. Se describen solicitudes, respuestas y persistencia.\n\n"
                "2.2.3 Seguridad de la informacion. Se explican autenticacion, autorizacion y cifrado.\n\n"
                "2.2.4 Algoritmos de clasificacion. Se comparan criterios de precision y complejidad.\n\n"
                "2.2.5 Experiencia de usuario. Se describen usabilidad y navegacion."
            ),
        }
    ]

    updated = apply_figure_recommendations(
        sections,
        values={
            "title": "Sistema web para gestion academica",
            "variable_independiente": "Arquitectura de software",
            "variable_dependiente": "Usabilidad del sistema",
        },
        format_id="unac-proyecto-cuant",
    )

    content = updated[0]["content"]
    figures = [block for block in content if isinstance(block, dict) and block.get("tipo") == "figura"]

    # Ahora sí genera figuras dinámicas para dominios no-mantenimiento
    assert len(figures) == 5, f"Esperaba 5 figuras (una por 2.2.x), se obtuvieron: {len(figures)}"
    # Los títulos incluyen el texto real del heading detectado
    assert any("Arquitectura de software" in f["titulo"] for f in figures)
    assert any("cliente servidor" in f["titulo"] or "cliente-servidor" in f["titulo"] for f in figures)
    assert any("Seguridad" in f["titulo"] for f in figures)
    assert any("clasificacion" in f["titulo"] or "Algoritmos" in f["titulo"] for f in figures)
    assert any("Experiencia de usuario" in f["titulo"] or "usabilidad" in f["titulo"] for f in figures)
    assert all(f["diagram_type"] == "concept_map" for f in figures)
    assert all("nota" not in f and "ruta_placeholder" not in f for f in figures)


def test_chapter_four_sections_drop_existing_figures_and_tables() -> None:
    sections = [
        {
            "sectionId": "sec-45",
            "path": "IV. METODOLOGIA DEL PROYECTO/4.5 Tecnicas e instrumentos para la recoleccion",
            "content": [
                {"tipo": "parrafo", "texto": "Texto metodologico de tecnicas e instrumentos."},
                {"tipo": "tabla", "titulo": "Tabla 4.2 Tecnicas e instrumentos de recoleccion de datos"},
                {"tipo": "figura", "caption": "Flujo metodologico del estudio sobre el titulo completo."},
            ],
        }
    ]

    updated = apply_figure_recommendations(
        sections,
        values={"title": "Plan RCM para flota CAT 24M"},
        format_id="unac-proyecto-cuant",
    )

    content = updated[0]["content"]
    assert isinstance(content, list)
    assert [block["tipo"] for block in content] == ["parrafo"]


def test_chapter_four_design_keeps_methodological_formula_but_drops_visuals() -> None:
    sections = [
        {
            "sectionId": "sec-41",
            "path": "IV. METODOLOGIA DEL PROYECTO/4.1 Diseno metodologico",
            "content": [
                {"tipo": "parrafo", "texto": "El esquema del diseno se representa de la siguiente manera."},
                {"tipo": "formula", "texto": "M O1 X O2", "alineacion": "center"},
                {"tipo": "figura", "caption": "Figura 4.1 Esquema del diseno preexperimental"},
            ],
        }
    ]

    updated = apply_figure_recommendations(
        sections,
        values={"title": "Plan RCM para flota CAT 24M"},
        format_id="unac-proyecto-cuant",
    )

    content = updated[0]["content"]
    assert isinstance(content, list)
    assert [block["tipo"] for block in content] == ["parrafo", "formula"]


def test_chapter_three_operationalization_drops_visual_and_tabular_blocks() -> None:
    sections = [
        {
            "sectionId": "sec-32",
            "path": "III. HIPOTESIS Y VARIABLES/3.2 Operacionalizacion de variable",
            "content": [
                {"tipo": "parrafo", "texto": "Puente de operacionalizacion para las tablas institucionales."},
                {
                    "tipo": "tabla",
                    "titulo": "Tabla 3.1 Operacionalizacion de la variable independiente",
                    "encabezados": ["A"],
                    "filas": [["1"]],
                },
                {"tipo": "figura", "caption": "Figura no permitida"},
            ],
        }
    ]

    updated = apply_figure_recommendations(
        sections,
        values={"title": "Plan RCM para flota CAT 24M"},
        format_id="unac-proyecto-cuant",
    )

    content = updated[0]["content"]
    assert isinstance(content, list)
    assert [block["tipo"] for block in content] == ["parrafo"]
