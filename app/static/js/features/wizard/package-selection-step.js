import {
  fetchPromptPackage,
  normalizeSelectedSections,
  selectionKey,
  buildSectionTree,
  isGroupingOnlySection,
  hasOwnBlocks,
  countRequiredVariables,
  parentScopeLabel,
  computeNodeSelectionState,
  applyNodeSelection,
  collectConcreteSelectionKeys
} from "./prompt-package-client.js";
import { flattenSections } from "./section-selection.js";
import { escapeHtml } from "../../shared/dom.js";

function cloneBlock(block) {
  return {
    block_id: block?.block_id || block?.id || "",
    header: block?.header || block?.cabecera || block?.titulo_cabecera || block?.label || "",
    cabecera: block?.cabecera || block?.header || block?.titulo_cabecera || block?.label || "",
    label: block?.label || block?.header || block?.cabecera || "",
    instructions: block?.instructions || "",
    required_variables: Array.isArray(block?.required_variables) ? [...block.required_variables] : [],
    required: Boolean(block?.required ?? true),
  };
}

function cloneSection(section) {
  return {
    section_id: section?.section_id || section?.sectionId || "",
    section_path: section?.section_path || section?.sectionPath || section?.path || "",
    section_title: section?.section_title || section?.sectionTitle || section?.title || "",
    parent_section_path: section?.parent_section_path || section?.parentSectionPath || "",
    section_level: Number(section?.section_level || section?.sectionLevel || 1),
    section_order: Number(section?.section_order || section?.sectionOrder || 0),
    optional: Boolean(section?.optional),
    default_selected: Boolean(section?.default_selected ?? section?.defaultSelected ?? true),
    source_hints: section?.source_hints || section?.sourceHints || "",
    blocks: Array.isArray(section?.blocks) ? section.blocks.map(cloneBlock) : [],
  };
}

function isCustomSection(section) {
  return String(section?.section_id || section?.sectionId || "").startsWith("custom_section_");
}

function isCustomBlock(block) {
  return String(block?.block_id || block?.id || "").startsWith("custom_block_");
}

function mergePromptSections(baseSections, snapshotSections) {
  const safeBase = Array.isArray(baseSections) ? baseSections.map(cloneSection) : [];
  const normalizedOverlay = (Array.isArray(snapshotSections) ? snapshotSections : []).map(cloneSection);
  const overlayByKey = new Map();

  normalizedOverlay.forEach((section) => {
    const keys = [
      selectionKey(section),
      String(section.section_path || "").trim(),
      String(section.section_id || "").trim(),
    ].filter(Boolean);
    keys.forEach((key) => overlayByKey.set(key, section));
  });

  const merged = safeBase.map((section) => {
    const overlay = overlayByKey.get(selectionKey(section))
      || overlayByKey.get(String(section.section_path || "").trim())
      || overlayByKey.get(String(section.section_id || "").trim());
    if (!overlay || typeof overlay !== "object") {
      return section;
    }
    return {
      ...section,
      ...overlay,
      section_id: section.section_id || overlay.section_id || overlay.sectionId || "",
      section_path: section.section_path || overlay.section_path || overlay.sectionPath || overlay.path || "",
      section_title: section.section_title || overlay.section_title || overlay.sectionTitle || overlay.title || "",
      parent_section_path: section.parent_section_path || overlay.parent_section_path || overlay.parentSectionPath || "",
      section_level: Number(section.section_level || overlay.section_level || overlay.sectionLevel || 1),
      section_order: Number(section.section_order || overlay.section_order || overlay.sectionOrder || 0),
      source_hints: section.source_hints || overlay.source_hints || overlay.sourceHints || "",
      blocks: Array.isArray(overlay.blocks) && overlay.blocks.length ? overlay.blocks.map(cloneBlock) : section.blocks,
    };
  });

  const seenKeys = new Set(
    merged.flatMap((section) => [
      selectionKey(section),
      String(section.section_path || "").trim(),
      String(section.section_id || "").trim(),
    ].filter(Boolean))
  );

  normalizedOverlay.forEach((section) => {
    const keys = [
      selectionKey(section),
      String(section.section_path || "").trim(),
      String(section.section_id || "").trim(),
    ].filter(Boolean);
    if (keys.some((key) => seenKeys.has(key))) return;
    merged.push(section);
    keys.forEach((key) => seenKeys.add(key));
  });

  return merged;
}

function mergeProjectSnapshot(promptPackage, project) {
  if (
    !project
    || String(project?.format_id || "") !== String(promptPackage?.format_id || project?.format_id || "")
    || !project?.prompt_snapshot
    || typeof project.prompt_snapshot !== "object"
  ) {
    return promptPackage;
  }

  return {
    ...promptPackage,
    ...project.prompt_snapshot,
    sections: mergePromptSections(promptPackage.sections, project.prompt_snapshot.sections),
    selected_sections: Array.isArray(project.selected_sections)
      ? project.selected_sections
      : (Array.isArray(project.prompt_snapshot?.selected_sections) ? project.prompt_snapshot.selected_sections : promptPackage.selected_sections),
  };
}

function selectedSectionsFromKeys(promptPackage, selectedKeys) {
  const sections = flattenSections(promptPackage);
  const tree = buildSectionTree(promptPackage);
  const safeKeys = selectedKeys instanceof Set ? selectedKeys : new Set();
  const concreteKeys = new Set();
  tree.forEach((node) => {
    collectConcreteSelectionKeys(node, []).forEach((key) => concreteKeys.add(key));
  });

  return sections
    .filter((section) => {
      const key = selectionKey(section);
      return safeKeys.has(key) && concreteKeys.has(key);
    })
    .map((section) => ({
      section_id: section.section_id || "",
      section_path: section.section_path || "",
      section_title: section.section_title || "",
      parent_section_path: section.parent_section_path || "",
      section_level: Number(section.section_level || 1),
      section_order: Number(section.section_order || 0),
      optional: Boolean(section.optional),
      default_selected: Boolean(section.default_selected ?? true),
    }));
}

function metricLabel(section) {
  const ownBlocks = Array.isArray(section?.blocks) ? section.blocks.length : 0;
  const childCount = Array.isArray(section?.children) ? section.children.length : 0;
  if (childCount > 0) {
    return `${ownBlocks} bloque(s) propios · ${childCount} hija(s)`;
  }
  return `${ownBlocks} bloque(s) · ${countRequiredVariables(section)} variable(s) requerida(s)`;
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

function uniqueSectionPath(promptPackage, parentPath, title) {
  const safeTitle = String(title || "").trim();
  const basePath = parentPath ? `${parentPath}/${safeTitle}` : safeTitle;
  const existing = new Set(
    flattenSections(promptPackage)
      .map((section) => String(section?.section_path || "").trim().toLowerCase())
      .filter(Boolean)
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

function nextSectionOrder(promptPackage) {
  return flattenSections(promptPackage).reduce(
    (maxOrder, section) => Math.max(maxOrder, Number(section?.section_order || 0)),
    0,
  ) + 1;
}

function findSectionByKey(promptPackage, key) {
  const safeKey = String(key || "").trim();
  if (!safeKey) return null;
  return flattenSections(promptPackage).find((section) => {
    const sectionKey = selectionKey(section);
    return sectionKey === safeKey
      || String(section?.section_path || "").trim() === safeKey
      || String(section?.section_id || "").trim() === safeKey;
  }) || null;
}

function customStructureSummary(promptPackage) {
  const sections = flattenSections(promptPackage);
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

export function createPackageSelectionStep({
  store,
  getGrid,
  getFormatLabel,
  getNextButton,
  onPromptPackageResolved,
  onSelectionChanged,
}) {
  let selectedKeys = new Set();
  let expandedKeys = new Set();
  let expansionHydrated = false;
  let selectionHydrated = false;
  let customEventsBound = false;

  function commitSelection(promptPackage) {
    const normalized = selectedSectionsFromKeys(promptPackage, selectedKeys);
    selectionHydrated = true;
    if (promptPackage && typeof promptPackage === "object") {
      promptPackage.selected_sections = normalized;
    }
    store.setSelectedSections(normalized);
    onSelectionChanged?.(normalized, new Set(selectedKeys));
    return normalized;
  }

  function concreteKeySet(promptPackage) {
    const keys = new Set();
    buildSectionTree(promptPackage).forEach((node) => {
      collectConcreteSelectionKeys(node, []).forEach((key) => keys.add(key));
    });
    return keys;
  }

  function syncPromptPackage(nextPromptPackage, { selectKeys = [], deselectKeys = [], expandNodeKeys = [] } = {}) {
    const normalizedPackage = {
      ...(nextPromptPackage || {}),
      sections: Array.isArray(nextPromptPackage?.sections) ? nextPromptPackage.sections.map(cloneSection) : [],
    };

    deselectKeys.forEach((key) => selectedKeys.delete(key));
    selectKeys.forEach((key) => {
      if (key) selectedKeys.add(key);
    });
    expandNodeKeys.forEach((key) => {
      if (key) expandedKeys.add(key);
    });

    const concreteKeys = concreteKeySet(normalizedPackage);
    selectedKeys = new Set([...selectedKeys].filter((key) => concreteKeys.has(key)));

    store.setPromptPackage(normalizedPackage);
    onPromptPackageResolved?.(normalizedPackage);
    commitSelection(normalizedPackage);
    render(normalizedPackage);
    return normalizedPackage;
  }

  function hydrateExpandedKeys(tree) {
    const previous = expandedKeys instanceof Set ? expandedKeys : new Set();
    const next = new Set();

    const visit = (node) => {
      const nodeKey = selectionKey(node);
      const children = Array.isArray(node?.children) ? node.children : [];
      if (children.length) {
        if (expansionHydrated && previous.has(nodeKey)) {
          next.add(nodeKey);
        }
      }
      children.forEach((child) => visit(child));
    };

    (Array.isArray(tree) ? tree : []).forEach((node) => visit(node));
    expandedKeys = next;
    expansionHydrated = true;
  }

  function setCustomError(message = "") {
    const errorBox = document.getElementById("custom-structure-error");
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

  function updateCustomFormMode() {
    const kind = document.getElementById("custom-structure-kind")?.value || "chapter";
    const parentGroup = document.getElementById("custom-parent-group");
    const targetGroup = document.getElementById("custom-target-group");
    const titleGroup = document.getElementById("custom-title-group");
    const headerGroup = document.getElementById("custom-header-group");
    const varsGroup = document.getElementById("custom-vars-group");
    const promptGroup = document.getElementById("custom-prompt-group");
    const addButton = document.getElementById("btn-add-custom-structure");
    const titleInput = document.getElementById("custom-section-title");
    const headerInput = document.getElementById("custom-block-header");

    parentGroup?.classList.toggle("hidden", kind !== "section");
    targetGroup?.classList.toggle("hidden", kind !== "block");
    titleGroup?.classList.toggle("hidden", kind === "block");
    headerGroup?.classList.toggle("hidden", kind === "chapter");
    varsGroup?.classList.toggle("hidden", kind === "chapter");
    promptGroup?.classList.toggle("hidden", kind === "chapter");

    if (addButton) {
      addButton.innerHTML = kind === "chapter"
        ? '<i class="fa-solid fa-plus"></i> Agregar capítulo'
        : (kind === "section"
            ? '<i class="fa-solid fa-plus"></i> Agregar subsección'
            : '<i class="fa-solid fa-plus"></i> Agregar bloque');
    }

    if (titleInput) {
      titleInput.placeholder = kind === "chapter"
        ? "Ej: CAPÍTULO ESPECIAL"
        : "Ej: 1.6 Alcance operativo adicional";
    }
    if (headerInput) {
      headerInput.placeholder = kind === "block"
        ? "Ej: Alcance operativo"
        : "Ej: Desarrollo del alcance operativo";
    }
  }

  function resetCustomForm() {
    const titleInput = document.getElementById("custom-section-title");
    const headerInput = document.getElementById("custom-block-header");
    const promptInput = document.getElementById("custom-block-prompt");
    const variablesInput = document.getElementById("custom-block-variables");
    if (titleInput) titleInput.value = "";
    if (headerInput) headerInput.value = "";
    if (promptInput) promptInput.value = "";
    if (variablesInput) variablesInput.value = "";
    setCustomError("");
  }

  function renderCustomStructurePanel(promptPackage) {
    const kindSelect = document.getElementById("custom-structure-kind");
    const parentSelect = document.getElementById("custom-parent-section");
    const targetSelect = document.getElementById("custom-target-section");
    const addButton = document.getElementById("btn-add-custom-structure");
    const list = document.getElementById("custom-structure-list");
    const sections = promptPackage ? flattenSections(promptPackage) : [];
    const sectionOptions = sections.map((section) => ({
      key: selectionKey(section),
      label: sectionOptionLabel(section),
      isCustom: isCustomSection(section),
    }));

    [parentSelect, targetSelect].forEach((select) => {
      if (!select) return;
      const previousValue = select.value;
      select.innerHTML = sectionOptions.length
        ? sectionOptions.map((option) => `
            <option value="${escapeHtml(option.key)}">${escapeHtml(option.isCustom ? `[Personalizado] ${option.label}` : option.label)}</option>
          `).join("")
        : '<option value="">No hay secciones disponibles</option>';

      if (sectionOptions.some((option) => option.key === previousValue)) {
        select.value = previousValue;
      }
    });

    const controls = [
      kindSelect,
      parentSelect,
      targetSelect,
      document.getElementById("custom-section-title"),
      document.getElementById("custom-block-header"),
      document.getElementById("custom-block-prompt"),
      document.getElementById("custom-block-variables"),
      addButton,
    ];
    controls.forEach((control) => {
      if (!control) return;
      control.disabled = !promptPackage;
    });

    updateCustomFormMode();

    if (!list) return;
    if (!promptPackage) {
      list.innerHTML = '<div class="rounded-xl border border-dashed border-slate-200 bg-slate-50 px-4 py-4 text-sm text-slate-400">Selecciona un formato para habilitar la personalización.</div>';
      return;
    }

    const { customSections, customBlocks } = customStructureSummary(promptPackage);
    if (!customSections.length && !customBlocks.length) {
      list.innerHTML = '<div class="rounded-xl border border-dashed border-slate-200 bg-slate-50 px-4 py-4 text-sm text-slate-400">Aún no agregaste elementos personalizados.</div>';
      return;
    }

    const sectionItems = customSections.map((section) => `
      <div class="rounded-2xl border border-blue-200 bg-blue-50/50 px-4 py-4">
        <div class="flex items-start justify-between gap-3">
          <div class="min-w-0">
            <div class="text-[10px] font-black uppercase tracking-widest text-blue-600">Sección personalizada</div>
            <div class="mt-1 text-sm font-bold text-slate-800">${escapeHtml(sectionOptionLabel(section))}</div>
            <div class="mt-1 text-[11px] text-slate-500">${escapeHtml(metricLabel({ ...section, children: [] }))}</div>
          </div>
          <button type="button" class="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-red-200 bg-white text-red-400 transition hover:bg-red-500 hover:text-white" data-remove-custom-section="${escapeHtml(selectionKey(section))}" aria-label="Eliminar sección personalizada">
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
          <button type="button" class="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-red-200 bg-white text-red-400 transition hover:bg-red-500 hover:text-white" data-remove-custom-block="${escapeHtml(block.block_id || "")}" data-block-section-key="${escapeHtml(selectionKey(section))}" aria-label="Eliminar bloque personalizado">
            <i class="fa-solid fa-trash-can"></i>
          </button>
        </div>
      </div>
    `).join("");

    list.innerHTML = `
      <div class="space-y-3">
        ${sectionItems}
        ${blockItems}
      </div>
    `;
  }

  function addCustomChapter(promptPackage) {
    const titleInput = document.getElementById("custom-section-title");
    const rawTitle = String(titleInput?.value || "").trim();
    if (!rawTitle) {
      setCustomError("Escribe el título del capítulo personalizado.");
      return;
    }

    const sectionPath = uniqueSectionPath(promptPackage, "", rawTitle);
    const sectionTitle = sectionPath.split("/").pop()?.trim() || rawTitle;
    const newSection = {
      section_id: buildCustomId("section"),
      section_path: sectionPath,
      section_title: sectionTitle,
      parent_section_path: "",
      section_level: 1,
      section_order: nextSectionOrder(promptPackage),
      optional: false,
      default_selected: true,
      source_hints: "",
      blocks: [],
    };

    syncPromptPackage(
      {
        ...promptPackage,
        sections: [...(Array.isArray(promptPackage.sections) ? promptPackage.sections.map(cloneSection) : []), newSection],
      },
      { expandNodeKeys: [selectionKey(newSection)] },
    );
    resetCustomForm();
  }

  function addCustomSubsection(promptPackage) {
    const parentKey = String(document.getElementById("custom-parent-section")?.value || "").trim();
    const title = String(document.getElementById("custom-section-title")?.value || "").trim();
    const header = String(document.getElementById("custom-block-header")?.value || "").trim() || title;
    const instructions = String(document.getElementById("custom-block-prompt")?.value || "").trim();
    const requiredVariables = normalizeVariableList(document.getElementById("custom-block-variables")?.value || "");

    const parentSection = findSectionByKey(promptPackage, parentKey);
    if (!parentSection) {
      setCustomError("Selecciona la sección padre donde quieres crear la subsección.");
      return;
    }
    if (!title) {
      setCustomError("Escribe el título de la subsección personalizada.");
      return;
    }
    if (!instructions) {
      setCustomError("Escribe el prompt de la subsección personalizada.");
      return;
    }

    const sectionPath = uniqueSectionPath(promptPackage, String(parentSection.section_path || "").trim(), title);
    const sectionTitle = sectionPath.split("/").pop()?.trim() || title;
    const newSection = {
      section_id: buildCustomId("section"),
      section_path: sectionPath,
      section_title: sectionTitle,
      parent_section_path: String(parentSection.section_path || "").trim(),
      section_level: Number(parentSection.section_level || 1) + 1,
      section_order: nextSectionOrder(promptPackage),
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
    };

    syncPromptPackage(
      {
        ...promptPackage,
        sections: [...(Array.isArray(promptPackage.sections) ? promptPackage.sections.map(cloneSection) : []), newSection],
      },
      {
        selectKeys: [selectionKey(newSection)],
        expandNodeKeys: [selectionKey(parentSection), selectionKey(newSection)],
      },
    );
    resetCustomForm();
  }

  function addCustomBlock(promptPackage) {
    const targetKey = String(document.getElementById("custom-target-section")?.value || "").trim();
    const header = String(document.getElementById("custom-block-header")?.value || "").trim();
    const instructions = String(document.getElementById("custom-block-prompt")?.value || "").trim();
    const requiredVariables = normalizeVariableList(document.getElementById("custom-block-variables")?.value || "");
    const targetSection = findSectionByKey(promptPackage, targetKey);

    if (!targetSection) {
      setCustomError("Selecciona la sección donde deseas agregar el bloque.");
      return;
    }
    if (!header) {
      setCustomError("Escribe la cabecera del bloque extra.");
      return;
    }
    if (!instructions) {
      setCustomError("Escribe el prompt del bloque extra.");
      return;
    }

    const nextSections = (Array.isArray(promptPackage.sections) ? promptPackage.sections : []).map(cloneSection);
    const targetIndex = nextSections.findIndex((section) => selectionKey(section) === selectionKey(targetSection));
    if (targetIndex < 0) {
      setCustomError("No se pudo actualizar la sección seleccionada.");
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

    syncPromptPackage(
      {
        ...promptPackage,
        sections: nextSections,
      },
      {
        selectKeys: [selectionKey(targetSection)],
        expandNodeKeys: [selectionKey(targetSection)],
      },
    );
    resetCustomForm();
  }

  function removeCustomSection(sectionKey) {
    const promptPackage = store.getState().promptPackage;
    if (!promptPackage) return;

    const sections = (Array.isArray(promptPackage.sections) ? promptPackage.sections : []).map(cloneSection);
    const targetSection = sections.find((section) => selectionKey(section) === sectionKey);
    if (!targetSection || !isCustomSection(targetSection)) return;

    const targetPath = String(targetSection.section_path || "").trim();
    const removedKeys = new Set();
    const nextSections = sections.filter((section) => {
      const sectionPath = String(section.section_path || "").trim();
      const removeSection = isCustomSection(section)
        && (
          selectionKey(section) === sectionKey
          || sectionPath === targetPath
          || sectionPath.startsWith(`${targetPath}/`)
        );
      if (removeSection) {
        removedKeys.add(selectionKey(section));
        expandedKeys.delete(selectionKey(section));
      }
      return !removeSection;
    });

    syncPromptPackage(
      {
        ...promptPackage,
        sections: nextSections,
      },
      {
        deselectKeys: [...removedKeys],
      },
    );
  }

  function removeCustomBlock(sectionKey, blockId) {
    const promptPackage = store.getState().promptPackage;
    if (!promptPackage) return;

    const sections = (Array.isArray(promptPackage.sections) ? promptPackage.sections : []).map(cloneSection);
    const sectionIndex = sections.findIndex((section) => selectionKey(section) === sectionKey);
    if (sectionIndex < 0) return;

    sections[sectionIndex].blocks = sections[sectionIndex].blocks.filter(
      (block) => String(block.block_id || "") !== String(blockId || "")
    );

    const targetSection = sections[sectionIndex];
    const hasChildren = sections.some(
      (section) => String(section.parent_section_path || "").trim() === String(targetSection.section_path || "").trim()
    );

    if (isCustomSection(targetSection) && !targetSection.blocks.length && !hasChildren) {
      removeCustomSection(sectionKey);
      return;
    }

    syncPromptPackage(
      {
        ...promptPackage,
        sections,
      },
      {
        deselectKeys: targetSection.blocks.length ? [] : [sectionKey],
      },
    );
  }

  function handleAddCustomStructure() {
    const promptPackage = store.getState().promptPackage;
    if (!promptPackage) {
      setCustomError("Selecciona primero un formato institucional.");
      return;
    }

    setCustomError("");
    const kind = document.getElementById("custom-structure-kind")?.value || "chapter";
    if (kind === "chapter") {
      addCustomChapter(promptPackage);
      return;
    }
    if (kind === "section") {
      addCustomSubsection(promptPackage);
      return;
    }
    addCustomBlock(promptPackage);
  }

  function bindCustomStructureEvents() {
    if (customEventsBound) return;
    const kindSelect = document.getElementById("custom-structure-kind");
    const addButton = document.getElementById("btn-add-custom-structure");
    const list = document.getElementById("custom-structure-list");

    if (!kindSelect || !addButton || !list) return;

    kindSelect.addEventListener("change", () => {
      setCustomError("");
      updateCustomFormMode();
    });
    addButton.addEventListener("click", () => handleAddCustomStructure());
    list.addEventListener("click", (event) => {
      const target = event.target instanceof HTMLElement ? event.target : null;
      const removeSectionButton = target?.closest("[data-remove-custom-section]");
      if (removeSectionButton instanceof HTMLElement) {
        removeCustomSection(String(removeSectionButton.dataset.removeCustomSection || ""));
        return;
      }

      const removeBlockButton = target?.closest("[data-remove-custom-block]");
      if (removeBlockButton instanceof HTMLElement) {
        removeCustomBlock(
          String(removeBlockButton.dataset.blockSectionKey || ""),
          String(removeBlockButton.dataset.removeCustomBlock || ""),
        );
      }
    });

    customEventsBound = true;
  }

  function renderNode({
    node,
    tree,
    depth,
    indexRef,
    promptPackage,
    container,
    nextButton,
  }) {
    const nodeKey = selectionKey(node);
    const state = computeNodeSelectionState(node, selectedKeys);
    const isChecked = state === "checked";
    const isPartial = state === "indeterminate";
    const groupingOnly = isGroupingOnlySection(node);
    const ownBlocks = hasOwnBlocks(node);
    const children = Array.isArray(node?.children) ? node.children : [];
    const canExpand = children.length > 0;
    const isExpanded = canExpand && expandedKeys.has(nodeKey);
    const scope = parentScopeLabel(node);
    const title = node.section_title || node.section_path || `Seccion ${indexRef.value}`;

    const wrapper = document.createElement("div");
    wrapper.className = "col-span-full";
    wrapper.style.paddingLeft = `${Math.max(0, depth) * 20}px`;

    const card = document.createElement("div");
    card.className = "chapter-card group p-4 bg-white rounded-2xl border-2 shadow-sm cursor-pointer transition-all";
    card.classList.add(isChecked ? "border-blue-400" : (isPartial ? "border-blue-200" : "border-slate-100"));
    if (isChecked) {
      card.classList.add("bg-blue-50/50");
    } else if (isPartial) {
      card.classList.add("bg-blue-50/30");
    } else {
      card.classList.add("hover:border-blue-400", "hover:bg-blue-50/50");
    }

    card.innerHTML = `
      <div class="flex items-start justify-between gap-4">
        <div class="flex items-start gap-4 min-w-0">
          <div class="w-10 h-10 rounded-xl border border-slate-200 bg-slate-50 flex items-center justify-center shrink-0 transition-colors group-hover:bg-white group-hover:border-blue-200">
            <span class="text-sm font-black ${isChecked || isPartial ? "text-blue-500" : "text-slate-400"}">${indexRef.value}</span>
          </div>
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-2 flex-wrap">
              ${canExpand ? `
                <button type="button" class="wizard-tree-toggle inline-flex h-6 w-6 items-center justify-center rounded-full border border-slate-200 bg-white text-xs font-black text-slate-500 transition-colors hover:border-blue-300 hover:text-blue-600" aria-label="${isExpanded ? "Comprimir" : "Expandir"} ${escapeHtml(title)}">
                  ${isExpanded ? "-" : "+"}
                </button>
              ` : ""}
              <div class="text-[9px] font-black text-blue-500 uppercase tracking-widest">${escapeHtml(scope || node.section_path || title)}</div>
              ${node.optional ? '<span class="text-[9px] font-black uppercase tracking-widest text-amber-600 bg-amber-50 border border-amber-200 rounded-full px-2 py-0.5">Opcional</span>' : ""}
              ${groupingOnly ? '<span class="text-[9px] font-black uppercase tracking-widest text-slate-500 bg-slate-100 border border-slate-200 rounded-full px-2 py-0.5">Agrupador</span>' : ""}
              ${isCustomSection(node) ? '<span class="text-[9px] font-black uppercase tracking-widest text-emerald-600 bg-emerald-50 border border-emerald-200 rounded-full px-2 py-0.5">Personalizado</span>' : ""}
            </div>
            <div class="font-bold text-slate-800 leading-tight text-sm mt-1">${escapeHtml(title)}</div>
            <div class="text-[11px] text-slate-400 mt-1">${escapeHtml(metricLabel(node))}</div>
          </div>
        </div>
        <div class="flex items-start gap-3 shrink-0">
          ${!ownBlocks && Array.isArray(node.children) && node.children.length ? '<i class="fa-solid fa-sitemap text-slate-300 mt-1"></i>' : ""}
          <input type="checkbox" class="wizard-tree-checkbox mt-1 h-5 w-5 rounded border-slate-300 text-blue-600 focus:ring-blue-500">
        </div>
      </div>
    `;

    const checkbox = card.querySelector(".wizard-tree-checkbox");
    if (checkbox) {
      checkbox.checked = isChecked;
      checkbox.indeterminate = isPartial;
      checkbox.setAttribute("aria-label", title);
      checkbox.addEventListener("click", (event) => event.stopPropagation());
      checkbox.addEventListener("change", () => {
        selectedKeys = applyNodeSelection(tree, selectedKeys, nodeKey, checkbox.checked);
        commitSelection(promptPackage);
        render(promptPackage);
        if (nextButton) nextButton.disabled = selectedKeys.size === 0;
      });
    }

    const toggleButton = card.querySelector(".wizard-tree-toggle");
    if (toggleButton) {
      toggleButton.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        if (isExpanded) {
          expandedKeys.delete(nodeKey);
        } else {
          expandedKeys.add(nodeKey);
        }
        render(promptPackage);
      });
    }

    card.addEventListener("click", (event) => {
      if (
        event.target instanceof HTMLElement
        && (
          event.target.closest("input[type='checkbox']")
          || event.target.closest(".wizard-tree-toggle")
        )
      ) {
        return;
      }
      selectedKeys = applyNodeSelection(tree, selectedKeys, nodeKey, !isChecked);
      commitSelection(promptPackage);
      render(promptPackage);
      if (nextButton) nextButton.disabled = selectedKeys.size === 0;
    });

    wrapper.appendChild(card);
    container.appendChild(wrapper);
    indexRef.value += 1;

    if (isExpanded) {
      children.forEach((child) => {
        renderNode({
          node: child,
          tree,
          depth: depth + 1,
          indexRef,
          promptPackage,
          container,
          nextButton,
        });
      });
    }
  }

  function render(promptPackage = store.getState().promptPackage) {
    const grid = getGrid?.();
    const nextButton = getNextButton?.();
    if (!grid) return;

    const tree = buildSectionTree(promptPackage);
    grid.innerHTML = "";

    if (!tree.length) {
      if (nextButton) nextButton.disabled = true;
      grid.innerHTML = '<div class="col-span-full text-sm text-slate-500 p-5 bg-slate-50 border border-slate-200 rounded-2xl flex items-center gap-3"><i class="fa-solid fa-circle-info fa-lg text-blue-400"></i> No se detectaron secciones generativas en este formato.</div>';
      return;
    }

    hydrateExpandedKeys(tree);

    if (!selectionHydrated) {
      normalizeSelectedSections(null, promptPackage).forEach((section) => {
        const key = selectionKey(section);
        if (key) selectedKeys.add(key);
      });
      selectionHydrated = true;
    }

    const indexRef = { value: 1 };
    tree.forEach((node) => {
      renderNode({
        node,
        tree,
        depth: 0,
        indexRef,
        promptPackage,
        container: grid,
        nextButton,
      });
    });

    if (nextButton) nextButton.disabled = selectedKeys.size === 0;
  }

  return {
    async loadForFormat(format, project) {
      const grid = getGrid?.();
      const formatLabel = getFormatLabel?.();
      if (grid) {
        grid.innerHTML = '<div class="col-span-full text-center p-5"><div class="loader mx-auto mb-3"></div><p class="text-slate-500 text-sm">Cargando paquete institucional y secciones del formato...</p></div>';
      }
      if (!format) {
        store.setPromptPackage(null);
        store.setSelectedSections([]);
        selectedKeys = new Set();
        expandedKeys = new Set();
        expansionHydrated = false;
        selectionHydrated = false;
        render(null);
        return null;
      }

      if (formatLabel) {
        formatLabel.textContent = format.title || format.name || format.id || "-";
      }

      const promptPackage = mergeProjectSnapshot(await fetchPromptPackage(format.id), project);
      store.setPromptPackage(promptPackage);
      onPromptPackageResolved?.(promptPackage);

      const initialSource = Array.isArray(project?.selected_sections)
        ? project.selected_sections
        : (Array.isArray(promptPackage?.selected_sections) && promptPackage.selected_sections.length
            ? promptPackage.selected_sections
            : null);
      const initialSelection = normalizeSelectedSections(initialSource, promptPackage);
      
      // FORZAR SELECCIÓN ÚNICA para Maestría y Proyecto UNAC SOLO si no hay NADA guardado previamente
      const formatId = String(promptPackage?.format_id || promptPackage?._meta?.id || "").toLowerCase();
      const metaUniversity = String(promptPackage?._meta?.university || "").toLowerCase();
      const metaCategory = String(promptPackage?._meta?.category || "").toLowerCase();
      const hasPreviousSelection = Array.isArray(project?.selected_sections) && project.selected_sections.length > 0;
        const isMaestriaOrProyecto = (
          formatId.includes("maestria") ||
          formatId.includes("unac-proyecto") ||
          (metaUniversity === "unac" && metaCategory.includes("proyecto"))
        );

      if (isMaestriaOrProyecto && !hasPreviousSelection) {
         // Si es maestría/proyecto UNAC y REALMENTE no hay nada previo en el proyecto, ponemos el default
         selectedKeys = new Set(["titulo-info-basica"]);
      } else {
         selectedKeys = new Set(initialSelection.map(selectionKey));
      }

      expandedKeys = new Set();
      expansionHydrated = false;
      selectionHydrated = true;
      commitSelection(promptPackage);
      render(promptPackage);
      return promptPackage;
    },
    render,
    selectAll() {
      const promptPackage = store.getState().promptPackage;
      const tree = buildSectionTree(promptPackage);
      const allConcreteKeys = new Set();
      tree.forEach((node) => {
        collectConcreteSelectionKeys(node, []).forEach((key) => allConcreteKeys.add(key));
      });
      const areAllSelected = allConcreteKeys.size > 0
        && Array.from(allConcreteKeys).every((key) => selectedKeys.has(key));
      selectedKeys = areAllSelected ? new Set() : allConcreteKeys;
      selectionHydrated = true;
      commitSelection(promptPackage);
      render(promptPackage);
    },
    mount() {
      bindCustomStructureEvents();
      render();
    },
    unmount() {},
    validate() {
      return store.getState().selectedSections.length > 0;
    },
    serialize() {
      return store.getState().selectedSections;
    },
  };
}
