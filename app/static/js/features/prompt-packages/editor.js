import { requestJson } from "../../shared/api-client.js";
import { getPromptAdminState, patchPromptAdminState } from "./state.js";
import { selectionKey } from "../wizard/prompt-package-client.js";
import { createAdminEditorState, findEditableSection } from "./admin-editor.js";
import { flattenSections } from "../wizard/section-selection.js";
import { escapeHtml } from "../../shared/dom.js";

function currentEditableSection() {
  return findEditableSection(getPromptAdminState().editorState, getPromptAdminState().activeSectionKey);
}

function sectionDisplayMeta(section, index) {
  const rawPath = String(section?.section_path || section?.section_title || "").trim();
  const pathParts = rawPath.split("/").map((value) => value.trim()).filter(Boolean);
  const scope = String(
    (pathParts.length > 1 ? pathParts.slice(0, -1).join(" / ") : section?.parent_section_path)
    || `Seccion ${index + 1}`
  ).trim();
  const title = String(
    section?.section_title
    || pathParts[pathParts.length - 1]
    || rawPath
    || `Seccion ${index + 1}`
  ).trim();
  return { scope, title };
}

function asciiToken(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-zA-Z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .toUpperCase();
}

function buildPromptIdentifier(state, section) {
  const meta = sectionDisplayMeta(section, 1);
  const scope = asciiToken(section?.parent_section_path || meta.scope || meta.title);
  const university = asciiToken(state?.meta?.university);
  const docType = asciiToken(state?.meta?.docType);
  const variant = asciiToken(state?.meta?.variant);
  const fallbackId = String(state?.editorState?.id || "").trim();
  const tokens = [university, docType, variant, scope].filter(Boolean);
  return tokens.length ? tokens.join("_") : fallbackId;
}

function normalizeBlock(section, block, index) {
  const sectionKey = selectionKey(section) || `section_${index + 1}`;
  const header = String(
    block?.header || block?.cabecera || block?.titulo_cabecera || block?.label || `Cabecera ${index + 1}`
  );
  return {
    block_id: String(block?.block_id || `${sectionKey}_block_${index + 1}`),
    header,
    cabecera: header,
    label: String(block?.label || block?.header || `Prompt ${index + 1}`),
    instructions: String(block?.instructions || ""),
    required_variables: Array.isArray(block?.required_variables)
      ? block.required_variables.map((value) => String(value || "").trim()).filter(Boolean)
      : [],
    required: Boolean(block?.required ?? true),
    legacy_prompt_id: String(block?.legacy_prompt_id || ""),
  };
}

function ensureSectionBlocks(section) {
  if (!section) return [];
  const current = Array.isArray(section.blocks) ? section.blocks : [];
  if (current.length) {
    section.blocks = current.map((block, index) => normalizeBlock(section, block, index));
    return section.blocks;
  }
  section.blocks = [normalizeBlock(section, {}, 0)];
  return section.blocks;
}

function cloneSection(section) {
  return {
    section_id: String(section?.section_id || section?.sectionId || ""),
    section_path: String(section?.section_path || section?.sectionPath || section?.path || ""),
    section_title: String(section?.section_title || section?.sectionTitle || section?.title || ""),
    parent_section_path: String(section?.parent_section_path || section?.parentSectionPath || ""),
    section_level: Number(section?.section_level || section?.sectionLevel || 1),
    section_order: Number(section?.section_order || section?.sectionOrder || 0),
    optional: Boolean(section?.optional),
    default_selected: Boolean(section?.default_selected ?? section?.defaultSelected ?? true),
    source_hints: String(section?.source_hints || section?.sourceHints || ""),
    blocks: Array.isArray(section?.blocks)
      ? section.blocks.map((block, index) => normalizeBlock(section, block, index))
      : [],
  };
}

function packageSections() {
  const state = getPromptAdminState().editorState;
  return Array.isArray(state?.sections) ? state.sections : [];
}

function packageStructureSnapshot() {
  return {
    sections: packageSections().map(cloneSection),
    section_tree: [],
  };
}

function isCustomSection(section) {
  return String(section?.section_id || "").startsWith("custom_section_");
}

function isCustomBlock(block) {
  return String(block?.block_id || "").startsWith("custom_block_");
}

function buildCustomId(kind) {
  const suffix = typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
    ? crypto.randomUUID().replace(/-/g, "").slice(0, 12)
    : `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`;
  return `custom_${kind}_${suffix}`;
}

function normalizeVariableList(rawValue) {
  return Array.from(new Set(
    String(rawValue || "")
      .split(/[,\n;]+/)
      .map((value) => String(value || "").trim())
      .filter(Boolean)
      .map((value) => value.replace(/\s+/g, "_").toLowerCase()),
  ));
}

function sectionOptionLabel(section) {
  const parts = String(section?.section_path || section?.section_title || "")
    .split("/")
    .map((part) => part.trim())
    .filter(Boolean);
  return parts.join(" > ") || String(section?.section_title || section?.section_path || "Seccion");
}

function nextSectionOrder() {
  return flattenSections(packageStructureSnapshot()).reduce(
    (maxOrder, section) => Math.max(maxOrder, Number(section?.section_order || 0)),
    0,
  ) + 1;
}

function uniqueSectionPath(parentPath, title) {
  const safeTitle = String(title || "").trim();
  const basePath = parentPath ? `${parentPath}/${safeTitle}` : safeTitle;
  const existing = new Set(
    flattenSections(packageStructureSnapshot())
      .map((section) => String(section?.section_path || "").trim().toLowerCase())
      .filter(Boolean),
  );
  if (!existing.has(basePath.toLowerCase())) {
    return basePath;
  }
  let index = 2;
  while (existing.has(`${basePath} (${index})`.toLowerCase())) {
    index += 1;
  }
  return `${basePath} (${index})`;
}

function updateEditorSections(nextSections, activeSectionKey = getPromptAdminState().activeSectionKey) {
  const state = getPromptAdminState();
  if (!state.editorState) return;

  const nextEditorState = createAdminEditorState({
    ...state.editorState,
    sections: nextSections.map(cloneSection),
  });

  patchPromptAdminState({
    promptPackage: {
      ...(state.promptPackage || nextEditorState),
      ...nextEditorState,
      sections: nextEditorState.sections,
      section_tree: [],
    },
    editorState: nextEditorState,
    activeSectionKey,
  });

  window.renderPromptSectionIndex?.();
  window.renderPromptPackageCustomization?.();
}

function setPackageStructureError(message = "") {
  const errorBox = document.getElementById("admin-custom-structure-error");
  if (!errorBox) return;
  const safeMessage = String(message || "").trim();
  if (!safeMessage) {
    errorBox.textContent = "";
    errorBox.classList.add("hidden");
    return;
  }
  errorBox.textContent = safeMessage;
  errorBox.classList.remove("hidden");
}

function updatePackageStructureMode() {
  const kind = document.getElementById("admin-custom-structure-kind")?.value || "chapter";
  const parentGroup = document.getElementById("admin-custom-parent-group");
  const targetGroup = document.getElementById("admin-custom-target-group");
  const titleGroup = document.getElementById("admin-custom-title-group");
  const headerGroup = document.getElementById("admin-custom-header-group");
  const varsGroup = document.getElementById("admin-custom-vars-group");
  const promptGroup = document.getElementById("admin-custom-prompt-group");
  const addButton = document.getElementById("btn-add-admin-custom-structure");
  const titleInput = document.getElementById("admin-custom-section-title");
  const headerInput = document.getElementById("admin-custom-block-header");

  parentGroup?.classList.toggle("hidden", kind !== "section");
  targetGroup?.classList.toggle("hidden", kind !== "block");
  titleGroup?.classList.toggle("hidden", kind === "block");
  headerGroup?.classList.toggle("hidden", kind === "chapter");
  varsGroup?.classList.toggle("hidden", kind === "chapter");
  promptGroup?.classList.toggle("hidden", kind === "chapter");

  if (addButton) {
    addButton.innerHTML = kind === "chapter"
      ? '<i class="fa-solid fa-plus"></i> Agregar capitulo'
      : (kind === "section"
          ? '<i class="fa-solid fa-plus"></i> Agregar subseccion'
          : '<i class="fa-solid fa-plus"></i> Agregar bloque');
  }

  if (titleInput) {
    titleInput.placeholder = kind === "chapter"
      ? "Ej: CAPITULO ESPECIAL"
      : "Ej: 1.6 Alcance operativo adicional";
  }

  if (headerInput) {
    headerInput.placeholder = kind === "block"
      ? "Ej: Alcance operativo"
      : "Ej: Desarrollo del alcance operativo";
  }
}

function resetPackageStructureForm() {
  const titleInput = document.getElementById("admin-custom-section-title");
  const headerInput = document.getElementById("admin-custom-block-header");
  const promptInput = document.getElementById("admin-custom-block-prompt");
  const variablesInput = document.getElementById("admin-custom-block-variables");
  if (titleInput) titleInput.value = "";
  if (headerInput) headerInput.value = "";
  if (promptInput) promptInput.value = "";
  if (variablesInput) variablesInput.value = "";
  setPackageStructureError("");
}

function packageStructureSummary() {
  const sections = flattenSections(packageStructureSnapshot());
  const customSections = sections.filter(isCustomSection);
  const customBlocks = [];

  sections.forEach((section) => {
    if (isCustomSection(section)) return;
    (Array.isArray(section.blocks) ? section.blocks : []).forEach((block) => {
      if (!isCustomBlock(block)) return;
      customBlocks.push({ section, block });
    });
  });

  return { customSections, customBlocks };
}

function renderPromptPackageCustomization() {
  const state = getPromptAdminState();
  const kindSelect = document.getElementById("admin-custom-structure-kind");
  const parentSelect = document.getElementById("admin-custom-parent-section");
  const targetSelect = document.getElementById("admin-custom-target-section");
  const addButton = document.getElementById("btn-add-admin-custom-structure");
  const saveButton = document.getElementById("btn-save-admin-custom-structure");
  const list = document.getElementById("admin-custom-structure-list");
  const controls = [
    kindSelect,
    parentSelect,
    targetSelect,
    document.getElementById("admin-custom-section-title"),
    document.getElementById("admin-custom-block-header"),
    document.getElementById("admin-custom-block-prompt"),
    document.getElementById("admin-custom-block-variables"),
    addButton,
    saveButton,
  ];

  controls.forEach((control) => {
    if (!control) return;
    control.disabled = !state.editorState;
  });

  updatePackageStructureMode();

  if (!list) return;
  if (!state.editorState) {
    list.innerHTML = '<div class="rounded-xl border border-dashed border-slate-200 bg-slate-50 px-4 py-4 text-sm text-slate-400">Abre un paquete para habilitar esta personalizacion.</div>';
    return;
  }

  const sections = flattenSections(packageStructureSnapshot());
  const options = sections.map((section) => ({
    key: selectionKey(section),
    label: sectionOptionLabel(section),
    isCustom: isCustomSection(section),
  }));

  [parentSelect, targetSelect].forEach((select) => {
    if (!select) return;
    const previousValue = select.value;
    select.innerHTML = options.length
      ? options.map((option) => `
          <option value="${escapeHtml(option.key)}">${escapeHtml(option.isCustom ? `[Personalizado] ${option.label}` : option.label)}</option>
        `).join("")
      : '<option value="">No hay secciones disponibles</option>';
    if (options.some((option) => option.key === previousValue)) {
      select.value = previousValue;
    }
  });

  const { customSections, customBlocks } = packageStructureSummary();
  if (!customSections.length && !customBlocks.length) {
    list.innerHTML = '<div class="rounded-xl border border-dashed border-slate-200 bg-slate-50 px-4 py-4 text-sm text-slate-400">Aun no agregaste elementos personalizados.</div>';
    return;
  }

  const sectionItems = customSections.map((section) => `
    <div class="rounded-2xl border border-blue-200 bg-blue-50/50 px-4 py-4">
      <div class="flex items-start justify-between gap-3">
        <div class="min-w-0">
          <div class="text-[10px] font-black uppercase tracking-widest text-blue-600">Seccion personalizada</div>
          <div class="mt-1 text-sm font-bold text-slate-800">${escapeHtml(sectionOptionLabel(section))}</div>
          <div class="mt-1 text-[11px] text-slate-500">${escapeHtml(`${(Array.isArray(section.blocks) ? section.blocks.length : 0)} bloque(s) | ${Array.isArray(section.children) ? section.children.length : 0} hija(s)`)}</div>
        </div>
        <button type="button" class="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-red-200 bg-white text-red-400 transition hover:bg-red-500 hover:text-white" data-remove-admin-custom-section="${escapeHtml(selectionKey(section))}" aria-label="Eliminar seccion personalizada">
          <i class="fa-solid fa-trash-can"></i>
        </button>
      </div>
    </div>
  `).join("");

  const blockItems = customBlocks.map(({ section, block }) => `
    <div class="rounded-2xl border border-slate-200 bg-white px-4 py-4">
      <div class="flex items-start justify-between gap-3">
        <div class="min-w-0">
          <div class="text-[10px] font-black uppercase tracking-widest text-emerald-600">Bloque personalizado</div>
          <div class="mt-1 text-sm font-bold text-slate-800">${escapeHtml(block.header || block.label || "Bloque extra")}</div>
          <div class="mt-1 text-[11px] text-slate-500">En: ${escapeHtml(sectionOptionLabel(section))}</div>
        </div>
        <button type="button" class="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-red-200 bg-white text-red-400 transition hover:bg-red-500 hover:text-white" data-remove-admin-custom-block="${escapeHtml(block.block_id || "")}" data-admin-block-section-key="${escapeHtml(selectionKey(section))}" aria-label="Eliminar bloque personalizado">
          <i class="fa-solid fa-trash-can"></i>
        </button>
      </div>
    </div>
  `).join("");

  list.innerHTML = `<div class="space-y-3">${sectionItems}${blockItems}</div>`;
}

function addCustomChapterToPackage() {
  const state = getPromptAdminState();
  const rawTitle = String(document.getElementById("admin-custom-section-title")?.value || "").trim();
  if (!state.editorState) {
    setPackageStructureError("Abre primero un paquete institucional.");
    return;
  }
  if (!rawTitle) {
    setPackageStructureError("Escribe el titulo del capitulo.");
    return;
  }

  const nextSections = packageSections().map(cloneSection);
  const sectionPath = uniqueSectionPath("", rawTitle);
  nextSections.push({
    section_id: buildCustomId("section"),
    section_path: sectionPath,
    section_title: sectionPath.split("/").pop()?.trim() || rawTitle,
    parent_section_path: "",
    section_level: 1,
    section_order: nextSectionOrder(),
    optional: false,
    default_selected: true,
    source_hints: "",
    blocks: [],
  });

  updateEditorSections(nextSections);
  resetPackageStructureForm();
}

function addCustomSubsectionToPackage() {
  const state = getPromptAdminState();
  const parentKey = String(document.getElementById("admin-custom-parent-section")?.value || "").trim();
  const title = String(document.getElementById("admin-custom-section-title")?.value || "").trim();
  const header = String(document.getElementById("admin-custom-block-header")?.value || "").trim() || title;
  const instructions = String(document.getElementById("admin-custom-block-prompt")?.value || "").trim();
  const requiredVariables = normalizeVariableList(document.getElementById("admin-custom-block-variables")?.value || "");
  if (!state.editorState) {
    setPackageStructureError("Abre primero un paquete institucional.");
    return;
  }
  const parentSection = findEditableSection(state.editorState, parentKey);
  if (!parentSection) {
    setPackageStructureError("Selecciona la seccion padre.");
    return;
  }
  if (!title) {
    setPackageStructureError("Escribe el titulo de la subseccion.");
    return;
  }
  if (!instructions) {
    setPackageStructureError("Escribe el prompt de la subseccion.");
    return;
  }

  const nextSections = packageSections().map(cloneSection);
  const sectionPath = uniqueSectionPath(String(parentSection.section_path || "").trim(), title);
  nextSections.push({
    section_id: buildCustomId("section"),
    section_path: sectionPath,
    section_title: sectionPath.split("/").pop()?.trim() || title,
    parent_section_path: String(parentSection.section_path || "").trim(),
    section_level: Number(parentSection.section_level || 1) + 1,
    section_order: nextSectionOrder(),
    optional: false,
    default_selected: true,
    source_hints: "",
    blocks: [
      {
        block_id: buildCustomId("block"),
        header,
        cabecera: header,
        label: header,
        instructions,
        required_variables: requiredVariables,
        required: true,
      },
    ],
  });

  updateEditorSections(nextSections);
  resetPackageStructureForm();
}

function addCustomBlockToPackage() {
  const state = getPromptAdminState();
  const targetKey = String(document.getElementById("admin-custom-target-section")?.value || "").trim();
  const header = String(document.getElementById("admin-custom-block-header")?.value || "").trim();
  const instructions = String(document.getElementById("admin-custom-block-prompt")?.value || "").trim();
  const requiredVariables = normalizeVariableList(document.getElementById("admin-custom-block-variables")?.value || "");
  if (!state.editorState) {
    setPackageStructureError("Abre primero un paquete institucional.");
    return;
  }
  if (!header) {
    setPackageStructureError("Escribe la cabecera del bloque.");
    return;
  }
  if (!instructions) {
    setPackageStructureError("Escribe el prompt del bloque.");
    return;
  }

  const nextSections = packageSections().map(cloneSection);
  const targetIndex = nextSections.findIndex((section) => selectionKey(section) === targetKey);
  if (targetIndex < 0) {
    setPackageStructureError("Selecciona la seccion objetivo.");
    return;
  }

  nextSections[targetIndex].blocks.push({
    block_id: buildCustomId("block"),
    header,
    cabecera: header,
    label: header,
    instructions,
    required_variables: requiredVariables,
    required: true,
  });

  updateEditorSections(nextSections);
  resetPackageStructureForm();
}

function removeCustomSectionFromPackage(sectionKey) {
  const state = getPromptAdminState();
  if (!state.editorState) return;
  const nextSections = packageSections().map(cloneSection);
  const targetSection = nextSections.find((section) => selectionKey(section) === sectionKey);
  if (!targetSection || !isCustomSection(targetSection)) return;

  const targetPath = String(targetSection.section_path || "").trim();
  const next = nextSections.filter((section) => {
    const sectionPath = String(section.section_path || "").trim();
    return !(
      isCustomSection(section)
      && (
        selectionKey(section) === sectionKey
        || sectionPath === targetPath
        || sectionPath.startsWith(`${targetPath}/`)
      )
    );
  });

  const activeKey = String(state.activeSectionKey || "").trim();
  const shouldClearActive = nextSections.some((section) => {
    const sectionPath = String(section.section_path || "").trim();
    return (
      selectionKey(section) === activeKey
      && (
        selectionKey(section) === sectionKey
        || sectionPath === targetPath
        || sectionPath.startsWith(`${targetPath}/`)
      )
    );
  });

  updateEditorSections(next, shouldClearActive ? "" : state.activeSectionKey);
}

function removeCustomBlockFromPackage(sectionKey, blockId) {
  const state = getPromptAdminState();
  if (!state.editorState) return;
  const nextSections = packageSections().map(cloneSection);
  const sectionIndex = nextSections.findIndex((section) => selectionKey(section) === sectionKey);
  if (sectionIndex < 0) return;

  nextSections[sectionIndex].blocks = nextSections[sectionIndex].blocks.filter(
    (block) => String(block.block_id || "") !== String(blockId || ""),
  );

  const targetSection = nextSections[sectionIndex];
  const hasChildren = nextSections.some(
    (section) => String(section.parent_section_path || "").trim() === String(targetSection.section_path || "").trim(),
  );

  if (isCustomSection(targetSection) && !targetSection.blocks.length && !hasChildren) {
    removeCustomSectionFromPackage(sectionKey);
    return;
  }

  updateEditorSections(nextSections);
}

function handleAddPackageStructure() {
  setPackageStructureError("");
  const kind = document.getElementById("admin-custom-structure-kind")?.value || "chapter";
  if (kind === "chapter") {
    addCustomChapterToPackage();
    return;
  }
  if (kind === "section") {
    addCustomSubsectionToPackage();
    return;
  }
  addCustomBlockToPackage();
}

function bindPromptPackageCustomization() {
  if (window.__promptPackageCustomizationBound) return;
  const kindSelect = document.getElementById("admin-custom-structure-kind");
  const addButton = document.getElementById("btn-add-admin-custom-structure");
  const saveButton = document.getElementById("btn-save-admin-custom-structure");
  const list = document.getElementById("admin-custom-structure-list");
  if (!kindSelect || !addButton || !saveButton || !list) return;

  kindSelect.addEventListener("change", () => {
    setPackageStructureError("");
    updatePackageStructureMode();
  });
  addButton.addEventListener("click", () => handleAddPackageStructure());
  saveButton.addEventListener("click", () => savePromptPackageStructure());
  list.addEventListener("click", (event) => {
    const target = event.target instanceof HTMLElement ? event.target : null;
    const removeSectionButton = target?.closest("[data-remove-admin-custom-section]");
    if (removeSectionButton instanceof HTMLElement) {
      removeCustomSectionFromPackage(String(removeSectionButton.dataset.removeAdminCustomSection || ""));
      return;
    }
    const removeBlockButton = target?.closest("[data-remove-admin-custom-block]");
    if (removeBlockButton instanceof HTMLElement) {
      removeCustomBlockFromPackage(
        String(removeBlockButton.dataset.adminBlockSectionKey || ""),
        String(removeBlockButton.dataset.removeAdminCustomBlock || ""),
      );
    }
  });

  window.__promptPackageCustomizationBound = true;
}

function renderVariableTags(block) {
  const variables = Array.isArray(block.required_variables) ? block.required_variables : [];
  if (!variables.length) {
    return '<span class="inline-flex items-center rounded-2xl border border-dashed border-slate-300 bg-slate-50 px-4 py-2 text-[11px] font-semibold text-slate-400">Sin variables definidas</span>';
  }
  return variables.map((value) => `
    <span class="var-tag inline-flex items-center gap-2 rounded-2xl border border-blue-200 bg-blue-50 px-3.5 py-2 text-[11px] font-bold text-blue-700 shadow-sm" data-variable="${escapeHtml(value)}">
      <span>${escapeHtml(value)}</span>
      <button type="button" class="js-remove-var text-blue-300 hover:text-red-500 transition-colors" data-variable="${escapeHtml(value)}">
        <i class="fa-solid fa-circle-xmark"></i>
      </button>
    </span>
  `).join("");
}

function syncPackageTemplateFromField() {
  const templateField = document.getElementById("package-base-template");
  const state = getPromptAdminState();
  if (!templateField || !state.editorState) return;
  state.editorState.template = String(templateField.value || "");
}

function renderPromptPackageContext() {
  const state = getPromptAdminState();
  const templateField = document.getElementById("package-base-template");
  const saveButton = document.getElementById("btn-save-package-context");
  if (templateField) {
    templateField.disabled = !state.editorState;
    const nextValue = String(state.editorState?.template || "");
    if (document.activeElement !== templateField && templateField.value !== nextValue) {
      templateField.value = nextValue;
    }
  }
  if (saveButton) {
    saveButton.disabled = !state.editorState;
  }
}

function bindPromptPackageContext() {
  if (window.__promptPackageContextBound) return;
  const templateField = document.getElementById("package-base-template");
  const saveButton = document.getElementById("btn-save-package-context");
  if (!templateField || !saveButton) return;

  templateField.addEventListener("input", () => {
    syncPackageTemplateFromField();
  });
  saveButton.addEventListener("click", () => savePromptPackageStructure());
  window.__promptPackageContextBound = true;
}

function collectSectionFromDom(section) {
  const container = document.getElementById("prompts-container");
  if (!container || !section) return;

  section.blocks = Array.from(container.querySelectorAll(".prompt-block")).map((blockNode, index) => {
    const existing = ensureSectionBlocks(section)[index] || {};
    const variables = Array.from(blockNode.querySelectorAll(".var-tag[data-variable]"))
      .map((tag) => String(tag.getAttribute("data-variable") || "").trim())
      .filter(Boolean);
    return normalizeBlock(section, {
      ...existing,
      header: blockNode.querySelector(".prompt-block-header")?.value || `Cabecera ${index + 1}`,
      cabecera: blockNode.querySelector(".prompt-block-header")?.value || `Cabecera ${index + 1}`,
      label: blockNode.querySelector(".prompt-block-label")?.value || `Prompt ${index + 1}`,
      instructions: blockNode.querySelector(".prompt-block-instructions")?.value || "",
      required_variables: variables,
      required: Boolean(existing.required ?? true),
    }, index);
  });
  section.source_hints = String(section.blocks[0]?.instructions || "").trim();

  syncPackageTemplateFromField();
}

function renderPromptBlocks(section) {
  const container = document.getElementById("prompts-container");
  if (!container || !section) return;

  const blocks = ensureSectionBlocks(section);
  const { scope, title } = sectionDisplayMeta(section, 1);
  container.innerHTML = blocks.map((block, index) => `
    <div class="prompt-block bg-white rounded-[2.25rem] border border-slate-200 shadow-[0_30px_80px_-52px_rgba(15,23,42,0.45)] overflow-hidden mb-8 fade-in" data-block-index="${index}">
      <input type="hidden" class="prompt-block-label" value="${escapeHtml(block.label || `Prompt ${index + 1}`)}">

      <div class="p-5 md:p-6 flex flex-col gap-4 bg-slate-50/90 border-b border-slate-100">
        <div class="flex flex-wrap gap-3 items-center">
          <div class="px-5 py-2.5 bg-emerald-500 text-white rounded-2xl flex items-center gap-3 shadow-md shadow-emerald-200 shrink-0">
            <i class="fa-solid fa-bolt text-xs"></i>
            <span class="text-xs font-black uppercase tracking-widest">Prompt ${index + 1}</span>
          </div>

          <div class="inline-flex items-center rounded-2xl border border-slate-200 bg-slate-100 px-4 py-3 text-xs font-black uppercase tracking-wide text-slate-500 shadow-sm">
            ${escapeHtml(scope)}
          </div>

          <div class="min-w-[240px] flex-1 rounded-2xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
            <div class="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400">Secci&oacute;n</div>
            <div class="mt-1 text-sm font-bold text-slate-700">${escapeHtml(title)}</div>
          </div>

          <div class="min-w-[260px] flex-1 overflow-hidden rounded-2xl border border-blue-200 bg-white shadow-sm">
            <div class="flex items-center">
              <div class="border-r border-blue-100 bg-blue-50 px-4 py-3 text-[10px] font-black uppercase tracking-[0.2em] text-blue-600">Cabecera ${index + 1}</div>
              <input type="text" class="prompt-block-header flex-1 bg-white px-4 py-3 text-sm font-semibold text-slate-700 outline-none" value="${escapeHtml(block.header || `Cabecera ${index + 1}`)}" placeholder="Ej: Realidad problem&aacute;tica">
            </div>
          </div>

          ${index > 0 ? `
            <button type="button" class="js-remove-block w-12 h-12 flex items-center justify-center rounded-2xl bg-red-50 text-red-400 hover:bg-red-500 hover:text-white transition-all shadow-sm">
              <i class="fa-solid fa-trash-can"></i>
            </button>
          ` : ""}
        </div>
      </div>

      <div class="p-6 md:p-8 space-y-6">
        <div class="space-y-3">
          <label class="text-[11px] font-black text-slate-400 uppercase tracking-[0.2em] ml-2">Prompt</label>
          <textarea class="prompt-block-instructions w-full h-[220px] p-7 bg-slate-900 text-blue-50 border-2 border-slate-800 rounded-[2rem] text-sm font-mono leading-relaxed focus:border-blue-500 outline-none shadow-2xl resize-none"
            placeholder="Escribe aqui el prompt de este bloque...">${escapeHtml(index === 0 && String(section.source_hints || "").trim() ? section.source_hints : block.instructions)}</textarea>
        </div>

        <div class="bg-slate-50/80 p-6 rounded-[2rem] border border-slate-100 shadow-inner shadow-slate-100">
          <div class="flex flex-wrap items-center justify-between gap-3 mb-4">
            <div class="flex items-center gap-2">
              <i class="fa-solid fa-tags text-blue-500 text-sm"></i>
              <label class="text-[11px] font-black text-slate-600 uppercase tracking-widest">Variables de este bloque</label>
            </div>
          </div>

          <div class="local-vars-tags flex flex-wrap gap-2 mb-4">${renderVariableTags(block)}</div>

          <div class="flex gap-3">
            <input type="text" placeholder="A&ntilde;adir variable espec&iacute;fica (ej: poblaci&oacute;n, muestra...)" class="local-var-input flex-1 px-5 py-3 bg-white border border-slate-200 rounded-2xl text-sm outline-none focus:border-blue-400 transition-all shadow-sm">
            <button type="button" class="js-add-var w-14 bg-slate-900 text-white rounded-2xl hover:bg-blue-600 transition-all shadow-lg shadow-slate-200">
              <i class="fa-solid fa-plus"></i>
            </button>
          </div>
        </div>
      </div>
    </div>
  `).join("");

  container.querySelectorAll(".js-remove-block").forEach((button) => {
    button.addEventListener("click", () => removePromptBlock(Number(button.closest(".prompt-block")?.dataset.blockIndex || -1)));
  });
  container.querySelectorAll(".js-add-var").forEach((button) => {
    button.addEventListener("click", () => addVariableToBlock(button));
  });
  container.querySelectorAll(".js-remove-var").forEach((button) => {
    button.addEventListener("click", () => {
      removeVariableFromBlock(
        Number(button.closest(".prompt-block")?.dataset.blockIndex || -1),
        String(button.dataset.variable || "").trim(),
      );
    });
  });
}

function addPromptBlock() {
  const section = currentEditableSection();
  if (!section) return;
  collectSectionFromDom(section);
  const nextIndex = ensureSectionBlocks(section).length;
  ensureSectionBlocks(section).push(normalizeBlock(section, {}, nextIndex));
  renderPromptBlocks(section);
}

function removePromptBlock(blockIndex) {
  const section = currentEditableSection();
  if (!section) return;
  collectSectionFromDom(section);
  section.blocks = ensureSectionBlocks(section).filter((_, index) => index !== blockIndex);
  if (!section.blocks.length) {
    section.blocks = [normalizeBlock(section, {}, 0)];
  }
  renderPromptBlocks(section);
}

function addVariableToBlock(button) {
  const section = currentEditableSection();
  if (!section) return;
  collectSectionFromDom(section);
  const blockNode = button?.closest(".prompt-block");
  const blockIndex = Number(blockNode?.dataset.blockIndex || -1);
  if (blockIndex < 0) return;
  const input = blockNode.querySelector(".local-var-input");
  const variableName = String(input?.value || "").trim().replace(/\s+/g, "_").toLowerCase();
  if (!variableName) return;

  const blocks = ensureSectionBlocks(section);
  const target = blocks[blockIndex];
  if (!Array.isArray(target.required_variables)) target.required_variables = [];
  if (!target.required_variables.includes(variableName)) {
    target.required_variables.push(variableName);
  }
  input.value = "";
  renderPromptBlocks(section);
}

function removeVariableFromBlock(blockIndex, variableName) {
  const section = currentEditableSection();
  if (!section) return;
  collectSectionFromDom(section);
  const target = ensureSectionBlocks(section)[blockIndex];
  if (!target) return;
  target.required_variables = (Array.isArray(target.required_variables) ? target.required_variables : []).filter(
    (value) => String(value || "").trim() !== String(variableName || "").trim(),
  );
  renderPromptBlocks(section);
}

function openManualModal(sectionKey) {
  const section = typeof sectionKey === "string" ? findEditableSection(getPromptAdminState().editorState, sectionKey) : sectionKey;
  if (!section) {
    alert("No se pudo resolver la seccion seleccionada.");
    return;
  }

  patchPromptAdminState({ activeSectionKey: selectionKey(section) });
  const state = getPromptAdminState();
  const logoImg = document.getElementById("manual-logo-img");
  if (logoImg) {
    if (state.meta.logo) {
      logoImg.src = state.meta.logo;
      logoImg.classList.remove("hidden");
    } else {
      logoImg.classList.add("hidden");
    }
  }

  document.getElementById("manual-title-display").textContent = state.meta.title || state.editorState?.name || "Paquete institucional";
  document.getElementById("manual-subtitle-display").textContent = state.meta.subtitle || state.editorState?.name || "Paquete institucional";

  const promptIdField = document.getElementById("manual-prompt-name");
  if (promptIdField) {
    promptIdField.value = buildPromptIdentifier(state, section);
    promptIdField.readOnly = true;
    promptIdField.classList.add("bg-slate-800", "text-slate-200");
    promptIdField.classList.remove("cursor-not-allowed");
  }

  renderPromptBlocks(section);
  document.getElementById("modal-manual-config")?.classList.remove("hidden");
}

function closeManualModal() {
  document.getElementById("modal-manual-config")?.classList.add("hidden");
}

async function savePackage() {
  return persistEditorState({
    closeAfterSave: true,
    successMessage: "Paquete institucional guardado correctamente.",
  });
}

async function savePromptPackageStructure() {
  return persistEditorState({
    closeAfterSave: false,
    successMessage: "Estructura del paquete guardada correctamente.",
  });
}

async function persistEditorState({ closeAfterSave = false, successMessage = "Paquete institucional guardado correctamente." } = {}) {
  const state = getPromptAdminState();
  if (!state.editorState) {
    alert("No hay un paquete activo para guardar.");
    return;
  }

  syncPackageTemplateFromField();
  const modalOpen = !document.getElementById("modal-manual-config")?.classList.contains("hidden");
  const section = modalOpen ? currentEditableSection() : null;
  if (section) {
    collectSectionFromDom(section);
  }

  const payload = {
    id: state.editorState.id,
    name: state.editorState.name,
    doc_type: state.editorState.doc_type || state.editorState.docType || "Tesis Completa",
    is_active: state.editorState.is_active ?? true,
    format_id: state.editorState.format_id,
    format_name: state.editorState.format_name,
    format_version: state.editorState.format_version,
    system_instruction: state.editorState.system_instruction || "",
    variables: Array.isArray(state.editorState.variables) ? state.editorState.variables : [],
    template: state.editorState.template || "",
    sections: Array.isArray(state.editorState.sections) ? state.editorState.sections : [],
  };

  const saved = state.editorState?.id
    ? await requestJson(`/api/prompts/${encodeURIComponent(state.editorState.id)}`, { method: "PUT", body: payload })
    : await requestJson("/api/prompts", { method: "POST", body: payload });

  patchPromptAdminState({
    promptPackage: saved,
    editorState: createAdminEditorState(saved),
  });

  renderPromptPackageContext();
  window.renderPromptSectionIndex?.();
  window.renderPromptPackageCustomization?.();
  if (closeAfterSave) {
    closeManualModal();
  }
  alert(successMessage);
}

export function bootPromptPackageEditor() {
  bindPromptPackageContext();
  bindPromptPackageCustomization();
  window.openManualModal = openManualModal;
  window.closeManualModal = closeManualModal;
  window.addPromptBlock = addPromptBlock;
  window.addVariableToBlock = addVariableToBlock;
  window.savePackage = savePackage;
  window.savePromptPackageStructure = savePromptPackageStructure;
  window.renderPromptPackageContext = renderPromptPackageContext;
  window.renderPromptPackageCustomization = renderPromptPackageCustomization;
}
