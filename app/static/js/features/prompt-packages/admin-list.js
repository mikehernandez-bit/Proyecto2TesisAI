import { createPromptSectionTree } from "./section-tree.js";
import { patchPromptAdminState } from "./state.js";

let sectionTree = null;

function showOnlyView(viewId) {
  document.querySelectorAll(".view-section").forEach((element) => element.classList.add("hidden"));
  document.getElementById(viewId)?.classList.remove("hidden");
}

function bindUniversityCards() {
  const gridAdmin = document.getElementById("prompts-grid-admin");
  const panels = document.querySelectorAll(".univ-panel");
  [
    { id: "card-unac", target: "panel-unac" },
    { id: "card-uni", target: "panel-uni" },
    { id: "card-uns", target: "panel-uns" },
  ].forEach((card) => {
    document.getElementById(card.id)?.addEventListener("click", () => {
      gridAdmin?.classList.add("hidden");
      panels.forEach((panel) => panel.classList.add("hidden"));
      document.getElementById(card.target)?.classList.remove("hidden");
    });
  });

  document.querySelectorAll(".btn-back").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.preventDefault();
      panels.forEach((panel) => panel.classList.add("hidden"));
      gridAdmin?.classList.remove("hidden");
    });
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

export function bootPromptPackageAdminList() {
  if (window.__promptAdminListBooted) {
    return;
  }
  window.__promptAdminListBooted = true;

  if (!sectionTree) {
    sectionTree = createPromptSectionTree({
      getContainer: () => document.getElementById("index-blocks-container"),
      getTitle: () => document.getElementById("index-title"),
      getSubtitle: () => document.getElementById("index-subtitle"),
      onOpenSection: (sectionKey) => {
        patchPromptAdminState({ activeSectionKey: sectionKey });
        window.openManualModal?.(sectionKey);
      },
    });
  }
  window.renderPromptSectionIndex = () => sectionTree.render();

  bindUniversityCards();
  bindAccordions();

  document.body.addEventListener("click", (event) => {
    const button = event.target.closest(".btn-edit-pkg");
    if (!button) return;
    event.preventDefault();
    event.stopPropagation();
    showOnlyView("view-prompt-index");
    sectionTree.openIndex(button).catch((error) => {
      const container = document.getElementById("index-blocks-container");
      if (container) {
        container.innerHTML = `<div class="rounded-2xl border border-red-200 bg-red-50 px-5 py-8 text-sm text-red-700">${error?.message || "No se pudo cargar el paquete institucional."}</div>`;
      }
    });
  });
}
