import pytest

from app.integrations.gicatesis.types import RenderPayloadValidationError
from app.modules.api.payload_helpers import build_render_payload


def _values() -> dict:
    return {
        "title": "Plan de mantenimiento RCM para mejorar la disponibilidad",
        "problema_general": "¿De qué manera el plan mejora la disponibilidad?",
        "problemas_especificos": [
            "¿De qué manera mejora la confiabilidad?",
            "¿De qué manera mejora la mantenibilidad?",
        ],
        "objetivo_general": "Determinar la mejora de la disponibilidad.",
        "objetivos_especificos": [
            "Evaluar la confiabilidad.",
            "Evaluar la mantenibilidad.",
        ],
        "hipotesis_especificas": [
            "El plan mejora la confiabilidad.",
            "El plan mejora la mantenibilidad.",
        ],
    }


def test_valid_matrix_is_preserved_in_render_payload() -> None:
    payload = build_render_payload(
        format_id="unac-proyecto-cuant",
        values=_values(),
        ai_result_raw={"sections": []},
    )

    assert payload["values"]["problema_general"].startswith("¿")


def test_misaligned_matrix_is_rejected_before_docx() -> None:
    values = _values()
    values["objetivos_especificos"] = ["Evaluar la confiabilidad."]

    with pytest.raises(RenderPayloadValidationError) as captured:
        build_render_payload(
            format_id="unac-proyecto-cuant",
            values=values,
            ai_result_raw={"sections": []},
        )
    assert "correspondencia uno a uno" in str(captured.value.errors)
