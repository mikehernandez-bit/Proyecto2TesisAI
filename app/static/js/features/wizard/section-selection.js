import { selectionKey } from "./prompt-package-client.js";

export function flattenSections(promptPackage) {
  const sections = Array.isArray(promptPackage?.sections) ? promptPackage.sections : [];
  return sections
    .map((section) => ({
      section_id: section.section_id || section.sectionId || "",
      section_path: section.section_path || section.sectionPath || section.path || "",
      section_title: section.section_title || section.sectionTitle || section.title || "",
      parent_section_path: section.parent_section_path || section.parentSectionPath || "",
      section_level: Number(section.section_level || section.sectionLevel || 1),
      optional: Boolean(section.optional),
      default_selected: Boolean(section.default_selected ?? section.defaultSelected ?? true),
      blocks: Array.isArray(section.blocks) ? section.blocks : [],
    }))
    .filter((section) => section.section_id || section.section_path);
}

export function selectedSectionMap(promptPackage, selectedSections) {
  const selectedKeys = new Set(
    (Array.isArray(selectedSections) ? selectedSections : []).map(selectionKey).filter(Boolean)
  );
  const normalized = flattenSections(promptPackage);
  return normalized.map((section) => ({
    ...section,
    key: selectionKey(section),
    selected: selectedKeys.size ? selectedKeys.has(selectionKey(section)) : section.default_selected,
  }));
}

export function sectionCountLabel(items) {
  const total = Array.isArray(items) ? items.length : 0;
  const selected = Array.isArray(items) ? items.filter((item) => item.selected).length : 0;
  return { selected, total };
}
