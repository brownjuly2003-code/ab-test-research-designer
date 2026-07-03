// @vitest-environment jsdom

import { act } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({
  requestCalculation: vi.fn()
}));

import { requestCalculation } from "../lib/api";
import { cloneInitialState, type FullPayload } from "../lib/experiment";
import { renderIntoDocument, flushEffects } from "../test/dom";
import { useCalculationPreview } from "./useCalculationPreview";

function buildPreview(sampleSizePerVariant = 100, estimatedDurationDays = 12) {
  return {
    calculation_summary: {
      metric_type: "binary" as const,
      baseline_value: 0.042,
      mde_pct: 5,
      mde_absolute: 0.0021,
      alpha: 0.05,
      power: 0.8
    },
    results: {
      sample_size_per_variant: sampleSizePerVariant,
      total_sample_size: sampleSizePerVariant * 2,
      effective_daily_traffic: 5000,
      estimated_duration_days: estimatedDurationDays
    },
    assumptions: [],
    warnings: [],
    bonferroni_note: null
  };
}

function PreviewProbe({ draft, enabled }: { draft: FullPayload; enabled: boolean }) {
  const state = useCalculationPreview(draft, enabled);

  return (
    <div>
      <span data-testid="result">
        {state.result ? String(state.result.results.sample_size_per_variant) : ""}
      </span>
      <span data-testid="error">{state.error ?? ""}</span>
      <span data-testid="loading">{String(state.isLoading)}</span>
    </div>
  );
}

describe("useCalculationPreview", () => {
  beforeEach(() => {
    vi.mocked(requestCalculation).mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it("waits for required fields before requesting a preview", async () => {
    vi.useFakeTimers();
    const invalidDraft = cloneInitialState();
    invalidDraft.setup.expected_daily_traffic = 0;
    vi.mocked(requestCalculation).mockResolvedValueOnce(buildPreview());

    const view = await renderIntoDocument(<PreviewProbe draft={invalidDraft} enabled={true} />);
    try {
      await flushEffects();

      await act(async () => {
        await vi.advanceTimersByTimeAsync(300);
      });
      await flushEffects();

      expect(requestCalculation).not.toHaveBeenCalled();

      const validDraft = cloneInitialState();
      await view.rerender(<PreviewProbe draft={validDraft} enabled={true} />);

      await act(async () => {
        await vi.advanceTimersByTimeAsync(300);
      });
      await flushEffects();

      expect(requestCalculation).toHaveBeenCalledTimes(1);
      expect(view.container.querySelector('[data-testid="result"]')?.textContent).toBe("100");
    } finally {
      await view.unmount();
    }
  });

  it("debounces successive updates and keeps the latest preview result", async () => {
    vi.useFakeTimers();
    vi.mocked(requestCalculation)
      .mockResolvedValueOnce(buildPreview(100, 12))
      .mockResolvedValueOnce(buildPreview(140, 18));

    const view = await renderIntoDocument(<PreviewProbe draft={cloneInitialState()} enabled={true} />);
    try {
      await flushEffects();

      await act(async () => {
        await vi.advanceTimersByTimeAsync(300);
      });
      await flushEffects();

      expect(requestCalculation).toHaveBeenCalledTimes(1);
      expect(view.container.querySelector('[data-testid="result"]')?.textContent).toBe("100");

      const updatedDraft = cloneInitialState();
      updatedDraft.setup.expected_daily_traffic = 24000;
      await view.rerender(<PreviewProbe draft={updatedDraft} enabled={true} />);

      await act(async () => {
        await vi.advanceTimersByTimeAsync(299);
      });
      await flushEffects();

      expect(requestCalculation).toHaveBeenCalledTimes(1);

      await act(async () => {
        await vi.advanceTimersByTimeAsync(1);
      });
      await flushEffects();

      expect(requestCalculation).toHaveBeenCalledTimes(2);
      expect(view.container.querySelector('[data-testid="result"]')?.textContent).toBe("140");
    } finally {
      await view.unmount();
    }
  });

  it("aborts an in-flight preview request as soon as inputs change", async () => {
    vi.useFakeTimers();
    let firstSignal: AbortSignal | undefined;
    vi.mocked(requestCalculation)
      .mockImplementationOnce(async (_payload, options) => {
        firstSignal = options?.signal;

        return await new Promise((_, reject) => {
          firstSignal?.addEventListener(
            "abort",
            () => reject(new DOMException("The operation was aborted.", "AbortError")),
            { once: true }
          );
        });
      })
      .mockResolvedValueOnce(buildPreview(140, 18));

    const view = await renderIntoDocument(<PreviewProbe draft={cloneInitialState()} enabled={true} />);
    try {
      await flushEffects();

      await act(async () => {
        await vi.advanceTimersByTimeAsync(300);
      });
      await flushEffects();

      expect(requestCalculation).toHaveBeenCalledTimes(1);
      expect(firstSignal?.aborted).toBe(false);

      const updatedDraft = cloneInitialState();
      updatedDraft.setup.expected_daily_traffic = 24000;
      await view.rerender(<PreviewProbe draft={updatedDraft} enabled={true} />);
      await flushEffects();

      expect(firstSignal?.aborted).toBe(true);
      expect(requestCalculation).toHaveBeenCalledTimes(1);

      await act(async () => {
        await vi.advanceTimersByTimeAsync(300);
      });
      await flushEffects();

      expect(requestCalculation).toHaveBeenCalledTimes(2);
      expect(view.container.querySelector('[data-testid="result"]')?.textContent).toBe("140");
    } finally {
      await view.unmount();
    }
  });

  it("surfaces a muted preview error when the request fails", async () => {
    vi.useFakeTimers();
    vi.mocked(requestCalculation).mockRejectedValueOnce(new Error("offline"));

    const view = await renderIntoDocument(<PreviewProbe draft={cloneInitialState()} enabled={true} />);
    try {
      await flushEffects();

      await act(async () => {
        await vi.advanceTimersByTimeAsync(300);
      });
      await flushEffects();

      expect(requestCalculation).toHaveBeenCalledTimes(1);
      // the hook exposes an i18n key; LivePreviewPanel translates it at render time
      expect(view.container.querySelector('[data-testid="error"]')?.textContent).toBe("livePreview.error");
    } finally {
      await view.unmount();
    }
  });

  it("forwards CUPED fields in the preview payload when the toggle is enabled", async () => {
    vi.useFakeTimers();
    vi.mocked(requestCalculation).mockResolvedValueOnce(buildPreview(75, 8));

    const draft = cloneInitialState();
    draft.metrics.metric_type = "continuous";
    draft.metrics.baseline_value = 45;
    draft.metrics.std_dev = 12;
    draft.metrics.cuped_pre_experiment_std = 11.8;
    draft.metrics.cuped_correlation = 0.5;
    draft.metrics.cuped_enabled = true;

    const view = await renderIntoDocument(<PreviewProbe draft={draft} enabled={true} />);
    try {
      await flushEffects();

      await act(async () => {
        await vi.advanceTimersByTimeAsync(300);
      });
      await flushEffects();

      expect(requestCalculation).toHaveBeenCalledTimes(1);
      expect(vi.mocked(requestCalculation).mock.calls[0]?.[0]).toMatchObject({
        metric_type: "continuous",
        cuped_pre_experiment_std: 11.8,
        cuped_correlation: 0.5
      });
    } finally {
      await view.unmount();
    }
  });

  it("sizes a ratio metric via the delta-method path once baseline and std_dev are set", async () => {
    vi.useFakeTimers();
    vi.mocked(requestCalculation).mockResolvedValueOnce(buildPreview(20345, 1));

    const incompleteDraft = cloneInitialState();
    incompleteDraft.metrics.metric_type = "ratio";
    incompleteDraft.metrics.baseline_value = 0.05;
    incompleteDraft.metrics.std_dev = "";
    incompleteDraft.metrics.numerator_metric_name = "ad_clicks";
    incompleteDraft.metrics.denominator_metric_name = "ad_impressions";

    const view = await renderIntoDocument(<PreviewProbe draft={incompleteDraft} enabled={true} />);
    try {
      await flushEffects();
      await act(async () => {
        await vi.advanceTimersByTimeAsync(300);
      });
      await flushEffects();

      // Without std_dev a ratio cannot be sized, so no request fires.
      expect(requestCalculation).not.toHaveBeenCalled();

      const validDraft = cloneInitialState();
      validDraft.metrics.metric_type = "ratio";
      validDraft.metrics.baseline_value = 0.05;
      validDraft.metrics.std_dev = 0.09;
      validDraft.metrics.numerator_metric_name = "ad_clicks";
      validDraft.metrics.denominator_metric_name = "ad_impressions";
      await view.rerender(<PreviewProbe draft={validDraft} enabled={true} />);

      await act(async () => {
        await vi.advanceTimersByTimeAsync(300);
      });
      await flushEffects();

      expect(requestCalculation).toHaveBeenCalledTimes(1);
      expect(vi.mocked(requestCalculation).mock.calls[0]?.[0]).toMatchObject({
        metric_type: "ratio",
        baseline_value: 0.05,
        std_dev: 0.09
      });
    } finally {
      await view.unmount();
    }
  });

  it("sizes a count / rate metric from the baseline event rate and per-user exposure", async () => {
    vi.useFakeTimers();
    vi.mocked(requestCalculation).mockResolvedValueOnce(buildPreview(1437, 1));

    const draft = cloneInitialState();
    draft.metrics.metric_type = "count";
    draft.metrics.baseline_value = 0.3;
    draft.metrics.exposure_per_user = 2;

    const view = await renderIntoDocument(<PreviewProbe draft={draft} enabled={true} />);
    try {
      await flushEffects();
      await act(async () => {
        await vi.advanceTimersByTimeAsync(300);
      });
      await flushEffects();

      expect(requestCalculation).toHaveBeenCalledTimes(1);
      expect(vi.mocked(requestCalculation).mock.calls[0]?.[0]).toMatchObject({
        metric_type: "count",
        baseline_value: 0.3,
        exposure_per_user: 2
      });
    } finally {
      await view.unmount();
    }
  });

  it("waits for the equivalence margin before previewing a TOST plan", async () => {
    vi.useFakeTimers();
    vi.mocked(requestCalculation).mockResolvedValueOnce(buildPreview(1713, 30));

    const marginlessDraft = cloneInitialState();
    marginlessDraft.metrics.metric_type = "continuous";
    marginlessDraft.metrics.baseline_value = 100;
    marginlessDraft.metrics.std_dev = 20;
    marginlessDraft.metrics.planned_test = "tost";
    marginlessDraft.metrics.equivalence_margin_pct = "";

    const view = await renderIntoDocument(<PreviewProbe draft={marginlessDraft} enabled={true} />);
    try {
      await flushEffects();
      await act(async () => {
        await vi.advanceTimersByTimeAsync(300);
      });
      await flushEffects();

      // The margin drives a TOST plan; without it the backend would 422, so no request fires.
      expect(requestCalculation).not.toHaveBeenCalled();

      const validDraft = structuredClone(marginlessDraft);
      validDraft.metrics.equivalence_margin_pct = 2;
      await view.rerender(<PreviewProbe draft={validDraft} enabled={true} />);

      await act(async () => {
        await vi.advanceTimersByTimeAsync(300);
      });
      await flushEffects();

      expect(requestCalculation).toHaveBeenCalledTimes(1);
      expect(vi.mocked(requestCalculation).mock.calls[0]?.[0]).toMatchObject({
        metric_type: "continuous",
        planned_test: "tost",
        equivalence_margin_pct: 2
      });
    } finally {
      await view.unmount();
    }
  });

  it("waits for desired precision in bayesian mode and forwards bayesian payload fields", async () => {
    vi.useFakeTimers();
    vi.mocked(requestCalculation).mockResolvedValueOnce(buildPreview(10800, 8));

    const incompleteDraft = cloneInitialState();
    incompleteDraft.constraints.analysis_mode = "bayesian";
    incompleteDraft.constraints.desired_precision = null;

    const view = await renderIntoDocument(<PreviewProbe draft={incompleteDraft} enabled={true} />);
    try {
      await flushEffects();

      await act(async () => {
        await vi.advanceTimersByTimeAsync(300);
      });
      await flushEffects();

      expect(requestCalculation).not.toHaveBeenCalled();

      const validDraft = cloneInitialState();
      validDraft.constraints.analysis_mode = "bayesian";
      validDraft.constraints.desired_precision = 0.5;
      validDraft.constraints.credibility = 0.95;
      await view.rerender(<PreviewProbe draft={validDraft} enabled={true} />);

      await act(async () => {
        await vi.advanceTimersByTimeAsync(300);
      });
      await flushEffects();

      expect(requestCalculation).toHaveBeenCalledTimes(1);
      expect(vi.mocked(requestCalculation).mock.calls[0]?.[0]).toMatchObject({
        analysis_mode: "bayesian",
        desired_precision: 0.5,
        credibility: 0.95
      });
    } finally {
      await view.unmount();
    }
  });
});
