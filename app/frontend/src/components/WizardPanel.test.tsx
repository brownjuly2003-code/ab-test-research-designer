// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../hooks/useCalculationPreview", () => ({
  useCalculationPreview: vi.fn(() => ({
    result: null,
    isLoading: false,
    error: null
  }))
}));

vi.mock("./ResultsPanel", () => ({
  default: function ResultsPanelMock() {
    return <div data-testid="results-panel-mock">Results panel</div>;
  }
}));

import { cloneInitialState, sections } from "../lib/experiment";
import { useAnalysisStore } from "../stores/analysisStore";
import { useDraftStore } from "../stores/draftStore";
import { useProjectStore } from "../stores/projectStore";
import { useWizardStore } from "../stores/wizardStore";
import { flushEffects, renderIntoDocument } from "../test/dom";
import WizardPanel from "./WizardPanel";
import WizardReviewStep from "./WizardReviewStep";

const initialAnalysisState = useAnalysisStore.getState();
const initialDraftState = useDraftStore.getState();
const initialProjectState = useProjectStore.getState();
const initialWizardState = useWizardStore.getState();

function createReviewStepProps(overrides: Partial<Parameters<typeof WizardReviewStep>[0]> = {}): Parameters<typeof WizardReviewStep>[0] {
  return {
    form: cloneInitialState(),
    activeProjectId: "p-1",
    hasUnsavedChanges: true,
    canMutateBackend: false,
    backendMutationMessage: "Backend is running in read-only API mode.",
    validationErrors: ["Project name is required."],
    importingDraft: false,
    loading: false,
    saving: false,
    onBack: vi.fn(),
    onSave: vi.fn(),
    onStartNew: vi.fn(),
    onImportDraft: vi.fn(),
    onExportDraft: vi.fn(),
    onRunAnalysis: vi.fn(),
    ...overrides
  };
}

function seedWizardPanelState(overrides: {
  form?: ReturnType<typeof cloneInitialState>;
  step?: number;
  activeProjectId?: string | null;
  hasUnsavedChanges?: boolean;
  canMutateBackend?: boolean;
  backendMutationMessage?: string;
  validationErrors?: string[];
} = {}) {
  useDraftStore.setState({
    ...useDraftStore.getState(),
    draft: overrides.form ?? cloneInitialState(),
    isDirty: overrides.hasUnsavedChanges ?? false
  });
  useWizardStore.setState({
    ...useWizardStore.getState(),
    step: overrides.step ?? 0,
    importingDraft: false
  });
  useProjectStore.setState({
    ...useProjectStore.getState(),
    activeProjectId: overrides.activeProjectId ?? null,
    hasUnsavedChanges: overrides.hasUnsavedChanges ?? false,
    canMutateBackend: overrides.canMutateBackend ?? true,
    backendMutationMessage: overrides.backendMutationMessage ?? "",
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
    validationErrors: overrides.validationErrors ?? [],
    isAnalyzing: false,
    statusMessage: "",
    analysisError: "",
    results: {}
  });
}

describe("Wizard snapshots", () => {
  beforeEach(() => {
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

  it("renders the draft-step wizard shell consistently", async () => {
    seedWizardPanelState();
    const view = await renderIntoDocument(<WizardPanel />);
    try {
      await flushEffects();

      expect(view.container.innerHTML).toMatchSnapshot();
    } finally {
      await view.unmount();
    }
  });

  it("renders the review step consistently with saved-project warnings", async () => {
    const form = cloneInitialState();
    form.project.project_name = "";

    const view = await renderIntoDocument(
      <WizardReviewStep
        {...createReviewStepProps({
          form
        })}
      />
    );
    try {
      await flushEffects();

      expect(view.container.innerHTML).toMatchSnapshot();
    } finally {
      await view.unmount();
    }
  });

  it("renders WizardPanel review mode consistently", async () => {
    seedWizardPanelState({
      step: sections.length,
      activeProjectId: "p-1",
      hasUnsavedChanges: true,
      canMutateBackend: false,
      backendMutationMessage: "Backend is running in read-only API mode.",
      validationErrors: ["Project name is required."]
    });
    const view = await renderIntoDocument(<WizardPanel />);
    try {
      await flushEffects();

      expect(view.container.innerHTML).toMatchSnapshot();
    } finally {
      await view.unmount();
    }
  });

  it("reads wizard state directly from stores without prop drilling", async () => {
    const form = cloneInitialState();
    form.project.project_name = "Store-backed wizard";
    seedWizardPanelState({
      form,
      step: 0,
      activeProjectId: "p-1",
      hasUnsavedChanges: true
    });

    const view = await renderIntoDocument(<WizardPanel />);
    try {
      await flushEffects();

      expect(view.container.textContent).toContain("Editing saved project");
      expect(view.container.textContent).toContain("Project id: p-1");
      const projectNameInput = view.container.querySelector("#project-project_name");
      if (!(projectNameInput instanceof HTMLInputElement)) {
        throw new Error("Project name input was not rendered");
      }

      expect(projectNameInput.value).toBe("Store-backed wizard");
    } finally {
      await view.unmount();
    }
  });
});
