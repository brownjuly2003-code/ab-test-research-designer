// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../PowerCurveChart", () => ({
  default: function PowerCurveChartMock() {
    return <div>Power curve chart</div>;
  }
}));

import PowerCurveSection from "../PowerCurveSection";
import { flushEffects, renderIntoDocument } from "../../../test/dom";
import {
  defaultSensitivityData,
  resetResultsStores,
  seedResultsStores
} from "./resultsTestUtils";

describe("PowerCurveSection", () => {
  beforeEach(() => {
    resetResultsStores();
    seedResultsStores();
  });

  afterEach(() => {
    resetResultsStores();
  });

  it("renders a power curve when sensitivity data is available", async () => {
    const view = await renderIntoDocument(
      <PowerCurveSection
        sensitivityData={defaultSensitivityData}
        sensitivityLoading={false}
        sensitivityUnavailableMessage="Unavailable"
      />
    );
    try {
      await flushEffects();

      expect(view.container.textContent).toContain("Power curve chart");
    } finally {
      await view.unmount();
    }
  });
});
