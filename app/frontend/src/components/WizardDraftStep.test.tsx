// @vitest-environment jsdom

import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../hooks/useCalculationPreview", () => ({
  useCalculationPreview: vi.fn()
}));

import { useCalculationPreview } from "../hooks/useCalculationPreview";
import {
  cloneInitialState,
  sections,
  setSectionFieldValue,
  type DraftFieldValue,
  type FullPayload,
  type FullPayloadSectionKey
} from "../lib/experiment";
import { changeValue, click, flushEffects, renderIntoDocument } from "../test/dom";
import WizardDraftStep from "./WizardDraftStep";

function buildPreviewResult(overrides: Record<string, unknown> = {}) {
  return {
    calculation_summary: {
      metric_type: "binary" as const,
      baseline_value: 0.042,
      mde_pct: 5,
      mde_absolute: 0.0021,
      alpha: 0.05,
      power: 0.8
    },
    results: {
      sample_size_per_variant: 100,
      total_sample_size: 200,
      effective_daily_traffic: 5000,
      estimated_duration_days: 12
    },
    assumptions: [],
    warnings: [],
    bonferroni_note: null,
    cuped_std: null,
    cuped_sample_size_per_variant: null,
    cuped_variance_reduction_pct: null,
    cuped_duration_days: null,
    ...overrides
  };
}

function getSection(sectionKey: FullPayloadSectionKey) {
  const section = sections.find((item) => item.section === sectionKey);
  if (!section) {
    throw new Error(`Section not found: ${sectionKey}`);
  }
  return section;
}

function createStepProps(currentSection: FullPayloadSectionKey, form: FullPayload) {
  return {
    current: getSection(currentSection),
    form,
    canGoBack: true,
    activeProjectId: null,
    hasUnsavedChanges: false,
    canMutateBackend: true,
    backendMutationMessage: "",
    validationErrors: [],
    importingDraft: false,
    loading: false,
    saving: false,
    onUpdateSection: () => {},
    onBack: () => {},
    onNext: () => {},
    onSave: () => {},
    onStartNew: () => {},
    onOpenTemplateGallery: () => {},
    onImportDraft: () => {},
    onExportDraft: () => {}
  };
}

function WizardDraftStepHarness() {
  return <WizardDraftStepHarnessWithSection currentSection="metrics" />;
}

function WizardDraftStepHarnessWithSection({
  currentSection
}: {
  currentSection: FullPayloadSectionKey;
}) {
  const [form, setForm] = useState(cloneInitialState());

  function handleUpdate(section: FullPayloadSectionKey, key: string, value: DraftFieldValue) {
    setForm((current) => setSectionFieldValue(current, section, key, value));
  }

  return (
    <WizardDraftStep
      current={getSection(currentSection)}
      form={form}
      canGoBack={true}
      activeProjectId={null}
      hasUnsavedChanges={false}
      canMutateBackend={true}
      backendMutationMessage=""
      validationErrors={[]}
      importingDraft={false}
      loading={false}
      saving={false}
      onUpdateSection={handleUpdate}
      onBack={() => {}}
      onNext={() => {}}
      onSave={() => {}}
      onStartNew={() => {}}
      onOpenTemplateGallery={() => {}}
      onImportDraft={() => {}}
      onExportDraft={() => {}}
    />
  );
}

describe("WizardDraftStep", () => {
  beforeEach(() => {
    vi.mocked(useCalculationPreview).mockReturnValue({
      result: buildPreviewResult(),
      isLoading: false,
      error: null
    });
  });

  it("shows live preview only on setup and metrics sections", async () => {
    const form = cloneInitialState();
    const view = await renderIntoDocument(<WizardDraftStep {...createStepProps("setup", form)} />);
    try {
      await flushEffects();
      expect(view.container.querySelector(".live-preview-panel")).not.toBeNull();

      await view.rerender(<WizardDraftStep {...createStepProps("metrics", form)} />);
      await flushEffects();
      expect(view.container.querySelector(".live-preview-panel")).not.toBeNull();

      await view.rerender(<WizardDraftStep {...createStepProps("constraints", form)} />);
      await flushEffects();
      expect(view.container.querySelector(".live-preview-panel")).toBeNull();
    } finally {
      await view.unmount();
    }
  });

  it("keeps MDE and power slider controls synchronized", async () => {
    vi.mocked(useCalculationPreview).mockReturnValue({
      result: null,
      isLoading: false,
      error: null
    });

    const view = await renderIntoDocument(<WizardDraftStepHarness />);
    try {
      await flushEffects();

      const mdeSlider = view.container.querySelector('input[aria-label="MDE % slider"]');
      const mdeNumber = view.container.querySelector("#metrics-mde_pct");

      if (!(mdeSlider instanceof HTMLInputElement)) {
        throw new Error("MDE slider was not rendered");
      }
      if (!(mdeNumber instanceof HTMLInputElement)) {
        throw new Error("MDE number input was not rendered");
      }

      await changeValue(mdeSlider, "7.5");
      await flushEffects();
      expect(mdeNumber.value).toBe("7.5");

      await changeValue(mdeNumber, "9.5");
      await flushEffects();
      expect(mdeSlider.value).toBe("9.5");
    } finally {
      await view.unmount();
    }
  });

  it("adds guardrail rows, toggles metric-specific inputs, and hides the add button at three items", async () => {
    vi.mocked(useCalculationPreview).mockReturnValue({
      result: null,
      isLoading: false,
      error: null
    });

    const view = await renderIntoDocument(<WizardDraftStepHarness />);
    try {
      await flushEffects();

      expect(view.container.textContent).toContain("Guardrail metrics");
      const firstGuardrailName = view.container.querySelector("#guardrail-metric-name-1");
      if (!(firstGuardrailName instanceof HTMLInputElement)) {
        throw new Error("First guardrail name input was not rendered");
      }

      expect(firstGuardrailName.value).toBe("Payment error rate");

      const addButton = Array.from(view.container.querySelectorAll("button")).find(
        (button) => button.textContent?.includes("Add guardrail metric")
      );
      if (!(addButton instanceof HTMLButtonElement)) {
        throw new Error("Add guardrail metric button was not rendered");
      }

      await click(addButton);
      await flushEffects();

      const metricTypeInputs = Array.from(
        view.container.querySelectorAll('select[aria-label^="Guardrail metric type"]')
      );
      const lastMetricType = metricTypeInputs[metricTypeInputs.length - 1];
      if (!(lastMetricType instanceof HTMLSelectElement)) {
        throw new Error("Guardrail metric type select was not rendered");
      }

      await changeValue(lastMetricType, "continuous");
      await flushEffects();

      expect(view.container.querySelector('input[aria-label="Guardrail baseline mean 3"]')).not.toBeNull();
      expect(view.container.querySelector('input[aria-label="Guardrail std dev 3"]')).not.toBeNull();
      expect(view.container.textContent).not.toContain("Add guardrail metric");
    } finally {
      await view.unmount();
    }
  });

  it("offers metric-specific planned tests and reveals the TOST margin input", async () => {
    vi.mocked(useCalculationPreview).mockReturnValue({
      result: null,
      isLoading: false,
      error: null
    });

    const view = await renderIntoDocument(<WizardDraftStepHarness />);
    try {
      await flushEffects();

      // Binary default: z-test + Fisher's exact, no margin input.
      const binaryPlannedTest = view.container.querySelector("#metrics-planned_test");
      if (!(binaryPlannedTest instanceof HTMLSelectElement)) {
        throw new Error("Planned test select was not rendered for the binary metric");
      }
      const binaryOptions = Array.from(binaryPlannedTest.options).map((option) => option.value);
      expect(binaryOptions).toEqual(["z_test", "fisher_exact"]);
      expect(view.container.querySelector("#metrics-equivalence_margin_pct")).toBeNull();

      const metricType = view.container.querySelector("#metrics-metric_type");
      if (!(metricType instanceof HTMLSelectElement)) {
        throw new Error("Metric type select was not rendered");
      }
      await changeValue(metricType, "continuous");
      await flushEffects();

      const continuousPlannedTest = view.container.querySelector("#metrics-planned_test");
      if (!(continuousPlannedTest instanceof HTMLSelectElement)) {
        throw new Error("Planned test select was not rendered for the continuous metric");
      }
      const continuousOptions = Array.from(continuousPlannedTest.options).map(
        (option) => option.value
      );
      expect(continuousOptions).toEqual(["z_test", "mann_whitney", "tost"]);

      // The equivalence margin appears only once TOST is chosen.
      expect(view.container.querySelector("#metrics-equivalence_margin_pct")).toBeNull();
      await changeValue(continuousPlannedTest, "tost");
      await flushEffects();
      expect(view.container.querySelector("#metrics-equivalence_margin_pct")).not.toBeNull();

      // Switching the metric type falls back to the default z plan (no stale rank/TOST choice).
      await changeValue(metricType, "binary");
      await flushEffects();
      const resetPlannedTest = view.container.querySelector("#metrics-planned_test");
      if (!(resetPlannedTest instanceof HTMLSelectElement)) {
        throw new Error("Planned test select disappeared after switching back to binary");
      }
      expect(resetPlannedTest.value).toBe("z_test");
      expect(view.container.querySelector("#metrics-equivalence_margin_pct")).toBeNull();
    } finally {
      await view.unmount();
    }
  });

  it("edits the guardrail harm-direction and tolerance-margin and persists them", async () => {
    vi.mocked(useCalculationPreview).mockReturnValue({
      result: null,
      isLoading: false,
      error: null
    });

    const view = await renderIntoDocument(<WizardDraftStepHarness />);
    try {
      await flushEffects();

      const direction = view.container.querySelector("#guardrail-direction-1");
      if (!(direction instanceof HTMLSelectElement)) {
        throw new Error("Guardrail direction select was not rendered");
      }
      // Defaults to the classic latency / error guardrail (an increase is harmful).
      expect(direction.value).toBe("increase_is_bad");

      await changeValue(direction, "decrease_is_bad");
      await flushEffects();
      const directionAfter = view.container.querySelector("#guardrail-direction-1");
      if (!(directionAfter instanceof HTMLSelectElement)) {
        throw new Error("Guardrail direction select disappeared after edit");
      }
      expect(directionAfter.value).toBe("decrease_is_bad");

      const margin = view.container.querySelector("#guardrail-margin-1");
      if (!(margin instanceof HTMLInputElement)) {
        throw new Error("Guardrail margin input was not rendered");
      }
      await changeValue(margin, "5");
      await flushEffects();
      const marginAfter = view.container.querySelector("#guardrail-margin-1");
      if (!(marginAfter instanceof HTMLInputElement)) {
        throw new Error("Guardrail margin input disappeared after edit");
      }
      expect(marginAfter.value).toBe("5");
    } finally {
      await view.unmount();
    }
  });

  it("renders interim analyses control on constraints step", async () => {
    vi.mocked(useCalculationPreview).mockReturnValue({
      result: null,
      isLoading: false,
      error: null
    });

    const form = cloneInitialState();
    const view = await renderIntoDocument(<WizardDraftStep {...createStepProps("constraints", form)} />);
    try {
      await flushEffects();

      expect(view.container.textContent).toContain("Interim analyses");
      const select = view.container.querySelector("#constraints-n_looks");
      if (!(select instanceof HTMLSelectElement)) {
        throw new Error("Interim analyses select was not rendered");
      }

      expect(select.value).toBe("1");
    } finally {
      await view.unmount();
    }
  });

  it("shows frequentist controls by default on constraints and switches to bayesian precision controls", async () => {
    vi.mocked(useCalculationPreview).mockReturnValue({
      result: null,
      isLoading: false,
      error: null
    });

    const view = await renderIntoDocument(
      <WizardDraftStepHarnessWithSection currentSection="constraints" />
    );
    try {
      await flushEffects();

      expect(view.container.textContent).toContain("Analysis framework");
      expect(view.container.querySelector("#metrics-alpha")).not.toBeNull();
      expect(view.container.querySelector("#metrics-power")).not.toBeNull();
      expect(view.container.querySelector("#constraints-desired_precision")).toBeNull();

      const bayesianRadio = view.container.querySelector('input[name="analysis_mode"][value="bayesian"]');
      if (!(bayesianRadio instanceof HTMLInputElement)) {
        throw new Error("Bayesian mode radio was not rendered");
      }

      await click(bayesianRadio);
      await flushEffects();

      expect(view.container.querySelector("#metrics-alpha")).toBeNull();
      expect(view.container.querySelector("#metrics-power")).toBeNull();
      expect(view.container.querySelector("#constraints-desired_precision")).not.toBeNull();
      expect(view.container.querySelector("#constraints-credibility")).not.toBeNull();
    } finally {
      await view.unmount();
    }
  });

  it("shows CUPED controls only for continuous metrics and reveals inputs after enabling the toggle", async () => {
    vi.mocked(useCalculationPreview).mockReturnValue({
      result: null,
      isLoading: false,
      error: null
    });

    const view = await renderIntoDocument(<WizardDraftStepHarness />);
    try {
      await flushEffects();

      expect(view.container.textContent).not.toContain("Enable CUPED variance reduction");

      const metricType = view.container.querySelector("#metrics-metric_type");
      if (!(metricType instanceof HTMLSelectElement)) {
        throw new Error("Metric type select was not rendered");
      }

      await changeValue(metricType, "continuous");
      await flushEffects();

      expect(view.container.textContent).toContain("Enable CUPED variance reduction");

      const toggle = view.container.querySelector('input[type="checkbox"]');
      if (!(toggle instanceof HTMLInputElement)) {
        throw new Error("CUPED toggle was not rendered");
      }

      await click(toggle);
      await flushEffects();

      expect(view.container.textContent).toContain("Pre-experiment std dev");
      expect(view.container.textContent).toContain("Correlation with outcome");
    } finally {
      await view.unmount();
    }
  });

  it("renders CUPED preview details when the live calculation includes a CUPED comparison", async () => {
    const form = cloneInitialState();
    form.metrics.metric_type = "continuous";
    form.metrics.std_dev = 12;
    vi.mocked(useCalculationPreview).mockReturnValue({
      result: buildPreviewResult({
        calculation_summary: {
          metric_type: "continuous",
          baseline_value: 45,
          mde_pct: 4.4444,
          mde_absolute: 2,
          alpha: 0.05,
          power: 0.8
        },
        cuped_std: 10.3923,
        cuped_sample_size_per_variant: 75,
        cuped_variance_reduction_pct: 25,
        cuped_duration_days: 8
      }),
      isLoading: false,
      error: null
    });

    const view = await renderIntoDocument(<WizardDraftStep {...createStepProps("metrics", form)} />);
    try {
      await flushEffects();

      expect(view.container.textContent).toContain("CUPED sample size");
      expect(view.container.textContent).toContain("25% variance reduction");
    } finally {
      await view.unmount();
    }
  });
});
