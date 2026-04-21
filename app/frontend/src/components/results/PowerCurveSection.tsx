import { Suspense, lazy, useRef } from "react";

import type { SensitivityResponse } from "../../lib/generated/api-contract";
import { useDraftStore } from "../../stores/draftStore";
import { useAnalysisStore } from "../../stores/analysisStore";
import { useProjectStore } from "../../stores/projectStore";
import ChartExportMenu, { slugifyChartFilename } from "../ChartExport";
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
  const chartRef = useRef<HTMLDivElement | null>(null);
  const analysisResult = useAnalysisStore((state) => state.analysisResult);
  const selectedHistoryAnalysis = useProjectStore((state) => state.selectedHistoryRun?.analysis ?? null);
  const activeProject = useProjectStore((state) => state.activeProject);
  const draftProjectName = useDraftStore((state) => state.draft.project.project_name);
  const displayedAnalysis = getDisplayedAnalysis(selectedHistoryAnalysis, analysisResult);

  if (!displayedAnalysis?.report) {
    return null;
  }

  const currentMde = resolveCurrentMde(displayedAnalysis);
  const currentPower = displayedAnalysis.calculations.calculation_summary.power;
  const filenameBase = `${slugifyChartFilename(activeProject?.project_name || draftProjectName || "experiment")}-power-curve`;

  return (
    <div className="card">
      <div className="section-heading">
        <div>
          <h3>Power curve</h3>
          <p className="muted">Compare MDE targets against planned power levels and required sample size.</p>
        </div>
      </div>
      {sensitivityLoading ? (
        <p className="muted">Loading sensitivity analysis...</p>
      ) : sensitivityData?.cells.length ? (
        <div ref={chartRef} role="img" aria-label="Power curve chart showing minimum detectable effect versus target power">
          <ChartExportMenu chartRef={chartRef} filenameBase={filenameBase} />
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
        </div>
      ) : (
        <div className="callout">
          <Icon name="info" className="icon icon-inline" />
          <span>{sensitivityUnavailableMessage}</span>
        </div>
      )}
    </div>
  );
}
