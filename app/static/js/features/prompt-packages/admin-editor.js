import { selectionKey } from "../wizard/prompt-package-client.js";

function clonePackageSection(section) {
  return {
    section_id: section.section_id || section.sectionId || "",
    section_path: section.section_path || section.sectionPath || section.path || "",
    section_title: section.section_title || section.sectionTitle || section.title || "",
    parent_section_path: section.parent_section_path || section.parentSectionPath || "",
    section_level: Number(section.section_level || section.sectionLevel || 1),
    section_order: Number(section.section_order || section.sectionOrder || 0),
    optional: Boolean(section.optional),
    default_selected: Boolean(section.default_selected ?? section.defaultSelected ?? true),
    source_hints: section.source_hints || section.sourceHints || "",
    blocks: Array.isArray(section.blocks)
      ? section.blocks.map((block) => ({
          block_id: block.block_id || block.id || "",
          header: block.header || block.cabecera || block.titulo_cabecera || block.label || "",
          cabecera: block.cabecera || block.header || block.titulo_cabecera || block.label || "",
          label: block.label || "",
          instructions: block.instructions || "",
          required_variables: Array.isArray(block.required_variables) ? [...block.required_variables] : [],
          required: Boolean(block.required ?? true),
          legacy_prompt_id: block.legacy_prompt_id || "",
        }))
      : [],
  };
}

export function createAdminEditorState(promptPackage) {
  return {
    ...promptPackage,
    sections: (Array.isArray(promptPackage?.sections) ? promptPackage.sections : []).map(clonePackageSection),
  };
}

export function findEditableSection(editorState, key) {
  return (Array.isArray(editorState?.sections) ? editorState.sections : []).find(
    (section) => selectionKey(section) === key
  );
}
