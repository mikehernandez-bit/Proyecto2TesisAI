from app.core.services.generation_checkpoints import ConstructionCheckpoint, GenerationCheckpoint


def test_checkpoint_contracts_are_serializable() -> None:
    generation = GenerationCheckpoint(
        input_fingerprint="abc",
        profile_version="UNAC_MAINTENANCE_V1",
        saved_sections_count=2,
        resume_from_index=2,
        completed_section_ids=("sec-1", "sec-2"),
        failed_stage="quality_validation",
        failed_quality_keys=("2.1.1",),
    )
    construction = ConstructionCheckpoint(
        input_fingerprint="abc",
        stage="render_pdf",
        completed_tasks=("payload", "render_docx"),
        docx_path="outputs/project.docx",
    )

    assert generation.to_dict()["saved_sections_count"] == 2
    assert generation.to_dict()["failed_quality_keys"] == ("2.1.1",)
    assert construction.to_dict()["stage"] == "render_pdf"
