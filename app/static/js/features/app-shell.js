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
import { createFormatCatalogController } from "./app-shell/format-catalog.js";
import {
  getCategoryLabel as resolveCategoryLabel,
  resolveProjectFormat,
  renderWizardContext,
} from "./app-shell/wizard-context.js";
import {
  createWizardPayloadCollector,
  createDraftProjectService,
  createWizardStatePersistence,
} from "./app-shell/wizard-persistence.js";
import { createWizardProjectRehydrator } from "./app-shell/project-rehydration.js";
import {
  createWizardOrchestrator,
  createProviderStepOrchestrator,
} from "./app-shell/wizard-orchestrator.js";
import {
  formatProjectDate as _formatProjectDate,
  projectValues as _projectValues,
  selectedSectionsFingerprint as _selectedSectionsFingerprint,
  promptSnapshotFingerprint as _promptSnapshotFingerprint,
  hasMeaningfulProjectValues as _hasMeaningfulProjectValues,
  effectiveProjectStatus as _effectiveProjectStatus,
  projectTokenTotal as _projectTokenTotal,
  projectBudgetTotal as _projectBudgetTotal,
  portfolioUsageSummary as _portfolioUsageSummary,
  sortProjectsForProduct as _sortProjectsForProduct,
} from "./app-shell/project-helpers.js";
import { createWizardFieldRenderer } from "./app-shell/wizard-fields.js";
import {
  selectionKey,
  normalizeSelectedSections,
} from "./wizard/prompt-package-client.js";
import { flattenSections } from "./wizard/section-selection.js";
import { escapeHtml } from "../shared/dom.js";

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
  let promptLoadRevision = 0;

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
  let formatCatalogController = null;
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

  function _renderPortfolioMetrics(items) {
    const normalizedItems = Array.isArray(items) ? items : [];
    const usageSummary = _portfolioUsageSummary(normalizedItems);
    if ($("stat-total-projects")) $("stat-total-projects").innerText = String(normalizedItems.length);
    if ($("stat-total-tokens")) $("stat-total-tokens").innerText = formatInt(usageSummary.totalTokens);
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

  function _selectionKey(section) {
    return selectionKey(section);
  }

  function _flattenPromptSections(promptPackage = selectedPrompt) {
    return flattenSections(promptPackage);
  }

  function _normalizeSelectedSectionsForPackage(promptPackage = selectedPrompt, selectedSections = selectedChaptersData) {
    return normalizeSelectedSections(selectedSections, promptPackage);
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

  const renderWizardField = createWizardFieldRenderer({
    escapeHtml,
    readInputValue: _readInputValue,
    syncVariableInputs: _syncVariableInputs,
  });

  function _setSelectedSectionsState(sections = [], keys = new Set()) {
    selectedChaptersData = Array.isArray(sections) ? sections : [];
    selectedChapterKeys = keys instanceof Set ? new Set(keys) : new Set(keys || []);
    wizardState.chapters = [...selectedChaptersData];
    wizardStore.setSelectedSections(selectedChaptersData);
  }

  async function _navigateToWizardStep(step, context = {}) {
    currentStep = step;
    wizardStore.setCurrentStep(step);
    if (wizardController) {
      await wizardController.goTo(step, context);
      return;
    }
    updateStepperUI();
    showStep(step);
  }

  const collectWizardPayloadImpl = createWizardPayloadCollector({
    serializeDetails: () => detailsStepController?.serialize?.(),
    getTitleValue: () => $("var_title")?.value?.trim() || "Proyecto Tesis",
    getSelectedPrompt: () => selectedPrompt,
    getSelectedChaptersData: () => selectedChaptersData,
    setSelectedChaptersData: (sections) => {
      selectedChaptersData = Array.isArray(sections) ? sections : [];
    },
    wizardStateRef: () => wizardState,
    wizardStore,
    normalizeSelectedSectionsForPackage: _normalizeSelectedSectionsForPackage,
  });

  const wizardStatePersistence = createWizardStatePersistence({
    apiSend,
    collectWizardPayload: () => collectWizardPayloadImpl(),
    getCurrentProject: () => currentProject,
    setCurrentProject: (project) => {
      currentProject = project;
    },
  });

  const projectHydrator = createWizardProjectRehydrator({
    getPromptsCache: () => promptsCache,
    projectValues: _projectValues,
    wizardStore,
    getElement: $,
    getCurrentPrompt: () => selectedPrompt,
    setCurrentProject: (project) => {
      currentProject = project;
    },
    setSelectedFormat: (format) => {
      selectedFormat = format;
      wizardStore.setFormat(format);
    },
    setSelectedPrompt: (promptPackage) => {
      selectedPrompt = promptPackage;
    },
    setSelectedSectionsState: _setSelectedSectionsState,
    normalizeSelectedSectionsForPackage: _normalizeSelectedSectionsForPackage,
    selectionKey: _selectionKey,
    resolveProjectFormat: (project) => resolveProjectFormat(project, formatsCache),
    syncSelectedFormatCard: () => formatCatalogController?.syncSelectedFormatCard?.(),
    loadPromptsForWizard: () => loadPromptsForWizard(),
    renderDynamicForm,
    renderWizardContext: (project) => _renderWizardContext(project),
    inferProjectStep: _inferProjectStep,
    navigateToStep: _navigateToWizardStep,
    loadProviderStatus,
    getGenerationController: () => generationController,
    persistWizardState: (step, mode) => _persistWizardState(step, mode),
    selectedSectionsFingerprint: _selectedSectionsFingerprint,
    promptSnapshotFingerprint: _promptSnapshotFingerprint,
    getSelectedFormat: () => selectedFormat,
    getSelectedPrompt: () => selectedPrompt,
  });

  const draftProjectService = createDraftProjectService({
    apiSend,
    collectWizardPayload: () => collectWizardPayloadImpl(),
    getCurrentProject: () => currentProject,
    setCurrentProject: (project) => {
      currentProject = project;
    },
    getCurrentStep: () => currentStep,
    getSelectedFormat: () => selectedFormat,
    getSelectedPrompt: () => selectedPrompt,
    hasProjectCoreChanges: (project, wizardPayload) => projectHydrator.hasProjectCoreChanges(project, wizardPayload),
    wizardStore,
  });

  const wizardOrchestrator = createWizardOrchestrator({
    initializeFrontControllers: _initializeFrontControllers,
    setCurrentWizardMode: (mode) => {
      currentWizardMode = mode;
    },
    resetStepper,
    loadFormats: () => formatCatalogController?.loadFormats?.(),
    getWizardNavigationVersion: () => wizardNavigationVersion,
    loadPromptsForWizard: (promptId) => loadPromptsForWizard(promptId),
    rehydrateWizardProject: (project, options) => projectHydrator.rehydrateWizardProject(project, options),
    renderWizardContext: (project) => _renderWizardContext(project),
    loadProviderStatus,
  });

  const providerStepOrchestrator = createProviderStepOrchestrator({
    getSelectedFormat: () => selectedFormat,
    getSelectedPrompt: () => selectedPrompt,
    isPreparingGeneration: () => generationController?.isPreparing?.(),
    isMaestriaMode: () => Boolean(detailsStepController?.isMaestria),
    validateMaestria: () => detailsStepController?.validateMaestria?.() || [],
    setStep3Error,
    getElement: $,
    upsertProjectDraftFromWizard: () => draftProjectService.upsertProjectDraftFromWizard(),
    nextStep,
  });

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
    promptLoadRevision += 1;
    packageSelectionStep?.cancelPendingLoad?.();
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
    return resolveCategoryLabel(rawCategory);
  }

  async function initWizard() {
    const options = arguments[0] && typeof arguments[0] === "object" ? arguments[0] : {};
    return wizardOrchestrator.initWizard(options);
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


  function _syncSelectedFormatCard() {
    return formatCatalogController?.syncSelectedFormatCard?.();
  }


  function _resolveProjectFormat(project) {
    return resolveProjectFormat(project, formatsCache);
  }



  async function _persistWizardState(step, mode = "continue") {
    return wizardStatePersistence.persistWizardState(step, mode);
  }

  function _renderWizardContext(project) {
    return renderWizardContext({
      project,
      currentWizardMode,
      currentStep,
      getElement: $,
      statusBadge: (item) => statusBadge(_effectiveProjectStatus(item)),
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
    if (!confirm("Â¿Eliminar este proyecto? Esta acciÃ³n no se puede deshacer.")) return;
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

  async function refreshProviderStatus() {
    return probeProviderStatus(currentProject?.id || null);
  }


  function _resolveProjectPrompt(project) {
    return projectHydrator.resolveProjectPrompt(project);
  }

  function _populateWizardValues(project) {
    return projectHydrator.populateWizardValues(project);
  }

  function _hasProjectCoreChanges(project, wizardPayload) {
    return projectHydrator.hasProjectCoreChanges(project, wizardPayload);
  }

  async function loadPromptsForWizard() {
    const requestRevision = ++promptLoadRevision;
    try {
      if (!packageSelectionStep) return;
      wizardStore.setFormat(selectedFormat);
      const promptPackage = await packageSelectionStep.loadForFormat(selectedFormat, currentProject);
      if (requestRevision !== promptLoadRevision || !promptPackage) return;
      selectedPrompt = promptPackage;
      if (selectedPrompt?.id) {
        promptsCache = [
          ...promptsCache.filter((item) => String(item?.id || "") !== String(selectedPrompt.id)),
          selectedPrompt,
        ];
      }
      _syncWizardStore();
    } catch (error) {
      if (requestRevision !== promptLoadRevision) return;
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
    return collectWizardPayloadImpl();
  }

  async function _upsertProjectDraftFromWizard() {
    return draftProjectService.upsertProjectDraftFromWizard();
  }

  async function _rehydrateWizardProject(project, options = {}) {
    return projectHydrator.rehydrateWizardProject(project, options);
  }

  async function goToProviderStep() {
    return providerStepOrchestrator.goToProviderStep();
  }

  // ---------------------------------------------------------------------------
  // MaestrÃ­a Excel helpers â€” exposed on TesisAI
  // ---------------------------------------------------------------------------

  /** Trigger download of the blank Excel template. */
  function downloadExcelTemplate() {
    try {
      // Usamos un formulario POST oculto para disparar la descarga nativa del navegador.
      // Esto es mÃ¡s robusto que fetch+blob y evita problemas de 405 si el GET no estÃ¡ habilitado.
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
   * Explicitly save the maestrÃ­a form to the backend.
   * Called by the "Guardar" button in step 3.
   */
  async function saveMaestriaDetails() {
    const projectId = currentProject?.id;
    if (!projectId) {
      // No project yet â€” just sync to store, the upsert will handle it on continue
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
      const saved = await apiSend(`/api/projects/${encodeURIComponent(projectId)}/maestria-details`, "PUT", values);
      const titulo = String(values.titulo || "").trim();
      currentProject = {
        ...(currentProject || {}),
        ...(saved?.project || {}),
        id: projectId,
        title: titulo || saved?.title || currentProject?.title || "",
        maestria_details: values,
      };
      wizardStore.setCurrentProject(currentProject);
      wizardStore.setMaestriaDetails(values);
      if (saved?.project?.values) {
        wizardStore.setProjectValues(saved.project.values);
      }
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

    formatCatalogController = createFormatCatalogController({
      fetchImpl: fetch,
      getElement: $,
      parseError,
      escapeHtml,
      getSelectedFormat: () => selectedFormat,
      setSelectedFormat: (format) => {
        selectedFormat = format;
        wizardStore.setFormat(format);
      },
      getCategoryLabel,
      setFormatsCache: (items) => {
        formatsCache = Array.isArray(items) ? items : [];
      },
      setGicatesisOnline: (value) => {
        gicatesisOnline = Boolean(value);
      },
      onFormatSelected: () => loadPromptsForWizard(),
    });

    packageSelectionStep = createPackageSelectionStep({
      store: wizardStore,
      getGrid: () => $("chapter-selection-grid"),
      getFormatLabel: () => $("step2-format-name-display"),
      getNextButton: () => $("btn-step2-next"),
      getSelectAllButton: () => $("btn-step2-select-all"),
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
      renderField: renderWizardField,
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
      collectWizardPayload,
      hasProjectCoreChanges: _hasProjectCoreChanges,
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
      getScrollContainer: () => $("app-main-scroll"),
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
    refreshProviderStatus,
    cancelGeneration: () => generationController?.cancelGeneration?.(),
    retryGeneration: () => generationController?.retryGeneration?.(),
    restartGeneration: () => generationController?.restartGeneration?.(),
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
    // MaestrÃ­a Excel flow
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


