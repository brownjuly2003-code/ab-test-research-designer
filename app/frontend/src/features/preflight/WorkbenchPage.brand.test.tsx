// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../../lib/api/workbench", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api/workbench")>();
  return { ...actual, loadRun: vi.fn() };
});

import { loadRun, type PersistedRunView } from "../../lib/api/workbench";
import { flushEffects, renderIntoDocument } from "../../test/dom";
import WorkbenchPage from "./WorkbenchPage";

const readyView: PersistedRunView = {
  run_id: "run-asos",
  protocol_revision_id: "sha256:protocol",
  kind: "analysis",
  status: "succeeded",
  started_at: "2026-08-22T00:00:00Z",
  completed_at: "2026-08-22T00:00:01Z",
  sealed_at: "2026-08-22T00:00:01Z",
  protocol: { protocol: { protocol_id: "asos", title: "ASOS public benchmark" } },
  run: { run_id: "run-asos" },
  sources: [],
  metrics: [],
  findings: [],
  estimates: [],
  decisions: [],
  report_available: true,
  bundle: { bundle_id: "sha256:bundle", verdicts: { lineage: "pass" } }
};

describe("Trialmark Workbench branding", () => {
  afterEach(() => {
    window.history.replaceState(null, "", "/");
    vi.restoreAllMocks();
  });

  it("shows Trialmark branding while loading and after a persisted run is ready", async () => {
    window.history.replaceState(null, "", "/runs/run-asos");
    let resolveLoad: ((view: PersistedRunView) => void) | undefined;
    vi.mocked(loadRun).mockReturnValue(
      new Promise<PersistedRunView>((resolve) => {
        resolveLoad = resolve;
      })
    );

    const rendered = await renderIntoDocument(<WorkbenchPage />);
    try {
      expect(rendered.container.textContent).toContain("Trialmark Workbench");

      resolveLoad?.(readyView);
      await flushEffects();

      expect(rendered.container.textContent).toContain("Trialmark Workbench · persisted evidence");
    } finally {
      await rendered.unmount();
    }
  });
});
