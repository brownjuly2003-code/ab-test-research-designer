// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import SrmCheckSection from "../SrmCheckSection";
import { flushEffects, renderIntoDocument } from "../../../test/dom";
import { resetResultsStores, seedResultsStores } from "./resultsTestUtils";

describe("SrmCheckSection", () => {
  beforeEach(() => {
    resetResultsStores();
    seedResultsStores();
  });

  afterEach(() => {
    resetResultsStores();
  });

  it("renders SRM form fields for each variant", async () => {
    const view = await renderIntoDocument(<SrmCheckSection />);
    try {
      await flushEffects();

      expect(view.container.textContent).toContain("Did traffic split as planned?");
      expect(view.container.textContent).toContain("Control");
      expect(view.container.textContent).toContain("Check for SRM");
    } finally {
      await view.unmount();
    }
  });
});
