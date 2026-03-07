import { describe, expect, it } from "vitest";

import {
  buildApiPayload,
  buildCalculationPayload,
  cloneInitialState,
  hydrateLoadedPayload,
  parseTrafficSplit,
  validateForm
} from "./experiment";

describe("experiment helpers", () => {
  it("parses traffic split from a comma-separated string", () => {
    expect(parseTrafficSplit("50, 30,20")).toEqual([50, 30, 20]);
  });

  it("builds API payload with parsed traffic split and nullable std dev", () => {
    const state = cloneInitialState();
    state.setup.traffic_split = "60,40";
    state.metrics.std_dev = "";

    const payload = buildApiPayload(state);

    expect(payload.setup.traffic_split).toEqual([60, 40]);
    expect(payload.metrics.std_dev).toBeNull();
  });

  it("builds calculation payload from the normalized state", () => {
    const state = cloneInitialState();
    state.setup.traffic_split = "70,30";

    const payload = buildCalculationPayload(state);

    expect(payload.traffic_split).toEqual([70, 30]);
    expect(payload.metric_type).toBe("binary");
    expect(payload.long_test_possible).toBe(true);
  });

  it("hydrates a saved payload back into wizard-friendly string fields", () => {
    const state = cloneInitialState();
    const normalized = buildApiPayload(state);

    const hydrated = hydrateLoadedPayload(normalized);

    expect(hydrated.setup.traffic_split).toBe("50,50");
    expect(hydrated.metrics.std_dev).toBe("");
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
