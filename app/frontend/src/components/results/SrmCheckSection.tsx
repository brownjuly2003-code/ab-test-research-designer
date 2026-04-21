import { useEffect, useState } from "react";

import { t } from "../../i18n";
import type { SrmCheckResponse } from "../../lib/api";
import { apiUrl } from "../../lib/experiment";
import { useAnalysisStore } from "../../stores/analysisStore";
import { useProjectStore } from "../../stores/projectStore";
import SrmCheckView from "./internal/SrmCheckView";
import { buildApiRequestHeaders, getDisplayedAnalysis } from "./resultsShared";

type SrmCheckPayload = { observed_counts: number[]; expected_fractions: number[] };

export default function SrmCheckSection() {
  const analysisResult = useAnalysisStore((state) => state.analysisResult);
  const selectedHistoryAnalysis = useProjectStore((state) => state.selectedHistoryRun?.analysis ?? null);
  const selectedHistoryRunId = useProjectStore((state) => state.selectedHistoryRun?.id ?? "");
  const displayedAnalysis = getDisplayedAnalysis(selectedHistoryAnalysis, analysisResult);
  const [srmCounts, setSrmCounts] = useState<string[]>([]);
  const [srmResult, setSrmResult] = useState<SrmCheckResponse | null>(null);
  const [srmLoading, setSrmLoading] = useState(false);
  const [srmError, setSrmError] = useState("");

  if (!displayedAnalysis?.report) {
    return null;
  }

  const variantNames = displayedAnalysis.report.experiment_design?.variants.map((variant) => variant.name) ?? [];
  const trafficSplit = displayedAnalysis.report.experiment_design?.traffic_split ?? [];
  const trafficSplitTotal = trafficSplit.reduce((total, value) => total + value, 0);
  const srmExpectedFractions = trafficSplitTotal > 0 ? trafficSplit.map((value) => value / trafficSplitTotal) : [];
  const canRunSrm =
    variantNames.length > 1 &&
    srmExpectedFractions.length === variantNames.length &&
    srmCounts.length === variantNames.length &&
    srmCounts.every((value) => value.trim() !== "" && Number.isInteger(Number(value)) && Number(value) >= 0);

  useEffect(() => {
    setSrmCounts(Array.from({ length: variantNames.length }, () => ""));
    setSrmResult(null);
    setSrmLoading(false);
    setSrmError("");
  }, [selectedHistoryRunId, trafficSplit.join(","), variantNames.join("|")]);

  async function runSrmCheck(): Promise<void> {
    if (!canRunSrm) {
      return;
    }

    const payload: SrmCheckPayload = {
      observed_counts: srmCounts.map((value) => Number(value)),
      expected_fractions: srmExpectedFractions
    };

    setSrmLoading(true);
    setSrmResult(null);
    setSrmError("");

    try {
      const response = await fetch(apiUrl("/api/v1/srm-check"), {
        method: "POST",
        headers: buildApiRequestHeaders(),
        body: JSON.stringify(payload)
      });
      const body = await response.json().catch(() => ({}));

      if (!response.ok) {
        const detail = typeof body.detail === "string" ? body.detail : t("results.srmCheck.serviceUnavailable");
        throw new Error(detail);
      }

      setSrmResult(body);
    } catch (requestError) {
      setSrmError(requestError instanceof Error ? requestError.message : t("results.srmCheck.serviceUnavailable"));
    } finally {
      setSrmLoading(false);
    }
  }

  return <SrmCheckView variantNames={variantNames} srmCounts={srmCounts} onChangeCount={(index, value) => { const next = [...srmCounts]; next[index] = value; setSrmCounts(next); }} onRun={() => { void runSrmCheck(); }} canRunSrm={canRunSrm} srmLoading={srmLoading} srmError={srmError} srmResult={srmResult} />;
}
