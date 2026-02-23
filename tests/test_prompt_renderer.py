"""Tests for app.core.services.ai.prompt_renderer."""
import pytest
from app.core.services.ai.prompt_renderer import PromptRenderer, SYSTEM_PROMPT


@pytest.fixture
def renderer():
    return PromptRenderer()


class TestRender:
    def test_basic_substitution(self, renderer):
        template = "Tema: {{tema}}. Objetivo: {{objetivo_general}}."
        values = {"tema": "IA en salud", "objetivo_general": "mejorar diagnosticos"}
        result = renderer.render(template, values)
        assert result == "Tema: IA en salud. Objetivo: mejorar diagnosticos."

    def test_missing_variables_kept_as_placeholders(self, renderer):
        template = "Tema: {{tema}}. Hipotesis: {{hipotesis}}."
        values = {"tema": "Redes neuronales"}
        result = renderer.render(template, values)
        assert "Redes neuronales" in result
        assert "{{hipotesis}}" in result  # kept as-is

    def test_empty_template(self, renderer):
        result = renderer.render("", {"tema": "algo"})
        assert result == ""

    def test_whitespace_in_braces(self, renderer):
        template = "{{ tema }} y {{  objetivo_general  }}"
        values = {"tema": "X", "objetivo_general": "Y"}
        result = renderer.render(template, values)
        assert result == "X y Y"


class TestBuildSectionPrompt:
    def test_section_prompt_contains_path(self, renderer):
        prompt = renderer.build_section_prompt(
            base_prompt="Escribe sobre IA",
            section_path="Capitulo 1 > Introduccion",
            section_id="sec-0001",
        )
        assert "Capitulo 1 > Introduccion" in prompt
        assert "sec-0001" in prompt
        assert "Escribe sobre IA" in prompt

    def test_section_prompt_with_extra_context(self, renderer):
        prompt = renderer.build_section_prompt(
            base_prompt="Base",
            section_path="Marco Teorico",
            section_id="sec-0002",
            extra_context="Incluir 3 referencias APA",
        )
        assert "Incluir 3 referencias APA" in prompt

    def test_system_prompt_included(self, renderer):
        """System prompt formatting rules must appear in every section prompt."""
        prompt = renderer.build_section_prompt(
            base_prompt="Base",
            section_path="Introduccion",
            section_id="sec-0001",
        )
        assert "REGLAS OBLIGATORIAS" in prompt
        assert "NO uses Markdown" in prompt
        assert "Texto plano" in prompt.lower() or "texto plano" in prompt

    def test_system_prompt_renders_project_values(self, renderer):
        """Project variables in SYSTEM_PROMPT should be rendered."""
        values = {
            "title": "Mi Tesis",
            "tema": "IA Logistica",
            "objetivo_general": "Optimizar",
            "poblacion": "Empresas",
            "variable_independiente": "Algoritmos",
        }
        prompt = renderer.build_section_prompt(
            base_prompt="Base",
            section_path="Intro",
            section_id="sec-0001",
            values=values,
        )
        assert "Mi Tesis" in prompt
        assert "IA Logistica" in prompt
        assert "Optimizar" in prompt
        assert "Empresas" in prompt
        assert "Algoritmos" in prompt

    def test_system_prompt_constant_has_rules(self):
        """Verify the SYSTEM_PROMPT constant contains key formatting rules."""
        assert "NO uses Markdown" in SYSTEM_PROMPT
        assert "NO escribas el titulo" in SYSTEM_PROMPT
        assert "FIGURA DE EJEMPLO" in SYSTEM_PROMPT
        assert "<<SKIP_SECTION>>" in SYSTEM_PROMPT
        assert "{{title}}" in SYSTEM_PROMPT
        assert "{{tema}}" in SYSTEM_PROMPT
