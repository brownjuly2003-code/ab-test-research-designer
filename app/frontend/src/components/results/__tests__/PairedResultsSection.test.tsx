// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import PairedResultsSection from "../PairedResultsSection";
import i18n from "../../../i18n";
import { changeValue, click, findButton, flushEffects, renderIntoDocument } from "../../../test/dom";

describe("PairedResultsSection", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the paired-samples form with a test selector", async () => {
    const view = await renderIntoDocument(<PairedResultsSection />);
    try {
      await flushEffects();
      expect(view.container.textContent).toContain("Paired samples");
      expect(view.container.querySelector("select")).not.toBeNull();
      expect(view.container.querySelectorAll("textarea")).toHaveLength(2);
      expect(findButton(view.container, "Run paired test")).toBeTruthy();
    } finally {
      await view.unmount();
    }
  });

  it("posts the parsed paired samples and renders the result", async () => {
    const response = {
      test_type: "paired_t",
      n_pairs: 10,
      effect: 1.7,
      effect_label: "mean difference",
      ci_lower: 1.0214,
      ci_upper: 2.3786,
      ci_level: 0.95,
      p_value: 0.000307,
      test_statistic: 5.6667,
      is_significant: true,
      effect_size: 1.792,
      effect_size_label: "Cohen's dz",
      method: null,
      n_zero_differences: null,
      n_discordant: null,
      discordant_positive: null,
      discordant_negative: null,
      verdict: "Statistically significant uplift at alpha=0.050",
      interpretation: "Treatment mean 13.1000 vs control 11.4000..."
    };
    const fetchMock = vi.fn(async (..._args: unknown[]) => ({ ok: true, json: async () => response }));
    vi.stubGlobal("fetch", fetchMock);

    const view = await renderIntoDocument(<PairedResultsSection />);
    try {
      await flushEffects();
      const textareas = view.container.querySelectorAll("textarea");
      await changeValue(textareas[0] as HTMLTextAreaElement, "10 12 9 15 11 14 8 13 10 12");
      await changeValue(textareas[1] as HTMLTextAreaElement, "12 15 10 16 13 14 11 15 12 13");

      await click(findButton(view.container, "Run paired test"));
      await flushEffects();

      expect(fetchMock).toHaveBeenCalledTimes(1);
      const [url, requestInit] = fetchMock.mock.calls[0] as [string, RequestInit];
      expect(String(url)).toContain("/api/v1/results/paired");
      const body = JSON.parse(String(requestInit.body));
      expect(body.test_type).toBe("paired_t");
      expect(body.control_values).toHaveLength(10);
      expect(body.treatment_values).toHaveLength(10);
      expect(body.alpha).toBe(0.05);

      expect(view.container.textContent).toContain("Statistically significant uplift");
      expect(view.container.textContent).toContain("mean difference");
      expect(view.container.textContent).toContain("Cohen's dz");
    } finally {
      await view.unmount();
    }
  });

  it("shows a length-mismatch hint and does not call the API", async () => {
    const fetchMock = vi.fn(async (..._args: unknown[]) => ({ ok: true, json: async () => ({}) }));
    vi.stubGlobal("fetch", fetchMock);

    const view = await renderIntoDocument(<PairedResultsSection />);
    try {
      await flushEffects();
      const textareas = view.container.querySelectorAll("textarea");
      await changeValue(textareas[0] as HTMLTextAreaElement, "1 2 3");
      await changeValue(textareas[1] as HTMLTextAreaElement, "1 2");

      await click(findButton(view.container, "Run paired test"));
      await flushEffects();

      expect(fetchMock).not.toHaveBeenCalled();
      expect(view.container.textContent).toContain("same number of paired values");
    } finally {
      await view.unmount();
    }
  });
});
