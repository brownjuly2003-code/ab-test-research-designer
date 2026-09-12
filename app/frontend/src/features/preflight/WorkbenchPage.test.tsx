// @vitest-environment jsdom

import "vitest-axe/extend-expect";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";
import * as matchers from "vitest-axe/matchers";

vi.mock("../../lib/api/workbench", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api/workbench")>();
  return {
    ...actual,
    loadRunPortfolio: vi.fn(),
    loadRun: vi.fn(),
    remediateRunFinding: vi.fn(),
    overrideRunFinding: vi.fn(),
    downloadRunBundle: vi.fn(),
    recordRunDecision: vi.fn()
  };
});

import {
  downloadRunBundle,
  loadRun,
  loadRunPortfolio,
  recordRunDecision,
  type PersistedRunPortfolio,
  type PersistedRunView
} from "../../lib/api/workbench";
import {
  changeValue,
  click,
  findButton,
  flushEffects,
  mockBlobDownloadGlobals,
  renderIntoDocument
} from "../../test/dom";
import WorkbenchPage from "./WorkbenchPage";

expect.extend(matchers);

type AxeMatcher = { toHaveNoViolations: () => void };

const parentView: PersistedRunView = {
  run_id: "run_asos_d53f0e_terminal",
  protocol_revision_id: "sha256:protocol",
  kind: "analysis",
  status: "succeeded",
  started_at: "2026-08-22T00:00:00Z",
  completed_at: "2026-08-22T00:00:01Z",
  sealed_at: "2026-08-22T00:00:01Z",
  protocol: {
    protocol: {
      protocol_id: "asos-public-benchmark-d53f0e",
      title: "ASOS public benchmark d53f0e"
    }
  },
  run: { run_id: "run_asos_d53f0e_terminal" },
  sources: [
    {
      source_snapshot_id: "source_asos_d53f0e_terminal",
      kind: "duckdb_file",
      captured_at: "2026-08-22T00:00:00Z",
      fingerprint: { value: "sha256:source" }
    }
  ],
  metrics: [],
  findings: [],
  estimates: [
    {
      estimate_id: "estimate_asos_d53f0e_1",
      effect_measure: "mean_difference",
      point_estimate: 0.000802132,
      uncertainty: { level: "0.95", lower: -0.000024, upper: 0.001629 },
      lineage: { metric: { metric_id: "metric_asos_1" } }
    }
  ],
  decisions: [
    {
      decision_id: "decision_asos_d53f0e_proposed",
      human_verdict: "inconclusive",
      rationale: "Proposed for human review after independent ABX verification.",
      state: "proposed",
      decided_by: { actor_ref: "local-operator", role: "evidence_system" }
    }
  ],
  report_available: true,
  bundle: {
    bundle_id: "sha256:bundle-parent",
    verdicts: { integrity: "pass", lineage: "pass" }
  }
};

const childView: PersistedRunView = {
  ...parentView,
  run_id: "run_asos_d53f0e_decision",
  run: {
    run_id: "run_asos_d53f0e_decision",
    parent_run_id: parentView.run_id
  },
  decisions: [
    {
      decision_id: "decision-001",
      human_verdict: "ship",
      rationale: "The persisted evidence supports this benchmark decision.",
      state: "approved",
      decided_by: { actor_ref: "local-operator", role: "benchmark_reviewer" }
    }
  ],
  bundle: {
    bundle_id: "sha256:bundle-child",
    verdicts: { integrity: "pass", lineage: "pass" }
  }
};

const portfolio: PersistedRunPortfolio = {
  runs: [
    {
      run_id: parentView.run_id,
      protocol_revision_id: parentView.protocol_revision_id,
      kind: parentView.kind,
      status: parentView.status,
      started_at: parentView.started_at,
      completed_at: parentView.completed_at,
      sealed_at: parentView.sealed_at,
      bundle_id: parentView.bundle.bundle_id,
      verdicts: parentView.bundle.verdicts
    }
  ]
};

describe("Persisted Trialmark Workbench", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockBlobDownloadGlobals("blob:persisted-bundle");
    vi.mocked(loadRunPortfolio).mockResolvedValue(portfolio);
    vi.mocked(loadRun).mockImplementation(async (runId) =>
      runId === childView.run_id ? childView : parentView
    );
    vi.mocked(downloadRunBundle).mockResolvedValue({
      blob: new Blob(["PK"], { type: "application/vnd.trialmark.bundle+zip" }),
      filename: `${parentView.run_id}.tmk`
    });
    vi.mocked(recordRunDecision).mockResolvedValue(childView);
  });

  afterEach(() => {
    window.history.replaceState(null, "", "/");
    vi.restoreAllMocks();
  });

  it("lists persisted runs at /runs", async () => {
    window.history.replaceState(null, "", "/runs");
    const rendered = await renderIntoDocument(<WorkbenchPage />);
    try {
      await flushEffects();
      expect(loadRunPortfolio).toHaveBeenCalledOnce();
      expect(rendered.container.textContent).toContain("Evidence runs");
      expect(rendered.container.textContent).toContain("1 persisted runs");
      expect(rendered.container.textContent).toContain(parentView.run_id);
    } finally {
      await rendered.unmount();
    }
  });

  it("records a decision as an append-only child run", async () => {
    window.history.replaceState(null, "", `/runs/${parentView.run_id}`);
    const rendered = await renderIntoDocument(<WorkbenchPage />);
    try {
      await flushEffects();
      expect(rendered.container.textContent).toContain("ASOS public benchmark d53f0e");
      expect(rendered.container.textContent).toContain("1 estimates");
      expect(rendered.container.textContent).toContain("lineage pass");

      const decisionStage = Array.from(
        rendered.container.querySelectorAll('[aria-label="Evidence workflow progress"] li')
      ).find((item) => item.querySelector("strong")?.textContent === "Decision");
      expect(decisionStage?.getAttribute("data-state")).toBe("current");
      expect(decisionStage?.textContent).toContain("Awaiting owner");

      const decisionPanel = Array.from(rendered.container.querySelectorAll("section")).find((section) =>
        section.textContent?.includes("Human authority")
      );
      expect(decisionPanel?.querySelector("h2")?.textContent).toBe("Record decision");
      const verdict = Array.from(rendered.container.querySelectorAll("label")).find((label) =>
        label.textContent?.includes("Verdict")
      )?.querySelector("select");
      expect(verdict).toBeInstanceOf(HTMLSelectElement);
      expect(findButton(rendered.container, "Record human decision")).toBeInstanceOf(HTMLButtonElement);

      await click(findButton(rendered.container, "Download .tmk"));
      await flushEffects();
      expect(downloadRunBundle).toHaveBeenCalledWith(parentView.run_id);

      const rationale = rendered.container.querySelector(
        'textarea[placeholder="Decision grounded in the persisted evidence"]'
      );
      expect(rationale).toBeInstanceOf(HTMLTextAreaElement);
      await changeValue(
        rationale as HTMLTextAreaElement,
        "The persisted evidence supports this benchmark decision."
      );
      await click(findButton(rendered.container, "Record human decision"));
      await flushEffects();

      expect(recordRunDecision).toHaveBeenCalledWith(parentView.run_id, {
        verdict: "ship",
        rationale: "The persisted evidence supports this benchmark decision."
      });
      expect(window.location.pathname).toBe(`/runs/${childView.run_id}`);
      expect(rendered.container.textContent).toContain("Decision record");
      expect(rendered.container.textContent).toContain("local-operator");
    } finally {
      await rendered.unmount();
    }
  });

  it("has no serious or critical accessibility violations", async () => {
    window.history.replaceState(null, "", `/runs/${parentView.run_id}`);
    const rendered = await renderIntoDocument(<WorkbenchPage />);
    try {
      await flushEffects();
      const results = await axe(rendered.container);
      (expect({
        ...results,
        violations: results.violations.filter(
          (violation) => violation.impact === "serious" || violation.impact === "critical"
        )
      }) as unknown as AxeMatcher).toHaveNoViolations();
    } finally {
      await rendered.unmount();
    }
  });
});
