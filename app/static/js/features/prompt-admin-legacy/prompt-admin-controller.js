export function createPromptAdminLegacyController({
  apiGet,
  apiSend,
  getElement,
  escapeHtml,
  wizardStateRef,
  setStep2NextEnabled,
  onPromptsChanged,
  confirmDelete = (message) => window.confirm(message),
}) {
  function getWizardState() {
    return wizardStateRef?.() || { module: "", enfoque: "", chapters: [] };
  }

  function safeElement(id) {
    return getElement(id);
  }

  function openPromptModal(promptObj = null) {
    const error = safeElement("modal-error");
    if (error) {
      error.classList.add("hidden");
      error.innerText = "";
    }

    const title = safeElement("modal-title");
    const promptId = safeElement("modal-prompt-id");
    const name = safeElement("modal-name");
    const docType = safeElement("modal-doc-type");
    const isActive = safeElement("modal-is-active");
    const template = safeElement("modal-template");
    const vars = safeElement("modal-vars");

    if (!title || !promptId || !name || !docType || !isActive || !template || !vars) {
      return;
    }

    if (!promptObj) {
      title.innerText = "Nuevo Prompt";
      promptId.value = "";
      name.value = "";
      docType.value = "Tesis Completa";
      isActive.checked = true;
      template.value = "";
      vars.value = '["tema","objetivo_general"]';
    } else {
      title.innerText = "Editar Prompt";
      promptId.value = promptObj.id;
      name.value = promptObj.name || "";
      docType.value = promptObj.doc_type || "Tesis Completa";
      isActive.checked = Boolean(promptObj.is_active);
      template.value = promptObj.template || "";
      vars.value = JSON.stringify(promptObj.variables || []);
    }

    safeElement("modal-prompt")?.classList.remove("hidden");
  }

  function closePromptModal() {
    safeElement("modal-prompt")?.classList.add("hidden");
  }

  async function savePrompt() {
    try {
      safeElement("modal-error")?.classList.add("hidden");
      const id = String(safeElement("modal-prompt-id")?.value || "").trim();
      const name = String(safeElement("modal-name")?.value || "").trim();
      const docType = safeElement("modal-doc-type")?.value || "Tesis Completa";
      const isActive = Boolean(safeElement("modal-is-active")?.checked);
      const template = safeElement("modal-template")?.value || "";

      let variables;
      try {
        variables = JSON.parse(safeElement("modal-vars")?.value || "[]");
        if (!Array.isArray(variables)) throw new Error("invalid");
      } catch (_) {
        throw new Error('Variables debe ser un JSON Array valido. Ej: ["tema","objetivo_general"]');
      }

      if (!name) throw new Error("Nombre requerido");

      const body = { name, doc_type: docType, is_active: isActive, template, variables };
      if (!id) await apiSend("/api/prompts", "POST", body);
      else await apiSend(`/api/prompts/${encodeURIComponent(id)}`, "PUT", body);

      closePromptModal();
      await refreshPromptsAdmin();
      await onPromptsChanged?.();
    } catch (error) {
      const element = safeElement("modal-error");
      if (element) {
        element.classList.remove("hidden");
        element.innerText = error?.message || String(error);
      }
    }
  }

  async function deletePrompt(id) {
    if (!confirmDelete("Eliminar este prompt?")) return;
    await apiSend(`/api/prompts/${encodeURIComponent(id)}`, "DELETE");
    await refreshPromptsAdmin();
    await onPromptsChanged?.();
  }

  function renderModules(availablePrompts) {
    const grid = safeElement("prompts-grid");
    if (!grid) return;
    grid.innerHTML = "";

    const modules = [...new Set((Array.isArray(availablePrompts) ? availablePrompts : []).map((item) => item.metodologia).filter(Boolean))];
    modules.forEach((moduleCode) => {
      const card = document.createElement("div");
      card.className = "p-4 border-2 border-slate-100 rounded-2xl cursor-pointer hover:border-blue-500 hover:bg-blue-50 transition-all font-bold text-slate-700 text-center uppercase text-sm";
      card.textContent = moduleCode === "INF"
        ? "Informe de Tesis"
        : moduleCode === "PROY"
          ? "Proyecto de Tesis"
          : "Tesis de Maestria";
      card.onclick = () => {
        const wizardState = getWizardState();
        wizardState.module = moduleCode;
        renderEnfoques(availablePrompts.filter((item) => item.metodologia === moduleCode));
      };
      grid.appendChild(card);
    });
  }

  function renderEnfoques(filteredPrompts) {
    const grid = safeElement("prompts-grid");
    if (!grid) return;
    grid.innerHTML = `
      <div class="col-span-full mb-4">
        <button onclick="TesisAI.loadPromptsForWizard()" class="text-xs text-blue-600 font-bold underline">
          <i class="fa-solid fa-arrow-left"></i> Cambiar tipo
        </button>
        <h4 class="text-sm font-black text-slate-800 mt-2 uppercase">Selecciona el Enfoque:</h4>
      </div>
    `;

    const enfoques = [...new Set((Array.isArray(filteredPrompts) ? filteredPrompts : []).map((item) => item.categoria).filter(Boolean))];
    enfoques.forEach((enfoque) => {
      const card = document.createElement("div");
      card.className = "p-4 border-2 border-slate-100 rounded-2xl cursor-pointer hover:border-blue-500 transition-all font-black text-xs text-slate-500 text-center uppercase";
      card.textContent = enfoque;
      card.onclick = () => {
        const wizardState = getWizardState();
        wizardState.enfoque = enfoque;
        renderChapters(filteredPrompts.filter((item) => item.categoria === enfoque));
      };
      grid.appendChild(card);
    });
  }

  function renderChapters(finalPrompts) {
    const grid = safeElement("prompts-grid");
    if (!grid) return;
    const wizardState = getWizardState();
    wizardState.chapters = [];
    setStep2NextEnabled(false);
    grid.innerHTML = `
      <div class="col-span-full mb-4">
        <button onclick="TesisAI.loadPromptsForWizard()" class="text-xs text-blue-600 font-bold underline">
          <i class="fa-solid fa-arrow-left"></i> Reiniciar seleccion
        </button>
        <h4 class="text-sm font-black text-slate-800 mt-2 uppercase">Selecciona los Capitulos a generar:</h4>
      </div>
    `;

    (Array.isArray(finalPrompts) ? finalPrompts : []).forEach((pack) => {
      (Array.isArray(pack.prompts) ? pack.prompts : []).forEach((block) => {
        const card = document.createElement("div");
        card.className = "chapter-option flex items-center justify-between p-4 bg-white border-2 border-slate-100 rounded-2xl cursor-pointer hover:border-emerald-400 transition-all group";
        card.innerHTML = `
          <div class="flex items-center gap-3">
            <div class="w-8 h-8 rounded-lg bg-slate-50 border flex items-center justify-center text-[10px] font-black text-slate-400 group-hover:text-emerald-600 transition-colors">
              ${escapeHtml(block.numero_prompt || "-")}
            </div>
            <div>
              <div class="text-[9px] font-black text-blue-500 uppercase">${escapeHtml(block.capitulo_nombre || "Capitulo")}</div>
              <div class="text-xs font-bold text-slate-700">${escapeHtml(block.titulo_cabecera || "Sin titulo")}</div>
            </div>
          </div>
          <div class="check-icon hidden text-emerald-500"><i class="fa-solid fa-circle-check"></i></div>
        `;
        card.onclick = () => {
          const isSelected = card.classList.toggle("border-emerald-500");
          card.querySelector(".check-icon")?.classList.toggle("hidden");
          if (isSelected) wizardState.chapters.push(block);
          else wizardState.chapters = wizardState.chapters.filter((item) => item !== block);
          setStep2NextEnabled(wizardState.chapters.length > 0);
        };
        grid.appendChild(card);
      });
    });
  }

  async function refreshPromptsAdmin() {
    const items = await apiGet("/api/prompts");
    const tbody = safeElement("prompts-table");
    const emptyState = safeElement("prompts-empty");
    if (!tbody || !emptyState) return items;

    tbody.innerHTML = "";
    if (!items.length) {
      emptyState.classList.remove("hidden");
      return items;
    }
    emptyState.classList.add("hidden");

    items.forEach((prompt) => {
      const vars = (prompt.variables || [])
        .slice(0, 6)
        .map((value) => `<span class="bg-blue-50 text-blue-600 px-2 py-1 rounded text-xs border border-blue-100 mx-1">${escapeHtml(value)}</span>`)
        .join("");
      const status = prompt.is_active
        ? '<span class="text-green-600 text-xs font-bold">Activo</span>'
        : '<span class="text-gray-400 text-xs font-bold">Inactivo</span>';

      const row = document.createElement("tr");
      row.className = "hover:bg-gray-50 transition";
      row.innerHTML = `
        <td class="px-6 py-4 font-medium">${escapeHtml(prompt.name)}</td>
        <td class="px-6 py-4">${vars || '<span class="text-xs text-gray-400">Sin variables</span>'}</td>
        <td class="px-6 py-4">${status}</td>
        <td class="px-6 py-4 text-right text-gray-400">
          <button class="mr-3 hover:text-blue-600" aria-label="Editar"><i class="fa-solid fa-pen"></i></button>
          <button class="hover:text-red-600" aria-label="Eliminar"><i class="fa-solid fa-trash"></i></button>
        </td>
      `;

      row.querySelector(".fa-pen")?.parentElement?.addEventListener("click", () => openPromptModal(prompt));
      row.querySelector(".fa-trash")?.parentElement?.addEventListener("click", () => deletePrompt(prompt.id));
      tbody.appendChild(row);
    });
    return items;
  }

  return {
    openPromptModal,
    closePromptModal,
    savePrompt,
    deletePrompt,
    renderModules,
    renderEnfoques,
    renderChapters,
    refreshPromptsAdmin,
  };
}
