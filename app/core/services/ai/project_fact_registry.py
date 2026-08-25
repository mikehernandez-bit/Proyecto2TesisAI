"""Closed fact registry used by UNAC V2 prompts and validation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.core.services.maestria_payload_mapper import normalize_maestria_details


@dataclass(frozen=True)
class ProjectFactRegistry:
    facts: dict[str, Any]

    def prompt_contract(self) -> str:
        populated = {key: value for key, value in self.facts.items() if value not in (None, "", [], {})}
        return (
            "REGISTRO CERRADO DE HECHOS DEL PROYECTO:\n"
            + json.dumps(populated, ensure_ascii=False, sort_keys=True)
            + "\nToda cifra, ubicación, equipo, método, instrumento, población, muestra o periodo "
            "que no figure aquí está prohibido como hecho del proyecto. No inventes porcentajes de mejora, "
            "resultados, Monte Carlo, sensores IoT ni tecnologías no registradas."
        )


def build_project_fact_registry(values: dict[str, Any] | None) -> ProjectFactRegistry:
    details = normalize_maestria_details(values or {})
    matrix = details.get("matriz_consistencia") if isinstance(details.get("matriz_consistencia"), dict) else {}
    facts = {
        "titulo": details.get("titulo"),
        "objeto_estudio": details.get("objeto_estudio"),
        "variable_independiente": details.get("variable_independiente"),
        "variable_dependiente": details.get("variable_dependiente"),
        "dimensiones_variable_independiente": matrix.get("dimensiones_variable_independiente"),
        "dimensiones_variable_dependiente": matrix.get("dimensiones_variable_dependiente"),
        "problema_general": matrix.get("problema_general"),
        "objetivo_general": matrix.get("objetivo_general"),
        "hipotesis_general": matrix.get("hipotesis_general"),
        "tipo_investigacion": details.get("tipo") or matrix.get("tipo_investigacion"),
        "enfoque": details.get("enfoque") or matrix.get("enfoque_investigacion"),
        "nivel": details.get("nivel_investigacion") or matrix.get("nivel_investigacion"),
        "diseno": details.get("diseno_investigacion") or matrix.get("diseno"),
        "poblacion": details.get("poblacion") or matrix.get("poblacion"),
        "muestra": details.get("muestra") or matrix.get("muestra"),
        "lugar": details.get("lugar_ejecucion") or details.get("lugar"),
        "periodo": details.get("temporal") or details.get("periodo"),
        "tecnicas": matrix.get("tecnicas"),
        "instrumentos": matrix.get("instrumentos"),
        "procesamiento_datos": matrix.get("procesamiento_datos"),
    }
    return ProjectFactRegistry(facts=facts)
