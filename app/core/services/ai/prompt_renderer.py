"""Prompt template renderer for AI generation.

Renders {{variable}} placeholders in prompt templates and builds
section-specific prompts for AI providers.

The SYSTEM_PROMPT constant enforces strict output rules so responses are
plain-text and ready for Word/PDF assembly.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# Pattern matches {{variable_name}} with optional whitespace inside braces
_PLACEHOLDER_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}")


SYSTEM_PROMPT = (
    "Eres un redactor academico profesional en espanol. "
    "Vas a escribir SOLO el contenido de UNA seccion de un documento de tesis.\n"
    "IMPORTANTE: El formato (titulos, caratula, estilos, saltos de pagina, indices) "
    "lo maneja el Word/PDF. Tu NO debes formatear.\n"
    "\n"
    "DATOS DEL PROYECTO:\n"
    "- Titulo: {{title}}\n"
    "- Tema: {{tema}}\n"
    "- Objetivo general: {{objetivo_general}}\n"
    "- Poblacion: {{poblacion}}\n"
    "- Variable independiente: {{variable_independiente}}\n"
    "\n"
    "SECCION A REDACTAR:\n"
    "- Nombre/Ruta de la seccion: {section_path}\n"
    "- Identificador interno: {section_id}\n"
    "\n"
    "REGLAS OBLIGATORIAS (si no cumples, la salida se considera incorrecta):\n"
    "1) Devuelve SOLO texto plano. NO uses Markdown "
    "(NO **negritas**, NO ###, NO listas con guiones, NO tablas con |).\n"
    "2) NO escribas el titulo de la seccion. El titulo ya lo pone el formato. "
    "Empieza directo con el contenido.\n"
    "3) NO pongas saltos de pagina ni caracteres raros. "
    "No uses ---, ***, ni \\f. No empieces con lineas en blanco.\n"
    "4) Parrafos: usa parrafos normales separados por UNA linea en blanco. "
    "Dentro del parrafo NO metas saltos de linea cada pocas palabras.\n"
    "5) Prohibido inventar INDICES en texto "
    "(nada de tabla de contenido manual ni numeraciones de indice).\n"
    "6) Si la seccion es de indice (INDICE, INDICE DE TABLAS, INDICE DE FIGURAS, "
    "INDICE DE ABREVIATURAS o cualquier ruta que empiece por INDICE/), "
    "responde EXACTAMENTE: <<SKIP_SECTION>>.\n"
    "7) No uses placeholders como FIGURA DE EJEMPLO, TABLA DE EJEMPLO, XXX, "
    "[pendiente], lorem ipsum, TÍTULO DEL PROYECTO.\n"
    "   - Si necesitas referirte a una figura, escribe solo la leyenda en texto:\n"
    "     Figura X. (Descripcion breve). Fuente: Elaboracion propia.\n"
    "8) Manten tono academico, coherente con Peru/Lima si aplica. "
    "Incluye conectores y evita relleno.\n"
    "9) Minimo: 180-250 palabras si es seccion de contenido "
    "(introduccion, problema, marco, metodologia, etc.).\n"
    "10) No uses sangrias raras ni dobles espacios. Usa maximo una linea en blanco entre parrafos.\n"
    "\n"
    "Ahora redacta la seccion {section_path} cumpliendo TODO.\n"
)


class PromptRenderer:
    """Renders prompt templates by replacing {{variable}} placeholders."""

    @staticmethod
    def _clip_preview(text: str, max_chars: int = 480) -> str:
        normalized = " ".join(str(text or "").split())
        if len(normalized) <= max_chars:
            return normalized
        return f"{normalized[: max_chars - 1]}…"

    def render(
        self,
        template: str,
        values: Dict[str, Any],
        trace_hook: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> str:
        """Replace {{variable}} placeholders with values from the dict.

        Missing variables are left as-is (e.g. ``{{missing}}``) with a
        warning logged. This keeps generation resilient to incomplete input.
        """
        if not template:
            return ""

        missing: List[str] = []

        def _replace(match: re.Match) -> str:
            key = match.group(1)
            if key in values and values[key] not in (None, ""):
                return str(values[key])
            missing.append(key)
            return match.group(0)

        result = _PLACEHOLDER_RE.sub(_replace, template)

        if missing:
            logger.warning(
                "PromptRenderer: missing variables %s - kept as placeholders",
                missing,
            )

        if trace_hook is not None:
            try:
                trace_hook(
                    {
                        "step": "prompt.render",
                        "status": "done",
                        "title": "Prompt final armado",
                        "detail": "Se combinaron plantilla y variables del proyecto.",
                        "preview": {
                            "prompt": self._clip_preview(result),
                        },
                        "meta": {
                            "missingVariables": missing,
                        },
                    }
                )
            except Exception:
                logger.debug("PromptRenderer trace hook failed", exc_info=True)
        return result

    def build_section_prompt(
        self,
        base_prompt: str,
        section_path: str,
        section_id: str,
        *,
        extra_context: str = "",
        values: Dict[str, Any] | None = None,
    ) -> str:
        """Build a prompt for generating a single section."""
        rendered_system = self.render(SYSTEM_PROMPT, values or {})
        rendered_system = rendered_system.replace("{section_path}", section_path)
        rendered_system = rendered_system.replace("{section_id}", section_id)

        parts = [rendered_system]

        if base_prompt.strip():
            parts.extend(
                [
                    "",
                    "CONTEXTO ADICIONAL DEL PROYECTO:",
                    base_prompt.strip(),
                ]
            )

        if extra_context:
            parts.extend(["", f"Contexto adicional de la seccion: {extra_context}"])

        return "\n".join(parts)
