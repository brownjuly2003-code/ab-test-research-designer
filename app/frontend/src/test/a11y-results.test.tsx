// @vitest-environment jsdom

import "vitest-axe/extend-expect";

vi.mock("recharts", () => import("./recharts-stub"));

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";
import * as matchers from "vitest-axe/matchers";

import ResultsPanel from "../components/ResultsPanel";
import AiAdviceSection from "../components/results/AiAdviceSection";
import ComparisonSection from "../components/results/ComparisonSection";
import ExperimentDesignSection from "../components/results/ExperimentDesignSection";
import MetricsPlanSection from "../components/results/MetricsPlanSection";
import ObservedResultsSection from "../components/results/ObservedResultsSection";
import PowerCurveSection from "../components/results/PowerCurveSection";
import RisksSection from "../components/results/RisksSection";
import SensitivitySection from "../components/results/SensitivitySection";
import SequentialDesignSection from "../components/results/SequentialDesignSection";
import SrmCheckSection from "../components/results/SrmCheckSection";
import WarningsSection from "../components/results/WarningsSection";
import {
  buildAnalysisResult,
  buildProjectComparison,
  defaultSensitivityData,
  resetResultsStores,
  seedResultsStores
} from "../components/results/__tests__/resultsTestUtils";
import { flushEffects, renderIntoDocument } from "./dom";

expect.extend(matchers);

type AxeMatcher = {
  toHaveNoViolations: () => void;
};

describe("Results accessibility", () => {
  beforeEach(() => {
    document.documentElement.lang = "en";
    resetResultsStores();
    seedResultsStores({
      analysis: buildAnalysisResult({ metricType: "continuous" }),
      projectComparison: buildProjectComparison()
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        json: async () => defaultSensitivityData,
        blob: async () => new Blob(["report"], { type: "text/html" }),
        headers: new Headers()
      }))
    );
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
    resetResultsStores();
  });

  it("has no critical or serious accessibility violations in the full results panel", async () => {
    const view = await renderIntoDocument(<ResultsPanel />);
    try {
      await flushEffects();
      await flushEffects();

      const results = await axe(view.container);

      (expect({
        ...results,
        violations: results.violations.filter(
          (violation) => violation.impact === "critical" || violation.impact === "serious"
        )
      }) as unknown as AxeMatcher).toHaveNoViolations();
    } finally {
      await view.unmount();
    }
  }, 20000);

  it("has no critical or serious accessibility violations in PowerCurveSection", async () => {
    const view = await renderIntoDocument(
      <PowerCurveSection
        sensitivityData={defaultSensitivityData}
        sensitivityLoading={false}
        sensitivityUnavailableMessage="Unavailable"
      />
    );
    try {
      await flushEffects();
      await flushEffects();

      const results = await axe(view.container);

      (expect({
        ...results,
        violations: results.violations.filter(
          (violation) => violation.impact === "critical" || violation.impact === "serious"
        )
      }) as unknown as AxeMatcher).toHaveNoViolations();
    } finally {
      await view.unmount();
    }
  });

  it("has no critical or serious accessibility violations in SensitivitySection", async () => {
    const view = await renderIntoDocument(
      <SensitivitySection
        sensitivityData={defaultSensitivityData}
        sensitivityLoading={false}
        sensitivityUnavailableMessage="Unavailable"
        standaloneExporting={false}
        standaloneExportError=""
        canExportPdf={true}
        onExportReport={vi.fn()}
        onExportPdf={vi.fn()}
        onExportProjectData={vi.fn()}
        onExportStandalone={vi.fn()}
      />
    );
    try {
      await flushEffects();

      const results = await axe(view.container);

      (expect({
        ...results,
        violations: results.violations.filter(
          (violation) => violation.impact === "critical" || violation.impact === "serious"
        )
      }) as unknown as AxeMatcher).toHaveNoViolations();
    } finally {
      await view.unmount();
    }
  });

  it("has no critical or serious accessibility violations in SrmCheckSection", async () => {
    const view = await renderIntoDocument(<SrmCheckSection />);
    try {
      await flushEffects();

      const results = await axe(view.container);

      (expect({
        ...results,
        violations: results.violations.filter(
          (violation) => violation.impact === "critical" || violation.impact === "serious"
        )
      }) as unknown as AxeMatcher).toHaveNoViolations();
    } finally {
      await view.unmount();
    }
  });

  it("has no critical or serious accessibility violations in ObservedResultsSection", async () => {
    const view = await renderIntoDocument(<ObservedResultsSection onResultsAnalysisChange={vi.fn()} />);
    try {
      await flushEffects();

      const results = await axe(view.container);

      (expect({
        ...results,
        violations: results.violations.filter(
          (violation) => violation.impact === "critical" || violation.impact === "serious"
        )
      }) as unknown as AxeMatcher).toHaveNoViolations();
    } finally {
      await view.unmount();
    }
  });

  it("has no critical or serious accessibility violations in AiAdviceSection", async () => {
    const view = await renderIntoDocument(<AiAdviceSection />);
    try {
      await flushEffects();

      const results = await axe(view.container);

      (expect({
        ...results,
        violations: results.violations.filter(
          (violation) => violation.impact === "critical" || violation.impact === "serious"
        )
      }) as unknown as AxeMatcher).toHaveNoViolations();
    } finally {
      await view.unmount();
    }
  });

  it("has no critical or serious accessibility violations in WarningsSection", async () => {
    const view = await renderIntoDocument(<WarningsSection />);
    try {
      await flushEffects();

      const results = await axe(view.container);

      (expect({
        ...results,
        violations: results.violations.filter(
          (violation) => violation.impact === "critical" || violation.impact === "serious"
        )
      }) as unknown as AxeMatcher).toHaveNoViolations();
    } finally {
      await view.unmount();
    }
  });

  it("has no critical or serious accessibility violations in RisksSection", async () => {
    const view = await renderIntoDocument(<RisksSection />);
    try {
      await flushEffects();

      const results = await axe(view.container);

      (expect({
        ...results,
        violations: results.violations.filter(
          (violation) => violation.impact === "critical" || violation.impact === "serious"
        )
      }) as unknown as AxeMatcher).toHaveNoViolations();
    } finally {
      await view.unmount();
    }
  });

  it("has no critical or serious accessibility violations in ExperimentDesignSection", async () => {
    const view = await renderIntoDocument(<ExperimentDesignSection />);
    try {
      await flushEffects();

      const results = await axe(view.container);

      (expect({
        ...results,
        violations: results.violations.filter(
          (violation) => violation.impact === "critical" || violation.impact === "serious"
        )
      }) as unknown as AxeMatcher).toHaveNoViolations();
    } finally {
      await view.unmount();
    }
  });

  it("has no critical or serious accessibility violations in MetricsPlanSection", async () => {
    const view = await renderIntoDocument(<MetricsPlanSection />);
    try {
      await flushEffects();

      const results = await axe(view.container);

      (expect({
        ...results,
        violations: results.violations.filter(
          (violation) => violation.impact === "critical" || violation.impact === "serious"
        )
      }) as unknown as AxeMatcher).toHaveNoViolations();
    } finally {
      await view.unmount();
    }
  });

  it("has no critical or serious accessibility violations in ComparisonSection", async () => {
    const view = await renderIntoDocument(<ComparisonSection />);
    try {
      await flushEffects();

      const results = await axe(view.container);

      (expect({
        ...results,
        violations: results.violations.filter(
          (violation) => violation.impact === "critical" || violation.impact === "serious"
        )
      }) as unknown as AxeMatcher).toHaveNoViolations();
    } finally {
      await view.unmount();
    }
  });

  it("has no critical or serious accessibility violations in SequentialDesignSection", async () => {
    const view = await renderIntoDocument(<SequentialDesignSection />);
    try {
      await flushEffects();

      const results = await axe(view.container);

      (expect({
        ...results,
        violations: results.violations.filter(
          (violation) => violation.impact === "critical" || violation.impact === "serious"
        )
      }) as unknown as AxeMatcher).toHaveNoViolations();
    } finally {
      await view.unmount();
    }
  });
});
