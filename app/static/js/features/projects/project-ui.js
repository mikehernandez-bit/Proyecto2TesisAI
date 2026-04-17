export function createProjectUi({
  escapeHtml,
  effectiveProjectStatus,
  hasMeaningfulProjectValues,
}) {
  function statusBadge(status) {
    if (status === "ready") return '<span class="bg-emerald-100 text-emerald-700 px-2 py-1 rounded text-xs font-semibold">Listo para generar</span>';
    if (status === "draft") return '<span class="bg-slate-100 text-slate-700 px-2 py-1 rounded text-xs font-semibold">Borrador</span>';
    if (status === "generating") return '<span class="bg-blue-100 text-blue-700 px-2 py-1 rounded text-xs font-semibold">Generando</span>';
    if (status === "rendering") return '<span class="bg-sky-100 text-sky-700 px-2 py-1 rounded text-xs font-semibold">Renderizando</span>';
    if (status === "ai_received") return '<span class="bg-indigo-100 text-indigo-700 px-2 py-1 rounded text-xs font-semibold">IA recibida</span>';
    if (status === "cancel_requested") return '<span class="bg-amber-100 text-amber-700 px-2 py-1 rounded text-xs font-semibold">Cancelando</span>';
    if (status === "simulated") return '<span class="bg-cyan-100 text-cyan-700 px-2 py-1 rounded text-xs font-semibold">Simulado</span>';
    if (status === "completed") return '<span class="bg-green-100 text-green-700 px-2 py-1 rounded text-xs font-semibold">Completado</span>';
    if (status === "completed_with_incidents") return '<span class="bg-amber-100 text-amber-700 px-2 py-1 rounded text-xs font-semibold">Completado con incidencias</span>';
    if (status === "processing") return '<span class="bg-yellow-100 text-yellow-700 px-2 py-1 rounded text-xs font-semibold">Procesando</span>';
    if (status === "render_failed") return '<span class="bg-orange-100 text-orange-700 px-2 py-1 rounded text-xs font-semibold">Render fallido</span>';
    if (status === "generation_failed" || status === "ai_failed" || status === "blocked") return '<span class="bg-red-100 text-red-700 px-2 py-1 rounded text-xs font-semibold">Fallo</span>';
    if (status === "failed") return '<span class="bg-red-100 text-red-700 px-2 py-1 rounded text-xs font-semibold">Fallo</span>';
    return '<span class="bg-gray-100 text-gray-600 px-2 py-1 rounded text-xs font-semibold">N/A</span>';
  }

  function inferDraftStep(project) {
    if (!project?.format_id) return 1;
    if (!project?.prompt_id) return 2;
    if (!hasMeaningfulProjectValues(project)) return 3;
    return 4;
  }

  function inferProjectStep(project, mode = "continue") {
    const requestedMode = String(mode || "continue").toLowerCase();
    const status = effectiveProjectStatus(project);
    if (requestedMode === "review") {
      if (status === "rendering" || status === "render_failed") return 6;
      if (["completed", "completed_with_incidents", "simulated"].includes(status)) return 5;
      if (status === "generating" || status === "processing" || status === "sending" || status === "cancel_requested") {
        return 5;
      }
    }
    if (requestedMode === "edit-format") return 1;
    if (requestedMode === "edit-prompt") return 2;
    if (requestedMode === "edit-details") return 3;
    if (requestedMode === "edit-ia") return 4;

    if (status === "generating" || status === "processing" || status === "sending" || status === "cancel_requested") return 5;
    if (status === "rendering" || status === "render_failed") return 6;
    if (["completed", "completed_with_incidents", "simulated"].includes(status)) return 7;
    if (status === "failed" || status === "blocked") return 5;

    const wizardStep = Number(project?.wizard_state?.current_step || 0);
    if (wizardStep >= 1 && wizardStep <= 4) return wizardStep;
    return inferDraftStep(project);
  }

  function projectPrimaryAction(project) {
    const status = effectiveProjectStatus(project);
    if (status === "draft" || status === "ready") {
      return { label: "Continuar", mode: "continue", icon: "fa-solid fa-play" };
    }
    if (status === "generating" || status === "rendering" || status === "cancel_requested") {
      return { label: "Abrir", mode: "continue", icon: "fa-solid fa-wave-square" };
    }
    if (status === "render_failed") {
      return { label: "Revisar", mode: "review", icon: "fa-solid fa-triangle-exclamation" };
    }
    if (status === "failed" || status === "blocked") {
      return { label: "Reintentar", mode: "continue", icon: "fa-solid fa-rotate-right" };
    }
    return { label: "Revisar", mode: "review", icon: "fa-solid fa-folder-open" };
  }

  function renderProjectActions(project, variant = "table") {
    const primary = projectPrimaryAction(project);
    const canDownload = (project.status === "completed" || project.status === "completed_with_incidents") && project.output_file;
    const baseClasses = variant === "hero"
      ? {
        primary: "inline-flex h-10 w-10 items-center justify-center rounded-xl bg-slate-900 text-sm text-white shadow-sm transition hover:bg-slate-950",
        tertiary: "inline-flex h-10 w-10 items-center justify-center rounded-xl border border-emerald-300 bg-emerald-50 text-sm text-emerald-700 transition hover:bg-emerald-100",
        danger: "inline-flex h-10 w-10 items-center justify-center rounded-xl border border-rose-300 bg-rose-50 text-sm text-rose-700 transition hover:bg-rose-100",
      }
      : {
        primary: "inline-flex h-9 w-9 items-center justify-center rounded-lg bg-slate-900 text-xs text-white transition hover:bg-slate-950",
        tertiary: "inline-flex h-9 w-9 items-center justify-center rounded-lg border border-emerald-300 bg-emerald-50 text-xs text-emerald-700 transition hover:bg-emerald-100",
        danger: "inline-flex h-9 w-9 items-center justify-center rounded-lg border border-rose-300 bg-rose-50 text-xs text-rose-700 transition hover:bg-rose-100",
      };

    return `
      <button
        type="button"
        class="${baseClasses.primary}"
        title="${escapeHtml(primary.label)}"
        aria-label="${escapeHtml(primary.label)}"
        data-action="app.openProject"
        data-project-id="${escapeHtml(project.id)}"
        data-mode="${escapeHtml(primary.mode)}"
      >
        <i class="${escapeHtml(primary.icon)}"></i>
      </button>
      ${canDownload
        ? `<a
            class="${baseClasses.tertiary}"
            href="/api/download/${encodeURIComponent(project.id)}"
            title="Descargar"
            aria-label="Descargar"
          ><i class="fa-solid fa-download"></i></a>`
        : ""}
      <button
        type="button"
        class="${baseClasses.danger}"
        title="Eliminar"
        aria-label="Eliminar"
        data-action="app.deleteProject"
        data-project-id="${escapeHtml(project.id)}"
      >
        <i class="fa-solid fa-trash"></i>
      </button>
    `;
  }

  return {
    statusBadge,
    inferDraftStep,
    inferProjectStep,
    projectPrimaryAction,
    renderProjectActions,
  };
}
