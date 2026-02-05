/**
 * TesisAI Gen - Frontend JS (SPA)
 *
 * TODO (DEV): Conectar servicios reales:
 *   - Formatos: /api/formats -> app/core/services/format_api.py
 *   - n8n: /api/projects/generate -> app/core/services/n8n_client.py + callback /api/n8n/callback/{project_id}
 */

const TesisAI = (() => {
  let currentView = "dashboard";
  let currentStep = 1;

  let selectedFormat = null;
  let selectedPrompt = null;

  let currentProject = null;
  let pollTimer = null;

  const $ = (id) => document.getElementById(id);

  function escapeHtml(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
    }[c]));
  }

  async function apiGet(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  }

  async function apiSend(url, method, body) {
    const r = await fetch(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  }

  function showView(viewId) {
    document.querySelectorAll(".view-section").forEach((el) => el.classList.add("hidden"));
    const selected = $("view-" + viewId);
    if (selected) selected.classList.remove("hidden");

    document.querySelectorAll(".nav-item").forEach((el) => {
      el.classList.remove("bg-slate-800", "text-blue-400");
      el.classList.add("text-slate-300");
    });

    const activeNav = $("nav-" + viewId);
    if (activeNav) {
      activeNav.classList.remove("text-slate-300");
      activeNav.classList.add("bg-slate-800", "text-blue-400");
    }

    currentView = viewId;

    if (viewId === "dashboard") refreshDashboard();
    if (viewId === "wizard") initWizard();
    if (viewId === "admin-prompts") refreshPromptsAdmin();
    if (viewId === "history") refreshHistory();
  }

  function statusBadge(status) {
    if (status === "completed") return '<span class="bg-green-100 text-green-700 px-2 py-1 rounded text-xs font-semibold">Completado</span>';
    if (status === "processing") return '<span class="bg-yellow-100 text-yellow-700 px-2 py-1 rounded text-xs font-semibold">Procesando</span>';
    if (status === "failed") return '<span class="bg-red-100 text-red-700 px-2 py-1 rounded text-xs font-semibold">Falló</span>';
    return '<span class="bg-gray-100 text-gray-600 px-2 py-1 rounded text-xs font-semibold">N/A</span>';
  }

  async function refreshDashboard() {
    const items = await apiGet("/api/projects");
    $("stat-total-projects").innerText = String(items.length);

    const tbody = $("dashboard-recent-projects");
    tbody.innerHTML = "";

    if (!items.length) {
      $("dashboard-empty").classList.remove("hidden");
      return;
    }
    $("dashboard-empty").classList.add("hidden");

    items.slice(0, 5).forEach((p) => {
      const canDownload = p.status === "completed" && p.output_file;
      const downloadBtn = canDownload
        ? `<a class="text-blue-600 hover:text-blue-800" href="/api/download/${encodeURIComponent(p.id)}" title="Descargar"><i class="fa-solid fa-download"></i></a>`
        : `<span class="text-gray-300" title="No disponible"><i class="fa-solid fa-download"></i></span>`;

      const row = document.createElement("tr");
      row.className = "hover:bg-gray-50";
      row.innerHTML = `
        <td class="px-6 py-4">
          <div class="font-medium text-slate-800">${escapeHtml(p.title)}</div>
          <div class="text-xs text-gray-400">${escapeHtml(p.prompt_name || "")}</div>
        </td>
        <td class="px-6 py-4 text-gray-600">${escapeHtml(p.format_name || p.format_id || "")}</td>
        <td class="px-6 py-4">${statusBadge(p.status)}</td>
        <td class="px-6 py-4 text-gray-500">${escapeHtml(p.created_at || "")}</td>
        <td class="px-6 py-4 text-right">${downloadBtn}</td>
      `;
      tbody.appendChild(row);
    });
  }

  function resetStepper() {
    currentStep = 1;
    $("current-step-label").innerText = "1";

    for (let i = 1; i <= 4; i++) {
      const dot = $(`step-${i}-dot`);
      if (!dot) continue;
      dot.className = "w-8 h-8 rounded-full bg-gray-200 text-gray-500 flex items-center justify-center font-bold text-sm z-10";
      dot.innerHTML = i === 4 ? '<i class="fa-solid fa-check"></i>' : String(i);
      if (i === 1) {
        dot.classList.remove("bg-gray-200", "text-gray-500");
        dot.classList.add("bg-blue-600", "text-white");
      }
    }
    for (let i = 1; i <= 3; i++) {
      const line = $(`step-${i}-line`);
      if (!line) continue;
      line.className = "flex-1 h-1 bg-gray-200 mx-2 rounded";
    }

    for (let i = 1; i <= 4; i++) {
      const c = $(`step-${i}-content`);
      if (c) c.classList.add("hidden");
    }
    $("step-1-content").classList.remove("hidden");

    selectedFormat = null;
    selectedPrompt = null;
    currentProject = null;
    $("btn-step1-next").disabled = true;
    $("btn-step2-next").disabled = true;

    $("loading-state").classList.remove("hidden");
    $("success-state").classList.add("hidden");
  }

  async function initWizard() {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
    resetStepper();
    await loadFormats();
    await loadPromptsForWizard();
  }

  function nextStep(step) {
    $(`step-${currentStep}-content`).classList.add("hidden");

    const prevDot = $(`step-${currentStep}-dot`);
    if (prevDot) {
      prevDot.classList.remove("bg-blue-600");
      prevDot.classList.add("bg-green-500", "text-white");
      prevDot.innerHTML = '<i class="fa-solid fa-check"></i>';
    }
    const prevLine = $(`step-${currentStep}-line`);
    if (prevLine) {
      prevLine.classList.remove("bg-gray-200");
      prevLine.classList.add("bg-green-500");
    }

    currentStep = step;

    const curDot = $(`step-${currentStep}-dot`);
    if (curDot) {
      curDot.classList.remove("bg-gray-200", "text-gray-500");
      curDot.classList.add("bg-blue-600", "text-white");
    }

    $(`step-${currentStep}-content`).classList.remove("hidden");
    $(`step-${currentStep}-content`).classList.add("fade-in");
    $("current-step-label").innerText = String(currentStep);
  }

  function prevStep(step) {
    $(`step-${currentStep}-content`).classList.add("hidden");
    currentStep = step;
    $(`step-${currentStep}-content`).classList.remove("hidden");
    $("current-step-label").innerText = String(currentStep);
  }

  async function loadFormats() {
    // New API returns {formats: [...], stale: boolean, cachedAt: string}
    const response = await apiGet("/api/formats");
    const items = response.formats || response; // Support both old and new format

    // Show stale warning if data is from cache while GicaTesis is down
    if (response.stale) {
      console.warn("⚠️ Using stale cache - GicaTesis may be unavailable");
    }

    // Category label mapping for better UX
    const categoryLabels = {
      "proyecto": "Proyecto de Tesis",
      "informe": "Informe de Tesis",
      "maestria": "Tesis de Postgrado",
      "posgrado": "Tesis de Postgrado",
      "general": "Documentos Generales"
    };

    // Extract unique universities
    const unis = Array.from(new Set(items.map(x => x.university))).filter(Boolean).sort();

    // Extract unique LABELS (merging categories that map to the same name)
    const uniqueLabels = Array.from(new Set(items.map(x => categoryLabels[x.category] || x.category)))
      .filter(l => l) // Filter out empty
      .sort();

    const uniSel = $("filter-university");
    const carSel = $("filter-career"); // Note: HTML still uses "career" id but we filter by category

    uniSel.innerHTML = '<option value="">Todas las Universidades</option>' + unis.map(u => `<option value="${escapeHtml(u)}">${escapeHtml(u.toUpperCase())}</option>`).join("");
    // Use the labels as values for the dropdown
    carSel.innerHTML = '<option value="">Tipo de Documento</option>' + uniqueLabels.map(l => `<option value="${escapeHtml(l)}">${escapeHtml(l)}</option>`).join("");

    async function render() {
      const u = uniSel.value || "";
      const selectedLabel = carSel.value || "";

      const filtered = items.filter(x => {
        // HIDE GENERAL CONFIGS (like References Config)
        if (x.category === "general") return false;

        const matchesUni = !u || x.university === u;
        // Map the item's category to its label for comparison
        const itemLabel = categoryLabels[x.category] || x.category;
        const matchesCategory = !selectedLabel || itemLabel === selectedLabel;
        return matchesUni && matchesCategory;
      });

      const grid = $("formats-grid");
      grid.innerHTML = "";

      if (!filtered.length) {
        grid.innerHTML = '<div class="text-sm text-gray-500">No hay formatos para esos filtros.</div>';
        return;
      }

      filtered.forEach((f) => {
        const card = document.createElement("div");
        card.className = "format-card border-2 border-gray-100 hover:border-blue-400 p-4 rounded-lg cursor-pointer transition group relative bg-white";
        card.onclick = () => selectFormat(f, card);

        const docType = f.documentType ? ` (${f.documentType})` : "";
        const uniCode = f.university?.toLowerCase() || "uni";

        // Try to verify if we have a logo URL logic (future BFF proxy: /api/assets/logos/unac.png)
        // For now we render a nice fallback if image fails, or just use the text logic if no proxy
        // But since user asked for LOGO, let's setup the structure.

        // MVP: Use text for now but cleaner, UNLESS we assume GicaTesis has logos at specific paths
        // Let's stick to the request: "CAMBIAMOS EL LOGO POR EL DE LA UNIVERSIDAD"
        // I will use a generic map for now to public URLs if available, or just colors.
        // Actually, let's use the initials but style them like a logo.

        const logoUrl = `/api/assets/logos/${uniCode}.png`;
        // We will need to implement this proxy in router.py for it to work perfectly.

        card.innerHTML = `
          <div class="absolute top-3 right-3 opacity-0 group-hover:opacity-100 text-blue-500">
            <i class="fa-solid fa-circle-check fa-lg"></i>
          </div>
          <div class="flex items-center gap-4 mb-3">
            <div class="w-12 h-12 shrink-0 flex items-center justify-center p-1 border rounded bg-gray-50">
               <img src="${logoUrl}" alt="${uniCode}" class="w-full h-full object-contain" onerror="this.onerror=null;this.parentNode.innerHTML='<span class=\'text-blue-700 font-bold\'>${escapeHtml(uniCode.toUpperCase())}</span>'">
            </div>
            <div>
              <div class="font-bold text-sm text-slate-800 leading-tight">${escapeHtml(f.title || f.name)}</div>
              <div class="text-xs text-gray-400 mt-1">v${escapeHtml(f.version?.substring(0, 8) || "")}</div>
            </div>
          </div>
          <div class="mt-2 text-xs text-slate-500 bg-slate-50 p-2 rounded flex items-center gap-2">
            <i class="fa-solid fa-tag text-blue-400"></i> 
            <span>${escapeHtml(categoryLabels[f.category] || f.category)}${escapeHtml(docType)}</span>
          </div>
        `;
        grid.appendChild(card);
      });
    }

    uniSel.onchange = render;
    carSel.onchange = render;
    await render();
  }


  function selectFormat(formatObj, cardEl) {
    document.querySelectorAll(".format-card").forEach(c => c.classList.remove("border-blue-500", "bg-blue-50"));
    cardEl.classList.remove("border-gray-100");
    cardEl.classList.add("border-blue-500", "bg-blue-50");
    selectedFormat = formatObj;
    $("btn-step1-next").disabled = false;
  }

  async function loadPromptsForWizard() {
    const items = await apiGet("/api/prompts");
    const active = items.filter(p => p.is_active);

    const grid = $("prompts-grid");
    grid.innerHTML = "";

    if (!active.length) {
      grid.innerHTML = '<div class="text-sm text-gray-500">No hay prompts activos. Ve a “Gestión Prompts”.</div>';
      return;
    }

    active.forEach((p, idx) => {
      const card = document.createElement("div");
      card.className = "prompt-card border-2 border-gray-100 hover:border-blue-500 p-5 rounded-lg cursor-pointer transition bg-white text-center";
      card.onclick = () => selectPrompt(p, card);

      const badge = idx === 0 ? '<span class="bg-indigo-100 text-indigo-700 text-[10px] px-2 py-0.5 rounded-full font-bold">RECOMENDADO</span>' : '';
      card.innerHTML = `
        <div class="w-12 h-12 bg-indigo-50 text-indigo-600 rounded-full flex items-center justify-center mx-auto mb-3">
          <i class="fa-solid fa-book-open"></i>
        </div>
        <h4 class="font-bold text-slate-800">${escapeHtml(p.name)}</h4>
        <p class="text-xs text-gray-500 mt-1 mb-3">${escapeHtml(p.doc_type || "")}</p>
        ${badge}
      `;
      grid.appendChild(card);
    });
  }

  function selectPrompt(promptObj, cardEl) {
    document.querySelectorAll(".prompt-card").forEach(c => c.classList.remove("border-blue-500", "ring-2", "ring-blue-200"));
    cardEl.classList.remove("border-gray-100");
    cardEl.classList.add("border-blue-500", "ring-2", "ring-blue-200");
    selectedPrompt = promptObj;
    $("btn-step2-next").disabled = false;
    renderDynamicForm();
  }

  function renderDynamicForm() {
    const container = $("dynamic-form");
    container.innerHTML = "";

    if (!selectedPrompt) {
      container.innerHTML = '<div class="text-sm text-gray-500">Selecciona un prompt primero.</div>';
      return;
    }

    const vars = Array.isArray(selectedPrompt.variables) ? selectedPrompt.variables : [];
    if (!vars.length) {
      container.innerHTML = '<div class="text-sm text-gray-500">Este prompt no tiene variables. Edita el prompt en “Gestión Prompts”.</div>';
      return;
    }

    const titleBlock = document.createElement("div");
    titleBlock.innerHTML = `
      <label class="block text-sm font-medium text-slate-700 mb-1">Título (opcional)</label>
      <input id="var_title" type="text" class="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none" placeholder="Ej: Implementación de IA en procesos logísticos...">
    `;
    container.appendChild(titleBlock);

    vars.forEach((v) => {
      const id = "var_" + v;
      const label = v.replaceAll("_", " ");
      const block = document.createElement("div");

      const useTextarea = /(objetivo|resumen|metodologia|hipotesis|problema|justificacion)/i.test(v);

      if (useTextarea) {
        block.innerHTML = `
          <label class="block text-sm font-medium text-slate-700 mb-1">${escapeHtml(label)} ({{${escapeHtml(v)}}})</label>
          <textarea id="${escapeHtml(id)}" rows="3" class="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none" placeholder="Escribe ${escapeHtml(label)}..."></textarea>
        `;
      } else {
        block.innerHTML = `
          <label class="block text-sm font-medium text-slate-700 mb-1">${escapeHtml(label)} ({{${escapeHtml(v)}}})</label>
          <input id="${escapeHtml(id)}" type="text" class="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none" placeholder="Escribe ${escapeHtml(label)}...">
        `;
      }
      container.appendChild(block);
    });
  }

  async function startGeneration() {
    if (!selectedFormat || !selectedPrompt) return;

    const vars = {};
    (selectedPrompt.variables || []).forEach((v) => {
      const el = $("var_" + v);
      vars[v] = el ? el.value : "";
    });

    const title = $("var_title")?.value || vars.tema || "Proyecto";
    const payload = {
      format_id: selectedFormat.id,
      prompt_id: selectedPrompt.id,
      title,
      variables: vars,
    };

    nextStep(4);
    $("loading-label").innerText = "Creando proyecto...";

    const proj = await apiSend("/api/projects/generate", "POST", payload);
    currentProject = proj;

    $("loading-label").innerText = "Procesando (polling)...";

    if (pollTimer) clearInterval(pollTimer);

    pollTimer = setInterval(async () => {
      try {
        const p = await apiGet(`/api/projects/${encodeURIComponent(currentProject.id)}`);
        if (p.status === "completed") {
          clearInterval(pollTimer);
          pollTimer = null;
          showSuccess(p);
          refreshDashboard().catch(() => { });
          refreshHistory().catch(() => { });
        }
        if (p.status === "failed") {
          clearInterval(pollTimer);
          pollTimer = null;
          $("loading-label").innerText = "Falló: " + (p.error || "Error");
        }
      } catch (_) { }
    }, 1200);
  }

  function showSuccess(project) {
    $("loading-state").classList.add("hidden");
    $("success-state").classList.remove("hidden");
    $("success-state").classList.add("fade-in");

    $("success-desc").innerHTML = `El archivo fue creado para <strong>${escapeHtml(project.format_name || project.format_id)}</strong> con el prompt <strong>${escapeHtml(project.prompt_name || "")}</strong>.`;
    $("output-filename").innerText = project.output_file ? project.output_file.split("/").pop() : "Documento.docx";
    $("download-link").href = `/api/download/${encodeURIComponent(project.id)}`;

    const d4 = $("step-4-dot");
    d4.classList.remove("bg-blue-600", "bg-gray-200", "text-gray-500");
    d4.classList.add("bg-green-500", "text-white");
  }

  function openPromptModal(promptObj = null) {
    $("modal-error").classList.add("hidden");
    $("modal-error").innerText = "";

    if (!promptObj) {
      $("modal-title").innerText = "Nuevo Prompt";
      $("modal-prompt-id").value = "";
      $("modal-name").value = "";
      $("modal-doc-type").value = "Tesis Completa";
      $("modal-is-active").checked = true;
      $("modal-template").value = "";
      $("modal-vars").value = '["tema","objetivo_general"]';
    } else {
      $("modal-title").innerText = "Editar Prompt";
      $("modal-prompt-id").value = promptObj.id;
      $("modal-name").value = promptObj.name || "";
      $("modal-doc-type").value = promptObj.doc_type || "Tesis Completa";
      $("modal-is-active").checked = !!promptObj.is_active;
      $("modal-template").value = promptObj.template || "";
      $("modal-vars").value = JSON.stringify(promptObj.variables || []);
    }

    $("modal-prompt").classList.remove("hidden");
  }

  function closePromptModal() {
    $("modal-prompt").classList.add("hidden");
  }

  async function savePrompt() {
    try {
      $("modal-error").classList.add("hidden");

      const id = $("modal-prompt-id").value.trim();
      const name = $("modal-name").value.trim();
      const doc_type = $("modal-doc-type").value;
      const is_active = $("modal-is-active").checked;
      const template = $("modal-template").value;

      let variables;
      try {
        variables = JSON.parse($("modal-vars").value);
        if (!Array.isArray(variables)) throw new Error();
      } catch (_) {
        throw new Error('Variables debe ser un JSON Array válido. Ej: ["tema","objetivo_general"]');
      }

      if (!name) throw new Error("Nombre requerido");

      const body = { name, doc_type, is_active, template, variables };

      if (!id) await apiSend("/api/prompts", "POST", body);
      else await apiSend(`/api/prompts/${encodeURIComponent(id)}`, "PUT", body);

      closePromptModal();
      await refreshPromptsAdmin();
      await loadPromptsForWizard();
    } catch (e) {
      $("modal-error").classList.remove("hidden");
      $("modal-error").innerText = e.message || String(e);
    }
  }

  async function deletePrompt(id) {
    if (!confirm("¿Eliminar este prompt?")) return;
    await apiSend(`/api/prompts/${encodeURIComponent(id)}`, "DELETE");
    await refreshPromptsAdmin();
    await loadPromptsForWizard();
  }

  async function refreshPromptsAdmin() {
    const items = await apiGet("/api/prompts");
    const tbody = $("prompts-table");
    tbody.innerHTML = "";

    if (!items.length) {
      $("prompts-empty").classList.remove("hidden");
      return;
    }
    $("prompts-empty").classList.add("hidden");

    items.forEach((p) => {
      const vars = (p.variables || []).slice(0, 6).map(v => `<span class="bg-blue-50 text-blue-600 px-2 py-1 rounded text-xs border border-blue-100 mx-1">${escapeHtml(v)}</span>`).join("");
      const status = p.is_active ? '<span class="text-green-600 text-xs font-bold">● Activo</span>' : '<span class="text-gray-400 text-xs font-bold">● Inactivo</span>';

      const row = document.createElement("tr");
      row.className = "hover:bg-gray-50 transition";
      row.innerHTML = `
        <td class="px-6 py-4 font-medium">${escapeHtml(p.name)}</td>
        <td class="px-6 py-4">${vars || '<span class="text-xs text-gray-400">Sin variables</span>'}</td>
        <td class="px-6 py-4">${status}</td>
        <td class="px-6 py-4 text-right text-gray-400">
          <i class="fa-solid fa-pen hover:text-blue-600 cursor-pointer mr-3"></i>
          <i class="fa-solid fa-trash hover:text-red-600 cursor-pointer"></i>
        </td>
      `;
      row.querySelector(".fa-pen").onclick = () => openPromptModal(p);
      row.querySelector(".fa-trash").onclick = () => deletePrompt(p.id);
      tbody.appendChild(row);
    });
  }

  async function refreshHistory() {
    const items = await apiGet("/api/projects");
    const tbody = $("history-table");
    tbody.innerHTML = "";

    const q = ($("history-search")?.value || "").toLowerCase();
    const filtered = items.filter(p => {
      const blob = `${p.title || ""} ${p.prompt_name || ""} ${p.format_name || ""}`.toLowerCase();
      return !q || blob.includes(q);
    });

    if (!filtered.length) {
      $("history-empty").classList.remove("hidden");
      return;
    }
    $("history-empty").classList.add("hidden");

    filtered.forEach((p) => {
      const canDownload = p.status === "completed" && p.output_file;
      const actions = canDownload
        ? `<a class="p-2 text-slate-500 hover:text-green-600 hover:bg-green-50 rounded" title="Descargar DOCX" href="/api/download/${encodeURIComponent(p.id)}"><i class="fa-solid fa-file-word"></i></a>`
        : `<span class="p-2 text-gray-300 rounded" title="No disponible"><i class="fa-solid fa-file-word"></i></span>`;

      const row = document.createElement("tr");
      row.className = "hover:bg-gray-50 transition";
      row.innerHTML = `
        <td class="px-6 py-4">
          <div class="font-medium text-slate-800">${escapeHtml(p.title)}</div>
          <div class="text-xs text-gray-400 flex gap-1 mt-1">
            <i class="fa-solid fa-robot mt-0.5"></i> ${escapeHtml(p.prompt_name || "")}
          </div>
        </td>
        <td class="px-6 py-4 text-gray-600">${escapeHtml(p.format_name || p.format_id || "")}</td>
        <td class="px-6 py-4">${statusBadge(p.status)}</td>
        <td class="px-6 py-4 text-gray-500">${escapeHtml(p.created_at || "")}</td>
        <td class="px-6 py-4 text-right flex justify-end gap-2">${actions}</td>
      `;
      tbody.appendChild(row);
    });
  }

  function wireHistorySearch() {
    const input = $("history-search");
    if (!input) return;
    input.oninput = () => refreshHistory().catch(() => { });
  }

  return {
    showView,
    nextStep,
    prevStep,
    startGeneration,
    openPromptModal,
    closePromptModal,
    savePrompt,
    async boot() {
      wireHistorySearch();
      await refreshDashboard();
    },
  };
})();

window.TesisAI = TesisAI;
window.addEventListener("DOMContentLoaded", () => TesisAI.boot().catch(console.error));
