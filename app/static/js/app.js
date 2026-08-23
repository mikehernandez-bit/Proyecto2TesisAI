import { createTesisAI } from "./features/app-shell.js";
import { bindDeclarativeActions } from "./core/action-dispatcher.js";
import { installLegacyFacade } from "./core/legacy-facade.js";
import { bootPromptPackageAdminList } from "./features/prompt-packages/admin-list.js";
import { bootPromptPackageEditor } from "./features/prompt-packages/editor.js";

function buildActionHandlers(app, promptEditor) {
  return {
    "app.showView": ({ element }) => app.showView(String(element.dataset.view || "").trim()),
    "app.nextStep": ({ element }) => app.nextStep(Number(element.dataset.step || 1)),
    "app.prevStep": ({ element }) => app.prevStep(Number(element.dataset.step || 1)),
    "app.selectAllChapters": () => app.selectAllChapters(),
    "app.saveChapterSelectionAndGoDetails": () => app.saveChapterSelectionAndGoDetails(),
    "app.downloadExcelTemplate": () => app.downloadExcelTemplate(),
    "app.triggerFileInput": ({ element }) => {
      const targetId = String(element.dataset.target || "").trim();
      if (!targetId) return;
      document.getElementById(targetId)?.click();
    },
    "app.onExcelFileSelected": ({ element }) => app.onExcelFileSelected(element),
    "app.saveMaestriaDetails": () => app.saveMaestriaDetails(),
    "app.goToProviderStep": () => app.goToProviderStep(),
    "app.triggerGeneration": () => app.triggerGeneration(),
    "app.refreshProviderStatus": () => app.refreshProviderStatus(),
    "app.cancelGeneration": () => app.cancelGeneration(),
    "app.retryGeneration": () => app.retryGeneration(),
    "app.restartGeneration": () => app.restartGeneration(),
    "app.goToDownloads": () => app.goToDownloads(),
    "app.closeBudgetModal": () => app.closeBudgetModal(),
    "app.refreshBudgetPricing": () => app.refreshBudgetPricing(),
    "app.calculateBudgetEstimate": () => app.calculateBudgetEstimate(),
    "app.openSidebarBudget": () => app.openSidebarBudget(),
    "app.goToProjectStep": ({ element }) => app.goToProjectStep(
      Number(element.dataset.step || element.dataset.wizardJump || 1),
    ),
    "app.openProject": ({ element }) => app.openProject(
      String(element.dataset.projectId || "").trim(),
      { mode: String(element.dataset.mode || "continue").trim() || "continue" },
    ),
    "app.deleteProject": ({ element }) => app.deleteProject(String(element.dataset.projectId || "").trim()),
    "prompt.closeManualModal": () => promptEditor.closeManualModal(),
    "prompt.addPromptBlock": () => promptEditor.addPromptBlock(),
    "prompt.savePackage": () => promptEditor.savePackage(),
  };
}

window.addEventListener("DOMContentLoaded", () => {
  const app = createTesisAI();
  const promptEditor = bootPromptPackageEditor();
  const promptAdminList = bootPromptPackageAdminList({
    openManualModal: promptEditor.openManualModal,
    renderPromptPackageContext: promptEditor.renderPromptPackageContext,
    renderPromptPackageCustomization: promptEditor.renderPromptPackageCustomization,
  });
  promptEditor.setHooks({
    renderPromptSectionIndex: promptAdminList.renderPromptSectionIndex,
    renderPromptPackageContext: promptEditor.renderPromptPackageContext,
    renderPromptPackageCustomization: promptEditor.renderPromptPackageCustomization,
  });

  bindDeclarativeActions({
    handlers: buildActionHandlers(app, promptEditor),
  });

  installLegacyFacade(app);
  app.boot().catch(console.error);
});
