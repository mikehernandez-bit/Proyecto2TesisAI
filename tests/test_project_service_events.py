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
