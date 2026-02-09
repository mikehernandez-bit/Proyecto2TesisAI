/**
 * GicaGen frontend SPA.
 *
 * Wizard flow:
 * 1) Select format
 * 2) Select prompt
 * 3) Fill details
 * 4) n8n simulation guide
 * 5) Simulated downloads
 */
const TesisAI = (() => {
  const TOTAL_STEPS = 5;

  let currentView = "dashboard";
  let currentStep = 1;

  let selectedFormat = null;
  let selectedPrompt = null;
  let currentProject = null;
  let n8nSpec = null;
  let simRunResult = null;
  let isPreparingGuide = false;
  let isRunningSimulation = false;

  const $ = (id) => document.getElementById(id);

  function escapeHtml(input) {
    return String(input ?? "").replace(/[&<>"']/g, (char) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#039;",
    }[char]));
  }

  function toPrettyJson(value) {
    return JSON.stringify(value ?? {}, null, 2);
  }

  async function copyText(text) {
    await navigator.clipboard.writeText(String(text ?? ""));
  }

  function downloadText(filename, text) {
    const blob = new Blob([String(text ?? "")], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  async function parseError(response) {
    const raw = await response.text();
    try {
      const payload = JSON.parse(raw);
      if (payload && typeof payload.detail === "string") return payload.detail;
      return raw;
    } catch (_) {
      return raw;
    }
  }

  async function apiGet(url) {
    const response = await fetch(url);
    if (!response.ok) throw new Error(await parseError(response));
    return response.json();
  }

  async function apiSend(url, method, body) {
    const response = await fetch(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!response.ok) throw new Error(await parseError(response));
    return response.json();
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
    if (viewId === "dashboard") refreshDashboard().catch(console.error);
    if (viewId === "wizard") initWizard().catch(console.error);
    if (viewId === "admin-prompts") refreshPromptsAdmin().catch(console.error);
    if (viewId === "history") refreshHistory().catch(console.error);
  }

  function statusBadge(status) {
    if (status === "draft") return '<span class="bg-slate-100 text-slate-700 px-2 py-1 rounded text-xs font-semibold">Borrador</span>';
    if (status === "ai_received") return '<span class="bg-indigo-100 text-indigo-700 px-2 py-1 rounded text-xs font-semibold">IA recibida</span>';
    if (status === "simulated") return '<span class="bg-cyan-100 text-cyan-700 px-2 py-1 rounded text-xs font-semibold">Simulado</span>';
    if (status === "completed") return '<span class="bg-green-100 text-green-700 px-2 py-1 rounded text-xs font-semibold">Completado</span>';
    if (status === "processing") return '<span class="bg-yellow-100 text-yellow-700 px-2 py-1 rounded text-xs font-semibold">Procesando</span>';
    if (status === "failed") return '<span class="bg-red-100 text-red-700 px-2 py-1 rounded text-xs font-semibold">Fallo</span>';
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

    items.slice(0, 5).forEach((project) => {
      const canDownload = project.status === "completed" && project.output_file;
      const downloadBtn = canDownload
        ? `<a class="text-blue-600 hover:text-blue-800" href="/api/download/${encodeURIComponent(project.id)}" title="Descargar"><i class="fa-solid fa-download"></i></a>`
        : `<span class="text-gray-300" title="No disponible"><i class="fa-solid fa-download"></i></span>`;

      const row = document.createElement("tr");
      row.className = "hover:bg-gray-50";
      row.innerHTML = `
        <td class="px-6 py-4">
          <div class="font-medium text-slate-800">${escapeHtml(project.title)}</div>
          <div class="text-xs text-gray-400">${escapeHtml(project.prompt_name || "")}</div>
        </td>
        <td class="px-6 py-4 text-gray-600">${escapeHtml(project.format_name || project.format_id || "")}</td>
        <td class="px-6 py-4">${statusBadge(project.status)}</td>
        <td class="px-6 py-4 text-gray-500">${escapeHtml(project.created_at || "")}</td>
        <td class="px-6 py-4 text-right">${downloadBtn}</td>
      `;
      tbody.appendChild(row);
    });
  }

  function updateStepperUI() {
    $("current-step-label").innerText = String(currentStep);

    for (let i = 1; i <= TOTAL_STEPS; i += 1) {
      const dot = $(`step-${i}-dot`);
      if (!dot) continue;
      dot.className = "w-8 h-8 rounded-full flex items-center justify-center font-bold text-sm z-10";

      if (i < currentStep) {
        dot.classList.add("bg-green-500", "text-white");
        dot.innerHTML = '<i class="fa-solid fa-check"></i>';
      } else if (i === currentStep) {
        dot.classList.add("bg-blue-600", "text-white");
        dot.innerHTML = String(i);
      } else {
        dot.classList.add("bg-gray-200", "text-gray-500");
        dot.innerHTML = String(i);
      }
    }

    for (let i = 1; i < TOTAL_STEPS; i += 1) {
      const line = $(`step-${i}-line`);
      if (!line) continue;
      line.className = "flex-1 h-1 mx-2 rounded";
      if (i < currentStep) line.classList.add("bg-green-500");
      else line.classList.add("bg-gray-200");
    }
  }

  function showStep(step) {
    for (let i = 1; i <= TOTAL_STEPS; i += 1) {
      const content = $(`step-${i}-content`);
      if (!content) continue;
      if (i === step) {
        content.classList.remove("hidden");
        content.classList.add("fade-in");
      } else {
        content.classList.add("hidden");
      }
    }
  }

  function resetStepper() {
    currentStep = 1;
    selectedFormat = null;
    selectedPrompt = null;
    currentProject = null;
    n8nSpec = null;
    simRunResult = null;
    isPreparingGuide = false;
    isRunningSimulation = false;

    if ($("btn-step1-next")) $("btn-step1-next").disabled = true;
    if ($("btn-step2-next")) $("btn-step2-next").disabled = true;
    if ($("btn-step3-guide")) $("btn-step3-guide").disabled = false;

    setStep3Error("");
    if ($("n8n-guide-empty")) $("n8n-guide-empty").classList.remove("hidden");
    if ($("n8n-guide-content")) $("n8n-guide-content").classList.add("hidden");
    if ($("sim-run-status")) $("sim-run-status").textContent = "";
    if ($("btn-run-sim")) $("btn-run-sim").disabled = false;

    if ($("sim-project-id")) $("sim-project-id").textContent = "-";
    if ($("sim-download-docx")) $("sim-download-docx").setAttribute("href", "#");
    if ($("sim-download-pdf")) $("sim-download-pdf").setAttribute("href", "#");

    updateStepperUI();
    showStep(1);
  }

  function nextStep(step) {
    currentStep = step;
    updateStepperUI();
    showStep(step);
  }

  function prevStep(step) {
    currentStep = step;
    updateStepperUI();
    showStep(step);
  }

  function getCategoryLabel(rawCategory) {
    const labels = {
      proyecto: "Proyecto de tesis",
      informe: "Informe de tesis",
      maestria: "Tesis de postgrado",
      posgrado: "Tesis de postgrado",
      general: "Documentos generales",
    };
    return labels[rawCategory] || rawCategory || "Sin categoria";
  }

  async function initWizard() {
    resetStepper();
    await loadFormats();
    await loadPromptsForWizard();
  }

  async function loadFormats() {
    const response = await apiGet("/api/formats");
    const items = response.formats || [];

    const universities = Array.from(new Set(items.map((x) => x.university))).filter(Boolean).sort();
    const categories = Array.from(new Set(items.map((x) => getCategoryLabel(x.category)))).filter(Boolean).sort();

    const uniSel = $("filter-university");
    const catSel = $("filter-career");

    uniSel.innerHTML = '<option value="">Todas las universidades</option>' +
      universities.map((u) => `<option value="${escapeHtml(u)}">${escapeHtml(String(u).toUpperCase())}</option>`).join("");
    catSel.innerHTML = '<option value="">Tipo de documento</option>' +
      categories.map((c) => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join("");

    async function render() {
      const selectedUni = uniSel.value || "";
      const selectedCategory = catSel.value || "";
      const filtered = items.filter((item) => {
        const matchesUni = !selectedUni || item.university === selectedUni;
        const matchesCategory = !selectedCategory || getCategoryLabel(item.category) === selectedCategory;
        return matchesUni && matchesCategory;
      });

      const grid = $("formats-grid");
      grid.innerHTML = "";

      if (!filtered.length) {
        grid.innerHTML = '<div class="text-sm text-gray-500">No hay formatos para esos filtros.</div>';
        return;
      }

      filtered.forEach((format) => {
        const card = document.createElement("div");
        card.className = "format-card border-2 border-gray-100 hover:border-blue-400 p-4 rounded-lg cursor-pointer transition group relative bg-white";
        card.onclick = () => selectFormat(format, card);

        const docType = format.documentType ? ` (${format.documentType})` : "";
        const universityCode = String(format.university || "generic").toLowerCase();
        const logoUrl = `/api/assets/logos/${universityCode}.png`;

        card.innerHTML = `
          <div class="absolute top-3 right-3 opacity-0 group-hover:opacity-100 text-blue-500">
            <i class="fa-solid fa-circle-check fa-lg"></i>
          </div>
          <div class="flex items-center gap-4 mb-3">
            <div class="w-12 h-12 shrink-0 flex items-center justify-center p-1 border rounded bg-gray-50">
              <img src="${logoUrl}" alt="${escapeHtml(universityCode)}" class="w-full h-full object-contain"
                onerror="this.onerror=null;this.parentNode.innerHTML='<span class=&quot;text-blue-700 font-bold&quot;>${escapeHtml(String(universityCode).toUpperCase())}</span>'">
            </div>
            <div>
              <div class="font-bold text-sm text-slate-800 leading-tight">${escapeHtml(format.title || format.name || format.id)}</div>
              <div class="text-xs text-gray-400 mt-1">v${escapeHtml(String(format.version || "").substring(0, 8))}</div>
            </div>
          </div>
          <div class="mt-2 text-xs text-slate-500 bg-slate-50 p-2 rounded flex items-center gap-2">
            <i class="fa-solid fa-tag text-blue-400"></i>
            <span>${escapeHtml(getCategoryLabel(format.category))}${escapeHtml(docType)}</span>
          </div>
        `;

        grid.appendChild(card);
      });
    }

    uniSel.onchange = render;
    catSel.onchange = render;
    await render();
  }

  function selectFormat(formatObj, cardEl) {
    document.querySelectorAll(".format-card").forEach((c) => c.classList.remove("border-blue-500", "bg-blue-50"));
    cardEl.classList.remove("border-gray-100");
    cardEl.classList.add("border-blue-500", "bg-blue-50");
    selectedFormat = formatObj;
    $("btn-step1-next").disabled = false;
  }

  async function loadPromptsForWizard() {
    const items = await apiGet("/api/prompts");
    const active = items.filter((p) => p.is_active);

    const grid = $("prompts-grid");
    grid.innerHTML = "";

    if (!active.length) {
      grid.innerHTML = '<div class="text-sm text-gray-500">No hay prompts activos. Ve a Gestion prompts.</div>';
      return;
    }

    active.forEach((prompt, idx) => {
      const card = document.createElement("div");
      card.className = "prompt-card border-2 border-gray-100 hover:border-blue-500 p-5 rounded-lg cursor-pointer transition bg-white text-center";
      card.onclick = () => selectPrompt(prompt, card);

      const badge = idx === 0
        ? '<span class="bg-indigo-100 text-indigo-700 text-[10px] px-2 py-0.5 rounded-full font-bold">RECOMENDADO</span>'
        : "";

      card.innerHTML = `
        <div class="w-12 h-12 bg-indigo-50 text-indigo-600 rounded-full flex items-center justify-center mx-auto mb-3">
          <i class="fa-solid fa-book-open"></i>
        </div>
        <h4 class="font-bold text-slate-800">${escapeHtml(prompt.name)}</h4>
        <p class="text-xs text-gray-500 mt-1 mb-3">${escapeHtml(prompt.doc_type || "")}</p>
        ${badge}
      `;

      grid.appendChild(card);
    });
  }

  function selectPrompt(promptObj, cardEl) {
    document.querySelectorAll(".prompt-card").forEach((c) => c.classList.remove("border-blue-500", "ring-2", "ring-blue-200"));
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
      container.innerHTML = '<div class="text-sm text-gray-500">Este prompt no tiene variables.</div>';
      return;
    }

    const titleBlock = document.createElement("div");
    titleBlock.innerHTML = `
      <label class="block text-sm font-medium text-slate-700 mb-1">Titulo (opcional)</label>
      <input id="var_title" type="text" class="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none"
        placeholder="Ej: Implementacion de IA en procesos logisticos">
    `;
    container.appendChild(titleBlock);

    vars.forEach((variable) => {
      const id = "var_" + variable;
      const label = variable.replaceAll("_", " ");
      const block = document.createElement("div");
      const useTextarea = /(objetivo|resumen|metodologia|hipotesis|problema|justificacion)/i.test(variable);

      if (useTextarea) {
        block.innerHTML = `
          <label class="block text-sm font-medium text-slate-700 mb-1">${escapeHtml(label)} ({{${escapeHtml(variable)}}})</label>
          <textarea id="${escapeHtml(id)}" rows="3"
            class="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none"
            placeholder="Escribe ${escapeHtml(label)}"></textarea>
        `;
      } else {
        block.innerHTML = `
          <label class="block text-sm font-medium text-slate-700 mb-1">${escapeHtml(label)} ({{${escapeHtml(variable)}}})</label>
          <input id="${escapeHtml(id)}" type="text"
            class="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none"
            placeholder="Escribe ${escapeHtml(label)}">
        `;
      }

      container.appendChild(block);
    });
  }

  function collectWizardPayload() {
    const values = {};
    (selectedPrompt?.variables || []).forEach((variable) => {
      const el = $("var_" + variable);
      values[variable] = el ? el.value : "";
    });

    const title = $("var_title")?.value || values.tema || "Proyecto";
    return { title, values };
  }

  function setStep3Error(message) {
    const el = $("step3-error");
    if (!el) return;
    const normalized = String(message || "").trim();
    if (!normalized) {
      el.classList.add("hidden");
      el.textContent = "";
      return;
    }
    el.classList.remove("hidden");
    el.textContent = normalized;
  }

  function renderN8nGuide() {
    const empty = $("n8n-guide-empty");
    const content = $("n8n-guide-content");
    if (!n8nSpec || !empty || !content) return;

    empty.classList.add("hidden");
    content.classList.remove("hidden");

    const summary = n8nSpec.summary || {};
    const summaryFormat = summary.format || {};
    const summaryPrompt = summary.prompt || {};

    $("n8n-summary").innerHTML = `
      <div><strong>Formato:</strong> ${escapeHtml(summaryFormat.title || summaryFormat.id || "")}</div>
      <div><strong>Prompt:</strong> ${escapeHtml(summaryPrompt.name || summaryPrompt.id || "")}</div>
      <div><strong>projectId:</strong> <code>${escapeHtml(summary.projectId || "")}</code></div>
      <div><strong>status:</strong> ${escapeHtml(summary.status || "")}</div>
    `;

    const envCheck = n8nSpec.envCheck || {};
    const envItems = Object.entries(envCheck);
    $("n8n-autocheck").innerHTML = envItems.map(([name, meta]) => {
      const ok = !!meta?.ok;
      const mark = ok ? "OK" : "MISSING";
      const cls = ok ? "text-green-600" : "text-red-600";
      return `<li><span class="${cls} font-semibold">${mark}</span> <code>${escapeHtml(name)}</code> = ${escapeHtml(meta?.value ?? "")}</li>`;
    }).join("");

    const request = n8nSpec.request || {};
    const expected = n8nSpec.expectedResponse || {};

    $("n8n-payload").textContent = toPrettyJson(request.payload || {});
    $("n8n-headers").textContent = toPrettyJson({
      toN8N: request.headers || {},
      toCallback: expected.headers || {},
    });

    const checklist = n8nSpec.checklist || [];
    $("n8n-checklist").innerHTML = checklist.map((item) => (
      `<li><strong>${escapeHtml(item.title || "")}</strong> - ${escapeHtml(item.detail || "")}</li>`
    )).join("");

    const payloadRuntime = request.payload?.runtime || {};
    $("n8n-urls").innerHTML = `
      <div><strong>Webhook n8n:</strong> <code>${escapeHtml(request.webhookUrl || "")}</code></div>
      <div><strong>Callback GicaGen:</strong> <code>${escapeHtml(expected.callbackUrl || payloadRuntime.callbackUrl || "")}</code></div>
      <div><strong>GicaTesis base:</strong> <code>${escapeHtml(payloadRuntime.gicatesisBaseUrl || "")}</code></div>
    `;

    $("n8n-format-detail").textContent = toPrettyJson(n8nSpec.formatDetail || {});
    $("n8n-format-definition").textContent = toPrettyJson(
      n8nSpec.formatDefinition || n8nSpec.formatDetail?.definition || {}
    );
    $("n8n-prompt-text").textContent = String(
      n8nSpec.promptDetail?.text || n8nSpec.promptText || request.payload?.prompt?.text || ""
    );
    $("n8n-expected-response").textContent = toPrettyJson(expected.bodyExample || {});
    $("n8n-sim-output").textContent = toPrettyJson(
      n8nSpec.simulationOutput || expected.bodyExample || {}
    );

    const runOutput = n8nSpec.simulationOutput || {};
    const runId = runOutput.runId || "";
    if ($("sim-run-status")) {
      $("sim-run-status").textContent = runId
        ? `Resultado simulado disponible (runId: ${runId})`
        : "Aun no se ejecuto una simulacion manual.";
    }

    const exportButton = $("btn-export-guide");
    if (exportButton) exportButton.disabled = !n8nSpec.markdown;
  }

  async function prepareN8nGuide() {
    if (!selectedFormat || !selectedPrompt || isPreparingGuide) return;

    const actionButton = $("btn-step3-guide");
    isPreparingGuide = true;
    if (actionButton) actionButton.disabled = true;
    setStep3Error("");

    try {
      const wizard = collectWizardPayload();

      if (!currentProject?.id) {
        const draft = await apiSend("/api/projects/draft", "POST", {
          title: wizard.title,
          formatId: selectedFormat.id,
          formatName: selectedFormat.title || selectedFormat.name || selectedFormat.id,
          formatVersion: selectedFormat.version,
          promptId: selectedPrompt.id,
          values: wizard.values,
        });
        const draftId = draft?.id || draft?.projectId;
        if (!draftId) throw new Error("No se pudo obtener projectId del borrador.");
        currentProject = { ...(draft || {}), id: draftId };
      } else {
        await apiSend(`/api/projects/${encodeURIComponent(currentProject.id)}`, "PUT", {
          title: wizard.title,
          formatId: selectedFormat.id,
          formatName: selectedFormat.title || selectedFormat.name || selectedFormat.id,
          formatVersion: selectedFormat.version,
          promptId: selectedPrompt.id,
          values: wizard.values,
          status: "draft",
        });
      }

      n8nSpec = await apiGet(`/api/integrations/n8n/spec?projectId=${encodeURIComponent(currentProject.id)}`);
      nextStep(4);
      renderN8nGuide();
      refreshDashboard().catch(() => {});
      refreshHistory().catch(() => {});
    } catch (error) {
      const message = error?.message || "No se pudo generar la guia n8n.";
      setStep3Error(message);
      alert(`Error: ${message}`);
    } finally {
      isPreparingGuide = false;
      if (actionButton) actionButton.disabled = false;
    }
  }

  function continueToSimDownloads() {
    if (!currentProject?.id) return;

    const id = currentProject.id;
    const output = simRunResult || n8nSpec?.simulationOutput || {};
    const runId = output.runId || "";
    const docxUrl = output.artifacts?.find?.((x) => x.type === "docx")?.downloadUrl
      || `/api/sim/download/docx?projectId=${encodeURIComponent(id)}${runId ? `&runId=${encodeURIComponent(runId)}` : ""}`;
    const pdfUrl = output.artifacts?.find?.((x) => x.type === "pdf")?.downloadUrl
      || `/api/sim/download/pdf?projectId=${encodeURIComponent(id)}${runId ? `&runId=${encodeURIComponent(runId)}` : ""}`;

    if ($("sim-project-id")) $("sim-project-id").textContent = id;
    if ($("sim-download-docx")) $("sim-download-docx").setAttribute("href", docxUrl);
    if ($("sim-download-pdf")) $("sim-download-pdf").setAttribute("href", pdfUrl);
    nextStep(5);
  }

  async function runN8nSimulation() {
    if (!currentProject?.id || isRunningSimulation) return;

    const button = $("btn-run-sim");
    isRunningSimulation = true;
    if (button) button.disabled = true;
    if ($("sim-run-status")) $("sim-run-status").textContent = "Ejecutando simulacion...";

    try {
      const result = await apiSend(
        `/api/sim/n8n/run?projectId=${encodeURIComponent(currentProject.id)}`,
        "POST"
      );
      simRunResult = result;
      if (n8nSpec) {
        n8nSpec.simulationOutput = {
          projectId: result.projectId,
          runId: result.runId,
          status: "success",
          aiResult: result.aiResult,
          artifacts: result.artifacts,
        };
      }
      renderN8nGuide();
      refreshDashboard().catch(() => {});
      refreshHistory().catch(() => {});
    } catch (error) {
      const message = error?.message || "No se pudo ejecutar la simulacion.";
      if ($("sim-run-status")) $("sim-run-status").textContent = message;
      alert(`Error: ${message}`);
    } finally {
      isRunningSimulation = false;
      if (button) button.disabled = false;
    }
  }

  async function copyN8nPayload() {
    if (!n8nSpec) return;
    await copyText(toPrettyJson(n8nSpec.request?.payload || {}));
  }

  async function copyN8nHeaders() {
    if (!n8nSpec) return;
    await copyText(toPrettyJson({
      toN8N: n8nSpec.request?.headers || {},
      toCallback: n8nSpec.expectedResponse?.headers || {},
    }));
  }

  async function copyN8nWebhook() {
    if (!n8nSpec) return;
    await copyText(n8nSpec.request?.webhookUrl || "");
  }

  function exportN8nGuide() {
    if (!n8nSpec || !n8nSpec.markdown) return;
    const projectId = n8nSpec.summary?.projectId || "project";
    downloadText(`n8n-guide-${projectId}.md`, n8nSpec.markdown);
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
        if (!Array.isArray(variables)) throw new Error("invalid");
      } catch (_) {
        throw new Error('Variables debe ser un JSON Array valido. Ej: ["tema","objetivo_general"]');
      }

      if (!name) throw new Error("Nombre requerido");

      const body = { name, doc_type, is_active, template, variables };
      if (!id) await apiSend("/api/prompts", "POST", body);
      else await apiSend(`/api/prompts/${encodeURIComponent(id)}`, "PUT", body);

      closePromptModal();
      await refreshPromptsAdmin();
      await loadPromptsForWizard();
    } catch (error) {
      $("modal-error").classList.remove("hidden");
      $("modal-error").innerText = error.message || String(error);
    }
  }

  async function deletePrompt(id) {
    if (!confirm("Eliminar este prompt?")) return;
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
          <i class="fa-solid fa-pen hover:text-blue-600 cursor-pointer mr-3"></i>
          <i class="fa-solid fa-trash hover:text-red-600 cursor-pointer"></i>
        </td>
      `;
      row.querySelector(".fa-pen").onclick = () => openPromptModal(prompt);
      row.querySelector(".fa-trash").onclick = () => deletePrompt(prompt.id);
      tbody.appendChild(row);
    });
  }

  async function refreshHistory() {
    const items = await apiGet("/api/projects");
    const tbody = $("history-table");
    tbody.innerHTML = "";

    const q = ($("history-search")?.value || "").toLowerCase();
    const filtered = items.filter((project) => {
      const blob = `${project.title || ""} ${project.prompt_name || ""} ${project.format_name || ""}`.toLowerCase();
      return !q || blob.includes(q);
    });

    if (!filtered.length) {
      $("history-empty").classList.remove("hidden");
      return;
    }
    $("history-empty").classList.add("hidden");

    filtered.forEach((project) => {
      const canDownload = project.status === "completed" && project.output_file;
      const actions = canDownload
        ? `<a class="p-2 text-slate-500 hover:text-green-600 hover:bg-green-50 rounded" title="Descargar DOCX" href="/api/download/${encodeURIComponent(project.id)}"><i class="fa-solid fa-file-word"></i></a>`
        : `<span class="p-2 text-gray-300 rounded" title="No disponible"><i class="fa-solid fa-file-word"></i></span>`;

      const row = document.createElement("tr");
      row.className = "hover:bg-gray-50 transition";
      row.innerHTML = `
        <td class="px-6 py-4">
          <div class="font-medium text-slate-800">${escapeHtml(project.title)}</div>
          <div class="text-xs text-gray-400 flex gap-1 mt-1">
            <i class="fa-solid fa-robot mt-0.5"></i> ${escapeHtml(project.prompt_name || "")}
          </div>
        </td>
        <td class="px-6 py-4 text-gray-600">${escapeHtml(project.format_name || project.format_id || "")}</td>
        <td class="px-6 py-4">${statusBadge(project.status)}</td>
        <td class="px-6 py-4 text-gray-500">${escapeHtml(project.created_at || "")}</td>
        <td class="px-6 py-4 text-right flex justify-end gap-2">${actions}</td>
      `;
      tbody.appendChild(row);
    });
  }

  function wireHistorySearch() {
    const input = $("history-search");
    if (!input) return;
    input.oninput = () => refreshHistory().catch(() => {});
  }

  return {
    showView,
    nextStep,
    prevStep,
    prepareN8nGuide,
    runN8nSimulation,
    continueToSimDownloads,
    openPromptModal,
    closePromptModal,
    savePrompt,
    copyN8nPayload,
    copyN8nHeaders,
    copyN8nWebhook,
    exportN8nGuide,
    async boot() {
      wireHistorySearch();
      await refreshDashboard();
    },
  };
})();

window.TesisAI = TesisAI;
window.addEventListener("DOMContentLoaded", () => TesisAI.boot().catch(console.error));
