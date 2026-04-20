import type { AnalysisResponsePayload } from "../../lib/experiment";

const apiSessionTokenStorageKey = "ab-test-research-designer:api-token:v1";

export function getDisplayedAnalysis(
  selectedHistoryAnalysis: AnalysisResponsePayload | null,
  analysisResult: AnalysisResponsePayload | null
) {
  return selectedHistoryAnalysis ?? analysisResult;
}

export function buildApiRequestHeaders(): Record<string, string> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json"
  };

  if (typeof window === "undefined") {
    return headers;
  }

  const token = window.sessionStorage.getItem(apiSessionTokenStorageKey)?.trim();
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  return headers;
}

export function formatResultTimestamp(timestamp: string): string {
  const parsed = new Date(timestamp);
  if (Number.isNaN(parsed.getTime())) {
    return timestamp;
  }

  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(parsed);
}

export function formatDelta(value: number, suffix = ""): string {
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${value}${suffix}`;
}
