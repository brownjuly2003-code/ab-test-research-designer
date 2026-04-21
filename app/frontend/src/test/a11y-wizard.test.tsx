// @vitest-environment jsdom

import "vitest-axe/extend-expect";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";
import * as matchers from "vitest-axe/matchers";

vi.mock("../hooks/useCalculationPreview", () => ({
  useCalculationPreview: vi.fn(() => ({
    result: null,
    isLoading: false,
    error: null
  }))
}));

vi.mock("../components/ResultsPanel", () => ({
  default: function ResultsPanelMock() {
    return <div data-testid="results-panel-mock">Results panel</div>;
  }
}));

import WizardPanel from "../components/WizardPanel";
import { cloneInitialState, sections } from "../lib/experiment";
import { useAnalysisStore } from "../stores/analysisStore";
import { useDraftStore } from "../stores/draftStore";
import { useProjectStore } from "../stores/projectStore";
import { useWizardStore } from "../stores/wizardStore";
import { flushEffects, renderIntoDocument } from "./dom";

expect.extend(matchers);

const initialAnalysisState = useAnalysisStore.getState();
const initialDraftState = useDraftStore.getState();
const initialProjectState = useProjectStore.getState();
const initialWizardState = useWizardStore.getState();

type AxeMatcher = {
  toHaveNoViolations: () => void;
};

function seedWizardPanelState(step: number) {
  const form = cloneInitialState();
  form.project.project_name = "Checkout redesign";
  form.hypothesis.hypothesis_statement = "Shorter checkout improves conversion.";
  form.setup.expected_daily_traffic = 5000;
  form.metrics.primary_metric_name = "purchase_conversion";

  useDraftStore.setState({
    ...useDraftStore.getState(),
    draft: form,
    isDirty: false
  });
  useWizardStore.setState({
    ...useWizardStore.getState(),
    step,
    importingDraft: false
  });
  useProjectStore.setState({
    ...useProjectStore.getState(),
    activeProjectId: null,
    hasUnsavedChanges: false,
    canMutateBackend: true,
    backendMutationMessage: "",
    isSavingProject: false,
    loadingProjectHistory: false,
    activeProject: null,
    projectHistory: null,
    selectedHistoryRun: null,
    projectComparison: null,
    projectError: ""
  });
  useAnalysisStore.setState({
    ...useAnalysisStore.getState(),
    validationErrors: [],
    isAnalyzing: false,
    statusMessage: "",
    analysisError: "",
    results: {}
  });
}

describe("Wizard accessibility", () => {
  beforeEach(() => {
    document.documentElement.lang = "en";
    useAnalysisStore.setState(initialAnalysisState, true);
    useDraftStore.setState(initialDraftState, true);
    useProjectStore.setState(initialProjectState, true);
    useWizardStore.setState(initialWizardState, true);
  });

  afterEach(() => {
    useAnalysisStore.setState(initialAnalysisState, true);
    useDraftStore.setState(initialDraftState, true);
    useProjectStore.setState(initialProjectState, true);
    useWizardStore.setState(initialWizardState, true);
  });

  it("has no critical or serious accessibility violations on the Project step", async () => {
    seedWizardPanelState(0);
    const view = await renderIntoDocument(<WizardPanel />);
    try {
      await flushEffects();

      expect(view.container.querySelector("h2")?.textContent).toBe(sections[0]?.title);

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

  it("has no critical or serious accessibility violations on the Hypothesis step", async () => {
    seedWizardPanelState(1);
    const view = await renderIntoDocument(<WizardPanel />);
    try {
      await flushEffects();

      expect(view.container.querySelector("h2")?.textContent).toBe(sections[1]?.title);

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

  it("has no critical or serious accessibility violations on the Setup step", async () => {
    seedWizardPanelState(2);
    const view = await renderIntoDocument(<WizardPanel />);
    try {
      await flushEffects();

      expect(view.container.querySelector("h2")?.textContent).toBe(sections[2]?.title);

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

  it("has no critical or serious accessibility violations on the Metrics step", async () => {
    seedWizardPanelState(3);
    const view = await renderIntoDocument(<WizardPanel />);
    try {
      await flushEffects();

      expect(view.container.querySelector("h2")?.textContent).toBe(sections[3]?.title);

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

  it("has no critical or serious accessibility violations on the Constraints step", async () => {
    seedWizardPanelState(4);
    const view = await renderIntoDocument(<WizardPanel />);
    try {
      await flushEffects();

      expect(view.container.querySelector("h2")?.textContent).toBe(sections[4]?.title);

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

  it("has no critical or serious accessibility violations on the Review step", async () => {
    seedWizardPanelState(sections.length);
    const view = await renderIntoDocument(<WizardPanel />);
    try {
      await flushEffects();

      expect(view.container.querySelector("h2")?.textContent).toBe("Review inputs");

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
