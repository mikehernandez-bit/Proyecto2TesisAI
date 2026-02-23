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
  const TOTAL_STEPS = 6;

  let currentView = "dashboard";
  let currentStep = 1;

  let selectedFormat = null;
  let selectedPrompt = null;
  let currentProject = null;
  let n8nSpec = null;
  let simRunResult = null;
  let isPreparingGuide = false;
  let isRunningSimulation = false;
  let providerStatusCache = null;
  let gicatesisOnline = true;

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
      if (payload && payload.detail && typeof payload.detail.message === "string") {
        return payload.detail.message;
      }
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
    if (status === "generating") return '<span class="bg-blue-100 text-blue-700 px-2 py-1 rounded text-xs font-semibold">Generando</span>';
    if (status === "ai_received") return '<span class="bg-indigo-100 text-indigo-700 px-2 py-1 rounded text-xs font-semibold">IA recibida</span>';
    if (status === "cancel_requested") return '<span class="bg-amber-100 text-amber-700 px-2 py-1 rounded text-xs font-semibold">Cancelando</span>';
    if (status === "simulated") return '<span class="bg-cyan-100 text-cyan-700 px-2 py-1 rounded text-xs font-semibold">Simulado</span>';
    if (status === "completed") return '<span class="bg-green-100 text-green-700 px-2 py-1 rounded text-xs font-semibold">Completado</span>';
    if (status === "completed_with_incidents") return '<span class="bg-amber-100 text-amber-700 px-2 py-1 rounded text-xs font-semibold">Completado con incidencias</span>';
    if (status === "processing") return '<span class="bg-yellow-100 text-yellow-700 px-2 py-1 rounded text-xs font-semibold">Procesando</span>';
    if (status === "generation_failed" || status === "ai_failed" || status === "blocked") return '<span class="bg-red-100 text-red-700 px-2 py-1 rounded text-xs font-semibold">Fallo</span>';
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
      const canDownload = (project.status === "completed" || project.status === "completed_with_incidents") && project.output_file;
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
    if ($("btn-step3-next-provider")) {
      $("btn-step3-next-provider").classList.remove("hidden");
    }
    if ($("step3-loading")) $("step3-loading").classList.add("hidden");
    if ($("btn-step4-generate")) $("btn-step4-generate").classList.remove("hidden");
    if ($("step4-loading")) $("step4-loading").classList.add("hidden");

    setStep3Error("");
    setStep4Error("");

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
    if (step === 4) {
      loadProviderStatus(currentProject?.id || null).catch(console.error);
    }
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
    if ($("btn-provider-refresh")) {
      $("btn-provider-refresh").onclick = () => probeProviderStatus(currentProject?.id || null).catch(console.error);
    }
    await loadProviderStatus();
  }

  async function loadFormats() {
    // Use raw fetch to read X-Upstream-Online / X-Data-Source headers.
    const raw = await fetch("/api/formats");
    if (!raw.ok) throw new Error(await parseError(raw));

    gicatesisOnline = raw.headers.get("X-Upstream-Online") !== "false";
    const dataSource = raw.headers.get("X-Data-Source") || "cache";

    const response = await raw.json();
    const items = response.formats || [];

    // Show / hide the offline banner
    const banner = $("gicatesis-offline-banner");
    if (banner) {
      if (!gicatesisOnline) {
        banner.classList.remove("hidden");
      } else {
        banner.classList.add("hidden");
      }
    }

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

        // When GicaTesis is offline, skip loading remote logos — use text fallback.
        const logoHtml = gicatesisOnline
          ? `<img src="${logoUrl}" alt="${escapeHtml(universityCode)}" class="w-full h-full object-contain"
              onerror="this.onerror=null;this.parentNode.innerHTML='<span class=&quot;text-blue-700 font-bold&quot;>${escapeHtml(String(universityCode).toUpperCase())}</span>'">`
          : `<span class="text-blue-700 font-bold">${escapeHtml(String(universityCode).toUpperCase())}</span>`;

        card.innerHTML = `
          <div class="absolute top-3 right-3 opacity-0 group-hover:opacity-100 text-blue-500">
            <i class="fa-solid fa-circle-check fa-lg"></i>
          </div>
          <div class="flex items-center gap-4 mb-3">
            <div class="w-12 h-12 shrink-0 flex items-center justify-center p-1 border rounded bg-gray-50">
              ${logoHtml}
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

  function setStep4Error(message) {
    const el = $("step4-error");
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

  function setProviderSelectorError(message) {
    const el = $("provider-select-error");
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

  function _providerHealthMeta(provider) {
    const probeStatus = String(
      provider?.probe?.status ?? provider?.last_probe_status ?? "UNVERIFIED"
    ).toUpperCase();
    const retryAfter = Number(
      provider?.probe?.retry_after_s ?? provider?.last_probe_retry_after_s ?? 0
    );
    const health = String(provider?.health || "UNKNOWN").toUpperCase();

    if (probeStatus === "OK") {
      return {
        label: "Disponible",
        icon: "OK",
        ring: "#16a34a",
        chip: "bg-green-50 text-green-700 border-green-200",
      };
    }
    if (probeStatus === "UNVERIFIED") {
      return {
        label: "No verificado",
        icon: "...",
        ring: "#64748b",
        chip: "bg-slate-50 text-slate-700 border-slate-200",
      };
    }
    if (probeStatus === "RATE_LIMITED") {
      return {
        label: retryAfter > 0 ? `Rate-limited (${retryAfter}s)` : "Rate-limited",
        icon: "!",
        ring: "#f59e0b",
        chip: "bg-amber-50 text-amber-700 border-amber-200",
      };
    }
    if (probeStatus === "EXHAUSTED") {
      return {
        label: "Sin cuota",
        icon: "X",
        ring: "#dc2626",
        chip: "bg-red-50 text-red-700 border-red-200",
      };
    }
    if (probeStatus === "AUTH_ERROR") {
      return {
        label: "Credenciales invalidas",
        icon: "X",
        ring: "#dc2626",
        chip: "bg-red-50 text-red-700 border-red-200",
      };
    }
    if (probeStatus === "ERROR" || health === "DEGRADED") {
      return {
        label: "Degradado",
        icon: "!",
        ring: "#f97316",
        chip: "bg-orange-50 text-orange-700 border-orange-200",
      };
    }
    return {
      label: "Desconocido",
      icon: "o",
      ring: "#64748b",
      chip: "bg-slate-50 text-slate-700 border-slate-200",
    };
  }

  function _ringMarkup({ valueText, percent, color, label, subLabel }) {
    const safePercent = Number.isFinite(percent) ? Math.max(0, Math.min(100, percent)) : 0;
    const radius = 24;
    const circumference = 2 * Math.PI * radius;
    const dash = (safePercent / 100) * circumference;
    return `
      <div class="provider-ring flex flex-col items-center">
        <svg viewBox="0 0 64 64" role="img" aria-label="${escapeHtml(label)}">
          <circle cx="32" cy="32" r="${radius}" fill="none" stroke="#e2e8f0" stroke-width="6"></circle>
          <circle
            cx="32" cy="32" r="${radius}" fill="none" stroke="${escapeHtml(color)}" stroke-width="6"
            stroke-linecap="round"
            stroke-dasharray="${dash} ${circumference - dash}"
            transform="rotate(-90 32 32)"
          ></circle>
          <text x="32" y="31" text-anchor="middle" font-size="10" fill="#0f172a">${escapeHtml(valueText)}</text>
          <text x="32" y="42" text-anchor="middle" font-size="7.5" fill="#64748b">${safePercent}%</text>
        </svg>
        <div class="provider-ring-label">${escapeHtml(label)}</div>
        <div class="text-[10px] text-slate-500">${escapeHtml(subLabel || "")}</div>
      </div>
    `;
  }

  function _findProvider(providerId) {
    const providers = providerStatusCache?.providers;
    if (!Array.isArray(providers)) return null;
    return providers.find((item) => item && item.id === providerId) || null;
  }

  function _computeFallbackSelection(primaryProvider) {
    const providers = Array.isArray(providerStatusCache?.providers)
      ? providerStatusCache.providers
      : [];
    const candidate = providers.find((item) => item?.id && item.id !== primaryProvider);
    if (candidate) {
      return {
        fallback_provider: candidate.id,
        fallback_model: candidate.model || "",
      };
    }
    return {
      fallback_provider: primaryProvider === "gemini" ? "mistral" : "gemini",
      fallback_model: "",
    };
  }

  function _providersStatusUrl(projectId = null) {
    if (!projectId) return "/api/providers/status";
    return `/api/providers/status?projectId=${encodeURIComponent(projectId)}`;
  }

  function _providersProbeUrl(projectId = null) {
    if (!projectId) return "/api/providers/probe";
    return `/api/providers/probe?projectId=${encodeURIComponent(projectId)}`;
  }

  function _providersSelectUrl(projectId = null) {
    if (!projectId) return "/api/providers/select";
    return `/api/providers/select?projectId=${encodeURIComponent(projectId)}`;
  }

  async function _saveProviderSelection(payload, projectId = null) {
    const body = {
      provider: payload.provider || providerStatusCache?.selected_provider || "gemini",
      model: payload.model || _findProvider(payload.provider)?.model || providerStatusCache?.selected_model || "",
      fallback_provider: payload.fallback_provider || providerStatusCache?.fallback_provider || "mistral",
      fallback_model: payload.fallback_model || _findProvider(payload.fallback_provider || "")?.model || providerStatusCache?.fallback_model || "",
      mode: payload.mode || providerStatusCache?.mode || "auto",
    };
    const updated = await apiSend(_providersSelectUrl(projectId), "POST", body);
    providerStatusCache = updated;
    renderProviderSelector(updated);
  }

  async function _selectProvider(providerId) {
    const provider = _findProvider(providerId);
    if (!provider) return;
    const mode = providerStatusCache?.mode || "auto";
    const fallback = _computeFallbackSelection(providerId);
    await _saveProviderSelection({
      provider: providerId,
      model: provider.model || "",
      fallback_provider: mode === "auto" ? fallback.fallback_provider : (providerStatusCache?.fallback_provider || fallback.fallback_provider),
      fallback_model: mode === "auto" ? fallback.fallback_model : (providerStatusCache?.fallback_model || fallback.fallback_model),
      mode,
    }, currentProject?.id || null);
  }

  async function _setProviderMode(mode) {
    if (!providerStatusCache) return;
    const selectedProvider = providerStatusCache.selected_provider || "gemini";
    const selectedModel = providerStatusCache.selected_model || (_findProvider(selectedProvider)?.model || "");
    const fallback = _computeFallbackSelection(selectedProvider);
    await _saveProviderSelection({
      provider: selectedProvider,
      model: selectedModel,
      fallback_provider: mode === "auto" ? fallback.fallback_provider : (providerStatusCache.fallback_provider || fallback.fallback_provider),
      fallback_model: mode === "auto" ? fallback.fallback_model : (providerStatusCache.fallback_model || fallback.fallback_model),
      mode,
    }, currentProject?.id || null);
  }

  function renderProviderSelector(payload) {
    const container = $("provider-cards");
    if (!container) return;

    const providers = Array.isArray(payload?.providers) ? payload.providers : [];
    if (!providers.length) {
      container.innerHTML = '<div class="text-xs text-slate-500">No hay providers disponibles.</div>';
      return;
    }

    const selected = String(payload?.selected_provider || "");
    const mode = String(payload?.mode || "auto");
    const fallbackText = mode === "auto"
      ? `${payload?.fallback_provider || "-"} (${payload?.fallback_model || "-"})`
      : "Desactivado (modo fijo)";
    if ($("provider-fallback-label")) {
      $("provider-fallback-label").textContent = `Fallback: ${fallbackText}`;
    }

    if ($("provider-mode-fixed")) $("provider-mode-fixed").checked = mode === "fixed";
    if ($("provider-mode-auto")) $("provider-mode-auto").checked = mode !== "fixed";

    container.innerHTML = providers.map((provider) => {
      const health = _providerHealthMeta(provider);
      const configured = !!provider.configured;
      const isSelected = provider.id === selected;
      const probeStatus = String(provider?.probe?.status ?? provider?.last_probe_status ?? "UNVERIFIED").toUpperCase();
      const blocked = probeStatus === "EXHAUSTED" || probeStatus === "AUTH_ERROR";

      const rlRemaining = Number(provider?.rate_limit?.remaining ?? 0);
      const rlLimit = Number(provider?.rate_limit?.limit ?? 0);
      const rlReset = Number(provider?.rate_limit?.reset_seconds ?? 0);
      const rlPercent = rlLimit > 0 ? Math.round((Math.max(0, rlRemaining) / rlLimit) * 100) : 0;
      const rlText = rlLimit > 0 ? `${Math.max(0, rlRemaining)}/${rlLimit}` : "N/D";
      const rlSub = rlReset > 0 ? `Reset: ${rlReset}s` : "Sin espera";

      const quotaRemaining = provider?.quota?.remaining ?? provider?.quota?.remaining_tokens;
      const quotaLimit = provider?.quota?.limit ?? provider?.quota?.limit_tokens;
      const hasQuota = Number.isFinite(quotaRemaining) && Number.isFinite(quotaLimit) && quotaLimit > 0;
      const quotaPercent = hasQuota ? Math.round((Math.max(0, quotaRemaining) / quotaLimit) * 100) : 0;
      const quotaText = hasQuota ? `${quotaRemaining}/${quotaLimit}` : "No disp.";
      const quotaSub = hasQuota ? (provider?.quota?.period || "month") : "Estimacion";

      const warningParts = [];
      if (provider?.probe?.detail || provider?.last_probe_detail) {
        warningParts.push(`Probe: ${escapeHtml(provider?.probe?.detail || provider?.last_probe_detail)}`);
      }
      if (provider?.stats?.last_error) {
        warningParts.push(`Ultimo error: ${escapeHtml(provider.stats.last_error)}`);
      }
      const warning = warningParts.length
        ? `<div class="mt-2 text-[11px] text-slate-600">${warningParts.join("<br/>")}</div>`
        : "";

      return `
        <div class="border rounded-xl p-3 bg-white ${isSelected ? "provider-card-selected" : "border-slate-200"}">
          <div class="flex items-start justify-between gap-2">
            <div>
              <div class="text-sm font-semibold text-slate-800">${escapeHtml(provider.display_name || provider.id)}</div>
              <div class="text-xs text-slate-500">${escapeHtml(provider.model || "-")}</div>
            </div>
            <span class="text-[11px] border rounded-full px-2 py-1 ${health.chip}">
              ${health.icon} ${escapeHtml(health.label)}
            </span>
          </div>
          <div class="mt-3 flex items-center justify-center gap-4">
            ${_ringMarkup({
              valueText: rlText,
              percent: rlPercent,
              color: health.ring,
              label: "Rate-limit",
              subLabel: rlSub,
            })}
            ${_ringMarkup({
              valueText: quotaText,
              percent: quotaPercent,
              color: hasQuota ? health.ring : "#94a3b8",
              label: "Cuota",
              subLabel: quotaSub,
            })}
          </div>
          <div class="mt-3 flex items-center justify-between gap-2">
            <div class="text-[11px] text-slate-500">
              ${configured ? "Configurado" : "Sin API key"}
            </div>
            <button
              type="button"
              data-provider-select="${escapeHtml(provider.id)}"
              class="text-xs px-3 py-1.5 rounded ${blocked ? "bg-slate-200 text-slate-400 cursor-not-allowed" : "bg-blue-600 text-white hover:bg-blue-700"}"
              ${blocked ? "disabled" : ""}
            >
              ${isSelected ? "Seleccionado" : "Seleccionar"}
            </button>
          </div>
          ${warning}
        </div>
      `;
    }).join("");

    container.querySelectorAll("button[data-provider-select]").forEach((button) => {
      button.onclick = async () => {
        const targetProvider = button.getAttribute("data-provider-select");
        if (!targetProvider) return;
        try {
          setProviderSelectorError("");
          await _selectProvider(targetProvider);
        } catch (error) {
          setProviderSelectorError(error?.message || "No se pudo guardar la seleccion.");
        }
      };
    });

    if ($("provider-mode-fixed")) {
      $("provider-mode-fixed").onchange = async () => {
        if (!$("provider-mode-fixed").checked) return;
        try {
          setProviderSelectorError("");
          await _setProviderMode("fixed");
        } catch (error) {
          setProviderSelectorError(error?.message || "No se pudo actualizar el modo.");
        }
      };
    }
    if ($("provider-mode-auto")) {
      $("provider-mode-auto").onchange = async () => {
        if (!$("provider-mode-auto").checked) return;
        try {
          setProviderSelectorError("");
          await _setProviderMode("auto");
        } catch (error) {
          setProviderSelectorError(error?.message || "No se pudo actualizar el modo.");
        }
      };
    }
  }

  async function loadProviderStatus(projectId = null) {
    const container = $("provider-cards");
    if (container) {
      container.innerHTML = '<div class="text-xs text-slate-500">Consultando estado de providers...</div>';
    }
    try {
      setProviderSelectorError("");
      const payload = await apiGet(_providersStatusUrl(projectId));
      providerStatusCache = payload;
      renderProviderSelector(payload);
    } catch (error) {
      providerStatusCache = null;
      if (container) {
        container.innerHTML = '<div class="text-xs text-red-600">No se pudo obtener el estado de providers.</div>';
      }
      setProviderSelectorError(error?.message || "No se pudo obtener el estado de providers.");
    }
  }

  async function probeProviderStatus(projectId = null) {
    const container = $("provider-cards");
    if (container) {
      container.innerHTML = '<div class="text-xs text-slate-500">Ejecutando probe real de providers...</div>';
    }
    try {
      setProviderSelectorError("");
      const payload = await apiSend(_providersProbeUrl(projectId), "POST", {});
      providerStatusCache = payload;
      renderProviderSelector(payload);
    } catch (error) {
      setProviderSelectorError(error?.message || "No se pudo ejecutar el probe de providers.");
      await loadProviderStatus(projectId);
    }
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

  // =========================================================================
  // Generation flow (Step 4 progress panel)
  // =========================================================================
  const GEN_POLL_INTERVAL = 1000;   // ms between polls
  const GEN_SUCCESS_STATUSES = ["completed", "completed_with_incidents", "simulated"];
  const GEN_FAIL_STATUSES = [
    "failed",
    "n8n_failed",
    "generation_failed",
    "ai_failed",
    "blocked",
    "timeout",
    "cancel_requested",
  ];
  const PIPELINE_NODES = [
    { id: "format", label: "Formato JSON cargado" },
    { id: "variables", label: "Variables del proyecto" },
    { id: "prompt", label: "Prompt final armado" },
    { id: "ai", label: "IA generando secciones" },
    { id: "clean", label: "Limpieza y validacion" },
    { id: "payload", label: "Payload a GicaTesis" },
    { id: "render", label: "Render DOCX y PDF" },
  ];

  let _genCancelled = false;
  let _genTimerHandle = null;
  let _genElapsed = 0;
  let _lastRenderedTraceCount = 0;
  let _lastTraceState = null;

  function _sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function _formatEventTime(ts) {
    if (!ts) return "--:--";
    const d = new Date(ts);
    if (Number.isNaN(d.getTime())) return "--:--";
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  }

  function _stateIcon(state) {
    if (state === "done") return "\u2705";
    if (state === "running") return "\u23f3";
    if (state === "error") return "\u274c";
    if (state === "warn") return "\u26a0\ufe0f";
    return "\u25cb";
  }

  function _setLiveSummary(text, tone = "neutral") {
    const el = $("gen-live-summary");
    if (!el) return;
    el.textContent = text;
    el.className = "text-sm";
    if (tone === "ok") el.classList.add("text-green-600");
    else if (tone === "error") el.classList.add("text-red-600");
    else if (tone === "warn") el.classList.add("text-amber-700");
    else el.classList.add("text-slate-500");
  }

  function _updateLiveBadge(state = "live") {
    const badge = $("gen-live-badge");
    if (!badge) return;
    badge.className = "inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-semibold border";
    if (state === "ok") {
      badge.classList.add("bg-green-50", "text-green-700", "border-green-200");
      badge.innerHTML = '<span class="w-2 h-2 rounded-full bg-green-500"></span> Completado';
    } else if (state === "error") {
      badge.classList.add("bg-red-50", "text-red-700", "border-red-200");
      badge.innerHTML = '<span class="w-2 h-2 rounded-full bg-red-500"></span> Con error';
    } else if (state === "warn") {
      badge.classList.add("bg-amber-50", "text-amber-700", "border-amber-200");
      badge.innerHTML = '<span class="w-2 h-2 rounded-full bg-amber-500"></span> Revisar';
    } else {
      badge.classList.add("bg-blue-50", "text-blue-700", "border-blue-200");
      badge.innerHTML = '<span class="w-2 h-2 rounded-full bg-blue-500 animate-pulse"></span> En vivo';
    }
  }

  function _renderPipelineNodes(nodeStates) {
    const container = $("gen-pipeline-nodes");
    if (!container) return;

    container.innerHTML = PIPELINE_NODES.map((node, index) => {
      const state = nodeStates[node.id]?.state || "pending";
      const detail = nodeStates[node.id]?.detail || "";
      const toneClass = state === "done"
        ? "border-green-200 bg-green-50 text-green-700"
        : state === "running"
          ? "border-blue-200 bg-blue-50 text-blue-700"
          : state === "warn"
            ? "border-amber-200 bg-amber-50 text-amber-700"
          : state === "error"
            ? "border-red-200 bg-red-50 text-red-700"
            : "border-slate-200 bg-white text-slate-500";
      const flowClass = state === "running"
        ? "trace-node-line"
        : state === "warn"
          ? "bg-amber-200"
        : state === "done"
          ? "bg-green-200"
        : state === "error"
          ? "bg-red-200"
            : "bg-slate-200";

      return `
        <div class="flex gap-2">
          <div class="flex flex-col items-center pt-1">
            <span class="w-5 h-5 rounded-full text-[11px] flex items-center justify-center border ${toneClass}">
              ${_stateIcon(state)}
            </span>
            ${index < PIPELINE_NODES.length - 1 ? `<span class="w-[2px] h-8 rounded ${flowClass}"></span>` : ""}
          </div>
          <div class="pb-2">
            <div class="text-xs font-semibold text-slate-700">${escapeHtml(node.label)}</div>
            <div class="text-[11px] text-slate-500">${escapeHtml(detail || "Pendiente")}</div>
          </div>
        </div>
      `;
    }).join("");
  }

  function _renderDocBlocks(state) {
    const container = $("gen-doc-blocks");
    if (!container) return;

    const sectionItems = state.sections.paths.slice(0, 6).map((path, idx) => ({
      label: path || `Seccion ${idx + 1}`,
      status: idx + 1 < state.sections.current ? "done" : "running",
    }));
    const baseItems = [
      { label: "Caratula", status: state.nodes.prompt.state === "done" ? "done" : "running" },
      { label: "Indice", status: state.nodes.ai.state === "done" ? "done" : "running" },
      { label: "Abreviaturas", status: state.sections.hasAbbreviations ? "done" : "pending" },
      ...sectionItems,
    ];

    if (!baseItems.length) {
      container.innerHTML = '<div class="text-xs text-slate-400">Aun no hay bloques.</div>';
      return;
    }

    container.innerHTML = baseItems.map((item) => {
      const isDone = item.status === "done";
      const isRunning = item.status === "running";
      return `
        <div class="rounded-lg border p-2 ${
          isDone ? "border-green-200 bg-green-50" : "border-slate-200 bg-slate-50"
        }">
          <div class="flex items-center justify-between gap-2">
            <span class="text-xs font-medium text-slate-700">${escapeHtml(item.label)}</span>
            <span class="text-[11px]">${isDone ? "\u2705" : isRunning ? "\u23f3" : "\u25cb"}</span>
          </div>
          <div class="mt-2 h-6 rounded ${isDone ? "bg-white border border-green-100" : "doc-skeleton"}"></div>
        </div>
      `;
    }).join("");

    const total = state.sections.total;
    const current = state.sections.current;
    const progressText = total > 0
      ? `Secciones ${Math.min(current, total)}/${total}${state.sections.currentPath ? ` (${state.sections.currentPath})` : ""}`
      : "Secciones 0/0";
    if ($("gen-sections-progress")) $("gen-sections-progress").textContent = progressText;
    const width = total > 0 ? Math.min(100, Math.round((Math.min(current, total) / total) * 100)) : 0;
    if ($("gen-sections-bar")) $("gen-sections-bar").style.width = `${width}%`;
  }

  function _renderTimeline(events) {
    const list = $("gen-trace-timeline");
    const empty = $("gen-trace-empty");
    if (!list || !empty) return;
    if (!events.length) {
      list.innerHTML = "";
      empty.classList.remove("hidden");
      return;
    }
    empty.classList.add("hidden");

    // Deduplicate bursts: same stage/provider/message within a 3s window.
    const collapsed = [];
    events.slice(-120).forEach((event) => {
      const stage = String(event.stage || event.step || "");
      const status = String(event.status || event.level || "running");
      const title = String(event.title || event.message || "");
      const provider = String(event.provider || event.meta?.provider || "");
      const sectionPath = String(event.sectionPath || event.meta?.sectionPath || "");
      const key = `${stage}|${status}|${provider}|${sectionPath}|${title.trim().toLowerCase()}`;
      const ts = Number(new Date(event.ts || 0).getTime() || 0);
      const last = collapsed.length ? collapsed[collapsed.length - 1] : null;
      if (last && last._dedupeKey === key) {
        const lastTs = Number(new Date(last.ts || 0).getTime() || 0);
        if (ts > 0 && lastTs > 0 && (ts - lastTs) <= 3000) {
          last._count = Number(last._count || 1) + 1;
          last.ts = event.ts || last.ts;
          return;
        }
      }
      collapsed.push({ ...event, _dedupeKey: key, _count: 1 });
    });

    list.innerHTML = collapsed.slice(-60).map((event) => {
      const status = String(
        event.status
        || (event.level === "error" ? "error" : event.level === "warn" ? "warn" : "running")
      );
      const icon = _stateIcon(status);
      const tone = status === "done"
        ? "border-green-200 bg-green-50"
        : status === "error"
          ? "border-red-200 bg-red-50"
          : status === "warn"
            ? "border-amber-200 bg-amber-50"
            : "border-blue-200 bg-blue-50";

      const preview = event.preview && typeof event.preview === "object" ? event.preview : null;
      const meta = event.meta && typeof event.meta === "object" ? event.meta : null;
      const detail = event.detail || "";
      const title = String(event.title || event.message || event.stage || "Evento");
      const countTag = Number(event._count || 1) > 1
        ? ` <span class="text-[10px] text-slate-500">(x${Number(event._count)})</span>`
        : "";
      const hasExtra = Boolean(detail || preview || meta);
      const detailHtml = hasExtra ? `
        <div class="mt-2 text-[11px] text-slate-600 space-y-2">
          ${detail ? `<div>${escapeHtml(detail)}</div>` : ""}
          ${preview?.prompt ? `<div><strong>Prompt</strong><pre class="mt-1 whitespace-pre-wrap bg-white border border-slate-200 rounded p-2">${escapeHtml(preview.prompt)}</pre></div>` : ""}
          ${preview?.raw ? `<div><strong>IA (crudo)</strong><pre class="mt-1 whitespace-pre-wrap bg-white border border-slate-200 rounded p-2">${escapeHtml(preview.raw)}</pre></div>` : ""}
          ${preview?.clean ? `<div><strong>Limpio</strong><pre class="mt-1 whitespace-pre-wrap bg-white border border-slate-200 rounded p-2">${escapeHtml(preview.clean)}</pre></div>` : ""}
          ${preview?.payload ? `<div><strong>Payload resumido</strong><pre class="mt-1 whitespace-pre-wrap bg-white border border-slate-200 rounded p-2">${escapeHtml(preview.payload)}</pre></div>` : ""}
          ${meta ? `<div><strong>Meta</strong><pre class="mt-1 whitespace-pre-wrap bg-white border border-slate-200 rounded p-2">${escapeHtml(JSON.stringify(meta, null, 2))}</pre></div>` : ""}
        </div>
      ` : "";

      if (!hasExtra) {
        return `
          <div class="rounded-lg border ${tone} p-2">
            <div class="text-xs font-medium text-slate-700">
              ${icon} ${escapeHtml(_formatEventTime(event.ts))} - ${escapeHtml(title)}${countTag}
            </div>
          </div>
        `;
      }

      return `
        <details class="rounded-lg border ${tone} p-2">
          <summary class="cursor-pointer text-xs font-medium text-slate-700">
            ${icon} ${escapeHtml(_formatEventTime(event.ts))} - ${escapeHtml(title)}${countTag}
          </summary>
          ${detailHtml}
        </details>
      `;
    }).join("");
  }

  function _deriveTraceState(events, progress = null, projectStatus = "") {
    const nodes = {
      format: { state: "pending", detail: "Pendiente" },
      variables: { state: "pending", detail: "Pendiente" },
      prompt: { state: "pending", detail: "Pendiente" },
      ai: { state: "pending", detail: "Pendiente" },
      clean: { state: "pending", detail: "Pendiente" },
      payload: { state: "pending", detail: "Pendiente" },
      render: { state: "pending", detail: "Pendiente" },
    };
    const sections = {
      current: 0,
      total: 0,
      currentPath: "",
      paths: [],
      hasAbbreviations: false,
    };
    let fallbackText = "";
    let docxDone = false;
    let pdfDone = false;
    let quotaRetrying = false;

    const applyNode = (nodeId, status, detail) => {
      const node = nodes[nodeId];
      if (!node) return;
      if (status === "error") {
        node.state = "error";
      } else if (status === "warn") {
        if (node.state !== "error") node.state = "warn";
      } else if (status === "done") {
        if (node.state === "pending" || node.state === "running") node.state = "done";
      } else if (status === "running") {
        if (node.state === "pending") node.state = "running";
      }
      if (detail) node.detail = detail;
    };

    events.forEach((event) => {
      const step = String(event.step || event.stage || "");
      const status = String(
        event.status
        || (event.level === "error" ? "error" : event.level === "warn" ? "warn" : "running")
      );
      const title = String(event.title || event.message || event.stage || "");
      const meta = event.meta && typeof event.meta === "object" ? event.meta : {};

      if (step.startsWith("format.")) applyNode("format", status, title);
      if (step === "project.variables.ready") applyNode("variables", status, title);
      if (step === "prompt.render") applyNode("prompt", status, title);
      if (step.startsWith("ai.generate.section") || step.startsWith("ai.provider.")) applyNode("ai", status, title);
      if (step === "ai.validation" || step.startsWith("ai.correction")) applyNode("clean", status, title);
      if (step.startsWith("gicatesis.payload")) applyNode("payload", status, title);

      if (step === "gicatesis.render.docx") {
        applyNode("render", status, title);
        if (status === "done") docxDone = true;
      }
      if (step === "gicatesis.render.pdf") {
        applyNode("render", status, title);
        if (status === "done") pdfDone = true;
      }
      if (docxDone && pdfDone && nodes.render.state !== "error") {
        nodes.render.state = "done";
        nodes.render.detail = "DOCX y PDF listos";
      }

      if (
        step === "ai.provider.fallback"
        || step === "ai.provider.quota"
        || step === "provider_fallback"
      ) {
        fallbackText = `${title}${event.detail ? ` - ${event.detail}` : ""}`;
        if (step === "ai.provider.quota") quotaRetrying = true;
      }

      if (step === "ai.generate.section" || step === "section_start" || step === "section_done") {
        const idx = Number(meta.sectionIndex || event.sectionCurrent || 0);
        const total = Number(meta.sectionTotal || event.sectionTotal || 0);
        const path = String(meta.sectionPath || event.sectionPath || "");
        if (idx > 0) sections.current = Math.max(sections.current, idx);
        if (total > 0) sections.total = Math.max(sections.total, total);
        if (path) {
          sections.currentPath = path;
          if (!sections.paths.includes(path)) sections.paths.push(path);
          if (path.toUpperCase().includes("ABREVIATURAS")) sections.hasAbbreviations = true;
        }
      }

      if (step === "generation.job" && status === "done") {
        applyNode("format", "done", nodes.format.detail || "Completado");
        applyNode("variables", "done", nodes.variables.detail || "Completado");
        applyNode("prompt", "done", nodes.prompt.detail || "Completado");
        applyNode("ai", "done", nodes.ai.detail || "Completado");
        if (nodes.clean.state === "pending" || nodes.clean.state === "running") {
          applyNode("clean", "done", "Validado");
        }
        applyNode("payload", "done", nodes.payload.detail || "Payload enviado");
        applyNode("render", "done", "DOCX y PDF listos");
      }
    });

    if (progress && typeof progress === "object") {
      const pCurrent = Number(progress.current || 0);
      const pTotal = Number(progress.total || 0);
      const pPath = String(progress.currentPath || "");
      if (pCurrent > 0) sections.current = Math.max(sections.current, pCurrent);
      if (pTotal > 0) sections.total = Math.max(sections.total, pTotal);
      if (pPath) {
        sections.currentPath = pPath;
        if (!sections.paths.includes(pPath)) sections.paths.push(pPath);
      }
    }

    if (sections.total > 0 && sections.current >= sections.total && nodes.ai.state !== "error") {
      if (nodes.ai.state === "pending" || nodes.ai.state === "running") {
        nodes.ai.state = "done";
      }
      if (!nodes.ai.detail || nodes.ai.detail === "Pendiente") {
        nodes.ai.detail = "Secciones completadas";
      }
    }

    if (projectStatus && GEN_SUCCESS_STATUSES.includes(projectStatus)) {
      const completedWithIncidents = projectStatus === "completed_with_incidents";
      const markDone = (nodeId, detailText) => {
        if (nodes[nodeId].state === "pending" || nodes[nodeId].state === "running") {
          nodes[nodeId].state = "done";
        }
        if (!nodes[nodeId].detail || nodes[nodeId].detail === "Pendiente") {
          nodes[nodeId].detail = detailText;
        }
      };
      markDone("format", "Formato cargado");
      markDone("variables", "Variables listas");
      markDone("prompt", "Prompt armado");
      markDone("ai", "Generacion completada");
      if (nodes.clean.state !== "warn") markDone("clean", "Validacion completada");
      markDone("payload", "Payload enviado");
      if (nodes.render.state !== "error") {
        nodes.render.state = "done";
        nodes.render.detail = "DOCX y PDF listos";
      }
      if (completedWithIncidents) {
        if (nodes.ai.state === "error") {
          nodes.ai.state = "warn";
        }
        if (nodes.clean.state === "error") {
          nodes.clean.state = "warn";
        }
      }
    }

    return { nodes, sections, fallbackText, quotaRetrying };
  }

  function _resetGenUI() {
    _lastRenderedTraceCount = 0;
    _lastTraceState = null;
    _setLiveSummary("Preparando ejecucion...", "neutral");
    _updateLiveBadge("live");
    _renderPipelineNodes({
      format: { state: "pending", detail: "Pendiente" },
      variables: { state: "pending", detail: "Pendiente" },
      prompt: { state: "pending", detail: "Pendiente" },
      ai: { state: "pending", detail: "Pendiente" },
      clean: { state: "pending", detail: "Pendiente" },
      payload: { state: "pending", detail: "Pendiente" },
      render: { state: "pending", detail: "Pendiente" },
    });
    _renderDocBlocks({
      nodes: {
        prompt: { state: "pending" },
        ai: { state: "pending" },
      },
      sections: {
        current: 0,
        total: 0,
        currentPath: "",
        paths: [],
        hasAbbreviations: false,
      },
    });
    _renderTimeline([]);
    if ($("gen-pipeline-fallback")) {
      $("gen-pipeline-fallback").classList.add("hidden");
      $("gen-pipeline-fallback").textContent = "";
    }
    if ($("gen-timer")) $("gen-timer").classList.add("hidden");
    if ($("gen-timer-value")) $("gen-timer-value").textContent = "0s";
    if ($("gen-error")) { $("gen-error").classList.add("hidden"); $("gen-error").textContent = ""; }
    if ($("gen-success")) $("gen-success").classList.add("hidden");
    if ($("btn-gen-retry")) $("btn-gen-retry").classList.add("hidden");
    if ($("btn-gen-downloads")) $("btn-gen-downloads").classList.add("hidden");
    if ($("btn-gen-cancel")) $("btn-gen-cancel").classList.remove("hidden");
  }

  function _showGenError(msg) {
    const el = $("gen-error");
    if (el) { el.textContent = msg; el.classList.remove("hidden"); }
    if ($("btn-gen-retry")) $("btn-gen-retry").classList.remove("hidden");
    if ($("btn-gen-cancel")) $("btn-gen-cancel").classList.add("hidden");
    _updateLiveBadge("error");
    _setLiveSummary(msg, "error");
  }

  function _startGenTimer() {
    _genElapsed = 0;
    if ($("gen-timer")) $("gen-timer").classList.remove("hidden");
    _genTimerHandle = setInterval(() => {
      _genElapsed++;
      if ($("gen-timer-value")) $("gen-timer-value").textContent = `${_genElapsed}s`;
    }, 1000);
  }

  function _stopGenTimer() {
    if (_genTimerHandle) { clearInterval(_genTimerHandle); _genTimerHandle = null; }
  }

  async function _renderLiveTrace(projectId) {
    let projectSnapshot = null;
    try {
      projectSnapshot = await apiGet(`/api/projects/${encodeURIComponent(projectId)}`);
    } catch (_) {
      return null;
    }

    const events = Array.isArray(projectSnapshot?.events)
      ? projectSnapshot.events
      : Array.isArray(projectSnapshot?.trace)
        ? projectSnapshot.trace
        : [];
    _lastRenderedTraceCount = events.length;
    const state = _deriveTraceState(
      events,
      projectSnapshot?.progress || null,
      String(projectSnapshot?.status || ""),
    );
    _lastTraceState = state;
    _renderPipelineNodes(state.nodes);
    _renderDocBlocks(state);
    _renderTimeline(events);

    if (state.fallbackText && $("gen-pipeline-fallback")) {
      $("gen-pipeline-fallback").classList.remove("hidden");
      $("gen-pipeline-fallback").textContent = state.fallbackText;
    } else if ($("gen-pipeline-fallback")) {
      $("gen-pipeline-fallback").classList.add("hidden");
      $("gen-pipeline-fallback").textContent = "";
    }
    return projectSnapshot;
  }

  function _buildArtifacts(project) {
    const runId = project.run_id || "";
    const artifacts = Array.isArray(project.artifacts) ? project.artifacts : [];
    const artifactDocx = artifacts.find((x) => x.type === "docx")?.downloadUrl;
    const artifactPdf = artifacts.find((x) => x.type === "pdf")?.downloadUrl;
    const hasLocalOutput = !!project.output_file;
    const hasLocalPdf = !!project.pdf_file;
    const fallbackDocx = hasLocalOutput
      ? `/api/download/${encodeURIComponent(project.id)}`
      : `/api/sim/download/docx?projectId=${encodeURIComponent(project.id)}${runId ? `&runId=${encodeURIComponent(runId)}` : ""}`;
    const fallbackPdf = hasLocalPdf
      ? `/api/download/${encodeURIComponent(project.id)}/pdf`
      : `/api/sim/download/pdf?projectId=${encodeURIComponent(project.id)}${runId ? `&runId=${encodeURIComponent(runId)}` : ""}`;
    return {
      projectId: project.id,
      runId,
      artifacts: [
        { type: "docx", downloadUrl: artifactDocx || fallbackDocx },
        { type: "pdf", downloadUrl: artifactPdf || fallbackPdf },
      ],
    };
  }

  async function _waitForGeneration(projectId) {
    _startGenTimer();
    while (true) {
      if (_genCancelled) {
        _stopGenTimer();
        return;
      }

      const project = await _renderLiveTrace(projectId);
      if (project) currentProject = project;

      if (project && GEN_SUCCESS_STATUSES.includes(project.status)) {
        _stopGenTimer();
        simRunResult = _buildArtifacts(project);
        const warningsCount = Number(project?.warnings_count || 0);
        const withIncidents = project.status === "completed_with_incidents" || warningsCount > 0;
        if (withIncidents) {
          _setLiveSummary(
            `Flujo completado con incidencias en ${_genElapsed}s. Se omitieron pasos opcionales de IA.`,
            "warn",
          );
          _updateLiveBadge("warn");
        } else {
          _setLiveSummary(`Flujo completado en ${_genElapsed}s`, "ok");
          _updateLiveBadge("ok");
        }
        if ($("gen-success")) $("gen-success").classList.remove("hidden");
        if ($("btn-gen-downloads")) $("btn-gen-downloads").classList.remove("hidden");
        if ($("btn-gen-cancel")) $("btn-gen-cancel").classList.add("hidden");
        refreshDashboard().catch(() => { });
        refreshHistory().catch(() => { });
        return;
      }

      if (project && GEN_FAIL_STATUSES.includes(project.status)) {
        _stopGenTimer();
        const errMsg = project.error || `Generacion fallida (${project.status})`;
        _showGenError(errMsg);
        return;
      }

      if (project) {
        if (_lastTraceState?.quotaRetrying) {
          _setLiveSummary("Esperando reintento del proveedor IA por cuota...", "warn");
        } else {
          _setLiveSummary(`Ejecutando flujo... ${_genElapsed}s`, "neutral");
        }
      } else {
        _setLiveSummary(`Sincronizando estado del proyecto... ${_genElapsed}s`, "warn");
      }
      await _sleep(GEN_POLL_INTERVAL);
    }
  }

  async function _upsertProjectDraftFromWizard() {
    const wizard = collectWizardPayload();
    let projectId = currentProject?.id;

    if (!projectId) {
      const draft = await apiSend("/api/projects/draft", "POST", {
        title: wizard.title,
        formatId: selectedFormat.id,
        formatName: selectedFormat.title || selectedFormat.name || selectedFormat.id,
        formatVersion: selectedFormat.version,
        promptId: selectedPrompt.id,
        values: wizard.values,
      });
      projectId = draft?.id || draft?.projectId;
      currentProject = { ...(draft || {}), id: projectId };
    } else {
      const updated = await apiSend(`/api/projects/${encodeURIComponent(projectId)}`, "PUT", {
        title: wizard.title,
        formatId: selectedFormat.id,
        formatName: selectedFormat.title || selectedFormat.name || selectedFormat.id,
        formatVersion: selectedFormat.version,
        promptId: selectedPrompt.id,
        values: wizard.values,
        status: "draft",
      });
      currentProject = { ...(updated || {}), id: projectId };
    }

    if (!projectId) throw new Error("No se pudo obtener projectId.");
    return projectId;
  }

  async function goToProviderStep() {
    if (!selectedFormat || !selectedPrompt || isPreparingGuide) return;

    setStep3Error("");
    const btn = $("btn-step3-next-provider");
    const loader = $("step3-loading");
    if (btn) btn.classList.add("hidden");
    if (loader) loader.classList.remove("hidden");

    try {
      const projectId = await _upsertProjectDraftFromWizard();
      await loadProviderStatus(projectId);
      nextStep(4);
    } catch (error) {
      setStep3Error(error?.message || "No se pudo preparar el proyecto.");
    } finally {
      if (btn) btn.classList.remove("hidden");
      if (loader) loader.classList.add("hidden");
    }
  }

  async function triggerGeneration() {
    if (!selectedFormat || !selectedPrompt || isPreparingGuide) return;

    isPreparingGuide = true;
    _genCancelled = false;
    setStep4Error("");

    // Hide Step 4 button, show Step 4 loading state
    const btn = $("btn-step4-generate");
    const loader = $("step4-loading");
    if (btn) btn.classList.add("hidden");
    if (loader) loader.classList.remove("hidden");

    try {
      const projectId = await _upsertProjectDraftFromWizard();

      // Persist current provider/mode selection in this project.
      if (providerStatusCache) {
        await _saveProviderSelection(
          {
            provider: providerStatusCache.selected_provider || "gemini",
            model: providerStatusCache.selected_model || "",
            fallback_provider: providerStatusCache.fallback_provider || "mistral",
            fallback_model: providerStatusCache.fallback_model || "",
            mode: providerStatusCache.mode || "auto",
          },
          projectId,
        );
      }

      // --- Navigate to Step 5 & reset UI ---
      _resetGenUI();
      nextStep(5);
      _setLiveSummary("Enviando solicitud de generacion...", "neutral");

      let genResult;
      try {
        genResult = await apiSend(
          `/api/projects/${encodeURIComponent(projectId)}/generate`, "POST", {}
        );
      } catch (e) {
        const detail = e?.message || "Error al enviar solicitud";
        _showGenError(detail);
        return;
      }

      if (_genCancelled) return;

      const mode = genResult?.mode || "ai";
      if (mode === "demo") _setLiveSummary("Modo demo activo. Ejecutando generacion local...", "warn");
      else {
        const provider = genResult?.provider || providerStatusCache?.selected_provider || "gemini";
        const model = genResult?.model || providerStatusCache?.selected_model || "-";
        const selectionMode = genResult?.selectionMode || providerStatusCache?.mode || "auto";
        _setLiveSummary(
          `Usando: ${provider} (${model}) - modo ${selectionMode}.`,
          "neutral",
        );
      }
      await _waitForGeneration(projectId);

    } catch (error) {
      _stopGenTimer();
      const message = error?.message || "Error en generacion.";
      if (currentStep < 5) {
        setStep4Error(message);
        if (btn) btn.classList.remove("hidden");
        if (loader) loader.classList.add("hidden");
      } else {
        _showGenError(message);
      }
    } finally {
      isPreparingGuide = false;
      const btn2 = $("btn-step4-generate");
      const loader2 = $("step4-loading");
      if (btn2) btn2.classList.remove("hidden");
      if (loader2) loader2.classList.add("hidden");
    }
  }

  async function cancelGeneration() {
    _genCancelled = true;
    _stopGenTimer();
    if (currentProject?.id) {
      try {
        await apiSend(`/api/projects/${encodeURIComponent(currentProject.id)}/cancel`, "POST", {});
      } catch (_) {
        // ignore cancel API errors: local UI still transitions to cancelled state
      }
    }
    _showGenError("Cancelacion solicitada.");
    _updateLiveBadge("warn");
    _setLiveSummary("Cancelacion solicitada. Puedes reintentar cuando desees.", "warn");
  }

  function retryGeneration() {
    triggerGeneration();
  }

  function goToDownloads() {
    continueToSimDownloads();
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
    nextStep(6);
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
      refreshDashboard().catch(() => { });
      refreshHistory().catch(() => { });
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
      const canDownload = (project.status === "completed" || project.status === "completed_with_incidents") && project.output_file;
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
    input.oninput = () => refreshHistory().catch(() => { });
  }

  return {
    showView,
    nextStep,
    prevStep,
    goToProviderStep,
    triggerGeneration,
    cancelGeneration,
    retryGeneration,
    goToDownloads,
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
