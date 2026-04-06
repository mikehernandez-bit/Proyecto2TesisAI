import { requestJson } from "../../shared/api-client.js";
import { getPromptAdminState, patchPromptAdminState } from "./state.js";
import { selectionKey } from "../wizard/prompt-package-client.js";
import { findEditableSection } from "./admin-editor.js";
import { escapeHtml } from "../../shared/dom.js";

function currentEditableSection() {
  return findEditableSection(getPromptAdminState().editorState, getPromptAdminState().activeSectionKey);
}

function normalizeBlock(section, block, index) {
  const sectionKey = selectionKey(section) || `section_${index + 1}`;
  return {
    block_id: String(block?.block_id || `${sectionKey}_block_${index + 1}`),
    label: String(block?.label || `Prompt ${index + 1}`),
    instructions: String(block?.instructions || ""),
    required_variables: Array.isArray(block?.required_variables)
      ? block.required_variables.map((value) => String(value || "").trim()).filter(Boolean)
      : [],
    required: Boolean(block?.required ?? true),
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

function renderVariableTags(block) {
  const variables = Array.isArray(block.required_variables) ? block.required_variables : [];
  if (!variables.length) {
    return '<span class="px-3 py-2 bg-slate-100 text-slate-500 rounded-xl text-[10px] font-bold border border-slate-200">Sin variables</span>';
  }
  return variables.map((value) => `
    <span class="var-tag inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-[10px] font-bold text-slate-700 shadow-sm" data-variable="${escapeHtml(value)}">
      <span>${escapeHtml(value)}</span>
      <button type="button" class="js-remove-var text-slate-300 hover:text-red-500" data-variable="${escapeHtml(value)}">
        <i class="fa-solid fa-circle-xmark"></i>
      </button>
    </span>
  `).join("");
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
      label: blockNode.querySelector(".prompt-block-label")?.value || `Prompt ${index + 1}`,
      instructions: blockNode.querySelector(".prompt-block-instructions")?.value || "",
      required_variables: variables,
      required: Boolean(blockNode.querySelector(".prompt-block-required")?.checked),
    }, index);
  });

  const templateField = document.getElementById("package-base-template");
  if (templateField && getPromptAdminState().editorState) {
    getPromptAdminState().editorState.template = String(templateField.value || "");
  }
}

function renderPromptBlocks(section) {
  const container = document.getElementById("prompts-container");
  if (!container || !section) return;

  const baseTemplate = document.getElementById("package-base-template");
  if (baseTemplate) {
    baseTemplate.value = String(getPromptAdminState().editorState?.template || "");
  }

  const blocks = ensureSectionBlocks(section);
  container.innerHTML = blocks.map((block, index) => `
    <div class="prompt-block bg-white rounded-[2.5rem] border border-slate-200 shadow-sm overflow-hidden mb-8 fade-in" data-block-index="${index}">
      <div class="p-6 flex flex-col gap-4 bg-slate-50 border-b border-slate-100">
        <div class="flex flex-wrap gap-4 items-center">
          <div class="px-5 py-2.5 bg-emerald-500 text-white rounded-2xl flex items-center gap-3 shadow-md shrink-0">
            <i class="fa-solid fa-bolt text-xs"></i>
            <span class="text-xs font-black uppercase tracking-widest">Prompt ${index + 1}</span>
          </div>
          <div class="flex-1 min-w-[220px] rounded-2xl border border-slate-200 bg-slate-100 px-4 py-2 text-sm font-bold text-slate-700">
            ${escapeHtml(section.section_path || section.section_title || "Sección institucional")}
          </div>
          <label class="inline-flex items-center gap-2 rounded-2xl border border-slate-200 bg-white px-4 py-2 text-xs font-bold text-slate-600">
            <input type="checkbox" class="prompt-block-required" ${block.required ? "checked" : ""}>
            Bloque obligatorio
          </label>
          ${index > 0 ? `
            <button type="button" class="js-remove-block w-11 h-11 flex items-center justify-center rounded-2xl bg-red-50 text-red-400 hover:bg-red-500 hover:text-white transition-all">
              <i class="fa-solid fa-trash-can"></i>
            </button>
          ` : ""}
        </div>
        <div class="rounded-2xl border border-slate-200 bg-white overflow-hidden">
          <div class="bg-slate-100 px-4 py-2 text-[10px] font-black uppercase tracking-widest text-slate-500 border-b border-slate-200">Etiqueta del bloque</div>
          <input type="text" class="prompt-block-label w-full bg-white px-4 py-3 text-sm font-bold text-slate-700 outline-none" value="${escapeHtml(block.label)}" placeholder="Ej: Realidad problemática">
        </div>
      </div>

      <div class="p-8 space-y-6">
        <div class="space-y-3">
          <label class="text-[11px] font-black text-slate-400 uppercase tracking-[0.2em] ml-2">Instrucciones para la IA</label>
          <textarea class="prompt-block-instructions w-full h-[220px] p-7 bg-slate-900 text-blue-50 border-2 border-slate-800 rounded-[2rem] text-sm font-mono leading-relaxed focus:border-blue-500 outline-none shadow-2xl resize-none"
            placeholder="Describe cómo debe actuar la IA en esta sección...">${escapeHtml(block.instructions)}</textarea>
        </div>

        <div class="bg-slate-50/80 p-6 rounded-[2rem] border border-slate-100">
          <div class="flex items-center gap-2 mb-4">
            <i class="fa-solid fa-tags text-blue-500 text-sm"></i>
            <label class="text-[11px] font-black text-slate-600 uppercase tracking-widest">Variables requeridas</label>
          </div>
          <div class="local-vars-tags flex flex-wrap gap-2 mb-4">${renderVariableTags(block)}</div>
          <div class="flex gap-2">
            <input type="text" placeholder="Añadir variable específica (ej: población, muestra...)" class="local-var-input flex-1 px-5 py-3 bg-white border border-slate-200 rounded-2xl text-sm outline-none focus:border-blue-400 transition-all shadow-sm">
            <button type="button" class="js-add-var px-5 bg-slate-900 text-white rounded-2xl hover:bg-blue-600 transition-all shadow-lg">
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
    alert("No se pudo resolver la sección seleccionada.");
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

  document.getElementById("manual-title-display").textContent = state.editorState?.name || "Paquete institucional";
  document.getElementById("manual-subtitle-display").textContent = section.section_path || section.section_title || "Sección institucional";
  const promptIdField = document.getElementById("manual-prompt-name");
  if (promptIdField) {
    promptIdField.value = String(state.editorState?.id || "");
    promptIdField.readOnly = true;
    promptIdField.classList.add("bg-slate-800", "text-slate-400", "cursor-not-allowed");
  }

  renderPromptBlocks(section);
  document.getElementById("modal-manual-config")?.classList.remove("hidden");
}

function closeManualModal() {
  document.getElementById("modal-manual-config")?.classList.add("hidden");
}

async function savePackage() {
  const state = getPromptAdminState();
  const section = currentEditableSection();
  if (!state.editorState || !section) {
    alert("No hay una sección activa para guardar.");
    return;
  }

  collectSectionFromDom(section);
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
    editorState: {
      ...saved,
      sections: Array.isArray(saved.sections) ? saved.sections.map((item) => ({ ...item })) : [],
    },
  });

  window.renderPromptSectionIndex?.();
  closeManualModal();
  alert("Paquete institucional guardado correctamente.");
}

export function bootPromptPackageEditor() {
  window.openManualModal = openManualModal;
  window.closeManualModal = closeManualModal;
  window.addPromptBlock = addPromptBlock;
  window.addVariableToBlock = addVariableToBlock;
  window.savePackage = savePackage;
}
