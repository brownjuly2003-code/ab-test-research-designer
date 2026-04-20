import { create } from "zustand";

type StepUpdater = number | ((current: number) => number);

export interface WizardState {
  step: number;
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
  } catch {}
}

export const useWizardStore = create<WizardState>((set) => ({
  step: 0,
  showOnboarding: !readOnboardingSeen(),
  importingDraft: false,
  setStep: (step) => set((state) => ({
    step: typeof step === "function" ? step(state.step) : step
  })),
  setShowOnboarding: (showOnboarding) => {
    persistOnboardingState(showOnboarding);
    set({ showOnboarding });
  },
  setImportingDraft: (importingDraft) => set({ importingDraft }),
  openWizard: (step = 0) => {
    persistOnboardingState(false);
    set({ step, showOnboarding: false });
  },
  hydrateWizard: () => set({
    step: 0,
    importingDraft: false,
    showOnboarding: !readOnboardingSeen()
  })
}));
