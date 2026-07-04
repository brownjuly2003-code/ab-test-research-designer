import { formatLocalizedTimestamp } from "../../lib/formatDate";
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

  if (typeof document !== "undefined") {
    const language = document.documentElement.lang?.trim();
    if (language) {
      headers["Accept-Language"] = language;
    }
  }

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
  return formatLocalizedTimestamp(timestamp);
}

export function formatDelta(value: number, suffix = ""): string {
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${value}${suffix}`;
}

// A Bayesian "beats control/holdout" probability approaching 1 rounds to a false-certainty
// "100.00%" at 2 decimals; cap the display instead of implying the treatment can never lose.
export function formatCappedProbabilityPercent(fraction: number | null | undefined): string {
  if (fraction == null) {
    return "—";
  }
  const percent = (fraction * 100).toFixed(2);
  if (fraction < 1 && percent === "100.00") {
    return ">99.9%";
  }
  return `${percent}%`;
}
