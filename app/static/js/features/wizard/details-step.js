import { selectionKey } from "./prompt-package-client.js";
import { flattenSections } from "./section-selection.js";

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

function uniqueValues(values) {
  const seen = new Set();
  const result = [];
  (Array.isArray(values) ? values : []).forEach((value) => {
    const key = String(value || "").trim();
    if (!key || seen.has(key)) return;
    seen.add(key);
    result.push(key);
  });
  return result;
}

function shouldReplaceVariableOwner(currentOwner, candidateGroup) {
  if (!currentOwner) return true;
  const currentLevel = Number(currentOwner.section_level || 0);
  const candidateLevel = Number(candidateGroup.section_level || 0);
  if (candidateLevel !== currentLevel) return candidateLevel > currentLevel;

  const currentOrder = Number(currentOwner.section_order || 0);
  const candidateOrder = Number(candidateGroup.section_order || 0);
  if (candidateOrder !== currentOrder) return candidateOrder > currentOrder;

  return String(candidateGroup.section_path || "").length >= String(currentOwner.section_path || "").length;
}

export function buildDetailsGroups(promptPackage, selectedSections) {
  const packageVariables = uniqueValues(promptPackage?.variables);
  const selectedKeys = new Set((Array.isArray(selectedSections) ? selectedSections : []).map(selectionKey));
  const sections = flattenSections(promptPackage);
  const byPath = new Map(
    sections
      .filter((section) => String(section.section_path || "").trim())
      .map((section) => [String(section.section_path || "").trim(), section]),
  );

  const allSectionVariableNames = new Set();
  sections.forEach((section) => {
    (Array.isArray(section.blocks) ? section.blocks : []).forEach((block) => {
      uniqueValues(block.required_variables).forEach((value) => {
        if (value) allSectionVariableNames.add(String(value).trim().toLowerCase());
      });
    });
  });

  const groups = [];
  sections.forEach((section) => {
    const key = selectionKey(section);
    const isSelected = selectedKeys.size ? selectedKeys.has(key) : Boolean(section.default_selected);
    if (!isSelected) return;

    const variablesByName = new Map();
    (Array.isArray(section.blocks) ? section.blocks : []).forEach((block) => {
      uniqueValues(block.required_variables).forEach((variable) => {
        const variableName = String(variable || "").trim().toLowerCase();
        if (!variableName) return;
        const current = variablesByName.get(variableName) || {
          name: variableName,
          required: false,
          block_headers: new Set(),
        };
        current.required = current.required || Boolean(block.required ?? true);
        const blockHeader = repairVisibleText(
          String(block.cabecera || block.header || block.label || "Prompt").trim(),
        );
        if (blockHeader) current.block_headers.add(blockHeader);
        variablesByName.set(variableName, current);
      });
    });

    const breadcrumbParts = String(section.section_path || "")
      .split("/")
      .map((part) => repairVisibleText(part.trim()))
      .filter(Boolean);
    const parentSection = byPath.get(String(section.parent_section_path || "").trim());

    groups.push({
      key,
      section_id: section.section_id || "",
      section_path: repairVisibleText(section.section_path || section.path || ""),
      section_title: repairVisibleText(section.section_title || section.title || ""),
      section_breadcrumb: breadcrumbParts.join(" > "),
      chapter_parent: breadcrumbParts.length ? breadcrumbParts[0] : "",
      immediate_parent: repairVisibleText(
        String(parentSection?.section_title || parentSection?.section_path || "").trim(),
      ),
      section_level: Number(section.section_level || 1),
      section_order: Number(section.section_order || 0),
      variables: Array.from(variablesByName.values()).map((item) => ({
        name: item.name,
        required: item.required,
        block_headers: Array.from(item.block_headers),
      })),
    });
  });

  const ownerByVariable = new Map();
  groups.forEach((group) => {
    (Array.isArray(group.variables) ? group.variables : []).forEach((item) => {
      const variableName = String(item?.name || "").trim().toLowerCase();
      if (!variableName || variableName === "title" || variableName === "tema") return;
      const currentOwner = ownerByVariable.get(variableName);
      if (shouldReplaceVariableOwner(currentOwner, group)) {
        ownerByVariable.set(variableName, group);
      }
    });
  });

  const globalVariables = packageVariables.filter(
    (name) => !allSectionVariableNames.has(String(name).toLowerCase()),
  );

  return {
    packageVariables,
    globalVariables,
    groups: groups
      .map((group) => ({
        ...group,
        owned_variables: (Array.isArray(group.variables) ? group.variables : []).filter((item) => {
          const variableName = String(item?.name || "").trim().toLowerCase();
          return ownerByVariable.get(variableName)?.key === group.key;
        }),
      }))
      .filter((group) => Array.isArray(group.owned_variables) && group.owned_variables.length > 0),
  };
}

function isUnacProyectoFormat(store) {
  const state = store.getState();
  const format = state.format || state.currentProject?.format || null;
  const formatId = String(format?.format_id || format?.id || state.currentProject?.format_id || "").toLowerCase().trim();
  const university = String(format?.university || "").toLowerCase().trim();
  const category = String(format?.category || "").toLowerCase().trim();
  return (
    formatId.includes("unac-proyecto") ||
    (university === "unac" && category.includes("proyecto"))
  );
}

function isMaestriaFormat(store) {
  const state = store.getState();
  const format = state.format || state.currentProject?.format || null;
  if (!format) return false;
  const category = String(format.category || "").toLowerCase().trim();
  const formatId = String(format.format_id || format.id || state.currentProject?.format_id || "").toLowerCase().trim();
  const university = String(format.university || "").toLowerCase().trim();
  return (
    category.includes("maestria") ||
    category.includes("posgrado") ||
    category.includes("postgrado") ||
    category.includes("informe") ||
    formatId.includes("unac-maestria") ||
    formatId.includes("unac-proyecto") ||
    formatId.includes("unac-informe") ||
    formatId.includes("uni-informe") ||
    (university === "unac" && category.includes("proyecto"))
  );
}

function cleanText(value) {
  return String(value || "").trim();
}

function pickText(...values) {
  for (const value of values) {
    const text = cleanText(value);
    if (text) return text;
  }
  return "";
}

function cloneData(value) {
  return value == null ? value : JSON.parse(JSON.stringify(value));
}

function splitLines(value) {
  return String(value || "")
    .replace(/\r/g, "")
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}

function joinLines(values) {
  return (Array.isArray(values) ? values : [])
    .map((item) => cleanText(item))
    .filter(Boolean)
    .join("\n");
}

function emptyMatrixSpecificRow() {
  return { problema: "", objetivo: "", hipotesis: "" };
}

function emptyOperationalizationRow() {
  return {
    dimension: "",
    indicador: "",
    indice: "",
    metodo_tecnica: "",
    tecnica_instrumentos: "",
  };
}

function normalizeOperationalizationRows(raw, minimumRows = 1) {
  const rows = Array.isArray(raw) ? raw : [];
  const normalized = rows
    .map((row) => ({
      dimension: cleanText(row?.dimension),
      indicador: cleanText(row?.indicador),
      indice: cleanText(row?.indice),
      metodo_tecnica: cleanText(row?.metodo_tecnica || row?.metodoTecnica),
      tecnica_instrumentos: cleanText(row?.tecnica_instrumentos || row?.tecnicaInstrumentos),
    }))
    .filter((row) => Object.values(row).some(Boolean));
  while (normalized.length < minimumRows) normalized.push(emptyOperationalizationRow());
  return normalized;
}

function collectOperationalizationDimensions(rows) {
  return (Array.isArray(rows) ? rows : [])
    .map((row) => cleanText(row?.dimension))
    .filter(Boolean);
}

function normalizeMatrixSpecificRows(rawMatrix) {
  const matrix = rawMatrix && typeof rawMatrix === "object" ? rawMatrix : {};
  const problemas = Array.isArray(matrix.problemas_especificos) ? matrix.problemas_especificos : [];
  const objetivos = Array.isArray(matrix.objetivos_especificos) ? matrix.objetivos_especificos : [];
  const hipotesis = Array.isArray(matrix.hipotesis_especificas) ? matrix.hipotesis_especificas : [];
  const total = Math.max(problemas.length, objetivos.length, hipotesis.length, 1);

  return Array.from({ length: total }, (_, index) => ({
    problema: cleanText(problemas[index]),
    objetivo: cleanText(objetivos[index]),
    hipotesis: cleanText(hipotesis[index]),
  }));
}

function normalizeMaestriaSeed(raw) {
  const values = raw && typeof raw === "object" ? raw : {};
  const matrix = values.matriz_consistencia || values.matrizConsistencia || {};
  const operVd = values.operacionalizacion_vd || values.operacionalizacionVD || {};
  const operVi = values.operacionalizacion_vi || values.operacionalizacionVI || {};
  const temasOcde = Array.isArray(values.tema_ocde) ? values.tema_ocde : [];

  return {
    titulo: pickText(values.titulo, values.title, values.tema),
    linea_investigacion: cleanText(values.linea_investigacion),
    anio: cleanText(values.anio),
    lugar_caratula: cleanText(values.lugar_caratula),
    autor1_nombres: cleanText(values.autor1_nombres),
    autor1_dni: cleanText(values.autor1_dni),
    autor1_orcid: cleanText(values.autor1_orcid),
    autor2_nombres: cleanText(values.autor2_nombres),
    autor2_dni: cleanText(values.autor2_dni),
    autor2_orcid: cleanText(values.autor2_orcid),
    asesor_nombres: cleanText(values.asesor_nombres),
    asesor_dni: cleanText(values.asesor_dni),
    asesor_orcid: cleanText(values.asesor_orcid),
    coasesor_nombres: cleanText(values.coasesor_nombres),
    coasesor_dni: cleanText(values.coasesor_dni),
    coasesor_orcid: cleanText(values.coasesor_orcid),
    facultad: cleanText(values.facultad),
    unidad_investigacion: cleanText(values.unidad_investigacion || values.unidadInvestigacion),
    objeto_estudio: cleanText(values.objeto_estudio),
    variable_independiente: pickText(values.variable_independiente, values.vi),
    variable_dependiente: pickText(values.variable_dependiente, values.vd),
    lugar_ejecucion: cleanText(values.lugar_ejecucion),
    unidad_analisis: cleanText(values.unidad_analisis),
    tipo: cleanText(values.tipo),
    enfoque: cleanText(values.enfoque),
    diseno_investigacion: cleanText(values.diseno_investigacion),
    nivel_investigacion: cleanText(values.nivel_investigacion),
    poblacion: cleanText(values.poblacion),
    muestra: cleanText(values.muestra),
    lugar: cleanText(values.lugar),
    temporal: cleanText(values.temporal),
    tema_ocde_1: pickText(values.tema_ocde_1, temasOcde[0]),
    tema_ocde_2: pickText(values.tema_ocde_2, temasOcde[1]),
    tema_ocde_3: pickText(values.tema_ocde_3, temasOcde[2]),
    abreviaturas: Array.isArray(values.abreviaturas) ? cloneData(values.abreviaturas) : [],
      matriz_consistencia: {
        problema_general: cleanText(matrix.problema_general),
        objetivo_general: cleanText(matrix.objetivo_general),
        hipotesis_general: cleanText(matrix.hipotesis_general),
        variable_independiente: pickText(matrix.variable_independiente, values.variable_independiente, values.vi),
        dimensiones_variable_independiente: splitLines(matrix.dimensiones_variable_independiente).length
          ? splitLines(matrix.dimensiones_variable_independiente)
          : collectOperationalizationDimensions(operVi.filas || operVi.rows),
        problemas_especificos: normalizeMatrixSpecificRows(matrix).map((row) => row.problema).filter(Boolean),
        objetivos_especificos: normalizeMatrixSpecificRows(matrix).map((row) => row.objetivo).filter(Boolean),
        hipotesis_especificas: normalizeMatrixSpecificRows(matrix).map((row) => row.hipotesis).filter(Boolean),
        variable_dependiente: pickText(matrix.variable_dependiente, values.variable_dependiente, values.vd),
        dimensiones_variable_dependiente: splitLines(matrix.dimensiones_variable_dependiente).length
          ? splitLines(matrix.dimensiones_variable_dependiente)
          : collectOperationalizationDimensions(operVd.filas || operVd.rows),
      tipo_investigacion: pickText(matrix.tipo_investigacion, values.tipo),
      nivel_investigacion: pickText(matrix.nivel_investigacion, values.nivel_investigacion),
      enfoque_investigacion: pickText(matrix.enfoque_investigacion, values.enfoque),
      diseno: pickText(matrix.diseno, values.diseno_investigacion),
      poblacion: pickText(matrix.poblacion, values.poblacion),
      muestra: pickText(matrix.muestra, values.muestra),
      tecnicas: cleanText(matrix.tecnicas),
      instrumentos: cleanText(matrix.instrumentos),
      procesamiento_datos: cleanText(matrix.procesamiento_datos),
    },
      operacionalizacion_vd: {
        variable: pickText(operVd.variable, values.variable_dependiente, values.vd),
        definicion_conceptual: cleanText(operVd.definicion_conceptual || operVd.definicionConceptual),
        definicion_operacional: cleanText(operVd.definicion_operacional || operVd.definicionOperacional),
        filas: normalizeOperationalizationRows(operVd.filas || operVd.rows, 2),
      },
      operacionalizacion_vi: {
        variable: pickText(operVi.variable, values.variable_independiente, values.vi),
        definicion_conceptual: cleanText(operVi.definicion_conceptual || operVi.definicionConceptual),
        definicion_operacional: cleanText(operVi.definicion_operacional || operVi.definicionOperacional),
        filas: normalizeOperationalizationRows(operVi.filas || operVi.rows, 4),
      },
    };
  }

function mergeMaestriaDetails(base, override) {
  const safeBase = normalizeMaestriaSeed(base);
  const safeOverride = normalizeMaestriaSeed(override);

  return normalizeMaestriaSeed({
    ...safeBase,
    ...safeOverride,
    abreviaturas: safeOverride.abreviaturas?.length ? safeOverride.abreviaturas : safeBase.abreviaturas,
    matriz_consistencia: {
      ...safeBase.matriz_consistencia,
      ...safeOverride.matriz_consistencia,
    },
    operacionalizacion_vd: {
      ...safeBase.operacionalizacion_vd,
      ...safeOverride.operacionalizacion_vd,
      filas: safeOverride.operacionalizacion_vd?.filas?.length
        ? safeOverride.operacionalizacion_vd.filas
        : safeBase.operacionalizacion_vd.filas,
    },
    operacionalizacion_vi: {
      ...safeBase.operacionalizacion_vi,
      ...safeOverride.operacionalizacion_vi,
      filas: safeOverride.operacionalizacion_vi?.filas?.length
        ? safeOverride.operacionalizacion_vi.filas
        : safeBase.operacionalizacion_vi.filas,
    },
  });
}

function buildFlatMaestriaValues(details) {
  const safe = normalizeMaestriaSeed(details);
  const temaOcde = [safe.tema_ocde_1, safe.tema_ocde_2, safe.tema_ocde_3].filter(Boolean);
  const matrix = safe.matriz_consistencia;

  return {
    titulo: safe.titulo,
    title: safe.titulo,
    tema: safe.titulo,
    linea_investigacion: safe.linea_investigacion,
    anio: safe.anio,
    lugar_caratula: safe.lugar_caratula,
    autor1_nombres: safe.autor1_nombres,
    autor1_dni: safe.autor1_dni,
    autor1_orcid: safe.autor1_orcid,
    autor2_nombres: safe.autor2_nombres,
    autor2_dni: safe.autor2_dni,
    autor2_orcid: safe.autor2_orcid,
    asesor_nombres: safe.asesor_nombres,
    asesor_dni: safe.asesor_dni,
    asesor_orcid: safe.asesor_orcid,
    coasesor_nombres: safe.coasesor_nombres,
    coasesor_dni: safe.coasesor_dni,
    coasesor_orcid: safe.coasesor_orcid,
    facultad: safe.facultad,
    unidad_investigacion: safe.unidad_investigacion,
    objeto_estudio: safe.objeto_estudio,
    variable_independiente: safe.variable_independiente,
    variable_dependiente: safe.variable_dependiente,
    vi: safe.variable_independiente,
    vd: safe.variable_dependiente,
    lugar_ejecucion: safe.lugar_ejecucion,
    unidad_analisis: safe.unidad_analisis,
    tipo: safe.tipo,
    enfoque: safe.enfoque,
    diseno_investigacion: safe.diseno_investigacion,
    nivel_investigacion: safe.nivel_investigacion,
    poblacion: safe.poblacion,
    muestra: safe.muestra,
    lugar: safe.lugar,
    temporal: safe.temporal,
    tema_ocde_1: safe.tema_ocde_1,
    tema_ocde_2: safe.tema_ocde_2,
    tema_ocde_3: safe.tema_ocde_3,
    tema_ocde: temaOcde,
    abreviaturas: cloneData(safe.abreviaturas),
    matriz_consistencia: cloneData(matrix),
    operacionalizacion_vd: cloneData(safe.operacionalizacion_vd),
    operacionalizacion_vi: cloneData(safe.operacionalizacion_vi),
    problema_general: matrix.problema_general,
    objetivo_general: matrix.objetivo_general,
    hipotesis_general: matrix.hipotesis_general,
    problemas_especificos: cloneData(matrix.problemas_especificos),
    objetivos_especificos: cloneData(matrix.objetivos_especificos),
    hipotesis_especificas: cloneData(matrix.hipotesis_especificas),
    dimensiones_variable_independiente: cloneData(matrix.dimensiones_variable_independiente),
    dimensiones_variable_dependiente: cloneData(matrix.dimensiones_variable_dependiente),
    matriz_tipo_investigacion: matrix.tipo_investigacion,
    matriz_nivel_investigacion: matrix.nivel_investigacion,
    matriz_enfoque_investigacion: matrix.enfoque_investigacion,
    matriz_diseno: matrix.diseno,
    matriz_poblacion: matrix.poblacion,
    matriz_muestra: matrix.muestra,
    matriz_tecnicas: matrix.tecnicas,
    matriz_instrumentos: matrix.instrumentos,
    matriz_procesamiento_datos: matrix.procesamiento_datos,
  };
}

const MAESTRIA_REQUIRED_FIELDS = [
  "titulo",
  "linea_investigacion",
  "anio",
  "autor1_nombres",
  "asesor_nombres",
  "objeto_estudio",
  "variable_independiente",
  "variable_dependiente",
  "lugar_ejecucion",
  "unidad_analisis",
  "tipo",
  "enfoque",
  "diseno_investigacion",
  "tema_ocde_1",
  "poblacion",
  "muestra",
  "lugar",
  "temporal",
];

const MAESTRIA_LABELS = {
  titulo: "Titulo del proyecto",
  linea_investigacion: "Linea de investigacion",
  anio: "Anio",
  autor1_nombres: "Autor 1",
  asesor_nombres: "Asesor",
  objeto_estudio: "Objeto de estudio",
  variable_independiente: "Variable independiente",
  variable_dependiente: "Variable dependiente",
  lugar_ejecucion: "Lugar de ejecucion",
  unidad_analisis: "Unidad de analisis",
  tipo: "Tipo",
  enfoque: "Enfoque",
  diseno_investigacion: "Diseno de investigacion",
  tema_ocde_1: "Tema OCDE 1",
  poblacion: "Poblacion",
  muestra: "Muestra",
  lugar: "Lugar",
  temporal: "Temporal",
};

function _collectMaestriaValues() {
  const values = {};
  document.querySelectorAll("[data-maestria]").forEach((el) => {
    const key = el.getAttribute("data-maestria");
    if (!key) return;
    values[key] = String(el.value || "").trim();
  });
  return values;
}

function _populateMaestriaForm(values, { force = false } = {}) {
  document.querySelectorAll("[data-maestria]").forEach((el) => {
    const key = el.getAttribute("data-maestria");
    if (!key) return;
    const incoming = String(values?.[key] || "").trim();
    if (!incoming && !force) return;
    if (!String(el.value || "").trim() || force) {
      el.value = incoming;
    }
  });
}

function _validateMaestriaValues(values) {
  const errors = [];
  for (const field of MAESTRIA_REQUIRED_FIELDS) {
    if (!String(values[field] || "").trim()) {
      errors.push(`"${MAESTRIA_LABELS[field] || field}" es obligatorio.`);
    }
  }
  const anio = String(values.anio || "").trim();
  if (anio && !/^\d{4}$/.test(anio)) {
    errors.push("El campo Anio debe tener 4 digitos.");
  }
  const temporal = String(values.temporal || "").trim();
  if (temporal && !/^\d{4}$/.test(temporal)) {
    errors.push("El campo Temporal debe tener 4 digitos.");
  }
  return errors;
}

function _activateMaestriaUI() {
  const excelBlock = document.getElementById("step3-excel-block");
  const maestriaForm = document.getElementById("step3-maestria-form");
  const dynamicForm = document.getElementById("dynamic-form");
  const saveBtn = document.getElementById("btn-step3-save-maestria");

  if (excelBlock) excelBlock.classList.remove("hidden");
  if (maestriaForm) maestriaForm.classList.remove("hidden");
  if (dynamicForm) dynamicForm.classList.add("hidden");
  if (saveBtn) saveBtn.classList.remove("hidden");
}

function _resetExcelUI() {
  const preview = document.getElementById("step3-extraction-preview");
  const processing = document.getElementById("excel-processing-state");
  const loading = document.getElementById("excel-loading");
  const error = document.getElementById("excel-error");
  const success = document.getElementById("excel-success");
  const filenameLabel = document.getElementById("excel-filename-label");

  if (preview) preview.classList.add("hidden");
  if (processing) processing.classList.add("hidden");
  if (loading) loading.classList.add("hidden");
  if (error) error.classList.add("hidden");
  if (success) success.classList.add("hidden");
  if (filenameLabel) {
    filenameLabel.classList.add("hidden");
    filenameLabel.textContent = "";
  }
}

function _renderExtractionPreview(result) {
  const previewEl = document.getElementById("step3-extraction-preview");
  const summaryEl = document.getElementById("extraction-summary");
  const warningsEl = document.getElementById("extraction-warnings");
  const missingEl = document.getElementById("extraction-missing");
  if (!previewEl || !summaryEl || !warningsEl || !missingEl) return;

  const extracted = Array.isArray(result?.extracted_fields) ? result.extracted_fields : [];
  const warnings = Array.isArray(result?.warnings) ? result.warnings : [];
  const missing = Array.isArray(result?.missing_required) ? result.missing_required : [];

  summaryEl.innerHTML = extracted.length
    ? `<span class="font-medium">${extracted.length} campo(s) extraidos.</span>`
    : "<span>No se extrajeron campos del Excel.</span>";

  if (warnings.length) {
    warningsEl.classList.remove("hidden");
    warningsEl.innerHTML = warnings.map((item) => `<div>⚠ ${item}</div>`).join("");
  } else {
    warningsEl.classList.add("hidden");
    warningsEl.innerHTML = "";
  }

  if (missing.length) {
    missingEl.classList.remove("hidden");
    missingEl.innerHTML =
      '<div class="font-medium">Campos obligatorios faltantes:</div>'
      + missing.map((item) => `<div>• ${item}</div>`).join("");
  } else {
    missingEl.classList.add("hidden");
    missingEl.innerHTML = "";
  }

  previewEl.classList.remove("hidden");
}

export function createDetailsStep({
  store,
  getContainer,
  escapeHtml,
  renderField,
  readInputValue,
  syncVariableInputs,
}) {
  const esc = (value) => escapeHtml(String(value || ""));
  let maestriaInputsBound = false;

  function hydrateExistingValues() {
    const state = store.getState();
    const values = state.projectValues || {};
    const titleField = document.getElementById("var_title");
    if (titleField) {
      titleField.value = String(values.title || values.tema || "");
    }
    document.querySelectorAll("#dynamic-form [data-variable]").forEach((input) => {
      const variableName = String(input.getAttribute("data-variable") || "").trim();
      if (!variableName) return;
      input.value = String(values?.[variableName] ?? "");
    });
  }

  function renderStandardForm() {
    const container = getContainer?.();
    if (!container) return;
    container.innerHTML = "";

    const state = store.getState();
    const promptPackage = state.promptPackage;
    const selectedSections = state.selectedSections;
    if (!promptPackage || !selectedSections.length) {
      container.innerHTML =
        '<div class="text-sm text-gray-500 text-center py-10 font-medium">Selecciona las secciones que deseas generar en el paso 2.</div>';
      return;
    }

    const details = buildDetailsGroups(promptPackage, selectedSections);
    const sectionVariableNames = new Set();
    (Array.isArray(details.groups) ? details.groups : []).forEach((group) => {
      (Array.isArray(group.owned_variables) ? group.owned_variables : []).forEach((item) => {
        if (item?.name) sectionVariableNames.add(String(item.name).toLowerCase());
      });
    });

    const titleWrapper = document.createElement("div");
    titleWrapper.className = "mb-8 space-y-6";
    titleWrapper.innerHTML = `
      <div class="flex items-center gap-3 mb-6">
        <div class="h-6 w-1 bg-blue-600 rounded-full"></div>
        <h3 class="text-xs font-black uppercase tracking-widest text-slate-800">Datos generales</h3>
      </div>
      <div class="p-6 bg-blue-50 rounded-3xl border-2 border-blue-100 shadow-sm">
        <div class="flex justify-between items-center mb-3 px-1">
          <label for="var_title" class="block text-[10px] font-black text-blue-900 uppercase tracking-widest">Titulo del proyecto</label>
          <span class="text-[9px] bg-blue-600 text-white px-2 py-0.5 rounded-full font-bold">Obligatorio</span>
        </div>
        <input id="var_title" type="text" class="w-full p-4 border-2 border-blue-200 rounded-2xl focus:border-blue-500 focus:ring-4 focus:ring-blue-500/10 outline-none bg-white font-bold text-slate-800" placeholder="Ej: Implementacion de un sistema para mejorar la atencion de proyectos.">
        <p class="mt-3 text-[11px] text-slate-500">Define el tema principal del proyecto y se usa como contexto general para la generacion.</p>
      </div>
    `;
    container.appendChild(titleWrapper);

    const packageVariables = (Array.isArray(details.globalVariables) ? details.globalVariables : [])
      .map((name) => String(name || "").trim().toLowerCase())
      .filter((name) => name && name !== "title" && name !== "tema" && !sectionVariableNames.has(name));

    if (packageVariables.length) {
      const generalWrapper = document.createElement("div");
      generalWrapper.className = "p-6 bg-white rounded-3xl border border-slate-200 shadow-sm mb-6";
      generalWrapper.innerHTML = `
        <div class="flex items-center gap-3 mb-6 pb-4 border-b border-slate-100">
          <div class="w-8 h-8 rounded-lg bg-slate-100 text-slate-500 flex items-center justify-center font-black text-sm">G</div>
          <div>
            <h3 class="text-xs font-black text-slate-400 uppercase tracking-widest">Contexto general</h3>
            <h4 class="text-sm font-bold text-slate-800">Variables base del paquete</h4>
          </div>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4"></div>
      `;
      const grid = generalWrapper.querySelector(".grid");
      packageVariables.forEach((variableName) => {
        renderField(grid, { scopeKey: "general", variableName, required: true });
      });
      container.appendChild(generalWrapper);
    }

    (Array.isArray(details.groups) ? details.groups : []).forEach((group, index) => {
      const groupVariables = [];
      const seenVariables = new Set();
      (Array.isArray(group.owned_variables) ? group.owned_variables : []).forEach((item) => {
        const variableName = String(item?.name || "").trim().toLowerCase();
        if (!variableName || variableName === "title" || variableName === "tema" || seenVariables.has(variableName)) {
          return;
        }
        seenVariables.add(variableName);
        groupVariables.push({
          name: variableName,
          required: Boolean(item?.required ?? true),
        });
      });

      if (!groupVariables.length) return;

      const wrapper = document.createElement("div");
      wrapper.className = "p-6 bg-white rounded-3xl border border-slate-200 shadow-sm mb-6";
      wrapper.innerHTML = `
        <div class="flex items-center gap-3 mb-6 pb-4 border-b border-slate-100">
          <div class="w-8 h-8 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center font-black text-sm">${index + 1}</div>
          <div>
            <h3 class="text-xs font-black text-slate-400 uppercase tracking-widest">${esc(group.section_breadcrumb || group.section_path || group.section_title || "Seccion")}</h3>
            <h4 class="text-sm font-bold text-slate-800">${esc(group.section_title || group.section_path || "Variables requeridas")}</h4>
            ${group.chapter_parent ? `<p class="mt-1 text-[11px] text-slate-500">Capítulo padre: ${esc(group.chapter_parent)}</p>` : ""}
          </div>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4"></div>
      `;
      const grid = wrapper.querySelector(".grid");
      groupVariables.forEach((item) => {
        renderField(grid, {
          scopeKey: group.key || group.section_id || group.section_path || `section_${index + 1}`,
          variableName: item.name,
          required: item.required,
          sectionTitle: group.section_title,
          sectionPath: group.section_breadcrumb || group.section_path,
        });
      });
      container.appendChild(wrapper);
    });

    const titleField = document.getElementById("var_title");
    if (titleField) {
      titleField.addEventListener("input", () => {
        const values = { ...(store.getState().projectValues || {}) };
        values.title = String(titleField.value || "").trim();
        if (!String(values.tema || "").trim()) values.tema = values.title;
        store.setProjectValues(values);
      });
    }

    document.querySelectorAll("#dynamic-form [data-variable]").forEach((input) => {
      input.addEventListener("input", () => {
        const variableName = String(input.getAttribute("data-variable") || "").trim();
        const value = readInputValue(input);
        syncVariableInputs(variableName, value, input.id);
        const values = { ...(store.getState().projectValues || {}) };
        values[variableName] = value;
        store.setProjectValues(values);
      });
    });

    hydrateExistingValues();
  }

  function collectStandard() {
    const values = {};
    document.querySelectorAll("#dynamic-form [data-variable]").forEach((input) => {
      const variableName = String(input.getAttribute("data-variable") || "").trim();
      if (!variableName) return;
      const currentValue = readInputValue(input);
      if (!(variableName in values) || !String(values[variableName] || "").trim()) {
        values[variableName] = currentValue;
      }
    });

    const title = document.getElementById("var_title")?.value?.trim() || "Proyecto Tesis";
    values.title = title;
    if (!String(values.tema || "").trim()) values.tema = title;
    store.setProjectValues(values);
    return { title, values };
  }

  function getExistingMaestriaDetails() {
    const state = store.getState();
    const currentProjectDetails = normalizeMaestriaSeed(state.currentProject?.maestria_details || {});
    const stateDetails = normalizeMaestriaSeed(state.maestriaDetails || {});
    const flatValues = normalizeMaestriaSeed(state.projectValues || {});
    return mergeMaestriaDetails(mergeMaestriaDetails(currentProjectDetails, flatValues), stateDetails);
  }

  function getSeedMaestriaDetails() {
    return getExistingMaestriaDetails();
  }

  function getMatrixSpecificRowsFromDetails(details) {
    return normalizeMatrixSpecificRows(details?.matriz_consistencia);
  }

  function renderMatrixSpecificRows(rows) {
    const safeRows = Array.isArray(rows) && rows.length ? rows : [emptyMatrixSpecificRow()];
    const renderFieldBlock = (field, label) => safeRows.map((row, index) => `
      <div class="mb-3 last:mb-0">
        <div class="text-[10px] font-black uppercase tracking-wider text-slate-400 mb-1">${label} ${index + 1}</div>
        <textarea
          data-matrix-specific-row="${index}"
          data-matrix-specific-field="${field}"
          rows="4"
          class="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100 resize-none"
        >${esc(row?.[field] || "")}</textarea>
      </div>
    `).join("");

    return {
      problema: renderFieldBlock("problema", "Problema especifico"),
      objetivo: renderFieldBlock("objetivo", "Objetivo especifico"),
      hipotesis: renderFieldBlock("hipotesis", "Hipotesis especifica"),
    };
  }

function snapshotMatrixSpecificRows() {
    const indexes = new Set(
      Array.from(document.querySelectorAll("[data-matrix-specific-row]"))
        .map((el) => Number(el.getAttribute("data-matrix-specific-row") || 0)),
    );
    if (!indexes.size) return [emptyMatrixSpecificRow()];
    return Array.from(indexes)
      .sort((a, b) => a - b)
      .map((index) => ({
        problema: cleanText(
          document.querySelector(`[data-matrix-specific-row="${index}"][data-matrix-specific-field="problema"]`)?.value,
        ),
        objetivo: cleanText(
          document.querySelector(`[data-matrix-specific-row="${index}"][data-matrix-specific-field="objetivo"]`)?.value,
        ),
        hipotesis: cleanText(
          document.querySelector(`[data-matrix-specific-row="${index}"][data-matrix-specific-field="hipotesis"]`)?.value,
        ),
      }));
  }

  function renderDimensionMirrorList(dimensions) {
    const items = (Array.isArray(dimensions) ? dimensions : []).filter(Boolean);
    if (!items.length) {
      return '<div class="rounded-lg border border-dashed border-slate-200 px-3 py-2 text-xs text-slate-400">Se reflejan desde la operacionalización.</div>';
    }
    return items.map((item) => `
      <div class="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700">${esc(item)}</div>
    `).join("");
  }

  function renderMatrixEditor(details) {
    const target = document.getElementById("mf-matrix-editor");
    if (!target) return;

    const current = normalizeMaestriaSeed(details);
    const matrix = current.matriz_consistencia;
    const specificRows = getMatrixSpecificRowsFromDetails(current);
    const rowSpan = specificRows.length + 3;

    target.innerHTML = `
      <div class="mb-3 text-sm font-bold text-slate-700">Anexo 1: Matriz de consistencia</div>
      <div class="overflow-x-auto rounded-2xl border border-slate-200">
        <table class="min-w-[1200px] w-full text-sm border-separate border-spacing-0 bg-white">
          <thead>
            <tr>
              <th colspan="5" class="px-5 py-4 text-center text-sm font-black text-slate-800 border-b border-slate-200 bg-slate-50">
                <span id="mf-matrix-title-mirror">${esc(current.titulo || "Titulo pendiente")}</span>
              </th>
            </tr>
            <tr class="bg-slate-50">
              <th class="px-4 py-3 text-center text-xs font-black uppercase tracking-wider text-slate-600 border-b border-r border-slate-200">Problema</th>
              <th class="px-4 py-3 text-center text-xs font-black uppercase tracking-wider text-slate-600 border-b border-r border-slate-200">Objetivos</th>
              <th class="px-4 py-3 text-center text-xs font-black uppercase tracking-wider text-slate-600 border-b border-r border-slate-200">Hipotesis</th>
              <th class="px-4 py-3 text-center text-xs font-black uppercase tracking-wider text-slate-600 border-b border-r border-slate-200">Variables</th>
              <th class="px-4 py-3 text-center text-xs font-black uppercase tracking-wider text-slate-600 border-b border-slate-200">Metodologia</th>
            </tr>
          </thead>
          <tbody>
            <tr class="align-top">
              <td class="px-4 py-3 text-center text-[10px] font-black uppercase tracking-wider text-slate-500 border-r border-b border-slate-200 bg-slate-50">Problema general</td>
              <td class="px-4 py-3 text-center text-[10px] font-black uppercase tracking-wider text-slate-500 border-r border-b border-slate-200 bg-slate-50">Objetivo general</td>
              <td class="px-4 py-3 text-center text-[10px] font-black uppercase tracking-wider text-slate-500 border-r border-b border-slate-200 bg-slate-50">Hipotesis general</td>
              <td rowspan="${rowSpan}" class="p-4 border-r border-b border-slate-200 bg-slate-50/60 align-top">
                <div class="space-y-4">
                  <div class="rounded-xl bg-white border border-slate-200 p-3">
                    <div class="text-[10px] font-black uppercase tracking-wider text-slate-400">Variable independiente</div>
                    <div id="mf-matrix-vi-mirror" class="mt-2 text-sm font-bold text-slate-800">${esc(current.variable_independiente || "Pendiente")}</div>
                    <label class="block text-[10px] font-black uppercase tracking-wider text-slate-400 mt-3 mb-1">Dimensiones</label>
                    <div id="mf-matrix-vi-dimensions-mirror" class="space-y-2">${renderDimensionMirrorList(matrix.dimensiones_variable_independiente)}</div>
                  </div>
                  <div class="rounded-xl bg-white border border-slate-200 p-3">
                    <div class="text-[10px] font-black uppercase tracking-wider text-slate-400">Variable dependiente</div>
                    <div id="mf-matrix-vd-mirror" class="mt-2 text-sm font-bold text-slate-800">${esc(current.variable_dependiente || "Pendiente")}</div>
                    <label class="block text-[10px] font-black uppercase tracking-wider text-slate-400 mt-3 mb-1">Dimensiones</label>
                    <div id="mf-matrix-vd-dimensions-mirror" class="space-y-2">${renderDimensionMirrorList(matrix.dimensiones_variable_dependiente)}</div>
                  </div>
                </div>
              </td>
              <td rowspan="${rowSpan}" class="p-4 border-b border-slate-200 bg-slate-50/60 align-top">
                <div class="space-y-4">
                  <div class="rounded-xl bg-white border border-slate-200 p-3">
                    <div class="text-[10px] font-black uppercase tracking-wider text-slate-400 mb-2">Metodologia</div>
                    <div id="mf-matrix-methodology-summary" class="space-y-2 text-sm text-slate-700"></div>
                  </div>
                  <div>
                    <label class="block text-[10px] font-black uppercase tracking-wider text-slate-400 mb-1">Tecnicas</label>
                    <textarea data-matrix="tecnicas" rows="4" class="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100 resize-none">${esc(matrix.tecnicas)}</textarea>
                  </div>
                  <div>
                    <label class="block text-[10px] font-black uppercase tracking-wider text-slate-400 mb-1">Instrumentos</label>
                    <textarea data-matrix="instrumentos" rows="4" class="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100 resize-none">${esc(matrix.instrumentos)}</textarea>
                  </div>
                  <div>
                    <label class="block text-[10px] font-black uppercase tracking-wider text-slate-400 mb-1">Procesamiento de datos</label>
                    <textarea data-matrix="procesamiento_datos" rows="5" class="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100 resize-none">${esc(matrix.procesamiento_datos)}</textarea>
                  </div>
                </div>
              </td>
            </tr>
            <tr class="align-top">
              <td class="p-4 border-r border-b border-slate-200">
                <textarea data-matrix="problema_general" rows="7" class="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100 resize-none">${esc(matrix.problema_general)}</textarea>
              </td>
              <td class="p-4 border-r border-b border-slate-200">
                <textarea data-matrix="objetivo_general" rows="7" class="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100 resize-none">${esc(matrix.objetivo_general)}</textarea>
              </td>
              <td class="p-4 border-r border-b border-slate-200">
                <textarea data-matrix="hipotesis_general" rows="7" class="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100 resize-none">${esc(matrix.hipotesis_general)}</textarea>
              </td>
            </tr>
            <tr class="align-top bg-slate-50">
              <td class="px-4 py-3 text-center text-[10px] font-black uppercase tracking-wider text-slate-500 border-r border-b border-slate-200">Problemas especificos</td>
              <td class="px-4 py-3 text-center text-[10px] font-black uppercase tracking-wider text-slate-500 border-r border-b border-slate-200">Objetivos especificos</td>
              <td class="px-4 py-3 text-center text-[10px] font-black uppercase tracking-wider text-slate-500 border-r border-b border-slate-200">Hipotesis especificas</td>
            </tr>
            ${specificRows.map((row, index) => `
              <tr class="align-top">
                <td class="p-4 border-r border-b border-slate-200">
                  <textarea
                    data-matrix-specific-row="${index}"
                    data-matrix-specific-field="problema"
                    rows="4"
                    class="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100 resize-none"
                  >${esc(row?.problema || "")}</textarea>
                </td>
                <td class="p-4 border-r border-b border-slate-200">
                  <textarea
                    data-matrix-specific-row="${index}"
                    data-matrix-specific-field="objetivo"
                    rows="4"
                    class="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100 resize-none"
                  >${esc(row?.objetivo || "")}</textarea>
                </td>
                <td class="p-4 border-r border-b border-slate-200">
                  <textarea
                    data-matrix-specific-row="${index}"
                    data-matrix-specific-field="hipotesis"
                    rows="4"
                    class="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100 resize-none"
                  >${esc(row?.hipotesis || "")}</textarea>
                </td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
      <div class="mt-4 flex flex-wrap gap-3">
        <button type="button" id="btn-matrix-add-row" class="inline-flex items-center gap-2 rounded-xl bg-slate-900 px-4 py-2 text-sm font-bold text-white hover:bg-slate-800"><i class="fa-solid fa-plus"></i>Agregar fila especifica</button>
        <button type="button" id="btn-matrix-remove-row" class="inline-flex items-center gap-2 rounded-xl border border-slate-300 px-4 py-2 text-sm font-bold text-slate-700 hover:bg-slate-50"><i class="fa-solid fa-minus"></i>Quitar ultima fila</button>
      </div>
    `;

    target.querySelectorAll("textarea").forEach((el) => {
      el.addEventListener("input", () => {
        syncMirrorDisplays();
        syncMaestriaToStore();
      });
    });

    target.querySelector("#btn-matrix-add-row")?.addEventListener("click", () => {
      const currentDetails = collectStructuredMaestriaDetails();
      const rows = getMatrixSpecificRowsFromDetails(currentDetails);
      rows.push(emptyMatrixSpecificRow());
      currentDetails.matriz_consistencia.problemas_especificos = rows.map((row) => row.problema || "");
      currentDetails.matriz_consistencia.objetivos_especificos = rows.map((row) => row.objetivo || "");
      currentDetails.matriz_consistencia.hipotesis_especificas = rows.map((row) => row.hipotesis || "");
      renderMatrixEditor(currentDetails);
      syncMirrorDisplays();
      syncMaestriaToStore();
    });

    target.querySelector("#btn-matrix-remove-row")?.addEventListener("click", () => {
      const currentDetails = collectStructuredMaestriaDetails();
      const rows = getMatrixSpecificRowsFromDetails(currentDetails);
      if (rows.length > 1) rows.pop();
      currentDetails.matriz_consistencia.problemas_especificos = rows.map((row) => row.problema || "");
      currentDetails.matriz_consistencia.objetivos_especificos = rows.map((row) => row.objetivo || "");
      currentDetails.matriz_consistencia.hipotesis_especificas = rows.map((row) => row.hipotesis || "");
      renderMatrixEditor(currentDetails);
      syncMirrorDisplays();
      syncMaestriaToStore();
    });
  }

  function getOperationalizationRows(details, kind) {
    return normalizeOperationalizationRows(details?.filas, kind === "vd" ? 2 : 4);
  }

  function snapshotOperationalizationRows(kind) {
    const rows = Array.from(document.querySelectorAll(`[data-oper-kind="${kind}"][data-oper-row]`));
    if (!rows.length) return [emptyOperationalizationRow()];
    return rows.map((row) => ({
      dimension: cleanText(row.querySelector('[data-oper-field="dimension"]')?.value),
      indicador: cleanText(row.querySelector('[data-oper-field="indicador"]')?.value),
      indice: cleanText(row.querySelector('[data-oper-field="indice"]')?.value),
      metodo_tecnica: cleanText(row.querySelector('[data-oper-field="metodo_tecnica"]')?.value),
      tecnica_instrumentos: cleanText(row.querySelector('[data-oper-field="tecnica_instrumentos"]')?.value),
    }));
  }

  function renderOperationalizationEditor(kind, details) {
    const isVd = kind === "vd";
    const target = document.getElementById(isVd ? "mf-oper-vd-editor" : "mf-oper-vi-editor");
    if (!target) return;

    const current = normalizeMaestriaSeed(details);
    const operation = isVd ? current.operacionalizacion_vd : current.operacionalizacion_vi;
      const rows = getOperationalizationRows(operation, kind);
    const rowSpan = Math.max(rows.length, 1);
    const headerTitle = isVd ? "Metodo y tecnica" : "Tecnica e instrumentos";
    const mirrorId = isVd ? "mf-oper-vd-variable-mirror" : "mf-oper-vi-variable-mirror";
    const variableMirror = isVd ? current.variable_dependiente : current.variable_independiente;

    target.innerHTML = `
      <div class="overflow-x-auto rounded-2xl border border-slate-200">
        <table class="min-w-[1320px] w-full text-sm border-separate border-spacing-0 bg-white">
          <thead class="bg-slate-50">
            <tr>
              <th class="px-4 py-3 text-center text-xs font-black uppercase tracking-wider text-slate-600 border-b border-r border-slate-200">Variable</th>
              <th class="px-4 py-3 text-center text-xs font-black uppercase tracking-wider text-slate-600 border-b border-r border-slate-200">Definicion conceptual</th>
              <th class="px-4 py-3 text-center text-xs font-black uppercase tracking-wider text-slate-600 border-b border-r border-slate-200">Definicion operacional</th>
              <th class="px-4 py-3 text-center text-xs font-black uppercase tracking-wider text-slate-600 border-b border-r border-slate-200">Dimensiones</th>
              <th class="px-4 py-3 text-center text-xs font-black uppercase tracking-wider text-slate-600 border-b border-r border-slate-200">Indicadores</th>
              <th class="px-4 py-3 text-center text-xs font-black uppercase tracking-wider text-slate-600 border-b border-r border-slate-200">Indice</th>
              <th class="px-4 py-3 text-center text-xs font-black uppercase tracking-wider text-slate-600 border-b border-slate-200">${headerTitle}</th>
            </tr>
          </thead>
          <tbody>
            ${rows.map((row, index) => `
              <tr data-oper-kind="${kind}" data-oper-row="${index}" class="align-top">
                ${index === 0 ? `
                  <td rowspan="${rowSpan}" class="p-4 border-r border-b border-slate-200 bg-slate-50/60">
                    <div class="text-[10px] font-black uppercase tracking-wider text-slate-400 mb-2">Variable principal</div>
                    <div id="${mirrorId}" class="text-sm font-bold text-slate-800">${esc(variableMirror || "Pendiente")}</div>
                  </td>
                  <td rowspan="${rowSpan}" class="p-4 border-r border-b border-slate-200">
                    <textarea data-oper-kind="${kind}" data-oper-root="definicion_conceptual" rows="${Math.max(rowSpan * 6, 8)}" class="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100 resize-none">${esc(operation.definicion_conceptual)}</textarea>
                  </td>
                  <td rowspan="${rowSpan}" class="p-4 border-r border-b border-slate-200">
                    <textarea data-oper-kind="${kind}" data-oper-root="definicion_operacional" rows="${Math.max(rowSpan * 6, 8)}" class="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100 resize-none">${esc(operation.definicion_operacional)}</textarea>
                  </td>
                ` : ""}
                <td class="p-4 border-r border-b border-slate-200">
                  <textarea data-oper-field="dimension" rows="4" class="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100 resize-none">${esc(row.dimension)}</textarea>
                </td>
                <td class="p-4 border-r border-b border-slate-200">
                  <textarea data-oper-field="indicador" rows="4" class="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100 resize-none">${esc(row.indicador)}</textarea>
                </td>
                <td class="p-4 border-r border-b border-slate-200">
                  <textarea data-oper-field="indice" rows="4" class="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100 resize-none">${esc(row.indice)}</textarea>
                </td>
                <td class="p-4 border-b border-slate-200">
                  <label class="block text-[10px] font-black uppercase tracking-wider text-slate-400 mb-1">Metodo / tecnica</label>
                  <textarea data-oper-field="metodo_tecnica" rows="3" class="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100 resize-none mb-3">${esc(row.metodo_tecnica)}</textarea>
                  <label class="block text-[10px] font-black uppercase tracking-wider text-slate-400 mb-1">Instrumentos</label>
                  <textarea data-oper-field="tecnica_instrumentos" rows="3" class="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100 resize-none">${esc(row.tecnica_instrumentos)}</textarea>
                </td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
      <div class="mt-4 flex flex-wrap gap-3">
        <button type="button" data-oper-action="add" data-oper-kind-action="${kind}" class="inline-flex items-center gap-2 rounded-xl bg-slate-900 px-4 py-2 text-sm font-bold text-white hover:bg-slate-800"><i class="fa-solid fa-plus"></i>Agregar fila</button>
        <button type="button" data-oper-action="remove" data-oper-kind-action="${kind}" class="inline-flex items-center gap-2 rounded-xl border border-slate-300 px-4 py-2 text-sm font-bold text-slate-700 hover:bg-slate-50"><i class="fa-solid fa-minus"></i>Quitar ultima fila</button>
      </div>
    `;

    target.querySelectorAll("textarea").forEach((el) => {
      el.addEventListener("input", () => {
        syncMirrorDisplays();
        syncMaestriaToStore();
      });
    });

    target.querySelector(`[data-oper-action="add"][data-oper-kind-action="${kind}"]`)?.addEventListener("click", () => {
      const currentDetails = collectStructuredMaestriaDetails();
      const op = isVd ? currentDetails.operacionalizacion_vd : currentDetails.operacionalizacion_vi;
        op.filas = [...getOperationalizationRows(op, kind), emptyOperationalizationRow()];
      renderOperationalizationEditor(kind, currentDetails);
      syncMirrorDisplays();
      syncMaestriaToStore();
    });

    target.querySelector(`[data-oper-action="remove"][data-oper-kind-action="${kind}"]`)?.addEventListener("click", () => {
      const currentDetails = collectStructuredMaestriaDetails();
      const op = isVd ? currentDetails.operacionalizacion_vd : currentDetails.operacionalizacion_vi;
        const rows = getOperationalizationRows(op, kind);
      if (rows.length > 1) rows.pop();
      op.filas = rows;
      renderOperationalizationEditor(kind, currentDetails);
      syncMirrorDisplays();
      syncMaestriaToStore();
    });
  }

  function collectMatrixDetails() {
    const baseValues = _collectMaestriaValues();
    const specificRows = snapshotMatrixSpecificRows();
    const viRows = snapshotOperationalizationRows("vi");
    const vdRows = snapshotOperationalizationRows("vd");

    return {
      problema_general: cleanText(document.querySelector('[data-matrix="problema_general"]')?.value),
      objetivo_general: cleanText(document.querySelector('[data-matrix="objetivo_general"]')?.value),
      hipotesis_general: cleanText(document.querySelector('[data-matrix="hipotesis_general"]')?.value),
      variable_independiente: cleanText(baseValues.variable_independiente),
      dimensiones_variable_independiente: collectOperationalizationDimensions(viRows),
      problemas_especificos: specificRows.map((row) => cleanText(row.problema)).filter(Boolean),
      objetivos_especificos: specificRows.map((row) => cleanText(row.objetivo)).filter(Boolean),
      hipotesis_especificas: specificRows.map((row) => cleanText(row.hipotesis)).filter(Boolean),
      variable_dependiente: cleanText(baseValues.variable_dependiente),
      dimensiones_variable_dependiente: collectOperationalizationDimensions(vdRows),
      tipo_investigacion: cleanText(baseValues.tipo),
      nivel_investigacion: cleanText(baseValues.nivel_investigacion),
      enfoque_investigacion: cleanText(baseValues.enfoque),
      diseno: cleanText(baseValues.diseno_investigacion),
      poblacion: cleanText(baseValues.poblacion),
      muestra: cleanText(baseValues.muestra),
      tecnicas: cleanText(document.querySelector('[data-matrix="tecnicas"]')?.value),
      instrumentos: cleanText(document.querySelector('[data-matrix="instrumentos"]')?.value),
      procesamiento_datos: cleanText(document.querySelector('[data-matrix="procesamiento_datos"]')?.value),
    };
  }

  function collectOperationalizationDetails(kind) {
    const isVd = kind === "vd";
    const baseValues = _collectMaestriaValues();
    const rows = snapshotOperationalizationRows(kind).filter((row) => Object.values(row).some(Boolean));
    const rootSelector = `[data-oper-kind="${kind}"]`;

    return {
      variable: cleanText(isVd ? baseValues.variable_dependiente : baseValues.variable_independiente),
      definicion_conceptual: cleanText(document.querySelector(`${rootSelector}[data-oper-root="definicion_conceptual"]`)?.value),
      definicion_operacional: cleanText(document.querySelector(`${rootSelector}[data-oper-root="definicion_operacional"]`)?.value),
      filas: rows.length ? rows : [emptyOperationalizationRow()],
    };
  }

  function collectStructuredMaestriaDetails() {
    const seed = getSeedMaestriaDetails();
    const values = _collectMaestriaValues();
    return normalizeMaestriaSeed({
      ...seed,
      ...values,
      titulo: pickText(values.titulo, values.title, values.tema, seed.titulo),
      abreviaturas: cloneData(seed.abreviaturas || []),
      facultad: values.facultad || seed.facultad,
      unidad_investigacion: values.unidad_investigacion || seed.unidad_investigacion,
      matriz_consistencia: collectMatrixDetails(),
      operacionalizacion_vd: collectOperationalizationDetails("vd"),
      operacionalizacion_vi: collectOperationalizationDetails("vi"),
    });
  }

  function collectMaestriaFlatValues(details) {
    return buildFlatMaestriaValues(details);
  }

  function syncMirrorDisplays() {
    const details = collectStructuredMaestriaDetails();
    const values = _collectMaestriaValues();
    const title = pickText(values.titulo, values.title, values.tema, "Titulo pendiente");
    const vi = pickText(values.variable_independiente, "Pendiente");
    const vd = pickText(values.variable_dependiente, "Pendiente");

    const titleMirror = document.getElementById("mf-matrix-title-mirror");
    if (titleMirror) titleMirror.textContent = title;
    const viMatrixMirror = document.getElementById("mf-matrix-vi-mirror");
    if (viMatrixMirror) viMatrixMirror.textContent = vi;
    const vdMatrixMirror = document.getElementById("mf-matrix-vd-mirror");
    if (vdMatrixMirror) vdMatrixMirror.textContent = vd;
    const viOperMirror = document.getElementById("mf-oper-vi-variable-mirror");
    if (viOperMirror) viOperMirror.textContent = vi;
    const vdOperMirror = document.getElementById("mf-oper-vd-variable-mirror");
    if (vdOperMirror) vdOperMirror.textContent = vd;
    const viDimensionsMirror = document.getElementById("mf-matrix-vi-dimensions-mirror");
    if (viDimensionsMirror) {
      viDimensionsMirror.innerHTML = renderDimensionMirrorList(
        details?.matriz_consistencia?.dimensiones_variable_independiente,
      );
    }
    const vdDimensionsMirror = document.getElementById("mf-matrix-vd-dimensions-mirror");
    if (vdDimensionsMirror) {
      vdDimensionsMirror.innerHTML = renderDimensionMirrorList(
        details?.matriz_consistencia?.dimensiones_variable_dependiente,
      );
    }

    const methodologySummary = document.getElementById("mf-matrix-methodology-summary");
    if (methodologySummary) {
      const items = [
        ["Tipo", values.tipo],
        ["Nivel", values.nivel_investigacion],
        ["Enfoque", values.enfoque],
        ["Diseno", values.diseno_investigacion],
        ["Poblacion", values.poblacion],
        ["Muestra", values.muestra],
      ];
      methodologySummary.innerHTML = items.map(([label, value]) => `
        <div class="rounded-lg border border-slate-200 px-3 py-2">
          <div class="text-[10px] font-black uppercase tracking-wider text-slate-400">${esc(label)}</div>
          <div class="text-sm text-slate-800 mt-1">${esc(value || "Pendiente")}</div>
        </div>
      `).join("");
    }
  }

  function populateStructuredMaestriaForm(details, { force = false } = {}) {
    const safe = normalizeMaestriaSeed(details);
    _populateMaestriaForm(safe, { force });
    renderMatrixEditor(safe);
    renderOperationalizationEditor("vd", safe);
    renderOperationalizationEditor("vi", safe);
    syncMirrorDisplays();
  }

  function syncMaestriaToStore() {
    const structured = collectStructuredMaestriaDetails();
    const flat = collectMaestriaFlatValues(structured);
    store.setMaestriaDetails(structured);
    store.setProjectValues(flat);
  }

  function wireMaestriaUI() {
    if (maestriaInputsBound) return;
    maestriaInputsBound = true;
    document.querySelectorAll("[data-maestria]").forEach((el) => {
      el.addEventListener("input", () => {
        syncMirrorDisplays();
        syncMaestriaToStore();
      });
    });
  }

  function renderMaestriaStep() {
    _activateMaestriaUI();
    const guide = document.getElementById("step3-guide-text");
    if (guide) {
      guide.textContent =
        "Carga la plantilla Excel o completa el formulario manual. "
        + "Las tablas de Matriz y Operacionalizacion se llenan aqui mismo.";
    }

    const seed = getSeedMaestriaDetails();
    populateStructuredMaestriaForm(seed, { force: true });
    wireMaestriaUI();

    const preview = store.getState().excelPreviewResult;
    if (preview) {
      _renderExtractionPreview(preview);
    }
    syncMaestriaToStore();
  }

  async function processExcelFile(file) {
    const processingEl = document.getElementById("excel-processing-state");
    const loadingEl = document.getElementById("excel-loading");
    const errorEl = document.getElementById("excel-error");
    const successEl = document.getElementById("excel-success");
    const successText = document.getElementById("excel-success-text");

    if (processingEl) processingEl.classList.remove("hidden");
    if (loadingEl) loadingEl.classList.remove("hidden");
    if (errorEl) errorEl.classList.add("hidden");
    if (successEl) successEl.classList.add("hidden");

    try {
      const formData = new FormData();
      formData.append("file", file);
      const response = await fetch("/api/wizard/details/excel-preview", {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        let detail = "No se pudo procesar el Excel.";
        try {
          const payload = await response.json();
          detail = String(payload?.detail || detail);
        } catch (_) {
          // noop
        }
        throw new Error(detail);
      }

      const result = await response.json();
      store.setExcelPreviewResult(result);
      const seed = getSeedMaestriaDetails();
      const parsed = normalizeMaestriaSeed(result?.data || result?.flat || {});
      const merged = mergeMaestriaDetails(seed, parsed);
      populateStructuredMaestriaForm(merged, { force: true });
      syncMaestriaToStore();
      _renderExtractionPreview(result);

      if (loadingEl) loadingEl.classList.add("hidden");
      if (successEl) {
        successEl.classList.remove("hidden");
        if (successText) {
          successText.textContent = `${(result?.extracted_fields || []).length} campo(s) extraidos correctamente.`;
        }
      }

      return result;
    } catch (error) {
      if (loadingEl) loadingEl.classList.add("hidden");
      if (errorEl) {
        errorEl.textContent = error?.message || "No se pudo procesar el Excel.";
        errorEl.classList.remove("hidden");
      }
      throw error;
    }
  }

  async function validateMaestriaTitle() {
    const details = collectStructuredMaestriaDetails();
    const errors = _validateMaestriaValues(details);
    if (errors.length) {
      throw new Error(errors[0]);
    }

    const response = await fetch("/api/wizard/details/validate-title", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(details),
    });

    const payload = await response.json();
    if (!response.ok) {
      throw new Error(String(payload?.detail || "No se pudo validar el titulo."));
    }

    const correctedTitle = cleanText(payload?.title);
    if (correctedTitle) {
      const titleInput = document.querySelector('[data-maestria="titulo"]');
      if (titleInput) titleInput.value = correctedTitle;
      syncMirrorDisplays();
      syncMaestriaToStore();
    }

    return payload;
  }

  function render() {
    if (isMaestriaFormat(store)) {
      renderMaestriaStep();
    } else {
      renderStandardForm();
    }
  }

  function collect() {
    if (!isMaestriaFormat(store)) {
      return collectStandard();
    }

    const maestriaDetails = collectStructuredMaestriaDetails();
    const values = collectMaestriaFlatValues(maestriaDetails);
    const title = pickText(maestriaDetails.titulo, values.title, "Proyecto Tesis");
    store.setMaestriaDetails(maestriaDetails);
    store.setProjectValues(values);
    return { title, values, maestriaDetails };
  }

  function validate() {
    if (!isMaestriaFormat(store)) {
      const { title } = collectStandard();
      return Boolean(String(title || "").trim());
    }

    const errors = _validateMaestriaValues(collectStructuredMaestriaDetails());
    const errEl = document.getElementById("step3-error");
    if (errors.length) {
      if (errEl) {
        errEl.textContent = errors[0];
        errEl.classList.remove("hidden");
      }
      return false;
    }
    if (errEl) {
      errEl.textContent = "";
      errEl.classList.add("hidden");
    }
    return true;
  }

  function reset() {
    const dynamicForm = document.getElementById("dynamic-form");
    if (dynamicForm) dynamicForm.innerHTML = "";
    const titleField = document.getElementById("var_title");
    if (titleField) titleField.value = "";

    document.querySelectorAll("[data-maestria]").forEach((el) => {
      if ("value" in el) el.value = "";
    });
    const matrixEditor = document.getElementById("mf-matrix-editor");
    if (matrixEditor) matrixEditor.innerHTML = "";
    const operVd = document.getElementById("mf-oper-vd-editor");
    if (operVd) operVd.innerHTML = "";
    const operVi = document.getElementById("mf-oper-vi-editor");
    if (operVi) operVi.innerHTML = "";

    _resetExcelUI();
    store.setMaestriaDetails(null);
    store.setExcelPreviewResult(null);
  }

  return {
    mount() {
      render();
    },
    unmount() {
      collect();
    },
    validate,
    serialize() {
      return collect();
    },
    render,
    processExcelFile,
    collectMaestria() {
      return collectStructuredMaestriaDetails();
    },
    validateMaestria() {
      return _validateMaestriaValues(collectStructuredMaestriaDetails());
    },
    validateMaestriaTitle,
    get isMaestria() {
      return isMaestriaFormat(store);
    },
    reset,
  };
}
