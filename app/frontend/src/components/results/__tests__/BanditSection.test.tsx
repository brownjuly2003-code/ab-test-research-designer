// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import BanditSection from "../BanditSection";
import { click, findButton, flushEffects, renderIntoDocument } from "../../../test/dom";
import { buildAnalysisResult, resetResultsStores, seedResultsStores } from "./resultsTestUtils";

const banditResponse = {
  arm_allocation: [0.18, 0.82],
  best_arm_index: 1,
  best_arm_allocation: 0.82,
  probability_best_arm: 0.95,
  final_bandit_regret: 4.2,
  final_uniform_regret: 21,
  regret_curve: [
    { step: 1, bandit_cumulative_regret: 0.02, uniform_cumulative_regret: 0.03 },
    { step: 2000, bandit_cumulative_regret: 4.2, uniform_cumulative_regret: 21 }
  ],
  num_simulations: 400,
  horizon: 2000
};

describe("BanditSection", () => {
  beforeEach(() => {
    resetResultsStores();
    seedResultsStores();
  });

  afterEach(() => {
    resetResultsStores();
    vi.unstubAllGlobals();
  });

  it("renders the simulation form for binary metrics", async () => {
    const view = await renderIntoDocument(<BanditSection />);
    try {
      await flushEffects();

      expect(view.container.textContent).toContain("Bandit vs fixed split");
      expect(view.container.textContent).toContain("Control conversion (%)");
      expect(view.container.textContent).toContain("Simulate bandit");
    } finally {
      await view.unmount();
    }
  });

  it("shows the binary-only notice for continuous metrics", async () => {
    resetResultsStores();
    seedResultsStores({ analysis: buildAnalysisResult({ metricType: "continuous" }) });

    const view = await renderIntoDocument(<BanditSection />);
    try {
      await flushEffects();

      expect(view.container.textContent).toContain("binary (conversion) metrics only");
      expect(view.container.textContent).not.toContain("Simulate bandit");
    } finally {
      await view.unmount();
    }
  });

  it("renders allocation and convergence after simulating", async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => banditResponse
    }));
    vi.stubGlobal("fetch", fetchMock);

    const view = await renderIntoDocument(<BanditSection />);
    try {
      await flushEffects();
      await click(findButton(view.container, "Simulate bandit"));
      await flushEffects();
      await flushEffects();
      await flushEffects();

      expect(fetchMock).toHaveBeenCalledTimes(1);
      expect(view.container.textContent).toContain("Bandit concentrates traffic on Treatment");
      expect(view.container.textContent).toContain("Expected traffic allocation");
    } finally {
      await view.unmount();
    }
  });
});
