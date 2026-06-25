import { useState } from "react";

import { t } from "../../i18n";
import type { MultipleTestingRequest, MultipleTestingResponse } from "../../lib/api";
import { apiUrl } from "../../lib/experiment";
import MultipleTestingView, { type MetricRow } from "./internal/MultipleTestingView";
import { buildApiRequestHeaders } from "./resultsShared";

function createEmptyRows(count: number): MetricRow[] {
  return Array.from({ length: count }, () => ({ label: "", pValue: "" }));
}

function parsePValue(raw: string): number | null {
  const trimmed = raw.trim();
  if (trimmed === "") {
    return null;
  }
  const value = Number(trimmed);
  if (!Number.isFinite(value) || value < 0 || value > 1) {
    return null;
  }
  return value;
}

export default function MultipleTestingSection() {
  const [metrics, setMetrics] = useState<MetricRow[]>(() => createEmptyRows(3));
  const [method, setMethod] = useState<"bh" | "holm">("bh");
  const [level, setLevel] = useState("0.05");
  const [result, setResult] = useState<MultipleTestingResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const validMetrics = metrics
    .map((metric) => ({ label: metric.label.trim(), pValue: parsePValue(metric.pValue) }))
    .filter((metric): metric is { label: string; pValue: number } => metric.label !== "" && metric.pValue !== null);
  const levelValue = Number(level);
  const levelValid = Number.isFinite(levelValue) && levelValue > 0 && levelValue < 1;
  const canRun = validMetrics.length >= 1 && levelValid;

  function updateMetric(index: number, field: "label" | "pValue", value: string): void {
    setMetrics((current) => current.map((metric, position) => (position === index ? { ...metric, [field]: value } : metric)));
  }

  function addMetric(): void {
    setMetrics((current) => [...current, { label: "", pValue: "" }]);
  }

  function removeMetric(index: number): void {
    setMetrics((current) => (current.length <= 1 ? current : current.filter((_, position) => position !== index)));
  }

  async function runCorrection(): Promise<void> {
    if (!canRun) {
      return;
    }

    const payload: MultipleTestingRequest = {
      metrics: validMetrics.map((metric) => ({ label: metric.label, p_value: metric.pValue })),
      level: levelValue,
      method
    };

    setLoading(true);
    setResult(null);
    setError("");

    try {
      const response = await fetch(apiUrl("/api/v1/multiple-testing"), {
        method: "POST",
        headers: buildApiRequestHeaders(),
        body: JSON.stringify(payload)
      });
      const body = await response.json().catch(() => ({}));

      if (!response.ok) {
        const detail = typeof body.detail === "string" ? body.detail : t("results.multipleTesting.serviceUnavailable");
        throw new Error(detail);
      }

      setResult(body as MultipleTestingResponse);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : t("results.multipleTesting.serviceUnavailable"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <MultipleTestingView
      metrics={metrics}
      method={method}
      level={level}
      onChangeMetric={updateMetric}
      onAddMetric={addMetric}
      onRemoveMetric={removeMetric}
      onChangeMethod={setMethod}
      onChangeLevel={setLevel}
      onRun={() => {
        void runCorrection();
      }}
      canRun={canRun}
      loading={loading}
      error={error}
      result={result}
    />
  );
}
