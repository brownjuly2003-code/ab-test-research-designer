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
        baseline_rate: 40
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
        baseline_rate: 2.4
      },
      {
        name: "Refund value",
        metric_type: "continuous",
        baseline_mean: 18,
        std_dev: 6.5
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
