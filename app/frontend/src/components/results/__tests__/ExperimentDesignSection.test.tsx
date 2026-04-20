// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import ExperimentDesignSection from "../ExperimentDesignSection";
import { flushEffects, renderIntoDocument } from "../../../test/dom";
import { resetResultsStores, seedResultsStores } from "./resultsTestUtils";

describe("ExperimentDesignSection", () => {
  beforeEach(() => {
    resetResultsStores();
    seedResultsStores();
  });

  afterEach(() => {
    resetResultsStores();
  });

  it("renders experiment setup and open questions", async () => {
    const view = await renderIntoDocument(<ExperimentDesignSection />);
    try {
      await flushEffects();

      expect(view.container.textContent).toContain("Control");
      expect(view.container.textContent).toContain("new users on web");
      expect(view.container.textContent).toContain("Will mobile respond differently?");
    } finally {
      await view.unmount();
    }
  });
});
