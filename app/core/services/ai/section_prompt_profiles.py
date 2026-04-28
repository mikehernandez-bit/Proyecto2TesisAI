from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Sequence

from app.core.services.maestria_payload_mapper import normalize_maestria_details

_TARGET_FORMATS = {"unac-proyecto-cuant", "unac-maestria-cuant"}


def _normalize_text(value: Any) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    without_accents = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return " ".join(without_accents.lower().split())


def _compact(value: Any) -> str:
    return " ".join(str(value or "").split())


def _clip(value: Any, max_chars: int = 260) -> str:
    text = _compact(value)
    if len(text) <= max_chars:
        return text
    return f"{text[: max_chars - 3].rstrip()}..."


def _join_list(values: Sequence[Any], *, max_items: int = 5, empty: str = "---") -> str:
    cleaned = [_compact(item) for item in values if _compact(item)]
    if not cleaned:
        return empty
    if len(cleaned) > max_items:
        cleaned = [*cleaned[:max_items], f"(+{len(cleaned) - max_items} mas)"]
    return "; ".join(cleaned)


def _is_target_format(format_id: str | None) -> bool:
    return _normalize_text(format_id) in _TARGET_FORMATS


@dataclass(frozen=True)
class SectionPromptProfile:
    word_range: str
    purpose: str
    structure: tuple[str, ...]
    quality_rules: tuple[str, ...]
    context_mode: str


_SECTION_PROFILES: dict[str, SectionPromptProfile] = {
    "introduccion": SectionPromptProfile(
        word_range="650 a 900 palabras",
        purpose=(
            "Abrir el proyecto con contexto estrategico, situacion local, justificacion tecnica "
            "de la propuesta y cierre metodologico breve."
        ),
        structure=(
            "Contexto estrategico del sector y criticidad del problema.",
            "Situacion especifica del equipo, proceso u organizacion con brecha o KPI observable.",
            "Antecedentes recientes que respaldan la propuesta tecnica sin copiar fichas completas.",
            "Presentacion de la propuesta de solucion y del objetivo general.",
            "Cierre metodologico y mapa breve de capitulos.",
        ),
        quality_rules=(
            "No inventes resultados de implementacion ni beneficios ya comprobados; el documento es un proyecto.",
            "Usa tono de ingenieria de mantenimiento y confiabilidad, no texto generico.",
            "Evita repetir literalmente el titulo en cada parrafo.",
        ),
        context_mode="project_overview",
    ),
    "i. planteamiento del problema": SectionPromptProfile(
        word_range="90 a 150 palabras",
        purpose=(
            "Redactar solo una apertura breve del capitulo, sin duplicar el desarrollo de las subsecciones 1.1 a 1.5."
        ),
        structure=(
            "Presenta el foco del capitulo y la logica problema -> objetivos -> justificacion -> delimitaciones.",
            "Menciona de forma breve la variable principal, el contexto y la propuesta.",
        ),
        quality_rules=(
            "No desarrolles otra vez el contenido completo de 1.1 a 1.5.",
            "Usa unicamente uno o dos parrafos cortos de transicion.",
        ),
        context_mode="problem_overview",
    ),
    "i. planteamiento del problema/1.1 descripcion de la realidad problematica": SectionPromptProfile(
        word_range="1800 a 2400 palabras",
        purpose=(
            "Construir un diagnostico tecnico de alta densidad argumental, desde el contexto "
            "macro de la mineria hasta el problema local del activo, con transiciones claras "
            "hacia el analisis causal y cuatro figuras tecnicas intercaladas en el punto exacto."
        ),
        structure=(
            (
                "Parrafo 1: contexto operativo macro de la mineria a cielo abierto, presion por continuidad "
                "operativa y rol estrategico del activo o proceso estudiado dentro de la cadena de valor."
            ),
            (
                "Parrafo 2: contexto internacional con antecedentes tecnicos comparables sobre confiabilidad, "
                "disponibilidad, mantenibilidad o RCM en equipos mineros o activos equivalentes."
            ),
            (
                "Parrafo 3: contexto latinoamericano o sectorial cercano con evidencia de gestion de activos, "
                "brechas de disponibilidad o mejora de mantenimiento."
            ),
            (
                "Parrafo 4: contexto peruano con antecedentes aplicados a maquinaria minera o mantenimiento RCM, "
                "con foco en el valor tecnico del metodo y no en relleno historico."
            ),
            (
                "Parrafos 5 y 6: diagnostico local usando exclusivamente brecha, KPI, activos, lugar, "
                "poblacion, muestra, variables y datos estructurados del Excel; explicar por que la brecha "
                "operativa es critica para la continuidad productiva."
            ),
            (
                "Parrafo 7: diagnostico tecnico con lenguaje de ingenieria de mantenimiento, lectura causal del "
                "problema y transicion directa al Pareto."
            ),
            (
                "Figura 1.1: insertar inmediatamente despues del parrafo que explica la concentracion de fallas, "
                "con guia textual extensa para construir el Diagrama de Pareto y leer la regla 80/20."
            ),
            (
                "Parrafo 8: interpretar que los sistemas o modos vitales requieren un analisis causa-raiz y "
                "transicionar al Ishikawa."
            ),
            (
                "Figura 1.2: insertar inmediatamente despues del parrafo causal, con guia textual extensa para "
                "construir el Ishikawa, sus ramas 6M, subcausas y lectura tecnica."
            ),
            (
                "Parrafo 9: evaluar alternativas de solucion con criterios tecnicos, economicos y estrategicos, "
                "explicando por que unas se descartan y otras se preseleccionan."
            ),
            (
                "Figura 1.3: insertar inmediatamente despues del parrafo de comparacion de alternativas, con guia "
                "textual extensa para la Matriz de Relevancia."
            ),
            (
                "Parrafo 10: priorizar cuantitativamente las alternativas factibles y justificar la seleccion de la "
                "mejor estrategia."
            ),
            (
                "Figura 1.4: insertar inmediatamente despues del parrafo de priorizacion, con guia textual extensa "
                "para la Matriz de Priorizacion y su nota de escala."
            ),
            (
                "Parrafo final: cierre tecnico que conecte la variable independiente con la variable dependiente, "
                "sus dimensiones y la propuesta de solucion del proyecto."
            ),
        ),
        quality_rules=(
            "La seccion debe sentirse analitica y sustentada, no descriptiva sin criterio.",
            "La voz debe parecer la de un ingeniero redactando un proyecto formal, no la de un resumen de chatbot.",
            (
                "No uses TABLE_JSON ni conviertas Pareto, Ishikawa o matrices de decision "
                "en tablas dentro de la respuesta IA."
            ),
            "No uses FIGURE_JSON ni intentes insertar imagenes reales en esta seccion.",
            (
                "No inventes porcentajes, costos, disponibilidad, MTBF, MTTR, cantidades de equipos "
                "ni fuentes si no vienen en el Excel."
            ),
            (
                "Si falta un dato cuantitativo, redacta la necesidad de calcularlo con el historial de fallas, "
                "sin fabricar el numero."
            ),
            (
                "No cites autores, estudios, normas o porcentajes inventados. Si no tienes una fuente o dato "
                "especifico ya capturado por el sistema, contextualiza sin falsear la referencia."
            ),
            (
                "Cuando hables de las figuras, explica como elaborarlas "
                "manualmente, que datos deben contener y como interpretarlas."
            ),
            (
                "Cada figura debe quedar como placeholder: Figura pendiente de elaboracion propia, "
                "seguida por Fuente: Elaboracion propia y luego una nota tecnica en cursiva con la guia de elaboracion."
            ),
            (
                "Ubica cada figura inmediatamente despues del parrafo que la explica; "
                "no agrupes Figura 1.1, Figura 1.2, Figura 1.3 y Figura 1.4 al final de la seccion."
            ),
            (
                "Cada nota de figura debe ser mas detallada que una sola frase: "
                "incluir insumos, pasos de construccion, "
                "estructura visual minima y lectura esperada del grafico o matriz."
            ),
            ("Usa la rotulacion exacta Figura 1.1, Figura 1.2, Figura 1.3 y Figura 1.4 dentro del desarrollo."),
            (
                "En la guia de la Matriz de Priorizacion incluye la nota final: "
                "Escala: 1 (Desfavorable) a 10 (Favorable)."
            ),
            (
                "Despues de Figura 1.4, cierra conectando la variable independiente con "
                "la variable dependiente y sus dimensiones."
            ),
            "No cierres en abstracto; termina conectando explicitamente con la solucion propuesta.",
        ),
        context_mode="problem_detail",
    ),
    "i. planteamiento del problema/1.2 formulacion del problema": SectionPromptProfile(
        word_range="120 a 220 palabras",
        purpose=(
            "Formular el problema general y los problemas especificos en "
            "forma interrogativa y totalmente alineados con la matriz."
        ),
        structure=(
            "Problema general como subtitulo independiente.",
            "Una pregunta para el problema general.",
            "Problemas especificos como subtitulo independiente.",
            "Dos o mas preguntas especificas derivadas de dimensiones o focos del estudio.",
        ),
        quality_rules=(
            "No agregues explicaciones extensas ni justificacion adicional.",
            "Usa exactamente los rotulos Problema general y Problemas especificos.",
            "Cada pregunta debe mantener coherencia exacta con variables, "
            "unidad de analisis, lugar y horizonte temporal.",
        ),
        context_mode="matrix_core",
    ),
    "i. planteamiento del problema/1.3 objetivos": SectionPromptProfile(
        word_range="120 a 220 palabras",
        purpose=(
            "Plantear el objetivo general y los objetivos especificos como espejo operativo del problema formulado."
        ),
        structure=(
            "Objetivo general como subtitulo independiente.",
            "Objetivo general con verbo en infinitivo y relacion explicita con la propuesta.",
            "Objetivos especificos como subtitulo independiente.",
            "Objetivos especificos coherentes con problemas especificos y dimensiones relevantes.",
        ),
        quality_rules=(
            "Usa exactamente los rotulos Objetivo general y Objetivos especificos.",
            "No uses verbos ambiguos ni objetivos demasiado amplios.",
            "No agregues parrafos introductorios innecesarios.",
        ),
        context_mode="matrix_core",
    ),
    "i. planteamiento del problema/1.4 justificacion": SectionPromptProfile(
        word_range="1100 a 1700 palabras",
        purpose="Sustentar por que el proyecto merece ejecutarse desde varias dimensiones academicas y tecnicas.",
        structure=(
            "1.4.1 Justificacion normativa.",
            "1.4.2 Justificacion teorica.",
            "1.4.3 Justificacion practica.",
            "1.4.4 Justificacion metodologica.",
            "1.4.5 Justificacion economica.",
            "1.4.6 Justificacion social.",
        ),
        quality_rules=(
            "Cada tipo de justificacion debe aportar un criterio distinto; "
            "no repitas el mismo argumento con otro titulo.",
            "Cada subtitulo debe desarrollar un parrafo sustantivo, no una frase corta.",
            "Usa tiempo futuro y enfoque de proyecto cuando describas beneficios esperados.",
        ),
        context_mode="justification",
    ),
    "i. planteamiento del problema/1.5 delimitaciones de la investigacion": SectionPromptProfile(
        word_range="450 a 750 palabras",
        purpose="Definir delimitaciones teoricas, espaciales y temporales de forma precisa y sin ambiguedad.",
        structure=(
            "1.5.1 Delimitacion teorica.",
            "1.5.2 Delimitacion temporal.",
            "1.5.3 Delimitacion espacial.",
        ),
        quality_rules=(
            "No confundas delimitaciones con limitaciones del estudio.",
            "Cada delimitacion debe tener un parrafo completo y aplicarse al caso real.",
            "Cada delimitacion debe vincularse con el proyecto real y no con una definicion generica.",
        ),
        context_mode="delimitations",
    ),
    "ii. marco teorico": SectionPromptProfile(
        word_range="90 a 150 palabras",
        purpose=(
            "Redactar una apertura breve del capitulo teorico, sin "
            "reemplazar el desarrollo de antecedentes, bases teoricas y conceptos."
        ),
        structure=(
            "Presenta el rol del marco teorico para sostener la investigacion.",
            "Anticipa antecedentes, bases teoricas y conceptos clave del estudio.",
        ),
        quality_rules=("No desarrolles aqui fichas de antecedentes ni explicaciones largas.",),
        context_mode="theory_overview",
    ),
    "ii. marco teorico/2.1 antecedentes": SectionPromptProfile(
        word_range="1600 a 2200 palabras",
        purpose=(
            "Sintetizar antecedentes internacionales y nacionales con enfoque analitico y aporte explicito al estudio."
        ),
        structure=(
            "Antecedentes internacionales.",
            "Antecedentes nacionales.",
            "En cada antecedente: objetivo, metodo, resultados y aporte al estudio.",
        ),
        quality_rules=(
            "No conviertas la seccion en una lista mecanica de resenes identicas.",
            "Cada antecedente debe cerrar indicando el aporte concreto al proyecto.",
        ),
        context_mode="backgrounds",
    ),
    "ii. marco teorico/2.2 bases teoricas": SectionPromptProfile(
        word_range="1800 a 2800 palabras",
        purpose="Desarrollar el sustento tecnico principal de las variables, dimensiones y normas del estudio.",
        structure=(
            "Marco tecnico de la variable independiente.",
            "Marco tecnico de la variable dependiente.",
            "Normas, modelos o metodos especializados aplicables al proyecto.",
            "Definiciones operativas y relaciones entre dimensiones e indicadores.",
        ),
        quality_rules=(
            "Usa redaccion tecnica y cohesion conceptual; evita definiciones enciclopedicas desconectadas.",
            "Cuando corresponda, explica ecuaciones o indicadores sin inventar datos observados.",
        ),
        context_mode="theoretical_bases",
    ),
    "ii. marco teorico/2.3 marco conceptual": SectionPromptProfile(
        word_range="250 a 450 palabras",
        purpose="Delimitar los conceptos nucleares y la relacion entre variables y dimensiones del estudio.",
        structure=(
            "Concepto central de la variable independiente.",
            "Concepto central de la variable dependiente.",
            "Conexion de las dimensiones con el problema de estudio.",
        ),
        quality_rules=("No repitas todo el contenido de bases teoricas; sintetiza y ordena.",),
        context_mode="conceptual_frame",
    ),
    "ii. marco teorico/2.4 definicion de terminos basicos": SectionPromptProfile(
        word_range="250 a 450 palabras",
        purpose="Definir terminos tecnicos basicos directamente utiles para entender el proyecto.",
        structure=("Glosario tecnico breve y ordenado.",),
        quality_rules=(
            "Prioriza terminos realmente usados en el proyecto.",
            "Cada definicion debe ser tecnica y funcional, no decorativa.",
        ),
        context_mode="basic_terms",
    ),
    "iii. hipotesis y variables": SectionPromptProfile(
        word_range="80 a 140 palabras",
        purpose="Redactar una apertura breve del capitulo de hipotesis y variables antes de las subsecciones.",
        structure=("Menciona la hipotesis general y el rol de la operacionalizacion.",),
        quality_rules=("No dupliques el texto completo de 3.1 ni reconstruyas tablas en este bloque padre.",),
        context_mode="hypothesis_overview",
    ),
    "iii. hipotesis y variables/3.1 hipotesis": SectionPromptProfile(
        word_range="120 a 220 palabras",
        purpose="Declarar la hipotesis general y las hipotesis especificas en forma afirmativa y verificable.",
        structure=(
            "Hipotesis general como subtitulo independiente.",
            "Hipotesis general en forma afirmativa.",
            "Hipotesis especificas como subtitulo independiente.",
            "Hipotesis especificas alineadas con problemas y objetivos especificos.",
        ),
        quality_rules=(
            "Usa exactamente los rotulos Hipotesis general e Hipotesis especificas.",
            "No conviertas las hipotesis en preguntas.",
            "No introduzcas nuevas variables o dimensiones no capturadas en la matriz.",
        ),
        context_mode="hypotheses",
    ),
    "iii. hipotesis y variables/3.2 operacionalizacion de variable": SectionPromptProfile(
        word_range="80 a 160 palabras",
        purpose=(
            "Redactar solo un puente explicativo de la operacionalizacion; "
            "la estructura tabular ya debe basarse en los datos capturados."
        ),
        structure=(
            "Explica brevemente que la operacionalizacion organiza variables, dimensiones, indicadores e instrumentos.",
            (
                "Despues del puente textual deben insertarse las tablas Tabla 3.1 "
                "y Tabla 3.2 desde los datos estructurados."
            ),
        ),
        quality_rules=(
            "No reconstruyas manualmente la tabla si el proyecto ya tiene operacionalizacion estructurada.",
            "No inventes nuevas filas, indicadores o tecnicas.",
            "No uses numeracion de captura; la numeracion de tabla la aplica el render final.",
        ),
        context_mode="operationalization",
    ),
    "iv. metodologia del proyecto": SectionPromptProfile(
        word_range="90 a 150 palabras",
        purpose="Abrir el capitulo metodologico con una sintesis breve de su logica general.",
        structure=("Presenta el enfoque, diseno y logica de aplicacion del estudio.",),
        quality_rules=("No reemplaces el desarrollo de 4.1 a 4.7.",),
        context_mode="methodology_overview",
    ),
    "iv. metodologia del proyecto/4.1 diseno metodologico": SectionPromptProfile(
        word_range="220 a 380 palabras",
        purpose="Sustentar el tipo, enfoque, nivel y diseno metodologico del proyecto con coherencia tecnica.",
        structure=(
            "Tipo de investigacion.",
            "Enfoque de investigacion.",
            "Nivel de investigacion.",
            "Diseno metodologico y justificacion.",
        ),
        quality_rules=("Usa tiempo futuro y evita mezclar resultados con plan metodologico.",),
        context_mode="design",
    ),
    "iv. metodologia del proyecto/4.2 metodo de investigacion": SectionPromptProfile(
        word_range="180 a 300 palabras",
        purpose="Explicar el metodo cientifico o enfoque procedimental con el que se desarrollara el estudio.",
        structure=(
            "Metodo de investigacion adoptado.",
            "Etapas principales de aplicacion al proyecto.",
        ),
        quality_rules=("No repitas textualmente el apartado de diseno.",),
        context_mode="method",
    ),
    "iv. metodologia del proyecto/4.3 poblacion y muestra": SectionPromptProfile(
        word_range="180 a 320 palabras",
        purpose="Definir tecnicamente la poblacion, la muestra y el criterio de muestreo del estudio.",
        structure=(
            "Poblacion.",
            "Muestra.",
            "Criterio de muestreo o razon de muestreo censal.",
        ),
        quality_rules=("No contradigas los datos estructurados del proyecto.",),
        context_mode="population_sample",
    ),
    "iv. metodologia del proyecto/4.4 lugar de estudio": SectionPromptProfile(
        word_range="100 a 180 palabras",
        purpose="Describir el contexto operativo y geotecnico del lugar de estudio sin divagar.",
        structure=(
            "Ubicacion y contexto operativo.",
            "Rasgos del entorno relevantes para el problema.",
        ),
        quality_rules=("No conviertas la seccion en descripcion turistica o institucional extensa.",),
        context_mode="study_place",
    ),
    (
        "iv. metodologia del proyecto/4.5 tecnicas e instrumentos para la recoleccion de la informacion"
    ): SectionPromptProfile(
        word_range="260 a 420 palabras",
        purpose=("Sustentar tecnicas e instrumentos concretos de recoleccion y el tipo de informacion que aportan."),
        structure=(
            "Tecnicas de recoleccion.",
            "Instrumentos asociados.",
            "Uso previsto de cada tecnica o instrumento en el proyecto.",
        ),
        quality_rules=("No enumeres tecnicas sin explicar para que sirven dentro del estudio.",),
        context_mode="techniques_instruments",
    ),
    "iv. metodologia del proyecto/4.6 analisis y procesamiento de datos": SectionPromptProfile(
        word_range="220 a 360 palabras",
        purpose="Explicar el tratamiento analitico de los datos y la logica de procesamiento prevista.",
        structure=(
            "Preparacion y organizacion de datos.",
            "Analisis o tratamiento principal.",
            "Software, criterios o contrastes previstos.",
        ),
        quality_rules=("No declares resultados estadisticos ya obtenidos; describe el procedimiento futuro.",),
        context_mode="data_processing",
    ),
    "iv. metodologia del proyecto/4.7 aspectos eticos": SectionPromptProfile(
        word_range="160 a 260 palabras",
        purpose="Precisar compromisos eticos y criterios de integridad academica y profesional.",
        structure=(
            "Principios eticos aplicables.",
            "Tratamiento responsable de informacion y autoria.",
        ),
        quality_rules=(
            "No conviertas la seccion en un listado normativo vacio; aterriza los compromisos al proyecto.",
        ),
        context_mode="ethics",
    ),
    "v. cronograma de actividades": SectionPromptProfile(
        word_range="60 a 120 palabras",
        purpose="Introducir brevemente el cronograma como plan de ejecucion del proyecto.",
        structure=("Explica brevemente que el cronograma ordena actividades, secuencia y horizonte temporal.",),
        quality_rules=(
            "No escribas un desarrollo extenso; si no hay datos "
            "suficientes, limita la seccion a una introduccion breve.",
        ),
        context_mode="schedule",
    ),
    "vi. presupuesto": SectionPromptProfile(
        word_range="60 a 120 palabras",
        purpose="Introducir brevemente el presupuesto como estimacion de recursos para ejecutar el proyecto.",
        structure=("Explica brevemente el criterio general de asignacion de costos.",),
        quality_rules=("No inventes rubros demasiado especificos si no estan disponibles en el proyecto.",),
        context_mode="budget",
    ),
}
_SECTION_PROFILES["i. planteamiento del problema/1.5 delimitantes de la investigacion"] = _SECTION_PROFILES[
    "i. planteamiento del problema/1.5 delimitaciones de la investigacion"
]


def _profile_key(section_id: str, section_path: str) -> str:
    if _normalize_text(section_id) == "titulo-info-basica":
        return "titulo-info-basica"
    return _normalize_text(section_path)


def _resolve_profile(section_id: str, section_path: str) -> SectionPromptProfile | None:
    key = _profile_key(section_id, section_path)
    return _SECTION_PROFILES.get(key)


def _append_line(lines: List[str], label: str, value: Any, *, max_chars: int = 220) -> None:
    text = _clip(value, max_chars=max_chars)
    if text:
        lines.append(f"- {label}: {text}")


def _collect_row_values(rows: Iterable[Dict[str, Any]], key: str) -> List[str]:
    values: List[str] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        text = _compact(row.get(key))
        normalized = text.lower()
        if not text or normalized in seen:
            continue
        seen.add(normalized)
        values.append(text)
    return values


def _dict_or_empty(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _row_dicts(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, dict)]


def _string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [_compact(item) for item in value if _compact(item)]


def _structured_context_lines(mode: str, details: Dict[str, Any]) -> List[str]:
    matriz = _dict_or_empty(details.get("matriz_consistencia"))
    operacionalizacion_vi = _dict_or_empty(details.get("operacionalizacion_vi"))
    operacionalizacion_vd = _dict_or_empty(details.get("operacionalizacion_vd"))
    vi_rows = _row_dicts(operacionalizacion_vi.get("filas"))
    vd_rows = _row_dicts(operacionalizacion_vd.get("filas"))
    vi_dimensions = _collect_row_values(vi_rows, "dimension") or _string_list(
        matriz.get("dimensiones_variable_independiente")
    )
    vd_dimensions = _collect_row_values(vd_rows, "dimension") or _string_list(
        matriz.get("dimensiones_variable_dependiente")
    )
    technique_candidates = (
        _collect_row_values(vi_rows, "tecnica_instrumentos")
        + _collect_row_values(vd_rows, "tecnica_instrumentos")
        + _collect_row_values(vd_rows, "metodo_tecnica")
        + _collect_row_values(vi_rows, "metodo_tecnica")
    )
    lines: List[str] = []

    if mode in {"project_overview", "problem_overview", "problem_detail", "justification", "delimitations"}:
        _append_line(lines, "Titulo del proyecto", details.get("titulo"))
        _append_line(lines, "Linea de investigacion", details.get("linea_investigacion"))
        _append_line(lines, "Objeto de estudio", details.get("objeto_estudio"))
        _append_line(lines, "Problema general", matriz.get("problema_general"))
        _append_line(lines, "Objetivo general", matriz.get("objetivo_general"))
        _append_line(
            lines,
            "Variable independiente",
            matriz.get("variable_independiente") or details.get("variable_independiente"),
        )
        _append_line(lines, "Dimensiones VI", _join_list(vi_dimensions))
        _append_line(
            lines,
            "Variable dependiente",
            matriz.get("variable_dependiente") or details.get("variable_dependiente"),
        )
        _append_line(lines, "Dimensiones VD", _join_list(vd_dimensions))
        _append_line(
            lines,
            "Lugar de ejecucion",
            details.get("lugar_ejecucion") or details.get("lugar"),
        )
        _append_line(lines, "Unidad de analisis", details.get("unidad_analisis"))
        _append_line(lines, "Horizonte temporal", details.get("temporal") or details.get("anio"))
        if mode == "problem_detail":
            _append_line(lines, "Tipo de investigacion", details.get("tipo") or matriz.get("tipo_investigacion"))
            _append_line(
                lines, "Nivel de investigacion", details.get("nivel_investigacion") or matriz.get("nivel_investigacion")
            )
            _append_line(lines, "Enfoque", details.get("enfoque") or matriz.get("enfoque_investigacion"))
            _append_line(lines, "Diseno", details.get("diseno_investigacion") or matriz.get("diseno"))
            _append_line(lines, "Poblacion", details.get("poblacion") or matriz.get("poblacion"))
            _append_line(lines, "Muestra", details.get("muestra") or matriz.get("muestra"))
            _append_line(
                lines, "Problemas especificos", _join_list(matriz.get("problemas_especificos") or [], max_items=4)
            )
            _append_line(
                lines, "Objetivos especificos", _join_list(matriz.get("objetivos_especificos") or [], max_items=4)
            )
            _append_line(
                lines, "Hipotesis especificas", _join_list(matriz.get("hipotesis_especificas") or [], max_items=4)
            )

    if mode == "matrix_core":
        _append_line(lines, "Problema general", matriz.get("problema_general"))
        _append_line(
            lines,
            "Problemas especificos",
            _join_list(matriz.get("problemas_especificos") or [], max_items=4),
        )
        _append_line(lines, "Objetivo general", matriz.get("objetivo_general"))
        _append_line(
            lines,
            "Objetivos especificos",
            _join_list(matriz.get("objetivos_especificos") or [], max_items=4),
        )
        _append_line(lines, "Hipotesis general", matriz.get("hipotesis_general"))
        _append_line(
            lines,
            "Hipotesis especificas",
            _join_list(matriz.get("hipotesis_especificas") or [], max_items=4),
        )
        _append_line(
            lines,
            "Variable independiente",
            matriz.get("variable_independiente") or details.get("variable_independiente"),
        )
        _append_line(
            lines,
            "Variable dependiente",
            matriz.get("variable_dependiente") or details.get("variable_dependiente"),
        )
        _append_line(lines, "Unidad de analisis", details.get("unidad_analisis"))
        _append_line(lines, "Lugar", details.get("lugar_ejecucion") or details.get("lugar"))
        _append_line(lines, "Temporal", details.get("temporal") or details.get("anio"))

    if mode in {"theory_overview", "backgrounds", "theoretical_bases", "conceptual_frame", "basic_terms"}:
        _append_line(lines, "Tema o titulo de trabajo", details.get("titulo"))
        _append_line(lines, "Variable independiente", details.get("variable_independiente"))
        _append_line(
            lines,
            "Definicion conceptual VI",
            operacionalizacion_vi.get("definicion_conceptual"),
            max_chars=260,
        )
        _append_line(
            lines,
            "Definicion operacional VI",
            operacionalizacion_vi.get("definicion_operacional"),
            max_chars=260,
        )
        _append_line(lines, "Dimensiones VI", _join_list(vi_dimensions))
        _append_line(lines, "Variable dependiente", details.get("variable_dependiente"))
        _append_line(
            lines,
            "Definicion conceptual VD",
            operacionalizacion_vd.get("definicion_conceptual"),
            max_chars=260,
        )
        _append_line(
            lines,
            "Definicion operacional VD",
            operacionalizacion_vd.get("definicion_operacional"),
            max_chars=260,
        )
        _append_line(lines, "Dimensiones VD", _join_list(vd_dimensions))
        _append_line(
            lines,
            "Tema OCDE",
            _join_list(
                [
                    details.get("tema_ocde_1"),
                    details.get("tema_ocde_2"),
                    details.get("tema_ocde_3"),
                ],
                max_items=3,
            ),
        )

    if mode in {"hypothesis_overview", "hypotheses", "operationalization"}:
        _append_line(lines, "Hipotesis general", matriz.get("hipotesis_general"))
        _append_line(
            lines,
            "Hipotesis especificas",
            _join_list(matriz.get("hipotesis_especificas") or [], max_items=4),
        )
        _append_line(lines, "Variable independiente", details.get("variable_independiente"))
        _append_line(lines, "Dimensiones VI", _join_list(vi_dimensions))
        _append_line(lines, "Variable dependiente", details.get("variable_dependiente"))
        _append_line(lines, "Dimensiones VD", _join_list(vd_dimensions))
        if mode == "operationalization":
            _append_line(
                lines,
                "Indicadores VI",
                _join_list(_collect_row_values(vi_rows, "indicador"), max_items=6),
            )
            _append_line(
                lines,
                "Indicadores VD",
                _join_list(_collect_row_values(vd_rows, "indicador"), max_items=6),
            )

    if mode in {
        "methodology_overview",
        "design",
        "method",
        "population_sample",
        "study_place",
        "techniques_instruments",
        "data_processing",
        "ethics",
        "schedule",
        "budget",
    }:
        _append_line(
            lines,
            "Tipo de investigacion",
            details.get("tipo") or matriz.get("tipo_investigacion"),
        )
        _append_line(
            lines,
            "Enfoque",
            details.get("enfoque") or matriz.get("enfoque_investigacion"),
        )
        _append_line(
            lines,
            "Nivel",
            details.get("nivel_investigacion") or matriz.get("nivel_investigacion"),
        )
        _append_line(lines, "Diseno", details.get("diseno_investigacion") or matriz.get("diseno"))
        _append_line(lines, "Poblacion", details.get("poblacion") or matriz.get("poblacion"))
        _append_line(lines, "Muestra", details.get("muestra") or matriz.get("muestra"))
        _append_line(
            lines,
            "Lugar de estudio",
            details.get("lugar_ejecucion") or details.get("lugar"),
        )
        _append_line(lines, "Unidad de analisis", details.get("unidad_analisis"))
        _append_line(
            lines,
            "Tecnicas registradas",
            matriz.get("tecnicas") or _join_list(technique_candidates, max_items=5),
        )
        _append_line(lines, "Instrumentos registrados", matriz.get("instrumentos"))
        _append_line(
            lines,
            "Procesamiento de datos",
            matriz.get("procesamiento_datos"),
            max_chars=260,
        )

    return lines


def _problem_figure_contract(details: Dict[str, Any]) -> List[str]:
    title = _compact(details.get("titulo")) or "el proyecto"
    variable_independiente = _compact(details.get("variable_independiente")) or "la variable independiente"
    variable_dependiente = _compact(details.get("variable_dependiente")) or "la variable dependiente"
    lugar = _compact(details.get("lugar_ejecucion") or details.get("lugar")) or "el contexto local"
    matriz = _dict_or_empty(details.get("matriz_consistencia"))
    vi_dimensions = _join_list(_string_list(matriz.get("dimensiones_variable_independiente")), max_items=4, empty="")
    vd_dimensions = _join_list(_string_list(matriz.get("dimensiones_variable_dependiente")), max_items=3, empty="")
    return [
        "Figuras obligatorias para 1.1 (desarrollalas como guia textual, no como imagen):",
        (
            f"- Figura 1.1 Diagrama de Pareto de modos de falla en flota CAT 24M: "
            f"explica que debe graficarse para {title}; "
            "indica que el usuario debe construir una tabla base con columnas sistema/modo de falla, frecuencia, "
            "porcentaje individual y porcentaje acumulado; ordenar de mayor a menor, usar barras para frecuencia, "
            "curva acumulada en eje secundario y linea de corte del 80 %. Tambien debe precisar el titulo tecnico "
            "de la figura, el eje X con los sistemas o modos, el eje Y izquierdo con frecuencia absoluta o relativa, "
            "el eje Y derecho con porcentaje acumulado, el orden descendente de las barras, y una lectura final sobre "
            "los pocos vitales que explican la mayor parte de la indisponibilidad y justifican focalizar el RCM."
        ),
        (
            f"- Figura 1.2 Analisis de Causa-Efecto de Baja Disponibilidad (Ishikawa): "
            f"explica como construir el diagrama "
            f"para la brecha del problema en {lugar}; incluye problema central, "
            "ramas 6M (Metodos, Medicion, Mano de Obra, Medio Ambiente, Maquinaria, Materiales), "
            "subcausas por rama y la interpretacion final. Debe indicar que cada rama tenga al menos dos subcausas "
            "concretas, describir como se distribuyen visualmente sobre la espina central y cerrar conectando Metodos "
            "con la estrategia de mantenimiento actual y Medio Ambiente/Maquinaria con las condiciones de operacion "
            "del activo."
        ),
        (
            "- Figura 1.3 Matriz de Relevancia para el filtrado de alternativas de solucion: "
            "explica como comparar alternativas de solucion; "
            "incluye al menos una opcion descartada y dos preseleccionadas, con criterios de "
            "viabilidad tecnica, viabilidad economica y alineamiento con la causa raiz. Debe indicar la estructura "
            "de columnas, como marcar la decision final de cada alternativa y por que la alternativa RCM aparece "
            "como solucion estructural porque ataca la metodologia de mantenimiento y no solo contiene sus efectos."
        ),
        (
            f"- Figura 1.4 Matriz de Priorizacion de soluciones factibles: "
            f"explica como ponderar alternativas para elegir la mas conveniente "
            f"frente a {variable_dependiente}; incluye criterios ponderados, pesos, puntajes, total ponderado "
            f"y cierre justificando por que {variable_independiente} es la mejor alternativa. Si las dimensiones "
            f"VI registradas son {vi_dimensions or 'las dimensiones de la variable independiente'} y las dimensiones "
            f"VD son {vd_dimensions or 'las dimensiones de la variable dependiente'}, usa esa relacion para explicar "
            "por que la priorizacion soporta el resto del proyecto. Debe indicar ademas la escala de 1 a 10, "
            "el criterio de mayor peso, la forma de calcular el total ponderado y la lectura final que valida la "
            "seleccion de la alternativa principal."
        ),
    ]


def build_format_editorial_contract(format_id: str | None) -> str:
    if not _is_target_format(format_id):
        return ""
    return "\n".join(
        [
            "Contrato editorial global del formato:",
            "- Documento objetivo: proyecto de tesis de maestria UNAC con "
            "enfoque cuantitativo, no una tesis ya concluida.",
            "- Usa los datos estructurados del Excel y del proyecto como "
            "verdad operativa; no inventes hechos, resultados ni mediciones "
            "no registradas.",
            "- Busca parecerte a un entregable tecnico bien hecho en "
            "estructura, densidad argumental y tono ingenieril, pero sin "
            "copiar frases ni parrafos literales.",
            "- Mantiene coherencia terminologica de mantenimiento, "
            "confiabilidad y disponibilidad durante todo el documento.",
            "- Cuando la seccion tenga un rango de palabras especifico, "
            "respeta ese rango por encima de reglas genericas heredadas.",
            "- En capitulos padre, redacta solo aperturas breves si luego existen subsecciones detalladas.",
            "- En secciones tabulares o estructuradas, prioriza texto "
            "puente y no reinventes tablas ya capturadas en el proyecto.",
        ]
    )


def build_section_editorial_context(
    *,
    format_id: str | None,
    section_id: str,
    section_path: str,
    values: Dict[str, Any] | None,
) -> str:
    if not _is_target_format(format_id):
        return ""
    profile = _resolve_profile(section_id, section_path)
    if profile is None:
        return ""

    details = normalize_maestria_details(values or {})
    lines: List[str] = [
        "Contrato editorial especifico de esta seccion:",
        f"- Rango de palabras aceptable: {profile.word_range}.",
        f"- Proposito: {profile.purpose}",
        "- Estructura interna esperada:",
    ]
    lines.extend(f"  {index}. {item}" for index, item in enumerate(profile.structure, start=1))
    lines.append("- Criterios de calidad:")
    lines.extend(f"  - {item}" for item in profile.quality_rules)

    context_lines = _structured_context_lines(profile.context_mode, details)
    if context_lines:
        lines.append("Hechos estructurados relevantes del proyecto:")
        lines.extend(context_lines)

    if (
        _profile_key(section_id, section_path)
        == "i. planteamiento del problema/1.1 descripcion de la realidad problematica"
    ):
        lines.extend(_problem_figure_contract(details))

    return "\n".join(lines)


def build_stable_project_memory_snapshot(format_id: str | None, values: Dict[str, Any] | None) -> str:
    if not _is_target_format(format_id):
        return ""
    details = normalize_maestria_details(values or {})
    matriz = details.get("matriz_consistencia") or {}
    items = [
        ("titulo", details.get("titulo")),
        ("objeto_estudio", details.get("objeto_estudio")),
        ("variable_independiente", details.get("variable_independiente")),
        (
            "dimensiones_vi",
            _join_list(list(matriz.get("dimensiones_variable_independiente") or []), max_items=4, empty=""),
        ),
        ("variable_dependiente", details.get("variable_dependiente")),
        (
            "dimensiones_vd",
            _join_list(list(matriz.get("dimensiones_variable_dependiente") or []), max_items=4, empty=""),
        ),
        ("problema_general", matriz.get("problema_general")),
        ("objetivo_general", matriz.get("objetivo_general")),
        ("tipo", details.get("tipo") or matriz.get("tipo_investigacion")),
        ("enfoque", details.get("enfoque") or matriz.get("enfoque_investigacion")),
        ("diseno", details.get("diseno_investigacion") or matriz.get("diseno")),
        ("poblacion", details.get("poblacion") or matriz.get("poblacion")),
        ("muestra", details.get("muestra") or matriz.get("muestra")),
        ("lugar", details.get("lugar_ejecucion") or details.get("lugar")),
        ("temporal", details.get("temporal") or details.get("anio")),
    ]
    selected: List[str] = []
    for key, value in items:
        text = _clip(value, max_chars=100)
        if text:
            selected.append(f"{key}={text}")
    return "; ".join(selected[:10])
