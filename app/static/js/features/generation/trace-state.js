export const GEN_POLL_INTERVAL = 1000;
export const GEN_MISSING_PROJECT_MAX_POLLS = 5;
export const GEN_SUCCESS_STATUSES = ["completed", "completed_with_incidents", "simulated"];
export const GEN_FAIL_STATUSES = [
  "failed",
  "render_failed",
  "n8n_failed",
  "generation_failed",
  "ai_failed",
  "blocked",
  "timeout",
  "cancel_requested",
];

function asArray(value) {
  return Array.isArray(value) ? value : [];
}

function asObject(value) {
  return value && typeof value === "object" ? value : {};
}

export function sectionKey(section) {
  return String(
    section?.section_id
    || section?.sectionId
    || section?.section_path
    || section?.sectionPath
    || section?.path
    || ""
  ).trim();
}

export function sectionTitleFromPath(path) {
  const parts = sectionPathParts(path);
  return parts.length ? parts[parts.length - 1] : "";
}

export function sectionPathParts(path) {
  return String(path || "").split("/").map((item) => item.trim()).filter(Boolean);
}

export function resolveSectionParentPath(section) {
  const explicitParent = String(
    section?.parent_section_path
    || section?.sectionParentPath
    || ""
  ).trim();
  if (explicitParent) return explicitParent;
  const parts = sectionPathParts(section?.section_path || section?.path || "");
  if (parts.length <= 1) return "";
  return parts.slice(0, -1).join("/");
}

function resolveSectionLevel(section) {
  const explicitLevel = Number(section?.section_level || section?.sectionLevel || 0);
  if (Number.isFinite(explicitLevel) && explicitLevel > 0) return explicitLevel;
  return Math.max(1, sectionPathParts(section?.section_path || section?.path || "").length);
}

function resolveSectionOrder(section, fallback = null) {
  const explicitOrder = Number(section?.section_order ?? section?.sectionOrder);
  if (Number.isFinite(explicitOrder) && explicitOrder >= 0) return explicitOrder;
  return Number.isFinite(fallback) && fallback >= 0 ? fallback : null;
}

function sortGenerationSections(sections) {
  return [...asArray(sections)].sort((left, right) => {
    const leftOrder = resolveSectionOrder(left, Number.MAX_SAFE_INTEGER);
    const rightOrder = resolveSectionOrder(right, Number.MAX_SAFE_INTEGER);
    if (leftOrder !== rightOrder) return leftOrder - rightOrder;

    const leftLevel = resolveSectionLevel(left);
    const rightLevel = resolveSectionLevel(right);
    if (leftLevel !== rightLevel) return leftLevel - rightLevel;

    return String(left?.section_path || left?.path || "").localeCompare(
      String(right?.section_path || right?.path || ""),
      "es",
    );
  });
}

function stringifySectionOutput(value) {
  if (value == null) return "";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch (_) {
    return String(value);
  }
}

function mergeGenerationSection(baseSection, incomingSection) {
  const base = asObject(baseSection);
  const incoming = asObject(incomingSection);
  const statusRank = {
    pending: 0,
    generating: 1,
    running: 1,
    ok: 2,
    done: 2,
    completed: 2,
    error: 3,
    failed: 3,
  };

  const pickString = (...values) => values.find((item) => String(item || "").trim()) || "";
  const pickNumber = (...values) => {
    const numeric = values
      .map((item) => Number(item || 0))
      .filter((item) => Number.isFinite(item) && item > 0);
    return numeric.length ? Math.max(...numeric) : 0;
  };

  const baseStatus = String(base.status || "").toLowerCase();
  const incomingStatus = String(incoming.status || "").toLowerCase();
  const mergedStatus = (statusRank[incomingStatus] || 0) >= (statusRank[baseStatus] || 0)
    ? (incoming.status || base.status || "pending")
    : (base.status || incoming.status || "pending");

  return {
    ...base,
    ...incoming,
    section_id: pickString(base.section_id, base.sectionId, incoming.section_id, incoming.sectionId),
    section_path: pickString(base.section_path, base.path, incoming.section_path, incoming.path),
    section_title: pickString(base.section_title, incoming.section_title) || sectionTitleFromPath(pickString(base.section_path, base.path, incoming.section_path, incoming.path)),
    parent_section_path: pickString(
      base.parent_section_path,
      base.sectionParentPath,
      incoming.parent_section_path,
      incoming.sectionParentPath,
    ),
    section_order: resolveSectionOrder(
      { section_order: base.section_order ?? base.sectionOrder },
      resolveSectionOrder({ section_order: incoming.section_order ?? incoming.sectionOrder }),
    ),
    section_level: pickNumber(base.section_level, base.sectionLevel, incoming.section_level, incoming.sectionLevel) || 1,
    status: mergedStatus,
    prompt_sent: pickString(base.prompt_sent, incoming.prompt_sent),
    ai_output: pickString(base.ai_output, incoming.ai_output),
    input_tokens: pickNumber(base.input_tokens, incoming.input_tokens),
    output_tokens: pickNumber(base.output_tokens, incoming.output_tokens),
    total_tokens: pickNumber(base.total_tokens, incoming.total_tokens),
    estimated_cost_usd: Math.max(Number(base.estimated_cost_usd || 0), Number(incoming.estimated_cost_usd || 0), 0),
    pricing_source: pickString(base.pricing_source, incoming.pricing_source) || "unavailable",
    pricing_fetched_at: pickString(base.pricing_fetched_at, incoming.pricing_fetched_at),
    currency: pickString(base.currency, incoming.currency) || "USD",
    pricing_available: Boolean(base.pricing_available || incoming.pricing_available),
    provider: pickString(base.provider, incoming.provider),
    model: pickString(base.model, incoming.model),
    duration_ms: pickNumber(base.duration_ms, incoming.duration_ms),
    estimated: Boolean(base.estimated || incoming.estimated),
    source: pickString(base.source, incoming.source),
    attempt_count: pickNumber(base.attempt_count, incoming.attempt_count),
    error: pickString(base.error, incoming.error),
  };
}

function mergeGenerationSections(...collections) {
  const sectionsByKey = new Map();
  collections.flat().forEach((item) => {
    if (!item || typeof item !== "object") return;
    const key = sectionKey(item);
    if (!key) return;
    const existing = sectionsByKey.get(key);
    sectionsByKey.set(key, existing ? mergeGenerationSection(existing, item) : item);
  });
  return sortGenerationSections(Array.from(sectionsByKey.values()));
}

function normalizePlannedSection(item, index) {
  const normalized = {
    section_id: String(item?.section_id || item?.sectionId || ""),
    section_path: String(item?.section_path || item?.sectionPath || item?.path || ""),
    section_title: String(item?.section_title || item?.sectionTitle || ""),
    parent_section_path: String(item?.parent_section_path || item?.sectionParentPath || ""),
    section_order: resolveSectionOrder(item, index),
    section_level: Number(item?.section_level || item?.sectionLevel || 1) || 1,
    status: String(item?.status || "pending"),
    total_tokens: Number(item?.total_tokens || 0),
    input_tokens: Number(item?.input_tokens || 0),
    output_tokens: Number(item?.output_tokens || 0),
    estimated_cost_usd: Number(item?.estimated_cost_usd || 0),
    pricing_source: String(item?.pricing_source || "unavailable"),
    pricing_fetched_at: String(item?.pricing_fetched_at || ""),
    currency: String(item?.currency || "USD"),
    pricing_available: Boolean(item?.pricing_available),
    provider: String(item?.provider || ""),
    model: String(item?.model || ""),
    prompt_sent: String(item?.prompt_sent || item?.prompt || ""),
    ai_output: stringifySectionOutput(item?.ai_output || item?.content || ""),
    attempt_count: Number(item?.attempt_count || 0),
    duration_ms: Number(item?.duration_ms || 0),
    estimated: Boolean(item?.estimated),
    source: String(item?.source || ""),
  };
  if (!normalized.section_title) {
    normalized.section_title = sectionTitleFromPath(normalized.section_path);
  }
  if (!normalized.parent_section_path) {
    normalized.parent_section_path = resolveSectionParentPath(normalized);
  }
  return normalized;
}

function normalizeAiResultSection(item, index, projectStatus = "") {
  return {
    section_id: String(item?.sectionId || item?.section_id || ""),
    section_path: String(item?.path || item?.section_path || ""),
    section_title: String(item?.title || item?.section_title || "") || sectionTitleFromPath(item?.path || item?.section_path || ""),
    parent_section_path: resolveSectionParentPath(item),
    section_order: resolveSectionOrder(item, index),
    section_level: resolveSectionLevel(item),
    status: GEN_SUCCESS_STATUSES.includes(String(projectStatus || "")) ? "ok" : "pending",
    prompt_sent: String(item?.prompt_sent || item?.prompt || ""),
    ai_output: stringifySectionOutput(item?.content || item?.ai_output || ""),
    input_tokens: 0,
    output_tokens: 0,
    total_tokens: 0,
    estimated_cost_usd: 0,
    pricing_source: "unavailable",
    pricing_fetched_at: "",
    currency: "USD",
    pricing_available: false,
    provider: String(item?.provider || ""),
    model: String(item?.model || ""),
    duration_ms: 0,
    estimated: false,
    source: "",
    attempt_count: 0,
  };
}

export function resolveGenerationPhase(projectSnapshot) {
  const project = asObject(projectSnapshot);
  const phase = asObject(project.generation_phase);
  const planned = asArray(phase.planned_sections).map((item, index) => normalizePlannedSection(item, index));
  const directSections = asArray(phase.sections).map((item, index) => normalizePlannedSection({
    ...item,
    status: item?.status || "pending",
    prompt_sent: item?.prompt_sent || "",
    ai_output: item?.ai_output || "",
    input_tokens: item?.input_tokens || 0,
    output_tokens: item?.output_tokens || 0,
    total_tokens: item?.total_tokens || 0,
    estimated_cost_usd: item?.estimated_cost_usd || 0,
    pricing_source: item?.pricing_source || "unavailable",
    provider: item?.provider || "",
    model: item?.model || "",
    duration_ms: item?.duration_ms || 0,
    source: item?.source || "",
    attempt_count: item?.attempt_count || 0,
  }, index));
  const aiSections = asArray(project.ai_result?.sections).map((item, index) => normalizeAiResultSection(item, planned.length + index, project.status));

  const mergedSections = mergeGenerationSections(planned, directSections, aiSections);
  const currentPath = String(
    phase.current_path
    || phase.current_section_path
    || project.progress?.currentPath
    || mergedSections.find((item) => String(item.status || "").toLowerCase() === "generating")?.section_path
    || ""
  ).trim();
  const totalSections = Math.max(
    Number(phase.total_sections || 0),
    Number(project.progress?.total || 0),
    planned.length,
    mergedSections.length,
  );
  const completedSections = mergedSections.filter((item) => {
    const safe = String(item.status || "").toLowerCase();
    return safe === "ok" || safe === "done" || safe === "completed";
  }).length;

  return {
    status: String(phase.status || (mergedSections.length ? "running" : "idle")),
    basePrompt: String(phase.base_prompt || project.prompt_template || ""),
    totalSections,
    completedSections,
    currentPath,
    sections: mergedSections,
  };
}

function collectGenerationNodeSections(node) {
  if (!node || typeof node !== "object") return [];
  const sections = [];
  if (node.selfSection && typeof node.selfSection === "object") sections.push(node.selfSection);
  asArray(node.children).forEach((child) => {
    sections.push(...collectGenerationNodeSections(child));
  });
  return sections;
}

function aggregateGenerationSource(sections) {
  const sources = new Set(
    sections
      .map((item) => String(item?.source || "").trim())
      .filter(Boolean),
  );
  if (!sources.size) return "-";
  if (sources.has("mixed") || sources.size > 1) return "mixed";
  return Array.from(sources)[0];
}

function pricingSourceLabel(values) {
  const sources = new Set(
    asArray(values)
      .map((item) => String(item || "").trim().toLowerCase())
      .filter(Boolean),
  );
  if (!sources.size) return "unavailable";
  if (sources.has("mixed") || sources.size > 1) return "mixed";
  return Array.from(sources)[0];
}

export function humanizePricingSource(value) {
  const safe = String(value || "").trim().toLowerCase();
  if (safe === "updated") return "Actualizado";
  if (safe === "cached") return "Cacheado";
  if (safe === "mixed") return "Mixto";
  return "No disponible";
}

export function statusBadgeClass(status) {
  const safe = String(status || "").toLowerCase();
  if (safe === "ok" || safe === "done" || safe === "completed") {
    return {
      wrap: "bg-emerald-50 text-emerald-700 border-emerald-200",
      label: "OK",
    };
  }
  if (safe === "generating" || safe === "running") {
    return {
      wrap: "bg-blue-50 text-blue-700 border-blue-200",
      label: "GENERANDO",
    };
  }
  if (safe === "error" || safe === "failed") {
    return {
      wrap: "bg-red-50 text-red-700 border-red-200",
      label: "ERROR",
    };
  }
  return {
    wrap: "bg-slate-50 text-slate-600 border-slate-200",
    label: "PENDIENTE",
  };
}

export function summarizeGenerationNode(node) {
  const sections = collectGenerationNodeSections(node);
  const statuses = sections.map((item) => String(item?.status || "").toLowerCase());
  const completedCount = statuses.filter((item) => ["ok", "done", "completed"].includes(item)).length;
  const errorCount = statuses.filter((item) => ["error", "failed"].includes(item)).length;
  const generatingCount = statuses.filter((item) => ["generating", "running"].includes(item)).length;
  let status = "pending";
  if (errorCount > 0) status = "error";
  else if (generatingCount > 0 || (completedCount > 0 && completedCount < sections.length)) status = "generating";
  else if (sections.length > 0 && completedCount === sections.length) status = "ok";

  const latestSection = [...sections]
    .reverse()
    .find((item) => item && (item.provider || item.model || item.ai_output || item.prompt_sent))
    || sections[sections.length - 1]
    || null;

  return {
    status,
    totalCount: sections.length,
    completedCount,
    input_tokens: sections.reduce((sum, item) => sum + Number(item?.input_tokens || 0), 0),
    output_tokens: sections.reduce((sum, item) => sum + Number(item?.output_tokens || 0), 0),
    total_tokens: sections.reduce((sum, item) => sum + Number(item?.total_tokens || 0), 0),
    estimated_cost_usd: sections.reduce((sum, item) => sum + Number(item?.estimated_cost_usd || 0), 0),
    duration_ms: sections.reduce((sum, item) => sum + Number(item?.duration_ms || 0), 0),
    attempt_count: sections.reduce((sum, item) => sum + Number(item?.attempt_count || 0), 0),
    latestSection,
    source: aggregateGenerationSource(sections),
    pricing_source: pricingSourceLabel(sections.map((item) => item?.pricing_source)),
  };
}

export function buildGenerationTree(sections) {
  const orderedSections = sortGenerationSections(sections);
  const root = {
    key: "__root__",
    path: "",
    label: "",
    depth: 0,
    children: [],
    childMap: new Map(),
    selfSection: null,
    order: 0,
  };

  orderedSections.forEach((rawSection, index) => {
    if (!rawSection || typeof rawSection !== "object") return;
    const section = {
      ...rawSection,
      section_path: String(rawSection.section_path || rawSection.path || "").trim(),
      section_title: String(rawSection.section_title || sectionTitleFromPath(rawSection.section_path || rawSection.path || "")).trim(),
      parent_section_path: resolveSectionParentPath(rawSection),
      section_order: resolveSectionOrder(rawSection, index),
      section_level: resolveSectionLevel(rawSection),
    };
    const parts = sectionPathParts(section.section_path);
    if (!parts.length) return;
    const sectionOrder = resolveSectionOrder(section, index) ?? index;

    let parentNode = root;
    parts.forEach((part, depthIndex) => {
      const currentPath = parts.slice(0, depthIndex + 1).join("/");
      let currentNode = parentNode.childMap.get(currentPath);
      if (!currentNode) {
        currentNode = {
          key: `group:${currentPath}`,
          path: currentPath,
          label: part,
          depth: depthIndex + 1,
          children: [],
          childMap: new Map(),
          selfSection: null,
          order: sectionOrder,
        };
        parentNode.childMap.set(currentPath, currentNode);
        parentNode.children.push(currentNode);
      }
      const currentOrder = Number.isFinite(Number(currentNode.order)) ? Number(currentNode.order) : sectionOrder;
      currentNode.order = Math.min(currentOrder, sectionOrder);
      if (depthIndex === parts.length - 1) {
        currentNode.selfSection = currentNode.selfSection
          ? mergeGenerationSection(currentNode.selfSection, section)
          : section;
      }
      parentNode = currentNode;
    });
  });

  const finalize = (node) => {
    node.children.sort((left, right) => {
      const byOrder = resolveSectionOrder({ section_order: left.order }, Number.MAX_SAFE_INTEGER)
        - resolveSectionOrder({ section_order: right.order }, Number.MAX_SAFE_INTEGER);
      if (byOrder !== 0) return byOrder;
      return String(left.label || "").localeCompare(String(right.label || ""), "es");
    });
    node.children.forEach((child) => {
      finalize(child);
      child.summary = summarizeGenerationNode(child);
    });
    return node;
  };

  return finalize(root);
}

export function findGenerationNode(node, key) {
  if (!node || !key) return null;
  if (String(node.key || "") === String(key)) return node;
  if (node.selfSection && sectionKey(node.selfSection) === String(key)) return node;
  for (const child of asArray(node.children)) {
    const found = findGenerationNode(child, key);
    if (found) return found;
  }
  return null;
}

export function defaultExpandedGroupPath(treeRoot, phase) {
  const currentSection = asArray(phase.sections).find((item) => String(item.status || "").toLowerCase() === "generating")
    || asArray(phase.sections).find((item) => String(item.section_path || "") === String(phase.currentPath || ""))
    || asArray(phase.sections).find((item) => {
      const safe = String(item.status || "").toLowerCase();
      return safe === "ok" || safe === "done" || safe === "completed";
    })
    || asArray(phase.sections)[0];
  if (!currentSection) return "";
  return resolveSectionParentPath(currentSection) || String(currentSection.section_path || "");
}

export function normalizeConstructionPhase(projectSnapshot) {
  const phase = asObject(projectSnapshot?.construction_phase);
  return {
    status: String(phase.status || "idle"),
    currentTask: String(phase.current_task || ""),
    tasks: asArray(phase.tasks).filter((item) => item && typeof item === "object"),
  };
}

function constructionEventKey(event) {
  const step = String(event?.step || "").toLowerCase();
  if (step === "project.status.ai_received") return "handoff";
  if (step.startsWith("gicatesis.payload")) return "payload";
  if (step.startsWith("gicatesis.render.docx")) return "render_docx";
  if (step.startsWith("gicatesis.render.pdf")) return "render_pdf";
  if (step.includes("validation")) return "final_validation";
  return `${step}:${String(event?.title || "").trim()}`;
}

export function buildConstructionTimeline(projectSnapshot, phase) {
  const events = asArray(projectSnapshot?.events);
  const relevantEvents = events.filter((event) => {
    const step = String(event?.step || "").toLowerCase();
    return step.startsWith("gicatesis.") || step.includes("render") || step === "project.status.ai_received";
  });

  const latestEventByKey = new Map();
  relevantEvents.forEach((event, index) => {
    if (!event || typeof event !== "object") return;
    latestEventByKey.set(constructionEventKey(event), { ...event, _order: index });
  });

  const timeline = [];
  const taskOrder = ["handoff", "payload", "render_docx", "render_pdf", "final_validation"];
  const taskAlias = {
    handoff: {
      label: "Contenido IA validado",
      detail: "La generacion IA termino y el contenido validado quedo listo para construir el documento.",
    },
    payload: {
      label: "Payload a GicaTesis",
      detail: "Payload validado y enviado a GicaTesis.",
    },
    render_docx: {
      label: "Render DOCX",
      detail: "Construccion del DOCX final.",
    },
    render_pdf: {
      label: "Render PDF",
      detail: "Construccion del PDF final.",
    },
    final_validation: {
      label: "Validacion final",
      detail: "DOCX y PDF generados y validados para descarga.",
    },
  };

  taskOrder.forEach((taskId, order) => {
    const task = asArray(phase?.tasks).find((item) => String(item?.id || "") === taskId);
    const event = latestEventByKey.get(taskId);
    const status = String(task?.status || event?.status || "pending").toLowerCase();
    if (status === "pending") return;
    timeline.push({
      ts: task?.updated_at || event?.ts || "",
      status,
      title: String(event?.title || task?.label || taskAlias[taskId]?.label || "Evento"),
      detail: String(event?.detail || task?.detail || taskAlias[taskId]?.detail || ""),
      _order: Number(event?._order ?? order),
    });
  });

  return timeline.sort((left, right) => {
    const leftOrder = Number(left?._order ?? 0);
    const rightOrder = Number(right?._order ?? 0);
    return leftOrder - rightOrder;
  });
}

export function formatEventTime(ts) {
  if (!ts) return "--:--";
  const parsed = new Date(ts);
  if (Number.isNaN(parsed.getTime())) return "--:--";
  return parsed.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function buildArtifacts(project) {
  const runId = project?.run_id || "";
  const artifacts = asArray(project?.artifacts);
  const artifactDocx = artifacts.find((item) => item?.type === "docx")?.downloadUrl;
  const artifactPdf = artifacts.find((item) => item?.type === "pdf")?.downloadUrl;
  const hasLocalOutput = Boolean(project?.output_file);
  const hasLocalPdf = Boolean(project?.pdf_file);
  const fallbackDocx = hasLocalOutput
    ? `/api/download/${encodeURIComponent(project.id)}`
    : `/api/sim/download/docx?projectId=${encodeURIComponent(project.id)}${runId ? `&runId=${encodeURIComponent(runId)}` : ""}`;
  const fallbackPdf = hasLocalPdf
    ? `/api/download/${encodeURIComponent(project.id)}/pdf`
    : `/api/sim/download/pdf?projectId=${encodeURIComponent(project.id)}${runId ? `&runId=${encodeURIComponent(runId)}` : ""}`;
  return {
    projectId: project?.id || "",
    runId,
    artifacts: [
      { type: "docx", downloadUrl: artifactDocx || fallbackDocx },
      { type: "pdf", downloadUrl: artifactPdf || fallbackPdf },
    ],
  };
}

export function createGenerationRuntimeState() {
  const state = {
    cancelled: false,
    preparing: false,
    timerHandle: null,
    elapsed: 0,
    selectedSectionKey: "",
    expandedGroupPath: "",
    lastTraceState: null,
    lastRenderedTraceCount: 0,
    artifacts: null,
    activeError: "",
  };

  function stopTimer() {
    if (state.timerHandle) {
      clearInterval(state.timerHandle);
      state.timerHandle = null;
    }
  }

  return {
    setCancelled(value) {
      state.cancelled = Boolean(value);
    },
    isCancelled() {
      return state.cancelled;
    },
    setPreparing(value) {
      state.preparing = Boolean(value);
    },
    isPreparing() {
      return state.preparing;
    },
    startTimer(onTick) {
      stopTimer();
      state.elapsed = 0;
      onTick?.(state.elapsed);
      state.timerHandle = setInterval(() => {
        state.elapsed += 1;
        onTick?.(state.elapsed);
      }, 1000);
    },
    stopTimer,
    getElapsed() {
      return state.elapsed;
    },
    setSelectedSectionKey(value) {
      state.selectedSectionKey = String(value || "").trim();
    },
    getSelectedSectionKey() {
      return state.selectedSectionKey;
    },
    setExpandedGroupPath(value) {
      state.expandedGroupPath = String(value || "").trim();
    },
    getExpandedGroupPath() {
      return state.expandedGroupPath;
    },
    setLastTraceState(value) {
      state.lastTraceState = value;
    },
    getLastTraceState() {
      return state.lastTraceState;
    },
    setLastRenderedTraceCount(value) {
      state.lastRenderedTraceCount = Number(value || 0);
    },
    getLastRenderedTraceCount() {
      return state.lastRenderedTraceCount;
    },
    setArtifacts(value) {
      state.artifacts = value || null;
    },
    getArtifacts() {
      return state.artifacts;
    },
    setActiveError(value) {
      state.activeError = String(value || "").trim();
    },
    getActiveError() {
      return state.activeError;
    },
    reset() {
      stopTimer();
      state.cancelled = false;
      state.preparing = false;
      state.elapsed = 0;
      state.selectedSectionKey = "";
      state.expandedGroupPath = "";
      state.lastTraceState = null;
      state.lastRenderedTraceCount = 0;
      state.artifacts = null;
      state.activeError = "";
    },
  };
}
