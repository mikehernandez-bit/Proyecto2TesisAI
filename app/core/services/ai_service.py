"""
Servicio de IA con Google Gemini (Nuevo SDK google-genai)
Usa Structured Outputs (Pydantic) para garantizar JSON 100% válido y sin errores de comillas.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from pydantic import BaseModel
from google import genai
from google.genai import types

from app.core.config import settings

logger = logging.getLogger(__name__)

# 1. Definimos la estructura ESTRICTA que Gemini debe devolver.
# Esto evita que rompa el JSON con comillas sueltas.
class AISectionOutput(BaseModel):
    sectionId: str
    path: str
    content: str

class AIResultOutput(BaseModel):
    sections: list[AISectionOutput]


class GeminiService:
    def __init__(self):
        self.api_key = settings.GEMINI_API_KEY
        self.client = None
        if self.api_key:
            self.client = genai.Client(api_key=self.api_key)
            self.model_id = 'gemini-2.5-flash' 

    async def generate_document_content(
        self, 
        prompt_template: str, 
        variables: Dict[str, Any], 
        section_index: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        
        if not self.client:
            raise ValueError("GEMINI_API_KEY no está configurada en el archivo .env")

        # 2. Reemplazar variables en el prompt
        prompt_final = prompt_template
        for key, val in variables.items():
            prompt_final = prompt_final.replace(f"{{{{{key}}}}}", str(val))
            prompt_final = prompt_final.replace(f"{{{key}}}", str(val))

        # Extraemos las secciones que necesitamos
        secciones_esperadas = [{"sectionId": s["sectionId"], "path": s["path"]} for s in section_index]
        
        # 3. Instrucción mejorada (Texto Plano sin HTML)
        instruccion_sistema = f"""
Actúa como un experto académico e investigador. 
Tu tarea es generar el contenido para un documento basado en el siguiente prompt del usuario:
---
{prompt_final}
---

INSTRUCCIONES CRÍTICAS PARA EL FORMATO:
- Debes generar el "content" (contenido) para CADA UNA de las secciones listadas abajo.
- El contenido debe ser ESTRICTAMENTE TEXTO PLANO (Plain Text).
- PROHIBIDO USAR ETIQUETAS HTML. NO uses <p>, <h1>, <ul>, <br>, ni ninguna otra.
- Usa saltos de línea normales (\\n) para separar los párrafos.
- Para hacer listas, usa simples guiones (- ).
- Usa ortografía normal con tildes (escribe "Introducción", NO uses códigos como "Introducci&oacute;n").

Secciones a rellenar:
{json.dumps(secciones_esperadas, indent=2)}
"""
        logger.info("Enviando petición a Gemini (Structured Output Mode)...")
        
        try:
            # 4. Llamar a Gemini inyectando el esquema (response_schema)
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=instruccion_sistema,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=AIResultOutput, # ¡Esta es la magia que arregla el JSON!
                    temperature=0.7,
                )
            )
            
            # 5. Parseo y limpieza
            raw_text = response.text.strip()
            
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:]
            elif raw_text.startswith("```"):
                raw_text = raw_text[3:]
                
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]
                
            raw_text = raw_text.strip()
            
            # strict=False ayuda con caracteres invisibles de control
            resultado_json = json.loads(raw_text, strict=False)
            
            return resultado_json
            
        except Exception as e:
            logger.error(f"Error generando contenido con Gemini: {e}")
            raise RuntimeError(f"El texto de la IA fue demasiado largo o mal formado: {str(e)}")

# Instancia global
ai_service = GeminiService()