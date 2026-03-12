# app/core/services/ai/validator.py
from typing import Any, Dict, List

def validate_thesis_quality(ai_result: Dict[str, Any], section_index: List[Dict[str, Any]], format_id: str) -> tuple[bool, List[str]]:
    """
    Evalúa las reglas de longitud, completitud y títulos.
    Retorna un booleano (is_valid) y una lista de evidencias (textos para logs).
    """
    evidencias = []
    is_valid = True

    secciones_generadas = ai_result.get("sections", [])
    rutas_generadas = {sec.get("path", ""): sec.get("content", "") for sec in secciones_generadas}

    evidencias.append(f"🔎 Validando formato {format_id} ({len(section_index)} títulos esperados)")

    for esperado in section_index:
        path = esperado.get("path", "")
        if not path:
            continue

        # 1. Validación de Títulos faltantes (Estructura UNAC/UNI)
        if path not in rutas_generadas:
            evidencias.append(f"❌ TÍTULO FALTANTE: Se omitió la sección '{path}'.")
            is_valid = False
        else:
            contenido = rutas_generadas[path].strip()
            palabras = len(contenido.split())

            # 2. Reglas de Longitud (Tokens/Palabras)
            # Se requiere un mínimo de palabras para considerar que no es una alucinación vacía
            if palabras < 30: 
                evidencias.append(f"⚠️ LONGITUD: '{path}' es demasiado corta ({palabras} palabras).")
                is_valid = False
            else:
                evidencias.append(f"✅ LONGITUD: '{path}' cumple el mínimo ({palabras} palabras).")

            # 3. Completitud (Cortes abruptos de la IA)
            if contenido.endswith(",") or contenido.endswith(" y") or contenido.endswith(" el"):
                evidencias.append(f"❌ COMPLETITUD: '{path}' parece estar cortado a la mitad.")
                is_valid = False

    if is_valid:
        evidencias.append("🏆 CALIDAD: El documento superó todas las reglas de calidad.")
    else:
        evidencias.append("⚠️ CALIDAD: El documento presenta observaciones estructurales.")

    return is_valid, evidencias