// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import ComparisonSection from "../ComparisonSection";
import { flushEffects, renderIntoDocument } from "../../../test/dom";
import {
  buildProjectComparison,
  resetResultsStores,
  seedResultsStores
} from "./resultsTestUtils";

describe("ComparisonSection", () => {
  beforeEach(() => {
    resetResultsStores();
    seedResultsStores({
      projectComparison: buildProjectComparison()
    });
  });

  afterEach(() => {
    resetResultsStores();
  });

  it("renders saved project comparison details", async () => {
    const view = await renderIntoDocument(<ComparisonSection />);
    try {
      await flushEffects();

      expect(view.container.textContent).toContain("Pricing challenger");
      expect(view.container.textContent).toContain("Stored checkout test");
      expect(view.container.textContent).toContain("Comparison highlights");
    } finally {
      await view.unmount();
    }
  });
});
