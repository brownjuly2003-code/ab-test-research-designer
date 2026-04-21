import { t } from "../../i18n";
import { useAnalysisStore } from "../../stores/analysisStore";
import { useProjectStore } from "../../stores/projectStore";

export default function RisksSection() {
  const analysisResult = useAnalysisStore((state) => state.analysisResult);
  const selectedHistoryAnalysis = useProjectStore((state) => state.selectedHistoryRun?.analysis ?? null);
  const displayedAnalysis = selectedHistoryAnalysis ?? analysisResult;

  if (!displayedAnalysis?.report) {
    return null;
  }

  return (
    <div className="two-col">
      <div className="card">
        <h3>{t("results.risks.statisticalAndOperational")}</h3>
        <ul className="list">
          {(displayedAnalysis.report.risks?.statistical ?? []).map((item) => (
            <li key={`statistical-${String(item)}`}>{String(item)}</li>
          ))}
          {(displayedAnalysis.report.risks?.operational ?? []).map((item) => (
            <li key={`operational-${String(item)}`}>{String(item)}</li>
          ))}
        </ul>
      </div>
      <div className="card">
        <h3>{t("results.risks.product")}</h3>
        <ul className="list">
          {(displayedAnalysis.report.risks?.product ?? []).map((item) => (
            <li key={`product-${String(item)}`}>{String(item)}</li>
          ))}
        </ul>
      </div>
      <div className="card">
        <h3>{t("results.risks.technical")}</h3>
        <ul className="list">
          {(displayedAnalysis.report.risks?.technical ?? []).map((item) => (
            <li key={`technical-${String(item)}`}>{String(item)}</li>
          ))}
        </ul>
      </div>
      <div className="card">
        <h3>{t("results.risks.recommendations")}</h3>
        <ul className="list">
          {(displayedAnalysis.report.recommendations?.before_launch ?? []).map((item) => (
            <li key={`before-${String(item)}`}>{t("results.risks.beforeLaunch")}: {String(item)}</li>
          ))}
          {(displayedAnalysis.report.recommendations?.during_test ?? []).map((item) => (
            <li key={`during-${String(item)}`}>{t("results.risks.duringTest")}: {String(item)}</li>
          ))}
          {(displayedAnalysis.report.recommendations?.after_test ?? []).map((item) => (
            <li key={`after-${String(item)}`}>{t("results.risks.afterTest")}: {String(item)}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}
