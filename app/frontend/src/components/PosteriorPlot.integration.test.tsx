// @vitest-environment jsdom

// Real-recharts rendering in jsdom requires ResponsiveContainer to skip its
// layout probe and forward fixed dimensions to children; without this, the
// chart collapses to 0x0 and no `.recharts-area-area` is produced. The
// companion axe test in PosteriorPlot.test.tsx uses a flat recharts stub for
// speed; this file keeps real recharts so the visual assertion stays honest.
vi.mock("recharts", async () => {
  const actual = await vi.importActual<typeof import("recharts")>("recharts");
  const React = await vi.importActual<typeof import("react")>("react");

  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: React.ReactElement }) =>
      React.cloneElement(
        React.Children.only(children) as React.ReactElement<Record<string, unknown>>,
        { width: 720, height: 260 } as Record<string, unknown>
      )
  };
});

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { flushEffects, renderIntoDocument } from "../test/dom";
import PosteriorPlot from "./PosteriorPlot";

describe("PosteriorPlot integration", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "ResizeObserver",
      class ResizeObserver {
        observe() {}
        unobserve() {}
        disconnect() {}
      }
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders a shaded credibility interval overlay", async () => {
    const view = await renderIntoDocument(
      <PosteriorPlot
        posteriorMean={12}
        posteriorStd={1.6}
        credibilityInterval={{ lower: 9.5, upper: 14.5, level: 0.9 }}
        metricType="continuous"
      />
    );

    try {
      await flushEffects();

      expect(view.container.querySelectorAll(".recharts-area-area").length).toBeGreaterThan(1);
    } finally {
      await view.unmount();
    }
  }, 15000);
});
