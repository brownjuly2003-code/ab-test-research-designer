import { Suspense, lazy } from "react";

import type { SensitivityResponse } from "../../lib/generated/api-contract";
import { useAnalysisStore } from "../../stores/analysisStore";
import { useProjectStore } from "../../stores/projectStore";
import ChartErrorBoundary from "../ChartErrorBoundary";
import Icon from "../Icon";
import { getDisplayedAnalysis } from "./resultsShared";
import { resolveCurrentMde, resolveMetricType } from "./sensitivityShared";

const PowerCurveChart = lazy(() => import("../PowerCurveChart"));

type PowerCurveSectionProps = {
  sensitivityData: SensitivityResponse | null;
  sensitivityLoading: boolean;
  sensitivityUnavailableMessage: string;
};

export default function PowerCurveSection({
  sensitivityData,
  sensitivityLoading,
  sensitivityUnavailableMessage
}: PowerCurveSectionProps) {
  const analysisResult = useAnalysisStore((state) => state.analysisResult);
  const selectedHistoryAnalysis = useProjectStore((state) => state.selectedHistoryRun?.analysis ?? null);
  const displayedAnalysis = getDisplayedAnalysis(selectedHistoryAnalysis, analysisResult);

  if (!displayedAnalysis?.report) {
    return null;
  }

  const currentMde = resolveCurrentMde(displayedAnalysis);
  const currentPower = displayedAnalysis.calculations.calculation_summary.power;

  return (
    <div className="card">
      <h3>Power curve</h3>
      <p className="muted">Compare MDE targets against planned power levels and required sample size.</p>
      {sensitivityLoading ? (
        <p className="muted">Loading sensitivity analysis...</p>
      ) : sensitivityData?.cells.length ? (
        <ChartErrorBoundary rawData={sensitivityData.cells}>
          <Suspense fallback={<p className="muted">Loading chart...</p>}>
            <PowerCurveChart
              cells={sensitivityData.cells}
              currentMde={currentMde}
              currentPower={currentPower}
              metricType={resolveMetricType(displayedAnalysis.calculations.calculation_summary.metric_type)}
            />
          </Suspense>
        </ChartErrorBoundary>
      ) : (
        <div className="callout">
          <Icon name="info" className="icon icon-inline" />
          <span>{sensitivityUnavailableMessage}</span>
        </div>
      )}
    </div>
  );
}
