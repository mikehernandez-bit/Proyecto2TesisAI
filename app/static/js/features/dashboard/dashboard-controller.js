export function createDashboardController({
  apiGet,
  getElement,
  sortProjectsForProduct,
  renderPortfolioMetrics,
  effectiveProjectStatus,
  formatProjectDate,
  escapeHtml,
  projectUi,
}) {
  async function refreshDashboard() {
    const items = sortProjectsForProduct(await apiGet("/api/projects"));
    renderPortfolioMetrics(items);

    const tbody = getElement("dashboard-recent-projects");
    if (!tbody) return;
    tbody.innerHTML = "";

    const latestCard = getElement("dashboard-latest-card");
    const latestProject = items[0] || null;
    if (latestCard && latestProject) {
      latestCard.classList.remove("hidden");
      if (getElement("dashboard-latest-title")) {
        getElement("dashboard-latest-title").textContent = latestProject.title || "Proyecto sin título";
      }
      if (getElement("dashboard-latest-meta")) {
        getElement("dashboard-latest-meta").textContent = `${latestProject.format_name || latestProject.format_id || "-"} · ${latestProject.prompt_name || "Sin prompt"} · ${formatProjectDate(latestProject)}`;
      }
      if (getElement("dashboard-latest-status")) {
        getElement("dashboard-latest-status").innerHTML = projectUi.statusBadge(effectiveProjectStatus(latestProject));
      }
      if (getElement("dashboard-latest-summary")) {
        getElement("dashboard-latest-summary").innerHTML = `
          <div class="rounded-2xl border bg-slate-50 px-4 py-3">
            <div class="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Estado real</div>
            <div class="mt-1 font-semibold text-slate-900">${escapeHtml(String(effectiveProjectStatus(latestProject) || "-").replaceAll("_", " "))}</div>
          </div>
          <div class="rounded-2xl border bg-slate-50 px-4 py-3">
            <div class="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Paso sugerido</div>
            <div class="mt-1 font-semibold text-slate-900">Paso ${projectUi.inferProjectStep(latestProject)}</div>
          </div>
          <div class="rounded-2xl border bg-slate-50 px-4 py-3">
            <div class="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Última actividad</div>
            <div class="mt-1 font-semibold text-slate-900">${escapeHtml(formatProjectDate(latestProject))}</div>
          </div>
        `;
      }
      if (getElement("dashboard-latest-actions")) {
        getElement("dashboard-latest-actions").innerHTML = projectUi.renderProjectActions(latestProject, "hero");
      }
    } else if (latestCard) {
      latestCard.classList.add("hidden");
    }

    const empty = getElement("dashboard-empty");
    if (!items.length) {
      empty?.classList.remove("hidden");
      return;
    }
    empty?.classList.add("hidden");

    items.slice(0, 5).forEach((project) => {
      const row = document.createElement("tr");
      row.className = "hover:bg-gray-50";
      row.innerHTML = `
        <td class="px-6 py-4">
          <div class="font-medium text-slate-800">${escapeHtml(project.title)}</div>
          <div class="text-xs text-gray-400">${escapeHtml(project.prompt_name || "")}</div>
        </td>
        <td class="px-6 py-4 text-gray-600">${escapeHtml(project.format_name || project.format_id || "")}</td>
        <td class="px-6 py-4">${projectUi.statusBadge(effectiveProjectStatus(project))}</td>
        <td class="px-6 py-4 text-gray-500">${escapeHtml(formatProjectDate(project))}</td>
        <td class="px-6 py-4 text-right">
          <div class="flex items-center justify-end gap-2">${projectUi.renderProjectActions(project)}</div>
        </td>
      `;
      tbody.appendChild(row);
    });
  }

  return {
    refreshDashboard,
  };
}
