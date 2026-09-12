import type {
  PersistedDecisionRequest,
  PersistedOverrideRequest,
  PersistedRunPortfolio,
  PersistedRunView
} from "../generated/api-contract";
import { apiBlobRequest, apiJsonRequest } from "./client";

export type {
  PersistedDecisionRequest,
  PersistedOverrideRequest,
  PersistedRunPortfolio,
  PersistedRunSummary,
  PersistedRunView
} from "../generated/api-contract";

function runPath(runId: string): string {
  return `/api/v2/runs/${encodeURIComponent(runId)}`;
}

export function loadRunPortfolio(signal?: AbortSignal): Promise<PersistedRunPortfolio> {
  return apiJsonRequest("/api/v2/runs", {
    signal,
    errorFallback: "Unable to load persisted evidence runs."
  });
}

export function loadRun(runId: string, signal?: AbortSignal): Promise<PersistedRunView> {
  return apiJsonRequest(runPath(runId), {
    signal,
    errorFallback: "Unable to load the persisted evidence run."
  });
}

export function remediateRunFinding(
  runId: string,
  findingId: string
): Promise<PersistedRunView> {
  return apiJsonRequest(
    `${runPath(runId)}/findings/${encodeURIComponent(findingId)}:remediate`,
    {
      method: "POST",
      errorFallback: "Unable to persist the finding remediation."
    }
  );
}

export function overrideRunFinding(
  runId: string,
  findingId: string,
  body: PersistedOverrideRequest
): Promise<PersistedRunView> {
  return apiJsonRequest(
    `${runPath(runId)}/findings/${encodeURIComponent(findingId)}:override`,
    {
      method: "POST",
      body,
      errorFallback: "Unable to persist the formal override."
    }
  );
}

export function downloadRunBundle(
  runId: string
): Promise<{ blob: Blob; filename: string }> {
  return apiBlobRequest(`${runPath(runId)}:bundle`, {
    errorFallback: "Unable to download the persisted evidence bundle.",
    fallbackFilename: `${runId}.tmk`
  });
}

export function recordRunDecision(
  runId: string,
  body: PersistedDecisionRequest
): Promise<PersistedRunView> {
  return apiJsonRequest(`${runPath(runId)}/decisions`, {
    method: "POST",
    body,
    errorFallback: "Unable to record the persisted human decision."
  });
}
