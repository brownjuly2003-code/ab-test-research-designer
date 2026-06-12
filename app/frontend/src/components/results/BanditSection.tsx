import { useEffect, useState } from "react";

import { t } from "../../i18n";
import type { BanditSimulationResponse } from "../../lib/api";
import { apiUrl } from "../../lib/experiment";
import { useAnalysisStore } from "../../stores/analysisStore";
import { useProjectStore } from "../../stores/projectStore";
import BanditView from "./internal/BanditView";
import { buildApiRequestHeaders, getDisplayedAnalysis } from "./resultsShared";

const DEFAULT_HORIZON = "2000";

function toPercentString(fraction: number): string {
  if (!Number.isFinite(fraction)) {
    return "";
  }
  return Number((fraction * 100).toFixed(2)).toString();
}

export default function BanditSection() {
  const analysisResult = useAnalysisStore((state) => state.analysisResult);
  const selectedHistoryAnalysis = useProjectStore((state) => state.selectedHistoryRun?.analysis ?? null);
  const selectedHistoryRunId = useProjectStore((state) => state.selectedHistoryRun?.id ?? "");
  const displayedAnalysis = getDisplayedAnalysis(selectedHistoryAnalysis, analysisResult);
  const [armRates, setArmRates] = useState<string[]>([]);
  const [horizon, setHorizon] = useState<string>(DEFAULT_HORIZON);
  const [result, setResult] = useState<BanditSimulationResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const variantNames = displayedAnalysis?.report?.experiment_design?.variants.map((variant) => variant.name) ?? [];
  const summary = displayedAnalysis?.calculations?.calculation_summary;
  const metricType = summary?.metric_type ?? "";
  const baselineValue = Number(summary?.baseline_value ?? 0);
  const mdeAbsolute = Number(summary?.mde_absolute ?? 0);
  const unavailable = metricType !== "binary";

  useEffect(() => {
    const defaults = variantNames.map((_name, index) => {
      const rate = index === 0 ? baselineValue : Math.min(baselineValue + mdeAbsolute, 0.999);
      return toPercentString(rate);
    });
    setArmRates(defaults);
    setHorizon(DEFAULT_HORIZON);
    setResult(null);
    setLoading(false);
    setError("");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedHistoryRunId, variantNames.join("|"), metricType, baselineValue, mdeAbsolute]);

  if (!displayedAnalysis?.report) {
    return null;
  }

  const horizonValue = Number(horizon);
  const canRun =
    !unavailable &&
    variantNames.length >= 2 &&
    armRates.length === variantNames.length &&
    armRates.every((value) => value.trim() !== "" && Number.isFinite(Number(value)) && Number(value) >= 0 && Number(value) <= 100) &&
    Number.isInteger(horizonValue) &&
    horizonValue >= 10 &&
    horizonValue <= 5000;

  async function runBanditSimulation(): Promise<void> {
    if (!canRun) {
      return;
    }

    const payload = {
      arm_rates: armRates.map((value) => Number(value) / 100),
      horizon: horizonValue
    };

    setLoading(true);
    setResult(null);
    setError("");

    try {
      const response = await fetch(apiUrl("/api/v1/simulate/bandit"), {
        method: "POST",
        headers: buildApiRequestHeaders(),
        body: JSON.stringify(payload)
      });
      const body = await response.json().catch(() => ({}));

      if (!response.ok) {
        const detail = typeof body.detail === "string" ? body.detail : t("results.bandit.serviceUnavailable");
        throw new Error(detail);
      }

      setResult(body);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : t("results.bandit.serviceUnavailable"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <BanditView
      variantNames={variantNames}
      armRates={armRates}
      onChangeRate={(index, value) => {
        const next = [...armRates];
        next[index] = value;
        setArmRates(next);
      }}
      horizon={horizon}
      onChangeHorizon={setHorizon}
      onRun={() => {
        void runBanditSimulation();
      }}
      canRun={canRun}
      loading={loading}
      error={error}
      result={result}
      unavailable={unavailable}
    />
  );
}
