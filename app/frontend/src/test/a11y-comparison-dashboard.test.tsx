// @vitest-environment jsdom

import "vitest-axe/extend-expect";

vi.mock("recharts", () => import("./recharts-stub"));

import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";
import * as matchers from "vitest-axe/matchers";

import ComparisonDashboard from "../components/ComparisonDashboard";
import { buildMultiProjectComparison } from "../components/results/__tests__/resultsTestUtils";
import { click, flushEffects, renderIntoDocument } from "./dom";

expect.extend(matchers);

type AxeMatcher = {
  toHaveNoViolations: () => void;
};

function ComparisonDashboardHarness() {
  const [open, setOpen] = useState(true);

  return (
    <>
      <button id="compare-selected-projects-button" type="button">
        Compare selected
      </button>
      {open ? (
        <ComparisonDashboard comparison={buildMultiProjectComparison()} onClose={() => setOpen(false)} />
      ) : null}
    </>
  );
}

describe("Comparison dashboard accessibility", () => {
  beforeEach(() => {
    document.documentElement.lang = "en";
    vi.stubGlobal(
      "ResizeObserver",
      class ResizeObserver {
        observe() {}
        unobserve() {}
        disconnect() {}
      }
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("has no axe violations and restores focus on close", async () => {
    const view = await renderIntoDocument(<ComparisonDashboardHarness />);
    try {
      await flushEffects();
      await flushEffects();

      const heading = view.container.querySelector("#comparison-dashboard-heading");
      expect(document.activeElement).toBe(heading);

      const results = await axe(view.container);
      (expect(results) as unknown as AxeMatcher).toHaveNoViolations();

      const closeButton = view.container.querySelector('button[data-testid="comparison-dashboard-close"]');
      if (!(closeButton instanceof HTMLButtonElement)) {
        throw new Error("Close button was not rendered");
      }

      await click(closeButton);
      await flushEffects();

      expect(document.activeElement).toBe(document.getElementById("compare-selected-projects-button"));
    } finally {
      await view.unmount();
    }
  }, 30000);
});
