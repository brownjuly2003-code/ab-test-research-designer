// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import RisksSection from "../RisksSection";
import { flushEffects, renderIntoDocument } from "../../../test/dom";
import { resetResultsStores, seedResultsStores } from "./resultsTestUtils";

describe("RisksSection", () => {
  beforeEach(() => {
    resetResultsStores();
    seedResultsStores();
  });

  afterEach(() => {
    resetResultsStores();
  });

  it("renders risk groups and recommendation items", async () => {
    const view = await renderIntoDocument(<RisksSection />);
    try {
      await flushEffects();

      expect(view.container.textContent).toContain("Monitor peeking risk.");
      expect(view.container.textContent).toContain("Legacy event logging requires validation.");
      expect(view.container.textContent).toContain("Before launch: Verify tracking");
    } finally {
      await view.unmount();
    }
  });
});
