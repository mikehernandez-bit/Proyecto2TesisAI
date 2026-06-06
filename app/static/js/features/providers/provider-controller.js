export function createProviderController({
  apiGet,
  apiSend,
  getElement,
  escapeHtml,
  wizardStore,
  getCurrentProjectId,
}) {
  let providerStatusCache = null;
  const FIXED_PROVIDER = "mistral";
  const FIXED_MODE = "fixed";

  function visibleProviders(payload = providerStatusCache) {
    const providers = Array.isArray(payload?.providers) ? payload.providers : [];
    return providers.filter((provider) => provider?.id === FIXED_PROVIDER);
  }

  function setProviderSelectorError(message) {
    const element = getElement("provider-select-error");
    if (!element) return;
    const normalized = String(message || "").trim();
    if (!normalized) {
      element.classList.add("hidden");
      element.textContent = "";
      return;
    }
    element.classList.remove("hidden");
    element.textContent = normalized;
  }

  function providerHealthMeta(provider) {
    const probeStatus = String(
      provider?.probe?.status ?? provider?.last_probe_status ?? "UNVERIFIED"
    ).toUpperCase();
    const retryAfter = Number(
      provider?.probe?.retry_after_s ?? provider?.last_probe_retry_after_s ?? 0
    );
    const health = String(provider?.health || "UNKNOWN").toUpperCase();

    if (probeStatus === "OK") {
      return {
        label: "Disponible",
        icon: "OK",
        ring: "#16a34a",
        chip: "bg-green-50 text-green-700 border-green-200",
      };
    }
    if (probeStatus === "UNVERIFIED") {
      return {
        label: "No verificado",
        icon: "...",
        ring: "#64748b",
        chip: "bg-slate-50 text-slate-700 border-slate-200",
      };
    }
    if (probeStatus === "RATE_LIMITED") {
      return {
        label: retryAfter > 0 ? `Rate-limited (${retryAfter}s)` : "Rate-limited",
        icon: "!",
        ring: "#f59e0b",
        chip: "bg-amber-50 text-amber-700 border-amber-200",
      };
    }
    if (probeStatus === "EXHAUSTED") {
      return {
        label: "Sin cuota",
        icon: "X",
        ring: "#dc2626",
        chip: "bg-red-50 text-red-700 border-red-200",
      };
    }
    if (probeStatus === "AUTH_ERROR") {
      return {
        label: "Credenciales invalidas",
        icon: "X",
        ring: "#dc2626",
        chip: "bg-red-50 text-red-700 border-red-200",
      };
    }
    if (probeStatus === "ERROR" || health === "DEGRADED") {
      return {
        label: "Degradado",
        icon: "!",
        ring: "#f97316",
        chip: "bg-orange-50 text-orange-700 border-orange-200",
      };
    }
    return {
      label: "Desconocido",
      icon: "o",
      ring: "#64748b",
      chip: "bg-slate-50 text-slate-700 border-slate-200",
    };
  }

  function findProvider(providerId) {
    const providers = visibleProviders();
    if (!Array.isArray(providers)) return null;
    return providers.find((item) => item && item.id === providerId) || null;
  }

  function providerEligibleForFallback(provider) {
    if (!provider || !provider.id) return false;
    if (!provider.configured) return false;
    const probeStatus = String(
      provider?.probe?.status ?? provider?.last_probe_status ?? "UNVERIFIED"
    ).toUpperCase();
    const health = String(provider?.health || "UNKNOWN").toUpperCase();
    if (probeStatus === "EXHAUSTED" || probeStatus === "AUTH_ERROR") return false;
    if (health === "EXHAUSTED") return false;
    return true;
  }

  function fallbackOptionsForPrimary(primaryProvider) {
    const providers = visibleProviders();
    return providers.filter((item) =>
      item?.id &&
      item.id !== primaryProvider &&
      providerEligibleForFallback(item)
    );
  }

  function computeFallbackSelection(primaryProvider) {
    const options = fallbackOptionsForPrimary(primaryProvider);
    const candidate = options[0];
    if (candidate) {
      return {
        fallback_provider: candidate.id,
        fallback_model: candidate.model || "",
      };
    }
    return {
      fallback_provider: "",
      fallback_model: "",
    };
  }

  function providersStatusUrl(projectId = null) {
    if (!projectId) return "/api/providers/status";
    return `/api/providers/status?projectId=${encodeURIComponent(projectId)}`;
  }

  function providersProbeUrl(projectId = null) {
    if (!projectId) return "/api/providers/probe";
    return `/api/providers/probe?projectId=${encodeURIComponent(projectId)}`;
  }

  function providersSelectUrl(projectId = null) {
    if (!projectId) return "/api/providers/select";
    return `/api/providers/select?projectId=${encodeURIComponent(projectId)}`;
  }

  async function saveProviderSelection(payload, projectId = null) {
    const selectedProvider = FIXED_PROVIDER;
    const body = {
      provider: selectedProvider,
      model: payload.model || findProvider(selectedProvider)?.model || providerStatusCache?.selected_model || "",
      fallback_provider: "",
      fallback_model: "",
      mode: FIXED_MODE,
    };
    const updated = await apiSend(providersSelectUrl(projectId), "POST", body);
    providerStatusCache = updated;
    wizardStore.setProviderSelection(updated);
    renderProviderSelector(updated);
    return updated;
  }

  async function selectProvider(providerId) {
    const provider = findProvider(providerId);
    if (!provider) return null;
    return saveProviderSelection({
      provider: FIXED_PROVIDER,
      model: provider.model || "",
      fallback_provider: "",
      fallback_model: "",
      mode: FIXED_MODE,
    }, getCurrentProjectId() || null);
  }

  async function setProviderMode(mode) {
    if (!providerStatusCache) return null;
    const selectedProvider = FIXED_PROVIDER;
    const selectedModel = providerStatusCache.selected_model || (findProvider(selectedProvider)?.model || "");
    return saveProviderSelection({
      provider: selectedProvider,
      model: selectedModel,
      fallback_provider: "",
      fallback_model: "",
      mode: FIXED_MODE,
    }, getCurrentProjectId() || null);
  }

  function renderProviderSelector(payload) {
    const container = getElement("provider-cards");
    if (!container) return;

    const providers = visibleProviders(payload);
    if (!providers.length) {
      container.innerHTML = '<div class="text-xs text-slate-500">Mistral no está disponible en este momento.</div>';
      return;
    }

    const selected = FIXED_PROVIDER;
    const selectedProviderData = findProvider(selected);

    container.innerHTML = providers.map((provider) => {
      const health = providerHealthMeta(provider);
      const configured = !!provider.configured;
      const isSelected = provider.id === selected;
      const probeStatus = String(provider?.probe?.status ?? provider?.last_probe_status ?? "UNVERIFIED").toUpperCase();
      const online = provider?.online === true;
      const blocked = !configured || !online || probeStatus === "EXHAUSTED" || probeStatus === "AUTH_ERROR";

      const warningParts = [];
      if (provider?.probe?.detail || provider?.last_probe_detail) {
        warningParts.push(`Probe: ${escapeHtml(provider?.probe?.detail || provider?.last_probe_detail)}`);
      }
      if (provider?.stats?.last_error) {
        warningParts.push(`Ultimo error: ${escapeHtml(provider.stats.last_error)}`);
      }
      const warning = warningParts.length
        ? `<div class="mt-2 text-[11px] text-slate-600">${warningParts.join("<br/>")}</div>`
        : "";

      return `
        <div class="border rounded-xl p-3 bg-white ${isSelected ? "provider-card-selected" : "border-slate-200"}">
          <div class="flex items-start justify-between gap-2">
            <div>
              <div class="text-sm font-semibold text-slate-800">${escapeHtml(provider.display_name || provider.id)}</div>
              <div class="text-xs text-slate-500">${escapeHtml(provider.model || "-")}</div>
            </div>
            <span class="text-[11px] border rounded-full px-2 py-1 ${health.chip}">
              ${health.icon} ${escapeHtml(health.label)}
            </span>
          </div>
          <div class="mt-3 flex items-center justify-between gap-2">
            <div class="text-[11px] text-slate-500">
              ${configured ? (online ? "Configurado" : "Offline") : "Sin API key"}
            </div>
            <button
              type="button"
              data-provider-select="${escapeHtml(provider.id)}"
              class="text-xs px-3 py-1.5 rounded ${blocked ? "bg-slate-200 text-slate-400 cursor-not-allowed" : "bg-blue-600 text-white hover:bg-blue-700"}"
              ${blocked ? "disabled" : ""}
            >
              ${isSelected ? "Seleccionado" : "Seleccionar"}
            </button>
          </div>
          ${warning}
        </div>
      `;
    }).join("");

    container.querySelectorAll("button[data-provider-select]").forEach((button) => {
      button.onclick = async () => {
        const targetProvider = button.getAttribute("data-provider-select");
        if (!targetProvider) return;
        try {
          setProviderSelectorError("");
          await selectProvider(targetProvider);
        } catch (error) {
          setProviderSelectorError(error?.message || "No se pudo guardar la seleccion.");
        }
      };
    });

  }

  function needsAutoProviderProbe(payload) {
    const providers = Array.isArray(payload?.providers) ? payload.providers : [];
    if (!providers.length) return false;
    return providers.some((provider) => {
      const probeStatus = String(
        provider?.probe?.status ?? provider?.last_probe_status ?? "UNVERIFIED"
      ).toUpperCase();
      return probeStatus === "UNVERIFIED";
    });
  }

  async function loadProviderStatus(projectId = null, options = {}) {
    const autoProbe = Boolean(options?.autoProbe);
    const container = getElement("provider-cards");
    if (container) {
      container.innerHTML = '<div class="text-xs text-slate-500">Consultando estado de providers...</div>';
    }
    try {
      setProviderSelectorError("");
      const payload = await apiGet(providersStatusUrl(projectId));
      providerStatusCache = payload;
      wizardStore.setProviderSelection(payload);
      renderProviderSelector(payload);
      if (autoProbe && needsAutoProviderProbe(payload)) {
        await probeProviderStatus(projectId, { showLoading: false });
      }
      return payload;
    } catch (error) {
      providerStatusCache = null;
      if (container) {
        container.innerHTML = '<div class="text-xs text-red-600">No se pudo obtener el estado de providers.</div>';
      }
      setProviderSelectorError(error?.message || "No se pudo obtener el estado de providers.");
      throw error;
    }
  }

  async function probeProviderStatus(projectId = null, options = {}) {
    const showLoading = options?.showLoading !== false;
    const container = getElement("provider-cards");
    if (container && showLoading) {
      container.innerHTML = '<div class="text-xs text-slate-500">Ejecutando probe real de providers...</div>';
    }
    try {
      setProviderSelectorError("");
      const payload = await apiSend(providersProbeUrl(projectId), "POST", {});
      providerStatusCache = payload;
      wizardStore.setProviderSelection(payload);
      renderProviderSelector(payload);
      return payload;
    } catch (error) {
      setProviderSelectorError(error?.message || "No se pudo ejecutar el probe de providers.");
      await loadProviderStatus(projectId);
      throw error;
    }
  }

  return {
    loadProviderStatus,
    probeProviderStatus,
    saveProviderSelection,
    getStatusCache() {
      return providerStatusCache;
    },
    setStatusCache(value) {
      providerStatusCache = value;
    },
  };
}
