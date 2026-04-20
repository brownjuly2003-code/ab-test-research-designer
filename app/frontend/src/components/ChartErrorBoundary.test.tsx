// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { flushEffects, renderIntoDocument } from "../test/dom";
import ChartErrorBoundary from "./ChartErrorBoundary";

function BrokenComponent(): never {
  throw new Error("boom");
}

describe("ChartErrorBoundary", () => {
  beforeEach(() => {
    vi.spyOn(console, "error").mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows chart fallback and raw data when chart rendering fails", async () => {
    const view = await renderIntoDocument(
      <ChartErrorBoundary rawData={{ points: [1, 2, 3] }}>
        <BrokenComponent />
      </ChartErrorBoundary>
    );
    try {
      await flushEffects();

      expect(view.container.textContent).toContain("Chart unavailable");
      expect(view.container.querySelector("pre")?.textContent).toContain('"points"');
      expect(view.container.querySelector("pre")?.textContent).toContain("1");
    } finally {
      await view.unmount();
    }
  });
});
