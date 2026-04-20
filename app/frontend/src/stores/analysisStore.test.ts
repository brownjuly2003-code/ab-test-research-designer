// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({
  requestAnalysis: vi.fn()
}));

import { cloneInitialState, type AnalysisResponsePayload } from "../lib/experiment";

function buildAnalysisResult(): AnalysisResponsePayload {
  return {
    calculations: {
      calculation_summary: {
        metric_type: "binary",
        baseline_value: 0.042,
        mde_pct: 5,
        mde_absolute: 0.0021,
        alpha: 0.05,
        power: 0.8
      },
      results: {
        sample_size_per_variant: 100,
        total_sample_size: 300,
        effective_daily_traffic: 5000,
        estimated_duration_days: 12
      },
      assumptions: [],
      warnings: []
    },
    report: {
      executive_summary: "Deterministic summary",
      calculations: {
        sample_size_per_variant: 100,
        total_sample_size: 300,
        estimated_duration_days: 12,
        assumptions: []
      },
      experiment_design: {
        variants: [
          { name: "A", description: "current experience" },
          { name: "B", description: "new checkout" }
        ],
        randomization_unit: "user",
        traffic_split: [50, 50],
        target_audience: "new users on web",
        inclusion_criteria: "new users only",
        exclusion_criteria: "internal staff",
        recommended_duration_days: 12,
        stopping_conditions: ["planned duration reached"]
      },
      metrics_plan: {
        primary: ["purchase_conversion"],
        secondary: ["add_to_cart_rate"],
        guardrail: ["payment_error_rate"],
        diagnostic: ["assignment_rate"]
      },
      guardrail_metrics: [
        {
          name: "Payment error rate",
          metric_type: "binary",
          baseline: 2.4,
          detectable_mde_pp: 0.321,
          note: "With N=100 per variant, can detect >= 0.32 pp change at 80% power"
        }
      ],
      risks: {
        statistical: ["No major deterministic warnings identified at this stage."],
        product: ["Expected result depends on the hypothesis."],
        technical: ["legacy event logging"],
        operational: ["tracking quality"]
      },
      recommendations: {
        before_launch: ["Verify tracking"],
        during_test: ["Watch SRM"],
        after_test: ["Segment the result"]
      },
      open_questions: ["Will mobile respond differently?"]
    },
    advice: {
      available: false,
      provider: "offline",
      model: "offline",
      advice: null,
      raw_text: null,
      error: "offline",
      error_code: "request_error"
    }
  };
}

async function loadAnalysisModules() {
  vi.resetModules();
  const api = await import("../lib/api");
  const store = await import("./analysisStore");

  return {
    requestAnalysis: vi.mocked(api.requestAnalysis),
    useAnalysisStore: store.useAnalysisStore
  };
}

describe("analysisStore", () => {
  beforeEach(() => {
    vi.useRealTimers();
  });

  afterEach(() => {
    vi.clearAllMocks();
    vi.useRealTimers();
  });

  it("stores analysis results on a successful run", async () => {
    const { requestAnalysis, useAnalysisStore } = await loadAnalysisModules();
    const result = buildAnalysisResult();
    requestAnalysis.mockResolvedValueOnce(result);

    await useAnalysisStore.getState().runAnalysis(cloneInitialState());

    expect(requestAnalysis).toHaveBeenCalledTimes(1);
    expect(useAnalysisStore.getState().analysisResult).toEqual(result);
    expect(useAnalysisStore.getState().results.calculations?.results.sample_size_per_variant).toBe(100);
    expect(useAnalysisStore.getState().validationErrors).toEqual([]);
  });

  it("stores continuous analysis results and returns deterministic persistable snapshots", async () => {
    const { requestAnalysis, useAnalysisStore } = await loadAnalysisModules();
    const draft = cloneInitialState();
    draft.metrics.metric_type = "continuous";
    draft.metrics.std_dev = 18;

    const result = buildAnalysisResult();
    result.calculations.calculation_summary.metric_type = "continuous";
    result.calculations.calculation_summary.baseline_value = 120;
    result.calculations.calculation_summary.mde_absolute = 6;
    requestAnalysis.mockResolvedValueOnce(result);

    const outcome = await useAnalysisStore.getState().runAnalysis(draft);
    const firstSnapshot = useAnalysisStore.getState().getPersistableAnalysis();
    const secondSnapshot = useAnalysisStore.getState().getPersistableAnalysis(outcome);

    expect(outcome?.calculations.calculation_summary.metric_type).toBe("continuous");
    expect(useAnalysisStore.getState().results.calculations?.calculation_summary.metric_type).toBe(
      "continuous"
    );
    expect(firstSnapshot).toEqual({
      calculations: result.calculations,
      report: result.report,
      advice: result.advice
    });
    expect(firstSnapshot).toEqual(secondSnapshot);
  });

  it("validates the draft before sending the request", async () => {
    const { requestAnalysis, useAnalysisStore } = await loadAnalysisModules();
    const invalidDraft = cloneInitialState();
    invalidDraft.project.project_name = "";

    await useAnalysisStore.getState().runAnalysis(invalidDraft);

    expect(requestAnalysis).not.toHaveBeenCalled();
    expect(useAnalysisStore.getState().validationErrors).toContain("Project name is required.");
  });

  it("invalidates linked results and feedback together", async () => {
    const { requestAnalysis, useAnalysisStore } = await loadAnalysisModules();
    requestAnalysis.mockResolvedValueOnce(buildAnalysisResult());

    await useAnalysisStore.getState().runAnalysis(cloneInitialState());

    useAnalysisStore.getState().linkResultToProject("project-1", "run-1");
    useAnalysisStore.getState().showStatus("Saved");

    expect(useAnalysisStore.getState().resultsProjectId).toBe("project-1");
    expect(useAnalysisStore.getState().resultsAnalysisRunId).toBe("run-1");

    useAnalysisStore.getState().invalidateResults();

    expect(useAnalysisStore.getState().analysisResult).toBeNull();
    expect(useAnalysisStore.getState().resultsProjectId).toBeNull();
    expect(useAnalysisStore.getState().resultsAnalysisRunId).toBeNull();
    expect(useAnalysisStore.getState().statusMessage).toBe("");
    expect(useAnalysisStore.getState().analysisError).toBe("");
  });

  it("clears completed analysis state together with linked project metadata", async () => {
    const { requestAnalysis, useAnalysisStore } = await loadAnalysisModules();
    requestAnalysis.mockResolvedValueOnce(buildAnalysisResult());

    const invalidDraft = cloneInitialState();
    invalidDraft.project.project_name = "";

    await useAnalysisStore.getState().runAnalysis(cloneInitialState());

    useAnalysisStore.getState().linkResultToProject("project-1", "run-1");
    useAnalysisStore.getState().showError("Failed");
    useAnalysisStore.getState().validateDraft(invalidDraft);

    expect(useAnalysisStore.getState().resultsProjectId).toBe("project-1");
    expect(useAnalysisStore.getState().resultsAnalysisRunId).toBe("run-1");
    expect(useAnalysisStore.getState().analysisError).toBe("Failed");
    expect(useAnalysisStore.getState().validationErrors).toContain("Project name is required.");

    useAnalysisStore.getState().clearAnalysis();

    expect(useAnalysisStore.getState().analysisResult).toBeNull();
    expect(useAnalysisStore.getState().resultsProjectId).toBeNull();
    expect(useAnalysisStore.getState().resultsAnalysisRunId).toBeNull();
    expect(useAnalysisStore.getState().analysisError).toBe("");
    expect(useAnalysisStore.getState().statusMessage).toBe("");
    expect(useAnalysisStore.getState().validationErrors).toEqual([]);
  });

  it("aborts an in-flight analysis when clearAnalysis is called", async () => {
    const { requestAnalysis, useAnalysisStore } = await loadAnalysisModules();
    let activeSignal: AbortSignal | undefined;
    requestAnalysis.mockImplementationOnce(async (_payload, options) => {
      activeSignal = options?.signal;

      return await new Promise((_, reject) => {
        activeSignal?.addEventListener(
          "abort",
          () => reject(new DOMException("The operation was aborted.", "AbortError")),
          { once: true }
        );
      });
    });

    const runPromise = useAnalysisStore.getState().runAnalysis(cloneInitialState());
    await Promise.resolve();

    expect(useAnalysisStore.getState().isAnalyzing).toBe(true);
    expect(activeSignal?.aborted).toBe(false);

    useAnalysisStore.getState().clearAnalysis();

    expect(activeSignal?.aborted).toBe(true);
    await expect(runPromise).resolves.toBeNull();
    expect(useAnalysisStore.getState().isAnalyzing).toBe(false);
    expect(useAnalysisStore.getState().analysisResult).toBeNull();
  });

  it("tracks explicit toast types for status and error feedback", async () => {
    const { useAnalysisStore } = await loadAnalysisModules();

    useAnalysisStore.getState().showStatus("Saved", "success");

    expect(useAnalysisStore.getState().statusMessage).toBe("Saved");
    expect(useAnalysisStore.getState().statusToastType).toBe("success");
    expect(useAnalysisStore.getState().analysisError).toBe("");

    useAnalysisStore.getState().showError("Failed", "warning");

    expect(useAnalysisStore.getState().analysisError).toBe("Failed");
    expect(useAnalysisStore.getState().errorToastType).toBe("warning");
    expect(useAnalysisStore.getState().statusMessage).toBe("");
    expect(useAnalysisStore.getState().statusToastType).toBeNull();

    useAnalysisStore.getState().showStatus("Recovered", "info");

    expect(useAnalysisStore.getState().statusMessage).toBe("Recovered");
    expect(useAnalysisStore.getState().statusToastType).toBe("info");
    expect(useAnalysisStore.getState().analysisError).toBe("");
    expect(useAnalysisStore.getState().errorToastType).toBeNull();
  });
});
