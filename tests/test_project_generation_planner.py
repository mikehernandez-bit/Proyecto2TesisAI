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
    assert "Prompt introduccion" in planned[0]["additional_context"]
    assert "evidencia tecnica" in planned[1]["additional_context"]
