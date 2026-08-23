import { byId } from "../../shared/dom.js";

export function createWizardController({ totalSteps = 7, onStepChange, getScrollContainer } = {}) {
  const stepRegistry = new Map();
  let currentStep = 1;
  let mountedStep = null;

  function resetScrollPosition() {
    const container = getScrollContainer?.();
    if (!container) return;
    if (typeof container.scrollTo === "function") {
      container.scrollTo({ top: 0, left: 0, behavior: "auto" });
      return;
    }
    container.scrollTop = 0;
    container.scrollLeft = 0;
  }

  function scheduleScrollReset() {
    if (typeof requestAnimationFrame === "function") {
      requestAnimationFrame(resetScrollPosition);
      return;
    }
    resetScrollPosition();
  }

  function updateStepperUI(step) {
    const label = byId("current-step-label");
    if (label) {
      label.textContent = String(step);
    }

    for (let index = 1; index <= totalSteps; index += 1) {
      const dot = byId(`step-${index}-dot`);
      if (!dot) continue;
      dot.className = "w-8 h-8 rounded-full flex items-center justify-center font-bold text-sm z-10";
      if (index < step) {
        dot.classList.add("bg-green-500", "text-white");
        dot.innerHTML = '<i class="fa-solid fa-check"></i>';
      } else if (index === step) {
        dot.classList.add("bg-blue-600", "text-white");
        dot.textContent = String(index);
      } else {
        dot.classList.add("bg-gray-200", "text-gray-500");
        dot.textContent = String(index);
      }
    }

    for (let index = 1; index < totalSteps; index += 1) {
      const line = byId(`step-${index}-line`);
      if (!line) continue;
      line.className = "flex-1 h-1 mx-2 rounded";
      line.classList.add(index < step ? "bg-green-500" : "bg-gray-200");
    }
  }

  function showStep(step) {
    for (let index = 1; index <= totalSteps; index += 1) {
      const content = byId(`step-${index}-content`);
      if (!content) continue;
      if (index === step) {
        content.classList.remove("hidden");
        content.classList.add("fade-in");
      } else {
        content.classList.add("hidden");
      }
    }
  }

  return {
    registerStep(step, handlers = {}) {
      stepRegistry.set(Number(step), handlers);
    },
    async goTo(step, context = {}) {
      const nextStep = Math.max(1, Math.min(totalSteps, Number(step || 1)));
      if (mountedStep?.unmount) {
        mountedStep.unmount();
      }
      currentStep = nextStep;
      updateStepperUI(nextStep);
      showStep(nextStep);
      resetScrollPosition();
      mountedStep = stepRegistry.get(nextStep) || null;
      if (mountedStep?.mount) {
        await mountedStep.mount(context);
      }
      await onStepChange?.(nextStep, context);
      scheduleScrollReset();
    },
    getCurrentStep() {
      return currentStep;
    },
    refresh() {
      updateStepperUI(currentStep);
      showStep(currentStep);
    },
  };
}
