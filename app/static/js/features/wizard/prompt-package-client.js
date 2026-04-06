import { requestJson } from "../../shared/api-client.js";

export async function fetchPromptPackage(formatId) {
  if (!formatId) {
    throw new Error("formatId requerido");
  }
  return requestJson(`/api/formats/${encodeURIComponent(formatId)}/prompt-package`);
}

export function selectionKey(section) {
  if (!section) return "";
  if (typeof section === "string") return section.trim();
  return String(
    section.section_id ||
      section.sectionId ||
      section.section_path ||
      section.sectionPath ||
      section.path ||
      ""
  ).trim();
}

export function normalizeSelectedSections(selectedSections, promptPackage) {
  const sections = Array.isArray(promptPackage?.sections) ? promptPackage.sections : [];
  const byKey = new Map(sections.map((item) => [selectionKey(item), item]));
  const keys = Array.isArray(selectedSections) && selectedSections.length
    ? selectedSections.map(selectionKey).filter(Boolean)
    : (Array.isArray(promptPackage?.selected_sections) ? promptPackage.selected_sections : [])
        .map(selectionKey)
        .filter(Boolean);
  return keys
    .map((key) => {
      const section = byKey.get(key);
      if (!section) return null;
      return {
        section_id: section.section_id || section.sectionId || "",
        section_path: section.section_path || section.sectionPath || section.path || "",
        section_title: section.section_title || section.sectionTitle || section.title || "",
        parent_section_path: section.parent_section_path || section.parentSectionPath || "",
        section_level: Number(section.section_level || section.sectionLevel || 1),
        optional: Boolean(section.optional),
        default_selected: Boolean(section.default_selected ?? section.defaultSelected ?? true),
      };
    })
    .filter(Boolean);
}
