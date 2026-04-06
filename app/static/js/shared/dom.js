export function byId(id, root = document) {
  if (!id) return null;
  if (typeof root.getElementById === "function") {
    return root.getElementById(id);
  }
  return root.querySelector(`#${id}`);
}

export function show(element, displayClass = "hidden") {
  if (!element) return;
  element.classList.remove(displayClass);
}

export function hide(element, displayClass = "hidden") {
  if (!element) return;
  element.classList.add(displayClass);
}

export function setText(element, value) {
  if (!element) return;
  element.textContent = String(value ?? "");
}

export function setHtml(element, value) {
  if (!element) return;
  element.innerHTML = String(value ?? "");
}

export function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  }[char]));
}
