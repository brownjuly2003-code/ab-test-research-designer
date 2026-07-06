// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// recharts' ResponsiveContainer measures its parent, which is 0×0 in jsdom; inject a fixed size so the
// Kaplan–Meier chart actually renders (same shim as SequentialBoundaryChart.test.tsx).
vi.mock("recharts", async () => {
  const actual = await vi.importActual<typeof import("recharts")>("recharts");
  const React = await vi.importActual<typeof import("react")>("react");
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: React.ReactElement }) =>
      React.cloneElement(
        React.Children.only(children) as React.ReactElement<Record<string, unknown>>,
        { width: 720, height: 280 } as Record<string, unknown>
      )
  };
});

import SurvivalResultsSection, { buildSurvivalSeries, parseSurvivalArm } from "../SurvivalResultsSection";
import i18n from "../../../i18n";
import { changeValue, click, findButton, flushEffects, renderIntoDocument } from "../../../test/dom";

describe("parseSurvivalArm", () => {
  it("parses durations with explicit event / censor flags", () => {
    expect(parseSurvivalArm("6 1\n6 0\n7 1")).toEqual({
      durations: [6, 6, 7],
      events_observed: [true, false, true]
    });
  });

  it("treats a bare duration as an observed event", () => {
    expect(parseSurvivalArm("5\n8")).toEqual({
      durations: [5, 8],
      events_observed: [true, true]
    });
  });

  it("rejects empty input, negative durations, and non 0/1 flags", () => {
    expect(parseSurvivalArm("")).toBeNull();
    expect(parseSurvivalArm("-1 1")).toBeNull();
    expect(parseSurvivalArm("5 2")).toBeNull();
    expect(parseSurvivalArm("x 1")).toBeNull();
  });
});

describe("buildSurvivalSeries", () => {
  it("merges both arms onto a shared carry-forward timeline starting at S(0)=1", () => {
    const control = [{ time: 2, survival: 0.8, at_risk: 5, n_events: 1, std_error: 0, ci_lower: 0, ci_upper: 1 }];
    const treatment = [{ time: 3, survival: 0.9, at_risk: 10, n_events: 1, std_error: 0, ci_lower: 0, ci_upper: 1 }];
    expect(buildSurvivalSeries(control, treatment)).toEqual([
      { time: 0, control: 1, treatment: 1 },
      { time: 2, control: 0.8, treatment: 1 },
      { time: 3, control: 0.8, treatment: 0.9 }
    ]);
  });
});

describe("SurvivalResultsSection", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the survival form with control and treatment inputs", async () => {
    const view = await renderIntoDocument(<SurvivalResultsSection />);
    try {
      await flushEffects();
      expect(view.container.textContent).toContain("Survival curves (log-rank)");
      expect(view.container.querySelectorAll("textarea").length).toBe(2);
      expect(findButton(view.container, "Run log-rank test")).toBeTruthy();
    } finally {
      await view.unmount();
    }
  });

  it("posts both arms and renders the log-rank result with the Kaplan–Meier curve", async () => {
    const response = {
      chi_square: 16.7929,
      degrees_of_freedom: 1,
      p_value: 0.000042,
      is_significant: true,
      observed_control: 21,
      expected_control: 10.7495,
      observed_treatment: 9,
      expected_treatment: 19.2505,
      n_control: 21,
      n_treatment: 21,
      control_curve: [
        { time: 1, survival: 0.904762, at_risk: 21, n_events: 2, std_error: 0.064, ci_lower: 0.78, ci_upper: 1 }
      ],
      treatment_curve: [
        { time: 6, survival: 0.857143, at_risk: 21, n_events: 3, std_error: 0.07636, ci_lower: 0.7075, ci_upper: 1 }
      ],
      verdict: "Survival curves differ at alpha=0.050",
      interpretation: "Log-rank chi-square 16.7929 on 1 degree of freedom..."
    };
    const fetchMock = vi.fn(async (..._args: unknown[]) => ({ ok: true, json: async () => response }));
    vi.stubGlobal("fetch", fetchMock);

    const view = await renderIntoDocument(<SurvivalResultsSection />);
    try {
      await flushEffects();
      const [controlArea, treatmentArea] = Array.from(view.container.querySelectorAll("textarea"));
      await changeValue(controlArea as HTMLTextAreaElement, "1 1\n2 1");
      await changeValue(treatmentArea as HTMLTextAreaElement, "6 1\n6 0");

      await click(findButton(view.container, "Run log-rank test"));
      await flushEffects();

      expect(fetchMock).toHaveBeenCalledTimes(1);
      const [url, requestInit] = fetchMock.mock.calls[0] as [string, RequestInit];
      expect(String(url)).toContain("/api/v1/results/survival");
      const body = JSON.parse(String(requestInit.body));
      expect(body.control_arm.durations).toEqual([1, 2]);
      expect(body.treatment_arm.events_observed).toEqual([true, false]);
      expect(body.alpha).toBe(0.05);

      expect(view.container.textContent).toContain("Survival curves differ");
      expect(view.container.textContent).toContain("16.7929");
      // the Kaplan–Meier chart renders as an accessible role="img" region
      expect(view.container.querySelector('[role="img"]')).not.toBeNull();
      // and the per-arm step-point data table equivalents render
      expect(view.container.querySelectorAll("table").length).toBe(2);
    } finally {
      await view.unmount();
    }
  });

  it("shows a parse hint and does not call the API when an arm is empty", async () => {
    const fetchMock = vi.fn(async (..._args: unknown[]) => ({ ok: true, json: async () => ({}) }));
    vi.stubGlobal("fetch", fetchMock);

    const view = await renderIntoDocument(<SurvivalResultsSection />);
    try {
      await flushEffects();
      const [controlArea] = Array.from(view.container.querySelectorAll("textarea"));
      await changeValue(controlArea as HTMLTextAreaElement, "6 1");
      // treatment left empty

      await click(findButton(view.container, "Run log-rank test"));
      await flushEffects();

      expect(fetchMock).not.toHaveBeenCalled();
      expect(view.container.textContent).toContain("at least one subject per arm");
    } finally {
      await view.unmount();
    }
  });
});
