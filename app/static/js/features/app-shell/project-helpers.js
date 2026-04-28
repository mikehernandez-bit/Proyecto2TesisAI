function parseDate(value) {
  const raw = String(value || "").trim();
  if (!raw) return null;
  const parsed = new Date(raw);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

export function formatProjectDate(project) {
  return String(project?.updated_at || project?.created_at || "-");
}

export function projectValues(project) {
  if (project?.values && typeof project.values === "object") return project.values;
  if (project?.variables && typeof project.variables === "object") return project.variables;
  return {};
}

export function selectedSectionsFingerprint(sections) {
  const normalized = Array.isArray(sections) ? sections : [];
  const keys = Array.from(new Set(
    normalized
      .map((item) => {
        if (typeof item === "string") return item.trim();
        return String(
          item?.section_path
          || item?.sectionPath
          || item?.path
          || item?.section_id
          || item?.sectionId
          || "",
        ).trim();
      })
      .filter(Boolean),
  )).sort();
  return JSON.stringify(keys);
}

export function promptSnapshotFingerprint(promptSnapshot) {
  if (!promptSnapshot || typeof promptSnapshot !== "object") return "";
  const sections = Array.isArray(promptSnapshot.sections) ? promptSnapshot.sections : [];
  const normalized = sections.map((section) => ({
    section_id: String(section?.section_id || section?.sectionId || "").trim(),
    section_path: String(section?.section_path || section?.sectionPath || section?.path || "").trim(),
    parent_section_path: String(section?.parent_section_path || section?.parentSectionPath || "").trim(),
    section_level: Number(section?.section_level || section?.sectionLevel || 1),
    section_order: Number(section?.section_order || section?.sectionOrder || 0),
    source_hints: String(section?.source_hints || section?.sourceHints || "").trim(),
    blocks: (Array.isArray(section?.blocks) ? section.blocks : []).map((block) => ({
      block_id: String(block?.block_id || block?.id || "").trim(),
      header: String(block?.header || block?.cabecera || block?.titulo_cabecera || block?.label || "").trim(),
      label: String(block?.label || "").trim(),
      instructions: String(block?.instructions || "").trim(),
      required_variables: Array.from(new Set(
        (Array.isArray(block?.required_variables) ? block.required_variables : [])
          .map((value) => String(value || "").trim())
          .filter(Boolean),
      )).sort(),
    })),
  }));
  return JSON.stringify(normalized);
}

export function hasMeaningfulProjectValues(project) {
  const values = projectValues(project);
  return Object.entries(values).some(([key, value]) => {
    if (key === "title") return false;
    return String(value ?? "").trim().length > 0;
  });
}

export function effectiveProjectStatus(project) {
  const rawStatus = String(project?.status || "").toLowerCase().trim();
  if (rawStatus === "draft" && project?.format_id && project?.prompt_id && hasMeaningfulProjectValues(project)) {
    return "ready";
  }
  if (rawStatus === "ai_received") return "rendering";
  return rawStatus;
}

function projectStatusPriority(project) {
  const status = effectiveProjectStatus(project);
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

export function projectTokenTotal(project) {
  const usage = project?.token_usage && typeof project.token_usage === "object"
    ? project.token_usage
    : project?.progress?.tokenUsage || {};
  const total = Number(usage?.total_tokens || 0);
  return Number.isFinite(total) ? Math.max(0, total) : 0;
}

export function projectBudgetTotal(project) {
  const cost = project?.generation_cost && typeof project.generation_cost === "object"
    ? project.generation_cost
    : project?.progress?.costUsage || {};
  const total = Number(cost?.total_cost_usd || 0);
  return Number.isFinite(total) ? Math.max(0, total) : 0;
}

export function portfolioUsageSummary(items) {
  return (Array.isArray(items) ? items : []).reduce(
    (summary, project) => {
      summary.totalTokens += projectTokenTotal(project);
      summary.totalBudget += projectBudgetTotal(project);
      return summary;
    },
    { totalTokens: 0, totalBudget: 0 },
  );
}

export function sortProjectsForProduct(items) {
  return [...(Array.isArray(items) ? items : [])].sort((left, right) => {
    const leftTs = parseDate(left?.updated_at || left?.created_at)?.getTime() || 0;
    const rightTs = parseDate(right?.updated_at || right?.created_at)?.getTime() || 0;
    if (leftTs !== rightTs) return rightTs - leftTs;
    return projectStatusPriority(right) - projectStatusPriority(left);
  });
}
