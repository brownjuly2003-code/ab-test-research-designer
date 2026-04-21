import { Suspense, lazy, useRef } from "react";
import { useTranslation } from "react-i18next";

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
  const { t } = useTranslation();
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
          <h3>{t("results.powerCurve.title")}</h3>
          <p className="muted">{t("results.powerCurve.description")}</p>
        </div>
      </div>
      {sensitivityLoading ? (
        <p className="muted">{t("results.powerCurve.loadingSensitivity")}</p>
      ) : sensitivityData?.cells.length ? (
        <div ref={chartRef}>
          <ChartExportMenu chartRef={chartRef} filenameBase={filenameBase} />
          <div role="img" aria-label={t("results.powerCurve.chartAriaLabel")}>
            <ChartErrorBoundary rawData={sensitivityData.cells}>
              <Suspense fallback={<p className="muted">{t("results.powerCurve.loadingChart")}</p>}>
                <PowerCurveChart
                  cells={sensitivityData.cells}
                  currentMde={currentMde}
                  currentPower={currentPower}
                  metricType={resolveMetricType(displayedAnalysis.calculations.calculation_summary.metric_type)}
                />
              </Suspense>
            </ChartErrorBoundary>
          </div>
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
