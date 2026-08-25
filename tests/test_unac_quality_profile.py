from __future__ import annotations

from app.core.services.ai.unac_quality_profile import (
    audit_unac_maintenance_sections,
    canonical_formula_for_key,
    canonicalize_duplicate_semantic_units,
    ensure_canonical_formulas,
    extract_semantic_unit_content,
    is_unac_maintenance_project,
    load_unac_maintenance_profile,
    minimum_for_section_path,
    replace_semantic_unit_content,
    requirements_for_section_path,
)


def test_profile_is_versioned_from_engineer_deliverable() -> None:
    profile = load_unac_maintenance_profile()
    assert profile.id == "UNAC_MAINTENANCE_V1"
    assert profile.source_sha256 == "4712AD32B8B84C352995A1326A67BFE2385C15999890891D76B1AAD68377A92F"
    floors = {item.key: item.min_words for item in profile.requirements}
    assert floors["introduccion"] == 643
    assert floors["1.1"] == 1276
    assert floors["2.1.1"] == 1611
    assert floors["2.1.2"] == 1634
    assert floors["2.2.8"] == 287


def test_aggregate_floor_uses_all_reference_subsections() -> None:
    assert minimum_for_section_path("II. MARCO TEÓRICO/2.1 Antecedentes") == 3245
    assert minimum_for_section_path("II. MARCO TEÓRICO/2.2 Bases teóricas") == 1839
    assert minimum_for_section_path("I. PLANTEAMIENTO/1.4 Justificación") == 864


def test_profile_applies_only_to_unac_maintenance_domain() -> None:
    values = {
        "title": "Plan de mantenimiento centrado en confiabilidad",
        "variable_dependiente": "Disponibilidad inherente",
    }
    assert is_unac_maintenance_project("unac-proyecto-cuant", values)
    assert not is_unac_maintenance_project("uni-proyecto", values)
    assert not is_unac_maintenance_project("unac-proyecto-cuant", {"title": "Comprensión lectora"})


def test_narrative_audit_excludes_caption_table_formula_and_citation_markers() -> None:
    core = "contexto problema propuesta metodo organizacion "
    unique = " ".join(f"contenido{i}" for i in range(638))
    sections = [
        {
            "sectionId": "intro",
            "path": "INTRODUCCIÓN",
            "content": [
                {
                    "tipo": "parrafo",
                    "texto": core + unique + " [[CITE:S1]] [[CITE:S2;S3]]",
                },
                {"tipo": "figura", "caption": "Figura con cien palabras que no cuentan"},
                {"tipo": "tabla", "filas": [["texto auxiliar que no cuenta"]]},
                {"tipo": "formula", "latex": r"x=\frac{a}{b}", "texto": "x=a/b"},
            ],
        }
    ]

    audit = audit_unac_maintenance_sections(sections)
    assert len(audit) == 1
    assert audit[0].key == "introduccion"
    assert audit[0].words == 643
    assert audit[0].citations == 3
    assert audit[0].formulas == 1
    assert audit[0].status == "ok"


def test_short_section_reports_exact_deficit() -> None:
    audits = audit_unac_maintenance_sections(
        [{"sectionId": "objectives", "path": "I/1.3 Objetivos", "content": "Determinar la mejora."}]
    )
    assert len(audits) == 1
    assert audits[0].words == 3
    assert audits[0].minimum == 86
    assert audits[0].difference == -83
    assert audits[0].status == "error"


def test_semantic_topic_aliases_do_not_require_literal_manifest_words() -> None:
    narrative = (
        "La unidad minera está ubicada en la Sierra Central y desarrolla su operación bajo un entorno "
        "geográfico de elevada exigencia. "
        + " ".join(f"detalle_operativo_{index}" for index in range(115))
    )
    audit = audit_unac_maintenance_sections(
        [{"sectionId": "place", "path": "IV/4.4 Lugar de estudio", "content": narrative}]
    )[0]
    assert audit.words >= audit.minimum
    assert audit.missing_topics == ()
    assert audit.status == "ok"


def test_normative_justification_accepts_standards_as_semantic_evidence() -> None:
    narrative = (
        "El mantenimiento asegurará el cumplimiento de las obligaciones legales mediante SAE JA1011, ISO 14224 y el "
        "Decreto Supremo 024-2016-EM. "
        + " ".join(f"trazabilidad_{index}" for index in range(170))
    )
    audit = audit_unac_maintenance_sections(
        [{"sectionId": "normative", "path": "I/1.4.1 Justificación normativa", "content": narrative}]
    )[0]

    assert audit.words >= audit.minimum
    assert "normativa" not in audit.missing_topics
    assert audit.status == "ok"


def test_terms_glossary_recognizes_bold_term_period_definition_entries() -> None:
    entries = []
    for index in range(13):
        definition = " ".join(f"explicacion_{index}_{word}" for word in range(34))
        entries.append(f"**Termino tecnico {index}.** {definition} [[CITE:S{index}]]")
    audit = audit_unac_maintenance_sections(
        [{"sectionId": "terms", "path": "II/2.4 Definición de términos básicos", "content": "\n\n".join(entries)}]
    )[0]

    assert audit.words >= audit.minimum
    assert audit.citations == 13
    assert audit.missing_topics == ()
    assert audit.status == "ok"


def test_population_accepts_equivalent_equipment_unit_of_analysis() -> None:
    narrative = (
        "La población está conformada por cinco motoniveladoras CAT 24M de la flota de equipos. "
        "La muestra censal coincide con toda la población, n = 5, e incluye cada equipo evaluado. "
        + " ".join(f"criterio_{index}" for index in range(35))
    )
    audit = audit_unac_maintenance_sections(
        [{"sectionId": "population", "path": "IV/4.3 Población y muestra", "content": narrative}]
    )[0]

    assert audit.words >= audit.minimum
    assert audit.missing_topics == ()
    assert audit.status == "ok"


def test_antecedent_accepts_aporta_as_contribution_signal() -> None:
    narrative = (
        "problema objetivo metodo muestra resultados conclusion este estudio aporta al proyecto "
        + " ".join(f"evidencia_internacional_{index}" for index in range(1620))
    )
    audit = audit_unac_maintenance_sections(
        [{"sectionId": "international", "path": "II/2.1.1 Antecedentes internacionales", "content": narrative}]
    )[0]

    assert "aporte" not in audit.missing_topics


def test_conceptual_framework_accepts_dimension_labels() -> None:
    narrative = (
        "Variable independiente mantenimiento centrado en confiabilidad. "
        "Dimensión análisis de criticidad. Dimensión AMEF. "
        "Variable dependiente disponibilidad inherente. Dimensión confiabilidad y dimensión mantenibilidad. "
        "La relación entre ambas variables explica el efecto técnico. "
        + " ".join(f"desarrollo_conceptual_{index}" for index in range(590))
    )
    audit = audit_unac_maintenance_sections(
        [{"sectionId": "concepts", "path": "II/2.3 Marco conceptual", "content": narrative}]
    )[0]

    assert audit.missing_topics == ()


def test_replacing_one_semantic_unit_preserves_its_sibling() -> None:
    requirement = next(item for item in requirements_for_section_path("I/1.4 Justificación") if item.key == "1.4.2")
    original = (
        "1.4 Justificación\n\n"
        "1.4.1 Justificación normativa\n\nTexto normativo que debe conservarse.\n\n"
        "1.4.2 Justificación teórica\n\nTexto teórico corto.\n\n"
        "1.4.3 Justificación práctica\n\nTexto práctico que tampoco debe cambiar."
    )
    updated = replace_semantic_unit_content(
        original,
        requirement=requirement,
        replacement="1.4.2 Justificación teórica\n\nNuevo aporte teórico sobre confiabilidad.",
    )
    rendered = "\n".join(str(block.get("texto") or "") for block in updated)
    assert "Texto normativo que debe conservarse" in rendered
    assert "Nuevo aporte teórico sobre confiabilidad" in rendered
    assert "Texto teórico corto" not in rendered
    assert "Texto práctico que tampoco debe cambiar" in rendered


def test_duplicate_composite_units_are_collapsed_without_losing_required_words() -> None:
    topics = "problema objetivo metodo muestra resultados conclusion aporta "
    content = [
        {"tipo": "parrafo", "texto": "2.1.1 Antecedentes internacionales"},
        {"tipo": "parrafo", "texto": topics + " ".join(f"internacional_a_{i}" for i in range(900))},
        {"tipo": "parrafo", "texto": "2.1.2 Antecedentes nacionales"},
        {"tipo": "parrafo", "texto": topics + " ".join(f"nacional_a_{i}" for i in range(1700))},
        {"tipo": "parrafo", "texto": "2.1.1 Antecedentes internacionales"},
        {"tipo": "parrafo", "texto": topics + " ".join(f"internacional_b_{i}" for i in range(800))},
        {"tipo": "parrafo", "texto": "2.1.2 Antecedentes nacionales"},
        {"tipo": "parrafo", "texto": topics + " ".join(f"nacional_b_{i}" for i in range(1700))},
    ]
    sections = [{"sectionId": "antecedents", "path": "II/2.1 Antecedentes", "content": content}]

    canonicalize_duplicate_semantic_units(sections)

    rendered = [str(block.get("texto") or "") for block in sections[0]["content"]]
    assert sum(text.startswith("2.1.1 ") for text in rendered) == 1
    assert sum(text.startswith("2.1.2 ") for text in rendered) == 1
    audits = {item.key: item for item in audit_unac_maintenance_sections(sections)}
    assert audits["2.1.1"].words >= audits["2.1.1"].minimum
    assert audits["2.1.2"].words >= audits["2.1.2"].minimum
    assert audits["2.1.1"].duplicate_ratio <= 0.22
    assert audits["2.1.2"].duplicate_ratio <= 0.22


def test_profile_headings_are_canonicalized_even_without_duplicates() -> None:
    sections = [
        {
            "sectionId": "theory",
            "path": "II/2.2 Bases teóricas",
            "content": [
                {"tipo": "parrafo", "texto": "2.2.6 Mantenibilidad y su relación con el RCM"},
                {"tipo": "parrafo", "texto": "Desarrollo sobre confiabilidad y tasa de falla."},
                {"tipo": "parrafo", "texto": "2.2.7 Motoniveladoras CAT 24M"},
                {"tipo": "parrafo", "texto": "Desarrollo sobre mantenibilidad y MTTR."},
                {"tipo": "parrafo", "texto": "2.2.8 Impacto del RCM en la productividad minera"},
                {"tipo": "parrafo", "texto": "Descripción del equipo objeto de estudio."},
            ],
        }
    ]

    canonicalize_duplicate_semantic_units(sections)

    headings = [str(block.get("texto") or "") for block in sections[0]["content"]]
    assert "2.2.6 Confiabilidad" in headings
    assert "2.2.7 Mantenibilidad" in headings
    assert "2.2.8 Equipo u objeto de estudio" in headings


def test_canonical_formulas_are_inserted_once_in_the_correct_units() -> None:
    content = (
        "2.2 Bases teóricas\n\n"
        "2.2.5 Disponibilidad inherente\n\nDefinición e interpretación con MTBF y MTTR.\n\n"
        "2.2.6 Confiabilidad\n\nDefinición de confiabilidad, tasa de falla, tiempo e interpretación.\n\n"
        "2.2.7 Mantenibilidad\n\nDefinición de mantenibilidad, reparación, MTTR e interpretación.\n\n"
        "2.2.8 Equipo u objeto de estudio\n\nDescripción del equipo."
    )
    sections = [{"sectionId": "theory", "path": "II/2.2 Bases teóricas", "content": content}]
    ensure_canonical_formulas(sections)
    ensure_canonical_formulas(sections)

    formulas = [block for block in sections[0]["content"] if block.get("tipo") == "formula"]
    assert [formula["id"] for formula in formulas] == [
        "disponibilidad-inherente-ai",
        "confiabilidad-rt",
        "mantenibilidad-mt",
    ]
    assert len(extract_semantic_unit_content(sections[0]["content"], "2.2.6")) >= 3


def test_existing_formula_is_replaced_by_the_canonical_equation() -> None:
    sections = [
        {
            "sectionId": "theory",
            "path": "II/2.2 Bases teóricas",
            "content": [
                {"tipo": "parrafo", "texto": "2.2.5 Disponibilidad inherente"},
                {"tipo": "parrafo", "texto": "Definición previa suficiente."},
                {
                    "tipo": "formula",
                    "latex": r"A = \frac{MTBF}{MTBF + MTTR}",
                    "texto": "A = MTBF / (MTBF + MTTR)",
                    "numero": "(99)",
                    "id": "formula-incorrecta",
                },
                {"tipo": "parrafo", "texto": "2.2.6 Confiabilidad"},
                {"tipo": "parrafo", "texto": "Desarrollo."},
                {"tipo": "parrafo", "texto": "2.2.7 Mantenibilidad"},
                {"tipo": "parrafo", "texto": "Desarrollo."},
                {"tipo": "parrafo", "texto": "2.2.8 Equipo u objeto de estudio"},
            ],
        }
    ]

    ensure_canonical_formulas(sections)

    availability = extract_semantic_unit_content(sections[0]["content"], "2.2.5")
    formulas = [block for block in availability if block.get("tipo") == "formula"]
    assert formulas == [canonical_formula_for_key("2.2.5")]
