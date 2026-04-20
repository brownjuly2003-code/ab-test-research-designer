// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import SequentialDesignSection from "../SequentialDesignSection";
import { flushEffects, renderIntoDocument } from "../../../test/dom";
import { resetResultsStores, seedResultsStores } from "./resultsTestUtils";

describe("SequentialDesignSection", () => {
  beforeEach(() => {
    resetResultsStores();
    seedResultsStores();
  });

  afterEach(() => {
    resetResultsStores();
  });

  it("renders O'Brien-Fleming boundaries from stores", async () => {
    const view = await renderIntoDocument(<SequentialDesignSection />);
    try {
      await flushEffects();

      expect(view.container.textContent).toContain("Group sequential design");
      expect(view.container.textContent).toContain("Stop early");
      expect(view.container.textContent).toContain("2.80");
    } finally {
      await view.unmount();
    }
  });
});
