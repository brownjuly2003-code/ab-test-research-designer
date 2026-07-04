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

  it("groups results into four lifecycle stages with an anchor table of contents", async () => {
    const view = await renderIntoDocument(<ResultsPanel />);
    try {
      await flushEffects();

      const stages = Array.from(view.container.querySelectorAll("[data-stage]")).map((element) =>
        element.getAttribute("data-stage")
      );
      expect(stages).toEqual(["planning", "posthoc", "execution", "decision"]);

      const tocLinks = Array.from(view.container.querySelectorAll('nav a[href^="#stage-"]')).map((anchor) =>
        anchor.getAttribute("href")
      );
      expect(tocLinks).toEqual(["#stage-planning", "#stage-posthoc", "#stage-execution", "#stage-decision"]);

      // Every ToC link has a matching anchored stage heading to jump to.
      for (const key of ["planning", "posthoc", "execution", "decision"]) {
        expect(view.container.querySelector(`#stage-${key} #stage-${key}-heading`)).not.toBeNull();
      }
    } finally {
      await view.unmount();
    }
  }, 15000);

  it("surfaces the Decision stage first once the experiment has live data", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        // The live-stats probe reads exposures_total; the sensitivity fetch reads cells.
        json: async () => ({ ...defaultSensitivityData, exposures_total: 4200 }),
        blob: async () => new Blob(["report"], { type: "text/html" }),
        headers: new Headers()
      }))
    );

    const view = await renderIntoDocument(<ResultsPanel />);
    try {
      // The probe resolves asynchronously; flush until the reorder lands.
      let stages: (string | null)[] = [];
      for (let attempt = 0; attempt < 8; attempt += 1) {
        await flushEffects();
        stages = Array.from(view.container.querySelectorAll("[data-stage]")).map((element) =>
          element.getAttribute("data-stage")
        );
        if (stages[0] === "decision") {
          break;
        }
      }
      expect(stages).toEqual(["decision", "execution", "planning", "posthoc"]);
    } finally {
      await view.unmount();
    }
  }, 15000);
});
