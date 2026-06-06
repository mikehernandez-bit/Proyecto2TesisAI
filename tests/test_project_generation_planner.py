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


def test_plan_sections_adds_text_only_guidance_for_relevance_matrix_blocks():
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
                        "block_id": "diag-2",
                        "header": "Matriz de relevancia",
                        "label": "Prompt matriz de relevancia",
                        "instructions": "Evalua alternativas de solucion y su viabilidad.",
                        "required_variables": ["alternativas_solucion"],
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
    assert "no generes imagen ni FIGURE_JSON" in planned[0]["additional_context"]
    assert "alternativas descartadas o preseleccionadas" in planned[0]["additional_context"]


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


def test_plan_sections_skips_misplaced_chapter_two_matrix_children():
    definition = {
        "cuerpo": [
            {
                "titulo": "II. MARCO TEORICO",
                "contenido": [
                    {"texto": "2.1 Antecedentes"},
                    {
                        "titulo": "2.2 Bases teoricas",
                        "contenido": [
                            {"texto": "Matriz de Consistencia de Implementacion"},
                            {"texto": "Matriz de Operacionalizacion de Diseno"},
                        ],
                    },
                ],
            }
        ],
    }

    section_service = InstitutionalSectionService()
    prompt_package = {
        "format_id": "unac-proyecto-cuant",
        "sections": [
            {
                "section_id": "bad-1",
                "section_path": (
                    "II. MARCO TEORICO/2.2 Bases teoricas/Matriz de Consistencia de Implementacion"
                ),
                "section_title": "Matriz de Consistencia de Implementacion",
                "parent_section_path": "II. MARCO TEORICO/2.2 Bases teoricas",
                "section_level": 3,
                "default_selected": True,
                "blocks": [{"header": "Matriz", "instructions": "No debe generarse."}],
            }
        ],
    }

    planner = ProjectGenerationPlanner(section_service=section_service)
    planned = planner.plan_sections(
        definition=definition,
        prompt_package=prompt_package,
        selected_sections=[{"section_path": "II. MARCO TEORICO"}],
    )

    paths = [item["path"] for item in planned]
    assert "II. MARCO TEORICO/2.1 Antecedentes" in paths
    assert "II. MARCO TEORICO/2.2 Bases teoricas" in paths
    assert all("Matriz de Consistencia" not in path for path in paths)
    assert all("Matriz de Operacionalizacion" not in path for path in paths)


def test_plan_sections_skips_static_table_sections_from_prompt_package():
    section_service = InstitutionalSectionService()
    prompt_package = {
        "format_id": "unac-proyecto-cuant",
        "sections": [
            {
                "section_id": "matrix-1",
                "section_path": "II. MARCO TEORICO/2.2 Bases teoricas/Matriz de Consistencia de Implementacion",
                "section_title": "Matriz de Consistencia de Implementacion",
                "parent_section_path": "II. MARCO TEORICO/2.2 Bases teoricas",
                "section_level": 3,
                "default_selected": True,
                "blocks": [{"header": "Matriz", "instructions": "No debe generarse."}],
            },
            {
                "section_id": "matrix-2",
                "section_path": "II. MARCO TEORICO/2.2 Bases teoricas/Matriz de Operacionalizacion de Diseno",
                "section_title": "Matriz de Operacionalizacion de Diseno",
                "parent_section_path": "II. MARCO TEORICO/2.2 Bases teoricas",
                "section_level": 3,
                "default_selected": True,
                "blocks": [{"header": "Matriz", "instructions": "No debe generarse."}],
            },
            {
                "section_id": "cron-resumen",
                "section_path": "IV. METODOLOGIA DEL PROYECTO/Cronograma Resumido de Actividades",
                "section_title": "Cronograma Resumido de Actividades",
                "parent_section_path": "IV. METODOLOGIA DEL PROYECTO",
                "section_level": 2,
                "default_selected": True,
                "blocks": [{"header": "Cronograma", "instructions": "No debe generarse."}],
            },
            {
                "section_id": "cron-ejecucion",
                "section_path": "V. CRONOGRAMA DE ACTIVIDADES/Cronograma de ejecucion",
                "section_title": "Cronograma de ejecucion",
                "parent_section_path": "V. CRONOGRAMA DE ACTIVIDADES",
                "section_level": 2,
                "default_selected": True,
                "blocks": [{"header": "Cronograma", "instructions": "Debe generarse."}],
            },
        ],
    }

    planner = ProjectGenerationPlanner(section_service=section_service)
    planned = planner.plan_sections(
        definition={},
        prompt_package=prompt_package,
        selected_sections=None,
    )

    paths = [item["path"] for item in planned]
    assert "V. CRONOGRAMA DE ACTIVIDADES" in paths
    assert all(not path.startswith("V. CRONOGRAMA DE ACTIVIDADES/") for path in paths)
    assert all("Cronograma Resumido de Actividades" not in path for path in paths)
    assert all("Matriz de Consistencia de Implementacion" not in path for path in paths)
    assert all("Matriz de Operacionalizacion de Diseno" not in path for path in paths)


def test_plan_sections_skips_accented_static_tables_from_prompt_package():
    section_service = InstitutionalSectionService()
    prompt_package = {
        "format_id": "unac-proyecto-cuant",
        "sections": [
            {
                "section_id": "matrix-accent-1",
                "section_path": "II. MARCO TEÓRICO/2.2 Bases teóricas/Matriz de Consistencia de Implementación",
                "section_title": "Matriz de Consistencia de Implementación",
                "parent_section_path": "II. MARCO TEÓRICO/2.2 Bases teóricas",
                "section_level": 3,
                "default_selected": True,
                "blocks": [{"header": "Matriz", "instructions": "No debe generarse."}],
            },
            {
                "section_id": "matrix-accent-2",
                "section_path": "II. MARCO TEÓRICO/2.2 Bases teóricas/Matriz de Operacionalización de Diseño",
                "section_title": "Matriz de Operacionalización de Diseño",
                "parent_section_path": "II. MARCO TEÓRICO/2.2 Bases teóricas",
                "section_level": 3,
                "default_selected": True,
                "blocks": [{"header": "Matriz", "instructions": "No debe generarse."}],
            },
            {
                "section_id": "ok-1",
                "section_path": "III. HIPÓTESIS Y VARIABLES/3.2 Operacionalización de variable",
                "section_title": "3.2 Operacionalización de variable",
                "parent_section_path": "III. HIPÓTESIS Y VARIABLES",
                "section_level": 2,
                "default_selected": True,
                "blocks": [{"header": "Operacionalización", "instructions": "Debe generarse."}],
            },
        ],
    }

    planner = ProjectGenerationPlanner(section_service=section_service)
    planned = planner.plan_sections(
        definition={},
        prompt_package=prompt_package,
        selected_sections=None,
    )

    paths = [item["path"] for item in planned]
    assert "III. HIPÓTESIS Y VARIABLES/3.2 Operacionalización de variable" in paths
    assert all("Matriz de Consistencia de Implementación" not in path for path in paths)
    assert all("Matriz de Operacionalización de Diseño" not in path for path in paths)


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


def test_plan_sections_skips_parent_blocks_for_unac_project_details_flow():
    definition = {
        "cuerpo": [
            {
                "titulo": "III. HIPOTESIS Y VARIABLES",
                "contenido": [
                    {"texto": "3.1 Hipotesis"},
                    {"texto": "3.2 Operacionalizacion de variable"},
                ],
            }
        ],
    }

    section_service = InstitutionalSectionService()
    extracted = section_service.extract_sections(definition)
    by_path = {item["section_path"]: item for item in extracted}
    prompt_package = {
        "id": "unac-proyecto-cuant",
        "sections": [
            {
                **by_path["III. HIPOTESIS Y VARIABLES"],
                "blocks": [
                    {
                        "block_id": "chapter-iii",
                        "header": "Marco del capitulo",
                        "instructions": "No debe generarse para proyecto UNAC.",
                    }
                ],
            },
            {
                **by_path["III. HIPOTESIS Y VARIABLES/3.1 Hipotesis"],
                "blocks": [
                    {
                        "block_id": "hypothesis",
                        "header": "Hipotesis",
                        "instructions": "Validar hipotesis.",
                    }
                ],
            },
            {
                **by_path["III. HIPOTESIS Y VARIABLES/3.2 Operacionalizacion de variable"],
                "blocks": [
                    {
                        "block_id": "operationalization",
                        "header": "Operacionalizacion",
                        "instructions": "Validar tablas.",
                    }
                ],
            },
        ],
    }

    planner = ProjectGenerationPlanner(section_service=section_service)
    planned = planner.plan_sections(
        definition=definition,
        prompt_package=prompt_package,
        selected_sections=[{"section_path": "III. HIPOTESIS Y VARIABLES"}],
    )

    planned_paths = [item["path"] for item in planned if item["path"] != "Título + Información Básica"]
    assert planned_paths == [
        "III. HIPOTESIS Y VARIABLES/3.1 Hipotesis",
        "III. HIPOTESIS Y VARIABLES/3.2 Operacionalizacion de variable",
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


def test_plan_sections_injects_titulo_info_basica_for_unac_proyecto():
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
        "format_id": "unac-proyecto-cuant",
        "university": "unac",
        "category": "Proyecto de Tesis",
        "sections": [
            {
                **by_path["I. PLANTEAMIENTO DEL PROBLEMA/1.1 Realidad problematica"],
                "blocks": [
                    {
                        "block_id": "rp-1",
                        "header": "Realidad problematica",
                        "label": "Prompt realidad problematica",
                        "instructions": "Describe el problema real con evidencia.",
                        "required_variables": ["variable_dependiente"],
                        "required": True,
                    }
                ],
            }
        ],
    }

    planner = ProjectGenerationPlanner(section_service=section_service)
    planned = planner.plan_sections(
        definition=definition,
        prompt_package=prompt_package,
        selected_sections=[
            {"section_path": "I. PLANTEAMIENTO DEL PROBLEMA/1.1 Realidad problematica"},
        ],
    )

    assert [item["sectionId"] for item in planned] == [
        "titulo-info-basica",
        by_path["I. PLANTEAMIENTO DEL PROBLEMA/1.1 Realidad problematica"]["section_id"],
    ]
    assert planned[0]["path"] == "Título + Información Básica"


def test_plan_sections_collapses_schedule_and_budget_to_parent_sections_for_unac_project():
    definition = {
        "cuerpo": [
            {
                "titulo": "V. CRONOGRAMA DE ACTIVIDADES",
                "contenido": [
                    {"texto": "Cronograma de ejecucion"},
                    {
                        "tipo": "tabla",
                        "titulo": "Cronograma Detallado de Actividades",
                        "encabezados": ["Actividad", "Mes 1"],
                        "filas": [["Revision", "X"]],
                    },
                ],
            },
            {
                "titulo": "VI. PRESUPUESTO",
                "contenido": [
                    {"texto": "Recursos y Presupuesto"},
                    {
                        "tipo": "tabla",
                        "titulo": "Presupuesto del Proyecto",
                        "encabezados": ["Rubro", "Costo"],
                        "filas": [["Materiales", "100"]],
                    },
                ],
            },
        ]
    }

    section_service = InstitutionalSectionService()
    extracted = section_service.extract_sections(definition)
    prompt_package = {
        "format_id": "unac-proyecto-cuant",
        "sections": [{**item, "blocks": []} for item in extracted],
    }

    planner = ProjectGenerationPlanner(section_service=section_service)
    planned = planner.plan_sections(
        definition=definition,
        prompt_package=prompt_package,
        selected_sections=None,
    )

    planned_paths = [item["path"] for item in planned]
    assert "V. CRONOGRAMA DE ACTIVIDADES" in planned_paths
    assert "VI. PRESUPUESTO" in planned_paths
    assert all(not path.startswith("V. CRONOGRAMA DE ACTIVIDADES/") for path in planned_paths)
    assert all(not path.startswith("VI. PRESUPUESTO/") for path in planned_paths)
    assert planned[0]["title"] == "Título + Información Básica"
    assert planned[0]["blocks"][0]["header"] == "Validación de Título e Información Básica"

def test_plan_sections_accepts_legacy_child_selection_and_maps_to_parent():
    definition = {
        "cuerpo": [
            {
                "titulo": "V. CRONOGRAMA DE ACTIVIDADES",
                "contenido": [
                    {"texto": "Cronograma de ejecucion"},
                    {
                        "tipo": "tabla",
                        "titulo": "Cronograma Detallado de Actividades",
                        "encabezados": ["Actividad", "Mes 1"],
                        "filas": [["Revision", "X"]],
                    },
                ],
            },
            {
                "titulo": "VI. PRESUPUESTO",
                "contenido": [
                    {"texto": "Recursos y Presupuesto"},
                    {
                        "tipo": "tabla",
                        "titulo": "Presupuesto del Proyecto",
                        "encabezados": ["Rubro", "Costo"],
                        "filas": [["Materiales", "100"]],
                    },
                ],
            },
        ]
    }

    section_service = InstitutionalSectionService()
    extracted = section_service.extract_sections(definition)
    prompt_package = {
        "format_id": "unac-proyecto-cuant",
        "sections": [{**item, "blocks": []} for item in extracted],
    }

    planner = ProjectGenerationPlanner(section_service=section_service)
    planned = planner.plan_sections(
        definition=definition,
        prompt_package=prompt_package,
        selected_sections=[
            {"section_path": "V. CRONOGRAMA DE ACTIVIDADES/Cronograma de ejecucion"},
            {"section_path": "VI. PRESUPUESTO/Presupuesto del Proyecto"},
        ],
    )

    planned_paths = [item["path"] for item in planned]
    assert "V. CRONOGRAMA DE ACTIVIDADES" in planned_paths
    assert "VI. PRESUPUESTO" in planned_paths
    assert all(not path.startswith("V. CRONOGRAMA DE ACTIVIDADES/") for path in planned_paths)
    assert all(not path.startswith("VI. PRESUPUESTO/") for path in planned_paths)
