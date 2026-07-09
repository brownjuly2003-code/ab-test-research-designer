// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RatioResultsSection from "../RatioResultsSection";
import i18n from "../../../i18n";
import { changeValue, click, findButton, flushEffects, renderIntoDocument } from "../../../test/dom";

describe("RatioResultsSection", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the four per-arm pair fields", async () => {
    const view = await renderIntoDocument(<RatioResultsSection />);
    try {
      await flushEffects();
      expect(view.container.textContent).toContain("Ratio metric");
      expect(view.container.querySelectorAll("textarea")).toHaveLength(4);
      expect(findButton(view.container, "Run ratio test")).toBeTruthy();
    } finally {
      await view.unmount();
    }
  });

  it("posts the parsed pairs and renders the delta-method result", async () => {
    const response = {
      metric_type: "ratio",
      observed_effect: 0.10183,
      observed_effect_relative: 23.35,
      control_rate: null,
      treatment_rate: null,
      ci_lower: 0.079005,
      ci_upper: 0.124654,
      ci_level: 0.95,
      p_value: 0.0,
      test_statistic: 8.7443,
      is_significant: true,
      power_achieved: 1.0,
      verdict: "Statistically significant uplift at alpha=0.050",
      interpretation: "Treatment ratio 0.538000 vs control 0.436170..."
    };
    const fetchMock = vi.fn(async (..._args: unknown[]) => ({ ok: true, json: async () => response }));
    const onResultsAnalysisChange = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const view = await renderIntoDocument(<RatioResultsSection onResultsAnalysisChange={onResultsAnalysisChange} />);
    try {
      await flushEffects();
      const textareas = view.container.querySelectorAll("textarea");
      await changeValue(textareas[0] as HTMLTextAreaElement, "1.2 2.1 0.7 3.9");
      await changeValue(textareas[1] as HTMLTextAreaElement, "3 5 2 8");
      await changeValue(textareas[2] as HTMLTextAreaElement, "2.0 3.1 1.4 3.8");
      await changeValue(textareas[3] as HTMLTextAreaElement, "4 6 3 7");

      await click(findButton(view.container, "Run ratio test"));
      await flushEffects();

      expect(fetchMock).toHaveBeenCalledTimes(1);
      const [url, requestInit] = fetchMock.mock.calls[0] as [string, RequestInit];
      expect(String(url)).toContain("/api/v1/results/ratio");
      const body = JSON.parse(String(requestInit.body));
      expect(body.control_arm.numerators).toEqual([1.2, 2.1, 0.7, 3.9]);
      expect(body.control_arm.denominators).toEqual([3, 5, 2, 8]);
      expect(body.treatment_arm.numerators).toEqual([2.0, 3.1, 1.4, 3.8]);
      expect(body.treatment_arm.denominators).toEqual([4, 6, 3, 7]);
      expect(body.alpha).toBe(0.05);

      expect(view.container.textContent).toContain("Statistically significant uplift");
      expect(view.container.textContent).toContain("Ratio difference");
      expect(view.container.textContent).toContain("23.35%");
      expect(onResultsAnalysisChange).toHaveBeenCalledWith(response);
    } finally {
      await view.unmount();
    }
  });

  it("shows a per-arm length-mismatch hint and does not call the API", async () => {
    const fetchMock = vi.fn(async (..._args: unknown[]) => ({ ok: true, json: async () => ({}) }));
    const onResultsAnalysisChange = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const view = await renderIntoDocument(<RatioResultsSection onResultsAnalysisChange={onResultsAnalysisChange} />);
    try {
      await flushEffects();
      const textareas = view.container.querySelectorAll("textarea");
      await changeValue(textareas[0] as HTMLTextAreaElement, "1 2 3");
      await changeValue(textareas[1] as HTMLTextAreaElement, "1 2");
      await changeValue(textareas[2] as HTMLTextAreaElement, "1 2 3");
      await changeValue(textareas[3] as HTMLTextAreaElement, "1 2 3");

      await click(findButton(view.container, "Run ratio test"));
      await flushEffects();

      expect(fetchMock).not.toHaveBeenCalled();
      expect(view.container.textContent).toContain("same number of values");
      expect(onResultsAnalysisChange).toHaveBeenCalledWith(null);
    } finally {
      await view.unmount();
    }
  });
});
