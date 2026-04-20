// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from "vitest";

const onboardingStorageKey = "ab-test:onboarding-seen";

async function loadWizardStore() {
  vi.resetModules();
  return import("./wizardStore");
}

beforeEach(() => {
  window.localStorage.clear();
});

describe("wizardStore", () => {
  it("updates the active step", async () => {
    const { useWizardStore } = await loadWizardStore();

    useWizardStore.getState().setStep(3);

    expect(useWizardStore.getState().step).toBe(3);
  });

  it("openWizard resets step and hides onboarding", async () => {
    const { useWizardStore } = await loadWizardStore();

    useWizardStore.getState().setStep(4);
    useWizardStore.getState().openWizard();

    expect(useWizardStore.getState().step).toBe(0);
    expect(useWizardStore.getState().showOnboarding).toBe(false);
    expect(window.localStorage.getItem(onboardingStorageKey)).toBe("true");
  });

  it("initializes onboarding from localStorage", async () => {
    window.localStorage.setItem(onboardingStorageKey, "true");

    const { useWizardStore } = await loadWizardStore();

    expect(useWizardStore.getState().showOnboarding).toBe(false);
  });
});
