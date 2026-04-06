import { createAdminEditorState, findEditableSection } from "./admin-editor.js";
import { getPromptAdminState, patchPromptAdminState } from "./state.js";
import { fetchPromptPackage, selectionKey } from "../wizard/prompt-package-client.js";
import { escapeHtml } from "../../shared/dom.js";

export function createPromptSectionTree({
  getContainer,
  getTitle,
  getSubtitle,
  onOpenSection,
}) {
  function sections() {
    return Array.isArray(getPromptAdminState().editorState?.sections)
      ? getPromptAdminState().editorState.sections
      : [];
  }

  function render() {
    const container = getContainer?.();
    if (!container) return;

    const items = sections();
    if (!items.length) {
      container.innerHTML = '<div class="rounded-2xl border border-slate-200 bg-white px-5 py-8 text-center text-sm text-slate-500">No se detectaron secciones editables en este formato.</div>';
      return;
    }

    container.innerHTML = "";
    items.forEach((section, index) => {
      const requiredVariables = Array.from(new Set(
        (Array.isArray(section.blocks) ? section.blocks : [])
          .flatMap((block) => Array.isArray(block.required_variables) ? block.required_variables : [])
          .map((value) => String(value || "").trim())
          .filter(Boolean),
      ));
      const card = document.createElement("button");
      card.type = "button";
      card.className = "w-full bg-white border border-slate-200 rounded-2xl p-5 text-left hover:border-blue-400 hover:shadow-md transition-all group";
      card.innerHTML = `
        <div class="flex items-start justify-between gap-4">
          <div class="flex items-start gap-4 min-w-0">
            <div class="w-12 h-12 rounded-xl bg-slate-50 text-slate-400 flex items-center justify-center font-black text-lg group-hover:bg-blue-50 group-hover:text-blue-600 transition-colors shrink-0">
              ${index + 1}
            </div>
            <div class="min-w-0">
              <div class="flex items-center gap-2 flex-wrap">
                <span class="text-[10px] font-black text-blue-500 uppercase tracking-widest">${escapeHtml(section.section_path || section.section_title || `Sección ${index + 1}`)}</span>
                ${section.optional ? '<span class="px-2 py-0.5 rounded-full border border-amber-200 bg-amber-50 text-[10px] font-black uppercase text-amber-700">Opcional</span>' : ""}
              </div>
              <div class="mt-1 text-sm font-bold text-slate-800">${escapeHtml(section.section_title || section.section_path || `Sección ${index + 1}`)}</div>
              <div class="mt-2 text-xs text-slate-500">${Array.isArray(section.blocks) ? section.blocks.length : 0} bloque(s) · ${requiredVariables.length} variable(s) requerida(s)</div>
            </div>
          </div>
          <div class="text-slate-300 group-hover:text-blue-500 transition-colors shrink-0">
            <i class="fa-solid fa-chevron-right"></i>
          </div>
        </div>
      `;
      card.addEventListener("click", () => onOpenSection?.(selectionKey(section)));
      container.appendChild(card);
    });
  }

  async function openIndex(buttonOrFormatId) {
    const rawFormatId = typeof buttonOrFormatId === "string"
      ? buttonOrFormatId
      : String(buttonOrFormatId?.dataset?.formatId || "");
    if (!rawFormatId) {
      throw new Error("No se encontró format_id para este paquete.");
    }

    const button = typeof buttonOrFormatId === "string" ? null : buttonOrFormatId;
    const meta = button
      ? {
          logo: button.dataset.logo || "",
          title: button.dataset.title || "Paquete institucional",
          subtitle: button.dataset.subtitle || "",
          university: button.dataset.univ || "",
        }
      : {};

    patchPromptAdminState({
      formatId: rawFormatId,
      meta,
    });

    if (getTitle?.()) {
      getTitle().textContent = `${meta.university || ""} ${meta.title || "Paquete institucional"}`.trim();
    }
    if (getSubtitle?.()) {
      getSubtitle().textContent = "Cargando secciones desde el formato institucional...";
    }
    const container = getContainer?.();
    if (container) {
      container.innerHTML = '<div class="rounded-2xl border border-slate-200 bg-white px-5 py-8 text-center text-sm text-slate-500">Cargando estructura institucional...</div>';
    }

    const promptPackage = await fetchPromptPackage(rawFormatId);
    patchPromptAdminState({
      promptPackage,
      editorState: createAdminEditorState(promptPackage),
      activeSectionKey: "",
    });

    if (getTitle?.()) {
      getTitle().textContent = getPromptAdminState().editorState?.name || `${meta.university || ""} ${meta.title || "Paquete institucional"}`.trim();
    }
    if (getSubtitle?.()) {
      getSubtitle().textContent = getPromptAdminState().editorState?.format_name
        ? `${getPromptAdminState().editorState.format_name} · ${getPromptAdminState().editorState.doc_type || "Documento institucional"}`
        : (meta.subtitle || "Secciones institucionales");
    }

    render();
    return promptPackage;
  }

  return {
    render,
    openIndex,
    findSection(key) {
      return findEditableSection(getPromptAdminState().editorState, key);
    },
  };
}
