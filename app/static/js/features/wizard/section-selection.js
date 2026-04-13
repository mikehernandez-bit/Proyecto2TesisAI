export {
  selectionKey,
  buildSectionTree,
  flattenTree,
  normalizeSection,
  hasOwnBlocks,
  isGroupingOnlySection,
  countRequiredVariables,
  parentScopeLabel,
  collectConcreteSelectionKeys,
  computeNodeSelectionState,
  applyNodeSelection,
  findNodeByKey
} from "./prompt-package-client.js";

/**
 * Re-implementing high-level bridge functions that depend on the unified core.
 */
import {
  selectionKey,
  buildSectionTree,
  flattenTree,
  normalizeSection
} from "./prompt-package-client.js";

export function flattenSections(promptPackage) {
  let orderedSections = flattenTree(buildSectionTree(promptPackage));

  const rawSections = Array.isArray(promptPackage?.sections)
    ? promptPackage.sections
        .map(normalizeSection)
        .filter((section) => section.section_id || section.section_path)
    : [];
  if (!rawSections.length) {
    return orderedSections;
  }

  const rawByKey = new Map();
  rawSections.forEach((section) => {
    [selectionKey(section), section.section_path, section.section_id]
      .filter(Boolean)
      .forEach((key) => rawByKey.set(key, section));
  });

  return orderedSections.map((section) => (
    rawByKey.get(selectionKey(section))
    || rawByKey.get(section.section_path)
    || rawByKey.get(section.section_id)
    || section
  ));
}

export function selectedSectionMap(promptPackage, selectedSections) {
  const selectedKeys = new Set(
    (Array.isArray(selectedSections) ? selectedSections : []).map(selectionKey).filter(Boolean)
  );
  return flattenSections(promptPackage).map((section) => ({
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
