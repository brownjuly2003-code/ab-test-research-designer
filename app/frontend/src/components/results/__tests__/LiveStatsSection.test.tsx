// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import LiveStatsSection from "../LiveStatsSection";
import { click, findButton, flushEffects, renderIntoDocument } from "../../../test/dom";
import { resetResultsStores, seedResultsStores } from "./resultsTestUtils";
import { useAnalysisStore } from "../../../stores/analysisStore";
import { useProjectStore } from "../../../stores/projectStore";

const liveStatsResponse = {
  experiment_id: "p-1",
  metric_type: "binary",
  primary_metric_name: "purchase_conversion",
  exposures_total: 10000,
  conversions_total: 1100,
  disclaimer: "MVP execution layer — a full plan -> run -> analyze cycle demonstration.",
  srm: {
    status: "ok",
    chi_square: 1.0,
    p_value: 0.32,
    is_srm: false,
    observed_counts: [5000, 5000],
    expected_counts: [5000, 5000],
    verdict: "No sample-ratio mismatch; traffic split matches the design."
  },
  comparisons: [
    {
      treatment_index: 1,
      status: "ok",
      control: { variation_index: 0, exposed_users: 5000, converted_users: 500, conversion_rate: 0.1 },
      treatment: { variation_index: 1, exposed_users: 5000, converted_users: 600, conversion_rate: 0.12 },
      analysis: {
        metric_type: "binary",
        observed_effect: 2.0,
        observed_effect_relative: 20.0,
        control_rate: 10.0,
        treatment_rate: 12.0,
        ci_lower: 0.8,
        ci_upper: 3.2,
        ci_level: 0.95,
        p_value: 0.0014,
        test_statistic: 3.2,
        is_significant: true,
        power_achieved: 0.9,
        verdict: "Statistically significant uplift",
        interpretation: "Treatment beats control."
      },
      probability_treatment_beats_control: 0.9996,
      sequential_significant: false,
      note: null
    }
  ],
  sequential: {
    status: "active",
    n_looks: 3,
    planned_sample_size_per_variant: 58919,
    total_exposed: 10000,
    information_fraction: 0.0849,
    current_boundary_z: 6.881,
    note: "O'Brien-Fleming sequential boundary at the current information fraction."
  },
  cuped: {
    status: "unavailable",
    note: "CUPED needs a per-user pre-experiment covariate, which the MVP does not ingest."
  }
};

describe("LiveStatsSection", () => {
  beforeEach(() => {
    resetResultsStores();
    seedResultsStores();
  });

  afterEach(() => {
    resetResultsStores();
    vi.unstubAllGlobals();
  });

  it("renders the refresh control for a saved experiment", async () => {
    const view = await renderIntoDocument(<LiveStatsSection />);
    try {
      await flushEffects();
      expect(view.container.textContent).toContain("Live experiment results");
      expect(findButton(view.container, "Refresh live stats")).not.toBeNull();
    } finally {
      await view.unmount();
    }
  });

  it("fetches live stats and renders SRM + comparison", async () => {
    const fetchMock = vi.fn(async (..._args: unknown[]) => ({ ok: true, json: async () => liveStatsResponse }));
    vi.stubGlobal("fetch", fetchMock);

    const view = await renderIntoDocument(<LiveStatsSection />);
    try {
      await flushEffects();
      await click(findButton(view.container, "Refresh live stats"));
      await flushEffects();
      await flushEffects();

      expect(fetchMock).toHaveBeenCalledTimes(1);
      const requestedUrl = String(fetchMock.mock.calls[0]?.[0]);
      expect(requestedUrl).toContain("/api/v1/experiments/p-1/live-stats");

      const text = view.container.textContent ?? "";
      expect(text).toContain("Balanced"); // SRM ok label
      expect(text).toContain("Treatment vs Control"); // comparison title
      expect(text).toContain("Significant");
      expect(text).toContain("P(treatment beats control)");
      expect(text).toContain("CUPED");
    } finally {
      await view.unmount();
    }
  });

  it("shows an empty state when no exposures are recorded yet", async () => {
    const empty = { ...liveStatsResponse, exposures_total: 0, conversions_total: 0, comparisons: [] };
    const fetchMock = vi.fn(async (..._args: unknown[]) => ({ ok: true, json: async () => empty }));
    vi.stubGlobal("fetch", fetchMock);

    const view = await renderIntoDocument(<LiveStatsSection />);
    try {
      await flushEffects();
      await click(findButton(view.container, "Refresh live stats"));
      await flushEffects();
      await flushEffects();

      expect(view.container.textContent).toContain("No exposures recorded yet");
    } finally {
      await view.unmount();
    }
  });

  it("shows the save-first hint when no experiment is saved", async () => {
    useAnalysisStore.setState({ ...useAnalysisStore.getState(), resultsProjectId: null });
    useProjectStore.setState({
      ...useProjectStore.getState(),
      activeProjectId: null,
      activeProject: null,
      selectedHistoryRun: null
    });

    const view = await renderIntoDocument(<LiveStatsSection />);
    try {
      await flushEffects();
      expect(view.container.textContent).toContain("Save this experiment first");
    } finally {
      await view.unmount();
    }
  });
});
