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

describe("Arabic RTL accessibility", () => {
  beforeEach(async () => {
    document.documentElement.lang = "en";
    document.documentElement.dir = "ltr";
    window.localStorage.clear();
    await i18n.changeLanguage("ar");
  });

  afterEach(async () => {
    document.documentElement.dir = "ltr";
    await i18n.changeLanguage("en");
  });

  it("renders a 7-language switcher and updates html lang/dir", async () => {
    const view = await renderIntoDocument(<App />);

    try {
      await flushEffects();

      const languageGroup = view.container.querySelector('[aria-label="Language preference"]');
      expect(languageGroup).not.toBeNull();

      const buttons = Array.from(languageGroup?.querySelectorAll("button") ?? []);
      expect(buttons.map((button) => button.textContent?.trim())).toEqual(["EN", "RU", "DE", "ES", "FR", "ZH", "AR"]);

      const activeButton = buttons.find((button) => button.textContent?.trim() === "AR");
      expect(activeButton?.getAttribute("aria-pressed")).toBe("true");
      expect(document.documentElement.lang).toBe("ar");
      expect(document.documentElement.dir).toBe("rtl");
    } finally {
      await view.unmount();
    }
  });

  it("has no critical or serious accessibility violations in rtl", async () => {
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
