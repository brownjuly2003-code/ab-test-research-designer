import { useTranslation } from "react-i18next";

import { useAnalysisStore } from "../../stores/analysisStore";
import { useProjectStore } from "../../stores/projectStore";
import styles from "./MetricsPlanSection.module.css";

export default function MetricsPlanSection() {
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
        <h3>{t("results.metricsPlan.coverage")}</h3>
        <ul className="list">
          {(displayedAnalysis.report.metrics_plan?.primary ?? []).map((item) => (
            <li key={`primary-${String(item)}`}>{t("results.metricsPlan.primary")}: {String(item)}</li>
          ))}
          {(displayedAnalysis.report.metrics_plan?.secondary ?? []).map((item) => (
            <li key={`secondary-${String(item)}`}>{t("results.metricsPlan.secondary")}: {String(item)}</li>
          ))}
          {(displayedAnalysis.report.metrics_plan?.guardrail ?? []).map((item) => (
            <li key={`guardrail-${String(item)}`}>{t("results.metricsPlan.guardrail")}: {String(item)}</li>
          ))}
          {(displayedAnalysis.report.metrics_plan?.diagnostic ?? []).map((item) => (
            <li key={`diagnostic-${String(item)}`}>{t("results.metricsPlan.diagnostic")}: {String(item)}</li>
          ))}
        </ul>
      </div>
      {(displayedAnalysis.report.guardrail_metrics ?? []).length > 0 ? (
        <div className="card">
          <h3>{t("results.metricsPlan.guardrailMetrics")}</h3>
          <p className="muted">{t("results.metricsPlan.guardrailMetricsDescription")}</p>
          <div className={styles["guardrail-stack"]}>
            {(displayedAnalysis.report.guardrail_metrics ?? []).map((guardrail, index) => (
              <div key={`${guardrail.name}-${index}`} className={styles["guardrail-report-row"]}>
                <div>
                  <strong>{guardrail.name}</strong>
                  <div className="muted">
                    {t("results.metricsPlan.baseline")}: {guardrail.baseline}
                    {guardrail.metric_type === "binary" ? "%" : ""}
                  </div>
                </div>
                <div className={styles["guardrail-detectable-change"]}>
                  {guardrail.metric_type === "binary"
                    ? `>= ${guardrail.detectable_mde_pp} pp`
                    : `>= ${guardrail.detectable_mde_absolute}`}
                </div>
                <div className="muted">{guardrail.note}</div>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
