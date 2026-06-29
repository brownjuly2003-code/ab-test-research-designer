// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ObservedResultsSection from "../ObservedResultsSection";
import { changeValue, click, findButton, flushEffects, renderIntoDocument } from "../../../test/dom";
import { buildAnalysisResult, resetResultsStores, seedResultsStores } from "./resultsTestUtils";

describe("ObservedResultsSection", () => {
  beforeEach(() => {
    resetResultsStores();
    seedResultsStores();
  });

  afterEach(() => {
    resetResultsStores();
    vi.unstubAllGlobals();
  });

  it("renders the post-test form for actual results", async () => {
    const view = await renderIntoDocument(<ObservedResultsSection onResultsAnalysisChange={vi.fn()} />);
    try {
      await flushEffects();

      expect(view.container.textContent).toContain("Enter actual experiment results");
      expect(view.container.textContent).toContain("Control conversions");
      expect(view.container.textContent).toContain("Analyze results");
    } finally {
      await view.unmount();
    }
  });

  it("offers the Mann–Whitney test only for continuous plans, not binary", async () => {
    const view = await renderIntoDocument(<ObservedResultsSection onResultsAnalysisChange={vi.fn()} />);
    try {
      await flushEffects();
      // The default seeded plan is binary -> no non-parametric toggle.
      expect(view.container.textContent).not.toContain("Mann–Whitney (non-parametric)");
    } finally {
      await view.unmount();
    }
  });

  it("offers Fisher's exact as the alternative test on a binary plan", async () => {
    const view = await renderIntoDocument(<ObservedResultsSection onResultsAnalysisChange={vi.fn()} />);
    try {
      await flushEffects();
      // The default seeded plan is binary -> the exact small-sample alternative is offered.
      expect(view.container.textContent).toContain("Fisher's exact (small samples)");
      expect(view.container.textContent).not.toContain("Fisher's exact (small samples)Mann");
    } finally {
      await view.unmount();
    }
  });

  it("runs a Fisher's exact analysis from the 2x2 counts on a binary plan", async () => {
    const response = {
      metric_type: "fisher_exact",
      observed_effect: -63.3333,
      observed_effect_relative: -79.17,
      control_rate: 80,
      treatment_rate: 16.6667,
      ci_lower: -90,
      ci_upper: -36,
      ci_level: 0.95,
      p_value: 0.034965,
      test_statistic: 20,
      is_significant: true,
      power_achieved: 0.7,
      verdict: "Statistically significant change at alpha=0.050",
      interpretation: "Fisher's exact two-sided p-value 0.034965; result is statistically significant.",
      effect_size: 20,
      effect_size_label: "odds ratio"
    };
    const fetchMock = vi.fn(async (..._args: unknown[]) => ({ ok: true, json: async () => response }));
    vi.stubGlobal("fetch", fetchMock);

    const view = await renderIntoDocument(<ObservedResultsSection onResultsAnalysisChange={vi.fn()} />);
    try {
      await flushEffects();
      await click(findButton(view.container, "Fisher's exact (small samples)"));
      await flushEffects();

      const byId = (id: string) => view.container.querySelector<HTMLInputElement>(`#${id}`)!;
      await changeValue(byId("results-control-conversions"), "8");
      await changeValue(byId("results-control-users"), "10");
      await changeValue(byId("results-treatment-conversions"), "1");
      await changeValue(byId("results-treatment-users"), "6");

      await click(findButton(view.container, "Analyze results"));
      await flushEffects();

      expect(fetchMock).toHaveBeenCalledTimes(1);
      const [, requestInit] = fetchMock.mock.calls[0] as [string, RequestInit];
      const body = JSON.parse(String(requestInit.body));
      expect(body.metric_type).toBe("fisher_exact");
      expect(body.binary).toEqual({
        control_conversions: 8,
        control_users: 10,
        treatment_conversions: 1,
        treatment_users: 6,
        alpha: 0.05
      });

      // The odds-ratio effect size is surfaced with its label.
      expect(view.container.textContent).toContain("odds ratio");
      expect(view.container.textContent).toContain("Fisher's exact two-sided p-value");
    } finally {
      await view.unmount();
    }
  });

  it("runs a Mann–Whitney analysis from raw samples on a continuous plan", async () => {
    seedResultsStores({ analysis: buildAnalysisResult({ metricType: "continuous" }) });
    const response = {
      metric_type: "mann_whitney",
      observed_effect: 5,
      observed_effect_relative: 90,
      ci_lower: 2,
      ci_upper: 8,
      ci_level: 0.95,
      p_value: 0.005075,
      test_statistic: 2.8022,
      is_significant: true,
      power_achieved: 0.8,
      verdict: "Statistically significant uplift at alpha=0.050",
      interpretation: "Treatment median 10.5000 vs control 5.5000. Mann–Whitney U 87.5.",
      effect_size: 0.75,
      effect_size_label: "rank-biserial correlation"
    };
    const fetchMock = vi.fn(async (..._args: unknown[]) => ({ ok: true, json: async () => response }));
    vi.stubGlobal("fetch", fetchMock);

    const view = await renderIntoDocument(<ObservedResultsSection onResultsAnalysisChange={vi.fn()} />);
    try {
      await flushEffects();
      // Continuous plan -> the test selector is offered; switch to the non-parametric test.
      await click(findButton(view.container, "Mann–Whitney (non-parametric)"));
      await flushEffects();

      const textareas = view.container.querySelectorAll<HTMLTextAreaElement>("textarea");
      expect(textareas.length).toBe(2);
      await changeValue(textareas[0], "1, 2, 3, 4, 5, 6, 7, 8, 9, 10");
      await changeValue(textareas[1], "6 7 8 9 10 11 12 13 14 15");

      await click(findButton(view.container, "Analyze results"));
      await flushEffects();

      expect(fetchMock).toHaveBeenCalledTimes(1);
      const [, requestInit] = fetchMock.mock.calls[0] as [string, RequestInit];
      const body = JSON.parse(String(requestInit.body));
      expect(body.metric_type).toBe("mann_whitney");
      expect(body.ranked.control_values).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
      expect(body.ranked.treatment_values).toEqual([6, 7, 8, 9, 10, 11, 12, 13, 14, 15]);

      // The non-parametric effect size is surfaced.
      expect(view.container.textContent).toContain("rank-biserial correlation");
      expect(view.container.textContent).toContain("Mann–Whitney U 87.5");
    } finally {
      await view.unmount();
    }
  });

  it("runs a Poisson rate analysis from events over exposure on any plan", async () => {
    const response = {
      metric_type: "count",
      observed_effect: 0.15,
      observed_effect_relative: 150,
      ci_lower: 0.034,
      ci_upper: 0.266,
      ci_level: 0.95,
      p_value: 0.016674,
      test_statistic: 2.5,
      is_significant: true,
      power_achieved: 0.7,
      verdict: "Statistically significant change at alpha=0.050",
      interpretation: "Rate ratio 2.5000. Poisson exact two-sided p-value 0.016674; result is statistically significant.",
      effect_size: 2.5,
      effect_size_label: "rate ratio"
    };
    const fetchMock = vi.fn(async (..._args: unknown[]) => ({ ok: true, json: async () => response }));
    vi.stubGlobal("fetch", fetchMock);

    const view = await renderIntoDocument(<ObservedResultsSection onResultsAnalysisChange={vi.fn()} />);
    try {
      await flushEffects();
      // The Poisson rate test is plan-independent: offered even on the default binary plan.
      await click(findButton(view.container, "Rate (Poisson)"));
      await flushEffects();

      const byId = (id: string) => view.container.querySelector<HTMLInputElement>(`#${id}`)!;
      await changeValue(byId("results-control-events"), "10");
      await changeValue(byId("results-control-exposure"), "100");
      await changeValue(byId("results-treatment-events"), "25");
      await changeValue(byId("results-treatment-exposure"), "100");

      await click(findButton(view.container, "Analyze results"));
      await flushEffects();

      expect(fetchMock).toHaveBeenCalledTimes(1);
      const [, requestInit] = fetchMock.mock.calls[0] as [string, RequestInit];
      const body = JSON.parse(String(requestInit.body));
      expect(body.metric_type).toBe("count");
      expect(body.count).toEqual({
        control_events: 10,
        control_exposure: 100,
        treatment_events: 25,
        treatment_exposure: 100,
        alpha: 0.05
      });

      expect(view.container.textContent).toContain("rate ratio");
      expect(view.container.textContent).toContain("Poisson exact two-sided p-value");
    } finally {
      await view.unmount();
    }
  });

  it("offers bootstrap / permutation on a continuous plan but not on a binary plan", async () => {
    const binaryView = await renderIntoDocument(<ObservedResultsSection onResultsAnalysisChange={vi.fn()} />);
    try {
      await flushEffects();
      // The default seeded plan is binary -> the continuous-only resampling test is hidden.
      expect(binaryView.container.textContent).not.toContain("Bootstrap / permutation");
    } finally {
      await binaryView.unmount();
    }

    seedResultsStores({ analysis: buildAnalysisResult({ metricType: "continuous" }) });
    const continuousView = await renderIntoDocument(<ObservedResultsSection onResultsAnalysisChange={vi.fn()} />);
    try {
      await flushEffects();
      expect(continuousView.container.textContent).toContain("Bootstrap / permutation");
    } finally {
      await continuousView.unmount();
    }
  });

  it("runs a bootstrap / permutation analysis from raw samples on a continuous plan", async () => {
    seedResultsStores({ analysis: buildAnalysisResult({ metricType: "continuous" }) });
    const response = {
      metric_type: "bootstrap",
      observed_effect: 6,
      observed_effect_relative: 41.38,
      ci_lower: 1.6,
      ci_upper: 10.4,
      ci_level: 0.95,
      p_value: 0.0095,
      test_statistic: 2.683,
      is_significant: true,
      power_achieved: 0.76,
      verdict: "Statistically significant uplift at alpha=0.050",
      interpretation:
        "Mean difference +6.0000 with 95.0% percentile bootstrap CI [1.6000, 10.4000]. Permutation two-sided p-value 0.009500 over 2000 relabellings; result is statistically significant.",
      effect_size: 0.98,
      effect_size_label: "Cohen's d"
    };
    const fetchMock = vi.fn(async (..._args: unknown[]) => ({ ok: true, json: async () => response }));
    vi.stubGlobal("fetch", fetchMock);

    const view = await renderIntoDocument(<ObservedResultsSection onResultsAnalysisChange={vi.fn()} />);
    try {
      await flushEffects();
      // Continuous plan -> switch to the resampling test, which reuses the raw-sample textareas.
      await click(findButton(view.container, "Bootstrap / permutation"));
      await flushEffects();

      const textareas = view.container.querySelectorAll<HTMLTextAreaElement>("textarea");
      expect(textareas.length).toBe(2);
      await changeValue(textareas[0], "1 2 3 4 5 6 7 8 9 10");
      await changeValue(textareas[1], "7 8 9 10 11 12 13 14 15 16");

      await click(findButton(view.container, "Analyze results"));
      await flushEffects();

      expect(fetchMock).toHaveBeenCalledTimes(1);
      const [, requestInit] = fetchMock.mock.calls[0] as [string, RequestInit];
      const body = JSON.parse(String(requestInit.body));
      expect(body.metric_type).toBe("bootstrap");
      expect(body.ranked.control_values).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
      expect(body.ranked.treatment_values).toEqual([7, 8, 9, 10, 11, 12, 13, 14, 15, 16]);

      // The Cohen's d effect size and the percentile-bootstrap prose are surfaced.
      expect(view.container.textContent).toContain("Cohen's d");
      expect(view.container.textContent).toContain("percentile bootstrap CI");
    } finally {
      await view.unmount();
    }
  });

  it("offers the quantile effect on a continuous plan but not on a binary plan", async () => {
    const binaryView = await renderIntoDocument(<ObservedResultsSection onResultsAnalysisChange={vi.fn()} />);
    try {
      await flushEffects();
      // The default seeded plan is binary -> the continuous-only quantile test is hidden.
      expect(binaryView.container.textContent).not.toContain("Quantile effect");
    } finally {
      await binaryView.unmount();
    }

    seedResultsStores({ analysis: buildAnalysisResult({ metricType: "continuous" }) });
    const continuousView = await renderIntoDocument(<ObservedResultsSection onResultsAnalysisChange={vi.fn()} />);
    try {
      await flushEffects();
      expect(continuousView.container.textContent).toContain("Quantile effect");
    } finally {
      await continuousView.unmount();
    }
  });

  it("runs a quantile analysis from raw samples carrying the chosen quantile", async () => {
    seedResultsStores({ analysis: buildAnalysisResult({ metricType: "continuous" }) });
    const response = {
      metric_type: "quantile",
      observed_effect: 6,
      observed_effect_relative: 100,
      ci_lower: 2.1,
      ci_upper: 9.8,
      ci_level: 0.95,
      p_value: 0.0125,
      test_statistic: 2.4,
      is_significant: true,
      power_achieved: 0.66,
      verdict: "Statistically significant uplift at alpha=0.050",
      interpretation:
        "Treatment P90 quantile 15.0000 vs control 9.0000. Quantile shift +6.0000 with 95.0% percentile bootstrap CI [2.1000, 9.8000]. Permutation two-sided p-value 0.012500 over 2000 relabellings; result is statistically significant."
    };
    const fetchMock = vi.fn(async (..._args: unknown[]) => ({ ok: true, json: async () => response }));
    vi.stubGlobal("fetch", fetchMock);

    const view = await renderIntoDocument(<ObservedResultsSection onResultsAnalysisChange={vi.fn()} />);
    try {
      await flushEffects();
      // Continuous plan -> switch to the quantile test, which reuses the raw-sample textareas plus a
      // quantile input.
      await click(findButton(view.container, "Quantile effect"));
      await flushEffects();

      const textareas = view.container.querySelectorAll<HTMLTextAreaElement>("textarea");
      expect(textareas.length).toBe(2);
      await changeValue(textareas[0], "1 2 3 4 5 6 7 8 9 10");
      await changeValue(textareas[1], "7 8 9 10 11 12 13 14 15 16");
      const quantileInput = view.container.querySelector<HTMLInputElement>("#results-quantile-ranked")!;
      expect(quantileInput).not.toBeNull();
      await changeValue(quantileInput, "0.9");

      await click(findButton(view.container, "Analyze results"));
      await flushEffects();

      expect(fetchMock).toHaveBeenCalledTimes(1);
      const [, requestInit] = fetchMock.mock.calls[0] as [string, RequestInit];
      const body = JSON.parse(String(requestInit.body));
      expect(body.metric_type).toBe("quantile");
      expect(body.ranked.control_values).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
      expect(body.ranked.treatment_values).toEqual([7, 8, 9, 10, 11, 12, 13, 14, 15, 16]);
      expect(body.ranked.quantile).toBe(0.9);

      // The quantile prose is surfaced.
      expect(view.container.textContent).toContain("quantile");
      expect(view.container.textContent).toContain("percentile bootstrap CI");
    } finally {
      await view.unmount();
    }
  });

  it("offers the TOST equivalence test on a continuous plan but not on a binary plan", async () => {
    const binaryView = await renderIntoDocument(<ObservedResultsSection onResultsAnalysisChange={vi.fn()} />);
    try {
      await flushEffects();
      // The default seeded plan is binary -> the continuous-only equivalence test is hidden.
      expect(binaryView.container.textContent).not.toContain("Equivalence (TOST)");
    } finally {
      await binaryView.unmount();
    }

    seedResultsStores({ analysis: buildAnalysisResult({ metricType: "continuous" }) });
    const continuousView = await renderIntoDocument(<ObservedResultsSection onResultsAnalysisChange={vi.fn()} />);
    try {
      await flushEffects();
      expect(continuousView.container.textContent).toContain("Equivalence (TOST)");
    } finally {
      await continuousView.unmount();
    }
  });

  it("runs a TOST equivalence analysis from summary statistics plus a margin", async () => {
    seedResultsStores({ analysis: buildAnalysisResult({ metricType: "continuous" }) });
    const response = {
      metric_type: "equivalence",
      observed_effect: 0.1,
      observed_effect_relative: 1,
      ci_lower: -0.13,
      ci_upper: 0.33,
      ci_level: 0.9,
      p_value: 0.0026,
      test_statistic: -2.83,
      is_significant: true,
      power_achieved: 0.56,
      verdict: "Equivalent within ±0.5000 at alpha=0.050",
      interpretation:
        "Treatment mean 10.1000 vs control 10.0000. Effect +0.1000 tested against an equivalence margin of ±0.5000: equivalence demonstrated. The 90.0% confidence interval [-0.1300, 0.3300] is the TOST decision interval; two one-sided p-value 0.002600."
    };
    const fetchMock = vi.fn(async (..._args: unknown[]) => ({ ok: true, json: async () => response }));
    vi.stubGlobal("fetch", fetchMock);

    const view = await renderIntoDocument(<ObservedResultsSection onResultsAnalysisChange={vi.fn()} />);
    try {
      await flushEffects();
      // Continuous plan -> switch to the equivalence test, which reuses the continuous summary inputs
      // plus an equivalence-margin field.
      await click(findButton(view.container, "Equivalence (TOST)"));
      await flushEffects();

      const setNumber = async (id: string, value: string) => {
        const input = view.container.querySelector<HTMLInputElement>(id)!;
        expect(input).not.toBeNull();
        await changeValue(input, value);
      };
      await setNumber("#results-control-mean", "10");
      await setNumber("#results-control-std", "2");
      await setNumber("#results-control-n", "100");
      await setNumber("#results-treatment-mean", "10.1");
      await setNumber("#results-treatment-std", "2");
      await setNumber("#results-treatment-n", "100");
      await setNumber("#results-equivalence-margin", "0.5");

      await click(findButton(view.container, "Analyze results"));
      await flushEffects();

      expect(fetchMock).toHaveBeenCalledTimes(1);
      const [, requestInit] = fetchMock.mock.calls[0] as [string, RequestInit];
      const body = JSON.parse(String(requestInit.body));
      expect(body.metric_type).toBe("equivalence");
      expect(body.continuous.equivalence_margin).toBe(0.5);
      expect(body.continuous.control_mean).toBe(10);
      expect(body.continuous.treatment_mean).toBe(10.1);

      // The equivalence prose is surfaced.
      expect(view.container.textContent).toContain("equivalence demonstrated");
      expect(view.container.textContent).toContain("TOST decision interval");
    } finally {
      await view.unmount();
    }
  });
});
