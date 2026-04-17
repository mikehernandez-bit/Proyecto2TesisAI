export function createWizardProjectRehydrator({
  getPromptsCache,
  projectValues,
  wizardStore,
  getElement,
  getCurrentPrompt,
  setCurrentProject,
  setSelectedFormat,
  setSelectedPrompt,
  setSelectedSectionsState,
  normalizeSelectedSectionsForPackage,
  selectionKey,
  resolveProjectFormat,
  syncSelectedFormatCard,
  loadPromptsForWizard,
  renderDynamicForm,
  renderWizardContext,
  inferProjectStep,
  navigateToStep,
  loadProviderStatus,
  getGenerationController,
  persistWizardState,
  selectedSectionsFingerprint,
  promptSnapshotFingerprint,
  getSelectedFormat,
  getSelectedPrompt,
} = {}) {
  function resolveProjectPrompt(project) {
    if (project?.prompt_snapshot && typeof project.prompt_snapshot === "object") {
      return project.prompt_snapshot;
    }

    const promptId = String(project?.prompt_id || "").trim();
    if (!promptId) return null;

    return (Array.isArray(getPromptsCache?.()) ? getPromptsCache() : []).find(
      (item) => String(item?.id || "") === promptId,
    ) || null;
  }

  function populateWizardValues(project) {
    const values = projectValues?.(project) || {};
    wizardStore?.setProjectValues?.({
      ...values,
      title: String(project?.title || values.title || values.tema || ""),
    });
    wizardStore?.setMaestriaDetails?.(project?.maestria_details || null);

    const titleInput = getElement?.("var_title");
    if (titleInput) {
      titleInput.value = String(project?.title || values.title || values.tema || "");
    }

    document.querySelectorAll("#dynamic-form [data-variable]").forEach((input) => {
      const variableName = String(input.getAttribute("data-variable") || "").trim();
      if (!variableName) return;
      input.value = String(values?.[variableName] ?? "");
    });
  }

  function hasProjectCoreChanges(project, wizardPayload) {
    if (!project) return false;

    const currentValues = projectValues?.(project) || {};
    const nextValues = wizardPayload?.values || {};
    const currentMaestria = JSON.stringify(project?.maestria_details || null);
    const nextMaestria = JSON.stringify(wizardPayload?.maestriaDetails || null);
    const currentKeys = Array.from(new Set([
      ...Object.keys(currentValues),
      ...Object.keys(nextValues),
    ])).sort();

    const valuesChanged = currentKeys.some(
      (key) => String(currentValues?.[key] ?? "") !== String(nextValues?.[key] ?? ""),
    );

    return (
      String(project?.format_id || "") !== String(getSelectedFormat?.()?.id || "")
      || String(project?.prompt_id || "") !== String(getSelectedPrompt?.()?.id || "")
      || String(project?.title || "") !== String(wizardPayload?.title || "")
      || valuesChanged
      || currentMaestria !== nextMaestria
      || selectedSectionsFingerprint?.(project?.selected_sections || []) !== selectedSectionsFingerprint?.(wizardPayload?.selectedSections || [])
      || promptSnapshotFingerprint?.(project?.prompt_snapshot) !== promptSnapshotFingerprint?.(wizardPayload?.promptSnapshot)
    );
  }

  async function rehydrateWizardProject(project, options = {}) {
    setCurrentProject?.(project);
    wizardStore?.setCurrentProject?.(project);

    const resolvedFormat = resolveProjectFormat?.(project);
    setSelectedFormat?.(resolvedFormat);

    if (resolvedFormat) {
      syncSelectedFormatCard?.();
      const nextButton = getElement?.("btn-step1-next");
      if (nextButton) nextButton.disabled = false;
      await loadPromptsForWizard?.();
    }

    const resolvedPrompt = resolveProjectPrompt(project) || getCurrentPrompt?.() || null;
    setSelectedPrompt?.(resolvedPrompt);
    wizardStore?.setPromptPackage?.(resolvedPrompt);

    if (resolvedPrompt) {
      const selectedSections = normalizeSelectedSectionsForPackage?.(
        resolvedPrompt,
        project?.selected_sections || resolvedPrompt?.selected_sections || [],
      ) || [];
      const selectedKeys = new Set(selectedSections.map((section) => selectionKey?.(section)));

      setSelectedSectionsState?.(selectedSections, selectedKeys);
      renderDynamicForm?.();
      populateWizardValues(project);

      const stepTwoNextButton = getElement?.("btn-step2-next");
      if (stepTwoNextButton) stepTwoNextButton.disabled = selectedKeys.size === 0;
    } else {
      renderDynamicForm?.();
    }

    const targetStep = Math.max(
      1,
      Math.min(7, Number(options?.step || inferProjectStep?.(project, options?.mode))),
    );

    await navigateToStep?.(targetStep, {
      mode: options?.mode || "continue",
      projectId: project.id,
    });

    renderWizardContext?.(project);

    if (targetStep >= 4) {
      await loadProviderStatus?.(project.id || null);
    }
    if (targetStep >= 5) {
      await getGenerationController?.()?.renderLiveTrace?.(project.id);
    }
    if (targetStep === 7) {
      getGenerationController?.()?.rehydrateDownloads?.(project);
    }

    await persistWizardState?.(targetStep, String(options?.mode || "continue"));
  }

  return {
    resolveProjectPrompt,
    populateWizardValues,
    hasProjectCoreChanges,
    rehydrateWizardProject,
  };
}
