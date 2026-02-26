"""Test completo del flujo de prompts: selección → renderizado → entrega a IA.

Cubre:
- PromptService: carga y búsqueda de prompts
- PromptRenderer: renderizado de variables y construcción de prompts
- Integración: el prompt llega correctamente al LLM en cada escenario
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

# --------------------------------------------------------------------- #
# Importaciones del proyecto                                            #
# --------------------------------------------------------------------- #
from app.core.services.prompt_service import PromptService
from app.core.services.ai.prompt_renderer import PromptRenderer, SYSTEM_PROMPT


# --------------------------------------------------------------------- #
# Fixtures                                                               #
# --------------------------------------------------------------------- #
PROMPTS_JSON = Path("data/prompts.json")

SAMPLE_PROMPT_CUANT = {
    "id": "prompt_test_cuant",
    "name": "Informe Cuantitativo TEST",
    "doc_type": "Tesis Completa",
    "is_active": True,
    "system_instruction": "Actúa como asesor experto cuantitativo.",
    "template": (
        "Actúa como asesor experto cuantitativo. "
        "Tema: {{tema}}. Objetivo: {{objetivo_general}}."
    ),
    "variables": ["tema", "objetivo_general", "poblacion"],
    "sections": [
        {
            "section_id": "sec_0",
            "name": "Marco Teórico",
            "instruction": "Redacta el marco teórico.",
            "variables": ["antecedentes"],
            "order": 0,
        },
    ],
}

SAMPLE_PROMPT_CUAL = {
    "id": "prompt_test_cual",
    "name": "Informe Cualitativo TEST",
    "doc_type": "Tesis Completa",
    "is_active": True,
    "system_instruction": "Actúa como asesor cualitativo interpretativo.",
    "template": (
        "Actúa como asesor cualitativo interpretativo. "
        "Escenario: {{escenario_estudio}}. Informantes: {{informantes_clave}}."
    ),
    "variables": ["escenario_estudio", "informantes_clave"],
    "sections": [],
}


@pytest.fixture
def temp_prompts_file():
    """Crea un archivo temporal con prompts para testing."""
    data = [SAMPLE_PROMPT_CUANT, SAMPLE_PROMPT_CUAL]
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    )
    json.dump(data, tmp, ensure_ascii=False)
    tmp.close()
    yield tmp.name
    os.unlink(tmp.name)


@pytest.fixture
def prompt_service(temp_prompts_file):
    """PromptService configurado con datos de prueba."""
    return PromptService(path=temp_prompts_file)


@pytest.fixture
def renderer():
    return PromptRenderer()


# ===================================================================== #
#  1. PROMPT SERVICE – carga y búsqueda                                 #
# ===================================================================== #
class TestPromptServiceCRUD:
    """Verifica que PromptService carga y busca prompts correctamente."""

    def test_list_prompts_returns_all(self, prompt_service):
        """Debe listar todos los prompts disponibles."""
        prompts = prompt_service.list_prompts()
        assert len(prompts) == 2

    def test_get_prompt_by_id(self, prompt_service):
        """Debe encontrar un prompt por su ID."""
        result = prompt_service.get_prompt("prompt_test_cuant")
        assert result is not None
        assert result["name"] == "Informe Cuantitativo TEST"

    def test_get_prompt_by_id_not_found(self, prompt_service):
        """Debe retornar None si el ID no existe."""
        result = prompt_service.get_prompt("prompt_inexistente")
        assert result is None

    def test_get_prompt_has_template(self, prompt_service):
        """Todo prompt debe tener un template no vacío."""
        result = prompt_service.get_prompt("prompt_test_cuant")
        assert result["template"]
        assert len(result["template"]) > 10

    def test_get_prompt_has_variables(self, prompt_service):
        """Todo prompt debe declarar sus variables."""
        result = prompt_service.get_prompt("prompt_test_cuant")
        assert "variables" in result
        assert len(result["variables"]) > 0

    def test_prompt_cualitativo_has_different_template(self, prompt_service):
        """Prompt cualitativo debe tener template distinto al cuantitativo."""
        cuant = prompt_service.get_prompt("prompt_test_cuant")
        cual = prompt_service.get_prompt("prompt_test_cual")
        assert cuant["template"] != cual["template"]


# ===================================================================== #
#  2. PROMPT SERVICE – con datos REALES (prompts.json)                  #
# ===================================================================== #
class TestPromptServiceReal:
    """Verifica que los prompts reales en prompts.json están bien formados."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.service = PromptService(path=str(PROMPTS_JSON))
        self.prompts = self.service.list_prompts()

    def test_at_least_9_prompts(self):
        """Debe haber al menos 9 prompts reales (uno por formato)."""
        # El usuario dejó 10 prompts
        assert len(self.prompts) >= 9, (
            f"Se esperaban al menos 9 prompts, hay {len(self.prompts)}"
        )

    def test_no_test_prompts_remain(self):
        """No deben quedar prompts de prueba 'Test Prompt QA'."""
        for p in self.prompts:
            assert p["name"] != "Test Prompt QA", (
                f"Prompt de prueba {p['id']} aún existe"
            )

    def test_each_prompt_has_required_fields(self):
        """Cada prompt debe tener id, name, template."""
        for p in self.prompts:
            assert p.get("id"), f"Prompt sin ID: {p}"
            assert p.get("name"), f"Prompt sin name: {p.get('id')}"
            assert p.get("template"), f"Prompt sin template: {p.get('id')}"

    def test_each_prompt_has_variables(self):
        """Cada prompt real debe declarar variables."""
        for p in self.prompts:
            variables = p.get("variables", [])
            assert len(variables) > 0, (
                f"Prompt {p['id']} ({p['name']}) no tiene variables"
            )

    def test_no_duplicate_ids(self):
        """No debe haber IDs duplicados."""
        ids = [p["id"] for p in self.prompts]
        assert len(ids) == len(set(ids)), (
            f"IDs duplicados: {[x for x in ids if ids.count(x) > 1]}"
        )

    @pytest.mark.parametrize(
        "prompt_id",
        [
            "prompt_45c88af464",   # Posgrado UNI
            "prompt_29aa7778cc",   # Maestría Cuant UNAC
            "prompt_7cf94e7523",   # Maestría Cual UNAC
            "prompt_6bc6fb0e9f",   # Plan Trabajo UNI
            "prompt_9f0764d149",   # Proyecto Cuant UNAC
            "prompt_c90ea886b7",   # Proyecto Cual UNAC
            "prompt_17595d0ce3",   # Informe UNI
            "prompt_fc13e3c0d8",   # Informe Cual UNAC
            "prompt_1936b2172c",   # Informe Cuant UNAC
        ],
    )
    def test_each_format_prompt_exists(self, prompt_id):
        """Cada formato de tesis debe tener su prompt asociado."""
        result = self.service.get_prompt(prompt_id)
        assert result is not None, f"Prompt {prompt_id} no encontrado"
        assert result["is_active"], f"Prompt {prompt_id} está inactivo"


# ===================================================================== #
#  3. PROMPT RENDERER – variables y placeholders                        #
# ===================================================================== #
class TestPromptRenderer:
    """Verifica el renderizado de templates con variables."""

    def test_render_replaces_variables(self, renderer):
        """Debe reemplazar {{variable}} con su valor."""
        template = "Tema: {{tema}}. Objetivo: {{objetivo_general}}."
        values = {"tema": "Redes neuronales", "objetivo_general": "Analizar el impacto"}
        result = renderer.render(template, values)
        assert "Redes neuronales" in result
        assert "Analizar el impacto" in result
        assert "{{tema}}" not in result

    def test_render_keeps_missing_variables(self, renderer):
        """Variables no proporcionadas se mantienen como {{variable}}."""
        template = "Tema: {{tema}}. Dato: {{dato_faltante}}."
        values = {"tema": "IA aplicada"}
        result = renderer.render(template, values)
        assert "IA aplicada" in result
        assert "{{dato_faltante}}" in result

    def test_render_empty_template(self, renderer):
        """Template vacío retorna cadena vacía."""
        result = renderer.render("", {"tema": "algo"})
        assert result == ""

    def test_render_no_variables_in_template(self, renderer):
        """Template sin {{}} se retorna tal cual."""
        template = "Este es un texto fijo sin variables."
        result = renderer.render(template, {"tema": "algo"})
        assert result == template

    def test_render_with_all_real_prompt_variables(self, renderer):
        """Simula un prompt real con todas sus variables."""
        template = (
            "Actúa como asesor. "
            "Tema: {{tema}}. Objetivo: {{objetivo_general}}. "
            "Hipótesis: {{hipotesis_general}}. "
            "Población: {{poblacion_total}}."
        )
        values = {
            "tema": "Optimización de procesos industriales",
            "objetivo_general": "Determinar la influencia del control automático",
            "hipotesis_general": "El control automático mejora la eficiencia en 20%",
            "poblacion_total": "150 operarios de la planta",
        }
        result = renderer.render(template, values)
        for val in values.values():
            assert val in result, f"Valor '{val}' no encontrado en prompt renderizado"
        assert "{{" not in result  # Ninguna variable sin resolver

    def test_render_trace_hook_called(self, renderer):
        """El trace_hook se llama al renderizar."""
        hook = MagicMock()
        renderer.render("Tema: {{tema}}", {"tema": "Test"}, trace_hook=hook)
        hook.assert_called_once()
        call_arg = hook.call_args[0][0]
        assert call_arg["step"] == "prompt.render"
        assert call_arg["status"] == "done"


# ===================================================================== #
#  4. BUILD SECTION PROMPT – prompt final para la IA                    #
# ===================================================================== #
class TestBuildSectionPrompt:
    """Verifica que build_section_prompt construye el prompt completo."""

    def test_system_prompt_included(self, renderer):
        """El SYSTEM_PROMPT global debe estar en el prompt final."""
        result = renderer.build_section_prompt(
            base_prompt="Escribe sobre redes",
            section_path="II. MARCO TEÓRICO/2.1 Antecedentes",
            section_id="sec-0012",
            values={"tema": "IA", "title": "Tesis de IA"},
        )
        assert "Eres un redactor academico profesional" in result
        assert "REGLAS OBLIGATORIAS" in result

    def test_section_path_injected(self, renderer):
        """La ruta de sección debe aparecer en el prompt final."""
        path = "II. MARCO TEÓRICO/2.1 Antecedentes"
        result = renderer.build_section_prompt(
            base_prompt="base",
            section_path=path,
            section_id="sec-0012",
            values={},
        )
        assert path in result

    def test_base_prompt_appears_as_context(self, renderer):
        """El prompt del usuario debe aparecer como CONTEXTO ADICIONAL."""
        base = "Actúa como asesor de la UNAC experto en cuantitativa."
        result = renderer.build_section_prompt(
            base_prompt=base,
            section_path="I. PLANTEAMIENTO",
            section_id="sec-0001",
            values={},
        )
        assert "CONTEXTO ADICIONAL DEL PROYECTO" in result
        assert base in result

    def test_extra_context_added(self, renderer):
        """El extra_context (hints) se incluye al final."""
        result = renderer.build_section_prompt(
            base_prompt="base",
            section_path="IV. METODOLOGÍA",
            section_id="sec-0005",
            extra_context="Usar diseño experimental puro con grupo control.",
            values={},
        )
        assert "diseño experimental puro" in result

    def test_variables_rendered_in_system_prompt(self, renderer):
        """Las variables del proyecto se resuelven en el SYSTEM_PROMPT."""
        result = renderer.build_section_prompt(
            base_prompt="base",
            section_path="INTRODUCCIÓN",
            section_id="sec-0001",
            values={
                "title": "Control automático en planta industrial",
                "tema": "Control PID",
                "objetivo_general": "Mejorar eficiencia",
                "poblacion": "100 operarios",
                "variable_independiente": "Sistema de control",
            },
        )
        assert "Control automático en planta industrial" in result
        assert "Control PID" in result
        assert "Mejorar eficiencia" in result

    def test_empty_base_prompt_still_has_system_prompt(self, renderer):
        """Con prompt base vacío, sigue existiendo el SYSTEM_PROMPT."""
        result = renderer.build_section_prompt(
            base_prompt="",
            section_path="INTRODUCCIÓN",
            section_id="sec-0001",
            values={},
        )
        assert "Eres un redactor academico profesional" in result
        assert "INTRODUCCIÓN" in result


# ===================================================================== #
#  5. INTEGRACIÓN – distintos prompts generan contextos diferentes      #
# ===================================================================== #
class TestPromptIntegration:
    """Verifica que distintos prompts producen contextos de IA diferentes."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.service = PromptService(path=str(PROMPTS_JSON))
        self.renderer = PromptRenderer()

    def _build_prompt_for_section(
        self,
        prompt_id: str,
        section_path: str,
        values: Dict[str, Any],
    ) -> str:
        """Simula el flujo completo: buscar prompt → renderizar → build."""
        prompt_data = self.service.get_prompt(prompt_id)
        assert prompt_data is not None, f"Prompt {prompt_id} no encontrado"
        template = prompt_data.get("template", "")
        base_prompt = self.renderer.render(template, values)
        return self.renderer.build_section_prompt(
            base_prompt=base_prompt,
            section_path=section_path,
            section_id="sec-test",
            values=values,
        )

    def test_cuantitativo_unac_includes_estadistica(self):
        """El prompt cuantitativo UNAC debe mencionar estadística."""
        result = self._build_prompt_for_section(
            prompt_id="prompt_1936b2172c",  # Informe Cuant UNAC
            section_path="IV. METODOLOGÍA/4.1 Diseño metodológico",
            values={
                "tema": "Control de calidad",
                "herramienta_ingenieria": "Diagrama de Pareto",
                "diagnostico_local": "Planta de manufactura Lima Norte",
            },
        )
        # El template cuantitativo menciona conceptos estadísticos
        assert "cuantitativo" in result.lower() or "estadístic" in result.lower() or (
            "APA" in result
        ), "El prompt cuantitativo debe tener contexto estadístico/cuantitativo"

    def test_cualitativo_unac_includes_categorias(self):
        """El prompt cualitativo UNAC debe mencionar categorías."""
        result = self._build_prompt_for_section(
            prompt_id="prompt_fc13e3c0d8",  # Informe Cual UNAC
            section_path="III. METODOLOGÍA/3.1 Categorías",
            values={
                "tema": "Satisfacción laboral",
                "escenario_estudio": "Hospital Nacional Callao",
                "informantes_clave": "10 enfermeras jefe",
            },
        )
        assert "cualitativ" in result.lower() or "categorización" in result.lower() or (
            "interpretativ" in result.lower()
        ), "El prompt cualitativo debe tener contexto de categorías/interpretación"

    def test_different_prompts_produce_different_contexts(self):
        """Dos prompts distintos deben generar contextos diferentes para la IA."""
        values = {"tema": "Automatización industrial"}

        prompt_cuant = self._build_prompt_for_section(
            prompt_id="prompt_1936b2172c",
            section_path="I. PLANTEAMIENTO",
            values=values,
        )
        prompt_cual = self._build_prompt_for_section(
            prompt_id="prompt_fc13e3c0d8",
            section_path="I. PLANTEAMIENTO",
            values=values,
        )

        # El SYSTEM_PROMPT es común; el CONTEXTO ADICIONAL debe diferir
        assert prompt_cuant != prompt_cual, (
            "Prompts de enfoques diferentes deben generar contextos distintos"
        )

    def test_maestria_cuant_has_alfa_cronbach(self):
        """El prompt de Maestría Cuant UNAC menciona Alfa de Cronbach."""
        result = self._build_prompt_for_section(
            prompt_id="prompt_29aa7778cc",
            section_path="IV. METODOLOGÍA",
            values={"tema": "Gestión de calidad"},
        )
        assert "Cronbach" in result, (
            "Prompt de maestría cuantitativa debe mencionar Alfa de Cronbach"
        )

    def test_plan_trabajo_uni_has_aportes_tangibles(self):
        """El prompt Plan de Trabajo UNI menciona aportes/patentes."""
        result = self._build_prompt_for_section(
            prompt_id="prompt_6bc6fb0e9f",
            section_path="IV. BENEFICIARIOS",
            values={"tema": "Robots agrícolas"},
        )
        text_lower = result.lower()
        assert "patente" in text_lower or "tangible" in text_lower or (
            "prototipo" in text_lower
        ), "Prompt Plan UNI debe mencionar aportes tangibles"

    def test_posgrado_uni_has_capitulos(self):
        """El prompt de Posgrado UNI menciona capítulos."""
        result = self._build_prompt_for_section(
            prompt_id="prompt_45c88af464",
            section_path="CAPÍTULO I. PROTOCOLO",
            values={"tema": "Semiconductores"},
        )
        text_lower = result.lower()
        assert "capítulo" in text_lower or "maestro" in text_lower or (
            "posgrado" in text_lower or "doctor" in text_lower
        ), "Prompt Posgrado UNI debe mencionar capítulos o grado"

    def test_proyecto_cuant_has_matriz_consistencia(self):
        """El prompt Proyecto Cuant UNAC menciona matriz de consistencia."""
        result = self._build_prompt_for_section(
            prompt_id="prompt_9f0764d149",
            section_path="III. HIPÓTESIS Y VARIABLES",
            values={"tema": "Lean Manufacturing"},
        )
        assert "consistencia" in result.lower() or "operacionalización" in result.lower(), (
            "Prompt Proyecto Cuant debe mencionar matriz de consistencia u operacionalización"
        )

    def test_proyecto_cual_has_categorias_aprioristicas(self):
        """El prompt Proyecto Cual UNAC menciona Categorías Apriorísticas."""
        result = self._build_prompt_for_section(
            prompt_id="prompt_c90ea886b7",
            section_path="III. METODOLOGÍA",
            values={"tema": "Clima organizacional"},
        )
        text_lower = result.lower()
        assert "apriorística" in text_lower or "categoría" in text_lower or (
            "fenomenológico" in text_lower
        ), "Prompt Proyecto Cual debe mencionar categorías apriorísticas"


# ===================================================================== #
#  6. PROMPT LLEGA AL LLM – mock de generate_with_provider_fallback     #
# ===================================================================== #
class TestPromptReachesLLM:
    """Verifica que el prompt renderizado LLEGA al proveedor de IA."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.service = PromptService(path=str(PROMPTS_JSON))
        self.renderer = PromptRenderer()

    def test_full_pipeline_prompt_delivered(self):
        """Simula el pipeline generate() y verifica que el prompt llega."""
        # 1. Cargar prompt
        prompt_data = self.service.get_prompt("prompt_29aa7778cc")
        assert prompt_data is not None

        # 2. Simular variables del proyecto
        project = {
            "id": "proj_test_001",
            "title": "Optimización de procesos con Six Sigma",
            "variables": {
                "tema": "Six Sigma en manufactura",
                "objetivo_general": "Reducir defectos en línea de producción",
                "diagnostico_local": "Planta Callao",
                "herramienta_ingenieria": "Diagrama de Ishikawa",
            },
        }

        # 3. Renderizar template (como lo hace generate())
        template_text = prompt_data.get("template", "")
        values = project["variables"]
        base_prompt = self.renderer.render(template_text, values)

        # Verificar renderizado
        assert "Six Sigma en manufactura" in base_prompt or "{{tema}}" not in base_prompt

        # 4. Construir prompt final por sección (como lo hace _generate_sections)
        project_values = dict(values)
        project_values["title"] = project["title"]

        final_prompt = self.renderer.build_section_prompt(
            base_prompt=base_prompt,
            section_path="II. MARCO TEÓRICO/2.1 Antecedentes",
            section_id="sec-0012",
            values=project_values,
        )

        # 5. Verificar que el prompt final contiene TODO lo necesario
        assert "Eres un redactor academico profesional" in final_prompt
        assert "II. MARCO TEÓRICO/2.1 Antecedentes" in final_prompt
        assert "CONTEXTO ADICIONAL DEL PROYECTO" in final_prompt
        assert "Optimización de procesos con Six Sigma" in final_prompt
        assert "REGLAS OBLIGATORIAS" in final_prompt

        # 6. Simular envío al LLM (el prompt NO está vacío)
        assert len(final_prompt) > 500, (
            f"Prompt final muy corto ({len(final_prompt)} chars), "
            "posiblemente algo no se renderizó"
        )

    def test_prompt_structure_for_every_real_prompt(self):
        """Cada prompt real genera un prompt final válido para la IA."""
        all_prompts = self.service.list_prompts()
        for prompt_data in all_prompts:
            pid = prompt_data["id"]
            template = prompt_data.get("template", "")
            if not template:
                continue

            values = {"tema": "Test Tema", "title": "Tesis Test"}
            base_prompt = self.renderer.render(template, values)

            final = self.renderer.build_section_prompt(
                base_prompt=base_prompt,
                section_path="INTRODUCCIÓN",
                section_id="sec-0001",
                values=values,
            )

            # El prompt final debe:
            assert len(final) > 200, f"Prompt {pid}: muy corto ({len(final)} chars)"
            assert "INTRODUCCIÓN" in final, f"Prompt {pid}: sin sección"
            assert "CONTEXTO ADICIONAL" in final or not base_prompt.strip(), (
                f"Prompt {pid}: sin contexto adicional"
            )

    @pytest.mark.parametrize(
        "prompt_id,expected_keyword",
        [
            ("prompt_1936b2172c", "cuantitativo"),
            ("prompt_fc13e3c0d8", "cualitativo"),
            ("prompt_29aa7778cc", "Cronbach"),
            ("prompt_6bc6fb0e9f", "técnico"),
            ("prompt_45c88af464", "Posgrado"),
        ],
    )
    def test_prompt_specific_keywords_reach_llm(self, prompt_id, expected_keyword):
        """El keyword esperado de cada tipo de prompt llega al prompt final."""
        prompt_data = self.service.get_prompt(prompt_id)
        assert prompt_data is not None

        base_prompt = self.renderer.render(
            prompt_data["template"],
            {"tema": "Prueba de integración"},
        )
        final = self.renderer.build_section_prompt(
            base_prompt=base_prompt,
            section_path="I. PLANTEAMIENTO",
            section_id="sec-0001",
            values={"tema": "Prueba"},
        )

        assert expected_keyword.lower() in final.lower(), (
            f"Prompt {prompt_id}: keyword '{expected_keyword}' no llega al LLM. "
            f"Primeros 500 chars del prompt: {final[:500]}"
        )
