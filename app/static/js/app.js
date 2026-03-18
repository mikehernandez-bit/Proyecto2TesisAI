/**
 * GicaGen frontend SPA.
 *
 * Wizard flow:
 * 1) Select format
 * 2) Select prompt
 * 3) Fill details
 * 4) Select IA
 * 5) IA generation
 * 6) Construction / render
 * 7) Downloads
 */
const TesisAI = (() => {
  const TOTAL_STEPS = 7;

  let currentView = "dashboard";
  let currentStep = 1;

  let selectedFormat = null;
  let selectedPrompt = null;
  let currentProject = null;
  let currentWizardMode = "new";
  let n8nSpec = null;
  let simRunResult = null;
  let isPreparingGuide = false;
  let isRunningSimulation = false;
  let providerStatusCache = null;
  let gicatesisOnline = true;
  let formatsCache = [];
  let promptsCache = [];

  const $ = (id) => document.getElementById(id);
  const INTL_INT_FORMAT = new Intl.NumberFormat("es-PE");

  function formatInt(value) {
    const numeric = Number(value || 0);
    if (!Number.isFinite(numeric)) return "0";
    return INTL_INT_FORMAT.format(Math.max(0, Math.round(numeric)));
  }

  function _parseDate(value) {
    const raw = String(value || "").trim();
    if (!raw) return null;
    const parsed = new Date(raw);
    return Number.isNaN(parsed.getTime()) ? null : parsed;
  }

  function _formatProjectDate(project) {
    return String(project?.updated_at || project?.created_at || "-");
  }

  function _projectValues(project) {
    if (project?.values && typeof project.values === "object") return project.values;
    if (project?.variables && typeof project.variables === "object") return project.variables;
    return {};
  }

  function _hasMeaningfulProjectValues(project) {
    const values = _projectValues(project);
    return Object.entries(values).some(([key, value]) => {
      if (key === "title") return false;
      return String(value ?? "").trim().length > 0;
    });
  }

  function _effectiveProjectStatus(project) {
    const rawStatus = String(project?.status || "").toLowerCase().trim();
    if (rawStatus === "draft" && project?.format_id && project?.prompt_id && _hasMeaningfulProjectValues(project)) {
      return "ready";
    }
    if (rawStatus === "ai_received") return "rendering";
    return rawStatus;
  }

  function _projectStatusPriority(project) {
    const status = _effectiveProjectStatus(project);
    const priorities = {
      generating: 6,
      rendering: 5,
      ready: 4,
      draft: 3,
      render_failed: 3,
      failed: 3,
      blocked: 3,
      cancel_requested: 3,
      completed_with_incidents: 2,
      completed: 2,
      simulated: 2,
    };
    return priorities[status] || 0;
  }

  function _sortProjectsForProduct(items) {
    return [...(Array.isArray(items) ? items : [])].sort((left, right) => {
      const leftTs = _parseDate(left?.updated_at || left?.created_at)?.getTime() || 0;
      const rightTs = _parseDate(right?.updated_at || right?.created_at)?.getTime() || 0;
      if (leftTs !== rightTs) return rightTs - leftTs;
      return _projectStatusPriority(right) - _projectStatusPriority(left);
    });
  }

  function escapeHtml(input) {
    return String(input ?? "").replace(/[&<>"']/g, (char) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#039;",
    }[char]));
  }

  function toPrettyJson(value) {
    return JSON.stringify(value ?? {}, null, 2);
  }

  async function copyText(text) {
    await navigator.clipboard.writeText(String(text ?? ""));
  }

  function downloadText(filename, text) {
    const blob = new Blob([String(text ?? "")], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  async function parseError(response) {
    const raw = await response.text();
    try {
      const payload = JSON.parse(raw);
      if (payload && typeof payload.detail === "string") return payload.detail;
      if (payload && payload.detail && typeof payload.detail.message === "string") {
        return payload.detail.message;
      }
      return raw;
    } catch (_) {
      return raw;
    }
  }

  async function apiGet(url) {
    const response = await fetch(url);
    if (!response.ok) throw new Error(await parseError(response));
    return response.json();
  }

  async function apiSend(url, method, body) {
    const response = await fetch(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!response.ok) throw new Error(await parseError(response));
    return response.json();
  }

  function _renderTokenUsage(projectSnapshot) {
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

    if ($("gen-token-input-total")) $("gen-token-input-total").textContent = formatInt(usage?.input_tokens_total || 0);
    if ($("gen-token-output-total")) $("gen-token-output-total").textContent = formatInt(usage?.output_tokens_total || 0);
    if ($("gen-token-total")) $("gen-token-total").textContent = formatInt(usage?.total_tokens || 0);
    if ($("gen-token-current-section")) $("gen-token-current-section").textContent = currentSectionLabel;
    if ($("gen-token-current-model")) $("gen-token-current-model").textContent = modelLabel || "-";
    if ($("gen-token-source")) $("gen-token-source").textContent = sourceLabel;
    if ($("gen-token-calls")) $("gen-token-calls").textContent = formatInt(callsTotal);

    if ($("gen-provider-badge")) {
      if (providerLabel) {
        $("gen-provider-badge").classList.remove("hidden");
        if ($("gen-provider-name")) $("gen-provider-name").textContent = providerLabel;
      } else {
        $("gen-provider-badge").classList.add("hidden");
        if ($("gen-provider-name")) $("gen-provider-name").textContent = "-";
      }
    }
    if ($("gen-model-badge")) {
      if (modelLabel) {
        $("gen-model-badge").classList.remove("hidden");
        if ($("gen-model-name")) $("gen-model-name").textContent = modelLabel;
      } else {
        $("gen-model-badge").classList.add("hidden");
        if ($("gen-model-name")) $("gen-model-name").textContent = "-";
      }
    }
  }

  function _sectionKey(section) {
    return String(section?.section_id || section?.sectionId || section?.section_path || section?.path || "").trim();
  }

  function _sectionTitleFromPath(path) {
    const parts = String(path || "").split("/").map((item) => item.trim()).filter(Boolean);
    return parts.length ? parts[parts.length - 1] : "";
  }

  function _sectionPathParts(path) {
    return String(path || "").split("/").map((item) => item.trim()).filter(Boolean);
  }

  function _resolveSectionParentPath(section) {
    const explicitParent = String(section?.parent_section_path || section?.sectionParentPath || "").trim();
    if (explicitParent) return explicitParent;
    const parts = _sectionPathParts(section?.section_path || section?.path || "");
    if (parts.length <= 1) return "";
    return parts.slice(0, -1).join("/");
  }

  function _resolveSectionLevel(section) {
    const explicitLevel = Number(section?.section_level || section?.sectionLevel || 0);
    if (Number.isFinite(explicitLevel) && explicitLevel > 0) return explicitLevel;
    return Math.max(1, _sectionPathParts(section?.section_path || section?.path || "").length);
  }

  function _resolveSectionOrder(section, fallback = null) {
    const explicitOrder = Number(section?.section_order ?? section?.sectionOrder);
    if (Number.isFinite(explicitOrder) && explicitOrder >= 0) return explicitOrder;
    return Number.isFinite(fallback) && fallback >= 0 ? fallback : null;
  }

  function _sortGenerationSections(sections) {
    return [...(Array.isArray(sections) ? sections : [])].sort((left, right) => {
      const leftOrder = _resolveSectionOrder(left, Number.MAX_SAFE_INTEGER);
      const rightOrder = _resolveSectionOrder(right, Number.MAX_SAFE_INTEGER);
      if (leftOrder !== rightOrder) return leftOrder - rightOrder;

      const leftLevel = _resolveSectionLevel(left);
      const rightLevel = _resolveSectionLevel(right);
      if (leftLevel !== rightLevel) return leftLevel - rightLevel;

      return String(left?.section_path || left?.path || "").localeCompare(
        String(right?.section_path || right?.path || ""),
        "es",
      );
    });
  }

  function _stringifySectionOutput(value) {
    if (value == null) return "";
    if (typeof value === "string") return value;
    try {
      return JSON.stringify(value, null, 2);
    } catch (_) {
      return String(value);
    }
  }

  function _mergeGenerationSection(baseSection, incomingSection) {
    const base = baseSection && typeof baseSection === "object" ? baseSection : {};
    const incoming = incomingSection && typeof incomingSection === "object" ? incomingSection : {};
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
      section_title: pickString(base.section_title, incoming.section_title),
      parent_section_path: pickString(
        base.parent_section_path,
        base.sectionParentPath,
        incoming.parent_section_path,
        incoming.sectionParentPath,
      ),
      section_order: _resolveSectionOrder(
        { section_order: base.section_order ?? base.sectionOrder },
        _resolveSectionOrder({ section_order: incoming.section_order ?? incoming.sectionOrder }),
      ),
      section_level: pickNumber(base.section_level, base.sectionLevel, incoming.section_level, incoming.sectionLevel) || 1,
      status: mergedStatus,
      prompt_sent: pickString(base.prompt_sent, incoming.prompt_sent),
      ai_output: pickString(base.ai_output, incoming.ai_output),
      input_tokens: pickNumber(base.input_tokens, incoming.input_tokens),
      output_tokens: pickNumber(base.output_tokens, incoming.output_tokens),
      total_tokens: pickNumber(base.total_tokens, incoming.total_tokens),
      provider: pickString(base.provider, incoming.provider),
      model: pickString(base.model, incoming.model),
      duration_ms: pickNumber(base.duration_ms, incoming.duration_ms),
      estimated: Boolean(base.estimated || incoming.estimated),
      source: pickString(base.source, incoming.source),
      attempt_count: pickNumber(base.attempt_count, incoming.attempt_count),
      error: pickString(base.error, incoming.error),
    };
  }

  function _mergeGenerationSections(...collections) {
    const sectionsByKey = new Map();
    collections.flat().forEach((item) => {
      if (!item || typeof item !== "object") return;
      const key = _sectionKey(item);
      if (!key) return;
      const existing = sectionsByKey.get(key);
      sectionsByKey.set(key, existing ? _mergeGenerationSection(existing, item) : item);
    });
    return _sortGenerationSections(Array.from(sectionsByKey.values()));
  }

  function _statusBadgeClass(status) {
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

  function _normalizeGenerationPhase(projectSnapshot) {
    const phase = projectSnapshot?.generation_phase && typeof projectSnapshot.generation_phase === "object"
      ? projectSnapshot.generation_phase
      : {};
    const sections = Array.isArray(phase.sections) ? phase.sections.filter((item) => item && typeof item === "object") : [];
    const planned = Array.isArray(phase.planned_sections)
      ? phase.planned_sections.filter((item) => item && typeof item === "object")
      : [];
    const sectionsByKey = new Map();
    sections.forEach((item) => {
      sectionsByKey.set(_sectionKey(item), item);
    });
    const merged = [];
    planned.forEach((item, index) => {
      const key = _sectionKey(item);
      const existing = sectionsByKey.get(key);
      const plannedSection = {
        section_id: item.section_id || item.sectionId || "",
        section_path: item.section_path || item.sectionPath || item.path || "",
        section_title: item.section_title || item.sectionTitle || "",
        parent_section_path: item.parent_section_path || item.sectionParentPath || "",
        section_order: _resolveSectionOrder(item, index),
        section_level: Number(item.section_level || item.sectionLevel || 1),
        status: "pending",
        total_tokens: 0,
        input_tokens: 0,
        output_tokens: 0,
        provider: "",
        model: "",
        prompt_sent: "",
        ai_output: "",
      };
      merged.push(existing ? _mergeGenerationSection(existing, plannedSection) : plannedSection);
      sectionsByKey.delete(key);
    });
    let nextSectionOrder = planned.length;
    sectionsByKey.forEach((item) => {
      merged.push({
        ...item,
        section_order: _resolveSectionOrder(item, nextSectionOrder),
      });
      nextSectionOrder += 1;
    });
    const orderedSections = _sortGenerationSections(merged);
    const total = Number(phase.total_sections || orderedSections.length || 0);
    const completed = orderedSections.filter((item) => String(item.status || "").toLowerCase() === "ok").length;
    const currentKey = String(phase.current_section_id || phase.current_section_path || "").trim();
    return {
      status: String(phase.status || "idle"),
      basePrompt: String(phase.base_prompt || ""),
      totalSections: total,
      completedSections: completed,
      currentKey,
      sections: orderedSections,
    };
  }

  function _deriveGenerationPhaseFromTrace(projectSnapshot) {
    const events = Array.isArray(projectSnapshot?.events)
      ? projectSnapshot.events
      : Array.isArray(projectSnapshot?.trace)
        ? projectSnapshot.trace
        : [];
    const progress = projectSnapshot?.progress && typeof projectSnapshot.progress === "object"
      ? projectSnapshot.progress
      : {};
    const generationSnapshot = projectSnapshot?.generation_snapshot && typeof projectSnapshot.generation_snapshot === "object"
      ? projectSnapshot.generation_snapshot
      : {};
    const sectionsByKey = new Map();
    let basePrompt = "";
    let totalSections = Number(progress.total || generationSnapshot.total_sections || 0);

    events.forEach((event) => {
      if (!event || typeof event !== "object") return;
      const step = String(event.step || "");
      const meta = event.meta && typeof event.meta === "object" ? event.meta : {};
      const preview = event.preview && typeof event.preview === "object" ? event.preview : {};

      if (!basePrompt && (step === "prompt.base" || step === "prompt.render")) {
        basePrompt = String(preview.prompt || "");
      }

      if (step === "format.section_index") {
        totalSections = Math.max(totalSections, Number(meta.sectionTotal || 0));
        const outline = Array.isArray(meta.sectionOutline) ? meta.sectionOutline : [];
        outline.forEach((item, index) => {
          if (!item || typeof item !== "object") return;
          const normalized = {
            section_id: String(item.sectionId || item.section_id || ""),
            section_path: String(item.sectionPath || item.section_path || item.path || ""),
            section_title: _sectionTitleFromPath(String(item.sectionPath || item.section_path || item.path || "")),
            parent_section_path: String(item.sectionParentPath || item.parent_section_path || ""),
            section_order: _resolveSectionOrder(item, index),
            section_level: Number(item.sectionLevel || item.section_level || 1),
            status: "pending",
            total_tokens: 0,
            input_tokens: 0,
            output_tokens: 0,
            provider: "",
            model: "",
            prompt_sent: "",
            ai_output: "",
            attempt_count: 0,
            duration_ms: 0,
            estimated: false,
            source: "",
          };
          const key = _sectionKey(normalized);
          if (key && !sectionsByKey.has(key)) sectionsByKey.set(key, normalized);
        });
      }

      if (step === "ai.generate.section") {
        const section = {
          section_id: String(meta.sectionId || ""),
          section_path: String(meta.sectionPath || ""),
          section_title: _sectionTitleFromPath(String(meta.sectionPath || "")),
          parent_section_path: String(meta.sectionParentPath || ""),
          section_order: _resolveSectionOrder(
            meta,
            Math.max(0, Number(meta.sectionIndex || meta.section_index || 1) - 1),
          ),
          section_level: Number(meta.sectionLevel || 1),
          status: String(event.status || "pending") === "done"
            ? "ok"
            : String(event.status || "pending") === "running"
              ? "generating"
              : String(event.status || "pending") === "error"
                ? "error"
                : "pending",
          total_tokens: Number(meta.sectionUsage?.total_tokens || 0),
          input_tokens: Number(meta.sectionUsage?.input_tokens_total || 0),
          output_tokens: Number(meta.sectionUsage?.output_tokens_total || 0),
          provider: String(meta.provider || ""),
          model: String(meta.model || ""),
          prompt_sent: String(preview.prompt || ""),
          ai_output: String(preview.raw || ""),
          attempt_count: Number((Array.isArray(meta.usageAttempts) ? meta.usageAttempts.length : 0) || 0),
          duration_ms: Number(meta.durationMs || 0),
          estimated: Boolean(meta.sectionUsage?.has_estimated_usage),
          source: Number(meta.sectionUsage?.estimated_calls || 0) > 0
            ? (Number(meta.sectionUsage?.reported_calls || 0) > 0 ? "mixed" : "estimated")
            : "reported_by_provider",
        };
        const key = _sectionKey(section);
        if (key) {
          const existing = sectionsByKey.get(key) || {};
          sectionsByKey.set(key, { ...existing, ...section });
        }
      }
    });

    const seededSections = Array.isArray(generationSnapshot.completed_sections)
      ? generationSnapshot.completed_sections
      : [];
    seededSections.forEach((item, index) => {
      if (!item || typeof item !== "object") return;
      const normalized = {
        section_id: String(item.sectionId || item.section_id || ""),
        section_path: String(item.path || item.section_path || ""),
        section_title: _sectionTitleFromPath(String(item.path || item.section_path || "")),
        parent_section_path: _resolveSectionParentPath(item),
        section_order: _resolveSectionOrder(item, totalSections + index),
        section_level: _resolveSectionLevel(item),
        status: "ok",
        total_tokens: 0,
        input_tokens: 0,
        output_tokens: 0,
        provider: "",
        model: "",
        prompt_sent: "",
        ai_output: "",
        attempt_count: 0,
        duration_ms: 0,
        estimated: false,
        source: "",
      };
      const key = _sectionKey(normalized);
      if (key && !sectionsByKey.has(key)) sectionsByKey.set(key, normalized);
    });

    const aiResultSections = Array.isArray(projectSnapshot?.ai_result?.sections)
      ? projectSnapshot.ai_result.sections
      : [];
    aiResultSections.forEach((item, index) => {
      if (!item || typeof item !== "object") return;
      const normalized = {
        section_id: String(item.sectionId || item.section_id || ""),
        section_path: String(item.path || item.section_path || ""),
        section_title: _sectionTitleFromPath(String(item.path || item.section_path || "")),
        parent_section_path: _resolveSectionParentPath(item),
        section_order: _resolveSectionOrder(item, totalSections + seededSections.length + index),
        section_level: _resolveSectionLevel(item),
        status: GEN_SUCCESS_STATUSES.includes(String(projectSnapshot?.status || "")) ? "ok" : "pending",
        total_tokens: 0,
        input_tokens: 0,
        output_tokens: 0,
        provider: "",
        model: "",
        prompt_sent: "",
        ai_output: _stringifySectionOutput(item.content),
        attempt_count: 0,
        duration_ms: 0,
        estimated: false,
        source: "",
      };
      const key = _sectionKey(normalized);
      if (!key) return;
      const existing = sectionsByKey.get(key) || {};
      sectionsByKey.set(key, _mergeGenerationSection(existing, normalized));
    });

    const sections = _sortGenerationSections(Array.from(sectionsByKey.values()));
    const completedSections = sections.filter((item) => String(item.status || "") === "ok").length;
    return {
      status: sections.length ? "running" : "idle",
      basePrompt: basePrompt || String(projectSnapshot?.prompt_template || ""),
      totalSections: Math.max(totalSections, sections.length),
      completedSections,
      currentKey: String(progress.currentPath || generationSnapshot.current_path || ""),
      sections,
    };
  }

  function _resolveGenerationPhase(projectSnapshot) {
    const direct = _normalizeGenerationPhase(projectSnapshot);
    const derived = _deriveGenerationPhaseFromTrace(projectSnapshot);
    const mergedSections = _mergeGenerationSections(derived.sections || [], direct.sections || []);
    const completedSections = mergedSections.filter((item) => {
      const safe = String(item.status || "").toLowerCase();
      return safe === "ok" || safe === "done" || safe === "completed";
    }).length;
    return {
      status: direct.status !== "idle" ? direct.status : derived.status,
      basePrompt: direct.basePrompt || derived.basePrompt,
      totalSections: Math.max(direct.totalSections || 0, derived.totalSections || 0, mergedSections.length),
      completedSections: Math.max(direct.completedSections || 0, derived.completedSections || 0, completedSections),
      currentKey: direct.currentKey || derived.currentKey,
      sections: mergedSections,
    };
  }

  function _collectGenerationNodeSections(node) {
    if (!node || typeof node !== "object") return [];
    const sections = [];
    if (node.selfSection && typeof node.selfSection === "object") sections.push(node.selfSection);
    (Array.isArray(node.children) ? node.children : []).forEach((child) => {
      sections.push(..._collectGenerationNodeSections(child));
    });
    return sections;
  }

  function _aggregateGenerationSource(sections) {
    const sources = new Set(
      sections
        .map((item) => String(item?.source || "").trim())
        .filter(Boolean),
    );
    if (!sources.size) return "-";
    if (sources.has("mixed") || sources.size > 1) return "mixed";
    return Array.from(sources)[0];
  }

  function _summarizeGenerationNode(node) {
    const sections = _collectGenerationNodeSections(node);
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
      duration_ms: sections.reduce((sum, item) => sum + Number(item?.duration_ms || 0), 0),
      attempt_count: sections.reduce((sum, item) => sum + Number(item?.attempt_count || 0), 0),
      latestSection,
      source: _aggregateGenerationSource(sections),
    };
  }

  function _buildGenerationTree(sections) {
    const orderedSections = _sortGenerationSections(sections);
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
        section_title: String(
          rawSection.section_title || _sectionTitleFromPath(rawSection.section_path || rawSection.path || "")
        ).trim(),
        parent_section_path: _resolveSectionParentPath(rawSection),
        section_order: _resolveSectionOrder(rawSection, index),
        section_level: _resolveSectionLevel(rawSection),
      };
      const parts = _sectionPathParts(section.section_path);
      if (!parts.length) return;
      const sectionOrder = _resolveSectionOrder(section, index) ?? index;

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
            ? _mergeGenerationSection(currentNode.selfSection, section)
            : section;
        }
        parentNode = currentNode;
      });
    });

    const finalize = (node) => {
      node.children.sort((left, right) => {
        const byOrder = _resolveSectionOrder({ section_order: left.order }, Number.MAX_SAFE_INTEGER)
          - _resolveSectionOrder({ section_order: right.order }, Number.MAX_SAFE_INTEGER);
        if (byOrder !== 0) return byOrder;
        return String(left.label || "").localeCompare(String(right.label || ""), "es");
      });
      node.children.forEach((child) => {
        finalize(child);
        child.summary = _summarizeGenerationNode(child);
      });
      return node;
    };

    return finalize(root);
  }

  function _findGenerationNode(node, key) {
    if (!node || !key) return null;
    if (String(node.key || "") === String(key)) return node;
    if (node.selfSection && _sectionKey(node.selfSection) === String(key)) return node;
    for (const child of Array.isArray(node.children) ? node.children : []) {
      const found = _findGenerationNode(child, key);
      if (found) return found;
    }
    return null;
  }

  function _defaultExpandedGroupPath(treeRoot, phase) {
    const currentSection = phase.sections.find((item) => String(item.status || "").toLowerCase() === "generating")
      || phase.sections.find((item) => _sectionKey(item) === String(phase.currentKey || ""))
      || phase.sections.find((item) => String(item.status || "").toLowerCase() === "ok")
      || phase.sections[0];
    if (!currentSection) return "";
    return _resolveSectionParentPath(currentSection) || String(currentSection.section_path || "");
  }

  function _renderGenerationTreeNodes(nodes, selectedKey, expandedGroupPath) {
    return nodes.map((node) => {
      const summary = node.summary || _summarizeGenerationNode(node);
      const badge = _statusBadgeClass(summary.status);
      const hasChildren = Array.isArray(node.children) && node.children.length > 0;
      const isExpanded = hasChildren && String(expandedGroupPath || "").startsWith(String(node.path || ""));
      const isSelected = String(selectedKey || "") === String(node.key || "");
      const latestSection = summary.latestSection || node.selfSection || {};
      const detail = hasChildren
        ? `${formatInt(summary.completedCount)}/${formatInt(summary.totalCount)} subsecciones`
        : `${latestSection.provider || "-"} · ${latestSection.model || "-"} · ${formatInt(summary.total_tokens)} tokens`;
      const indent = Math.max(0, Number(node.depth || 1) - 1) * 16;

      return `
        <div class="space-y-2">
          <button
            class="w-full text-left rounded-2xl border p-3 transition ${isSelected ? "border-slate-900 bg-slate-50 shadow-sm" : "bg-white hover:shadow-sm"}"
            data-ai-node-key="${escapeHtml(node.key)}"
            data-ai-node-kind="${hasChildren ? "group" : "leaf"}"
            data-ai-node-path="${escapeHtml(node.path)}"
            style="margin-left:${indent}px"
          >
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0">
                <div class="flex items-center gap-2 text-xs text-slate-400 font-semibold">
                  ${hasChildren ? `<span class="inline-flex h-5 w-5 items-center justify-center rounded-full border border-slate-200 text-slate-500">${isExpanded ? "−" : "+"}</span>` : '<span class="inline-flex h-5 w-5 items-center justify-center rounded-full border border-slate-200 text-slate-400">•</span>'}
                  <span>${hasChildren ? "Bloque" : "Subseccion"}</span>
                </div>
                <div class="font-semibold text-slate-900 truncate">${escapeHtml(node.label || "Sin nombre")}</div>
                <div class="mt-1 text-xs text-slate-500 truncate">${escapeHtml(detail || "Pendiente")}</div>
              </div>
              <span class="inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-extrabold ${badge.wrap}">
                ${badge.label}
              </span>
            </div>
          </button>
          ${hasChildren && isExpanded
            ? `<div class="space-y-2">${_renderGenerationTreeNodes(node.children, selectedKey, expandedGroupPath)}</div>`
            : ""}
        </div>
      `;
    }).join("");
  }

  function _syncWizardStepWithProject(projectSnapshot) {
    if (!projectSnapshot || currentStep < 5) return;
    const projectStatus = String(projectSnapshot.status || "");
    const generationPhase = projectSnapshot?.generation_phase && typeof projectSnapshot.generation_phase === "object"
      ? projectSnapshot.generation_phase
      : {};
    const generationStatus = String(generationPhase.status || "");
    const constructionPhase = projectSnapshot?.construction_phase && typeof projectSnapshot.construction_phase === "object"
      ? projectSnapshot.construction_phase
      : {};
    const constructionStatus = String(constructionPhase.status || "");

    if (GEN_SUCCESS_STATUSES.includes(projectStatus)) {
      simRunResult = _buildArtifacts(projectSnapshot);
      if (currentWizardMode !== "review" && currentStep < 7) continueToSimDownloads();
      return;
    }
    if (projectStatus === "render_failed") {
      if (currentStep < 6) nextStep(6);
      return;
    }
    if (
      currentStep === 5
      && (
        ["completed", "failed", "blocked"].includes(generationStatus)
        || ["running", "completed", "error"].includes(constructionStatus)
      )
    ) {
      nextStep(6);
    }
  }

  function _renderAIGeneration(projectSnapshot) {
    const phase = _resolveGenerationPhase(projectSnapshot);
    if (Array.isArray(phase.sections) && phase.sections.length > 0) {
      _renderAIGenerationHierarchical(projectSnapshot, phase);
      return;
    }
    const sectionList = $("gen-ai-section-list");
    const basePrompt = $("gen-base-prompt");
    const totalSections = Math.max(
      Number(phase.totalSections || 0),
      Number(projectSnapshot?.progress?.total || 0),
      phase.sections.length,
    );
    const completedSections = Math.max(
      Number(phase.completedSections || 0),
      phase.sections.filter((item) => String(item.status || "").toLowerCase() === "ok").length,
      Number(projectSnapshot?.progress?.current || 0),
    );
    const currentSectionPath = String(
      phase.sections.find((item) => String(item.status || "").toLowerCase() === "generating")?.section_path
      || projectSnapshot?.progress?.currentPath
      || phase.sections[completedSections]?.section_path
      || ""
    );

    if (basePrompt) {
      basePrompt.textContent = phase.basePrompt || "Aun no disponible.";
    }
    if ($("gen-ai-count")) {
      $("gen-ai-count").textContent = `${formatInt(completedSections)}/${formatInt(totalSections)}`;
    }
    if ($("gen-sections-progress")) {
      $("gen-sections-progress").innerHTML = totalSections > 0
        ? `Secciones <b>${formatInt(Math.min(completedSections, totalSections))}/${formatInt(totalSections)}</b>${currentSectionPath ? ` · ${escapeHtml(currentSectionPath)}` : ""}`
        : "Secciones <b>0/0</b>";
    }
    if ($("gen-sections-bar")) {
      const width = totalSections > 0 ? Math.min(100, Math.round((Math.min(completedSections, totalSections) / totalSections) * 100)) : 0;
      $("gen-sections-bar").style.width = `${width}%`;
    }
    if ($("gen-queue-count")) {
      $("gen-queue-count").textContent = String(Math.max(0, totalSections - completedSections));
    }
    if ($("gen-done-count")) {
      $("gen-done-count").textContent = String(Math.max(0, completedSections));
    }
    if ($("gen-final-badge")) {
      if (totalSections > 0 && completedSections >= totalSections) $("gen-final-badge").classList.remove("hidden");
      else $("gen-final-badge").classList.add("hidden");
    }
    if (!phase.sections.length) {
      if (sectionList) {
        sectionList.innerHTML = '<div class="rounded-2xl border border-dashed p-4 text-sm text-slate-500">Aun no hay secciones registradas por la IA.</div>';
      }
      _genAiSelectedSectionKey = "";
      if ($("gen-ai-detail-title")) $("gen-ai-detail-title").textContent = "Sin sección seleccionada";
      if ($("gen-ai-detail-meta")) $("gen-ai-detail-meta").textContent = "Selecciona una sección para auditar prompt, respuesta y tokens.";
      if ($("gen-ai-detail-prompt")) $("gen-ai-detail-prompt").textContent = "Aun no disponible.";
      if ($("gen-ai-detail-response")) $("gen-ai-detail-response").textContent = "Aun no disponible.";
      if ($("gen-ai-detail-input")) $("gen-ai-detail-input").textContent = "0";
      if ($("gen-ai-detail-output")) $("gen-ai-detail-output").textContent = "0";
      if ($("gen-ai-detail-total")) $("gen-ai-detail-total").textContent = "0";
      if ($("gen-ai-detail-duration")) $("gen-ai-detail-duration").textContent = "-";
      if ($("gen-ai-detail-provider")) $("gen-ai-detail-provider").textContent = "-";
      if ($("gen-ai-detail-model")) $("gen-ai-detail-model").textContent = "-";
      if ($("gen-ai-detail-source")) $("gen-ai-detail-source").textContent = "-";
      if ($("gen-ai-detail-status")) {
        $("gen-ai-detail-status").className = "inline-flex items-center rounded-full border bg-slate-50 px-3 py-1 text-xs font-extrabold text-slate-700 border-slate-200";
        $("gen-ai-detail-status").textContent = "PENDIENTE";
      }
      return;
    }

    if (!phase.sections.some((item) => _sectionKey(item) === _genAiSelectedSectionKey)) {
      const preferred = phase.sections.find((item) => String(item.status || "").toLowerCase() === "generating")
        || phase.sections.find((item) => String(item.status || "").toLowerCase() === "ok")
        || phase.sections[0];
      _genAiSelectedSectionKey = _sectionKey(preferred);
    }

    if (sectionList) {
      sectionList.innerHTML = phase.sections.map((item, index) => {
        const key = _sectionKey(item);
        const badge = _statusBadgeClass(item.status);
        const selected = key === _genAiSelectedSectionKey;
        return `
          <button class="w-full text-left rounded-2xl border p-3 transition ${selected ? "border-slate-900 bg-slate-50 shadow-sm" : "bg-white hover:shadow-sm"}"
            data-ai-section-key="${escapeHtml(key)}">
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0">
                <div class="text-xs text-slate-400 font-semibold">Sección ${index + 1}</div>
                <div class="font-semibold text-slate-900 truncate">${escapeHtml(item.section_path || item.section_title || "Sin nombre")}</div>
                <div class="mt-1 text-xs text-slate-500 truncate">
                  ${escapeHtml(item.provider || "-")} · ${escapeHtml(item.model || "-")} · ${formatInt(item.total_tokens || 0)} tokens
                </div>
              </div>
              <span class="inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-extrabold ${badge.wrap}">
                ${badge.label}
              </span>
            </div>
          </button>
        `;
      }).join("");
      sectionList.querySelectorAll("[data-ai-section-key]").forEach((button) => {
        button.onclick = () => {
          _genAiSelectedSectionKey = String(button.getAttribute("data-ai-section-key") || "");
          _renderAIGeneration(projectSnapshot);
        };
      });
    }

    const selected = phase.sections.find((item) => _sectionKey(item) === _genAiSelectedSectionKey) || phase.sections[0];
    const badge = _statusBadgeClass(selected.status);
    if ($("gen-ai-detail-title")) {
      $("gen-ai-detail-title").textContent = selected.section_path || selected.section_title || "Sin nombre";
    }
    if ($("gen-ai-detail-meta")) {
      $("gen-ai-detail-meta").textContent = `Sección ${selected.section_id || "-"} · Intentos: ${formatInt(selected.attempt_count || 0)}`;
    }
    if ($("gen-ai-detail-status")) {
      $("gen-ai-detail-status").className = `inline-flex items-center rounded-full border px-3 py-1 text-xs font-extrabold ${badge.wrap}`;
      $("gen-ai-detail-status").textContent = badge.label;
    }
    if ($("gen-ai-detail-input")) $("gen-ai-detail-input").textContent = formatInt(selected.input_tokens || 0);
    if ($("gen-ai-detail-output")) $("gen-ai-detail-output").textContent = formatInt(selected.output_tokens || 0);
    if ($("gen-ai-detail-total")) $("gen-ai-detail-total").textContent = formatInt(selected.total_tokens || 0);
    if ($("gen-ai-detail-duration")) {
      $("gen-ai-detail-duration").textContent = selected.duration_ms ? `${formatInt(selected.duration_ms)} ms` : "-";
    }
    if ($("gen-ai-detail-provider")) $("gen-ai-detail-provider").textContent = selected.provider || "-";
    if ($("gen-ai-detail-model")) $("gen-ai-detail-model").textContent = selected.model || "-";
    if ($("gen-ai-detail-source")) $("gen-ai-detail-source").textContent = selected.source || "-";
    if ($("gen-ai-detail-prompt")) $("gen-ai-detail-prompt").textContent = selected.prompt_sent || "Aun no disponible.";
    if ($("gen-ai-detail-response")) $("gen-ai-detail-response").textContent = selected.ai_output || "Aun no disponible.";
  }

  function _renderAIGenerationHierarchical(projectSnapshot, phase) {
    const sectionList = $("gen-ai-section-list");
    const basePrompt = $("gen-base-prompt");
    const treeRoot = _buildGenerationTree(phase.sections || []);
    const totalSections = Math.max(
      Number(phase.totalSections || 0),
      Number(projectSnapshot?.progress?.total || 0),
      (phase.sections || []).length,
    );
    const completedSections = Math.max(
      Number(phase.completedSections || 0),
      (phase.sections || []).filter((item) => {
        const status = String(item.status || "").toLowerCase();
        return ["ok", "done", "completed"].includes(status);
      }).length,
    );
    const currentSectionPath = String(
      (phase.sections || []).find((item) => String(item.status || "").toLowerCase() === "generating")?.section_path
      || projectSnapshot?.progress?.currentPath
      || phase.currentKey
      || ""
    );

    if (basePrompt) {
      basePrompt.textContent = phase.basePrompt || "Aun no disponible.";
    }
    if ($("gen-ai-count")) {
      $("gen-ai-count").textContent = `${formatInt(completedSections)}/${formatInt(totalSections)}`;
    }
    if ($("gen-sections-progress")) {
      $("gen-sections-progress").innerHTML = totalSections > 0
        ? `Secciones <b>${formatInt(Math.min(completedSections, totalSections))}/${formatInt(totalSections)}</b>${currentSectionPath ? ` · ${escapeHtml(currentSectionPath)}` : ""}`
        : "Secciones <b>0/0</b>";
    }
    if ($("gen-sections-bar")) {
      const width = totalSections > 0
        ? Math.min(100, Math.round((Math.min(completedSections, totalSections) / totalSections) * 100))
        : 0;
      $("gen-sections-bar").style.width = `${width}%`;
    }
    if ($("gen-queue-count")) {
      $("gen-queue-count").textContent = String(Math.max(0, totalSections - completedSections));
    }
    if ($("gen-done-count")) {
      $("gen-done-count").textContent = String(Math.max(0, completedSections));
    }
    if ($("gen-final-badge")) {
      if (totalSections > 0 && completedSections >= totalSections) $("gen-final-badge").classList.remove("hidden");
      else $("gen-final-badge").classList.add("hidden");
    }

    if (_genAiExpandedGroupPath == null) {
      _genAiExpandedGroupPath = _defaultExpandedGroupPath(treeRoot, phase);
    }
    if (!_findGenerationNode(treeRoot, _genAiSelectedSectionKey)) {
      const preferred = (phase.sections || []).find((item) => String(item.status || "").toLowerCase() === "generating")
        || (phase.sections || []).find((item) => String(item.status || "").toLowerCase() === "ok")
        || (phase.sections || [])[0];
      if (preferred) {
        _genAiSelectedSectionKey = _sectionKey(preferred);
        _genAiExpandedGroupPath = _resolveSectionParentPath(preferred) || String(preferred.section_path || "");
      }
    }

    if (sectionList) {
      sectionList.innerHTML = _renderGenerationTreeNodes(
        treeRoot.children || [],
        _genAiSelectedSectionKey,
        _genAiExpandedGroupPath,
      );
      sectionList.querySelectorAll("[data-ai-node-key]").forEach((button) => {
        button.onclick = () => {
          const selectedKey = String(button.getAttribute("data-ai-node-key") || "");
          const nodeKind = String(button.getAttribute("data-ai-node-kind") || "");
          const nodePath = String(button.getAttribute("data-ai-node-path") || "");
          _genAiSelectedSectionKey = selectedKey;
          if (nodeKind === "group") {
            _genAiExpandedGroupPath = _genAiExpandedGroupPath === nodePath
              ? _resolveSectionParentPath({ section_path: nodePath })
              : nodePath;
          } else {
            _genAiExpandedGroupPath = _resolveSectionParentPath({ section_path: nodePath }) || nodePath;
          }
          _renderAIGenerationHierarchical(projectSnapshot, phase);
        };
      });
    }

    const selectedNode = _findGenerationNode(treeRoot, _genAiSelectedSectionKey)
      || _findGenerationNode(treeRoot, `group:${_defaultExpandedGroupPath(treeRoot, phase)}`)
      || (treeRoot.children || [])[0];
    const selectedSummary = _summarizeGenerationNode(selectedNode);
    const selected = selectedNode?.selfSection || selectedSummary.latestSection || (phase.sections || [])[0] || {};
    const isGroupSelection = Array.isArray(selectedNode?.children) && selectedNode.children.length > 0;
    const badge = _statusBadgeClass(isGroupSelection ? selectedSummary.status : selected.status);

    if ($("gen-ai-detail-title")) {
      $("gen-ai-detail-title").textContent = isGroupSelection
        ? (selectedNode?.path || selectedNode?.label || "Bloque")
        : (selected.section_path || selected.section_title || "Sin nombre");
    }
    if ($("gen-ai-detail-meta")) {
      $("gen-ai-detail-meta").textContent = isGroupSelection
        ? `Bloque jerarquico · ${formatInt(selectedSummary.completedCount)}/${formatInt(selectedSummary.totalCount)} subsecciones completadas`
        : `Seccion ${selected.section_id || "-"} · Padre: ${selected.parent_section_path || "raiz"} · Intentos: ${formatInt(selected.attempt_count || 0)}`;
    }
    if ($("gen-ai-detail-status")) {
      $("gen-ai-detail-status").className = `inline-flex items-center rounded-full border px-3 py-1 text-xs font-extrabold ${badge.wrap}`;
      $("gen-ai-detail-status").textContent = badge.label;
    }
    if ($("gen-ai-detail-input")) {
      $("gen-ai-detail-input").textContent = formatInt(isGroupSelection ? selectedSummary.input_tokens : selected.input_tokens || 0);
    }
    if ($("gen-ai-detail-output")) {
      $("gen-ai-detail-output").textContent = formatInt(isGroupSelection ? selectedSummary.output_tokens : selected.output_tokens || 0);
    }
    if ($("gen-ai-detail-total")) {
      $("gen-ai-detail-total").textContent = formatInt(isGroupSelection ? selectedSummary.total_tokens : selected.total_tokens || 0);
    }
    if ($("gen-ai-detail-duration")) {
      const durationMs = isGroupSelection ? selectedSummary.duration_ms : selected.duration_ms || 0;
      $("gen-ai-detail-duration").textContent = durationMs ? `${formatInt(durationMs)} ms` : "-";
    }
    if ($("gen-ai-detail-provider")) {
      $("gen-ai-detail-provider").textContent = isGroupSelection
        ? (selectedSummary.latestSection?.provider || "-")
        : (selected.provider || "-");
    }
    if ($("gen-ai-detail-model")) {
      $("gen-ai-detail-model").textContent = isGroupSelection
        ? (selectedSummary.latestSection?.model || "-")
        : (selected.model || "-");
    }
    if ($("gen-ai-detail-source")) {
      $("gen-ai-detail-source").textContent = isGroupSelection
        ? (selectedSummary.source || "-")
        : (selected.source || "-");
    }
    if ($("gen-ai-detail-prompt")) {
      $("gen-ai-detail-prompt").textContent = isGroupSelection
        ? `Este bloque agrupa ${formatInt(selectedSummary.totalCount)} subsecciones.\nSelecciona una subseccion hija para ver el prompt exacto enviado por la IA.\n\nSubsecciones:\n${(selectedNode?.children || []).map((item) => `- ${item.label}`).join("\n") || "- Sin hijas registradas"}`
        : (selected.prompt_sent || "Aun no disponible.");
    }
    if ($("gen-ai-detail-response")) {
      $("gen-ai-detail-response").textContent = isGroupSelection
        ? `Resumen del bloque:\n${(selectedNode?.children || []).map((item) => {
          const childSummary = item.summary || _summarizeGenerationNode(item);
          const childBadge = _statusBadgeClass(childSummary.status);
          return `- ${item.label}: ${childBadge.label} (${formatInt(childSummary.completedCount)}/${formatInt(childSummary.totalCount)})`;
        }).join("\n") || "Sin subsecciones registradas."}`
        : (selected.ai_output || "Aun no disponible.");
    }
  }

  function _normalizeConstructionPhase(projectSnapshot) {
    const phase = projectSnapshot?.construction_phase && typeof projectSnapshot.construction_phase === "object"
      ? projectSnapshot.construction_phase
      : {};
    const tasks = Array.isArray(phase.tasks) ? phase.tasks.filter((item) => item && typeof item === "object") : [];
    return {
      status: String(phase.status || "idle"),
      currentTask: String(phase.current_task || ""),
      tasks,
    };
  }

  function _constructionEventKey(event) {
    const step = String(event?.step || "").toLowerCase();
    if (step === "project.status.ai_received") return "handoff";
    if (step.startsWith("gicatesis.payload")) return "payload";
    if (step.startsWith("gicatesis.render.docx")) return "render_docx";
    if (step.startsWith("gicatesis.render.pdf")) return "render_pdf";
    if (step.includes("validation")) return "final_validation";
    return `${step}:${String(event?.title || "").trim()}`;
  }

  function _buildConstructionTimeline(projectSnapshot, phase) {
    const events = Array.isArray(projectSnapshot?.events) ? projectSnapshot.events : [];
    const relevantEvents = events.filter((event) => {
      const step = String(event?.step || "").toLowerCase();
      return step.startsWith("gicatesis.") || step.includes("render") || step === "project.status.ai_received";
    });

    const latestEventByKey = new Map();
    relevantEvents.forEach((event, index) => {
      if (!event || typeof event !== "object") return;
      latestEventByKey.set(_constructionEventKey(event), { ...event, _order: index });
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
      const task = (phase.tasks || []).find((item) => String(item?.id || "") === taskId);
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

  function _renderConstruction(projectSnapshot) {
    const phase = _normalizeConstructionPhase(projectSnapshot);
    const tasks = phase.tasks;
    const doneCount = tasks.filter((item) => String(item.status || "") === "done").length;
    const totalCount = tasks.length || 0;
    const width = totalCount > 0 ? Math.min(100, Math.round((doneCount / totalCount) * 100)) : 0;
    const statusBadge = _statusBadgeClass(
      phase.status === "completed" ? "done" : phase.status === "running" ? "generating" : phase.status
    );
    if ($("construct-progress-count")) $("construct-progress-count").textContent = `${doneCount}/${totalCount}`;
    if ($("construct-progress-bar")) $("construct-progress-bar").style.width = `${width}%`;
    if ($("construct-status-badge")) {
      $("construct-status-badge").className = `inline-flex items-center rounded-full border px-3 py-1 text-xs font-extrabold ${statusBadge.wrap}`;
      $("construct-status-badge").textContent = statusBadge.label;
    }
    if ($("construct-summary")) {
      if (phase.status === "completed") $("construct-summary").textContent = "El contenido ya fue transformado en DOCX/PDF y validado para descarga.";
      else if (phase.status === "running") $("construct-summary").textContent = "Armando el documento final a partir de la salida validada de IA.";
      else if (phase.status === "error") $("construct-summary").textContent = "La construcción se detuvo por un error; revisa el timeline técnico.";
      else $("construct-summary").textContent = "Aun no inicia la fase de construcción.";
    }

    const taskList = $("construct-task-list");
    if (taskList) {
      taskList.innerHTML = tasks.map((item) => {
        const badge = _statusBadgeClass(item.status);
        return `
          <div class="rounded-2xl border bg-white p-3">
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0">
                <div class="font-semibold text-slate-900">${escapeHtml(item.label || item.id || "Tarea")}</div>
                <div class="mt-1 text-xs text-slate-500">${escapeHtml(item.detail || "Pendiente")}</div>
              </div>
              <span class="inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-extrabold ${badge.wrap}">
                ${badge.label}
              </span>
            </div>
          </div>
        `;
      }).join("") || '<div class="rounded-2xl border border-dashed p-4 text-sm text-slate-500">Aun no hay tareas de construcción registradas.</div>';
    }

    const constructionEvents = _buildConstructionTimeline(projectSnapshot, phase);
    const list = $("construct-trace-list");
    const empty = $("construct-trace-empty");
    if (list && empty) {
      if (!constructionEvents.length) {
        list.innerHTML = "";
        empty.classList.remove("hidden");
      } else {
        empty.classList.add("hidden");
        list.innerHTML = constructionEvents.map((event) => {
          const status = String(event.status || "running");
          const badge = _statusBadgeClass(status);
          return `
            <div class="rounded-2xl border bg-white p-3">
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0">
                  <div class="text-xs text-slate-400">${escapeHtml(_formatEventTime(event.ts))}</div>
                  <div class="mt-1 font-semibold text-slate-900">${escapeHtml(event.title || event.message || event.step || "Evento")}</div>
                  <div class="mt-1 text-xs text-slate-500">${escapeHtml(event.detail || event.message || "")}</div>
                </div>
                <span class="inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-extrabold ${badge.wrap}">
                  ${badge.label}
                </span>
              </div>
            </div>
          `;
        }).join("");
      }
    }

    if ($("btn-go-construction")) {
      if (phase.status !== "idle") $("btn-go-construction").classList.remove("hidden");
      else $("btn-go-construction").classList.add("hidden");
    }
    if ($("btn-step6-downloads")) {
      if (String(projectSnapshot?.status || "").startsWith("completed")) $("btn-step6-downloads").classList.remove("hidden");
      else $("btn-step6-downloads").classList.add("hidden");
    }
  }

  function showView(viewId, options = {}) {
    document.querySelectorAll(".view-section").forEach((el) => el.classList.add("hidden"));
    const selected = $("view-" + viewId);
    if (selected) selected.classList.remove("hidden");

    document.querySelectorAll(".nav-item").forEach((el) => {
      el.classList.remove("bg-slate-800", "text-blue-400");
      el.classList.add("text-slate-300");
    });

    const activeNav = $("nav-" + viewId);
    if (activeNav) {
      activeNav.classList.remove("text-slate-300");
      activeNav.classList.add("bg-slate-800", "text-blue-400");
    }

    currentView = viewId;
    if (viewId === "dashboard") refreshDashboard().catch(console.error);
    if (viewId === "wizard") initWizard(options).catch(console.error);
    if (viewId === "admin-prompts") refreshPromptsAdmin().catch(console.error);
    if (viewId === "history") refreshHistory().catch(console.error);
  }

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

  function _inferDraftStep(project) {
    if (!project?.format_id) return 1;
    if (!project?.prompt_id) return 2;
    if (!_hasMeaningfulProjectValues(project)) return 3;
    return 4;
  }

  function _inferProjectStep(project, mode = "continue") {
    const requestedMode = String(mode || "continue").toLowerCase();
    const status = _effectiveProjectStatus(project);
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
    return _inferDraftStep(project);
  }

  function _projectPrimaryAction(project) {
    const status = _effectiveProjectStatus(project);
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

  function _renderProjectActions(project, variant = "table") {
    const primary = _projectPrimaryAction(project);
    const canDownload = (project.status === "completed" || project.status === "completed_with_incidents") && project.output_file;
    const baseClasses = variant === "hero"
      ? {
        primary: "rounded-xl bg-slate-900 text-white px-4 py-2 text-sm font-extrabold hover:bg-slate-950",
        secondary: "rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm font-extrabold text-slate-700 hover:bg-slate-50",
        tertiary: "rounded-xl border border-emerald-300 bg-emerald-50 px-4 py-2 text-sm font-extrabold text-emerald-700 hover:bg-emerald-100",
      }
      : {
        primary: "inline-flex items-center gap-2 rounded-lg bg-slate-900 px-3 py-2 text-xs font-bold text-white hover:bg-slate-950",
        secondary: "inline-flex items-center gap-2 rounded-lg border border-slate-300 px-3 py-2 text-xs font-bold text-slate-700 hover:bg-slate-50",
        tertiary: "inline-flex items-center gap-2 rounded-lg border border-emerald-300 px-3 py-2 text-xs font-bold text-emerald-700 hover:bg-emerald-50",
      };

    return `
      <button class="${baseClasses.primary}" onclick="TesisAI.openProject('${escapeHtml(project.id)}', { mode: '${escapeHtml(primary.mode)}' })">
        <i class="${escapeHtml(primary.icon)}"></i>
        ${escapeHtml(primary.label)}
      </button>
      ${canDownload
        ? `<a class="${baseClasses.tertiary}" href="/api/download/${encodeURIComponent(project.id)}"><i class="fa-solid fa-download"></i> Descargar</a>`
        : ""}
    `;
  }

  async function refreshDashboard() {
    const items = _sortProjectsForProduct(await apiGet("/api/projects"));
    $("stat-total-projects").innerText = String(items.length);

    const tbody = $("dashboard-recent-projects");
    tbody.innerHTML = "";

    const latestCard = $("dashboard-latest-card");
    const latestProject = items[0] || null;
    if (latestCard && latestProject) {
      latestCard.classList.remove("hidden");
      if ($("dashboard-latest-title")) $("dashboard-latest-title").textContent = latestProject.title || "Proyecto sin título";
      if ($("dashboard-latest-meta")) {
        $("dashboard-latest-meta").textContent = `${latestProject.format_name || latestProject.format_id || "-"} · ${latestProject.prompt_name || "Sin prompt"} · ${_formatProjectDate(latestProject)}`;
      }
      if ($("dashboard-latest-status")) $("dashboard-latest-status").innerHTML = statusBadge(_effectiveProjectStatus(latestProject));
      if ($("dashboard-latest-summary")) {
        $("dashboard-latest-summary").innerHTML = `
          <div class="rounded-2xl border bg-slate-50 px-4 py-3">
            <div class="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Estado real</div>
            <div class="mt-1 font-semibold text-slate-900">${escapeHtml(String(_effectiveProjectStatus(latestProject) || "-").replaceAll("_", " "))}</div>
          </div>
          <div class="rounded-2xl border bg-slate-50 px-4 py-3">
            <div class="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Paso sugerido</div>
            <div class="mt-1 font-semibold text-slate-900">Paso ${_inferProjectStep(latestProject)}</div>
          </div>
          <div class="rounded-2xl border bg-slate-50 px-4 py-3">
            <div class="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Última actividad</div>
            <div class="mt-1 font-semibold text-slate-900">${escapeHtml(_formatProjectDate(latestProject))}</div>
          </div>
        `;
      }
      if ($("dashboard-latest-actions")) {
        $("dashboard-latest-actions").innerHTML = _renderProjectActions(latestProject, "hero");
      }
    } else if (latestCard) {
      latestCard.classList.add("hidden");
    }

    if (!items.length) {
      $("dashboard-empty").classList.remove("hidden");
      return;
    }
    $("dashboard-empty").classList.add("hidden");

    items.slice(0, 5).forEach((project) => {
      const row = document.createElement("tr");
      row.className = "hover:bg-gray-50";
      row.innerHTML = `
        <td class="px-6 py-4">
          <div class="font-medium text-slate-800">${escapeHtml(project.title)}</div>
          <div class="text-xs text-gray-400">${escapeHtml(project.prompt_name || "")}</div>
        </td>
        <td class="px-6 py-4 text-gray-600">${escapeHtml(project.format_name || project.format_id || "")}</td>
        <td class="px-6 py-4">${statusBadge(_effectiveProjectStatus(project))}</td>
        <td class="px-6 py-4 text-gray-500">${escapeHtml(_formatProjectDate(project))}</td>
        <td class="px-6 py-4 text-right">
          <div class="flex items-center justify-end gap-2">${_renderProjectActions(project)}</div>
        </td>
      `;
      tbody.appendChild(row);
    });
  }

  function updateStepperUI() {
    $("current-step-label").innerText = String(currentStep);

    for (let i = 1; i <= TOTAL_STEPS; i += 1) {
      const dot = $(`step-${i}-dot`);
      if (!dot) continue;
      dot.className = "w-8 h-8 rounded-full flex items-center justify-center font-bold text-sm z-10";

      if (i < currentStep) {
        dot.classList.add("bg-green-500", "text-white");
        dot.innerHTML = '<i class="fa-solid fa-check"></i>';
      } else if (i === currentStep) {
        dot.classList.add("bg-blue-600", "text-white");
        dot.innerHTML = String(i);
      } else {
        dot.classList.add("bg-gray-200", "text-gray-500");
        dot.innerHTML = String(i);
      }
    }

    for (let i = 1; i < TOTAL_STEPS; i += 1) {
      const line = $(`step-${i}-line`);
      if (!line) continue;
      line.className = "flex-1 h-1 mx-2 rounded";
      if (i < currentStep) line.classList.add("bg-green-500");
      else line.classList.add("bg-gray-200");
    }
  }

  function showStep(step) {
    for (let i = 1; i <= TOTAL_STEPS; i += 1) {
      const content = $(`step-${i}-content`);
      if (!content) continue;
      if (i === step) {
        content.classList.remove("hidden");
        content.classList.add("fade-in");
      } else {
        content.classList.add("hidden");
      }
    }
  }

  function resetStepper() {
    currentStep = 1;
    currentWizardMode = "new";
    selectedFormat = null;
    selectedPrompt = null;
    currentProject = null;
    n8nSpec = null;
    simRunResult = null;
    isPreparingGuide = false;
    isRunningSimulation = false;

    if ($("btn-step1-next")) $("btn-step1-next").disabled = true;
    if ($("btn-step2-next")) $("btn-step2-next").disabled = true;
    if ($("btn-step3-next-provider")) {
      $("btn-step3-next-provider").classList.remove("hidden");
    }
    if ($("step3-loading")) $("step3-loading").classList.add("hidden");
    if ($("btn-step4-generate")) $("btn-step4-generate").classList.remove("hidden");
    if ($("step4-loading")) $("step4-loading").classList.add("hidden");

    setStep3Error("");
    setStep4Error("");

    if ($("sim-project-id")) $("sim-project-id").textContent = "-";
    if ($("sim-download-docx")) $("sim-download-docx").setAttribute("href", "#");
    if ($("sim-download-pdf")) $("sim-download-pdf").setAttribute("href", "#");

    updateStepperUI();
    showStep(1);
    _renderWizardContext(null);
  }

  function nextStep(step, options = {}) {
    currentStep = step;
    updateStepperUI();
    showStep(step);
    _renderWizardContext(currentProject);
    if (step === 4) {
      loadProviderStatus(currentProject?.id || null, { autoProbe: true }).catch(console.error);
    }
    _persistWizardState(step, String(options?.mode || "continue")).catch(() => { });
  }

  function prevStep(step) {
    currentStep = step;
    updateStepperUI();
    showStep(step);
    _renderWizardContext(currentProject);
    _persistWizardState(step, "edit").catch(() => { });
  }

  function getCategoryLabel(rawCategory) {
    const labels = {
      proyecto: "Proyecto de tesis",
      informe: "Informe de tesis",
      maestria: "Tesis de postgrado",
      posgrado: "Tesis de postgrado",
      general: "Documentos generales",
    };
    return labels[rawCategory] || rawCategory || "Sin categoria";
  }

  async function initWizard() {
    const options = arguments[0] && typeof arguments[0] === "object" ? arguments[0] : {};
    currentWizardMode = String(options?.mode || "new").toLowerCase();
    resetStepper();
    currentWizardMode = String(options?.mode || "new").toLowerCase();
    await loadFormats();
    await loadPromptsForWizard(options?.project?.prompt_id || "");
    if ($("btn-step3-next-provider")) {
      $("btn-step3-next-provider").onclick = (event) => {
        if (event) event.preventDefault();
        goToProviderStep().catch((error) => {
          setStep3Error(error?.message || "No se pudo avanzar a Seleccionar IA.");
        });
      };
    }
    if ($("btn-step4-generate")) {
      $("btn-step4-generate").onclick = (event) => {
        if (event) event.preventDefault();
        triggerGeneration().catch((error) => {
          setStep4Error(error?.message || "No se pudo iniciar la generación.");
        });
      };
    }
    if ($("btn-provider-refresh")) {
      $("btn-provider-refresh").onclick = () => probeProviderStatus(currentProject?.id || null).catch(console.error);
    }
    document.querySelectorAll("[data-wizard-jump]").forEach((button) => {
      button.onclick = () => goToProjectStep(Number(button.getAttribute("data-wizard-jump") || 1));
    });
    if (options?.project) {
      await _rehydrateWizardProject(options.project, options);
      return;
    }
    _renderWizardContext(null);
    await loadProviderStatus();
  }

  async function loadFormats() {
    // Use raw fetch to read X-Upstream-Online / X-Data-Source headers.
    const raw = await fetch("/api/formats");
    if (!raw.ok) throw new Error(await parseError(raw));

    gicatesisOnline = raw.headers.get("X-Upstream-Online") !== "false";
    const dataSource = raw.headers.get("X-Data-Source") || "cache";

    const response = await raw.json();
    const items = response.formats || [];
    formatsCache = items;

    // Show / hide the offline banner
    const banner = $("gicatesis-offline-banner");
    if (banner) {
      if (!gicatesisOnline) {
        banner.classList.remove("hidden");
      } else {
        banner.classList.add("hidden");
      }
    }

    const universities = Array.from(new Set(items.map((x) => x.university))).filter(Boolean).sort();
    const categories = Array.from(new Set(items.map((x) => getCategoryLabel(x.category)))).filter(Boolean).sort();

    const uniSel = $("filter-university");
    const catSel = $("filter-career");

    uniSel.innerHTML = '<option value="">Todas las universidades</option>' +
      universities.map((u) => `<option value="${escapeHtml(u)}">${escapeHtml(String(u).toUpperCase())}</option>`).join("");
    catSel.innerHTML = '<option value="">Tipo de documento</option>' +
      categories.map((c) => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join("");

    async function render() {
      const selectedUni = uniSel.value || "";
      const selectedCategory = catSel.value || "";
      const filtered = items.filter((item) => {
        const matchesUni = !selectedUni || item.university === selectedUni;
        const matchesCategory = !selectedCategory || getCategoryLabel(item.category) === selectedCategory;
        return matchesUni && matchesCategory;
      });

      const grid = $("formats-grid");
      grid.innerHTML = "";

      if (!filtered.length) {
        grid.innerHTML = '<div class="text-sm text-gray-500">No hay formatos para esos filtros.</div>';
        return;
      }

      filtered.forEach((format) => {
        const card = document.createElement("div");
        card.className = "format-card border-2 border-gray-100 hover:border-blue-400 p-4 rounded-lg cursor-pointer transition group relative bg-white";
        card.dataset.formatId = String(format.id || "");
        card.onclick = () => selectFormat(format, card);

        const docType = format.documentType ? ` (${format.documentType})` : "";
        const universityCode = String(format.university || "generic").toLowerCase();
        const logoUrl = `/api/assets/logos/${universityCode}.png`;

        // When GicaTesis is offline, skip loading remote logos — use text fallback.
        const logoHtml = gicatesisOnline
          ? `<img src="${logoUrl}" alt="${escapeHtml(universityCode)}" class="w-full h-full object-contain"
              onerror="this.onerror=null;this.parentNode.innerHTML='<span class=&quot;text-blue-700 font-bold&quot;>${escapeHtml(String(universityCode).toUpperCase())}</span>'">`
          : `<span class="text-blue-700 font-bold">${escapeHtml(String(universityCode).toUpperCase())}</span>`;

        card.innerHTML = `
          <div class="absolute top-3 right-3 opacity-0 group-hover:opacity-100 text-blue-500">
            <i class="fa-solid fa-circle-check fa-lg"></i>
          </div>
          <div class="flex items-center gap-4 mb-3">
            <div class="w-12 h-12 shrink-0 flex items-center justify-center p-1 border rounded bg-gray-50">
              ${logoHtml}
            </div>
            <div>
              <div class="font-bold text-sm text-slate-800 leading-tight">${escapeHtml(format.title || format.name || format.id)}</div>
              <div class="text-xs text-gray-400 mt-1">v${escapeHtml(String(format.version || "").substring(0, 8))}</div>
            </div>
          </div>
          <div class="mt-2 text-xs text-slate-500 bg-slate-50 p-2 rounded flex items-center gap-2">
            <i class="fa-solid fa-tag text-blue-400"></i>
            <span>${escapeHtml(getCategoryLabel(format.category))}${escapeHtml(docType)}</span>
          </div>
        `;

        grid.appendChild(card);
      });
      _syncSelectedFormatCard();
    }

    uniSel.onchange = render;
    catSel.onchange = render;
    await render();
  }

  function selectFormat(formatObj, cardEl) {
    document.querySelectorAll(".format-card").forEach((c) => c.classList.remove("border-blue-500", "bg-blue-50"));
    selectedFormat = formatObj;
    if (cardEl) {
      cardEl.classList.remove("border-gray-100");
      cardEl.classList.add("border-blue-500", "bg-blue-50");
    } else {
      _syncSelectedFormatCard();
    }
    $("btn-step1-next").disabled = false;
  }

  function _syncSelectedFormatCard() {
    document.querySelectorAll(".format-card").forEach((card) => {
      const isSelected = String(card.dataset.formatId || "") === String(selectedFormat?.id || "");
      card.classList.remove("border-blue-500", "bg-blue-50");
      if (isSelected) {
        card.classList.add("border-blue-500", "bg-blue-50");
      }
    });
  }

  async function loadPromptsForWizard(includePromptId = "") {
    const items = await apiGet("/api/prompts");
    promptsCache = items;
    const active = items.filter((p) => p.is_active);
    const selectedPromptId = String(includePromptId || currentProject?.prompt_id || "").trim();
    const selectedPromptEntry = items.find((item) => String(item?.id || "") === selectedPromptId);
    const visiblePrompts = selectedPromptEntry && !active.some((item) => item.id === selectedPromptEntry.id)
      ? [selectedPromptEntry, ...active]
      : active;

    const grid = $("prompts-grid");
    grid.innerHTML = "";

    if (!visiblePrompts.length) {
      grid.innerHTML = '<div class="text-sm text-gray-500">No hay prompts activos. Ve a Gestion prompts.</div>';
      return;
    }

    visiblePrompts.forEach((prompt, idx) => {
      const card = document.createElement("div");
      card.className = "prompt-card border-2 border-gray-100 hover:border-blue-500 p-5 rounded-lg cursor-pointer transition bg-white text-center";
      card.dataset.promptId = String(prompt.id || "");
      card.onclick = () => selectPrompt(prompt, card);

      const badge = idx === 0
        ? '<span class="bg-indigo-100 text-indigo-700 text-[10px] px-2 py-0.5 rounded-full font-bold">RECOMENDADO</span>'
        : "";

      card.innerHTML = `
        <div class="w-12 h-12 bg-indigo-50 text-indigo-600 rounded-full flex items-center justify-center mx-auto mb-3">
          <i class="fa-solid fa-book-open"></i>
        </div>
        <h4 class="font-bold text-slate-800">${escapeHtml(prompt.name)}</h4>
        <p class="text-xs text-gray-500 mt-1 mb-3">${escapeHtml(prompt.doc_type || "")}</p>
        ${badge}
      `;

      grid.appendChild(card);
    });
    _syncSelectedPromptCard();
  }

  function selectPrompt(promptObj, cardEl) {
    document.querySelectorAll(".prompt-card").forEach((c) => c.classList.remove("border-blue-500", "ring-2", "ring-blue-200"));
    selectedPrompt = promptObj;
    if (cardEl) {
      cardEl.classList.remove("border-gray-100");
      cardEl.classList.add("border-blue-500", "ring-2", "ring-blue-200");
    } else {
      _syncSelectedPromptCard();
    }
    $("btn-step2-next").disabled = false;
    renderDynamicForm();
  }

  function _syncSelectedPromptCard() {
    document.querySelectorAll(".prompt-card").forEach((card) => {
      const isSelected = String(card.dataset.promptId || "") === String(selectedPrompt?.id || "");
      card.classList.remove("border-blue-500", "ring-2", "ring-blue-200");
      if (isSelected) {
        card.classList.add("border-blue-500", "ring-2", "ring-blue-200");
      }
    });
  }

  function renderDynamicForm() {
    const container = $("dynamic-form");
    if (!container) return;
    container.innerHTML = "";

    if (!selectedPrompt) {
      container.innerHTML = '<div class="text-sm text-gray-500 text-center py-10 font-medium font-inter">Selecciona un formato para activar la guía.</div>';
      return;
    }

    // 1. DICCIONARIO DE AYUDA ACADÉMICA
    const academicHelp = {
      "diagnostico_local": "Describe fallas, demoras o síntomas detectados en la empresa. Es obligatorio usar herramientas como Ishikawa o Pareto para el sustento técnico.",
      "problema_principal": "Formula la gran pregunta de investigación: ¿De qué manera la propuesta X mejora la situación Y?",
      "autor": "Tus nombres y apellidos completos tal como deben aparecer en la carátula oficial.",
      "asesor": "Nombre del mentor asignado por la facultad. Comparte la responsabilidad de la autenticidad del trabajo.",
      "facultad": "Nombre completo de la facultad (ej: Facultad de Ingeniería Eléctrica y Electrónica).",
      "escuela": "Tu carrera profesional específica dentro de la UNAC.",
      "linea_investigacion": "Debe ser una de las líneas oficiales aprobadas por tu Escuela Profesional.",
      "anio": "El año de sustentación o presentación del informe.",
      "herramienta_ingenieria": "Es obligatorio según el reglamento: utiliza un Diagrama de Ishikawa (Causa-Efecto), Pareto (80/20), Árbol de problemas o Matriz de Vester para diagnosticar técnicamente el origen del problema.",
      "datos_evidencia": "Presenta el sustento numérico real: estadísticas de fallas, reportes de mermas, horas de parada de máquina o costos actuales por inactividad.",
      "objetivo_general": "Define tu meta final. Debe iniciar con un verbo fuerte en infinitivo (Determinar, Diseñar, Implementar) y responder directamente a tu pregunta de investigación principal.",
      "impacto_economico": "¿Cuánto dinero ahorrará la empresa o cuál es el beneficio costo-beneficio de tu propuesta?",
      "variable_independiente": "Es tu propuesta o 'el remedio': el sistema, software, algoritmo o plan de mantenimiento que vas a aplicar.",
      "variable_dependiente": "Es el 'paciente' que quieres curar: el indicador técnico que se verá afectado positivamente por tu propuesta.",
      "resumen_antecedentes": "Resume investigaciones indexadas de los últimos 5 a 10 años. Menciona: Autor, Año, Objetivo, Metodología y resultados numéricos.",
      "dimensiones_variables": "Son los grandes componentes en los que divides tus variables para poder medirlas.",
      "indicadores_medida": "Es la unidad de medida exacta y observable de tus dimensiones. Ejemplos: Porcentaje (%), Horas (h), Soles (S/).",
      "poblacion_total": "El universo completo de elementos con características comunes para tu estudio.",
      "muestra_estudio": "Es la parte representativa que vas a medir realmente.",
      "instrumentos_utilizados": "Son tus herramientas de captura: cuestionarios validados, fichas de registro, sensores calibrados.",
      "datos_recolectados": "Ingresa aquí los resultados de tus mediciones o el resumen estadístico descriptivo.",
      "resultados_pruebas_estadisticas": "Ingresa el p-valor (Sig.) obtenido en SPSS o Minitab. Si es menor a 0.05, tu hipótesis ha sido demostrada.",
      "conclusiones_numéricas": "Responde a tus objetivos con hallazgos directos. No uses opiniones, usa cifras reales.",
      "propuestas_accion": "Acciones prácticas y viables dirigidas a la empresa.",
      "problema_general": "Es la interrogante maestra que busca comprender el fenómeno y las categorías centrales de tu estudio. Debe ser una pregunta abierta que invite a profundizar en significados.",
      "problemas_especificos": "Son las sub-preguntas que desglosan tus categorías preliminares para analizar procesos o vivencias específicas.",
      "objetivos_especificos": "Indica los pasos para analizar cada categoría. ¡Importante! Debes iniciar con verbos como: Comprender, Interpretar, Analizar o Describir.",
      "justificacion_estudio": "Explica la utilidad de tu tesis: ¿Cómo ayuda a la empresa a entender sus procesos y qué nuevos conceptos aporta?",
      "delimitacion_espacial": "Indica el lugar exacto (empresa, área o institución) donde realizarás la toma de datos.",
      "delimitacion_temporal": "Define con claridad el periodo de tiempo (meses o años) que abarca tu recolección de información.",
      "antecedentes": "Resume investigaciones similares de los últimos 5-10 años. Menciona autor, año, diseño y hallazgos.",
      "bases_teoricas": "Es el sustento científico de tu tesis. Analiza las teorías y modelos que explican tus categorías.",
      "marco_conceptual": "Define conceptualmente tus categorías y subcategorías basándote en la literatura revisada.",
      "escenario_estudio": "Describe el ambiente físico y social donde realizarás el estudio.",
      "informantes_clave": "Identifica a las personas que te darán la información y menciona el 'muestreo por saturación'.",
      "aspectos_eticos": "Declara el respeto al anonimato, la justicia y el uso de consentimientos informados.",
      "categorias_emergentes": "Presenta los grandes hallazgos encontrados. Incluye fragmentos de entrevistas (citas textuales).",
      "conclusiones_cualitativas": "Redacta reflexiones finales sobre las comprensiones logradas.",
      "conclusiones_numericas": "Son las respuestas directas y numeradas a tus objetivos.",
      "diseno_cualitativo": "Define si tu investigación es Fenomenológica, Etnográfica, de Teoría Fundamentada o un Estudio de Caso.",
      "matriz_categorizacion": "Es la tabla que organiza tus Categorías Apriorísticas y sus componentes (Subcategorías).",
      "cronograma_actividades": "Muestra la secuencia de todos los pasos de tu investigación.",
      "presupuesto_soles": "Presenta el detalle de los recursos humanos, materiales y financieros.",
      "delimitacion_teorica": "Especifica las teorías, normas técnicas (ISO, IEEE, ANSI) o modelos de ingeniería.",
      "hipotesis_general": "Es la respuesta tentativa y probable a tu problema principal.",
      "hipotesis_especificas": "Son las respuestas probables a cada uno de tus problemas específicos.",
      "descripcion_problema": "Es el pilar de tu tesis UNI. Debes plantear el problema técnico a resolver de manera detallada, sentando las bases para tu hipótesis técnica.",
      "justificacion_cientifica": "Prioridad técnica: Describe el problema como un análisis de causa y efecto. Debe señalar por qué tu investigación es relevante académica y económicamente.",
      "metas_cuantitativas": "Obligatorio en objetivos: Indica resultados medibles que esperas alcanzar a corto, mediano y largo plazo.",
      "resumen_proyecto": "UNI: Describe brevemente las características generales del proyecto. No incluyas objetivos, metas ni bibliografía aquí.",
      "hipotesis_trabajo": "Propuesta técnica lógica que responde al problema planteado.",
      "infraestructura_requerida": "Descripción de los laboratorios, talleres o instalaciones físicas necesarias.",
      "metodologia_etapas": "Pasos secuenciales del proyecto. La UNI exige distinguir entre las etapas de fundamentación teórica y las experimentales.",
      "procedimientos_tecnicos": "Detalle de los métodos, algoritmos o protocolos de ingeniería que aplicarás.",
      "usuarios_finales": "Identifica a las personas o sectores que usarán el producto de tu investigación.",
      "productos_tangibles": "Resultados físicos o digitales que entregarás: patentes, prototipos, hardware o software.",
      "recursos_humanos": "Lista del personal técnico involucrado, detallando su calificación y función.",
      "recursos_materiales": "Instrumentos, equipos y materiales necesarios, indicando especificaciones técnicas.",
      "cronograma_detallado": "Calendario de actividades que debe incluir las fechas de entrega de informes de avance.",
      "partidas_presupuestales": "Clasificación de gastos según el formato fiscal: subvenciones, bienes, servicios, equipos.",
      "calendario_gastos": "Cronograma financiero que especifica en qué periodos se realizará cada desembolso.",
      "antecedentes_cientificos": "UNI: Describe la evolución del conocimiento técnico y el estado del arte de tu tema.",
      "carrera": "Escribe el nombre de tu especialidad tal como figura en los registros oficiales.",
      "programa_maestria": "Escribe el nombre exacto de tu mención o programa.",
      "unidad_posgrado": "Nombre de la Unidad de Posgrado de tu facultad correspondiente.",
      "grado_academico": "Grado al que optas (ej: Maestro en Ciencias de la Ingeniería).",
      "codigo_ocde": "Código y descripción según la clasificación OCDE para áreas de ciencia y tecnología.",
      "propuesta_solucion": "Menciona la mejora técnica o el modelo interpretativo que propones para el problema.",
      "justificacion_importancia": "Sustenta la relevancia teórica, práctica y social. Indica quiénes son los beneficiarios.",
      "limitaciones_estudio": "Indica factores (tiempo, acceso a datos) que restringen el estudio.",
      "antecedentes_internacionales": "Resumen exhaustivo de investigaciones extranjeras (autor, año, metodología y hallazgos).",
      "antecedentes_nacionales": "Investigaciones peruanas previas. Detalla qué aportan a tu tesis actual.",
      "terminos_basicos": "Glosario de conceptos técnicos y categorías operativas alineadas al contexto de tu investigación.",
      "participantes_muestreo": "Describe a tus informantes clave, criterios de selección y sustenta el tamaño de muestra.",
      "instrumentos_recoleccion": "Detalla las técnicas (entrevista, focus group) y herramientas, incluyendo su validez.",
      "procedimiento_analisis": "Explica el paso a paso: inmersión en campo, transcripción y procesamiento de datos.",
      "rigor_cientifico": "Explica cómo garantizas la credibilidad, transferibilidad, dependencia y confirmabilidad.",
      "metodo_analisis_datos": "Enfoque de análisis (temático, contenido) y uso de software como Atlas.ti o NVivo.",
      "aspectos_eticos_investigacion": "Detalla el uso de consentimiento informado, confidencialidad y aprobación institucional.",
      "presentacion_resultados": "Hallazgos ordenados por categorías con evidencias (citas textuales) y figuras numeradas.",
      "discusion_hallazgos": "Interpreta tus resultados contrastándolos con la literatura y antecedentes revisados.",
      "conclusiones_estudio": "Sentencias directas y numeradas que responden a los objetivos e hipótesis planteadas.",
      "recomendaciones_estudio": "Sugerencias aplicables para la institución o sector y nuevas líneas de investigación.",
      "orcid_asesor": "Código ORCID de 16 dígitos que identifica a tu asesor como investigador a nivel internacional.",
      "lugar_ejecucion": "Nombre de la empresa, institución o área geográfica donde realizarás la recolección de datos.",
      "unidad_analisis": "Es el objeto, proceso, persona o grupo del cual vas a extraer la información para tu estudio.",
      "mencion": "Nombre exacto de la especialidad del programa de posgrado.",
      "introduccion_tesis": "Visión general que contextualiza el tema de investigación y describe la estructura del documento.",
      "metodologia_posgrado": "Descripción técnica de la estrategia de investigación, incluyendo técnicas e instrumentos.",
      "definicion_terminos": "Glosario especializado que define los conceptos técnicos clave.",
      "analisis_resultados": "Presentación y examen minucioso de los datos recolectados y resultados técnicos.",
      "contrastacion_hipotesis": "Proceso técnico y estadístico donde se valida o rechaza la hipótesis de investigación.",
      "conclusiones_posgrado": "Sentencias directas y numeradas que sintetizan los hallazgos más relevantes.",
      "recomendaciones_posgrado": "Propuestas de acción técnica para el sector productivo o nuevas líneas de investigación."
    };

    const vars = Array.isArray(selectedPrompt.variables) ? selectedPrompt.variables : [];

    // 2. FILTRADO: REQUERIDOS (Pilares) VS COMPLEMENTARIOS
    const mainKeys = [
      "diagnostico_local",
      "problema_principal",
      "problema_general",
      "descripcion_problema",
      "justificacion_cientifica",
      "resumen_proyecto"
    ];

    const cleanVars = vars.map(v => v.trim().toLowerCase());
    const mainVars = cleanVars.filter(v => mainKeys.includes(v));
    const secondaryVars = cleanVars.filter(v => !mainKeys.includes(v));

    // --- SECCIÓN 1: PILARES MAESTROS ---
    const sectionRequired = document.createElement("div");
    sectionRequired.className = "mb-8 space-y-6";
    sectionRequired.innerHTML = `
        <div class="flex items-center gap-3 mb-6">
            <div class="h-6 w-1 bg-blue-600 rounded-full shadow-[0_0_10px_rgba(37,99,235,0.3)]"></div>
            <h3 class="text-xs font-black uppercase tracking-widest text-slate-800">1. Pilares de la Investigación</h3>
        </div>
    `;
    container.appendChild(sectionRequired);

    // BLOQUE DE TÍTULO
    const titleBlock = document.createElement("div");
    titleBlock.className = "p-6 bg-blue-50 rounded-3xl border-2 border-blue-100 shadow-sm mb-6 group transition-all";
    titleBlock.innerHTML = `
        <div class="flex justify-between items-center mb-3 px-1">
            <label class="block text-[10px] font-black text-blue-900 uppercase tracking-widest">Título del Proyecto</label>
            <span class="text-[9px] bg-blue-600 text-white px-2 py-0.5 rounded-full font-bold">OBLIGATORIO</span>
        </div>
        <input id="var_title" type="text" class="w-full p-4 border-2 border-blue-200 rounded-2xl focus:border-blue-500 focus:ring-4 focus:ring-blue-500/10 outline-none bg-white font-bold text-slate-800 shadow-inner" placeholder="Ej: Implementación de un sistema para mejorar...">
        <p class="mt-3 text-[10px] text-slate-400 italic group-hover:text-blue-700 group-focus-within:text-blue-700 transition-all px-1">
            <i class="fa-solid fa-lightbulb mr-1"></i> Fórmula: [Solución] + [Variable/Problema] + [Lugar de estudio].
        </p>
    `;
    sectionRequired.appendChild(titleBlock);

    // Renderizar Pilares
    mainVars.forEach(v => renderField(v, sectionRequired, true));

    // --- SECCIÓN 2: DATOS COMPLEMENTARIOS (COLAPSABLE) ---
    if (secondaryVars.length > 0) {
      const accordionWrapper = document.createElement("div");
      accordionWrapper.className = "mt-10 border-t border-slate-100 pt-6";

      const toggleBtn = document.createElement("button");
      toggleBtn.className = "flex items-center justify-between w-full p-4 bg-slate-50 hover:bg-slate-100 rounded-2xl transition-all border border-slate-200 group";
      toggleBtn.innerHTML = `
            <div class="flex items-center gap-3">
                <div class="w-8 h-8 rounded-xl bg-white flex items-center justify-center shadow-sm text-slate-400 group-hover:text-blue-600 transition-colors">
                    <i class="fa-solid fa-folder-plus text-xs"></i>
                </div>
                <div class="text-left">
                    <span class="block text-[11px] font-black text-slate-700 uppercase tracking-tight">DATOS COMPLEMENTARIOS</span>
                    <span class="block text-[9px] text-slate-500 font-medium">Información opcional para la carátula oficial.</span>
                </div>
            </div>
            <i class="fa-solid fa-chevron-down text-slate-400 group-hover:translate-y-1 transition-all mr-2"></i>
        `;

      const optionalContent = document.createElement("div");
      optionalContent.className = "hidden mt-6 grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-4 px-2";

      toggleBtn.onclick = (e) => {
        e.preventDefault();
        optionalContent.classList.toggle("hidden");
        toggleBtn.querySelector(".fa-chevron-down").classList.toggle("rotate-180");
      };

      secondaryVars.forEach(v => renderField(v, optionalContent, false));

      accordionWrapper.appendChild(toggleBtn);
      accordionWrapper.appendChild(optionalContent);
      container.appendChild(accordionWrapper);
    }

    function renderField(variable, target, isMain) {
      const id = "var_" + variable;
      const cleanLabel = variable.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ');
      const helpText = academicHelp[variable] || `Dato requerido de ${cleanLabel.toLowerCase()} para el rigor técnico.`;
      const isLong = /(diagnostico|problema|resumen|conclusiones|propuestas|objetivo|metodologia|hipotesis|justificacion|antecedentes|bases_teoricas|marco|descripcion|introduccion|analisis|contrastacion|discusion|resultados)/i.test(variable);

      const block = document.createElement("div");
      block.className = `group ${isMain ? 'mb-8' : 'mb-2'}`;
      block.innerHTML = `
          <div class="flex justify-between items-center mb-2 px-1">
            <label class="block text-[10px] font-bold ${isMain ? 'text-slate-700' : 'text-slate-400'} uppercase tracking-widest group-hover:text-blue-600 transition-colors">${cleanLabel}</label>
            ${isMain ? '<span class="text-[8px] bg-amber-100 text-amber-700 px-2 py-0.5 rounded font-black uppercase tracking-tighter">Prioridad</span>' : ''}
          </div>
          <div class="relative">
            ${isLong
          ? `<textarea id="${id}" rows="3" class="w-full p-4 border-2 ${isMain ? 'border-slate-300' : 'border-slate-200'} rounded-2xl focus:border-blue-600 focus:ring-4 focus:ring-blue-500/10 outline-none text-sm transition-all bg-white" placeholder="Redacta aquí..."></textarea>`
          : `<input id="${id}" type="text" class="w-full p-4 border-2 ${isMain ? 'border-slate-300' : 'border-slate-200'} rounded-2xl focus:border-blue-600 focus:ring-4 focus:ring-blue-500/10 outline-none text-sm transition-all bg-white" placeholder="Ingresa el dato...">`
        }
          </div>
          <p class="mt-2 text-[10px] text-slate-400 italic flex items-start gap-1.5 px-1 font-medium leading-tight group-hover:text-blue-700 group-focus-within:text-blue-800 transition-all duration-300">
            <i class="fa-solid fa-graduation-cap mt-0.5 opacity-50 group-hover:opacity-100 group-hover:scale-110 transition-all"></i>
            <span>${helpText}</span>
          </p>
        `;
      target.appendChild(block);
    }
  }

  function collectWizardPayload() {
    const values = {};
    (selectedPrompt?.variables || []).forEach((variable) => {
      const el = $("var_" + variable);
      values[variable] = el ? el.value : "";
    });

    const title = $("var_title")?.value || values.tema || "Proyecto";
    return { title, values };
  }

  function _resolveProjectFormat(project) {
    const formatId = String(project?.format_id || "").trim();
    if (!formatId) return null;
    return formatsCache.find((item) => String(item?.id || "") === formatId)
      || {
        id: formatId,
        title: project?.format_name || formatId,
        name: project?.format_name || formatId,
        version: project?.format_version || "",
      };
  }

  function _resolveProjectPrompt(project) {
    const promptId = String(project?.prompt_id || "").trim();
    if (!promptId) return null;
    return promptsCache.find((item) => String(item?.id || "") === promptId) || null;
  }

  function _populateWizardValues(project) {
    const values = _projectValues(project);
    if ($("var_title")) {
      $("var_title").value = String(project?.title || values.title || values.tema || "");
    }
    (selectedPrompt?.variables || []).forEach((variable) => {
      const input = $("var_" + variable);
      if (!input) return;
      input.value = String(values?.[variable] ?? "");
    });
  }

  async function _persistWizardState(step, mode = "continue") {
    if (!currentProject?.id) return;
    try {
      const currentWizardState = currentProject?.wizard_state && typeof currentProject.wizard_state === "object"
        ? currentProject.wizard_state
        : {};
      const updated = await apiSend(`/api/projects/${encodeURIComponent(currentProject.id)}`, "PUT", {
        wizardState: {
          currentStep: step,
          lastCompletedStep: Math.max(
            Number(currentWizardState?.last_completed_step || currentWizardState?.lastCompletedStep || 1),
            step,
          ),
          lastOpenMode: mode,
          updatedAt: new Date().toISOString(),
        },
      });
      currentProject = { ...(updated || currentProject), id: currentProject.id };
    } catch (_) {
      // El flujo principal no debe bloquearse si solo falla la persistencia de step.
    }
  }

  function _renderWizardContext(project) {
    const panel = $("wizard-context-panel");
    if (!panel) return;
    if (!project?.id || currentWizardMode === "review") {
      panel.classList.add("hidden");
      return;
    }

    panel.classList.remove("hidden");
    if ($("wizard-context-title")) {
      $("wizard-context-title").textContent = project.title || "Proyecto existente";
    }
    if ($("wizard-context-text")) {
      $("wizard-context-text").textContent = `Proyecto ${project.id} · ${project.prompt_name || "Sin prompt"} · ${project.format_name || project.format_id || "Sin formato"}. Si modificas pasos previos y guardas, la generación posterior se reiniciará de forma explícita.`;
    }
    if ($("wizard-context-status")) {
      $("wizard-context-status").innerHTML = statusBadge(_effectiveProjectStatus(project));
    }
    document.querySelectorAll("[data-wizard-jump]").forEach((button) => {
      const buttonStep = Number(button.getAttribute("data-wizard-jump") || 1);
      button.classList.remove("bg-amber-100", "border-amber-400");
      if (buttonStep === currentStep) {
        button.classList.add("bg-amber-100", "border-amber-400");
      }
    });
  }

  async function _rehydrateWizardProject(project, options = {}) {
    currentProject = project;
    selectedFormat = _resolveProjectFormat(project);
    if (selectedFormat) {
      _syncSelectedFormatCard();
      if ($("btn-step1-next")) $("btn-step1-next").disabled = false;
    }

    selectedPrompt = _resolveProjectPrompt(project);
    if (selectedPrompt) {
      _syncSelectedPromptCard();
      if ($("btn-step2-next")) $("btn-step2-next").disabled = false;
      renderDynamicForm();
      _populateWizardValues(project);
    } else {
      renderDynamicForm();
    }

    _renderWizardContext(project);

    const targetStep = Math.max(1, Math.min(7, Number(options?.step || _inferProjectStep(project, options?.mode))));
    currentStep = targetStep;
    updateStepperUI();
    showStep(targetStep);

    if (targetStep >= 4) {
      await loadProviderStatus(project.id || null);
    }
    if (targetStep >= 5) {
      await _renderLiveTrace(project.id);
    }
    if (targetStep === 7) {
      simRunResult = _buildArtifacts(project);
      continueToSimDownloads();
    }
    await _persistWizardState(targetStep, String(options?.mode || "continue"));
  }

  async function openProject(projectId, options = {}) {
    const project = await apiGet(`/api/projects/${encodeURIComponent(projectId)}`);
    const step = Math.max(1, Math.min(7, Number(options?.step || _inferProjectStep(project, options?.mode))));
    showView("wizard", { ...options, project, step });
  }

  function goToProjectStep(step) {
    const targetStep = Math.max(1, Math.min(4, Number(step || 1)));
    nextStep(targetStep, { mode: "edit" });
  }

  function _hasProjectCoreChanges(project, wizardPayload) {
    if (!project) return false;
    const currentValues = _projectValues(project);
    const nextValues = wizardPayload?.values || {};
    const currentKeys = Array.from(new Set([...Object.keys(currentValues), ...Object.keys(nextValues)])).sort();
    const valuesChanged = currentKeys.some((key) => String(currentValues?.[key] ?? "") !== String(nextValues?.[key] ?? ""));
    return (
      String(project?.format_id || "") !== String(selectedFormat?.id || "")
      || String(project?.prompt_id || "") !== String(selectedPrompt?.id || "")
      || String(project?.title || "") !== String(wizardPayload?.title || "")
      || valuesChanged
    );
  }

  function setStep3Error(message) {
    const el = $("step3-error");
    if (!el) return;
    const normalized = String(message || "").trim();
    if (!normalized) {
      el.classList.add("hidden");
      el.textContent = "";
      return;
    }
    el.classList.remove("hidden");
    el.textContent = normalized;
  }

  function setStep4Error(message) {
    const el = $("step4-error");
    if (!el) return;
    const normalized = String(message || "").trim();
    if (!normalized) {
      el.classList.add("hidden");
      el.textContent = "";
      return;
    }
    el.classList.remove("hidden");
    el.textContent = normalized;
  }

  function setProviderSelectorError(message) {
    const el = $("provider-select-error");
    if (!el) return;
    const normalized = String(message || "").trim();
    if (!normalized) {
      el.classList.add("hidden");
      el.textContent = "";
      return;
    }
    el.classList.remove("hidden");
    el.textContent = normalized;
  }

  function _providerHealthMeta(provider) {
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

  function _ringMarkup({ valueText, percent, color, label, subLabel }) {
    const safePercent = Number.isFinite(percent) ? Math.max(0, Math.min(100, percent)) : 0;
    const radius = 24;
    const circumference = 2 * Math.PI * radius;
    const dash = (safePercent / 100) * circumference;
    return `
      <div class="provider-ring flex flex-col items-center">
        <svg viewBox="0 0 64 64" role="img" aria-label="${escapeHtml(label)}">
          <circle cx="32" cy="32" r="${radius}" fill="none" stroke="#e2e8f0" stroke-width="6"></circle>
          <circle
            cx="32" cy="32" r="${radius}" fill="none" stroke="${escapeHtml(color)}" stroke-width="6"
            stroke-linecap="round"
            stroke-dasharray="${dash} ${circumference - dash}"
            transform="rotate(-90 32 32)"
          ></circle>
          <text x="32" y="31" text-anchor="middle" font-size="10" fill="#0f172a">${escapeHtml(valueText)}</text>
          <text x="32" y="42" text-anchor="middle" font-size="7.5" fill="#64748b">${safePercent}%</text>
        </svg>
        <div class="provider-ring-label">${escapeHtml(label)}</div>
        <div class="text-[10px] text-slate-500">${escapeHtml(subLabel || "")}</div>
      </div>
    `;
  }

  function _findProvider(providerId) {
    const providers = providerStatusCache?.providers;
    if (!Array.isArray(providers)) return null;
    return providers.find((item) => item && item.id === providerId) || null;
  }

  function _providerEligibleForFallback(provider) {
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

  function _fallbackOptionsForPrimary(primaryProvider) {
    const providers = Array.isArray(providerStatusCache?.providers)
      ? providerStatusCache.providers
      : [];
    return providers.filter((item) =>
      item?.id &&
      item.id !== primaryProvider &&
      _providerEligibleForFallback(item)
    );
  }

  function _computeFallbackSelection(primaryProvider) {
    const options = _fallbackOptionsForPrimary(primaryProvider);
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

  function _providersStatusUrl(projectId = null) {
    if (!projectId) return "/api/providers/status";
    return `/api/providers/status?projectId=${encodeURIComponent(projectId)}`;
  }

  function _providersProbeUrl(projectId = null) {
    if (!projectId) return "/api/providers/probe";
    return `/api/providers/probe?projectId=${encodeURIComponent(projectId)}`;
  }

  function _providersSelectUrl(projectId = null) {
    if (!projectId) return "/api/providers/select";
    return `/api/providers/select?projectId=${encodeURIComponent(projectId)}`;
  }

  async function _saveProviderSelection(payload, projectId = null) {
    const selectedProvider = payload.provider || providerStatusCache?.selected_provider || "gemini";
    const mode = payload.mode || providerStatusCache?.mode || "auto";
    const fallbackDefault = _computeFallbackSelection(selectedProvider);
    const fallbackProviderRaw = payload.fallback_provider || providerStatusCache?.fallback_provider || fallbackDefault.fallback_provider;
    const fallbackProvider = mode === "auto" && fallbackProviderRaw === selectedProvider
      ? fallbackDefault.fallback_provider
      : fallbackProviderRaw;
    const fallbackProviderData = _findProvider(fallbackProvider);
    const body = {
      provider: selectedProvider,
      model: payload.model || _findProvider(selectedProvider)?.model || providerStatusCache?.selected_model || "",
      fallback_provider: fallbackProvider || "",
      fallback_model: payload.fallback_model || fallbackProviderData?.model || providerStatusCache?.fallback_model || fallbackDefault.fallback_model,
      mode,
    };
    const updated = await apiSend(_providersSelectUrl(projectId), "POST", body);
    providerStatusCache = updated;
    renderProviderSelector(updated);
  }

  async function _selectProvider(providerId) {
    const provider = _findProvider(providerId);
    if (!provider) return;
    const mode = providerStatusCache?.mode || "auto";
    const fallback = _computeFallbackSelection(providerId);
    await _saveProviderSelection({
      provider: providerId,
      model: provider.model || "",
      fallback_provider: mode === "auto" ? fallback.fallback_provider : (providerStatusCache?.fallback_provider || fallback.fallback_provider),
      fallback_model: mode === "auto" ? fallback.fallback_model : (providerStatusCache?.fallback_model || fallback.fallback_model),
      mode,
    }, currentProject?.id || null);
  }

  async function _setProviderMode(mode) {
    if (!providerStatusCache) return;
    const selectedProvider = providerStatusCache.selected_provider || "gemini";
    const selectedModel = providerStatusCache.selected_model || (_findProvider(selectedProvider)?.model || "");
    const options = _fallbackOptionsForPrimary(selectedProvider);
    const currentFallback = providerStatusCache.fallback_provider || "";
    const fallbackCandidate = options.find((item) => item.id === currentFallback) || options[0] || null;
    const fallback = {
      fallback_provider: fallbackCandidate?.id || "",
      fallback_model: fallbackCandidate?.model || "",
    };
    await _saveProviderSelection({
      provider: selectedProvider,
      model: selectedModel,
      fallback_provider: mode === "auto" ? fallback.fallback_provider : (providerStatusCache.fallback_provider || fallback.fallback_provider),
      fallback_model: mode === "auto" ? fallback.fallback_model : (providerStatusCache.fallback_model || fallback.fallback_model),
      mode,
    }, currentProject?.id || null);
  }

  function renderProviderSelector(payload) {
    const container = $("provider-cards");
    if (!container) return;

    const providers = Array.isArray(payload?.providers) ? payload.providers : [];
    if (!providers.length) {
      container.innerHTML = '<div class="text-xs text-slate-500">No hay providers disponibles.</div>';
      return;
    }

    const selected = String(payload?.selected_provider || "");
    const mode = String(payload?.mode || "auto");
    const selectedProviderData = _findProvider(selected);
    const fallbackProviderData = _findProvider(payload?.fallback_provider || "");
    const fallbackText = mode === "auto"
      ? (fallbackProviderData
        ? `${fallbackProviderData.display_name || fallbackProviderData.id} (${payload?.fallback_model || fallbackProviderData.model || "-"})`
        : "Sin proveedor de respaldo disponible")
      : "Desactivado (modo fijo)";
    if ($("provider-fallback-label")) {
      $("provider-fallback-label").textContent = `Proveedor de respaldo: ${fallbackText}`;
    }

    const backupControl = $("provider-backup-control");
    const backupSelect = $("provider-backup-select");
    if (backupControl && backupSelect) {
      if (mode === "auto") {
        backupControl.classList.remove("hidden");
        const options = _fallbackOptionsForPrimary(selected);
        if (!options.length) {
          backupSelect.disabled = true;
          backupSelect.innerHTML = '<option value="">Sin proveedor de respaldo disponible</option>';
          backupSelect.onchange = null;
        } else {
          backupSelect.disabled = false;
          backupSelect.innerHTML = options
            .map((item) => {
              const label = item.display_name || item.id;
              return `<option value="${escapeHtml(item.id)}">${escapeHtml(label)} (${escapeHtml(item.model || "-")})</option>`;
            })
            .join("");
          let selectedFallback = String(payload?.fallback_provider || "");
          if (!options.some((item) => item.id === selectedFallback)) {
            selectedFallback = options[0].id;
          }
          backupSelect.value = selectedFallback;
          backupSelect.onchange = async () => {
            const fallbackProvider = String(backupSelect.value || "").trim();
            const fallbackData = _findProvider(fallbackProvider);
            try {
              setProviderSelectorError("");
              await _saveProviderSelection(
                {
                  provider: selected,
                  model: payload?.selected_model || selectedProviderData?.model || "",
                  fallback_provider: fallbackProvider,
                  fallback_model: fallbackData?.model || "",
                  mode: "auto",
                },
                currentProject?.id || null
              );
            } catch (error) {
              setProviderSelectorError(error?.message || "No se pudo guardar el proveedor de respaldo.");
            }
          };
        }
      } else {
        backupControl.classList.add("hidden");
        backupSelect.disabled = true;
        backupSelect.innerHTML = '<option value="">Desactivado en modo fijo</option>';
        backupSelect.onchange = null;
      }
    }

    if ($("provider-mode-fixed")) $("provider-mode-fixed").checked = mode === "fixed";
    if ($("provider-mode-auto")) $("provider-mode-auto").checked = mode !== "fixed";

    container.innerHTML = providers.map((provider) => {
      const health = _providerHealthMeta(provider);
      const configured = !!provider.configured;
      const isSelected = provider.id === selected;
      const probeStatus = String(provider?.probe?.status ?? provider?.last_probe_status ?? "UNVERIFIED").toUpperCase();
      const online = provider?.online === true;
      const blocked = !configured || !online || probeStatus === "EXHAUSTED" || probeStatus === "AUTH_ERROR";

      const rlRemaining = Number(provider?.rate_limit?.remaining ?? 0);
      const rlLimit = Number(provider?.rate_limit?.limit ?? 0);
      const rlReset = Number(provider?.rate_limit?.reset_seconds ?? 0);
      const rlPercent = rlLimit > 0 ? Math.round((Math.max(0, rlRemaining) / rlLimit) * 100) : 0;
      const rlText = rlLimit > 0 ? `${Math.max(0, rlRemaining)}/${rlLimit}` : "N/D";
      const rlSub = rlReset > 0 ? `Reset: ${rlReset}s` : "Sin espera";

      const quotaRemaining = provider?.quota?.remaining ?? provider?.quota?.remaining_tokens;
      const quotaLimit = provider?.quota?.limit ?? provider?.quota?.limit_tokens;
      const hasQuota = Number.isFinite(quotaRemaining) && Number.isFinite(quotaLimit) && quotaLimit > 0;
      const quotaPercent = hasQuota ? Math.round((Math.max(0, quotaRemaining) / quotaLimit) * 100) : 0;
      const quotaText = hasQuota ? `${quotaRemaining}/${quotaLimit}` : "No disp.";
      const quotaSub = hasQuota ? (provider?.quota?.period || "month") : "Estimacion";

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
          <div class="mt-3 flex items-center justify-center gap-4">
            ${_ringMarkup({
        valueText: rlText,
        percent: rlPercent,
        color: health.ring,
        label: "Rate-limit",
        subLabel: rlSub,
      })}
            ${_ringMarkup({
        valueText: quotaText,
        percent: quotaPercent,
        color: hasQuota ? health.ring : "#94a3b8",
        label: "Cuota",
        subLabel: quotaSub,
      })}
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
          await _selectProvider(targetProvider);
        } catch (error) {
          setProviderSelectorError(error?.message || "No se pudo guardar la seleccion.");
        }
      };
    });

    if ($("provider-mode-fixed")) {
      $("provider-mode-fixed").onchange = async () => {
        if (!$("provider-mode-fixed").checked) return;
        try {
          setProviderSelectorError("");
          await _setProviderMode("fixed");
        } catch (error) {
          setProviderSelectorError(error?.message || "No se pudo actualizar el modo.");
        }
      };
    }
    if ($("provider-mode-auto")) {
      $("provider-mode-auto").onchange = async () => {
        if (!$("provider-mode-auto").checked) return;
        try {
          setProviderSelectorError("");
          await _setProviderMode("auto");
        } catch (error) {
          setProviderSelectorError(error?.message || "No se pudo actualizar el modo.");
        }
      };
    }
  }

  function _needsAutoProviderProbe(payload) {
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
    const container = $("provider-cards");
    if (container) {
      container.innerHTML = '<div class="text-xs text-slate-500">Consultando estado de providers...</div>';
    }
    try {
      setProviderSelectorError("");
      const payload = await apiGet(_providersStatusUrl(projectId));
      providerStatusCache = payload;
      renderProviderSelector(payload);
      if (autoProbe && _needsAutoProviderProbe(payload)) {
        await probeProviderStatus(projectId, { showLoading: false });
      }
    } catch (error) {
      providerStatusCache = null;
      if (container) {
        container.innerHTML = '<div class="text-xs text-red-600">No se pudo obtener el estado de providers.</div>';
      }
      setProviderSelectorError(error?.message || "No se pudo obtener el estado de providers.");
    }
  }

  async function probeProviderStatus(projectId = null, options = {}) {
    const showLoading = options?.showLoading !== false;
    const container = $("provider-cards");
    if (container && showLoading) {
      container.innerHTML = '<div class="text-xs text-slate-500">Ejecutando probe real de providers...</div>';
    }
    try {
      setProviderSelectorError("");
      const payload = await apiSend(_providersProbeUrl(projectId), "POST", {});
      providerStatusCache = payload;
      renderProviderSelector(payload);
    } catch (error) {
      setProviderSelectorError(error?.message || "No se pudo ejecutar el probe de providers.");
      await loadProviderStatus(projectId);
    }
  }

  function renderN8nGuide() {
    const empty = $("n8n-guide-empty");
    const content = $("n8n-guide-content");
    if (!n8nSpec || !empty || !content) return;

    empty.classList.add("hidden");
    content.classList.remove("hidden");

    const summary = n8nSpec.summary || {};
    const summaryFormat = summary.format || {};
    const summaryPrompt = summary.prompt || {};

    $("n8n-summary").innerHTML = `
      <div><strong>Formato:</strong> ${escapeHtml(summaryFormat.title || summaryFormat.id || "")}</div>
      <div><strong>Prompt:</strong> ${escapeHtml(summaryPrompt.name || summaryPrompt.id || "")}</div>
      <div><strong>projectId:</strong> <code>${escapeHtml(summary.projectId || "")}</code></div>
      <div><strong>status:</strong> ${escapeHtml(summary.status || "")}</div>
    `;

    const envCheck = n8nSpec.envCheck || {};
    const envItems = Object.entries(envCheck);
    $("n8n-autocheck").innerHTML = envItems.map(([name, meta]) => {
      const ok = !!meta?.ok;
      const mark = ok ? "OK" : "MISSING";
      const cls = ok ? "text-green-600" : "text-red-600";
      return `<li><span class="${cls} font-semibold">${mark}</span> <code>${escapeHtml(name)}</code> = ${escapeHtml(meta?.value ?? "")}</li>`;
    }).join("");

    const request = n8nSpec.request || {};
    const expected = n8nSpec.expectedResponse || {};

    $("n8n-payload").textContent = toPrettyJson(request.payload || {});
    $("n8n-headers").textContent = toPrettyJson({
      toN8N: request.headers || {},
      toCallback: expected.headers || {},
    });

    const checklist = n8nSpec.checklist || [];
    $("n8n-checklist").innerHTML = checklist.map((item) => (
      `<li><strong>${escapeHtml(item.title || "")}</strong> - ${escapeHtml(item.detail || "")}</li>`
    )).join("");

    const payloadRuntime = request.payload?.runtime || {};
    $("n8n-urls").innerHTML = `
      <div><strong>Webhook n8n:</strong> <code>${escapeHtml(request.webhookUrl || "")}</code></div>
      <div><strong>Callback GicaGen:</strong> <code>${escapeHtml(expected.callbackUrl || payloadRuntime.callbackUrl || "")}</code></div>
      <div><strong>GicaTesis base:</strong> <code>${escapeHtml(payloadRuntime.gicatesisBaseUrl || "")}</code></div>
    `;

    $("n8n-format-detail").textContent = toPrettyJson(n8nSpec.formatDetail || {});
    $("n8n-format-definition").textContent = toPrettyJson(
      n8nSpec.formatDefinition || n8nSpec.formatDetail?.definition || {}
    );
    $("n8n-prompt-text").textContent = String(
      n8nSpec.promptDetail?.text || n8nSpec.promptText || request.payload?.prompt?.text || ""
    );
    $("n8n-expected-response").textContent = toPrettyJson(expected.bodyExample || {});
    $("n8n-sim-output").textContent = toPrettyJson(
      n8nSpec.simulationOutput || expected.bodyExample || {}
    );

    const runOutput = n8nSpec.simulationOutput || {};
    const runId = runOutput.runId || "";
    if ($("sim-run-status")) {
      $("sim-run-status").textContent = runId
        ? `Resultado simulado disponible (runId: ${runId})`
        : "Aun no se ejecuto una simulacion manual.";
    }

    const exportButton = $("btn-export-guide");
    if (exportButton) exportButton.disabled = !n8nSpec.markdown;
  }

  // =========================================================================
  // Generation flow (Step 4 progress panel)
  // =========================================================================
  const GEN_POLL_INTERVAL = 1000;   // ms between polls
  const GEN_MISSING_PROJECT_MAX_POLLS = 5;
  const GEN_SUCCESS_STATUSES = ["completed", "completed_with_incidents", "simulated"];
  const GEN_FAIL_STATUSES = [
    "failed",
    "render_failed",
    "n8n_failed",
    "generation_failed",
    "ai_failed",
    "blocked",
    "timeout",
    "cancel_requested",
  ];
  const PIPELINE_NODES = [
    { id: "format", label: "Formato JSON cargado" },
    { id: "variables", label: "Variables del proyecto" },
    { id: "prompt", label: "Prompt final armado" },
    { id: "ai", label: "IA generando secciones" },
    { id: "clean", label: "Limpieza y validacion" },
    { id: "payload", label: "Payload a GicaTesis" },
    { id: "render", label: "Render DOCX y PDF" },
  ];

  let _genCancelled = false;
  let _genTimerHandle = null;
  let _genElapsed = 0;
  let _lastRenderedTraceCount = 0;
  let _lastTraceState = null;
  let _genAiSelectedSectionKey = "";
  let _genAiExpandedGroupPath = null;

  function _sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function _formatEventTime(ts) {
    if (!ts) return "--:--";
    const d = new Date(ts);
    if (Number.isNaN(d.getTime())) return "--:--";
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  }

  function _stateIcon(state) {
    if (state === "done") return "\u2705";
    if (state === "running") return "\u23f3";
    if (state === "error") return "\u274c";
    if (state === "warn") return "\u26a0\ufe0f";
    return "\u25cb";
  }

  function _setLiveSummary(text, tone = "neutral") {
    const el = $("gen-live-summary");
    if (!el) return;
    el.textContent = text;
    el.className = "text-sm";
    if (tone === "ok") el.classList.add("text-green-600");
    else if (tone === "error") el.classList.add("text-red-600");
    else if (tone === "warn") el.classList.add("text-amber-700");
    else el.classList.add("text-slate-500");
  }

  function _updateLiveBadge(state = "live") {
    const badge = $("gen-live-badge");
    if (!badge) return;
    badge.className = "inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-semibold border";
    if (state === "ok") {
      badge.classList.add("bg-green-50", "text-green-700", "border-green-200");
      badge.innerHTML = '<span class="w-2 h-2 rounded-full bg-green-500"></span> Completado';
    } else if (state === "error") {
      badge.classList.add("bg-red-50", "text-red-700", "border-red-200");
      badge.innerHTML = '<span class="w-2 h-2 rounded-full bg-red-500"></span> Con error';
    } else if (state === "warn") {
      badge.classList.add("bg-amber-50", "text-amber-700", "border-amber-200");
      badge.innerHTML = '<span class="w-2 h-2 rounded-full bg-amber-500"></span> Revisar';
    } else {
      badge.classList.add("bg-blue-50", "text-blue-700", "border-blue-200");
      badge.innerHTML = '<span class="w-2 h-2 rounded-full bg-blue-500 animate-pulse"></span> En vivo';
    }
  }

  function _renderPipelineNodes(nodeStates) {
    const container = $("gen-pipeline-nodes");
    if (!container) return;

    let doneCount = 0;
    PIPELINE_NODES.forEach((node) => {
      const s = nodeStates[node.id]?.state || "pending";
      if (s === "done" || s === "warn") doneCount++;
    });
    if ($("gen-pipeline-count")) {
      $("gen-pipeline-count").textContent = `${doneCount}/${PIPELINE_NODES.length}`;
    }

    container.innerHTML = PIPELINE_NODES.map((node) => {
      const state = nodeStates[node.id]?.state || "pending";
      const detail = nodeStates[node.id]?.detail || "";
      const iconBg = state === "done" ? "bg-emerald-50 border-emerald-200"
        : state === "running" ? "bg-blue-50 border-blue-200"
          : state === "warn" ? "bg-amber-50 border-amber-200"
            : state === "error" ? "bg-red-50 border-red-200"
              : "bg-slate-50 border-slate-200";
      const iconText = state === "done" ? "text-emerald-700"
        : state === "running" ? "text-blue-700"
          : state === "warn" ? "text-amber-700"
            : state === "error" ? "text-red-700"
              : "text-slate-400";
      const iconChar = state === "done" ? "✓"
        : state === "running" ? "▶"
          : state === "warn" ? "!"
            : state === "error" ? "✕"
              : "·";
      const pillClass = state === "done" ? "bg-emerald-50 text-emerald-700 border-emerald-200"
        : state === "running" ? "bg-blue-50 text-blue-700 border-blue-200"
          : state === "warn" ? "bg-amber-50 text-amber-700 border-amber-200"
            : state === "error" ? "bg-red-50 text-red-700 border-red-200"
              : "bg-slate-50 text-slate-500 border-slate-200";
      const pillLabel = state === "done" ? "OK"
        : state === "running" ? "EN CURSO"
          : state === "warn" ? "WARN"
            : state === "error" ? "ERROR" : "PEND";

      return `
        <div class="flex items-start gap-3 rounded-2xl border bg-white p-3">
          <div class="h-8 w-8 rounded-full border flex items-center justify-center ${iconBg} shrink-0">
            <span class="${iconText} text-sm">${iconChar}</span>
          </div>
          <div class="min-w-0 flex-1">
            <div class="flex items-center justify-between gap-2">
              <div class="font-semibold text-slate-900 truncate">${escapeHtml(node.label)}</div>
              <span class="text-[11px] font-extrabold px-2 py-1 rounded-full border ${pillClass}">${pillLabel}</span>
            </div>
            <div class="text-xs text-slate-500 mt-1 truncate">${escapeHtml(detail || "Pendiente")}</div>
          </div>
        </div>
      `;
    }).join("");
  }

  function _renderDocBlocks(state) {
    const container = $("gen-doc-blocks");
    if (!container) return;

    const total = state.sections.total;
    const current = state.sections.current;
    const currentPath = state.sections.currentPath || "";

    // Build outline items with Map-based upsert (no duplicates)
    const outlineMap = new Map();
    state.sections.paths.forEach((path, idx) => {
      const key = path || `Seccion ${idx + 1}`;
      const sectionNum = idx + 1;
      const status = sectionNum <= current ? "done" : sectionNum === current + 1 ? "running" : "pending";
      // Upsert: if key exists, only upgrade status (pending -> running -> done)
      const existing = outlineMap.get(key);
      if (existing) {
        if (status === "done" || (status === "running" && existing.status === "pending")) {
          existing.status = status;
        }
      } else {
        outlineMap.set(key, { label: key, status, order: outlineMap.size });
      }
    });
    const sectionItems = Array.from(outlineMap.values())
      .sort((a, b) => a.order - b.order)
      .slice(0, 30);

    const baseItems = [
      { label: "Caratula", status: state.nodes.prompt.state === "done" ? "done" : "running" },
      { label: "Indice", status: state.nodes.ai.state === "done" ? "done" : "running" },
      ...(state.sections.hasAbbreviations ? [{ label: "Abreviaturas", status: "done" }] : []),
      ...sectionItems,
    ];

    // Render outline buttons
    container.innerHTML = baseItems.map((item) => {
      const isDone = item.status === "done";
      const isRunning = item.status === "running";
      const pillClass = isDone ? "bg-emerald-50 text-emerald-700 border-emerald-200"
        : isRunning ? "bg-blue-50 text-blue-700 border-blue-200"
          : "bg-slate-50 text-slate-500 border-slate-200";
      const pillLabel = isDone ? "OK" : isRunning ? "EN CURSO" : "PEND";
      const ringClass = isRunning ? "ring-2 ring-blue-100 shadow-sm" : "";
      return `
        <button class="w-full text-left rounded-2xl border p-3 bg-white flex items-start justify-between gap-3 hover:shadow-sm ${ringClass}">
          <div class="min-w-0">
            <div class="font-semibold text-slate-900 truncate">${escapeHtml(item.label)}</div>
            <div class="text-xs text-slate-500 truncate mt-1">${isDone ? "Generada" : isRunning ? "Generando..." : "Pendiente"}</div>
          </div>
          <span class="text-[11px] font-extrabold px-2 py-1 rounded-full border ${pillClass}">${pillLabel}</span>
        </button>
      `;
    }).join("");

    // Update progress card text + bar
    const progressText = total > 0
      ? `Secciones <b>${Math.min(current, total)}/${total}</b>${currentPath ? ` · ${currentPath}` : ""}`
      : "Secciones <b>0/0</b>";
    if ($("gen-sections-progress")) $("gen-sections-progress").innerHTML = progressText;
    const width = total > 0 ? Math.min(100, Math.round((Math.min(current, total) / total) * 100)) : 0;
    if ($("gen-sections-bar")) $("gen-sections-bar").style.width = `${width}%`;



    // Update queue/done counters
    const doneN = Math.min(current, total);
    const queueN = Math.max(0, total - doneN);
    if ($("gen-queue-count")) $("gen-queue-count").textContent = String(queueN);
    if ($("gen-done-count")) $("gen-done-count").textContent = String(doneN);

    // Show "Listo" badge if complete
    if (total > 0 && current >= total) {
      if ($("gen-final-badge")) $("gen-final-badge").classList.remove("hidden");
    } else {
      if ($("gen-final-badge")) $("gen-final-badge").classList.add("hidden");
    }
  }

  let _collapsedTimelineEvents = [];
  let _activeTimelineFilter = "all";

  function _renderTimeline(events) {
    const list = $("gen-trace-timeline");
    const empty = $("gen-trace-empty");
    if (!list || !empty) return;
    if (!events.length) {
      list.innerHTML = "";
      empty.classList.remove("hidden");
      _collapsedTimelineEvents = [];
      return;
    }
    empty.classList.add("hidden");

    // Deduplicate bursts
    const collapsed = [];
    events.slice(-120).forEach((event) => {
      const stage = String(event.stage || event.step || "");
      const status = String(event.status || event.level || "running");
      const title = String(event.title || event.message || "");
      const provider = String(event.provider || event.meta?.provider || "");
      const sectionPath = String(event.sectionPath || event.meta?.sectionPath || "");
      const key = `${stage}|${status}|${provider}|${sectionPath}|${title.trim().toLowerCase()}`;
      const ts = Number(new Date(event.ts || 0).getTime() || 0);
      const last = collapsed.length ? collapsed[collapsed.length - 1] : null;
      if (last && last._dedupeKey === key) {
        const lastTs = Number(new Date(last.ts || 0).getTime() || 0);
        if (ts > 0 && lastTs > 0 && (ts - lastTs) <= 3000) {
          last._count = Number(last._count || 1) + 1;
          last.ts = event.ts || last.ts;
          return;
        }
      }
      collapsed.push({ ...event, _dedupeKey: key, _count: 1 });
    });

    const visible = collapsed.slice(-60);
    _collapsedTimelineEvents = visible;

    // Determine filter + search
    const search = ($("gen-timeline-search")?.value || "").toLowerCase().trim();

    list.innerHTML = visible.map((event, idx) => {
      const status = String(event.status || (event.level === "error" ? "error" : event.level === "warn" ? "warn" : "running"));
      const title = String(event.title || event.message || event.stage || "Evento");
      const stage = String(event.stage || event.step || "").toLowerCase();
      const stageLabel = stage.includes("ai") || stage.includes("ia") ? "IA"
        : stage.includes("render") || stage.includes("docx") || stage.includes("pdf") ? "Render"
          : stage || "Pipeline";
      const dotColor = status === "done" ? "bg-emerald-500" : status === "error" ? "bg-red-500" : status === "warn" ? "bg-amber-500" : "bg-blue-500";
      const countTag = Number(event._count || 1) > 1 ? ` (x${event._count})` : "";

      // Filtering
      if (_activeTimelineFilter === "ai" && !stage.includes("ai") && !stage.includes("ia")) return "";
      if (_activeTimelineFilter === "render" && !stage.includes("render") && !stage.includes("docx") && !stage.includes("pdf")) return "";
      if (search && !title.toLowerCase().includes(search) && !stage.includes(search)) return "";

      return `
        <button class="timeline-item w-full text-left rounded-2xl border p-3 bg-white transition" data-event-index="${idx}">
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0">
              <div class="flex items-center gap-2">
                <span class="h-2.5 w-2.5 rounded-full ${dotColor} ring-4 ring-black/5 shrink-0"></span>
                <div class="text-xs text-slate-500">${escapeHtml(_formatEventTime(event.ts))}</div>
              </div>
              <div class="mt-1 text-sm font-semibold text-slate-900 truncate">${escapeHtml(title)}${countTag}</div>
              <div class="mt-1 text-xs text-slate-500 truncate">${escapeHtml(stageLabel)}</div>
            </div>
            <span class="inline-flex items-center rounded-full border bg-white px-3 py-1 text-[11px] font-extrabold text-slate-700 shrink-0">
              ${escapeHtml(status === "done" ? "OK" : status)}
            </span>
          </div>
        </button>
      `;
    }).join("");

    // Attach click handlers (highlight only, no inspector)
    list.querySelectorAll(".timeline-item[data-event-index]").forEach((el) => {
      el.onclick = () => {
        const idx = parseInt(el.getAttribute("data-event-index"), 10);
        if (Number.isFinite(idx) && _collapsedTimelineEvents[idx]) {
          list.querySelectorAll(".timeline-item").forEach((e) => e.classList.remove("selected"));
          el.classList.add("selected");
        }
      };
    });
  }

  function _filterTimeline(filter) {
    if (filter && typeof filter === "string") _activeTimelineFilter = filter;
    // Update filter button styles
    document.querySelectorAll("[data-tl-filter]").forEach((btn) => {
      if (btn.getAttribute("data-tl-filter") === _activeTimelineFilter) {
        btn.className = "rounded-xl bg-slate-900 text-white px-3 py-1.5 text-xs font-extrabold";
      } else {
        btn.className = "rounded-xl border bg-white px-3 py-1.5 text-xs font-extrabold text-slate-700 hover:bg-slate-50";
      }
    });
    // Re-render with current events
    if (_collapsedTimelineEvents.length) {
      const list = $("gen-trace-timeline");
      const search = ($("gen-timeline-search")?.value || "").toLowerCase().trim();
      if (!list) return;
      list.innerHTML = _collapsedTimelineEvents.map((event, idx) => {
        const status = String(event.status || (event.level === "error" ? "error" : event.level === "warn" ? "warn" : "running"));
        const title = String(event.title || event.message || event.stage || "Evento");
        const stage = String(event.stage || event.step || "").toLowerCase();
        const stageLabel = stage.includes("ai") || stage.includes("ia") ? "IA"
          : stage.includes("render") || stage.includes("docx") || stage.includes("pdf") ? "Render"
            : stage || "Pipeline";
        const dotColor = status === "done" ? "bg-emerald-500" : status === "error" ? "bg-red-500" : status === "warn" ? "bg-amber-500" : "bg-blue-500";
        const countTag = Number(event._count || 1) > 1 ? ` (x${event._count})` : "";
        if (_activeTimelineFilter === "ai" && !stage.includes("ai") && !stage.includes("ia")) return "";
        if (_activeTimelineFilter === "render" && !stage.includes("render") && !stage.includes("docx") && !stage.includes("pdf")) return "";
        if (search && !title.toLowerCase().includes(search) && !stage.includes(search)) return "";
        return `
          <button class="timeline-item w-full text-left rounded-2xl border p-3 bg-white transition" data-event-index="${idx}">
            <div class="flex items-start justify-between gap-2">
              <div class="min-w-0">
                <div class="flex items-center gap-2">
                  <span class="h-2.5 w-2.5 rounded-full ${dotColor} ring-4 ring-black/5 shrink-0"></span>
                  <div class="text-xs text-slate-500">${escapeHtml(_formatEventTime(event.ts))}</div>
                </div>
                <div class="mt-1 text-sm font-semibold text-slate-900 truncate">${escapeHtml(title)}${countTag}</div>
                <div class="mt-1 text-xs text-slate-500 truncate">${escapeHtml(stageLabel)}</div>
              </div>
              <span class="inline-flex items-center rounded-full border bg-white px-3 py-1 text-[11px] font-extrabold text-slate-700 shrink-0">${escapeHtml(status === "done" ? "OK" : status)}</span>
            </div>
          </button>
        `;
      }).join("");
      list.querySelectorAll(".timeline-item[data-event-index]").forEach((el) => {
        el.onclick = () => {
          const idx = parseInt(el.getAttribute("data-event-index"), 10);
          if (Number.isFinite(idx) && _collapsedTimelineEvents[idx]) {
            list.querySelectorAll(".timeline-item").forEach((e) => e.classList.remove("selected"));
            el.classList.add("selected");
          }
        };
      });
    }
  }

  function _normalizeGenerationSnapshot(projectSnapshot) {
    const rawSnapshot = projectSnapshot?.generation_snapshot;
    const snapshot = rawSnapshot && typeof rawSnapshot === "object" ? rawSnapshot : {};
    let completedSections = Array.isArray(snapshot.completed_sections)
      ? snapshot.completed_sections
      : [];
    if (!completedSections.length) {
      const aiSections = Array.isArray(projectSnapshot?.ai_result?.sections)
        ? projectSnapshot.ai_result.sections
        : [];
      completedSections = aiSections
        .filter((item) => item && typeof item === "object")
        .map((item) => ({
          sectionId: String(item.sectionId || item.section_id || ""),
          path: String(item.path || item.section_path || ""),
        }))
        .filter((item) => item.sectionId || item.path);
    }
    const completedPaths = completedSections
      .map((item) => String(item?.path || "").trim())
      .filter(Boolean);
    return {
      savedSectionsCount: Math.max(
        0,
        Number(snapshot.saved_sections_count || completedSections.length || 0),
      ),
      totalSections: Math.max(0, Number(snapshot.total_sections || 0)),
      currentPath: String(snapshot.current_path || ""),
      completedSections,
      completedPaths,
      tokenUsage: snapshot.tokenUsage && typeof snapshot.tokenUsage === "object" ? snapshot.tokenUsage : null,
      status: String(snapshot.status || "idle"),
    };
  }

  function _deriveTraceState(events, progress = null, projectStatus = "", projectSnapshot = null) {
    const nodes = {
      format: { state: "pending", detail: "Pendiente" },
      variables: { state: "pending", detail: "Pendiente" },
      prompt: { state: "pending", detail: "Pendiente" },
      ai: { state: "pending", detail: "Pendiente" },
      clean: { state: "pending", detail: "Pendiente" },
      payload: { state: "pending", detail: "Pendiente" },
      render: { state: "pending", detail: "Pendiente" },
    };
    const sections = {
      current: 0,
      total: 0,
      currentPath: "",
      paths: [],
      hasAbbreviations: false,
    };
    let fallbackText = "";
    let docxDone = false;
    let pdfDone = false;
    let quotaRetrying = false;
    const generationSnapshot = _normalizeGenerationSnapshot(projectSnapshot);

    const applyNode = (nodeId, status, detail) => {
      const node = nodes[nodeId];
      if (!node) return;
      if (status === "error") {
        node.state = "error";
      } else if (status === "warn") {
        if (node.state !== "error") node.state = "warn";
      } else if (status === "done") {
        if (node.state === "pending" || node.state === "running") node.state = "done";
      } else if (status === "running") {
        if (node.state === "pending") node.state = "running";
      }
      if (detail) node.detail = detail;
    };

    if (generationSnapshot.completedPaths.length || generationSnapshot.savedSectionsCount > 0) {
      sections.current = Math.max(sections.current, generationSnapshot.savedSectionsCount);
      if (generationSnapshot.totalSections > 0) {
        sections.total = Math.max(sections.total, generationSnapshot.totalSections);
      }
      generationSnapshot.completedPaths.forEach((path) => {
        if (!sections.paths.includes(path)) sections.paths.push(path);
        if (path.toUpperCase().includes("ABREVIATURAS")) sections.hasAbbreviations = true;
      });
      if (generationSnapshot.currentPath) {
        sections.currentPath = generationSnapshot.currentPath;
        if (!sections.paths.includes(generationSnapshot.currentPath)) {
          sections.paths.push(generationSnapshot.currentPath);
        }
      }
      applyNode("format", "done", "Formato JSON cargado");
      applyNode("variables", "done", "Variables del proyecto preparadas");
      applyNode("prompt", "done", "Prompt final armado");
      if (projectStatus === "generating") {
        const resumeTarget = generationSnapshot.savedSectionsCount + 1;
        applyNode("ai", "running", `Reanudando desde seccion ${resumeTarget}`);
      } else if (projectStatus === "failed" || projectStatus === "blocked" || projectStatus === "cancel_requested") {
        applyNode("ai", "warn", "Avance parcial conservado para reintento");
      } else {
        applyNode("ai", "done", "Secciones parciales conservadas");
      }
    }

    events.forEach((event) => {
      const step = String(event.step || event.stage || "");
      const status = String(
        event.status
        || (event.level === "error" ? "error" : event.level === "warn" ? "warn" : "running")
      );
      const title = String(event.title || event.message || event.stage || "");
      const meta = event.meta && typeof event.meta === "object" ? event.meta : {};

      if (step.startsWith("format.")) applyNode("format", status, title);
      if (step === "project.variables.ready") applyNode("variables", status, title);
      if (step === "prompt.render") applyNode("prompt", status, title);
      if (step.startsWith("ai.generate.section") || step.startsWith("ai.provider.")) applyNode("ai", status, title);
      if (step === "ai.validation" || step.startsWith("ai.correction")) applyNode("clean", status, title);
      if (step.startsWith("gicatesis.payload")) applyNode("payload", status, title);

      if (step === "gicatesis.render.docx") {
        applyNode("render", status, title);
        if (status === "done") docxDone = true;
      }
      if (step === "gicatesis.render.pdf") {
        applyNode("render", status, title);
        if (status === "done") pdfDone = true;
      }
      if (docxDone && pdfDone && nodes.render.state !== "error") {
        nodes.render.state = "done";
        nodes.render.detail = "DOCX y PDF listos";
      }

      if (
        step === "ai.provider.fallback"
        || step === "ai.provider.quota"
        || step === "provider_fallback"
      ) {
        fallbackText = `${title}${event.detail ? ` - ${event.detail}` : ""}`;
        if (step === "ai.provider.quota") quotaRetrying = true;
      }

      if (step === "ai.generate.section" || step === "section_start" || step === "section_done") {
        const idx = Number(meta.sectionIndex || event.sectionCurrent || 0);
        const total = Number(meta.sectionTotal || event.sectionTotal || 0);
        const path = String(meta.sectionPath || event.sectionPath || "");
        if (idx > 0) sections.current = Math.max(sections.current, idx);
        if (total > 0) sections.total = Math.max(sections.total, total);
        if (path) {
          sections.currentPath = path;
          if (!sections.paths.includes(path)) sections.paths.push(path);
          if (path.toUpperCase().includes("ABREVIATURAS")) sections.hasAbbreviations = true;
        }
      }

      if (step === "generation.job" && status === "done") {
        applyNode("format", "done", nodes.format.detail || "Completado");
        applyNode("variables", "done", nodes.variables.detail || "Completado");
        applyNode("prompt", "done", nodes.prompt.detail || "Completado");
        applyNode("ai", "done", nodes.ai.detail || "Completado");
        if (nodes.clean.state === "pending" || nodes.clean.state === "running") {
          applyNode("clean", "done", "Validado");
        }
        applyNode("payload", "done", nodes.payload.detail || "Payload enviado");
        applyNode("render", "done", "DOCX y PDF listos");
      }
    });

    if (progress && typeof progress === "object") {
      const pCurrent = Number(progress.current || 0);
      const pTotal = Number(progress.total || 0);
      const pPath = String(progress.currentPath || "");
      if (pCurrent > 0) sections.current = Math.max(sections.current, pCurrent);
      if (pTotal > 0) sections.total = Math.max(sections.total, pTotal);
      if (pPath) {
        sections.currentPath = pPath;
        if (!sections.paths.includes(pPath)) sections.paths.push(pPath);
      }
    }

    if (sections.total > 0 && sections.current >= sections.total && nodes.ai.state !== "error") {
      if (nodes.ai.state === "pending" || nodes.ai.state === "running") {
        nodes.ai.state = "done";
      }
      if (!nodes.ai.detail || nodes.ai.detail === "Pendiente") {
        nodes.ai.detail = "Secciones completadas";
      }
    }

    if (projectStatus && GEN_SUCCESS_STATUSES.includes(projectStatus)) {
      const completedWithIncidents = projectStatus === "completed_with_incidents";
      const markDone = (nodeId, detailText) => {
        if (nodes[nodeId].state === "pending" || nodes[nodeId].state === "running") {
          nodes[nodeId].state = "done";
        }
        if (!nodes[nodeId].detail || nodes[nodeId].detail === "Pendiente") {
          nodes[nodeId].detail = detailText;
        }
      };
      markDone("format", "Formato cargado");
      markDone("variables", "Variables listas");
      markDone("prompt", "Prompt armado");
      markDone("ai", "Generacion completada");
      if (nodes.clean.state !== "warn") markDone("clean", "Validacion completada");
      markDone("payload", "Payload enviado");
      if (nodes.render.state !== "error") {
        nodes.render.state = "done";
        nodes.render.detail = "DOCX y PDF listos";
      }
      if (completedWithIncidents) {
        if (nodes.ai.state === "error") {
          nodes.ai.state = "warn";
        }
        if (nodes.clean.state === "error") {
          nodes.clean.state = "warn";
        }
      }
    }

    if (projectStatus === "render_failed") {
      const markDone = (nodeId, detailText) => {
        if (nodes[nodeId].state === "pending" || nodes[nodeId].state === "running") {
          nodes[nodeId].state = "done";
        }
        if (!nodes[nodeId].detail || nodes[nodeId].detail === "Pendiente") {
          nodes[nodeId].detail = detailText;
        }
      };
      markDone("format", "Formato cargado");
      markDone("variables", "Variables listas");
      markDone("prompt", "Prompt armado");
      markDone("ai", "Contenido IA conservado");
      if (nodes.clean.state === "pending" || nodes.clean.state === "running") {
        markDone("clean", "Validacion completada");
      }
      if (nodes.render.state === "pending" || nodes.render.state === "running") {
        nodes.render.state = "error";
        nodes.render.detail = "Render fallido. Puedes reintentar sin volver a IA.";
      }
    }

    return { nodes, sections, fallbackText, quotaRetrying };
  }

  function _resetGenUI() {
    _lastRenderedTraceCount = 0;
    _lastTraceState = null;
    _collapsedTimelineEvents = [];
    _activeTimelineFilter = "all";
    _genAiSelectedSectionKey = "";
    _genAiExpandedGroupPath = null;
    _setLiveSummary("Preparando ejecucion...", "neutral");
    _updateLiveBadge("live");
    if ($("gen-pipeline-count")) $("gen-pipeline-count").textContent = "0/7";

    // Reset badges
    if ($("gen-status-badge")) $("gen-status-badge").classList.add("hidden");
    if ($("gen-provider-badge")) $("gen-provider-badge").classList.add("hidden");
    if ($("gen-model-badge")) $("gen-model-badge").classList.add("hidden");
    if ($("gen-final-badge")) $("gen-final-badge").classList.add("hidden");
    // Reset counters
    if ($("gen-queue-count")) $("gen-queue-count").textContent = "0";
    if ($("gen-done-count")) $("gen-done-count").textContent = "0";
    if ($("gen-token-input-total")) $("gen-token-input-total").textContent = "0";
    if ($("gen-token-output-total")) $("gen-token-output-total").textContent = "0";
    if ($("gen-token-total")) $("gen-token-total").textContent = "0";
    if ($("gen-token-current-section")) $("gen-token-current-section").textContent = "-";
    if ($("gen-token-current-model")) $("gen-token-current-model").textContent = "-";
    if ($("gen-token-source")) $("gen-token-source").textContent = "Sin uso IA";
    if ($("gen-token-calls")) $("gen-token-calls").textContent = "0";
    if ($("gen-base-prompt")) $("gen-base-prompt").textContent = "Aun no disponible.";
    if ($("gen-ai-count")) $("gen-ai-count").textContent = "0/0";
    if ($("gen-ai-section-list")) $("gen-ai-section-list").innerHTML = "";
    if ($("gen-ai-detail-title")) $("gen-ai-detail-title").textContent = "Sin sección seleccionada";
    if ($("gen-ai-detail-meta")) $("gen-ai-detail-meta").textContent = "Selecciona una sección para auditar prompt, respuesta y tokens.";
    if ($("gen-ai-detail-input")) $("gen-ai-detail-input").textContent = "0";
    if ($("gen-ai-detail-output")) $("gen-ai-detail-output").textContent = "0";
    if ($("gen-ai-detail-total")) $("gen-ai-detail-total").textContent = "0";
    if ($("gen-ai-detail-duration")) $("gen-ai-detail-duration").textContent = "-";
    if ($("gen-ai-detail-provider")) $("gen-ai-detail-provider").textContent = "-";
    if ($("gen-ai-detail-model")) $("gen-ai-detail-model").textContent = "-";
    if ($("gen-ai-detail-source")) $("gen-ai-detail-source").textContent = "-";
    if ($("gen-ai-detail-prompt")) $("gen-ai-detail-prompt").textContent = "Aun no disponible.";
    if ($("gen-ai-detail-response")) $("gen-ai-detail-response").textContent = "Aun no disponible.";
    if ($("gen-ai-detail-status")) {
      $("gen-ai-detail-status").className = "inline-flex items-center rounded-full border bg-slate-50 px-3 py-1 text-xs font-extrabold text-slate-700 border-slate-200";
      $("gen-ai-detail-status").textContent = "PENDIENTE";
    }
    if ($("btn-go-construction")) $("btn-go-construction").classList.add("hidden");
    if ($("btn-step6-downloads")) $("btn-step6-downloads").classList.add("hidden");
    if ($("construct-summary")) $("construct-summary").textContent = "Transformando la salida de IA en artefactos finales del documento.";
    if ($("construct-progress-count")) $("construct-progress-count").textContent = "0/5";
    if ($("construct-progress-bar")) $("construct-progress-bar").style.width = "0%";
    if ($("construct-status-badge")) {
      $("construct-status-badge").className = "inline-flex items-center rounded-full border bg-white px-3 py-1 text-xs font-extrabold text-slate-700";
      $("construct-status-badge").textContent = "Pendiente";
    }
    if ($("construct-task-list")) $("construct-task-list").innerHTML = "";
    if ($("construct-trace-list")) $("construct-trace-list").innerHTML = "";
    if ($("construct-trace-empty")) $("construct-trace-empty").classList.remove("hidden");
    // Reset doc tab to 'doc'
    _switchDocTab("doc");
    // Reset search
    if ($("gen-timeline-search")) $("gen-timeline-search").value = "";
    // Reset filters
    document.querySelectorAll("[data-tl-filter]").forEach((btn) => {
      if (btn.getAttribute("data-tl-filter") === "all") {
        btn.className = "rounded-xl bg-slate-900 text-white px-3 py-1.5 text-xs font-extrabold";
      } else {
        btn.className = "rounded-xl border bg-white px-3 py-1.5 text-xs font-extrabold text-slate-700 hover:bg-slate-50";
      }
    });
    _renderPipelineNodes({
      format: { state: "pending", detail: "Pendiente" },
      variables: { state: "pending", detail: "Pendiente" },
      prompt: { state: "pending", detail: "Pendiente" },
      ai: { state: "pending", detail: "Pendiente" },
      clean: { state: "pending", detail: "Pendiente" },
      payload: { state: "pending", detail: "Pendiente" },
      render: { state: "pending", detail: "Pendiente" },
    });
    _renderDocBlocks({
      nodes: {
        prompt: { state: "pending" },
        ai: { state: "pending" },
      },
      sections: {
        current: 0,
        total: 0,
        currentPath: "",
        paths: [],
        hasAbbreviations: false,
      },
    });
    _renderTokenUsage(null);
    _renderTimeline([]);
    if ($("gen-pipeline-fallback")) {
      $("gen-pipeline-fallback").classList.add("hidden");
      $("gen-pipeline-fallback").textContent = "";
    }
    if ($("gen-timer")) $("gen-timer").classList.add("hidden");
    if ($("gen-timer-value")) $("gen-timer-value").textContent = "0s";
    if ($("gen-error")) {
      $("gen-error").classList.add("hidden");
      const errSpan = $("gen-error").querySelector("span");
      if (errSpan) errSpan.textContent = "";
    }
    if ($("gen-success")) $("gen-success").classList.add("hidden");
    if ($("btn-gen-retry")) $("btn-gen-retry").classList.add("hidden");
    if ($("btn-construct-retry")) $("btn-construct-retry").classList.add("hidden");
    if ($("btn-gen-cancel")) $("btn-gen-cancel").classList.remove("hidden");
  }

  function _showGenError(msg) {
    const el = $("gen-error");
    if (el) {
      el.classList.remove("hidden");
      const span = el.querySelector("span");
      if (span) span.textContent = msg;
    }
    if ($("btn-gen-retry")) $("btn-gen-retry").classList.remove("hidden");
    if ($("btn-construct-retry")) $("btn-construct-retry").classList.remove("hidden");
    if ($("btn-gen-cancel")) $("btn-gen-cancel").classList.add("hidden");
    _updateLiveBadge("error");
    _setLiveSummary(msg, "error");
  }

  function _startGenTimer() {
    _genElapsed = 0;
    if ($("gen-timer")) $("gen-timer").classList.remove("hidden");
    _genTimerHandle = setInterval(() => {
      _genElapsed++;
      if ($("gen-timer-value")) $("gen-timer-value").textContent = `${_genElapsed}s`;
    }, 1000);
  }

  function _stopGenTimer() {
    if (_genTimerHandle) { clearInterval(_genTimerHandle); _genTimerHandle = null; }
  }

  async function _renderLiveTrace(projectId) {
    let projectSnapshot = null;
    try {
      projectSnapshot = await apiGet(`/api/projects/${encodeURIComponent(projectId)}`);
    } catch (_) {
      return null;
    }

    const events = Array.isArray(projectSnapshot?.events)
      ? projectSnapshot.events
      : Array.isArray(projectSnapshot?.trace)
        ? projectSnapshot.trace
        : [];
    currentProject = projectSnapshot;
    _lastRenderedTraceCount = events.length;
    _lastTraceState = null;
    _syncWizardStepWithProject(projectSnapshot);
    _renderAIGeneration(projectSnapshot);
    _renderConstruction(projectSnapshot);
    _renderTokenUsage(projectSnapshot);
    return projectSnapshot;
  }

  function _buildArtifacts(project) {
    const runId = project.run_id || "";
    const artifacts = Array.isArray(project.artifacts) ? project.artifacts : [];
    const artifactDocx = artifacts.find((x) => x.type === "docx")?.downloadUrl;
    const artifactPdf = artifacts.find((x) => x.type === "pdf")?.downloadUrl;
    const hasLocalOutput = !!project.output_file;
    const hasLocalPdf = !!project.pdf_file;
    const fallbackDocx = hasLocalOutput
      ? `/api/download/${encodeURIComponent(project.id)}`
      : `/api/sim/download/docx?projectId=${encodeURIComponent(project.id)}${runId ? `&runId=${encodeURIComponent(runId)}` : ""}`;
    const fallbackPdf = hasLocalPdf
      ? `/api/download/${encodeURIComponent(project.id)}/pdf`
      : `/api/sim/download/pdf?projectId=${encodeURIComponent(project.id)}${runId ? `&runId=${encodeURIComponent(runId)}` : ""}`;
    return {
      projectId: project.id,
      runId,
      artifacts: [
        { type: "docx", downloadUrl: artifactDocx || fallbackDocx },
        { type: "pdf", downloadUrl: artifactPdf || fallbackPdf },
      ],
    };
  }

  async function _waitForGeneration(projectId) {
    _startGenTimer();
    let missingProjectPolls = 0;
    while (true) {
      if (_genCancelled) {
        _stopGenTimer();
        return;
      }

      const project = await _renderLiveTrace(projectId);
      if (project) currentProject = project;

      const generationPhase = project?.generation_phase && typeof project.generation_phase === "object"
        ? project.generation_phase
        : null;
      const generationStatus = String(generationPhase?.status || "");
      const constructionPhase = project?.construction_phase && typeof project.construction_phase === "object"
        ? project.construction_phase
        : null;
      const constructionStatus = String(constructionPhase?.status || "");
      if (
        project
        && currentStep === 5
        && (
          ["completed", "failed", "blocked"].includes(generationStatus)
          || ["running", "completed", "error"].includes(constructionStatus)
        )
      ) {
        nextStep(6);
      }

      if (project && GEN_SUCCESS_STATUSES.includes(project.status)) {
        _stopGenTimer();
        simRunResult = _buildArtifacts(project);
        const warningsCount = Number(project?.warnings_count || 0);
        const withIncidents = project.status === "completed_with_incidents" || warningsCount > 0;
        if (withIncidents) {
          _setLiveSummary(
            `Flujo completado con incidencias en ${_genElapsed}s. Se omitieron pasos opcionales de IA.`,
            "warn",
          );
          _updateLiveBadge("warn");
        } else {
          _setLiveSummary(`Flujo completado en ${_genElapsed}s`, "ok");
          _updateLiveBadge("ok");
        }
        if ($("gen-success")) $("gen-success").classList.remove("hidden");
        if ($("btn-gen-downloads")) $("btn-gen-downloads").classList.remove("hidden");
        if ($("btn-construct-retry")) $("btn-construct-retry").classList.add("hidden");
        if ($("btn-gen-cancel")) $("btn-gen-cancel").classList.add("hidden");
        if (currentStep < 7) continueToSimDownloads();
        refreshDashboard().catch(() => { });
        refreshHistory().catch(() => { });
        return;
      }

      if (project && GEN_FAIL_STATUSES.includes(project.status)) {
        _stopGenTimer();
        const errMsg = project.status === "render_failed"
          ? (project.error || "Render fallido. El contenido IA se conserva; reintenta para ejecutar solo render.")
          : (project.error || `Generacion fallida (${project.status})`);
        if (project.status === "render_failed" && currentStep < 6) nextStep(6);
        _showGenError(errMsg);
        return;
      }

      if (project) {
        missingProjectPolls = 0;
        if (_lastTraceState?.quotaRetrying) {
          _setLiveSummary("Esperando reintento del proveedor IA por cuota...", "warn");
        } else {
          _setLiveSummary(`Ejecutando flujo... ${_genElapsed}s`, "neutral");
        }
      } else {
        missingProjectPolls += 1;
        if (missingProjectPolls >= GEN_MISSING_PROJECT_MAX_POLLS) {
          _stopGenTimer();
          _showGenError(
            "No se encontro el proyecto durante el seguimiento. Reinicia el backend y vuelve a intentar desde el historial o creando un nuevo borrador.",
          );
          return;
        }
        _setLiveSummary(`Sincronizando estado del proyecto... ${_genElapsed}s`, "warn");
      }
      await _sleep(GEN_POLL_INTERVAL);
    }
  }

  async function _upsertProjectDraftFromWizard() {
    const wizard = collectWizardPayload();
    let projectId = currentProject?.id;
    const resetGeneratedState = _hasProjectCoreChanges(currentProject, wizard);
    const wizardStatePayload = {
      currentStep: currentStep,
      lastCompletedStep: Math.max(Number(currentProject?.wizard_state?.last_completed_step || 1), currentStep),
      lastOpenMode: currentProject?.id ? "edit" : "new",
      updatedAt: new Date().toISOString(),
    };

    if (!projectId) {
      const draft = await apiSend("/api/projects/draft", "POST", {
        title: wizard.title,
        formatId: selectedFormat.id,
        formatName: selectedFormat.title || selectedFormat.name || selectedFormat.id,
        formatVersion: selectedFormat.version,
        promptId: selectedPrompt.id,
        values: wizard.values,
        wizardState: wizardStatePayload,
      });
      projectId = draft?.id || draft?.projectId;
      currentProject = { ...(draft || {}), id: projectId };
    } else {
      const updated = await apiSend(`/api/projects/${encodeURIComponent(projectId)}`, "PUT", {
        title: wizard.title,
        formatId: selectedFormat.id,
        formatName: selectedFormat.title || selectedFormat.name || selectedFormat.id,
        formatVersion: selectedFormat.version,
        promptId: selectedPrompt.id,
        values: wizard.values,
        status: "draft",
        wizardState: wizardStatePayload,
        resetGeneratedState,
      });
      currentProject = { ...(updated || {}), id: projectId };
    }

    if (!projectId) throw new Error("No se pudo obtener projectId.");
    return projectId;
  }

  async function goToProviderStep() {
    if (!selectedFormat || !selectedPrompt) {
      setStep3Error("Selecciona formato y prompt antes de continuar.");
      return;
    }
    if (isPreparingGuide) {
      setStep3Error("Hay un proceso en curso. Espera unos segundos e intenta de nuevo.");
      return;
    }

    setStep3Error("");
    const btn = $("btn-step3-next-provider");
    const loader = $("step3-loading");
    if (btn) btn.classList.add("hidden");
    if (loader) loader.classList.remove("hidden");

    try {
      const projectId = await _upsertProjectDraftFromWizard();
      nextStep(4);
    } catch (error) {
      setStep3Error(error?.message || "No se pudo preparar el proyecto.");
    } finally {
      if (btn) btn.classList.remove("hidden");
      if (loader) loader.classList.add("hidden");
    }
  }

  async function triggerGeneration() {
    if (!selectedFormat || !selectedPrompt || isPreparingGuide) return;

    isPreparingGuide = true;
    _genCancelled = false;
    setStep4Error("");

    // Hide Step 4 button, show Step 4 loading state
    const btn = $("btn-step4-generate");
    const loader = $("step4-loading");
    if (btn) btn.classList.add("hidden");
    if (loader) loader.classList.remove("hidden");

    try {
      const projectId = await _upsertProjectDraftFromWizard();

      // Persist current provider/mode selection in this project.
      if (providerStatusCache) {
        await _saveProviderSelection(
          {
            provider: providerStatusCache.selected_provider || "gemini",
            model: providerStatusCache.selected_model || "",
            fallback_provider: providerStatusCache.fallback_provider || "mistral",
            fallback_model: providerStatusCache.fallback_model || "",
            mode: providerStatusCache.mode || "auto",
          },
          projectId,
        );
      }

      // --- Navigate to Step 5 & reset UI ---
      _resetGenUI();
      nextStep(5);
      _setLiveSummary("Enviando solicitud de generacion...", "neutral");

      let genResult;
      try {
        genResult = await apiSend(
          `/api/projects/${encodeURIComponent(projectId)}/generate`, "POST", {}
        );
      } catch (e) {
        const detail = e?.message || "Error al enviar solicitud";
        _showGenError(detail);
        return;
      }

      if (_genCancelled) return;

      const mode = genResult?.mode || "ai";
      if (mode === "demo") _setLiveSummary("Modo demo activo. Ejecutando generacion local...", "warn");
      else if (mode === "render_only") {
        _setLiveSummary(
          "Reintentando solo render con el ai_result guardado. No se volvera a llamar al proveedor IA.",
          "warn",
        );
      }
      else {
        const provider = genResult?.provider || providerStatusCache?.selected_provider || "gemini";
        const model = genResult?.model || providerStatusCache?.selected_model || "-";
        const selectionMode = genResult?.selectionMode || providerStatusCache?.mode || "auto";
        const savedSections = Number(genResult?.savedSections || 0);
        const resumeFromSection = Number(genResult?.resumeFromSection || 1);
        const resumeMode = String(genResult?.resumeMode || "auto").toLowerCase();
        if (savedSections > 0 && (resumeMode === "auto" || resumeMode === "resume")) {
          _setLiveSummary(
            `Reanudando desde seccion ${resumeFromSection} (se conservaron ${savedSections}). Usando: ${provider} (${model}) - modo ${selectionMode}.`,
            "warn",
          );
        } else {
          _setLiveSummary(
            `Usando: ${provider} (${model}) - modo ${selectionMode}.`,
            "neutral",
          );
        }
      }
      await _waitForGeneration(projectId);

    } catch (error) {
      _stopGenTimer();
      const message = error?.message || "Error en generacion.";
      if (currentStep < 5) {
        setStep4Error(message);
        if (btn) btn.classList.remove("hidden");
        if (loader) loader.classList.add("hidden");
      } else {
        _showGenError(message);
      }
    } finally {
      isPreparingGuide = false;
      const btn2 = $("btn-step4-generate");
      const loader2 = $("step4-loading");
      if (btn2) btn2.classList.remove("hidden");
      if (loader2) loader2.classList.add("hidden");
    }
  }

  async function cancelGeneration() {
    _genCancelled = true;
    _stopGenTimer();
    if (currentProject?.id) {
      try {
        await apiSend(`/api/projects/${encodeURIComponent(currentProject.id)}/cancel`, "POST", {});
      } catch (_) {
        // ignore cancel API errors: local UI still transitions to cancelled state
      }
    }
    _showGenError("Cancelacion solicitada.");
    _updateLiveBadge("warn");
    _setLiveSummary("Cancelacion solicitada. Puedes reintentar cuando desees.", "warn");
  }

  function retryGeneration() {
    triggerGeneration();
  }

  function goToDownloads() {
    continueToSimDownloads();
  }

  function continueToSimDownloads() {
    if (!currentProject?.id) return;

    const id = currentProject.id;
    const output = simRunResult || n8nSpec?.simulationOutput || {};
    const runId = output.runId || "";
    const docxUrl = output.artifacts?.find?.((x) => x.type === "docx")?.downloadUrl
      || `/api/sim/download/docx?projectId=${encodeURIComponent(id)}${runId ? `&runId=${encodeURIComponent(runId)}` : ""}`;
    const pdfUrl = output.artifacts?.find?.((x) => x.type === "pdf")?.downloadUrl
      || `/api/sim/download/pdf?projectId=${encodeURIComponent(id)}${runId ? `&runId=${encodeURIComponent(runId)}` : ""}`;

    if ($("sim-project-id")) $("sim-project-id").textContent = id;
    if ($("sim-download-docx")) $("sim-download-docx").setAttribute("href", docxUrl);
    if ($("sim-download-pdf")) $("sim-download-pdf").setAttribute("href", pdfUrl);
    nextStep(7);
  }

  async function runN8nSimulation() {
    if (!currentProject?.id || isRunningSimulation) return;

    const button = $("btn-run-sim");
    isRunningSimulation = true;
    if (button) button.disabled = true;
    if ($("sim-run-status")) $("sim-run-status").textContent = "Ejecutando simulacion...";

    try {
      const result = await apiSend(
        `/api/sim/n8n/run?projectId=${encodeURIComponent(currentProject.id)}`,
        "POST"
      );
      simRunResult = result;
      if (n8nSpec) {
        n8nSpec.simulationOutput = {
          projectId: result.projectId,
          runId: result.runId,
          status: "success",
          aiResult: result.aiResult,
          artifacts: result.artifacts,
        };
      }
      renderN8nGuide();
      refreshDashboard().catch(() => { });
      refreshHistory().catch(() => { });
    } catch (error) {
      const message = error?.message || "No se pudo ejecutar la simulacion.";
      if ($("sim-run-status")) $("sim-run-status").textContent = message;
      alert(`Error: ${message}`);
    } finally {
      isRunningSimulation = false;
      if (button) button.disabled = false;
    }
  }

  async function copyN8nPayload() {
    if (!n8nSpec) return;
    await copyText(toPrettyJson(n8nSpec.request?.payload || {}));
  }

  async function copyN8nHeaders() {
    if (!n8nSpec) return;
    await copyText(toPrettyJson({
      toN8N: n8nSpec.request?.headers || {},
      toCallback: n8nSpec.expectedResponse?.headers || {},
    }));
  }

  async function copyN8nWebhook() {
    if (!n8nSpec) return;
    await copyText(n8nSpec.request?.webhookUrl || "");
  }

  function exportN8nGuide() {
    if (!n8nSpec || !n8nSpec.markdown) return;
    const projectId = n8nSpec.summary?.projectId || "project";
    downloadText(`n8n-guide-${projectId}.md`, n8nSpec.markdown);
  }

  function openPromptModal(promptObj = null) {
    $("modal-error").classList.add("hidden");
    $("modal-error").innerText = "";

    if (!promptObj) {
      $("modal-title").innerText = "Nuevo Prompt";
      $("modal-prompt-id").value = "";
      $("modal-name").value = "";
      $("modal-doc-type").value = "Tesis Completa";
      $("modal-is-active").checked = true;
      $("modal-template").value = "";
      $("modal-vars").value = '["tema","objetivo_general"]';
    } else {
      $("modal-title").innerText = "Editar Prompt";
      $("modal-prompt-id").value = promptObj.id;
      $("modal-name").value = promptObj.name || "";
      $("modal-doc-type").value = promptObj.doc_type || "Tesis Completa";
      $("modal-is-active").checked = !!promptObj.is_active;
      $("modal-template").value = promptObj.template || "";
      $("modal-vars").value = JSON.stringify(promptObj.variables || []);
    }

    $("modal-prompt").classList.remove("hidden");
  }

  function closePromptModal() {
    $("modal-prompt").classList.add("hidden");
  }

  async function savePrompt() {
    try {
      $("modal-error").classList.add("hidden");
      const id = $("modal-prompt-id").value.trim();
      const name = $("modal-name").value.trim();
      const doc_type = $("modal-doc-type").value;
      const is_active = $("modal-is-active").checked;
      const template = $("modal-template").value;

      let variables;
      try {
        variables = JSON.parse($("modal-vars").value);
        if (!Array.isArray(variables)) throw new Error("invalid");
      } catch (_) {
        throw new Error('Variables debe ser un JSON Array valido. Ej: ["tema","objetivo_general"]');
      }

      if (!name) throw new Error("Nombre requerido");

      const body = { name, doc_type, is_active, template, variables };
      if (!id) await apiSend("/api/prompts", "POST", body);
      else await apiSend(`/api/prompts/${encodeURIComponent(id)}`, "PUT", body);

      closePromptModal();
      await refreshPromptsAdmin();
      await loadPromptsForWizard();
    } catch (error) {
      $("modal-error").classList.remove("hidden");
      $("modal-error").innerText = error.message || String(error);
    }
  }

  async function deletePrompt(id) {
    if (!confirm("Eliminar este prompt?")) return;
    await apiSend(`/api/prompts/${encodeURIComponent(id)}`, "DELETE");
    await refreshPromptsAdmin();
    await loadPromptsForWizard();
  }

  async function refreshPromptsAdmin() {
    const items = await apiGet("/api/prompts");
    const tbody = $("prompts-table");
    tbody.innerHTML = "";

    if (!items.length) {
      $("prompts-empty").classList.remove("hidden");
      return;
    }
    $("prompts-empty").classList.add("hidden");

    items.forEach((prompt) => {
      const vars = (prompt.variables || [])
        .slice(0, 6)
        .map((value) => `<span class="bg-blue-50 text-blue-600 px-2 py-1 rounded text-xs border border-blue-100 mx-1">${escapeHtml(value)}</span>`)
        .join("");
      const status = prompt.is_active
        ? '<span class="text-green-600 text-xs font-bold">Activo</span>'
        : '<span class="text-gray-400 text-xs font-bold">Inactivo</span>';

      const row = document.createElement("tr");
      row.className = "hover:bg-gray-50 transition";
      row.innerHTML = `
        <td class="px-6 py-4 font-medium">${escapeHtml(prompt.name)}</td>
        <td class="px-6 py-4">${vars || '<span class="text-xs text-gray-400">Sin variables</span>'}</td>
        <td class="px-6 py-4">${status}</td>
        <td class="px-6 py-4 text-right text-gray-400">
          <i class="fa-solid fa-pen hover:text-blue-600 cursor-pointer mr-3"></i>
          <i class="fa-solid fa-trash hover:text-red-600 cursor-pointer"></i>
        </td>
      `;
      row.querySelector(".fa-pen").onclick = () => openPromptModal(prompt);
      row.querySelector(".fa-trash").onclick = () => deletePrompt(prompt.id);
      tbody.appendChild(row);
    });
  }

  async function refreshHistory() {
    const items = _sortProjectsForProduct(await apiGet("/api/projects"));
    const tbody = $("history-table");
    tbody.innerHTML = "";

    const q = ($("history-search")?.value || "").toLowerCase();
    const filtered = items.filter((project) => {
      const blob = `${project.title || ""} ${project.prompt_name || ""} ${project.format_name || ""}`.toLowerCase();
      return !q || blob.includes(q);
    });

    if (!filtered.length) {
      $("history-empty").classList.remove("hidden");
      return;
    }
    $("history-empty").classList.add("hidden");

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
        <td class="px-6 py-4">${statusBadge(_effectiveProjectStatus(project))}</td>
        <td class="px-6 py-4 text-gray-500">${escapeHtml(_formatProjectDate(project))}</td>
        <td class="px-6 py-4 text-right">
          <div class="flex justify-end gap-2">${_renderProjectActions(project)}</div>
        </td>
      `;
      tbody.appendChild(row);
    });
  }

  function wireHistorySearch() {
    const input = $("history-search");
    if (!input) return;
    input.oninput = () => refreshHistory().catch(() => { });
  }

  // =========================================================================


  function _switchDocTab(tab) {
    document.querySelectorAll("[data-doc-tab]").forEach((btn) => {
      if (btn.getAttribute("data-doc-tab") === tab) {
        btn.classList.add("active");
      } else {
        btn.classList.remove("active");
      }
    });
    document.querySelectorAll("[data-doc-panel]").forEach((panel) => {
      if (panel.getAttribute("data-doc-panel") === tab) {
        panel.classList.remove("hidden");
      } else {
        panel.classList.add("hidden");
      }
    });
  }



  return {
    showView,
    nextStep,
    prevStep,
    goToProviderStep,
    triggerGeneration,
    cancelGeneration,
    retryGeneration,
    goToDownloads,
    runN8nSimulation,
    continueToSimDownloads,
    openProject,
    goToProjectStep,
    openPromptModal,
    closePromptModal,
    savePrompt,
    copyN8nPayload,
    copyN8nHeaders,
    copyN8nWebhook,
    exportN8nGuide,
    _switchDocTab,
    _filterTimeline,
    async boot() {
      wireHistorySearch();
      await refreshDashboard();
    },
  };
})();

window.TesisAI = TesisAI;
window.addEventListener("DOMContentLoaded", () => TesisAI.boot().catch(console.error));

