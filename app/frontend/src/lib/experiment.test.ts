import { describe, expect, it } from "vitest";

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
    state.metrics.guardrail_metrics = "payment_error_rate";

    const payload = buildApiPayload(state);

    expect(payload.setup.traffic_split).toEqual([60, 40]);
    expect(payload.metrics.std_dev).toBeNull();
    expect(payload.metrics.secondary_metrics).toEqual(["add_to_cart_rate", "checkout_start_rate"]);
    expect(payload.metrics.guardrail_metrics).toEqual(["payment_error_rate"]);
  });

  it("builds calculation payload from the normalized state", () => {
    const state = cloneInitialState();
    state.setup.traffic_split = "70,30";

    const payload = buildCalculationPayload(state);

    expect(payload.traffic_split).toEqual([70, 30]);
    expect(payload.metric_type).toBe("binary");
    expect(payload.long_test_possible).toBe(true);
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
    expect(hydrated.metrics.guardrail_metrics).toBe("payment_error_rate, refund_rate");
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

  it("rejects malformed imported draft json", () => {
    expect(() => parseImportedDraft("{bad json")).toThrow("Draft JSON is invalid.");
    expect(() => parseImportedDraft(JSON.stringify({ nope: true }))).toThrow(
      "Imported JSON does not match the experiment payload format."
    );
  });

  it("builds review sections with formatted values and required constraint fields", () => {
    const sections = getReviewSections(cloneInitialState());
    const constraints = sections.find((section) => section.title === "Constraints");

    expect(constraints?.items).toEqual(
      expect.arrayContaining([
        { label: "Seasonality present", value: "Yes" },
        { label: "Legal / ethics constraints", value: "none" },
        { label: "Deadline pressure", value: "medium" }
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

  it("accepts the default initial state as valid", () => {
    expect(validateForm(cloneInitialState())).toEqual([]);
  });
});
