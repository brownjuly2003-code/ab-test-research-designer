// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import SensitivitySection from "../SensitivitySection";
import { flushEffects, renderIntoDocument } from "../../../test/dom";
import {
  buildAnalysisResult,
  defaultSensitivityData,
  resetResultsStores,
  seedResultsStores
} from "./resultsTestUtils";

describe("SensitivitySection", () => {
  beforeEach(() => {
    resetResultsStores();
    seedResultsStores({
      analysis: buildAnalysisResult({ metricType: "continuous" })
    });
  });

  afterEach(() => {
    resetResultsStores();
  });

  it("renders summary cards, CUPED, bayesian estimates, and sensitivity table", async () => {
    const view = await renderIntoDocument(
      <SensitivitySection
        sensitivityData={defaultSensitivityData}
        sensitivityLoading={false}
        sensitivityUnavailableMessage="Unavailable"
        standaloneExporting={false}
        standaloneExportError=""
        canExportPdf
        onExportReport={vi.fn()}
        onExportPdf={vi.fn()}
        onExportProjectData={vi.fn()}
        onExportStandalone={vi.fn()}
      />
    );
    try {
      await flushEffects();

      expect(view.container.textContent).toContain("CUPED-adjusted estimate");
      expect(view.container.textContent).toContain("Bayesian estimate");
      expect(view.container.textContent).toContain("Sensitivity table");
      expect(view.container.textContent).toContain("Project history context");
    } finally {
      await view.unmount();
    }
  });
});
