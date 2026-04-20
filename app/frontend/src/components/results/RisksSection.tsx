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
        <h3>Statistical and operational considerations</h3>
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
        <h3>Product</h3>
        <ul className="list">
          {(displayedAnalysis.report.risks?.product ?? []).map((item) => (
            <li key={`product-${String(item)}`}>{String(item)}</li>
          ))}
        </ul>
      </div>
      <div className="card">
        <h3>Technical</h3>
        <ul className="list">
          {(displayedAnalysis.report.risks?.technical ?? []).map((item) => (
            <li key={`technical-${String(item)}`}>{String(item)}</li>
          ))}
        </ul>
      </div>
      <div className="card">
        <h3>Recommendations</h3>
        <ul className="list">
          {(displayedAnalysis.report.recommendations?.before_launch ?? []).map((item) => (
            <li key={`before-${String(item)}`}>Before launch: {String(item)}</li>
          ))}
          {(displayedAnalysis.report.recommendations?.during_test ?? []).map((item) => (
            <li key={`during-${String(item)}`}>During test: {String(item)}</li>
          ))}
          {(displayedAnalysis.report.recommendations?.after_test ?? []).map((item) => (
            <li key={`after-${String(item)}`}>After test: {String(item)}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}
