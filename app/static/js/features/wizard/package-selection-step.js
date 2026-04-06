import { fetchPromptPackage, normalizeSelectedSections, selectionKey } from "./prompt-package-client.js";
import { flattenSections, selectedSectionMap } from "./section-selection.js";
import { escapeHtml } from "../../shared/dom.js";

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
    sections: Array.isArray(project.prompt_snapshot.sections) && project.prompt_snapshot.sections.length
      ? project.prompt_snapshot.sections
      : promptPackage.sections,
    selected_sections: Array.isArray(project.selected_sections) && project.selected_sections.length
      ? project.selected_sections
      : promptPackage.selected_sections,
    section_tree: promptPackage.section_tree,
  };
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

  function syncSelection(promptPackage, selectedSections) {
    const normalized = normalizeSelectedSections(selectedSections, promptPackage);
    selectedKeys = new Set(normalized.map(selectionKey));
    store.setSelectedSections(normalized);
    onSelectionChanged?.(normalized, selectedKeys);
    return normalized;
  }

  function render(promptPackage = store.getState().promptPackage) {
    const grid = getGrid?.();
    const nextButton = getNextButton?.();
    if (!grid) return;

    const items = selectedSectionMap(promptPackage, store.getState().selectedSections);
    grid.innerHTML = "";

    if (!items.length) {
      if (nextButton) nextButton.disabled = true;
      grid.innerHTML = '<div class="col-span-full text-sm text-slate-500 p-5 bg-slate-50 border border-slate-200 rounded-2xl flex items-center gap-3"><i class="fa-solid fa-circle-info fa-lg text-blue-400"></i> No se detectaron secciones generativas en este formato.</div>';
      return;
    }

    if (!selectedKeys.size) {
      selectedKeys = new Set(items.filter((item) => item.selected).map((item) => item.key));
    }

    items.forEach((section, index) => {
      const key = section.key || selectionKey(section) || String(index + 1);
      const isSelected = selectedKeys.has(key);
      const card = document.createElement("div");
      card.className = "chapter-card group p-4 bg-white rounded-2xl border-2 border-slate-100 shadow-sm cursor-pointer transition-all hover:border-blue-400 hover:bg-blue-50/50";
      card.dataset.chapterId = key;
      if (isSelected) {
        card.classList.add("border-blue-400", "bg-blue-50/50");
      }
      card.innerHTML = `
        <div class="flex items-center justify-between w-full">
          <div class="flex items-center gap-4">
            <div class="w-10 h-10 rounded-xl border border-slate-200 bg-slate-50 flex items-center justify-center shrink-0 transition-colors group-hover:bg-white group-hover:border-blue-200">
              <span class="text-sm font-black text-slate-400 group-hover:text-blue-500">${index + 1}</span>
            </div>
            <div class="text-left">
              <div class="flex items-center gap-2 flex-wrap">
                <div class="text-[9px] font-black text-blue-500 uppercase tracking-widest">${escapeHtml(section.section_path || section.section_title || `Sección ${index + 1}`)}</div>
                ${section.optional ? '<span class="text-[9px] font-black uppercase tracking-widest text-amber-600 bg-amber-50 border border-amber-200 rounded-full px-2 py-0.5">Opcional</span>' : ""}
              </div>
              <div class="font-bold text-slate-800 leading-tight text-sm mt-0.5">${escapeHtml(section.section_title || section.section_path || `Sección ${index + 1}`)}</div>
              <div class="text-[11px] text-slate-400 mt-1">Nivel ${Math.max(1, Number(section.section_level || 1))} · ${Array.isArray(section.blocks) ? section.blocks.length : 0} bloque(s) de prompt</div>
            </div>
          </div>
          <div class="check-icon ${isSelected ? "" : "hidden"} text-blue-500"><i class="fa-solid fa-circle-check fa-lg"></i></div>
        </div>
      `;
      card.addEventListener("click", () => {
        if (selectedKeys.has(key)) {
          selectedKeys.delete(key);
          card.classList.remove("border-blue-400", "bg-blue-50/50");
          card.querySelector(".check-icon")?.classList.add("hidden");
        } else {
          selectedKeys.add(key);
          card.classList.add("border-blue-400", "bg-blue-50/50");
          card.querySelector(".check-icon")?.classList.remove("hidden");
        }
        const sections = flattenSections(promptPackage).filter((item) => selectedKeys.has(selectionKey(item)));
        syncSelection(promptPackage, sections);
        if (nextButton) nextButton.disabled = selectedKeys.size === 0;
      });
      grid.appendChild(card);
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
        render(null);
        return null;
      }

      if (formatLabel) {
        formatLabel.textContent = format.title || format.name || format.id || "-";
      }

      const promptPackage = mergeProjectSnapshot(await fetchPromptPackage(format.id), project);
      store.setPromptPackage(promptPackage);
      onPromptPackageResolved?.(promptPackage);
      const initialSelection = normalizeSelectedSections(
        project?.selected_sections || promptPackage.selected_sections || [],
        promptPackage,
      );
      syncSelection(promptPackage, initialSelection);
      render(promptPackage);
      return promptPackage;
    },
    render,
    selectAll() {
      const promptPackage = store.getState().promptPackage;
      const sections = flattenSections(promptPackage);
      syncSelection(promptPackage, sections);
      selectedKeys = new Set(sections.map(selectionKey));
      render(promptPackage);
    },
    mount() {
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
