import { describe, expect, it } from "vitest";

import {
  buildActualResultsState,
  buildResultsRequest,
  parseSampleValues,
  type ActualResultsState
} from "../observedResultsShared";

function emptyState(): ActualResultsState {
  return buildActualResultsState("continuous", 0.05, null);
}

describe("parseSampleValues", () => {
  it("splits on commas, spaces, semicolons and newlines", () => {
    expect(parseSampleValues("1, 2 3;4\n5")).toEqual([1, 2, 3, 4, 5]);
  });

  it("accepts decimals and negatives", () => {
    expect(parseSampleValues("-1.5 2.25\n-0")).toEqual([-1.5, 2.25, -0]);
  });

  it("rejects fewer than two values", () => {
    expect(parseSampleValues("42")).toBeNull();
    expect(parseSampleValues("   ")).toBeNull();
  });

  it("rejects non-numeric tokens", () => {
    expect(parseSampleValues("1, 2, abc")).toBeNull();
    expect(parseSampleValues("1 2 NaN")).toBeNull();
  });
});

describe("buildResultsRequest (mann_whitney)", () => {
  it("builds a ranked payload from the two raw-sample fields", () => {
    const state = emptyState();
    state.ranked = { control_values: "1 2 3 4", treatment_values: "5,6,7,8", alpha: "0.05" };
    const payload = buildResultsRequest("mann_whitney", state);
    expect(payload).toEqual({
      metric_type: "mann_whitney",
      ranked: { control_values: [1, 2, 3, 4], treatment_values: [5, 6, 7, 8], alpha: 0.05 }
    });
  });

  it("returns null when an arm has fewer than two values", () => {
    const state = emptyState();
    state.ranked = { control_values: "1", treatment_values: "5 6 7", alpha: "0.05" };
    expect(buildResultsRequest("mann_whitney", state)).toBeNull();
  });

  it("returns null when an arm exceeds the 1000-value cap", () => {
    const state = emptyState();
    const tooMany = Array.from({ length: 1001 }, (_, index) => String(index)).join(" ");
    state.ranked = { control_values: tooMany, treatment_values: "5 6", alpha: "0.05" };
    expect(buildResultsRequest("mann_whitney", state)).toBeNull();
  });

  it("returns null when alpha is out of range", () => {
    const state = emptyState();
    state.ranked = { control_values: "1 2 3", treatment_values: "4 5 6", alpha: "0.5" };
    expect(buildResultsRequest("mann_whitney", state)).toBeNull();
  });
});

describe("buildResultsRequest (bootstrap)", () => {
  it("reuses the ranked raw-sample input and tags the payload as bootstrap", () => {
    const state = emptyState();
    state.ranked = { control_values: "1 2 3 4", treatment_values: "5,6,7,8", alpha: "0.05" };
    const payload = buildResultsRequest("bootstrap", state);
    expect(payload).toEqual({
      metric_type: "bootstrap",
      ranked: { control_values: [1, 2, 3, 4], treatment_values: [5, 6, 7, 8], alpha: 0.05 }
    });
  });

  it("applies the same ranked validation as mann_whitney (min two values per arm)", () => {
    const state = emptyState();
    state.ranked = { control_values: "1", treatment_values: "5 6 7", alpha: "0.05" };
    expect(buildResultsRequest("bootstrap", state)).toBeNull();
  });

  it("restores a saved bootstrap request into the ranked form", () => {
    const restored = buildActualResultsState("bootstrap", 0.05, {
      metric_type: "bootstrap",
      ranked: { control_values: [1, 2, 3], treatment_values: [4, 5, 6], alpha: 0.01 }
    });
    expect(restored.ranked).toEqual({
      control_values: "1\n2\n3",
      treatment_values: "4\n5\n6",
      alpha: "0.01"
    });
  });
});

describe("buildResultsRequest (fisher_exact)", () => {
  it("reuses the binary 2x2 input and tags the payload as fisher_exact", () => {
    const state = emptyState();
    state.binary = {
      control_conversions: "8",
      control_users: "10",
      treatment_conversions: "1",
      treatment_users: "6",
      alpha: "0.05"
    };
    const payload = buildResultsRequest("fisher_exact", state);
    expect(payload).toEqual({
      metric_type: "fisher_exact",
      binary: {
        control_conversions: 8,
        control_users: 10,
        treatment_conversions: 1,
        treatment_users: 6,
        alpha: 0.05
      }
    });
  });

  it("applies the same binary validation (conversions cannot exceed users)", () => {
    const state = emptyState();
    state.binary = {
      control_conversions: "11",
      control_users: "10",
      treatment_conversions: "1",
      treatment_users: "6",
      alpha: "0.05"
    };
    expect(buildResultsRequest("fisher_exact", state)).toBeNull();
  });
});

describe("buildResultsRequest (count)", () => {
  it("builds a count payload from events and exposure per arm", () => {
    const state = emptyState();
    state.count = {
      control_events: "10",
      control_exposure: "100",
      treatment_events: "25",
      treatment_exposure: "100",
      alpha: "0.05"
    };
    const payload = buildResultsRequest("count", state);
    expect(payload).toEqual({
      metric_type: "count",
      count: {
        control_events: 10,
        control_exposure: 100,
        treatment_events: 25,
        treatment_exposure: 100,
        alpha: 0.05
      }
    });
  });

  it("rejects non-integer event counts and non-positive exposure", () => {
    const state = emptyState();
    state.count = {
      control_events: "10.5",
      control_exposure: "100",
      treatment_events: "25",
      treatment_exposure: "100",
      alpha: "0.05"
    };
    expect(buildResultsRequest("count", state)).toBeNull();
    state.count = { ...state.count, control_events: "10", control_exposure: "0" };
    expect(buildResultsRequest("count", state)).toBeNull();
  });
});
