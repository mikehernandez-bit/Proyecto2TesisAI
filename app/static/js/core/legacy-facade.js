export function installLegacyFacade(app, root = window) {
  if (!app || !root) return null;

  const facade = Object.entries(app).reduce((api, [key, value]) => {
    if (typeof value === "function") {
      api[key] = (...args) => app[key](...args);
    }
    return api;
  }, {});

  root.TesisAI = Object.freeze(facade);
  return root.TesisAI;
}
