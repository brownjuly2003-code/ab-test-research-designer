import { useTranslation } from "react-i18next";

import { useAnalysisStore } from "../../stores/analysisStore";
import { useProjectStore } from "../../stores/projectStore";
import Icon from "../Icon";

export default function AiAdviceSection() {
  const { t } = useTranslation();
  const analysisResult = useAnalysisStore((state) => state.analysisResult);
  const selectedHistoryAnalysis = useProjectStore((state) => state.selectedHistoryRun?.analysis ?? null);
  const displayedAnalysis = selectedHistoryAnalysis ?? analysisResult;

  if (!displayedAnalysis?.report) {
    return null;
  }

  return (
    <div className="card">
      <h3>{t("results.aiAdvice.title")}</h3>
      {displayedAnalysis.advice.available ? (
        <>
          <p className="muted">
            {t("results.aiAdvice.provider")} {String(displayedAnalysis.advice.provider)} | {t("results.aiAdvice.model")} {String(displayedAnalysis.advice.model)}
          </p>
          <div className="two-col">
            <div className="card">
              <strong>{t("results.aiAdvice.assessment")}</strong>
              <p className="muted">{String(displayedAnalysis.advice.advice?.brief_assessment ?? "")}</p>
            </div>
            <div className="card">
              <strong>{t("results.aiAdvice.designImprovements")}</strong>
              <ul className="list">
                {(displayedAnalysis.advice.advice?.design_improvements ?? []).map((item) => (
                  <li key={String(item)}>{String(item)}</li>
                ))}
              </ul>
            </div>
            <div className="card">
              <strong>{t("results.aiAdvice.keyRisks")}</strong>
              <ul className="list">
                {(displayedAnalysis.advice.advice?.key_risks ?? []).map((item) => (
                  <li key={String(item)}>{String(item)}</li>
                ))}
              </ul>
            </div>
            <div className="card">
              <strong>{t("results.aiAdvice.metricRecommendations")}</strong>
              <ul className="list">
                {(displayedAnalysis.advice.advice?.metric_recommendations ?? []).map((item) => (
                  <li key={String(item)}>{String(item)}</li>
                ))}
              </ul>
            </div>
            <div className="card">
              <strong>{t("results.aiAdvice.interpretationPitfalls")}</strong>
              <ul className="list">
                {(displayedAnalysis.advice.advice?.interpretation_pitfalls ?? []).map((item) => (
                  <li key={String(item)}>{String(item)}</li>
                ))}
              </ul>
            </div>
            <div className="card">
              <strong>{t("results.aiAdvice.additionalChecks")}</strong>
              <ul className="list">
                {(displayedAnalysis.advice.advice?.additional_checks ?? []).map((item) => (
                  <li key={String(item)}>{String(item)}</li>
                ))}
              </ul>
            </div>
          </div>
        </>
      ) : (
        <div className="callout">
          <Icon name="info" className="icon icon-inline" />
          <span>
            {t("results.aiAdvice.unavailable")} {String(displayedAnalysis.advice.error ?? "")}
          </span>
        </div>
      )}
    </div>
  );
}
