function resolveActionElement(target, attributeName) {
  if (!(target instanceof Element)) return null;
  return target.closest(`[${attributeName}]`);
}

function resolveErrorContainer(element) {
  const targetId = String(element?.dataset?.errorTarget || "").trim();
  if (!targetId) return null;
  return document.getElementById(targetId);
}

function setErrorState(element, error) {
  const container = resolveErrorContainer(element);
  if (!container) return;

  const fallbackMessage = String(element?.dataset?.errorMessage || "").trim();
  const message = String(error?.message || fallbackMessage || "Ocurrio un error inesperado.").trim();
  container.textContent = message;
  container.classList.remove("hidden");
}

function clearErrorState(element) {
  const container = resolveErrorContainer(element);
  if (!container) return;
  container.textContent = "";
  container.classList.add("hidden");
}

async function runHandler({ handlers, actionName, element, event, root }) {
  const handler = handlers[actionName];
  if (typeof handler !== "function") return;

  clearErrorState(element);
  try {
    await handler({ element, event, root });
  } catch (error) {
    console.error(`Action "${actionName}" failed:`, error);
    setErrorState(element, error);
  }
}

export function bindDeclarativeActions({ handlers = {}, root = document } = {}) {
  const onClick = async (event) => {
    const element = resolveActionElement(event.target, "data-action");
    if (!element) return;
    event.preventDefault();
    if ("disabled" in element && element.disabled) return;
    await runHandler({
      handlers,
      actionName: String(element.dataset.action || "").trim(),
      element,
      event,
      root,
    });
  };

  const onChange = async (event) => {
    const element = resolveActionElement(event.target, "data-change-action");
    if (!element) return;
    await runHandler({
      handlers,
      actionName: String(element.dataset.changeAction || "").trim(),
      element,
      event,
      root,
    });
  };

  root.addEventListener("click", onClick);
  root.addEventListener("change", onChange);

  return {
    destroy() {
      root.removeEventListener("click", onClick);
      root.removeEventListener("change", onChange);
    },
  };
}
