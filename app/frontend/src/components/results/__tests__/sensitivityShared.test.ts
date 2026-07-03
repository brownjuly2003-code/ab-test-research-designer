// @vitest-environment jsdom

import { beforeEach, describe, expect, it } from "vitest";

import { browserDraftStorageKey, initialState } from "../../../lib/experiment";
import type { FullPayload } from "../../../lib/experiment";
import { buildSensitivityPayload, resolveCurrentMde, resolveMetricType } from "../sensitivityShared";
import { buildAnalysisResult } from "./resultsTestUtils";

function seedDraft(overrides: Partial<FullPayload["metrics"]>) {
  const draft: FullPayload = {
    ...initialState,
    metrics: {
      ...initialState.metrics,
      ...overrides
    }
  };
  window.localStorage.setItem(browserDraftStorageKey, JSON.stringify(draft));
}

beforeEach(() => {
  window.localStorage.clear();
});

describe("resolveMetricType", () => {
  it("keeps binary as binary", () => {
    expect(resolveMetricType("binary")).toBe("binary");
  });

  it("keeps continuous as continuous", () => {
    expect(resolveMetricType("continuous")).toBe("continuous");
  });

  it("groups ratio with continuous, not binary", () => {
    expect(resolveMetricType("ratio")).toBe("continuous");
  });
});

describe("resolveCurrentMde", () => {
  it("uses the absolute MDE for a ratio analysis, like continuous", () => {
    const analysis = buildAnalysisResult({ metricType: "ratio" });
    expect(resolveCurrentMde(analysis)).toBe(analysis.calculations.calculation_summary.mde_absolute);
  });
});

describe("buildSensitivityPayload", () => {
  it("builds a ratio request from the matching persisted draft", () => {
    seedDraft({
      metric_type: "ratio",
      numerator_metric_name: "revenue",
      denominator_metric_name: "sessions",
      std_dev: 12.5
    });
    const analysis = buildAnalysisResult({ metricType: "ratio" });

    const payload = buildSensitivityPayload(analysis);

    expect(payload).toMatchObject({
      metric_type: "ratio",
      baseline_mean: analysis.calculations.calculation_summary.baseline_value,
      std_dev: 12.5
    });
  });

  it("returns null when the persisted draft is not a ratio metric", () => {
    seedDraft({ metric_type: "continuous", std_dev: 12.5 });
    const analysis = buildAnalysisResult({ metricType: "ratio" });

    expect(buildSensitivityPayload(analysis)).toBeNull();
  });

  it("returns null when the persisted ratio draft has no std_dev yet", () => {
    seedDraft({ metric_type: "ratio", std_dev: "" });
    const analysis = buildAnalysisResult({ metricType: "ratio" });

    expect(buildSensitivityPayload(analysis)).toBeNull();
  });
});
