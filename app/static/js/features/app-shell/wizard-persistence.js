export function createWizardPayloadCollector({
  serializeDetails,
  getTitleValue,
  getSelectedPrompt,
  getSelectedChaptersData,
  setSelectedChaptersData,
  wizardStateRef,
  wizardStore,
  normalizeSelectedSectionsForPackage,
} = {}) {
  return function collectWizardPayload() {
    const fallbackTitle = String(getTitleValue?.() || "Proyecto Tesis").trim() || "Proyecto Tesis";
    const serializedDetails = serializeDetails?.() || { title: fallbackTitle, values: {} };
    const values = { ...(serializedDetails.values || {}) };
    const maestriaDetails = serializedDetails.maestriaDetails || wizardStore?.getState?.().maestriaDetails || null;
    const title = String(serializedDetails.title || fallbackTitle).trim() || fallbackTitle;
    const selectedPrompt = getSelectedPrompt?.() || null;

    values.title = title;
    if (!String(values.tema || "").trim()) {
      values.tema = title;
    }

    const selectedSections = normalizeSelectedSectionsForPackage?.(
      selectedPrompt,
      getSelectedChaptersData?.() || [],
    ) || [];

    setSelectedChaptersData?.(selectedSections);

    const wizardState = wizardStateRef?.();
    if (wizardState && typeof wizardState === "object") {
      wizardState.chapters = [...selectedSections];
    }

    wizardStore?.setProjectValues?.(values);
    wizardStore?.setSelectedSections?.(selectedSections);
    wizardStore?.setMaestriaDetails?.(maestriaDetails);

    return {
      title,
      values,
      maestriaDetails,
      selectedSections,
      promptSnapshot: selectedPrompt,
    };
  };
}

export function createDraftProjectService({
  apiSend,
  collectWizardPayload,
  getCurrentProject,
  setCurrentProject,
  getCurrentStep,
  getSelectedFormat,
  getSelectedPrompt,
  hasProjectCoreChanges,
  wizardStore,
} = {}) {
  return {
    async upsertProjectDraftFromWizard() {
      const currentProject = getCurrentProject?.() || null;
      const selectedFormat = getSelectedFormat?.();
      const selectedPrompt = getSelectedPrompt?.();
      const currentStep = Number(getCurrentStep?.() || 1);
      const wizard = collectWizardPayload?.();
      let projectId = currentProject?.id;
      const resetGeneratedState = hasProjectCoreChanges?.(currentProject, wizard);

      const wizardStatePayload = {
        currentStep,
        lastCompletedStep: Math.max(
          Number(currentProject?.wizard_state?.last_completed_step || 1),
          currentStep,
        ),
        lastOpenMode: currentProject?.id ? "edit" : "new",
        updatedAt: new Date().toISOString(),
      };

      const payload = {
        title: wizard?.title,
        formatId: selectedFormat?.id,
        formatName: selectedFormat?.title || selectedFormat?.name || selectedFormat?.id,
        formatVersion: selectedFormat?.version,
        promptId: selectedPrompt?.id,
        values: wizard?.values,
        maestriaDetails: wizard?.maestriaDetails,
        promptSnapshot: wizard?.promptSnapshot,
        selectedSections: wizard?.selectedSections,
        wizardState: wizardStatePayload,
      };

      let nextProject = null;
      if (!projectId) {
        const draft = await apiSend?.("/api/projects/draft", "POST", payload);
        projectId = draft?.id || draft?.projectId;
        nextProject = { ...(draft || {}), id: projectId };
      } else {
        const updated = await apiSend?.(`/api/projects/${encodeURIComponent(projectId)}`, "PUT", {
          ...payload,
          status: "draft",
          resetGeneratedState,
        });
        nextProject = { ...(updated || {}), id: projectId };
      }

      if (!projectId) {
        throw new Error("No se pudo obtener projectId.");
      }

      setCurrentProject?.(nextProject);
      wizardStore?.setCurrentProject?.(nextProject);
      return projectId;
    },
  };
}

export function createWizardStatePersistence({
  apiSend,
  collectWizardPayload,
  getCurrentProject,
  setCurrentProject,
} = {}) {
  return {
    async persistWizardState(step, mode = "continue") {
      const currentProject = getCurrentProject?.() || null;
      if (!currentProject?.id) return;

      try {
        const wizardData = collectWizardPayload?.();
        const currentWizardState = currentProject?.wizard_state && typeof currentProject.wizard_state === "object"
          ? currentProject.wizard_state
          : {};

        const updated = await apiSend?.(`/api/projects/${encodeURIComponent(currentProject.id)}`, "PUT", {
          selectedSections: wizardData?.selectedSections || [],
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

        setCurrentProject?.({ ...(updated || currentProject), id: currentProject.id });
      } catch (_) {
        // El flujo principal no debe bloquearse si solo falla la persistencia del step.
      }
    },
  };
}
