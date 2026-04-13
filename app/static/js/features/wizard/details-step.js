/**
 * Details Step — Wizard Step 3
 *
 * Supports two modes:
 *  - Maestría UNAC: Excel upload → preview → editable structured form
 *  - Other formats: Dynamic form generated from prompt package variables (existing behavior)
 *
 * The mode is determined by the format.category from the store.
 */

import { selectionKey } from "./prompt-package-client.js";
import { flattenSections } from "./section-selection.js";

// ---------------------------------------------------------------------------
// Utility helpers (unchanged from original)
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// buildDetailsGroups — unchanged from original, used for non-maestría formats
// ---------------------------------------------------------------------------

export function buildDetailsGroups(promptPackage, selectedSections) {
  const packageVariables = uniqueValues(promptPackage?.variables);
  const selectedKeys = new Set((Array.isArray(selectedSections) ? selectedSections : []).map(selectionKey));
  const sections = flattenSections(promptPackage);
  const byPath = new Map(
    sections
      .filter((section) => String(section.section_path || "").trim())
      .map((section) => [String(section.section_path || "").trim(), section]),
  );

  // Identify variables used strictly by ANY section (so we don't treat them as globals if unselected)
  const allSectionVariableNames = new Set();
  sections.forEach((section) => {
    (Array.isArray(section.blocks) ? section.blocks : []).forEach((block) => {
      uniqueValues(block.required_variables).forEach((v) => {
        if (v) allSectionVariableNames.add(String(v).trim().toLowerCase());
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
    (name) => !allSectionVariableNames.has(String(name).toLowerCase())
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

// ---------------------------------------------------------------------------
// ============================================================================
// STATE & UTILS
// ============================================================================

/** Returns true if the current format in the store is maestría/posgrado */
function isMaestriaFormat(store) {
  const state = store.getState();
  const format = state.format || state.currentProject?.format || null;
  if (!format) return false;
  const category = String(format.category || "").toLowerCase().trim();
  return category.includes("maestria") || category.includes("posgrado") || category.includes("postgrado");
}

// ---------------------------------------------------------------------------
// Maestría UI helpers
// ---------------------------------------------------------------------------

const MAESTRIA_REQUIRED_FIELDS = new Set([
  "titulo", "autor1_nombres", "asesor_nombres",
  "linea_investigacion", "lugar_ejecucion", "unidad_analisis",
  "tipo", "enfoque", "diseno_investigacion", "tema_ocde_1",
  "objeto_estudio", "variable_independiente", "variable_dependiente",
  "poblacion", "muestra", "lugar", "temporal"
]);

/** Read all maestría form inputs into a flat dict. */
function _collectMaestriaValues() {
  const values = {};
  document.querySelectorAll("[data-maestria]").forEach((el) => {
    const key = el.getAttribute("data-maestria");
    if (!key) return;
    values[key] = String(el.value || "").trim();
  });
  return values;
}

/** Populate maestría form inputs from a flat dict. Does not overwrite non-empty fields
 *  unless force=true. This avoids wiping manual edits when rehidrating. */
function _populateMaestriaForm(values, { force = false } = {}) {
  document.querySelectorAll("[data-maestria]").forEach((el) => {
    const key = el.getAttribute("data-maestria");
    if (!key) return;
    const incoming = String(values[key] || "").trim();
    if (!incoming) return; // never wipe with empty
    const current = String(el.value || "").trim();
    if (!current || force) {
      el.value = incoming;
    }
  });
}

/** Returns validation errors for the maestría form. */
function _validateMaestriaValues(values) {
  const errors = [];
  for (const field of MAESTRIA_REQUIRED_FIELDS) {
    if (!String(values[field] || "").trim()) {
      const labels = {
        titulo: "Título del Proyecto",
        autor1_nombres: "Apellidos y Nombres (Autor 1)",
        asesor_nombres: "Apellidos y Nombres (Asesor)",
        anio: "Año",
        linea_investigacion: "Línea de Investigación",
        lugar_ejecucion: "Lugar de Ejecución",
        unidad_analisis: "Unidad de Análisis",
        tipo: "Tipo",
        enfoque: "Enfoque",
        diseno_investigacion: "Diseño de Investigación",
        tema_ocde_1: "Tema OCDE 1",
      };
      errors.push(`"${labels[field] || field}" es obligatorio.`);
    }
  }
  // El campo anio ya no es obligatorio ni se valida aquí porque se fuerza en el backend.
  // Solo validamos que temporal sea un año razonable si se ingresa.
  const temporal = String(values.temporal || "").trim();
  if (temporal && !/^\d{4}$/.test(temporal)) {
    errors.push("El campo Temporal (Año) debe ser un año de 4 dígitos.");
  }
  return errors;
}

/** Show / hide the maestría UI blocks. */
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

/** Reset the maestría UI state: hide preview, clear file input label. */
function _resetExcelUI() {
  const preview = document.getElementById("step3-extraction-preview");
  const processing = document.getElementById("excel-processing-state");
  const loading = document.getElementById("excel-loading");
  const error = document.getElementById("excel-error");
  const success = document.getElementById("excel-success");
  const filenameLabel = document.getElementById("excel-filename-label");

  if (preview) preview.classList.add("hidden");
  if (processing) processing.classList.add("hidden");
  if (loading) loading?.classList.add("hidden");
  if (error) error.classList.add("hidden");
  if (success) success.classList.add("hidden");
  if (filenameLabel) {
    filenameLabel.classList.add("hidden");
    filenameLabel.textContent = "";
  }
}

/** Show the extraction preview block with the parse result. */
function _renderExtractionPreview(result) {
  const previewEl = document.getElementById("step3-extraction-preview");
  const summaryEl = document.getElementById("extraction-summary");
  const warningsEl = document.getElementById("extraction-warnings");
  const missingEl = document.getElementById("extraction-missing");
  if (!previewEl || !summaryEl) return;

  const extracted = result.extracted_fields || [];
  const warnings = result.warnings || [];
  const missing = result.missing_required || [];

  summaryEl.innerHTML = extracted.length
    ? `<span class="font-medium">${extracted.length} campo(s) extraídos.</span>`
    : "<span>No se extrajeron campos del Excel.</span>";

  if (warnings.length) {
    warningsEl.classList.remove("hidden");
    warningsEl.innerHTML = warnings.map((w) => `<div>⚠ ${w}</div>`).join("");
  } else {
    warningsEl.classList.add("hidden");
  }

  if (missing.length) {
    missingEl.classList.remove("hidden");
    missingEl.innerHTML =
      `<div class="font-medium">Campos obligatorios faltantes:</div>` +
      missing.map((m) => `<div>• ${m}</div>`).join("");
  } else {
    missingEl.classList.add("hidden");
  }

  previewEl.classList.remove("hidden");
}

// ---------------------------------------------------------------------------
// Main factory
// ---------------------------------------------------------------------------

export function createDetailsStep({
  store,
  getContainer,
  escapeHtml,
  renderField,
  readInputValue,
  syncVariableInputs,
}) {
  // ── Standard form helpers (unchanged) ──────────────────────────────────

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
          <label for="var_title" class="block text-[10px] font-black text-blue-900 uppercase tracking-widest">Título del proyecto</label>
          <span class="text-[9px] bg-blue-600 text-white px-2 py-0.5 rounded-full font-bold">Obligatorio</span>
        </div>
        <input id="var_title" type="text" class="w-full p-4 border-2 border-blue-200 rounded-2xl focus:border-blue-500 focus:ring-4 focus:ring-blue-500/10 outline-none bg-white font-bold text-slate-800" placeholder="Ej: Implementación de un sistema para mejorar la atención de proyectos.">
        <p class="mt-3 text-[11px] text-slate-500">Define el tema principal del proyecto y se usa como contexto general para la generación.</p>
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
          block_headers: Array.isArray(item?.block_headers) ? item.block_headers : [],
        });
      });

      if (!groupVariables.length) return;

      const wrapper = document.createElement("div");
      wrapper.className = "p-6 bg-white rounded-3xl border border-slate-200 shadow-sm mb-6";
      wrapper.innerHTML = `
        <div class="flex items-center gap-3 mb-6 pb-4 border-b border-slate-100">
          <div class="w-8 h-8 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center font-black text-sm">${index + 1}</div>
          <div>
            <h3 class="text-xs font-black text-slate-400 uppercase tracking-widest">${escapeHtml(group.section_breadcrumb || group.section_path || group.section_title || "Sección")}</h3>
            <h4 class="text-sm font-bold text-slate-800">${escapeHtml(group.section_title || group.section_path || "Variables requeridas")}</h4>
            ${group.chapter_parent ? `<p class="mt-1 text-[11px] text-slate-500">Capítulo padre: ${escapeHtml(group.chapter_parent)}</p>` : ""}
            ${group.immediate_parent && group.immediate_parent !== group.chapter_parent ? `<p class="mt-1 text-[11px] text-slate-500">Sección padre inmediata: ${escapeHtml(group.immediate_parent)}</p>` : ""}
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
        if (!String(values.tema || "").trim()) {
          values.tema = values.title;
        }
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
    if (!String(values.tema || "").trim()) {
      values.tema = title;
    }

    store.setProjectValues(values);
    return { title, values };
  }

  // ── Maestría mode helpers ───────────────────────────────────────────────

  /** Wire change events on maestría inputs → update store. */
  function _wireMaestriaInputs() {
    document.querySelectorAll("[data-maestria]").forEach((el) => {
      el.addEventListener("input", () => {
        _syncMaestriaToStore();
      });
    });
  }

  /** Collect from form and push to store.maestriaDetails + store.projectValues. */
  function _syncMaestriaToStore() {
    const values = _collectMaestriaValues();
    store.setMaestriaDetails(values);
    // Also keep projectValues in sync (for non-maestría parts of the payload)
    const pv = { ...(store.getState().projectValues || {}), ...values };
    store.setProjectValues(pv);
  }

  /** Mount the maestría step: activate UI blocks, rehidrante if state exists. */
  function renderMaestriaStep() {
    _activateMaestriaUI();

    // Try to rehidrate from store
    const state = store.getState();
    const existing = state.maestriaDetails || state.projectValues || null;
    if (existing && Object.keys(existing).length) {
      _populateMaestriaForm(existing, { force: false });
    }

    // Wire inputs for continuous sync
    _wireMaestriaInputs();

    // Update guide text
    const guide = document.getElementById("step3-guide-text");
    if (guide) {
      guide.textContent =
        "Descarga la plantilla Excel, llénala y súbela para extraer tus datos automáticamente. " +
        "También puedes llenar el formulario directamente.";
    }
  }

  // ── Public API ──────────────────────────────────────────────────────────

  function render() {
    if (isMaestriaFormat(store)) {
      renderMaestriaStep();
    } else {
      renderStandardForm();
    }
  }

  function collect() {
    if (isMaestriaFormat(store)) {
      const values = _collectMaestriaValues();
      store.setMaestriaDetails(values);
      const pv = { ...(store.getState().projectValues || {}), ...values };
      store.setProjectValues(pv);
      const title = values.titulo || "Proyecto Tesis";
      return { title, values };
    }
    return collectStandard();
  }

  function validate() {
    if (isMaestriaFormat(store)) {
      const values = _collectMaestriaValues();
      const errors = _validateMaestriaValues(values);
      if (errors.length) {
        const errEl = document.getElementById("step3-error");
        if (errEl) {
          errEl.textContent = errors[0];
          errEl.classList.remove("hidden");
        }
        return false;
      }
      const errEl = document.getElementById("step3-error");
      if (errEl) errEl.classList.add("hidden");
      return true;
    }
    const { title } = collectStandard();
    return Boolean(String(title || "").trim());
  }

  /**
   * Called by TesisAI.onExcelFileSelected — processes the selected file.
   * Returns a promise resolving to the preview result.
   */
  async function processExcelFile(file) {
    const loadingEl = document.getElementById("excel-loading");
    const errorEl = document.getElementById("excel-error");
    const successEl = document.getElementById("excel-success");
    const successText = document.getElementById("excel-success-text");
    const processingEl = document.getElementById("excel-processing-state");

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
        let msg = "Error al procesar el Excel.";
        try {
          const payload = await response.json();
          if (payload?.detail) msg = String(payload.detail);
        } catch (_) {}
        throw new Error(msg);
      }

      const result = await response.json();
      store.setExcelPreviewResult(result);

      // Populate form with extracted data (don't overwrite existing manual edits)
      if (result.flat) {
        _populateMaestriaForm(result.flat, { force: true });
        _syncMaestriaToStore();
      }

      // Render preview block
      _renderExtractionPreview(result);

      if (loadingEl) loadingEl.classList.add("hidden");
      if (successEl) {
        successEl.classList.remove("hidden");
        const count = (result.extracted_fields || []).length;
        if (successText) successText.textContent = `${count} campo(s) extraídos correctamente.`;
      }

      return result;
    } catch (err) {
      if (loadingEl) loadingEl.classList.add("hidden");
      if (errorEl) {
        errorEl.textContent = err.message || "No se pudo procesar el Excel.";
        errorEl.classList.remove("hidden");
      }
      throw err;
    }
  }

  function reset() {
    // 1. Clear standard form
    const dynamicForm = document.getElementById("dynamic-form");
    if (dynamicForm) dynamicForm.innerHTML = "";
    const titleField = document.getElementById("var_title");
    if (titleField) titleField.value = "";

    // 2. Clear Maestría form
    document.querySelectorAll("[data-maestria]").forEach((el) => {
      if ("value" in el) el.value = "";
    });

    // 3. Clear Excel UI
    _resetExcelUI();

    // 4. Clear common errors
    const errEl = document.getElementById("step3-error");
    if (errEl) {
      errEl.textContent = "";
      errEl.classList.add("hidden");
    }
  }


  return {
    mount() {
      render();
    },
    unmount() {
      collect();
    },
    validate() {
      return validate();
    },
    serialize() {
      return collect();
    },
    render,
    /** Expose for TesisAI.onExcelFileSelected */
    processExcelFile,
    /** Expose for TesisAI.saveMaestriaDetails — collects and validates before returning */
    collectMaestria() {
      return _collectMaestriaValues();
    },
    validateMaestria() {
      return _validateMaestriaValues(_collectMaestriaValues());
    },
    /** True if current format is maestría */
    get isMaestria() {
      return isMaestriaFormat(store);
    },
    reset,
  };
}
