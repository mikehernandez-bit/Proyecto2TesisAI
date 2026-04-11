"""
Maestría UNAC — Payload Mapper

Maps wizard project values (flat dict) to the canonical values dict expected
by GicaTesis for the master's thesis format.

This is a single source of truth for variable naming between GicaGen and GicaTesis.
"""

from __future__ import annotations

from typing import Any


def map_maestria_values(raw_values: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize and map wizard values for GicaTesis maestría format.
    Ensures no duplication: each variable has one canonical name.
    """
    v = raw_values or {}

    def _get(key: str, *fallbacks: str) -> str:
        for k in (key, *fallbacks):
            value = str(v.get(k, "") or "").strip()
            # Strict filtering for empty/null placeholders from legacy systems
            if value and value.lower() not in ("none", "null", "nan", "undefined"):
                return value
        return ""

    titulo = _get("titulo", "title", "tema")
    tema_ocde_raw = v.get("tema_ocde") if isinstance(v.get("tema_ocde"), list) else []

    mapped = {
        # Canonical field
        "titulo": titulo,
        "title": titulo,
        "tema": titulo,
        # Datos generales
        "linea_investigacion": _get("linea_investigacion"),
        "anio": "2026",  # Forzado por requerimiento UNAC Maestría
        "lugar_caratula": _get("lugar_caratula", "lugar"),
        # Autor 1
        "autor1_nombres": _get("autor1_nombres"),
        "autor1_dni": _get("autor1_dni"),
        "autor1_orcid": _get("autor1_orcid"),
        # Autor 2
        "autor2_nombres": _get("autor2_nombres"),
        "autor2_dni": _get("autor2_dni"),
        "autor2_orcid": _get("autor2_orcid"),
        # Asesor
        "asesor_nombres": _get("asesor_nombres"),
        "asesor_dni": _get("asesor_dni"),
        "asesor_orcid": _get("asesor_orcid"),
        # Coasesor
        "coasesor_nombres": _get("coasesor_nombres"),
        "coasesor_dni": _get("coasesor_dni"),
        "coasesor_orcid": _get("coasesor_orcid"),
        # Investigación
        "lugar_ejecucion": _get("lugar_ejecucion"),
        "unidad_analisis": _get("unidad_analisis"),
        "tipo": _get("tipo"),
        "enfoque": _get("enfoque"),
        "diseno_investigacion": _get("diseno_investigacion"),
        "nivel_investigacion": _get("nivel_investigacion"),
        "vi": _get("variable_independiente", "vi"),
        "vd": _get("variable_dependiente", "vd"),
        "variable_independiente": _get("variable_independiente", "vi"),
        "variable_dependiente": _get("variable_dependiente", "vd"),
        "objeto_estudio": _get("objeto_estudio"),
        "poblacion": _get("poblacion"),
        "muestra": _get("muestra"),
        "lugar": _get("lugar"),
        "temporal": _get("temporal"),
        # OCDE themes
        "tema_ocde_1": _get("tema_ocde_1") or (tema_ocde_raw[0] if len(tema_ocde_raw) > 0 else ""),
        "tema_ocde_2": _get("tema_ocde_2") or (tema_ocde_raw[1] if len(tema_ocde_raw) > 1 else ""),
        "tema_ocde_3": _get("tema_ocde_3") or (tema_ocde_raw[2] if len(tema_ocde_raw) > 2 else ""),
        # Institutional metadata (UNAC Maestría - FIME)
        "facultad": _get("facultad") or "Facultad de Ingeniería Mecánica y de Energía",
        "unidad_investigacion": _get("unidad_investigacion") or "Unidad de Posgrado de la Facultad de Ingeniería Mecánica y de Energía",
        "escuela": _get("escuela"),
        "tipo_documento": _get("tipo_documento") or "Tesis de Maestría",
        "frase_grado": _get("frase_grado") or "PARA OPTAR EL GRADO ACADÉMICO DE MAESTRO EN CIENCIAS CON MENCIÓN EN GERENCIA DEL MANTENIMIENTO",
    }
    
    # Filter out empty values to avoid overwriting existing better data in merge
    return {k: v for k, v in mapped.items() if v}


def is_maestria_format(format_obj: dict[str, Any] | None) -> bool:
    """
    Check if the given format object corresponds to a UNAC maestría format.

    Args:
        format_obj: The format dict from GicaTesis catalog (format_id, category, university…).

    Returns:
        True if the format is a maestria/posgrado category.
    """
    if not isinstance(format_obj, dict):
        return False
    
    # 1. Direct check via category (from catalog)
    category = str(format_obj.get("category", "")).lower().strip()
    if category in {"maestria", "posgrado"}:
        return True
        
    # 2. Fallback check via format_id (from project object)
    format_id = str(format_obj.get("format_id", "")).lower().strip()
    if format_id.startswith("unac-maestria-"):
        return True
        
    return False
