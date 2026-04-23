import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { compareMultipleProjectsRequest } from "./api";

function jsonResponse(payload: unknown, init?: ResponseInit): Response {
  return new Response(JSON.stringify(payload), {
    headers: { "Content-Type": "application/json" },
    ...init
  });
}

describe("compareMultipleProjectsRequest", () => {
  beforeEach(() => {
    const storage = new Map<string, string>();
    vi.stubGlobal("fetch", vi.fn());
    vi.stubGlobal("sessionStorage", {
      getItem: (key: string) => storage.get(key) ?? null,
      setItem: (key: string, value: string) => {
        storage.set(key, value);
      },
      removeItem: (key: string) => {
        storage.delete(key);
      }
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("adds Monte-Carlo query parameters when requested", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({
        projects: [],
        shared_warnings: [],
        shared_risks: [],
        shared_assumptions: [],
        unique_per_project: {},
        sample_size_range: { min: 0, max: 0, median: 0 },
        duration_range: { min: 0, max: 0, median: 0 },
        metric_types_used: [],
        recommendation_highlights: [],
        monte_carlo_distribution: {}
      })
    );

    await compareMultipleProjectsRequest(["p-1", "p-2"], {
      includeMonteCarlo: true,
      monteCarloSimulations: 10000
    });

    expect(String(vi.mocked(fetch).mock.calls[0]?.[0])).toContain(
      "/api/v1/projects/compare?include_monte_carlo=true&monte_carlo_simulations=10000"
    );
  });
});
