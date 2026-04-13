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

  function _selectedSectionsFingerprint(sections) {
    const normalized = Array.isArray(sections) ? sections : [];
    const keys = Array.from(new Set(
      normalized
        .map((item) => {
          if (typeof item === "string") return item.trim();
          return String(item?.section_path || item?.sectionPath || item?.path || item?.section_id || item?.sectionId || "").trim();
        })
        .filter(Boolean),
    )).sort();
    return JSON.stringify(keys);
  }

  function _promptSnapshotFingerprint(promptSnapshot) {
    if (!promptSnapshot || typeof promptSnapshot !== "object") return "";
    const sections = Array.isArray(promptSnapshot.sections) ? promptSnapshot.sections : [];
    const normalized = sections.map((section) => ({
      section_id: String(section?.section_id || section?.sectionId || "").trim(),
      section_path: String(section?.section_path || section?.sectionPath || section?.path || "").trim(),
      parent_section_path: String(section?.parent_section_path || section?.parentSectionPath || "").trim(),
      section_level: Number(section?.section_level || section?.sectionLevel || 1),
      section_order: Number(section?.section_order || section?.sectionOrder || 0),
      source_hints: String(section?.source_hints || section?.sourceHints || "").trim(),
      blocks: (Array.isArray(section?.blocks) ? section.blocks : []).map((block) => ({
        block_id: String(block?.block_id || block?.id || "").trim(),
        header: String(block?.header || block?.cabecera || block?.titulo_cabecera || block?.label || "").trim(),
        label: String(block?.label || "").trim(),
        instructions: String(block?.instructions || "").trim(),
        required_variables: Array.from(new Set(
          (Array.isArray(block?.required_variables) ? block.required_variables : [])
            .map((value) => String(value || "").trim())
            .filter(Boolean),
        )).sort(),
      })),
    }));
    return JSON.stringify(normalized);
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
        section_order: Number(section.section_order || section.sectionOrder || 0),
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
    detailsStepController?.reset?.();
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
          setStep4Error(error?.message || "No se pudo iniciar la generación.");
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

    // ¡TRUCO DE SISTEMAS_HENYER! Forzamos la carga desde aquí mismo
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
      const wizardData = collectWizardPayload();
      const currentWizardState = currentProject?.wizard_state && typeof currentProject.wizard_state === "object"
        ? currentProject.wizard_state
        : {};
      const updated = await apiSend(`/api/projects/${encodeURIComponent(currentProject.id)}`, "PUT", {
        selectedSections: wizardData.selectedSections,
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
      $("wizard-context-text").textContent = `Proyecto ${project.id} · ${project.prompt_name || "Sin prompt"} · ${project.format_name || project.format_id || "Sin formato"}. Si modificas pasos previos y guardas, la generación posterior se adelantará de forma explícita.`;
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
    if (!confirm("¿Eliminar este proyecto? Esta acción no se puede deshacer.")) return;
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

  const WIZARD_FIELD_META = {
    tema: {
      label: "Tema del proyecto",
      placeholder: "Ej: Mejora del tiempo de atención de proyectos de investigación.",
      note: "Resume en una frase el tema central que se desarrollará en el documento.",
      example: "Ejemplo: Mejora del proceso de atención de expedientes en una unidad de investigación.",
    },
    escenario_estudio: {
      label: "Escenario de estudio",
      placeholder: "Ej: Unidad de Investigación de la FIIS - UNAC.",
      note: "Indica el lugar, área o institución donde se desarrolla el estudio.",
      example: "Ejemplo: Oficina de proyectos de investigación de una facultad pública.",
    },
    informantes_clave: {
      label: "Informantes clave",
      placeholder: "Ej: Jefe de unidad, asistentes administrativos y docentes investigadores.",
      note: "Señala las personas o perfiles que aportan información relevante al estudio.",
      example: "Ejemplo: Tres administrativos, dos coordinadores y un responsable de investigación.",
    },
    variable_independiente: {
      label: "Variable independiente",
      placeholder: "Ej: Implementación de un sistema web de seguimiento.",
      note: "Describe la intervención, propuesta o factor principal que se evaluará.",
      example: "Ejemplo: Automatización del flujo de recepción y revisión de expedientes.",
    },
    variable_dependiente: {
      label: "Variable dependiente",
      placeholder: "Ej: Tiempo de atención de proyectos de investigación.",
      note: "Indica el resultado, efecto o indicador que se busca explicar o mejorar.",
      example: "Ejemplo: Reducción del tiempo promedio de atención de expedientes.",
    },
    contexto_organizacion: {
      label: "Contexto de la organización",
      placeholder: "Ej: La unidad atiende expedientes de proyectos de pregrado y posgrado durante todo el año.",
      note: "Resume cómo funciona hoy el área, institución o proceso donde ocurre el problema.",
      example: "Ejemplo: La atención depende de revisiones manuales y seguimiento por correo.",
    },
    contexto_estudio: {
      label: "Contexto del estudio",
      placeholder: "Ej: Proceso interno de evaluación y trámite de proyectos en 2024.",
      note: "Explica el entorno específico en el que se analizará la situación problemática.",
      example: "Ejemplo: Gestión administrativa de expedientes en una unidad universitaria.",
    },
    problema_observable: {
      label: "Problema observable",
      placeholder: "Ej: Demoras frecuentes en la atención de proyectos de investigación.",
      note: "Describe el síntoma principal o la situación problemática que se observa en el contexto.",
      example: "Ejemplo: Durante 2024, la atención de expedientes superó en promedio los 20 días hábiles.",
    },
    sustento_local: {
      label: "Sustento local",
      placeholder: "Ej: Registros internos muestran retrasos, expedientes observados y reprocesos.",
      note: "Aporta evidencias concretas del lugar de estudio: datos, reportes, registros o hechos verificables.",
      example: "Ejemplo: 18 de 25 expedientes fueron observados más de una vez durante el último semestre.",
    },
    descripcion_situacion_actual: {
      label: "Situación actual",
      placeholder: "Ej: El proceso sigue un flujo manual con validaciones en varias etapas.",
      note: "Resume cómo funciona hoy el proceso y qué limitaciones presenta.",
      example: "Ejemplo: No existe trazabilidad centralizada ni alertas para el seguimiento de expedientes.",
    },
    propuesta_solucion_preliminar: {
      label: "Propuesta de solución preliminar",
      placeholder: "Ej: Implementar un sistema web para registrar, derivar y monitorear expedientes.",
      note: "Indica la solución o línea de mejora que se perfila frente al problema detectado.",
      example: "Ejemplo: Digitalizar el seguimiento de expedientes y automatizar alertas de revisión.",
    },
    enfoque_de_solucion: {
      label: "Enfoque de solución",
      placeholder: "Ej: Automatización del flujo y trazabilidad del proceso.",
      note: "Explica brevemente cómo se pretende abordar la mejora o intervención.",
      example: "Ejemplo: Centralizar estados, responsables y tiempos de respuesta en una sola plataforma.",
    },
    contexto_internacional: {
      label: "Contexto internacional",
      placeholder: "Ej: Estudios recientes reportan digitalización y trazabilidad en procesos similares.",
      note: "Resume un antecedente o tendencia internacional relacionada con el problema.",
      example: "Ejemplo: Universidades de la región han reducido tiempos de trámite con plataformas de seguimiento.",
    },
    contexto_nacional: {
      label: "Contexto nacional",
      placeholder: "Ej: En el Perú persisten retrasos administrativos en procesos académicos documentados.",
      note: "Describe cómo se presenta el problema o la variable en el contexto nacional.",
      example: "Ejemplo: Informes institucionales muestran demoras recurrentes en procesos universitarios similares.",
    },
    sustento_ingenieril: {
      label: "Sustento ingenieril",
      placeholder: "Ej: Se aplicará Ishikawa y Pareto para identificar causas y priorizar mejoras.",
      note: "Indica la herramienta de ingeniería o análisis que se usará para diagnosticar el problema.",
      example: "Ejemplo: Diagrama de Ishikawa para causas raíz y Pareto para priorizar incidencias.",
    },
    periodo_analisis: {
      label: "Periodo de análisis",
      placeholder: "Ej: Enero a diciembre de 2024.",
      note: "Define el periodo de tiempo que abarca la observación o revisión de la situación problemática.",
      example: "Ejemplo: Se analizarán registros y tiempos de atención del año 2024.",
    },
    objetivo_general: {
      label: "Objetivo general",
      placeholder: "Ej: Determinar cómo la implementación de un sistema web mejora el tiempo de atención.",
      note: "Formula el objetivo principal que orienta el estudio.",
      example: "Ejemplo: Evaluar el impacto de una solución digital en la eficiencia del proceso.",
    },
    objetivo_especifico: {
      label: "Objetivo específico",
      placeholder: "Ej: Identificar las causas principales de retraso en la atención de expedientes.",
      note: "Especifica una meta puntual que ayude a cumplir el objetivo general.",
      example: "Ejemplo: Medir tiempos, detectar cuellos de botella y proponer mejoras concretas.",
    },
    poblacion: {
      label: "Población",
      placeholder: "Ej: Expedientes de proyectos registrados durante 2024.",
      note: "Indica el universo o conjunto total que se analizará.",
      example: "Ejemplo: Todos los expedientes de investigación tramitados en la unidad durante el periodo de estudio.",
    },
    muestra: {
      label: "Muestra",
      placeholder: "Ej: 30 expedientes seleccionados para análisis detallado.",
      note: "Señala el subconjunto específico que se revisará o medirá.",
      example: "Ejemplo: Expedientes observados entre enero y junio con mayor tiempo de atención.",
    },
  };

  function _repairVisibleText(value) {
    const raw = String(value ?? "").trim();
    if (!raw || !/[ÃÂâ]/.test(raw)) return raw;
    try {
      const bytes = Uint8Array.from(raw, (char) => char.charCodeAt(0) & 0xff);
      const decoded = new TextDecoder("utf-8", { fatal: false }).decode(bytes).trim();
      return decoded && !decoded.includes("\uFFFD") ? decoded : raw;
    } catch (_) {
      return raw;
    }
  }

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
    const normalized = String(variableName || "")
      .split("_")
      .filter(Boolean)
      .map((chunk) => chunk.charAt(0).toUpperCase() + chunk.slice(1))
      .join(" ");
    return _repairVisibleText(normalized);
  }

  function _fallbackFieldMeta(variableName, sectionTitle = "") {
    const label = _prettyVariableLabel(variableName);
    const section = _repairVisibleText(sectionTitle);
    return {
      label,
      placeholder: `Ej: ${label}.`,
      note: section
        ? `Completa este dato para contextualizar la sección ${section}.`
        : `Completa este dato con información concreta y verificable.`,
      example: `Ejemplo: ${label} redactado con información real del contexto de estudio.`,
    };
  }

  function _renderWizardField(target, { scopeKey, variableName, required = true, sectionTitle = "", sectionPath = "" }) {
    const fieldId = _detailFieldId(scopeKey, variableName);
    const meta = WIZARD_FIELD_META[variableName] || _fallbackFieldMeta(variableName, sectionTitle || sectionPath);
    const isLong = /(diagnostico|problema|resumen|conclusiones|propuestas|objetivo|metodologia|hipotesis|justificacion|antecedentes|bases|marco|descripcion|introduccion|analisis|contrastacion|discusion|resultados|contexto|sustento)/i.test(variableName);
    const wrapper = document.createElement("div");
    wrapper.className = "space-y-2.5";
    wrapper.innerHTML = `
      <div class="flex items-center justify-between gap-3">
        <label for="${fieldId}" class="text-[10px] font-bold uppercase tracking-widest text-slate-600">${escapeHtml(_repairVisibleText(meta.label || _prettyVariableLabel(variableName)))}</label>
        ${required ? '<span class="text-[9px] bg-amber-100 text-amber-700 px-2 py-0.5 rounded font-black uppercase">Obligatorio</span>' : '<span class="text-[9px] bg-slate-100 text-slate-500 px-2 py-0.5 rounded font-black uppercase">Opcional</span>'}
      </div>
      ${isLong
        ? `<textarea id="${fieldId}" data-variable="${escapeHtml(variableName)}" rows="3" class="w-full rounded-2xl border-2 border-slate-200 bg-white px-4 py-3 text-sm outline-none transition focus:border-blue-500 focus:ring-4 focus:ring-blue-500/10" placeholder="${escapeHtml(_repairVisibleText(meta.placeholder || ""))}"></textarea>`
        : `<input id="${fieldId}" data-variable="${escapeHtml(variableName)}" type="text" class="w-full rounded-2xl border-2 border-slate-200 bg-white px-4 py-3 text-sm outline-none transition focus:border-blue-500 focus:ring-4 focus:ring-blue-500/10" placeholder="${escapeHtml(_repairVisibleText(meta.placeholder || ""))}">`
      }
      <p class="text-[11px] leading-relaxed text-slate-500">${escapeHtml(_repairVisibleText(meta.note || ""))}</p>
      ${meta.example ? `<p class="text-[11px] leading-relaxed text-slate-400"><span class="font-semibold text-slate-500">Ejemplo:</span> ${escapeHtml(_repairVisibleText(String(meta.example || "").replace(/^Ejemplo:\s*/i, "")))}</p>` : ""}
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
      || _promptSnapshotFingerprint(project?.prompt_snapshot) !== _promptSnapshotFingerprint(wizardPayload?.promptSnapshot)
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

    // Validate maestría form if applicable
    if (detailsStepController?.isMaestria) {
      const errors = detailsStepController.validateMaestria?.() || [];
      if (errors.length) {
        setStep3Error(errors[0]);
        return;
      }
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

  // ---------------------------------------------------------------------------
  // Maestría Excel helpers — exposed on TesisAI
  // ---------------------------------------------------------------------------

  /** Trigger download of the blank Excel template. */
  function downloadExcelTemplate() {
    try {
      // Usamos un formulario POST oculto para disparar la descarga nativa del navegador.
      // Esto es más robusto que fetch+blob y evita problemas de 405 si el GET no está habilitado.
      const form = document.createElement("form");
      form.method = "POST";
      form.action = "/api/wizard/details/excel-template";
      document.body.appendChild(form);
      form.submit();
      form.remove();
    } catch (err) {
      setStep3Error("No se pudo iniciar la descarga de la plantilla.");
    }
  }

  /** Called by the file input's onchange. Passes the file to detailsStepController. */
  async function onExcelFileSelected(inputEl) {
    const file = inputEl?.files?.[0];
    if (!file) return;
    // Show filename
    const label = $("excel-filename-label");
    if (label) {
      label.textContent = file.name;
      label.classList.remove("hidden");
    }
    // Reset input so the same file can be re-uploaded
    if (inputEl) inputEl.value = "";
    setStep3Error("");
    try {
      await detailsStepController?.processExcelFile?.(file);
    } catch (err) {
      setStep3Error(err.message || "Error al procesar el Excel.");
    }
  }

  /**
   * Explicitly save the maestría form to the backend.
   * Called by the "Guardar" button in step 3.
   */
  async function saveMaestriaDetails() {
    const projectId = currentProject?.id;
    if (!projectId) {
      // No project yet — just sync to store, the upsert will handle it on continue
      detailsStepController?.serialize?.();
      return;
    }

    const values = detailsStepController?.collectMaestria?.();
    if (!values) return;

    const errors = detailsStepController?.validateMaestria?.() || [];
    if (errors.length) {
      setStep3Error(errors[0]);
      return;
    }

    setStep3Error("");
    const saveBtn = $("btn-step3-save-maestria");
    if (saveBtn) {
      saveBtn.disabled = true;
      saveBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin mr-1.5"></i> Guardando...';
    }
    try {
      await apiSend(`/api/projects/${encodeURIComponent(projectId)}/maestria-details`, "PUT", values);
      // Also update local project state
      const titulo = String(values.titulo || "").trim();
      currentProject = { ...(currentProject || {}), title: titulo || currentProject?.title || "" };
      wizardStore.setCurrentProject(currentProject);
      if (saveBtn) {
        saveBtn.innerHTML = '<i class="fa-solid fa-check mr-1.5 text-green-500"></i> Guardado';
        setTimeout(() => { saveBtn.innerHTML = '<i class="fa-solid fa-floppy-disk mr-1.5"></i> Guardar'; }, 2000);
      }
    } catch (err) {
      setStep3Error(err.message || "No se pudieron guardar los datos.");
    } finally {
      if (saveBtn) saveBtn.disabled = false;
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
    // Maestría Excel flow
    downloadExcelTemplate,
    onExcelFileSelected,
    saveMaestriaDetails,
    validateMaestriaTitle: () => detailsStepController?.validateMaestriaTitle?.(),
    async boot() {
      _initializeFrontControllers();
      wireHistorySearch();
      wizardController?.refresh();
      await refreshDashboard();
    },
  };
}
