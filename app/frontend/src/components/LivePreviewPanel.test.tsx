// @vitest-environment jsdom

import "../i18n";

import { describe, expect, it } from "vitest";

import LivePreviewPanel from "./LivePreviewPanel";
import type { CalculationResponse } from "../lib/experiment";
import { renderIntoDocument } from "../test/dom";

function makeResult(overrides: Partial<Record<string, unknown>> = {}): CalculationResponse {
  return {
    results: {
      sample_size_per_variant: 2980,
      estimated_duration_days: 12,
      allocated_daily_traffic: null
    },
    cuped_sample_size_per_variant: null,
    cuped_variance_reduction_pct: null,
    bonferroni_note: null,
    design_effect: null,
    avg_cluster_size: null,
    clusters_per_variant: null,
    ...overrides
  } as unknown as CalculationResponse;
}

describe("LivePreviewPanel", () => {
  it("renders a cluster design-effect badge when a cluster design is planned", async () => {
    const view = await renderIntoDocument(
      <LivePreviewPanel
        result={makeResult({ design_effect: 2.98, clusters_per_variant: 30, avg_cluster_size: 100 })}
        isLoading={false}
        error={null}
      />
    );

    try {
      const text = view.container.textContent ?? "";
      expect(text).toContain("Design effect 2.98");
      expect(text).toContain("30 clusters");
    } finally {
      await view.unmount();
    }
  });

  it("omits the cluster badge for a non-cluster design", async () => {
    const view = await renderIntoDocument(
      <LivePreviewPanel result={makeResult()} isLoading={false} error={null} />
    );

    try {
      expect(view.container.textContent ?? "").not.toContain("Design effect");
    } finally {
      await view.unmount();
    }
  });
});
