# ruff: noqa: E501
from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Sequence

from app.core.services.maestria_payload_mapper import normalize_maestria_details
from app.core.services.ai.project_fact_registry import build_project_fact_registry
from app.core.services.ai.unac_quality_profile import (
    is_unac_maintenance_project,
    load_unac_maintenance_profile,
    requirements_for_section_path,
)

_TARGET_FORMATS = {
    "unac-proyecto-cual",
    "unac-proyecto-cuant",
    "unac-maestria-cuant",
}


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
        word_range="1300 a 1450 palabras narrativas, sin contar titulos de figuras, fuentes ni guias azules",
        purpose=(
            "Construir una realidad problematica completa de tesis universitaria, no un resumen ejecutivo: "
            "contexto operativo, antecedentes con autores e indicadores, diagnostico local, interpretacion "
            "tecnica de Pareto, Ishikawa, matrices de decision y cierre metodologico con variables. "
            "Debe seguir el ejemplo guia del profesor en el orden narrativo antes y despues de cada figura."
        ),
        structure=(
            (
                "Parrafo 1 (120 a 160 palabras): contexto operativo macro de la mineria a cielo abierto, continuidad "
                "operativa, vias de acarreo, rol estrategico de las motoniveladoras CAT 24M, fallas funcionales "
                "imprevistas, baja disponibilidad y necesidad de una estrategia centrada en confiabilidad. "
                "No inicies directamente con el RCM."
            ),
            (
                "Parrafo 2 (200 a 250 palabras): antecedentes internacionales con autores, año, pais, equipo "
                "o sistema analizado, problema tecnico e indicadores concretos de disponibilidad, confiabilidad, "
                "mantenibilidad, MTBF, MTTR o impacto productivo. Incluye referencias especificas como Jakkula "
                "et al. (2021) en India y Nouri et al. (2023) en Iran si corresponden al caso."
            ),
            (
                "Parrafo 3 (130 a 180 palabras): antecedentes latinoamericanos con pais, autor, año, industria "
                "o equipo, problema de disponibilidad, uso de RCM, taxonomia, criticidad o mejora de mantenimiento, "
                "y resultado tecnico. Conecta con baja disponibilidad, correctivos frecuentes y falta de planes "
                "basados en confiabilidad."
            ),
            (
                "Parrafo 4 (180 a 230 palabras): antecedentes peruanos recientes en maquinaria minera. Usa "
                "Flores (2024) con camiones Caterpillar 785 y Chavez (2024) con perforadoras Everdigm T450 cuando "
                "el caso CAT 24M no tenga otras fuentes registradas. Menciona disponibilidad inicial/final, MTBF, "
                "MTTR o mejora proyectada solo si el dato esta en la guia o datos del proyecto."
            ),
            (
                "Parrafo 5 (170 a 220 palabras): diagnostico local de la flota CAT 24M en Sierra Central. Incluye "
                "obligatoriamente disponibilidad inherente promedio actual 85 %, target corporativo 90 %, brecha "
                "negativa 5 %, Sistema de Implementos o Mando de Circulo, Tren de Potencia, Sistema Hidraulico, "
                "75 % de eventos de parada, efecto en vias de acarreo, correctivos, MTTR y MTBF."
            ),
            (
                "Parrafo 6 (50 a 70 palabras): introduce el Pareto antes de Figura 1.1. Explica que se usa para "
                "jerarquizar fallas, evitar dispersion de recursos, aplicar la regla 80/20 e identificar pocos "
                "vitales. Debe cerrar con referencia a la Figura 1.1."
            ),
            (
                "Figura 1.1: solo referenciarla en el parrafo analitico; el sistema insertara el bloque controlado "
                "con fuente y guia azul. No redactes debajo una guia tecnica manual."
            ),
            (
                "Parrafo 7 (130 a 170 palabras): interpreta Figura 1.1. Explica sistemas criticos, 75 % de los "
                "eventos de parada, pocos vitales, Sistema de Implementos o Mando de Circulo, Tren de Potencia, "
                "Sistema Hidraulico, efecto sobre disponibilidad, MTBF y MTTR."
            ),
            (
                "Parrafo 8 (50 a 70 palabras): transicion a Ishikawa antes de Figura 1.2. Explica que, tras "
                "identificar sistemas criticos, se analizan causas raiz mediante Diagrama de Causa-Efecto para "
                "ordenar factores de metodos, maquinaria, mano de obra, materiales, medicion y medio ambiente."
            ),
            (
                "Figura 1.2: solo referenciarla dentro del parrafo causal; el sistema insertara el bloque controlado "
                "con fuente y guia azul. No redactes debajo una guia tecnica manual."
            ),
            (
                "Parrafo 9 (170 a 220 palabras): interpreta Figura 1.2. Explica problema sistemico, causa raiz "
                "principal en Metodos, mantenimiento rigido por horas motor, ausencia de condicion real, carga "
                "dinamica, severidad ambiental, polvo, silice abrasiva, altitud, temperatura, desgaste acelerado "
                "y necesidad de RCM."
            ),
            (
                "Parrafo 10 (60 a 80 palabras): presenta alternativas antes de Figura 1.3. Explica que se evalua "
                "renovacion de flota, sustitucion de componentes, monitoreo en linea, optimizacion de stock y RCM "
                "mediante matriz de relevancia por viabilidad tecnica, economica y estrategica."
            ),
            (
                "Figura 1.3: solo referenciarla dentro del parrafo de comparacion; el sistema insertara el bloque "
                "controlado con fuente y guia azul. No redactes debajo una guia tecnica manual."
            ),
            (
                "Parrafo 11 (130 a 170 palabras): interpreta Figura 1.3. Explica alternativas descartadas y razones: "
                "renovacion anticipada por alto CAPEX, sustitucion masiva como solucion inmediata sin reducir "
                "recurrencia, monitoreo en linea con inversion y capacitacion, optimizacion de stock como reduccion "
                "de espera sin atacar frecuencia, y RCM como alternativa estructural."
            ),
            (
                "Parrafo 12 (50 a 70 palabras): presenta priorizacion antes de Figura 1.4. Explica matriz ponderada, "
                "impacto en disponibilidad como criterio principal, costo de implementacion, sostenibilidad, retorno "
                "y seleccion de la solucion optima."
            ),
            (
                "Figura 1.4: solo referenciarla dentro del parrafo de priorizacion; el sistema insertara el bloque "
                "controlado con fuente y guia azul. No redactes debajo una guia tecnica manual."
            ),
            (
                "Parrafo 13 (170 a 220 palabras): interpreta Figura 1.4 cuantitativamente. Incluye obligatoriamente "
                "Impacto en Disponibilidad con peso 50 %, Costo de Implementacion con peso 30 %, RCM con puntaje "
                "global 7.9, optimizacion de stock con puntaje global 4.6, diferencia entre reducir MTTR y evitar "
                "recurrencia, y efecto del RCM sobre MTBF y MTTR."
            ),
            (
                "Parrafo 14 (150 a 200 palabras): cierre con Variable Independiente: Plan de Mantenimiento Centrado "
                "en Confiabilidad; Variable Dependiente: Disponibilidad Inherente; SAE JA1011:2024; ISO 14224; "
                "taxonomia de activos; analisis de criticidad; AMEF; implementacion del plan; MTBF, MTTR y cierre "
                "de brecha entre 85 % y 90 %."
            ),
        ),
        quality_rules=(
            "La seccion debe sentirse analitica y sustentada, no descriptiva sin criterio.",
            "Parrafos 5 y 6: diagnostico local y apertura especifica del Pareto antes de insertar Figura 1.1.",
            "La voz debe parecer la de un ingeniero redactando un proyecto formal, no la de un resumen de chatbot.",
            "El cuerpo narrativo debe quedar entre 1300 y 1450 palabras; objetivo recomendado: 1380 palabras.",
            "No uses vinetas, listas ni subtitulos internos dentro del desarrollo final de 1.1.",
            "No uses frases vagas como 'estudios internacionales han demostrado' sin autor, año, pais e indicador.",
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
                "El cuerpo academico debe interpretar el problema y la decision tecnica; no debe explicar pasos "
                "manuales para dibujar las figuras. Esos pasos pertenecen unicamente a la guia azul controlada."
            ),
            "no redactes guias manuales dentro del cuerpo narrativo de 1.1.",
            (
                "Cada figura debe quedar con este orden: rotulo Figura 1.x, espacio visual de la figura, "
                "Fuente: Elaboracion propia y debajo una guia tecnica de elaboracion en color azul, "
                "sin cursiva y sin asteriscos."
            ),
            (
                "No escribas bloques manuales en texto plano como 'Figura 1.2' en una linea, titulo en otra, "
                "'*Fuente: Elaboracion propia.*' y '*Guia tecnica:*'. Esos bloques quedan prohibidos."
            ),
            (
                "No escribas parrafos sueltos debajo de una figura que empiecen con 'Diagrama de Pareto...', "
                "'Diagrama de Ishikawa...', 'Matriz de Relevancia...', 'Matriz de Priorizacion...' o "
                "'Guia tecnica:'. Eso duplica el bloque controlado y sera eliminado."
            ),
            (
                "Ubica cada figura inmediatamente despues del parrafo que la explica; "
                "no agrupes Figura 1.1, Figura 1.2, Figura 1.3 y Figura 1.4 al final de la seccion."
            ),
            (
                "Antes de cada figura debe existir un parrafo largo y especifico que la justifique: antes de "
                "Figura 1.1 va el diagnostico local/Pareto; antes de Figura 1.2 va la causa raiz/Ishikawa; "
                "antes de Figura 1.3 va la evaluacion de alternativas; antes de Figura 1.4 va la priorizacion "
                "ponderada. No insertes una figura despues de una frase de una sola linea."
            ),
            (
                "Despues de cada figura debe existir una interpretacion tecnica: despues de Figura 1.1 Pareto; "
                "despues de Figura 1.2 causa raiz; despues de Figura 1.3 relevancia; despues de Figura 1.4 "
                "priorizacion cuantitativa y luego cierre de variables."
            ),
            (
                "No cuentes la guia azul como desarrollo academico de la realidad problematica; por eso cada "
                "parrafo narrativo debe aportar diagnostico, causa, decision o cierre tecnico propio."
            ),
            "No escribas el texto visible 'Figura pendiente de elaboracion propia' dentro del cuerpo del documento.",
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
            "Formular unicamente el problema general y los problemas especificos en "
            "forma interrogativa, respetando el orden dimensional fijado por la matriz y sin "
            "agregar desarrollo explicativo."
        ),
        structure=(
            "Problema general como subtitulo independiente.",
            "Una pregunta para el problema general.",
            "Problemas especificos como subtitulo independiente.",
            "Dos o mas preguntas especificas derivadas de dimensiones o focos del estudio.",
            (
                "Si existe orden de dimensiones de la variable dependiente, "
                "replicarlo exactamente en las preguntas especificas."
            ),
        ),
        quality_rules=(
            "No agregues explicaciones extensas ni justificacion adicional.",
            "Usa exactamente los rotulos Problema general y Problemas especificos.",
            "Cada pregunta debe mantener coherencia exacta con variables, "
            "unidad de analisis, lugar y horizonte temporal.",
            "No inviertas el orden de las dimensiones especificas por reescritura estilistica.",
            (
                "Si el proyecto trabaja disponibilidad inherente con dimensiones "
                "confiabilidad y mantenibilidad, conserva el orden "
                "confiabilidad -> mantenibilidad."
            ),
            "No agregues ningun parrafo final despues de las preguntas.",
        ),
        context_mode="matrix_core",
    ),
    "i. planteamiento del problema/1.3 objetivos": SectionPromptProfile(
        word_range="120 a 220 palabras",
        purpose=(
            "Plantear el objetivo general y los objetivos especificos como espejo operativo del problema formulado, "
            "sin alterar el orden dimensional ni agregar comentario adicional."
        ),
        structure=(
            "Objetivo general como subtitulo independiente.",
            "Objetivo general con verbo en infinitivo y relacion explicita con la propuesta.",
            "Objetivos especificos como subtitulo independiente.",
            "Objetivos especificos coherentes con problemas especificos y dimensiones relevantes.",
            (
                "Replica exactamente el mismo orden de los problemas especificos "
                "y de las dimensiones de la variable dependiente."
            ),
        ),
        quality_rules=(
            "Usa exactamente los rotulos Objetivo general y Objetivos especificos.",
            "No uses verbos ambiguos ni objetivos demasiado amplios.",
            "No agregues parrafos introductorios innecesarios.",
            (
                "Si el objetivo general ya coincide con la variable dependiente "
                "principal del proyecto, mantenlo sin reformularlo creativamente."
            ),
            ("No inviertas el orden de confiabilidad y mantenibilidad cuando esas sean las dimensiones del estudio."),
            "No agregues explicaciones ni justificaciones debajo de los objetivos.",
        ),
        context_mode="matrix_core",
    ),
    "i. planteamiento del problema/1.4 justificacion": SectionPromptProfile(
        word_range="860 a 1070 palabras",
        purpose=(
            "Sustentar por que el proyecto merece ejecutarse mediante seis justificaciones diferenciadas, "
            "densas y tecnicamente aterrizadas al caso minero, sin caer en formulaciones genericas. "
            "La salida debe incluir obligatoriamente los subtitulos numerados 1.4.1 a 1.4.6."
        ),
        structure=(
            (
                "Escribe primero la linea exacta '1.4.1 Justificacion normativa' y debajo un solo parrafo "
                "de 145 a 175 palabras; prioriza SAE JA1011 "
                "como eje tecnico del RCM, incorpora ISO 14224:2016 para taxonomia/registro/analisis de fallas "
                "y vincula D. S. N.° 024-2016-EM con mantenimiento mecanico, prevencion de accidentes, trazabilidad "
                "y cumplimiento normativo."
            ),
            (
                "Escribe la linea exacta '1.4.2 Justificacion teorica' y debajo un solo parrafo de 135 a 165 "
                "palabras; centra el argumento en "
                "confiabilidad operacional, Moubray, seis patrones de falla, analisis funcional, AMEF, MTBF, MTTR "
                "y disponibilidad inherente de la flota CAT 24M."
            ),
            (
                "Escribe la linea exacta '1.4.3 Justificacion practica' y debajo un solo parrafo de 130 a 160 "
                "palabras; presenta el RCM como "
                "instrumento de gestion tecnica, contrapone correctivos ineficaces frente a CBM e inspeccion tecnica, "
                "y conecta motoniveladoras, vias de acarreo, desgaste de camiones y productividad minera."
            ),
            (
                "Escribe la linea exacta '1.4.4 Justificacion metodologica' y debajo un solo parrafo de 120 a 150 "
                "palabras; usa SAE JA1011 para "
                "ordenar analisis funcional y de fallas, AMEF para priorizar modos criticos y diseno preexperimental "
                "longitudinal con preprueba/posprueba y comparacion de MTBF/MTTR."
            ),
            (
                "Escribe la linea exacta '1.4.5 Justificacion economica' y debajo un solo parrafo de 145 a 175 "
                "palabras; desarrolla OPEX, costos "
                "correctivos no programados, repuestos de emergencia, ciclo de vida de componentes criticos, desgaste "
                "de neumaticos, combustible, velocidad de ciclo y lucro cesante."
            ),
            (
                "Escribe la linea exacta '1.4.6 Justificacion social' y debajo un solo parrafo de 140 a 170 "
                "palabras; aterriza riesgos laborales, "
                "calidad de vida del capital humano, vias uniformes, vibraciones de cuerpo entero, ISO 2631, dolores "
                "lumbares/cervicales, descansos medicos, estres, fatiga y seguridad del personal tecnico."
            ),
        ),
        quality_rules=(
            "No redactes una introduccion general de 1.4; empieza directamente con 1.4.1 Justificacion normativa.",
            (
                "Los subtitulos 1.4.1, 1.4.2, 1.4.3, 1.4.4, 1.4.5 y 1.4.6 deben aparecer "
                "literalmente como lineas independientes, antes del parrafo correspondiente."
            ),
            "Cada tipo de justificacion debe aportar un criterio distinto; "
            "no repitas el mismo argumento con otro titulo.",
            "Cada subtitulo debe desarrollar un parrafo sustantivo, no una frase corta.",
            "Usa tiempo futuro y enfoque de proyecto cuando describas beneficios esperados.",
            (
                "Evita frases de relleno sobre aporte a la literatura, competitividad, "
                "comunidad o sostenibilidad si no estan claramente ancladas al caso."
            ),
            (
                "No permitas que ISO 55000 desplace a SAE JA1011 cuando la seccion "
                "se refiera al sustento normativo del RCM."
            ),
            (
                "Manten un tono academico-ingenieril denso, con prioridad en "
                "mantenimiento, confiabilidad operacional y contexto minero."
            ),
            (
                "No cierres la seccion con un parrafo global adicional; el desarrollo "
                "debe terminar en la justificacion social."
            ),
        ),
        context_mode="justification",
    ),
    "i. planteamiento del problema/1.5 delimitaciones de la investigacion": SectionPromptProfile(
        word_range="320 a 420 palabras",
        purpose=(
            "Definir delimitaciones teorica, temporal y espacial con precision operativa, "
            "alineadas al caso minero y sin introducir restricciones no declaradas. "
            "La salida debe incluir obligatoriamente los subtitulos numerados 1.5.1 a 1.5.3."
        ),
        structure=(
            (
                "Escribe primero la linea exacta '1.5.1 Delimitacion teorica' y debajo un solo parrafo de "
                "120 a 155 palabras; delimita el estudio a "
                "ingenieria de mantenimiento y confiabilidad operacional, con RCM, SAE JA1011, Moubray, "
                "ISO 14224:2016, analisis de criticidad y modos de falla; centra disponibilidad inherente, "
                "confiabilidad y mantenibilidad; excluye TPM y Lean Maintenance."
            ),
            (
                "Escribe la linea exacta '1.5.2 Delimitacion temporal' y debajo un solo parrafo de 90 a 120 "
                "palabras; define 2025 como horizonte, "
                "separado en fase de diagnostico y fase de ejecucion/monitoreo, y justificalo por temporada seca, "
                "temporada humeda y horas de operacion estadisticamente significativas."
            ),
            (
                "Escribe la linea exacta '1.5.3 Delimitacion espacial' y debajo un solo parrafo de 110 a 145 "
                "palabras; ubica la investigacion en una "
                "unidad minera a cielo abierto de Junin/Sierra Central cuando esos datos existan, y distingue area "
                "operativa y soporte tecnico con vias de acarreo, frentes de trabajo, pendientes, suelos abrasivos, "
                "alta polucion, talleres de mantenimiento y oficinas de planeamiento."
            ),
        ),
        quality_rules=(
            "No redactes una introduccion general de 1.5; empieza directamente con 1.5.1 Delimitacion teorica.",
            (
                "Los subtitulos 1.5.1, 1.5.2 y 1.5.3 deben aparecer literalmente como lineas independientes, "
                "antes del parrafo correspondiente."
            ),
            "No confundas delimitaciones con limitaciones del estudio.",
            "Cada delimitacion debe tener un parrafo completo y aplicarse al caso real.",
            "Cada delimitacion debe vincularse con el proyecto real y no con una definicion generica.",
            (
                "No introduzcas autores, normas o enfoques que desplacen el eje "
                "RCM -> SAE JA1011 -> Moubray -> ISO 14224:2016 si el proyecto "
                "es de confiabilidad operacional."
            ),
            (
                "No agregues exclusiones temporales no declaradas por el usuario "
                "ni cierres generales al final de la seccion."
            ),
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
        word_range="2400 a 3000 palabras si el formato no pide menos",
        purpose=(
            "Redactar antecedentes empiricos extensos, especificos y trazables, separando evidencia "
            "internacional y nacional sin figuras, tablas ni placeholders visibles."
        ),
        structure=(
            "Inicia directamente con el subtitulo '2.1.1 Antecedentes internacionales' como una linea independiente y limpia, sin markdown, sin asteriscos ni negritas y sin introduccion generica.",
            "Antecedentes internacionales: cinco antecedentes si el paquete no indica otra cantidad. Cada antecedente debe desarrollarse en su propio parrafo.",
            "Luego coloca el subtitulo '2.1.2 Antecedentes nacionales' como una linea independiente y limpia, sin markdown, sin asteriscos ni negritas.",
            "Antecedentes nacionales: cinco antecedentes si el paquete no indica otra cantidad. Cada antecedente debe desarrollarse en su propio parrafo.",
            (
                "Cada antecedente debe ser un parrafo largo de 190 a 300 palabras con autor(es) y año, "
                "titulo exacto, problema abordado, pregunta o proposito, objetivo, tipo/enfoque/diseno, "
                "unidad de analisis o muestra, proceso o fases aplicadas, tecnicas/instrumentos/herramientas, "
                "resultados concretos, conclusion y aporte al proyecto actual."
            ),
        ),
        quality_rules=(
            "No insertes figuras, tablas, mapas conceptuales ni formulas en 2.1 Antecedentes.",
            "No uses libros base, normas o manuales como antecedentes empiricos; reservalos para bases teoricas.",
            "Evita antecedentes vagos como 'un estudio realizado por una universidad' si no hay autor, año y titulo.",
            "No inventes autores, titulos ni cifras; si el dato no esta disponible, redacta con trazabilidad verificable.",
            "Exige resultados numericos o hallazgos concretos cuando el antecedente los reporte.",
            "No agregues cierres genericos como 'los antecedentes revisados confirman'.",
            "Cada antecedente debe cerrar con el aporte concreto al titulo, variables, dimensiones o contexto real.",
        ),
        context_mode="backgrounds",
    ),
    "ii. marco teorico/2.2 bases teoricas": SectionPromptProfile(
        word_range="1500 a 2200 palabras",
        purpose=(
            "Desarrollar bases teoricas densas, academicas y jerarquizadas por subtitulos 2.2.x derivados del "
            "titulo, variables, dimensiones, poblacion, muestra y contexto real del proyecto, con patron "
            "preciso de figuras y formulas cuando correspondan."
        ),
        structure=(
            "Cada subtema debe iniciar con una linea independiente tipo 2.2.x Titulo del subtema.",
            "Cada subtitulo 2.2.x debe desarrollar 2 a 3 parrafos tecnicos antes de cambiar de subtema.",
            "Subtema teorico principal de la variable independiente: fundamento, definicion, alcance y autores clave.",
            "Subtema de proceso, modelo, arquitectura, procedimiento o flujo si el proyecto lo requiere.",
            "Subtema de clasificacion, taxonomia, categorias o niveles si aporta a las dimensiones.",
            "Subtema de herramienta, metodo, instrumento, tecnica o tecnologia asociada al estudio.",
            "Subtemas de indicadores, indices o relaciones cuantitativas con formula solo si el tema los requiere.",
            "Subtema de equipo, sistema, objeto de estudio, poblacion, tecnologia o caso aplicado cuando corresponda.",
            (
                "Si el tema es de mantenimiento/confiabilidad, cubre explicitamente: RCM, proceso del RCM, "
                "taxonomia ISO 14224, AMEF, disponibilidad inherente, confiabilidad, mantenibilidad y objeto de estudio."
            ),
        ),
        quality_rules=(
            "No insertes matriz de consistencia ni matriz de operacionalizacion dentro de 2.2 Bases teoricas.",
            "No generes tablas Markdown ni TABLE_JSON en 2.2; las figuras deben ser bloques FIGURE_JSON.",
            "Los subtitulos 2.2.x deben quedar como lineas independientes y limpias, no incrustados dentro del mismo parrafo.",
            "No uses **negritas**, ##, bullets ni numeraciones de lista para simular subtitulos; usa lineas textuales 2.2.x.",
            "No arrastres nombres, autores, normas, indicadores o equipos del ejemplo guia si el proyecto no trata ese campo.",
            "Si el proyecto es de mantenimiento, usa teorias de mantenimiento, confiabilidad, disponibilidad y activos.",
            "Si el proyecto es de software, usa arquitectura, datos, interfaz, seguridad, algoritmos o metodologia tecnica.",
            "Si el proyecto es de educacion, usa teorias de aprendizaje, didactica, competencias, evaluacion y rendimiento.",
            "Si el proyecto es de estructuras, usa cargas, resistencia, normas, materiales, modelamiento y diseno.",
            "Si el proyecto es de salud, usa fundamentos clinicos, epidemiologia, diagnostico, intervencion e instrumentos.",
            "Cada subtema debe incluir citas parenteticas verificables en formato Autor (año) o (Autor, año).",
            "No inicies 2.2 con figuras; cada figura debe aparecer despues de parrafos que expliquen el concepto.",
            "No coloques figuras consecutivas sin texto teorico entre ellas.",
            "Usa formulas solo si el tema requiere indicadores, calculos, indices, ratios o ecuaciones.",
            "Toda formula debe ir despues de definir el concepto y sus variables, y antes de una interpretacion.",
            "Si el caso es mantenimiento/confiabilidad, replica el patron del entregable 1 en cantidad y ubicacion de subtitulos, figuras y formulas, sin copiar frases literales.",
            "No muestres placeholders tecnicos ni frases como 'reemplazar por la figura validada por el autor'.",
        ),
        context_mode="theoretical_bases",
    ),
    "ii. marco teorico/2.3 marco conceptual": SectionPromptProfile(
        word_range="500 a 650 palabras",
        purpose=(
            "Delimitar variables y dimensiones reales del proyecto como constructos conceptuales breves, "
            "sin convertir la seccion en otra base teorica."
        ),
        structure=(
            "Variable independiente: usar el nombre exacto registrado en el proyecto.",
            "Un parrafo conceptual breve de 60 a 90 palabras para la variable independiente.",
            "Dimensiones de la variable independiente: una entrada textual por cada dimension registrada.",
            "Variable dependiente: usar el nombre exacto registrado en el proyecto.",
            "Un parrafo conceptual breve de 60 a 90 palabras para la variable dependiente.",
            "Dimensiones de la variable dependiente: una entrada textual por cada dimension registrada.",
        ),
        quality_rules=(
            "No generes tabla, figura, mapa conceptual ni formula en 2.3.",
            "Usa subtitulos textuales del tipo 'Variable independiente: ...' y 'Dimension: ...'.",
            "No repitas formulas ni desarrollos largos ya tratados en bases teoricas.",
            "Mantiene definiciones cortas, tecnicas y vinculadas al tema real, no a un caso fijo.",
        ),
        context_mode="conceptual_frame",
    ),
    "ii. marco teorico/2.4 definicion de terminos basicos": SectionPromptProfile(
        word_range="434 a 500 palabras; exactamente trece definiciones",
        purpose="Definir terminos tecnicos basicos directamente utiles para entender el proyecto.",
        structure=(
            "Lista textual con formato exacto 'Termino. Definicion...'.",
            (
            "Incluye exactamente trece terminos derivados del area, variable independiente, dimensiones de la variable "
                "independiente, variable dependiente, dimensiones de la variable dependiente e indicadores principales."
            ),
            "Ordena los terminos desde conceptos base del area hasta variables, dimensiones e indicadores.",
        ),
        quality_rules=(
            "No uses dos puntos despues del termino; usa punto.",
            "No insertes figura, tabla, formula ni cierre final en 2.4.",
            "No agregues frases finales como 'estos terminos constituyen' o 'en conjunto, estas definiciones'.",
            "Mantiene citas entre parentesis cuando correspondan al campo real del proyecto.",
            "No hardcodees terminos de mantenimiento si el proyecto pertenece a otro dominio.",
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
        word_range="80 a 140 palabras",
        purpose=(
            "Declarar la hipotesis general y las hipotesis especificas en forma afirmativa, verificable "
            "y con el mismo orden dimensional del documento guia."
        ),
        structure=(
            "Hipotesis general como subtitulo independiente.",
            "Hipotesis general sobre mejora de la disponibilidad inherente.",
            "Hipotesis especificas como subtitulo independiente.",
            "Primera hipotesis especifica: mejora de la confiabilidad.",
            "Segunda hipotesis especifica: mejora de la mantenibilidad.",
        ),
        quality_rules=(
            "Usa exactamente los rotulos Hipotesis general e Hipotesis especificas.",
            "El orden obligatorio de hipotesis especificas es confiabilidad -> mantenibilidad.",
            "No conviertas las hipotesis en preguntas.",
            "No introduzcas nuevas variables o dimensiones no capturadas en la matriz.",
            "No agregues figuras, tablas ni explicacion adicional en 3.1.",
        ),
        context_mode="hypotheses",
    ),
    "iii. hipotesis y variables/3.2 operacionalizacion de variable": SectionPromptProfile(
        word_range="80 a 160 palabras de puente textual; sin bloques estructurados",
        purpose=(
            "Redactar solo un puente explicativo de la operacionalizacion. "
            "Las Tablas 3.1 y 3.2 se renderizan desde los datos estructurados del proyecto."
        ),
        structure=(
            "Explica brevemente que la operacionalizacion organiza variables, dimensiones, indicadores e instrumentos.",
            "Mantente en texto narrativo breve y coherente con VI, VD y sus dimensiones.",
        ),
        quality_rules=(
            "No generes TABLE_JSON, FIGURE_JSON ni FORMULA_JSON en 3.2.",
            "No reconstruyas manualmente tablas 3.1/3.2 ni cambies su estructura institucional.",
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
        word_range="300 a 380 palabras",
        purpose=(
            "Sustentar el tipo, nivel o alcance y diseno metodologico reales del proyecto con "
            "texto academico sobrio; usar esquema textual solo si el diseno lo justifica."
        ),
        structure=(
            "Parrafo 1 (90 a 120 palabras): tipo de investigacion y justificacion segun el proposito del proyecto.",
            "Parrafo 2 (70 a 100 palabras): nivel o alcance y relacion con problema, objetivos, variables o propuesta.",
            (
                "Parrafo 3 (120 a 160 palabras): diseno de investigacion, corte temporal, unidad analizada "
                "y forma de contrastar la hipotesis o evaluar la propuesta."
            ),
            "Esquema textual opcional si el diseno lo requiere: M O\u2081 X O\u2082.",
            "Leyenda textual del esquema: M, O\u2081, X y O\u2082, adaptada a la muestra, medicion e intervencion reales.",
        ),
        quality_rules=(
            "Los hechos estructurados Tipo, Nivel y Diseno son obligatorios y prevalecen sobre cualquier supuesto del modelo.",
            "No declares un nivel correlacional o descriptivo si el Nivel registrado es explicativo.",
            "No declares un diseno no experimental o transversal si el Diseno registrado es preexperimental con preprueba y posprueba.",
            "No desarrolles el enfoque cuantitativo aqui; reserva su explicacion central para 4.2.",
            "No generes Tabla 4.1, matriz metodologica, FIGURE_JSON ni figura numerada.",
            "El esquema M O\u2081 X O\u2082 debe quedar como texto o FORMULA_JSON, nunca como figura.",
            "No fuerces el esquema preexperimental si el diseno real es no experimental, transversal u otro.",
            "No agregues cierre generico sobre combinacion de elementos metodologicos.",
            "No hardcodees mantenimiento, mineria, unidad minera, fechas ni equipos del ejemplo guia.",
        ),
        context_mode="design",
    ),
    "iv. metodologia del proyecto/4.2 metodo de investigacion": SectionPromptProfile(
        word_range="240 a 320 palabras",
        purpose=(
            "Explicar el enfoque, metodo o estrategia analitica y logica operativa de la investigacion "
            "segun los datos reales del proyecto."
        ),
        structure=(
            "Parrafo 1 (80 a 110 palabras): enfoque de investigacion y tipo de informacion que se recolectara.",
            (
                "Parrafo 2 (80 a 110 palabras): metodo o estrategia analitica, como hipotetico-deductivo, "
                "inductivo, analitico-sintetico, sistemico, comparativo o validacion tecnica."
            ),
            "Parrafo 3 (80 a 110 palabras): logica operativa para diagnosticar, disenar, implementar, comparar o evaluar.",
        ),
        quality_rules=(
            "No fuerces enfoque cuantitativo ni metodo hipotetico-deductivo si el proyecto registra otro enfoque.",
            "No menciones indicadores, tecnicas o herramientas del ejemplo guia salvo que existan en el proyecto.",
            "No generes figuras, tablas ni cierres genericos en 4.2.",
        ),
        context_mode="method",
    ),
    "iv. metodologia del proyecto/4.3 poblacion y muestra": SectionPromptProfile(
        word_range="50 a 90 palabras",
        purpose="Definir tecnicamente la poblacion, la muestra y el criterio de muestreo del estudio.",
        structure=(
            "Un solo parrafo breve.",
            "Poblacion: usa la poblacion registrada en Detalles o matriz de consistencia.",
            "Muestra: usa la muestra registrada y el tipo de muestreo si esta disponible.",
            "Justificacion breve: tamano reducido, accesibilidad, representatividad, criterios tecnicos o necesidad del estudio.",
        ),
        quality_rules=(
            "No agregues desarrollo extenso, estratificacion innecesaria, figuras ni tablas.",
            "No contradigas los datos estructurados del proyecto.",
            "No hardcodees cantidades, equipos, aulas, pacientes, usuarios o instituciones no registradas.",
        ),
        context_mode="population_sample",
    ),
    "iv. metodologia del proyecto/4.4 lugar de estudio": SectionPromptProfile(
        word_range="110 a 160 palabras",
        purpose="Describir el lugar de estudio en un solo parrafo denso y operativo, sin soporte visual.",
        structure=(
            "Ubicacion geografica, institucional, empresarial, comunitaria, clinica, academica o tecnica registrada.",
            "Areas, procesos, espacios, unidades o actores incluidos en el estudio.",
            "Condiciones operativas, tecnicas, sociales, ambientales o pedagogicas relevantes.",
            "Relacion directa del lugar o contexto con el problema de investigacion.",
        ),
        quality_rules=(
            "Redacta un solo parrafo; no agregues figura de ubicacion, tabla ni cierre adicional.",
            "No conviertas la seccion en descripcion turistica o institucional extensa.",
            "No hardcodees unidad minera, Junin, altitud, talleres o vias de acarreo si no aparecen en el proyecto.",
        ),
        context_mode="study_place",
    ),
    (
        "iv. metodologia del proyecto/4.5 tecnicas e instrumentos para la recoleccion de la informacion"
    ): SectionPromptProfile(
        word_range="240 a 320 palabras",
        purpose=(
            "Sustentar en un solo parrafo denso las tecnicas e instrumentos reales de recoleccion, "
            "el tipo de informacion obtenida y la validacion correspondiente."
        ),
        structure=(
            "Un solo parrafo denso.",
            "Indica el numero de tecnicas principales registradas o pertinentes al diseno.",
            "Tecnica 1, instrumento asociado y tipo de informacion que aportara.",
            "Tecnica 2, instrumento asociado y tipo de informacion que aportara.",
            "Tecnica 3 o tecnica complementaria si corresponde al proyecto.",
            (
                "Incluye encuesta, entrevista, observacion, analisis documental, pruebas, rubricas, ensayos, "
                "metricas, registros o juicio de expertos solo si son coherentes con el tema real."
            ),
        ),
        quality_rules=(
            "No generes Tabla 4.2, figura, flujo metodologico ni frase de sintesis de tabla.",
            "No enumeres tecnicas sin explicar para que sirven dentro del estudio.",
            "No hardcodees manuales, normas, historiales, software, indicadores o instrumentos del ejemplo guia.",
        ),
        context_mode="techniques_instruments",
    ),
    "iv. metodologia del proyecto/4.6 analisis y procesamiento de datos": SectionPromptProfile(
        word_range="250 a 330 palabras",
        purpose=(
            "Explicar el procesamiento de datos en cuatro parrafos metodologicos: organizacion, diagnostico, "
            "herramientas analiticas y comparacion, interpretacion o validacion final."
        ),
        structure=(
            "Parrafo 1: estructuracion, codificacion y depuracion de datos, registros, respuestas o mediciones.",
            (
                "Parrafo 2: diagnostico inicial o linea base mediante indicadores, pruebas, metricas, categorias "
                "o criterios pertinentes."
            ),
            "Parrafo 3: herramientas analiticas especificas del proyecto, segun tema y diseno.",
            (
                "Parrafo 4: analisis comparativo, interpretativo, estadistico, tecnico o de contrastacion final "
                "para responder objetivos e hipotesis."
            ),
        ),
        quality_rules=(
            "No generes Tabla 4.3, flujo de procesamiento, figura ni placeholder tecnico.",
            "No fuerces Pareto, AMEF, NPR, indicadores de mantenimiento, graficas ni cuadros si el tema no lo requiere.",
            "No declares resultados estadisticos ya obtenidos; describe el procedimiento futuro.",
            "No agregues cierre generico sin relacion con objetivos, hipotesis, propuesta o variables.",
        ),
        context_mode="data_processing",
    ),
    "iv. metodologia del proyecto/4.7 aspectos eticos": SectionPromptProfile(
        word_range="280 a 360 palabras",
        purpose=(
            "Precisar compromisos eticos sobre marco institucional o normativo aplicable, probidad, "
            "transparencia, objetividad, confidencialidad y consentimiento."
        ),
        structure=(
            (
                "Parrafo 1 (70 a 100 palabras): marco etico institucional, reglamento, comite, norma o codigo "
                "aplicable al formato o proyecto."
            ),
            (
                "Parrafo 2 (90 a 120 palabras): probidad, transparencia, autenticidad de datos, no manipulacion, "
                "no fabricacion de resultados y respeto de propiedad intelectual."
            ),
            (
                "Parrafo 3 (110 a 150 palabras): objetividad, confidencialidad, consentimiento informado, "
                "anonimato, participacion voluntaria y uso academico responsable de la informacion."
            ),
        ),
        quality_rules=(
            "No hardcodees UNAC ni Resolucion N. 260-19-CU salvo que el formato institucional o usuario lo indique.",
            "No generes figura, tabla, flujo metodologico ni cierre visual.",
            "No conviertas la seccion en un listado normativo vacio; aterriza los compromisos al proyecto.",
        ),
        context_mode="ethics",
    ),
    "v. cronograma de actividades": SectionPromptProfile(
        word_range="solo tabla estructurada; sin parrafos narrativos",
        purpose=(
            "Generar exclusivamente la Tabla 5.1 de cronograma con la estructura institucional de GicaTesis "
            "para proyecto de tesis UNAC, adaptando contenido al tema actual."
        ),
        structure=(
            (
                "Salida obligatoria exacta: UN SOLO bloque delimitado como "
                "<<<TABLE_JSON ... TABLE_JSON>>> sin texto antes ni despues."
            ),
            (
                "Usa esta estructura fija del objeto: "
                "{tipo:'tabla', id:'tabla_5_1_cronograma_actividades', titulo:'Tabla 5.1 Cronograma de actividades', "
                "orientacion:'landscape', subtipo:'cronograma_actividades', encabezados:[13 columnas], "
                "filas:[35 filas], anio:'<ANIO>', meses:['Ene'..'Dic'], simbolo_marca:'●', "
                "filas_fase:[1,5,9,13,17,21,26,30], celdas_combinadas:[...], celdas_fusionadas:[...], estilo:{...}}."
            ),
            (
                "Plantilla completa de filas obligatoria (sin saltarla): "
                "fila 0 = meses; fila 1 = FASE 1; filas 2-4 = actividades 1.x; fila 5 = FASE 2; filas 6-8 = actividades 2.x; "
                "fila 9 = FASE 3; filas 10-12 = actividades 3.x; fila 13 = FASE 4; filas 14-16 = actividades 4.x; "
                "fila 17 = FASE 5; filas 18-20 = actividades 5.x; fila 21 = FASE 6; filas 22-25 = actividades 6.x; "
                "fila 26 = FASE 7; filas 27-29 = actividades 7.x; fila 30 = FASE 8; filas 31-34 = actividades 8.x."
            ),
            (
                "Distribucion obligatoria de actividades por fase: "
                "FASE 1=3 actividades, FASE 2=3, FASE 3=3, FASE 4=3, "
                "FASE 5=3, FASE 6=4, FASE 7=3, FASE 8=4. "
                "Total obligatorio: 26 actividades."
            ),
            (
                "Fusiona encabezado y fases: en celdas_fusionadas incluye "
                "(-1,0, filas_span=2, cols_span=1), (-1,1, filas_span=1, cols_span=12) y cada fase con cols_span=13."
            ),
            (
                "Estilo obligatorio: modelo_referencia='cronograma_actividades.docx', "
                "titulo_capitulo='V. CRONOGRAMA DE ACTIVIDADES', titulo_exacto=true, orientacion_pagina='landscape', "
                "margenes_reducidos=true."
            ),
            (
                "Plantilla completa obligatoria (estructura exacta; reemplaza FASE/ACTIVIDAD/<ANIO> con contenido del tema actual):\n"
                "<<<TABLE_JSON\n"
                "{\n"
                '  "tipo": "tabla",\n'
                '  "id": "tabla_5_1_cronograma_actividades",\n'
                '  "titulo": "Tabla 5.1 Cronograma de actividades",\n'
                '  "encabezados": ["FASES Y ACTIVIDADES", "<ANIO>", "", "", "", "", "", "", "", "", "", "", ""],\n'
                '  "filas": [\n'
                '    ["", "Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Set", "Oct", "Nov", "Dic"],\n'
                '    ["FASE 1", "", "", "", "", "", "", "", "", "", "", "", ""],\n'
                '    ["ACTIVIDAD 1.1", "", "X", "", "", "", "", "", "", "", "", "", ""],\n'
                '    ["ACTIVIDAD 1.2", "", "X", "", "", "", "", "", "", "", "", "", ""],\n'
                '    ["ACTIVIDAD 1.3", "", "", "X", "", "", "", "", "", "", "", "", ""],\n'
                '    ["FASE 2", "", "", "", "", "", "", "", "", "", "", "", ""],\n'
                '    ["ACTIVIDAD 2.1", "", "", "X", "", "", "", "", "", "", "", "", ""],\n'
                '    ["ACTIVIDAD 2.2", "", "", "", "X", "", "", "", "", "", "", "", ""],\n'
                '    ["ACTIVIDAD 2.3", "", "", "", "X", "", "", "", "", "", "", "", ""],\n'
                '    ["FASE 3", "", "", "", "", "", "", "", "", "", "", "", ""],\n'
                '    ["ACTIVIDAD 3.1", "", "", "", "", "X", "", "", "", "", "", "", ""],\n'
                '    ["ACTIVIDAD 3.2", "", "", "", "", "X", "", "", "", "", "", "", ""],\n'
                '    ["ACTIVIDAD 3.3", "", "", "", "", "", "X", "", "", "", "", "", ""],\n'
                '    ["FASE 4", "", "", "", "", "", "", "", "", "", "", "", ""],\n'
                '    ["ACTIVIDAD 4.1", "", "", "", "", "", "X", "", "", "", "", "", ""],\n'
                '    ["ACTIVIDAD 4.2", "", "", "", "", "", "", "X", "", "", "", "", ""],\n'
                '    ["ACTIVIDAD 4.3", "", "", "", "", "", "", "X", "", "", "", "", ""],\n'
                '    ["FASE 5", "", "", "", "", "", "", "", "", "", "", "", ""],\n'
                '    ["ACTIVIDAD 5.1", "", "", "", "", "", "", "", "X", "", "", "", ""],\n'
                '    ["ACTIVIDAD 5.2", "", "", "", "", "", "", "", "X", "", "", "", ""],\n'
                '    ["ACTIVIDAD 5.3", "", "", "", "", "", "", "", "", "X", "", "", ""],\n'
                '    ["FASE 6", "", "", "", "", "", "", "", "", "", "", "", ""],\n'
                '    ["ACTIVIDAD 6.1", "", "", "", "", "", "", "", "", "X", "", "", ""],\n'
                '    ["ACTIVIDAD 6.2", "", "", "", "", "", "", "", "", "", "X", "", ""],\n'
                '    ["ACTIVIDAD 6.3", "", "", "", "", "", "", "", "", "", "X", "", ""],\n'
                '    ["ACTIVIDAD 6.4", "", "", "", "", "", "", "", "", "", "", "X", ""],\n'
                '    ["FASE 7", "", "", "", "", "", "", "", "", "", "", "", ""],\n'
                '    ["ACTIVIDAD 7.1", "", "", "", "", "", "", "", "", "", "", "X", ""],\n'
                '    ["ACTIVIDAD 7.2", "", "", "", "", "", "", "", "", "", "", "X", ""],\n'
                '    ["ACTIVIDAD 7.3", "", "", "", "", "", "", "", "", "", "", "", "X"],\n'
                '    ["FASE 8", "", "", "", "", "", "", "", "", "", "", "", ""],\n'
                '    ["ACTIVIDAD 8.1", "", "", "", "", "", "", "", "", "", "", "", "X"],\n'
                '    ["ACTIVIDAD 8.2", "", "", "", "", "", "", "", "", "", "", "", "X"],\n'
                '    ["ACTIVIDAD 8.3", "", "", "", "", "", "", "", "", "", "", "", "X"],\n'
                '    ["ACTIVIDAD 8.4", "", "", "", "", "", "", "", "", "", "", "", "X"]\n'
                "  ],\n"
                '  "orientacion": "landscape",\n'
                '  "subtipo": "cronograma_actividades",\n'
                '  "anio": "<ANIO>",\n'
                '  "meses": ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Set", "Oct", "Nov", "Dic"],\n'
                '  "simbolo_marca": "\\u25cf",\n'
                '  "filas_fase": [1, 5, 9, 13, 17, 21, 26, 30],\n'
                '  "celdas_combinadas": [\n'
                '    {"fila": -1, "fila_fin": 0, "col_inicio": 0, "col_fin": 0, "texto": "FASES Y ACTIVIDADES"},\n'
                '    {"fila": -1, "col_inicio": 1, "col_fin": 12, "texto": "<ANIO>"},\n'
                '    {"fila": 1, "col_inicio": 0, "col_fin": 12, "texto": "FASE 1"},\n'
                '    {"fila": 5, "col_inicio": 0, "col_fin": 12, "texto": "FASE 2"},\n'
                '    {"fila": 9, "col_inicio": 0, "col_fin": 12, "texto": "FASE 3"},\n'
                '    {"fila": 13, "col_inicio": 0, "col_fin": 12, "texto": "FASE 4"},\n'
                '    {"fila": 17, "col_inicio": 0, "col_fin": 12, "texto": "FASE 5"},\n'
                '    {"fila": 21, "col_inicio": 0, "col_fin": 12, "texto": "FASE 6"},\n'
                '    {"fila": 26, "col_inicio": 0, "col_fin": 12, "texto": "FASE 7"},\n'
                '    {"fila": 30, "col_inicio": 0, "col_fin": 12, "texto": "FASE 8"}\n'
                "  ],\n"
                '  "celdas_fusionadas": [\n'
                '    {"fila": -1, "col": 0, "filas_span": 2, "cols_span": 1, "texto": "FASES Y ACTIVIDADES", "bold": true, "alignment": "center"},\n'
                '    {"fila": -1, "col": 1, "filas_span": 1, "cols_span": 12, "texto": "<ANIO>", "bold": true, "alignment": "center"},\n'
                '    {"fila": 1, "col": 0, "filas_span": 1, "cols_span": 13, "texto": "FASE 1", "bold": true, "alignment": "center"},\n'
                '    {"fila": 5, "col": 0, "filas_span": 1, "cols_span": 13, "texto": "FASE 2", "bold": true, "alignment": "center"},\n'
                '    {"fila": 9, "col": 0, "filas_span": 1, "cols_span": 13, "texto": "FASE 3", "bold": true, "alignment": "center"},\n'
                '    {"fila": 13, "col": 0, "filas_span": 1, "cols_span": 13, "texto": "FASE 4", "bold": true, "alignment": "center"},\n'
                '    {"fila": 17, "col": 0, "filas_span": 1, "cols_span": 13, "texto": "FASE 5", "bold": true, "alignment": "center"},\n'
                '    {"fila": 21, "col": 0, "filas_span": 1, "cols_span": 13, "texto": "FASE 6", "bold": true, "alignment": "center"},\n'
                '    {"fila": 26, "col": 0, "filas_span": 1, "cols_span": 13, "texto": "FASE 7", "bold": true, "alignment": "center"},\n'
                '    {"fila": 30, "col": 0, "filas_span": 1, "cols_span": 13, "texto": "FASE 8", "bold": true, "alignment": "center"}\n'
                "  ],\n"
                '  "estilo": {\n'
                '    "modelo_referencia": "cronograma_actividades.docx",\n'
                '    "titulo_capitulo": "V. CRONOGRAMA DE ACTIVIDADES",\n'
                '    "titulo_exacto": true,\n'
                '    "titulo_tamano_pt": 9.5,\n'
                '    "titulo_space_after_pt": 6,\n'
                '    "ancho_tabla": "100%",\n'
                '    "ancho_columnas": [8.91, 1.59, 1.59, 1.59, 1.59, 1.59, 1.59, 1.59, 1.59, 1.59, 1.59, 1.59, 1.59],\n'
                '    "alineacion_actividades": "left",\n'
                '    "alineacion_meses": "center",\n'
                '    "encabezados_negrita": true,\n'
                '    "fases_negrita": true,\n'
                '    "fases_centradas": true,\n'
                '    "bordes": "grid",\n'
                '    "fuente_tamano_pt": 8,\n'
                '    "fuente_meses_pt": 8,\n'
                '    "fuente_actividades_pt": 8,\n'
                '    "fuente_fases_pt": 8,\n'
                '    "fuente_marcas_pt": 10,\n'
                '    "compactar_cronograma": false,\n'
                '    "orientacion_pagina": "landscape",\n'
                '    "margenes_reducidos": true\n'
                "  }\n"
                "}\n"
                "TABLE_JSON>>>"
            ),
        ),
        quality_rules=(
            "No redactes introduccion, explicacion, lista, subseccion ni parrafo posterior.",
            "No devuelvas dos bloques TABLE_JSON; debe ser exactamente uno.",
            "Entrega un unico bloque TABLE_JSON valido con tipo='tabla', encabezados y filas no vacios.",
            "No uses placeholders finales (FASE X, ACTIVIDAD X.Y, <ANIO>); reemplazalos por contenido real del tema.",
            "No cambies claves, orden logico, cantidad de columnas (13), cantidad de filas (35) ni filas_fase.",
            "No alteres el numero de fases (8) ni la distribucion de actividades por fase (3,3,3,3,3,4,3,4).",
            "Mantiene coherencia temporal con marcas '●' y evita filas/columnas vacias sin sentido.",
        ),
        context_mode="schedule",
    ),
    "vi. presupuesto": SectionPromptProfile(
        word_range="solo tabla estructurada; sin parrafos narrativos",
        purpose=(
            "Generar exclusivamente la Tabla 6.1 de presupuesto con la estructura institucional de GicaTesis "
            "para proyecto de tesis UNAC, adaptando rubros y montos al tema actual."
        ),
        structure=(
            (
                "Salida obligatoria exacta: UN SOLO bloque delimitado como "
                "<<<TABLE_JSON ... TABLE_JSON>>> sin texto antes ni despues."
            ),
            (
                "Usa esta estructura fija del objeto: "
                "{tipo:'tabla', id:'tabla_6_1_presupuesto_investigacion', titulo:'Tabla 6.1 Presupuesto de investigacion', "
                "orientacion:'portrait', subtipo:'presupuesto_investigacion', "
                "encabezados:['N°','DESCRIPCION DEL GASTO','CANTIDAD','COSTO UNIT. (S/.)','COSTO TOTAL (S/.)'], "
                "filas:[14 filas], filas_categoria:[0,2,7,11], fila_total:13, celdas_combinadas:[...], "
                "celdas_fusionadas:[...], estilo:{...}}."
            ),
            (
                "Plantilla completa de filas obligatoria (sin saltarla): "
                "fila 0 categoria 1, fila 1 item 1.1; fila 2 categoria 2, filas 3-6 items 2.1..2.4; "
                "fila 7 categoria 3, filas 8-10 items 3.1..3.3; fila 11 categoria 4, fila 12 item 4.1; "
                "fila 13 TOTAL GENERAL."
            ),
            (
                "Distribucion obligatoria de items por categoria: "
                "Categoria 1=1 item, Categoria 2=4 items, Categoria 3=3 items, Categoria 4=1 item. "
                "Total obligatorio: 9 items."
            ),
            (
                "Fusiona categorias y total en columnas 0..3 (celdas_combinadas y celdas_fusionadas) "
                "con alineacion left para categorias y center para total."
            ),
            (
                "Estilo obligatorio: modelo_referencia='presupuesto_investigacion_vertical.docx', "
                "titulo_capitulo='VI. PRESUPUESTO', titulo_exacto=true, orientacion_pagina='portrait'."
            ),
            (
                "Plantilla completa obligatoria (estructura exacta; reemplaza CATEGORIA/ITEM y montos con contenido del tema actual):\n"
                "<<<TABLE_JSON\n"
                "{\n"
                '  "tipo": "tabla",\n'
                '  "id": "tabla_6_1_presupuesto_investigacion",\n'
                '  "titulo": "Tabla 6.1 Presupuesto de investigacion",\n'
                '  "encabezados": ["N°", "DESCRIPCION DEL GASTO", "CANTIDAD", "COSTO UNIT. (S/.)", "COSTO TOTAL (S/.)"],\n'
                '  "filas": [\n'
                '    ["1. CATEGORIA 1", "", "", "", "2,000.00"],\n'
                '    ["1.1", "ITEM 1.1", "1", "2,000.00", "2,000.00"],\n'
                '    ["2. CATEGORIA 2", "", "", "", "4,849.00"],\n'
                '    ["2.1", "ITEM 2.1", "1", "2,999.00", "2,999.00"],\n'
                '    ["2.2", "ITEM 2.2", "12", "50.00", "600.00"],\n'
                '    ["2.3", "ITEM 2.3", "4", "250.00", "1,000.00"],\n'
                '    ["2.4", "ITEM 2.4", "1", "250.00", "250.00"],\n'
                '    ["3. CATEGORIA 3", "", "", "", "560.00"],\n'
                '    ["3.1", "ITEM 3.1", "1", "150.00", "150.00"],\n'
                '    ["3.2", "ITEM 3.2", "1", "350.00", "350.00"],\n'
                '    ["3.3", "ITEM 3.3", "1", "60.00", "60.00"],\n'
                '    ["4. CATEGORIA 4", "", "", "", "370.00"],\n'
                '    ["4.1", "ITEM 4.1", "1", "370.00", "370.00"],\n'
                '    ["TOTAL GENERAL", "", "", "", "S/. 7,779.00"]\n'
                "  ],\n"
                '  "orientacion": "portrait",\n'
                '  "subtipo": "presupuesto_investigacion",\n'
                '  "filas_categoria": [0, 2, 7, 11],\n'
                '  "fila_total": 13,\n'
                '  "celdas_combinadas": [\n'
                '    {"fila": 0, "col_inicio": 0, "col_fin": 3, "texto": "1. CATEGORIA 1"},\n'
                '    {"fila": 2, "col_inicio": 0, "col_fin": 3, "texto": "2. CATEGORIA 2"},\n'
                '    {"fila": 7, "col_inicio": 0, "col_fin": 3, "texto": "3. CATEGORIA 3"},\n'
                '    {"fila": 11, "col_inicio": 0, "col_fin": 3, "texto": "4. CATEGORIA 4"},\n'
                '    {"fila": 13, "col_inicio": 0, "col_fin": 3, "texto": "TOTAL GENERAL"}\n'
                "  ],\n"
                '  "celdas_fusionadas": [\n'
                '    {"fila": 0, "col": 0, "filas_span": 1, "cols_span": 4, "texto": "1. CATEGORIA 1", "bold": true, "alignment": "left"},\n'
                '    {"fila": 2, "col": 0, "filas_span": 1, "cols_span": 4, "texto": "2. CATEGORIA 2", "bold": true, "alignment": "left"},\n'
                '    {"fila": 7, "col": 0, "filas_span": 1, "cols_span": 4, "texto": "3. CATEGORIA 3", "bold": true, "alignment": "left"},\n'
                '    {"fila": 11, "col": 0, "filas_span": 1, "cols_span": 4, "texto": "4. CATEGORIA 4", "bold": true, "alignment": "left"},\n'
                '    {"fila": 13, "col": 0, "filas_span": 1, "cols_span": 4, "texto": "TOTAL GENERAL", "bold": true, "alignment": "center"}\n'
                "  ],\n"
                '  "estilo": {\n'
                '    "modelo_referencia": "presupuesto_investigacion_vertical.docx",\n'
                '    "titulo_capitulo": "VI. PRESUPUESTO",\n'
                '    "titulo_exacto": true,\n'
                '    "titulo_tamano_pt": 10,\n'
                '    "titulo_space_after_pt": 10,\n'
                '    "ancho_tabla": "100%",\n'
                '    "ancho_columnas": [1.4, 8, 2, 3.2, 3.2],\n'
                '    "orientacion_pagina": "portrait",\n'
                '    "encabezados_negrita": true,\n'
                '    "categorias_negrita": true,\n'
                '    "total_negrita": true,\n'
                '    "alineacion_descripcion": "left",\n'
                '    "alineacion_numeros": "center",\n'
                '    "alineacion_costos": "right",\n'
                '    "bordes": "grid",\n'
                '    "fuente_tamano_pt": 9,\n'
                '    "fuente_encabezado_pt": 8.5,\n'
                '    "fuente_categoria_pt": 9,\n'
                '    "fuente_total_pt": 9\n'
                "  }\n"
                "}\n"
                "TABLE_JSON>>>"
            ),
        ),
        quality_rules=(
            "No redactes introduccion, explicacion, lista, subseccion ni parrafo posterior.",
            "No devuelvas dos bloques TABLE_JSON; debe ser exactamente uno.",
            "Entrega un unico bloque TABLE_JSON valido con tipo='tabla', encabezados y filas no vacios.",
            "No uses placeholders finales (CATEGORIA X, ITEM X.Y); reemplazalos por contenido real del tema.",
            "No cambies claves, cantidad de columnas (5), cantidad de filas (14), filas_categoria ni fila_total.",
            "No alteres el numero de categorias (4) ni la distribucion de items por categoria (1,4,3,1).",
            "Consistencia aritmetica obligatoria: suma de items = subtotales y suma de subtotales = total general.",
            "Formato monetario obligatorio: 1,250.00 y TOTAL GENERAL como 'S/. x,xxx.xx'.",
        ),
        context_mode="budget",
    ),
}
_SECTION_PROFILES["i. planteamiento del problema/1.5 delimitantes de la investigacion"] = _SECTION_PROFILES[
    "i. planteamiento del problema/1.5 delimitaciones de la investigacion"
]
_SECTION_PROFILES["iii. hipotesis y variables/3.1 hipotesis (general y especificas)"] = _SECTION_PROFILES[
    "iii. hipotesis y variables/3.1 hipotesis"
]
_SECTION_PROFILES["iv. metodologia"] = _SECTION_PROFILES["iv. metodologia del proyecto"]
_SECTION_PROFILES["iv. metodologia/4.1 diseno metodologico"] = _SECTION_PROFILES[
    "iv. metodologia del proyecto/4.1 diseno metodologico"
]
_SECTION_PROFILES["iv. metodologia/4.2 metodo de investigacion"] = _SECTION_PROFILES[
    "iv. metodologia del proyecto/4.2 metodo de investigacion"
]
_SECTION_PROFILES["iv. metodologia/4.3 poblacion y muestra"] = _SECTION_PROFILES[
    "iv. metodologia del proyecto/4.3 poblacion y muestra"
]
_SECTION_PROFILES["iv. metodologia/4.4 lugar de estudio"] = _SECTION_PROFILES[
    "iv. metodologia del proyecto/4.4 lugar de estudio"
]
_SECTION_PROFILES["iv. metodologia/4.5 tecnicas e instrumentos para la recoleccion de la informacion"] = (
    _SECTION_PROFILES["iv. metodologia del proyecto/4.5 tecnicas e instrumentos para la recoleccion de la informacion"]
)
_SECTION_PROFILES["iv. metodologia/4.6 analisis y procesamiento de datos"] = _SECTION_PROFILES[
    "iv. metodologia del proyecto/4.6 analisis y procesamiento de datos"
]
_SECTION_PROFILES["iv. metodologia/4.7 aspectos eticos"] = _SECTION_PROFILES[
    "iv. metodologia del proyecto/4.7 aspectos eticos"
]
_SECTION_PROFILES["iv. metodologia del proyecto/4.7 aspectos eticos en investigacion"] = _SECTION_PROFILES[
    "iv. metodologia del proyecto/4.7 aspectos eticos"
]
_SECTION_PROFILES["iv. metodologia/4.7 aspectos eticos en investigacion"] = _SECTION_PROFILES[
    "iv. metodologia del proyecto/4.7 aspectos eticos"
]
_SECTION_PROFILES["ii. revision de literatura/2.2 bases teoricas"] = _SECTION_PROFILES[
    "ii. marco teorico/2.2 bases teoricas"
]
_SECTION_PROFILES["v. cronograma"] = _SECTION_PROFILES["v. cronograma de actividades"]
_SECTION_PROFILES["cronograma"] = _SECTION_PROFILES["v. cronograma de actividades"]
_SECTION_PROFILES["cronograma de actividades"] = _SECTION_PROFILES["v. cronograma de actividades"]
_SECTION_PROFILES["presupuesto"] = _SECTION_PROFILES["vi. presupuesto"]
_SECTION_PROFILES["presupuesto de investigacion"] = _SECTION_PROFILES["vi. presupuesto"]

_SECTION_PROFILES["v. cronograma de actividades"] = SectionPromptProfile(
    word_range="solo tabla estructurada; sin parrafos narrativos",
    purpose=(
        "Generar exclusivamente un blueprint semantico del cronograma para proyecto de tesis UNAC. "
        "La IA solo define fases, actividades y rangos mensuales; GicaGen construira la tabla institucional final."
    ),
    structure=(
        (
            "Salida obligatoria exacta: UN SOLO bloque delimitado como "
            "<<<TABLE_JSON ... TABLE_JSON>>> sin texto antes ni despues."
        ),
        (
            "NO construyas la tabla institucional final. No escribas encabezados, filas, celdas_combinadas, "
            "celdas_fusionadas ni estilo del cronograma."
        ),
        (
            "Devuelve un objeto JSON con tipo='tabla' y subtipo='cronograma_plan'. "
            "Estructura obligatoria: {tipo:'tabla', subtipo:'cronograma_plan', anio:'2025 o anio del proyecto', "
            "fases:[{numero, titulo, actividades:[{numero, titulo, mes_inicio, mes_fin}]}]}."
        ),
        (
            "La distribucion semantica es fija: 8 fases y 26 actividades, con patron 3-3-3-3-3-4-3-4. "
            "Fase 1 = actividades 1.1 a 1.3; Fase 2 = 2.1 a 2.3; Fase 3 = 3.1 a 3.3; "
            "Fase 4 = 4.1 a 4.3; Fase 5 = 5.1 a 5.3; Fase 6 = 6.1 a 6.4; Fase 7 = 7.1 a 7.3; "
            "Fase 8 = 8.1 a 8.4."
        ),
        (
            "Cada actividad debe declarar mes_inicio y mes_fin como enteros del 1 al 12, donde 1=Ene, 2=Feb, "
            "3=Mar, 4=Abr, 5=May, 6=Jun, 7=Jul, 8=Ago, 9=Set, 10=Oct, 11=Nov, 12=Dic."
        ),
        (
            "Genera 8 fases nuevas y 26 actividades nuevas con tono academico + tecnico, coherentes con el tema, "
            "las variables, la metodologia, la poblacion y el contexto operacional del proyecto. No copies "
            "literalmente las fases del ejemplo institucional ni uses cronogramas genericos."
        ),
        (
            "Numeracion obligatoria: las fases deben empezar con '1.', '2.' ... '8.' y cada actividad con "
            "'1.1.', '1.2.' ... '8.4.' segun corresponda. No uses etiquetas finales tipo 'FASE 1', "
            "'ACTIVIDAD 1.1', '[FASE...]', '[ACTIVIDAD...]' o '<ANIO>'."
        ),
        (
            "Ventanas mensuales obligatorias por fase para asegurar coherencia: "
            "Fase 1 solo puede marcar Feb-Mar; Fase 2 Feb-Abr; Fase 3 Abr-Jun; Fase 4 Jun-Jul; "
            "Fase 5 Jul-Ago; Fase 6 Jul-Oct; Fase 7 Ago-Nov; Fase 8 Oct-Dic."
        ),
        (
            "Cada actividad debe tener al menos un rango mensual valido. Si ocupa varios meses, el rango debe ser "
            "contiguo y expresarse solo con mes_inicio..mes_fin, sin enumerar celdas."
        ),
        "Regla de anio: usa el anio del proyecto si el contexto lo indica; si no existe, usa 2025.",
        (
            "Ejemplo minimo de forma esperada: "
            "{tipo:'tabla', subtipo:'cronograma_plan', anio:'2025', fases:[{numero:1, titulo:'1. ...', "
            "actividades:[{numero:'1.1', titulo:'1.1. ...', mes_inicio:2, mes_fin:2}, ...]} ...]}."
        ),
    ),
    quality_rules=(
        "No redactes introduccion, explicacion, lista, subseccion ni parrafo posterior.",
        "No devuelvas dos bloques TABLE_JSON; debe ser exactamente uno.",
        "Entrega un unico bloque TABLE_JSON valido con tipo='tabla' y subtipo='cronograma_plan'.",
        "No generes la tabla institucional final ni inventes merges, filas o columnas manuales.",
        "No alteres el numero de fases (8) ni la distribucion de actividades por fase (3,3,3,3,3,4,3,4).",
        "No uses placeholders finales; reemplazalos por contenido real del tema.",
        "No coloques mes_inicio o mes_fin fuera de la ventana mensual permitida de su fase.",
        "No devuelvas fences markdown tipo ```json ni ```.",
        "Las fases y actividades deben sonar a proyecto de tesis tecnico aplicado al tema actual, no a cronograma generico.",
    ),
    context_mode="schedule",
)
_SECTION_PROFILES["v. cronograma"] = _SECTION_PROFILES["v. cronograma de actividades"]
_SECTION_PROFILES["cronograma"] = _SECTION_PROFILES["v. cronograma de actividades"]
_SECTION_PROFILES["cronograma de actividades"] = _SECTION_PROFILES["v. cronograma de actividades"]


def _profile_key(section_id: str, section_path: str) -> str:
    if _normalize_text(section_id) == "titulo-info-basica":
        return "titulo-info-basica"
    return _normalize_text(section_path)


def _is_theoretical_bases_key(key: str) -> bool:
    return key in {
        "ii. marco teorico/2.2 bases teoricas",
        "ii. revision de literatura/2.2 bases teoricas",
    }


def _resolve_profile(section_id: str, section_path: str) -> SectionPromptProfile | None:
    key = _profile_key(section_id, section_path)
    profile = _SECTION_PROFILES.get(key)
    if profile is not None:
        return profile

    # Allow schedule/budget subsection paths to inherit parent chapter contracts.
    if "cronograma" in key:
        schedule_profile = _SECTION_PROFILES.get("v. cronograma de actividades")
        if schedule_profile is not None:
            return schedule_profile
    if "presupuesto" in key:
        budget_profile = _SECTION_PROFILES.get("vi. presupuesto")
        if budget_profile is not None:
            return budget_profile
    return None


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
        _append_line(
            lines,
            "Orden obligatorio de dimensiones especificas",
            _join_list(vd_dimensions, max_items=4),
        )
        _append_line(lines, "Unidad de analisis", details.get("unidad_analisis"))
        _append_line(lines, "Lugar", details.get("lugar_ejecucion") or details.get("lugar"))
        _append_line(lines, "Temporal", details.get("temporal") or details.get("anio"))

    if mode == "justification":
        _append_line(lines, "Tipo de investigacion", details.get("tipo") or matriz.get("tipo_investigacion"))
        _append_line(lines, "Enfoque", details.get("enfoque") or matriz.get("enfoque_investigacion"))
        _append_line(lines, "Diseno", details.get("diseno_investigacion") or matriz.get("diseno"))
        _append_line(lines, "Poblacion", details.get("poblacion") or matriz.get("poblacion"))
        _append_line(lines, "Muestra", details.get("muestra") or matriz.get("muestra"))
        _append_line(
            lines,
            "Tecnicas registradas",
            matriz.get("tecnicas") or _join_list(technique_candidates, max_items=5),
        )
        _append_line(lines, "Instrumentos registrados", matriz.get("instrumentos"))
        _append_line(lines, "Procesamiento de datos", matriz.get("procesamiento_datos"), max_chars=260)
        _append_line(lines, "Hipotesis general", matriz.get("hipotesis_general"), max_chars=240)

    if mode == "delimitations":
        _append_line(lines, "Tipo de investigacion", details.get("tipo") or matriz.get("tipo_investigacion"))
        _append_line(lines, "Enfoque", details.get("enfoque") or matriz.get("enfoque_investigacion"))
        _append_line(lines, "Diseno", details.get("diseno_investigacion") or matriz.get("diseno"))
        _append_line(lines, "Poblacion", details.get("poblacion") or matriz.get("poblacion"))
        _append_line(lines, "Muestra", details.get("muestra") or matriz.get("muestra"))

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
        "Figuras obligatorias para 1.1 (mencionalas en el analisis, pero no redactes guias manuales):",
        (
            "Para cada figura, exige este orden exacto en el bloque final: Figura 1.x con titulo; Fuente: "
            "Elaboracion propia.; y justo debajo una guia tecnica azul, sin cursiva ni asteriscos. "
            "Ese bloque lo controla el sistema; no lo dupliques como texto normal."
        ),
        (
            "No escribas bloques Markdown manuales de figuras con lineas separadas tipo Figura 1.x, "
            "*Fuente:* o *Guia tecnica:*; las figuras deben quedar solo como bloque controlado."
        ),
        (
            "No escribas parrafos sueltos como 'Diagrama de Pareto de fallas...', "
            "'Diagrama de Ishikawa...', 'Matriz de Relevancia...' o 'Guia tecnica:'. "
            "En lugar de eso, redacta analisis real antes y despues de cada figura, como en el ejemplo guia."
        ),
        (
            "Patron obligatorio: parrafo largo de analisis -> Figura 1.1; parrafo largo de causa raiz -> "
            "Figura 1.2; parrafo largo de alternativas -> Figura 1.3; parrafo largo de priorizacion -> "
            "Figura 1.4; parrafo final de consecuencia. Nunca coloques una figura despues de una frase corta."
        ),
        (
            f"- Figura 1.1 Diagrama de Pareto de modos de falla en flota CAT 24M: "
            f"el parrafo anterior debe diagnosticar {title} con KPI, brecha, sistemas criticos y lectura 80/20. "
            "Debe parecerse al parrafo guia: disponibilidad inherente, brecha contra target, historial de fallas, "
            "sistemas acumulados y cierre 'tal como se aprecia en la Figura 1.1'."
        ),
        (
            f"- Figura 1.2 Analisis de Causa-Efecto de Baja Disponibilidad (Ishikawa): "
            f"el parrafo anterior debe explicar la brecha del problema en {lugar} con metodos, medicion, mano de obra, "
            "medio ambiente, maquinaria y materiales como categorias de diagnostico. Cierra conectando Metodos con "
            "la estrategia de mantenimiento actual y Medio Ambiente/Maquinaria con las condiciones de operacion, "
            "y referencia la Figura 1.2."
        ),
        (
            "- Figura 1.3 Matriz de Relevancia para el filtrado de alternativas de solucion: "
            "el parrafo anterior debe comparar alternativas, descartar una opcion inviable, reconocer una medida "
            "de contencion "
            "y justificar el RCM como solucion estructural porque ataca la metodologia de mantenimiento y no solo "
            "contiene sus efectos; debe cerrar con referencia a la Figura 1.3."
        ),
        (
            f"- Figura 1.4 Matriz de Priorizacion de soluciones factibles: "
            f"el parrafo anterior debe interpretar la ponderacion de alternativas frente a {variable_dependiente}, "
            f"diferenciar entre reducir MTTR y evitar recurrencia de fallas, y justificar por que "
            f"{variable_independiente} es la mejor alternativa. Si las dimensiones "
            f"VI registradas son {vi_dimensions or 'las dimensiones de la variable independiente'} y las dimensiones "
            f"VD son {vd_dimensions or 'las dimensiones de la variable dependiente'}, usa esa relacion para explicar "
            "por que la priorizacion soporta el resto del proyecto. Despues de la Figura 1.4 redacta el parrafo "
            "final de consecuencia que conecta VI, VD, confiabilidad y mantenibilidad."
        ),
    ]


def _is_maintenance_reliability_case(details: Dict[str, Any]) -> bool:
    tokens = " ".join(
        _normalize_text(details.get(key))
        for key in (
            "titulo",
            "title",
            "tema",
            "linea_investigacion",
            "objeto_estudio",
            "variable_independiente",
            "variable_dependiente",
            "poblacion",
            "muestra",
        )
    )
    markers = (
        "mantenimiento",
        "confiabilidad",
        "disponibilidad",
        "amef",
        "iso 14224",
        "mtbf",
        "mttr",
        "cat 24m",
        "motoniveladora",
        "mineria",
        "minera",
    )
    hit_count = sum(1 for marker in markers if marker in tokens)
    return hit_count >= 3 and ("mantenimiento" in tokens or "confiabilidad" in tokens or "disponibilidad" in tokens)


def _chapter_two_bases_contract(details: Dict[str, Any]) -> List[str]:
    maintenance_case = _is_maintenance_reliability_case(details)
    return [
        "Contrato adaptativo de bloques para 2.2 Bases teoricas:",
        (
            "- La salida debe construirse por subtitulos numerados de tercer nivel y no por bloques corridos. "
            "Cada subtitulo debe ir como linea independiente con patron 2.2.x y debajo debe desarrollar "
            "2 a 3 parrafos tecnicos antes de pasar al siguiente subtema."
        ),
        (
            "- Deriva los subtemas del titulo, problema, variables, dimensiones, poblacion, muestra y contexto. "
            "El ejemplo del profesor fija densidad, secuencia, jerarquia de subtitulos y criterio visual; "
            "no fija frases literales."
        ),
        (
            "- Selector tematico: mantenimiento -> mantenimiento, confiabilidad, disponibilidad, activos, AMEF, "
            "taxonomia, equipo e indicadores; "
            "software -> arquitectura, datos, interfaz, seguridad, tecnologias y algoritmos; educacion -> aprendizaje, "
            "didactica, competencias, evaluacion y rendimiento; estructuras -> cargas, resistencia, normas, materiales "
            "y modelamiento; salud -> fundamentos clinicos, epidemiologia, diagnostico, intervencion e instrumentos."
        ),
        (
            "- Las figuras nunca deben abrir la seccion ni un subtema. Primero va el subtitulo 2.2.x, luego el "
            "desarrollo teorico, y recien despues el apoyo visual. No coloques una figura al inicio ni dos figuras "
            "consecutivas."
        ),
        (
            "- Figuras: usa 0 a 4 segun necesidad. Emitelas como FIGURE_JSON solo despues de 2 o 3 parrafos "
            "que expliquen el concepto, proceso, clasificacion, herramienta o equipo. Despues de cada figura debe "
            "existir un parrafo inmediato de lectura tecnica o conexion con el subtema siguiente."
        ),
        (
            "- Formulas: usa FORMULA_JSON solo si el tema requiere indicadores, calculos, indices, ratios o ecuaciones. "
            "Antes define el concepto y sus variables; despues interpreta el resultado. No inventes formulas para "
            "temas cualitativos o conceptuales."
        ),
        (
            "- No uses encabezados Markdown, asteriscos, listas ni subtitulos en negrita. Los subtitulos 2.2.x deben "
            "quedar como lineas limpias, sin ** ni ##."
        ),
        (
            "- No generes TABLE_JSON, matriz de consistencia, matriz de operacionalizacion, placeholders visibles, "
            "figuras de ejemplo ni notas como 'reemplazar por la figura validada por el autor' dentro de 2.2."
        ),
        (
            "- Cuando un subtema use formula, evita dejar la ecuacion aislada: debe quedar entre una definicion previa "
            "y una interpretacion posterior."
        ),
        (
            "- La cantidad de figuras, formulas y subtitulos debe responder al dominio real del proyecto, no a una "
            "plantilla ciega. Si el tema no corresponde a mantenimiento y confiabilidad, no arrastres RCM, AMEF, "
            "ISO 14224 ni CAT 24M."
        ),
        "- Prohibido hardcodear elementos del ejemplo guia si no pertenecen al dominio real del proyecto.",
        *(
            [
                (
                    "- Caso mantenimiento/confiabilidad/mineria: usa obligatoriamente ocho subtitulos de tercer nivel "
                    "en este orden exacto: 2.2.1 Mantenimiento Centrado en Confiabilidad (RCM); 2.2.2 Proceso del RCM; "
                    "2.2.3 Taxonomia de equipos segun ISO 14224:2016; 2.2.4 Analisis de Modos y Efecto de Fallas "
                    "(AMEF); 2.2.5 Disponibilidad inherente; 2.2.6 Confiabilidad; 2.2.7 Mantenibilidad; "
                    "2.2.8 Motoniveladora CAT 24M."
                ),
                (
                    "- En ese caso, la secuencia visual tambien es obligatoria: Figura 2.1 despues del subtema "
                    "2.2.2; Figura 2.2 despues del subtema 2.2.3; Figura 2.3 despues del subtema 2.2.4; "
                    "Figura 2.4 despues del subtema 2.2.8."
                ),
                (
                    "- En el mismo caso, las formulas deben concentrarse en 2.2.5 Disponibilidad inherente, "
                    "2.2.6 Confiabilidad y 2.2.7 Mantenibilidad. No pongas formulas en 2.2.1, 2.2.2, 2.2.3, "
                    "2.2.4 ni 2.2.8."
                ),
                (
                    "- CRITICO: Cada formula matematica de 2.2.5, 2.2.6 y 2.2.7 DEBE emitirse obligatoriamente "
                    "como un bloque <<<FORMULA_JSON ... FORMULA_JSON>>>. Jamas escribas una ecuacion como texto "
                    "plano aislado en un parrafo (por ejemplo 'MTBF = ...' o 'Disponibilidad = ...' como linea "
                    "suelta). Una formula en texto plano es un error critico que la hace aparecer en el indice "
                    "del documento como si fuera un titulo, arruinando la tabla de contenidos. Usa siempre el "
                    "bloque FORMULA_JSON con los campos obligatorios 'tipo', 'latex', 'texto', 'alineacion' e 'id'; "
                    "'latex' es la expresion canonica editable, 'texto' es el respaldo legible e 'id' debe ser estable. "
                    "Puedes incluir 'numero' cuando corresponda. Ejemplo: "
                    "{\"tipo\":\"formula\",\"latex\":\"R(t)=e^{-\\\\lambda t}\","
                    "\"texto\":\"R(t) = e^(-lambda t)\",\"alineacion\":\"center\",\"id\":\"confiabilidad-rt\"}."
                ),
                (
                    "- Patron del entregable 1: 2.2.1 desarrolla fundamento teorico del RCM sin figura; "
                    "2.2.2 explica el proceso del RCM y luego su figura; 2.2.3 explica la taxonomia y luego su figura; "
                    "2.2.4 explica el AMEF y luego su figura; 2.2.5 a 2.2.7 desarrollan indicadores con formulas; "
                    "2.2.8 describe tecnicamente el equipo y luego su figura."
                ),
            ]
            if maintenance_case
            else []
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
            "- Mantiene coherencia terminologica con el dominio real del proyecto, "
            "sus variables, dimensiones y contexto; no arrastres vocabulario de un caso guia si no corresponde.",
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
    maintenance_requirements = ()
    if is_unac_maintenance_project(format_id, values or {}):
        maintenance_requirements = requirements_for_section_path(section_path)
    if maintenance_requirements:
        minimum_words = sum(item.min_words for item in maintenance_requirements)
        target_words = sum(item.target_words for item in maintenance_requirements)
        maximum_words = sum(item.max_words for item in maintenance_requirements)
        word_contract = (
            f"mínimo obligatorio {minimum_words}, objetivo {target_words} y máximo estricto "
            f"{maximum_words} palabras narrativas"
        )
    else:
        word_contract = profile.word_range

    profile_key = _profile_key(section_id, section_path)
    structure = profile.structure
    quality_rules = profile.quality_rules
    if maintenance_requirements:
        if profile_key.endswith("/1.1 descripcion de la realidad problematica"):
            structure = tuple(
                [
                    "Párrafo 1: contexto operativo internacional del problema.",
                    "Párrafo 2: diagnóstico internacional sustentado, sin trasladar datos al proyecto.",
                    "Párrafo 3: diagnóstico nacional y brecha de conocimiento.",
                    "Párrafo 4: contexto local usando únicamente hechos registrados.",
                    "Párrafo 5: brecha, causas y consecuencias operativas.",
                    "Párrafo 6: explicación previa del análisis de Pareto cualitativo.",
                    "Párrafo 7: interpretación del apoyo visual de Pareto sin inventar frecuencias.",
                    "Párrafo 8: transición causal hacia el esquema de Ishikawa.",
                    "Párrafo 9: interpretación técnica de causas, limitada a hechos disponibles.",
                    "Párrafo 10: presentación cualitativa de alternativas de solución.",
                    "Párrafo 11: comparación de pertinencia sin puntajes inventados.",
                    "Párrafo 12: criterios de priorización de alternativas.",
                    "Párrafo 13: interpretación de la priorización sin fabricar resultados.",
                    "Párrafo 14: cierre con brecha, variables y solución propuesta.",
                ]
            )
            quality_rules = (
                "Redacta entre 12 y 14 párrafos narrativos; el sistema insertará cuatro apoyos visuales no numerados.",
                "No escribas FIGURE_JSON, guías de elaboración, porcentajes, puntajes, autores ni datos no registrados.",
                "Los apoyos visuales son esquemas cualitativos; no se cuentan como narración ni aparecen en el índice.",
                "Mantén progresión internacional, nacional y local, seguida de brecha, causas, consecuencias y solución.",
            )
        elif profile_key.endswith("/2.1 antecedentes"):
            structure = (
                "2.1.1 Antecedentes internacionales: exactamente cinco estudios, uno por párrafo.",
                "2.1.2 Antecedentes nacionales: exactamente cinco estudios, uno por párrafo.",
                "Cada párrafo contiene autor, título, problema, objetivo, método, muestra, resultado, conclusión y aporte.",
            )
            quality_rules = (
                "No agregues introducciones ni cierres colectivos; entrega diez estudios y dos encabezados.",
                "No uses libros, normas, manuales, figuras, tablas o fórmulas como antecedentes empíricos.",
                "No inventes cifras del proyecto ni repitas plantillas de apertura y cierre.",
            )
        elif profile_key.endswith("/2.4 definicion de terminos basicos"):
            structure = ("Redacta exactamente trece entradas con formato 'Término. Definición'.",)
            quality_rules = (
                "Una definición sustantiva y una cita asignada por cada término.",
                "No insertes figura, tabla, formula ni cierre final en 2.4.",
                "No hardcodees terminos de mantenimiento que no correspondan a las variables o dimensiones registradas.",
            )

    lines: List[str] = [
        "Contrato editorial especifico de esta seccion:",
        f"- Rango de palabras aceptable: {word_contract}.",
        f"- Proposito: {profile.purpose}",
        "- Estructura interna esperada:",
    ]
    if maintenance_requirements:
        lines.append(build_project_fact_registry(values or {}).prompt_contract())
    lines.extend(f"  {index}. {item}" for index, item in enumerate(structure, start=1))
    lines.append("- Criterios de calidad:")
    lines.extend(f"  - {item}" for item in quality_rules)

    context_lines = _structured_context_lines(profile.context_mode, details)
    if context_lines:
        lines.append("Hechos estructurados relevantes del proyecto:")
        lines.extend(context_lines)

    if (
        profile_key
        == "i. planteamiento del problema/1.1 descripcion de la realidad problematica"
    ):
        lines.extend(
            [
                "Apoyos visuales controlados por el sistema: Pareto cualitativo, Ishikawa, matriz de relevancia y matriz de priorización.",
                "No redactes títulos, fuentes, instrucciones de dibujo ni valores para esos apoyos.",
            ]
        )
    if _is_theoretical_bases_key(profile_key):
        if maintenance_requirements:
            lines.extend(
                [
                    "Contrato V2 para 2.2 Bases teóricas:",
                    "- Usa exactamente los ocho subtítulos canónicos 2.2.1 a 2.2.8 del perfil de mantenimiento.",
                    "- Desarrolla de dos a tres párrafos por subtítulo y respeta el intervalo individual indicado.",
                    "- No emitas FIGURE_JSON ni FORMULA_JSON: el sistema inserta cuatro figuras reales y tres ecuaciones canónicas.",
                    "- Las figuras formales se ubican después de 2.2.2, 2.2.3, 2.2.4 y 2.2.8.",
                    "- Las figuras nunca deben abrir la seccion ni un subtema.",
                    "- No generes TABLE_JSON, matriz de consistencia ni matriz de operacionalización.",
                    "- Las ecuaciones se ubican en 2.2.5, 2.2.6 y 2.2.7 entre definición e interpretación.",
                    "- No arrastres autores, cifras, equipos o resultados del documento guía.",
                    "- Prohibido hardcodear elementos del ejemplo guia que no estén en el registro de hechos.",
                ]
            )
        else:
            lines.extend(_chapter_two_bases_contract(details))

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
