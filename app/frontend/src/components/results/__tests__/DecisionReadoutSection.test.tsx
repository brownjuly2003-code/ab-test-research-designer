// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import DecisionReadoutSection from "../DecisionReadoutSection";
import { click, findButton, flushEffects, renderIntoDocument } from "../../../test/dom";
import { resetResultsStores, seedResultsStores } from "./resultsTestUtils";
import { useAnalysisStore } from "../../../stores/analysisStore";
import { useProjectStore } from "../../../stores/projectStore";

const shipDecision = {
  experiment_id: "p-1",
  verdict: "ship",
  confidence: "high",
  reasons: [
    { code: "significant_win", params: { arm: 1, effect_relative: 20.0, p_value: 0.0014 } },
    { code: "bayesian_win", params: { arm: 1, probability: 0.9996 } }
  ],
  blockers: []
};

const blockedDecision = {
  experiment_id: "p-1",
  verdict: "no_ship",
  confidence: "low",
  reasons: [{ code: "blocked_untrustworthy", params: {} }],
  blockers: [{ code: "srm_mismatch", params: { p_value: 0.0002 } }]
};

const keepRunningDecision = {
  experiment_id: "p-1",
  verdict: "keep_running",
  confidence: "low",
  reasons: [
    { code: "inconclusive_ci", params: { arm: 1 } },
    { code: "info_fraction_incomplete", params: { information_fraction: 0.4 } }
  ],
  blockers: []
};

async function renderWithDecision(decision: unknown) {
  const fetchMock = vi.fn(async (..._args: unknown[]) => ({ ok: true, json: async () => decision }));
  vi.stubGlobal("fetch", fetchMock);
  const view = await renderIntoDocument(<DecisionReadoutSection />);
  await flushEffects();
  await click(findButton(view.container, "Synthesize decision"));
  await flushEffects();
  await flushEffects();
  return { view, fetchMock };
}

describe("DecisionReadoutSection", () => {
  beforeEach(() => {
    resetResultsStores();
    seedResultsStores();
  });

  afterEach(() => {
    resetResultsStores();
    vi.unstubAllGlobals();
  });

  it("renders the synthesize control for a saved experiment", async () => {
    const view = await renderIntoDocument(<DecisionReadoutSection />);
    try {
      await flushEffects();
      expect(view.container.textContent).toContain("Decision readout");
      expect(findButton(view.container, "Synthesize decision")).not.toBeNull();
    } finally {
      await view.unmount();
    }
  });

  it("renders a ship verdict with localized win reasons resolved to variant names", async () => {
    const { view, fetchMock } = await renderWithDecision(shipDecision);
    try {
      const requestedUrl = String(fetchMock.mock.calls[0]?.[0]);
      expect(requestedUrl).toContain("/api/v1/experiments/p-1/decision");

      const text = view.container.textContent ?? "";
      expect(text).toContain("Ship it");
      expect(text).toContain("Confidence: High");
      // arm index 1 resolves to the seeded "Treatment" variant name; effect formats as +20.00%.
      expect(text).toContain("Treatment is a significant winner (+20.00% relative effect");
      expect(text).toContain("Treatment beats control with probability 99.96%");
      expect(findButton(view.container, "Copy as Markdown")).not.toBeNull();
    } finally {
      await view.unmount();
    }
  });

  it("surfaces a blocker prominently and forces a no-ship verdict", async () => {
    const { view } = await renderWithDecision(blockedDecision);
    try {
      const text = view.container.textContent ?? "";
      expect(text).toContain("Don't ship");
      expect(text).toContain("Blockers");
      expect(text).toContain("Sample-ratio mismatch (p=0.0002)");
    } finally {
      await view.unmount();
    }
  });

  it("renders a keep-running verdict with an information-fraction reason", async () => {
    const { view } = await renderWithDecision(keepRunningDecision);
    try {
      const text = view.container.textContent ?? "";
      expect(text).toContain("Keep running");
      expect(text).toContain("confidence interval still includes zero");
      expect(text).toContain("Only 40.00% of the planned sample");
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

    const view = await renderIntoDocument(<DecisionReadoutSection />);
    try {
      await flushEffects();
      expect(view.container.textContent).toContain("Save this experiment first");
    } finally {
      await view.unmount();
    }
  });
});
