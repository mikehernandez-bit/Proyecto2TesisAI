export function createBudgetController({
  apiGet,
  getElement,
  fetchExchangeRate,
  sortProjectsForProduct,
  effectiveProjectStatus,
  projectTokenTotal,
  formatInt,
  formatUsd,
  formatPen,
  formatUsdRate,
  formatProjectDate,
  getUsdToPenRate,
  escapeHtml,
  getCurrentProjectId,
}) {
  let currentBudgetProjectId = "";
  let currentBudgetProjects = [];
  let currentBudgetPayload = null;
  let budgetEstimateVisible = false;

  function closeBudgetModal() {
    currentBudgetProjectId = "";
    currentBudgetProjects = [];
    currentBudgetPayload = null;
    budgetEstimateVisible = false;
    getElement("modal-project-budget")?.classList.add("hidden");
    getElement("budget-loading")?.classList.add("hidden");
    if (getElement("budget-error")) {
      getElement("budget-error").classList.add("hidden");
      getElement("budget-error").textContent = "";
    }
  }

  function showBudgetError(message) {
    getElement("modal-project-budget")?.classList.remove("hidden");
    getElement("budget-loading")?.classList.add("hidden");
    if (getElement("budget-error")) {
      getElement("budget-error").classList.remove("hidden");
      getElement("budget-error").textContent = String(message || "No se pudo abrir Presupuesto IA.");
    }
  }

  function resolveBudgetProjectId(projects, preferredProjectId = "") {
    const items = Array.isArray(projects) ? projects : [];
    const preferred = String(preferredProjectId || "").trim();
    if (preferred && items.some((item) => String(item?.id || "") === preferred)) return preferred;

    const currentId = String(getCurrentProjectId() || "").trim();
    if (currentId && items.some((item) => String(item?.id || "") === currentId)) return currentId;

    const tokenCandidate = items.find((item) => projectTokenTotal(item) > 0);
    if (tokenCandidate?.id) return String(tokenCandidate.id);

    return String(items[0]?.id || "").trim();
  }

  function renderBudgetProjectOptions(projects, selectedProjectId = "") {
    const projectSelect = getElement("budget-project-select");
    const helper = getElement("budget-project-helper");
    if (!projectSelect) return "";

    const items = Array.isArray(projects) ? projects : [];
    if (!items.length) {
      projectSelect.innerHTML = '<option value="">Sin proyectos disponibles</option>';
      projectSelect.disabled = true;
      if (helper) helper.textContent = "No hay proyectos registrados para calcular presupuesto.";
      return "";
    }

    projectSelect.innerHTML = items.map((project) => {
      const title = String(project?.title || "Proyecto sin titulo").trim();
      const formatName = String(project?.format_name || project?.format_id || "Sin formato").trim();
      const tokenLabel = formatInt(projectTokenTotal(project));
      return `
        <option value="${escapeHtml(project.id || "")}">
          ${escapeHtml(`${title} · ${formatName} · ${tokenLabel} tokens`)}
        </option>
      `;
    }).join("");
    projectSelect.disabled = false;

    const resolvedId = resolveBudgetProjectId(items, selectedProjectId);
    if (resolvedId) projectSelect.value = resolvedId;

    const selectedProject = items.find((project) => String(project?.id || "") === String(projectSelect.value || "")) || items[0];
    if (helper) {
      const status = String(effectiveProjectStatus(selectedProject) || "-").replaceAll("_", " ");
      helper.textContent = `${status} · Actualizado ${formatProjectDate(selectedProject)}`;
    }
    return String(projectSelect.value || "");
  }

  async function prepareBudgetProjects(preferredProjectId = "") {
    const items = sortProjectsForProduct(await apiGet("/api/projects"));
    currentBudgetProjects = items;
    return renderBudgetProjectOptions(items, preferredProjectId);
  }

  function renderBudgetEstimateVisibility() {
    getElement("budget-estimate-pending")?.classList.toggle("hidden", budgetEstimateVisible);
    getElement("budget-estimate-results")?.classList.toggle("hidden", !budgetEstimateVisible);
    getElement("budget-compare-pending")?.classList.toggle("hidden", budgetEstimateVisible);
    getElement("budget-compare-results")?.classList.toggle("hidden", !budgetEstimateVisible);
    getElement("budget-sections-pending")?.classList.toggle("hidden", budgetEstimateVisible);
    getElement("budget-sections-results")?.classList.toggle("hidden", !budgetEstimateVisible);
    if (getElement("budget-calculate-button")) {
      getElement("budget-calculate-button").innerHTML = budgetEstimateVisible
        ? '<i class="fa-solid fa-rotate-right"></i> Recalcular presupuesto'
        : '<i class="fa-solid fa-calculator"></i> Calcular presupuesto';
    }
  }

  function renderBudgetProviderOptions(catalogProviders, selectedProvider, selectedModel) {
    const providerSelect = getElement("budget-provider-select");
    const modelSelect = getElement("budget-model-select");
    if (!providerSelect || !modelSelect) return;

    const providers = Array.isArray(catalogProviders) ? catalogProviders : [];
    providerSelect.innerHTML = providers.map((item) => `
      <option value="${escapeHtml(item.id || "")}">${escapeHtml(item.label || item.id || "-")}</option>
    `).join("");

    if (selectedProvider) providerSelect.value = selectedProvider;
    const currentProvider = providers.find((item) => String(item.id || "") === String(providerSelect.value || "")) || providers[0];
    const models = Array.isArray(currentProvider?.models) ? currentProvider.models : [];
    modelSelect.innerHTML = models.map((item) => `
      <option value="${escapeHtml(item.model || "")}">${escapeHtml(item.display_name || item.model || "-")}</option>
    `).join("");
    if (selectedModel && models.some((item) => String(item.model || "") === String(selectedModel))) {
      modelSelect.value = selectedModel;
    }
  }

  function renderBudgetPayload(payload) {
    currentBudgetPayload = payload || null;
    const project = payload?.project || {};
    const usage = payload?.usage || {};
    const pricing = payload?.selected_pricing || {};
    const estimate = payload?.estimate || {};
    const comparisons = Array.isArray(payload?.comparisons) ? payload.comparisons : [];
    const catalogProviders = Array.isArray(payload?.catalog?.providers) ? payload.catalog.providers : [];

    renderBudgetProviderOptions(
      catalogProviders,
      pricing?.provider || estimate?.provider || "",
      pricing?.model || estimate?.model || "",
    );
    renderBudgetProjectOptions(currentBudgetProjects, project?.id || currentBudgetProjectId);

    if (getElement("budget-project-title")) getElement("budget-project-title").textContent = project.title || "Proyecto sin titulo";
    if (getElement("budget-project-meta")) {
      getElement("budget-project-meta").textContent = `${project.format_name || "-"} - ${String(project.status || "-").replaceAll("_", " ")}`;
    }
    if (getElement("budget-project-origin")) {
      const originalProvider = String(project.original_provider || "").trim();
      const originalModel = String(project.original_model || "").trim();
      getElement("budget-project-origin").textContent = originalProvider && originalModel
        ? `Modelo original usado: ${originalProvider} - ${originalModel}`
        : "Aun no hay un modelo historico dominante registrado para este proyecto.";
    }

    if (getElement("budget-usage-input")) getElement("budget-usage-input").textContent = formatInt(usage.input_tokens_total || 0);
    if (getElement("budget-usage-output")) getElement("budget-usage-output").textContent = formatInt(usage.output_tokens_total || 0);
    if (getElement("budget-usage-total")) getElement("budget-usage-total").textContent = formatInt(usage.total_tokens || 0);
    if (getElement("budget-usage-meta")) {
      const usageSource = String(usage.usage_source || "unavailable");
      getElement("budget-usage-meta").textContent = `Llamadas: ${formatInt(usage.calls_total || 0)} - Fuente: ${usageSource} - Estimadas: ${formatInt(usage.estimated_calls || 0)}`;
    }

    if (getElement("budget-pricing-state")) {
      const providerLabel = pricing.provider_label || pricing.provider || "-";
      const modelLabel = pricing.display_name || pricing.model || "Sin modelo";
      getElement("budget-pricing-state").textContent = `${providerLabel} - ${modelLabel}`;
    }
    if (getElement("budget-pricing-meta")) {
      const sourceState = String(pricing.pricing_source || "unavailable");
      const sourceOrigin = String(pricing.pricing_origin || "unavailable").replaceAll("_", " ");
      const endpointProvider = String(pricing.endpoint_provider || "").trim();
      const endpointSuffix = endpointProvider ? ` - Endpoint: ${endpointProvider}` : "";
      const cacheSuffix = pricing.is_cached_fallback ? " - usando cache valida" : "";
      getElement("budget-pricing-meta").textContent = `Fuente: ${sourceOrigin} - Estado: ${sourceState}${endpointSuffix}${cacheSuffix}`;
    }
    if (getElement("budget-price-check-note")) {
      const providerLabel = pricing.provider_label || pricing.provider || "Sin proveedor";
      const modelLabel = pricing.display_name || pricing.model || "Sin modelo";
      const sourceOrigin = String(pricing.pricing_origin || "unavailable").replaceAll("_", " ");
      getElement("budget-price-check-note").textContent = `Precio actual extraido para ${providerLabel} - ${modelLabel} desde ${sourceOrigin}. Verificalo antes de aplicar la simulacion.`;
    }

    if (getElement("budget-price-input")) getElement("budget-price-input").textContent = formatUsdRate(pricing.input_price_per_1m_tokens);
    if (getElement("budget-price-output")) getElement("budget-price-output").textContent = formatUsdRate(pricing.output_price_per_1m_tokens);
    if (getElement("budget-price-cached-input")) getElement("budget-price-cached-input").textContent = formatUsdRate(pricing.cached_input_price_per_1m_tokens);
    if (getElement("budget-price-meta")) {
      const requestPrice = Number(pricing.request_price);
      const requestSuffix = Number.isFinite(requestPrice) && requestPrice > 0 ? ` - Req: ${formatUsd(requestPrice)}` : "";
      getElement("budget-price-meta").textContent = `${pricing.currency || "USD"} - ${pricing.pricing_mode || "unavailable"}${requestSuffix}`;
    }
    if (getElement("budget-price-rule")) {
      const extras = [];
      if (Number.isFinite(Number(pricing.image_price)) && Number(pricing.image_price) > 0) {
        extras.push(`Imagen: ${formatUsd(Number(pricing.image_price))}`);
      }
      if (Number.isFinite(Number(pricing.web_search_price)) && Number(pricing.web_search_price) > 0) {
        extras.push(`Web search: ${formatUsd(Number(pricing.web_search_price))}`);
      }
      if (String(pricing.endpoint_tag || "").trim()) {
        extras.push(`Tag endpoint: ${pricing.endpoint_tag}`);
      }
      const ruleText = pricing.threshold_rule || "Sin reglas adicionales informadas para este modelo.";
      getElement("budget-price-rule").textContent = extras.length ? `${ruleText} - ${extras.join(" - ")}` : ruleText;
    }
    if (getElement("budget-price-fetched")) {
      getElement("budget-price-fetched").textContent = pricing.fetched_at
        ? `Actualizado: ${pricing.fetched_at}`
        : "Fecha de pricing no disponible";
    }
    if (getElement("budget-price-source")) {
      getElement("budget-price-source").setAttribute("href", pricing.source_url || "#");
      getElement("budget-price-source").classList.toggle("pointer-events-none", !pricing.source_url);
      getElement("budget-price-source").classList.toggle("opacity-50", !pricing.source_url);
    }

    if (getElement("budget-cost-input")) getElement("budget-cost-input").textContent = formatUsd(estimate.estimated_input_cost || 0);
    if (getElement("budget-cost-output")) getElement("budget-cost-output").textContent = formatUsd(estimate.estimated_output_cost || 0);
    if (getElement("budget-cost-total")) getElement("budget-cost-total").textContent = formatUsd(estimate.estimated_total_cost || 0);
    if (getElement("budget-cost-total-pen")) getElement("budget-cost-total-pen").textContent = formatPen(estimate.estimated_total_cost || 0);
    if (getElement("budget-pen-rate")) getElement("budget-pen-rate").textContent = `TC: 1 USD = ${getUsdToPenRate()} PEN`;
    renderBudgetEstimateVisibility();

    if (getElement("budget-compare-table")) {
      getElement("budget-compare-table").innerHTML = comparisons.map((item) => `
        <tr class="hover:bg-slate-50">
          <td class="px-4 py-3">
            <div class="font-semibold text-slate-800">${escapeHtml(item.provider_label || item.provider || "-")}</div>
            <div class="text-xs text-slate-400">${escapeHtml(item.pricing_source || "unavailable")}</div>
          </td>
          <td class="px-4 py-3 text-slate-700">${escapeHtml(item.display_name || item.model || "-")}</td>
          <td class="px-4 py-3 text-right font-bold ${item.available ? "text-slate-900" : "text-slate-400"}">${item.available ? escapeHtml(formatUsd(item.estimated_total_cost || 0)) : "No disponible"}</td>
        </tr>
      `).join("") || '<tr><td colspan="3" class="px-4 py-4 text-sm text-slate-500">No hay modelos disponibles para comparar.</td></tr>';
    }

    if (getElement("budget-sections-table")) {
      const rows = Array.isArray(estimate.sections) ? estimate.sections : [];
      getElement("budget-sections-table").innerHTML = rows.map((item) => `
        <tr class="hover:bg-slate-50">
          <td class="px-4 py-3">
            <div class="font-semibold text-slate-800">${escapeHtml(item.section_path || item.section_title || "Seccion")}</div>
          </td>
          <td class="px-4 py-3 text-right text-slate-600">${escapeHtml(formatInt(item.input_tokens || 0))}</td>
          <td class="px-4 py-3 text-right text-slate-600">${escapeHtml(formatInt(item.output_tokens || 0))}</td>
          <td class="px-4 py-3 text-right text-slate-600">${escapeHtml(formatInt(item.total_tokens || 0))}</td>
          <td class="px-4 py-3 text-right font-semibold text-slate-900">${escapeHtml(formatUsd(item.estimated_total_cost || 0))}</td>
        </tr>
      `).join("") || '<tr><td colspan="5" class="px-4 py-4 text-sm text-slate-500">No hay secciones historicas con tokens registrados para este proyecto.</td></tr>';
    }
  }

  async function loadBudget(projectId, options = {}) {
    if (!projectId) return;
    currentBudgetProjectId = projectId;
    renderBudgetProjectOptions(currentBudgetProjects, projectId);
    const params = new URLSearchParams();
    if (options.provider) params.set("provider", String(options.provider));
    if (options.model) params.set("model", String(options.model));
    if (options.refreshPricing) params.set("refreshPricing", "true");

    getElement("budget-loading")?.classList.remove("hidden");
    if (getElement("budget-error")) {
      getElement("budget-error").classList.add("hidden");
      getElement("budget-error").textContent = "";
    }

    try {
      const payload = await apiGet(`/api/projects/${encodeURIComponent(projectId)}/budget${params.toString() ? `?${params.toString()}` : ""}`);
      renderBudgetPayload(payload);
    } catch (error) {
      if (getElement("budget-error")) {
        getElement("budget-error").classList.remove("hidden");
        getElement("budget-error").textContent = error?.message || "No se pudo calcular el presupuesto IA.";
      }
    } finally {
      getElement("budget-loading")?.classList.add("hidden");
    }
  }

  async function openBudgetModal(projectId) {
    await fetchExchangeRate();
    getElement("modal-project-budget")?.classList.remove("hidden");
    if (getElement("budget-project-select")) {
      getElement("budget-project-select").onchange = async () => {
        budgetEstimateVisible = false;
        renderBudgetEstimateVisibility();
        const nextProjectId = String(getElement("budget-project-select")?.value || "").trim();
        if (!nextProjectId) return;
        await loadBudget(nextProjectId);
      };
    }
    if (getElement("budget-provider-select")) {
      getElement("budget-provider-select").onchange = async () => {
        budgetEstimateVisible = false;
        renderBudgetEstimateVisibility();
        renderBudgetProviderOptions(currentBudgetPayload?.catalog?.providers || [], getElement("budget-provider-select")?.value || "", "");
        const provider = getElement("budget-provider-select")?.value || "";
        const model = getElement("budget-model-select")?.value || "";
        await loadBudget(currentBudgetProjectId, { provider, model });
      };
    }
    if (getElement("budget-model-select")) {
      getElement("budget-model-select").onchange = async () => {
        budgetEstimateVisible = false;
        renderBudgetEstimateVisibility();
        const provider = getElement("budget-provider-select")?.value || "";
        const model = getElement("budget-model-select")?.value || "";
        await loadBudget(currentBudgetProjectId, { provider, model });
      };
    }
    budgetEstimateVisible = false;
    renderBudgetEstimateVisibility();
    const selectedProjectId = await prepareBudgetProjects(projectId);
    if (!selectedProjectId) {
      showBudgetError("Aun no hay proyectos registrados para calcular un presupuesto IA.");
      return;
    }
    await loadBudget(selectedProjectId);
  }

  async function openSidebarBudget() {
    await openBudgetModal(String(getCurrentProjectId() || "").trim());
  }

  async function refreshBudgetPricing() {
    if (!currentBudgetProjectId) return;
    budgetEstimateVisible = false;
    renderBudgetEstimateVisibility();
    const provider = getElement("budget-provider-select")?.value || "";
    const model = getElement("budget-model-select")?.value || "";
    await loadBudget(currentBudgetProjectId, { provider, model, refreshPricing: true });
  }

  function calculateBudgetEstimate() {
    if (!currentBudgetPayload) return;
    budgetEstimateVisible = true;
    renderBudgetPayload(currentBudgetPayload);
  }

  return {
    closeBudgetModal,
    openBudgetModal,
    openSidebarBudget,
    refreshBudgetPricing,
    calculateBudgetEstimate,
  };
}
