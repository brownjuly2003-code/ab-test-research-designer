// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import AiAdviceSection from "../AiAdviceSection";
import i18n from "../../../i18n";
import { flushEffects, renderIntoDocument } from "../../../test/dom";
import { buildAnalysisResult, resetResultsStores, seedResultsStores } from "./resultsTestUtils";

describe("AiAdviceSection", () => {
  beforeEach(async () => {
    // Deterministically load the default-language bundle before rendering so t() resolves keys
    // regardless of test-file run order (matches the i18n.test.tsx readiness pattern).
    await i18n.changeLanguage("en");
    resetResultsStores();
  });

  afterEach(() => {
    resetResultsStores();
  });

  it("renders available advice content from stores", async () => {
    seedResultsStores();
    const view = await renderIntoDocument(<AiAdviceSection />);
    try {
      await flushEffects();

      expect(view.container.textContent).toContain("local_orchestrator");
      expect(view.container.textContent).toContain("The experiment is feasible with careful monitoring.");
    } finally {
      await view.unmount();
    }
  });

  it("shows a neutral seeded-demo message instead of the raw backend error", async () => {
    seedResultsStores({
      analysis: buildAnalysisResult({ adviceAvailable: false, adviceErrorCode: "seed_demo_disabled_llm" })
    });
    const view = await renderIntoDocument(<AiAdviceSection />);
    try {
      await flushEffects();

      expect(view.container.textContent).toContain("AI advice is not generated for this seeded demo project");
      expect(view.container.textContent).not.toContain("Demo seed skips live LLM advice");
    } finally {
      await view.unmount();
    }
  });
});
