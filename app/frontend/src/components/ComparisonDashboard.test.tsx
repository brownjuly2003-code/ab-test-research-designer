// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { buildMultiProjectComparison } from "./results/__tests__/resultsTestUtils";
import ComparisonDashboard from "./ComparisonDashboard";
import { flushEffects, renderIntoDocument } from "../test/dom";

describe("ComparisonDashboard", () => {
  beforeEach(() => {
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders three project series across dashboard sections", async () => {
    const view = await renderIntoDocument(
      <ComparisonDashboard comparison={buildMultiProjectComparison()} onClose={vi.fn()} />
    );
    try {
      await flushEffects();
      await flushEffects();

      expect(view.container.querySelectorAll('[data-testid="power-curve-series"]').length).toBe(3);
      expect(view.container.querySelectorAll('[data-testid="comparison-sensitivity-table"]').length).toBe(3);
      expect(view.container.querySelectorAll('[data-testid="forest-plot-row"]').length).toBe(3);
    } finally {
      await view.unmount();
    }
  });
});
