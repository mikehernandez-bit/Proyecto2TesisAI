const INITIAL_STATE = Object.freeze({
  currentStep: 1,
  format: null,
  promptPackage: null,
  selectedSections: [],
  projectValues: {},
  providerSelection: null,
  generationTrace: null,
  buildArtifacts: null,
  currentProject: null,
  // Maestría UNAC — Excel flow state
  maestriaDetails: null,      // Fully validated details from Excel or manual form
  excelPreviewResult: null,   // Last raw parse result from POST /api/wizard/details/excel-preview
});

function deepClone(value) {
  if (value == null) return value;
  return JSON.parse(JSON.stringify(value));
}

function cloneState(state) {
  return {
    ...state,
    selectedSections: Array.isArray(state.selectedSections) ? [...state.selectedSections] : [],
    projectValues: { ...(state.projectValues || {}) },
    maestriaDetails: deepClone(state.maestriaDetails),
    excelPreviewResult: deepClone(state.excelPreviewResult),
  };
}

export function createWizardStore(initialState = {}) {
  let state = cloneState({ ...INITIAL_STATE, ...initialState });
  const listeners = new Set();

  function emit() {
    const snapshot = cloneState(state);
    listeners.forEach((listener) => listener(snapshot));
  }

  return {
    getState() {
      return cloneState(state);
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    patch(partial) {
      state = cloneState({ ...state, ...(partial || {}) });
      emit();
      return this.getState();
    },
    setCurrentStep(currentStep) {
      return this.patch({ currentStep: Number(currentStep || 1) });
    },
    setFormat(format) {
      return this.patch({ format: format || null });
    },
    setPromptPackage(promptPackage) {
      return this.patch({ promptPackage: promptPackage || null });
    },
    setSelectedSections(selectedSections) {
      return this.patch({ selectedSections: Array.isArray(selectedSections) ? selectedSections : [] });
    },
    setProjectValues(projectValues) {
      return this.patch({ projectValues: { ...(projectValues || {}) } });
    },
    setProviderSelection(providerSelection) {
      return this.patch({ providerSelection: providerSelection || null });
    },
    setGenerationTrace(generationTrace) {
      return this.patch({ generationTrace: generationTrace || null });
    },
    setBuildArtifacts(buildArtifacts) {
      return this.patch({ buildArtifacts: buildArtifacts || null });
    },
    setCurrentProject(currentProject) {
      return this.patch({ currentProject: currentProject || null });
    },
    /** Store the fully validated maestría details (from Excel or manual form). */
    setMaestriaDetails(maestriaDetails) {
      return this.patch({ maestriaDetails: maestriaDetails || null });
    },
    /** Store the raw preview result from the last Excel parse. */
    setExcelPreviewResult(excelPreviewResult) {
      return this.patch({ excelPreviewResult: excelPreviewResult || null });
    },
    reset() {
      state = cloneState(INITIAL_STATE);
      emit();
      return this.getState();
    },
  };
}
