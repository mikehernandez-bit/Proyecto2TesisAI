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
    is_chapter_four_design_section,
    is_chapter_four_text_only_section,
    is_chapter_three_hypotheses_section,
    is_chapter_three_operationalization_section,
    normalized_path_segments,
)

_CANONICAL_PLACEHOLDER_PATH = "assets/placeholder_figura.png"
_FIGURE_GUIDE_BLUE = "0000FF"
_FIGURE_ID_RE = re.compile(r"[^a-z0-9]+")
_BLANK_LINE_RE = re.compile(r"\n\s*\n")
_THEORETICAL_HEADING_RE = re.compile(r"^\s*2\.2\.(\d+)\s+")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ])")
_STALE_PROJECT_MARKDOWN_FIGURE_RE = re.compile(
    r"(?:^|\n)\s*Figura\s+1\.[1-4]\s*\n\s*[^\n\r]*\s*\n"
    r"\s*\*Fuente:\s*Elaboraci[oó]n propia\.?\*\s*\n"
    r"\s*\*Gu[ií]a t[eé]cnica:.*?\*(?=\s*(?:\n[A-ZÁÉÍÓÚÑ0-9]|$))",
    re.IGNORECASE | re.DOTALL,
)
_STALE_PROJECT_LOOSE_FIGURE_TITLE_PREFIXES = (
    "diagrama de pareto de fallas",
    "diagrama de pareto de modos de falla",
    "diagrama de ishikawa",
    "matriz de relevancia de alternativas",
    "matriz de relevancia para alternativas",
    "matriz de priorizacion de alternativas",
    "matriz de priorizacion de estrategias",
    "matriz de priorizacion de soluciones",
)
_STALE_PROJECT_GUIDE_LINE_PREFIXES = (
    "guia tecnica",
    "para elaborar este diagrama",
    "para elaborar esta matriz",
    "luego, se calcula",
    "luego se calcula",
    "el eje vertical",
    "el eje horizontal",
    "el eje x",
    "el eje y",
    "la linea de pareto",
    "la interseccion",
    "de esta espina",
    "para el caso hidraulico",
    "las relaciones se validan",
    "la matriz se elabora",
    "la matriz utiliza una escala",
    "cada alternativa",
    "el rcm obtiene",
    "el rcm debe destacar",
    "el rcm se posiciona",
)
_GENERIC_FIGURE_MARKERS = (
    "FIGURA DE EJEMPLO",
    "DIAGRAMA ILUSTRATIVO",
    "ARBOL DE PROBLEMAS",
    "ARQUETIPO GENERICO",
    "ARQUITECTURA CONCEPTUAL APLICADA",
    "MAPA CONCEPTUAL DEL ESTUDIO",
    "PLACEHOLDER TECNICO",
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
_PROJECT_PROBLEM_ORDERED_ANCHORS = (
    (
        "diagnostico local",
        "fallas registradas",
        "fallas no programadas",
        "concentracion de fallas",
        "concentran",
        "sistemas principales",
        "modos de falla",
        "pocos vitales",
        "pareto",
        "80/20",
        "80 %",
        "80%",
    ),
    (
        "causa raiz",
        "causas raiz",
        "causa-efecto",
        "ishikawa",
        "metodo",
        "metodos",
        "mantenimiento rigido",
        "mantenimiento reactivo",
        "gestion reactiva",
        "medio ambiente",
        "maquinaria",
        "desgaste acelerado",
    ),
    (
        "matriz de relevancia",
        "alternativas de solucion",
        "alternativas factibles",
        "viabilidad tecnica",
        "viabilidad economica",
        "alineamiento estrategico",
        "descartadas",
        "descartada",
        "preseleccionadas",
        "preseleccionada",
        "medida de contencion",
    ),
    (
        "matriz de priorizacion",
        "priorizacion ponderada",
        "priorizar cuantitativamente",
        "analisis cuantitativo",
        "puntaje global",
        "puntaje ponderado",
        "total ponderado",
        "impacto en la disponibilidad",
        "impacto en disponibilidad",
        "seleccionar la estrategia optima",
    ),
)
_CHAPTER_TWO_SUBTOPIC_ANCHORS = (
    ("proceso del rcm", "siete preguntas", "arbol logico de decision"),
    ("taxonomia", "iso 14224", "niveles taxonomicos"),
    ("amef", "analisis de modos", "numero de prioridad de riesgo", "npr"),
    ("motoniveladora cat 24m", "cat 24m", "c18 acert", "vertedera"),
)
_CHAPTER_TWO_FIGURE_TARGET_HEADINGS = (2, 3, 4, 8)
_CHAPTER_TWO_FIGURES = (
    {
        "tipo": "figura",
        "id": "fig_2_1_proceso_rcm",
        "titulo": "Proceso del RCM",
        "caption": "Figura 2.1 Proceso del RCM",
        "ruta_placeholder": _CANONICAL_PLACEHOLDER_PATH,
        "fuente": "Nota. Adaptado de RCM|Terotecnic Ingenieria.",
        "nota": (
            "Guía para elaborar la figura: Diseña un diagrama de flujo estructurado titulado \"Proceso del RCM\" "
            "que orqueste visualmente el ciclo completo de implementación del Mantenimiento Centrado en Confiabilidad. "
            "El gráfico debe ilustrar claramente las siete preguntas fundamentales de la norma SAE JA1011 distribuidas "
            "en bloques secuenciales: funciones del activo, fallas funcionales, modos de falla principales, efectos "
            "de las fallas, consecuencias de las fallas, tareas proactivas aplicables y acciones a tomar si no hay "
            "tareas eficaces. Utiliza rectángulos para las etapas de análisis, rombos de decisión para la selección "
            "de tareas proactivas y óvalos para el inicio y fin del proceso. Conecta todos los elementos con líneas "
            "y flechas direccionales que indiquen la secuencia lógica. Agrega leyendas descriptivas a cada bloque y "
            "utiliza un código de colores contrastante para diferenciar las fases de preparación, análisis crítico "
            "y toma de decisiones operativas. En la sección inferior del diagrama, incluye una nota técnica explicativa "
            "que detalle cómo cada etapa del flujo alimenta directamente el desarrollo del AMEF y la optimización de "
            "los planes de mantenimiento preventivo y predictivo en la organización."
        ),
        "nota_color": _FIGURE_GUIDE_BLUE,
    },
    {
        "tipo": "figura",
        "id": "fig_2_2_niveles_taxonomicos",
        "titulo": "Niveles taxonomicos",
        "caption": "Figura 2.2 Niveles taxonomicos",
        "ruta_placeholder": _CANONICAL_PLACEHOLDER_PATH,
        "fuente": "Nota. La taxonomia de activos fisicos como fundamento. Reliability CONNECT.",
        "nota": (
            "Guía para elaborar la figura: Construye un diagrama piramidal o jerárquico titulado \"Niveles taxonómicos\" "
            "basado estrictamente en la norma ISO 14224:2016 para la recolección de datos de mantenimiento y confiabilidad. "
            "Estructura el gráfico en una jerarquía vertical descendente de nueve niveles divididos en tres categorías "
            "principales: uso industrial (Nivel 1: Industria, Nivel 2: Categoría de negocio, Nivel 3: Instalación), "
            "categoría de equipo (Nivel 4: Clase de equipo, Nivel 5: Unidad de equipo, Nivel 6: Subunidad o sistema "
            "principal) y localización de falla (Nivel 7: Componente, Nivel 8: Parte o subcomponente, Nivel 9: Detalle "
            "o elemento mínimo). Utiliza cajas rectangulares alineadas para cada nivel, conectadas con líneas jerárquicas "
            "sólidas. Resalta visualmente el Nivel 5 (Unidad de equipo) y el Nivel 6 (Subunidad) como los puntos críticos "
            "de recolección de datos operativos y de falla. Añade etiquetas descriptivas claras en cada bloque y un "
            "cuadro lateral informativo que describa el impacto de una correcta taxonomía en la consistencia de los "
            "indicadores MTBF y MTTR."
        ),
        "nota_color": _FIGURE_GUIDE_BLUE,
    },
    {
        "tipo": "figura",
        "id": "fig_2_3_amef",
        "titulo": "Analisis de Modo y Efecto de Falla",
        "caption": "Figura 2.3 Analisis de Modo y Efecto de Falla",
        "ruta_placeholder": _CANONICAL_PLACEHOLDER_PATH,
        "fuente": (
            "Nota. Representacion del analisis de modos y efectos de falla aplicado al mantenimiento "
            "centrado en confiabilidad."
        ),
        "nota": (
            "Guía para elaborar la figura: Elabora un esquema conceptual titulado \"Análisis de Modo y Efecto de "
            "Falla (AMEF)\" que represente gráficamente la estructura metodológica para evaluar y priorizar los riesgos "
            "de falla en los activos críticos del proyecto. Dibuja un diagrama relacional que conecte en forma de "
            "cascada de izquierda a derecha los siguientes elementos analíticos: el Componente, la Función asociada, "
            "la Falla funcional potencial, los Modos de falla específicos y sus Efectos operativos y de seguridad. "
            "Incorpora un bloque central destacado para el cálculo del Número de Prioridad de Riesgo (NPR), detallando "
            "sus tres variables de entrada mediante multiplicadores: Severidad (S), Ocurrencia (O) y Detección (D), "
            "en una escala del 1 al 10. Representa las conexiones con flechas y colores diferenciados para indicar "
            "la ruta crítica de análisis. Incluye en la parte inferior del esquema la fórmula formal NPR = S x O x D "
            "junto con una escala visual de criticidad (Baja, Media, Alta) para guiar al usuario en la definición "
            "de acciones recomendadas de mantenimiento."
        ),
        "nota_color": _FIGURE_GUIDE_BLUE,
    },
    {
        "tipo": "figura",
        "id": "fig_2_4_motoniveladora_cat_24m",
        "titulo": "Motoniveladora CAT 24M",
        "caption": "Figura 2.4 Motoniveladora CAT 24M",
        "ruta_placeholder": _CANONICAL_PLACEHOLDER_PATH,
        "fuente": "Nota. Motoniveladora 24M.",
        "nota": (
            "Guía para elaborar la figura: Construye un diagrama técnico de distribución titulado \"Motoniveladora "
            "CAT 24M\" que identifique visualmente los sistemas y componentes críticos sometidos a análisis en este "
            "proyecto. Utiliza una vista en corte lateral o despiece simplificado de la máquina como base gráfica. "
            "Rotula y apunta con líneas de referencia precisas a los componentes clave: el motor diésel CAT C18 ACERT, "
            "el sistema de transmisión y tren de fuerza, el sistema hidráulico principal de implementos, el mecanismo "
            "del círculo y vertedera, y el sistema de control electrónico. Cada etiqueta debe estar acompañada de "
            "una breve descripción técnica de su función operativa y de su susceptibilidad a modos de falla críticos "
            "identificados en la línea base. Asegura una presentación profesional con fondos neutros, fuentes "
            "consistentes y líneas de cota claras. Agrega un cuadro lateral descriptivo que resuma la especificación "
            "técnica general del equipo y su importancia en las operaciones mineras o de construcción de caminos."
        ),
        "nota_color": _FIGURE_GUIDE_BLUE,
    },
)
_THEORETICAL_MAINTENANCE_MARKERS = (
    "mantenimiento",
    "confiabilidad",
    "disponibilidad inherente",
    "iso 14224",
    "amef",
    "mtbf",
    "mttr",
    "cat 24m",
    "motoniveladora",
    "rcm",
    "mineria",
    "minera",
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
    if _normalize_token(block.get("tipo")) != "figura":
        return False
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


def _is_chapter_two_text_only_path(path: str) -> bool:
    joined = " / ".join(normalized_path_segments(path))
    if "MARCO TEORICO" not in joined and "REVISION DE LITERATURA" not in joined:
        return False
    return any(
        marker in joined
        for marker in (
            "ANTECEDENTES",
            "MARCO CONCEPTUAL",
            "DEFINICION DE TERMINOS BASICOS",
            "DEFINICION DE TERMINOS",
        )
    )


def _is_chapter_two_bases_path(path: str) -> bool:
    joined = " / ".join(normalized_path_segments(path))
    return ("MARCO TEORICO" in joined or "REVISION DE LITERATURA" in joined) and "BASES TEORICAS" in joined


def _theoretical_bases_is_maintenance_case(content: Any, values: dict[str, Any] | None = None) -> bool:
    content_text = _normalize_token(_visible_text(content))
    values_text = ""
    if isinstance(values, dict):
        values_text = " ".join(
            _normalize_token(values.get(key))
            for key in (
                "title",
                "titulo",
                "tema",
                "linea_investigacion",
                "objeto_estudio",
                "variable_independiente",
                "variable_dependiente",
                "poblacion",
                "muestra",
            )
        )
    combined = " ".join(part for part in (content_text, values_text) if part)
    hits = sum(1 for marker in _THEORETICAL_MAINTENANCE_MARKERS if marker in combined)
    return hits >= 3 and (
        "mantenimiento" in combined or "confiabilidad" in combined or "disponibilidad" in combined
    )


def _project_problem_figure_blocks(section_id: str, path: str) -> list[dict[str, Any]]:
    notes = (
        (
            'Construye un diagrama de Pareto titulado "Diagrama de Pareto de modos de falla en flota '
            'CAT 24M". Usa los registros reales de fallas del periodo de línea base disponible en el CMMS '
            "o historial de mantenimiento. Coloca una tabla base con estas columnas obligatorias: sistema o "
            "modo de falla, frecuencia de fallas, porcentaje individual, porcentaje acumulado y costo de "
            "reparación si el dato existe. Agrupa nombres equivalentes antes de graficar; por ejemplo, no "
            "separes una falla hidráulica repetida solo porque fue registrada con otra descripción. Ordena "
            "las filas de mayor a menor frecuencia. Calcula el porcentaje individual como frecuencia del modo "
            "de falla entre total de fallas por 100. Calcula el porcentaje acumulado sumando progresivamente "
            "los porcentajes individuales. En el gráfico, coloca en el eje X los sistemas o modos de falla; "
            "en el eje Y izquierdo, la frecuencia absoluta de fallas; en el eje Y derecho, el porcentaje "
            "acumulado de 0 % a 100 %. Usa barras verticales para la frecuencia, una línea curva para el "
            "porcentaje acumulado y una línea horizontal de referencia en 80 %. Marca con color distinto los "
            "modos ubicados antes del cruce con el 80 % y agrega una lectura breve: esos son los pocos vitales "
            "que deben priorizarse en el plan RCM."
        ),
        (
            'Construye un diagrama de Ishikawa titulado "Análisis de Causa-Efecto de Baja Disponibilidad '
            '(Ishikawa)". Coloca en la cabeza del diagrama el efecto exacto: "Baja disponibilidad inherente '
            'de la flota CAT 24M". Dibuja una espina central horizontal y seis ramas principales con el '
            "enfoque 6M: Método, Medición, Mano de obra, Medio ambiente, Maquinaria y Materiales. En Método, "
            "coloca mantenimiento reactivo, rutinas preventivas insuficientes, ausencia de tareas RCM y "
            "procedimientos de lubricación no estandarizados. En Medición, coloca registros incompletos, "
            "MTBF/MTTR no depurados, ausencia de trazabilidad ISO 14224 y falta de control de tiempos de "
            "parada. En Mano de obra, coloca brechas de capacitación, inspecciones variables, diagnóstico "
            "lento y dependencia de experiencia individual. En Medio ambiente, coloca polvo, abrasividad, "
            "pendientes dinámicas, altitud operativa y variación climática. En Maquinaria, coloca desgaste "
            "del tren de fuerza, sistema hidráulico, sistema eléctrico y componentes de desgaste rápido. En "
            "Materiales, coloca calidad de repuestos, compatibilidad de fluidos, stock crítico insuficiente "
            "y repuestos no homologados. Cierra la figura con una lectura causal que indique qué ramas "
            "explican la mayor parte de la baja disponibilidad y cómo el RCM atacará esas causas."
        ),
        (
            'Construye una matriz titulada "Matriz de Relevancia para el filtrado de alternativas de '
            'solución". Coloca las alternativas en filas: mantenimiento correctivo mejorado, mantenimiento '
            "preventivo por horas, mantenimiento predictivo parcial, capacitación técnica focalizada y plan "
            "de mantenimiento centrado en confiabilidad (RCM). Coloca estos criterios en columnas: reducción "
            "esperada de fallas, viabilidad técnica, costo de implementación, tiempo de adaptación, "
            "disponibilidad de datos y alineación con la causa raíz. Asigna a cada criterio un peso; por "
            "ejemplo, reducción esperada de fallas 0.30, viabilidad técnica 0.20, costo 0.15, tiempo 0.10, "
            "disponibilidad de datos 0.10 y alineación con causa raíz 0.15. Califica cada alternativa de 1 a "
            "5, donde 1 significa baja relevancia y 5 alta relevancia. Multiplica cada calificación por su "
            'peso y suma el total por alternativa. Agrega una columna final llamada "Decisión" con tres '
            "opciones: descartada, condicionada o preseleccionada. Resalta el RCM como alternativa "
            "preseleccionada porque interviene modos de falla, criticidad y tareas de mantenimiento, no solo "
            "la reparación posterior a la falla."
        ),
        (
            'Construye una matriz titulada "Matriz de Priorización de soluciones factibles". Coloca en las '
            "filas solo las alternativas que pasaron la matriz de relevancia. Coloca en las columnas estos "
            "criterios cuantitativos: impacto en disponibilidad inherente, reducción de fallas recurrentes, "
            "factibilidad técnica, costo-beneficio, tiempo de implementación y sostenibilidad operativa. "
            "Asigna un peso porcentual a cada criterio y verifica que la suma sea exactamente 100 %. Califica "
            "cada alternativa de 1 a 10, donde 1 es desfavorable y 10 favorable. En cada celda coloca el "
            "puntaje asignado; debajo o en una columna auxiliar calcula el puntaje ponderado multiplicando "
            'peso por puntaje. Agrega una columna "Total ponderado" y suma los puntajes ponderados de cada '
            "alternativa. Ordena las alternativas de mayor a menor total. Resalta en azul o sombreado la "
            "alternativa ganadora: implementación de un plan de mantenimiento centrado en confiabilidad "
            "(RCM). Debajo de la matriz coloca la escala: 1 (Desfavorable) a 10 (Favorable)."
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
                "fuente": "Elaboración propia.",
                "nota": _augment_project_problem_figure_note(index, note),
                "nota_color": _FIGURE_GUIDE_BLUE,
            }
        )
    return blocks


def _augment_project_problem_figure_note(index: int, note: str) -> str:
    extra_details = {
        1: (
            " Verifica que la tabla base salga del historial de fallas depurado y que cada fila represente "
            "un sistema o modo de falla homogéneo. Revisa que no existan categorías duplicadas, calcula el "
            "porcentaje individual sobre el total de eventos y luego el porcentaje acumulado. Muestra con "
            "claridad el eje X, el eje Y izquierdo y el eje Y derecho con porcentaje acumulado. Cierra con "
            "una lectura que explique por qué los sistemas ubicados antes del cruce con el 80 % se consideran "
            "prioritarios para el proyecto."
        ),
        2: (
            " Escribe cada subcausa como un factor observable y técnico, no como una frase vaga. Mantén el "
            "problema central en la cabeza del diagrama y conecta cada subcausa con una rama 6M. Cierra la "
            "interpretación señalando qué rama concentra la causa raíz dominante y por qué eso obliga a pasar "
            "de un mantenimiento reactivo o rígido a un enfoque RCM."
        ),
        3: (
            " Usa la matriz para filtrar qué opciones merecen pasar a la evaluación final. Incluye una "
            "alternativa descartada, una alternativa de contención y la alternativa estructural. Explica "
            "visualmente la decisión en la columna final para que se entienda por qué el RCM continúa a la "
            "priorización."
        ),
        4: (
            " Muestra el peso porcentual de cada criterio, el puntaje asignado a cada alternativa, el producto "
            "peso por puntaje y el total ponderado. Redacta la conclusión de la figura como una validación "
            "cuantitativa de la alternativa elegida."
        ),
    }
    return f"Guía para elaborar la figura: {note}{extra_details.get(index, '')}"


def _strip_stale_project_problem_visual_markup_from_text(text: str) -> str:
    cleaned = _STALE_PROJECT_MARKDOWN_FIGURE_RE.sub("\n", text)
    cleaned = _strip_stale_project_problem_loose_guides(cleaned)
    return _BLANK_LINE_RE.sub("\n\n", cleaned).strip()


def _is_stale_project_problem_loose_title(text: str) -> bool:
    return any(text.startswith(prefix) for prefix in _STALE_PROJECT_LOOSE_FIGURE_TITLE_PREFIXES)


def _is_stale_project_problem_guide_line(text: str) -> bool:
    return any(text.startswith(prefix) for prefix in _STALE_PROJECT_GUIDE_LINE_PREFIXES)


def _strip_stale_project_problem_loose_guides(text: str) -> str:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    cleaned_lines: list[str] = []
    skipping_guide = False

    for line in lines:
        normalized = _normalize_token(line)
        if skipping_guide and not normalized:
            continue
        if _is_stale_project_problem_loose_title(normalized) or normalized.startswith("guia tecnica"):
            skipping_guide = True
            continue
        if skipping_guide and _is_stale_project_problem_guide_line(normalized):
            continue

        skipping_guide = False
        cleaned_lines.append(line)

    return "\n".join(cleaned_lines)


def _strip_stale_project_problem_visual_markup(content: Any) -> Any:
    if isinstance(content, str):
        return _strip_stale_project_problem_visual_markup_from_text(content)
    if not isinstance(content, list):
        return content

    cleaned_blocks: list[Any] = []
    for item in content:
        if isinstance(item, dict) and _normalize_token(item.get("tipo")) == "parrafo":
            text = _strip_stale_project_problem_visual_markup_from_text(str(item.get("texto") or ""))
            if text:
                next_item = dict(item)
                next_item["texto"] = text
                cleaned_blocks.append(next_item)
            continue
        cleaned_blocks.append(item)
    return cleaned_blocks


def _is_project_problem_figure(block: dict[str, Any]) -> bool:
    if _normalize_token(block.get("tipo")) != "figura":
        return False
    figure_title = _normalize_token(block.get("titulo") or block.get("caption"))
    return any(_normalize_token(title) == figure_title for title in _PROJECT_PROBLEM_FIGURE_TITLES)


def _is_stale_project_problem_visual_paragraph(block: dict[str, Any]) -> bool:
    if _normalize_token(block.get("tipo")) != "parrafo":
        return False
    text = _normalize_token(block.get("texto"))
    if not text:
        return False
    stale_prefixes = (
        "figura 1.1",
        "figura 1.2",
        "figura 1.3",
        "figura 1.4",
        "figura pendiente de elaboracion propia",
        "fuente elaboracion propia",
        "fuente: elaboracion propia",
        "guia para elaborar la figura",
        "guia para construir la figura",
        "guia tecnica",
        "diagrama de pareto de fallas",
        "diagrama de pareto de modos de falla",
        "diagrama de ishikawa",
        "matriz de relevancia de alternativas",
        "matriz de relevancia para alternativas",
        "matriz de priorizacion de alternativas",
        "matriz de priorizacion de estrategias",
        "matriz de priorizacion de soluciones",
        "nota tecnica la figura 1",
        "nota tecnica figura 1",
        "nota tecnica: la figura 1",
        "nota tecnica: figura 1",
        "este grafico debe",
        "la construccion del pareto debe",
        "este diagrama debe",
        "esta matriz debe",
        "la matriz debe incluir",
        "cada alternativa debe calificarse",
        "los puntajes deben",
        "escala: 1",
    )
    return any(text.startswith(prefix) for prefix in stale_prefixes)


def _paragraph_matches_anchor(block: dict[str, Any], anchors: tuple[str, ...]) -> bool:
    if _normalize_token(block.get("tipo")) != "parrafo":
        return False
    text = _normalize_token(block.get("texto"))
    return any(_normalize_token(anchor) in text for anchor in anchors)


def _paragraph_matches_ordered_anchor(block: dict[str, Any], figure_index: int) -> bool:
    text = _normalize_token(block.get("texto"))
    if _normalize_token(block.get("tipo")) != "parrafo" or not text:
        return False
    return _project_problem_anchor_score(block, figure_index) > 0


def _project_problem_anchor_score(block: dict[str, Any], figure_index: int) -> int:
    if _normalize_token(block.get("tipo")) != "parrafo":
        return 0
    text = _normalize_token(block.get("texto"))
    if not text:
        return 0
    if figure_index == 2 and any(marker in text for marker in ("matriz de priorizacion", "priorizacion ponderada")):
        return 0

    anchors = _PROJECT_PROBLEM_ORDERED_ANCHORS[figure_index]
    score = sum(8 for anchor in anchors if anchor in text)
    if score == 0:
        return 0

    word_count = len(text.split())
    score += min(word_count, 140) // 7
    explicit_marker = f"figura 1.{figure_index + 1}"
    if explicit_marker in text:
        score += 90 if word_count >= 45 else 20
    if word_count < 22:
        score -= 18
    return max(score, 0)


def _paragraph_has_any_project_anchor(block: dict[str, Any]) -> bool:
    return any(_paragraph_matches_anchor(block, anchors) for anchors in _PROJECT_PROBLEM_FIGURE_ANCHORS)


def _paragraph_project_anchor_count(block: dict[str, Any]) -> int:
    return sum(1 for anchors in _PROJECT_PROBLEM_FIGURE_ANCHORS if _paragraph_matches_anchor(block, anchors))


def _split_anchor_paragraphs(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    split_blocks: list[dict[str, Any]] = []
    for block in blocks:
        if _normalize_token(block.get("tipo")) != "parrafo" or not _paragraph_has_any_project_anchor(block):
            split_blocks.append(block)
            continue
        if _paragraph_project_anchor_count(block) <= 1:
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


def _fallback_ordered_anchor_index(blocks: list[dict[str, Any]], figure_index: int, start_index: int) -> int:
    paragraph_indexes = [
        index
        for index, block in enumerate(blocks)
        if index >= start_index and _normalize_token(block.get("tipo")) == "parrafo"
    ]
    if paragraph_indexes:
        return paragraph_indexes[min(figure_index, len(paragraph_indexes) - 1)]
    return _fallback_anchor_index(blocks, figure_index)


def _best_ordered_anchor_index(blocks: list[dict[str, Any]], figure_index: int, start_index: int) -> int:
    scored = [
        (_project_problem_anchor_score(blocks[block_index], figure_index), block_index)
        for block_index in range(start_index, len(blocks))
    ]
    scored = [(score, block_index) for score, block_index in scored if score > 0]
    if not scored:
        return -1
    return max(scored, key=lambda item: (item[0], -item[1]))[1]


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
    cleaned_content = _strip_stale_project_problem_visual_markup(section.get("content"))
    blocks = _content_to_blocks(cleaned_content)
    required_blocks = _project_problem_figure_blocks(str(section.get("sectionId") or ""), path)
    # Rebuild controlled project figures so stale generated output cannot leave
    # them appended as a consecutive group at the end of 1.1.
    content_blocks = [
        block
        for block in blocks
        if _normalize_token(block.get("tipo")) != "figura"
        and not _is_project_problem_figure(block)
        and not _is_stale_project_problem_visual_paragraph(block)
    ]

    search_start = 0
    for index, block in enumerate(required_blocks):
        anchor_index = _best_ordered_anchor_index(content_blocks, index, search_start)
        if anchor_index < 0:
            anchor_index = _fallback_ordered_anchor_index(content_blocks, index, search_start)
        has_explicit_anchor = 0 <= anchor_index < len(content_blocks) and _paragraph_matches_ordered_anchor(
            content_blocks[anchor_index], index
        )
        _insert_after_index(
            content_blocks,
            anchor_index,
            block,
            lead_text="" if has_explicit_anchor else _PROJECT_PROBLEM_FIGURE_LEADS[index],
        )
        search_start = min(anchor_index + 2, len(content_blocks))

    section["content"] = content_blocks


def _is_chapter_two_figure(block: dict[str, Any]) -> bool:
    if _normalize_token(block.get("tipo")) != "figura":
        return False
    figure_id = _normalize_token(block.get("id"))
    title = _normalize_token(block.get("titulo") or block.get("caption"))
    if figure_id.startswith("fig_2_"):
        return True
    controlled_titles = {_normalize_token(item["titulo"]) for item in _CHAPTER_TWO_FIGURES}
    controlled_captions = {_normalize_token(item["caption"]) for item in _CHAPTER_TWO_FIGURES}
    return title in controlled_titles or title in controlled_captions


def _matches_any_anchor(block: dict[str, Any], anchors: tuple[str, ...]) -> bool:
    if _normalize_token(block.get("tipo")) != "parrafo":
        return False
    text = _normalize_token(block.get("texto"))
    return any(_normalize_token(anchor) in text for anchor in anchors)


def _first_anchor_index(blocks: list[dict[str, Any]], anchors: tuple[str, ...], *, start: int = 0) -> int:
    for index in range(max(0, start), len(blocks)):
        if _matches_any_anchor(blocks[index], anchors):
            return index
    return -1


def _chapter_two_heading_indices(blocks: list[dict[str, Any]]) -> dict[int, int]:
    indices: dict[int, int] = {}
    for index, block in enumerate(blocks):
        if _normalize_token(block.get("tipo")) != "parrafo":
            continue
        text = str(block.get("texto") or "").strip()
        if not text:
            continue
        first_line = text.splitlines()[0].strip()
        match = _THEORETICAL_HEADING_RE.match(first_line)
        if match:
            indices[int(match.group(1))] = index
    return indices


def _chapter_two_insert_index(
    blocks: list[dict[str, Any]],
    *,
    figure_index: int,
) -> int:
    heading_indices = _chapter_two_heading_indices(blocks)
    target_heading = _CHAPTER_TWO_FIGURE_TARGET_HEADINGS[figure_index]
    current_heading_index = heading_indices.get(target_heading)
    if current_heading_index is not None:
        later_heading_indexes = [
            index for number, index in heading_indices.items() if number > target_heading and index > current_heading_index
        ]
        next_heading_index = min(later_heading_indexes) if later_heading_indexes else -1
        upper_bound = next_heading_index if next_heading_index >= 0 else len(blocks)
        paragraph_indexes = [
            index
            for index in range(current_heading_index + 1, upper_bound)
            if _normalize_token(blocks[index].get("tipo")) == "parrafo"
        ]
        if paragraph_indexes:
            return paragraph_indexes[-1]
        return current_heading_index

    anchors = _CHAPTER_TWO_SUBTOPIC_ANCHORS[figure_index]
    start_index = _first_anchor_index(blocks, anchors)
    if start_index < 0:
        paragraph_indexes = [
            index for index, block in enumerate(blocks) if _normalize_token(block.get("tipo")) == "parrafo"
        ]
        if not paragraph_indexes:
            return -1
        return paragraph_indexes[min(figure_index, len(paragraph_indexes) - 1)]

    next_start_candidates = [
        _first_anchor_index(blocks, next_anchors, start=start_index + 1)
        for next_anchors in _CHAPTER_TWO_SUBTOPIC_ANCHORS[figure_index + 1 :]
    ]
    next_start = min((index for index in next_start_candidates if index >= 0), default=-1)
    if next_start > start_index:
        return next_start - 1

    paragraph_indexes = [
        index
        for index, block in enumerate(blocks)
        if index >= start_index and _normalize_token(block.get("tipo")) == "parrafo"
    ]
    return paragraph_indexes[-1] if paragraph_indexes else start_index


def _extract_heading_title(block: dict[str, Any]) -> str:
    """Extrae el título puro de un bloque de párrafo que comienza con un encabezado 2.2.x."""
    first_line = str(block.get("texto") or "").strip().splitlines()[0].strip()
    match = _THEORETICAL_HEADING_RE.match(first_line)
    if match:
        return first_line[match.end():].strip()
    return first_line


def _ensure_chapter_two_theoretical_figures(
    section: dict[str, Any],
    values: dict[str, Any] | None = None,
) -> None:
    """Inyecta una figura por cada subtítulo 2.2.x detectado en el contenido.

    Funciona para cualquier tema (mantenimiento, software, salud, etc.) porque
    detecta los encabezados reales que la IA generó en lugar de depender de
    listas hardcodeadas de términos de mantenimiento.
    """
    blocks = _content_to_blocks(section.get("content"))

    # Eliminar figuras existentes del capítulo 2 (controladas o genéricas) para
    # reconstruirlas desde cero con la lógica dinámica.
    content_blocks = [
        block for block in blocks
        if _normalize_token(block.get("tipo")) != "figura"
        or (not _is_chapter_two_figure(block) and not _is_generic_figure(block))
    ]

    # Detectar todos los encabezados 2.2.x y sus posiciones en el contenido
    heading_indices = _chapter_two_heading_indices(content_blocks)

    if not heading_indices:
        section["content"] = content_blocks
        return

    subject = _subject(values)
    sorted_headings = sorted(heading_indices.items())  # [(1, idx), (2, idx), ...]

    # Recopilar inserciones (anchor_index, figura) en orden normal
    # y luego insertar en orden inverso para no desplazar índices.
    insertions: list[tuple[int, dict[str, Any]]] = []

    for i, (heading_num, heading_block_idx) in enumerate(sorted_headings):
        raw_title = _extract_heading_title(content_blocks[heading_block_idx])
        if not raw_title:
            continue

        # Título de la figura: añade el tema del proyecto si no es genérico
        if subject and subject != "el estudio desarrollado":
            figure_title = f"{raw_title} aplicado a {subject}"
        else:
            figure_title = raw_title

        # Punto de inserción: el último párrafo antes del siguiente encabezado
        next_heading_idxs = [idx for h, idx in sorted_headings if h > heading_num]
        upper_bound = min(next_heading_idxs) if next_heading_idxs else len(content_blocks)

        paragraph_idxs = [
            idx for idx in range(heading_block_idx + 1, upper_bound)
            if _normalize_token(content_blocks[idx].get("tipo")) == "parrafo"
        ]
        anchor_index = paragraph_idxs[-1] if paragraph_idxs else heading_block_idx

        section_id = f"2_{heading_num}_{_FIGURE_ID_RE.sub('_', _normalize_token(raw_title))[:30]}"
        figure_block = _build_recommended_figure(
            section_id,
            str(section.get("path") or ""),
            figure_title,
        )
        insertions.append((anchor_index, figure_block))

    # Insertar en orden inverso para preservar los índices correctamente
    for anchor_index, figure_block in reversed(insertions):
        _insert_after_index(content_blocks, anchor_index, figure_block)

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
        "fuente": "Nota. Figura sugerida para validacion del autor.",
        "nota": (
            f"Guía para elaborar la figura: Diseña un esquema gráfico profesional titulado \"{title}\" "
            "que sirva como soporte visual y académico del desarrollo de esta sección. El diagrama debe "
            "estructurarse mediante bloques relacionales, diagramas de flujo o mapas conceptuales según "
            "corresponda a la naturaleza del subtema. Define con claridad las variables clave, los procesos "
            "involucrados o la arquitectura del sistema. Conecta los elementos conceptuales con líneas "
            "y flechas direccionales que muestren la secuencia lógica y el sentido de las relaciones. "
            "Utiliza formas geométricas consistentes (rectángulos, óvalos o círculos) y un esquema de colores "
            "sobrio y contrastante para mejorar la legibilidad. Asegura que todos los textos, variables y "
            "rótulos de la figura utilicen una fuente Arial de 10 puntos sin negritas ni marcadores adicionales. "
            "En la parte inferior de la figura, incluye siempre la fuente correspondiente en formato APA "
            "estándar (por ejemplo, 'Fuente: Elaboración propia' o la cita del autor correspondiente) "
            "y una nota técnica descriptiva que explique brevemente el contenido de la figura y su "
            "vinculación directa con el sustento analítico del proyecto."
        ),
        "nota_color": _FIGURE_GUIDE_BLUE,
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

        if _is_chapter_two_text_only_path(path):
            current_content = section.get("content")
            blocks = _content_to_blocks(current_content)
            if any(_normalize_token(block.get("tipo")) != "parrafo" for block in blocks):
                section["content"] = [block for block in blocks if _normalize_token(block.get("tipo")) == "parrafo"]
            continue

        if (
            is_chapter_three_hypotheses_section(path)
            or is_chapter_three_operationalization_section(path)
            or is_chapter_four_text_only_section(path)
        ):
            current_content = section.get("content")
            blocks = _content_to_blocks(current_content)
            if any(_normalize_token(block.get("tipo")) != "parrafo" for block in blocks):
                section["content"] = [block for block in blocks if _normalize_token(block.get("tipo")) == "parrafo"]
            continue

        if is_chapter_four_design_section(path):
            current_content = section.get("content")
            blocks = _content_to_blocks(current_content)
            if any(_normalize_token(block.get("tipo")) not in {"parrafo", "formula"} for block in blocks):
                section["content"] = [
                    block for block in blocks if _normalize_token(block.get("tipo")) in {"parrafo", "formula"}
                ]
            continue

        if _is_chapter_two_bases_path(path):
            # Inyecta una figura por cada subtítulo 2.2.x detectado dinámicamente.
            # Funciona para cualquier tema: el sistema lee los headings reales que
            # la IA generó en lugar de depender de marcadores de mantenimiento.
            _ensure_chapter_two_theoretical_figures(section, values)
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
