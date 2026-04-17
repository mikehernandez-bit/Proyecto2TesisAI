import { createPromptSectionTree } from "./section-tree.js";
import { markPromptAdminListBooted } from "./compat.js";
import { patchPromptAdminState } from "./state.js";

let sectionTree = null;
let universityCardsBound = false;
let promptEditorButtonsBound = false;
let promptAdminListApi = null;

function showOnlyView(viewId) {
  document.querySelectorAll(".view-section").forEach((element) => element.classList.add("hidden"));
  document.getElementById(viewId)?.classList.remove("hidden");
}

function showUniversityPanel(targetId) {
  document.getElementById("prompts-grid-admin")?.classList.add("hidden");
  document.querySelectorAll(".univ-panel").forEach((panel) => panel.classList.add("hidden"));
  document.getElementById(targetId)?.classList.remove("hidden");
}

function bindUniversityCards() {
  if (universityCardsBound) return;
  universityCardsBound = true;

  const cardToPanel = {
    "card-unac": "panel-unac",
    "card-uni": "panel-uni",
    "card-uns": "panel-uns",
  };

  Object.entries(cardToPanel).forEach(([cardId, targetId]) => {
    const card = document.getElementById(cardId);
    if (!card || card.dataset.boundPromptAdminCard === "true") return;
    card.dataset.boundPromptAdminCard = "true";
    card.addEventListener("click", (event) => {
      event.preventDefault();
      showUniversityPanel(targetId);
    });
  });

  document.querySelectorAll(".btn-back").forEach((backButton) => {
    if (backButton.dataset.boundPromptAdminBack === "true") return;
    backButton.dataset.boundPromptAdminBack = "true";
    backButton.addEventListener("click", (event) => {
      event.preventDefault();
      document.querySelectorAll(".univ-panel").forEach((panel) => panel.classList.add("hidden"));
      document.getElementById("prompts-grid-admin")?.classList.remove("hidden");
    });
  });

  document.body.addEventListener("click", (event) => {
    const card = event.target.closest("#card-unac, #card-uni, #card-uns");
    if (card) {
      const targetId = cardToPanel[card.id];
      if (targetId) {
        showUniversityPanel(targetId);
      }
      return;
    }

    const backButton = event.target.closest(".btn-back");
    if (!backButton) return;

    event.preventDefault();
    document.querySelectorAll(".univ-panel").forEach((panel) => panel.classList.add("hidden"));
    document.getElementById("prompts-grid-admin")?.classList.remove("hidden");
  });
}

function bindAccordions() {
  document.querySelectorAll(".btn-accordion").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.preventDefault();
      const targetId = button.getAttribute("data-target");
      const currentPanel = button.closest(".univ-panel");
      if (!targetId || !currentPanel) return;

      const target = document.getElementById(targetId);
      const willOpen = Boolean(target?.classList.contains("hidden"));

      currentPanel.querySelectorAll(".btn-accordion").forEach((item) => {
        const content = document.getElementById(item.getAttribute("data-target") || "");
        content?.classList.add("hidden");
        item.querySelector(".accordion-icon")?.classList.remove("rotate-180");
      });

      if (target && willOpen) {
        target.classList.remove("hidden");
        button.querySelector(".accordion-icon")?.classList.add("rotate-180");
      }
    });
  });
}

export function bootPromptPackageAdminList({
  openManualModal,
  renderPromptPackageContext,
  renderPromptPackageCustomization,
} = {}) {
  if (promptAdminListApi) {
    markPromptAdminListBooted();
    return promptAdminListApi;
  }

  if (!sectionTree) {
    sectionTree = createPromptSectionTree({
      getContainer: () => document.getElementById("index-blocks-container"),
      getTitle: () => document.getElementById("index-title"),
      getSubtitle: () => document.getElementById("index-subtitle"),
      onOpenSection: (sectionKey) => {
        patchPromptAdminState({ activeSectionKey: sectionKey });
        openManualModal?.(sectionKey);
      },
      onRenderAncillary: () => {
        renderPromptPackageContext?.();
        renderPromptPackageCustomization?.();
      },
    });
  }

  bindUniversityCards();
  bindAccordions();

  if (!promptEditorButtonsBound) {
    promptEditorButtonsBound = true;
    document.body.addEventListener("click", (event) => {
      const button = event.target.closest(".btn-edit-pkg");
      if (!button) return;
      event.preventDefault();
      event.stopPropagation();
      showOnlyView("view-prompt-index");
      sectionTree.openIndex(button).catch((error) => {
        const container = document.getElementById("index-blocks-container");
        if (container) {
          container.innerHTML = `<div class="rounded-[2rem] border border-red-200 bg-red-50 px-5 py-8 text-sm text-red-700">${error?.message || "No se pudo cargar el paquete institucional."}</div>`;
        }
      });
    });
  }

  promptAdminListApi = {
    renderPromptSectionIndex() {
      sectionTree?.render();
    },
    openIndex(buttonOrFormatId) {
      return sectionTree?.openIndex(buttonOrFormatId);
    },
  };

  markPromptAdminListBooted();

  return promptAdminListApi;
}
