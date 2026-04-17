const WIZARD_FIELD_META = {
  tema: {
    label: "Tema del proyecto",
    placeholder: "Ej: Mejora del tiempo de atencion de proyectos de investigacion.",
    note: "Resume en una frase el tema central que se desarrollara en el documento.",
    example: "Ejemplo: Mejora del proceso de atencion de expedientes en una unidad de investigacion.",
  },
  escenario_estudio: {
    label: "Escenario de estudio",
    placeholder: "Ej: Unidad de Investigacion de la FIIS - UNAC.",
    note: "Indica el lugar, area o institucion donde se desarrolla el estudio.",
    example: "Ejemplo: Oficina de proyectos de investigacion de una facultad publica.",
  },
  informantes_clave: {
    label: "Informantes clave",
    placeholder: "Ej: Jefe de unidad, asistentes administrativos y docentes investigadores.",
    note: "Senala las personas o perfiles que aportan informacion relevante al estudio.",
    example: "Ejemplo: Tres administrativos, dos coordinadores y un responsable de investigacion.",
  },
  variable_independiente: {
    label: "Variable independiente",
    placeholder: "Ej: Implementacion de un sistema web de seguimiento.",
    note: "Describe la intervencion, propuesta o factor principal que se evaluara.",
    example: "Ejemplo: Automatizacion del flujo de recepcion y revision de expedientes.",
  },
  variable_dependiente: {
    label: "Variable dependiente",
    placeholder: "Ej: Tiempo de atencion de proyectos de investigacion.",
    note: "Indica el resultado, efecto o indicador que se busca explicar o mejorar.",
    example: "Ejemplo: Reduccion del tiempo promedio de atencion de expedientes.",
  },
  contexto_organizacion: {
    label: "Contexto de la organización",
    placeholder: "Ej: La unidad atiende expedientes de proyectos de pregrado y posgrado durante todo el año.",
    note: "Resume cómo funciona hoy el área, institución o proceso donde ocurre el problema.",
    example: "Ejemplo: La atención depende de revisiones manuales y seguimiento por correo.",
  },
  contexto_estudio: {
    label: "Contexto del estudio",
    placeholder: "Ej: Proceso interno de evaluación y trámite de proyectos en 2024.",
    note: "Explica el entorno específico en el que se analizará la situación problemática.",
    example: "Ejemplo: Gestión administrativa de expedientes en una unidad universitaria.",
  },
  problema_observable: {
    label: "Problema observable",
    placeholder: "Ej: Demoras frecuentes en la atención de proyectos de investigación.",
    note: "Describe el síntoma principal o la situación problemática que se observa en el contexto.",
    example: "Ejemplo: Durante 2024, la atención de expedientes superó en promedio los 20 días hábiles.",
  },
  sustento_local: {
    label: "Sustento local",
    placeholder: "Ej: Registros internos muestran retrasos, expedientes observados y reprocesos.",
    note: "Aporta evidencias concretas del lugar de estudio: datos, reportes, registros o hechos verificables.",
    example: "Ejemplo: 18 de 25 expedientes fueron observados más de una vez durante el último semestre.",
  },
  descripcion_situacion_actual: {
    label: "Situación actual",
    placeholder: "Ej: El proceso sigue un flujo manual con validaciones en varias etapas.",
    note: "Resume cómo funciona hoy el proceso y qué limitaciones presenta.",
    example: "Ejemplo: No existe trazabilidad centralizada ni alertas para el seguimiento de expedientes.",
  },
  propuesta_solucion_preliminar: {
    label: "Propuesta de solución preliminar",
    placeholder: "Ej: Implementar un sistema web para registrar, derivar y monitorear expedientes.",
    note: "Indica la solución o línea de mejora que se perfila frente al problema detectado.",
    example: "Ejemplo: Digitalizar el seguimiento de expedientes y automatizar alertas de revisión.",
  },
  enfoque_de_solucion: {
    label: "Enfoque de solución",
    placeholder: "Ej: Automatización del flujo y trazabilidad del proceso.",
    note: "Explica brevemente cómo se pretende abordar la mejora o intervención.",
    example: "Ejemplo: Centralizar estados, responsables y tiempos de respuesta en una sola plataforma.",
  },
  contexto_internacional: {
    label: "Contexto internacional",
    placeholder: "Ej: Estudios recientes reportan digitalización y trazabilidad en procesos similares.",
    note: "Resume un antecedente o tendencia internacional relacionada con el problema.",
    example: "Ejemplo: Universidades de la región han reducido tiempos de trámite con plataformas de seguimiento.",
  },
  contexto_nacional: {
    label: "Contexto nacional",
    placeholder: "Ej: En el Perú persisten retrasos administrativos en procesos académicos documentados.",
    note: "Describe como se presenta el problema o la variable en el contexto nacional.",
    example: "Ejemplo: Informes institucionales muestran demoras recurrentes en procesos universitarios similares.",
  },
  sustento_ingenieril: {
    label: "Sustento ingenieril",
    placeholder: "Ej: Se aplicará Ishikawa y Pareto para identificar causas y priorizar mejoras.",
    note: "Indica la herramienta de ingeniería o análisis que se usará para diagnosticar el problema.",
    example: "Ejemplo: Diagrama de Ishikawa para causas raíz y Pareto para priorizar incidencias.",
  },
  periodo_analisis: {
    label: "Periodo de análisis",
    placeholder: "Ej: Enero a diciembre de 2024.",
    note: "Define el periodo de tiempo que abarca la observación o revisión de la situación problemática.",
    example: "Ejemplo: Se analizarán registros y tiempos de atención del año 2024.",
  },
  objetivo_general: {
    label: "Objetivo general",
    placeholder: "Ej: Determinar cómo la implementación de un sistema web mejora el tiempo de atención.",
    note: "Formula el objetivo principal que orienta el estudio.",
    example: "Ejemplo: Evaluar el impacto de una solución digital en la eficiencia del proceso.",
  },
  objetivo_especifico: {
    label: "Objetivo específico",
    placeholder: "Ej: Identificar las causas principales de retraso en la atención de expedientes.",
    note: "Especifica una meta puntual que ayude a cumplir el objetivo general.",
    example: "Ejemplo: Medir tiempos, detectar cuellos de botella y proponer mejoras concretas.",
  },
  poblacion: {
    label: "Población",
    placeholder: "Ej: Expedientes de proyectos registrados durante 2024.",
    note: "Indica el universo o conjunto total que se analizará.",
    example: "Ejemplo: Todos los expedientes de investigación tramitados en la unidad durante el periodo de estudio.",
  },
  muestra: {
    label: "Muestra",
    placeholder: "Ej: 30 expedientes seleccionados para análisis detallado.",
    note: "Señala el subconjunto específico que se revisará o medirá.",
    example: "Ejemplo: Expedientes observados entre enero y junio con mayor tiempo de atención.",
  },
};

function repairVisibleText(value) {
  const raw = String(value ?? "").trim();
  if (!raw || !/[ÃƒÃ‚Ã¢]/.test(raw)) return raw;
  try {
    const bytes = Uint8Array.from(raw, (char) => char.charCodeAt(0) & 0xff);
    const decoded = new TextDecoder("utf-8", { fatal: false }).decode(bytes).trim();
    return decoded && !decoded.includes("\uFFFD") ? decoded : raw;
  } catch (_) {
    return raw;
  }
}

function detailFieldId(scopeKey, variableName) {
  const scope = String(scopeKey || "general")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
  const variable = String(variableName || "campo")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
  return `var_${scope}_${variable}`;
}

function prettyVariableLabel(variableName) {
  const normalized = String(variableName || "")
    .split("_")
    .filter(Boolean)
    .map((chunk) => chunk.charAt(0).toUpperCase() + chunk.slice(1))
    .join(" ");
  return repairVisibleText(normalized);
}

function fallbackFieldMeta(variableName, sectionTitle = "") {
  const label = prettyVariableLabel(variableName);
  const section = repairVisibleText(sectionTitle);
  return {
    label,
    placeholder: `Ej: ${label}.`,
    note: section
      ? `Completa este dato para contextualizar la seccion ${section}.`
      : "Completa este dato con informacion concreta y verificable.",
    example: `Ejemplo: ${label} redactado con informacion real del contexto de estudio.`,
  };
}

export function createWizardFieldRenderer({
  escapeHtml,
  readInputValue,
  syncVariableInputs,
} = {}) {
  return function renderWizardField(
    target,
    { scopeKey, variableName, required = true, sectionTitle = "", sectionPath = "" },
  ) {
    const fieldId = detailFieldId(scopeKey, variableName);
    const meta = WIZARD_FIELD_META[variableName] || fallbackFieldMeta(variableName, sectionTitle || sectionPath);
    const isLong = /(diagnostico|problema|resumen|conclusiones|propuestas|objetivo|metodologia|hipotesis|justificacion|antecedentes|bases|marco|descripcion|introduccion|analisis|contrastacion|discusion|resultados|contexto|sustento)/i.test(variableName);
    const wrapper = document.createElement("div");
    wrapper.className = "space-y-2.5";
    wrapper.innerHTML = `
      <div class="flex items-center justify-between gap-3">
        <label for="${fieldId}" class="text-[10px] font-bold uppercase tracking-widest text-slate-600">${escapeHtml(repairVisibleText(meta.label || prettyVariableLabel(variableName)))}</label>
        ${required ? '<span class="text-[9px] bg-amber-100 text-amber-700 px-2 py-0.5 rounded font-black uppercase">Obligatorio</span>' : '<span class="text-[9px] bg-slate-100 text-slate-500 px-2 py-0.5 rounded font-black uppercase">Opcional</span>'}
      </div>
      ${isLong
        ? `<textarea id="${fieldId}" data-variable="${escapeHtml(variableName)}" rows="3" class="w-full rounded-2xl border-2 border-slate-200 bg-white px-4 py-3 text-sm outline-none transition focus:border-blue-500 focus:ring-4 focus:ring-blue-500/10" placeholder="${escapeHtml(repairVisibleText(meta.placeholder || ""))}"></textarea>`
        : `<input id="${fieldId}" data-variable="${escapeHtml(variableName)}" type="text" class="w-full rounded-2xl border-2 border-slate-200 bg-white px-4 py-3 text-sm outline-none transition focus:border-blue-500 focus:ring-4 focus:ring-blue-500/10" placeholder="${escapeHtml(repairVisibleText(meta.placeholder || ""))}">`
      }
      <p class="text-[11px] leading-relaxed text-slate-500">${escapeHtml(repairVisibleText(meta.note || ""))}</p>
      ${meta.example ? `<p class="text-[11px] leading-relaxed text-slate-400"><span class="font-semibold text-slate-500">Ejemplo:</span> ${escapeHtml(repairVisibleText(String(meta.example || "").replace(/^Ejemplo:\s*/i, "")))}</p>` : ""}
    `;
    target.appendChild(wrapper);
    const input = wrapper.querySelector("[data-variable]");
    if (input) {
      input.addEventListener("input", () => {
        syncVariableInputs?.(variableName, readInputValue?.(input), fieldId);
      });
    }
  };
}
