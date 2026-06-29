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
    state.ranked = { control_values: "1 2 3 4", treatment_values: "5,6,7,8", alpha: "0.05", quantile: "0.5" };
    const payload = buildResultsRequest("mann_whitney", state);
    expect(payload).toEqual({
      metric_type: "mann_whitney",
      ranked: { control_values: [1, 2, 3, 4], treatment_values: [5, 6, 7, 8], alpha: 0.05 }
    });
  });

  it("returns null when an arm has fewer than two values", () => {
    const state = emptyState();
    state.ranked = { control_values: "1", treatment_values: "5 6 7", alpha: "0.05", quantile: "0.5" };
    expect(buildResultsRequest("mann_whitney", state)).toBeNull();
  });

  it("returns null when an arm exceeds the 1000-value cap", () => {
    const state = emptyState();
    const tooMany = Array.from({ length: 1001 }, (_, index) => String(index)).join(" ");
    state.ranked = { control_values: tooMany, treatment_values: "5 6", alpha: "0.05", quantile: "0.5" };
    expect(buildResultsRequest("mann_whitney", state)).toBeNull();
  });

  it("returns null when alpha is out of range", () => {
    const state = emptyState();
    state.ranked = { control_values: "1 2 3", treatment_values: "4 5 6", alpha: "0.5", quantile: "0.5" };
    expect(buildResultsRequest("mann_whitney", state)).toBeNull();
  });
});

describe("buildResultsRequest (bootstrap)", () => {
  it("reuses the ranked raw-sample input and tags the payload as bootstrap", () => {
    const state = emptyState();
    state.ranked = { control_values: "1 2 3 4", treatment_values: "5,6,7,8", alpha: "0.05", quantile: "0.5" };
    const payload = buildResultsRequest("bootstrap", state);
    expect(payload).toEqual({
      metric_type: "bootstrap",
      ranked: { control_values: [1, 2, 3, 4], treatment_values: [5, 6, 7, 8], alpha: 0.05 }
    });
  });

  it("applies the same ranked validation as mann_whitney (min two values per arm)", () => {
    const state = emptyState();
    state.ranked = { control_values: "1", treatment_values: "5 6 7", alpha: "0.05", quantile: "0.5" };
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
      alpha: "0.01",
      quantile: "0.5"
    });
  });
});

describe("buildResultsRequest (quantile)", () => {
  it("reuses the ranked raw-sample input and carries the chosen quantile", () => {
    const state = emptyState();
    state.ranked = { control_values: "1 2 3 4", treatment_values: "5,6,7,8", alpha: "0.05", quantile: "0.9" };
    const payload = buildResultsRequest("quantile", state);
    expect(payload).toEqual({
      metric_type: "quantile",
      ranked: { control_values: [1, 2, 3, 4], treatment_values: [5, 6, 7, 8], alpha: 0.05, quantile: 0.9 }
    });
  });

  it("returns null when the quantile is out of the open (0, 1) range", () => {
    const state = emptyState();
    state.ranked = { control_values: "1 2 3", treatment_values: "4 5 6", alpha: "0.05", quantile: "1" };
    expect(buildResultsRequest("quantile", state)).toBeNull();
    state.ranked = { ...state.ranked, quantile: "0" };
    expect(buildResultsRequest("quantile", state)).toBeNull();
    state.ranked = { ...state.ranked, quantile: "" };
    expect(buildResultsRequest("quantile", state)).toBeNull();
  });

  it("applies the same ranked validation as mann_whitney (min two values per arm)", () => {
    const state = emptyState();
    state.ranked = { control_values: "1", treatment_values: "5 6 7", alpha: "0.05", quantile: "0.5" };
    expect(buildResultsRequest("quantile", state)).toBeNull();
  });

  it("restores a saved quantile request into the ranked form with its quantile", () => {
    const restored = buildActualResultsState("quantile", 0.05, {
      metric_type: "quantile",
      ranked: { control_values: [1, 2, 3], treatment_values: [4, 5, 6], alpha: 0.01, quantile: 0.9 }
    });
    expect(restored.ranked).toEqual({
      control_values: "1\n2\n3",
      treatment_values: "4\n5\n6",
      alpha: "0.01",
      quantile: "0.9"
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

describe("buildResultsRequest (equivalence)", () => {
  const continuousForm = {
    control_mean: "10",
    control_std: "2",
    control_n: "100",
    treatment_mean: "10.1",
    treatment_std: "2",
    treatment_n: "100",
    alpha: "0.05",
    equivalence_margin: "0.5"
  };

  it("reuses the continuous summary input and carries the equivalence margin", () => {
    const state = emptyState();
    state.continuous = { ...continuousForm };
    const payload = buildResultsRequest("equivalence", state);
    expect(payload).toEqual({
      metric_type: "equivalence",
      continuous: {
        control_mean: 10,
        control_std: 2,
        control_n: 100,
        treatment_mean: 10.1,
        treatment_std: 2,
        treatment_n: 100,
        alpha: 0.05,
        equivalence_margin: 0.5
      }
    });
  });

  it("returns null when the margin is blank or not positive", () => {
    const state = emptyState();
    state.continuous = { ...continuousForm, equivalence_margin: "" };
    expect(buildResultsRequest("equivalence", state)).toBeNull();
    state.continuous = { ...continuousForm, equivalence_margin: "0" };
    expect(buildResultsRequest("equivalence", state)).toBeNull();
    state.continuous = { ...continuousForm, equivalence_margin: "-1" };
    expect(buildResultsRequest("equivalence", state)).toBeNull();
  });

  it("applies the same continuous validation (std must be positive)", () => {
    const state = emptyState();
    state.continuous = { ...continuousForm, control_std: "0" };
    expect(buildResultsRequest("equivalence", state)).toBeNull();
  });

  it("restores a saved equivalence request into the continuous form with its margin", () => {
    const restored = buildActualResultsState("equivalence", 0.05, {
      metric_type: "equivalence",
      continuous: {
        control_mean: 1,
        control_std: 1,
        control_n: 50,
        treatment_mean: 1.2,
        treatment_std: 1.1,
        treatment_n: 60,
        alpha: 0.01,
        equivalence_margin: 0.5
      }
    });
    expect(restored.continuous).toEqual({
      control_mean: "1",
      control_std: "1",
      control_n: "50",
      treatment_mean: "1.2",
      treatment_std: "1.1",
      treatment_n: "60",
      alpha: "0.01",
      equivalence_margin: "0.5"
    });
  });
});
