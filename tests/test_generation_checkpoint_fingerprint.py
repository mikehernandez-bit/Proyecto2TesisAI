from app.modules.api.payload_helpers import project_input_fingerprint


def _project() -> dict:
    return {
        "format_id": "unac-proyecto-cuant",
        "format_version": "1",
        "prompt_id": "tesis",
        "title": "Proyecto",
        "values": {"periodo": "2025"},
        "variables": {"variable_dependiente": "Disponibilidad"},
        "selected_sections": [{"id": "sec-1"}],
        "ai_selection": {"provider": "mistral", "model": "model-a"},
    }


def test_provider_change_keeps_checkpoint_compatible() -> None:
    first = _project()
    second = _project()
    second["ai_selection"] = {"provider": "gemini", "model": "model-b"}

    assert project_input_fingerprint(first) == project_input_fingerprint(second)


def test_content_input_change_invalidates_checkpoint() -> None:
    first = _project()
    second = _project()
    second["variables"]["variable_dependiente"] = "Confiabilidad"

    assert project_input_fingerprint(first) != project_input_fingerprint(second)
