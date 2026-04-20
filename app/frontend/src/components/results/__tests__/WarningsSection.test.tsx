// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import WarningsSection from "../WarningsSection";
import { flushEffects, renderIntoDocument } from "../../../test/dom";
import { resetResultsStores, seedResultsStores } from "./resultsTestUtils";

describe("WarningsSection", () => {
  beforeEach(() => {
    resetResultsStores();
    seedResultsStores();
  });

  afterEach(() => {
    resetResultsStores();
  });

  it("renders warning rows from stores", async () => {
    const view = await renderIntoDocument(<WarningsSection />);
    try {
      await flushEffects();

      expect(view.container.textContent).toContain("SEASONALITY_PRESENT");
      expect(view.container.textContent).toContain("Seasonality may affect the baseline.");
    } finally {
      await view.unmount();
    }
  });
});
