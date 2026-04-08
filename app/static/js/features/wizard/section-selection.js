import { selectionKey } from "./prompt-package-client.js";

function normalizeBlock(block) {
  return {
    block_id: block?.block_id || block?.id || "",
    header: block?.header || block?.cabecera || block?.titulo_cabecera || block?.label || "",
    cabecera: block?.cabecera || block?.header || block?.titulo_cabecera || block?.label || "",
    label: block?.label || block?.header || block?.cabecera || "",
    instructions: block?.instructions || "",
    required_variables: Array.isArray(block?.required_variables) ? [...block.required_variables] : [],
    required: Boolean(block?.required ?? true),
  };
}

export function normalizeSection(section) {
  return {
    section_id: section?.section_id || section?.sectionId || "",
    section_path: section?.section_path || section?.sectionPath || section?.path || "",
    section_title: section?.section_title || section?.sectionTitle || section?.title || "",
    parent_section_path: section?.parent_section_path || section?.parentSectionPath || "",
    section_level: Number(section?.section_level || section?.sectionLevel || 1),
    section_order: Number(section?.section_order || section?.sectionOrder || 0),
    optional: Boolean(section?.optional),
    default_selected: Boolean(section?.default_selected ?? section?.defaultSelected ?? true),
    source_hints: section?.source_hints || section?.sourceHints || "",
    blocks: Array.isArray(section?.blocks) ? section.blocks.map(normalizeBlock) : [],
  };
}

function normalizeTreeNode(section) {
  return {
    ...normalizeSection(section),
    children: Array.isArray(section?.children) ? section.children.map(normalizeTreeNode) : [],
  };
}

function sortNodes(items) {
  items.sort((left, right) => {
    const orderGap = Number(left.section_order || 0) - Number(right.section_order || 0);
    if (orderGap !== 0) return orderGap;
    const levelGap = Number(left.section_level || 0) - Number(right.section_level || 0);
    if (levelGap !== 0) return levelGap;
    return String(left.section_path || left.section_id).localeCompare(String(right.section_path || right.section_id));
  });
  items.forEach((item) => sortNodes(item.children || []));
}

export function flattenTree(nodes, result = []) {
  (Array.isArray(nodes) ? nodes : []).forEach((node) => {
    result.push(normalizeSection(node));
    flattenTree(node.children || [], result);
  });
  return result;
}

export function flattenSections(promptPackage) {
  const orderedSections = flattenTree(buildSectionTree(promptPackage));
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

export function buildSectionTree(promptPackageOrSections) {
  if (Array.isArray(promptPackageOrSections?.section_tree) && promptPackageOrSections.section_tree.length) {
    const tree = promptPackageOrSections.section_tree.map(normalizeTreeNode);
    sortNodes(tree);
    return tree;
  }

  const rawSections = Array.isArray(promptPackageOrSections)
    ? promptPackageOrSections
    : (Array.isArray(promptPackageOrSections?.sections) ? promptPackageOrSections.sections : []);

  if (!rawSections.length) return [];

  if (rawSections.some((section) => Array.isArray(section?.children))) {
    return rawSections.map(normalizeTreeNode);
  }

  const nodes = new Map();
  const roots = [];

  rawSections
    .map(normalizeSection)
    .filter((section) => section.section_id || section.section_path)
    .forEach((section) => {
      nodes.set(section.section_path || section.section_id, { ...section, children: [] });
    });

  nodes.forEach((node) => {
    const parent = nodes.get(node.parent_section_path);
    if (!parent) {
      roots.push(node);
      return;
    }
    parent.children.push(node);
  });

  sortNodes(roots);
  return roots;
}

export function hasOwnBlocks(section) {
  return Array.isArray(section?.blocks) && section.blocks.length > 0;
}

export function isGroupingOnlySection(section) {
  const children = Array.isArray(section?.children) ? section.children : [];
  return children.length > 0 && !hasOwnBlocks(section);
}

export function countRequiredVariables(section) {
  return Array.from(new Set(
    (Array.isArray(section?.blocks) ? section.blocks : [])
      .flatMap((block) => Array.isArray(block.required_variables) ? block.required_variables : [])
      .map((value) => String(value || "").trim())
      .filter(Boolean),
  )).length;
}

export function parentScopeLabel(section) {
  const rawPath = String(section?.section_path || section?.section_title || "").trim();
  const pathParts = rawPath.split("/").map((value) => value.trim()).filter(Boolean);
  const scope = pathParts.length > 1
    ? pathParts.slice(0, -1).join(" / ")
    : String(section?.parent_section_path || "").trim();
  return scope || rawPath || "";
}

export function collectConcreteSelectionKeys(node, result = []) {
  if (!node) return result;
  if (!isGroupingOnlySection(node)) {
    const key = selectionKey(node);
    if (key) result.push(key);
  }
  (Array.isArray(node.children) ? node.children : []).forEach((child) => collectConcreteSelectionKeys(child, result));
  return result;
}

function findNodeByKey(nodes, key) {
  for (const node of Array.isArray(nodes) ? nodes : []) {
    if (selectionKey(node) === key || node.section_path === key) return node;
    const nested = findNodeByKey(node.children || [], key);
    if (nested) return nested;
  }
  return null;
}

export function computeNodeSelectionState(node, selectedKeys) {
  const concreteKeys = collectConcreteSelectionKeys(node, []);
  if (!concreteKeys.length) {
    return "unchecked";
  }
  const selectedCount = concreteKeys.filter((key) => selectedKeys.has(key)).length;
  if (!selectedCount) return "unchecked";
  if (selectedCount === concreteKeys.length) return "checked";
  return "indeterminate";
}

export function applyNodeSelection(tree, selectedKeys, nodeKey, checked) {
  const next = new Set(selectedKeys instanceof Set ? selectedKeys : []);
  const node = findNodeByKey(tree, nodeKey);
  if (!node) return next;
  collectConcreteSelectionKeys(node, []).forEach((key) => {
    if (checked) next.add(key);
    else next.delete(key);
  });
  return next;
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
