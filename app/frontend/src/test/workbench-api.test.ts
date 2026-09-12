import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { downloadRunBundle, loadRunPortfolio, recordRunDecision } from "../lib/api/workbench";

function jsonResponse(payload: unknown, init?: ResponseInit): Response {
  return new Response(JSON.stringify(payload), {
    headers: { "Content-Type": "application/json" },
    ...init
  });
}

describe("Persisted Trialmark Workbench API", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("loads the persisted run portfolio", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(jsonResponse({ runs: [] }));

    await loadRunPortfolio();

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/v2/runs"),
      expect.objectContaining({ method: "GET" })
    );
  });

  it("records a decision against the run named in the URL", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(jsonResponse({ run_id: "child" }));

    await recordRunDecision("run parent", {
      verdict: "hold",
      rationale: "The persisted evidence needs another accountable review."
    });

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/v2/runs/run%20parent/decisions"),
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          verdict: "hold",
          rationale: "The persisted evidence needs another accountable review."
        })
      })
    );
  });

  it("downloads the run-specific Trialmark bundle", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(
      new Response(new Blob(["PK"]), {
        headers: {
          "Content-Disposition": 'attachment; filename="run-asos.tmk"',
          "Content-Type": "application/vnd.trialmark.bundle+zip"
        }
      })
    );

    const artifact = await downloadRunBundle("run-asos");

    expect(artifact.filename).toBe("run-asos.tmk");
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/v2/runs/run-asos:bundle"),
      expect.objectContaining({ headers: expect.any(Object) })
    );
  });
});
