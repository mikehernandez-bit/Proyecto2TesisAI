from app.core.services.institutional_section_service import InstitutionalSectionService
from app.core.services.project_generation_planner import ProjectGenerationPlanner


def test_plan_sections_filters_by_selection_and_merges_block_context():
    definition = {
        "preliminares": {
            "introduccion": {"titulo": "INTRODUCCION"},
            "resumen": {"titulo": "RESUMEN"},
        },
        "cuerpo": [
            {
                "titulo": "I. PLANTEAMIENTO DEL PROBLEMA",
                "contenido": [
                    {"texto": "1.1 Realidad problematica"},
                ],
            }
        ],
    }

    section_service = InstitutionalSectionService()
    extracted = section_service.extract_sections(definition)
    by_path = {item["section_path"]: item for item in extracted}

    prompt_package = {
        "sections": [
            {
                **by_path["INTRODUCCION"],
                "blocks": [
                    {
                        "block_id": "intro-1",
                        "header": "Contexto introductorio",
                        "label": "Prompt introduccion",
                        "instructions": "Enfoca la introduccion en el problema institucional.",
                        "required_variables": ["variable_contextual"],
                        "required": True,
                    }
                ],
            },
            {
                **by_path["I. PLANTEAMIENTO DEL PROBLEMA/1.1 Realidad problematica"],
                "blocks": [
                    {
                        "block_id": "planteamiento-1",
                        "header": "Realidad problematica",
                        "label": "Prompt realidad problematica",
                        "instructions": "Sustenta con evidencia tecnica y variable dependiente.",
                        "required_variables": ["variable_dependiente"],
                        "required": True,
                    }
                ],
            },
        ]
    }

    planner = ProjectGenerationPlanner(section_service=section_service)
    planned = planner.plan_sections(
        definition=definition,
        prompt_package=prompt_package,
        selected_sections=[
            {"section_path": "INTRODUCCION"},
            {"section_path": "I. PLANTEAMIENTO DEL PROBLEMA/1.1 Realidad problematica"},
        ],
    )

    paths = [item["path"] for item in planned]
    assert paths == [
        "INTRODUCCION",
        "I. PLANTEAMIENTO DEL PROBLEMA/1.1 Realidad problematica",
    ]
    assert "RESUMEN" not in paths
    assert planned[0]["required_variables"] == ["variable_contextual"]
    assert planned[1]["required_variables"] == ["variable_dependiente"]
    assert planned[0]["blocks"][0]["header"] == "Contexto introductorio"
    assert planned[0]["blocks"][0]["cabecera"] == "Contexto introductorio"
    assert planned[0]["section_order"] < planned[1]["section_order"]
    assert "Capitulo padre: INTRODUCCION" in planned[0]["additional_context"]
    assert "Seccion actual: INTRODUCCION" in planned[0]["additional_context"]
    assert "Path completo: INTRODUCCION" in planned[0]["additional_context"]
    assert "Cabecera: Contexto introductorio" in planned[0]["additional_context"]
    assert "Etiqueta: Prompt introduccion" in planned[0]["additional_context"]
    assert "Capitulo padre: I. PLANTEAMIENTO DEL PROBLEMA" in planned[1]["additional_context"]
    assert "Seccion actual: 1.1 Realidad problematica" in planned[1]["additional_context"]
    assert "Path completo: I. PLANTEAMIENTO DEL PROBLEMA/1.1 Realidad problematica" in planned[1]["additional_context"]
    assert "Nivel jerarquico: 2" in planned[1]["additional_context"]
    assert "Orden institucional:" in planned[1]["additional_context"]
    assert "evidencia tecnica" in planned[1]["additional_context"]
    assert "Cabecera: Realidad problematica" in planned[1]["additional_context"]


def test_plan_sections_adds_text_only_guidance_for_diagram_blocks():
    definition = {
        "cuerpo": [
            {
                "titulo": "I. PLANTEAMIENTO DEL PROBLEMA",
                "contenido": [
                    {"texto": "1.1 Realidad problematica"},
                ],
            }
        ],
    }

    section_service = InstitutionalSectionService()
    extracted = section_service.extract_sections(definition)
    by_path = {item["section_path"]: item for item in extracted}

    prompt_package = {
        "sections": [
            {
                **by_path["I. PLANTEAMIENTO DEL PROBLEMA/1.1 Realidad problematica"],
                "blocks": [
                    {
                        "block_id": "diag-1",
                        "header": "Diagrama de Ishikawa",
                        "label": "Prompt Ishikawa",
                        "instructions": "Organiza el analisis causal del problema.",
                        "required_variables": ["problema_central"],
                        "required": True,
                    }
                ],
            }
        ]
    }

    planner = ProjectGenerationPlanner(section_service=section_service)
    planned = planner.plan_sections(
        definition=definition,
        prompt_package=prompt_package,
        selected_sections=[
            {"section_path": "I. PLANTEAMIENTO DEL PROBLEMA/1.1 Realidad problematica"},
        ],
    )

    assert len(planned) == 1
    assert planned[0]["blocks"][0]["header"] == "Diagrama de Ishikawa"
    assert "no generes imagen ni FIGURE_JSON" in planned[0]["additional_context"]
    assert "problema central, categorias, subcausas" in planned[0]["additional_context"]


def test_plan_sections_expands_selected_parent_recursively_without_generating_grouping_parent():
    definition = {
        "cuerpo": [
            {
                "titulo": "I. PLANTEAMIENTO DEL PROBLEMA",
                "contenido": [
                    {"texto": "1.1 Realidad problematica"},
                    {"texto": "1.2 Formulacion del problema"},
                ],
            }
        ],
    }

    section_service = InstitutionalSectionService()
    extracted = section_service.extract_sections(definition)
    by_path = {item["section_path"]: item for item in extracted}

    prompt_package = {
        "sections": [
            {
                **by_path["I. PLANTEAMIENTO DEL PROBLEMA/1.1 Realidad problematica"],
                "blocks": [
                    {
                        "block_id": "planteamiento-1",
                        "header": "Realidad problematica",
                        "label": "Prompt realidad problematica",
                        "instructions": "Describe el problema real con evidencia.",
                        "required_variables": ["variable_dependiente"],
                        "required": True,
                    }
                ],
            },
            {
                **by_path["I. PLANTEAMIENTO DEL PROBLEMA/1.2 Formulacion del problema"],
                "blocks": [
                    {
                        "block_id": "planteamiento-2",
                        "header": "Formulacion del problema",
                        "label": "Prompt formulacion",
                        "instructions": "Redacta la pregunta central.",
                        "required_variables": ["pregunta_principal"],
                        "required": True,
                    }
                ],
            },
        ]
    }

    planner = ProjectGenerationPlanner(section_service=section_service)
    planned = planner.plan_sections(
        definition=definition,
        prompt_package=prompt_package,
        selected_sections=[{"section_path": "I. PLANTEAMIENTO DEL PROBLEMA"}],
    )

    assert [item["path"] for item in planned] == [
        "I. PLANTEAMIENTO DEL PROBLEMA/1.1 Realidad problematica",
        "I. PLANTEAMIENTO DEL PROBLEMA/1.2 Formulacion del problema",
    ]


def test_plan_sections_keeps_parent_when_selected_parent_has_own_blocks():
    definition = {
        "cuerpo": [
            {
                "titulo": "I. PLANTEAMIENTO DEL PROBLEMA",
                "contenido": [
                    {"texto": "1.1 Realidad problematica"},
                ],
            }
        ],
    }

    section_service = InstitutionalSectionService()
    extracted = section_service.extract_sections(definition)
    by_path = {item["section_path"]: item for item in extracted}

    prompt_package = {
        "sections": [
            {
                **by_path["I. PLANTEAMIENTO DEL PROBLEMA"],
                "blocks": [
                    {
                        "block_id": "chapter-1",
                        "header": "Marco del capitulo",
                        "label": "Prompt del capitulo",
                        "instructions": "Presenta el alcance general del capitulo.",
                        "required_variables": ["tema"],
                        "required": True,
                    }
                ],
            },
            {
                **by_path["I. PLANTEAMIENTO DEL PROBLEMA/1.1 Realidad problematica"],
                "blocks": [
                    {
                        "block_id": "child-1",
                        "header": "Realidad problematica",
                        "label": "Prompt del hijo",
                        "instructions": "Detalla la realidad problematica.",
                        "required_variables": ["variable_dependiente"],
                        "required": True,
                    }
                ],
            },
        ]
    }

    planner = ProjectGenerationPlanner(section_service=section_service)
    planned = planner.plan_sections(
        definition=definition,
        prompt_package=prompt_package,
        selected_sections=[{"section_path": "I. PLANTEAMIENTO DEL PROBLEMA"}],
    )

    assert [item["path"] for item in planned] == [
        "I. PLANTEAMIENTO DEL PROBLEMA",
        "I. PLANTEAMIENTO DEL PROBLEMA/1.1 Realidad problematica",
    ]


def test_plan_sections_appends_custom_sections_from_prompt_snapshot_in_tree_order():
    definition = {
        "cuerpo": [
            {
                "titulo": "I. PLANTEAMIENTO DEL PROBLEMA",
                "contenido": [
                    {"texto": "1.1 Realidad problematica"},
                ],
            },
            {
                "titulo": "II. MARCO TEORICO",
                "contenido": [
                    {"texto": "2.1 Antecedentes"},
                ],
            },
        ],
    }

    section_service = InstitutionalSectionService()
    extracted = section_service.extract_sections(definition)
    by_path = {item["section_path"]: item for item in extracted}

    prompt_package = {
        "sections": [
            {
                **by_path["I. PLANTEAMIENTO DEL PROBLEMA/1.1 Realidad problematica"],
                "blocks": [
                    {
                        "block_id": "child-1",
                        "header": "Realidad problematica",
                        "label": "Prompt del hijo",
                        "instructions": "Detalla la realidad problematica.",
                        "required_variables": ["variable_dependiente"],
                        "required": True,
                    }
                ],
            },
            {
                "section_id": "custom_section_capitulo",
                "section_path": "CAPITULO ESPECIAL",
                "section_title": "CAPITULO ESPECIAL",
                "parent_section_path": "",
                "section_level": 1,
                "section_order": 99,
                "optional": False,
                "default_selected": True,
                "source_hints": "",
                "blocks": [],
            },
            {
                "section_id": "custom_section_sub",
                "section_path": "CAPITULO ESPECIAL/3.1 Aplicacion piloto",
                "section_title": "3.1 Aplicacion piloto",
                "parent_section_path": "CAPITULO ESPECIAL",
                "section_level": 2,
                "section_order": 100,
                "optional": False,
                "default_selected": True,
                "source_hints": "",
                "blocks": [
                    {
                        "block_id": "custom_block_1",
                        "header": "Aplicacion piloto",
                        "label": "Prompt aplicacion piloto",
                        "instructions": "Describe el piloto personalizado.",
                        "required_variables": ["alcance_piloto"],
                        "required": True,
                    }
                ],
            },
        ]
    }

    planner = ProjectGenerationPlanner(section_service=section_service)
    planned = planner.plan_sections(
        definition=definition,
        prompt_package=prompt_package,
        selected_sections=[
            {"section_path": "I. PLANTEAMIENTO DEL PROBLEMA/1.1 Realidad problematica"},
            {"section_path": "CAPITULO ESPECIAL"},
        ],
    )

    assert [item["path"] for item in planned] == [
        "I. PLANTEAMIENTO DEL PROBLEMA/1.1 Realidad problematica",
        "CAPITULO ESPECIAL/3.1 Aplicacion piloto",
    ]
    assert planned[1]["required_variables"] == ["alcance_piloto"]
    assert "Capitulo padre: CAPITULO ESPECIAL" in planned[1]["additional_context"]
    assert "Cabecera: Aplicacion piloto" in planned[1]["additional_context"]
