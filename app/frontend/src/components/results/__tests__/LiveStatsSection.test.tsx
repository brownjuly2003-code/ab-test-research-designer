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
      always_valid: {
        status: "ok",
        always_valid_p_value: 0.0123,
        confidence_level: 0.95,
        ci_sequence_lower: 0.4,
        ci_sequence_upper: 3.6,
        is_significant: true,
        mixture_variance: 0.000025,
        note: "Anytime-valid mSPRT view over the observed difference."
      },
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
  },
  stratified: {
    status: "unavailable",
    note: "Post-stratification needs a per-user stratum."
  }
};

const cupedAvailableResponse = {
  ...liveStatsResponse,
  metric_type: "continuous",
  primary_metric_name: "aov",
  cuped: {
    status: "available",
    note: "CUPED-adjusted estimates over users with a pre-period covariate.",
    theta: 8.5,
    variance_reduction_pct: 81.43,
    covariate_users_total: 12,
    exposed_users_total: 12,
    comparisons: [
      {
        treatment_index: 1,
        status: "ok",
        control: {
          variation_index: 0,
          covariate_users: 6,
          unadjusted_mean: 25.0,
          adjusted_mean: 25.0,
          adjusted_std: 3.9
        },
        treatment: {
          variation_index: 1,
          covariate_users: 6,
          unadjusted_mean: 32.5,
          adjusted_mean: 32.5,
          adjusted_std: 1.44
        },
        analysis: {
          metric_type: "continuous",
          observed_effect: 7.5,
          observed_effect_relative: 30.0,
          control_rate: 25.0,
          treatment_rate: 32.5,
          ci_lower: 4.0,
          ci_upper: 11.0,
          ci_level: 0.95,
          p_value: 0.002,
          test_statistic: 4.1,
          is_significant: true,
          power_achieved: 0.95,
          verdict: "Significant adjusted uplift",
          interpretation: "Treatment beats control after CUPED."
        },
        note: null
      }
    ]
  }
};

const ratioResponse = {
  ...liveStatsResponse,
  metric_type: "ratio",
  primary_metric_name: "ctr",
  comparisons: [
    {
      treatment_index: 1,
      status: "ok",
      control: { variation_index: 0, exposed_users: 500, converted_users: 0, ratio: 0.2 },
      treatment: { variation_index: 1, exposed_users: 500, converted_users: 0, ratio: 0.3 },
      analysis: {
        metric_type: "ratio",
        observed_effect: 0.1,
        observed_effect_relative: 50.0,
        control_rate: null,
        treatment_rate: null,
        ci_lower: 0.05,
        ci_upper: 0.15,
        ci_level: 0.95,
        p_value: 0.0009,
        test_statistic: 3.3,
        is_significant: true,
        power_achieved: 0.92,
        verdict: "Statistically significant uplift",
        interpretation: "Treatment ratio beats control."
      },
      probability_treatment_beats_control: null,
      sequential_significant: null,
      always_valid: {
        status: "ok",
        always_valid_p_value: 0.01,
        confidence_level: 0.95,
        ci_sequence_lower: 0.02,
        ci_sequence_upper: 0.18,
        is_significant: true,
        mixture_variance: 0.0001,
        note: "Anytime-valid mSPRT view."
      },
      note: null
    }
  ],
  cuped: {
    status: "not_applicable",
    note: "Live CUPED applies to continuous metrics."
  }
};

const stratifiedAvailableResponse = {
  ...liveStatsResponse,
  stratified: {
    status: "available",
    note: "Post-stratified estimate over exposed users that carry a stratum.",
    num_strata: 2,
    stratified_users_total: 400,
    exposed_users_total: 420,
    comparisons: [
      {
        treatment_index: 1,
        status: "ok",
        effect: 0.08,
        standard_error: 0.02,
        test_statistic: 4.0,
        p_value: 0.0001,
        ci_lower: 0.04,
        ci_upper: 0.12,
        ci_level: 0.95,
        is_significant: true,
        variance_reduction_pct: 23.5,
        num_strata: 2,
        strata: [
          { stratum: "ios", users: 200, control_users: 100, treatment_users: 100, effect: 0.1 },
          { stratum: "android", users: 200, control_users: 100, treatment_users: 100, effect: 0.06 }
        ],
        note: null
      }
    ]
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

  it("renders the anytime-valid (mSPRT) block for a comparison", async () => {
    const fetchMock = vi.fn(async (..._args: unknown[]) => ({ ok: true, json: async () => liveStatsResponse }));
    vi.stubGlobal("fetch", fetchMock);

    const view = await renderIntoDocument(<LiveStatsSection />);
    try {
      await flushEffects();
      await click(findButton(view.container, "Refresh live stats"));
      await flushEffects();
      await flushEffects();

      const text = view.container.textContent ?? "";
      expect(text).toContain("Anytime-valid"); // block label
      expect(text).toContain("Significant at any look"); // is_significant verdict
      expect(text).toContain("Always-valid p ="); // p-value + confidence sequence line
      expect(text).toContain("continuous monitoring"); // localized hint
    } finally {
      await view.unmount();
    }
  });

  it("renders the CUPED variance-reduction block when a covariate is available", async () => {
    const fetchMock = vi.fn(async (..._args: unknown[]) => ({ ok: true, json: async () => cupedAvailableResponse }));
    vi.stubGlobal("fetch", fetchMock);

    const view = await renderIntoDocument(<LiveStatsSection />);
    try {
      await flushEffects();
      await click(findButton(view.container, "Refresh live stats"));
      await flushEffects();
      await flushEffects();

      const text = view.container.textContent ?? "";
      expect(text).toContain("variance reduction"); // cupedReduction line
      expect(text).toContain("pre-period covariate"); // cupedCoverage line
      expect(text).toContain("adjusted mean"); // cupedArmLine
      expect(text).toContain("Adjusted effect"); // cupedAdjustedEffect line
    } finally {
      await view.unmount();
    }
  });

  it("lists each covariate's coefficient when CUPED uses multiple covariates", async () => {
    const multiResponse = {
      ...cupedAvailableResponse,
      cuped: {
        ...cupedAvailableResponse.cuped,
        theta: null,
        num_covariates: 2,
        covariates: [
          { name: "spend", theta: 3.2 },
          { name: "visits", theta: 1.6 }
        ]
      }
    };
    const fetchMock = vi.fn(async (..._args: unknown[]) => ({ ok: true, json: async () => multiResponse }));
    vi.stubGlobal("fetch", fetchMock);

    const view = await renderIntoDocument(<LiveStatsSection />);
    try {
      await flushEffects();
      await click(findButton(view.container, "Refresh live stats"));
      await flushEffects();
      await flushEffects();

      const text = view.container.textContent ?? "";
      expect(text).toContain("2 covariates"); // cupedReductionMulti line
      expect(text).toContain("spend"); // per-covariate coefficient line
      expect(text).toContain("visits");
    } finally {
      await view.unmount();
    }
  });

  it("renders ratio arms and the delta-method comparison", async () => {
    const fetchMock = vi.fn(async (..._args: unknown[]) => ({ ok: true, json: async () => ratioResponse }));
    vi.stubGlobal("fetch", fetchMock);

    const view = await renderIntoDocument(<LiveStatsSection />);
    try {
      await flushEffects();
      await click(findButton(view.container, "Refresh live stats"));
      await flushEffects();
      await flushEffects();

      const text = view.container.textContent ?? "";
      expect(text).toContain("ratio 0.2000"); // control arm ratio R̂
      expect(text).toContain("ratio 0.3000"); // treatment arm ratio R̂
      expect(text).toContain("Significant");
      expect(text).toContain("Effect 0.1000"); // delta-method ratio difference
      // Bayesian P(B>A) is not shown for ratio metrics.
      expect(text).not.toContain("P(treatment beats control)");
    } finally {
      await view.unmount();
    }
  });

  it("renders the post-stratification block with per-stratum effects", async () => {
    const fetchMock = vi.fn(async (..._args: unknown[]) => ({
      ok: true,
      json: async () => stratifiedAvailableResponse
    }));
    vi.stubGlobal("fetch", fetchMock);

    const view = await renderIntoDocument(<LiveStatsSection />);
    try {
      await flushEffects();
      await click(findButton(view.container, "Refresh live stats"));
      await flushEffects();
      await flushEffects();

      const text = view.container.textContent ?? "";
      expect(text).toContain("Post-stratification"); // block title
      expect(text).toContain("Post-stratified effect"); // stratifiedEffect line
      expect(text).toContain("Variance reduction"); // stratifiedReduction line
      expect(text).toContain("ios"); // per-stratum breakdown
      expect(text).toContain("android");
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
