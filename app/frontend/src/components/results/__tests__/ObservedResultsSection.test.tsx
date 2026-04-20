// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ObservedResultsSection from "../ObservedResultsSection";
import { flushEffects, renderIntoDocument } from "../../../test/dom";
import { resetResultsStores, seedResultsStores } from "./resultsTestUtils";

describe("ObservedResultsSection", () => {
  beforeEach(() => {
    resetResultsStores();
    seedResultsStores();
  });

  afterEach(() => {
    resetResultsStores();
  });

  it("renders the post-test form for actual results", async () => {
    const view = await renderIntoDocument(<ObservedResultsSection onResultsAnalysisChange={vi.fn()} />);
    try {
      await flushEffects();

      expect(view.container.textContent).toContain("Enter actual experiment results");
      expect(view.container.textContent).toContain("Control conversions");
      expect(view.container.textContent).toContain("Analyze results");
    } finally {
      await view.unmount();
    }
  });
});
