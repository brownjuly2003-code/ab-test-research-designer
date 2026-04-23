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

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return {
    ...actual,
    listTemplatesRequest: vi.fn(),
    useTemplateRequest: vi.fn()
  };
});

import { buildApiPayload, cloneInitialState, sections } from "../lib/experiment";
import { listTemplatesRequest } from "../lib/api";
import { useAnalysisStore } from "../stores/analysisStore";
import { useDraftStore } from "../stores/draftStore";
import { useProjectStore } from "../stores/projectStore";
import { useWizardStore } from "../stores/wizardStore";
import { click, findButton, flushEffects, renderIntoDocument } from "../test/dom";
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

  it("renders at least 10 templates grouped by category in the wizard template picker", async () => {
    const payload = buildApiPayload(cloneInitialState());
    payload.project.project_name = "";
    vi.mocked(listTemplatesRequest).mockResolvedValueOnce([
      { id: "checkout_conversion", name: "Checkout Conversion", category: "Revenue", description: "Test checkout changes against conversion.", built_in: true, payload, tags: ["binary", "checkout"], usage_count: 0 },
      { id: "feature_adoption", name: "Feature Adoption", category: "Engagement", description: "Use this template to evaluate feature discoverability and adoption among existing users.", built_in: true, payload, tags: ["binary", "feature"], usage_count: 0 },
      { id: "latency_impact", name: "Latency Impact", category: "Performance", description: "Assess whether latency changes affect conversion or engagement outcomes.", built_in: true, payload, tags: ["continuous", "latency"], usage_count: 0 },
      { id: "onboarding_completion", name: "Onboarding Completion", category: "Engagement", description: "Measure whether onboarding changes improve completion rate for new accounts.", built_in: true, payload, tags: ["binary", "onboarding"], usage_count: 0 },
      { id: "pricing_sensitivity", name: "Pricing Sensitivity", category: "Revenue", description: "Evaluate price or packaging changes using revenue-oriented continuous metrics.", built_in: true, payload, tags: ["continuous", "pricing"], usage_count: 0 },
      { id: "email_campaign", name: "Email Campaign", category: "Marketing", description: "Test email subject line and preheader changes against click-through with deliverability guardrails.", built_in: true, payload, tags: ["binary", "email"], usage_count: 0 },
      { id: "push_notification_reactivation", name: "Push Notification Reactivation", category: "Lifecycle", description: "Evaluate reactivation push copy and timing for dormant mobile users over a 30-day return window.", built_in: true, payload, tags: ["binary", "push"], usage_count: 0 },
      { id: "trial_to_paid", name: "Trial to Paid", category: "SaaS Monetization", description: "Compare a 14-day versus 7-day trial onboarding path using monetization and activation outcomes.", built_in: true, payload, tags: ["continuous", "saas"], usage_count: 0 },
      { id: "search_ranking_ctr", name: "Search Ranking CTR", category: "Search Discovery", description: "Measure how search rank-fusion tuning changes result-page click-through at high query volume.", built_in: true, payload, tags: ["binary", "search"], usage_count: 0 },
      { id: "app_onboarding_drop_off", name: "App Onboarding Drop-off", category: "Mobile Activation", description: "Test a 3-step mobile onboarding against the legacy 5-step flow using 24-hour activation as the primary outcome.", built_in: true, payload, tags: ["binary", "mobile"], usage_count: 0 }
    ]);
    seedWizardPanelState();

    const view = await renderIntoDocument(<WizardPanel />);
    try {
      await flushEffects();
      await click(findButton(view.container, "Start from template"));
      await flushEffects();

      const dialog = document.querySelector('[role="dialog"]');
      if (!(dialog instanceof HTMLDivElement)) {
        throw new Error("Template gallery dialog was not rendered");
      }

      expect(dialog.textContent).toContain("Experiment templates");
      expect(dialog.querySelectorAll('button[aria-label^="Use template "]')).toHaveLength(10);
      expect(dialog.textContent).toContain("Revenue");
      expect(dialog.textContent).toContain("Marketing");
      expect(dialog.textContent).toContain("SaaS Monetization");
      expect(dialog.textContent).toContain("Mobile Activation");
      expect(dialog.querySelectorAll("section").length).toBeGreaterThanOrEqual(6);
    } finally {
      await view.unmount();
    }
  });
});
