import {
  buildConstructionTimeline,
  buildGenerationTree,
  defaultExpandedGroupPath,
  findGenerationNode,
  formatEventTime,
  humanizePricingSource,
  normalizeConstructionPhase,
  resolveGenerationPhase,
  resolveSectionParentPath,
  sectionKey,
  statusBadgeClass,
  summarizeGenerationNode,
} from "./trace-state.js";

export function createTraceView({
  getElement,
  escapeHtml,
  formatInt,
  formatUsd,
  runtimeState,
}) {
  const COLLAPSED_GROUP_SENTINEL = "__collapsed__";

  function setText(id, value) {
    const element = getElement(id);
    if (element) element.textContent = String(value ?? "");
  }

  function setHtml(id, value) {
    const element = getElement(id);
    if (element) element.innerHTML = String(value ?? "");
  }

  function toggleHidden(id, hidden) {
    const element = getElement(id);
    if (!element) return;
    element.classList.toggle("hidden", Boolean(hidden));
  }

  function setLiveSummary(text, tone = "neutral") {
    const element = getElement("gen-live-summary");
    if (!element) return;
    element.textContent = String(text || "");
    element.className = "text-sm mt-1";
    if (tone === "ok") element.classList.add("text-green-600");
    else if (tone === "error") element.classList.add("text-red-600");
    else if (tone === "warn") element.classList.add("text-amber-700");
    else element.classList.add("text-slate-600");
  }

  function updateLiveBadge(state = "live") {
    const badge = getElement("gen-live-badge");
    if (!badge) return;
    badge.className = "inline-flex items-center rounded-full border px-3 py-1 text-xs font-extrabold";
    if (state === "ok") {
      badge.classList.add("bg-green-50", "text-green-700", "border-green-200");
      badge.innerHTML = '<span class="h-2 w-2 rounded-full bg-green-500 ring-4 ring-green-100"></span> Completado';
      return;
    }
    if (state === "error") {
      badge.classList.add("bg-red-50", "text-red-700", "border-red-200");
      badge.innerHTML = '<span class="h-2 w-2 rounded-full bg-red-500 ring-4 ring-red-100"></span> Con error';
      return;
    }
    if (state === "warn") {
      badge.classList.add("bg-amber-50", "text-amber-700", "border-amber-200");
      badge.innerHTML = '<span class="h-2 w-2 rounded-full bg-amber-500 ring-4 ring-amber-100"></span> Revisar';
      return;
    }
    badge.classList.add("bg-blue-50", "text-blue-700", "border-blue-200");
    badge.innerHTML = '<span class="h-2 w-2 rounded-full bg-blue-500 ring-4 ring-blue-100 animate-pulse"></span> En vivo';
  }

  function setTimerVisible(visible) {
    toggleHidden("gen-timer", !visible);
  }

  function setTimerSeconds(seconds) {
    setText("gen-timer-value", `${Math.max(0, Number(seconds || 0))}s`);
  }

  function clearGenerationDetail() {
    setText("gen-ai-detail-title", "Sin seccion seleccionada");
    setText("gen-ai-detail-meta", "Selecciona una seccion para auditar prompt, respuesta y tokens.");
    setText("gen-ai-detail-input", "0");
    setText("gen-ai-detail-output", "0");
    setText("gen-ai-detail-total", "0");
    setText("gen-ai-detail-duration", "-");
    setText("gen-ai-detail-provider", "-");
    setText("gen-ai-detail-model", "-");
    setText("gen-ai-detail-source", "-");
    setText("gen-ai-detail-pricing", "No disponible");
    setText("gen-ai-detail-prompt", "Aun no disponible.");
    setText("gen-ai-detail-response", "Aun no disponible.");
    const badge = getElement("gen-ai-detail-status");
    if (badge) {
      badge.className = "inline-flex items-center rounded-full border bg-slate-50 px-3 py-1 text-xs font-extrabold text-slate-700 border-slate-200";
      badge.textContent = "PENDIENTE";
    }
  }

  function reset() {
    runtimeState.setSelectedSectionKey("");
    runtimeState.setExpandedGroupPath("");
    runtimeState.setLastTraceState(null);
    runtimeState.setLastRenderedTraceCount(0);
    setLiveSummary("Preparando ejecucion...", "neutral");
    updateLiveBadge("live");
    setTimerVisible(false);
    setTimerSeconds(0);
    setText("gen-sections-progress", "Secciones 0/0");
    const progressBar = getElement("gen-sections-bar");
    if (progressBar) progressBar.style.width = "0%";
    setText("gen-queue-count", "0");
    setText("gen-done-count", "0");
    toggleHidden("gen-final-badge", true);
    toggleHidden("gen-provider-badge", true);
    toggleHidden("gen-model-badge", true);
    setText("gen-provider-name", "-");
    setText("gen-model-name", "-");
    setText("gen-token-input-total", "0");
    setText("gen-token-output-total", "0");
    setText("gen-token-total", "0");
    setText("gen-token-current-section", "-");
    setText("gen-token-current-model", "-");
    setText("gen-token-source", "Sin uso IA");
    setText("gen-token-calls", "0");
    setText("gen-base-prompt", "Aun no disponible.");
    setText("gen-ai-count", "0/0");
    setHtml("gen-ai-section-list", "");
    clearGenerationDetail();
    hideError();
    hideSuccess();
    hideConstructionRetry();
    hideConstructionReady();
    setText("construct-summary", "Transformando la salida de IA en artefactos finales del documento.");
    setText("construct-progress-count", "0/5");
    const constructBar = getElement("construct-progress-bar");
    if (constructBar) constructBar.style.width = "0%";
    const constructionBadge = getElement("construct-status-badge");
    if (constructionBadge) {
      constructionBadge.className = "inline-flex items-center rounded-full border bg-white px-3 py-1 text-xs font-extrabold text-slate-700";
      constructionBadge.textContent = "Pendiente";
    }
    setHtml("construct-task-list", "");
    setHtml("construct-trace-list", "");
    toggleHidden("construct-trace-empty", false);
  }

  function showError(message) {
    const element = getElement("gen-error");
    if (!element) return;
    runtimeState.setActiveError(String(message || ""));
    element.classList.remove("hidden");
    const detail = element.querySelector("span");
    if (detail) detail.textContent = String(message || "");
  }

  function hideError() {
    runtimeState.setActiveError("");
    toggleHidden("gen-error", true);
    const detail = getElement("gen-error")?.querySelector("span");
    if (detail) detail.textContent = "";
  }

  function showSuccess() {
    toggleHidden("gen-success", false);
  }

  function hideSuccess() {
    toggleHidden("gen-success", true);
  }

  function showRetry() {
    toggleHidden("btn-gen-retry", false);
    toggleHidden("btn-construct-retry", false);
    toggleHidden("btn-gen-cancel", true);
  }

  function hideRetry() {
    toggleHidden("btn-gen-retry", true);
    toggleHidden("btn-construct-retry", true);
    toggleHidden("btn-gen-cancel", false);
  }

  function hideConstructionRetry() {
    toggleHidden("btn-construct-retry", true);
  }

  function showConstructionReady() {
    toggleHidden("btn-go-construction", false);
    toggleHidden("btn-step6-downloads", false);
  }

  function hideConstructionReady() {
    toggleHidden("btn-go-construction", true);
    toggleHidden("btn-step6-downloads", true);
    toggleHidden("btn-gen-downloads", true);
  }

  function renderTokenUsage(projectSnapshot) {
    const usage = projectSnapshot?.progress?.tokenUsage || projectSnapshot?.token_usage || {};
    const lastCall = usage?.last_call || {};
    const currentSection = usage?.current_section || {};
    const currentSectionLabel = currentSection.section_path || currentSection.section_title || "-";
    const providerLabel = String(lastCall.provider || projectSnapshot?.progress?.provider || "").trim();
    const modelLabel = String(lastCall.model || "").trim();
    const callsTotal = Number(usage?.calls_total || 0);
    const reportedCalls = Number(usage?.reported_calls || 0);
    const estimatedCalls = Number(usage?.estimated_calls || 0);

    let sourceLabel = "Sin uso IA";
    if (callsTotal > 0 && reportedCalls > 0 && estimatedCalls > 0) sourceLabel = "Mixto";
    else if (callsTotal > 0 && estimatedCalls > 0) sourceLabel = "Estimado";
    else if (callsTotal > 0) sourceLabel = "Real";

    setText("gen-token-input-total", formatInt(usage?.input_tokens_total || 0));
    setText("gen-token-output-total", formatInt(usage?.output_tokens_total || 0));
    setText("gen-token-total", formatInt(usage?.total_tokens || 0));
    setText("gen-token-current-section", currentSectionLabel);
    setText("gen-token-current-model", modelLabel || "-");
    setText("gen-token-source", sourceLabel);
    setText("gen-token-calls", formatInt(callsTotal));

    if (providerLabel) {
      toggleHidden("gen-provider-badge", false);
      setText("gen-provider-name", providerLabel);
    } else {
      toggleHidden("gen-provider-badge", true);
      setText("gen-provider-name", "-");
    }
    if (modelLabel) {
      toggleHidden("gen-model-badge", false);
      setText("gen-model-name", modelLabel);
    } else {
      toggleHidden("gen-model-badge", true);
      setText("gen-model-name", "-");
    }
  }

  function renderTreeNodes(nodes, selectedKey, expandedGroupPath, phase) {
    return nodes.map((node) => {
      const summary = node.summary || summarizeGenerationNode(node);
      const badge = statusBadgeClass(summary.status);
      const hasChildren = Array.isArray(node.children) && node.children.length > 0;
      const isExpanded = hasChildren
        && String(expandedGroupPath || "") !== COLLAPSED_GROUP_SENTINEL
        && String(expandedGroupPath || "").startsWith(String(node.path || ""));
      const isSelected = String(selectedKey || "") === String(node.key || "");
      const latestSection = summary.latestSection || node.selfSection || {};
      const detail = hasChildren
        ? `${formatInt(summary.completedCount)}/${formatInt(summary.totalCount)} subsecciones`
        : `${latestSection.provider || "-"} · ${latestSection.model || "-"} · ${formatInt(summary.total_tokens)} tokens`;
      const indent = Math.max(0, Number(node.depth || 1) - 1) * 16;

      return `
        <div class="space-y-2.5">
          <button
            class="w-full text-left rounded-2xl border p-3.5 transition ${isSelected ? "border-slate-900 bg-slate-50 shadow-sm" : "bg-white hover:shadow-sm"}"
            data-ai-node-key="${escapeHtml(node.key)}"
            data-ai-node-kind="${hasChildren ? "group" : "leaf"}"
            data-ai-node-path="${escapeHtml(node.path)}"
            style="margin-left:${indent}px"
          >
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0 flex-1">
                <div class="flex items-center gap-2 text-xs text-slate-400 font-semibold">
                  ${hasChildren ? `<span class="inline-flex h-5 w-5 items-center justify-center rounded-full border border-slate-200 text-slate-500">${isExpanded ? "-" : "+"}</span>` : '<span class="inline-flex h-5 w-5 items-center justify-center rounded-full border border-slate-200 text-slate-400">*</span>'}
                  <span>${hasChildren ? "Bloque" : "Subseccion"}</span>
                </div>
                <div class="mt-1 font-semibold text-slate-900 leading-snug break-words">${escapeHtml(node.label || "Sin nombre")}</div>
                <div class="mt-1 text-xs text-slate-500 leading-relaxed break-words">${escapeHtml(detail || "Pendiente")}</div>
              </div>
              <span class="inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-extrabold ${badge.wrap}">
                ${badge.label}
              </span>
            </div>
          </button>
          ${hasChildren && isExpanded
            ? `<div class="space-y-2.5">${renderTreeNodes(node.children, selectedKey, expandedGroupPath, phase)}</div>`
            : ""}
        </div>
      `;
    }).join("");
  }

  function renderGenerationDetail(selectedNode, phase) {
    const selectedSummary = summarizeGenerationNode(selectedNode);
    const selectedSection = selectedNode?.selfSection || selectedSummary.latestSection || phase.sections[0] || {};
    const isGroupSelection = Array.isArray(selectedNode?.children) && selectedNode.children.length > 0;
    const badge = statusBadgeClass(isGroupSelection ? selectedSummary.status : selectedSection.status);

    setText(
      "gen-ai-detail-title",
      isGroupSelection
        ? (selectedNode?.path || selectedNode?.label || "Bloque")
        : (selectedSection.section_path || selectedSection.section_title || "Sin nombre"),
    );
    setText(
      "gen-ai-detail-meta",
      isGroupSelection
        ? `Bloque jerarquico · ${formatInt(selectedSummary.completedCount)}/${formatInt(selectedSummary.totalCount)} subsecciones completadas`
        : `Seccion ${selectedSection.section_id || "-"} · Padre: ${selectedSection.parent_section_path || "raiz"} · Intentos: ${formatInt(selectedSection.attempt_count || 0)}`,
    );

    const detailStatus = getElement("gen-ai-detail-status");
    if (detailStatus) {
      detailStatus.className = `inline-flex items-center rounded-full border px-3 py-1 text-xs font-extrabold ${badge.wrap}`;
      detailStatus.textContent = badge.label;
    }

    setText("gen-ai-detail-input", formatInt(isGroupSelection ? selectedSummary.input_tokens : selectedSection.input_tokens || 0));
    setText("gen-ai-detail-output", formatInt(isGroupSelection ? selectedSummary.output_tokens : selectedSection.output_tokens || 0));
    setText("gen-ai-detail-total", formatInt(isGroupSelection ? selectedSummary.total_tokens : selectedSection.total_tokens || 0));
    const durationMs = isGroupSelection ? selectedSummary.duration_ms : selectedSection.duration_ms || 0;
    setText("gen-ai-detail-duration", durationMs ? `${formatInt(durationMs)} ms` : "-");
    setText(
      "gen-ai-detail-provider",
      isGroupSelection ? (selectedSummary.latestSection?.provider || "-") : (selectedSection.provider || "-"),
    );
    setText(
      "gen-ai-detail-model",
      isGroupSelection ? (selectedSummary.latestSection?.model || "-") : (selectedSection.model || "-"),
    );
    setText(
      "gen-ai-detail-source",
      isGroupSelection ? (selectedSummary.source || "-") : (selectedSection.source || "-"),
    );
    setText(
      "gen-ai-detail-pricing",
      humanizePricingSource(isGroupSelection ? selectedSummary.pricing_source : selectedSection.pricing_source),
    );
    setText(
      "gen-ai-detail-prompt",
      isGroupSelection
        ? `Este bloque agrupa ${formatInt(selectedSummary.totalCount)} subsecciones.\nSelecciona una subseccion hija para ver el prompt exacto enviado por la IA.\n\nSubsecciones:\n${(selectedNode?.children || []).map((item) => `- ${item.label}`).join("\n") || "- Sin hijas registradas"}`
        : (selectedSection.prompt_sent || "Aun no disponible."),
    );
    setText(
      "gen-ai-detail-response",
      isGroupSelection
        ? `Resumen del bloque:\n${(selectedNode?.children || []).map((item) => {
          const childSummary = item.summary || summarizeGenerationNode(item);
          const childBadge = statusBadgeClass(childSummary.status);
          return `- ${item.label}: ${childBadge.label} (${formatInt(childSummary.completedCount)}/${formatInt(childSummary.totalCount)})`;
        }).join("\n") || "Sin subsecciones registradas."}`
        : (selectedSection.ai_output || "Aun no disponible."),
    );
  }

  function renderAIGeneration(projectSnapshot) {
    const phase = resolveGenerationPhase(projectSnapshot);
    const treeRoot = buildGenerationTree(phase.sections || []);

    setText("gen-base-prompt", phase.basePrompt || "Aun no disponible.");
    setText("gen-ai-count", `${formatInt(phase.completedSections)}/${formatInt(phase.totalSections)}`);
    setHtml(
      "gen-sections-progress",
      phase.totalSections > 0
        ? `Secciones <b>${formatInt(Math.min(phase.completedSections, phase.totalSections))}/${formatInt(phase.totalSections)}</b>${phase.currentPath ? ` · ${escapeHtml(phase.currentPath)}` : ""}`
        : "Secciones <b>0/0</b>",
    );
    const width = phase.totalSections > 0
      ? Math.min(100, Math.round((Math.min(phase.completedSections, phase.totalSections) / phase.totalSections) * 100))
      : 0;
    const progressBar = getElement("gen-sections-bar");
    if (progressBar) progressBar.style.width = `${width}%`;
    setText("gen-queue-count", String(Math.max(0, phase.totalSections - phase.completedSections)));
    setText("gen-done-count", String(Math.max(0, phase.completedSections)));
    toggleHidden("gen-final-badge", !(phase.totalSections > 0 && phase.completedSections >= phase.totalSections));

    if (!phase.sections.length) {
      setHtml(
        "gen-ai-section-list",
        '<div class="rounded-2xl border border-dashed p-4 text-sm text-slate-500">Aun no hay secciones registradas por la IA.</div>',
      );
      runtimeState.setSelectedSectionKey("");
      runtimeState.setExpandedGroupPath("");
      clearGenerationDetail();
      return;
    }

    if (!runtimeState.getExpandedGroupPath()) {
      runtimeState.setExpandedGroupPath(defaultExpandedGroupPath(treeRoot, phase));
    }

    if (!findGenerationNode(treeRoot, runtimeState.getSelectedSectionKey())) {
      const preferred = phase.sections.find((item) => String(item.status || "").toLowerCase() === "generating")
        || phase.sections.find((item) => {
          const safe = String(item.status || "").toLowerCase();
          return safe === "ok" || safe === "done" || safe === "completed";
        })
        || phase.sections[0];
      runtimeState.setSelectedSectionKey(sectionKey(preferred));
      runtimeState.setExpandedGroupPath(resolveSectionParentPath(preferred) || String(preferred.section_path || ""));
    }

    setHtml(
      "gen-ai-section-list",
      renderTreeNodes(treeRoot.children || [], runtimeState.getSelectedSectionKey(), runtimeState.getExpandedGroupPath(), phase),
    );

    getElement("gen-ai-section-list")?.querySelectorAll("[data-ai-node-key]").forEach((button) => {
      button.addEventListener("click", () => {
        const selectedKey = String(button.getAttribute("data-ai-node-key") || "");
        const nodeKind = String(button.getAttribute("data-ai-node-kind") || "");
        const nodePath = String(button.getAttribute("data-ai-node-path") || "");
        runtimeState.setSelectedSectionKey(selectedKey);
        if (nodeKind === "group") {
          const nextExpandedPath = runtimeState.getExpandedGroupPath() === nodePath
            ? (resolveSectionParentPath({ section_path: nodePath }) || COLLAPSED_GROUP_SENTINEL)
            : nodePath;
          runtimeState.setExpandedGroupPath(
            nextExpandedPath,
          );
        } else {
          runtimeState.setExpandedGroupPath(resolveSectionParentPath({ section_path: nodePath }) || nodePath);
        }
        renderAIGeneration(projectSnapshot);
      });
    });

    const selectedNode = findGenerationNode(treeRoot, runtimeState.getSelectedSectionKey())
      || findGenerationNode(treeRoot, `group:${defaultExpandedGroupPath(treeRoot, phase)}`)
      || (treeRoot.children || [])[0];
    renderGenerationDetail(selectedNode, phase);
  }

  function renderConstruction(projectSnapshot) {
    const phase = normalizeConstructionPhase(projectSnapshot);
    const tasks = phase.tasks;
    const doneCount = tasks.filter((item) => String(item.status || "") === "done").length;
    const totalCount = tasks.length || 0;
    const width = totalCount > 0 ? Math.min(100, Math.round((doneCount / totalCount) * 100)) : 0;
    const badge = statusBadgeClass(
      phase.status === "completed" ? "done" : phase.status === "running" ? "generating" : phase.status,
    );

    setText("construct-progress-count", `${doneCount}/${totalCount}`);
    const progressBar = getElement("construct-progress-bar");
    if (progressBar) progressBar.style.width = `${width}%`;
    const statusBadge = getElement("construct-status-badge");
    if (statusBadge) {
      statusBadge.className = `inline-flex items-center rounded-full border px-3 py-1 text-xs font-extrabold ${badge.wrap}`;
      statusBadge.textContent = badge.label;
    }

    if (phase.status === "completed") {
      setText("construct-summary", "El contenido ya fue transformado en DOCX/PDF y validado para descarga.");
    } else if (phase.status === "running") {
      setText("construct-summary", "Armando el documento final a partir de la salida validada de IA.");
    } else if (phase.status === "error") {
      setText("construct-summary", "La construccion se detuvo por un error; revisa el timeline tecnico.");
    } else {
      setText("construct-summary", "Aun no inicia la fase de construccion.");
    }

    setHtml(
      "construct-task-list",
      tasks.map((item) => {
        const itemBadge = statusBadgeClass(item.status);
        return `
          <div class="rounded-2xl border bg-white p-3">
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0">
                <div class="font-semibold text-slate-900">${escapeHtml(item.label || item.id || "Tarea")}</div>
                <div class="mt-1 text-xs text-slate-500">${escapeHtml(item.detail || "Pendiente")}</div>
              </div>
              <span class="inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-extrabold ${itemBadge.wrap}">
                ${itemBadge.label}
              </span>
            </div>
          </div>
        `;
      }).join("") || '<div class="rounded-2xl border border-dashed p-4 text-sm text-slate-500">Aun no hay tareas de construccion registradas.</div>',
    );

    const constructionEvents = buildConstructionTimeline(projectSnapshot, phase);
    if (!constructionEvents.length) {
      setHtml("construct-trace-list", "");
      toggleHidden("construct-trace-empty", false);
    } else {
      toggleHidden("construct-trace-empty", true);
      setHtml(
        "construct-trace-list",
        constructionEvents.map((event) => {
          const eventBadge = statusBadgeClass(event.status);
          return `
            <div class="rounded-2xl border bg-white p-3">
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0">
                  <div class="text-xs text-slate-400">${escapeHtml(formatEventTime(event.ts))}</div>
                  <div class="mt-1 font-semibold text-slate-900">${escapeHtml(event.title || "Evento")}</div>
                  <div class="mt-1 text-xs text-slate-500">${escapeHtml(event.detail || "")}</div>
                </div>
                <span class="inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-extrabold ${eventBadge.wrap}">
                  ${eventBadge.label}
                </span>
              </div>
            </div>
          `;
        }).join(""),
      );
    }

    toggleHidden("btn-go-construction", phase.status === "idle");
    toggleHidden("btn-step6-downloads", !String(projectSnapshot?.status || "").startsWith("completed"));
  }

  function render(projectSnapshot) {
    const activeError = runtimeState.getActiveError();
    if (activeError) showError(activeError);
    else hideError();
    renderTokenUsage(projectSnapshot);
    renderAIGeneration(projectSnapshot);
    renderConstruction(projectSnapshot);
  }

  return {
    reset,
    render,
    showError,
    hideError,
    showRetry,
    hideRetry,
    showSuccess,
    hideSuccess,
    setLiveSummary,
    updateLiveBadge,
    setTimerVisible,
    setTimerSeconds,
    showConstructionReady,
    hideConstructionReady,
    hideConstructionRetry,
  };
}
