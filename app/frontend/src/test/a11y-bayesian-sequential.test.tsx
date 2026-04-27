// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../components/PosteriorPlot", () => ({
  default: function PosteriorPlotMock() {
    return <div data-testid="posterior-plot-mock">Posterior plot</div>;
  }
}));

vi.mock("../components/SequentialBoundaryChart", () => ({
  default: function SequentialBoundaryChartMock() {
    return <div data-testid="sequential-boundary-chart-mock">Sequential boundary chart</div>;
  }
}));

vi.mock("../components/PowerCurveChart", () => ({
  default: function PowerCurveChartMock() {
    return <div>Power curve chart</div>;
  }
}));

import ResultsPanel from "../components/ResultsPanel";
import {
  buildAnalysisResult,
  defaultSensitivityData,
  resetResultsStores,
  seedResultsStores
} from "../components/results/__tests__/resultsTestUtils";
import { cloneInitialState } from "../lib/experiment";
import { useDraftStore } from "../stores/draftStore";
import { flushEffects, renderIntoDocument } from "./dom";

describe("Bayesian and sequential results accessibility", () => {
  beforeEach(() => {
    document.documentElement.lang = "en";
    resetResultsStores();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        json: async () => defaultSensitivityData,
        blob: async () => new Blob(["report"], { type: "text/html" }),
        headers: new Headers()
      }))
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    resetResultsStores();
  });

  it("renders BayesianSection with PosteriorPlot in bayesian mode", async () => {
    const analysis = buildAnalysisResult({ metricType: "continuous" });
    analysis.calculations.bayesian_note =
      "Bayesian estimate: N=10,800 per variant gives a 95% credible interval half-width <= 1 units.";
    const draft = cloneInitialState();
    draft.constraints.analysis_mode = "bayesian";
    draft.constraints.desired_precision = 1;
    draft.constraints.credibility = 0.95;

    useDraftStore.setState({
      ...useDraftStore.getState(),
      draft
    });
    seedResultsStores({ analysis, selectedHistoryRunId: "run-1" });

    const view = await renderIntoDocument(<ResultsPanel />);

    try {
      await flushEffects();
      await flushEffects();

      expect(view.container.querySelector('[data-testid="posterior-plot-mock"]')).not.toBeNull();
    } finally {
      await view.unmount();
    }
  }, 15000);

  it("renders SequentialBoundaryChart when sequential boundaries are available", async () => {
    const analysis = buildAnalysisResult({ metricType: "binary" });
    analysis.calculations.sequential_boundaries = [
      { look: 1, info_fraction: 0.25, cumulative_alpha_spent: 0.0008, z_boundary: 3.8, is_final: false },
      { look: 2, info_fraction: 0.5, cumulative_alpha_spent: 0.0045, z_boundary: 3.1, is_final: false },
      { look: 3, info_fraction: 0.75, cumulative_alpha_spent: 0.017, z_boundary: 2.5, is_final: false },
      { look: 4, info_fraction: 1, cumulative_alpha_spent: 0.05, z_boundary: 2.02, is_final: true }
    ];
    analysis.calculations.sequential_adjusted_sample_size = 420;
    analysis.calculations.sequential_inflation_factor = 1.05;
    seedResultsStores({ analysis, selectedHistoryRunId: "run-1" });

    const view = await renderIntoDocument(<ResultsPanel />);

    try {
      await flushEffects();
      await flushEffects();

      expect(view.container.querySelector('[data-testid="sequential-boundary-chart-mock"]')).not.toBeNull();
    } finally {
      await view.unmount();
    }
  }, 15000);
});
