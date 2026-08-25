"""Tests for simulated reference consolidation and native citation density."""

from app.core.services.ai.reference_proposals import (
    build_reference_section_content,
    consolidate_references,
    replace_references_section,
)


def test_build_reference_section_content_is_simulated_and_contextual() -> None:
    sections = [
        {
            "sectionId": "sec-0001",
            "path": "II. MARCO TEORICO/2.2 Bases teoricas",
            "content": "Moubray (2020) desarrolla conceptos de mantenimiento predictivo y gestion.",
        },
        {
            "sectionId": "sec-0002",
            "path": "IV. METODOLOGIA/4.1 Diseno metodologico",
            "content": "Hernandez (2021) describe el diseno metodologico y el plan de analisis.",
        },
        {
            "sectionId": "sec-0003",
            "path": "IX. REFERENCIAS BIBLIOGRAFICAS",
            "content": "Contenido viejo",
        },
    ]

    content = build_reference_section_content(
        sections,
        values={"tema": "Mantenimiento predictivo en sistemas industriales"},
    )

    assert "sin acceso a internet" in content
    assert "Fundamentos y evidencia sobre bases teoricas" in content
    assert "Metodos aplicados sobre diseno metodologico" in content
    assert "Mantenimiento predictivo en sistemas industriales" not in content
    assert "http" not in content.lower()
    assert "doi" not in content.lower()
    assert content.count("[[SOURCE:SIM_") == 2


def test_replace_references_section_overrides_final_reference_content() -> None:
    sections = [
        {
            "sectionId": "sec-0001",
            "path": "INTRODUCCION",
            "content": "Moubray (2020) fundamenta el contenido academico de esta introduccion.",
        },
        {
            "sectionId": "sec-0002",
            "path": "IX. REFERENCIAS BIBLIOGRAFICAS",
            "content": "Ejemplo viejo del formato",
        },
    ]

    updated = replace_references_section(sections)

    final_section = next(item for item in updated if "REFERENCIAS" in item["path"].upper())
    assert "sin acceso a internet" in final_section["content"]
    assert "Ejemplo viejo del formato" not in final_section["content"]
    assert "[[SOURCE:SIM_" in final_section["content"]
    assert "[[CITE:SIM_" in updated[0]["content"]


def test_replace_references_adds_citations_to_string_list_content() -> None:
    sections = [
        {
            "sectionId": "sec-0001",
            "path": "II. MARCO TEORICO/2.1 Antecedentes",
            "content": [
                "Smith y Johnson (2020) presentan contenido narrativo suficientemente amplio para insertar una cita nativa."
            ],
        },
        {
            "sectionId": "sec-0002",
            "path": "IX. REFERENCIAS BIBLIOGRAFICAS",
            "content": "Contenido viejo",
        },
    ]

    updated = replace_references_section(sections)

    assert "[[CITE:SIM_" in updated[0]["content"][0]
    assert "[[SOURCE:SIM_" in updated[1]["content"]


def test_title_and_basic_information_never_creates_or_requires_sources() -> None:
    sections = [
        {
            "sectionId": "titulo-info-basica",
            "path": "Título + Información Básica",
            "content": (
                "PLAN DE MANTENIMIENTO CENTRADO EN CONFIABILIDAD PARA MEJORAR "
                "LA DISPONIBILIDAD DE EQUIPOS MINEROS"
            ),
        },
        {
            "sectionId": "sec-0001",
            "path": "INTRODUCCIÓN",
            "content": (
                "Moubray (2020) desarrolla el contexto técnico del mantenimiento "
                "y la disponibilidad de la flota minera analizada."
            ),
        },
        {
            "sectionId": "sec-0027",
            "path": "VII. REFERENCIAS BIBLIOGRÁFICAS",
            "content": "Contenido anterior",
        },
    ]

    updated = replace_references_section(sections)

    special = next(item for item in updated if item["sectionId"] == "titulo-info-basica")
    introduction = next(item for item in updated if item["sectionId"] == "sec-0001")
    references = next(item for item in updated if item["sectionId"] == "sec-0027")
    assert "[[CITE:" not in special["content"]
    assert "[[CITE:SIM_" in introduction["content"]
    assert references["content"].count("[[SOURCE:SIM_") == 1
    assert "informacion basica" not in references["content"].lower()


def test_unac_density_matches_engineer_pattern_when_content_has_no_citations() -> None:
    def paragraphs(count: int) -> str:
        return "\n\n".join(
            f"Parrafo academico {index} con suficiente desarrollo conceptual y evidencia tecnica para distribuir la cita nativa correctamente."
            for index in range(1, count + 1)
        )

    paths_and_paragraphs = [
        ("INTRODUCCIÓN", 3),
        ("I. PLANTEAMIENTO DEL PROBLEMA/1.1 Descripción de la realidad problemática", 5),
        ("II. MARCO TEÓRICO/2.1 Antecedentes", 10),
        ("II. MARCO TEÓRICO/2.2 Bases teóricas", 14),
        ("II. MARCO TEÓRICO/2.3 Marco conceptual", 2),
        ("II. MARCO TEÓRICO/2.4 Definición de términos básicos", 13),
        ("III. HIPÓTESIS Y VARIABLES/3.2 Operacionalización de variable", 2),
        ("IV. METODOLOGÍA DEL PROYECTO/4.1 Diseño metodológico", 2),
        ("IV. METODOLOGÍA DEL PROYECTO/4.2 Método de investigación", 1),
    ]
    sections = [
        {"sectionId": f"sec-{index:02d}", "path": path, "content": paragraphs(count)}
        for index, (path, count) in enumerate(paths_and_paragraphs, start=1)
    ]
    sections.append(
        {
            "sectionId": "sec-refs",
            "path": "VII. REFERENCIAS BIBLIOGRÁFICAS",
            "content": "Contenido anterior",
        }
    )

    updated = replace_references_section(sections)

    expected_mentions = [3, 5, 10, 14, 2, 13, 2, 2, 1]
    for section, expected in zip(updated[:-1], expected_mentions):
        assert section["content"].count("[[CITE:") == expected
    references = updated[-1]["content"]
    assert sum(expected_mentions) == 52
    assert references.count("[[SOURCE:SIM_") == 29
    assert "plan de mantenimiento centrado en confiabilidad para mejorar" not in references.lower()


def test_existing_author_year_citations_become_native_without_duplicate_sources() -> None:
    sections = [
        {
            "sectionId": "intro",
            "path": "INTRODUCCION",
            "content": (
                "Moubray (2020) presenta el enfoque. Luego, el mismo sustento "
                "se confirma en otra evaluacion (Moubray, 2020)."
            ),
        },
        {"sectionId": "refs", "path": "VII. REFERENCIAS BIBLIOGRAFICAS", "content": "Viejo"},
    ]

    updated = replace_references_section(sections)

    assert updated[0]["content"].count("[[CITE:") == 2
    assert "Moubray (2020)" not in updated[0]["content"]
    assert "(Moubray, 2020)" not in updated[0]["content"]
    assert updated[1]["content"].count("[[SOURCE:SIM_") == 1


def test_mil_standard_is_preserved_as_a_technical_author() -> None:
    sections = [
        {
            "sectionId": "theory",
            "path": "II. MARCO TEÓRICO/2.2 Bases teóricas",
            "content": (
                "Según la norma MIL-STD-1629A (1980), el AMEF permite "
                "estructurar los modos, causas y efectos de falla."
            ),
        },
        {
            "sectionId": "refs",
            "path": "VII. REFERENCIAS BIBLIOGRÁFICAS",
            "content": "Anterior",
        },
    ]

    updated = replace_references_section(sections)

    assert "[[CITE:SIM_01_MIL_STD_1629A_1980]]" in updated[0]["content"]
    assert "MIL-STD-1629A (1980)." in updated[1]["content"]
    assert "MIL-STD-1629A, M." not in updated[1]["content"]


def test_saved_legacy_mil_standard_is_visually_normalized_on_render_retry() -> None:
    sections = [
        {
            "sectionId": "theory",
            "path": "II. MARCO TEÓRICO/2.2 Bases teóricas",
            "content": "El AMEF se sustenta en [[CITE:SIM_24_A_1980]].",
        },
        {
            "sectionId": "refs",
            "path": "VII. REFERENCIAS BIBLIOGRÁFICAS",
            "content": (
                "[[SOURCE:SIM_24_A_1980]] MIL-STD-1629A, M. (1980). "
                "Fundamentos y evidencia sobre bases teoricas. Fondo Editorial Tecnico."
            ),
        },
    ]

    updated = replace_references_section(sections)

    assert "[[SOURCE:SIM_24_A_1980]] MIL-STD-1629A (1980)." in updated[1]["content"]
    assert "MIL-STD-1629A, M." not in updated[1]["content"]


def test_unac_semantic_minimums_and_structured_operationalization_are_audited() -> None:
    def paragraph(label: str) -> dict:
        return {
            "tipo": "parrafo",
            "texto": (
                f"{label} desarrolla evidencia técnica suficiente para sustentar la definición, su alcance "
                "operacional y la relación con los indicadores del proyecto de mantenimiento analizado."
            ),
        }

    backgrounds = [paragraph("2.1.1 Antecedentes internacionales")]
    backgrounds.extend(paragraph(f"Antecedente internacional {index}") for index in range(1, 6))
    backgrounds.append(paragraph("2.1.2 Antecedentes nacionales"))
    backgrounds.extend(paragraph(f"Antecedente nacional {index}") for index in range(1, 6))

    theory_specs = (
        ("2.2.1 Mantenimiento Centrado en Confiabilidad (RCM)", 3),
        ("2.2.2 Proceso del RCM", 2),
        ("2.2.3 Taxonomía de equipos según ISO 14224:2016", 2),
        ("2.2.4 Análisis de Modos y Efecto de Fallas (AMEF)", 2),
        ("2.2.5 Disponibilidad inherente", 1),
        ("2.2.6 Confiabilidad", 3),
        ("2.2.7 Mantenibilidad", 2),
        ("2.2.8 Motoniveladora CAT 24M", 1),
    )
    theory: list[dict] = []
    for heading, count in theory_specs:
        theory.append(paragraph(heading))
        theory.extend(paragraph(f"Desarrollo {heading} {index}") for index in range(1, count + 1))

    def plain_paragraphs(count: int) -> str:
        return "\n\n".join(
            f"Párrafo {index} con desarrollo académico suficiente para distribuir una cita nativa pertinente."
            for index in range(1, count + 1)
        )

    sections = [
        {"sectionId": "intro", "path": "INTRODUCCIÓN", "content": plain_paragraphs(3)},
        {
            "sectionId": "problem",
            "path": "I. PLANTEAMIENTO DEL PROBLEMA/1.1 Descripción de la realidad problemática",
            "content": plain_paragraphs(5),
        },
        {"sectionId": "backgrounds", "path": "II. MARCO TEÓRICO/2.1 Antecedentes", "content": backgrounds},
        {"sectionId": "theory", "path": "II. MARCO TEÓRICO/2.2 Bases teóricas", "content": theory},
        {"sectionId": "concepts", "path": "II. MARCO TEÓRICO/2.3 Marco conceptual", "content": plain_paragraphs(2)},
        {"sectionId": "terms", "path": "II. MARCO TEÓRICO/2.4 Definición de términos básicos", "content": plain_paragraphs(13)},
        {"sectionId": "op", "path": "III. HIPÓTESIS Y VARIABLES/3.2 Operacionalización de variable", "content": "Tablas estructuradas."},
        {"sectionId": "design", "path": "IV. METODOLOGÍA DEL PROYECTO/4.1 Diseño metodológico", "content": plain_paragraphs(2)},
        {"sectionId": "method", "path": "IV. METODOLOGÍA DEL PROYECTO/4.2 Método de investigación", "content": plain_paragraphs(1)},
        {"sectionId": "refs", "path": "VII. REFERENCIAS BIBLIOGRÁFICAS", "content": "Anterior"},
    ]
    values = {
        "titulo": "Plan de mantenimiento centrado en confiabilidad para motoniveladoras",
        "operacionalizacion_vi": {
            "definicion_conceptual": "Definición conceptual de la estrategia RCM.",
        },
        "operacionalizacion_vd": {
            "definicion_conceptual": "Definición conceptual de la disponibilidad inherente.",
        },
    }

    result = consolidate_references(sections, values=values)

    assert result.failures == []
    assert result.distinct_sources >= 29
    assert result.mentions_by_section["rcm"] >= 3
    assert result.mentions_by_section["rcm_process"] >= 2
    assert result.mentions_by_section["reliability"] >= 3
    assert result.mentions_by_section["operationalization"] >= 2
    assert "[[CITE:" in result.structured_values["operacionalizacion_vi"]["definicion_conceptual"]
    assert "[[CITE:" in result.structured_values["operacionalizacion_vd"]["definicion_conceptual"]


def test_theory_citations_follow_canonical_numbers_when_titles_are_paraphrased() -> None:
    content: list[dict] = []
    headings = (
        "2.2.1 Mantenimiento Centrado en Confiabilidad (RCM)",
        "2.2.2 Proceso del RCM",
        "2.2.3 Taxonomía de equipos",
        "2.2.4 AMEF",
        "2.2.5 Disponibilidad inherente",
        "2.2.6 Mantenibilidad y su relación con el RCM",
        "2.2.7 Motoniveladoras CAT 24M",
        "2.2.8 Impacto del RCM en la productividad minera",
    )
    for heading in headings:
        content.append({"tipo": "parrafo", "texto": heading})
        content.extend(
            {
                "tipo": "parrafo",
                "texto": f"Desarrollo técnico sustantivo de {heading} con evidencia aplicable al proyecto {index}.",
            }
            for index in range(3)
        )
    sections = [
        {"sectionId": "theory", "path": "II/2.2 Bases teóricas", "content": content},
        {"sectionId": "refs", "path": "VII. REFERENCIAS BIBLIOGRÁFICAS", "content": "Anterior"},
    ]

    result = consolidate_references(sections)

    assert result.mentions_by_section["reliability"] >= 3
    assert result.mentions_by_section["maintainability"] >= 2
    assert result.mentions_by_section["study_equipment"] >= 1


def test_reference_consolidation_is_idempotent_and_keeps_repeated_mentions() -> None:
    sections = [
        {
            "sectionId": "intro",
            "path": "INTRODUCCION",
            "content": (
                "Moubray (2020) sustenta el primer argumento.\n\n"
                "Moubray (2020) sustenta un argumento diferente.\n\n"
                "Moubray (2020) vuelve a emplearse de forma pertinente."
            ),
        },
        {"sectionId": "refs", "path": "VII. REFERENCIAS BIBLIOGRAFICAS", "content": "Anterior"},
    ]

    first = replace_references_section(sections)
    second = replace_references_section(first)

    assert second[0]["content"].count("[[CITE:") == 3
    assert second[1]["content"].count("[[SOURCE:") == 1
