import { createAdminEditorState, findEditableSection } from "./admin-editor.js";
import { getPromptAdminState, patchPromptAdminState } from "./state.js";
import { fetchPromptPackage, selectionKey } from "../wizard/prompt-package-client.js";
import {
  buildSectionTree,
  countRequiredVariables,
  hasOwnBlocks,
  isGroupingOnlySection,
  parentScopeLabel,
} from "../wizard/section-selection.js";
import { escapeHtml } from "../../shared/dom.js";

function safeText(value, fallback = "") {
  const text = String(value || "").trim();
  return text || fallback;
}

function sectionMetrics(section) {
  const ownBlocks = Array.isArray(section?.blocks) ? section.blocks.length : 0;
  const childCount = Array.isArray(section?.children) ? section.children.length : 0;
  if (childCount > 0) {
    return `${ownBlocks} bloque(s) propios · ${childCount} hija(s)`;
  }
  return `${ownBlocks} bloque(s) · ${countRequiredVariables(section)} variable(s) requerida(s)`;
}

export function createPromptSectionTree({
  getContainer,
  getTitle,
  getSubtitle,
  onOpenSection,
}) {
  let expandedKeys = new Set();
  let expansionHydrated = false;

  function editorState() {
    return getPromptAdminState().editorState || {};
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

  function renderNode(container, section, depth, counter) {
    const scope = safeText(parentScopeLabel(section), section.section_path || section.section_title || `Seccion ${counter.value}`);
    const title = safeText(section.section_title, section.section_path || `Seccion ${counter.value}`);
    const nodeKey = selectionKey(section);
    const children = Array.isArray(section?.children) ? section.children : [];
    const canExpand = children.length > 0;
    const isExpanded = canExpand && expandedKeys.has(nodeKey);
    const card = document.createElement("button");
    card.type = "button";
    card.className = "w-full bg-white border border-slate-200 rounded-[2rem] p-5 text-left hover:border-blue-400 hover:shadow-md transition-all group";
    card.style.marginLeft = `${Math.max(0, depth) * 20}px`;
    card.innerHTML = `
      <div class="flex items-start justify-between gap-4">
        <div class="flex items-start gap-4 min-w-0">
          <div class="w-12 h-12 rounded-xl bg-slate-50 text-slate-400 flex items-center justify-center font-black text-lg group-hover:bg-blue-50 group-hover:text-blue-600 transition-colors shrink-0">
            ${counter.value}
          </div>
          <div class="min-w-0">
            <div class="flex items-center gap-2 flex-wrap">
              ${canExpand ? `
                <span class="js-tree-toggle inline-flex h-6 w-6 items-center justify-center rounded-full border border-slate-200 bg-white text-xs font-black text-slate-500 transition-colors group-hover:border-blue-300 group-hover:text-blue-600" aria-hidden="true">
                  ${isExpanded ? "-" : "+"}
                </span>
              ` : ""}
              <span class="text-[10px] font-black text-blue-500 uppercase tracking-widest">${escapeHtml(scope)}</span>
              ${section.optional ? '<span class="px-2 py-0.5 rounded-full border border-amber-200 bg-amber-50 text-[10px] font-black uppercase text-amber-700">Opcional</span>' : ""}
              ${isGroupingOnlySection(section) ? '<span class="px-2 py-0.5 rounded-full border border-slate-200 bg-slate-100 text-[10px] font-black uppercase text-slate-500">Agrupador</span>' : ""}
            </div>
            <div class="mt-1 text-sm font-bold text-slate-800">${escapeHtml(title)}</div>
            <div class="mt-2 text-xs text-slate-500">${escapeHtml(sectionMetrics(section))}</div>
          </div>
        </div>
        <div class="flex items-start gap-3 text-slate-300 group-hover:text-blue-500 transition-colors shrink-0">
          ${!hasOwnBlocks(section) && Array.isArray(section.children) && section.children.length ? '<i class="fa-solid fa-sitemap mt-1"></i>' : ""}
          <i class="fa-solid fa-chevron-right mt-1"></i>
        </div>
      </div>
    `;
    card.addEventListener("click", (event) => {
      const toggleHit = event.target instanceof HTMLElement && event.target.closest(".js-tree-toggle");
      if (toggleHit) {
        event.preventDefault();
        if (isExpanded) {
          expandedKeys.delete(nodeKey);
        } else {
          expandedKeys.add(nodeKey);
        }
        render();
        return;
      }
      onOpenSection?.(selectionKey(section));
    });
    container.appendChild(card);
    counter.value += 1;

    if (isExpanded) {
      children.forEach((child) => {
        renderNode(container, child, depth + 1, counter);
      });
    }
  }

  function render() {
    const container = getContainer?.();
    if (!container) return;

    const tree = buildSectionTree(editorState());
    hydrateExpandedKeys(tree);
    if (!tree.length) {
      container.innerHTML = '<div class="rounded-[2rem] border border-slate-200 bg-white px-5 py-8 text-center text-sm text-slate-500">No se detectaron secciones editables en este formato.</div>';
      window.renderPromptPackageContext?.();
      window.renderPromptPackageCustomization?.();
      return;
    }

    container.innerHTML = "";
    const counter = { value: 1 };
    tree.forEach((section) => renderNode(container, section, 0, counter));
    window.renderPromptPackageContext?.();
    window.renderPromptPackageCustomization?.();
  }

  async function openIndex(buttonOrFormatId) {
    const rawFormatId = typeof buttonOrFormatId === "string"
      ? buttonOrFormatId
      : String(buttonOrFormatId?.dataset?.formatId || "");
    if (!rawFormatId) {
      throw new Error("No se encontro format_id para este paquete.");
    }

    const button = typeof buttonOrFormatId === "string" ? null : buttonOrFormatId;
    const meta = button
      ? {
          logo: button.dataset.logo || "",
          title: button.dataset.title || "Paquete institucional",
          subtitle: button.dataset.subtitle || "",
          university: button.dataset.univ || "",
          docType: button.dataset.tipo || "",
          variant: button.dataset.subtipo || "",
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
      container.innerHTML = '<div class="rounded-[2rem] border border-slate-200 bg-white px-5 py-8 text-center text-sm text-slate-500">Cargando estructura institucional...</div>';
    }

    const promptPackage = await fetchPromptPackage(rawFormatId);
    patchPromptAdminState({
      promptPackage,
      editorState: createAdminEditorState(promptPackage),
      activeSectionKey: "",
    });
    expandedKeys = new Set();
    expansionHydrated = false;

    if (getTitle?.()) {
      getTitle().textContent = editorState()?.name || `${meta.university || ""} ${meta.title || "Paquete institucional"}`.trim();
    }
    if (getSubtitle?.()) {
      getSubtitle().textContent = editorState()?.format_name
        ? `${editorState().format_name} - ${editorState().doc_type || "Documento institucional"}`
        : (meta.subtitle || "Secciones institucionales");
    }

    render();
    return promptPackage;
  }

  return {
    render,
    openIndex,
    findSection(key) {
      return findEditableSection(editorState(), key);
    },
  };
}
