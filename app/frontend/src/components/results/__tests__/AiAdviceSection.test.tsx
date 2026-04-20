// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import AiAdviceSection from "../AiAdviceSection";
import { flushEffects, renderIntoDocument } from "../../../test/dom";
import { resetResultsStores, seedResultsStores } from "./resultsTestUtils";

describe("AiAdviceSection", () => {
  beforeEach(() => {
    resetResultsStores();
    seedResultsStores();
  });

  afterEach(() => {
    resetResultsStores();
  });

  it("renders available advice content from stores", async () => {
    const view = await renderIntoDocument(<AiAdviceSection />);
    try {
      await flushEffects();

      expect(view.container.textContent).toContain("local_orchestrator");
      expect(view.container.textContent).toContain("The experiment is feasible with careful monitoring.");
    } finally {
      await view.unmount();
    }
  });
});
