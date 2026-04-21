import { useTranslation } from "react-i18next";

import { useAnalysisStore } from "../../stores/analysisStore";
import { useProjectStore } from "../../stores/projectStore";

export default function ExperimentDesignSection() {
  const { t } = useTranslation();
  const analysisResult = useAnalysisStore((state) => state.analysisResult);
  const selectedHistoryAnalysis = useProjectStore((state) => state.selectedHistoryRun?.analysis ?? null);
  const displayedAnalysis = selectedHistoryAnalysis ?? analysisResult;

  if (!displayedAnalysis?.report) {
    return null;
  }

  return (
    <div className="two-col">
      <div className="card">
        <h3>{t("results.experimentDesign.variantAndRolloutStructure")}</h3>
        <ul className="list">
          {(displayedAnalysis.report.experiment_design?.variants ?? []).map((variant) => (
            <li key={variant.name}>
              <strong>{variant.name}</strong>: {variant.description}
            </li>
          ))}
        </ul>
      </div>
      <div className="card">
        <h3>{t("results.experimentDesign.setup")}</h3>
        <ul className="list">
          <li>
            <strong>{t("results.experimentDesign.randomizationUnit")}:</strong> {String(displayedAnalysis.report.experiment_design?.randomization_unit ?? "-")}
          </li>
          <li>
            <strong>{t("results.experimentDesign.trafficSplit")}:</strong> {String(displayedAnalysis.report.experiment_design?.traffic_split?.join(", ") ?? "-")}
          </li>
          <li>
            <strong>{t("results.experimentDesign.targetAudience")}:</strong> {String(displayedAnalysis.report.experiment_design?.target_audience ?? "-")}
          </li>
          <li>
            <strong>{t("results.experimentDesign.inclusion")}:</strong> {String(displayedAnalysis.report.experiment_design?.inclusion_criteria ?? "-")}
          </li>
          <li>
            <strong>{t("results.experimentDesign.exclusion")}:</strong> {String(displayedAnalysis.report.experiment_design?.exclusion_criteria ?? "-")}
          </li>
          <li>
            <strong>{t("results.experimentDesign.recommendedDuration")}:</strong> {String(displayedAnalysis.report.experiment_design?.recommended_duration_days ?? "-")} {t("results.experimentDesign.days")}
          </li>
        </ul>
      </div>
      <div className="card">
        <h3>{t("results.experimentDesign.stoppingConditions")}</h3>
        <ul className="list">
          {(displayedAnalysis.report.experiment_design?.stopping_conditions ?? []).map((item) => (
            <li key={String(item)}>{String(item)}</li>
          ))}
        </ul>
      </div>
      <div className="card">
        <h3>{t("results.experimentDesign.openQuestions")}</h3>
        <ul className="list">
          {(displayedAnalysis.report.open_questions ?? []).map((item) => (
            <li key={String(item)}>{String(item)}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}
