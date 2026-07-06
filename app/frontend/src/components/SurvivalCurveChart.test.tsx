// @vitest-environment jsdom

import "vitest-axe/extend-expect";

vi.mock("recharts", async () => {
  const actual = await vi.importActual<typeof import("recharts")>("recharts");
  const React = await vi.importActual<typeof import("react")>("react");

  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: React.ReactElement }) =>
      React.cloneElement(React.Children.only(children) as React.ReactElement<Record<string, unknown>>, { width: 720, height: 280 } as Record<string, unknown>)
  };
});

import { afterEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";
import * as matchers from "vitest-axe/matchers";

import { flushEffects, renderIntoDocument } from "../test/dom";
import SurvivalCurveChart from "./SurvivalCurveChart";

expect.extend(matchers);

type AxeMatcher = {
  toHaveNoViolations: () => void;
};

const series = [
  { time: 0, control: 1, treatment: 1 },
  { time: 6, control: 0.9, treatment: 0.857143 },
  { time: 10, control: 0.72, treatment: 0.752941 },
  { time: 23, control: 0.1, treatment: 0.448179 }
];

describe("SurvivalCurveChart", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders a labelled survival-curve region", async () => {
    const view = await renderIntoDocument(
      <SurvivalCurveChart
        series={series}
        controlLabel="Control"
        treatmentLabel="Treatment"
        ariaLabel="Kaplan-Meier survival curves for the control and treatment arms"
        timeAxisLabel="Time"
        survivalAxisLabel="Survival S(t)"
      />
    );
    try {
      await flushEffects();
      const region = view.container.querySelector('[role="img"]');
      expect(region).not.toBeNull();
      expect(region?.getAttribute("aria-label")).toContain("survival");
    } finally {
      await view.unmount();
    }
  }, 15000);

  it("has no axe violations", async () => {
    const view = await renderIntoDocument(
      <SurvivalCurveChart
        series={series}
        controlLabel="Control"
        treatmentLabel="Treatment"
        ariaLabel="Kaplan-Meier survival curves for the control and treatment arms"
        timeAxisLabel="Time"
        survivalAxisLabel="Survival S(t)"
      />
    );
    try {
      await flushEffects();
      (expect(await axe(view.container)) as unknown as AxeMatcher).toHaveNoViolations();
    } finally {
      await view.unmount();
    }
  }, 15000);
});
