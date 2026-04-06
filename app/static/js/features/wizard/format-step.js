export function createFormatStep({ onEnter } = {}) {
  return {
    mount() {
      onEnter?.();
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
