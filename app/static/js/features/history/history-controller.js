export function createHistoryController({
  apiGet,
  getElement,
  sortProjectsForProduct,
  renderPortfolioMetrics,
  effectiveProjectStatus,
  formatProjectDate,
  escapeHtml,
  projectUi,
}) {
  async function refreshHistory() {
    const items = sortProjectsForProduct(await apiGet("/api/projects"));
    renderPortfolioMetrics(items);
    const tbody = getElement("history-table");
    if (!tbody) return;
    tbody.innerHTML = "";

    const query = (getElement("history-search")?.value || "").toLowerCase();
    const filtered = items.filter((project) => {
      const blob = `${project.title || ""} ${project.prompt_name || ""} ${project.format_name || ""}`.toLowerCase();
      return !query || blob.includes(query);
    });

    const empty = getElement("history-empty");
    if (!filtered.length) {
      empty?.classList.remove("hidden");
      return;
    }
    empty?.classList.add("hidden");

    filtered.forEach((project) => {
      const row = document.createElement("tr");
      row.className = "hover:bg-gray-50 transition";
      row.innerHTML = `
        <td class="px-6 py-4">
          <div class="font-medium text-slate-800">${escapeHtml(project.title)}</div>
          <div class="text-xs text-gray-400 flex gap-1 mt-1">
            <i class="fa-solid fa-robot mt-0.5"></i> ${escapeHtml(project.prompt_name || "")}
          </div>
        </td>
        <td class="px-6 py-4 text-gray-600">${escapeHtml(project.format_name || project.format_id || "")}</td>
        <td class="px-6 py-4">${projectUi.statusBadge(effectiveProjectStatus(project))}</td>
        <td class="px-6 py-4 text-gray-500">${escapeHtml(formatProjectDate(project))}</td>
        <td class="px-6 py-4 text-right">
          <div class="flex justify-end gap-2">${projectUi.renderProjectActions(project)}</div>
        </td>
      `;
      tbody.appendChild(row);
    });
  }

  function wireHistorySearch() {
    const input = getElement("history-search");
    if (!input) return;
    input.oninput = () => refreshHistory().catch(() => {});
  }

  return {
    refreshHistory,
    wireHistorySearch,
  };
}
