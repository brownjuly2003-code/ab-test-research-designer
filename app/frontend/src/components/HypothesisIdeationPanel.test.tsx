// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({ requestHypotheses: vi.fn() }));

import { requestHypotheses, type HypothesisCandidate } from "../lib/api";
import HypothesisIdeationPanel from "./HypothesisIdeationPanel";
import { cloneInitialState } from "../lib/experiment";
import { click, findButton, flushEffects, renderIntoDocument } from "../test/dom";

describe("HypothesisIdeationPanel", () => {
  beforeEach(() => {
    vi.mocked(requestHypotheses).mockReset();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("generates candidates and applies the chosen one", async () => {
    vi.mocked(requestHypotheses).mockResolvedValue({
      available: true,
      provider: "local_orchestrator",
      model: "Claude Sonnet 4.6",
      hypotheses: [
        {
          change: "One-page checkout",
          rationale: "Fewer steps reduce drop-off",
          primary_metric: "purchase_conversion",
          expected_direction: "increase"
        }
      ],
      raw_text: "{}",
      error: null,
      error_code: null
    });
    const applied: HypothesisCandidate[] = [];

    const view = await renderIntoDocument(
      <HypothesisIdeationPanel form={cloneInitialState()} onApply={(candidate) => applied.push(candidate)} />
    );

    try {
      await flushEffects();
      await click(findButton(view.container, "Generate hypotheses"));
      await flushEffects();

      expect(vi.mocked(requestHypotheses)).toHaveBeenCalledTimes(1);
      expect(view.container.textContent).toContain("One-page checkout");

      await click(findButton(view.container, "Apply to form"));

      expect(applied).toHaveLength(1);
      expect(applied[0].change).toBe("One-page checkout");
    } finally {
      await view.unmount();
    }
  });

  it("shows an unavailable hint when the model returns no result", async () => {
    vi.mocked(requestHypotheses).mockResolvedValue({
      available: false,
      provider: "local_orchestrator",
      model: "Claude Sonnet 4.6",
      hypotheses: [],
      raw_text: null,
      error: "orchestrator down",
      error_code: "timeout"
    });

    const view = await renderIntoDocument(
      <HypothesisIdeationPanel form={cloneInitialState()} onApply={() => undefined} />
    );

    try {
      await flushEffects();
      await click(findButton(view.container, "Generate hypotheses"));
      await flushEffects();

      expect(view.container.textContent?.toLowerCase()).toContain("unavailable");
    } finally {
      await view.unmount();
    }
  });
});
