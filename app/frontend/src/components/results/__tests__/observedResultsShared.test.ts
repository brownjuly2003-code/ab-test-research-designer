import { describe, expect, it } from "vitest";

import {
  buildActualResultsState,
  buildResultsRequest,
  observedChooserQuestions,
  observedFormKind,
  observedTestButtons,
  observedTestLabelKey,
  parseSampleValues,
  recommendObservedTest,
  resolveEffectiveMetricType,
  resolveObservedMetricType,
  restoreObservedTest,
  supportedObservedMetricTypes,
  type ActualResultsState,
  type ObservedBaseMetricType,
  type ObservedTestSelection
} from "../observedResultsShared";

function emptyState(): ActualResultsState {
  return buildActualResultsState("continuous", 0.05, null);
}

describe("resolveObservedMetricType", () => {
  it("passes continuous plans through unchanged", () => {
    expect(resolveObservedMetricType("continuous")).toBe("continuous");
  });

  it("surfaces ratio plans as ratio, not a silent binary fallback", () => {
    expect(resolveObservedMetricType("ratio")).toBe("ratio");
  });

  it("defaults anything else (including binary) to binary", () => {
    expect(resolveObservedMetricType("binary")).toBe("binary");
    expect(resolveObservedMetricType("categorical")).toBe("binary");
  });
});

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
    state.ranked = { control_values: "1 2 3 4", treatment_values: "5,6,7,8", alpha: "0.05", quantile: "0.5", trim: "0.2" };
    const payload = buildResultsRequest("mann_whitney", state);
    expect(payload).toEqual({
      metric_type: "mann_whitney",
      ranked: { control_values: [1, 2, 3, 4], treatment_values: [5, 6, 7, 8], alpha: 0.05 }
    });
  });

  it("returns null when an arm has fewer than two values", () => {
    const state = emptyState();
    state.ranked = { control_values: "1", treatment_values: "5 6 7", alpha: "0.05", quantile: "0.5", trim: "0.2" };
    expect(buildResultsRequest("mann_whitney", state)).toBeNull();
  });

  it("returns null when an arm exceeds the 1000-value cap", () => {
    const state = emptyState();
    const tooMany = Array.from({ length: 1001 }, (_, index) => String(index)).join(" ");
    state.ranked = { control_values: tooMany, treatment_values: "5 6", alpha: "0.05", quantile: "0.5", trim: "0.2" };
    expect(buildResultsRequest("mann_whitney", state)).toBeNull();
  });

  it("returns null when alpha is out of range", () => {
    const state = emptyState();
    state.ranked = { control_values: "1 2 3", treatment_values: "4 5 6", alpha: "0.5", quantile: "0.5", trim: "0.2" };
    expect(buildResultsRequest("mann_whitney", state)).toBeNull();
  });
});

describe("buildResultsRequest (bootstrap)", () => {
  it("reuses the ranked raw-sample input and tags the payload as bootstrap", () => {
    const state = emptyState();
    state.ranked = { control_values: "1 2 3 4", treatment_values: "5,6,7,8", alpha: "0.05", quantile: "0.5", trim: "0.2" };
    const payload = buildResultsRequest("bootstrap", state);
    expect(payload).toEqual({
      metric_type: "bootstrap",
      ranked: { control_values: [1, 2, 3, 4], treatment_values: [5, 6, 7, 8], alpha: 0.05 }
    });
  });

  it("applies the same ranked validation as mann_whitney (min two values per arm)", () => {
    const state = emptyState();
    state.ranked = { control_values: "1", treatment_values: "5 6 7", alpha: "0.05", quantile: "0.5", trim: "0.2" };
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
      quantile: "0.5",
      trim: "0.2"
    });
  });
});

describe("buildResultsRequest (quantile)", () => {
  it("reuses the ranked raw-sample input and carries the chosen quantile", () => {
    const state = emptyState();
    state.ranked = { control_values: "1 2 3 4", treatment_values: "5,6,7,8", alpha: "0.05", quantile: "0.9", trim: "0.2" };
    const payload = buildResultsRequest("quantile", state);
    expect(payload).toEqual({
      metric_type: "quantile",
      ranked: { control_values: [1, 2, 3, 4], treatment_values: [5, 6, 7, 8], alpha: 0.05, quantile: 0.9 }
    });
  });

  it("returns null when the quantile is out of the open (0, 1) range", () => {
    const state = emptyState();
    state.ranked = { control_values: "1 2 3", treatment_values: "4 5 6", alpha: "0.05", quantile: "1", trim: "0.2" };
    expect(buildResultsRequest("quantile", state)).toBeNull();
    state.ranked = { ...state.ranked, quantile: "0" };
    expect(buildResultsRequest("quantile", state)).toBeNull();
    state.ranked = { ...state.ranked, quantile: "" };
    expect(buildResultsRequest("quantile", state)).toBeNull();
  });

  it("applies the same ranked validation as mann_whitney (min two values per arm)", () => {
    const state = emptyState();
    state.ranked = { control_values: "1", treatment_values: "5 6 7", alpha: "0.05", quantile: "0.5", trim: "0.2" };
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
      quantile: "0.9",
      trim: "0.2"
    });
  });
});

describe("buildResultsRequest (trimmed_t)", () => {
  it("reuses the ranked raw-sample input and carries the trim fraction", () => {
    const state = emptyState();
    state.ranked = { control_values: "1 2 3 4", treatment_values: "5,6,7,8", alpha: "0.05", quantile: "0.5", trim: "0.1" };
    const payload = buildResultsRequest("trimmed_t", state);
    expect(payload).toEqual({
      metric_type: "trimmed_t",
      ranked: { control_values: [1, 2, 3, 4], treatment_values: [5, 6, 7, 8], alpha: 0.05, trim: 0.1 }
    });
  });

  it("accepts a trim of zero (reduces to Welch's t)", () => {
    const state = emptyState();
    state.ranked = { control_values: "1 2 3 4", treatment_values: "5 6 7 8", alpha: "0.05", quantile: "0.5", trim: "0" };
    const payload = buildResultsRequest("trimmed_t", state);
    expect(payload).toEqual({
      metric_type: "trimmed_t",
      ranked: { control_values: [1, 2, 3, 4], treatment_values: [5, 6, 7, 8], alpha: 0.05, trim: 0 }
    });
  });

  it("returns null when the trim is out of the [0, 0.5) range or blank", () => {
    const state = emptyState();
    state.ranked = { control_values: "1 2 3", treatment_values: "4 5 6", alpha: "0.05", quantile: "0.5", trim: "0.5" };
    expect(buildResultsRequest("trimmed_t", state)).toBeNull();
    state.ranked = { ...state.ranked, trim: "-0.1" };
    expect(buildResultsRequest("trimmed_t", state)).toBeNull();
    state.ranked = { ...state.ranked, trim: "" };
    expect(buildResultsRequest("trimmed_t", state)).toBeNull();
  });

  it("applies the same ranked validation as mann_whitney (min two values per arm)", () => {
    const state = emptyState();
    state.ranked = { control_values: "1", treatment_values: "5 6 7", alpha: "0.05", quantile: "0.5", trim: "0.2" };
    expect(buildResultsRequest("trimmed_t", state)).toBeNull();
  });

  it("restores a saved trimmed_t request into the ranked form with its trim", () => {
    const restored = buildActualResultsState("trimmed_t", 0.05, {
      metric_type: "trimmed_t",
      ranked: { control_values: [1, 2, 3], treatment_values: [4, 5, 6], alpha: 0.01, trim: 0.1 }
    });
    expect(restored.ranked).toEqual({
      control_values: "1\n2\n3",
      treatment_values: "4\n5\n6",
      alpha: "0.01",
      quantile: "0.5",
      trim: "0.1"
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

describe("buildResultsRequest (boschloo_exact)", () => {
  it("reuses the binary 2x2 input and tags the payload as boschloo_exact", () => {
    const state = emptyState();
    state.binary = {
      control_conversions: "3",
      control_users: "10",
      treatment_conversions: "8",
      treatment_users: "10",
      alpha: "0.05"
    };
    const payload = buildResultsRequest("boschloo_exact", state);
    expect(payload).toEqual({
      metric_type: "boschloo_exact",
      binary: {
        control_conversions: 3,
        control_users: 10,
        treatment_conversions: 8,
        treatment_users: 10,
        alpha: 0.05
      }
    });
  });

  it("restores a saved boschloo_exact request into the binary form", () => {
    const restored = buildActualResultsState("boschloo_exact", 0.05, {
      metric_type: "boschloo_exact",
      binary: {
        control_conversions: 3,
        control_users: 10,
        treatment_conversions: 8,
        treatment_users: 10,
        alpha: 0.01
      }
    });
    expect(restored.binary).toEqual({
      control_conversions: "3",
      control_users: "10",
      treatment_conversions: "8",
      treatment_users: "10",
      alpha: "0.01"
    });
  });
});

describe("buildResultsRequest (barnard_exact)", () => {
  it("reuses the binary 2x2 input and tags the payload as barnard_exact", () => {
    const state = emptyState();
    state.binary = {
      control_conversions: "3",
      control_users: "10",
      treatment_conversions: "8",
      treatment_users: "10",
      alpha: "0.05"
    };
    const payload = buildResultsRequest("barnard_exact", state);
    expect(payload).toEqual({
      metric_type: "barnard_exact",
      binary: {
        control_conversions: 3,
        control_users: 10,
        treatment_conversions: 8,
        treatment_users: 10,
        alpha: 0.05
      }
    });
  });

  it("restores a saved barnard_exact request into the binary form", () => {
    const restored = buildActualResultsState("barnard_exact", 0.05, {
      metric_type: "barnard_exact",
      binary: {
        control_conversions: 3,
        control_users: 10,
        treatment_conversions: 8,
        treatment_users: 10,
        alpha: 0.01
      }
    });
    expect(restored.binary).toEqual({
      control_conversions: "3",
      control_users: "10",
      treatment_conversions: "8",
      treatment_users: "10",
      alpha: "0.01"
    });
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

describe("test registry — observedTestButtons", () => {
  it("offers the z-test default, the three exact tests and the plan-independent rate test on a binary plan", () => {
    expect(observedTestButtons("binary").map((button) => button.test)).toEqual(["parametric", "fisher_exact", "boschloo_exact", "barnard_exact", "count"]);
  });

  it("offers the full continuous suite in display order, default first", () => {
    expect(observedTestButtons("continuous").map((button) => button.test)).toEqual([
      "parametric",
      "mann_whitney",
      "bootstrap",
      "quantile",
      "trimmed_t",
      "equivalence",
      "count"
    ]);
  });

  it("offers only the continuous approximation and the rate test on a ratio plan", () => {
    expect(observedTestButtons("ratio").map((button) => button.test)).toEqual(["parametric", "count"]);
  });

  it("labels the default option per base plan", () => {
    expect(observedTestButtons("binary")[0].labelKey).toBe("results.observedResults.testType.zTest");
    expect(observedTestButtons("continuous")[0].labelKey).toBe("results.observedResults.testType.parametric");
    expect(observedTestButtons("ratio")[0].labelKey).toBe("results.observedResults.testType.continuousApprox");
  });
});

describe("test registry — resolveEffectiveMetricType", () => {
  it("resolves the parametric default to the base plan's own analyzer (ratio approximates as continuous in this generic form)", () => {
    expect(resolveEffectiveMetricType("binary", "parametric")).toBe("binary");
    expect(resolveEffectiveMetricType("continuous", "parametric")).toBe("continuous");
    expect(resolveEffectiveMetricType("ratio", "parametric")).toBe("continuous");
  });

  it("resolves each alternative offered for the base to its own analyzer", () => {
    expect(resolveEffectiveMetricType("binary", "fisher_exact")).toBe("fisher_exact");
    expect(resolveEffectiveMetricType("binary", "boschloo_exact")).toBe("boschloo_exact");
    expect(resolveEffectiveMetricType("binary", "barnard_exact")).toBe("barnard_exact");
    expect(resolveEffectiveMetricType("continuous", "mann_whitney")).toBe("mann_whitney");
    expect(resolveEffectiveMetricType("continuous", "equivalence")).toBe("equivalence");
    expect(resolveEffectiveMetricType("ratio", "count")).toBe("count");
    expect(resolveEffectiveMetricType("binary", "count")).toBe("count");
  });

  it("falls back to the base default when an alternative is not offered for that base (guard preserved)", () => {
    // Mann–Whitney is a continuous-only alternative; on a binary plan the old ladder folded it back to
    // binary, and the registry preserves that guard.
    expect(resolveEffectiveMetricType("binary", "mann_whitney")).toBe("binary");
    expect(resolveEffectiveMetricType("ratio", "fisher_exact")).toBe("continuous");
  });
});

describe("test registry — supportedObservedMetricTypes", () => {
  it("mirrors the previous hard-coded supported-type sets per base", () => {
    expect(supportedObservedMetricTypes("continuous")).toEqual([
      "continuous",
      "mann_whitney",
      "bootstrap",
      "quantile",
      "trimmed_t",
      "equivalence",
      "count"
    ]);
    expect(supportedObservedMetricTypes("binary")).toEqual(["binary", "fisher_exact", "boschloo_exact", "barnard_exact", "count"]);
    expect(supportedObservedMetricTypes("ratio")).toEqual(["continuous", "count"]);
  });
});

describe("test registry — restoreObservedTest", () => {
  it("maps a persisted analyzer metric_type back to its toggle selection for the base plan", () => {
    expect(restoreObservedTest("binary", "fisher_exact")).toBe("fisher_exact");
    expect(restoreObservedTest("binary", "boschloo_exact")).toBe("boschloo_exact");
    expect(restoreObservedTest("binary", "barnard_exact")).toBe("barnard_exact");
    expect(restoreObservedTest("continuous", "trimmed_t")).toBe("trimmed_t");
    expect(restoreObservedTest("continuous", "count")).toBe("count");
    expect(restoreObservedTest("ratio", "count")).toBe("count");
  });

  it("restores the base default type (and anything not offered for the base) to the parametric toggle", () => {
    expect(restoreObservedTest("binary", "binary")).toBe("parametric");
    expect(restoreObservedTest("continuous", "continuous")).toBe("parametric");
    // A continuous-only analyzer persisted against a binary plan cannot restore -> default toggle.
    expect(restoreObservedTest("binary", "mann_whitney")).toBe("parametric");
    // No persisted type at all.
    expect(restoreObservedTest("continuous", undefined)).toBe("parametric");
  });

  it("round-trips every button through resolve -> restore for each base plan", () => {
    const bases: ObservedBaseMetricType[] = ["binary", "continuous", "ratio"];
    for (const base of bases) {
      for (const button of observedTestButtons(base)) {
        const resolved = resolveEffectiveMetricType(base, button.test);
        const restored = restoreObservedTest(base, resolved);
        // The default and its analyzer both round-trip to the parametric toggle; alternatives to themselves.
        const expected: ObservedTestSelection = button.test === "parametric" ? "parametric" : button.test;
        expect(restored).toBe(expected);
      }
    }
  });
});

describe("test registry — observedFormKind", () => {
  it("routes each analyzer to its input form", () => {
    expect(observedFormKind("binary")).toBe("binary");
    expect(observedFormKind("fisher_exact")).toBe("binary");
    expect(observedFormKind("boschloo_exact")).toBe("binary");
    expect(observedFormKind("barnard_exact")).toBe("binary");
    expect(observedFormKind("continuous")).toBe("continuous");
    expect(observedFormKind("equivalence")).toBe("equivalence");
    expect(observedFormKind("mann_whitney")).toBe("ranked");
    expect(observedFormKind("bootstrap")).toBe("ranked");
    expect(observedFormKind("quantile")).toBe("ranked");
    expect(observedFormKind("trimmed_t")).toBe("ranked");
    expect(observedFormKind("count")).toBe("count");
  });
});

describe("recommendObservedTest — binary chooser", () => {
  it("asks a single small-sample question and recommends Fisher vs the z-test", () => {
    expect(observedChooserQuestions("binary").map((question) => question.id)).toEqual(["binarySmall"]);
    expect(recommendObservedTest("binary", {})).toBeNull();
    expect(recommendObservedTest("binary", { binarySmall: "yes" })).toEqual({
      test: "fisher_exact",
      rationaleKey: "results.observedResults.chooser.rationale.fisher_exact"
    });
    expect(recommendObservedTest("binary", { binarySmall: "no" })).toEqual({
      test: "parametric",
      rationaleKey: "results.observedResults.chooser.rationale.zTest"
    });
  });
});

describe("recommendObservedTest — continuous chooser", () => {
  it("needs all three questions before recommending", () => {
    expect(observedChooserQuestions("continuous").map((question) => question.id)).toEqual(["goal", "distribution", "focus"]);
    expect(recommendObservedTest("continuous", { goal: "difference", distribution: "normal" })).toBeNull();
  });

  it("prioritises the equivalence goal over everything else", () => {
    expect(recommendObservedTest("continuous", { goal: "equivalence", distribution: "skew_outliers", focus: "percentile" })).toEqual({
      test: "equivalence",
      rationaleKey: "results.observedResults.chooser.rationale.equivalence"
    });
  });

  it("recommends the quantile effect when a tail matters more than the mean", () => {
    expect(recommendObservedTest("continuous", { goal: "difference", distribution: "normal", focus: "percentile" })).toEqual({
      test: "quantile",
      rationaleKey: "results.observedResults.chooser.rationale.quantile"
    });
  });

  it("recommends the robust trimmed t for skewed / outlier-heavy data comparing the mean", () => {
    expect(recommendObservedTest("continuous", { goal: "difference", distribution: "skew_outliers", focus: "mean" })).toEqual({
      test: "trimmed_t",
      rationaleKey: "results.observedResults.chooser.rationale.trimmed_t"
    });
  });

  it("recommends Mann–Whitney for a small / non-normal sample comparing the mean", () => {
    expect(recommendObservedTest("continuous", { goal: "difference", distribution: "small_nonnormal", focus: "mean" })).toEqual({
      test: "mann_whitney",
      rationaleKey: "results.observedResults.chooser.rationale.mann_whitney"
    });
  });

  it("recommends the plain difference t-test for roughly-normal data comparing the mean", () => {
    expect(recommendObservedTest("continuous", { goal: "difference", distribution: "normal", focus: "mean" })).toEqual({
      test: "parametric",
      rationaleKey: "results.observedResults.chooser.rationale.parametric"
    });
  });

  it("names its recommendation with the same label as the toggle button", () => {
    expect(observedTestLabelKey("continuous", "trimmed_t")).toBe("results.observedResults.testType.trimmedT");
    expect(observedTestLabelKey("binary", "parametric")).toBe("results.observedResults.testType.zTest");
  });

  it("offers no chooser for ratio plans (two options needing different data)", () => {
    expect(observedChooserQuestions("ratio")).toEqual([]);
    expect(recommendObservedTest("ratio", {})).toBeNull();
  });
});
