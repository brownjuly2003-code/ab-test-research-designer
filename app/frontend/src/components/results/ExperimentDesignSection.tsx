import { useAnalysisStore } from "../../stores/analysisStore";
import { useProjectStore } from "../../stores/projectStore";

export default function ExperimentDesignSection() {
  const analysisResult = useAnalysisStore((state) => state.analysisResult);
  const selectedHistoryAnalysis = useProjectStore((state) => state.selectedHistoryRun?.analysis ?? null);
  const displayedAnalysis = selectedHistoryAnalysis ?? analysisResult;

  if (!displayedAnalysis?.report) {
    return null;
  }

  return (
    <div className="two-col">
      <div className="card">
        <h3>Variant and rollout structure</h3>
        <ul className="list">
          {(displayedAnalysis.report.experiment_design?.variants ?? []).map((variant) => (
            <li key={variant.name}>
              <strong>{variant.name}</strong>: {variant.description}
            </li>
          ))}
        </ul>
      </div>
      <div className="card">
        <h3>Setup</h3>
        <ul className="list">
          <li>
            <strong>Randomization unit:</strong> {String(displayedAnalysis.report.experiment_design?.randomization_unit ?? "-")}
          </li>
          <li>
            <strong>Traffic split:</strong> {String(displayedAnalysis.report.experiment_design?.traffic_split?.join(", ") ?? "-")}
          </li>
          <li>
            <strong>Target audience:</strong> {String(displayedAnalysis.report.experiment_design?.target_audience ?? "-")}
          </li>
          <li>
            <strong>Inclusion:</strong> {String(displayedAnalysis.report.experiment_design?.inclusion_criteria ?? "-")}
          </li>
          <li>
            <strong>Exclusion:</strong> {String(displayedAnalysis.report.experiment_design?.exclusion_criteria ?? "-")}
          </li>
          <li>
            <strong>Recommended duration:</strong> {String(displayedAnalysis.report.experiment_design?.recommended_duration_days ?? "-")} days
          </li>
        </ul>
      </div>
      <div className="card">
        <h3>Stopping conditions</h3>
        <ul className="list">
          {(displayedAnalysis.report.experiment_design?.stopping_conditions ?? []).map((item) => (
            <li key={String(item)}>{String(item)}</li>
          ))}
        </ul>
      </div>
      <div className="card">
        <h3>Open questions</h3>
        <ul className="list">
          {(displayedAnalysis.report.open_questions ?? []).map((item) => (
            <li key={String(item)}>{String(item)}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}
