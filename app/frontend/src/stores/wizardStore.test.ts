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

  it("tracks the furthest step reached and keeps it when stepping back", async () => {
    const { useWizardStore } = await loadWizardStore();

    useWizardStore.getState().setStep(4);
    useWizardStore.getState().setStep(1);

    expect(useWizardStore.getState().step).toBe(1);
    expect(useWizardStore.getState().maxVisitedStep).toBe(4);
  });

  it("openWizard(step) also extends the furthest visited step", async () => {
    const { useWizardStore } = await loadWizardStore();

    useWizardStore.getState().openWizard(5);

    expect(useWizardStore.getState().step).toBe(5);
    expect(useWizardStore.getState().maxVisitedStep).toBe(5);
  });

  it("hydrateWizard resets the furthest visited step", async () => {
    const { useWizardStore } = await loadWizardStore();

    useWizardStore.getState().setStep(3);
    useWizardStore.getState().hydrateWizard();

    expect(useWizardStore.getState().maxVisitedStep).toBe(0);
  });

  it("initializes onboarding from localStorage", async () => {
    window.localStorage.setItem(onboardingStorageKey, "true");

    const { useWizardStore } = await loadWizardStore();

    expect(useWizardStore.getState().showOnboarding).toBe(false);
  });
});
