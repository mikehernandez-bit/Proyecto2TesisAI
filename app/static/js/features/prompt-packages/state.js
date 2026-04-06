const INITIAL_STATE = {
  formatId: "",
  promptPackage: null,
  editorState: null,
  activeSectionKey: "",
  meta: {},
};

let state = { ...INITIAL_STATE };

export function getPromptAdminState() {
  return state;
}

export function patchPromptAdminState(partial) {
  state = {
    ...state,
    ...(partial || {}),
  };
  return state;
}
