import { describe, expect, it } from "vitest";

import sampleProject from "../fixtures/sample-project.json";

import {
  buildDraftTransferFile,
  buildApiPayload,
  buildCalculationPayload,
  cloneInitialState,
  getReviewSections,
  hydrateLoadedPayload,
  parseImportedDraft,
  parseMetricList,
  parseTrafficSplit,
  setSectionFieldValue,
  validateField,
  validateForm
} from "./experiment";

describe("experiment helpers", () => {
  it("parses traffic split from a comma-separated string", () => {
    expect(parseTrafficSplit("50, 30,20")).toEqual([50, 30, 20]);
  });

  it("parses optional metric lists from comma-separated strings", () => {
    expect(parseMetricList("add_to_cart_rate, refund_rate , ")).toEqual([
      "add_to_cart_rate",
      "refund_rate"
    ]);
  });

  it("builds API payload with parsed traffic split, metric lists, and nullable std dev", () => {
    const state = cloneInitialState();
    state.setup.traffic_split = "60,40";
    state.metrics.std_dev = "";
    state.metrics.secondary_metrics = "add_to_cart_rate, checkout_start_rate";
    state.metrics.guardrail_metrics = [
      {
        name: "Bounce rate",
        metric_type: "binary",
        baseline_rate: 40
      }
    ];

    const payload = buildApiPayload(state);

    expect(payload.setup.traffic_split).toEqual([60, 40]);
    expect(payload.metrics.std_dev).toBeNull();
    expect(payload.metrics.secondary_metrics).toEqual(["add_to_cart_rate", "checkout_start_rate"]);
    expect(payload.metrics.guardrail_metrics).toEqual([
      {
        name: "Bounce rate",
        metric_type: "binary",
        baseline_rate: 40,
        direction: "increase_is_bad"
      }
    ]);
  });

  it("builds calculation payload from the normalized state", () => {
    const state = cloneInitialState();
    state.setup.traffic_split = "70,30";

    const payload = buildCalculationPayload(state);

    expect(payload.traffic_split).toEqual([70, 30]);
    expect(payload.metric_type).toBe("binary");
    expect(payload.long_test_possible).toBe(true);
  });

  it("defaults holdout and mutual-exclusion to null in the calculation payload", () => {
    const payload = buildCalculationPayload(cloneInitialState());

    expect(payload.holdout_fraction).toBeNull();
    expect(payload.mutually_exclusive_experiments).toBeNull();
  });

  it("forwards holdout fraction and mutually exclusive experiments when set", () => {
    const state = cloneInitialState();
    state.constraints.holdout_fraction = 0.1;
    state.constraints.mutually_exclusive_experiments = 3;

    const payload = buildCalculationPayload(state);

    expect(payload.holdout_fraction).toBe(0.1);
    expect(payload.mutually_exclusive_experiments).toBe(3);
  });

  it("accepts an empty holdout / mutual-exclusion as valid", () => {
    expect(validateForm(cloneInitialState())).not.toContain("Holdout fraction must be between 0 and 1.");
  });

  it("flags an out-of-range holdout fraction and a sub-1 experiment count", () => {
    const state = cloneInitialState();
    state.constraints.holdout_fraction = 1;
    state.constraints.mutually_exclusive_experiments = 0;

    const issues = validateForm(state);

    expect(issues).toContain("Holdout fraction must be between 0 and 1.");
    expect(issues).toContain("Mutually exclusive experiments must be an integer of at least 1.");
  });

  it("includes CUPED fields in API and calculation payloads only when the UI toggle is enabled", () => {
    const state = cloneInitialState();
    state.metrics.metric_type = "continuous";
    state.metrics.baseline_value = 45;
    state.metrics.std_dev = 12;
    state.metrics.cuped_pre_experiment_std = 11.8;
    state.metrics.cuped_correlation = 0.5;
    state.metrics.cuped_enabled = true;

    const payload = buildApiPayload(state);
    const calculationPayload = buildCalculationPayload(state);

    expect(payload.metrics.cuped_pre_experiment_std).toBe(11.8);
    expect(payload.metrics.cuped_correlation).toBe(0.5);
    expect("cuped_enabled" in payload.metrics).toBe(false);
    expect(calculationPayload.cuped_pre_experiment_std).toBe(11.8);
    expect(calculationPayload.cuped_correlation).toBe(0.5);
  });

  it("defaults the planned test to z_test in both payloads", () => {
    const payload = buildApiPayload(cloneInitialState());
    const calculationPayload = buildCalculationPayload(cloneInitialState());

    expect(payload.metrics.planned_test).toBe("z_test");
    expect(payload.metrics.equivalence_margin_pct).toBeNull();
    expect(calculationPayload.planned_test).toBe("z_test");
    expect(calculationPayload.equivalence_margin_pct).toBeNull();
  });

  it("carries the equivalence margin only for a TOST plan", () => {
    const state = cloneInitialState();
    state.metrics.metric_type = "continuous";
    state.metrics.baseline_value = 100;
    state.metrics.std_dev = 20;
    state.metrics.planned_test = "tost";
    state.metrics.equivalence_margin_pct = 2;

    const tostPayload = buildCalculationPayload(state);
    expect(tostPayload.planned_test).toBe("tost");
    expect(tostPayload.equivalence_margin_pct).toBe(2);

    // A stale margin left over from a previous TOST selection must not leak into the payload.
    state.metrics.planned_test = "mann_whitney";
    const rankPayload = buildCalculationPayload(state);
    expect(rankPayload.planned_test).toBe("mann_whitney");
    expect(rankPayload.equivalence_margin_pct).toBeNull();
  });

  it("resets the planned test when the metric type changes", () => {
    const state = cloneInitialState();
    state.metrics.metric_type = "continuous";
    state.metrics.planned_test = "mann_whitney";
    state.metrics.equivalence_margin_pct = 2;

    const next = setSectionFieldValue(state, "metrics", "metric_type", "binary");

    expect(next.metrics.planned_test).toBe("z_test");
    expect(next.metrics.equivalence_margin_pct).toBe("");
  });

  it("hydrates legacy payloads without a planned test to the z_test default", () => {
    // The bundled sample project predates planned_test, so importing it exercises the legacy path.
    const hydrated = parseImportedDraft(JSON.stringify(sampleProject));

    expect(hydrated.metrics.planned_test).toBe("z_test");
    expect(hydrated.metrics.equivalence_margin_pct).toBe("");
  });

  it("builds a normalized draft transfer file", () => {
    const state = cloneInitialState();
    state.setup.traffic_split = "60,40";

    const draft = buildDraftTransferFile(state);

    expect(draft.schema_version).toBe(1);
    expect(draft.payload.setup.traffic_split).toEqual([60, 40]);
  });

  it("hydrates a saved payload back into wizard-friendly string fields", () => {
    const state = cloneInitialState();
    const normalized = buildApiPayload(state);

    const hydrated = hydrateLoadedPayload(normalized);

    expect(hydrated.setup.traffic_split).toBe("50,50");
    expect(hydrated.metrics.std_dev).toBe("");
    expect(hydrated.metrics.secondary_metrics).toBe("add_to_cart_rate");
    expect(hydrated.metrics.guardrail_metrics).toEqual([
      {
        name: "Payment error rate",
        metric_type: "binary",
        baseline_rate: 2.4,
        direction: "increase_is_bad",
        non_inferiority_margin_pct: ""
      },
      {
        name: "Refund value",
        metric_type: "continuous",
        baseline_mean: 18,
        std_dev: 6.5,
        direction: "increase_is_bad",
        non_inferiority_margin_pct: ""
      }
    ]);
  });

  it("hydrates persisted CUPED values back into wizard-friendly state and enables the toggle", () => {
    const state: Parameters<typeof buildApiPayload>[0] = {
      ...cloneInitialState(),
      metrics: {
        ...cloneInitialState().metrics,
        metric_type: "continuous",
        baseline_value: 45,
        std_dev: 12,
        cuped_pre_experiment_std: 11.8,
        cuped_correlation: 0.5,
        cuped_enabled: true
      }
    };
    const normalized = buildApiPayload(state);

    const hydrated = hydrateLoadedPayload(normalized);

    expect(hydrated.metrics.cuped_pre_experiment_std).toBe(11.8);
    expect(hydrated.metrics.cuped_correlation).toBe(0.5);
    expect(hydrated.metrics.cuped_enabled).toBe(true);
  });

  it("parses imported draft wrappers and restores wizard-friendly fields", () => {
    const imported = parseImportedDraft(
      JSON.stringify({
        schema_version: 1,
        payload: buildDraftTransferFile(cloneInitialState()).payload
      })
    );

    expect(imported.setup.traffic_split).toBe("50,50");
    expect(imported.metrics.secondary_metrics).toBe("add_to_cart_rate");
  });

  it("does not coerce missing imported CUPED fields to zero", () => {
    const imported = parseImportedDraft(JSON.stringify(sampleProject));
    const payload = buildApiPayload(imported);

    expect(imported.metrics.cuped_enabled).toBe(false);
    expect(imported.metrics.cuped_pre_experiment_std).toBe("");
    expect(imported.metrics.cuped_correlation).toBe("");
    expect(payload.metrics.cuped_pre_experiment_std).toBeNull();
    expect(payload.metrics.cuped_correlation).toBeNull();
  });

  it("rejects malformed imported draft json", () => {
    expect(() => parseImportedDraft("{bad json")).toThrow("Draft JSON is invalid.");
    expect(() => parseImportedDraft(JSON.stringify({ nope: true }))).toThrow(
      "Imported JSON does not match the experiment payload format."
    );
  });

  it("builds review sections with formatted values and required constraint fields", () => {
    const sections = getReviewSections(cloneInitialState());
    const constraints = sections.find((section) => section.title === "Constraints");
    const metrics = sections.find((section) => section.title === "Metrics");

    expect(constraints?.items).toEqual(
      expect.arrayContaining([
        { label: "Seasonality present", value: "Yes" },
        { label: "Legal / ethics constraints", value: "none" },
        { label: "Deadline pressure", value: "medium" }
      ])
    );
    expect(metrics?.items).toEqual(
      expect.arrayContaining([
        {
          label: "Guardrail metrics",
          value: expect.stringContaining("Payment error rate")
        }
      ])
    );
  });

  it("returns validation errors for mismatched variants and missing std dev", () => {
    const state = cloneInitialState();
    state.setup.traffic_split = "50,50";
    state.setup.variants_count = 3;
    state.metrics.metric_type = "continuous";
    state.metrics.std_dev = "";

    const errors = validateForm(state);

    expect(errors).toContain("Traffic split length must match variants count.");
    expect(errors).toContain("Continuous metrics require a positive std dev.");
  });

  it("validates a single field against the current form state", () => {
    const state = cloneInitialState();
    state.metrics.baseline_value = -5;

    expect(validateField(state, "metrics", "baseline_value")).toBe(
      "Binary baseline value must be between 0 and 1."
    );
    expect(validateField(state, "project", "domain")).toBeNull();
  });

  it("accepts the default initial state as valid", () => {
    expect(validateForm(cloneInitialState())).toEqual([]);
  });
});
