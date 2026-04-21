// @vitest-environment jsdom

import "vitest-axe/extend-expect";

vi.mock("recharts", async () => {
  const actual = await vi.importActual<typeof import("recharts")>("recharts");
  const React = await vi.importActual<typeof import("react")>("react");

  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: React.ReactElement }) =>
      React.cloneElement(React.Children.only(children) as React.ReactElement<Record<string, unknown>>, { width: 720, height: 260 } as Record<string, unknown>)
  };
});

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";
import * as matchers from "vitest-axe/matchers";

import { flushEffects, renderIntoDocument } from "../test/dom";
import PosteriorPlot from "./PosteriorPlot";

expect.extend(matchers);

type AxeMatcher = {
  toHaveNoViolations: () => void;
};

describe("PosteriorPlot", () => {
  let consoleErrorSpy: ReturnType<typeof vi.spyOn>;
  let consoleWarnSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    vi.stubGlobal(
      "ResizeObserver",
      class ResizeObserver {
        observe() {}
        unobserve() {}
        disconnect() {}
      }
    );
    consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    consoleWarnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
  });

  afterEach(() => {
    consoleErrorSpy.mockRestore();
    consoleWarnSpy.mockRestore();
    vi.unstubAllGlobals();
  });

  it("renders the posterior chart with an accessible label and no axe violations", async () => {
    const view = await renderIntoDocument(
      <PosteriorPlot
        posteriorMean={0.042}
        posteriorStd={0.0031}
        credibilityInterval={{ lower: 0.036, upper: 0.048, level: 0.95 }}
        priorMean={0.04}
        priorStd={0.005}
        metricType="binary"
      />
    );

    try {
      await flushEffects();

      const image = view.container.querySelector('[role="img"]');

      expect(image?.getAttribute("aria-label")).toContain("95% credibility interval");
      (expect(await axe(view.container)) as unknown as AxeMatcher).toHaveNoViolations();
    } finally {
      await view.unmount();
    }
  }, 15000);

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

  it("renders without runtime warnings for valid posterior inputs", async () => {
    const view = await renderIntoDocument(
      <PosteriorPlot
        posteriorMean={0.045}
        posteriorStd={0.004}
        credibilityInterval={{ lower: 0.038, upper: 0.052, level: 0.95 }}
        priorMean={0.041}
        priorStd={0.006}
        metricType="binary"
      />
    );

    try {
      await flushEffects();

      expect(consoleErrorSpy).not.toHaveBeenCalled();
      expect(consoleWarnSpy).not.toHaveBeenCalled();
    } finally {
      await view.unmount();
    }
  }, 15000);
});
