"""Unit tests for ProjectService event storage helpers."""

from app.core.services.project_service import ProjectService


def test_append_event_truncates_to_200(tmp_path):
    service = ProjectService(str(tmp_path / "projects.json"))
    project = service.create_project({"title": "Event window test"})
    project_id = project["id"]

    for index in range(250):
        service.append_event(
            project_id,
            {
                "ts": f"2026-02-19T10:00:{index:02d}Z",
                "stage": "test.event",
                "message": f"event-{index}",
            },
        )

    updated = service.get_project(project_id)
    assert updated is not None

    events = updated["events"]
    assert len(events) == 200
    assert events[0]["message"] == "event-50"
    assert events[-1]["message"] == "event-249"
    assert updated["trace"] == events


def test_mark_completed_with_warning_incidents_sets_incident_status(tmp_path):
    service = ProjectService(str(tmp_path / "projects.json"))
    project = service.create_project({"title": "Incidents status"})
    project_id = project["id"]

    service.append_incident(
        project_id,
        {
            "severity": "warning",
            "phase": "cleanup_correction",
            "provider": "mistral",
            "message": "Correccion omitida por error transitorio.",
        },
    )
    updated = service.mark_completed(project_id, output_file="outputs/test.docx")

    assert updated is not None
    assert updated["status"] == "completed_with_incidents"
    assert updated["warnings_count"] == 1
    assert len(updated["incidents"]) == 1


def test_mark_failed_can_keep_partial_ai_result(tmp_path):
    service = ProjectService(str(tmp_path / "projects.json"))
    project = service.create_project({"title": "Partial resume"})
    project_id = project["id"]

    service.update_project(
        project_id,
        {
            "run_id": "run-001",
            "ai_result": {
                "sections": [
                    {
                        "sectionId": "sec-0001",
                        "path": "Introduccion",
                        "content": "Contenido parcial",
                    }
                ]
            },
        },
    )

    failed = service.mark_failed(project_id, "Error transitorio", keep_ai_result=True)
    assert failed is not None
    assert failed["status"] == "failed"
    assert failed["ai_result"] is not None
    assert len(failed["ai_result"]["sections"]) == 1
    assert failed["run_id"] == "run-001"


def test_mark_render_failed_preserves_ai_result_and_clears_artifacts(tmp_path):
    service = ProjectService(str(tmp_path / "projects.json"))
    project = service.create_project({"title": "Render retry"})
    project_id = project["id"]

    service.update_project(
        project_id,
        {
            "run_id": "render-run-001",
            "ai_result": {
                "sections": [
                    {
                        "sectionId": "sec-0001",
                        "path": "Cronograma",
                        "content": "Contenido estructurado listo para render.",
                    }
                ]
            },
            "artifacts": [{"type": "docx", "downloadUrl": "/api/download/x"}],
            "output_file": "outputs/test.docx",
            "pdf_file": "outputs/test.pdf",
            "progress": {
                "current": 4,
                "total": 4,
                "currentPath": "Cronograma",
                "provider": "mistral",
            },
        },
    )

    failed = service.mark_render_failed(project_id, "422 payload invalid")
    assert failed is not None
    assert failed["status"] == "render_failed"
    assert failed["ai_result"] is not None
    assert failed["run_id"] == "render-run-001"
    assert failed["artifacts"] == []
    assert failed["output_file"] is None
    assert failed["pdf_file"] is None
    assert failed["progress"]["current"] == 4
    assert failed["progress"]["total"] == 4


def test_resume_checkpoint_is_saved_and_cleared_on_complete(tmp_path):
    service = ProjectService(str(tmp_path / "projects.json"))
    project = service.create_project({"title": "Resume checkpoint"})
    project_id = project["id"]

    updated = service.mark_resume_checkpoint(
        project_id,
        saved_sections_count=3,
        last_failed_section_path="Capitulo 3",
        reason="Error transitorio",
        base_run_id="run-xyz",
    )
    assert updated is not None
    assert updated["resume"]["eligible"] is True
    assert updated["resume"]["saved_sections_count"] == 3
    assert updated["resume"]["resume_from_index"] == 3
    assert updated["resume"]["last_failed_section_path"] == "Capitulo 3"
    assert updated["resume"]["base_run_id"] == "run-xyz"

    completed = service.mark_completed(project_id, output_file="outputs/final.docx")
    assert completed is not None
    assert completed["resume"]["eligible"] is False
    assert completed["resume"]["saved_sections_count"] == 0


def test_list_projects_orders_by_recent_activity_and_status(tmp_path):
    service = ProjectService(str(tmp_path / "projects.json"))
    draft = service.create_project({"title": "Draft project", "status": "draft"})
    generating = service.create_project({"title": "Generating project", "status": "generating"})
    completed = service.create_project({"title": "Completed project", "status": "completed"})

    items = service.store.read_list()
    for item in items:
        if item["id"] == draft["id"]:
            item["updated_at"] = "2026-03-18T10:00:00"
            item["status"] = "draft"
        elif item["id"] == generating["id"]:
            item["updated_at"] = "2026-03-18T10:00:00"
            item["status"] = "generating"
        elif item["id"] == completed["id"]:
            item["updated_at"] = "2026-03-18T11:00:00"
            item["status"] = "completed"
    service.store.write_list(items)

    ordered = service.list_projects()
    ordered_ids = [item["id"] for item in ordered[:3]]

    assert ordered_ids[0] == completed["id"]
    assert ordered_ids[1] == generating["id"]
    assert ordered_ids[2] == draft["id"]


def test_update_project_merges_wizard_state_without_losing_progress(tmp_path):
    service = ProjectService(str(tmp_path / "projects.json"))
    project = service.create_project({"title": "Wizard state merge"})

    updated = service.update_project(
        project["id"],
        {
            "wizard_state": {
                "current_step": 3,
                "last_open_mode": "edit",
            }
        },
    )

    assert updated is not None
    assert updated["wizard_state"]["current_step"] == 3
    assert updated["wizard_state"]["last_completed_step"] == 3
    assert updated["wizard_state"]["last_open_mode"] == "edit"


def test_update_project_can_skip_top_level_updated_at_for_navigation(tmp_path):
    service = ProjectService(str(tmp_path / "projects.json"))
    project = service.create_project({"title": "Readonly navigation"})

    items = service.store.read_list()
    items[0]["updated_at"] = "2026-03-18T10:00:00"
    service.store.write_list(items)

    updated = service.update_project(
        project["id"],
        {
            "wizard_state": {
                "current_step": 5,
                "last_open_mode": "review",
                "updated_at": "2026-03-19T08:00:00",
            }
        },
        touch_updated_at=False,
    )

    assert updated is not None
    assert updated["updated_at"] == "2026-03-18T10:00:00"
    assert updated["wizard_state"]["current_step"] == 5
    assert updated["wizard_state"]["last_open_mode"] == "review"


def test_update_project_preserves_custom_prompt_snapshot_sections_and_order(tmp_path):
    service = ProjectService(str(tmp_path / "projects.json"))
    project = service.create_project({"title": "Custom prompt snapshot"})

    updated = service.update_project(
        project["id"],
        {
            "prompt_snapshot": {
                "id": "prompt-demo",
                "sections": [
                    {
                        "section_id": "custom_section_capitulo",
                        "section_path": "CAPITULO ESPECIAL",
                        "section_title": "CAPITULO ESPECIAL",
                        "parent_section_path": "",
                        "section_level": 1,
                        "section_order": 10,
                        "blocks": [],
                    },
                    {
                        "section_id": "custom_section_sub",
                        "section_path": "CAPITULO ESPECIAL/3.1 Aplicacion piloto",
                        "section_title": "3.1 Aplicacion piloto",
                        "parent_section_path": "CAPITULO ESPECIAL",
                        "section_level": 2,
                        "section_order": 11,
                        "blocks": [
                            {
                                "block_id": "custom_block_1",
                                "header": "Aplicacion piloto",
                                "label": "Prompt aplicacion piloto",
                                "instructions": "Describe el piloto.",
                                "required_variables": ["alcance_piloto"],
                            }
                        ],
                    },
                ],
            },
            "selected_sections": [
                {
                    "section_id": "custom_section_sub",
                    "section_path": "CAPITULO ESPECIAL/3.1 Aplicacion piloto",
                    "section_title": "3.1 Aplicacion piloto",
                    "parent_section_path": "CAPITULO ESPECIAL",
                    "section_level": 2,
                    "section_order": 11,
                }
            ],
        },
    )

    assert updated is not None
    assert updated["prompt_snapshot"]["sections"][0]["section_order"] == 10
    assert updated["prompt_snapshot"]["sections"][1]["section_order"] == 11
    assert updated["selected_sections"][0]["section_order"] == 11
