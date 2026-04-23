// @vitest-environment jsdom

import "vitest-axe/extend-expect";

vi.mock("recharts", () => import("./recharts-stub"));

vi.mock("../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../lib/api")>("../lib/api");
  return {
    ...actual,
    compareMultipleProjectsRequest: vi.fn(),
    exportComparisonRequest: vi.fn(),
  };
});

import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";
import * as matchers from "vitest-axe/matchers";

import ComparisonDashboard from "../components/ComparisonDashboard";
import { buildMultiProjectComparison } from "../components/results/__tests__/resultsTestUtils";
import { compareMultipleProjectsRequest } from "../lib/api";
import { click, flushEffects, renderIntoDocument } from "./dom";

expect.extend(matchers);

type AxeMatcher = {
  toHaveNoViolations: () => void;
};

const monteCarloComparisonResponse = {
  ...buildMultiProjectComparison(),
  monte_carlo_distribution: {
    "p-1": {
      num_simulations: 10000,
      percentiles: { "5": -0.05, "25": 0.01, "50": 0.03, "75": 0.05, "95": 0.08 },
      probability_uplift_positive: 0.9,
      probability_uplift_above_threshold: {
        "0.01": 0.8,
        "0.02": 0.7,
        "0.03": 0.6,
        "0.04": 0.5,
        "0.05": 0.4,
        "0.06": 0.3,
        "0.07": 0.25,
        "0.08": 0.2,
        "0.09": 0.15,
        "0.10": 0.1
      },
      simulated_uplifts: [-0.02, 0.01, 0.03, 0.04, 0.06]
    },
    "p-2": {
      num_simulations: 10000,
      percentiles: { "5": -0.06, "25": 0.0, "50": 0.02, "75": 0.04, "95": 0.07 },
      probability_uplift_positive: 0.84,
      probability_uplift_above_threshold: {
        "0.01": 0.74,
        "0.02": 0.66,
        "0.03": 0.58,
        "0.04": 0.49,
        "0.05": 0.38,
        "0.06": 0.3,
        "0.07": 0.22,
        "0.08": 0.16,
        "0.09": 0.1,
        "0.10": 0.06
      },
      simulated_uplifts: [-0.03, 0.0, 0.02, 0.03, 0.05]
    },
    "p-3": {
      num_simulations: 10000,
      percentiles: { "5": -0.07, "25": -0.01, "50": 0.01, "75": 0.03, "95": 0.06 },
      probability_uplift_positive: 0.71,
      probability_uplift_above_threshold: {
        "0.01": 0.61,
        "0.02": 0.53,
        "0.03": 0.42,
        "0.04": 0.34,
        "0.05": 0.24,
        "0.06": 0.19,
        "0.07": 0.12,
        "0.08": 0.08,
        "0.09": 0.05,
        "0.10": 0.03
      },
      simulated_uplifts: [-0.04, -0.01, 0.01, 0.02, 0.04]
    }
  }
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

describe("Comparison distribution view accessibility", () => {
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
    vi.mocked(compareMultipleProjectsRequest).mockReset();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("has no axe violations after opening the distribution view", async () => {
    vi.mocked(compareMultipleProjectsRequest).mockResolvedValueOnce(
      monteCarloComparisonResponse as never
    );

    const view = await renderIntoDocument(<ComparisonDashboardHarness />);

    try {
      await flushEffects();
      const toggle = view.container.querySelector('[data-testid="comparison-distribution-toggle"]');
      if (!(toggle instanceof HTMLButtonElement)) {
        throw new Error("Distribution toggle was not rendered");
      }

      await click(toggle);
      await flushEffects();
      await flushEffects();

      const results = await axe(view.container);
      (expect(results) as unknown as AxeMatcher).toHaveNoViolations();
    } finally {
      await view.unmount();
    }
  }, 10000);
});
