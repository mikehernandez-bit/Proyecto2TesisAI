import { selectionKey } from "./prompt-package-client.js";

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

export function buildDetailsGroups(promptPackage, selectedSections) {
  const packageVariables = uniqueValues(promptPackage?.variables);
  const selectedKeys = new Set((Array.isArray(selectedSections) ? selectedSections : []).map(selectionKey));
  const groups = [];

  (Array.isArray(promptPackage?.sections) ? promptPackage.sections : []).forEach((section) => {
    const key = selectionKey(section);
    const isSelected = selectedKeys.size ? selectedKeys.has(key) : Boolean(section.default_selected);
    if (!isSelected) return;

    const variables = [];
    (Array.isArray(section.blocks) ? section.blocks : []).forEach((block) => {
      uniqueValues(block.required_variables).forEach((variable) => {
        variables.push({
          name: variable,
          block_label: block.label || "Prompt",
          required: Boolean(block.required ?? true),
        });
      });
    });

    groups.push({
      key,
      section_id: section.section_id || "",
      section_path: section.section_path || section.path || "",
      section_title: section.section_title || section.title || "",
      optional: Boolean(section.optional),
      variables,
    });
  });

  return {
    packageVariables,
    groups,
  };
}

export function createDetailsStep({
  store,
  getContainer,
  escapeHtml,
  renderField,
  readInputValue,
  syncVariableInputs,
}) {
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

  function render() {
    const container = getContainer?.();
    if (!container) return;
    container.innerHTML = "";

    const state = store.getState();
    const promptPackage = state.promptPackage;
    const selectedSections = state.selectedSections;
    if (!promptPackage || !selectedSections.length) {
      container.innerHTML = '<div class="text-sm text-gray-500 text-center py-10 font-medium">Selecciona las secciones que deseas generar en el paso 2.</div>';
      return;
    }

    const details = buildDetailsGroups(promptPackage, selectedSections);
    const sectionVariableNames = new Set();
    (Array.isArray(details.groups) ? details.groups : []).forEach((group) => {
      (Array.isArray(group.variables) ? group.variables : []).forEach((item) => {
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
        <input id="var_title" type="text" class="w-full p-4 border-2 border-blue-200 rounded-2xl focus:border-blue-500 focus:ring-4 focus:ring-blue-500/10 outline-none bg-white font-bold text-slate-800" placeholder="Ej: Implementación de un sistema para mejorar...">
        <p class="mt-3 text-[11px] text-slate-500">El título se usa como contexto general del proyecto y alimenta el tema principal del paquete cuando corresponde.</p>
      </div>
    `;
    container.appendChild(titleWrapper);

    const packageVariables = (Array.isArray(details.packageVariables) ? details.packageVariables : [])
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
      (Array.isArray(group.variables) ? group.variables : []).forEach((item) => {
        const variableName = String(item?.name || "").trim().toLowerCase();
        if (!variableName || variableName === "title" || variableName === "tema" || seenVariables.has(variableName)) return;
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
            <h3 class="text-xs font-black text-slate-400 uppercase tracking-widest">${escapeHtml(group.section_path || group.section_title || "Sección")}</h3>
            <h4 class="text-sm font-bold text-slate-800">${escapeHtml(group.section_title || group.section_path || "Variables requeridas")}</h4>
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

  function collect() {
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

  return {
    mount() {
      render();
    },
    unmount() {
      collect();
    },
    validate() {
      const { title } = collect();
      return Boolean(String(title || "").trim());
    },
    serialize() {
      return collect();
    },
    render,
  };
}
