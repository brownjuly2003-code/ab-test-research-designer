// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import MetricsPlanSection from "../MetricsPlanSection";
import { flushEffects, renderIntoDocument } from "../../../test/dom";
import { resetResultsStores, seedResultsStores } from "./resultsTestUtils";

describe("MetricsPlanSection", () => {
  beforeEach(() => {
    resetResultsStores();
    seedResultsStores();
  });

  afterEach(() => {
    resetResultsStores();
  });

  it("renders metrics coverage and guardrail details", async () => {
    const view = await renderIntoDocument(<MetricsPlanSection />);
    try {
      await flushEffects();

      expect(view.container.textContent).toContain("purchase_conversion");
      expect(view.container.textContent).toContain("Payment error rate");
      expect(view.container.textContent).toContain(">= 0.321 pp");
    } finally {
      await view.unmount();
    }
  });
});
