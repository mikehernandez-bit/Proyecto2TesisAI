from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.core.services.ai.ai_service import AIService


class _InMemorySelectionStore:
    def __init__(self) -> None:
        self._selection = {
            "provider": "gemini",
            "model": "gemini-2.0-flash",
            "fallback_provider": "mistral",
            "fallback_model": "mistral-medium-2505",
            "mode": "fixed",
        }

    def get_selection(self):
        return dict(self._selection)

    def normalize(self, payload):
        merged = dict(self._selection)
        merged.update(payload or {})
        return merged

    def set_selection(self, payload):
        self._selection.update(payload or {})
        return dict(self._selection)


class _UsageProvider:
    def is_configured(self) -> bool:
        return True

    def generate_with_usage(self, prompt: str, *, timeout: int = 60, model: str | None = None):
        return "Contenido generado para la sección seleccionada.", {
            "input_tokens": 80,
            "output_tokens": 40,
            "total_tokens": 120,
        }


def _settings():
    return SimpleNamespace(
        AI_PRIMARY_PROVIDER="gemini",
        AI_FALLBACK_ON_QUOTA=False,
        AI_FORCE_FALLBACK_ON_TRANSIENT=False,
        AI_CORRECTION_ENABLED=False,
        GEMINI_MODEL="gemini-2.0-flash",
        MISTRAL_MODEL="mistral-medium-2505",
        OPENROUTER_MODEL="openai/gpt-oss-120b:free",
    )


def test_generate_uses_only_planned_sections():
    service = AIService()
    service._selection_store = _InMemorySelectionStore()
    service._selection = service._selection_store.get_selection()
    service._clients = {
        "gemini": _UsageProvider(),
        "mistral": MagicMock(is_configured=MagicMock(return_value=False)),
        "openrouter": MagicMock(is_configured=MagicMock(return_value=False)),
    }

    project = {
        "id": "proj-selected-sections",
        "title": "Proyecto tesis",
        "variables": {"tema": "Proyecto tesis", "variable_dependiente": "Indicador X"},
    }
    format_detail = {
        "definition": {
            "preliminares": {
                "resumen": {"titulo": "RESUMEN"},
                "introduccion": {"titulo": "INTRODUCCION"},
            },
            "cuerpo": [
                {
                    "titulo": "I. PLANTEAMIENTO DEL PROBLEMA",
                    "contenido": [{"texto": "1.1 Realidad problematica"}],
                }
            ],
        }
    }
    planned_sections = [
        {
            "sectionId": "sec-0001",
            "path": "INTRODUCCION",
            "title": "INTRODUCCION",
            "level": 1,
            "hints": "",
            "optional": False,
            "default_selected": True,
            "blocks": [
                {
                    "block_id": "intro-1",
                    "label": "Prompt introduccion",
                    "instructions": "Enfoca solo la introduccion.",
                    "required_variables": ["variable_dependiente"],
                    "required": True,
                }
            ],
            "required_variables": ["variable_dependiente"],
            "additional_context": "Bloques de prompt activos:\n- Prompt introduccion",
        }
    ]

    with patch("app.core.services.ai.ai_service.settings", _settings()):
        result = service.generate(
            project,
            format_detail,
            {"template": "Tema: {{tema}}"},
            planned_sections=planned_sections,
        )

    assert len(result["sections"]) == 1
    assert result["sections"][0]["path"] == "INTRODUCCION"
    assert result["tokenUsage"]["calls_total"] == 1
