import type { AnalysisResponsePayload } from "../../lib/experiment";
import { apiUrl, buildApiPayload } from "../../lib/experiment";
import type { SensitivityRequest, SensitivityResponse } from "../../lib/generated/api-contract";
import { readDraftBootstrap } from "../../stores/draftStore";
import { buildApiRequestHeaders } from "./resultsShared";

const defaultMdeValues = [0.1, 0.5, 1, 2, 5];
const defaultPowerValues = [0.7, 0.8, 0.9, 0.95];

export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

// Display-only grouping (MDE formatting: percentage points vs. plain units). Ratio metrics are
// sized and displayed like continuous ones (delta-method-linearized), so they fall into the
// "continuous" bucket here — only binary is percentage-point-shaped.
export function resolveMetricType(metricType: string): "binary" | "continuous" {
  return metricType === "binary" ? "binary" : "continuous";
}

// Trims binary floating-point noise (e.g. 0.0021000000000000003 -> 0.0021) for display.
export function formatStatNumber(value: number): string {
  if (!Number.isFinite(value)) {
    return String(value);
  }
  return String(Number(value.toPrecision(12)));
}

export function resolveCurrentMde(analysis: AnalysisResponsePayload): number {
  const summary = analysis.calculations.calculation_summary;
  return resolveMetricType(summary.metric_type) === "continuous" ? summary.mde_absolute : summary.mde_pct;
}

function buildSensitivityScale(defaultValues: number[], currentValue: number, limit: number): number[] {
  const normalizedCurrent = Number(currentValue.toFixed(4));
  const available = Array.from(
    new Set([...defaultValues, normalizedCurrent].map((value) => Number(value.toFixed(4))))
  ).sort((left, right) => left - right);

  if (available.length <= limit) {
    return available;
  }

  const selected = new Set<number>([normalizedCurrent]);
  const remaining = available
    .filter((value) => value !== normalizedCurrent)
    .sort((left, right) => {
      const distance = Math.abs(left - normalizedCurrent) - Math.abs(right - normalizedCurrent);
      return distance !== 0 ? distance : left - right;
    });

  for (const value of remaining) {
    if (selected.size >= limit) {
      break;
    }
    selected.add(value);
  }

  return Array.from(selected).sort((left, right) => left - right);
}

export function buildSensitivityPayload(analysis: AnalysisResponsePayload): SensitivityRequest | null {
  const summary = analysis.calculations.calculation_summary;
  const results = analysis.calculations.results;
  const trafficSplit = analysis.report.experiment_design?.traffic_split ?? [];
  const variants = analysis.report.experiment_design?.variants.length ?? trafficSplit.length;
  const currentMde = resolveCurrentMde(analysis);
  const mdeValues = buildSensitivityScale(defaultMdeValues, currentMde, 5);
  const powerValues = buildSensitivityScale(defaultPowerValues, summary.power, 4);

  if (variants < 2 || trafficSplit.length !== variants) {
    return null;
  }

  if (summary.metric_type === "binary") {
    return {
      metric_type: "binary",
      baseline_rate: summary.baseline_value * 100,
      variants,
      alpha: summary.alpha,
      daily_traffic: results.effective_daily_traffic,
      audience_share: 1,
      traffic_split: trafficSplit,
      mde_values: mdeValues,
      power_values: powerValues
    };
  }

  // Continuous and ratio metrics both size through the delta-method-linearized continuous formula
  // (see calculations_service.py) — same shape, different metric_type on the wire. Ratio's baseline
  // is the baseline ratio R and its std_dev the per-user linearized standard deviation.
  if (summary.metric_type !== "continuous" && summary.metric_type !== "ratio") {
    return null;
  }
  const requestMetricType = summary.metric_type === "ratio" ? "ratio" : "continuous";

  const persistedDraft = buildApiPayload(readDraftBootstrap().form);
  if (persistedDraft.metrics.metric_type !== requestMetricType || persistedDraft.metrics.std_dev === null) {
    return null;
  }

  return {
    metric_type: requestMetricType,
    baseline_mean: summary.baseline_value,
    std_dev: persistedDraft.metrics.std_dev,
    variants,
    alpha: summary.alpha,
    daily_traffic: results.effective_daily_traffic,
    audience_share: 1,
    traffic_split: trafficSplit,
    mde_values: mdeValues,
    power_values: powerValues
  };
}

export async function fetchSensitivityData(
  payload: SensitivityRequest,
  signal: AbortSignal
): Promise<SensitivityResponse> {
  const response = await fetch(apiUrl("/api/v1/sensitivity"), {
    method: "POST",
    headers: buildApiRequestHeaders(),
    body: JSON.stringify(payload),
    signal
  });
  const body = await response.json().catch(() => ({}));

  if (!response.ok) {
    const detail = typeof body.detail === "string" ? body.detail : "Sensitivity analysis unavailable.";
    throw new Error(detail);
  }

  return body;
}
