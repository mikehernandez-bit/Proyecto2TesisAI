import { createWizardStore } from "../state/wizard-store.js";
import { createWizardController } from "./wizard/wizard-controller.js";
import { createFormatStep } from "./wizard/format-step.js";
import { createPackageSelectionStep } from "./wizard/package-selection-step.js";
import { createDetailsStep } from "./wizard/details-step.js";
import { createProviderStep } from "./wizard/provider-step.js";
import { createGenerationStep } from "./wizard/generation-step.js";
import { createBuildStep } from "./wizard/build-step.js";
import { createDownloadStep } from "./wizard/download-step.js";
import { createTraceView } from "./generation/trace-view.js";
import { createGenerationController } from "./generation/generation-controller.js";
import { createGenerationRuntimeState } from "./generation/trace-state.js";
import { createProjectUi } from "./projects/project-ui.js";
import { createDashboardController } from "./dashboard/dashboard-controller.js";
import { createHistoryController } from "./history/history-controller.js";
import { createBudgetController } from "./budget/budget-controller.js";
import { createProviderController } from "./providers/provider-controller.js";
import { createN8nGuideController } from "./n8n/n8n-guide-controller.js";
import { createPromptAdminLegacyController } from "./prompt-admin-legacy/prompt-admin-controller.js";

/**
 * GicaGen frontend SPA.
 *
 * Wizard flow:
 * 1) Select format
 * 2) Select package + sections
 * 3) Fill details
 * 4) Select IA
 * 5) IA generation
 * 6) Construction / render
 * 7) Downloads
 */
export function createTesisAI() {
  const TOTAL_STEPS = 7;

  let currentView = "dashboard";
  let currentStep = 1;

  let selectedFormat = null;
  let selectedPrompt = null;
  let currentProject = null;
  let selectedChapterKeys = new Set();
  let selectedChaptersData = [];
  let wizardState = {
      module: '',
      enfoque: '',
      chapters: []
  };
  let currentWizardMode = "new";
  let gicatesisOnline = true;
  let formatsCache = [];
  let promptsCache = [];
  let wizardNavigationVersion = 0;
  let wizardSessionVersion = 0;

  const $ = (id) => document.getElementById(id);
  const wizardStore = createWizardStore();
  let wizardController = null;
  let packageSelectionStep = null;
  let detailsStepController = null;
  let traceView = null;
  let projectUi = null;
  let dashboardController = null;
  let historyController = null;
  let budgetController = null;
  let providerController = null;
  let generationRuntimeState = null;
  let generationController = null;
  let n8nGuideController = null;
  let promptAdminLegacyController = null;
  const INTL_INT_FORMAT = new Intl.NumberFormat("es-PE");
  const INTL_USD_FORMAT = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 4,
    maximumFractionDigits: 6,
  });
  let USD_TO_PEN_RATE = 3.72;
  const INTL_PEN_FORMAT = new Intl.NumberFormat("es-PE", {
    style: "currency",
    currency: "PEN",
    minimumFractionDigits: 4,
    maximumFractionDigits: 4,
  });

  async function fetchExchangeRate() {
    try {
      const resp = await fetch("/api/exchange-rate");
      if (!resp.ok) return;
      const data = await resp.json();
      if (data.rate && Number(data.rate) > 0) {
        USD_TO_PEN_RATE = Number(data.rate);
      }
    } catch (_) { /* use fallback */ }
  }

  function formatInt(value) {
    const numeric = Number(value || 0);
    if (!Number.isFinite(numeric)) return "0";
    return INTL_INT_FORMAT.format(Math.max(0, Math.round(numeric)));
  }

  function formatUsd(value) {
    const numeric = Number(value || 0);
    if (!Number.isFinite(numeric)) return "USD -";
    return INTL_USD_FORMAT.format(Math.max(0, numeric));
  }

  function formatPen(usdValue) {
    const numeric = Number(usdValue || 0);
    if (!Number.isFinite(numeric)) return "PEN -";
    return INTL_PEN_FORMAT.format(Math.max(0, numeric * USD_TO_PEN_RATE));
  }

  function formatUsdRate(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return "No disponible";
    return `${INTL_USD_FORMAT.format(Math.max(0, numeric))} / 1M tokens`;
  }

  function _parseDate(value) {
    const raw = String(value || "").trim();
    if (!raw) return null;
    const parsed = new Date(raw);
    return Number.isNaN(parsed.getTime()) ? null : parsed;
  }

  function _formatProjectDate(project) {
    return String(project?.updated_at || project?.created_at || "-");
  }

  function _projectValues(project) {
    if (project?.values && typeof project.values === "object") return project.values;
    if (project?.variables && typeof project.variables === "object") return project.variables;
    return {};
  }

  function _hasMeaningfulProjectValues(project) {
    const values = _projectValues(project);
    return Object.entries(values).some(([key, value]) => {
      if (key === "title") return false;
      return String(value ?? "").trim().length > 0;
    });
  }

  function _effectiveProjectStatus(project) {
    const rawStatus = String(project?.status || "").toLowerCase().trim();
    if (rawStatus === "draft" && project?.format_id && project?.prompt_id && _hasMeaningfulProjectValues(project)) {
      return "ready";
    }
    if (rawStatus === "ai_received") return "rendering";
    return rawStatus;
  }

  function _projectStatusPriority(project) {
    const status = _effectiveProjectStatus(project);
    const priorities = {
      generating: 6,
      rendering: 5,
      ready: 4,
      draft: 3,
      render_failed: 3,
      failed: 3,
      blocked: 3,
      cancel_requested: 3,
      completed_with_incidents: 2,
      completed: 2,
      simulated: 2,
    };
    return priorities[status] || 0;
  }

  function _projectTokenTotal(project) {
    const usage = project?.token_usage && typeof project.token_usage === "object"
      ? project.token_usage
      : project?.progress?.tokenUsage || {};
    const total = Number(usage?.total_tokens || 0);
    return Number.isFinite(total) ? Math.max(0, total) : 0;
  }

  function _projectBudgetTotal(project) {
    const cost = project?.generation_cost && typeof project.generation_cost === "object"
      ? project.generation_cost
      : project?.progress?.costUsage || {};
    const total = Number(cost?.total_cost_usd || 0);
    return Number.isFinite(total) ? Math.max(0, total) : 0;
  }

  function _portfolioUsageSummary(items) {
    return (Array.isArray(items) ? items : []).reduce(
      (summary, project) => {
        summary.totalTokens += _projectTokenTotal(project);
        summary.totalBudget += _projectBudgetTotal(project);
        return summary;
      },
      { totalTokens: 0, totalBudget: 0 },
    );
  }

  function _renderPortfolioMetrics(items) {
    const usageSummary = _portfolioUsageSummary(items);
    if ($("stat-total-projects")) $("stat-total-projects").innerText = String(items.length);
    if ($("stat-total-tokens")) $("stat-total-tokens").innerText = formatInt(usageSummary.totalTokens);
  }

  function _sortProjectsForProduct(items) {
    return [...(Array.isArray(items) ? items : [])].sort((left, right) => {
      const leftTs = _parseDate(left?.updated_at || left?.created_at)?.getTime() || 0;
      const rightTs = _parseDate(right?.updated_at || right?.created_at)?.getTime() || 0;
      if (leftTs !== rightTs) return rightTs - leftTs;
      return _projectStatusPriority(right) - _projectStatusPriority(left);
    });
  }

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

  function appModules() {
    return window.TesisAIAppModules || {};
  }

  function _selectionKey(section) {
    const modules = appModules();
    if (typeof modules.selectionKey === "function") {
      return modules.selectionKey(section);
    }
    if (!section) return "";
    if (typeof section === "string") return String(section).trim();
    return String(
      section.section_id
      || section.sectionId
      || section.section_path
      || section.sectionPath
      || section.path
      || ""
    ).trim();
  }

  function _flattenPromptSections(promptPackage = selectedPrompt) {
    const modules = appModules();
    if (typeof modules.flattenSections === "function") {
      return modules.flattenSections(promptPackage);
    }
    return Array.isArray(promptPackage?.sections) ? promptPackage.sections : [];
  }

  function _normalizeSelectedSectionsForPackage(promptPackage = selectedPrompt, selectedSections = selectedChaptersData) {
    const modules = appModules();
    if (typeof modules.normalizeSelectedSections === "function") {
      return modules.normalizeSelectedSections(selectedSections, promptPackage);
    }
    const sections = _flattenPromptSections(promptPackage);
    const selectedKeys = new Set((Array.isArray(selectedSections) ? selectedSections : []).map(_selectionKey));
    return sections
      .filter((section) => selectedKeys.has(_selectionKey(section)))
      .map((section) => ({
        section_id: section.section_id || section.sectionId || "",
        section_path: section.section_path || section.sectionPath || section.path || "",
        section_title: section.section_title || section.sectionTitle || section.title || "",
        parent_section_path: section.parent_section_path || section.parentSectionPath || "",
        section_level: Number(section.section_level || section.sectionLevel || 1),
        optional: Boolean(section.optional),
        default_selected: Boolean(section.default_selected ?? section.defaultSelected ?? true),
      }));
  }

  function _selectedSectionItems(promptPackage = selectedPrompt, explicitKeys = selectedChapterKeys) {
    const sections = _flattenPromptSections(promptPackage);
    const keys = explicitKeys instanceof Set ? explicitKeys : new Set();
    return sections.filter((section) => keys.has(_selectionKey(section)));
  }

  function _refreshSelectedSectionsState(promptPackage = selectedPrompt) {
    selectedChaptersData = _normalizeSelectedSectionsForPackage(
      promptPackage,
      _selectedSectionItems(promptPackage, selectedChapterKeys),
    );
    wizardState.chapters = [...selectedChaptersData];
    wizardStore.setSelectedSections(selectedChaptersData);
  }

  function _syncWizardStore() {
    wizardStore.patch({
      currentStep,
      format: selectedFormat,
      promptPackage: selectedPrompt,
      selectedSections: selectedChaptersData,
      projectValues: _projectValues(currentProject),
      currentProject,
    });
  }

  function _syncVariableInputs(variableName, value, originId = "") {
    const safeVariable = typeof CSS !== "undefined" && typeof CSS.escape === "function"
      ? CSS.escape(String(variableName || ""))
      : String(variableName || "").replace(/"/g, '\\"');
    document.querySelectorAll(`[data-variable="${safeVariable}"]`).forEach((input) => {
      if (!input || input.id === originId) return;
      input.value = value;
    });
  }

  function _readInputValue(node) {
    if (!node) return "";
    if ("value" in node) return String(node.value || "");
    return "";
  }

  function showView(viewId, options = {}) {
    const nextOptions = options && typeof options === "object" ? { ...options } : {};
    if (viewId === "wizard" && !nextOptions._navVersion) {
      wizardNavigationVersion += 1;
      nextOptions._navVersion = wizardNavigationVersion;
    }

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
    if (viewId === "wizard") initWizard(nextOptions).catch(console.error);
    if (viewId === "history") refreshHistory().catch(console.error);
  }

  function statusBadge(status) {
    return projectUi?.statusBadge(status) || "";
  }

  function _inferDraftStep(project) {
    return projectUi?.inferDraftStep(project) || 1;
  }

  function _inferProjectStep(project, mode = "continue") {
    return projectUi?.inferProjectStep(project, mode) || 1;
  }

  function _projectPrimaryAction(project) {
    return projectUi?.projectPrimaryAction(project) || { label: "Abrir", mode: "continue", icon: "fa-solid fa-play" };
  }

  function _renderProjectActions(project, variant = "table") {
    return projectUi?.renderProjectActions(project, variant) || "";
  }

  async function refreshDashboard() {
    return dashboardController?.refreshDashboard();
  }

  async function refreshHistory() {
    return historyController?.refreshHistory();
  }

  function wireHistorySearch() {
    return historyController?.wireHistorySearch?.();
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
    wizardSessionVersion += 1;
    currentStep = 1;
    currentWizardMode = "new";
    selectedFormat = null;
    selectedPrompt = null;
    selectedChapterKeys = new Set();
    selectedChaptersData = [];
    wizardState = { module: "", enfoque: "", chapters: [] };
    currentProject = null;
    generationController?.resetState?.();
    n8nGuideController?.reset?.();

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

    wizardStore.reset();
    wizardStore.setCurrentStep(1);
    updateStepperUI();
    showStep(1);
    _renderWizardContext(null);
  }

  function nextStep(step, options = {}) {
    if (wizardController) {
      wizardController.goTo(step, options).catch(console.error);
      return;
    }
    currentStep = step;
    wizardStore.setCurrentStep(step);
    updateStepperUI();
    showStep(step);
    _renderWizardContext(currentProject);

    if (step === 2) {
      loadPromptsForWizard().catch(console.error);
    }

    if (step === 4) {
      loadProviderStatus(currentProject?.id || null, { autoProbe: true }).catch(console.error);
    }
    _persistWizardState(step, String(options?.mode || "continue")).catch(() => { });
  }

  function prevStep(step) {
    if (wizardController) {
      wizardController.goTo(step, { mode: "edit" }).catch(console.error);
      return;
    }
    currentStep = step;
    wizardStore.setCurrentStep(step);
    updateStepperUI();
    showStep(step);
    _renderWizardContext(currentProject);
    _persistWizardState(step, "edit").catch(() => { });
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
    const options = arguments[0] && typeof arguments[0] === "object" ? arguments[0] : {};
    const navVersion = Number(options?._navVersion || 0);
    currentWizardMode = String(options?.mode || "new").toLowerCase();
    resetStepper();
    currentWizardMode = String(options?.mode || "new").toLowerCase();
    await loadFormats();
    if (navVersion && navVersion !== wizardNavigationVersion) return;
    await loadPromptsForWizard(options?.project?.prompt_id || "");
    if (navVersion && navVersion !== wizardNavigationVersion) return;
    if ($("btn-step3-next-provider")) {
      $("btn-step3-next-provider").onclick = (event) => {
        if (event) event.preventDefault();
        goToProviderStep().catch((error) => {
          setStep3Error(error?.message || "No se pudo avanzar a Seleccionar IA.");
        });
      };
    }
    if ($("btn-step4-generate")) {
      $("btn-step4-generate").onclick = (event) => {
        if (event) event.preventDefault();
        generationController?.triggerGeneration?.().catch((error) => {
          setStep4Error(error?.message || "No se pudo iniciar la generaciÃ³n.");
        });
      };
    }
    if ($("btn-provider-refresh")) {
      $("btn-provider-refresh").onclick = () => probeProviderStatus(currentProject?.id || null).catch(console.error);
    }
    document.querySelectorAll("[data-wizard-jump]").forEach((button) => {
      button.onclick = () => goToProjectStep(Number(button.getAttribute("data-wizard-jump") || 1));
    });
    if (navVersion && navVersion !== wizardNavigationVersion) return;
    if (options?.project) {
      await _rehydrateWizardProject(options.project, options);
      return;
    }
    _renderWizardContext(null);
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
    formatsCache = items;

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
        card.dataset.formatId = String(format.id || "");
        card.onclick = () => selectFormat(format, card);

        const docType = format.documentType ? ` (${format.documentType})` : "";
        const universityCode = String(format.university || "generic").toLowerCase();
        const logoUrl = `/api/assets/logos/${universityCode}.png`;

        // When GicaTesis is offline, skip loading remote logos â€” use text fallback.
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
      _syncSelectedFormatCard();
    }

    uniSel.onchange = render;
    catSel.onchange = render;
    await render();
  }

  function selectAllChapters() {
    if (packageSelectionStep) {
      packageSelectionStep.selectAll();
      return;
    }
    const grid = $("chapter-selection-grid");
    if (!grid) return;
    _flattenPromptSections(selectedPrompt).forEach((section) => {
      selectedChapterKeys.add(_selectionKey(section));
    });
    _refreshSelectedSectionsState(selectedPrompt);
    grid.querySelectorAll(".chapter-card").forEach((card) => {
      card.classList.add("border-blue-400", "bg-blue-50/50");
      card.classList.remove("border-slate-100");
      card.querySelector(".check-icon")?.classList.remove("hidden");
    });
    if ($("btn-step2-next")) $("btn-step2-next").disabled = false;
  }

  function saveChapterSelectionAndGoDetails() {
    const promptPackage = selectedPrompt || wizardStore.getState().promptPackage;
    if (!promptPackage) return;

    _refreshSelectedSectionsState(promptPackage);
    if (wizardController) {
      wizardController.goTo(3, { mode: "edit" }).catch(console.error);
      return;
    }
    nextStep(3);
  }



  function selectFormat(formatObj, cardEl) {
    document.querySelectorAll(".format-card").forEach((c) => c.classList.remove("border-blue-500", "bg-blue-50"));
    selectedFormat = formatObj;
    if (cardEl) {
      cardEl.classList.remove("border-gray-100");
      cardEl.classList.add("border-blue-500", "bg-blue-50");
    } else {
      _syncSelectedFormatCard();
    }
    $("btn-step1-next").disabled = false;

    // Â¡TRUCO DE SISTEMAS_HENYER! Forzamos la carga desde aquÃ­ mismo
    loadPromptsForWizard(); 
  }

  function _syncSelectedFormatCard() {
    document.querySelectorAll(".format-card").forEach((card) => {
      const isSelected = String(card.dataset.formatId || "") === String(selectedFormat?.id || "");
      card.classList.remove("border-blue-500", "bg-blue-50");
      if (isSelected) {
        card.classList.add("border-blue-500", "bg-blue-50");
      }
    });
  }



  function selectPrompt(promptObj, cardEl) {
    document.querySelectorAll(".prompt-card").forEach((c) => c.classList.remove("border-blue-500", "ring-2", "ring-blue-200"));
    selectedPrompt = promptObj;
    if (cardEl) {
      cardEl.classList.remove("border-gray-100");
      cardEl.classList.add("border-blue-500", "ring-2", "ring-blue-200");
    } else {
      _syncSelectedPromptCard();
    }
    $("btn-step2-next").disabled = false;
    renderDynamicForm();
  }

  function _syncSelectedPromptCard() {
    document.querySelectorAll(".prompt-card").forEach((card) => {
      const isSelected = String(card.dataset.promptId || "") === String(selectedPrompt?.id || "");
      card.classList.remove("border-blue-500", "ring-2", "ring-blue-200");
      if (isSelected) {
        card.classList.add("border-blue-500", "ring-2", "ring-blue-200");
      }
    });
  }


  function _resolveProjectFormat(project) {
    const formatId = String(project?.format_id || "").trim();
    if (!formatId) return null;
    return formatsCache.find((item) => String(item?.id || "") === formatId)
      || {
        id: formatId,
        title: project?.format_name || formatId,
        name: project?.format_name || formatId,
        version: project?.format_version || "",
      };
  }



  async function _persistWizardState(step, mode = "continue") {
    if (!currentProject?.id) return;
    try {
      const currentWizardState = currentProject?.wizard_state && typeof currentProject.wizard_state === "object"
        ? currentProject.wizard_state
        : {};
      const updated = await apiSend(`/api/projects/${encodeURIComponent(currentProject.id)}`, "PUT", {
        wizardState: {
          currentStep: step,
          lastCompletedStep: Math.max(
            Number(currentWizardState?.last_completed_step || currentWizardState?.lastCompletedStep || 1),
            step,
          ),
          lastOpenMode: mode,
          updatedAt: new Date().toISOString(),
        },
        touchProjectTimestamp: false,
      });
      currentProject = { ...(updated || currentProject), id: currentProject.id };
    } catch (_) {
      // El flujo principal no debe bloquearse si solo falla la persistencia de step.
    }
  }

  function _renderWizardContext(project) {
    const panel = $("wizard-context-panel");
    if (!panel) return;
    if (!project?.id || currentWizardMode === "review") {
      panel.classList.add("hidden");
      return;
    }

    panel.classList.remove("hidden");
    if ($("wizard-context-title")) {
      $("wizard-context-title").textContent = project.title || "Proyecto existente";
    }
    if ($("wizard-context-text")) {
      $("wizard-context-text").textContent = `Proyecto ${project.id} Â· ${project.prompt_name || "Sin prompt"} Â· ${project.format_name || project.format_id || "Sin formato"}. Si modificas pasos previos y guardas, la generaciÃ³n posterior se reiniciarÃ¡ de forma explÃ­cita.`;
    }
    if ($("wizard-context-status")) {
      $("wizard-context-status").innerHTML = statusBadge(_effectiveProjectStatus(project));
    }
    document.querySelectorAll("[data-wizard-jump]").forEach((button) => {
      const buttonStep = Number(button.getAttribute("data-wizard-jump") || 1);
      button.classList.remove("bg-amber-100", "border-amber-400");
      if (buttonStep === currentStep) {
        button.classList.add("bg-amber-100", "border-amber-400");
      }
    });
  }


  async function openProject(projectId, options = {}) {
    wizardNavigationVersion += 1;
    const navVersion = wizardNavigationVersion;
    const project = await apiGet(`/api/projects/${encodeURIComponent(projectId)}`);
    if (navVersion !== wizardNavigationVersion) return;
    const step = Math.max(1, Math.min(7, Number(options?.step || _inferProjectStep(project, options?.mode))));
    showView("wizard", { ...options, project, step, _navVersion: navVersion });
  }

  async function deleteProject(projectId) {
    if (!projectId) return;
    if (!confirm("Ã‚Â¿Eliminar este proyecto? Esta acciÃ³n no se puede deshacer.")) return;
    await apiSend(`/api/projects/${encodeURIComponent(projectId)}`, "DELETE");
    if (currentProject?.id === projectId) {
      currentProject = null;
    }
    await refreshDashboard();
    await refreshHistory();
  }

  function closeBudgetModal() {
    return budgetController?.closeBudgetModal();
  }

  async function openBudgetModal(projectId) {
    return budgetController?.openBudgetModal(projectId);
  }

  async function openSidebarBudget() {
    return budgetController?.openSidebarBudget();
  }

  async function refreshBudgetPricing() {
    return budgetController?.refreshBudgetPricing();
  }

  function calculateBudgetEstimate() {
    return budgetController?.calculateBudgetEstimate();
  }

  function goToProjectStep(step) {
    const targetStep = Math.max(1, Math.min(4, Number(step || 1)));
    nextStep(targetStep, { mode: "edit" });
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

  async function _saveProviderSelection(payload, projectId = null) {
    return providerController?.saveProviderSelection(payload, projectId);
  }

  async function loadProviderStatus(projectId = null, options = {}) {
    return providerController?.loadProviderStatus(projectId, options);
  }

  async function probeProviderStatus(projectId = null, options = {}) {
    return providerController?.probeProviderStatus(projectId, options);
  }

  const WIZARD_FIELD_HELP = {
    variable_independiente: "Dato que orienta a la IA sobre la causa, intervención o propuesta principal del estudio.",
    variable_dependiente: "Dato que describe el efecto, resultado o indicador que la sección debe desarrollar.",
    variable_contextual: "Contexto institucional, geográfico o poblacional que delimita el alcance de la redacción.",
    objetivo_general: "Objetivo principal del proyecto que la IA utilizará como eje de la sección.",
    objetivo_especifico: "Objetivo concreto que ayuda a detallar la intención de la sección.",
    poblacion: "Define a quiénes o qué universo aborda el proyecto.",
    muestra: "Delimita el subconjunto o caso específico analizado en el estudio.",
  };

  function _detailFieldId(scopeKey, variableName) {
    const scope = String(scopeKey || "general")
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "");
    const variable = String(variableName || "campo")
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "");
    return `var_${scope}_${variable}`;
  }

  function _prettyVariableLabel(variableName) {
    return String(variableName || "")
      .split("_")
      .filter(Boolean)
      .map((chunk) => chunk.charAt(0).toUpperCase() + chunk.slice(1))
      .join(" ");
  }

  function _renderWizardField(target, { scopeKey, variableName, required = true }) {
    const fieldId = _detailFieldId(scopeKey, variableName);
    const isLong = /(diagnostico|problema|resumen|conclusiones|propuestas|objetivo|metodologia|hipotesis|justificacion|antecedentes|bases|marco|descripcion|introduccion|analisis|contrastacion|discusion|resultados)/i.test(variableName);
    const helpText = WIZARD_FIELD_HELP[variableName] || `Dato requerido para enriquecer la secciÃ³n ${_prettyVariableLabel(variableName).toLowerCase()}.`;
    const wrapper = document.createElement("div");
    wrapper.className = "space-y-2";
    wrapper.innerHTML = `
      <div class="flex items-center justify-between gap-3">
        <label for="${fieldId}" class="text-[10px] font-bold uppercase tracking-widest text-slate-600">${escapeHtml(_prettyVariableLabel(variableName))}</label>
        ${required ? '<span class="text-[9px] bg-amber-100 text-amber-700 px-2 py-0.5 rounded font-black uppercase">Obligatorio</span>' : '<span class="text-[9px] bg-slate-100 text-slate-500 px-2 py-0.5 rounded font-black uppercase">Opcional</span>'}
      </div>
      ${isLong
        ? `<textarea id="${fieldId}" data-variable="${escapeHtml(variableName)}" rows="3" class="w-full rounded-2xl border-2 border-slate-200 bg-white px-4 py-3 text-sm outline-none transition focus:border-blue-500 focus:ring-4 focus:ring-blue-500/10" placeholder="Ingresa el contenido requerido..."></textarea>`
        : `<input id="${fieldId}" data-variable="${escapeHtml(variableName)}" type="text" class="w-full rounded-2xl border-2 border-slate-200 bg-white px-4 py-3 text-sm outline-none transition focus:border-blue-500 focus:ring-4 focus:ring-blue-500/10" placeholder="Ingresa el dato requerido...">`
      }
      <p class="text-[11px] leading-relaxed text-slate-400">${escapeHtml(helpText)}</p>
    `;
    target.appendChild(wrapper);
    const input = wrapper.querySelector("[data-variable]");
    if (input) {
      input.addEventListener("input", () => {
        _syncVariableInputs(variableName, _readInputValue(input), fieldId);
      });
    }
  }

  function _resolveProjectPrompt(project) {
    if (project?.prompt_snapshot && typeof project.prompt_snapshot === "object") {
      return project.prompt_snapshot;
    }
    const promptId = String(project?.prompt_id || "").trim();
    if (!promptId) return null;
    return promptsCache.find((item) => String(item?.id || "") === promptId) || null;
  }

  function _populateWizardValues(project) {
    const values = _projectValues(project);
    wizardStore.setProjectValues({
      ...values,
      title: String(project?.title || values.title || values.tema || ""),
    });
    if ($("var_title")) {
      $("var_title").value = String(project?.title || values.title || values.tema || "");
    }
    document.querySelectorAll("#dynamic-form [data-variable]").forEach((input) => {
      const variableName = String(input.getAttribute("data-variable") || "").trim();
      if (!variableName) return;
      input.value = String(values?.[variableName] ?? "");
    });
  }

  function _hasProjectCoreChanges(project, wizardPayload) {
    if (!project) return false;
    const currentValues = _projectValues(project);
    const nextValues = wizardPayload?.values || {};
    const currentKeys = Array.from(new Set([...Object.keys(currentValues), ...Object.keys(nextValues)])).sort();
    const valuesChanged = currentKeys.some((key) => String(currentValues?.[key] ?? "") !== String(nextValues?.[key] ?? ""));
    const currentSelected = project?.selected_sections || [];
    const nextSelected = wizardPayload?.selectedSections || [];
    return (
      String(project?.format_id || "") !== String(selectedFormat?.id || "")
      || String(project?.prompt_id || "") !== String(selectedPrompt?.id || "")
      || String(project?.title || "") !== String(wizardPayload?.title || "")
      || valuesChanged
      || _selectedSectionsFingerprint(currentSelected) !== _selectedSectionsFingerprint(nextSelected)
    );
  }

  async function loadPromptsForWizard() {
    try {
      if (!packageSelectionStep) return;
      wizardStore.setFormat(selectedFormat);
      const promptPackage = await packageSelectionStep.loadForFormat(selectedFormat, currentProject);
      selectedPrompt = promptPackage;
      if (selectedPrompt?.id) {
        promptsCache = [
          ...promptsCache.filter((item) => String(item?.id || "") !== String(selectedPrompt.id)),
          selectedPrompt,
        ];
      }
      _syncWizardStore();
    } catch (error) {
      console.error("Error en loadPromptsForWizard:", error);
      const grid = $("chapter-selection-grid");
      if (grid) {
        grid.innerHTML = '<div class="col-span-full p-5 bg-red-50 border border-red-200 rounded-2xl text-red-600 text-sm font-bold">Error al cargar el paquete institucional.</div>';
      }
    }
  }

  function renderChapterSelection(chapters) {
    packageSelectionStep?.render(Array.isArray(chapters) && chapters.length ? { ...selectedPrompt, sections: chapters } : selectedPrompt);
  }

  function renderDynamicForm() {
    detailsStepController?.render();
  }

  function collectWizardPayload() {
    const serializedDetails = detailsStepController?.serialize?.() || { title: $("var_title")?.value?.trim() || "Proyecto Tesis", values: {} };
    const values = { ...(serializedDetails.values || {}) };
    const title = String(serializedDetails.title || "Proyecto Tesis").trim() || "Proyecto Tesis";
    values.title = title;
    if (!String(values.tema || "").trim()) {
      values.tema = title;
    }

    const selectedSections = _normalizeSelectedSectionsForPackage(selectedPrompt, selectedChaptersData);
    selectedChaptersData = selectedSections;
    wizardState.chapters = [...selectedSections];
    wizardStore.setProjectValues(values);
    wizardStore.setSelectedSections(selectedSections);

    return {
      title,
      values,
      selectedSections,
      promptSnapshot: selectedPrompt,
    };
  }

  async function _upsertProjectDraftFromWizard() {
    const wizard = collectWizardPayload();
    let projectId = currentProject?.id;
    const resetGeneratedState = _hasProjectCoreChanges(currentProject, wizard);
    const wizardStatePayload = {
      currentStep: currentStep,
      lastCompletedStep: Math.max(Number(currentProject?.wizard_state?.last_completed_step || 1), currentStep),
      lastOpenMode: currentProject?.id ? "edit" : "new",
      updatedAt: new Date().toISOString(),
    };

    const payload = {
      title: wizard.title,
      formatId: selectedFormat.id,
      formatName: selectedFormat.title || selectedFormat.name || selectedFormat.id,
      formatVersion: selectedFormat.version,
      promptId: selectedPrompt.id,
      values: wizard.values,
      promptSnapshot: wizard.promptSnapshot,
      selectedSections: wizard.selectedSections,
      wizardState: wizardStatePayload,
    };

    if (!projectId) {
      const draft = await apiSend("/api/projects/draft", "POST", payload);
      projectId = draft?.id || draft?.projectId;
      currentProject = { ...(draft || {}), id: projectId };
      wizardStore.setCurrentProject(currentProject);
    } else {
      const updated = await apiSend(`/api/projects/${encodeURIComponent(projectId)}`, "PUT", {
        ...payload,
        status: "draft",
        resetGeneratedState,
      });
      currentProject = { ...(updated || {}), id: projectId };
      wizardStore.setCurrentProject(currentProject);
    }

    if (!projectId) throw new Error("No se pudo obtener projectId.");
    return projectId;
  }

  async function _rehydrateWizardProject(project, options = {}) {
    currentProject = project;
    wizardStore.setCurrentProject(currentProject);
    selectedFormat = _resolveProjectFormat(project);
    wizardStore.setFormat(selectedFormat);
    if (selectedFormat) {
      _syncSelectedFormatCard();
      if ($("btn-step1-next")) $("btn-step1-next").disabled = false;
      await loadPromptsForWizard();
    }

    selectedPrompt = _resolveProjectPrompt(project) || selectedPrompt;
    wizardStore.setPromptPackage(selectedPrompt);
    if (selectedPrompt) {
      selectedChaptersData = _normalizeSelectedSectionsForPackage(
        selectedPrompt,
        project?.selected_sections || selectedPrompt?.selected_sections || [],
      );
      selectedChapterKeys = new Set(selectedChaptersData.map(_selectionKey));
      wizardState.chapters = [...selectedChaptersData];
      wizardStore.setSelectedSections(selectedChaptersData);
      renderChapterSelection(_flattenPromptSections(selectedPrompt));
      renderDynamicForm();
      _populateWizardValues(project);
      if ($("btn-step2-next")) $("btn-step2-next").disabled = selectedChapterKeys.size === 0;
    } else {
      renderDynamicForm();
    }

    _renderWizardContext(project);

    const targetStep = Math.max(1, Math.min(7, Number(options?.step || _inferProjectStep(project, options?.mode))));
    currentStep = targetStep;
    wizardStore.setCurrentStep(targetStep);
    if (wizardController) {
      await wizardController.goTo(targetStep, { mode: options?.mode || "continue", projectId: project.id });
    } else {
      updateStepperUI();
      showStep(targetStep);
    }

    if (targetStep >= 4) {
      await loadProviderStatus(project.id || null);
    }
    if (targetStep >= 5) {
      await generationController?.renderLiveTrace?.(project.id);
    }
    if (targetStep === 7) {
      generationController?.rehydrateDownloads?.(project);
    }
    await _persistWizardState(targetStep, String(options?.mode || "continue"));
  }

  async function goToProviderStep() {
    if (!selectedFormat || !selectedPrompt) {
      setStep3Error("Selecciona formato y paquete antes de continuar.");
      return;
    }
    if (generationController?.isPreparing?.()) {
      setStep3Error("Hay un proceso en curso. Espera unos segundos e intenta de nuevo.");
      return;
    }

    setStep3Error("");
    const btn = $("btn-step3-next-provider");
    const loader = $("step3-loading");
    if (btn) btn.classList.add("hidden");
    if (loader) loader.classList.remove("hidden");

    try {
      await _upsertProjectDraftFromWizard();
      nextStep(4);
    } catch (error) {
      setStep3Error(error?.message || "No se pudo preparar el proyecto.");
    } finally {
      if (btn) btn.classList.remove("hidden");
      if (loader) loader.classList.add("hidden");
    }
  }

  function addVariableToBlock() {
    return false;
  }

  function _initializeFrontControllers() {
    if (wizardController) return;

    projectUi = createProjectUi({
      escapeHtml,
      effectiveProjectStatus: _effectiveProjectStatus,
      hasMeaningfulProjectValues: _hasMeaningfulProjectValues,
    });

    dashboardController = createDashboardController({
      apiGet,
      getElement: $,
      sortProjectsForProduct: _sortProjectsForProduct,
      renderPortfolioMetrics: _renderPortfolioMetrics,
      effectiveProjectStatus: _effectiveProjectStatus,
      formatProjectDate: _formatProjectDate,
      escapeHtml,
      projectUi,
    });

    historyController = createHistoryController({
      apiGet,
      getElement: $,
      sortProjectsForProduct: _sortProjectsForProduct,
      renderPortfolioMetrics: _renderPortfolioMetrics,
      effectiveProjectStatus: _effectiveProjectStatus,
      formatProjectDate: _formatProjectDate,
      escapeHtml,
      projectUi,
    });

    budgetController = createBudgetController({
      apiGet,
      getElement: $,
      fetchExchangeRate,
      sortProjectsForProduct: _sortProjectsForProduct,
      effectiveProjectStatus: _effectiveProjectStatus,
      projectTokenTotal: _projectTokenTotal,
      formatInt,
      formatUsd,
      formatPen,
      formatUsdRate,
      formatProjectDate: _formatProjectDate,
      getUsdToPenRate: () => USD_TO_PEN_RATE,
      escapeHtml,
      getCurrentProjectId: () => currentProject?.id || "",
    });

    providerController = createProviderController({
      apiGet,
      apiSend,
      getElement: $,
      escapeHtml,
      wizardStore,
      getCurrentProjectId: () => currentProject?.id || "",
    });

    packageSelectionStep = createPackageSelectionStep({
      store: wizardStore,
      getGrid: () => $("chapter-selection-grid"),
      getFormatLabel: () => $("step2-format-name-display"),
      getNextButton: () => $("btn-step2-next"),
      onPromptPackageResolved: (promptPackage) => {
        selectedPrompt = promptPackage;
        wizardStore.setPromptPackage(promptPackage);
      },
      onSelectionChanged: (sections, keys) => {
        selectedChaptersData = Array.isArray(sections) ? sections : [];
        selectedChapterKeys = new Set(keys || []);
        wizardState.chapters = [...selectedChaptersData];
        wizardStore.setSelectedSections(selectedChaptersData);
      },
    });

    detailsStepController = createDetailsStep({
      store: wizardStore,
      getContainer: () => $("dynamic-form"),
      escapeHtml,
      renderField: (target, options) => _renderWizardField(target, options),
      readInputValue: _readInputValue,
      syncVariableInputs: _syncVariableInputs,
    });

    generationRuntimeState = createGenerationRuntimeState();

    traceView = createTraceView({
      getElement: $,
      escapeHtml,
      formatInt,
      formatUsd,
      runtimeState: generationRuntimeState,
    });

    generationController = createGenerationController({
      apiGet,
      apiSend,
      getElement: $,
      wizardStore,
      runtimeState: generationRuntimeState,
      traceView,
      getSelectedFormat: () => selectedFormat,
      getSelectedPrompt: () => selectedPrompt,
      getCurrentProject: () => currentProject,
      setCurrentProject: (project) => {
        currentProject = project;
      },
      getCurrentStep: () => currentStep,
      getCurrentWizardMode: () => currentWizardMode,
      getWizardSessionVersion: () => wizardSessionVersion,
      nextStep,
      setStep4Error,
      upsertProjectDraftFromWizard: _upsertProjectDraftFromWizard,
      getProviderStatus: () => providerController?.getStatusCache?.() || null,
      saveProviderSelection: (payload, projectId) => _saveProviderSelection(payload, projectId),
      refreshDashboard,
      refreshHistory,
    });

    n8nGuideController = createN8nGuideController({
      apiSend,
      getElement: $,
      escapeHtml,
      toPrettyJson,
      copyText,
      downloadText,
      getCurrentProject: () => currentProject,
      refreshDashboard,
      refreshHistory,
      onSimulationOutput: (result) => generationController?.setSimulationOutput?.(result),
    });

    promptAdminLegacyController = createPromptAdminLegacyController({
      apiGet,
      apiSend,
      getElement: $,
      escapeHtml,
      wizardStateRef: () => wizardState,
      setStep2NextEnabled: (enabled) => {
        if ($("btn-step2-next")) $("btn-step2-next").disabled = !enabled;
      },
      onPromptsChanged: loadPromptsForWizard,
    });

    wizardController = createWizardController({
      totalSteps: TOTAL_STEPS,
      onStepChange: async (step, context = {}) => {
        currentStep = step;
        wizardStore.setCurrentStep(step);
        _renderWizardContext(currentProject);
        if (step === 2) {
          await loadPromptsForWizard();
        } else if (step === 3) {
          renderDynamicForm();
        } else if (step === 4) {
          await loadProviderStatus(currentProject?.id || null, { autoProbe: true });
        } else if ((step === 5 || step === 6) && currentProject?.id) {
          await generationController?.renderLiveTrace?.(currentProject.id);
        }
        _persistWizardState(step, String(context?.mode || "continue")).catch(() => {});
      },
    });

    wizardController.registerStep(1, createFormatStep());
    wizardController.registerStep(2, packageSelectionStep);
    wizardController.registerStep(3, detailsStepController);
    wizardController.registerStep(4, createProviderStep());
    wizardController.registerStep(5, createGenerationStep());
    wizardController.registerStep(6, createBuildStep());
    wizardController.registerStep(7, createDownloadStep());
  }



  return {
    showView,
    nextStep,
    prevStep,
    goToProviderStep,
    triggerGeneration: () => generationController?.triggerGeneration?.(),
    cancelGeneration: () => generationController?.cancelGeneration?.(),
    retryGeneration: () => generationController?.retryGeneration?.(),
    goToDownloads: () => generationController?.goToDownloads?.(),
    runN8nSimulation: () => n8nGuideController?.runSimulation?.(),
    continueToSimDownloads: () => generationController?.continueToDownloads?.(),
    openProject,
    deleteProject,
    openBudgetModal,
    openSidebarBudget,
    closeBudgetModal,
    refreshBudgetPricing,
    calculateBudgetEstimate,
    goToProjectStep,
    openPromptModal: (promptObj) => promptAdminLegacyController?.openPromptModal?.(promptObj),
    closePromptModal: () => promptAdminLegacyController?.closePromptModal?.(),
    savePrompt: () => promptAdminLegacyController?.savePrompt?.(),
    copyN8nPayload: () => n8nGuideController?.copyPayload?.(),
    copyN8nHeaders: () => n8nGuideController?.copyHeaders?.(),
    copyN8nWebhook: () => n8nGuideController?.copyWebhook?.(),
    exportN8nGuide: () => n8nGuideController?.exportGuide?.(),
    _switchDocTab: () => false,
    _filterTimeline: () => false,
    loadPromptsForWizard,
    selectAllChapters,
    saveChapterSelectionAndGoDetails,
    addVariableToBlock,
    async boot() {
      _initializeFrontControllers();
      wireHistorySearch();
      wizardController?.refresh();
      await refreshDashboard();
    },
  };
}



