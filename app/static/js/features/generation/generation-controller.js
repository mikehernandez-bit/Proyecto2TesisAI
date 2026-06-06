import {
  buildArtifacts,
  GEN_FAIL_STATUSES,
  GEN_MISSING_PROJECT_MAX_POLLS,
  GEN_POLL_INTERVAL,
  GEN_SUCCESS_STATUSES,
} from "./trace-state.js";

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export function createGenerationController({
  apiGet,
  apiSend,
  getElement,
  wizardStore,
  runtimeState,
  traceView,
  getSelectedFormat,
  getSelectedPrompt,
  getCurrentProject,
  setCurrentProject,
  getCurrentStep,
  getCurrentWizardMode,
  getWizardSessionVersion,
  nextStep,
  setStep4Error,
  upsertProjectDraftFromWizard,
  getProviderStatus,
  saveProviderSelection,
  refreshDashboard,
  refreshHistory,
}) {
  function rememberProject(projectSnapshot) {
    setCurrentProject(projectSnapshot || null);
    wizardStore.setCurrentProject(projectSnapshot || null);
    wizardStore.setGenerationTrace(projectSnapshot?.generation_phase || null);
  }

  function setDownloadsFromProject(projectSnapshot) {
    const artifacts = buildArtifacts(projectSnapshot);
    runtimeState.setArtifacts(artifacts);
    return artifacts;
  }

  function setDownloadsPayload(payload) {
    if (!payload) {
      runtimeState.setArtifacts(null);
      return null;
    }
    const artifacts = Array.isArray(payload.artifacts) ? payload.artifacts : [];
    const normalized = {
      projectId: String(payload.projectId || payload.project_id || getCurrentProject()?.id || ""),
      runId: String(payload.runId || payload.run_id || ""),
      artifacts,
    };
    runtimeState.setArtifacts(normalized);
    return normalized;
  }

  function resolveLiveExecutionSummary(projectSnapshot) {
    const project = projectSnapshot && typeof projectSnapshot === "object" ? projectSnapshot : {};
    const generationPhase = project?.generation_phase && typeof project.generation_phase === "object"
      ? project.generation_phase
      : {};
    const sections = Array.isArray(generationPhase.sections) ? generationPhase.sections : [];
    const currentPath = String(
      generationPhase.current_path
      || generationPhase.current_section_path
      || "",
    ).trim();
    const activeSection = sections.find((section) => {
      const sectionPath = String(section?.section_path || section?.path || "").trim();
      return currentPath ? sectionPath === currentPath : Boolean(sectionPath);
    }) || sections[0] || {};
    const selection = project?.ai_selection && typeof project.ai_selection === "object"
      ? project.ai_selection
      : {};
    const provider = String(
      activeSection?.provider
      || generationPhase.provider
      || selection.provider
      || "",
    ).trim();
    const model = String(
      activeSection?.model
      || generationPhase.model
      || selection.model
      || "",
    ).trim();
    const mode = String(selection.mode || "").trim();
    if (!provider && !model) return "";
    const providerLabel = model ? `${provider} (${model})` : provider;
    return `Usando: ${providerLabel}${mode ? ` - modo ${mode}` : ""}. `;
  }

  function syncWizardStepWithProject(projectSnapshot) {
    if (!projectSnapshot || getCurrentStep() < 5) return;

    const projectStatus = String(projectSnapshot.status || "");
    const generationPhase = projectSnapshot?.generation_phase && typeof projectSnapshot.generation_phase === "object"
      ? projectSnapshot.generation_phase
      : {};
    const generationStatus = String(generationPhase.status || "");
    const constructionPhase = projectSnapshot?.construction_phase && typeof projectSnapshot.construction_phase === "object"
      ? projectSnapshot.construction_phase
      : {};
    const constructionStatus = String(constructionPhase.status || "");
    const generationCompleted = ["completed", "done", "ok"].includes(generationStatus.toLowerCase());
    const constructionStarted = ["running", "completed", "error"].includes(constructionStatus.toLowerCase());

    if (GEN_SUCCESS_STATUSES.includes(projectStatus)) {
      setDownloadsFromProject(projectSnapshot);
      if (getCurrentWizardMode() !== "review" && getCurrentStep() < 7) {
        continueToDownloads();
      }
      return;
    }

    if (projectStatus === "render_failed") {
      if (getCurrentStep() < 6) nextStep(6);
      return;
    }

    if (
      getCurrentStep() === 5
      && (generationCompleted || constructionStarted)
    ) {
      nextStep(6);
    }
  }

  async function renderLiveTrace(projectId, options = {}) {
    const sessionVersion = Number(options?.sessionVersion || getWizardSessionVersion());
    let projectSnapshot = null;
    try {
      projectSnapshot = await apiGet(`/api/projects/${encodeURIComponent(projectId)}`);
    } catch (_) {
      return null;
    }

    if (sessionVersion !== getWizardSessionVersion()) {
      return null;
    }

    const events = Array.isArray(projectSnapshot?.events)
      ? projectSnapshot.events
      : Array.isArray(projectSnapshot?.trace)
        ? projectSnapshot.trace
        : [];

    rememberProject(projectSnapshot);
    runtimeState.setLastRenderedTraceCount(events.length);
    traceView.render(projectSnapshot);
    syncWizardStepWithProject(projectSnapshot);
    return projectSnapshot;
  }

  function hideStep4Loading() {
    getElement("btn-step4-generate")?.classList.remove("hidden");
    getElement("step4-loading")?.classList.add("hidden");
  }

  function showStep4Loading() {
    getElement("btn-step4-generate")?.classList.add("hidden");
    getElement("step4-loading")?.classList.remove("hidden");
  }

  async function waitForGeneration(projectId) {
    const trackingSessionVersion = getWizardSessionVersion();
    runtimeState.startTimer((seconds) => {
      traceView.setTimerVisible(true);
      traceView.setTimerSeconds(seconds);
    });

    let missingProjectPolls = 0;
    while (true) {
      if (runtimeState.isCancelled() || trackingSessionVersion !== getWizardSessionVersion()) {
        runtimeState.stopTimer();
        return;
      }

      const project = await renderLiveTrace(projectId, { sessionVersion: trackingSessionVersion });
      if (trackingSessionVersion !== getWizardSessionVersion()) {
        runtimeState.stopTimer();
        return;
      }

      const generationPhase = project?.generation_phase && typeof project.generation_phase === "object"
        ? project.generation_phase
        : null;
      const generationStatus = String(generationPhase?.status || "");
      const constructionPhase = project?.construction_phase && typeof project.construction_phase === "object"
        ? project.construction_phase
        : null;
      const constructionStatus = String(constructionPhase?.status || "");
      const generationCompleted = ["completed", "done", "ok"].includes(generationStatus.toLowerCase());
      const constructionStarted = ["running", "completed", "error"].includes(constructionStatus.toLowerCase());

      if (
        project
        && getCurrentStep() === 5
        && (generationCompleted || constructionStarted)
      ) {
        nextStep(6);
      }

      if (project && GEN_SUCCESS_STATUSES.includes(project.status)) {
        runtimeState.stopTimer();
        setDownloadsFromProject(project);
        const warningsCount = Number(project?.warnings_count || 0);
        const withIncidents = project.status === "completed_with_incidents" || warningsCount > 0;
        if (withIncidents) {
          traceView.setLiveSummary(
            `Flujo completado con incidencias en ${runtimeState.getElapsed()}s. Se omitieron pasos opcionales de IA.`,
            "warn",
          );
          traceView.updateLiveBadge("warn");
        } else {
          traceView.setLiveSummary(`Flujo completado en ${runtimeState.getElapsed()}s`, "ok");
          traceView.updateLiveBadge("ok");
        }
        traceView.showSuccess();
        traceView.hideConstructionRetry();
        getElement("btn-gen-cancel")?.classList.add("hidden");
        if (getCurrentStep() < 7) continueToDownloads();
        refreshDashboard().catch(() => {});
        refreshHistory().catch(() => {});
        return;
      }

      if (project && GEN_FAIL_STATUSES.includes(project.status)) {
        runtimeState.stopTimer();
        const message = project.status === "render_failed"
          ? (project.error || "Render fallido. El contenido IA se conserva; reintenta para ejecutar solo render.")
          : (project.error || `Generacion fallida (${project.status})`);
        if (project.status === "render_failed" && getCurrentStep() < 6) nextStep(6);
        traceView.showError(message);
        traceView.showRetry();
        traceView.updateLiveBadge("error");
        traceView.setLiveSummary(message, "error");
        return;
      }

      if (project) {
        missingProjectPolls = 0;
        traceView.setLiveSummary(
          `${resolveLiveExecutionSummary(project)}Ejecutando flujo... ${runtimeState.getElapsed()}s`,
          "neutral",
        );
      } else {
        missingProjectPolls += 1;
        if (missingProjectPolls >= GEN_MISSING_PROJECT_MAX_POLLS) {
          runtimeState.stopTimer();
          const message = "No se encontro el proyecto durante el seguimiento. Reinicia el backend y vuelve a intentar desde el historial o creando un nuevo borrador.";
          traceView.showError(message);
          traceView.showRetry();
          traceView.updateLiveBadge("error");
          traceView.setLiveSummary(message, "error");
          return;
        }
        traceView.setLiveSummary(`Sincronizando estado del proyecto... ${runtimeState.getElapsed()}s`, "warn");
      }
      await sleep(GEN_POLL_INTERVAL);
    }
  }

  async function triggerGeneration() {
    if (!getSelectedFormat() || !getSelectedPrompt() || runtimeState.isPreparing()) return;

    runtimeState.setPreparing(true);
    runtimeState.setCancelled(false);
    setStep4Error("");
    showStep4Loading();

    try {
      const projectId = await upsertProjectDraftFromWizard();
      const providerStatus = getProviderStatus?.() || null;
      if (providerStatus) {
        await saveProviderSelection?.({
          provider: providerStatus.selected_provider || "gemini",
          model: providerStatus.selected_model || "",
          fallback_provider: providerStatus.fallback_provider || "mistral",
          fallback_model: providerStatus.fallback_model || "",
          mode: providerStatus.mode || "auto",
        }, projectId);
      }

      traceView.reset();
      traceView.hideRetry();
      nextStep(5);
      traceView.setLiveSummary("Enviando solicitud de generacion...", "neutral");

      let generationResult;
      try {
        generationResult = await apiSend(`/api/projects/${encodeURIComponent(projectId)}/generate`, "POST", {});
      } catch (error) {
        const detail = error?.message || "Error al enviar solicitud";
        traceView.showError(detail);
        traceView.showRetry();
        traceView.updateLiveBadge("error");
        traceView.setLiveSummary(detail, "error");
        return;
      }

      if (runtimeState.isCancelled()) return;

      const mode = generationResult?.mode || "ai";
      if (mode === "demo") {
        traceView.setLiveSummary("Modo demo activo. Ejecutando generacion local...", "warn");
      } else if (mode === "render_only") {
        traceView.setLiveSummary(
          "Reintentando solo render con el ai_result guardado. No se volvera a llamar al proveedor IA.",
          "warn",
        );
      } else {
        const provider = generationResult?.provider || providerStatus?.selected_provider || "gemini";
        const model = generationResult?.model || providerStatus?.selected_model || "-";
        const selectionMode = generationResult?.selectionMode || providerStatus?.mode || "auto";
        const savedSections = Number(generationResult?.savedSections || 0);
        const resumeFromSection = Number(generationResult?.resumeFromSection || 1);
        const resumeMode = String(generationResult?.resumeMode || "auto").toLowerCase();
        if (savedSections > 0 && (resumeMode === "auto" || resumeMode === "resume")) {
          traceView.setLiveSummary(
            `Reanudando desde seccion ${resumeFromSection} (se conservaron ${savedSections}). Usando: ${provider} (${model}) - modo ${selectionMode}.`,
            "warn",
          );
        } else {
          traceView.setLiveSummary(`Usando: ${provider} (${model}) - modo ${selectionMode}.`, "neutral");
        }
      }

      await waitForGeneration(projectId);
    } catch (error) {
      runtimeState.stopTimer();
      const message = error?.message || "Error en generacion.";
      if (getCurrentStep() < 5) {
        setStep4Error(message);
      } else {
        traceView.showError(message);
        traceView.showRetry();
        traceView.updateLiveBadge("error");
        traceView.setLiveSummary(message, "error");
      }
    } finally {
      runtimeState.setPreparing(false);
      hideStep4Loading();
    }
  }

  async function cancelGeneration() {
    runtimeState.setCancelled(true);
    runtimeState.stopTimer();
    const project = getCurrentProject();
    if (project?.id) {
      try {
        await apiSend(`/api/projects/${encodeURIComponent(project.id)}/cancel`, "POST", {});
      } catch (_) {
        // Local UI still transitions to cancelled state.
      }
    }
    traceView.showError("Cancelacion solicitada.");
    traceView.showRetry();
    traceView.updateLiveBadge("warn");
    traceView.setLiveSummary("Cancelacion solicitada. Puedes reintentar cuando desees.", "warn");
  }

  function retryGeneration() {
    return triggerGeneration();
  }

  function continueToDownloads() {
    const project = getCurrentProject();
    if (!project?.id) return;

    const output = runtimeState.getArtifacts() || setDownloadsFromProject(project);
    const runId = output?.runId || "";
    const docxUrl = output?.artifacts?.find?.((item) => item.type === "docx")?.downloadUrl
      || `/api/sim/download/docx?projectId=${encodeURIComponent(project.id)}${runId ? `&runId=${encodeURIComponent(runId)}` : ""}`;
    const pdfUrl = output?.artifacts?.find?.((item) => item.type === "pdf")?.downloadUrl
      || `/api/sim/download/pdf?projectId=${encodeURIComponent(project.id)}${runId ? `&runId=${encodeURIComponent(runId)}` : ""}`;

    getElement("sim-project-id") && (getElement("sim-project-id").textContent = project.id);
    getElement("sim-download-docx")?.setAttribute("href", docxUrl);
    getElement("sim-download-pdf")?.setAttribute("href", pdfUrl);
    nextStep(7);
  }

  function goToDownloads() {
    continueToDownloads();
  }

  function resetState() {
    runtimeState.reset();
    traceView.reset();
  }

  function rehydrateDownloads(projectSnapshot) {
    if (!projectSnapshot) return;
    rememberProject(projectSnapshot);
    setDownloadsFromProject(projectSnapshot);
    continueToDownloads();
  }

  return {
    renderLiveTrace,
    triggerGeneration,
    cancelGeneration,
    retryGeneration,
    goToDownloads,
    continueToDownloads,
    resetState,
    rehydrateDownloads,
    setSimulationOutput: setDownloadsPayload,
    isPreparing: () => runtimeState.isPreparing(),
  };
}
