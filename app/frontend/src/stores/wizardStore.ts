import { create } from "zustand";

type StepUpdater = number | ((current: number) => number);

export interface WizardState {
  step: number;
  // Highest step index reached this session; drives which step chips are clickable.
  maxVisitedStep: number;
  showOnboarding: boolean;
  importingDraft: boolean;
  setStep: (step: StepUpdater) => void;
  setShowOnboarding: (showOnboarding: boolean) => void;
  setImportingDraft: (importingDraft: boolean) => void;
  openWizard: (step?: number) => void;
  hydrateWizard: () => void;
}

const onboardingStorageKey = "ab-test:onboarding-seen";

function readOnboardingSeen(): boolean {
  if (typeof window === "undefined") {
    return false;
  }

  return window.localStorage.getItem(onboardingStorageKey) === "true";
}

function persistOnboardingState(showOnboarding: boolean) {
  if (typeof window === "undefined") {
    return;
  }

  try {
    if (showOnboarding) {
      window.localStorage.removeItem(onboardingStorageKey);
      return;
    }

    window.localStorage[onboardingStorageKey] = "true";
  } catch {
    // localStorage may be unavailable (private mode / quota); onboarding flag stays in-memory.
  }
}

export const useWizardStore = create<WizardState>((set) => ({
  step: 0,
  maxVisitedStep: 0,
  showOnboarding: !readOnboardingSeen(),
  importingDraft: false,
  setStep: (step) => set((state) => {
    const nextStep = typeof step === "function" ? step(state.step) : step;
    return { step: nextStep, maxVisitedStep: Math.max(state.maxVisitedStep, nextStep) };
  }),
  setShowOnboarding: (showOnboarding) => {
    persistOnboardingState(showOnboarding);
    set({ showOnboarding });
  },
  setImportingDraft: (importingDraft) => set({ importingDraft }),
  openWizard: (step = 0) => {
    persistOnboardingState(false);
    set((state) => ({ step, showOnboarding: false, maxVisitedStep: Math.max(state.maxVisitedStep, step) }));
  },
  hydrateWizard: () => set({
    step: 0,
    maxVisitedStep: 0,
    importingDraft: false,
    showOnboarding: !readOnboardingSeen()
  })
}));
