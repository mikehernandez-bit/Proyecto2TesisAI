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
    assert figure["titulo"] == "Visualizacion comparativa de resultados de analisis predictivo de fallas en motores industriales"
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
