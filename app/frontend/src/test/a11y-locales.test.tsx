// @vitest-environment jsdom

import type { ReactNode } from "react";

import "vitest-axe/extend-expect";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";
import * as matchers from "vitest-axe/matchers";

vi.mock("../components/ErrorBoundary", () => ({
  default: function ErrorBoundaryMock({ children }: { children: ReactNode }) {
    return <>{children}</>;
  }
}));

vi.mock("../components/SidebarPanel", () => ({
  default: function SidebarPanelMock() {
    return <aside>Sidebar panel</aside>;
  }
}));

vi.mock("../components/WizardPanel", () => ({
  default: function WizardPanelMock() {
    return <section><h2>Wizard panel</h2></section>;
  },
  GlobalSideEffects: function GlobalSideEffectsMock() {
    return null;
  },
  OnboardingPanel: function OnboardingPanelMock() {
    return <section>Onboarding panel</section>;
  }
}));

import App from "../App";
import i18n from "../i18n";
import { flushEffects, renderIntoDocument } from "./dom";

expect.extend(matchers);

type AxeMatcher = {
  toHaveNoViolations: () => void;
};

describe.each([
  { locale: "de", activeLabel: "DE" },
  { locale: "es", activeLabel: "ES" }
] as const)("Locale accessibility: $locale", ({ locale, activeLabel }) => {
  beforeEach(async () => {
    document.documentElement.lang = "en";
    window.localStorage.clear();
    await i18n.changeLanguage(locale);
  });

  afterEach(async () => {
    await i18n.changeLanguage("en");
  });

  it("renders the full language switcher and updates html lang", async () => {
    const view = await renderIntoDocument(<App />);

    try {
      await flushEffects();

      const languageGroup = view.container.querySelector('[aria-label="Language preference"]');
      expect(languageGroup).not.toBeNull();

      const buttons = Array.from(languageGroup?.querySelectorAll("button") ?? []);
      expect(buttons.map((button) => button.textContent?.trim())).toEqual(["EN", "RU", "DE", "ES"]);

      const activeButton = buttons.find((button) => button.textContent?.trim() === activeLabel);
      expect(activeButton?.getAttribute("aria-pressed")).toBe("true");
      expect(document.documentElement.lang).toBe(locale);
    } finally {
      await view.unmount();
    }
  });

  it("has no critical or serious accessibility violations", async () => {
    const view = await renderIntoDocument(<App />);

    try {
      await flushEffects();

      const results = await axe(view.container);

      (expect({
        ...results,
        violations: results.violations.filter(
          (violation) => violation.impact === "critical" || violation.impact === "serious"
        )
      }) as unknown as AxeMatcher).toHaveNoViolations();
    } finally {
      await view.unmount();
    }
  }, 15000);
});
