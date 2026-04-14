"""
Maestria UNAC - payload normalization and mapping.

Centralizes how Maestria values are represented inside GicaGen so:
- Excel upload and manual form converge to the same structure
- project persistence keeps one canonical shape
- GicaTesis receives stable flat aliases plus structured blocks
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

DEFAULT_FACULTAD = "Facultad de Ingeniería Mecánica y de Energía"
DEFAULT_UNIDAD_INVESTIGACION = "Unidad de Posgrado de la Facultad de Ingeniería Mecánica y de Energía"
DEFAULT_TIPO_DOCUMENTO = "Tesis de Maestría"
DEFAULT_FRASE_GRADO = "PARA OPTAR EL GRADO ACADÉMICO DE MAESTRO EN GERENCIA DE MANTENIMIENTO"


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"none", "null", "nan", "undefined"} else text


def _pick_text(*values: Any) -> str:
    for value in values:
        text = _clean_text(value)
        if text:
            return text
    return ""


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _clean_string_list(values: Any) -> list[str]:
    if isinstance(values, str):
        items = [item.strip() for item in values.replace("\r", "\n").split("\n")]
    elif isinstance(values, list):
        items = [_clean_text(item) for item in values]
    else:
        return []

    normalized: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = _clean_text(item)
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(text)
    return normalized


def _normalize_abbreviations(raw: Any) -> list[dict[str, str]]:
    items = raw if isinstance(raw, list) else []
    normalized: list[dict[str, str]] = []
    for item in items:
        data = _as_dict(item)
        sigla = _pick_text(data.get("sigla"), data.get("abbr"), data.get("abreviatura"))
        significado = _pick_text(
            data.get("significado"),
            data.get("descripcion"),
            data.get("description"),
            data.get("meaning"),
        )
        if not sigla and not significado:
            continue
        normalized.append(
            {
                "sigla": sigla,
                "significado": significado,
            }
        )
    return normalized


def _normalize_matriz_consistencia(raw: Any, root: dict[str, Any]) -> dict[str, Any]:
    data = _as_dict(raw)
    problemas = _as_dict(data.get("problemas"))
    objetivos = _as_dict(data.get("objetivos"))
    hipotesis = _as_dict(data.get("hipotesis"))
    variables = _as_dict(data.get("variables"))
    variable_independiente = _as_dict(variables.get("independiente"))
    variable_dependiente = _as_dict(variables.get("dependiente"))
    metodologia = _as_dict(data.get("metodologia"))

    return {
        "problema_general": _pick_text(data.get("problema_general"), problemas.get("general")),
        "objetivo_general": _pick_text(data.get("objetivo_general"), objetivos.get("general")),
        "hipotesis_general": _pick_text(data.get("hipotesis_general"), hipotesis.get("general")),
        "variable_independiente": _pick_text(
            data.get("variable_independiente"),
            variable_independiente.get("nombre"),
            root.get("variable_independiente"),
            root.get("vi"),
        ),
        "dimensiones_variable_independiente": _clean_string_list(
            data.get("dimensiones_variable_independiente")
            or variable_independiente.get("dimensiones")
        ),
        "problemas_especificos": _clean_string_list(
            data.get("problemas_especificos") or problemas.get("especificos")
        ),
        "objetivos_especificos": _clean_string_list(
            data.get("objetivos_especificos") or objetivos.get("especificos")
        ),
        "hipotesis_especificas": _clean_string_list(
            data.get("hipotesis_especificas") or hipotesis.get("especificos")
        ),
        "variable_dependiente": _pick_text(
            data.get("variable_dependiente"),
            variable_dependiente.get("nombre"),
            root.get("variable_dependiente"),
            root.get("vd"),
        ),
        "dimensiones_variable_dependiente": _clean_string_list(
            data.get("dimensiones_variable_dependiente")
            or variable_dependiente.get("dimensiones")
        ),
        "tipo_investigacion": _pick_text(
            data.get("tipo_investigacion"),
            metodologia.get("tipo"),
            root.get("tipo"),
        ),
        "nivel_investigacion": _pick_text(
            data.get("nivel_investigacion"),
            metodologia.get("nivel"),
            root.get("nivel_investigacion"),
        ),
        "enfoque_investigacion": _pick_text(
            data.get("enfoque_investigacion"),
            metodologia.get("enfoque"),
            root.get("enfoque"),
        ),
        "diseno": _pick_text(
            data.get("diseno"),
            metodologia.get("diseño"),
            metodologia.get("diseno"),
            root.get("diseno_investigacion"),
        ),
        "poblacion": _pick_text(
            data.get("poblacion"),
            metodologia.get("poblacion"),
            root.get("poblacion"),
        ),
        "muestra": _pick_text(
            data.get("muestra"),
            metodologia.get("muestra"),
            root.get("muestra"),
        ),
        "tecnicas": _pick_text(data.get("tecnicas"), metodologia.get("tecnicas")),
        "instrumentos": _pick_text(data.get("instrumentos"), metodologia.get("instrumentos")),
        "procesamiento_datos": _pick_text(
            data.get("procesamiento_datos"),
            metodologia.get("procesamiento_datos"),
        ),
    }


def _normalize_operationalization_row(raw: Any) -> dict[str, str]:
    data = _as_dict(raw)
    row = {
        "dimension": _pick_text(data.get("dimension")),
        "indicador": _pick_text(data.get("indicador")),
        "indice": _pick_text(data.get("indice")),
        "metodo_tecnica": _pick_text(data.get("metodo_tecnica"), data.get("metodoTecnica")),
        "tecnica_instrumentos": _pick_text(
            data.get("tecnica_instrumentos"),
            data.get("tecnicaInstrumentos"),
        ),
    }
    if not any(row.values()):
        return {}
    return row


def _normalize_operationalization(raw: Any, *, fallback_variable: str = "") -> dict[str, Any]:
    data = _as_dict(raw)
    rows = data.get("filas") if isinstance(data.get("filas"), list) else data.get("rows")
    normalized_rows = [
        row
        for row in (_normalize_operationalization_row(item) for item in (rows if isinstance(rows, list) else []))
        if row
    ]
    return {
        "variable": _pick_text(data.get("variable"), fallback_variable),
        "definicion_conceptual": _pick_text(
            data.get("definicion_conceptual"),
            data.get("definicionConceptual"),
        ),
        "definicion_operacional": _pick_text(
            data.get("definicion_operacional"),
            data.get("definicionOperacional"),
        ),
        "filas": normalized_rows,
    }


def normalize_maestria_details(raw_values: dict[str, Any] | None) -> dict[str, Any]:
    """
    Return the canonical Maestria structure used by Excel, manual form,
    persistence, AI context and render payloads.
    """
    values = deepcopy(raw_values or {})
    temas_ocde = _clean_string_list(
        values.get("tema_ocde")
        or [
            values.get("tema_ocde_1"),
            values.get("tema_ocde_2"),
            values.get("tema_ocde_3"),
        ]
    )
    details = {
        "titulo": _pick_text(values.get("titulo"), values.get("title"), values.get("tema")),
        "linea_investigacion": _pick_text(values.get("linea_investigacion")),
        "anio": _pick_text(values.get("anio")),
        "lugar_caratula": _pick_text(values.get("lugar_caratula")),
        "autor1_nombres": _pick_text(values.get("autor1_nombres")),
        "autor1_dni": _pick_text(values.get("autor1_dni")),
        "autor1_orcid": _pick_text(values.get("autor1_orcid")),
        "autor2_nombres": _pick_text(values.get("autor2_nombres")),
        "autor2_dni": _pick_text(values.get("autor2_dni")),
        "autor2_orcid": _pick_text(values.get("autor2_orcid")),
        "asesor_nombres": _pick_text(values.get("asesor_nombres")),
        "asesor_dni": _pick_text(values.get("asesor_dni")),
        "asesor_orcid": _pick_text(values.get("asesor_orcid")),
        "coasesor_nombres": _pick_text(values.get("coasesor_nombres")),
        "coasesor_dni": _pick_text(values.get("coasesor_dni")),
        "coasesor_orcid": _pick_text(values.get("coasesor_orcid")),
        "objeto_estudio": _pick_text(values.get("objeto_estudio")),
        "variable_independiente": _pick_text(values.get("variable_independiente"), values.get("vi")),
        "variable_dependiente": _pick_text(values.get("variable_dependiente"), values.get("vd")),
        "lugar_ejecucion": _pick_text(values.get("lugar_ejecucion")),
        "unidad_analisis": _pick_text(values.get("unidad_analisis")),
        "tipo": _pick_text(values.get("tipo")),
        "enfoque": _pick_text(values.get("enfoque")),
        "diseno_investigacion": _pick_text(values.get("diseno_investigacion")),
        "nivel_investigacion": _pick_text(values.get("nivel_investigacion")),
        "poblacion": _pick_text(values.get("poblacion")),
        "muestra": _pick_text(values.get("muestra")),
        "lugar": _pick_text(values.get("lugar")),
        "temporal": _pick_text(values.get("temporal")),
        "tema_ocde_1": temas_ocde[0] if len(temas_ocde) > 0 else "",
        "tema_ocde_2": temas_ocde[1] if len(temas_ocde) > 1 else "",
        "tema_ocde_3": temas_ocde[2] if len(temas_ocde) > 2 else "",
        "facultad": _pick_text(values.get("facultad")) or DEFAULT_FACULTAD,
        "unidad_investigacion": _pick_text(values.get("unidad_investigacion")) or DEFAULT_UNIDAD_INVESTIGACION,
        "abreviaturas": _normalize_abbreviations(values.get("abreviaturas")),
    }

    details["matriz_consistencia"] = _normalize_matriz_consistencia(
        values.get("matriz_consistencia") or values.get("matrizConsistencia"),
        details,
    )
    details["operacionalizacion_vd"] = _normalize_operationalization(
        values.get("operacionalizacion_vd") or values.get("operacionalizacionVD"),
        fallback_variable=details["variable_dependiente"],
    )
    details["operacionalizacion_vi"] = _normalize_operationalization(
        values.get("operacionalizacion_vi") or values.get("operacionalizacionVI"),
        fallback_variable=details["variable_independiente"],
    )
    return details


def map_maestria_values(raw_values: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize and map wizard values for GicaTesis maestria format.

    Returns:
    - canonical flat aliases used by the rest of GicaGen
    - structured blocks for matrix, operationalization and abbreviations
    """
    details = normalize_maestria_details(raw_values)
    titulo = details["titulo"]
    tema_ocde = _clean_string_list(
        [details.get("tema_ocde_1"), details.get("tema_ocde_2"), details.get("tema_ocde_3")]
    )
    matriz = details["matriz_consistencia"]
    operacionalizacion_vd = details["operacionalizacion_vd"]
    operacionalizacion_vi = details["operacionalizacion_vi"]
    abreviaturas = details["abreviaturas"]

    mapped: dict[str, Any] = {
        "titulo": titulo,
        "title": titulo,
        "tema": titulo,
        "linea_investigacion": details["linea_investigacion"],
        "anio": details["anio"],
        "lugar_caratula": details["lugar_caratula"],
        "autor1_nombres": details["autor1_nombres"],
        "autor1_dni": details["autor1_dni"],
        "autor1_orcid": details["autor1_orcid"],
        "autor2_nombres": details["autor2_nombres"],
        "autor2_dni": details["autor2_dni"],
        "autor2_orcid": details["autor2_orcid"],
        "asesor_nombres": details["asesor_nombres"],
        "asesor_dni": details["asesor_dni"],
        "asesor_orcid": details["asesor_orcid"],
        "coasesor_nombres": details["coasesor_nombres"],
        "coasesor_dni": details["coasesor_dni"],
        "coasesor_orcid": details["coasesor_orcid"],
        "lugar_ejecucion": details["lugar_ejecucion"],
        "unidad_analisis": details["unidad_analisis"],
        "tipo": details["tipo"],
        "enfoque": details["enfoque"],
        "diseno_investigacion": details["diseno_investigacion"],
        "nivel_investigacion": details["nivel_investigacion"],
        "variable_independiente": details["variable_independiente"],
        "variable_dependiente": details["variable_dependiente"],
        "vi": details["variable_independiente"],
        "vd": details["variable_dependiente"],
        "objeto_estudio": details["objeto_estudio"],
        "poblacion": details["poblacion"],
        "muestra": details["muestra"],
        "lugar": details["lugar"],
        "temporal": details["temporal"],
        "tema_ocde_1": details["tema_ocde_1"],
        "tema_ocde_2": details["tema_ocde_2"],
        "tema_ocde_3": details["tema_ocde_3"],
        "tema_ocde": tema_ocde,
        "facultad": details["facultad"],
        "unidad_investigacion": details["unidad_investigacion"],
        "escuela": "",
        "tipo_documento": DEFAULT_TIPO_DOCUMENTO,
        "frase_grado": DEFAULT_FRASE_GRADO,
        "abreviaturas": abreviaturas,
        "matriz_consistencia": matriz,
        "operacionalizacion_vd": operacionalizacion_vd,
        "operacionalizacion_vi": operacionalizacion_vi,
        # Flat aliases useful for prompts / render context.
        "problema_general": matriz["problema_general"],
        "objetivo_general": matriz["objetivo_general"],
        "hipotesis_general": matriz["hipotesis_general"],
        "problemas_especificos": matriz["problemas_especificos"],
        "objetivos_especificos": matriz["objetivos_especificos"],
        "hipotesis_especificas": matriz["hipotesis_especificas"],
        "dimensiones_variable_independiente": matriz["dimensiones_variable_independiente"],
        "dimensiones_variable_dependiente": matriz["dimensiones_variable_dependiente"],
        "matriz_tipo_investigacion": matriz["tipo_investigacion"],
        "matriz_nivel_investigacion": matriz["nivel_investigacion"],
        "matriz_enfoque_investigacion": matriz["enfoque_investigacion"],
        "matriz_diseno": matriz["diseno"],
        "matriz_poblacion": matriz["poblacion"],
        "matriz_muestra": matriz["muestra"],
        "matriz_tecnicas": matriz["tecnicas"],
        "matriz_instrumentos": matriz["instrumentos"],
        "matriz_procesamiento_datos": matriz["procesamiento_datos"],
    }

    return {
        key: value
        for key, value in mapped.items()
        if value not in ("", None, [], {})
    }


def is_maestria_format(format_obj: dict[str, Any] | None) -> bool:
    """Return True when the format corresponds to Maestria/Posgrado."""
    if not isinstance(format_obj, dict):
        return False

    category = str(format_obj.get("category", "")).lower().strip()
    if category in {"maestria", "posgrado", "postgrado"}:
        return True

    format_id = str(format_obj.get("format_id") or format_obj.get("id") or "").lower().strip()
    return "maestria" in format_id
