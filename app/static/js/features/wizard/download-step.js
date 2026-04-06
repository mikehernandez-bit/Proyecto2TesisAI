export function createDownloadStep({ onEnter } = {}) {
  return {
    async mount() {
      await onEnter?.();
    },
    unmount() {},
    validate() {
      return true;
    },
    serialize() {
      return null;
    },
  };
}
