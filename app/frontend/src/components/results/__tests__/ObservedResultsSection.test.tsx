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
});
