export function getCategoryLabel(rawCategory) {
  const labels = {
    proyecto: "Proyecto de tesis",
    informe: "Informe de tesis",
    maestria: "Tesis de postgrado",
    posgrado: "Tesis de postgrado",
    general: "Documentos generales",
  };
  return labels[rawCategory] || rawCategory || "Sin categoria";
}

export function resolveProjectFormat(project, formatsCache = []) {
  const formatId = String(project?.format_id || "").trim();
  if (!formatId) return null;
  return (Array.isArray(formatsCache) ? formatsCache : []).find(
    (item) => String(item?.id || "") === formatId,
  ) || {
    id: formatId,
    title: project?.format_name || formatId,
    name: project?.format_name || formatId,
    version: project?.format_version || "",
  };
}

export function renderWizardContext({
  project,
  currentWizardMode = "new",
  currentStep = 1,
  getElement,
  statusBadge,
  root = document,
} = {}) {
  const panel = getElement?.("wizard-context-panel");
  if (!panel) return;

  if (!project?.id || currentWizardMode === "review") {
    panel.classList.add("hidden");
    return;
  }

  panel.classList.remove("hidden");

  const title = getElement?.("wizard-context-title");
  if (title) {
    title.textContent = project.title || "Proyecto existente";
  }

  const text = getElement?.("wizard-context-text");
  if (text) {
    text.textContent = `Proyecto ${project.id} · ${project.prompt_name || "Sin prompt"} · ${project.format_name || project.format_id || "Sin formato"}. Si modificas pasos previos y guardas, la generacion posterior se reiniciara de forma explicita.`;
  }

  const status = getElement?.("wizard-context-status");
  if (status) {
    status.innerHTML = statusBadge?.(project) || "";
  }

  root.querySelectorAll("[data-wizard-jump]").forEach((button) => {
    const buttonStep = Number(button.getAttribute("data-wizard-jump") || 1);
    button.classList.remove("bg-amber-100", "border-amber-400");
    if (buttonStep === currentStep) {
      button.classList.add("bg-amber-100", "border-amber-400");
    }
  });
}
