import { useAnalysisStore } from "../../stores/analysisStore";
import { useProjectStore } from "../../stores/projectStore";
import Icon from "../Icon";

export default function AiAdviceSection() {
  const analysisResult = useAnalysisStore((state) => state.analysisResult);
  const selectedHistoryAnalysis = useProjectStore((state) => state.selectedHistoryRun?.analysis ?? null);
  const displayedAnalysis = selectedHistoryAnalysis ?? analysisResult;

  if (!displayedAnalysis?.report) {
    return null;
  }

  return (
    <div className="card">
      <h3>Local orchestrator output</h3>
      {displayedAnalysis.advice.available ? (
        <>
          <p className="muted">
            Provider: {String(displayedAnalysis.advice.provider)} | Model: {String(displayedAnalysis.advice.model)}
          </p>
          <div className="two-col">
            <div className="card">
              <strong>Assessment</strong>
              <p className="muted">{String(displayedAnalysis.advice.advice?.brief_assessment ?? "")}</p>
            </div>
            <div className="card">
              <strong>Design improvements</strong>
              <ul className="list">
                {(displayedAnalysis.advice.advice?.design_improvements ?? []).map((item) => (
                  <li key={String(item)}>{String(item)}</li>
                ))}
              </ul>
            </div>
            <div className="card">
              <strong>Key risks</strong>
              <ul className="list">
                {(displayedAnalysis.advice.advice?.key_risks ?? []).map((item) => (
                  <li key={String(item)}>{String(item)}</li>
                ))}
              </ul>
            </div>
            <div className="card">
              <strong>Metric recommendations</strong>
              <ul className="list">
                {(displayedAnalysis.advice.advice?.metric_recommendations ?? []).map((item) => (
                  <li key={String(item)}>{String(item)}</li>
                ))}
              </ul>
            </div>
            <div className="card">
              <strong>Interpretation pitfalls</strong>
              <ul className="list">
                {(displayedAnalysis.advice.advice?.interpretation_pitfalls ?? []).map((item) => (
                  <li key={String(item)}>{String(item)}</li>
                ))}
              </ul>
            </div>
            <div className="card">
              <strong>Additional checks</strong>
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
            AI advice unavailable. Core deterministic output still works. {String(displayedAnalysis.advice.error ?? "")}
          </span>
        </div>
      )}
    </div>
  );
}
