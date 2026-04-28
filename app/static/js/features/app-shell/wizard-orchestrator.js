export function createWizardOrchestrator({
  initializeFrontControllers,
  setCurrentWizardMode,
  resetStepper,
  loadFormats,
  getWizardNavigationVersion,
  loadPromptsForWizard,
  rehydrateWizardProject,
  renderWizardContext,
  loadProviderStatus,
} = {}) {
  return {
    async initWizard(options = {}) {
      const navVersion = Number(options?._navVersion || 0);
      const mode = String(options?.mode || "new").toLowerCase();

      initializeFrontControllers?.();
      setCurrentWizardMode?.(mode);
      resetStepper?.();
      setCurrentWizardMode?.(mode);

      await loadFormats?.();
      if (navVersion && navVersion !== getWizardNavigationVersion?.()) return;

      await loadPromptsForWizard?.(options?.project?.prompt_id || "");
      if (navVersion && navVersion !== getWizardNavigationVersion?.()) return;

      if (options?.project) {
        await rehydrateWizardProject?.(options.project, options);
        return;
      }

      renderWizardContext?.(null);
      await loadProviderStatus?.();
    },
  };
}

export function createProviderStepOrchestrator({
  getSelectedFormat,
  getSelectedPrompt,
  isPreparingGeneration,
  isMaestriaMode,
  validateMaestria,
  setStep3Error,
  getElement,
  upsertProjectDraftFromWizard,
  nextStep,
} = {}) {
  return {
    async goToProviderStep() {
      if (!getSelectedFormat?.() || !getSelectedPrompt?.()) {
        setStep3Error?.("Selecciona formato y paquete antes de continuar.");
        return;
      }

      if (isPreparingGeneration?.()) {
        setStep3Error?.("Hay un proceso en curso. Espera unos segundos e intenta de nuevo.");
        return;
      }

      if (isMaestriaMode?.()) {
        const errors = validateMaestria?.() || [];
        if (errors.length) {
          setStep3Error?.(errors[0]);
          return;
        }
      }

      setStep3Error?.("");

      const button = getElement?.("btn-step3-next-provider");
      const loader = getElement?.("step3-loading");
      if (button) button.classList.add("hidden");
      if (loader) loader.classList.remove("hidden");

      try {
        await upsertProjectDraftFromWizard?.();
        nextStep?.(4);
      } catch (error) {
        setStep3Error?.(error?.message || "No se pudo preparar el proyecto.");
      } finally {
        if (button) button.classList.remove("hidden");
        if (loader) loader.classList.add("hidden");
      }
    },
  };
}
