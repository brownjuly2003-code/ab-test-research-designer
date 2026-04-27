// @vitest-environment jsdom

import "vitest-axe/extend-expect";

vi.mock("recharts", async () => {
  const actual = await vi.importActual<typeof import("recharts")>("recharts");
  const React = await vi.importActual<typeof import("react")>("react");

  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: React.ReactElement }) =>
      React.cloneElement(React.Children.only(children) as React.ReactElement<Record<string, unknown>>, { width: 720, height: 240 } as Record<string, unknown>)
  };
});

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";
import * as matchers from "vitest-axe/matchers";

import { flushEffects, renderIntoDocument } from "../test/dom";
import SequentialBoundaryChart from "./SequentialBoundaryChart";

expect.extend(matchers);

type AxeMatcher = {
  toHaveNoViolations: () => void;
};

const boundaries = [
  { look: 1, alpha_spent: 0.0008, upper_boundary_z: 3.8, lower_boundary_z: -3.8, sample_size_cumulative: 2500 },
  { look: 2, alpha_spent: 0.0045, upper_boundary_z: 3.1, lower_boundary_z: -3.1, sample_size_cumulative: 5000 },
  { look: 3, alpha_spent: 0.017, upper_boundary_z: 2.5, lower_boundary_z: -2.5, sample_size_cumulative: 7500 },
  { look: 4, alpha_spent: 0.05, upper_boundary_z: 2.02, lower_boundary_z: -2.02, sample_size_cumulative: 10000 }
];

describe("SequentialBoundaryChart", () => {
  beforeEach(() => {
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders four sequential looks on the x-axis", async () => {
    const view = await renderIntoDocument(<SequentialBoundaryChart boundaries={boundaries} />);

    try {
      await flushEffects();

      expect(view.container.querySelectorAll(".recharts-cartesian-axis-tick").length).toBeGreaterThanOrEqual(4);
    } finally {
      await view.unmount();
    }
  }, 15000);

  it("renders an extra reference line for the current look", async () => {
    const view = await renderIntoDocument(<SequentialBoundaryChart boundaries={boundaries} currentLook={2} />);

    try {
      await flushEffects();

      expect(view.container.querySelectorAll(".recharts-reference-line-line").length).toBe(3);
    } finally {
      await view.unmount();
    }
  }, 15000);

  it("has no axe violations", async () => {
    const view = await renderIntoDocument(<SequentialBoundaryChart boundaries={boundaries} currentLook={3} />);

    try {
      await flushEffects();

      (expect(await axe(view.container)) as unknown as AxeMatcher).toHaveNoViolations();
    } finally {
      await view.unmount();
    }
  }, 15000);
});
