// @vitest-environment jsdom

import { describe, expect, it, vi } from "vitest";

import { cloneInitialState } from "../lib/experiment";
import { flushEffects, renderIntoDocument } from "../test/dom";
import WizardReviewStep from "./WizardReviewStep";

describe("WizardReviewStep", () => {
  it("renders the review step consistently for a saved project with validation warnings", async () => {
    const form = cloneInitialState();
    form.project.project_name = "";

    const view = await renderIntoDocument(
      <WizardReviewStep
        form={form}
        activeProjectId="p-1"
        hasUnsavedChanges={true}
        canMutateBackend={false}
        backendMutationMessage="Backend is running in read-only API mode."
        validationErrors={["Project name is required."]}
        importingDraft={false}
        loading={false}
        saving={false}
        onBack={vi.fn()}
        onSave={vi.fn()}
        onStartNew={vi.fn()}
        onImportDraft={vi.fn()}
        onExportDraft={vi.fn()}
        onRunAnalysis={vi.fn()}
      />
    );
    try {
      await flushEffects();

      expect(view.container.innerHTML).toMatchInlineSnapshot(`"<div class="_section_f04639 _step-content_f04639"><h2 tabindex="-1">Review inputs</h2><div class="note"><strong>Reviewing a saved project</strong><div class="muted">Unsaved changes are present. Check the values below before saving or running the deterministic backend flow.</div></div><div class="status" role="alert" aria-live="polite"><strong>Fix these fields before saving or running analysis:</strong><ul class="list"><li>Project name is required.</li></ul></div><div class="callout"><span>Backend is running in read-only API mode.</span></div><div class="two-col"><div class="card"><h3>Project context</h3><ul class="list"><li><strong>Project name:</strong> -</li><li><strong>Domain:</strong> e-commerce</li><li><strong>Product type:</strong> web app</li><li><strong>Platform:</strong> web</li><li><strong>Market:</strong> US</li><li><strong>Project description:</strong> We want to test a simplified checkout flow.</li></ul></div><div class="card"><h3>Hypothesis</h3><ul class="list"><li><strong>Change description:</strong> Reduce checkout from 4 steps to 2</li><li><strong>Target audience:</strong> new users on web</li><li><strong>Business problem:</strong> checkout abandonment is high</li><li><strong>Hypothesis statement:</strong> If we simplify checkout, purchase conversion will increase because the flow becomes easier.</li><li><strong>What to validate:</strong> impact on conversion</li><li><strong>Desired result:</strong> statistically meaningful uplift</li></ul></div><div class="card"><h3>Experiment setup</h3><ul class="list"><li><strong>Experiment type:</strong> ab</li><li><strong>Randomization unit:</strong> user</li><li><strong>Traffic split:</strong> 50,50</li><li><strong>Expected daily traffic:</strong> 12000</li><li><strong>Audience share in test:</strong> 0.6</li><li><strong>Variants count:</strong> 2</li><li><strong>Inclusion criteria:</strong> new users only</li><li><strong>Exclusion criteria:</strong> internal staff</li></ul></div><div class="card"><h3>Metrics</h3><ul class="list"><li><strong>Primary metric:</strong> purchase_conversion</li><li><strong>Metric type:</strong> binary</li><li><strong>Baseline value:</strong> 0.042</li><li><strong>Expected uplift %:</strong> 8</li><li><strong>MDE %:</strong> 5</li><li><strong>Secondary metrics:</strong> add_to_cart_rate</li><li><strong>Guardrail metrics:</strong> Payment error rate (binary, baseline 2.4%); Refund value (continuous, mean 18, std dev 6.5)</li></ul></div><div class="card"><h3>Constraints</h3><ul class="list"><li><strong>Seasonality present:</strong> Yes</li><li><strong>Active campaigns present:</strong> No</li><li><strong>Returning users present:</strong> Yes</li><li><strong>Analysis framework:</strong> frequentist</li><li><strong>Alpha:</strong> 0.05</li><li><strong>Power:</strong> 0.8</li><li><strong>Interference risk:</strong> medium</li><li><strong>Technical constraints:</strong> legacy event logging</li><li><strong>Legal / ethics constraints:</strong> none</li><li><strong>Known risks:</strong> tracking quality</li><li><strong>Deadline pressure:</strong> medium</li><li><strong>Long test possible:</strong> Yes</li><li><strong>AI context:</strong> Previous tests showed mixed results. Team worries about event quality and segmentation.</li></ul></div></div><div class="actions"><button class="btn secondary">Back</button><button class="btn ghost">New draft</button><button class="btn ghost">Import draft JSON</button><button class="btn ghost">Export draft JSON</button><button class="btn ghost" disabled="" title="Update project (Ctrl+S)">Update project</button><button class="btn primary" disabled="" title="Run analysis (Ctrl+Enter)">Run analysis</button></div></div>"`);
    } finally {
      await view.unmount();
    }
  });
});
