import { requestJson } from "./shared/api-client.js";
import {
  fetchPromptPackage,
  normalizeSelectedSections,
  selectionKey,
} from "./features/wizard/prompt-package-client.js";
import {
  flattenSections,
  selectedSectionMap,
  sectionCountLabel,
} from "./features/wizard/section-selection.js";
import { buildDetailsGroups } from "./features/wizard/details-step.js";
import {
  createAdminEditorState,
  findEditableSection,
} from "./features/prompt-packages/admin-editor.js";

window.TesisAIAppModules = {
  requestJson,
  fetchPromptPackage,
  normalizeSelectedSections,
  selectionKey,
  flattenSections,
  selectedSectionMap,
  sectionCountLabel,
  buildDetailsGroups,
  createAdminEditorState,
  findEditableSection,
};
