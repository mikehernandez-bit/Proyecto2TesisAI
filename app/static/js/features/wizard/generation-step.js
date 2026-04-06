export function createGenerationStep({ onEnter, onExit } = {}) {
  return {
    async mount() {
      await onEnter?.();
    },
    unmount() {
      onExit?.();
    },
    validate() {
      return true;
    },
    serialize() {
      return null;
    },
  };
}
