export function markPromptAdminListBooted(root = window) {
  if (!root) return;
  root.__promptAdminListBooted = true;
}
