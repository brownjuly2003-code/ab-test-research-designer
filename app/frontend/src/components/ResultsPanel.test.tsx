// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./PowerCurveChart", () => ({
  default: function PowerCurveChartMock() {
    return <div>Power curve chart</div>;
  }
}));

import ResultsPanel from "./ResultsPanel";
import { flushEffects, renderIntoDocument } from "../test/dom";
import {
  buildAnalysisResult,
  buildProjectComparison,
  defaultSensitivityData,
  resetResultsStores,
  seedResultsStores
} from "./results/__tests__/resultsTestUtils";

describe("ResultsPanel", () => {
  beforeEach(() => {
    resetResultsStores();
    seedResultsStores({
      analysis: buildAnalysisResult({ metricType: "continuous" }),
      projectComparison: buildProjectComparison()
    });
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true,
      json: async () => defaultSensitivityData,
      blob: async () => new Blob(["report"], { type: "text/html" }),
      headers: new Headers()
    })));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    resetResultsStores();
  });

  it("renders the decomposed accordion shell from stores", async () => {
    const view = await renderIntoDocument(<ResultsPanel />);
    try {
      await flushEffects();

      expect(view.container.textContent).toContain("Comparison");
      expect(view.container.textContent).toContain("Sensitivity");
      expect(view.container.textContent).toContain("Power curve");
      expect(view.container.textContent).toContain("Observed results");
      expect(view.container.textContent).toContain("AI recommendations");
      expect(view.container.textContent).toContain("SRM check");
    } finally {
      await view.unmount();
    }
  }, 15000);
});
