"""Derive recommended figure blocks from finalized AI section content.

The AI may return plain text for sections that academically justify a visual
aid. This module adds a single recommended figure placeholder with a specific
title when the section path and generated text make that recommendation useful.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from app.core.services.ai.section_content_policy import (
    allows_recommended_figure,
    normalized_path_segments,
)

_CANONICAL_PLACEHOLDER_PATH = "assets/placeholder_figura.png"
_FIGURE_ID_RE = re.compile(r"[^a-z0-9]+")
_BLANK_LINE_RE = re.compile(r"\n\s*\n")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ])")
_GENERIC_FIGURE_MARKERS = (
    "FIGURA DE EJEMPLO",
    "DIAGRAMA ILUSTRATIVO",
    "ARBOL DE PROBLEMAS",
    "ARQUETIPO GENERICO",
)
_FIGURE_TRIGGER_MARKERS = (
    "ARQUITECTURA",
    "FLUJO",
    "PROCESO",
    "MODELO",
    "MARCO CONCEPTUAL",
    "COMPONENTE",
    "ETAPA",
    "RESULTADO",
    "HALLAZGO",
    "CRONOGRAMA",
    "METODOLOGIA",
)
_PROJECT_TARGET_FORMATS = {
    "unac-proyecto-cuant",
    "unac-proyecto-cual",
    "unac-maestria-cuant",
    "unac-maestria-cual",
}
_PROJECT_PROBLEM_FIGURE_ANCHORS = (
    (
        "figura 1.1",
        "pareto",
        "modos de falla",
        "frecuencia acumulada",
        "pocos vitales",
        "80 %",
        "80%",
    ),
    (
        "figura 1.2",
        "ishikawa",
        "causa-efecto",
        "causa efecto",
        "causa raiz",
        "causa raíz",
        "6m",
    ),
    (
        "figura 1.3",
        "matriz de relevancia",
        "filtrado de alternativas",
        "alternativas de solucion",
        "alternativas de solución",
        "viabilidad tecnica",
        "viabilidad técnica",
    ),
    (
        "figura 1.4",
        "matriz de priorizacion",
        "matriz de priorización",
        "priorizacion de soluciones",
        "priorización de soluciones",
        "puntaje ponderado",
        "criterios ponderados",
    ),
)
_PROJECT_PROBLEM_FIGURE_TITLES = (
    "Diagrama de Pareto de modos de falla en flota CAT 24M",
    "Análisis de Causa-Efecto de Baja Disponibilidad (Ishikawa)",
    "Matriz de Relevancia para el filtrado de alternativas de solución",
    "Matriz de Priorización de soluciones factibles",
)
_PROJECT_PROBLEM_FIGURE_LEADS = (
    (
        "Para ubicar los pocos sistemas o modos de falla que explican la mayor parte de la "
        "indisponibilidad, la realidad problemática debe incorporar el siguiente Pareto."
    ),
    (
        "Luego de identificar los modos predominantes, se debe representar la relación "
        "causa-efecto de la baja disponibilidad mediante el siguiente Ishikawa."
    ),
    (
        "Con las causas raíz identificadas, se comparan las alternativas de solución mediante "
        "la siguiente matriz de relevancia."
    ),
    (
        "Finalmente, las alternativas factibles se ordenan con una matriz de priorización para "
        "justificar la selección de la solución desarrollada."
    ),
)


def _normalize_token(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    ascii_only = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_only.split())


def _paragraph_blocks_from_text(text: str) -> list[dict[str, str]]:
    paragraphs = [
        part.strip()
        for part in _BLANK_LINE_RE.split(text.replace("\r\n", "\n").replace("\r", "\n"))
        if part and part.strip()
    ]
    return [{"tipo": "parrafo", "texto": paragraph} for paragraph in paragraphs]


def _content_to_blocks(content: Any) -> list[dict[str, Any]]:
    if isinstance(content, str):
        return _paragraph_blocks_from_text(content)
    if not isinstance(content, list):
        return []

    blocks: list[dict[str, Any]] = []
    for item in content:
        if isinstance(item, str):
            blocks.extend(_paragraph_blocks_from_text(item))
            continue
        if isinstance(item, dict):
            blocks.append(dict(item))
    return blocks


def _visible_text(content: Any) -> str:
    parts: list[str] = []
    if isinstance(content, str):
        return re.sub(r"\s+", " ", content).strip()

    for block in _content_to_blocks(content):
        block_type = _normalize_token(block.get("tipo"))
        if block_type == "parrafo":
            text = str(block.get("texto") or "").strip()
            if text:
                parts.append(text)
        elif block_type == "figura":
            text = str(block.get("titulo") or block.get("caption") or "").strip()
            if text:
                parts.append(text)
        elif block_type == "tabla":
            text = str(block.get("titulo") or "").strip()
            if text:
                parts.append(text)
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


def _is_generic_figure(block: dict[str, Any]) -> bool:
    caption = _normalize_token(block.get("caption"))
    title = _normalize_token(block.get("titulo"))
    if not caption and not title:
        return True
    return any(marker.lower() in f"{caption} {title}" for marker in _GENERIC_FIGURE_MARKERS)


def _subject(values: dict[str, Any] | None) -> str:
    if not isinstance(values, dict):
        return "el estudio desarrollado"
    for key in ("tema", "title", "project_title", "projectTitle", "objetivo_general"):
        raw = values.get(key)
        text = str(raw or "").strip()
        if text:
            return text
    return "el estudio desarrollado"


def _slugify_figure_id(section_id: str, path: str) -> str:
    base = _normalize_token(section_id or path or "figura")
    slug = _FIGURE_ID_RE.sub("_", base).strip("_")
    return f"fig_{slug or 'sugerida'}"


def _text_has_figure_triggers(text: str) -> bool:
    normalized = _normalize_token(text).upper()
    return any(marker in normalized for marker in _FIGURE_TRIGGER_MARKERS)


def _path_requires_recommended_figure(path: str, content_text: str) -> bool:
    if not allows_recommended_figure(path):
        return False
    if len(content_text) < 80:
        return False

    joined = " / ".join(normalized_path_segments(path))
    strong_markers = (
        "MARCO CONCEPTUAL",
        "METODOLOGIA",
        "DISENO METODOLOGICO",
        "PROCEDIMIENTO",
        "RESULTADOS",
        "DISCUSION",
        "CRONOGRAMA",
        "FLUJO",
    )
    if any(marker in joined for marker in strong_markers):
        return True

    theoretical_markers = ("MARCO TEORICO", "BASES TEORICAS")
    return any(marker in joined for marker in theoretical_markers) and _text_has_figure_triggers(content_text)


def _is_project_target_format(format_id: str | None) -> bool:
    return _normalize_token(format_id) in _PROJECT_TARGET_FORMATS


def _is_reality_problem_path(path: str) -> bool:
    joined = " / ".join(normalized_path_segments(path))
    return "PLANTEAMIENTO DEL PROBLEMA" in joined and "REALIDAD PROBLEMATICA" in joined


def _project_problem_figure_blocks(section_id: str, path: str) -> list[dict[str, Any]]:
    notes = (
        (
            "Elaborar el Diagrama de Pareto a partir del historial de fallas de la flota CAT 24M. En una "
            "hoja de cálculo, registrar los sistemas o modos de falla en columnas: sistema, frecuencia de "
            "eventos, porcentaje individual y porcentaje acumulado. Ordenar de mayor a menor frecuencia, "
            "graficar barras para la frecuencia o porcentaje individual, agregar una línea acumulada en eje "
            "secundario y trazar la referencia del 80 %. La figura debe permitir identificar los pocos "
            "vitales que explican la mayor indisponibilidad y justificar por qué esos sistemas se analizan "
            "con prioridad en el proyecto."
        ),
        (
            "Elaborar el Ishikawa colocando como efecto principal la baja disponibilidad inherente de la "
            "flota CAT 24M. Dibujar la espina central y seis ramas 6M: Métodos, Medición, Mano de Obra, "
            "Medio Ambiente, Maquinaria y Materiales. En cada rama incorporar al menos dos subcausas "
            "técnicas derivadas del diagnóstico, por ejemplo mantenimiento rígido por horas, ausencia de "
            "monitoreo, desgaste por abrasividad, estrés térmico, capacitación insuficiente o repuestos "
            "críticos. La figura debe cerrar con una lectura causal que explique qué causa raíz será "
            "atacada por el plan RCM."
        ),
        (
            "Construir la Matriz de Relevancia con una fila por alternativa de solución y columnas de "
            "criterio: viabilidad técnica, viabilidad económica y alineamiento con la causa raíz. Incluir "
            "como mínimo una alternativa descartada por alto costo o bajo impacto, una alternativa logística "
            "de contención y el plan RCM como alternativa estructural. Marcar la decisión final de cada "
            "opción como descartada o preseleccionada, explicando por qué el RCM modifica el método de "
            "mantenimiento y no solo reduce tiempos de reparación."
        ),
        (
            "Elaborar la Matriz de Priorización con las alternativas factibles preseleccionadas. Definir "
            "criterios ponderados, por ejemplo impacto en disponibilidad, costo de implementación y tiempo "
            "de implementación; asignar pesos porcentuales, puntajes de 1 a 10 y calcular el total "
            "ponderado de cada alternativa. La figura debe mostrar que la alternativa con mayor puntaje es "
            "la que se desarrolla en el proyecto. Usar la nota: Escala: 1 (Desfavorable) a 10 (Favorable)."
        ),
    )
    blocks: list[dict[str, Any]] = []
    for index, (title, note) in enumerate(zip(_PROJECT_PROBLEM_FIGURE_TITLES, notes, strict=True), start=1):
        blocks.append(
            {
                "tipo": "figura",
                "id": f"{_slugify_figure_id(section_id, path)}_{index}",
                "titulo": title,
                "caption": title,
                "ruta_placeholder": _CANONICAL_PLACEHOLDER_PATH,
                "placeholder_text": "Figura pendiente de elaboración propia",
                "nota": _augment_project_problem_figure_note(index, note),
                "fuente": "Elaboración propia.",
            }
        )
    return blocks


def _augment_project_problem_figure_note(index: int, note: str) -> str:
    extra_details = {
        1: (
            " Ademas, precisa que la tabla base debe salir del historial de fallas depurado; "
            "cada fila debe representar un sistema o modo de falla homogeneo. El usuario debe verificar "
            "que no existan categorias duplicadas, calcular el porcentaje individual sobre el total de eventos "
            "y luego el porcentaje acumulado. La guia debe indicar con claridad el eje X, el eje Y izquierdo "
            "y el eje Y derecho con porcentaje acumulado. La lectura final debe explicar por que los sistemas "
            "ubicados antes del cruce con el 80 % se consideran prioritarios para el proyecto."
        ),
        2: (
            " Tambien debe indicarse que cada rama 6M debe contener subcausas concretas, escritas como factores "
            "observables o tecnicos y no como frases vagas. El problema central debe ubicarse en la cabeza del pez. "
            "La interpretacion debe cerrar senalando cual rama concentra la causa raiz dominante y por que eso obliga "
            "a pasar de un mantenimiento reactivo o rigido a un enfoque RCM."
        ),
        3: (
            " La guia debe dejar claro que la matriz no solo compara opciones, sino que filtra cuales merecen "
            "pasar a la evaluacion final. Por eso debe mostrarse una alternativa descartada, otra de contencion "
            "y la alternativa estructural, explicando visualmente la decision en una columna final."
        ),
        4: (
            " La explicacion debe pedir que el usuario muestre el peso porcentual de cada criterio, el puntaje "
            "asignado a cada alternativa, el producto peso por puntaje y el total ponderado. La conclusion de la "
            "figura debe redactarse como validacion cuantitativa de la alternativa elegida."
        ),
    }
    return f"{note}{extra_details.get(index, '')}"


def _is_project_problem_figure(block: dict[str, Any]) -> bool:
    if _normalize_token(block.get("tipo")) != "figura":
        return False
    figure_title = _normalize_token(block.get("titulo") or block.get("caption"))
    return any(_normalize_token(title) == figure_title for title in _PROJECT_PROBLEM_FIGURE_TITLES)


def _paragraph_matches_anchor(block: dict[str, Any], anchors: tuple[str, ...]) -> bool:
    if _normalize_token(block.get("tipo")) != "parrafo":
        return False
    text = _normalize_token(block.get("texto"))
    return any(_normalize_token(anchor) in text for anchor in anchors)


def _paragraph_has_any_project_anchor(block: dict[str, Any]) -> bool:
    return any(_paragraph_matches_anchor(block, anchors) for anchors in _PROJECT_PROBLEM_FIGURE_ANCHORS)


def _split_anchor_paragraphs(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    split_blocks: list[dict[str, Any]] = []
    for block in blocks:
        if _normalize_token(block.get("tipo")) != "parrafo" or not _paragraph_has_any_project_anchor(block):
            split_blocks.append(block)
            continue

        text = str(block.get("texto") or "").strip()
        sentences = [part.strip() for part in _SENTENCE_SPLIT_RE.split(text) if part.strip()]
        if len(sentences) <= 1:
            split_blocks.append(block)
            continue

        split_blocks.extend({"tipo": "parrafo", "texto": sentence} for sentence in sentences)
    return split_blocks


def _fallback_anchor_index(blocks: list[dict[str, Any]], figure_index: int) -> int:
    paragraph_indexes = [
        index for index, block in enumerate(blocks) if _normalize_token(block.get("tipo")) == "parrafo"
    ]
    if not paragraph_indexes:
        return -1
    # If the AI omits explicit figure mentions, still distribute figures near
    # the narrative paragraphs instead of grouping all of them at section end.
    return paragraph_indexes[min(figure_index, len(paragraph_indexes) - 1)]


def _insert_after_index(
    blocks: list[dict[str, Any]],
    anchor_index: int,
    figure_block: dict[str, Any],
    *,
    lead_text: str = "",
) -> None:
    if anchor_index < 0:
        if lead_text:
            blocks.append({"tipo": "parrafo", "texto": lead_text})
        blocks.append(figure_block)
        return
    insert_at = anchor_index + 1
    while insert_at < len(blocks) and _normalize_token(blocks[insert_at].get("tipo")) == "figura":
        insert_at += 1
    if lead_text:
        blocks.insert(insert_at, {"tipo": "parrafo", "texto": lead_text})
        insert_at += 1
    blocks.insert(insert_at, figure_block)


def _ensure_project_problem_figures(section: dict[str, Any]) -> None:
    path = str(section.get("path") or "").strip()
    blocks = _split_anchor_paragraphs(_content_to_blocks(section.get("content")))
    required_blocks = _project_problem_figure_blocks(str(section.get("sectionId") or ""), path)
    # Rebuild controlled project figures so stale generated output cannot leave
    # them appended as a consecutive group at the end of 1.1.
    content_blocks = [block for block in blocks if not _is_project_problem_figure(block)]

    for index, block in enumerate(required_blocks):
        anchor_index = next(
            (
                block_index
                for block_index, content_block in enumerate(content_blocks)
                if _paragraph_matches_anchor(content_block, _PROJECT_PROBLEM_FIGURE_ANCHORS[index])
            ),
            -1,
        )
        if anchor_index < 0:
            anchor_index = _fallback_anchor_index(content_blocks, index)
        has_explicit_anchor = 0 <= anchor_index < len(content_blocks) and _paragraph_matches_anchor(
            content_blocks[anchor_index], _PROJECT_PROBLEM_FIGURE_ANCHORS[index]
        )
        _insert_after_index(
            content_blocks,
            anchor_index,
            block,
            lead_text="" if has_explicit_anchor else _PROJECT_PROBLEM_FIGURE_LEADS[index],
        )

    section["content"] = content_blocks


def _figure_title(path: str, content_text: str, values: dict[str, Any] | None) -> str:
    joined = " / ".join(normalized_path_segments(path))
    subject = _subject(values)
    normalized_text = _normalize_token(content_text).upper()

    if "CRONOGRAMA" in joined:
        return f"Cronograma visual de actividades para {subject}"
    if any(marker in joined for marker in ("METODOLOGIA", "DISENO METODOLOGICO", "PROCEDIMIENTO", "FLUJO")):
        return f"Flujo metodologico del estudio sobre {subject}"
    if "MARCO CONCEPTUAL" in joined:
        return f"Mapa conceptual del estudio sobre {subject}"
    if any(marker in joined for marker in ("MARCO TEORICO", "BASES TEORICAS")):
        if "ARQUITECTURA" in normalized_text or "SISTEMA" in normalized_text:
            return f"Arquitectura conceptual aplicada a {subject}"
        return f"Modelo teorico de referencia para {subject}"
    if "RESULTADOS" in joined:
        return f"Visualizacion comparativa de resultados de {subject}"
    if "DISCUSION" in joined:
        return f"Relacion entre hallazgos y antecedentes sobre {subject}"
    return f"Esquema tecnico de {subject}"


def _build_recommended_figure(section_id: str, path: str, title: str) -> dict[str, Any]:
    return {
        "tipo": "figura",
        "id": _slugify_figure_id(section_id, path),
        "titulo": title,
        "caption": title,
        "ruta_placeholder": _CANONICAL_PLACEHOLDER_PATH,
        "fuente": "Placeholder tecnico controlado. Reemplazar por la figura validada por el autor.",
    }


def apply_figure_recommendations(
    sections: list[dict[str, Any]],
    *,
    values: dict[str, Any] | None = None,
    format_id: str | None = None,
) -> list[dict[str, Any]]:
    """Inject or repair one recommended figure block in eligible sections."""
    for section in sections:
        if not isinstance(section, dict):
            continue

        path = str(section.get("path") or "").strip()
        if not path:
            continue

        if _is_project_target_format(format_id) and _is_reality_problem_path(path):
            _ensure_project_problem_figures(section)
            continue

        current_content = section.get("content")
        content_text = _visible_text(current_content)
        blocks = _content_to_blocks(current_content)

        figure_indexes = [
            index for index, block in enumerate(blocks) if _normalize_token(block.get("tipo")) == "figura"
        ]

        if figure_indexes:
            title = _figure_title(path, content_text, values)
            replacement = _build_recommended_figure(
                str(section.get("sectionId") or ""),
                path,
                title,
            )
            generic_indexes = [index for index in figure_indexes if _is_generic_figure(blocks[index])]
            if generic_indexes:
                blocks[generic_indexes[0]] = replacement
                section["content"] = blocks
            continue

        if not _path_requires_recommended_figure(path, content_text):
            continue

        title = _figure_title(path, content_text, values)
        blocks.append(
            _build_recommended_figure(
                str(section.get("sectionId") or ""),
                path,
                title,
            )
        )
        section["content"] = blocks

    return sections
