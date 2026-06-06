from app.core.services.ai.figure_recommendations import apply_figure_recommendations


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
    assert all(figure["ruta_placeholder"] == "assets/placeholder_figura.png" for figure in figures)
    assert all("placeholder_text" not in figure for figure in figures)
    assert all(figure["fuente"] == "Elaboración propia." for figure in figures)
    assert all(figure["nota"].startswith("Guía para elaborar la figura:") for figure in figures)
    assert all(not figure["nota"].startswith("*") and not figure["nota"].endswith("*") for figure in figures)
    assert all(figure["nota_color"] == "0000FF" for figure in figures)
    assert "eje X los sistemas o modos de falla" in figures[0]["nota"]
    assert "línea horizontal de referencia en 80 %" in figures[0]["nota"]
    assert "el eje Y derecho con porcentaje acumulado" in figures[0]["nota"]
    assert "Baja disponibilidad inherente de la flota CAT 24M" in figures[1]["nota"]
    assert "seis ramas principales" in figures[1]["nota"]
    assert "cabeza del diagrama" in figures[1]["nota"]
    assert "Califica cada alternativa de 1 a 5" in figures[2]["nota"]
    assert "decisión en la columna final" in figures[2]["nota"]
    assert "la suma sea exactamente 100 %" in figures[3]["nota"]
    assert "peso por puntaje" in figures[3]["nota"]


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
    assert all("nota" in content[position] and "fuente" in content[position] for position in figure_positions)
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
    assert figures[0]["nota"].startswith("Guía para elaborar la figura:")
    assert figures[0]["nota_color"] == "0000FF"


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
    assert all(not figure["nota"].startswith("*") for figure in figures)


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


def test_chapter_two_bases_gets_four_controlled_figures() -> None:
    sections = [
        {
            "sectionId": "sec-bases",
            "path": "II. MARCO TEORICO/2.2 Bases teoricas",
            "content": (
                "Mantenimiento Centrado en Confiabilidad (RCM). Texto tecnico del RCM.\n\n"
                "Proceso del RCM. Las siete preguntas ordenan funciones, fallas y tareas.\n\n"
                "Taxonomia de equipos segun ISO 14224:2016. Los niveles taxonomicos ordenan activos.\n\n"
                "Analisis de Modos y Efecto de Fallas (AMEF). El NPR prioriza los modos de falla.\n\n"
                "Disponibilidad inherente. Se calcula sin demoras administrativas.\n\n"
                "Confiabilidad. El MTBF resume la frecuencia de interrupciones.\n\n"
                "Mantenibilidad. El MTTR resume el tiempo de reparacion.\n\n"
                "Motoniveladora CAT 24M. El equipo mantiene caminos de acarreo en mineria."
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

    assert [figure["caption"] for figure in figures] == [
        "Figura 2.1 Proceso del RCM",
        "Figura 2.2 Niveles taxonomicos",
        "Figura 2.3 Analisis de Modo y Efecto de Falla",
        "Figura 2.4 Motoniveladora CAT 24M",
    ]
    assert all(figure["ruta_placeholder"] == "assets/placeholder_figura.png" for figure in figures)
    assert "Placeholder tecnico" not in " ".join(str(figure) for figure in figures)
    assert figure_positions[0] < figure_positions[1] < figure_positions[2] < figure_positions[3]


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
