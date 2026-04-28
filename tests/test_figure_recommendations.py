from app.core.services.ai.figure_recommendations import apply_figure_recommendations


def test_adds_recommended_figure_to_methodology_text_section() -> None:
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
    assert isinstance(content, list)
    assert content[-1]["tipo"] == "figura"
    assert content[-1]["titulo"] == (
        "Flujo metodologico del estudio sobre mantenimiento predictivo en motores de combustion interna"
    )
    assert content[-1]["ruta_placeholder"] == "assets/placeholder_figura.png"


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
    assert all(figure["placeholder_text"] == "Figura pendiente de elaboración propia" for figure in figures)
    assert all(figure["fuente"] == "Elaboración propia." for figure in figures)
    assert "el eje Y derecho con porcentaje acumulado" in figures[0]["nota"]
    assert "la cabeza del pez" in figures[1]["nota"]
    assert "decision en una columna final" in figures[2]["nota"]
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


def test_project_reality_problem_interleaves_figures_after_references() -> None:
    sections = [
        {
            "sectionId": "sec-problem",
            "path": "I. PLANTEAMIENTO DEL PROBLEMA/1.1 Descripcion de la realidad problematica",
            "content": (
                "El diagnostico inicial requiere ordenar los modos de falla por Pareto. "
                "La Figura 1.1 muestra el punto donde debe colocarse el diagrama. "
                "El analisis causa-efecto se organiza con Ishikawa y ramas 6M. "
                "La Figura 1.2 muestra el punto donde debe colocarse el diagrama. "
                "La matriz de relevancia compara alternativas de solucion por viabilidad tecnica. "
                "La Figura 1.3 muestra el punto donde debe colocarse la matriz. "
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
    assert figure_positions[-1] < len(content) - 1
    assert all(content[figure_positions[index] + 1]["tipo"] == "parrafo" for index in range(len(figure_positions) - 1))
