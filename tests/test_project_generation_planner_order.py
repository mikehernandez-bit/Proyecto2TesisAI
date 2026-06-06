from app.core.services.institutional_section_service import InstitutionalSectionService
from app.core.services.project_generation_planner import ProjectGenerationPlanner


def test_plan_sections_keeps_negative_order_for_titulo_info_basica():
    definition = {
        "preliminares": {
            "introduccion": {"titulo": "INTRODUCCION"},
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
        "format_id": "unac-proyecto-cuant",
        "university": "unac",
        "category": "Proyecto de Tesis",
        "sections": [
            {
                **by_path["INTRODUCCION"],
                "blocks": [],
            },
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
            },
        ],
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

    assert planned[0]["sectionId"] == "titulo-info-basica"
    assert planned[0]["section_order"] == -100
    assert planned[0]["section_order"] < planned[1]["section_order"]
    assert planned[1]["path"] == "INTRODUCCION"
