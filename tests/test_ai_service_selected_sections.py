from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.core.services.ai.ai_service import AIService
from app.core.services.project_generation_planner import ProjectGenerationPlanner


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
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def is_configured(self) -> bool:
        return True

    def generate_with_usage(self, prompt: str, *, timeout: int = 60, model: str | None = None):
        self.prompts.append(prompt)
        return "Contenido generado para la seccion seleccionada.", {
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
    provider = _UsageProvider()
    service._clients = {
        "gemini": provider,
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
    prompt_package = {
        "sections": [
            {
                "section_id": "sec-0001",
                "section_path": "INTRODUCCION",
                "section_title": "INTRODUCCION",
                "section_level": 1,
                "optional": False,
                "default_selected": True,
                "blocks": [
                    {
                        "block_id": "intro-1",
                        "header": "Contexto introductorio",
                        "label": "Prompt introduccion",
                        "instructions": "Enfoca solo la introduccion.",
                        "required_variables": ["variable_dependiente"],
                        "required": True,
                    }
                ],
            }
        ]
    }
    planned_sections = ProjectGenerationPlanner().plan_sections(
        definition=format_detail["definition"],
        prompt_package=prompt_package,
        selected_sections=[{"section_path": "INTRODUCCION"}],
    )

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
    assert provider.prompts
    assert "Capitulo padre: INTRODUCCION" in provider.prompts[0]
    assert "Seccion actual: INTRODUCCION" in provider.prompts[0]
    assert "Cabecera: Contexto introductorio" in provider.prompts[0]


def test_generate_includes_app_memory_between_sections():
    service = AIService()
    service._selection_store = _InMemorySelectionStore()
    service._selection = service._selection_store.get_selection()
    provider = _UsageProvider()
    service._clients = {
        "gemini": provider,
        "mistral": MagicMock(is_configured=MagicMock(return_value=False)),
        "openrouter": MagicMock(is_configured=MagicMock(return_value=False)),
    }

    project = {
        "id": "proj-memory",
        "title": "Proyecto tesis",
        "variables": {
            "tema": "Proyecto tesis",
            "variable_dependiente": "Indicador X",
            "pregunta_principal": "Como mejorar el proceso",
        },
    }
    planned_sections = [
        {
            "sectionId": "sec-1",
            "path": "INTRODUCCION",
            "title": "INTRODUCCION",
            "parent_section_path": "",
            "level": 1,
            "section_order": 1,
            "hints": "",
            "optional": False,
            "default_selected": True,
            "blocks": [
                {
                    "block_id": "intro-1",
                    "header": "Contexto introductorio",
                    "cabecera": "Contexto introductorio",
                    "label": "Prompt introduccion",
                    "instructions": "Enfoca la introduccion.",
                    "required_variables": ["variable_dependiente"],
                    "required": True,
                }
            ],
            "required_variables": ["variable_dependiente"],
            "additional_context": "Capitulo padre: INTRODUCCION",
        },
        {
            "sectionId": "sec-2",
            "path": "I. PLANTEAMIENTO DEL PROBLEMA/1.1 Realidad problematica",
            "title": "1.1 Realidad problematica",
            "parent_section_path": "I. PLANTEAMIENTO DEL PROBLEMA",
            "level": 2,
            "section_order": 2,
            "hints": "",
            "optional": False,
            "default_selected": True,
            "blocks": [
                {
                    "block_id": "prob-1",
                    "header": "Realidad problematica",
                    "cabecera": "Realidad problematica",
                    "label": "Prompt realidad problematica",
                    "instructions": "Sustenta con evidencia.",
                    "required_variables": ["pregunta_principal"],
                    "required": True,
                }
            ],
            "required_variables": ["pregunta_principal"],
            "additional_context": "Capitulo padre: I. PLANTEAMIENTO DEL PROBLEMA",
        },
    ]

    with patch("app.core.services.ai.ai_service.settings", _settings()):
        result = service.generate(
            project,
            {"format_id": "unac-proyecto-cuant", "definition": {}},
            {"template": "Tema: {{tema}}"},
            planned_sections=planned_sections,
        )

    assert len(result["sections"]) == 2
    # 2 prompts: la reparacion hardcodeada de "1.1 realidad problematica"
    # (topico fijo RCM/CAT 24M) esta deshabilitada; ver _repair_reality_problem_sections.
    assert len(provider.prompts) == 2
    assert "Memoria de continuidad entre secciones:" not in provider.prompts[0]
    assert "Memoria de continuidad entre secciones:" in provider.prompts[1]
    assert "Secciones previas completadas: INTRODUCCION" in provider.prompts[1]
    assert "Seccion inmediatamente anterior: INTRODUCCION" in provider.prompts[1]
    assert "Variables o decisiones ya fijadas:" in provider.prompts[1]
