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
    section.section_id
      || section.sectionId
      || section.section_path
      || section.sectionPath
      || section.path
      || ""
  ).trim();
}

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

function buildTreeFromFlatSections(sections) {
  const nodes = new Map();
  const roots = [];

  sections
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

export function findNodeByKey(nodes, key) {
  for (const node of Array.isArray(nodes) ? nodes : []) {
    if (selectionKey(node) === key || node.section_path === key) return node;
    const nested = findNodeByKey(node.children || [], key);
    if (nested) return nested;
  }
  return null;
}

export function computeNodeSelectionState(node, selectedKeys) {
  const concreteKeys = collectConcreteSelectionKeys(node, []);
  if (!concreteKeys.length) return "unchecked";
  const keysSet = selectedKeys instanceof Set ? selectedKeys : new Set(selectedKeys);
  const selectedCount = concreteKeys.filter((key) => keysSet.has(key)).length;
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

export function buildSectionTree(promptPackage) {
  let roots = [];
  if (Array.isArray(promptPackage?.section_tree) && promptPackage.section_tree.length) {
    roots = promptPackage.section_tree.map(normalizeTreeNode);
    sortNodes(roots);
  } else {
    const sections = Array.isArray(promptPackage?.sections) ? promptPackage.sections : [];
    roots = buildTreeFromFlatSections(sections);
  }

  // Inyectar sección especial para Maestría UNAC y Proyecto UNAC si aplica (Universal)
  const formatId = String(promptPackage?.format_id || promptPackage?._meta?.id || "").toLowerCase();
  const metaUniversity = String(promptPackage?._meta?.university || "").toLowerCase();
  const metaCategory = String(promptPackage?._meta?.category || "").toLowerCase();
    const isMaestria = (
      formatId.includes("maestria") ||
      formatId.includes("unac-proyecto") ||
      (metaUniversity === "unac" && metaCategory.includes("proyecto"))
    );

  if (isMaestria) {
    const specialKey = "titulo-info-basica";
    if (!roots.some((s) => selectionKey(s) === specialKey)) {
      const specialSection = {
        ...normalizeSection({
          section_id: specialKey,
          section_path: "Título + Información Básica",
          section_title: "Título + Información Básica",
          section_order: -100, // Forzar que aparezca primero
          default_selected: true,
          optional: false,
          blocks: [
            {
              block_id: "block:titulo-info",
              header: "Validación de Título e Información Básica",
              label: "Validación de Título e Información Básica",
              required: true,
            },
          ],
        }),
        children: [],
      };
      roots.unshift(specialSection);
    }
  }

  return roots;
}

export function flattenTree(nodes, result = []) {
  (Array.isArray(nodes) ? nodes : []).forEach((node) => {
    const normalized = normalizeSection(node);
    result.push(normalized);
    flattenTree(node.children || [], result);
  });
  return result;
}

function collectConcreteNodes(node, result = []) {
  const children = Array.isArray(node?.children) ? node.children : [];
  const hasOwnBlocks = Array.isArray(node?.blocks) && node.blocks.length > 0;
  const isGroupingOnly = children.length > 0 && !hasOwnBlocks;
  if (!isGroupingOnly) {
    result.push(normalizeSection(node));
  }
  children.forEach((child) => collectConcreteNodes(child, result));
  return result;
}

function expandSelectedNode(node, resolvedKeys) {
  const target = node;
  if (!target) return;
  collectConcreteNodes(target).forEach((item) => {
    const key = selectionKey(item);
    if (key) resolvedKeys.add(key);
  });
}

export function normalizeSelectedSections(selectedSections, promptPackage) {
  const tree = buildSectionTree(promptPackage);
  const flatSections = flattenTree(tree);
  const byKey = new Map(flatSections.map((item) => [selectionKey(item), item]));
  const hasExplicitSelection = Array.isArray(selectedSections);
  const rawKeys = hasExplicitSelection
    ? selectedSections.map(selectionKey).filter(Boolean)
    : (Array.isArray(promptPackage?.selected_sections) && promptPackage.selected_sections.length
        ? promptPackage.selected_sections
        : flatSections.filter((section) => section.default_selected)
      )
        .map(selectionKey)
        .filter(Boolean);
  const resolvedKeys = new Set();

  rawKeys.forEach((key) => {
    const section = byKey.get(key) || flatSections.find((item) => key === item.section_path || key === item.section_id);
    if (!section) return;
    expandSelectedNode(section, resolvedKeys);
  });

  return flatSections
    .filter((section) => resolvedKeys.has(selectionKey(section)))
    .map((section) => ({
      section_id: section.section_id || "",
      section_path: section.section_path || "",
      section_title: section.section_title || "",
      parent_section_path: section.parent_section_path || "",
      section_level: Number(section.section_level || 1),
      section_order: Number(section.section_order || 0),
      optional: Boolean(section.optional),
      default_selected: Boolean(section.default_selected ?? true),
    }));
}
